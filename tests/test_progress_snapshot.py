"""Progress is a conservative, sanitized projection, never an acceptance oracle."""
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest


SPEC = importlib.util.spec_from_file_location("progress_snapshot", Path(__file__).parents[1] / "tools/progress_snapshot.py")
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def receipt(status="passed", version="build-1"):
    return {"status": status, "version": version, "evidence_refs": ["evidence-001"]}


def accepted_risk():
    return {**receipt("accepted"), "accountable_owner_ref": "OWNER-REF", "decision_ref": "DECISION-REF",
            "rationale_ref": "RATIONALE-REF", "control_refs": ["CONTROL-REF"], "expires_at": "2027-01-01T00:00:00Z"}


def ready_program(program_id="P1"):
    return {
        "program_id": program_id, "consumers": [], "migrations": [],
        "progress": {
            "current_version": "build-1", "lifecycle": "active",
            "conversion": receipt("converted"), "rule_catalog": receipt("complete"),
            "rules": [{"rule_id": "R1", "category": "business", "lifecycle": "retained",
                       "version": "build-1", "positive_passed": 100, "negative_passed": 100,
                       "evidence_refs": ["rule-receipt-001"]}],
            "gates": {gate: receipt() for gate in MODULE.REQUIRED_GATES},
            "blockers": [], "findings": []}}


def inventory(*programs):
    return {"schema_version": 1, "status": "complete", "programs": list(programs), "processes": []}


