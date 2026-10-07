"""Claude operates on files; Copilot retrieves missing evidence without coding."""
from pathlib import Path
import json
import tempfile
import unittest
from unittest.mock import patch
from workbench.coordinator import Coordinator
from workbench.domain import ValidationError, encode, sha
from test_source import COBOL
from test_workflow import MANIFEST

class LocalAgentFixture(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name);self.c=Coordinator(self.root);self.addCleanup(lambda:self.c.close())

    def create(self,missing=False):
        files={'JOBA.jcl':"//JOBA JOB (TEST),'FICTIONAL'\n//S010 EXEC PGM=ELIGIBLE\n"}
        if not missing:files['ELIGIBLE.cbl']=COBOL
        return self.c.create(MANIFEST,files,assistant_mode='claude_files')

class LocalAgentTests(LocalAgentFixture):
    def test_new_local_mode_never_uses_mainframe_connectors(self):
        self.create()
        with patch('workbench.connectors.ReadOnlyLineageResolver.from_environment',side_effect=AssertionError('network forbidden')),patch('workbench.connectors.read_only_discovery',side_effect=AssertionError('network forbidden')):
            self.c.start('process-a');self.c.advance('process-a')
        view=self.c.local_agent_action('process-a','inspect',{})
        self.assertEqual(view['status'],'WAITING_COPILOT')
        self.assertEqual(view['host_roles']['analysis'],'Claude Code, local files only; no MCP')
        self.assertTrue(Path(view['task_file']).is_file())
        self.assertEqual(self.c.agent_task('process-a')['host_roles']['copilot'],'Retrieve requested evidence only; no development, analysis, testing or review')

    def test_missing_program_produces_copyable_retrieval_prompt_and_known_inbox(self):
        self.create(True);self.c.start('process-a');self.c.advance('process-a')
        view=self.c.local_agent_action('process-a','inspect',{})
        self.assertEqual(view['status'],'WAITING_DISCOVERY')
        self.assertIn('ELIGIBLE',view['retrieval']['copilot_prompt'])
        self.assertIn('response.json',view['retrieval']['copilot_prompt'])
        self.assertFalse(self.c.ledger.get('process-a')['packet_issued'])

    def test_running_service_consumes_local_command_without_second_writer_or_http(self):
        from workbench.local_agent import submit_command
        self.create();self.c.start('process-a');self.c.launch_worker()
        with patch('urllib.request.urlopen',side_effect=AssertionError('No HTTP bridge')):
            result=submit_command(self.root,'process-a','inspect',{},timeout=5)
        self.assertEqual(result['result']['process_id'],'process-a')
        command_id=result['command_id']
        self.assertTrue((self.root/'.migration/agent-results'/f'{command_id}.json').is_file())
        self.assertEqual(submit_command(self.root,'process-a','inspect',{},timeout=5,command_id=command_id),result)
        with self.assertRaises(ValidationError):submit_command(self.root,'process-a','refresh',{},timeout=1,command_id=command_id)

if __name__=='__main__':unittest.main()

