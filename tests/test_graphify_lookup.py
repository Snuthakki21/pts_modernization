"""Boundary checks do not require the optional Graphify runtime."""
import importlib.util
import os
from pathlib import Path
import tempfile
import unittest

SPEC = importlib.util.spec_from_file_location("graphify_lookup", Path(__file__).parents[1] / "tools/graphify_lookup.py")
lookup = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(lookup)


class GraphifyLookupTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.file = self.root / "examples/demo.py"
        self.file.parent.mkdir()
        self.file.write_text("def rule():\n    return 1\n")

    def test_explicit_example_allowed(self):
        self.assertEqual(lookup.approved_file(self.root, "examples/demo.py"), self.file)

    def test_private_original_and_unrecognized_paths_rejected(self):
        for name in ["programs/A/source/main.py", "sources/main.py", "programs/A/runs/private/main.py", "secret.py"]:
            path = self.root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("pass\n")
            with self.subTest(name=name), self.assertRaises(ValueError):
                lookup.approved_file(self.root, name)

    def test_target_allowed(self):
        path = self.root / "programs/A/target/rules.py"
        path.parent.mkdir(parents=True)
        path.write_text("pass\n")
        self.assertEqual(lookup.approved_file(self.root, "programs/A/target/rules.py"), path)

    def test_symlink_and_parent_escape_rejected(self):
        (self.root / "examples/linked.py").symlink_to(self.file)
        for name in ["examples/linked.py", "../escape.py", "examples/../examples/demo.py"]:
            with self.subTest(name=name), self.assertRaises(ValueError):
                lookup.approved_file(self.root, name)

    def test_hardlink_rejected(self):
        (self.root / "examples/linked.py").hardlink_to(self.file)
        with self.assertRaises(ValueError):
            lookup.approved_file(self.root, "examples/linked.py")

    def test_non_python_and_oversize_rejected(self):
        path = self.root / "examples/data.json"
        path.write_text("{}")
        with self.assertRaises(ValueError):
            lookup.approved_file(self.root, "examples/data.json")
        self.file.write_bytes(b"x" * (lookup.MAX_FILE_BYTES + 1))
        with self.assertRaises(ValueError):
            lookup.approved_file(self.root, "examples/demo.py")

    def test_summary_omits_rationale_and_marks_truncation(self):
        graph = {"nodes": [{"id": "a", "label": "rule()", "file_type": "code", "source_location": "L1"},
                           {"id": "b", "label": "rule caller()", "file_type": "code", "source_location": "L4"},
                           {"id": "c", "label": "rule secret comment", "file_type": "rationale"}], "edges": []}
        result = lookup.select(graph, "rule", limit=1)
        self.assertEqual(result["match_count"], 2)
        self.assertTrue(result["truncated"])
        self.assertEqual(result["symbols"], [{"name": "rule()", "line": "L1"}])

    def test_parser_error_is_not_empty_success(self):
        with self.assertRaises(ValueError):
            lookup.select({"error": "parse failed"}, "rule")

    def test_long_names_are_bounded_and_visible(self):
        graph = {"nodes": [{"id": "a", "label": "rule" * 1000, "file_type": "code"}], "edges": []}
        result = lookup.select(graph, "rule")
        self.assertEqual(len(result["symbols"][0]["name"]), 160)
        self.assertTrue(result["truncated"])

    def test_original_edit_and_restore_cannot_change_parsed_snapshot(self):
        original = self.file.read_bytes()
        def extractor(path, root):
            self.file.write_bytes(b"def transient_rule():\n    return 2\n")
            parsed = path.read_bytes()
            self.file.write_bytes(original)
            return {"parsed": parsed}
        result = lookup.extract_snapshot(original, self.root, self.file.name, extractor)
        self.assertEqual(result["parsed"], original)
        self.assertFalse(list(self.root.glob(".graphify-lookup-*")))

    @unittest.skipUnless(os.open in os.supports_dir_fd and hasattr(os, "O_NOFOLLOW"), "POSIX no-follow opens required")
    def test_no_follow_reader_preserves_bytes(self):
        self.assertEqual(lookup.read_source(self.root, "examples/demo.py"), self.file.read_bytes())

    def test_no_follow_reader_rejects_ancestor_symlink(self):
        other = self.root / "other"
        other.mkdir()
        (other / "demo.py").write_text("pass\n")
        (self.root / "examples/link").symlink_to(other, target_is_directory=True)
        with self.assertRaises((OSError, ValueError)):
            lookup.read_source(self.root, "examples/link/demo.py")

    def test_guard_rejects_network_and_child_processes(self):
        for event in ["socket.connect", "socket.getaddrinfo", "subprocess.Popen", "os.system", "os.exec", "os.posix_spawn", "os.fork"]:
            with self.subTest(event=event), self.assertRaises(RuntimeError):
                lookup.no_external_calls(event, ())
        lookup.no_external_calls("open", ())


if __name__ == "__main__":
    unittest.main()
