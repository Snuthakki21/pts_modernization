"""Architectural advice is source-grounded and never registers an Oracle adapter."""
from copy import deepcopy
import unittest

from workbench import backends
from workbench.domain import ValidationError, sha


class TargetArchitectureTests(unittest.TestCase):
    def document(self, *, kind='sql', selected=True, text='CREATE TABLE APP.ACCOUNT (ID INTEGER);'):
        return {'id':'architecture-test', 'target_backend':{'name':'python-sqlite','contract_version':1},
                'analysis':{'source_snapshot':'a'*64, 'assets':[
                    {'path':'schema.sql','kind':kind,'selected':selected,
                     'source_text':text,'source_hash':sha(text)}],
                    'classifications':{'schema.sql':{'kind':kind,'confidence':'structural','conflicts':[],
                        'evidence':[{'line':1,'reason':'SQL statement'}, {'line':None,'reason':'Filename suffix hint'}]}}}}


    def test_future_language_and_database_targets_share_gates_but_stay_unselectable(self):
        view=backends.target_architecture(self.document())
        future={'python-oracle','python-bigquery','java','dotnet'}
        self.assertTrue(future <= {candidate['name'] for candidate in view['candidates']})
        for name in future:
            with self.assertRaises(ValidationError):backends.get_backend(name)
            self.assertFalse(next(candidate for candidate in view['candidates'] if candidate['name']==name)['selectable'])
        self.assertEqual(view['extension_contract']['implemented'],['python-sqlite'])
        self.assertIn('warehouse',view['extension_contract']['bigquery_boundary'].lower())

    def test_missing_analysis_remains_provisional(self):
        view=backends.target_architecture({'id':'empty'})
        self.assertEqual(view['status'],'ASSESSMENT_INCOMPLETE')
        self.assertEqual(view['evidence'],[])
        self.assertFalse(view['production_ready'])
        self.assertIn('not establish',view['rationale'])

    def test_structural_sql_opens_target_database_assessment(self):
        view=backends.target_architecture(self.document())
        self.assertEqual(view['recommendation'],'assess_database_target')
        self.assertEqual(view['status'],'ASSESSMENT_REQUIRED')
        self.assertEqual(view['evidence'][0]['start_line'],1)
        self.assertEqual(view['evidence'][0]['path'],'schema.sql')
        self.assertEqual(view['evidence'][0]['source_hash'],self.document()['analysis']['assets'][0]['source_hash'])

    def test_suffix_without_structural_content_cannot_recommend_database(self):
        doc=self.document(kind='unknown',text='*> SQL documentation only')
        doc['analysis']['classifications']['schema.sql']['confidence']='unresolved'
        view=backends.target_architecture(doc)
        self.assertEqual(view['evidence_count'],0)
        self.assertEqual(view['recommendation'],'retain_bounded_python_sqlite')

    def test_unselected_database_export_does_not_change_selected_advice(self):
        self.assertEqual(backends.target_architecture(self.document(selected=False))['evidence_count'],0)

    def test_conflicting_classification_does_not_become_database_fact(self):
        doc=self.document()
        doc['analysis']['classifications']['schema.sql']['conflicts']=['COBOL versus SQL']
        self.assertEqual(backends.target_architecture(doc)['evidence_count'],0)

    def test_dclgen_is_an_assessment_trigger_not_verified_database_support(self):
        view=backends.target_architecture(self.document(kind='dclgen'))
        self.assertEqual(view['status'],'ASSESSMENT_REQUIRED')
        self.assertTrue(all(not c['native_db2_parity_verified'] for c in view['candidates']))

    def test_legacy_suffix_only_analysis_is_not_promoted(self):
        doc=self.document();doc['analysis'].pop('classifications')
        self.assertEqual(backends.target_architecture(doc)['evidence_count'],0)

    def test_embedded_database_dependency_retains_source_provenance(self):
        doc=self.document(kind='cobol_program',text='EXEC SQL SELECT ID FROM APP.ACCOUNT END-EXEC')
        doc['lineage']={'nodes':[{'kind':'db2_table','name':'APP.ACCOUNT','selected':True,
            'evidence':[{'path':'schema.sql','line':1,'end_line':1,'origin':'source'}]}]}
        view=backends.target_architecture(doc)
        self.assertEqual(view['evidence_count'],1)
        self.assertEqual(view['evidence'][0]['kind'],'database_dependency')
        self.assertEqual(view['evidence'][0]['object'],'APP.ACCOUNT')

    def test_dynamic_database_dependency_is_still_an_unverified_obligation(self):
        doc=self.document(kind='cobol_program',text='EXEC SQL EXECUTE IMMEDIATE :QUERY END-EXEC')
        doc['lineage']={'nodes':[{'kind':'db2_table','name':'<dynamic SQL>','selected':True,
            'resolution':'unresolved_dynamic','evidence':[{'path':'schema.sql','line':1}]}]}
        view=backends.target_architecture(doc)
        self.assertEqual(view['status'],'ASSESSMENT_REQUIRED')
        self.assertFalse(next(c for c in view['candidates'] if c['name']=='python-oracle')['selectable'])

    def test_source_hash_mismatch_cannot_supply_architecture_evidence(self):
        doc=self.document();doc['analysis']['assets'][0]['source_hash']='0'*64
        self.assertEqual(backends.target_architecture(doc)['evidence_count'],0)

    def test_invalid_or_unlocated_spans_are_not_invented(self):
        doc=self.document();classification=doc['analysis']['classifications']['schema.sql']
        classification['evidence']=[{'line':None},{'line':True},{'line':0},{'line':2}]
        self.assertEqual(backends.target_architecture(doc)['evidence_count'],0)

    def test_advice_cannot_register_oracle_or_claim_native_parity(self):
        view=backends.target_architecture(self.document())
        oracle=next(c for c in view['candidates'] if c['name']=='python-oracle')
        self.assertFalse(oracle['selectable'])
        self.assertEqual(oracle['implementation_status'],'NOT_IMPLEMENTED')
        self.assertFalse(view['production_ready'])
        with self.assertRaises(ValidationError):backends.get_backend('python-oracle')

    def test_projection_does_not_mutate_ledger_or_share_mutable_policy(self):
        doc=self.document();before=deepcopy(doc)
        first=backends.target_architecture(doc);first['obligations'][0]['required_evidence'].clear()
        self.assertEqual(doc,before)
        self.assertTrue(backends.target_architecture(doc)['obligations'][0]['required_evidence'])

    def test_advice_is_deterministic_and_qualified_for_each_release(self):
        doc=self.document();a=backends.target_architecture(doc);b=backends.target_architecture(deepcopy(doc))
        self.assertEqual(a,b)
        self.assertTrue(all(r['url'].startswith('https://') for r in a['references']))
        self.assertTrue(any('null' in r['id'] for r in a['references']))
        self.assertTrue(any('transaction' in r['id'] for r in a['references']))
        self.assertTrue(all(o['status']=='UNVERIFIED' for o in a['obligations']))

    def test_evidence_bound_is_explicit_and_count_is_not_truncated(self):
        doc=self.document();asset=doc['analysis']['assets'][0]
        asset['source_text']='\n'.join('CREATE TABLE APP.T'+str(i)+' (ID INTEGER);' for i in range(70))
        asset['source_hash']=sha(asset['source_text'])
        doc['analysis']['classifications']['schema.sql']['evidence']=[{'line':i+1,'reason':'SQL statement'} for i in range(70)]
        view=backends.target_architecture(doc)
        self.assertEqual(view['evidence_count'],70)
        self.assertEqual(len(view['evidence']),50)
        self.assertFalse(view['evidence_complete'])

    def test_actual_sql_source_and_lineage_are_projected(self):
        from workbench.mainframe import load_knowledge
        from workbench.source import analyze_sources
        from workbench.lineage import map_lineage
        from pathlib import Path
        from test_source import COBOL
        manifest={'id':'real-analysis','jobs':[{'name':'JOB1','steps':[{'name':'STEP1','program':'ELIGIBLE','inputs':[],'outputs':[],'condition':'ALWAYS'}]}],
                  'mainframe_knowledge':load_knowledge(Path('.'))}
        files={'ELIGIBLE.cbl':COBOL,'schema.sql':'CREATE TABLE APP.ACCOUNT (ID INTEGER);'}
        doc={**manifest,'analysis':analyze_sources(files,manifest),'lineage':map_lineage(files,manifest)}
        view=backends.target_architecture(doc)
        self.assertEqual(view['status'],'ASSESSMENT_REQUIRED')
        self.assertTrue(any(e['path']=='schema.sql' and e['source_hash']==sha(files['schema.sql']) for e in view['evidence']))

    def test_actual_sql_looking_comment_does_not_change_architecture(self):
        from workbench.mainframe import load_knowledge
        from workbench.source import analyze_sources
        from pathlib import Path
        doc={'id':'comment','jobs':[], 'mainframe_knowledge':load_knowledge(Path('.'))}
        doc['analysis']=analyze_sources({'schema.sql':'-- CREATE TABLE APP.ACCOUNT (ID INTEGER);'},doc)
        self.assertEqual(backends.target_architecture(doc)['evidence_count'],0)

    def test_target_contract_version_requires_an_exact_supported_integer(self):
        for version in (True, 2, '1', None):
            with self.subTest(version=version):
                doc=self.document();doc['target_backend']['contract_version']=version
                self.assertEqual(backends.target_architecture(doc)['status'],'UNIMPLEMENTED_TARGET')

    def test_unknown_active_backend_is_reported_as_unimplemented(self):
        doc=self.document();doc['target_backend']['name']='python-oracle'
        view=backends.target_architecture(doc)
        self.assertFalse(view['active_backend']['implemented'])
        self.assertEqual(view['status'],'UNIMPLEMENTED_TARGET')
        self.assertEqual(view['recommendation'],'resolve_unimplemented_target')


if __name__ == '__main__':
    unittest.main()
