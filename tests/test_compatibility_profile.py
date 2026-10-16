"""Synthetic, offline contract checks for the compatibility-profile gate."""
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch


TOOL = Path(__file__).resolve().parents[1] / "tools/compatibility_profile.py"
DOMAINS = ("numeric", "characters", "layouts", "initialization", "dates",
           "database", "ordering", "errors")


def digest(data):
    return hashlib.sha256(data).hexdigest()


class CompatibilityProfileTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        (self.root / "source.cbl").write_text(
            "SYNTHETIC SOURCE ONLY\nEXPLICIT DOMAIN CONTRACT\n", encoding="utf-8")
        (self.root / "fixture.json").write_text('{"input": 1, "expected": 1}\n')

    def cli(self, command, *extra):
        result = subprocess.run(
            [sys.executable, str(TOOL), command, "--root", str(self.root),
             "--design", "design.json", "--program", "DEMO", *extra],
            capture_output=True, text=True, check=False)
        self.assertEqual(result.stderr, "", result.stderr)
        return result.returncode, json.loads(result.stdout)

    def initialize(self):
        code, output = self.cli("init", "--source", "source.cbl")
        self.assertEqual(code, 0, output)
        return json.loads((self.root / "design.json").read_text())

    def save(self, design):
        (self.root / "design.json").write_text(json.dumps(design), encoding="utf-8")

    def resolved(self):
        design = self.initialize()
        profile = design["compatibility"]
        for domain, entry in profile["semantics"].items():
            entry.update({
                "applicability": "applicable",
                "behavior": f"Synthetic {domain} contract returns its input unchanged.",
                "source_refs": [{"path": "source.cbl", "start_line": 1, "end_line": 2}],
                "runtime_settings": {"synthetic_mode": "identity"},
                "fixture_refs": [{"path": "fixture.json", "sha256": digest(
                    (self.root / "fixture.json").read_bytes())}],
            })
            spec = importlib.util.spec_from_file_location("compatibility_profile", TOOL)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            proof = {
                "schema_version": 1, "program_id": "DEMO", "domain": domain,
                "semantic_sha256": module.semantic_digest(entry),
                "source_fingerprints": profile["source_fingerprints"],
                "tests": [{"id": f"{domain}-identity", "fixture_path": "fixture.json",
                           "status": "passed"}],
            }
            path = self.root / f"{domain}-result.json"
            path.write_text(json.dumps(proof), encoding="utf-8")
            entry["proof"] = {"path": path.name, "sha256": digest(path.read_bytes())}
        self.save(design)
        return design

    def test_initializer_preserves_design_and_never_passes(self):
        self.save({"program_id": "DEMO", "decisions": [{"id": "existing"}]})
        design = self.initialize()
        self.assertEqual(design["decisions"], [{"id": "existing"}])
        self.assertEqual(set(design["compatibility"]["semantics"]), set(DOMAINS))
        code, output = self.cli("check")
        self.assertEqual(code, 1)
        self.assertEqual(output["compatibility"], "unverified")
        self.assertTrue(any("unknown" in error for error in output["errors"]))

    def test_initializer_refuses_existing_profile(self):
        self.initialize()
        original = (self.root / "design.json").read_bytes()
        code, _ = self.cli("init", "--source", "source.cbl")
        self.assertEqual(code, 1)
        self.assertEqual((self.root / "design.json").read_bytes(), original)

    def test_initializer_rejects_hardlink_to_source_without_changing_either_file(self):
        design = self.root / "design.json"
        source = self.root / "source.json"
        design.write_bytes(b'{"program_id":"DEMO"}\n')
        source.hardlink_to(design)
        original = design.read_bytes()
        code, output = self.cli("init", "--source", "source.json")
        self.assertEqual(code, 1, output)
        self.assertTrue(any("source" in error for error in output["errors"]))
        self.assertEqual(design.read_bytes(), original)
        self.assertEqual(source.read_bytes(), original)

    def test_overflow_numbers_are_rejected_recursively_in_not_applicable_entries(self):
        design = self.initialize()
        for entry in design["compatibility"]["semantics"].values():
            entry.update({"applicability": "not_applicable", "behavior": "No operation of this domain.",
                          "source_refs": [{"path": "source.cbl", "start_line": 1, "end_line": 1}]})
        entry = design["compatibility"]["semantics"]["numeric"]
        for token in ("1e999", "-1e999", "NaN", "Infinity", "-Infinity"):
            with self.subTest(token=token):
                entry["runtime_settings"] = {"nested": [{"number": "NUMBER_TOKEN"}]}
                (self.root / "design.json").write_text(json.dumps(design).replace('"NUMBER_TOKEN"', token))
                code, output = self.cli("check")
                self.assertEqual(code, 1, output)
                self.assertEqual(output["compatibility"], "unverified")

    def test_initializer_atomic_write_failure_preserves_existing_design(self):
        self.save({"program_id": "DEMO", "decisions": ["keep"]})
        design = self.root / "design.json"
        original = design.read_bytes()
        spec = importlib.util.spec_from_file_location("compatibility_profile", TOOL)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        with patch.object(module.os, "replace", side_effect=OSError("simulated failure")):
            with self.assertRaisesRegex(OSError, "simulated failure"):
                module.initialize(self.root, design, "DEMO", ["source.cbl"])
        self.assertEqual(design.read_bytes(), original)
        self.assertEqual(set(path.name for path in self.root.iterdir()), {"design.json", "source.cbl", "fixture.json"})

    def test_initializer_does_not_overwrite_concurrently_changed_design(self):
        self.save({"program_id": "DEMO", "decisions": ["before"]})
        design = self.root / "design.json"
        newer = b'{"program_id":"DEMO","decisions":["concurrent update"]}'
        spec = importlib.util.spec_from_file_location("compatibility_profile", TOOL)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        def concurrent_update(_descriptor):
            design.write_bytes(newer)
        with patch.object(module.os, "fsync", side_effect=concurrent_update):
            with self.assertRaisesRegex(ValueError, "changed during"):
                module.initialize(self.root, design, "DEMO", ["source.cbl"])
        self.assertEqual(design.read_bytes(), newer)
        self.assertEqual(set(path.name for path in self.root.iterdir()), {"design.json", "source.cbl", "fixture.json"})

    def test_resolved_profile_passes(self):
        self.resolved()
        code, output = self.cli("check")
        self.assertEqual(code, 0, output)
        self.assertEqual(output["compatibility"], "verified")

    def test_stale_source_fingerprint_fails(self):
        self.resolved()
        (self.root / "source.cbl").write_text("CHANGED SYNTHETIC SOURCE\n")
        code, output = self.cli("check")
        self.assertEqual(code, 1)
        self.assertTrue(any("sha256 mismatch" in e for e in output["errors"]))

    def test_missing_or_changed_fixture_fails(self):
        self.resolved()
        fixture = self.root / "fixture.json"
        fixture.write_text("{}\n")
        code, output = self.cli("check")
        self.assertEqual(code, 1)
        self.assertTrue(any("sha256 mismatch" in e for e in output["errors"]))
        fixture.unlink()
        code, output = self.cli("check")
        self.assertEqual(code, 1)
        self.assertTrue(any("not a file" in e for e in output["errors"]))

    def test_not_applicable_requires_reason_and_source_evidence(self):
        design = self.resolved()
        entry = design["compatibility"]["semantics"]["database"]
        entry.update({"applicability": "not_applicable", "behavior": "",
                      "source_refs": [], "fixture_refs": [], "proof": None})
        self.save(design)
        code, _ = self.cli("check")
        self.assertEqual(code, 1)
        entry.update({"behavior": "Synthetic source has no database access.",
                      "source_refs": [{"path": "source.cbl", "start_line": 1, "end_line": 2}]})
        self.save(design)
        code, output = self.cli("check")
        self.assertEqual(code, 0, output)

    def test_semantic_edit_invalidates_old_proof(self):
        design = self.resolved()
        design["compatibility"]["semantics"]["numeric"]["behavior"] = "Now add one."
        self.save(design)
        code, output = self.cli("check")
        self.assertEqual(code, 1)
        self.assertTrue(any("semantic_sha256 mismatch" in e for e in output["errors"]))

    def test_missing_and_failed_proof_fail(self):
        design = self.resolved()
        entry = design["compatibility"]["semantics"]["errors"]
        proof_file = self.root / entry["proof"]["path"]
        proof = json.loads(proof_file.read_text())
        proof["tests"][0]["status"] = "failed"
        proof_file.write_text(json.dumps(proof))
        entry["proof"]["sha256"] = digest(proof_file.read_bytes())
        self.save(design)
        code, output = self.cli("check")
        self.assertEqual(code, 1)
        self.assertTrue(any("passed" in e for e in output["errors"]))
        proof_file.unlink()
        code, _ = self.cli("check")
        self.assertEqual(code, 1)

    def test_digest_binds_runtime_settings_and_stale_receipt_bytes_fail(self):
        design = self.resolved()
        entry = design["compatibility"]["semantics"]["numeric"]
        code, output = self.cli("digest", "--domain", "numeric")
        self.assertEqual(code, 0, output)
        proof_file = self.root / entry["proof"]["path"]
        proof = json.loads(proof_file.read_text())
        self.assertEqual(output["semantic_sha256"], proof["semantic_sha256"])
        entry["runtime_settings"]["synthetic_mode"] = "changed"
        self.save(design)
        code, output = self.cli("check")
        self.assertEqual(code, 1)
        self.assertTrue(any("semantic_sha256 mismatch" in e for e in output["errors"]))
        proof_file.write_text(json.dumps(proof) + "\n")
        code, output = self.cli("check")
        self.assertEqual(code, 1)
        self.assertTrue(any("sha256 mismatch" in e for e in output["errors"]))

    def test_source_bytes_cannot_be_used_as_fixture_evidence(self):
        design = self.resolved()
        entry = design["compatibility"]["semantics"]["numeric"]
        copied_source = self.root / "copied-source.json"
        copied_source.write_bytes((self.root / "source.cbl").read_bytes())
        entry["fixture_refs"] = [{"path": copied_source.name,
                                   "sha256": digest(copied_source.read_bytes())}]
        self.save(design)
        code, output = self.cli("check")
        self.assertEqual(code, 1)
        self.assertTrue(any("source bytes" in e for e in output["errors"]))

    def test_missing_domain_and_malformed_profile_fail_cleanly(self):
        design = self.resolved()
        del design["compatibility"]["semantics"]["numeric"]
        self.save(design)
        code, output = self.cli("check")
        self.assertEqual(code, 1)
        self.assertTrue(any("exactly" in e for e in output["errors"]))
        design["compatibility"]["semantics"] = []
        self.save(design)
        code, output = self.cli("check")
        self.assertEqual(code, 1)
        self.assertTrue(any("object" in e for e in output["errors"]))

    def test_program_mismatch_fails(self):
        self.save({"program_id": "OTHER"})
        code, _ = self.cli("init", "--source", "source.cbl")
        self.assertEqual(code, 1)
        (self.root / "design.json").unlink()
        design = self.resolved()
        design["compatibility"]["program_id"] = "OTHER"
        self.save(design)
        code, _ = self.cli("check")
        self.assertEqual(code, 1)

    def test_escape_paths_and_symlinks_are_rejected(self):
        code, _ = self.cli("init", "--source", "../outside.cbl")
        self.assertEqual(code, 1)
        with tempfile.TemporaryDirectory() as outside:
            external = Path(outside) / "outside.cbl"
            external.write_text("SYNTHETIC OUTSIDE SOURCE\n")
            (self.root / "escape.cbl").symlink_to(external)
            code, _ = self.cli("init", "--source", "escape.cbl")
            self.assertEqual(code, 1)
        design = self.resolved()
        design["compatibility"]["semantics"]["numeric"]["fixture_refs"][0]["path"] = "../outside.json"
        self.save(design)
        code, output = self.cli("check")
        self.assertEqual(code, 1)
        self.assertTrue(any("relative" in e for e in output["errors"]))

    def test_invalid_source_span_and_unbound_source_fail(self):
        design = self.resolved()
        entry = design["compatibility"]["semantics"]["numeric"]
        entry["source_refs"][0]["end_line"] = 100
        self.save(design)
        code, output = self.cli("check")
        self.assertEqual(code, 1)
        self.assertTrue(any("line span" in e for e in output["errors"]))
        entry["source_refs"][0]["path"] = "unapproved.cbl"
        self.save(design)
        code, output = self.cli("check")
        self.assertEqual(code, 1)
        self.assertTrue(any("source_fingerprints" in e for e in output["errors"]))


if __name__ == "__main__":
    unittest.main()
