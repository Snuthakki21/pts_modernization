import copy
import json
import random
import secrets
import tempfile
import unittest
from pathlib import Path

from workbench.domain import ValidationError, encode, sha
from workbench.mainframe import classify_files, load_knowledge, utility_findings, validate_snapshot
from workbench.preflight import inspect_workspace
from workbench.source import analyze_sources
from workbench.target import emit_jobs


class MainframeKnowledgeTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(); self.root=Path(self.temp.name)
        self.snapshot=load_knowledge(self.root)
    def tearDown(self): self.temp.cleanup()
    def overlay(self, value):
        path=self.root/'knowledge'/'application-knowledge.json'
        path.parent.mkdir(exist_ok=True); path.write_text(json.dumps(value))
    def custom(self):
        return {'schema_version':1,'application':'Example only','notes':['Owner confirms business-date input is explicit.'],
            'utilities':[{'id':'APP_MATCH','name':'MATCHREF','aliases':['MRUN'],'category':'application_wrapper',
              'behavior':'Matches referrals using an application relationship file; requires full source evidence.',
              'required_evidence':['Source and control cards','Relationship file layout and matching/error rules'],
              'risks':['Unmatched and duplicate keys require distinct outcomes'],
              'references':['Local operating guide section 4, supplied by application owner'],
              'owner':'Application team','version':'Export version 1','record_formats':['Not yet confirmed'],
              'return_codes':['Not yet confirmed'],'side_effects':['Writes result dataset'],
              'dependencies':['Referral and eligibility files']} ]}
    def classify(self, files): return classify_files(files, {'jobs':[]}, self.snapshot)

    def test_extensionless_cobol_copybook_job_proc_and_include(self):
        result=self.classify({'PGM':'IDENTIFICATION DIVISION.\nPROGRAM-ID. PGM.\nDATA DIVISION.\nCOPY REC.\nPROCEDURE DIVISION.\nGOBACK.',
            'REC':'01 INPUT-RECORD.\n05 AGE PIC 9(3).', 'JOB':'//JOB1 JOB\n//S1 EXEC PGM=PGM',
            'MYPROC':'//MYPROC PROC\n//S1 EXEC PGM=PGM\n// PEND', 'INC':'//IN DD DSN=APP.IN,DISP=SHR'})
        self.assertEqual({k:v['kind'] for k,v in result.items()}, {'PGM':'cobol_program','REC':'copybook','JOB':'jcl_job','MYPROC':'jcl_proc','INC':'jcl_fragment'})
        self.assertTrue(any('COPY' in e['reason'] for e in result['REC']['evidence']))
        self.assertTrue(all(v['conversion_support']=='not_established' for v in result.values()))

    def test_conflicting_extension_and_mixed_source_are_not_silently_translated(self):
        result=self.classify({'WRONG.cbl':'//JOB1 JOB\n//S EXEC PGM=IEFBR14',
            'MIXED':'PROGRAM-ID. PGM.\n//JOB1 JOB', 'BOGUS.cbl':'ordinary data, no source markers'})
        self.assertEqual(result['WRONG.cbl']['kind'],'ambiguous')
        self.assertEqual(result['MIXED']['kind'],'ambiguous')
        self.assertEqual(result['BOGUS.cbl']['kind'],'unknown')
        self.assertTrue(result['WRONG.cbl']['conflicts'])

    def test_comment_or_literal_program_id_does_not_classify_program(self):
        result=self.classify({'NOTCODE':'000100*PROGRAM-ID. BAD.\n*> PROGRAM-ID. BAD.\n"PROGRAM-ID. BAD."',
                              'ACTUAL':'000100 IDENTIFICATION DIVISION.\n000200 PROGRAM-ID. REAL.\n000300 DATA DIVISION.'})
        self.assertEqual(result['NOTCODE']['kind'],'unknown')
        self.assertEqual(result['ACTUAL']['kind'],'cobol_program')
        self.assertEqual(result['ACTUAL']['evidence'][0]['line'],2)

    def test_dclgen_bms_controls_and_other_languages(self):
        result=self.classify({'HOST.cpy':'EXEC SQL DECLARE APP.TABLE1 TABLE\nEND-EXEC.\n01 HOST-REC.\n05 ITEM PIC X.',
           'MAP':'MAP1 DFHMSD TYPE=MAP\nSCREEN DFHMDI SIZE=(24,80)', 'SORTIN':'SORT FIELDS=(1,5,CH,A)',
           'R':'/* REXX */\nsay "hello"', 'P':'MAIN: PROCEDURE OPTIONS(MAIN);',
           'A':'PROGA CSECT\n         BR 14', 'C':'DEFINE TRANSACTION(T001) GROUP(APP) PROGRAM(PGM)',
           'CL':'PROC 0 ARG', 'S':'LJOB,JOB=NIGHTLY'})
        expected={'HOST.cpy':'dclgen','MAP':'bms_map','SORTIN':'utility_control','R':'rexx','P':'pli','A':'assembler','C':'cics_definition','CL':'clist','S':'scheduler_definition'}
        self.assertEqual({k:v['kind'] for k,v in result.items()},expected)

    def test_standalone_utility_control_members_are_recognized_without_suffix(self):
        cards=['INCLUDE COND=(1,1,CH,EQ,C"Y")','OMIT COND=(1,1,CH,EQ,C"N")',
               'COUNT FROM(INPUT) EMPTY','COPY FROM(INPUT) TO(OUTPUT)',
               'DELETE APP.OLD.DATA PURGE','SET MAXCC=0','LISTCAT']
        result=self.classify({str(n):text for n,text in enumerate(cards)})
        self.assertTrue(all(row['kind']=='utility_control' for row in result.values()))

    def test_jcl_inline_sort_cards_and_proc_stay_in_job(self):
        result=self.classify({'JOB.jcl':'//JOB1 JOB\n//PROC1 PROC\n//S1 EXEC PGM=ICEMAN\n//SYSIN DD *\nSORT FIELDS=COPY\n/*\n// PEND'})
        self.assertEqual(result['JOB.jcl']['kind'],'jcl_job')
        self.assertEqual(result['JOB.jcl']['utility_ids'],['DFSORT'])
        self.assertEqual(self.classify({'P.jcl':'//P PROC\n//S EXEC PGM=IEFBR14'})['P.jcl']['kind'],'jcl_proc')

    def test_recognized_iefbr14_retains_side_effect_risk_and_blocks_adapter(self):
        manifest={'jobs':[{'name':'JOBA','steps':[{'name':'S1','program':'IEFBR14'},{'name':'S2','program':'BUSINESS'}]}]}
        findings=utility_findings(manifest,self.snapshot)
        self.assertEqual(len(findings),1)
        self.assertEqual(findings[0]['conversion_support'],'adapter_required')
        self.assertIn('create or delete',findings[0]['behavior'])
        self.assertEqual(findings[0]['job'],'JOBA')

    def test_application_context_is_frozen_and_no_support_authority(self):
        app=self.custom(); self.overlay(app); snapshot=load_knowledge(self.root)
        app['utilities'][0]['behavior']='Different behavior'; self.overlay(app)
        self.assertNotEqual(snapshot['content_hash'],load_knowledge(self.root)['content_hash'])
        validate_snapshot(snapshot)
        findings=utility_findings({'jobs':[{'name':'J','steps':[{'name':'S','program':'MRUN'}]}]},snapshot)
        self.assertEqual(findings[0]['source'],'application')
        self.assertEqual(findings[0]['application_details']['owner'],'Application team')
        self.assertEqual(findings[0]['application_details']['evidence_status'],'unverified_application_context')
        self.assertIn('Matches referrals',findings[0]['behavior'])
        self.assertEqual(findings[0]['conversion_support'],'adapter_required')

    def test_overlay_cannot_shadow_standard_alias_or_assert_executable_support(self):
        for mutate in (lambda u:u.update({'name':'SORT'}), lambda u:u.update({'supported':True}), lambda u:u.update({'command':'python anything.py'})):
            app=self.custom(); mutate(app['utilities'][0]); self.overlay(app)
            with self.assertRaises(ValidationError): load_knowledge(self.root)

    def test_duplicate_json_keys_and_symlink_overlay_rejected(self):
        path=self.root/'knowledge'/'application-knowledge.json'; path.parent.mkdir()
        path.write_text('{"schema_version":1,"schema_version":1}')
        with self.assertRaises(ValidationError): load_knowledge(self.root)
        path.unlink(); path.symlink_to(self.root/'elsewhere.json')
        with self.assertRaises(ValidationError): load_knowledge(self.root)

    def test_snapshot_changes_and_bad_schema_fail_closed(self):
        altered=copy.deepcopy(self.snapshot); altered['catalog']['utilities'][0]['behavior']='Changed'
        with self.assertRaises(ValidationError): validate_snapshot(altered)
        bad=copy.deepcopy(self.snapshot); bad['schema_version']=True
        with self.assertRaises(ValidationError): validate_snapshot(bad)
        for field,value in [('aliases',['A','A']),('required_evidence',[]),('name','lowercase')]:
            bad=copy.deepcopy(self.snapshot); bad['catalog']['utilities'][0][field]=value
            bad['content_hash']=sha(encode({k:v for k,v in bad.items() if k!='content_hash'}))
            with self.assertRaises(ValidationError): validate_snapshot(bad)

    def test_source_only_utility_invocations_and_exact_manifest_deduplication(self):
        manifest={'jobs':[{'name':'JOBA','steps':[{'name':'S1','program':'IEFBR14'}]}]}
        files={'JOB':'//JOBA JOB\n//S1 EXEC PGM=IEFBR14\n//S2 EXEC PGM=IDCAMS',
               'FAKE':'*> //S3 EXEC PGM=IEBCOPY\nMOVE "PGM=BPXBATCH" TO TEXT',
               'PROC':'//P PROC\n//S4 EXEC PGM=IEBGENER'}
        found=utility_findings(manifest,self.snapshot,files)
        self.assertEqual([f['program'] for f in found],['IEFBR14','IDCAMS','IEBGENER'])
        self.assertEqual(found[0]['source_refs'],[{'path':'JOB','line':2}])
        self.assertEqual(found[1]['invocation_origin'],'source')
        self.assertEqual(found[2]['job'],'')

    def test_referenced_procedural_copybook_has_role_without_claiming_support(self):
        result=self.classify({'PGM':'PROGRAM-ID. A.\nCOPY RULES.', 'RULES':'IF ACTIVE = "Y"\nCONTINUE\nEND-IF'})
        self.assertEqual(result['RULES']['kind'],'copybook')
        self.assertEqual(result['RULES']['conversion_support'],'not_established')

    def test_national_character_programs_unnamed_steps_and_false_utility_literals(self):
        app=self.custom(); app['utilities'][0]['name']='$MATCH'; app['utilities'][0]['aliases']=['#MATCH','@MATCH']
        self.overlay(app); snapshot=load_knowledge(self.root)
        files={'JOB':'//JOB1 JOB\n//S1 EXEC PGM=$MATCH\n// EXEC PGM=#MATCH',
               'NOTJCL':'PROGRAM-ID. PGM.\nMOVE "PGM=IDCAMS" TO TEXT'}
        findings=utility_findings({'jobs':[]},snapshot,files)
        self.assertEqual([x['program'] for x in findings],['$MATCH','#MATCH'])
        self.assertEqual(findings[1]['step'],'')
        classes=classify_files(files,{'jobs':[]},snapshot)
        self.assertEqual(classes['JOB']['utility_ids'],['APP_MATCH'])
        self.assertEqual(classes['NOTJCL']['utility_ids'],[])

    def test_missing_optional_overlay_is_valid_and_deterministic(self):
        validate_snapshot(self.snapshot)
        self.assertIsNone(self.snapshot['source_hashes']['application'])
        self.assertEqual(self.snapshot,load_knowledge(self.root))
        self.assertEqual(len(self.snapshot['catalog']['categories']),17)
        self.assertGreaterEqual(len(self.snapshot['catalog']['utilities']),17)

    def test_db2_utility_without_verified_equivalent_retains_each_named_obligation(self):
        """Recognition of twenty driver contexts cannot become SQLite/no-op credit."""
        rng = random.Random(secrets.randbits(63))
        identities = rng.sample(range(1000000), 20)
        jobs, files = [], {}
        rows = []
        for index, identity in enumerate(identities):
            job, step = f'J{identity:06d}', f'S{index:03d}'
            utility = ('DSNUTILB', 'DSNTIAUL')[index % 2]
            jobs.append({'name': job, 'steps': [{'name': step, 'program': utility,
                         'condition': 'ALWAYS', 'inputs': ['SYSIN'], 'outputs': ['SYSREC']}]})
            # These are immutable simulated source exports; nothing is executed.
            files[f'{job}.jcl'] = f'//{job} JOB\n//{step} EXEC PGM={utility}\n'
            control = (f'REORG TABLESPACE APP.T{identity:06d}\n' if utility == 'DSNUTILB'
                       else f'SELECT * FROM APP.T{identity:06d};\n')
            files[f'{job}.control'] = control
            rows.append(f'| {index + 1} | {job} | 1 | {step} | {utility} | SYSIN | SYSREC | Always |')
        manifest_text = ('# Fictional Db2 utility preservation\n'
            '- Process ID: db2-fidelity\n- Process name: Fictional utility contexts\n'
            '| Job order | Job | Step order | Step | Program or utility | Input files/tables | Output files/tables | Condition or dependency |\n'
            '|---|---|---|---|---|---|---|---|\n' + '\n'.join(rows) + '\n')
        export = self.root / 'Endeavor'; export.mkdir()
        for path, text in files.items():
            (export / path).write_text(text, encoding='utf-8')
        manifest_path = self.root / 'process-input.md'; manifest_path.write_text(manifest_text)
        original = {path: (export / path).read_bytes() for path in files}
        preflight = inspect_workspace(self.root, manifest_path, environ={})
        self.assertEqual(preflight['status'], 'READY', preflight['checks'])
        self.assertEqual(preflight['conversion_status'], 'BLOCKED')
        manifest = {'jobs': jobs, 'mainframe_knowledge': self.snapshot}
        analysis = analyze_sources(files, manifest)
        findings = analysis['utility_findings']
        self.assertEqual(len(findings), 20)
        self.assertEqual({(item['job'], item['step'], item['program']) for item in findings},
                         {(job['name'], job['steps'][0]['name'], job['steps'][0]['program']) for job in jobs})
        gaps = [gap for gap in analysis['blockers'] if gap['kind'] == 'unsupported_utility']
        self.assertEqual(len(gaps), 20)
        self.assertEqual({(gap['job'], gap['step'], gap['utility_id']) for gap in gaps},
                         {(item['job'], item['step'], item['utility_id']) for item in findings})
        for finding, gap in zip(findings, gaps):
            self.assertEqual(finding['conversion_support'], 'adapter_required')
            self.assertTrue(finding['required_evidence'])
            self.assertEqual(finding['source_refs'], [{'path': finding['job'] + '.jcl', 'line': 2}])
            self.assertEqual(gap['source_refs'], finding['source_refs'])
            self.assertIn('no verified executable adapter', gap['message'])
            self.assertIn(finding['program'], gap['message'])
            self.assertIn(finding['required_evidence'][0], gap['message'])
        self.assertFalse(analysis['programs'])
        self.assertFalse(analysis['rules'])
        self.assertEqual({asset['path'] for asset in analysis['assets']}, set(files))
        for asset in analysis['assets']:
            self.assertEqual(asset['source_text'], files[asset['path']])
            self.assertEqual(asset['source_hash'], sha(files[asset['path']]))
            self.assertEqual(asset['loc']['physical'], len(files[asset['path']].splitlines()))
            self.assertTrue(asset['selected'])
        with self.assertRaisesRegex(ValidationError, 'Missing version-pinned program'):
            emit_jobs(manifest, {})
        self.assertEqual({path: (export / path).read_bytes() for path in files}, original)

if __name__=='__main__': unittest.main()
