"""Synthetic Endevor navigation checks; these never assert program acceptance."""
import hashlib
import importlib.util
import json
from datetime import datetime
from pathlib import Path
import re
import tempfile
import unittest
from unittest.mock import patch


SPEC = importlib.util.spec_from_file_location(
    "endevor_nav", Path(__file__).parents[1] / "tools/endevor_nav.py"
)
nav = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(nav)


class EndevorNavigationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = self.root / "Endevor"
        self.source.mkdir()
        self.manifest = {
            "schema_version": 1,
            "approved_source_reference": "synthetic-fixture-approval-only",
            "files": [],
        }

    def add(self, path, text, kind="cobol", encoding="utf-8", format="free"):
        source = self.source / path
        source.parent.mkdir(parents=True, exist_ok=True)
        source.write_bytes(text.encode(encoding))
        self.manifest["files"].append({
            "path": path,
            "kind": kind,
            "encoding": encoding,
            "format": format,
            "source_identity": f"SYNTH/TEST/APP/{kind}/{path}/VERSION-1",
        })
        self.save_manifest()
        return source

    def save_manifest(self):
        (self.source / "navigation.json").write_text(
            json.dumps(self.manifest, indent=2) + "\n", encoding="utf-8"
        )

    def fixture(self):
        self.add("COBOL/A.cbl", "IDENTIFICATION DIVISION.\nPROGRAM-ID. A.\n"
                 "COPY LAYOUT.\nPROCEDURE DIVISION.\nCALL 'B'.\n")
        self.add("COBOL/B.cbl", "IDENTIFICATION DIVISION.\nPROGRAM-ID. B.\n"
                 "EXEC SQL INCLUDE SQLAREA END-EXEC.\n"
                 "PROCEDURE DIVISION.\nCALL 'A'.\n")
        self.add("COPY/LAYOUT.cpy", "01 SYNTHETIC-ROW PIC X(4).\n", "copybook")
        self.add("SQL/SQLAREA.sql", "01 SYNTHETIC-SQL-STATE PIC X(5).\n", "sql")
        self.add("JCL/JOB.jcl", "//SYNTH JOB\n//STEP1 EXEC PGM=A\n", "jcl")
        nav.build(self.root)

    @staticmethod
    def paths(result):
        return {node["path"] for node in result["nodes"]}

    @staticmethod
    def pairs(result):
        paths = {node["id"]: node["path"] for node in result["nodes"]}
        return {(paths[edge["source"]], paths[edge["target"]])
                for edge in result["edges"]}

    def test_multi_hop_dependencies_keep_source_lines_and_hashes(self):
        self.fixture()
        result = nav.walk(self.root, "COBOL/A.cbl", max_depth=2)
        self.assertEqual(self.paths(result), {
            "COBOL/A.cbl", "COBOL/B.cbl", "COPY/LAYOUT.cpy", "SQL/SQLAREA.sql"
        })
        self.assertTrue({("COBOL/A.cbl", "COBOL/B.cbl"),
                         ("COBOL/A.cbl", "COPY/LAYOUT.cpy"),
                         ("COBOL/B.cbl", "SQL/SQLAREA.sql")} <= self.pairs(result))
        nodes = {node["id"]: node for node in result["nodes"]}
        for edge in result["edges"]:
            path = nodes[edge["source"]]["path"]
            source_bytes = (self.source / path).read_bytes()
            self.assertEqual(edge["source_sha256"], hashlib.sha256(source_bytes).hexdigest())
            self.assertGreaterEqual(edge["line"], 1)
            self.assertLessEqual(edge["line"], len(source_bytes.splitlines()))
        call = next(edge for edge in result["edges"]
                    if nodes[edge["source"]]["path"] == "COBOL/A.cbl"
                    and nodes[edge["target"]]["path"] == "COBOL/B.cbl")
        self.assertEqual(call["line"], 5)

    def test_reverse_traversal_reaches_callers_and_jcl(self):
        self.fixture()
        result = nav.walk(self.root, "COPY/LAYOUT.cpy", direction="dependents", max_depth=2)
        self.assertEqual(self.paths(result), {
            "COPY/LAYOUT.cpy", "COBOL/A.cbl", "COBOL/B.cbl", "JCL/JOB.jcl"
        })

    def test_jcl_procedure_chain_reaches_cobol_dependencies(self):
        self.add("JCL/JOB.jcl", "//SYNTH JOB\n//STEP1 EXEC RUNAPP\n", "jcl")
        self.add("PROC/RUNAPP.proc", "//RUNAPP PROC\n//RUN EXEC PGM=MAIN\n// PEND\n", "proc")
        self.add("COBOL/MAIN.cbl", "PROGRAM-ID. MAIN.\nCOPY LAYOUT.\n")
        self.add("COPY/LAYOUT.cpy", "01 SYNTHETIC-ROW PIC X.\n", "copybook")
        nav.build(self.root)
        result = nav.walk(self.root, "JCL/JOB.jcl", max_depth=3)
        self.assertEqual(self.paths(result), {
            "JCL/JOB.jcl", "PROC/RUNAPP.proc", "COBOL/MAIN.cbl", "COPY/LAYOUT.cpy"
        })
        self.assertEqual(self.pairs(result), {
            ("JCL/JOB.jcl", "PROC/RUNAPP.proc"),
            ("PROC/RUNAPP.proc", "COBOL/MAIN.cbl"),
            ("COBOL/MAIN.cbl", "COPY/LAYOUT.cpy"),
        })

    def test_both_directions_and_cycle_visit_each_node_once(self):
        self.fixture()
        result = nav.walk(self.root, "COBOL/A.cbl", direction="both", max_depth=8)
        self.assertEqual(len(result["nodes"]), 5)
        self.assertEqual(len({node["id"] for node in result["nodes"]}), 5)
        self.assertIn("JCL/JOB.jcl", self.paths(result))

    def test_depth_and_node_bounds_are_visible(self):
        self.fixture()
        zero = nav.walk(self.root, "COBOL/A.cbl", max_depth=0)
        self.assertEqual(self.paths(zero), {"COBOL/A.cbl"})
        bounded = nav.walk(self.root, "COBOL/A.cbl", max_depth=4, max_nodes=2)
        self.assertEqual(len(bounded["nodes"]), 2)
        self.assertTrue(bounded["truncated"])
        for options in [{"max_depth": -1}, {"max_nodes": 0}, {"direction": "execute"}]:
            with self.subTest(options=options), self.assertRaises(ValueError):
                nav.walk(self.root, "COBOL/A.cbl", **options)

    def test_unknown_start_does_not_fall_back_to_another_program(self):
        self.fixture()
        with self.assertRaises(ValueError):
            nav.walk(self.root, "MISSING")

    def test_changed_bytes_block_check_and_walk(self):
        self.fixture()
        (self.source / "COBOL/B.cbl").write_text("PROGRAM-ID. CHANGED.\n")
        for action in [lambda: nav.check(self.root),
                       lambda: nav.walk(self.root, "COBOL/A.cbl")]:
            with self.assertRaises(ValueError):
                action()

    def test_deleted_source_blocks_stale_navigation(self):
        self.fixture()
        (self.source / "COPY/LAYOUT.cpy").unlink()
        with self.assertRaises((ValueError, OSError)):
            nav.walk(self.root, "COBOL/A.cbl")

    def test_manifest_addition_invalidates_snapshot(self):
        self.fixture()
        self.add("COBOL/C.cbl", "PROGRAM-ID. C.\n")
        with self.assertRaises(ValueError):
            nav.walk(self.root, "COBOL/A.cbl")
        nav.build(self.root)
        self.assertEqual(self.paths(nav.walk(self.root, "COBOL/C.cbl")), {"COBOL/C.cbl"})

    def test_renamed_source_requires_manifest_refresh(self):
        self.fixture()
        (self.source / "COBOL/A.cbl").rename(self.source / "COBOL/RENAMED.cbl")
        with self.assertRaises((ValueError, OSError)):
            nav.walk(self.root, "COBOL/A.cbl")
        self.manifest["files"][0]["path"] = "COBOL/RENAMED.cbl"
        self.save_manifest()
        nav.build(self.root)
        result = nav.walk(self.root, "COBOL/RENAMED.cbl")
        self.assertIn("COBOL/RENAMED.cbl", self.paths(result))
        self.assertNotIn("COBOL/A.cbl", self.paths(result))

    def test_repeated_build_preserves_content_addressed_snapshot(self):
        self.fixture()
        first = nav.check(self.root)
        before = {str(path.relative_to(self.root)): path.read_bytes()
                  for path in (self.root / "knowledge/endevor/snapshots").rglob("*")
                  if path.is_file()}
        nav.build(self.root)
        after = {str(path.relative_to(self.root)): path.read_bytes()
                 for path in (self.root / "knowledge/endevor/snapshots").rglob("*")
                 if path.is_file()}
        self.assertTrue(before)
        self.assertEqual(before, after)
        self.assertEqual(first["snapshot"], nav.check(self.root)["snapshot"])

    def test_restored_source_bytes_match_prior_snapshot(self):
        self.fixture()
        path = self.source / "COBOL/B.cbl"
        original = path.read_bytes()
        path.write_bytes(original + b"*> transient edit\n")
        with self.assertRaises(ValueError):
            nav.check(self.root)
        path.write_bytes(original)
        nav.check(self.root)

    def test_ambiguous_members_are_not_silently_resolved(self):
        self.add("COBOL/MAIN.cbl", "PROGRAM-ID. MAIN.\nCALL 'SHARED'.\n")
        self.add("LIB1/SHARED.cbl", "PROGRAM-ID. SHARED.\n")
        self.add("LIB2/SHARED.cbl", "PROGRAM-ID. SHARED.\n")
        nav.build(self.root)
        result = nav.walk(self.root, "COBOL/MAIN.cbl", max_depth=3)
        self.assertEqual(self.paths(result), {"COBOL/MAIN.cbl"})
        self.assertTrue(any(item["state"] == "ambiguous" for item in result["unresolved"]))
        self.assertIn("SHARED", json.dumps(result["unresolved"]))

    def test_dynamic_call_and_symbolic_jcl_are_explicit_gaps(self):
        self.add("COBOL/MAIN.cbl", "PROGRAM-ID. MAIN.\nCALL WS-TARGET.\n")
        self.add("JCL/JOB.jcl", "//SYNTH JOB\n//STEP1 EXEC PGM=&TARGET\n", "jcl")
        nav.build(self.root)
        for start in ["COBOL/MAIN.cbl", "JCL/JOB.jcl"]:
            with self.subTest(start=start):
                result = nav.walk(self.root, start)
                self.assertEqual(self.paths(result), {start})
                self.assertTrue(any(item["state"] == "dynamic" for item in result["unresolved"]))

    def test_comments_and_display_literals_do_not_invent_dependencies(self):
        self.add("COBOL/MAIN.cbl", "PROGRAM-ID. MAIN.\n*> CALL 'FALSE'.\n"
                 'DISPLAY "CALL \'FALSE\'".\n'
                 "CALL 'REAL'. *> CALL 'FALSE'.\n")
        self.add("COBOL/REAL.cbl", "PROGRAM-ID. REAL.\n")
        self.add("COBOL/FALSE.cbl", "PROGRAM-ID. FALSE.\n")
        nav.build(self.root)
        result = nav.walk(self.root, "COBOL/MAIN.cbl")
        self.assertEqual(self.paths(result), {"COBOL/MAIN.cbl", "COBOL/REAL.cbl"})

    def test_fixed_format_comment_column_is_not_executable(self):
        self.add("COBOL/MAIN.cbl", "000100 IDENTIFICATION DIVISION.\n"
                 "000200 PROGRAM-ID. MAIN.\n000300*CALL 'FALSE'.\n"
                 "000400     CALL 'REAL'.\n", format="fixed")
        self.add("COBOL/REAL.cbl", "PROGRAM-ID. REAL.\n")
        self.add("COBOL/FALSE.cbl", "PROGRAM-ID. FALSE.\n")
        nav.build(self.root)
        self.assertEqual(self.paths(nav.walk(self.root, "COBOL/MAIN.cbl")),
                         {"COBOL/MAIN.cbl", "COBOL/REAL.cbl"})

    def test_jcl_comment_field_does_not_invent_a_second_exec(self):
        self.add("JCL/JOB.jcl", "//SYNTH JOB\n"
                 "//STEP EXEC PGM=MAIN  COMMENT TEXT EXEC PGM=FALSE\n", "jcl")
        self.add("COBOL/MAIN.cbl", "PROGRAM-ID. MAIN.\n")
        self.add("COBOL/FALSE.cbl", "PROGRAM-ID. FALSE.\n")
        nav.build(self.root)
        self.assertEqual(self.paths(nav.walk(self.root, "JCL/JOB.jcl")),
                         {"JCL/JOB.jcl", "COBOL/MAIN.cbl"})

    def test_jcl_instream_data_does_not_invent_dependencies(self):
        self.add("JCL/JOB.jcl", "//SYNTH JOB\n//INPUT DD DATA,DLM=@@\n"
                 "//FAKE EXEC PGM=FALSE\n@@\n//REAL EXEC PGM=MAIN\n", "jcl")
        self.add("COBOL/MAIN.cbl", "PROGRAM-ID. MAIN.\n")
        self.add("COBOL/FALSE.cbl", "PROGRAM-ID. FALSE.\n")
        nav.build(self.root)
        self.assertEqual(self.paths(nav.walk(self.root, "JCL/JOB.jcl")),
                         {"JCL/JOB.jcl", "COBOL/MAIN.cbl"})

    def test_explicit_cp037_decoding_preserves_byte_hash(self):
        path = self.add("COBOL/MAIN.cbl", "PROGRAM-ID. MAIN.\nCALL 'REAL'.\n", encoding="cp037")
        self.add("COBOL/REAL.cbl", "PROGRAM-ID. REAL.\n")
        nav.build(self.root)
        result = nav.walk(self.root, "COBOL/MAIN.cbl")
        self.assertEqual(self.paths(result), {"COBOL/MAIN.cbl", "COBOL/REAL.cbl"})
        self.assertEqual(result["edges"][0]["source_sha256"],
                         hashlib.sha256(path.read_bytes()).hexdigest())

    def test_manifest_requires_approval_and_qualified_source_identity(self):
        self.add("COBOL/A.cbl", "PROGRAM-ID. A.\n")
        for key in ["approved_source_reference", "source_identity"]:
            target = self.manifest if key == "approved_source_reference" else self.manifest["files"][0]
            original = target.pop(key)
            self.save_manifest()
            with self.subTest(key=key), self.assertRaises(ValueError):
                nav.build(self.root)
            target[key] = original

    def test_duplicate_and_case_colliding_paths_rejected(self):
        self.add("COBOL/A.cbl", "PROGRAM-ID. A.\n")
        self.manifest["files"].append(dict(self.manifest["files"][0]))
        self.save_manifest()
        with self.assertRaises(ValueError):
            nav.build(self.root)
        self.manifest["files"].pop()
        self.add("cobol/a.cbl", "PROGRAM-ID. OTHER.\n")
        with self.assertRaises(ValueError):
            nav.build(self.root)

    def test_parent_absolute_and_normalization_paths_rejected(self):
        self.add("COBOL/A.cbl", "PROGRAM-ID. A.\n")
        for path in ["../outside.cbl", "/tmp/outside.cbl", "COBOL/../COBOL/A.cbl", "./COBOL/A.cbl"]:
            self.manifest["files"][0]["path"] = path
            self.save_manifest()
            with self.subTest(path=path), self.assertRaises(ValueError):
                nav.build(self.root)

    def test_source_symlink_and_ancestor_symlink_are_rejected(self):
        original = self.add("COBOL/A.cbl", "PROGRAM-ID. A.\n")
        outside = self.root / "outside.cbl"
        outside.write_bytes(original.read_bytes())
        original.unlink()
        original.symlink_to(outside)
        with self.assertRaises((ValueError, OSError)):
            nav.build(self.root)
        original.unlink()
        original.parent.rmdir()
        source_dir = self.root / "other"
        source_dir.mkdir()
        (source_dir / "A.cbl").write_text("PROGRAM-ID. A.\n")
        original.parent.symlink_to(source_dir, target_is_directory=True)
        with self.assertRaises((ValueError, OSError)):
            nav.build(self.root)

    def test_hardlinked_source_is_rejected(self):
        source = self.add("COBOL/A.cbl", "PROGRAM-ID. A.\n")
        (self.root / "alias.cbl").hardlink_to(source)
        with self.assertRaises(ValueError):
            nav.build(self.root)

    def test_linked_manifest_is_rejected(self):
        self.add("COBOL/A.cbl", "PROGRAM-ID. A.\n")
        manifest = self.source / "navigation.json"
        outside = self.root / "manifest.json"
        manifest.rename(outside)
        manifest.symlink_to(outside)
        with self.assertRaises((ValueError, OSError)):
            nav.build(self.root)

    def test_output_ancestor_symlink_cannot_write_outside_bundle(self):
        self.add("COBOL/A.cbl", "PROGRAM-ID. A.\n")
        outside = self.root / "outside-output"
        outside.mkdir()
        (self.root / "knowledge").symlink_to(outside, target_is_directory=True)
        with self.assertRaises((ValueError, OSError)):
            nav.build(self.root)
        self.assertEqual(list(outside.iterdir()), [])

    def test_unlisted_source_is_never_read_or_reported(self):
        self.add("COBOL/A.cbl", "PROGRAM-ID. A.\n")
        (self.source / "DO-NOT-READ.cbl").symlink_to(self.root / "missing-protected-file")
        nav.build(self.root)
        self.assertEqual(self.paths(nav.walk(self.root, "COBOL/A.cbl")), {"COBOL/A.cbl"})

    def test_invalid_encoding_is_not_silently_replaced(self):
        path = self.add("COBOL/A.cbl", "PROGRAM-ID. A.\n")
        path.write_bytes(b"\xff\xfe\x00INVALID")
        with self.assertRaises((ValueError, UnicodeError)):
            nav.build(self.root)

    def test_okf_documents_have_valid_frontmatter_provenance_and_links(self):
        self.fixture()
        snapshot = nav.check(self.root)["snapshot"]
        bundle = self.root / "knowledge/endevor/snapshots" / snapshot
        entry = (self.root / "knowledge/endevor/index.md").read_text()
        self.assertTrue(entry.startswith('---\nokf_version: "0.2"\n---\n'))
        self.assertFalse((bundle / "index.md").read_text().startswith("---"))
        self.assertFalse((bundle / "files/index.md").read_text().startswith("---"))
        documents = [path for path in (bundle / "files").glob("*.md") if path.name != "index.md"]
        source_count = 0
        for document in documents:
            text = document.read_text(encoding="utf-8")
            self.assertTrue(text.startswith("---\n"))
            frontmatter, body = text[4:].split("\n---\n", 1)
            # The producer deliberately emits JSON-valued YAML, so standard-library
            # parsing validates this YAML subset without adding a runtime dependency.
            meta = {key: json.loads(value.strip())
                    for key, value in (line.split(":", 1) for line in frontmatter.splitlines())}
            self.assertIsInstance(meta["type"], str)
            self.assertTrue(meta["type"].strip())
            self.assertEqual(meta["status"], "draft")
            self.assertNotIn("verified", meta)
            for target in re.findall(r"\]\(([^)]+\.md)\)", body):
                self.assertTrue((document.parent / target).is_file(), target)
            if meta["type"] == "Navigation Page":
                continue
            source_count += 1
            self.assertTrue(meta["generated"]["by"].startswith("process:"))
            self.assertIsNotNone(datetime.fromisoformat(meta["generated"]["at"].replace("Z", "+00:00")).tzinfo)
            self.assertTrue(meta["sources"])
            self.assertTrue(all(isinstance(source["resource"], str) and source["resource"]
                                for source in meta["sources"]))
            self.assertTrue(meta["source_identity"].startswith("SYNTH/TEST/APP/"))
            self.assertRegex(meta["source_view_sha256"], r"^[0-9a-f]{64}$")
        self.assertEqual(source_count, 5)

    def test_projection_contains_navigation_metadata_not_copied_source_body(self):
        self.add("COBOL/A.cbl", "PROGRAM-ID. A.\n"
                 "DISPLAY 'SYNTHETIC-DO-NOT-COPY-THIS-LITERAL'.\n")
        nav.build(self.root)
        for artifact in (self.root / "knowledge/endevor").rglob("*"):
            if artifact.is_file():
                self.assertNotIn(b"SYNTHETIC-DO-NOT-COPY-THIS-LITERAL", artifact.read_bytes())

    def test_edited_generated_document_blocks_consumption_and_overwrite(self):
        self.fixture()
        bundle = self.root / "knowledge/endevor/snapshots" / nav.check(self.root)["snapshot"]
        concept = next(path for path in (bundle / "files").glob("*.md") if path.name != "index.md")
        edited = concept.read_bytes() + b"\nManual text must not be silently overwritten.\n"
        concept.write_bytes(edited)
        for action in [lambda: nav.check(self.root), lambda: nav.build(self.root)]:
            with self.assertRaises(ValueError):
                action()
        self.assertEqual(concept.read_bytes(), edited)

    def test_existing_unowned_output_entry_is_preserved(self):
        self.add("COBOL/A.cbl", "PROGRAM-ID. A.\n")
        output = self.root / "knowledge/endevor"
        output.mkdir(parents=True)
        original = b"Human knowledge must be reviewed before replacement.\n"
        (output / "index.md").write_bytes(original)
        with self.assertRaises(ValueError):
            nav.build(self.root)
        self.assertEqual((output / "index.md").read_bytes(), original)

    def test_manifest_duplicate_json_keys_are_rejected(self):
        self.add("COBOL/A.cbl", "PROGRAM-ID. A.\n")
        manifest = self.source / "navigation.json"
        manifest.write_text(manifest.read_text().replace('"schema_version": 1',
                                                        '"schema_version": 1, "schema_version": 1'))
        with self.assertRaises(ValueError):
            nav.build(self.root)

    def test_private_source_path_is_not_authorized_by_manifest(self):
        self.add("private/A.cbl", "PROGRAM-ID. A.\n")
        with self.assertRaises(ValueError):
            nav.build(self.root)

    def test_changed_generator_fingerprint_requires_rebuild(self):
        self.fixture()
        with patch.object(nav, "_tool_sha256", return_value="0" * 64):
            with self.assertRaises(ValueError):
                nav.walk(self.root, "COBOL/A.cbl")

    def test_repeated_references_have_bounded_output_and_exact_totals(self):
        self.add("COBOL/MAIN.cbl", "PROGRAM-ID. MAIN.\n" + "CALL 'OTHER'.\n" * 201
                 + "CALL 'MISSING'.\n" * 201)
        self.add("COBOL/OTHER.cbl", "PROGRAM-ID. OTHER.\n")
        nav.build(self.root)
        result = nav.walk(self.root, "COBOL/MAIN.cbl")
        self.assertEqual(len(result["edges"]), 200)
        self.assertEqual(len(result["unresolved"]), 200)
        self.assertEqual(result["edges_total"], 201)
        self.assertEqual(result["unresolved_total"], 201)
        self.assertTrue(result["references_truncated"])
        self.assertTrue(result["truncated"])

    def test_ambiguous_candidate_list_reports_omitted_candidates(self):
        self.add("COBOL/MAIN.cbl", "PROGRAM-ID. MAIN.\nCALL 'SHARED'.\n")
        for number in range(21):
            self.add(f"LIB{number}/SHARED.cbl", "PROGRAM-ID. SHARED.\n")
        nav.build(self.root)
        result = nav.walk(self.root, "COBOL/MAIN.cbl")
        ambiguous = next(ref for ref in result["unresolved"] if ref["state"] == "ambiguous")
        self.assertEqual(ambiguous["candidate_count"], 21)
        self.assertEqual(len(ambiguous["candidates"]), 20)
        self.assertTrue(ambiguous["candidates_truncated"])
        self.assertEqual(result["edges"], [])

    def test_reference_bomb_is_rejected_before_publication(self):
        self.add("COBOL/MAIN.cbl", "PROGRAM-ID. MAIN.\n" + "CALL 'OTHER'.\n" * 1001)
        with self.assertRaises(ValueError):
            nav.build(self.root)
        self.assertFalse((self.root / "knowledge/endevor/current.json").exists())

    def test_oversized_source_is_rejected_before_publication(self):
        path = self.add("COBOL/MAIN.cbl", "PROGRAM-ID. MAIN.\n")
        path.write_bytes(b"X" * (1024 * 1024 + 1))
        with self.assertRaises(ValueError):
            nav.build(self.root)
        self.assertFalse((self.root / "knowledge/endevor/current.json").exists())


if __name__ == "__main__":
    unittest.main()
