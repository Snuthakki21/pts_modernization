import tempfile
import unittest
from pathlib import Path
from workbench.source import analyze_program, analyze_sources
from workbench.target import emit_program, run_generated
from workbench.reference import run_reference
from workbench.fixtures import plan_cases, verify_program
from workbench.intake import parse_manifest
from workbench.domain import ValidationError

COBOL = '''IDENTIFICATION DIVISION.
PROGRAM-ID. ELIGIBLE.
DATA DIVISION.
LINKAGE SECTION.
01 INPUT-RECORD.
  05 AGE PIC 9(3).
  05 ACTIVE PIC X.
  05 DECISION PIC X.
PROCEDURE DIVISION USING INPUT-RECORD.
  IF AGE >= 18
    MOVE "Y" TO DECISION
  ELSE
    MOVE "N" TO DECISION
  END-IF.
  IF ACTIVE = "N"
    MOVE "N" TO DECISION
  ELSE
    CONTINUE
  END-IF.
  GOBACK.
'''


class SourceTests(unittest.TestCase):
    def test_free_format_long_condition_is_not_truncated(self):
        text=COBOL.replace('  IF AGE >= 18','       IF AGE >= 18'+' '*60+'AND ACTIVE = "Y"')
        p=analyze_program('ELIGIBLE.cbl',text,{})
        self.assertFalse(p['blockers'])
        self.assertEqual(p['rules'][0]['predicate']['op'],'AND')
        self.assertEqual(run_reference(p,{'AGE':20,'ACTIVE':'Z','DECISION':' '})['record']['DECISION'],'N')

    def test_unsupported_jcl_options_and_manifest_disagreement_block(self):
        from test_workflow import MANIFEST
        files={'ELIGIBLE.cbl':COBOL,'JOBA.jcl':'//JOBA JOB\n//S010 EXEC PGM=ELIGIBLE,COND=(0,EQ)\n//IN DD DSN=PROD.INPUT,DISP=SHR\n'}
        self.assertTrue(any(b['kind']=='unsupported_jcl' for b in analyze_sources(files,parse_manifest(MANIFEST))['blockers']))
        files['JOBA.jcl']='//JOBA JOB\n//OTHER EXEC PGM=ELIGIBLE\n'
        self.assertTrue(any(b['kind']=='scope_mismatch' for b in analyze_sources(files,parse_manifest(MANIFEST))['blockers']))
    def test_string_field_ordering_and_out_of_range_initializers_block(self):
        text=COBOL.replace('05 ACTIVE PIC X.','05 ACTIVE PIC X.\n  05 OTHER PIC X.').replace('ACTIVE = "N"','ACTIVE > OTHER')
        self.assertTrue(analyze_program('ELIGIBLE.cbl',text,{})['blockers'])
        text=COBOL.replace('05 AGE PIC 9(3).','05 AGE PIC 9(3) VALUE 1000.')
        self.assertTrue(analyze_program('ELIGIBLE.cbl',text,{})['blockers'])

    def test_generated_jobs_propagate_record_to_next_step(self):
        from workbench.target import emit_jobs
        manifest={'jobs':[{'name':'JOBA','steps':[{'name':'S1','program':'ONE','condition':'Always'},{'name':'S2','program':'TWO','condition':'RC=0'}]}]}
        namespace={};exec(emit_jobs(manifest,{'ONE':'v1','TWO':'v2'}),namespace)
        result=namespace['run_process']({'record':{'x':1}},{'ONE':lambda r:{'record':{'x':r['x']+1},'return_code':0},'TWO':lambda r:{'record':{'x':r['x']+1},'return_code':0}})
        self.assertEqual(result['JOBA'][-1]['record']['x'],3)
    def test_cobol_string_comparisons_pad_literal_and_free_indentation(self):
        text=COBOL.replace('05 ACTIVE PIC X.','05 ACTIVE PIC X(3).').replace('    MOVE','      MOVE')
        p=analyze_program('ELIGIBLE.cbl',text,{})
        self.assertFalse(p['blockers'])
        record={'AGE':20,'ACTIVE':'N  ','DECISION':' '}
        self.assertEqual(run_reference(p,record)['record']['DECISION'],'N')
        self.assertEqual(run_generated(emit_program(p),record)['record']['DECISION'],'N')

    def test_source_threshold_else_and_sequential_effect(self):
        p = analyze_program('ELIGIBLE.cbl', COBOL, {})
        self.assertFalse(p['blockers'])
        self.assertEqual(len(p['rules']), 2)
        self.assertEqual(run_reference(p, {'AGE':17, 'ACTIVE':'Y', 'DECISION':' '} )['record']['DECISION'], 'N')
        self.assertEqual(run_reference(p, {'AGE':18, 'ACTIVE':'Y', 'DECISION':' '} )['record']['DECISION'], 'Y')
        self.assertEqual(run_reference(p, {'AGE':19, 'ACTIVE':'N', 'DECISION':' '} )['record']['DECISION'], 'N')
        self.assertEqual(run_generated(emit_program(p), {'AGE':18, 'ACTIVE':'Y','DECISION':' '})['record']['DECISION'], 'Y')

    def test_unknown_statement_blocks_without_losing_source_lines(self):
        p=analyze_program('ELIGIBLE.cbl', COBOL.replace('GOBACK.', 'EXEC CICS RETURN END-EXEC.'),{})
        self.assertTrue(p['blockers'])
        self.assertEqual(len(p['coverage']),len(COBOL.splitlines()))
        self.assertTrue(any(r['disposition']=='unsupported' for r in p['coverage']))

    def test_copybook_source_hash_and_rule_evidence(self):
        p=analyze_program('ELIGIBLE.cbl',COBOL.replace('  05 AGE PIC 9(3).','COPY AGECOPY.'),{'AGECOPY.cpy':'05 AGE PIC 9(3).\n'})
        self.assertIn('AGE',p['fields'])
        self.assertEqual(p['copybooks'], ['AGECOPY'])
        self.assertTrue(p['rules'][0]['source_refs'])
        q=analyze_program('ELIGIBLE.cbl',COBOL.replace('>= 18','>= 19'),{})
        self.assertNotEqual(p['source_hash'],q['source_hash'])

    def test_boundary_witnesses_and_mutated_target_detected(self):
        p=analyze_program('ELIGIBLE.cbl',COBOL,{})
        cases=plan_cases(p,seed=11)
        ages={x['record']['AGE'] for x in cases['cases']}
        self.assertTrue({17,18,19}.issubset(ages))
        good=verify_program(p,emit_program(p),cases)
        self.assertFalse(good['differences'])
        bad=verify_program(p,emit_program(p).replace('>= 18','> 18'),cases)
        self.assertTrue(bad['differences'])
        self.assertTrue(good['coverage']['complete'])

    def test_target_cannot_import_or_call_unknown_functions(self):
        with self.assertRaises(ValidationError):run_generated('import os\ndef run_program(row):\n return os.environ\n',{})

    def test_missing_copybook_and_nested_if_are_accounted(self):
        p=analyze_program('ELIGIBLE.cbl',COBOL.replace('  05 AGE PIC 9(3).','COPY MISSING.'),{})
        self.assertTrue(p['blockers'])
        p=analyze_program('ELIGIBLE.cbl',COBOL.replace('MOVE "Y" TO DECISION','IF ACTIVE = "Y"\nMOVE "Y" TO DECISION\nEND-IF'),{})
        self.assertTrue(p['blockers'])


if __name__=='__main__': unittest.main()