class RetrievalLifecycleTests(LocalAgentFixture):
    def response(self, view, found=True, path='ELIGIBLE.cbl', text=COBOL):
        request=view['retrieval']; inbox=self.root/request['return_folder']
        provenance={'origin':'configured_mcp','tool':'read_member','locator':'TEST.SOURCE(ELIGIBLE)','retrieved_at':'2026-10-06T12:00:00Z'}
        items=[]
        for need in request['needs']:
            item={'need_id':need['need_id'],'status':'FOUND' if found else 'NOT_FOUND','provenance':provenance}
            if found:
                dest=inbox/'files'/path;dest.parent.mkdir(parents=True,exist_ok=True);dest.write_text(text,encoding='utf-8')
                item.update(path=path,sha256=sha(text))
            else:item['reason']='Not present in the approved library'
            items.append(item)
        (inbox/'response.json').write_bytes(encode({'request_id':request['request_id'],'items':items}))

    def ready(self, missing=False):
        self.create(missing);self.c.start('process-a');self.c.advance('process-a')
        return self.c.local_agent_action('process-a','inspect',{})

    def test_already_frozen_identical_file_is_valid_retrieval(self):
        self.ready()
        view=self.c.request_retrieval('process-a',[{'kind':'program','name':'ELIGIBLE','reason':'Need origin metadata'}])
        self.response(view)
        self.assertEqual(self.c.local_agent_action('process-a','continue',{})['status'],'WAITING_COPILOT')
        self.assertEqual(self.c.sources(self.c.ledger.get('process-a'))['ELIGIBLE.cbl'],COBOL)

    def test_interrupted_source_freeze_replays_pinned_return(self):
        view=self.ready(True);self.response(view)
        with patch.object(self.c,'freeze_discovered_sources',side_effect=OSError('simulated interrupted import')):
            with self.assertRaises(OSError):self.c.local_agent_action('process-a','continue',{})
        self.assertEqual(self.c.ledger.get('process-a')['retrieval_request']['status'],'IMPORTING')
        # The accepted snapshot is the recovery source, not mutable staging files.
        (self.root/view['retrieval']['return_folder']/'files/ELIGIBLE.cbl').write_text('tampered staging')
        self.c.close();self.c=Coordinator(self.root)
        self.assertEqual(self.c.local_agent_action('process-a','continue',{})['status'],'WAITING_COPILOT')
        self.assertEqual(self.c.sources(self.c.ledger.get('process-a'))['ELIGIBLE.cbl'],COBOL)

    def test_missing_requested_metadata_stays_blocked_without_repeated_prompts(self):
        self.ready()
        view=self.c.request_retrieval('process-a',[{'kind':'control','name':'BUSINESS-METADATA','reason':'Required mapping evidence'}])
        self.response(view,False)
        result=self.c.local_agent_action('process-a','continue',{})
        self.assertEqual(result['status'],'WAITING_DISCOVERY')
        self.assertEqual(result['retrieval_state']['status'],'CONSUMED')
        self.assertTrue(result['retrieval_state']['missing_items'])
        for _ in range(3):self.assertEqual(self.c.local_agent_action('process-a','continue',{})['retrieval'],view['retrieval'])
        self.assertFalse(self.c.ledger.get('process-a')['packet_issued'])
        self.assertTrue(any(b['kind']=='retrieval_unresolved' for b in self.c.ledger.get('process-a')['blockers']))

    def test_pending_retrieval_prevents_analysis_refresh_or_replacement(self):
        self.ready()
        task=self.c.agent_task('process-a')
        from test_copilot_handoff import CopilotHandoffTests
        submitted=CopilotHandoffTests().returned(task)
        self.c.request_retrieval('process-a',[{'kind':'program','name':'MORE','reason':'Missing dependency'}])
        for operation in (lambda:self.c.submit_agent_analysis('process-a',submitted),lambda:self.c.refresh_analysis('process-a'),
                          lambda:self.c.request_retrieval('process-a',[{'kind':'program','name':'OTHER','reason':'different'}])):
            with self.assertRaisesRegex(ValidationError,'retrieval'):operation()
        self.assertFalse(self.c.ledger.get('process-a')['packet_issued'])

    def test_analysis_action_retry_is_idempotent_after_packet(self):
        self.ready();task=self.c.agent_task('process-a')
        from test_copilot_handoff import CopilotHandoffTests
        body={'analysis':CopilotHandoffTests().returned(task)}
        first=self.c.local_agent_action('process-a','analysis',body)
        self.assertEqual(first['status'],'WAITING_SME')
        frozen=self.c.ledger.get('process-a')['packet_hash']
        self.assertEqual(self.c.local_agent_action('process-a','analysis',body)['status'],'WAITING_SME')
        self.assertEqual(self.c.ledger.get('process-a')['packet_hash'],frozen)

    def test_large_dependency_set_yields_bounded_request_and_visible_remaining_count(self):
        files={'JOBA.jcl':"//JOBA JOB (TEST),'FICTIONAL'\n"+''.join(f'//S{i:03d} EXEC PGM=P{i:03d}\n' for i in range(129))}
        self.c.create(MANIFEST,files,assistant_mode='claude_files');self.c.start('process-a');self.c.advance('process-a')
        view=self.c.local_agent_action('process-a','inspect',{})
        self.assertEqual(len(view['retrieval']['needs']),128)
        self.assertEqual(view['retrieval_state']['remaining_need_count'],2)
        self.assertEqual(len(self.c.ledger.get('process-a')['lineage']['closure']['gaps']),130)

    def test_local_task_has_no_mcp_tool_instructions(self):
        self.ready();task=self.c.agent_task('process-a')
        self.assertFalse(any(k.endswith('_tool') for k in task))
        self.assertEqual(task['local_evidence']['source_directory'],'input/sources')

    def test_unrelated_found_file_cannot_clear_manually_requested_copybook(self):
        self.ready()
        view=self.c.request_retrieval('process-a',[{'kind':'copybook','name':'MISSINGREQUIRED','reason':'Required copy layout'}])
        self.response(view)
        returned=self.c.local_agent_action('process-a','continue',{})
        self.assertEqual(returned['status'],'WAITING_DISCOVERY')
        self.assertTrue(self.c.ledger.get('process-a')['retrieval_unresolved'])
        self.assertFalse(self.c.ledger.get('process-a')['packet_issued'])

    def test_workspace_measurement_uses_local_queue_without_process_misattribution(self):
        from test_economics import EconomicsTests
        self.ready()
        receipt=EconomicsTests().work(process_id=None,stage='framework',complete=False,hours=8)
        from workbench.local_agent import submit_command
        self.c.launch_worker()
        response=submit_command(self.root,'process-a','measurement',{'receipt':receipt},timeout=5)
        self.assertEqual(response['status'],'DONE',response)
        self.assertEqual(self.c.economics()['framework']['recorded_detail_hours'],'8')
        self.assertIsNone(self.c.ledger.measurements()[0]['document']['process_id'])

    def test_twenty_randomized_program_returns_resume_from_exact_inbox(self):
        import random,secrets
        seed=secrets.randbits(63);rng=random.Random(seed)
        for index in range(20):
            pid=f'fixture-{index}';name=rng.choice(('I','Z'))+f'{rng.randrange(1000000):06}'
            threshold=rng.randrange(10,90);source=COBOL.replace('ELIGIBLE',name).replace('>= 18',f'>= {threshold}')
            manifest=MANIFEST.replace('process-a',pid).replace('ELIGIBLE',name)
            with self.subTest(seed=seed,program=name,threshold=threshold):
                self.c.create(manifest,{'JOBA.jcl':f"//JOBA JOB (TEST),'FICTIONAL'\n//S010 EXEC PGM={name}\n"},assistant_mode='claude_files')
                self.c.start(pid);self.c.advance(pid);view=self.c.local_agent_action(pid,'inspect',{})
                self.response(view,path=name+'.cbl',text=source)
                resumed=self.c.local_agent_action(pid,'continue',{})
                self.assertEqual(resumed['status'],'WAITING_COPILOT')
                doc=self.c.ledger.get(pid)
                self.assertEqual(self.c.sources(doc)[name+'.cbl'],source)
                self.assertEqual(doc['source_files'][name+'.cbl'],sha(source))
                self.assertEqual(doc['retrieval_unresolved'],{})
                self.assertIn(name,self.c.agent_task(pid)['program_catalog'])
                self.assertFalse(doc['packet_issued'])

    def test_requirements_save_invalidates_previous_retrieval_generation(self):
        self.ready()
        view=self.c.request_retrieval('process-a',[{'kind':'program','name':'ELIGIBLE','reason':'Origin evidence'}])
        self.response(view)
        selection=self.c.requirements_view('process-a')
        self.c.save_requirements('process-a',{'catalog_hash':selection['catalog_hash'],'revision':selection['revision'],'excluded_ids':[],'saved_by':'Fictional test operator'})
        self.assertEqual(self.c.ledger.get('process-a')['retrieval_request']['status'],'STALE')
        self.c.advance('process-a');current=self.c.local_agent_action('process-a','inspect',{})
        self.assertNotEqual(current['retrieval']['request_id'],view['retrieval']['request_id'])
        self.assertEqual(self.c.local_agent_action('process-a','continue',{})['status'],'WAITING_DISCOVERY')
        self.assertFalse(self.c.ledger.get('process-a').get('discovery_provenance'))

    def test_native_cli_uses_existing_writer_and_does_not_import_http_client(self):
        import subprocess,sys
        self.ready();self.c.launch_worker()
        result=subprocess.run([sys.executable,'-m','workbench.runner','agent','process-a','--workspace',str(self.root),'--timeout','5'],capture_output=True,text=True,timeout=15)
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)
        payload=json.loads(result.stdout)
        self.assertEqual(payload['status'],'DONE');self.assertEqual(payload['result']['status'],'WAITING_COPILOT')
        self.assertTrue((self.root/'.migration/agent-results'/f"{payload['command_id']}.json").exists())

    def test_invalid_action_payload_does_not_migrate_existing_process(self):
        self.c.create(MANIFEST,{'ELIGIBLE.cbl':COBOL})
        before=self.c.ledger.get('process-a')
        with self.assertRaises(ValidationError):self.c.local_agent_action('process-a','request',{'unexpected':True})
        self.assertEqual(self.c.ledger.get('process-a'),before)

    def test_invalid_nested_payload_does_not_migrate_legacy_task(self):
        self.c.create(MANIFEST,{'ELIGIBLE.cbl':COBOL,'JOBA.jcl':"//JOBA JOB (TEST),'FICTIONAL'\n//S010 EXEC PGM=ELIGIBLE\n"},assistant_mode='agent')
        self.c.start('process-a');self.c.advance('process-a')
        before=self.c.ledger.get('process-a')
        for action,payload in (('measurement',{'receipt':{}}),('request',{'needs':[{}]}),('analysis',{'analysis':{}})):
            with self.subTest(action=action):
                with self.assertRaises(ValidationError):self.c.local_agent_action('process-a',action,payload)
                self.assertEqual(self.c.ledger.get('process-a'),before)

    def test_requirements_cannot_change_mid_import_recovery(self):
        self.ready();view=self.c.request_retrieval('process-a',[{'kind':'program','name':'ELIGIBLE','reason':'Confirm origin'}]);self.response(view)
        with patch.object(self.c,'freeze_discovered_sources',side_effect=OSError('interrupted')):
            with self.assertRaises(OSError):self.c.continue_retrieval('process-a')
        requirements=self.c.requirements_view('process-a');before=self.c.ledger.get('process-a')
        with self.assertRaisesRegex(ValidationError,'import'):
            self.c.save_requirements('process-a',{'catalog_hash':requirements['catalog_hash'],'revision':requirements['revision'],'excluded_ids':[],'saved_by':'Fictional operator'})
        self.assertEqual(self.c.ledger.get('process-a'),before)

    def test_legacy_handoff_moves_to_local_task_without_deleting_evidence(self):
        self.c.create(MANIFEST,{'ELIGIBLE.cbl':COBOL,'JOBA.jcl':"//JOBA JOB (TEST),'FICTIONAL'\n//S010 EXEC PGM=ELIGIBLE\n"},assistant_mode='agent')
        self.c.start('process-a');self.c.advance('process-a')
        old=self.c.ledger.get('process-a');task=self.c.artifact('process-a',old['copilot_task_artifact']).read_bytes()
        self.c.prepare_development('process-a');handoff=self.c.ledger.get('process-a')['development_handoff']
        result=self.c.local_agent_action('process-a','inspect',{})
        current=self.c.ledger.get('process-a')
        self.assertEqual(result['status'],'WAITING_COPILOT')
        self.assertEqual(current['historical_development_handoff'],handoff)
        self.assertNotIn('development_handoff',current)
        self.assertEqual(self.c.artifact('process-a',old['copilot_task_artifact']).read_bytes(),task)
        self.assertEqual(self.c.agent_task('process-a')['kind'],'LOCAL_FILE_CLAUDE_ANALYSIS_TASK')
        self.assertFalse(current['packet_issued'])


