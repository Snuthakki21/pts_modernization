"""Regression witnesses from the independent source/template audit."""
import unittest
from workbench.source import analyze_program, analyze_sources
from workbench.target import emit_program, emit_jobs
from workbench.fixtures import plan_cases
from workbench.intake import parse_manifest
from workbench.domain import ValidationError
from test_source import COBOL
from test_workflow import MANIFEST

class AdversarialTests(unittest.TestCase):
    def program(self,text): return analyze_program('ELIGIBLE.cbl',text,{})
    def test_lowercase_numeric_picture(self):
        p=self.program(COBOL.lower())
        self.assertFalse(p['blockers']);self.assertEqual(p['fields']['AGE']['type'],'integer')
    def test_comment_marker_inside_literal(self):
        p=self.program(COBOL.replace('05 ACTIVE PIC X.','05 ACTIVE PIC X(2).').replace('ACTIVE = "N"','ACTIVE = "*>"'))
        self.assertFalse(p['blockers'])
    def test_sentence_period_cannot_end_if_scope_silently(self):
        self.assertTrue(self.program(COBOL.replace('MOVE "Y" TO DECISION','MOVE "Y" TO DECISION.'))['blockers'])
    def test_malformed_move_literal_is_not_swallowed(self):
        self.assertTrue(self.program(COBOL.replace('MOVE "Y" TO DECISION','MOVE "Y" "Z" TO DECISION').replace('05 DECISION PIC X.','05 DECISION PIC X(10).'))['blockers'])
    def test_multiple_program_ids_and_procedure_clauses_block(self):
        for text in [COBOL.replace('DATA DIVISION.','PROGRAM-ID. SECOND.\nDATA DIVISION.'),COBOL.replace('USING INPUT-RECORD.','USING INPUT-RECORD RETURNING AGE.')]:
            self.assertTrue(self.program(text)['blockers'])
    def test_literal_only_string_ordering_is_unknown_collation(self):
        self.assertTrue(self.program(COBOL.replace('AGE >= 18','"Z" < "a"'))['blockers'])
    def test_copybook_provenance_changes_semantic_hash(self):
        text=COBOL.replace('05 AGE PIC 9(3).','COPY AGECOPY.')
        a=analyze_program('ELIGIBLE.cbl',text,{'books/AGECOPY.cpy':'05 AGE PIC 9(3).'})
        b=analyze_program('ELIGIBLE.cbl',text,{'books/AGECOPY.cpy':'05 AGE PIC 9(2).'})
        self.assertNotEqual(a.get('semantic_hash'),b.get('semantic_hash'))
        self.assertEqual(a['dependencies'][0]['path'],'books/AGECOPY.cpy')
    def test_copybook_error_keeps_copy_span_unsupported(self):
        p=analyze_program('ELIGIBLE.cbl',COBOL.replace('05 AGE PIC 9(3).','COPY AGECOPY.'),{'AGECOPY.cpy':'05 AGE PIC 9(3).\nCOPY NESTED.'})
        row=next(r for r in p['coverage'] if 'COPY' in r['source'])
        self.assertEqual(row['disposition'],'unsupported')
    def test_ambiguous_copy_candidates_stay_in_selected_accounting(self):
        files={'ELIGIBLE.cbl':COBOL.replace('05 AGE PIC 9(3).','COPY AGECOPY.'),'a/AGECOPY.cpy':'05 AGE PIC 9(3).','b/AGECOPY.cpy':'05 AGE PIC 9(2).'}
        analysis=analyze_sources(files,parse_manifest(MANIFEST))
        self.assertTrue(analysis['blockers'])
        self.assertTrue(all(a['selected'] for a in analysis['assets']))
    def test_all_export_paths_survive_asset_selection(self):
        files={'ELIGIBLE.cbl':COBOL,'arbitrary-name.jcl':'//JOBA JOB\n//S010 EXEC PGM=ELIGIBLE','UNUSED.cbl':COBOL.replace('ELIGIBLE.','UNUSED.')}
        a=analyze_sources(files,parse_manifest(MANIFEST))
        self.assertEqual({a['path'] for a in a['assets']},set(files))
    def test_dd_requires_io_adapter(self):
        files={'ELIGIBLE.cbl':COBOL,'j.jcl':'//JOBA JOB\n//S010 EXEC PGM=ELIGIBLE\n//IN DD DSN=PROD.DATA,DISP=SHR'}
        self.assertTrue(any(b['kind']=='unsupported_jcl' for b in analyze_sources(files,parse_manifest(MANIFEST))['blockers']))
    def test_job_condition_is_parsed_before_generating_python(self):
        with self.assertRaises(ValidationError):emit_jobs({'jobs':[{'name':'JOB','steps':[{'name':'S','program':'ELIGIBLE','condition':'RC=0 or True'}]}]},{'ELIGIBLE':'v'})
    def test_budget_exhaustion_explains_missing_boundary_obligations(self):
        p=self.program(COBOL);suite=plan_cases(p,budget=2)
        self.assertFalse(suite['coverage']['complete'])
        self.assertTrue(suite['coverage'].get('obligation_gaps'))
    def test_working_storage_is_not_treated_as_caller_record(self):
        text=COBOL.replace('LINKAGE SECTION.','WORKING-STORAGE SECTION.').replace(' USING INPUT-RECORD.','.')
        self.assertTrue(self.program(text)['blockers'])
    def test_missing_divisions_and_duplicate_groups_block(self):
        for text in [COBOL.replace('IDENTIFICATION DIVISION.\n',''),COBOL.replace('DATA DIVISION.\n',''),COBOL.replace('01 INPUT-RECORD.','01 INPUT-RECORD.\n01 INPUT-RECORD.')]:
            self.assertTrue(self.program(text)['blockers'])
    def test_duplicate_jcl_job_declarations_are_not_merged(self):
        files={'ELIGIBLE.cbl':COBOL,'j.jcl':'//JOBA JOB\n//JOBA JOB\n//S010 EXEC PGM=ELIGIBLE'}
        self.assertTrue(any(b['kind']=='unsupported_jcl' for b in analyze_sources(files,parse_manifest(MANIFEST))['blockers']))
    def test_and_precedes_or_and_quoted_literals_stay_case_sensitive(self):
        from workbench.reference import run_reference
        p=self.program(COBOL.replace('AGE >= 18','AGE = 1 OR AGE = 2 AND ACTIVE = "y"'))
        self.assertFalse(p['blockers'])
        for age,active,want in [(1,'X',True),(2,'X',False),(2,'y',True),(2,'Y',False)]:
            self.assertEqual(run_reference(p,{'AGE':age,'ACTIVE':active,'DECISION':' '})['trace'][0]['branch'],want)
    def test_mutation_reports_masked_effect_without_false_credit(self):
        from workbench.fixtures import adversarial_review
        text=COBOL.replace('    CONTINUE','    MOVE "N" TO DECISION')
        p=self.program(text);report=adversarial_review(p,emit_program(p),plan_cases(p))
        self.assertFalse(report['passed'])
        self.assertTrue(any(m['kind']=='effect' and m['rule_id']==p['rules'][0]['id'] for m in report['gaps']))
    def test_frozen_oracle_and_coverage_cannot_be_forged(self):
        import copy
        from workbench.fixtures import verify_program
        p=self.program(COBOL);suite=plan_cases(p)
        poisoned=copy.deepcopy(suite);poisoned['cases'][0]['expected']['return_code']=99
        with self.assertRaises(ValidationError):verify_program(p,emit_program(p),poisoned)
        poisoned=copy.deepcopy(suite);poisoned['cases']=[]
        with self.assertRaises(ValidationError):verify_program(p,emit_program(p),poisoned)
    def test_orchestration_rejects_modified_template_before_execution(self):
        from workbench.orchestration import verify_jobs
        from pathlib import Path
        p=self.program(COBOL);doc=parse_manifest(MANIFEST)
        doc.update(analysis={'programs':{'ELIGIBLE':p}},program_versions={'ELIGIBLE':'v'})
        with self.assertRaises(ValidationError):verify_jobs(doc,Path('/nonexistent'),"raise Exception('untrusted')")
    def test_normalized_job_name_collision_is_rejected(self):
        doc={'jobs':[{'name':'A-B','steps':[]},{'name':'A_B','steps':[]}]}
        with self.assertRaises(ValidationError):emit_jobs(doc,{})
    def test_adversarial_review_covers_each_rule_and_effect(self):
        from workbench.fixtures import adversarial_review
        p=self.program(COBOL);report=adversarial_review(p,emit_program(p),plan_cases(p))
        self.assertTrue(report['passed'],report)
        self.assertEqual({m['rule_id'] for m in report['mutations']},{r['id'] for r in p['rules']})
        self.assertTrue(any(m['kind']=='effect' for m in report['mutations']))

if __name__=='__main__':unittest.main()
