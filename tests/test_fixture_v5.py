"""Source-valid risk-qualified fixtures and actual target evidence, not count padding."""
import copy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from workbench.cics import (adversarial_screen, emit_screen, parse_bms,
                            plan_screen_cases, verify_screen)
from workbench.domain import ValidationError, encode, sha
from workbench.fixtures import adversarial_review, plan_cases, validation_policy, verify_program
from workbench.orchestration import verify_jobs
from workbench.reference import run_reference
from workbench.source import analyze_program
from workbench.target import emit_jobs, emit_program
from test_cics import BMS, fixture as screen_fixture
from test_fixture_v3 import LINKED, executed_logic_inputs
from test_source import COBOL


class FixtureV5Tests(unittest.TestCase):
    def program(self, source=COBOL):
        value = analyze_program('ELIGIBLE.cbl', source, {})
        self.assertFalse(value['blockers'], value['blockers'])
        value['target_contract_version'] = 2
        return value

    def suite(self, program, seed=37, budget=4096):
        return plan_cases(program, seed, budget, 64, fixture_contract_version=5)

    def independently_count(self, program, suite):
        states = {rule['id']: set() for rule in program['rules']}
        for case in suite['cases']:
            if not case.get('randomized') or case['intentional_invalid']:
                continue
            for rid, value in executed_logic_inputs(program, case['record']).items():
                states[rid].add(sha(encode(value)))
        return {rid: len(values) for rid, values in states.items()}

    def test_historical_v1_v3_v4_replay_exactly_without_new_policy(self):
        hashes = {
            1: '36fb1af7e1a942f4fcc33d4af7fa40f237eb61e27330ec719a2b74d612bc19f3',
            3: '7c7047bfd52d26c786dadcf8302365a3ad78ec10a9c1e5eca96f91e19b0aedfd',
            4: '0fabc5368e024dda0238a63ce1f6209331aee2df8dc1e200aae160dde8375342',
        }
        for version, digest in hashes.items():
            with self.subTest(version=version):
                suite = plan_cases(self.program(), 37, 256, 0 if version == 1 else 20,
                                   fixture_contract_version=version)
                self.assertEqual(sha(encode(suite)), digest)
                self.assertNotIn('validation_policy', suite['coverage'])
                self.assertFalse(verify_program(self.program(), emit_program(self.program()), suite)['differences'])
        with self.assertRaises(ValidationError):
            plan_cases(self.program(), 37, 256, 64, fixture_contract_version=4)

    def test_base_floor_reconciles_independent_execution_and_actual_target(self):
        program = self.program(); suite = self.suite(program)
        self.assertEqual(suite['version'], 5)
        self.assertEqual(suite['coverage']['randomized_record_counts'], self.independently_count(program, suite))
        self.assertTrue(all(count >= 64 for count in self.independently_count(program, suite).values()))
        self.assertEqual(set(suite['coverage']['requirements_per_logic'].values()), {64})
        self.assertEqual(suite['coverage']['validation_policy']['risk_inputs'], [])
        for case in suite['cases']:
            self.assertEqual(case['expected'], run_reference(program, case['record']))
        result = verify_program(program, emit_program(program), suite)
        self.assertEqual(result['matched_count'], len(suite['cases']))
        self.assertFalse(result['observed_legacy_parity'])
        self.assertTrue(adversarial_review(program, emit_program(program), suite)['passed'])

    def test_compound_risk_records_source_and_only_raises_affected_rule(self):
        program = self.program(COBOL.replace('IF AGE >= 18', 'IF AGE >= 18 AND ACTIVE = "Y"'))
        suite = self.suite(program); first, second = [rule['id'] for rule in program['rules']]
        policy = suite['coverage']['validation_policy']
        self.assertEqual(policy['requirements_per_logic'], {first: 128, second: 64})
        risk = policy['risk_inputs'][0]
        self.assertEqual(risk['reasons'], ['compound_predicate'])
        self.assertEqual(risk['source_hash'], program['source_hash'])
        self.assertEqual(risk['source_path'], program['path'])
        self.assertEqual(risk['source_start'], program['rules'][0]['source_start'])
        self.assertEqual(suite['coverage']['randomized_record_counts'], self.independently_count(program, suite))
        self.assertGreaterEqual(self.independently_count(program, suite)[first], 128)
        for witness in suite['coverage']['positive_negative_witnesses'].values():
            self.assertGreater(witness['true_cases'], 0)
            self.assertGreater(witness['false_cases'], 0)
        review = adversarial_review(program, emit_program(program), suite)
        connectors = [row for row in review['mutations'] if row['kind'] == 'logical_operator']
        self.assertTrue(connectors)
        self.assertTrue(all(row['detected'] and row['witnesses'] for row in connectors))
        self.assertTrue(review['passed'])

    def test_linked_keys_have_128_distinct_states_and_both_source_outcomes(self):
        program = self.program(LINKED); suite = self.suite(program)
        rid = program['rules'][0]['id']
        self.assertEqual(suite['coverage']['requirements_per_logic'][rid], 128)
        self.assertEqual(suite['coverage']['validation_policy']['risk_inputs'][0]['reasons'], ['cross_layout_compared_key'])
        self.assertGreaterEqual(self.independently_count(program, suite)[rid], 128)
        relations = {row['status'] for case in suite['cases'] for row in case['correlations']}
        self.assertEqual(relations, {'MATCH', 'INTENTIONAL_MISMATCH'})
        for case in suite['cases']:
            if case['intentional_invalid']: continue
            self.assertEqual(case['files']['INPUT-RECORD'][0]['INPUT-ID'], case['record']['INPUT-ID'])
            self.assertEqual(case['files']['MASTER-RECORD'][0]['MASTER-ID'], case['record']['MASTER-ID'])
        self.assertFalse(verify_program(program, emit_program(program), suite)['differences'])
        self.assertFalse(suite['coverage']['correlation_gaps'])

    def test_prior_effect_cannot_fabricate_128_downstream_states(self):
        program = self.program(COBOL.replace('IF ACTIVE = "N"', 'IF DECISION = "Y"'))
        suite = self.suite(program); rid = program['rules'][1]['id']
        self.assertEqual(suite['coverage']['requirements_per_logic'][rid], 128)
        self.assertEqual(suite['coverage']['validation_policy']['risk_inputs'][0]['reasons'], ['prior_effect_changes_predicate_input'])
        self.assertEqual(self.independently_count(program, suite)[rid], 2)
        gap = next(row for row in suite['coverage']['record_count_gaps'] if row['rule_id'] == rid)
        self.assertEqual((gap['required'], gap['observed']), (128, 2))
        self.assertEqual(gap['status'], 'bounded_generation_exhausted')
        self.assertFalse(suite['coverage']['complete'])

    def test_finite_domain_no_unused_field_or_duplicate_padding(self):
        program = self.program(COBOL.replace('AGE PIC 9(3)', 'AGE PIC 9').replace('AGE >= 18', 'AGE >= 5'))
        suite = self.suite(program); rid = program['rules'][0]['id']
        self.assertEqual(self.independently_count(program, suite)[rid], 10)
        gap = next(row for row in suite['coverage']['record_count_gaps'] if row['rule_id'] == rid)
        self.assertEqual((gap['required'], gap['observed'], gap['proven_input_domain_size']), (64, 10, 10))
        self.assertEqual(gap['status'], 'limited_input_domain')
        self.assertEqual(verify_program(program, emit_program(program), suite)['status'], 'MATCHED_WITH_COVERAGE_GAPS')
        self.assertEqual(len({sha(encode(case['record'])) for case in suite['cases']}), len(suite['cases']))

    def test_budget_keeps_exact_named_state_and_obligation_deficits(self):
        program = self.program(); suite = self.suite(program, budget=2)
        self.assertEqual(len(suite['cases']), 2)
        self.assertTrue(suite['coverage']['record_count_gaps'])
        self.assertTrue(all(row['required'] == 64 for row in suite['coverage']['record_count_gaps']))
        self.assertTrue(suite['coverage']['obligation_gaps'])
        self.assertFalse(suite['coverage']['complete'])
        for invalid in (4097, True, 0):
            with self.subTest(invalid=invalid), self.assertRaises(ValidationError):
                self.suite(program, budget=invalid)
        self.assertEqual(validation_policy(program)['candidate_cap'], 10000)

    def test_layout_endpoints_spacing_leading_zeros_and_strict_negatives(self):
        program = self.program(COBOL.replace('ACTIVE PIC X.', 'ACTIVE PIC X(4).'))
        suite = self.suite(program)
        accepted = [case['record'] for case in suite['cases'] if not case['intentional_invalid']]
        self.assertTrue({0, 999}.issubset({record['AGE'] for record in accepted}))
        self.assertTrue({'    ', '0000', '9999', 'A   ', '   A'}.issubset({record['ACTIVE'] for record in accepted}))
        invalid = [case for case in suite['cases'] if case['intentional_invalid']]
        self.assertTrue(invalid)
        self.assertTrue(all(not case['logic_input_hashes'] for case in invalid))
        result = verify_program(program, emit_program(program), suite)
        self.assertEqual(result['invalid_inputs_executed'], len(invalid))
        self.assertFalse(result['differences'])

    def test_seed_policy_case_and_expectation_tampering_fail_before_target(self):
        from unittest.mock import patch
        program = self.program(); suite = self.suite(program)
        mutations = []
        changed = copy.deepcopy(suite); changed['seed'] += 1; mutations.append(changed)
        changed = copy.deepcopy(suite); changed['coverage']['validation_policy']['base_minimum'] = 20; mutations.append(changed)
        changed = copy.deepcopy(suite); changed['cases'][0]['expected']['return_code'] = 9; mutations.append(changed)
        changed = copy.deepcopy(suite); changed['coverage']['requirements_per_logic'][program['rules'][0]['id']] = 20; mutations.append(changed)
        with patch('workbench.fixtures.prepare_generated', side_effect=AssertionError('target executed before frozen contract validation')):
            for changed in mutations:
                with self.subTest(contract=changed['contract_hash']), self.assertRaises(ValidationError):
                    verify_program(program, emit_program(program), changed)
        self.assertEqual(encode(suite), encode(self.suite(json.loads(encode(program)))))
        self.assertNotEqual(encode(suite), encode(self.suite(program, seed=38)))

    def test_no_rules_still_requires_64_actual_layout_terminal_comparisons(self):
        program = self.program(COBOL[:COBOL.index('  IF AGE')] + '  GOBACK.\n')
        suite = self.suite(program)
        self.assertEqual(suite['coverage']['requirements_per_logic'], {})
        for row in suite['coverage']['logic_validation']['technical'].values():
            self.assertGreaterEqual(row['randomized_valid_records'], 64)
            self.assertTrue(row['complete'])
        self.assertFalse(verify_program(program, emit_program(program), suite)['differences'])

    def test_cli_new_generation_uses_v5_and_recorded_runtime_seed(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary); source = root / 'eligible.cbl'; source.write_text(COBOL)
            output = root / 'suite.json'
            process = subprocess.run([sys.executable, 'tools/synthetic_cases.py', '--source', str(source),
                                      '--output', str(output), '--seed', '37'], capture_output=True, text=True)
            self.assertEqual(process.returncode, 0, process.stderr)
            suite = json.loads(output.read_bytes())
            self.assertEqual((suite['version'], suite['seed'], suite['coverage']['budget']), (5, 37, 4096))
            self.assertTrue(all(count >= 64 for count in suite['coverage']['randomized_record_counts'].values()))


