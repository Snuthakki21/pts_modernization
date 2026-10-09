"""Independent synthetic regression checks for the condensed intake contract."""
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from workbench.coordinator import Coordinator
from workbench.domain import decode, encode, sha
from workbench.lineage import map_lineage
from workbench.retrieval import build_request, _verify_request
from workbench.runner import start_process
from workbench.workspace_inputs import initialize_inputs
from test_source import COBOL

PROCESS='Process ID: review-process\nProcess name: Synthetic boundary review\n## Jobs\n1. REFJOB\n'
JCL="//REFJOB JOB (TEST),'FICTIONAL'\n//S1 EXEC PGM=ELIGIBLE\n"


class AcceleratorBoundaryReviewTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.folder=Path(self.tmp.name);self.root=self.folder/'workspace';self.root.mkdir()
        self.c=Coordinator(self.root);self.addCleanup(self.c.close)

    def put_export(self, path=None, extra=''):
        destination=self.root/'Endeavor' if path is None else path
        destination.mkdir(parents=True,exist_ok=True)
        (destination/'REFJOB.jcl').write_text(JCL+extra)
        (destination/'ELIGIBLE.cbl').write_text(COBOL)
        return destination

    def test_default_empty_scaffold_accepts_process_then_stops_at_missing_job(self):
        initialize_inputs(self.root)
        doc=self.c.prepare_process(PROCESS)
        self.assertEqual(doc['source_files'],{})
        self.assertFalse(doc['packet_issued'])
        self.c.start(doc['id']);self.c.advance(doc['id'])
        current=self.c.ledger.get(doc['id'])
        self.assertEqual(current['status'],'WAITING_DISCOVERY')
        self.assertFalse(current['packet_issued']);self.assertIsNone(current['analysis'])
        self.assertTrue(current.get('retrieval_request'))
        self.assertFalse((self.c.process_root(doc['id'])/'input/sources').exists())

    def test_default_local_intake_records_exact_endeavor_folder_provenance(self):
        export=self.put_export()
        doc=self.c.prepare_process(PROCESS)
        self.assertEqual(doc['source_origin']['kind'],'folder')
        self.assertEqual(doc['source_origin']['location'],str(export.absolute()))

    def test_simple_process_cli_uses_fixed_export_instead_of_stale_preferences(self):
        export=self.put_export();stale=self.put_export(self.folder/'old-export',extra='//* different old source\n')
        self.c.configure_workstation({'source_mode':'folder','source_folder':str(stale)})
        process=self.root/'Process.md';process.write_text(PROCESS)
        doc=start_process(self.c,process,assistant_mode='claude_files',requirements_selection=True)
        self.assertEqual(doc['source_files']['REFJOB.jcl'],sha((export/'REFJOB.jcl').read_bytes()))
        self.assertEqual(doc['source_origin']['location'],str(export.absolute()))

    def test_simple_process_does_not_inherit_unrelated_old_process_notes(self):
        self.put_export();old=self.folder/'old-notes.md';old.write_text('Old unrelated synthetic process context.')
        self.c.configure_workstation({'process_notes':str(old)})
        process=self.root/'Process.md';process.write_text(PROCESS)
        doc=start_process(self.c,process,assistant_mode='claude_files',requirements_selection=True)
        documents=doc['process_context']['documents']
        self.assertEqual(len(documents),1)
        self.assertEqual(documents[0]['text'],PROCESS)

    def test_ui_prepare_does_not_inherit_unrelated_saved_process_notes(self):
        from fastapi.testclient import TestClient
        from workbench.api import create_app
        self.put_export()
        old=self.folder/'old-ui-notes.md';old.write_text('Unrelated prior synthetic process.')
        self.c.close()
        app=create_app(self.root)
        try:
            app.state.coordinator.configure_workstation({'process_notes':str(old)})
            with TestClient(app,base_url='http://127.0.0.1:8765') as client:
                token=client.get('/api/state').json()['token']
                response=client.post('/api/intake/prepare',json={'manifest':PROCESS},
                    headers={'origin':'http://127.0.0.1:8765','x-workbench-token':token})
                self.assertEqual(response.status_code,200,response.text)
                doc=app.state.coordinator.ledger.get('review-process')
                self.assertEqual([note['text'] for note in doc['process_context']['documents']],[PROCESS])
        finally:app.state.coordinator.close()

    def test_claude_files_automatically_fetches_exact_missing_source_after_local_index(self):
        from workbench.connectors import ReadOnlyLineageResolver
        from test_lineage_connectors import FakeZowe
        source=COBOL+'\n       COPY LOST.\n'
        client=FakeZowe([{'dsname':'APP.COPY','dsorg':'PO'}],{'APP.COPY':[{'member':'LOST'}]},
                        '       01 LOST PIC X(5).\n')
        doc=self.c.prepare_process(PROCESS,{'REFJOB.jcl':JCL,'ELIGIBLE.cbl':source})
        self.c.start(doc['id'])
        with patch.dict('os.environ',{'WB_ZOWE_PROFILE':'fictional','WB_DATASET_HINT':'APP.COPY'},clear=True), \
             patch('workbench.connectors.ZoweReader',return_value=client) as zowe, \
             patch('workbench.connectors.Db2MCP') as db2:
            self.c.advance(doc['id'])
        current=self.c.ledger.get(doc['id'])
        self.assertTrue(current['lineage']['closure']['complete'])
        self.assertEqual(current['status'],'WAITING_REQUIREMENTS')
        zowe.assert_called();db2.assert_not_called()
        self.assertTrue(all(call.args[0]=='fictional' for call in zowe.call_args_list))
        self.assertEqual(client.calls[0][1],'APP.COPY')
        self.assertEqual(client.calls[1][2]['pattern'],'LOST')
        self.assertEqual(client.calls[-1],('read','APP.COPY(LOST)'))
        self.assertEqual([call[0] for call in client.calls],['list','members','read'])
        self.assertEqual(current['source_files']['remote/APP.COPY/LOST.cpy'],sha(client.content))
        self.assertEqual(current['intake_source_files'],doc['intake_source_files'])
        self.assertFalse(current['packet_issued']);self.assertFalse(current.get('retrieval_request'))
        self.c.manifest_integrity(current)

    def test_claude_files_complete_local_closure_does_not_initialize_environment(self):
        from workbench.connectors import ReadOnlyLineageResolver
        self.put_export();doc=self.c.prepare_process(PROCESS);self.c.start(doc['id'])
        with patch.object(ReadOnlyLineageResolver,'from_environment',side_effect=AssertionError('Local closure must not load private configuration')) as configure:
            self.c.advance(doc['id'])
        current=self.c.ledger.get(doc['id'])
        self.assertEqual(current['status'],'WAITING_REQUIREMENTS')
        self.assertTrue(current['lineage']['closure']['complete'])
        self.assertEqual(current['lineage']['read_only_lookups'],[])
        configure.assert_not_called();self.assertFalse(current['packet_issued'])

    def missing_copybooks(self, *names):
        source=COBOL+''.join('\n       COPY '+name+'.\n' for name in names)
        doc=self.c.prepare_process(PROCESS,{'REFJOB.jcl':JCL,'ELIGIBLE.cbl':source})
        self.c.start(doc['id']);self.c.advance(doc['id'])
        current=self.c.ledger.get(doc['id'])
        self.assertEqual(current['status'],'WAITING_DISCOVERY')
        request=decode(self.c.artifact(doc['id'],current['retrieval_request']['artifact']).read_bytes())
        self.assertEqual({n['name'] for n in request['needs']},set(names))
        return doc,request

    def absent_response(self,doc,request):
        response={'request_id':request['request_id'],'items':[{'need_id':need['need_id'],
            'status':'NOT_FOUND','reason':'Member not found in approved source library',
            'provenance':{'origin':'zowe_cli','tool':'zowe files view ds',
                'locator':'APP.COPY('+need['name']+')','retrieved_at':'2026-10-09T18:00:00Z'}} for need in request['needs']]}
        (self.root/request['return_folder']/'response.json').write_bytes(encode(response))
        self.c.local_agent_action(doc['id'],'continue',{})
        current=self.c.ledger.get(doc['id'])
        accepted=current['retrieval_request']['response_artifact']
        return accepted,self.c.artifact(doc['id'],accepted).read_bytes()

    def put_manual_copybook(self,name):
        path=self.root/'supplemental'/'Copybooks'/(name+'.cpy')
        path.parent.mkdir(parents=True,exist_ok=True)
        path.write_bytes(('       01 '+name+' PIC X(5).\n').encode())
        return path

    def test_manual_copybook_is_used_only_after_failed_remote_receipt_and_preserved(self):
        supplied=self.put_manual_copybook('LOSTA')
        doc,request=self.missing_copybooks('LOSTA')
        self.assertNotIn('supplemental/Copybooks/LOSTA.cpy',self.c.ledger.get(doc['id'])['source_files'])
        failed_artifact,failed_bytes=self.absent_response(doc,request)
        current=self.c.ledger.get(doc['id'])
        self.assertEqual(current['status'],'WAITING_REQUIREMENTS')
        self.assertEqual(current['source_files']['supplemental/Copybooks/LOSTA.cpy'],sha(supplied.read_bytes()))
        self.assertEqual(self.c.artifact(doc['id'],failed_artifact).read_bytes(),failed_bytes)
        self.assertEqual(current['intake_source_files'],doc['intake_source_files'])
        self.assertEqual(current['discovery_provenance']['supplemental/Copybooks/LOSTA.cpy']['origin'],'operator_export')
        view=encode(self.c.local_agent_view(doc['id'])).decode()
        self.assertNotIn('01 LOSTA PIC X(5)',view)
        self.assertNotIn('APP.COPY(LOSTA)',view)
        self.assertFalse(current['packet_issued']);self.c.manifest_integrity(current)

    def test_partial_manual_returns_can_add_second_exact_source_later(self):
        doc,request=self.missing_copybooks('LOSTA','LOSTB')
        failed_artifact,failed_bytes=self.absent_response(doc,request)
        self.assertEqual(self.c.ledger.get(doc['id'])['status'],'WAITING_DISCOVERY')
        self.put_manual_copybook('LOSTA');self.c.local_agent_action(doc['id'],'continue',{})
        partial=self.c.ledger.get(doc['id'])
        self.assertEqual(partial['status'],'WAITING_DISCOVERY')
        self.assertIn('supplemental/Copybooks/LOSTA.cpy',partial['source_files'])
        self.assertNotIn('supplemental/Copybooks/LOSTB.cpy',partial['source_files'])
        first_bytes=self.c.sources(partial)['supplemental/Copybooks/LOSTA.cpy'].encode()
        self.put_manual_copybook('LOSTB');self.c.local_agent_action(doc['id'],'continue',{})
        current=self.c.ledger.get(doc['id'])
        self.assertEqual(current['status'],'WAITING_REQUIREMENTS')
        self.assertTrue(current['lineage']['closure']['complete'])
        self.assertEqual(self.c.artifact(doc['id'],failed_artifact).read_bytes(),failed_bytes)
        self.assertEqual(self.c.sources(current)['supplemental/Copybooks/LOSTA.cpy'].encode(),first_bytes)
        self.assertFalse(current['retrieval_unresolved']);self.assertFalse(current['packet_issued'])
        self.c.manifest_integrity(current)

    def test_legacy_table_guide_retains_its_existing_renderer(self):
        from test_workflow import MANIFEST
        job="//JOBA JOB (TEST),'FICTIONAL'\n//S010 EXEC PGM=ELIGIBLE\n"
        doc=self.c.prepare_process(MANIFEST,{'JOBA.jcl':job,'ELIGIBLE.cbl':COBOL})
        self.c.start(doc['id']);self.c.advance(doc['id'])
        current=self.c.ledger.get(doc['id']);guide=self.c.process_guide(doc['id'])
        self.assertNotIn('accelerator_contract_version',current)
        self.assertEqual(guide['steps'][0]['id'],'setup')
        rendered=self.c.artifact(doc['id'],current['guide_artifact']).read_text()
        self.assertIn('8. Source-derived tests do not establish observed mainframe parity.',rendered)
        self.assertIn('7. Deliver one authentic human SME packet and wait.',rendered)
        self.assertFalse(current['packet_issued'])

    def test_twenty_valid_static_jcl_libraries_survive_retrieval_packet_binding(self):
        for count in (17,18,19,20):
            with self.subTest(libraries=count):
                libraries=['DEV.L'+str(i) for i in range(count)]
                files={'REFJOB.jcl':'//REFJOB JOB\n//LIBS JCLLIB ORDER=('+','.join(libraries)+')\n//S1 EXEC PROC=RUNPROC'}
                declared={'id':'Synthetic','name':'Synthetic','jobs':[{'name':'REFJOB','order':1,'steps':[]}]}
                lineage=map_lineage(files,declared)
                needs=[{k:gap[k] for k in ('kind','name','reason','source','relationship','status','source_library_hints') if k in gap}
                       for gap in lineage['closure']['gaps']]
                request=build_request({'id':'Synthetic','source_files':{},'accelerator_contract_version':1,'demo':True},needs)
                _verify_request(request)
                need=next(n for n in request['needs'] if n['kind']=='proc')
                self.assertEqual(need['source_library_hints'],libraries)

    def test_coordinator_default_request_preserves_seventeen_to_twenty_library_hints(self):
        for count in (17,18,19,20):
            with self.subTest(libraries=count):
                libraries=['DEV.L'+str(i) for i in range(count)]
                process=PROCESS.replace('review-process','review-libraries-'+str(count))
                source='//REFJOB JOB\n//LIBS JCLLIB ORDER=('+','.join(libraries)+')\n//S1 EXEC PROC=RUNPROC\n'
                doc=self.c.prepare_process(process,{'REFJOB.jcl':source})
                self.c.start(doc['id']);self.c.advance(doc['id'])
                current=self.c.ledger.get(doc['id'])
                self.assertEqual(current['status'],'WAITING_DISCOVERY')
                self.assertFalse(current['packet_issued'])
                request=decode(self.c.artifact(doc['id'],current['retrieval_request']['artifact']).read_bytes())
                _verify_request(request)
                needs=[need for need in request['needs'] if need['kind']=='proc']
                self.assertEqual(len(needs),1)
                self.assertEqual(needs[0]['source_library_hints'],libraries)
                unresolved=list(current['retrieval_unresolved'].values())
                self.assertEqual([r['need']['source_library_hints'] for r in unresolved if r['need']['kind']=='proc'],[libraries])

    def test_coordinator_keeps_identical_member_in_two_qualified_scopes_separate(self):
        self.put_export();doc=self.c.prepare_process(PROCESS)
        self.c.start(doc['id']);self.c.advance(doc['id'])
        current=self.c.ledger.get(doc['id'])
        self.assertEqual(current['status'],'WAITING_REQUIREMENTS')
        needs=[{'kind':'proc','name':'RUNPROC','source':'job:REFJOB','relationship':'execute',
                'status':'missing','reason':'Exact synthetic PROC missing','library':library,
                'source_library_hints':[library]} for library in ('DEV.FIRST','DEV.SECOND')]
        self.c.request_retrieval(doc['id'],needs)
        current=self.c.ledger.get(doc['id'])
        request=decode(self.c.artifact(doc['id'],current['retrieval_request']['artifact']).read_bytes())
        _verify_request(request)
        self.assertEqual(len(request['needs']),2)
        self.assertEqual({n['library'] for n in request['needs']},{'DEV.FIRST','DEV.SECOND'})
        self.assertEqual(len({n['need_id'] for n in request['needs']}),2)
        self.assertEqual(len(current['retrieval_unresolved']),2)
        self.assertEqual(set(current['retrieval_unresolved']),{self.c._retrieval_need_key(n) for n in request['needs']})
        for key, record in current['retrieval_unresolved'].items():
            self.assertEqual(key,self.c._retrieval_need_key(record['need']))
            self.assertEqual(record['need']['source_library_hints'],[record['need']['library']])
            self.assertEqual(record['request_id'],request['request_id'])


if __name__=='__main__':unittest.main()