class ProgressTests(unittest.TestCase):
    def project(self, value):
        return MODULE.snapshot(value, "a" * 64, "2026-10-16T00:00:00Z")

    def test_empty_is_unverified_not_complete(self):
        result = self.project({"schema_version": 1, "status": "unverified", "programs": [], "processes": []})
        self.assertIsNone(result["counters"]["completion_percent"])
        self.assertEqual(result["counters"]["completed_programs"], 0)
        self.assertEqual(result["inventory_status"], "unverified")

    def test_complete_counts_unique_programs_not_consumers(self):
        p = ready_program()
        p["consumers"] = [{"process_id": "A", "step_id": "S1", "provider": "python", "version": "build-1"},
                          {"process_id": "A", "step_id": "S2", "provider": "python", "version": "build-1"}]
        value = inventory(p)
        value["processes"] = [{"process_id": "A"}]
        result = self.project(value)
        self.assertEqual(result["counters"]["total_programs"], 1)
        self.assertEqual(result["counters"]["completed_programs"], 1)
        self.assertEqual(result["processes"][0]["program_ids"], ["P1"])
        self.assertEqual(result["completeness"], "declared_not_verified")
        self.assertEqual(result["programs"][0]["conversion"]["evidence_refs"], ["evidence-001"])
        self.assertEqual(result["programs"][0]["rule_catalog"]["evidence_refs"], ["evidence-001"])

    def test_missing_catalog_or_gate_never_completed(self):
        for field in ("rules", "rule_catalog", "gates", "conversion"):
            with self.subTest(field=field):
                p = ready_program()
                del p["progress"][field]
                self.assertFalse(self.project(inventory(p))["programs"][0]["completed"])

    def test_every_retained_rule_requires_both_quotas_and_current_receipt(self):
        for change in ({"positive_passed": 99}, {"negative_passed": 99}, {"version": "old"}, {"evidence_refs": []}):
            p = ready_program()
            p["progress"]["rules"][0].update(change)
            self.assertFalse(self.project(inventory(p))["programs"][0]["completed"])
        p = ready_program()
        p["progress"]["rules"][0]["category"] = "technical"
        p["progress"]["rules"][0]["negative_passed"] = 0
        self.assertFalse(self.project(inventory(p))["programs"][0]["completed"])

    def test_gate_versions_and_evidence_are_mandatory(self):
        for gate in MODULE.REQUIRED_GATES:
            for change in ({"version": "old"}, {"evidence_refs": []}, {"status": "pending"}):
                p = ready_program()
                p["progress"]["gates"][gate].update(change)
                self.assertFalse(self.project(inventory(p))["programs"][0]["completed"])

    def test_approved_difference_only_accepted_for_legacy(self):
        p = ready_program()
        p["progress"]["gates"]["legacy_comparison"]["status"] = "approved_difference"
        self.assertTrue(self.project(inventory(p))["programs"][0]["completed"])
        p["progress"]["gates"]["security"]["status"] = "approved_difference"
        with self.assertRaises(MODULE.InvalidInput):
            self.project(inventory(p))

    def test_failed_gate_and_open_finding_block_acceptance(self):
        p = ready_program()
        p["progress"]["findings"] = [{"finding_id": "F1", "severity": "low", "status": "open"}]
        row = self.project(inventory(p))["programs"][0]
        self.assertEqual(row["state"], "blocked")
        self.assertFalse(row["completed"])
        p["progress"]["findings"] = []
        p["progress"]["gates"]["security"]["status"] = "failed"
        self.assertEqual(self.project(inventory(p))["programs"][0]["state"], "blocked")

    def test_retired_program_excluded_only_with_current_accepted_receipt(self):
        p = ready_program()
        p["progress"]["lifecycle"] = "retired"
        result = self.project(inventory(p))
        self.assertEqual(result["counters"]["active_programs"], 1)
        p["progress"]["retirement"] = receipt("accepted")
        result = self.project(inventory(p))
        self.assertEqual(result["counters"]["retired_programs"], 1)
        self.assertEqual(result["counters"]["completed_programs"], 0)
        self.assertIsNone(result["counters"]["completion_percent"])

    def test_unknown_process_reference_blocks_program(self):
        p = ready_program()
        p["consumers"] = [{"process_id": "UNKNOWN", "step_id": "S", "provider": "python", "version": "build-1"}]
        row = self.project(inventory(p))["programs"][0]
        self.assertEqual(row["state"], "blocked")
        self.assertIn("unknown_process_reference", [b["category"] for b in row["blockers"]])

    def test_process_completion_requires_integration_and_current_bindings(self):
        p = ready_program()
        p["consumers"] = [{"process_id": "A", "step_id": "S1", "provider": "python", "version": "build-1"}]
        value = inventory(p)
        value["processes"] = [{"process_id": "A"}]
        self.assertNotEqual(self.project(value)["processes"][0]["state"], "completed")
        value["processes"][0]["progress"] = {"current_version": "process-1", "integration": receipt(version="process-1")}
        self.assertEqual(self.project(value)["processes"][0]["state"], "completed")
        p["consumers"][0]["version"] = "old"
        result = self.project(value)
        self.assertEqual(result["processes"][0]["state"], "stale")
        self.assertTrue(result["programs"][0]["completed"])

    def test_migration_cycles_missing_dependencies_and_downstream_are_blocked(self):
        p = ready_program()
        p["migrations"] = [{"migration_id": key, "stage": "identified", "depends_on": deps} for key, deps in
                           (("M1", ["M2"]), ("M2", ["M1"]), ("M3", ["M2"]), ("M4", ["MISSING"]), ("M5", []))]
        migrations = self.project(inventory(p))["programs"][0]["migrations"]
        self.assertEqual([row["blocked"] for row in migrations], [True, True, True, True, False])

    def test_canonical_stale_migration_and_missing_artifact_are_blocked(self):
        p = ready_program()
        p["migrations"] = [{"migration_id": "M1", "stage": "stale", "depends_on": []},
                           {"migration_id": "M2", "stage": "ready", "depends_on": [],
                            "artifacts": [{"state": "missing", "path": "/never/read/this"}]}]
        migrations = self.project(inventory(p))["programs"][0]["migrations"]
        self.assertEqual([row["blocked"] for row in migrations], [True, True])

    def test_resolved_findings_require_current_resolution_evidence(self):
        p = ready_program()
        p["progress"]["findings"] = [{"finding_id": "F1", "severity": "low", "status": "accepted"}]
        self.assertFalse(self.project(inventory(p))["programs"][0]["completed"])
        p["progress"]["findings"][0]["resolution"] = accepted_risk()
        self.assertTrue(self.project(inventory(p))["programs"][0]["completed"])
        p["progress"]["findings"][0]["resolution"]["version"] = "old"
        self.assertFalse(self.project(inventory(p))["programs"][0]["completed"])

    def test_missing_rule_counts_remain_unknown(self):
        p = ready_program()
        del p["progress"]["rules"][0]["negative_passed"]
        row = self.project(inventory(p))["programs"][0]["rules"][0]
        self.assertIsNone(row["negative_passed"])
        self.assertFalse(row["quota_met"])

    def test_empty_or_fully_retired_catalog_cannot_complete_active_program(self):
        p = ready_program()
        p["progress"]["rules"] = []
        self.assertFalse(self.project(inventory(p))["programs"][0]["completed"])
        p = ready_program()
        p["progress"]["rules"][0].update({"lifecycle": "retired", "retirement": receipt("accepted")})
        self.assertFalse(self.project(inventory(p))["programs"][0]["completed"])

    def test_program_retirement_requires_closed_consumer_bindings(self):
        p = ready_program()
        p["progress"].update({"lifecycle": "retired", "retirement": receipt("accepted")})
        p["consumers"] = [{"process_id": "A", "step_id": "S1", "provider": "python", "version": "build-1"}]
        value = inventory(p)
        value["processes"] = [{"process_id": "A"}]
        result = self.project(value)
        self.assertEqual(result["counters"]["active_programs"], 1)
        self.assertEqual(result["counters"]["retired_programs"], 0)
        self.assertEqual(result["programs"][0]["state"], "blocked")

    def test_high_and_critical_risk_acceptance_cannot_complete_program(self):
        for severity in ("high", "critical"):
            p = ready_program()
            p["progress"]["findings"] = [{"finding_id": "F1", "severity": severity, "status": "accepted", "resolution": accepted_risk()}]
            self.assertFalse(self.project(inventory(p))["programs"][0]["completed"])

    def test_canonical_finding_states_and_expired_risk_decisions(self):
        p = ready_program()
        for state in ("closed_verified", "false_positive_with_evidence"):
            p["progress"]["findings"] = [{"finding_id": "F1", "severity": "high", "status": state, "resolution": receipt("verified")}]
            self.assertTrue(self.project(inventory(p))["programs"][0]["completed"])
        p["progress"]["findings"][0]["status"] = "fixed_pending_verification"
        self.assertFalse(self.project(inventory(p))["programs"][0]["completed"])
        p["progress"]["findings"] = [{"finding_id": "F1", "severity": "medium", "status": "accepted_risk", "resolution": accepted_risk()}]
        self.assertTrue(self.project(inventory(p))["programs"][0]["completed"])
        for field in ("accountable_owner_ref", "decision_ref", "rationale_ref", "control_refs", "expires_at"):
            resolution = accepted_risk()
            del resolution[field]
            p["progress"]["findings"][0]["resolution"] = resolution
            self.assertFalse(self.project(inventory(p))["programs"][0]["completed"])
        resolution = accepted_risk()
        resolution["expires_at"] = "2026-01-01T00:00:00Z"
        p["progress"]["findings"][0]["resolution"] = resolution
        self.assertFalse(self.project(inventory(p))["programs"][0]["completed"])

    def test_duplicate_ids_and_unknown_rule_categories_rejected(self):
        for value in (inventory(ready_program(), ready_program()), inventory(ready_program())):
            if len(value["programs"]) == 1:
                value["programs"][0]["progress"]["rules"][0]["category"] = "unknown"
            with self.assertRaises(MODULE.InvalidInput):
                self.project(value)

    def test_invalid_counts_rejected(self):
        for count in (True, -1, 1.5, "100", 2 ** 53):
            p = ready_program()
            p["progress"]["rules"][0]["positive_passed"] = count
            with self.assertRaises(MODULE.InvalidInput):
                self.project(inventory(p))

    def test_no_sensitive_fields_or_arbitrary_artifacts_exported(self):
        p = ready_program()
        p.update({"source": "SSN123", "database": "password", "runtime": "secret"})
        p["progress"]["raw_record"] = "private"
        p["migrations"] = [{"migration_id": "M1", "proposed_name": "Flow 1", "stage": "identified", "depends_on": [],
                            "blocker": "sensitive details", "artifacts": [{"path": "/etc/passwd"}]}]
        encoded = json.dumps(self.project(inventory(p)))
        for secret in ("SSN123", "password", "secret", "private", "/etc/passwd", "sensitive details"):
            self.assertNotIn(secret, encoded)

    def test_prototype_and_html_identifiers_rejected(self):
        for program_id in ("__proto__", "constructor", "prototype", "<script>", "../secret", "javascript:alert"):
            with self.assertRaises(MODULE.InvalidInput):
                self.project(inventory(ready_program(program_id)))

    def test_file_validation_and_new_only_atomic_export(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source, output = root / "inventory.json", root / "progress.json"
            source.write_text(json.dumps(inventory(ready_program())))
            MODULE.export(source, output)
            old = output.read_bytes()
            with self.assertRaises(MODULE.InvalidInput):
                MODULE.export(source, output)
            self.assertEqual(old, output.read_bytes())
            with self.assertRaises(MODULE.InvalidInput):
                MODULE.export(source, source)

    def test_duplicate_json_keys_nonfinite_and_oversized_are_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            for payload in ('{"programs":[],"programs":[]}', '{"x":NaN}', '{"x":1e309}', ' ' * (MODULE.MAX_BYTES + 1)):
                source = root / "inventory.json"
                source.write_text(payload)
                with self.assertRaises(MODULE.InvalidInput):
                    MODULE.export(source, root / "new.json")

    def test_symlink_and_hardlink_inputs_and_output_ancestors_rejected(self):
        import os
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "inventory.json"
            source.write_text(json.dumps(inventory()))
            link = root / "link.json"
            link.symlink_to(source)
            with self.assertRaises(MODULE.InvalidInput):
                MODULE.export(link, root / "new.json")
            link.unlink()
            os.link(source, link)
            with self.assertRaises(MODULE.InvalidInput):
                MODULE.export(source, root / "new.json")
            link.unlink()
            directory = root / "linked-directory"
            directory.symlink_to(root, target_is_directory=True)
            with self.assertRaises(MODULE.InvalidInput):
                MODULE.export(source, directory / "new.json")


if __name__ == "__main__":
    unittest.main()
