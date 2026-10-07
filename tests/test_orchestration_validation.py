import tempfile
import unittest
from pathlib import Path

from test_source import COBOL
from workbench.source import analyze_program
from workbench.target import emit_program, emit_jobs
from workbench.domain import sha, encode
from workbench.orchestration import verify_jobs


class JobValidationTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
        self.program=analyze_program('ELIGIBLE.cbl',COBOL,{})
        self.doc={'jobs':[{'name':'JOBA','steps':[{'name':'S1','program':'ELIGIBLE','condition':'Always'},{'name':'S2','program':'ELIGIBLE','condition':'RC=0'}]}],
                  'analysis':{'programs':{'ELIGIBLE':self.program}},'program_versions':{},
                  'authorization':{'seed':781,'max_cases_per_program':256},'fixture_contract_version':4}
        self.pin(emit_program(self.program))

    def pin(self,code):
        version=sha(code);path=self.root/'shared/target/python'/(version+'.py');path.parent.mkdir(parents=True,exist_ok=True);path.write_text(code)
        self.doc['program_versions']['ELIGIBLE']=version

    def verify(self):return verify_jobs(self.doc,self.root,emit_jobs(self.doc,self.doc['program_versions']))

    def test_randomized_twenty_steps_replay_with_full_results(self):
        result=self.verify()
        self.assertGreaterEqual(result['integration_cases'],20)
        self.assertTrue(result['matched']);self.assertTrue(result['validation']['complete'])
        self.assertTrue(all(s['executed_records']>=20 for s in result['validation']['steps']))
        self.assertGreaterEqual(result['randomized_cases'],20)
        self.assertEqual(encode(result),encode(self.verify()))
        self.doc['authorization']['seed']+=1
        self.assertNotEqual(result['cases'],self.verify()['cases'])

    def test_never_executed_step_has_explicit_gap(self):
        self.doc['jobs'][0]['steps'][1]['condition']='RC>0'
        result=self.verify()
        self.assertFalse(result['matched']);self.assertEqual(result['validation']['steps'][1]['executed_records'],0)
        self.assertTrue(result['validation']['gaps'])

    def test_changed_target_outputs_fail(self):
        self.pin(emit_program(self.program).replace('>= 18','> 18'))
        result=self.verify();self.assertFalse(result['matched'])
        self.assertTrue(any(not case['matched'] for case in result['cases']))
        self.assertFalse(result['validation']['complete'])

    def test_budget_never_claims_twenty(self):
        self.doc['authorization']['max_cases_per_program']=5
        result=self.verify();self.assertFalse(result['matched'])
        self.assertLessEqual(result['integration_cases'],5)
        self.assertTrue(result['validation']['gaps'])

    def test_legacy_receipt_shape_is_preserved(self):
        self.doc.pop('fixture_contract_version')
        result=self.verify();self.assertEqual(result['integration_cases'],1)
        self.assertNotIn('cases',result);self.assertNotIn('validation',result)

    def test_omitted_rule_gets_no_generated_trace_credit(self):
        omitted=self.program['rules'].pop()['id'];self.pin(emit_program(self.program))
        result=self.verify()
        self.assertTrue(result['matched'])
        self.assertNotIn(omitted,encode(result).decode())

    def test_small_domain_and_overwritten_state_do_not_pad_step_counts(self):
        source='''IDENTIFICATION DIVISION.
PROGRAM-ID. ELIGIBLE.
DATA DIVISION.
LINKAGE SECTION.
01 INPUT-RECORD.
05 FLAG PIC 9.
PROCEDURE DIVISION USING INPUT-RECORD.
IF FLAG >= 5
MOVE 1 TO FLAG
ELSE
MOVE 0 TO FLAG
END-IF.
GOBACK.
'''
        self.program=analyze_program('ELIGIBLE.cbl',source,{})
        self.assertFalse(self.program['blockers'])
        self.doc['analysis']['programs']['ELIGIBLE']=self.program
        self.pin(emit_program(self.program))
        result=self.verify();self.assertFalse(result['matched'])
        self.assertLessEqual(result['validation']['steps'][0]['executed_records'],10)
        self.assertLessEqual(result['validation']['steps'][1]['executed_records'],2)
        self.assertEqual(len(result['validation']['gaps']),2)

    def test_successive_jobs_preserve_record_and_reset_return_code(self):
        self.doc['jobs'].append({'name':'JOBB','steps':[{'name':'S1','program':'ELIGIBLE','condition':'RC=0'}]})
        result=self.verify();self.assertTrue(result['matched'])
        self.assertEqual(len(result['validation']['steps']),3)
        self.assertTrue(all(c['expected']==c['actual'] for c in result['cases']))
        self.assertTrue(all(c['expected']['JOBB'][0]['record']==c['actual']['JOBA'][-1]['record'] for c in result['cases']))

    def test_interactions_cannot_starve_random_quota(self):
        source='IDENTIFICATION DIVISION.\nPROGRAM-ID. ELIGIBLE.\nDATA DIVISION.\nLINKAGE SECTION.\n01 INPUT-RECORD.\n'
        source+=''.join('05 '+name+' PIC 9(3).\n' for name in 'ABCD')
        source+='PROCEDURE DIVISION USING INPUT-RECORD.\n'
        source+=''.join('IF '+name+' >= 50\nCONTINUE\nELSE\nCONTINUE\nEND-IF.\n' for name in 'ABCD')+'GOBACK.\n'
        self.program=analyze_program('ELIGIBLE.cbl',source,{})
        self.doc['analysis']['programs']['ELIGIBLE']=self.program
        self.doc['jobs'][0]['steps']=self.doc['jobs'][0]['steps'][:1]
        self.doc['authorization']['seed']=123
        self.pin(emit_program(self.program))
        result=self.verify();self.assertTrue(result['matched'],result['validation']['gaps'])
        self.assertGreaterEqual(result['randomized_cases'],20)

    def test_seed_bounds_and_prepared_target_checkpoint(self):
        from workbench.domain import ValidationError
        for seed in (-1,2**63,True):
            self.doc['authorization']['seed']=seed
            with self.assertRaises(ValidationError):self.verify()
        self.doc['authorization']['seed']=123
        from unittest.mock import patch
        from workbench.target import prepare_generated
        calls=[]
        def checkpoint():calls.append('checkpoint')
        def prepare(code):
            execute=prepare_generated(code)
            def invoke(record):
                self.assertEqual(calls[-1],'checkpoint');calls.append('execute');return execute(record)
            return invoke
        with patch('workbench.target.prepare_generated',side_effect=prepare):
            verify_jobs(self.doc,self.root,emit_jobs(self.doc,self.doc['program_versions']),checkpoint)
        self.assertIn('execute',calls)

    def test_random_quota_cannot_silently_drop_required_boundaries(self):
        self.doc['authorization']['max_cases_per_program']=20
        result=self.verify()
        self.assertEqual(result['randomized_cases'],20)
        self.assertTrue(any(gap.get('status')=='budget_exhausted' and 'boundary' in gap.get('explanation','') for gap in result['validation']['gaps']))
        self.assertFalse(result['matched'])
