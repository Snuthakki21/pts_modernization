"""The actual coordinator must discover before any conversion/review work."""
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from workbench.coordinator import Coordinator
from workbench.domain import ValidationError, encode, sha

EXAMPLES=Path(__file__).resolve().parent.parent/'examples'

class DiscoveryWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name);self.c=Coordinator(self.root);self.addCleanup(self.c.close)
        self.manifest=(EXAMPLES/'process-input.md').read_text()
        self.files={p.name:p.read_text() for p in (EXAMPLES/'Endeavor').iterdir() if p.is_file()}

    def create(self,files=None):return self.c.create(self.manifest,files or self.files,assistant_mode='copilot_chat')

    def test_missing_job_blocks_before_conversion_or_single_sme_packet(self):
        doc=self.create({k:v for k,v in self.files.items() if not k.endswith('.jcl')})
        self.c.start(doc['id']);result=self.c.advance(doc['id'])
        self.assertEqual(result['status'],'WAITING_DISCOVERY');self.assertFalse(result['packet_issued'])
        self.assertFalse((self.root/'shared/target/python').exists())
        self.assertTrue(result['lineage']['closure']['gaps'])

    def test_copilot_handoff_has_real_frozen_evidence_without_endpoint(self):
        doc=self.create();self.c.start(doc['id']);result=self.c.advance(doc['id'])
        self.assertEqual(result['status'],'WAITING_COPILOT');self.assertFalse(result['packet_issued'])
        self.c.artifact(doc['id'],result['analysis_artifact'])
        task=self.c.agent_task(doc['id']);info=next(iter(task['lineage']['sources'].items()))
        submission={'process_id':doc['id'],'task_hash':task['task_hash'],'lineage_hash':task['lineage_hash'],
          'summary':'Source-based fictional example review','assumptions':[],'questions':[],
          'source_refs':[{'path':info[0],'start_line':1,'end_line':1,'source_hash':info[1]['source_hash']}],
          'adapter_tasks':[{'id':t['id'],'implementation_plan':'Preserve as unresolved until independently implemented and verified','expected_tests':['Source-based positive and negative behavior']} for t in task['adapter_tasks']]}
        self.c.submit_agent_analysis(doc['id'],submission);result=self.c.advance(doc['id'])
        self.assertEqual(result['status'],'WAITING_SME');self.assertTrue(result['packet_issued'])
        self.assertEqual(result['llm']['usage']['status'],'UNKNOWN')
        with self.assertRaises(ValidationError):self.c.submit_agent_analysis(doc['id'],submission)

    def test_unrelated_duplicate_programs_retained_without_blocking_selected_scope(self):
        files={**self.files,'other/A.cbl':'IDENTIFICATION DIVISION.\nPROGRAM-ID. EXTRA.\nGOBACK.\n','other/B.cbl':'IDENTIFICATION DIVISION.\nPROGRAM-ID. EXTRA.\nGOBACK.\n'}
        doc=self.create(files);self.c.start(doc['id']);result=self.c.advance(doc['id'])
        self.assertEqual(result['status'],'WAITING_COPILOT');self.assertEqual(len(result['source_files']),len(files))
        self.assertNotIn('other/A.cbl',result['lineage_scope'])

    def test_refresh_invalidates_task_without_consuming_review_round(self):
        doc=self.create();self.c.start(doc['id']);self.c.advance(doc['id'])
        old=self.c.agent_task(doc['id']);old_path=self.c.ledger.get(doc['id'])['copilot_task_artifact']
        self.c.refresh_analysis(doc['id']);result=self.c.advance(doc['id']);new=self.c.agent_task(doc['id'])
        self.assertNotEqual(old['task_hash'],new['task_hash']);self.assertFalse(result['packet_issued'])
        self.assertIn(old_path,result['artifacts']);self.c.artifact(doc['id'],old_path)

    def test_mutated_lineage_cannot_shrink_scope_on_refresh(self):
        doc=self.create();self.c.start(doc['id']);self.c.advance(doc['id'])
        recorded=self.c.ledger.get(doc['id']);recorded['lineage']['scope']['selected_files']=[];self.c.ledger.save(recorded)
        with self.assertRaisesRegex(ValidationError,'lineage scope'):self.c.refresh_analysis(doc['id'])
        self.assertFalse(self.c.ledger.get(doc['id'])['packet_issued'])

    def test_discovery_journal_recovery_rejects_changed_bytes(self):
        doc=self.create();entry={'path':'discovered/BOOK.cpy','text':'01 BOOK.\n','source_hash':sha('01 BOOK.\n'),'provenance':{'dataset':'APP.BOOK(BOOK)'}}
        recover=self.c.recover_discovered_sources
        def crash_after_journal(current):
            if current.get('pending_discovery'):raise RuntimeError('crash')
            return recover(current)
        with patch.object(self.c,'recover_discovered_sources',side_effect=crash_after_journal):
            with self.assertRaises(RuntimeError):self.c.freeze_discovered_sources(doc,[entry])
        recorded=self.c.ledger.get(doc['id']);self.assertIn('pending_discovery',recorded)
        recovered=self.c.sources(recorded);self.assertEqual(recovered[entry['path']],entry['text'])
        self.assertNotIn('pending_discovery',self.c.ledger.get(doc['id']))
        journal=self.c.process_root(doc['id'])/recorded['artifacts'][-1]
        journal.write_bytes(b'{}')
        recorded['pending_discovery']={'artifact':recorded['artifacts'][-1],'hash':'0'*64}
        with self.assertRaisesRegex(ValidationError,'integrity'):self.c.recover_discovered_sources(recorded)

    def test_config_and_visio_layout_do_not_block_actual_coordinator(self):
        self.c.close();(self.root/'mcp.json').write_text('{}');(self.root/'Visio').mkdir();(self.root/'Visio/lineage.vsdx').write_bytes(b'placeholder')
        self.c=Coordinator(self.root);self.addCleanup(self.c.close)
        doc=self.create();self.c.start(doc['id']);self.assertEqual(self.c.advance(doc['id'])['status'],'WAITING_COPILOT')

    def test_documented_knowledge_and_zowe_schema_allow_actual_intake(self):
        self.c.close()
        (self.root/'knowledge').mkdir(exist_ok=True)
        (self.root/'knowledge/inventory-baseline.json').write_bytes((EXAMPLES/'inventory-baseline.json').read_bytes())
        (self.root/'knowledge/input-locations.json').write_bytes(encode({'schema_version':1,'locations':[]}))
        (self.root/'zowe.config.schema.json').write_bytes(b'{}')
        self.c=Coordinator(self.root);self.addCleanup(self.c.close)
        doc=self.create();self.c.start(doc['id']);result=self.c.advance(doc['id'])
        self.assertEqual(result['status'],'WAITING_COPILOT')
        self.assertEqual(result['inventory_baseline']['document']['declared_total'],1829)


