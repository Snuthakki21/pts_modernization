"""Fictional approved MCP exports through the real Coordinator; no live access."""
from pathlib import Path
import json
import random
import secrets
import tempfile
import unittest
from unittest.mock import patch

from workbench.coordinator import Coordinator
from workbench.database_workflow import database_view,prepare_database,database_rows,database_comparison
from workbench.domain import ValidationError,encode,sha
from workbench.layout import validate_workspace
from workbench.intake import parse_manifest
from workbench.lineage import map_lineage
from workbench.source import analyze_sources
from test_source import COBOL
from test_workflow import MANIFEST

DDL='CREATE TABLE APP.SALE (ID CHAR(8) NOT NULL PRIMARY KEY, VALUE VARCHAR(40));'


def catalog_text(width=40):
    body={'schema_version':1,'kind':'DB2_TABLE_DESCRIPTION','schema':'APP','table':'SALE',
          'columns':[{'NAME':'ID','COLNO':0,'COLTYPE':'CHAR','LENGTH':8,'NULLS':'N'},
                     {'NAME':'VALUE','COLNO':1,'COLTYPE':'VARCHAR','LENGTH':width,'NULLS':'Y'}],
          'description_complete':True,'ddl':None,'constraints':None,'indexes':None,'triggers':None,
          'provenance':{'origin':'configured_mcp','tool':'db2_describe_table','locator':'APP.SALE',
                        'retrieved_at':'2026-10-07T16:00:00Z','environment':'FICTIONAL_TEST'}}
    return encode(body).decode().replace('"kind"',r'"\u006bind"').replace('DB2_TABLE_DESCRIPTION',r'\u0044B2_TABLE_DESCRIPTION')


class DatabaseWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);self.c=Coordinator(self.root);self.addCleanup(self.c.close)

    def process(self,ddl=DDL,pid='process-a',exclude=False,approved=True,source_path='db2/SALE.ddl',online=False,guided=False):
        manifest=MANIFEST.replace('process-a',pid)
        if online:manifest=manifest.split('|',1)[0]+'\n| Transaction | Program | Mapset | Map |\n|---|---|---|---|\n| T001 | ELIGIBLE | | |\n'
        source=COBOL.replace('  GOBACK.','  EXEC SQL SELECT ID FROM APP.SALE END-EXEC.\n  GOBACK.')
        files={'ELIGIBLE.cbl':source,'JOBA.jcl':'//JOBA JOB\n//S010 EXEC PGM=ELIGIBLE\n'}
        if online:files['resources.csd']='DEFINE TRANSACTION(T001) PROGRAM(ELIGIBLE)\nDEFINE PROGRAM(ELIGIBLE)\n'
        if not approved:files[source_path]=ddl
        if guided:self.c.prepare_process(manifest,source_files=files)
        else:self.c.create(manifest,files,assistant_mode='claude_files',requirements_selection=True)
        self.c.start(pid);self.c.advance(pid)
        if approved:
            self.assertEqual(self.c.ledger.get(pid)['status'],'WAITING_DISCOVERY')
            request=self.c.request_retrieval(pid)['retrieval'];self.assertEqual(len(request['needs']),1)
            folder=self.root/request['return_folder'];path=folder/'files'/source_path;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(ddl.encode('utf-8'))
            provenance={'origin':'configured_mcp','tool':'db2_describe_table','locator':'APP.SALE','retrieved_at':'2026-10-07T16:00:00Z','environment':'FICTIONAL_TEST'}
            (folder/'response.json').write_bytes(encode({'request_id':request['request_id'],'items':[{'need_id':request['needs'][0]['need_id'],
                'status':'FOUND','path':source_path,'sha256':sha(ddl),'provenance':provenance}]}))
            self.c.continue_retrieval(pid)
        self.assertEqual(self.c.ledger.get(pid)['status'],'WAITING_REQUIREMENTS')
        model=self.c.requirements_view(pid);omissions=[r['id'] for r in model['items'] if r['source_path']==source_path] if exclude else []
        self.c.save_requirements(pid,{'catalog_hash':model['catalog_hash'],'revision':model['revision'],'excluded_ids':omissions,'saved_by':'Fictional schema scope operator'})
        self.c.advance(pid);self.assertEqual(self.c.ledger.get(pid)['status'],'WAITING_COPILOT')
        return self.c.ledger.get(pid)

    def test_actual_request_bound_schema_is_registered_empty_separate_and_replay_safe(self):
        before=self.process();source_hashes=dict(before['source_files']);task=before['copilot_task_artifact']
        view=database_view(self.c,'process-a');self.assertTrue(view['can_prepare']);self.assertEqual(len(view['schemas']),1)
        view=prepare_database(self.c,'process-a',{});self.assertEqual(len(view['databases']),1)
        database=view['databases'][0];doc=self.c.ledger.get('process-a')
        self.assertEqual(doc['source_files'],source_hashes);self.assertEqual(doc['copilot_task_artifact'],task)
        self.assertEqual(doc['status'],'WAITING_COPILOT');self.assertFalse(doc['packet_issued']);self.assertFalse(doc.get('runs'))
        self.assertTrue(database['artifact'].startswith('target/database/'));self.assertEqual(database['tables'][0]['name'],'APP.SALE')
        self.assertEqual(database['tables'][0]['rows'],0);self.assertFalse(database['native_database_verified'])
        self.assertEqual(prepare_database(self.c,'process-a',{}),view)
        page=database_rows(self.c,'process-a',database['id'],'APP.SALE');self.assertEqual(page['rows'],[]);self.assertTrue(page['read_only'])
        self.assertFalse(any(p.endswith('target.sqlite') for p in doc['artifacts']));self.assertEqual(validate_workspace(self.root),[])

    def test_twenty_runtime_randomized_schema_intents_execute_and_preserve_exact_keys(self):
        seed=secrets.randbits(63);rng=random.Random(seed);lengths=rng.sample(range(1,80),20)
        for i,width in enumerate(lengths):
            with self.subTest(seed=seed,index=i,width=width):
                pid='database'+str(i);ddl=f'CREATE TABLE APP.SALE (ID CHAR(8) NOT NULL PRIMARY KEY, VALUE VARCHAR({width}));'
                self.process(ddl,pid);view=prepare_database(self.c,pid);database=view['databases'][0]
                self.assertEqual(database['tables'][0]['rows'],0)
                self.assertEqual(database_rows(self.c,pid,database['id'],'APP.SALE',filters={'ID':'00000001'})['rows'],[])
                self.assertEqual(view['schemas'][0]['source_hash'],sha(ddl));self.assertTrue(view['schemas'][0]['can_build'])
                self.assertIn(database['artifact'],self.c.ledger.get(pid)['artifacts'])
        self.assertEqual(validate_workspace(self.root),[])

    def test_escaped_typed_catalog_json_flows_through_real_intake_and_schema_browser(self):
        body={'schema_version':1,'kind':'DB2_TABLE_DESCRIPTION','schema':'APP','table':'SALE',
              'columns':[{'NAME':'ID','COLNO':0,'COLTYPE':'CHAR','LENGTH':8,'NULLS':'N'},
                         {'NAME':'VALUE','COLNO':1,'COLTYPE':'VARCHAR','LENGTH':40,'NULLS':'Y'}],
              'description_complete':True,'ddl':None,'constraints':None,'indexes':None,'triggers':None,
              'provenance':{'origin':'configured_mcp','tool':'db2_describe_table','locator':'APP.SALE',
                            'retrieved_at':'2026-10-07T16:00:00Z','environment':'FICTIONAL_TEST'}}
        text=encode(body).decode().replace('"kind"',r'"\u006bind"').replace('DB2_TABLE_DESCRIPTION',r'\u0044B2_TABLE_DESCRIPTION')
        self.process(text,source_path='db2/description.json',online=True)
        view=database_view(self.c,'process-a');self.assertEqual(view['schemas'][0]['source_path'],'db2/description.json')
        self.assertEqual(view['schemas'][0]['source_hash'],sha(text));self.assertTrue(view['can_prepare'])
        prepared=prepare_database(self.c,'process-a');database=prepared['databases'][0]
        self.assertEqual([table['name'] for table in database['tables']],['APP.SALE'])
        self.assertEqual(database_rows(self.c,'process-a',database['id'],'APP.SALE')['rows'],[])
        self.assertFalse(prepared['native_database_verified']);self.assertFalse(self.c.ledger.get('process-a')['packet_issued'])

    def test_twenty_prepared_batch_catalogs_resolve_exact_scope_but_leave_sql_and_native_gaps(self):
        seed=secrets.randbits(63);rng=random.Random(seed);widths=rng.sample(range(1,80),20);states=set()
        obligations={'DDL','CONSTRAINTS','INDEXES','TRIGGERS','NATIVE_SQL_TRANSACTION_TYPE_AND_AUTHORIZATION_EQUIVALENCE'}
        for index,width in enumerate(widths):
            with self.subTest(seed=seed,index=index,width=width):
                pid='guidedcatalog'+str(index);path='db2/description.json';text=('\ufeff' if index%2 else '')+catalog_text(width)
                doc=self.process(text,pid=pid,source_path=path,guided=True)
                self.assertEqual(doc['guided_contract_version'],1);self.assertNotIn('cics_contract_version',doc)
                self.assertEqual(doc['source_files'][path],sha(text));states.add(doc['source_files'][path])
                self.assertEqual(self.c.sources(doc)[path],text)
                lineage=doc['lineage'];self.assertTrue(lineage['closure']['complete'])
                self.assertEqual(lineage['scope']['root_jobs'],['JOBA']);self.assertEqual(lineage['scope']['root_transactions'],[])
                self.assertEqual(set(lineage['scope']['selected_files']),{'ELIGIBLE.cbl','JOBA.jcl',path})
                node=next(n for n in lineage['nodes'] if n['kind']=='db2_table')
                self.assertEqual(node['name'],'APP.SALE');self.assertEqual(node['path'],path)
                self.assertFalse(node['executable_source']);self.assertEqual(node['conversion_support'],'UNVERIFIED')
                self.assertEqual(node['catalog_evidence']['source_hash'],sha(text))
                analysis=json.loads(self.c.artifact(pid,doc['analysis_artifact']).read_bytes())
                self.assertNotIn('cics',analysis);self.assertNotIn('cics_contract_version',analysis)
                self.assertEqual(analysis['db2_catalog_evidence'][0]['source_hash'],sha(text))
                asset=next(a for a in analysis['assets'] if a['path']==path)
                self.assertEqual(asset['kind'],'db2_catalog_evidence');self.assertFalse(asset['executable_source'])
                self.assertEqual({g['obligation'] for g in analysis['blockers'] if g['kind']=='db2_catalog_semantics_gap'},obligations)
                self.assertTrue(any(g['kind']=='unsupported_source' and 'EXEC SQL SELECT ID FROM APP.SALE' in g['message'] for g in analysis['blockers']))
                view=prepare_database(self.c,pid);database=view['databases'][0]
                self.assertEqual(database['tables'][0]['name'],'APP.SALE');self.assertEqual(database['tables'][0]['rows'],0)
                self.assertEqual(database_rows(self.c,pid,database['id'],'APP.SALE')['rows'],[])
                self.assertFalse(view['native_database_verified']);self.assertFalse(database['native_database_verified'])
                current=self.c.ledger.get(pid)
                self.assertEqual(current['source_files'],doc['source_files']);self.assertFalse(current['packet_issued']);self.assertFalse(current['runs'])
                self.assertIn(database['artifact'],current['artifacts']);self.assertEqual(current['status'],'WAITING_COPILOT')
        self.assertEqual(len(states),20);self.assertEqual(validate_workspace(self.root),[])

    def test_guided_catalog_version_is_strict_and_absent_marker_retains_unknown_accounting(self):
        manifest=parse_manifest(MANIFEST);path='db2/description.json';text=catalog_text()
        source=COBOL.replace('  GOBACK.','  EXEC SQL SELECT ID FROM APP.SALE END-EXEC.\n  GOBACK.')
        files={'ELIGIBLE.cbl':source,'JOBA.jcl':'//JOBA JOB\n//S010 EXEC PGM=ELIGIBLE\n',path:text}
        for version in (True,False,0,2,'1',1.0,{},[]):
            for operation in (map_lineage,analyze_sources):
                with self.subTest(version=repr(version),operation=operation.__name__),self.assertRaisesRegex(ValidationError,'guided intake contract'):
                    operation(files,{**manifest,'guided_contract_version':version})
        legacy=map_lineage(files,manifest);legacy_analysis=analyze_sources(files,manifest)
        self.assertFalse(legacy['closure']['complete']);self.assertTrue(any(n['kind']=='db2_table' and n['name']=='APP.SALE' for n in legacy['missing_objects']))
        self.assertNotIn('db2_catalog_evidence',legacy_analysis);self.assertNotIn('cics',legacy_analysis)
        self.assertTrue(any(a['path']==path and a['kind']=='other_source' for a in legacy_analysis['assets']))
        self.assertEqual(encode(map_lineage(files,{**manifest,'guided_contract_version':None})),encode(legacy))
        self.assertEqual(encode(analyze_sources(files,{**manifest,'guided_contract_version':None})),encode(legacy_analysis))
        guided=map_lineage(files,{**manifest,'guided_contract_version':1})
        self.assertTrue(guided['closure']['complete']);self.assertEqual(guided['scope']['root_jobs'],['JOBA'])
        self.assertFalse(next(n for n in guided['nodes'] if n['kind']=='db2_table')['executable_source'])

    def test_guided_catalog_opt_in_does_not_enable_native_cics_actions_or_resource_rules(self):
        manifest=parse_manifest(MANIFEST)
        files={'ELIGIBLE.cbl':COBOL.replace('  GOBACK.','  EXEC CICS SEND MAP("SCREEN") MAPSET("MAPS") END-EXEC.\n  GOBACK.'),
               'JOBA.jcl':'//JOBA JOB\n//S010 EXEC PGM=ELIGIBLE\n'}
        baseline=map_lineage(files,manifest);guided=map_lineage(files,{**manifest,'guided_contract_version':1})
        self.assertEqual(encode(baseline),encode(guided))
        analysis=analyze_sources(files,{**manifest,'guided_contract_version':1})
        self.assertNotIn('cics',analysis);self.assertNotIn('cics_contract_version',analysis)
        self.assertTrue(any(g['kind']=='unsupported_source' and 'EXEC CICS SEND' in g['message'] for g in analysis['blockers']))
        self.assertEqual(analysis['db2_catalog_evidence'],[])

    def test_saved_no_excludes_entire_schema_file_and_is_never_overridden(self):
        self.process(exclude=True);view=database_view(self.c,'process-a');self.assertFalse(view['schemas'][0]['can_build'])
        self.assertTrue(any('selected No in requirements' in g['message'] for g in view['schemas'][0]['gaps']))
        with self.assertRaises(ValidationError):prepare_database(self.c,'process-a')
        self.assertEqual(database_view(self.c,'process-a')['databases'],[])

    def test_manual_ddl_is_visible_with_exact_provenance_gap(self):
        self.process(approved=False);view=database_view(self.c,'process-a');self.assertEqual(len(view['schemas']),1)
        self.assertTrue(any(g['kind']=='database_provenance_gap' for g in view['schemas'][0]['gaps']))
        with self.assertRaises(ValidationError):prepare_database(self.c,'process-a')

    def test_unknown_ids_unsafe_sql_rows_and_changed_registered_file_fail_closed(self):
        self.process();view=prepare_database(self.c,'process-a');database=view['databases'][0]
        for call in (lambda:prepare_database(self.c,'process-a',{'sql':'DROP TABLE X'}),
                     lambda:database_rows(self.c,'process-a','unregistered','APP.SALE'),
                     lambda:database_rows(self.c,'process-a',database['id'],'APP.SALE;DELETE'),
                     lambda:database_rows(self.c,'process-a',database['id'],'APP.SALE',filters={'unknown':'value'})):
            with self.assertRaises(ValidationError):call()
        path=self.c.artifact('process-a',database['artifact']);path.write_bytes(path.read_bytes()+b'adversarial corruption')
        with self.assertRaises(ValidationError):database_view(self.c,'process-a')
        with self.assertRaises(ValidationError):prepare_database(self.c,'process-a')

    def test_lost_publication_response_reuses_only_exact_generated_intent(self):
        self.process()
        with patch.object(self.c.ledger,'save_event',side_effect=OSError('lost response')):
            with self.assertRaises(OSError):prepare_database(self.c,'process-a')
        self.assertEqual(self.c.ledger.get('process-a').get('application_databases'),None)
        view=prepare_database(self.c,'process-a');self.assertEqual(len(view['databases']),1)
        self.assertEqual(len(self.c.ledger.get('process-a')['application_databases']),1)

    def test_comparison_rejects_unfrozen_refs_and_mutable_payload_rows(self):
        self.process();body={'db2_before':'input/sources/not-found.json','db2_after':'input/sources/not-found.json',
              'sqlite_before':'target/unregistered.json','sqlite_after':'target/unregistered.json','context':{}}
        with self.assertRaises(ValidationError):database_comparison(self.c,'process-a',body)
        body['rows']=[]
        with self.assertRaises(ValidationError):database_comparison(self.c,'process-a',body)
        self.assertFalse(self.c.ledger.get('process-a').get('database_comparisons'))

if __name__=='__main__':unittest.main()