class ScreenV5Tests(unittest.TestCase):
    def suite(self, screen, budget=4096):
        return plan_screen_cases(screen, 9182, 64, budget, fixture_contract_version=5)

    def test_source_field_boundaries_protected_fields_and_invalid_types_compare(self):
        screen = screen_fixture(); suite = self.suite(screen); code = emit_screen(screen)
        self.assertGreaterEqual(suite['coverage']['fields']['ACCT'], 64)
        self.assertGreaterEqual(suite['coverage']['layout_randomized_states'], 64)
        accepted = {case['values']['ACCT'] for case in suite['cases'] if case['expected']['input_status'] == 'ACCEPT_INPUT'}
        self.assertTrue({'00000000', '        ', 'A       ', '       A'}.issubset(accepted))
        rejected = [case for case in suite['cases'] if case['kind'] == 'invalid_target_request']
        self.assertTrue(any(case['values'] == {} for case in rejected))
        self.assertTrue(any(isinstance(case['values'], dict) and 'MSG' in case['values'] for case in rejected))
        self.assertTrue(any(isinstance(case['values'], dict) and type(case['values'].get('ACCT')) is float for case in rejected))
        self.assertTrue(all(case['expected']['input_status'] == 'REJECT_INPUT' for case in rejected))
        self.assertEqual(len({sha(encode(case['values'])) for case in suite['cases']}), len(suite['cases']))
        for row in suite['coverage']['constant_fields'].values():
            self.assertEqual(row['distinct_source_display_values'], 1)
            self.assertIn('not 64 distinct display values', row['basis'])
        self.assertTrue(verify_screen(screen, code, suite)['passed'])
        self.assertTrue(adversarial_screen(screen, code, suite)['passed'])
        self.assertFalse(verify_screen(screen, code, suite)['native_controller_verified'])

    def test_static_only_screen_never_pads_a_single_state_into_64(self):
        screen = parse_bms('maps/STATIC.bms', BMS.replace('UNPROT,NORM,IC', 'PROT,NORM'))['screens'][0]
        suite = self.suite(screen)
        self.assertEqual(suite['coverage']['layout_randomized_states'], 0)
        gap = next(row for row in suite['coverage']['gaps'] if row['kind'] == 'screen_layout_state_deficit')
        self.assertEqual((gap['required'], gap['observed']), (64, 0))
        self.assertIn('one valid input state', gap['reason'])
        self.assertFalse(verify_screen(screen, emit_screen(screen), suite)['passed'])

    def test_screen_budget_never_hides_boundary_or_negative_deficits(self):
        text = 'MAPS DFHMSD TYPE=MAP,LANG=COBOL,MODE=INOUT\nSCREEN DFHMDI SIZE=(24,80)\n'
        text += ''.join(f'F{i} DFHMDF POS=({i+1},1),LENGTH=8,ATTRB=(UNPROT,NORM)\n' for i in range(20))
        text += ' DFHMSD TYPE=FINAL\n END\n'
        parsed = parse_bms('maps/MANY.bms', text)
        self.assertFalse(parsed['gaps'])
        suite = self.suite(parsed['screens'][0], budget=64)
        self.assertLessEqual(len(suite['cases']), 64)
        kinds = {row['kind'] for row in suite['coverage']['gaps']}
        self.assertTrue({'screen_boundary_budget_deficit', 'screen_negative_budget_deficit', 'screen_layout_state_deficit'}.issubset(kinds))
        self.assertFalse(suite['coverage']['complete'])
        with self.assertRaises(ValidationError): self.suite(screen_fixture(), budget=4097)

    def test_screen_contract_removal_or_count_tampering_cannot_recognize_v5_as_v4(self):
        screen = screen_fixture(); suite = self.suite(screen)
        changed = copy.deepcopy(suite); changed.pop('fixture_contract_version')
        with self.assertRaises(ValidationError): verify_screen(screen, emit_screen(screen), changed)
        changed = copy.deepcopy(suite); changed['coverage']['fields']['ACCT'] = 999
        with self.assertRaises(ValidationError): adversarial_screen(screen, emit_screen(screen), changed)


