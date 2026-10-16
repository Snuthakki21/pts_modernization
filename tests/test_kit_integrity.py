"""Mutate complete kit copies to verify missing-file and policy regressions."""
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("kit_integrity", ROOT / "tools/check_kit.py")
kit = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(kit)


class KitIntegrityTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=ROOT.parent)
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / "archive"
        shutil.copytree(ROOT, self.root, ignore=shutil.ignore_patterns(
            ".git", ".implementation", "__pycache__", "programs", "processes",
            "sources", "*.pyc", "tmp*", ".venv", "node_modules", "dist"))

    def report(self):
        return kit.audit(self.root)

    def edit_json(self, relative, mutate):
        path = self.root / relative
        value = json.loads(path.read_text())
        mutate(value)
        path.write_text(json.dumps(value))

    def test_archive_passes_without_claiming_git_history_was_checked(self):
        report = self.report()
        self.assertEqual([], report["errors"])
        self.assertEqual("pinned_baseline_only", report["preservation_basis"])
        self.assertEqual("not performed", report["runtime_validation"])

    def test_original_history_is_compared_when_available(self):
        (self.root / ".git").mkdir()
        baseline = json.loads((self.root / "config/preservation-baseline.json").read_text())
        def historical(args, **kwargs):
            path = args[-1].split(":", 1)[1]
            content = (json.dumps({"permissions": {"deny": baseline["permissions_deny"]}}).encode()
                       if path == ".claude/settings.json" else (self.root / path).read_bytes())
            return subprocess.CompletedProcess(args, 0, content, b"")
        with patch.object(kit.subprocess, "run", side_effect=historical):
            report = self.report()
        self.assertEqual([], report["errors"])
        self.assertEqual("git_history_and_pinned_baseline", report["preservation_basis"])

    def test_shallow_clone_without_historical_object_uses_pinned_baseline(self):
        (self.root / ".git").mkdir()
        with patch.object(kit.subprocess, "run", return_value=subprocess.CompletedProcess(
                ["git", "show"], 128, b"", b"unknown revision")):
            report = self.report()
        self.assertEqual([], report["errors"])
        self.assertEqual("pinned_baseline_only", report["preservation_basis"])

    def test_missing_required_artifacts_fail_with_the_missing_path(self):
        for relative in (
            "tools/replay_record.py",
            "tests/test_rule_cases.py",
            "examples/PTS_Modernization_Review_Template.xlsx",
            "knowledge/MEMORY.md",
            "docs/OPUS_QUALITY.md",
            "templates/program/design.json",
        ):
            with self.subTest(path=relative):
                path = self.root / relative
                original = path.read_bytes()
                path.unlink()
                try:
                    errors = self.report()["errors"]
                    self.assertTrue(any(relative in item for item in errors), errors)
                finally:
                    path.write_bytes(original)

    def test_removed_historical_deny_fails_even_in_archive(self):
        self.edit_json(".claude/settings.json",
                       lambda value: value["permissions"]["deny"].remove(
                           "Bash(zowe zos-jobs submit *)"))
        self.assertTrue(any("deny" in error.lower() for error in self.report()["errors"]))

    def test_missing_new_ui_lock_or_security_artifact_is_reported_explicitly(self):
        for relative in (
            "ui/src/App.jsx", "ui/package-lock.json", "tools/rea/package-lock.json",
            "docs/SECURITY_REVIEW.md", "config/token-tools.requirements.txt",
        ):
            with self.subTest(path=relative):
                path = self.root / relative
                original = path.read_bytes()
                path.unlink()
                try:
                    self.assertIn(f"Missing required kit file: {relative}", self.report()["errors"])
                finally:
                    path.write_bytes(original)

    def test_graphify_license_must_match_its_declared_hash(self):
        path = self.root / "docs/licenses/graphify/LICENSE"
        path.write_text("A substituted license\n")
        self.assertTrue(any("Graphify license hash" in error for error in self.report()["errors"]))

    def test_upstream_notice_links_are_not_treated_as_authored_kit_links(self):
        notice = self.root / "docs/licenses/rea/THIRD_PARTY_NOTICES.md"
        notice.write_text(notice.read_text() + "\n[Upstream source](src/upstream-only.c)\n")
        authored = self.root / "docs/licenses/rea/PROVENANCE.md"
        authored.write_text(authored.read_text() + "\n[Missing kit contract](missing-contract.md)\n")
        errors = self.report()["errors"]
        self.assertFalse(any("Broken link in docs/licenses/rea/THIRD_PARTY_NOTICES.md" in error
                             for error in errors), errors)
        self.assertIn("Broken link in docs/licenses/rea/PROVENANCE.md: missing-contract.md", errors)

    def test_program_source_protection_added_after_historical_baseline_is_preserved(self):
        self.edit_json(".claude/settings.json",
                       lambda value: value["permissions"]["deny"].remove(
                           "Read(//**/programs/*/source/**)"))
        self.assertTrue(any("deny" in error.lower() for error in self.report()["errors"]))

    def test_changed_license_cannot_be_hidden_by_updating_pack_hash(self):
        import hashlib
        relative = ".claude/skills/headroom/LICENSE.md"
        data = b"Replacement license\n"
        (self.root / relative).write_bytes(data)
        def update(value):
            for package in value["packages"]:
                for item in package["files"]:
                    if item["path"] == relative:
                        item.update(sha256=hashlib.sha256(data).hexdigest(), bytes=len(data))
        self.edit_json(".claude/skill-pack.json", update)
        self.assertTrue(any("License changed" in error for error in self.report()["errors"]))

    def test_modified_preservation_baseline_cannot_relax_policy(self):
        self.edit_json("config/preservation-baseline.json",
                       lambda value: value["permissions_deny"].clear())
        self.assertTrue(any("baseline" in error.lower() for error in self.report()["errors"]))

    def test_missing_baseline_fails_instead_of_trusting_current_settings(self):
        (self.root / "config/preservation-baseline.json").unlink()
        self.assertTrue(any("baseline" in error.lower() for error in self.report()["errors"]))

    def test_worker_model_mismatch_is_not_silently_accepted(self):
        self.edit_json(".claude/settings.json",
                       lambda value: value["env"].update(CLAUDE_CODE_SUBAGENT_MODEL="opus"))
        self.assertTrue(any("Worker model" in error for error in self.report()["errors"]))

    def test_changing_every_model_binding_to_another_model_still_fails(self):
        self.edit_json("config/project.json", lambda value: value["model"].update(id="claude-sonnet-4-6"))
        self.edit_json(".claude/settings.json", lambda value: value.update(model="claude-sonnet-4-6"))
        self.edit_json(".claude/settings.json", lambda value: value["env"].update(
            CLAUDE_CODE_SUBAGENT_MODEL="claude-sonnet-4-6"))
        for path in (self.root / ".claude/agents").glob("*.md"):
            path.write_text(path.read_text().replace("model: claude-opus-4-7", "model: claude-sonnet-4-6"))
        self.assertTrue(any("approved Opus" in error for error in self.report()["errors"]))

    def test_confirmed_managed_deployment_can_keep_its_explicit_binding(self):
        identity = "enterprise-opus47-deployment"
        self.edit_json("config/project.json", lambda value: value["model"].update(
            id=identity, provider="enterprise_gateway", provider_binding_confirmed=True,
            deployment_mapping_reference="approved deployment receipt DEPLOY-47"))
        self.edit_json(".claude/settings.json", lambda value: value.update(model=identity))
        self.edit_json(".claude/settings.json", lambda value: value["env"].update(
            CLAUDE_CODE_SUBAGENT_MODEL=identity))
        for path in (self.root / ".claude/agents").glob("*.md"):
            path.write_text(path.read_text().replace("model: claude-opus-4-7", f"model: {identity}"))
        self.assertEqual([], self.report()["errors"])
        self.edit_json("config/project.json", lambda value: value["model"].update(
            provider_binding_confirmed=False))
        self.assertTrue(any("mapping" in error.lower() for error in self.report()["errors"]))

    def test_effort_and_concurrency_must_match_project_binding(self):
        self.edit_json(".claude/settings.json", lambda value: value.update(effortLevel="low"))
        self.edit_json(".claude/settings.json", lambda value: value["env"].update(
            CLAUDE_CODE_MAX_CONCURRENT_SUBAGENTS="8"))
        errors = self.report()["errors"]
        self.assertTrue(any("effort" in error.lower() for error in errors), errors)
        self.assertTrue(any("concurrency" in error.lower() for error in errors), errors)

    def test_explicit_environment_model_cannot_override_approved_binding(self):
        self.edit_json(".claude/settings.json", lambda value: value["env"].update(
            ANTHROPIC_MODEL="claude-sonnet-4-6"))
        self.assertTrue(any("environment model" in error.lower() for error in self.report()["errors"]))

    def test_explicit_fallback_models_are_rejected(self):
        self.edit_json(".claude/settings.json", lambda value: value.update(
            fallbackModel=["claude-sonnet-4-6"]))
        self.assertTrue(any("fallback" in error.lower() for error in self.report()["errors"]))

    def test_environment_effort_cannot_override_project_quality(self):
        self.edit_json(".claude/settings.json", lambda value: value["env"].update(
            CLAUDE_CODE_EFFORT_LEVEL="low"))
        self.assertTrue(any("environment effort" in error.lower() for error in self.report()["errors"]))

    def test_ultracode_cannot_bypass_worker_limit(self):
        self.edit_json(".claude/settings.json", lambda value: value.update(ultracode=True))
        self.assertTrue(any("ultracode" in error.lower() for error in self.report()["errors"]))

    def test_explicit_environment_values_matching_project_are_allowed(self):
        self.edit_json(".claude/settings.json", lambda value: value["env"].update(
            ANTHROPIC_MODEL="claude-opus-4-7", CLAUDE_CODE_EFFORT_LEVEL="xhigh"))
        self.edit_json(".claude/settings.json", lambda value: value.update(
            ultracode=False, fallbackModel=[]))
        self.assertEqual([], self.report()["errors"])

    def test_agent_requires_nonempty_description(self):
        path = self.root / ".claude/agents/pts-qa.md"
        original = path.read_text()
        for replacement in (
            "", "description: \n", "description: # explanation pending\n",
            "description: |\n", "description: >\n",
        ):
            with self.subTest(replacement=replacement):
                path.write_text("\n".join(replacement.rstrip("\n") if line.startswith("description:")
                                          else line for line in original.split("\n")))
                errors = self.report()["errors"]
                self.assertTrue(any("description" in error.lower() for error in errors), errors)

    def test_agent_requires_closing_frontmatter_delimiter(self):
        path = self.root / ".claude/agents/pts-qa.md"
        original = path.read_text()
        opening, body = original[4:].split("\n---\n", 1)
        path.write_text("---\n" + opening + "\n" + body)
        self.assertTrue(any("frontmatter" in error.lower() for error in self.report()["errors"]))

    def test_root_memory_import_is_required(self):
        path = self.root / "CLAUDE.md"
        path.write_text(path.read_text().replace("@knowledge/MEMORY.md", "knowledge/MEMORY.md"))
        self.assertTrue(any("memory import" in error.lower() for error in self.report()["errors"]))

    def test_retained_pack_entry_cannot_be_removed(self):
        self.edit_json(".claude/skill-pack.json", lambda value: value["packages"].pop())
        self.assertTrue(any("Retained package" in error for error in self.report()["errors"]))

    def test_git_unavailable_falls_back_to_verified_baseline(self):
        (self.root / ".git").mkdir()
        with patch.object(kit.subprocess, "run", side_effect=FileNotFoundError("git")) as run:
            report = self.report()
        run.assert_called_once()
        self.assertEqual([], report["errors"])
        self.assertEqual("pinned_baseline_only", report["preservation_basis"])


if __name__ == "__main__":
    unittest.main()
