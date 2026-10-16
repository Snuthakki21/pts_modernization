"""Synthetic contract tests; no customer inputs or external execution."""

import hashlib
import json
import os
from pathlib import Path
import platform
import subprocess
import sys
import tempfile
import unittest


SCRIPT = Path(__file__).resolve().parents[1] / "tools" / "replay_record.py"


class ReplayRecordTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.bundle_root = self.root / "bundle"
        self.bundle_root.mkdir()
        self.output = self.root / "replay"
        self.records = [
            {"record_id": "selected", "parents": ["parent"], "data": {"amount": 7}},
            {"record_id": "unrelated", "parents": [], "data": {"amount": 90}},
            {"record_id": "parent", "parents": ["ancestor"], "data": {"amount": 2}},
            {"record_id": "context", "parents": [], "data": {"amount": 3}},
            {"record_id": "ancestor", "parents": [], "data": {"amount": 1}},
        ]
        self.bundle = {
            "schema_version": 1,
            "bundle_id": "synthetic-failure-1",
            "artifacts": {},
            "dependencies": {
                "complete": True,
                "context_record_ids": ["context"],
                "full_partition": {"required": False},
            },
            "clock": {"utc": "2026-01-02T03:04:05Z", "business_date": "2026-01-02"},
            "environment": {
                "contract_version": 1,
                "python": f"{sys.version_info.major}.{sys.version_info.minor}",
                "implementation": platform.python_implementation().lower(),
                "variables": {},
            },
            "expectations": {
                "selected": {
                    "expected": {"value": {"total": 10}, "provenance": {"source_id": "case-1", "version": "1"}},
                    "failed_observed": {"value": {"total": 7}, "provenance": {"source_id": "failed-run-1", "version": "1"}},
                }
            },
        }
        self.artifact("records", {"records": self.records})
        self.artifact("reference_data", {"increment": 3})
        self.artifact("state", {"balance": 0})
        self.artifact("target", "def transform(context):\n    return {'total': 7}\n", ".py")
        self.artifact("adapter", "def replay(context):\n    namespace = {}\n    exec(compile(context['target']['source'], '<pinned-target>', 'exec'), namespace)\n    return namespace['transform'](context)\n", ".py")
        self.save()

    def artifact(self, name, value, suffix=".json"):
        data = value.encode() if isinstance(value, str) else json.dumps(value).encode()
        path = self.bundle_root / (name + suffix)
        path.write_bytes(data)
        self.bundle["artifacts"][name] = {"path": path.name, "sha256": hashlib.sha256(data).hexdigest()}

    def save(self):
        self.manifest = self.bundle_root / "bundle.json"
        self.manifest.write_text(json.dumps(self.bundle), encoding="utf-8")

    def run_cli(self, execute=False, record="selected", output=None):
        self.save()
        args = [sys.executable, str(SCRIPT), "--bundle", str(self.manifest), "--record", record, "--output", str(output or self.output)]
        if execute:
            args.append("--execute")
        return subprocess.run(args, capture_output=True, text=True, check=False)

    def report(self):
        return json.loads((self.output / "report.json").read_text())

    def assert_invalid(self, result):
        self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
        self.assertFalse(self.output.exists())

    def test_default_materializes_sorted_transitive_and_context_closure_without_execution(self):
        self.artifact("adapter", "raise RuntimeError('must not import')\n", ".py")
        result = self.run_cli()
        self.assertEqual(result.returncode, 0, result.stderr)
        fixture = json.loads((self.output / "fixture.json").read_text())
        self.assertEqual([r["record_id"] for r in fixture["records"]], ["ancestor", "context", "parent", "selected"])
        self.assertEqual(fixture["clock"], self.bundle["clock"])
        self.assertEqual(fixture["state"], {"balance": 0})
        self.assertEqual(self.report()["execution"], "not_requested")
        self.assertEqual(self.report()["validation_status"], "not_established")
        self.assertEqual(self.report()["closure_basis"], "bundle_attestation_not_independently_proven")
        self.assertTrue((self.output / "artifacts" / "target.py").exists())

    def test_materialized_bundle_can_be_replayed_after_original_is_removed(self):
        result = self.run_cli()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.manifest.unlink()
        for path in self.bundle_root.iterdir():
            path.unlink()
        second = self.root / "second"
        result = subprocess.run([sys.executable, str(SCRIPT), "--bundle", str(self.output / "bundle.json"), "--record", "selected", "--output", str(second)], capture_output=True, text=True, check=False)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual((self.output / "fixture.json").read_bytes(), (second / "fixture.json").read_bytes())

    def test_full_partition_requires_complete_inventory_and_includes_unrelated_records(self):
        self.bundle["dependencies"]["full_partition"] = {"required": True, "complete": True, "record_ids": [r["record_id"] for r in self.records]}
        result = self.run_cli()
        self.assertEqual(result.returncode, 0, result.stderr)
        fixture = json.loads((self.output / "fixture.json").read_text())
        self.assertEqual({r["record_id"] for r in fixture["records"]}, {r["record_id"] for r in self.records})

    def test_incomplete_dependencies_rejected(self):
        self.bundle["dependencies"]["complete"] = False
        self.assert_invalid(self.run_cli())

    def test_unknown_partition_or_missing_partition_members_rejected(self):
        for partition in [{"required": True}, {"required": True, "complete": True, "record_ids": ["selected"]}]:
            with self.subTest(partition=partition):
                self.bundle["dependencies"]["full_partition"] = partition
                self.assert_invalid(self.run_cli())

    def test_unknown_context_or_selected_record_rejected(self):
        self.bundle["dependencies"]["context_record_ids"] = ["missing"]
        self.assert_invalid(self.run_cli())
        self.bundle["dependencies"]["context_record_ids"] = []
        self.assert_invalid(self.run_cli(record="missing"))

    def test_duplicate_dangling_and_cyclic_records_rejected_even_outside_selected_closure(self):
        corruptions = [
            self.records + [self.records[0]],
            self.records + [{"record_id": "bad", "parents": ["missing"], "data": {}}],
            self.records + [{"record_id": "bad", "parents": ["bad"], "data": {}}],
        ]
        for records in corruptions:
            with self.subTest(records=records[-1]["record_id"]):
                self.artifact("records", {"records": records})
                self.assert_invalid(self.run_cli())

    def test_missing_and_hash_mismatched_artifact_rejected(self):
        path = self.bundle_root / "state.json"
        path.write_text('{"balance":99}')
        self.assert_invalid(self.run_cli())
        path.unlink()
        self.assert_invalid(self.run_cli())

    def test_artifact_paths_cannot_escape_bundle_or_follow_escaping_symlink(self):
        external = self.root / "outside.json"
        external.write_text('{}')
        self.bundle["artifacts"]["state"]["sha256"] = hashlib.sha256(b'{}').hexdigest()
        for unsafe in ["../outside.json", str(external)]:
            with self.subTest(path=unsafe):
                self.bundle["artifacts"]["state"]["path"] = unsafe
                self.assert_invalid(self.run_cli())
        link = self.bundle_root / "escape.json"
        link.symlink_to(external)
        self.bundle["artifacts"]["state"]["path"] = link.name
        self.assert_invalid(self.run_cli())

    def test_existing_output_and_output_inside_bundle_rejected(self):
        self.output.mkdir()
        sentinel = self.output / "keep.txt"
        sentinel.write_text("keep")
        self.assertEqual(self.run_cli().returncode, 2)
        self.assertEqual(sentinel.read_text(), "keep")
        self.assertEqual(self.run_cli(output=self.bundle_root / "result").returncode, 2)
        self.assertFalse((self.bundle_root / "result").exists())

    def test_runtime_and_explicit_environment_mismatch_block_before_execution(self):
        self.bundle["environment"]["python"] = "0.0"
        self.assert_invalid(self.run_cli(execute=True))
        self.bundle["environment"]["python"] = f"{sys.version_info.major}.{sys.version_info.minor}"
        self.bundle["environment"]["variables"] = {"PTS_REPLAY_TEST_UNLIKELY_KEY": "required"}
        self.assertNotEqual(os.environ.get("PTS_REPLAY_TEST_UNLIKELY_KEY"), "required")
        self.assert_invalid(self.run_cli(execute=True))

    def test_reproducing_failure_is_not_correctness_success(self):
        result = self.run_cli(execute=True)
        self.assertEqual(result.returncode, 1, result.stderr)
        report = self.report()
        self.assertEqual(report["comparison"], "differs_from_expected")
        self.assertTrue(report["reproduced_failed_observation"])
        self.assertEqual(report["result"], {"total": 7})
        self.assertEqual(report["failed_observed"], self.bundle["expectations"]["selected"]["failed_observed"])
        self.assertEqual(report["validation_status"], "not_established")

    def test_expected_match_passes_values_and_explicit_context_without_mutating_global_clock(self):
        source = "def replay(context):\n    assert context['clock']['business_date'] == '2026-01-02'\n    assert context['state'] == {'balance': 0}\n    return {'total': 7 + context['reference_data']['increment']}\n"
        self.artifact("adapter", source, ".py")
        result = self.run_cli(execute=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.report()["comparison"], "matches_expected")
        self.assertFalse(self.report()["reproduced_failed_observation"])
        self.assertEqual(self.report()["validation_status"], "not_established")

    def test_adapter_output_and_errors_do_not_log_sensitive_values(self):
        self.artifact("adapter", "def replay(context):\n    print('SYNTHETIC_PRIVATE_VALUE')\n    raise ValueError('SYNTHETIC_PRIVATE_VALUE')\n", ".py")
        result = self.run_cli(execute=True)
        self.assertEqual(result.returncode, 2)
        self.assertNotIn("SYNTHETIC_PRIVATE_VALUE", result.stdout + result.stderr + (self.output / "report.json").read_text())
        self.assertEqual(self.report()["execution"], "error")
        self.assertEqual(self.report()["error_type"], "ValueError")

    def test_adapter_interrupts_are_sanitized_and_preserve_interrupted_report(self):
        for exception in ("KeyboardInterrupt", "GeneratorExit"):
            for phase in ("load", "replay"):
                with self.subTest(exception=exception, phase=phase):
                    self.output = self.root / f"interrupted-{exception}-{phase}"
                    statement = f"raise {exception}('SYNTHETIC_PRIVATE_VALUE')\n"
                    source = statement if phase == "load" else "def replay(context):\n    " + statement
                    self.artifact("adapter", source, ".py")
                    result = self.run_cli(execute=True)
                    self.assertEqual(result.returncode, 130)
                    report = self.report()
                    self.assertEqual(report["execution"], "interrupted")
                    self.assertEqual(report["error_type"], exception)
                    self.assertEqual(report["comparison"], "not_run")
                    self.assertEqual(report["validation_status"], "not_established")
                    self.assertNotIn("result", report)
                    self.assertNotIn("SYNTHETIC_PRIVATE_VALUE", result.stdout + result.stderr + (self.output / "report.json").read_text())

    def test_nan_in_input_or_adapter_result_and_duplicate_json_keys_rejected(self):
        for raw in ['{"balance":NaN}', '{"balance":1,"balance":2}']:
            self.artifact("state", raw)
            self.assert_invalid(self.run_cli())
        self.artifact("state", {"balance": 0})
        self.artifact("adapter", "def replay(context):\n    return float('nan')\n", ".py")
        self.assertEqual(self.run_cli(execute=True).returncode, 2)
        self.assertEqual(self.report()["execution"], "error")

    def test_missing_expectation_or_empty_provenance_rejected(self):
        del self.bundle["expectations"]["selected"]["expected"]["value"]
        self.assert_invalid(self.run_cli())
        self.bundle["expectations"]["selected"]["expected"]["value"] = {"total": 10}
        self.bundle["expectations"]["selected"]["expected"]["provenance"] = {}
        self.assert_invalid(self.run_cli())

    def test_boolean_is_not_equal_to_numeric_expected_value(self):
        self.bundle["expectations"]["selected"]["expected"]["value"] = True
        self.artifact("adapter", "def replay(context):\n    return 1\n", ".py")
        self.assertEqual(self.run_cli(execute=True).returncode, 1)
        self.assertEqual(self.report()["comparison"], "differs_from_expected")

    def test_nested_non_json_adapter_result_is_an_execution_error(self):
        self.artifact("adapter", "def replay(context):\n    return {'nested': (1, 2)}\n", ".py")
        self.assertEqual(self.run_cli(execute=True).returncode, 2)
        self.assertEqual(self.report()["execution"], "error")

    def test_forged_expectation_matching_known_failure_never_has_success_exit(self):
        self.bundle["expectations"]["selected"]["expected"]["value"] = {"total": 7}
        self.assertEqual(self.run_cli(execute=True).returncode, 1)
        self.assertEqual(self.report()["comparison"], "matches_expected")
        self.assertTrue(self.report()["reproduced_failed_observation"])
        self.assertEqual(self.report()["validation_status"], "not_established")


if __name__ == "__main__":
    unittest.main()
