"""First-use state creation must never reset or overwrite ongoing work."""
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch


SPEC = importlib.util.spec_from_file_location(
    "pts_init_workspace", Path(__file__).resolve().parents[1] / "tools/init_workspace.py")
workspace = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(workspace)


class WorkspaceInitializationTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name) / "repo"
        self.root.mkdir()

    def tearDown(self):
        self.temporary.cleanup()

    def load(self, name):
        return json.loads((self.root / name).read_text(encoding="utf-8"))

    def test_root_seed_contains_no_invented_programs_or_budget(self):
        result = workspace.initialize(self.root)
        self.assertEqual(result["status"], "initialized")
        self.assertEqual(len(result["created_files"]), 4)
        self.assertEqual(self.load("inventory.json")["programs"], [])
        self.assertEqual(self.load("inventory.json")["processes"], [])
        self.assertIsNone(self.load("knowledge/handoff.json")["repair_budget"]["configured_cycles_per_program"])
        self.assertFalse((self.root / "programs").exists())
        self.assertFalse((self.root / "processes").exists())

    def test_supplied_identifiers_create_only_their_scaffolds(self):
        result = workspace.initialize(self.root, program_ids=["PAY01"], process_ids=["DAILY"])
        self.assertEqual(result["status"], "initialized")
        self.assertEqual(self.load("programs/PAY01/analysis/design.json")["program_id"], "PAY01")
        self.assertEqual(self.load("programs/PAY01/analysis/source-map.json")["source_units"], [])
        self.assertEqual(self.load("processes/DAILY/process.json")["steps"], [])
        self.assertEqual(self.load("inventory.json")["programs"], [])
        for relative in ("programs/PAY01/source", "programs/PAY01/target",
                         "programs/PAY01/tests", "programs/PAY01/runs",
                         "processes/DAILY/integration/runs"):
            self.assertTrue((self.root / relative).is_dir(), relative)

    def test_repeat_preserves_decisions_budget_and_exact_bytes(self):
        workspace.initialize(self.root, program_ids=["P1"])
        handoff = self.load("knowledge/handoff.json")
        handoff["repair_budget"] = {"configured_cycles_per_program": 2,
                                    "remaining_by_program": {"P1": 0}}
        handoff["status"] = "blocked"
        handoff_path = self.root / "knowledge/handoff.json"
        handoff_path.write_text(json.dumps(handoff, indent=4) + "\n", encoding="utf-8")
        decisions = self.load("knowledge/decisions.json")
        decisions["decisions"].append({"decision_id": "D1", "accepted": True})
        decisions_path = self.root / "knowledge/decisions.json"
        decisions_path.write_text(json.dumps(decisions), encoding="utf-8")
        before = {p: p.read_bytes() for p in (handoff_path, decisions_path)}
        result = workspace.initialize(self.root, program_ids=["P1"])
        self.assertEqual(result["status"], "unchanged")
        self.assertEqual(result["created_files"], [])
        self.assertEqual(before, {p: p.read_bytes() for p in before})

    def test_invalid_identifiers_fail_before_writing(self):
        for value in ("", "../escape", "a/b", "a\\b", ".", "..", "CON", "nul", "COM1", "a" * 65):
            with self.subTest(value=value), self.assertRaises(ValueError):
                workspace.initialize(self.root, program_ids=[value])
            self.assertEqual(list(self.root.iterdir()), [])

    def test_case_collisions_are_not_portable_identifiers(self):
        with self.assertRaises(ValueError):
            workspace.initialize(self.root, program_ids=["Pay1", "PAY1"])
        self.assertEqual(list(self.root.iterdir()), [])

    def test_existing_case_colliding_directory_blocks_creation(self):
        (self.root / "programs/PAY1").mkdir(parents=True)
        with self.assertRaises(ValueError):
            workspace.initialize(self.root, program_ids=["pay1"])
        self.assertFalse((self.root / "inventory.json").exists())

    def test_missing_or_non_directory_root_is_rejected(self):
        with self.assertRaises(ValueError):
            workspace.initialize(self.root / "missing")
        path = self.root / "file"
        path.write_text("existing", encoding="utf-8")
        with self.assertRaises(ValueError):
            workspace.initialize(path)

    def test_symlink_root_is_rejected(self):
        alias = self.root.parent / "alias"
        alias.symlink_to(self.root, target_is_directory=True)
        with self.assertRaises(ValueError):
            workspace.initialize(alias)
        self.assertEqual(list(self.root.iterdir()), [])

    def test_symlink_parent_is_rejected_without_touching_outside(self):
        outside = self.root.parent / "outside"
        outside.mkdir()
        (self.root / "knowledge").symlink_to(outside, target_is_directory=True)
        with self.assertRaises(ValueError):
            workspace.initialize(self.root)
        self.assertEqual(list(outside.iterdir()), [])
        self.assertFalse((self.root / "inventory.json").exists())

    def test_symlink_or_hardlink_target_is_preserved_and_rejected(self):
        outside = self.root.parent / "outside.json"
        outside.write_text('{"schema_version":1,"programs":[],"processes":[],"status":"unverified"}', encoding="utf-8")
        target = self.root / "inventory.json"
        target.symlink_to(outside)
        with self.assertRaises(ValueError):
            workspace.initialize(self.root)
        target.unlink()
        target.hardlink_to(outside)
        before = outside.read_bytes()
        with self.assertRaises(ValueError):
            workspace.initialize(self.root)
        self.assertEqual(outside.read_bytes(), before)

    def test_incompatible_existing_state_blocks_all_creation(self):
        (self.root / "knowledge").mkdir()
        handoff = self.root / "knowledge/handoff.json"
        handoff.write_text('{"schema_version":0,"remaining_repairs":0}', encoding="utf-8")
        before = handoff.read_bytes()
        with self.assertRaisesRegex(ValueError, "preserved"):
            workspace.initialize(self.root, program_ids=["P1"])
        self.assertEqual(handoff.read_bytes(), before)
        self.assertFalse((self.root / "inventory.json").exists())
        self.assertFalse((self.root / "programs").exists())

    def test_wrong_existing_program_identity_cannot_be_reused(self):
        workspace.initialize(self.root, program_ids=["P1"])
        path = self.root / "programs/P1/program.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        data["program_id"] = "OTHER"
        path.write_text(json.dumps(data), encoding="utf-8")
        with self.assertRaises(ValueError):
            workspace.initialize(self.root, program_ids=["P1"], process_ids=["NEW"])
        self.assertFalse((self.root / "processes").exists())

    def test_write_failure_reports_partial_creation_without_overwriting(self):
        original = workspace._write_new
        calls = []

        def fail_second(path, content):
            calls.append(path)
            if len(calls) == 2:
                raise OSError("synthetic write failure")
            return original(path, content)

        with patch.object(workspace, "_write_new", side_effect=fail_second):
            result = workspace.initialize(self.root)
        self.assertEqual(result["status"], "partial")
        self.assertEqual(len(result["created_files"]), 1)
        first = self.root / result["created_files"][0]
        before = first.read_bytes()
        self.assertEqual(workspace.initialize(self.root)["status"], "initialized")
        self.assertEqual(first.read_bytes(), before)

    def test_target_appearing_after_preflight_is_never_overwritten(self):
        original = workspace._write_new

        def competing_writer(path, content):
            path.write_text("concurrent existing content", encoding="utf-8")
            return original(path, content)

        with patch.object(workspace, "_write_new", side_effect=competing_writer):
            result = workspace.initialize(self.root)
        self.assertEqual(result["status"], "partial")
        self.assertEqual(result["created_files"], [])
        self.assertEqual((self.root / "inventory.json").read_text(encoding="utf-8"),
                         "concurrent existing content")


if __name__ == "__main__":
    unittest.main()
