"""Synthetic contract tests for the offline migration view, not ETL acceptance."""
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch


SCRIPT = Path(__file__).resolve().parents[1] / "tools" / "render_migration.py"
BEGIN = b"<!-- BEGIN GENERATED MIGRATION FACTS -->"
END = b"<!-- END GENERATED MIGRATION FACTS -->"


class RendererTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.inventory_path = self.root / "inventory.json"
        self.map_path = self.root / "source-map.json"
        self.output = self.root / "docs" / "migration.md"
        self.output.parent.mkdir()
        self.original = b"Human notes\r\n\xc3\xa9\r\n" + BEGIN + b"\nold\n" + END + b"\r\nKeep me\x00\n"
        self.output.write_bytes(self.original)
        artifact = self.root / "artifacts" / "etl.py"
        artifact.parent.mkdir()
        artifact.write_bytes(b"# synthetic fixture\n")
        self.digest = hashlib.sha256(artifact.read_bytes()).hexdigest()
        self.inventory = {"programs": [{
            "program_id": "P1",
            "consumers": [{"process_id": "PROC1", "step_id": "STEP1",
                           "provider": "python", "version": "v1"}],
            "migrations": [self.migration("MIG-A")],
        }]}
        self.source_map = {"program_id": "P1", "source_units": [{"source_id": "SRC1"}],
                           "rules": [], "migrations": [{"migration_id": "MIG-A", "source_ids": ["SRC1"]}]}

    def migration(self, identifier, dependencies=()):
        return {"migration_id": identifier, "proposed_name": "Project rows", "stage": "identified",
                "blocker": "", "depends_on": list(dependencies),
                "artifacts": [{"path": "artifacts/etl.py", "sha256": self.digest, "state": "provided"}],
                "python_symbols": ["etl.project"], "retain_python": ["rules.decide"]}

    def add_migration(self, identifier, dependencies=()):
        self.inventory["programs"][0]["migrations"].append(self.migration(identifier, dependencies))
        self.source_map["migrations"].append({"migration_id": identifier, "source_ids": ["SRC1"]})

    def run_renderer(self, *extra):
        self.inventory_path.write_text(json.dumps(self.inventory), encoding="utf-8")
        self.map_path.write_text(json.dumps(self.source_map), encoding="utf-8")
        return subprocess.run([sys.executable, str(SCRIPT), "--inventory", str(self.inventory_path),
                               "--source-map", str(self.map_path), "--output", str(self.output), *extra],
                              capture_output=True, text=True, check=False)

    def successful_output(self):
        result = self.run_renderer()
        self.assertEqual(result.returncode, 0, result.stderr)
        return self.output.read_bytes().decode("utf-8")

    def assert_rejected(self, message):
        result = self.run_renderer()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn(message, result.stderr)
        self.assertEqual(self.output.read_bytes(), self.original)

    def test_refresh_preserves_commentary_and_is_idempotent(self):
        text = self.successful_output()
        rendered = self.output.read_bytes()
        self.assertEqual(rendered.split(BEGIN)[0], self.original.split(BEGIN)[0])
        self.assertEqual(rendered.split(END)[1], self.original.split(END)[1])
        for value in ["P1", "PROC1", "STEP1", "python", "v1", "etl.project", "rules.decide", "SRC1",
                      "../artifacts/etl.py", self.digest, "provided", "Blocker count: 0"]:
            self.assertIn(value, text)
        for path in [self.inventory_path, self.map_path]:
            self.assertIn(hashlib.sha256(path.read_bytes()).hexdigest(), text)
        self.successful_output()
        self.assertEqual(self.output.read_bytes(), rendered)

    def test_dependency_order_is_deterministic(self):
        self.add_migration("MIG-C", ["MIG-B"])
        self.add_migration("MIG-B", ["MIG-A"])
        text = self.successful_output()
        self.assertIn("1. MIG-A\n2. MIG-B\n3. MIG-C", text)
        # Reordering source mappings has no semantic effect apart from the input fingerprint.
        before = text.split("### Dependency order", 1)[1]
        self.source_map["migrations"].reverse()
        self.inventory["programs"][0]["migrations"].reverse()
        self.assertEqual(before, self.successful_output().split("### Dependency order", 1)[1])

    def test_cycles_and_descendants_are_explicitly_blocked(self):
        self.inventory["programs"][0]["migrations"][0]["depends_on"] = ["MIG-B"]
        self.add_migration("MIG-B", ["MIG-A"])
        self.add_migration("MIG-C", ["MIG-B"])
        self.add_migration("MIG-D")
        text = self.successful_output()
        self.assertIn("Cycle group: MIG-A, MIG-B", text)
        self.assertIn("MIG-C: blocked by cycle dependency", text)
        self.assertIn("1. MIG-D", text)
        self.assertIn("Blocker count: 3", text)

    def test_self_cycle_and_separate_cycle_groups(self):
        self.inventory["programs"][0]["migrations"][0]["depends_on"] = ["MIG-A"]
        self.add_migration("MIG-B", ["MIG-C"])
        self.add_migration("MIG-C", ["MIG-B"])
        self.add_migration("MIG-D", ["MIG-A", "MIG-B"])
        text = self.successful_output()
        self.assertIn("Cycle group: MIG-A.", text)
        self.assertIn("Cycle group: MIG-B, MIG-C.", text)
        self.assertIn("MIG-D: blocked by cycle dependency", text)
        self.assertIn("Blocker count: 4", text)

    def test_cross_program_dependency_and_multiple_source_maps(self):
        other = self.migration("MIG-B", ["MIG-A"])
        self.inventory["programs"].append({"program_id": "P2", "consumers": [], "migrations": [other]})
        other_map = self.root / "source-map-p2.json"
        other_map.write_text(json.dumps({"program_id": "P2", "source_units": [{"source_id": "SRC2"}],
                                        "rules": [], "migrations": [{"migration_id": "MIG-B", "source_ids": ["SRC2"]}]}))
        result = self.run_renderer("--source-map", str(other_map))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("1. MIG-A\n2. MIG-B", self.output.read_text())
        self.assertIn("SRC2", self.output.read_text())

    def test_stale_and_missing_artifacts_downgrade_declared_state(self):
        (self.root / "artifacts" / "etl.py").write_bytes(b"modified\n")
        text = self.successful_output()
        self.assertIn("stale", text)
        self.assertIn("SHA-256 mismatch", text)
        self.assertIn("Blocker count: 1", text)
        (self.root / "artifacts" / "etl.py").unlink()
        text = self.successful_output()
        self.assertIn("missing", text)
        self.assertIn("not found", text)

    def test_unpinned_and_deferred_artifacts_never_claim_provided(self):
        artifact = self.inventory["programs"][0]["migrations"][0]["artifacts"][0]
        artifact["sha256"] = None
        text = self.successful_output()
        self.assertIn("unpinned", text)
        self.assertIn("stale", text)
        artifact["state"] = "deferred"
        self.assertIn("deferred", self.successful_output())

    def test_duplicate_program_and_migration_ids_are_rejected(self):
        self.inventory["programs"].append(copy.deepcopy(self.inventory["programs"][0]))
        self.assert_rejected("duplicate program_id")
        self.inventory["programs"].pop()
        self.inventory["programs"][0]["migrations"].append(self.migration("MIG-A"))
        self.assert_rejected("duplicate migration_id")

    def test_unknown_dependency_is_rejected(self):
        self.inventory["programs"][0]["migrations"][0]["depends_on"] = ["MIG-UNKNOWN"]
        self.assert_rejected("unknown dependency")

    def test_missing_source_mapping_and_unknown_source_ids_are_rejected(self):
        self.source_map["migrations"] = []
        self.assert_rejected("missing source mapping")
        self.source_map["migrations"] = [{"migration_id": "MIG-A", "source_ids": ["UNKNOWN"]}]
        self.assert_rejected("unknown source_id")

    def test_markdown_input_is_literal_and_artifact_link_is_encoded(self):
        migration = self.inventory["programs"][0]["migrations"][0]
        migration["proposed_name"] = "[run](javascript:evil)|<img src=x>\n# injected"
        renamed = self.root / "artifacts" / "a [b](c).py"
        (self.root / "artifacts" / "etl.py").rename(renamed)
        migration["artifacts"][0]["path"] = "artifacts/a [b](c).py"
        text = self.successful_output()
        self.assertNotIn("<img", text)
        self.assertNotIn("[run](", text)
        self.assertNotIn("\n# injected", text)
        self.assertIn("a%20%5Bb%5D%28c%29.py", text)

    def test_external_and_escaping_artifact_paths_are_rejected(self):
        artifact = self.inventory["programs"][0]["migrations"][0]["artifacts"][0]
        for path in ["https://example.org/flow.json", "../outside.py", "/tmp/outside.py"]:
            with self.subTest(path=path):
                artifact["path"] = path
                self.assert_rejected("artifact path")

    def test_artifact_symlink_cannot_escape_inventory_root(self):
        with tempfile.TemporaryDirectory() as other:
            outside = Path(other) / "outside.py"
            outside.write_text("private fixture")
            (self.root / "link.py").symlink_to(outside)
            self.inventory["programs"][0]["migrations"][0]["artifacts"][0]["path"] = "link.py"
            self.assert_rejected("artifact path")

    def test_output_cannot_overlap_canonical_inputs_or_artifacts(self):
        self.inventory["programs"][0]["migrations"][0]["artifacts"][0]["path"] = "docs/migration.md"
        self.assert_rejected("output overlaps")
        self.inventory["programs"][0]["migrations"][0]["artifacts"][0]["path"] = "artifacts/etl.py"
        result = self.run_renderer("--output", str(self.inventory_path))
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("output overlaps", result.stderr)
        self.assertEqual(json.loads(self.inventory_path.read_text()), self.inventory)

    def test_hardlinked_output_artifact_is_rejected(self):
        artifact = self.root / "artifacts" / "etl.py"
        artifact.unlink()
        artifact.hardlink_to(self.output)
        self.assert_rejected("output overlaps")

    def test_duplicate_source_ids_are_rejected(self):
        self.source_map["source_units"].append({"source_id": "SRC1"})
        self.assert_rejected("duplicate source_id")

    def test_missing_or_duplicate_markers_reject_without_writes(self):
        for value in [b"notes only", BEGIN + END + END, END + BEGIN]:
            with self.subTest(value=value):
                self.original = value
                self.output.write_bytes(value)
                self.assert_rejected("markers")

    def test_empty_inventory_does_not_invent_candidates(self):
        self.inventory = {"programs": []}
        self.inventory_path.write_text(json.dumps(self.inventory))
        result = subprocess.run([sys.executable, str(SCRIPT), "--inventory", str(self.inventory_path),
                                 "--output", str(self.output)], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("No migration candidates supplied", self.output.read_text())

    def test_atomic_replace_failure_leaves_original_document(self):
        self.inventory_path.write_text(json.dumps(self.inventory))
        self.map_path.write_text(json.dumps(self.source_map))
        spec = importlib.util.spec_from_file_location("render_migration", SCRIPT)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        with patch.object(module.os, "replace", side_effect=OSError("simulated failure")):
            with self.assertRaisesRegex(OSError, "simulated failure"):
                module.refresh(self.inventory_path, [self.map_path], self.output)
        self.assertEqual(self.output.read_bytes(), self.original)
        self.assertEqual(list(self.output.parent.iterdir()), [self.output])


if __name__ == "__main__":
    unittest.main()
