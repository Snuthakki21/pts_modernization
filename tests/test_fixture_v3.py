"""Opt-in fixture density counts executed logic inputs, not padded records."""
import copy
import json
import random
import secrets
import string
import unittest

from workbench.domain import ValidationError, encode, sha
from workbench.fixtures import adversarial_review, plan_cases, verify_program
from workbench.reference import predicate, run_reference
from workbench.source import analyze_program
from workbench.target import emit_program, prepare_generated
from test_source import COBOL


LINKED = '''IDENTIFICATION DIVISION.
PROGRAM-ID. LINKED.
DATA DIVISION.
LINKAGE SECTION.
01 INPUT-RECORD.
  05 INPUT-ID PIC 9(2).
  05 RESULT PIC X.
01 MASTER-RECORD.
  05 MASTER-ID PIC 9(2).
PROCEDURE DIVISION USING INPUT-RECORD MASTER-RECORD.
  IF INPUT-ID = MASTER-ID
    MOVE "Y" TO RESULT
  ELSE
    MOVE "N" TO RESULT
  END-IF.
  GOBACK.
'''


def predicate_fields(node):
    if not isinstance(node, dict):
        return set()
    if 'field' in node:
        return {node['field']}
    return predicate_fields(node['left']) | predicate_fields(node['right'])


def executed_logic_inputs(program, record):
    """Replay supported source state without trusting fixture coverage metadata."""
    state = record.copy()
    inputs = {}
    for rule in program['rules']:
        names = sorted(predicate_fields(rule['predicate']))
        inputs[rule['id']] = {name: state[name] for name in names}
        branch = predicate(rule['predicate'], state)
        for effect in rule['then'] if branch else rule['else']:
            state[effect['field']] = effect['value']
    return inputs


