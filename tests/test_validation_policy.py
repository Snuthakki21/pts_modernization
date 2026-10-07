"""Runtime-seeded fixture policy: distinct executed states, replay and honest gaps."""
import copy
import json
import unittest
from unittest.mock import patch

from workbench.domain import ValidationError, encode, sha
from workbench.fixtures import adversarial_review, plan_cases, verify_program
from workbench.reference import run_reference
from workbench.source import analyze_program
from workbench.target import emit_program
from test_source import COBOL
from test_fixture_v3 import LINKED, executed_logic_inputs


class ValidationPolicyTests(unittest.TestCase):
    def program(self, source=COBOL):
        result=analyze_program('ELIGIBLE.cbl',source,{})
        self.assertFalse(result['blockers'],result['blockers'])
        result['target_contract_version']=2
        return result

    def suite(self, program, seed=917345, budget=4096):
        return plan_cases(program,seed,budget,min_records_per_logic=20,
                          fixture_contract_version=4)

    def independently_count_random(self, program, suite):
        states={rule['id']:set() for rule in program['rules']}
        for case in suite['cases']:
            if not case.get('randomized') or case['intentional_invalid']:continue
            for rid,values in executed_logic_inputs(program,case['record']).items():
                states[rid].add(sha(encode(values)))
        return {rid:len(values) for rid,values in states.items()}

    def test_frozen_v3_bytes_remain_unchanged(self):
        suite=plan_cases(self.program(),37,256,min_records_per_logic=20)
        self.assertEqual(sha(encode(suite)),
                         '7c7047bfd52d26c786dadcf8302365a3ad78ec10a9c1e5eca96f91e19b0aedfd')
        self.assertEqual(suite['version'],3)
        self.assertFalse(verify_program(self.program(),emit_program(self.program()),suite)['differences'])

    def test_twenty_randomized_distinct_executed_states_per_rule(self):
        program=self.program();suite=self.suite(program)
        self.assertEqual(suite['version'],4)
        self.assertEqual(suite['generator_version'],'source-subset-4')
        counts=self.independently_count_random(program,suite)
        self.assertTrue(all(value>=20 for value in counts.values()),counts)
        self.assertEqual(suite['coverage']['randomized_record_counts'],counts)
        self.assertTrue(suite['coverage']['complete'])
        self.assertTrue(suite['coverage']['logic_validation']['complete'])
        self.assertFalse(verify_program(program,emit_program(program),suite)['differences'])
        self.assertTrue(adversarial_review(program,emit_program(program),suite)['passed'])

    def test_replay_seed_preserves_all_bytes_after_canonical_json(self):
        program=self.program();suite=self.suite(program)
        self.assertEqual(encode(suite),encode(self.suite(json.loads(encode(program)))))
        self.assertEqual(encode(suite),encode(self.suite(program)))
        other=self.suite(program,seed=917346)
        random_records=lambda value:[case['record'] for case in value['cases'] if case.get('randomized')]
        self.assertNotEqual(random_records(suite),random_records(other))
        self.assertNotEqual(suite['contract_hash'],other['contract_hash'])
        self.assertEqual(suite['seed'],917345)

    def test_string_only_program_has_seed_sensitive_full_width_values(self):
        source=COBOL.replace('IF AGE >= 18','IF ACTIVE = "Y"').replace('ACTIVE PIC X.','ACTIVE PIC X(4).')
        program=self.program(source)
        first=self.suite(program,seed=100);second=self.suite(program,seed=101)
        strings=lambda suite:{case['record']['ACTIVE'] for case in suite['cases']
                              if case.get('randomized') and not case['intentional_invalid']}
        self.assertNotEqual(strings(first),strings(second))
        self.assertTrue(any(value.strip() and len(value.strip())>1 for value in strings(first)))
        self.assertTrue(all(len(value)==4 for value in strings(first)))
        self.assertTrue(all(value>=20 for value in self.independently_count_random(program,first).values()))

    def test_limited_domain_never_uses_unused_fields_to_pad_twenty(self):
        program=self.program(COBOL.replace('AGE PIC 9(3)','AGE PIC 9').replace('AGE >= 18','AGE >= 5'))
        suite=self.suite(program);rid=program['rules'][0]['id']
        self.assertEqual(suite['coverage']['record_counts'][rid],10)
        self.assertEqual(suite['coverage']['randomized_record_counts'][rid],10)
        gap=next(row for row in suite['coverage']['record_count_gaps'] if row['rule_id']==rid)
        self.assertEqual(gap['status'],'limited_input_domain')
        self.assertEqual(gap['proven_input_domain_size'],10)
        self.assertFalse(suite['coverage']['complete'])
        self.assertEqual(verify_program(program,emit_program(program),suite)['status'],'MATCHED_WITH_COVERAGE_GAPS')

    def test_prior_assignments_reduce_actual_randomized_downstream_states(self):
        program=self.program(COBOL.replace('IF ACTIVE = "N"','IF DECISION = "Y"'))
        suite=self.suite(program);rid=program['rules'][1]['id']
        self.assertEqual(suite['coverage']['randomized_record_counts'][rid],2)
        self.assertEqual(self.independently_count_random(program,suite)[rid],2)
        self.assertTrue(any(row['rule_id']==rid for row in suite['coverage']['record_count_gaps']))
        self.assertFalse(suite['coverage']['complete'])

    def test_small_budget_exposes_random_and_boundary_obligations(self):
        suite=self.suite(self.program(),budget=2)
        self.assertEqual(len(suite['cases']),2)
        self.assertTrue(suite['coverage']['record_count_gaps'])
        self.assertTrue(suite['coverage']['obligation_gaps'])
        self.assertFalse(suite['coverage']['complete'])

    def test_linked_random_records_preserve_source_group_projections_and_both_outcomes(self):
        program=self.program(LINKED);suite=self.suite(program)
        rows=[case for case in suite['cases'] if case.get('randomized') and not case['intentional_invalid']]
        statuses={relation['status'] for case in rows for relation in case['correlations']}
        self.assertEqual(statuses,{'MATCH','INTENTIONAL_MISMATCH'})
        for case in rows:
            self.assertEqual(case['files']['INPUT-RECORD'][0]['INPUT-ID'],case['record']['INPUT-ID'])
            self.assertEqual(case['files']['MASTER-RECORD'][0]['MASTER-ID'],case['record']['MASTER-ID'])
            self.assertEqual(case['expected'],run_reference(program,case['record']))
        self.assertFalse(suite['coverage']['correlation_gaps'])
        self.assertFalse(verify_program(program,emit_program(program),suite)['differences'])

    def test_technical_layout_and_terminal_have_twenty_random_cases_without_rules(self):
        source=COBOL[:COBOL.index('  IF AGE')]+"  GOBACK.\n"
        program=self.program(source);suite=self.suite(program)
        self.assertFalse(program['rules'])
        for name in ('input_layout','terminal'):
            evidence=suite['coverage']['logic_validation']['technical'][name]
            self.assertGreaterEqual(evidence['randomized_valid_records'],20)
            self.assertTrue(evidence['complete'])
        self.assertFalse(verify_program(program,emit_program(program),suite)['differences'])

    def test_no_input_domain_stays_a_technical_gap_even_without_rules(self):
        program=self.program();program['fields']={};program['rules']=[];program['relationships']=[]
        suite=self.suite(program)
        self.assertEqual(suite['coverage']['logic_validation']['technical']['terminal']['distinct_valid_records'],1)
        self.assertTrue(suite['coverage']['technical_record_count_gaps'])
        self.assertFalse(suite['coverage']['complete'])
        self.assertFalse(suite['coverage']['logic_validation']['complete'])

    def test_two_small_field_domains_exercise_joint_randomized_states(self):
        source=COBOL.replace('AGE PIC 9(3)','AGE PIC 9').replace('ACTIVE PIC X.','ACTIVE PIC 9.')
        source=source.replace('AGE >= 18','AGE >= 5 OR ACTIVE >= 5').replace('ACTIVE = "N"','ACTIVE >= 4')
        program=self.program(source);suite=self.suite(program)
        rid=program['rules'][0]['id']
        self.assertGreaterEqual(suite['coverage']['randomized_record_counts'][rid],20)
        second=program['rules'][1]['id']
        self.assertEqual(suite['coverage']['randomized_record_counts'][second],10)
        self.assertFalse(suite['coverage']['complete'])

    def test_expected_source_oracle_is_constructed_without_target_execution(self):
        with patch('workbench.fixtures.prepare_generated',side_effect=AssertionError('target ran before freeze')):
            suite=self.suite(self.program())
        self.assertTrue(suite['cases'])
        self.assertTrue(any(case['intentional_invalid'] for case in suite['cases']))
        self.assertTrue(all(not case['logic_input_hashes'] for case in suite['cases'] if case['intentional_invalid']))

    def test_tampered_random_metadata_or_version_cannot_get_verification_credit(self):
        program=self.program();suite=self.suite(program)
        for field,value in (('version',3),('seed',20)):
            changed=copy.deepcopy(suite);changed[field]=value
            with self.assertRaises(ValidationError):verify_program(program,emit_program(program),changed)
        changed=copy.deepcopy(suite);rid=program['rules'][0]['id']
        changed['coverage']['randomized_record_counts'][rid]+=1
        with self.assertRaises(ValidationError):adversarial_review(program,emit_program(program),changed)

    def test_source_mutation_witness_selection_avoids_optional_cartesian_padding(self):
        from pathlib import Path
        from workbench.fixtures import comparisons
        export=Path(__file__).resolve().parents[1]/'examples/Endeavor'
        program=analyze_program('ELIGIBLE.cbl',(export/'ELIGIBLE.cbl').read_text(),
                                {'LAYOUT.cpy':(export/'LAYOUT.cpy').read_text()})
        self.assertFalse(program['blockers'])
        program['target_contract_version']=2
        suite=self.suite(program)
        mutation_bound=sum(len(comparisons(rule['predicate']))+len(rule['then'])+len(rule['else'])
                           for rule in program['rules'])
        useful_bound=suite['coverage']['mandatory_candidates']+20*(len(program['rules'])+1)+mutation_bound
        self.assertLessEqual(len(suite['cases']),useful_bound,
                             'Optional Cartesian padding expands every target, unit and adversarial execution')
        self.assertFalse(suite['coverage']['obligation_gaps'])
        self.assertTrue(all(count>=20 for count in suite['coverage']['randomized_record_counts'].values()))
        self.assertTrue(suite['coverage']['complete'])
        review=adversarial_review(program,emit_program(program),suite)
        self.assertTrue(review['passed'],review['gaps'])
        self.assertTrue(all(item['detected'] for item in review['mutations']))

    def test_compound_boundary_mutations_keep_differentiating_interactions(self):
        program=self.program(COBOL.replace('IF AGE >= 18','IF AGE >= 18 AND ACTIVE = "Y"'))
        suite=self.suite(program)
        self.assertTrue(any(case['record'].get('AGE')==18 and case['record'].get('ACTIVE')=='Y'
                            for case in suite['cases'] if not case['intentional_invalid']))
        self.assertTrue(adversarial_review(program,emit_program(program),suite)['passed'])

    def test_v4_rejects_weakened_or_unknown_policy_and_invalid_seed(self):
        program=self.program()
        for minimum in (0,10,None):
            with self.assertRaises(ValidationError):
                plan_cases(program,min_records_per_logic=minimum,fixture_contract_version=4)
        for version in (0,2,True,5,'4'):
            with self.assertRaises(ValidationError):
                plan_cases(program,min_records_per_logic=20,fixture_contract_version=version)
        for seed in (-1,True,None,1.5,'21',2**63):
            with self.assertRaises(ValidationError):self.suite(program,seed=seed)


if __name__=='__main__':unittest.main()