class OrderedJobV5Tests(unittest.TestCase):
    def test_steps_require_64_distinct_executed_inputs_and_compared_order(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary); program = analyze_program('ELIGIBLE.cbl', COBOL, {})
            program['target_contract_version'] = 2; code = emit_program(program); version = sha(code)
            path = root / 'shared' / 'target' / 'python' / (version + '.py')
            path.parent.mkdir(parents=True); path.write_bytes(code.encode('utf-8'))
            doc = {'jobs': [{'name': 'JOBA', 'steps': [{'name': 'S1', 'program': 'ELIGIBLE', 'condition': ''},
                                                        {'name': 'S2', 'program': 'ELIGIBLE', 'condition': 'RC=0'}]}],
                   'analysis': {'programs': {'ELIGIBLE': program}}, 'program_versions': {'ELIGIBLE': version},
                   'authorization': {'seed': 781, 'max_cases_per_program': 4096}, 'fixture_contract_version': 5}
            jobs = emit_jobs(doc, doc['program_versions']); result = verify_jobs(doc, root, jobs)
            self.assertTrue(result['matched'], result)
            self.assertEqual(result['validation']['minimum_distinct_records_per_step'], 64)
            self.assertTrue(all(row['executed_records'] >= 64 for row in result['validation']['steps']))
            self.assertTrue(all(case['expected'] == case['actual'] for case in result['cases']))
            self.assertEqual(encode(result), encode(verify_jobs(doc, root, jobs)))
            doc['jobs'][0]['steps'][1]['condition'] = 'RC>0'
            result = verify_jobs(doc, root, emit_jobs(doc, doc['program_versions']))
            self.assertFalse(result['matched'])
            self.assertEqual(result['validation']['steps'][1]['executed_records'], 0)
            self.assertTrue(result['validation']['gaps'])
            doc['authorization']['max_cases_per_program'] = 4097
            with self.assertRaises(ValidationError): verify_jobs(doc, root, jobs)
