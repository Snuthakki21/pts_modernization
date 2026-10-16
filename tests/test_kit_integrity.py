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
        ignore_kit_caches = shutil.ignore_patterns(
            ".git", ".implementation", "__pycache__", "programs", "processes",
            "sources", "*.pyc", "tmp*", ".venv", "node_modules", "dist")

        def ignore_local_sources(directory, names):
            ignored = set(ignore_kit_caches(directory, names))
            if Path(directory) == ROOT / "Endevor":
                ignored.update(name for name in names if name != "README.md")
            if Path(directory) == ROOT / "knowledge":
                ignored.add("endevor")
            return ignored

        shutil.copytree(ROOT, self.root, ignore=ignore_local_sources)

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
        notices = json.loads((self.root / ".claude/skill-pack.json").read_text())["notices"]
        def historical(args, **kwargs):
            path = args[-1].split(":", 1)[1]
            content = (json.dumps({"permissions": {"deny": baseline["permissions_deny"]}}).encode()
                       if path == ".claude/settings.json" else notices[baseline["licenses"][path]].encode())
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

    def test_endevor_root_and_knowledge_exclusions_are_required(self):
        self.edit_json("config/project.json", lambda value: value["mainframe"].update(local_source_root="sources"))
        self.assertTrue(any("Endevor folder" in error for error in self.report()["errors"]))
        path = self.root / ".gitignore"
        path.write_text(path.read_text().replace("/knowledge/endevor/\n", ""))
        self.assertTrue(any("must stay ignored" in error for error in self.report()["errors"]))

    def test_missing_new_ui_lock_or_security_artifact_is_reported_explicitly(self):
        for relative in (
            "ui/src/App.jsx", "ui/package-lock.json", "docs/PUBLIC_SITE_DESIGN.md",
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

    def test_graphify_notice_must_match_its_pinned_hash(self):
        self.edit_json(".claude/skill-pack.json", lambda value: value["notices"].update(
            {kit.GRAPHIFY_NOTICES["LICENSE"]: "A substituted license\n"}))
        self.assertTrue(any("Graphify notice hash" in error for error in self.report()["errors"]))

    def test_graphify_notice_reference_cannot_be_replaced_by_a_new_hash(self):
        self.edit_json("config/token-tools.json", lambda value: value["selected"]["license_notices"].update(
            LICENSE="0" * 64))
        self.assertTrue(any("Graphify notice inventory" in error for error in self.report()["errors"]))

    def test_missing_consolidated_notices_fail_even_without_git_history(self):
        self.edit_json(".claude/skill-pack.json", lambda value: value.pop("notices"))
        errors = self.report()["errors"]
        self.assertTrue(any("License changed or missing" in error for error in errors))
        self.assertTrue(any("Graphify notice hash" in error for error in errors))

    def test_graphify_notice_store_cannot_point_away_from_canonical_provenance(self):
        self.edit_json("config/token-tools.json", lambda value: value["selected"].update(
            notice_store="missing-store.json#notices"))
        self.assertTrue(any("Graphify notice store" in error for error in self.report()["errors"]))

    def test_retained_package_notice_reference_and_hash_remain_pinned(self):
        baseline = json.loads((self.root / "config/preservation-baseline.json").read_text())
        expected = baseline["licenses"][".claude/skills/headroom/LICENSE.md"]
        for notice_hash, reference in ((expected, "notices/" + "0" * 64),
                                       ("0" * 64, "notices/" + expected)):
            with self.subTest(reference=reference):
                def update(value):
                    package = next(p for p in value["packages"] if p["name"] == "headroom")
                    package["license"].update(sha256=notice_hash, notice_reference=reference)
                self.edit_json(".claude/skill-pack.json", update)
                self.assertTrue(any("Retained notice binding mismatch" in error
                                    for error in self.report()["errors"]))

    def test_design_reference_is_required_without_rea_distribution(self):
        self.assertTrue((self.root / "docs/PUBLIC_SITE_DESIGN.md").is_file())
        for relative in kit.TEMPORARY_RESEARCH_PATHS:
            self.assertFalse((self.root / relative).exists())
        self.assertEqual([], self.report()["errors"])

    def test_temporary_rea_installation_cannot_be_reintroduced(self):
        for relative in kit.TEMPORARY_RESEARCH_PATHS:
            with self.subTest(path=relative):
                path = self.root / relative
                path.mkdir(parents=True)
                try:
                    self.assertIn(f"Temporary REA research distribution remains: {relative}",
                                  self.report()["errors"])
                finally:
                    path.rmdir()

    def test_authored_design_reference_links_are_checked(self):
        document = self.root / "docs/PUBLIC_SITE_DESIGN.md"
        document.write_text(document.read_text() + "\n[Missing contract](missing-contract.md)\n")
        self.assertIn("Broken link in docs/PUBLIC_SITE_DESIGN.md: missing-contract.md",
                      self.report()["errors"])

    def test_program_source_protection_added_after_historical_baseline_is_preserved(self):
        self.edit_json(".claude/settings.json",
                       lambda value: value["permissions"]["deny"].remove(
                           "Read(//**/programs/*/source/**)"))
        self.assertTrue(any("deny" in error.lower() for error in self.report()["errors"]))

    def test_changed_license_cannot_be_hidden_by_updating_pack_hash(self):
        import hashlib
        baseline = json.loads((self.root / "config/preservation-baseline.json").read_text())
        original_hash = baseline["licenses"][".claude/skills/headroom/LICENSE.md"]
        data = b"Replacement license\n"
        replacement_hash = hashlib.sha256(data).hexdigest()
        def update(value):
            value["notices"].pop(original_hash)
            value["notices"][replacement_hash] = data.decode()
            for package in value["packages"]:
                if package["name"] == "headroom":
                    package["license"].update(sha256=replacement_hash,
                                              notice_reference="notices/" + replacement_hash)
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

    def test_lead_requires_monitoring_cancellation_tools(self):
        path = self.root / ".claude/agents/pts-orchestrator.md"
        path.write_text(path.read_text().replace(", CronDelete", ""))
        self.assertTrue(any("monitoring tools" in error for error in self.report()["errors"]))

    def test_specialists_cannot_create_independent_schedules(self):
        path = self.root / ".claude/agents/pts-backend.md"
        path.write_text(path.read_text().replace("tools: Read,", "tools: CronCreate, Read,"))
        self.assertTrue(any("must not schedule" in error for error in self.report()["errors"]))

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
            CLAUDE_CODE_SUBAGENT_MODEL=identity, ANTHROPIC_DEFAULT_HAIKU_MODEL=identity))
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

    def test_auxiliary_small_fast_model_cannot_use_another_model(self):
        self.edit_json(".claude/settings.json", lambda value: value["env"].update(
            ANTHROPIC_DEFAULT_HAIKU_MODEL="claude-haiku-4-5"))
        self.assertTrue(any("small-fast model" in error for error in self.report()["errors"]))

    def test_auxiliary_small_fast_model_requires_explicit_pin(self):
        self.edit_json(".claude/settings.json", lambda value: value["env"].pop(
            "ANTHROPIC_DEFAULT_HAIKU_MODEL", None))
        self.assertTrue(any("small-fast model" in error for error in self.report()["errors"]))

    def test_automatic_goal_check_ins_cannot_be_enabled_or_left_unset(self):
        for value in ("5", 0, None):
            with self.subTest(value=value):
                def change(settings):
                    if value is None:
                        settings["env"].pop("CLAUDE_CODE_GOAL_CHECKIN_MINUTES", None)
                    else:
                        settings["env"]["CLAUDE_CODE_GOAL_CHECKIN_MINUTES"] = value
                self.edit_json(".claude/settings.json", change)
                self.assertTrue(any("goal check-ins" in error for error in self.report()["errors"]))

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
