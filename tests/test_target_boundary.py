"""Exported target programs own the input contract that fixture tests claim."""
import unittest
import json
from unittest.mock import patch, Mock

from workbench.domain import encode, sha, ValidationError
from workbench.fixtures import plan_cases, verify_program, adversarial_review
from workbench.reference import run_reference
from workbench.source import analyze_program
from workbench.target import emit_program, run_generated, emit_jobs, prepare_generated, check_generated
from test_source import COBOL


class TargetBoundaryTests(unittest.TestCase):
    def program(self, version=2):
        program = analyze_program('ELIGIBLE.cbl', COBOL, {})
        if version == 2:
            program['target_contract_version'] = 2
        return program

    def test_exported_function_rejects_invalid_records_without_wrapper(self):
        program = self.program()
        namespace = {}
        exec(emit_program(program), namespace)
        base = {'AGE': 18, 'ACTIVE': 'Y', 'DECISION': ' '}
        invalid = [None, [], list(base.items()), {}, {**base, 'EXTRA': 1},
                   {k: v for k, v in base.items() if k != 'AGE'}]
        invalid += [{**base, 'AGE': value} for value in (True, False, -1, 1000, 18.0, '18', None)]
        invalid += [{**base, 'ACTIVE': value} for value in ('', 'YY', None, 1, b'Y')]
        for record in invalid:
            with self.subTest(record=record):
                self.assertEqual(namespace['run_program'](record), run_reference(program, record))
                self.assertEqual(namespace['run_program'](record)['input_status'], 'REJECT_INPUT')
        self.assertEqual(namespace['run_program'](base), run_reference(program, base))
        self.assertEqual(base['DECISION'], ' ')

    def test_generated_runner_and_exported_function_apply_same_contract(self):
        program = self.program()
        class DictSubclass(dict):
            pass
        record = DictSubclass(AGE=18, ACTIVE='Y', DECISION=' ')
        self.assertEqual(run_generated(emit_program(program), record), run_reference(program, record))
        self.assertEqual(run_generated(emit_program(program), record)['input_status'], 'REJECT_INPUT')

    def test_invalid_fixtures_really_execute_generated_target(self):
        program = self.program()
        suite = plan_cases(program)
        code = emit_program(program)
        execute = Mock(wraps=prepare_generated(code))
        with patch('workbench.fixtures.prepare_generated', return_value=execute) as prepare:
            result = verify_program(program, code, suite)
        self.assertFalse(result['differences'])
        self.assertEqual(prepare.call_count, 1)
        self.assertEqual(execute.call_count, len(suite['cases']))
        self.assertTrue(any(c['record'] is None for c in suite['cases']))
        self.assertTrue(any(isinstance(c['record'], dict) and c['record'].get('AGE') is True for c in suite['cases']))
        self.assertTrue(any(isinstance(c['record'], dict) and 'AGE' not in c['record'] for c in suite['cases']))

    def test_code_is_validated_once_per_suite_with_each_checkpoint_retained(self):
        program = self.program()
        suite = plan_cases(program)
        checkpoint = Mock()
        with patch('workbench.target.check_generated', wraps=check_generated) as validate:
            result = verify_program(program, emit_program(program), suite, checkpoint=checkpoint)
        self.assertFalse(result['differences'])
        self.assertEqual(validate.call_count, 1)
        self.assertEqual(checkpoint.call_count, len(suite['cases']))

    def test_every_mutation_gets_its_own_validated_entry_point(self):
        program = self.program()
        code = emit_program(program)
        suite = plan_cases(program)
        with patch('workbench.target.check_generated', wraps=check_generated) as validate:
            result = adversarial_review(program, code, suite)
        self.assertTrue(result['passed'])
        # One check for each mutant plus the explicit forbidden-import probe.
        self.assertEqual(validate.call_count, len(result['mutations'])+1)

    def test_input_guard_mutations_have_rejecting_witnesses(self):
        program = self.program()
        report = adversarial_review(program, emit_program(program), plan_cases(program))
        guards = [m for m in report['mutations'] if m['kind'] == 'input_contract']
        self.assertTrue(guards)
        self.assertTrue(all(m['detected'] for m in guards), guards)
        self.assertTrue(report['passed'], report)

    def test_guard_does_not_gain_import_or_attribute_capability(self):
        code = emit_program(self.program())
        for changed in (code.replace("record.get('AGE')", "record.clear()"),
                        code.replace("len(record)", "eval(record)")):
            with self.assertRaises(ValidationError):
                run_generated(changed, {'AGE': 18, 'ACTIVE': 'Y', 'DECISION': ' '})

    def test_historical_emission_and_frozen_evidence_remain_identical(self):
        program = self.program(version=1)
        code = emit_program(program)
        suite = plan_cases(program)
        self.assertEqual(sha(code), 'bb5382bcd3d2c50ef1312119024db30ad294798e0e0fcb585608104ed47a4885')
        self.assertEqual(sha(encode(suite)), 'e0679cba54a12eaae407f0d0f06acd3c35d84604e0e7868237fab07c5a6b1076')
        self.assertEqual(sha(encode(adversarial_review(program, code, suite))), '83386b1d219bff284916ebe957c88ecf40633bc62f695530fd8bd414cde2680a')

    def test_canonical_ledger_round_trip_cannot_change_target_or_cases(self):
        program = self.program()
        persisted = json.loads(encode(program))
        self.assertEqual(emit_program(program), emit_program(persisted))
        self.assertEqual(encode(plan_cases(program)), encode(plan_cases(persisted)))

    def test_exported_jobs_stop_at_rejected_input_without_advancing(self):
        program = self.program()
        manifest = {'analysis': {'programs': {'ELIGIBLE': program}}, 'jobs': [
            {'name': 'JOBA', 'steps': [
                {'name': 'S1', 'program': 'ELIGIBLE', 'condition': 'ALWAYS'},
                {'name': 'S2', 'program': 'ELIGIBLE', 'condition': 'RC=0'}]},
            {'name': 'JOBB', 'steps': [
                {'name': 'S1', 'program': 'ELIGIBLE', 'condition': 'ALWAYS'}]}]}
        namespace = {}
        exec(emit_jobs(manifest, {'ELIGIBLE': 'pinned-version'}), namespace)
        inputs = []
        def execute(record):
            inputs.append(record)
            return run_generated(emit_program(program), record)
        record = {'AGE': True, 'ACTIVE': 'Y', 'DECISION': ' '}
        context = {'record': record.copy()}
        result = namespace['run_process'](context, {'ELIGIBLE': execute})
        self.assertEqual(list(result), ['JOBA'])
        self.assertEqual(len(result['JOBA']), 1)
        self.assertEqual(result['JOBA'][0]['input_status'], 'REJECT_INPUT')
        self.assertEqual(len(inputs), 1)
        self.assertEqual(context['record'], record)


if __name__ == '__main__':
    unittest.main()