class LocalContextIntegrityTests(LocalAgentFixture):
    def ready_with_context(self):
        inbox = self.root / 'knowledge/inbox'
        inbox.mkdir(parents=True)
        note = inbox / 'fictional-business-context.md'
        note.write_text('# Fictional context\nUser supplied; unverified. Exact timing is unknown.\n', encoding='utf-8')
        self.create()
        self.c.start('process-a')
        self.c.advance('process-a')
        return note, self.root / 'processes/process-a/analysis/process-context.json'

    def test_changed_frozen_context_blocks_local_handoff_without_repinning(self):
        _, path = self.ready_with_context()
        before = self.c.ledger.get('process-a')
        original = path.read_bytes()
        changed = json.loads(original)
        changed['documents'][0]['text'] = changed['documents'][0]['text'].replace('unknown', 'defined')
        changed['documents'][0]['sha256'] = sha(changed['documents'][0]['text'])
        altered = encode(changed)
        self.assertEqual(len(altered), len(original))
        path.write_bytes(altered)
        with self.assertRaisesRegex(ValidationError, 'context'):
            self.c.local_agent_action('process-a', 'inspect', {})
        self.assertEqual(self.c.ledger.get('process-a'), before)
        self.assertEqual(path.read_bytes(), altered)

    def test_missing_context_blocks_continue_before_any_stage_or_snapshot_changes(self):
        _, path = self.ready_with_context()
        before = self.c.ledger.get('process-a')
        path.unlink()
        with self.assertRaisesRegex(ValidationError, 'context'):
            self.c.local_agent_action('process-a', 'continue', {})
        self.assertEqual(self.c.ledger.get('process-a'), before)
        self.assertFalse(path.exists())

    def test_unpinned_context_cannot_refresh_analysis(self):
        _, path = self.ready_with_context()
        doc = self.c.ledger.get('process-a')
        doc['artifact_hashes'].pop('analysis/process-context.json')
        self.c.ledger.save(doc)
        before = self.c.ledger.get('process-a')
        original = path.read_bytes()
        with self.assertRaisesRegex(ValidationError, 'context'):
            self.c.refresh_analysis('process-a')
        self.assertEqual(self.c.ledger.get('process-a'), before)
        self.assertEqual(path.read_bytes(), original)

    def test_local_task_preserves_original_context_when_inbox_article_changes(self):
        note, path = self.ready_with_context()
        frozen = path.read_bytes()
        original_digest = sha(note.read_bytes())
        note.write_text('# Later context\nA later user correction.\n', encoding='utf-8')
        view = self.c.local_agent_action('process-a', 'inspect', {})
        task = self.c.agent_task('process-a')
        self.assertEqual(view['status'], 'WAITING_COPILOT')
        self.assertEqual(task['local_evidence']['context'], 'analysis/process-context.json')
        self.assertEqual(task['context_documents'][0]['sha256'], original_digest)
        self.assertEqual(task['context_documents'][0]['status'], 'UNVERIFIED_INPUT')
        self.assertEqual(path.read_bytes(), frozen)

    def test_historical_process_without_context_has_no_new_context_requirement(self):
        doc = self.create()
        relative = 'analysis/process-context.json'
        doc.pop('process_context')
        doc['artifact_hashes'].pop(relative)
        doc['artifacts'].remove(relative)
        self.c.ledger.save(doc)
        (self.root / 'processes/process-a' / relative).unlink()
        self.c.start('process-a')
        self.c.advance('process-a')
        view = self.c.local_agent_action('process-a', 'inspect', {})
        self.assertEqual(view['status'], 'WAITING_COPILOT')
        self.assertIsNone(self.c.agent_task('process-a')['local_evidence']['context'])

    def test_missing_ledger_context_cannot_downgrade_a_registered_snapshot_to_legacy(self):
        _, path = self.ready_with_context()
        doc = self.c.ledger.get('process-a')
        doc.pop('process_context')
        self.c.ledger.save(doc)
        before = self.c.ledger.get('process-a')
        original = path.read_bytes()
        with self.assertRaisesRegex(ValidationError, 'context'):
            self.c.agent_task('process-a')
        self.assertEqual(self.c.ledger.get('process-a'), before)
        self.assertEqual(path.read_bytes(), original)