class FixtureV3Tests(unittest.TestCase):
    def program(self, text=COBOL, version=2):
        program = analyze_program('ELIGIBLE.cbl', text, {})
        self.assertFalse(program['blockers'], program['blockers'])
        if version == 2:
            program['target_contract_version'] = 2
        return program

    def accepted(self, suite):
        return [case for case in suite['cases']
                if case['expected']['input_status'] == 'ACCEPT_INPUT']

    def independent_counts(self, program, suite):
        signatures = {rule['id']: set() for rule in program['rules']}
        for case in self.accepted(suite):
            for rid, inputs in executed_logic_inputs(program, case['record']).items():
                signatures[rid].add(sha(encode(inputs)))
        return {rid: len(hashes) for rid, hashes in signatures.items()}

    def assert_files_are_input_projections(self, program, suite):
        for case in suite['cases']:
            projections = {}
            if isinstance(case['record'], dict):
                for name, value in case['record'].items():
                    if name in program['fields']:
                        group = program['fields'][name]['group']
                        projections.setdefault(group, {})[name] = value
            self.assertEqual(case['files'], {group: [row]
                                            for group, row in projections.items()})

    def test_default_and_explicit_none_preserve_frozen_v1_v2_suite_bytes(self):
        pinned = {
            1: 'e0679cba54a12eaae407f0d0f06acd3c35d84604e0e7868237fab07c5a6b1076',
            2: 'fa772e3d4039128dff09e008e668d5f0fea0c241b28fd67e9d0634a182cc26c2',
        }
        for version, expected_hash in pinned.items():
            with self.subTest(version=version):
                program = self.program(version=version)
                suite = plan_cases(program)
                self.assertEqual(sha(encode(suite)), expected_hash)
                self.assertEqual(encode(suite), encode(plan_cases(
                    program, min_records_per_logic=None)))
                self.assertEqual(encode(suite), encode(plan_cases(
                    program, min_records_per_logic=0)))
                self.assertEqual(suite['version'], 1)
                self.assertEqual(suite['generator_version'], f'source-subset-{version}')
                self.assertNotIn('min_records_per_logic', suite['coverage'])
                # The historical complete flag covers branches and obligations;
                # it never established ten distinct logic input signatures.
                self.assertTrue(suite['coverage']['complete'])
                self.assertEqual(list(self.independent_counts(program, suite).values()), [6, 3])

    def test_opt_in_twenty_covers_each_rule_with_distinct_valid_logic_inputs(self):
        program = self.program()
        frozen_program = encode(program)
        suite = plan_cases(program, min_records_per_logic=20)
        self.assertEqual(suite['version'], 3)
        self.assertEqual(suite['generator_version'], 'source-subset-3')
        self.assertEqual(suite['coverage']['min_records_per_logic'], 20)
        self.assertEqual(program['target_contract_version'], 2)
        self.assertEqual(encode(program), frozen_program)
        self.assertEqual(suite['coverage']['record_counts'], self.independent_counts(program, suite))
        self.assertTrue(all(count >= 20 for count in suite['coverage']['record_counts'].values()))
        self.assertFalse(suite['coverage']['record_count_gaps'])
        summary = suite['coverage']['logic_validation']
        self.assertTrue(summary['complete'])
        self.assertEqual(summary['minimum_distinct_records_per_logic'], 20)
        self.assertEqual(summary['applicable_logic_count'], len(program['rules']))
        self.assertEqual(summary['logic_meeting_minimum'], len(program['rules']))
        self.assertEqual(summary['records_per_logic'], self.independent_counts(program, suite))
        self.assertEqual(summary['distinct_logic_records'], sum(summary['records_per_logic'].values()))
        for branches in suite['coverage']['rules'].values():
            self.assertTrue(branches['true'])
            self.assertTrue(branches['false'])
        result = verify_program(program, emit_program(program), suite)
        self.assertFalse(result['differences'])
        self.assertEqual(result['status'], 'MATCHED_SOURCE_DERIVED_EXPECTATIONS')
        self.assertFalse(result['observed_legacy_parity'])

    def test_density_argument_requires_an_integer_between_ten_and_twenty(self):
        program = self.program()
        for invalid in (9, 21, -1, True, False, 10.0, '10', [], {}):
            with self.subTest(invalid=invalid):
                with self.assertRaises(ValidationError):
                    plan_cases(program, min_records_per_logic=invalid)
        for minimum in (10, 20):
            self.assertEqual(plan_cases(program, min_records_per_logic=minimum)
                             ['coverage']['min_records_per_logic'], minimum)

    def test_metadata_reconciles_to_independent_source_state_and_group_projection(self):
        program = self.program()
        suite = plan_cases(program, min_records_per_logic=10)
        hashes = {rule['id']: set() for rule in program['rules']}
        for case in suite['cases']:
            self.assertEqual(case['expected'], run_reference(program, case['record']))
            if case['expected']['input_status'] == 'ACCEPT_INPUT':
                inputs = executed_logic_inputs(program, case['record'])
                self.assertEqual(case['logic_inputs'], inputs)
                self.assertEqual(case['logic_input_hashes'], {
                    rid: sha(encode(values)) for rid, values in inputs.items()})
                for rid, digest in case['logic_input_hashes'].items():
                    hashes[rid].add(digest)
            else:
                self.assertFalse(case.get('logic_inputs'))
                self.assertFalse(case.get('logic_input_hashes'))
        for rule in program['rules']:
            rid = rule['id']
            self.assertEqual(suite['coverage']['logic_fields'][rid],
                             sorted(predicate_fields(rule['predicate'])))
            self.assertEqual(set(suite['coverage']['record_hashes'][rid]), hashes[rid])
            self.assertEqual(len(suite['coverage']['record_hashes'][rid]), len(hashes[rid]))
            self.assertEqual(suite['coverage']['record_counts'][rid], len(hashes[rid]))
        self.assert_files_are_input_projections(program, suite)

    def test_single_digit_domain_cannot_supply_twenty_distinct_inputs(self):
        text = COBOL.replace('AGE PIC 9(3)', 'AGE PIC 9').replace('AGE >= 18', 'AGE >= 5')
        program = self.program(text)
        suite = plan_cases(program, min_records_per_logic=20)
        rid = program['rules'][0]['id']
        ages = {case['record']['AGE'] for case in self.accepted(suite)}
        self.assertEqual(ages, set(range(10)))
        self.assertEqual(suite['coverage']['record_counts'][rid], 10)
        gaps = [gap for gap in suite['coverage']['record_count_gaps'] if gap['rule_id'] == rid]
        self.assertEqual(len(gaps), 1)
        self.assertEqual(gaps[0]['required'], 20)
        self.assertEqual(gaps[0]['observed'], 10)
        self.assertTrue(gaps[0]['reason'])
        self.assertIn('domain', gaps[0]['status'])
        self.assertFalse(gaps[0]['multiplicity_applicable'])
        self.assertEqual(gaps[0]['proven_input_domain_size'], 10)
        self.assertFalse(suite['coverage']['complete'])
        self.assertFalse(suite['coverage']['logic_validation']['complete'])
        self.assertEqual(verify_program(program, emit_program(program), suite)['status'],
                         'MATCHED_WITH_COVERAGE_GAPS')

    def test_small_budgets_report_density_gaps_without_duplicate_credit(self):
        program = self.program()
        for budget in (1, 2):
            with self.subTest(budget=budget):
                suite = plan_cases(program, budget=budget, min_records_per_logic=10)
                self.assertLessEqual(len(suite['cases']), budget)
                self.assertEqual(suite['coverage']['record_counts'],
                                 self.independent_counts(program, suite))
                self.assertTrue(all(count <= budget for count in
                                    suite['coverage']['record_counts'].values()))
                gaps = suite['coverage']['record_count_gaps']
                self.assertEqual({gap['rule_id'] for gap in gaps},
                                 {rule['id'] for rule in program['rules']})
                self.assertTrue(all(gap['required'] == 10 and gap['observed'] <= budget
                                    and gap['reason'] and 'budget' in gap['status'] for gap in gaps))
                self.assertFalse(suite['coverage']['complete'])
                self.assertEqual(verify_program(program, emit_program(program), suite)['status'],
                                 'MATCHED_WITH_COVERAGE_GAPS')

    def test_expanded_budget_is_opt_in_and_remains_bounded(self):
        program = self.program()
        with self.assertRaises(ValidationError):
            plan_cases(program, budget=257)
        for budget in (257, 10000):
            suite = plan_cases(program, budget=budget, min_records_per_logic=10)
            self.assertEqual(suite['coverage']['budget'], budget)
            self.assertLessEqual(len(suite['cases']), budget)
        for invalid in (0, 10001, True, 257.0):
            with self.subTest(budget=invalid):
                with self.assertRaises(ValidationError):
                    plan_cases(program, budget=invalid, min_records_per_logic=10)

    def test_overwritten_input_field_cannot_pad_downstream_logic_density(self):
        text = COBOL.replace('IF ACTIVE = "N"', 'IF DECISION = "Y"')
        program = self.program(text)
        suite = plan_cases(program, min_records_per_logic=10)
        rid = program['rules'][1]['id']
        self.assertGreater(len(self.accepted(suite)), 10)
        self.assertEqual(suite['coverage']['logic_fields'][rid], ['DECISION'])
        self.assertEqual(self.independent_counts(program, suite)[rid], 2)
        self.assertEqual(suite['coverage']['record_counts'][rid], 2)
        self.assertEqual({case['logic_inputs'][rid]['DECISION']
                          for case in self.accepted(suite)}, {'Y', 'N'})
        self.assertTrue(any(gap['rule_id'] == rid and gap['observed'] == 2
                            for gap in suite['coverage']['record_count_gaps']))
        self.assertFalse(suite['coverage']['complete'])

    def test_constant_true_predicate_keeps_unreachable_branch_and_density_gaps(self):
        program = self.program(COBOL.replace('AGE >= 18', '1 = 1'))
        suite = plan_cases(program, min_records_per_logic=10)
        rid = program['rules'][0]['id']
        self.assertEqual(suite['coverage']['record_counts'][rid], 1)
        self.assertEqual(suite['coverage']['logic_fields'][rid], [])
        self.assertTrue(suite['coverage']['rules'][rid]['true'])
        self.assertFalse(suite['coverage']['rules'][rid]['false'])
        self.assertTrue(any(gap['rule_id'] == rid and gap['branch'] == 'false'
                            for gap in suite['coverage']['gaps']))
        self.assertTrue(any(gap['rule_id'] == rid and gap['observed'] == 1
                            for gap in suite['coverage']['record_count_gaps']))
        self.assertFalse(suite['coverage']['complete'])
        self.assertEqual(verify_program(program, emit_program(program), suite)['status'],
                         'MATCHED_WITH_COVERAGE_GAPS')
        review = adversarial_review(program, emit_program(program), suite)
        self.assertFalse(review['passed'])
        self.assertTrue(review['gaps'])

    def test_linked_groups_record_matched_and_intentionally_mismatched_keys(self):
        program = self.program(LINKED)
        suite = plan_cases(program, min_records_per_logic=20)
        rid = program['rules'][0]['id']
        statuses = set()
        for case in self.accepted(suite):
            relation, = case['correlations']
            self.assertEqual(relation['left'], 'INPUT-ID')
            self.assertEqual(relation['right'], 'MASTER-ID')
            self.assertEqual(relation['left_group'], 'INPUT-RECORD')
            self.assertEqual(relation['right_group'], 'MASTER-RECORD')
            self.assertEqual(relation['left_value'], case['record']['INPUT-ID'])
            self.assertEqual(relation['right_value'], case['record']['MASTER-ID'])
            self.assertEqual(relation['source_refs'], program['relationships'][0]['source_refs'])
            matched = case['record']['INPUT-ID'] == case['record']['MASTER-ID']
            self.assertEqual(relation['status'], 'MATCH' if matched else 'INTENTIONAL_MISMATCH')
            self.assertEqual(case['expected']['trace'][0]['branch'], matched)
            statuses.add(relation['status'])
        self.assertEqual(statuses, {'MATCH', 'INTENTIONAL_MISMATCH'})
        self.assertGreaterEqual(self.independent_counts(program, suite)[rid], 20)
        self.assert_files_are_input_projections(program, suite)
        self.assertFalse(verify_program(program, emit_program(program), suite)['differences'])

    def test_missing_linked_key_is_rejected_and_never_counts_as_logic_witness(self):
        program = self.program(LINKED)
        suite = plan_cases(program, min_records_per_logic=10)
        for key in ('INPUT-ID', 'MASTER-ID'):
            missing = [case for case in suite['cases']
                       if isinstance(case['record'], dict) and key not in case['record']]
            self.assertTrue(missing, key)
            for case in missing:
                self.assertTrue(case['intentional_invalid'])
                self.assertEqual(case['expected']['input_status'], 'REJECT_INPUT')
                self.assertFalse(case.get('logic_inputs'))
                self.assertFalse(case.get('logic_input_hashes'))
        self.assertEqual(suite['coverage']['record_counts'], self.independent_counts(program, suite))
        self.assert_files_are_input_projections(program, suite)

    def test_boundary_and_input_guard_mutations_use_the_opt_in_frozen_suite(self):
        program = self.program()
        suite = plan_cases(program, min_records_per_logic=10)
        code = emit_program(program)
        changed = verify_program(program, code.replace('>= 18', '> 18'), suite)
        self.assertEqual(changed['status'], 'MISMATCH')
        self.assertTrue(changed['differences'])
        self.assertTrue(any(case['record'].get('AGE') == 18 for case in self.accepted(suite)))
        review = adversarial_review(program, code, suite)
        self.assertTrue(review['passed'], review['gaps'])
        guards = [mutation for mutation in review['mutations'] if mutation['kind'] == 'input_contract']
        self.assertTrue(guards)
        self.assertTrue(all(mutation['detected'] and mutation['witnesses'] for mutation in guards))

    def test_tampered_density_and_linked_metadata_fail_frozen_regeneration(self):
        program = self.program(LINKED)
        suite = plan_cases(program, min_records_per_logic=10)
        rid = program['rules'][0]['id']
        accepted_index = next(index for index, case in enumerate(suite['cases'])
                              if case['expected']['input_status'] == 'ACCEPT_INPUT')
        def count(s):
            s['coverage']['record_counts'][rid] += 1
        def minimum(s):
            s['coverage']['min_records_per_logic'] = 20
        def density_hash(s):
            s['coverage']['record_hashes'][rid][0] = '0' * 64
        def logic(s):
            s['cases'][accepted_index]['logic_inputs'][rid]['INPUT-ID'] = 99
        def correlation(s):
            s['cases'][accepted_index]['correlations'][0]['status'] = 'FORGED_MATCH'
        def projection(s):
            s['cases'][accepted_index]['files']['MASTER-RECORD'][0]['MASTER-ID'] = 99
        def oracle(s):
            s['cases'][accepted_index]['expected']['return_code'] = 99
        def missing_case(s):
            s['cases'].pop()
        for mutate in (count, minimum, density_hash, logic, correlation, projection, oracle, missing_case):
            changed = copy.deepcopy(suite)
            mutate(changed)
            for validator in (verify_program, adversarial_review):
                with self.subTest(mutation=mutate.__name__, validator=validator.__name__):
                    with self.assertRaises(ValidationError):
                        validator(program, emit_program(program), changed)



    def test_counterintuitive_legacy_threshold_and_override_are_not_repaired(self):
        """Fictional faulty policy stays source-equivalent, including override order."""
        text = (COBOL.replace('PROGRAM-ID. ELIGIBLE.', 'PROGRAM-ID. COUNTER.')
                .replace('IF AGE >= 18', 'IF AGE < 18')
                .replace('IF ACTIVE = "N"\n    MOVE "N" TO DECISION',
                         'IF ACTIVE = "N"\n    MOVE "Y" TO DECISION'))
        program = self.program(text)
        frozen_source = encode(program)
        seed = secrets.randbits(63)
        rng = random.Random(seed)
        ages = [0, 17, 18, 19, 999]
        ages += rng.sample([age for age in range(1000) if age not in ages], 35)
        flags = ['N'] + rng.sample([flag for flag in string.ascii_uppercase + string.digits
                                   if flag != 'N'], 35)
        flags += rng.sample(flags, 4)
        records = [{'AGE': age, 'ACTIVE': flags[index], 'DECISION': ' '}
                   for index, age in enumerate(ages)]
        # Force the threshold equality and later override witnesses.
        records[2]['ACTIVE'] = 'Y'
        records[3]['ACTIVE'] = 'N'
        expected = []
        for record in records:
            age_branch = record['AGE'] < 18
            inactive_branch = record['ACTIVE'] == 'N'
            expected.append({'input_status': 'ACCEPT_INPUT',
                'record': {**record, 'DECISION': 'Y' if age_branch or inactive_branch else 'N'},
                'trace': [{'rule_id': program['rules'][index]['id'], 'branch': branch,
                           'source_refs': list(program['rules'][index]['source_refs'])}
                          for index, branch in enumerate((age_branch, inactive_branch))],
                'return_code': 0})
        frozen_expectations = encode(expected)
        self.assertEqual(len({record['AGE'] for record in records}), 40)
        self.assertGreaterEqual(len({record['ACTIVE'] for record in records}), 20)
        code = emit_program(program)
        execute = prepare_generated(code)
        for record, legacy_result in zip(records, expected):
            with self.subTest(seed=seed, record=record):
                original = encode(record)
                self.assertEqual(execute(record), legacy_result)
                self.assertEqual(encode(record), original)
        suite = plan_cases(program, seed=seed, min_records_per_logic=20)
        self.assertTrue(all(count >= 20 for count in self.independent_counts(program, suite).values()))
        self.assert_files_are_input_projections(program, suite)
        result = verify_program(program, code, suite)
        self.assertFalse(result['differences'])
        self.assertFalse(result['observed_legacy_parity'])
        # Plausible policy "repairs" must mismatch the unmodified source oracle.
        repairs = [code.replace("row['AGE'] < 18", "row['AGE'] >= 18"),
                   code.replace("row['ACTIVE'] == 'N'", "row['ACTIVE'] == 'Y'")]
        for repair in repairs:
            self.assertNotEqual(code, repair)
            repaired_execute = prepare_generated(repair)
            self.assertTrue(any(repaired_execute(record) != legacy_result
                                for record, legacy_result in zip(records, expected)))
            self.assertEqual(verify_program(program, repair, suite)['status'], 'MISMATCH')
        self.assertTrue(adversarial_review(program, code, suite)['passed'])
        self.assertEqual(encode(program), frozen_source)
        self.assertEqual(encode(expected), frozen_expectations)

    def test_counterintuitive_linked_customer_or_employee_logic_stays_exact(self):
        """Do not silently replace a source OR or wrong-customer comparison."""
        text = '''IDENTIFICATION DIVISION.
PROGRAM-ID. BADMATCH.
DATA DIVISION.
LINKAGE SECTION.
COPY MATCHREC.
PROCEDURE DIVISION USING SALE-RECORD REFERRAL-RECORD.
  IF SALE-ID <> REF-ID OR EMP-NO = REF-EMP-NO
    MOVE "Y" TO RESULT
  ELSE
    MOVE "N" TO RESULT
  END-IF.
  GOBACK.
'''
        copybook = '''01 SALE-RECORD.
  05 SALE-ID PIC X(4).
  05 EMP-NO PIC X(4).
  05 RESULT PIC X.
01 REFERRAL-RECORD.
  05 REF-ID PIC X(4).
  05 REF-EMP-NO PIC X(4).
'''
        program = analyze_program('BADMATCH.cbl', text, {'MATCHREC.cpy': copybook})
        self.assertFalse(program['blockers'], program['blockers'])
        program['target_contract_version'] = 2
        dependency, = program['dependencies']
        self.assertEqual(dependency['path'], 'MATCHREC.cpy')
        self.assertEqual(dependency['source_hash'], sha(copybook))
        self.assertTrue(all(field['source_ref'].startswith('MATCHREC.cpy:')
                            for field in program['fields'].values()))
        frozen_source = encode(program)
        seed = secrets.randbits(63)
        rng = random.Random(seed)
        ids = [0, 1, 999, 1000, 9999] + rng.sample(range(1001, 9999), 35)
        records = []
        for index, key in enumerate(ids):
            employee = rng.randrange(10000)
            same_customer = index % 4 < 2
            same_employee = index % 2 == 0
            records.append({'SALE-ID': f'{key:04d}',
                'REF-ID': f'{key if same_customer else (key + 1) % 10000:04d}',
                'EMP-NO': f'{employee:04d}',
                'REF-EMP-NO': f'{employee if same_employee else (employee + 1) % 10000:04d}',
                'RESULT': ' '})
        # Freeze literal source expectations before executing target code.
        expected = []
        for record in records:
            branch = record['SALE-ID'] != record['REF-ID'] or record['EMP-NO'] == record['REF-EMP-NO']
            expected.append({'input_status': 'ACCEPT_INPUT',
                'record': {**record, 'RESULT': 'Y' if branch else 'N'},
                'trace': [{'rule_id': program['rules'][0]['id'], 'branch': branch,
                           'source_refs': list(program['rules'][0]['source_refs'])}],
                'return_code': 0})
        expected_hash = sha(encode(expected))
        self.assertEqual(len({sha(encode(record)) for record in records}), 40)
        self.assertEqual({(row['SALE-ID'] == row['REF-ID'], row['EMP-NO'] == row['REF-EMP-NO'])
                          for row in records}, {(True, True), (True, False), (False, True), (False, False)})
        self.assertTrue(any(row['SALE-ID'].startswith('0') for row in records))
        code = emit_program(program)
        execute = prepare_generated(code)
        for record, legacy_result in zip(records, expected):
            with self.subTest(seed=seed, record=record):
                original = encode(record)
                self.assertEqual(execute(record), legacy_result)
                self.assertEqual(encode(record), original)
        suite = plan_cases(program, seed=seed, min_records_per_logic=20)
        self.assertGreaterEqual(self.independent_counts(program, suite)[program['rules'][0]['id']], 20)
        self.assert_files_are_input_projections(program, suite)
        # Compound OR metadata is not a universal join; exact linked file
        # values above and the suite's input projections are the witnesses.
        self.assertFalse(program['relationships'])
        result = verify_program(program, code, suite)
        self.assertFalse(result['differences'])
        self.assertFalse(result['observed_legacy_parity'])
        original_predicate = "((row['SALE-ID'] != row['REF-ID']) or (row['EMP-NO'] == row['REF-EMP-NO']))"
        for repair in [code.replace("row['SALE-ID'] != row['REF-ID']", "row['SALE-ID'] == row['REF-ID']"),
                       code.replace(original_predicate, original_predicate.replace(' or ', ' and '))]:
            self.assertNotEqual(code, repair)
            repaired_execute = prepare_generated(repair)
            self.assertTrue(any(repaired_execute(record) != legacy_result
                                for record, legacy_result in zip(records, expected)))
            self.assertEqual(verify_program(program, repair, suite)['status'], 'MISMATCH')
        self.assertTrue(adversarial_review(program, code, suite)['passed'])
        self.assertEqual(encode(program), frozen_source)
        self.assertEqual(sha(encode(expected)), expected_hash)

    def test_canonical_round_trip_and_same_seed_keep_opt_in_suite_deterministic(self):
        program = self.program(LINKED)
        suite = plan_cases(program, seed=37, min_records_per_logic=20)
        persisted = json.loads(encode(program))
        repeated = plan_cases(program, seed=37, min_records_per_logic=20)
        replayed = plan_cases(persisted, seed=37, min_records_per_logic=20)
        self.assertEqual(encode(suite), encode(repeated))
        self.assertEqual(encode(suite), encode(replayed))
        self.assertNotEqual(encode(suite), encode(plan_cases(
            program, seed=38, min_records_per_logic=20)))


if __name__ == '__main__':
    unittest.main()
