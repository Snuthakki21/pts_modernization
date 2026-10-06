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