class CicsRetrievalWorkflowTests(unittest.TestCase):
    def test_new_packet_uses_explicit_transports_and_historical_packet_is_unchanged(self):
        from workbench.retrieval import build_request, validate_binding
        doc={'id':'retrieval-audit','source_files':{}}
        needs=[{'kind':'db2_table','name':'APP.CUSTOMER','reason':'Observed columns and original DDL needed'}]
        old=build_request(doc,needs)
        validate_binding(old,doc)
        self.assertEqual(old['schema_version'],1)
        self.assertNotIn('Mandatory transport boundary',old['copilot_prompt'])
        new=build_request({**doc,'cics_contract_version':1},needs)
        validate_binding(new,{**doc,'cics_contract_version':1})
        self.assertEqual(new['schema_version'],2)
        self.assertIn('Zowe CLI',new['copilot_prompt']);self.assertIn('db2_describe_table',new['copilot_prompt'])
        self.assertIn('Claude Code has no MCP access',new['copilot_prompt'])
        self.assertIn('Do not invent DDL',new['copilot_prompt'])
        self.assertIn(new['return_folder'],new['copilot_prompt'])
        self.assertNotEqual(new['request_id'],old['request_id'])

    def test_catalog_return_validates_outer_provenance_hash_and_stays_inside_process_sources(self):
        from workbench.retrieval import build_request, write_request, inspect_response
        from test_lineage_discovery import Db2CatalogReceiptTests
        from unittest.mock import patch
        receipt=Db2CatalogReceiptTests().receipt();raw=encode(receipt)
        with tempfile.TemporaryDirectory(dir='.implementation/tmp') as temp:
            root=Path(temp);doc={'id':'retrieval-audit','source_files':{},'cics_contract_version':1}
            request=build_request(doc,[{'kind':'db2_table','name':'APP.CUSTOMER','reason':'Table description needed'}]);write_request(root,request)
            inbox=root/request['return_folder'];path='db2/APP.CUSTOMER.json.txt';(inbox/'files/db2').mkdir()
            (inbox/'files'/path).write_bytes(raw)
            response={'request_id':request['request_id'],'items':[{'need_id':request['needs'][0]['need_id'], 'status':'FOUND',
                'path':path,'sha256':sha(raw),'provenance':receipt['provenance']}]}
            (inbox/'response.json').write_bytes(encode(response))
            with patch('subprocess.Popen',side_effect=AssertionError('Retrieval import must not contact a service')):
                result=inspect_response(root,request,{})
            self.assertTrue(result['complete']);self.assertEqual(result['entries'][0]['text'],raw.decode())
            self.assertEqual(result['entries'][0]['source_hash'],sha(raw))
            self.assertFalse((root/'processes/retrieval-audit/input/sources'/path).exists())
            response['items'][0]['provenance']={**receipt['provenance'],'tool':'zowe'}
            (inbox/'response.json').write_bytes(encode(response))
            with self.assertRaisesRegex(ValidationError,'typed read-only Db2 MCP'):inspect_response(root,request,{})
            self.assertFalse((root/'processes/retrieval-audit/input/sources'/path).exists())

    def test_schema_two_db2_needs_and_schema_declarations_require_typed_mcp(self):
        from workbench.retrieval import build_request,write_request,inspect_response
        for kind,source,path in (('db2_table','CREATE TABLE APP.CUSTOMER (ID CHAR(9));','CUSTOMER.sql'),
                                 ('db2_stored_procedure','CREATE PROCEDURE APP.P() LANGUAGE SQL;','PROC.txt'),
                                 ('unknown_dependency','CREATE TABLE APP.CUSTOMER (ID CHAR(9));','CUSTOMER.txt'),
                                 ('unknown_dependency','CREATE\nTABLE APP.CUSTOMER (ID CHAR(9));','MULTILINE.txt')):
            for origin,tool in (('zowe_cli','zowe files view ds'),('configured_mcp','shell'),('configured_mcp','db2_sample_rows')):
                with self.subTest(kind=kind,path=path,origin=origin,tool=tool),tempfile.TemporaryDirectory(dir='.implementation/tmp') as temp:
                    root=Path(temp);doc={'id':'transport-audit','source_files':{},'cics_contract_version':1}
                    request=build_request(doc,[{'kind':kind,'name':'APP.CUSTOMER','reason':'Actual schema needed'}]);write_request(root,request)
                    inbox=root/request['return_folder'];(inbox/'files'/path).write_bytes(source.encode('utf-8'))
                    provenance={'origin':origin,'tool':tool,'locator':'APP.CUSTOMER','retrieved_at':'2026-10-07T16:00:00Z'}
                    item={'need_id':request['needs'][0]['need_id'],'status':'FOUND','path':path,'sha256':sha(source),'provenance':provenance}
                    (inbox/'response.json').write_bytes(encode({'request_id':request['request_id'],'items':[item]}))
                    with self.assertRaisesRegex(ValidationError,'typed read-only Db2 MCP'):inspect_response(root,request)
                    self.assertFalse((root/'processes/transport-audit/input/sources'/path).exists())
                    item['provenance']={**provenance,'origin':'configured_mcp','tool':'db2_describe_table'}
                    (inbox/'response.json').write_bytes(encode({'request_id':request['request_id'],'items':[item]}))
                    self.assertTrue(inspect_response(root,request)['complete'])

    def test_shared_source_cannot_bypass_db2_transport_on_second_need(self):
        from workbench.retrieval import build_request,write_request,inspect_response
        with tempfile.TemporaryDirectory(dir='.implementation/tmp') as temp:
            root=Path(temp);doc={'id':'transport-audit','source_files':{},'cics_contract_version':1}
            request=build_request(doc,[{'kind':'copybook','name':'CUSTOMER','reason':'Original source'},
                                       {'kind':'db2_table','name':'APP.CUSTOMER','reason':'Actual catalog'}]);write_request(root,request)
            inbox=root/request['return_folder'];raw='01 CUSTOMER.\n05 ID PIC X(9).\n';path='CUSTOMER.cpy';(inbox/'files'/path).write_bytes(raw.encode('utf-8'))
            items=[{'need_id':need['need_id'],'status':'FOUND','path':path,'sha256':sha(raw),'provenance':
                    {'origin':'zowe_cli','tool':'zowe files view ds','locator':'APP.COPY(CUSTOMER)','retrieved_at':'2026-10-07T16:00:00Z'}} for need in request['needs']]
            (inbox/'response.json').write_bytes(encode({'request_id':request['request_id'],'items':items}))
            with self.assertRaisesRegex(ValidationError,'typed read-only Db2 MCP'):inspect_response(root,request)

    def test_schema_one_preserves_historical_transport_acceptance(self):
        from workbench.retrieval import build_request,write_request,inspect_response
        with tempfile.TemporaryDirectory(dir='.implementation/tmp') as temp:
            root=Path(temp);request=build_request({'id':'historical','source_files':{}},[{'kind':'db2_table','name':'APP.CUSTOMER','reason':'Existing contract'}]);write_request(root,request)
            inbox=root/request['return_folder'];raw='CREATE TABLE APP.CUSTOMER (ID CHAR(9));';path='CUSTOMER.sql';(inbox/'files'/path).write_text(raw)
            item={'need_id':request['needs'][0]['need_id'],'status':'FOUND','path':path,'sha256':sha(raw),'provenance':
                  {'origin':'zowe_cli','tool':'zowe files view ds','locator':'APP.DDL(CUSTOMER)','retrieved_at':'2026-10-07T16:00:00Z'}}
            (inbox/'response.json').write_bytes(encode({'request_id':request['request_id'],'items':[item]}))
            self.assertEqual(request['schema_version'],1);self.assertTrue(inspect_response(root,request)['complete'])
