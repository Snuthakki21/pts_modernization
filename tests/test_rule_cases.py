import hashlib
import importlib.util
import json
import os
from pathlib import Path
import py_compile
import subprocess
import sys
import tempfile
import types
import unittest


SPEC = importlib.util.spec_from_file_location("rule_cases", Path(__file__).parents[1] / "tools/rule_cases.py")
rules = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(rules)

TARGET = '''def decide(amount):
    return amount >= 100

def evaluate(rule_id, inputs):
    answer = decide(inputs["amount"])
    return {"actual": {"eligible": answer}, "rule_events": [{"rule_id": rule_id, "category": "positive" if answer else "negative"}]}
'''
ORACLE = '''def generate_cases(rule, seed):
    for amount in range(200):
        yield {"case_id": rule["rule_id"] + "-" + str(amount), "category": "negative" if amount < 100 else "positive", "inputs": {"amount": amount}, "expected": {"eligible": amount >= 100}, "coverage_tags": ["below" if amount < 100 else "at_or_above"]}
'''


class RuleCasesTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.path = self.root / "catalog.json"
        (self.root / "source.cob").write_text("SYNTHETIC: eligibility starts at 100\n")
        (self.root / "target.py").write_text(TARGET)
        (self.root / "oracle.py").write_text(ORACLE)
        self.catalog = {
            "schema_version": 1, "program_id": "DEMO", "seed": 7,
            "source_files": [self.artifact("source.cob")],
            "source_units": [{"source_id": "S1", "kind": "executable"}],
            "target": self.artifact("target.py"),
            "oracle": {**self.artifact("oracle.py"), "provenance": {"kind": "source_derived", "reference": "source.cob:S1"}},
            "rules": [{"rule_id": "R1", "kind": "business", "source_ids": ["S1"],
                       "python_path": "target.py", "python_symbol": "decide",
                       "distinction_fields": ["amount"], "required_coverage": ["below", "at_or_above"],
                       "positive_meaning": "eligibility predicate true", "negative_meaning": "eligibility predicate false"}]
        }
        self.save()

    def artifact(self, name):
        return {"path": name, "sha256": hashlib.sha256((self.root / name).read_bytes()).hexdigest()}

    def save(self):
        self.path.write_text(json.dumps(self.catalog))

    def generate(self):
        return rules.generate(self.path, max_candidates=1000)

    def test_generate_and_execute_200_meaningful_cases(self):
        cases = self.generate()
        self.assertEqual(len(cases["cases"]), 200)
        result = rules.run(self.path, cases)
        self.assertTrue(result["unit_data_gate_passed"])
        self.assertEqual(result["rules"][0]["passing"], {"positive": 100, "negative": 100})
        self.assertFalse(result["program_acceptance_established"])

    def test_irrelevant_variations_do_not_count(self):
        (self.root / "oracle.py").write_text('''def generate_cases(rule, seed):
    for n in range(200):
        yield {"case_id": str(n), "category": "positive", "inputs": {"amount": 100, "noise": n}, "expected": {"eligible": True}, "coverage_tags": ["at_or_above"]}
''')
        self.catalog["oracle"].update(self.artifact("oracle.py")); self.save()
        cases = self.generate()
        self.assertFalse(cases["generation_gate_passed"])
        self.assertEqual(len(cases["cases"]), 1)
        self.assertEqual(cases["rules"][0]["discarded_duplicates"], 199)

    def test_technical_rule_has_same_quota(self):
        self.catalog["rules"][0]["kind"] = "technical"; self.save()
        cases = self.generate(); cases["cases"] = cases["cases"][:100]
        result = rules.run(self.path, cases)
        self.assertFalse(result["unit_data_gate_passed"])
        self.assertEqual(result["rules"][0]["passing"]["positive"], 0)

    def test_unmapped_executable_source_blocks(self):
        self.catalog["source_units"].append({"source_id": "S2", "kind": "executable"}); self.save()
        with self.assertRaisesRegex(ValueError, "unmapped"):
            self.generate()

    def test_target_cannot_be_its_own_oracle(self):
        self.catalog["oracle"].update(self.artifact("target.py")); self.save()
        with self.assertRaisesRegex(ValueError, "independent"):
            self.generate()

    def test_oracle_dependencies_cannot_copy_target_or_target_helper(self):
        for copied_artifact in ("target.py", "pinned_rule_helper.py"):
            with self.subTest(copied_artifact=copied_artifact):
                if copied_artifact == "target.py":
                    (self.root / "target.py").write_text(TARGET.replace("amount >= 100", "amount >= 99"))
                    self.catalog["target"] = self.artifact("target.py")
                else:
                    helper = self.use_helper()
                    helper.write_text('def decide(amount):\n    return amount >= 99\n')
                    self.catalog["target"]["dependencies"] = [self.artifact(helper.name)]
                (self.root / "oracle_copy.py").write_bytes((self.root / copied_artifact).read_bytes())
                (self.root / "oracle.py").write_text('''from oracle_copy import decide
def generate_cases(rule, seed):
    for amount in range(-1, 199):
        answer = decide(amount)
        yield {"case_id": rule["rule_id"] + "-" + str(amount), "category": "positive" if answer else "negative", "inputs": {"amount": amount}, "expected": {"eligible": answer}, "coverage_tags": ["at_or_above" if answer else "below"]}
''')
                self.catalog["oracle"] = {**self.artifact("oracle.py"),
                    "dependencies": [self.artifact("oracle_copy.py")],
                    "provenance": {"kind": "source_derived", "reference": "source.cob:S1"}}
                self.save()
                with self.assertRaisesRegex(ValueError, "independent"):
                    self.generate()

    def test_stale_target_blocks_frozen_cases(self):
        cases = self.generate()
        (self.root / "target.py").write_text(TARGET + "\n# changed\n")
        with self.assertRaisesRegex(ValueError, "hash"):
            rules.run(self.path, cases)

    def test_case_catalog_fingerprint_must_match(self):
        cases = self.generate(); cases["catalog_sha256"] = "0" * 64
        with self.assertRaisesRegex(ValueError, "fingerprint"):
            rules.run(self.path, cases)

    def test_passing_output_without_rule_event_does_not_count(self):
        (self.root / "target.py").write_text(TARGET.replace('[{"rule_id": rule_id, "category": "positive" if answer else "negative"}]', '[]'))
        self.catalog["target"] = self.artifact("target.py"); self.save()
        result = rules.run(self.path, self.generate())
        self.assertFalse(result["unit_data_gate_passed"])
        self.assertEqual(result["rules"][0]["passing"]["positive"], 0)

    def test_adapter_cannot_skip_mapped_python_symbol(self):
        (self.root / "target.py").write_text(TARGET.replace('answer = decide(inputs["amount"])', 'answer = inputs["amount"] >= 100'))
        self.catalog["target"] = self.artifact("target.py"); self.save()
        result = rules.run(self.path, self.generate())
        self.assertFalse(result["unit_data_gate_passed"])
        self.assertIn("mapped symbol not executed", result["cases"][0]["failures"])

    def test_bad_known_python_logic_fails_negative_and_positive_assertions(self):
        (self.root / "target.py").write_text(TARGET.replace("amount >= 100", "amount >= 99"))
        self.catalog["target"] = self.artifact("target.py"); self.save()
        result = rules.run(self.path, self.generate())
        self.assertFalse(result["unit_data_gate_passed"])
        self.assertEqual(result["rules"][0]["passing"]["negative"], 99)

    def test_duplicate_ids_and_unknown_rules_rejected(self):
        cases = self.generate(); cases["cases"][1]["case_id"] = cases["cases"][0]["case_id"]
        with self.assertRaisesRegex(ValueError, "duplicate case"):
            rules.run(self.path, cases)
        cases = self.generate(); cases["cases"][0]["rule_id"] = "NOT_A_RULE"
        with self.assertRaisesRegex(ValueError, "unknown rule"):
            rules.run(self.path, cases)

    def test_missing_coverage_tag_prevents_gate(self):
        cases = self.generate()
        for case in cases["cases"]:
            case["coverage_tags"] = []
        self.assertFalse(rules.run(self.path, cases)["unit_data_gate_passed"])

    def test_nonfinite_and_path_escape_rejected(self):
        cases = self.generate(); cases["cases"][0]["expected"] = float("nan")
        with self.assertRaises(ValueError):
            rules.run(self.path, cases)
        self.catalog["target"]["path"] = "../target.py"; self.save()
        with self.assertRaisesRegex(ValueError, "escape"):
            self.generate()

    def test_target_exception_is_failure_not_a_passing_negative(self):
        (self.root / "target.py").write_text(TARGET.replace('answer = decide(inputs["amount"])', 'raise RuntimeError("failure before rule")'))
        self.catalog["target"] = self.artifact("target.py"); self.save()
        result = rules.run(self.path, self.generate())
        self.assertFalse(result["unit_data_gate_passed"])
        self.assertEqual(result["rules"][0]["passing"]["negative"], 0)

    def use_helper(self):
        helper = self.root / "pinned_rule_helper.py"
        helper.write_text('def decide(amount):\n    return amount >= 100\n')
        (self.root / "target.py").write_text(
            'from pinned_rule_helper import decide\n' + TARGET[TARGET.index('def evaluate'):])
        self.catalog["target"] = {**self.artifact("target.py"),
                                  "dependencies": [self.artifact(helper.name)]}
        self.catalog["rules"][0]["python_path"] = helper.name
        self.save()
        return helper

    def test_pinned_sibling_helper_loads_and_restores_module_state(self):
        self.use_helper()
        before = dict(sys.modules)
        finders = list(sys.meta_path)
        result = rules.run(self.path, self.generate())
        self.assertTrue(result["unit_data_gate_passed"])
        for name in ("target", "oracle", "pinned_rule_helper"):
            self.assertIs(sys.modules.get(name), before.get(name))
        self.assertEqual(sys.meta_path, finders)

    def test_cached_helper_cannot_satisfy_new_pinned_bytes(self):
        helper = self.use_helper()
        old_module = types.ModuleType("pinned_rule_helper")
        exec(compile(helper.read_bytes(), str(helper), "exec"), old_module.__dict__)
        previous = sys.modules.get("pinned_rule_helper")
        sys.modules["pinned_rule_helper"] = old_module
        try:
            helper.write_text('def decide(amount):\n    return amount >= 1000\n')
            self.catalog["target"]["dependencies"] = [self.artifact(helper.name)]
            self.save()
            result = rules.run(self.path, self.generate())
            self.assertFalse(result["unit_data_gate_passed"])
            self.assertEqual(result["rules"][0]["passing"]["positive"], 0)
            self.assertIs(sys.modules["pinned_rule_helper"], old_module)
        finally:
            if previous is None:
                sys.modules.pop("pinned_rule_helper", None)
            else:
                sys.modules["pinned_rule_helper"] = previous

    def test_stale_timestamp_bytecode_cannot_replace_pinned_helper(self):
        helper = self.use_helper()
        previous_stat = helper.stat()
        py_compile.compile(str(helper), doraise=True)
        helper.write_text('def decide(amount):\n    return amount >= 999\n')
        os.utime(helper, ns=(previous_stat.st_atime_ns, previous_stat.st_mtime_ns))
        self.assertEqual(helper.stat().st_size, previous_stat.st_size)
        self.catalog["target"]["dependencies"] = [self.artifact(helper.name)]; self.save()
        result = rules.run(self.path, self.generate())
        self.assertFalse(result["unit_data_gate_passed"])
        self.assertEqual(result["rules"][0]["passing"]["positive"], 0)

    def test_import_failure_restores_previous_modules_and_finders(self):
        helper = self.use_helper()
        helper.write_text('raise RuntimeError("synthetic loading failure")\n'
                          'def decide(amount):\n    return amount >= 100\n')
        self.catalog["target"]["dependencies"] = [self.artifact(helper.name)]; self.save()
        before, finders = dict(sys.modules), list(sys.meta_path)
        with self.assertRaisesRegex(RuntimeError, "synthetic loading failure"):
            rules.run(self.path, self.generate())
        for name in ("target", "oracle", "pinned_rule_helper"):
            self.assertIs(sys.modules.get(name), before.get(name))
        self.assertEqual(sys.meta_path, finders)

    def test_dataclasses_with_postponed_annotations_are_registered(self):
        (self.root / "target.py").write_text(
            'from __future__ import annotations\nfrom dataclasses import dataclass\n'
            '@dataclass\nclass Record:\n    amount: int\n\n' + TARGET)
        self.catalog["target"] = self.artifact("target.py"); self.save()
        self.assertTrue(rules.run(self.path, self.generate())["unit_data_gate_passed"])

    def test_nested_shadow_does_not_count_as_top_level_rule_execution(self):
        (self.root / "target.py").write_text('''def decide(amount):
    raise RuntimeError("declared top-level rule")

def evaluate(rule_id, inputs):
    def decide(amount):
        return amount >= 100
    answer = decide(inputs["amount"])
    return {"actual": {"eligible": answer}, "rule_events": [{"rule_id": rule_id, "category": "positive" if answer else "negative"}]}
''')
        self.catalog["target"] = self.artifact("target.py"); self.save()
        result = rules.run(self.path, self.generate())
        self.assertFalse(result["unit_data_gate_passed"])
        self.assertEqual(result["cases"][0]["mapped_symbol_calls"], 0)

    def test_non_json_observations_produce_readable_cli_failure_receipts(self):
        for index, expression in enumerate(('float("nan")', 'object()')):
            with self.subTest(expression=expression):
                (self.root / "target.py").write_text(TARGET.replace(
                    '"actual": {"eligible": answer}', '"actual": {"eligible": ' + expression + '}'))
                self.catalog["target"] = self.artifact("target.py"); self.save()
                cases = self.generate()
                case_path = self.root / f"cases-{index}.json"
                case_path.write_text(json.dumps(cases))
                output = self.root / f"result-{index}.json"
                result = subprocess.run([
                    sys.executable, str(Path(rules.__file__)), "run", "--catalog", str(self.path),
                    "--cases", str(case_path), "--output", str(output), "--allow-local-execution"],
                    text=True, capture_output=True)
                self.assertEqual(result.returncode, 2)
                self.assertEqual(result.stderr, "")
                receipt = json.loads(output.read_text())
                self.assertFalse(receipt["unit_data_gate_passed"])
                self.assertIsNone(receipt["cases"][0]["observed"])
                self.assertTrue(receipt["cases"][0]["failures"])

    def test_optional_root_supports_nested_program_catalog(self):
        self.path = self.root / "programs/DEMO/analysis/rule-catalog.json"
        self.path.parent.mkdir(parents=True)
        self.save()
        cases = rules.generate(self.path, root=self.root)
        self.assertTrue(rules.run(self.path, cases, root=self.root)["unit_data_gate_passed"])
        output = self.root / "generated.json"
        completed = subprocess.run([
            sys.executable, str(Path(rules.__file__)), "generate", "--catalog", str(self.path),
            "--root", str(self.root), "--output", str(output), "--allow-local-execution"],
            text=True, capture_output=True)
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertTrue(json.loads(output.read_text())["generation_gate_passed"])
        with self.assertRaisesRegex(ValueError, "catalog.*inside"):
            rules.catalog(self.path, root=self.path.parent / "missing-root")

    def test_missing_entire_rule_is_reported_with_zero_passing_cases(self):
        self.catalog["source_units"].append({"source_id": "S2", "kind": "executable"})
        self.catalog["rules"].append({**self.catalog["rules"][0], "rule_id": "R2", "source_ids": ["S2"]})
        self.save()
        cases = self.generate()
        cases["cases"] = [case for case in cases["cases"] if case["rule_id"] != "R2"]
        result = rules.run(self.path, cases)
        self.assertFalse(result["unit_data_gate_passed"])
        missing = next(row for row in result["rules"] if row["rule_id"] == "R2")
        self.assertEqual(missing["passing"], {"positive": 0, "negative": 0})
        self.assertFalse(missing["meets_quota"])

    def test_unsupported_import_layouts_fail_clearly(self):
        for statement in ('from .helper import decide\n', 'import undeclared_rule_helper\n'):
            with self.subTest(statement=statement):
                (self.root / "target.py").write_text(statement + TARGET)
                self.catalog["target"] = self.artifact("target.py"); self.save()
                with self.assertRaisesRegex(ValueError, "unsupported.*import"):
                    rules.run(self.path, self.generate())

    def test_async_mapped_symbol_is_rejected(self):
        (self.root / "target.py").write_text(TARGET.replace('def decide', 'async def decide'))
        self.catalog["target"] = self.artifact("target.py"); self.save()
        with self.assertRaisesRegex(ValueError, "async"):
            self.generate()


if __name__ == "__main__":
    unittest.main()
