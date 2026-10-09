"""Claude retrieves approved evidence and operates through one Coordinator."""
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
    def test_opaque_identities_resolve_privately_and_actual_target_comparison_still_runs(self):
        from copy import deepcopy
        from test_copilot_handoff import CopilotHandoffTests
        from workbench.copilot import opaque_reference
        from workbench.fixtures import plan_cases,verify_program
        from workbench.target import emit_program
        marker='123-45-6789';path='sources/'+marker+'.cbl'
        files={'JOBA.jcl':'//JOBA JOB\n//S010 EXEC PGM=ELIGIBLE\n',path:COBOL,
               'controls/'+marker+'.ctl':'* fictional unrelated export\n'}
        self.c.create(MANIFEST,files,assistant_mode='claude_files');self.c.start('process-a');self.c.advance('process-a')
        task=self.c.agent_task('process-a');guide=self.c.save_process_guide('process-a')
        self.assertNotIn(marker,encode(task).decode()+Path(guide['markdown']['path']).read_text())
        self.assertEqual(set(task['lineage']['sources']),{opaque_reference('SOURCE',p) for p in files})
        self.assertIn('SOURCE_<hash>',task['return_contract']['source_ref']['path'])
        submitted=CopilotHandoffTests().returned(task)
        submitted['source_refs']=[{key:value for key,value in next(ref for ref in task['source_excerpts']
            if ref['path']==opaque_reference('SOURCE',path)).items() if key!='text'}]
        actual_rule=self.c.ledger.get('process-a')['analysis']['rules'][0]['id']
        submitted['rule_classification_defaults']={opaque_reference('PROGRAM','ELIGIBLE'):{'category':'technical_logic','reason':'Fictional explicitly reviewed classification'}}
        submitted['rule_classifications']={opaque_reference('RULE',actual_rule):{'category':'unclassified','reason':'Business meaning remains unverified'}}
        for key,value in [('path',path),('path','SOURCE_'+'0'*64),('source_hash','0'*64),('end_line',999999)]:
            with self.subTest(key=key,value=value):
                invalid=deepcopy(submitted);invalid['source_refs'][0][key]=value
                before=self.c.ledger.get('process-a')
                with self.assertRaises(ValidationError):self.c.submit_agent_analysis('process-a',invalid)
                self.assertEqual(self.c.ledger.get('process-a'),before)
        self.c.submit_agent_analysis('process-a',submitted)
        doc=self.c.ledger.get('process-a');accepted=doc['llm']
        self.assertEqual(accepted['source_refs'][0]['path'],path)
        self.assertIn('ELIGIBLE',accepted['analysis']['rule_classification_defaults'])
        self.assertIn(actual_rule,accepted['analysis']['rule_classifications'])
        self.assertEqual(self.c.sources(doc),files)
        program=doc['analysis']['programs']['ELIGIBLE'];program={**program,'target_contract_version':2}
        suite=plan_cases(program,472019,budget=4096,min_records_per_logic=64,fixture_contract_version=5)
        comparison=verify_program(program,emit_program(program),suite)
        self.assertEqual(comparison['differences'],[]);self.assertGreater(comparison['matched_count'],64)
        self.assertFalse(comparison['observed_legacy_parity'])

    def test_saved_private_requirements_are_consumed_locally_and_never_advertised_to_claude(self):
        marker='123-45-6789';source=COBOL.replace('DECISION PIC X.','DECISION PIC X(11).').replace('MOVE "Y"','MOVE "'+marker+'"')
        self.c.prepare_process(MANIFEST,{'JOBA.jcl':'//JOBA JOB\n//S010 EXEC PGM=ELIGIBLE\n','ELIGIBLE.cbl':source})
        self.c.start('process-a');self.c.advance('process-a');scope=self.c.requirements_view('process-a')
        self.c.save_requirements('process-a',{'catalog_hash':scope['catalog_hash'],'revision':scope['revision'],
            'excluded_ids':[],'saved_by':'Fictional synthetic operator'})
        self.c.advance('process-a');doc=self.c.ledger.get('process-a')
        canonical=self.c.artifact('process-a',doc['requirements_artifact']).read_bytes()
        self.assertIn(marker,canonical.decode())
        task=self.c.agent_task('process-a');view=self.c.local_agent_view('process-a');guide=self.c.save_process_guide('process-a')
        self.assertIsNone(view['requirements_file']);self.assertNotIn('path',task['requirements'])
        self.assertFalse(task['requirements']['private_contents_allowed'])
        self.assertEqual(task['requirements']['sha256'],sha(canonical))
        serialized=encode(task).decode()+encode(view).decode()+Path(guide['markdown']['path']).read_text()+guide['handoffs']['claude']['prompt']
        self.assertNotIn(marker,serialized);self.assertNotIn(doc['requirements_artifact'],guide['handoffs']['claude']['prompt'])
        self.assertEqual(self.c.artifact('process-a',doc['requirements_artifact']).read_bytes(),canonical)

    def test_old_metadata_task_without_opaque_identity_contract_stays_frozen_until_refresh(self):
        from workbench.copilot import build_task
        from workbench.layout import output_path
        from workbench.domain import write_new
        self.create();self.c.start('process-a');self.c.advance('process-a')
        doc=self.c.ledger.get('process-a');legacy_doc={**doc,'agent_transport':'historical'}
        old=build_task(legacy_doc,self.c.sources(doc),doc['analysis'])
        old['data_policy']={'version':1,'mode':'METADATA_AND_HASH_REFERENCES_ONLY'}
        old['task_hash']=sha(encode({k:v for k,v in old.items() if k!='task_hash'}))
        raw=encode(old);relative='analysis/copilot-task-'+sha(raw)+'.json'
        write_new(output_path(self.root,'process-a',relative),raw);self.c.register(doc,relative)
        doc['copilot_task_artifact']=relative;self.c.ledger.save(doc)
        view=self.c.local_agent_view('process-a');guide=self.c.save_process_guide('process-a')
        self.assertIsNone(view['task_file']);self.assertTrue(view['historical_private_task_blocked'])
        self.assertIsNone(guide['handoffs']['claude']);self.assertEqual(guide['next_action']['action'],'refresh')
        self.c.local_agent_action('process-a','refresh',{})
        self.assertEqual(self.c.agent_task('process-a')['data_policy']['source_identity_mode'],'OPAQUE_HASH_REFERENCES')
        self.assertEqual(self.c.artifact('process-a',relative).read_bytes(),raw)

    def test_agent_api_never_returns_private_rules_obligations_context_or_raw_source(self):
        from workbench.api import create_app
        from fastapi.testclient import TestClient
        marker='123-45-6789';inbox=self.root/'knowledge/inbox';inbox.mkdir(parents=True)
        (inbox/'private-notes.md').write_text('# Context\n'+marker+'\n')
        source=COBOL.replace('MOVE "Y"','MOVE "'+marker+'"').replace('GOBACK.',"DISPLAY '"+marker+"'.\nGOBACK.")
        self.c.create(MANIFEST,{'JOBA.jcl':'//JOBA JOB\n//S010 EXEC PGM=ELIGIBLE\n','ELIGIBLE.cbl':source},assistant_mode='claude_files')
        self.c.start('process-a');self.c.advance('process-a');self.c.close()
        app=create_app(self.root);client=TestClient(app,base_url='http://127.0.0.1:8765')
        try:
            for suffix in ('agent/task','agent/lineage','agent/rules','agent/obligations','agent/context?document_id=NOTE_1&start_line=1&end_line=2'):
                response=client.get('/api/process/process-a/'+suffix)
                self.assertEqual(response.status_code,200,(suffix,response.text));self.assertNotIn(marker,response.text)
            response=client.get('/api/process/process-a/agent/source?path=ELIGIBLE.cbl')
            self.assertEqual(response.status_code,400);self.assertNotIn(marker,response.text)
        finally:client.close();app.state.coordinator.close()
        self.c=Coordinator(self.root)

    def test_cli_errors_expose_only_fixed_categories_and_digests(self):
        from workbench.runner import _model_error
        marker='123-45-6789 private@example.invalid'
        result=_model_error(ValidationError('source retrieval '+marker))
        self.assertNotIn(marker,json.dumps(result));self.assertNotIn('private@example.invalid',json.dumps(result))
        self.assertIn('retrieval',result['error']);self.assertIn('source',result['error'])
        self.assertEqual(result['error_sha256'],sha('source retrieval '+marker))

    def test_historical_task_with_private_context_is_not_advertised_after_human_packet(self):
        from test_copilot_handoff import CopilotHandoffTests
        marker='123-45-6789'
        source=COBOL.replace('PROCEDURE DIVISION USING INPUT-RECORD.',
                            '*> '+marker+'\nPROCEDURE DIVISION USING INPUT-RECORD.')
        self.c.create(MANIFEST,{'JOBA.jcl':'//JOBA JOB\n//S010 EXEC PGM=ELIGIBLE\n','ELIGIBLE.cbl':source},assistant_mode='copilot_chat')
        self.c.start('process-a');self.c.advance('process-a')
        task=self.c.agent_task('process-a');self.assertIn(marker,encode(task).decode())
        guide=self.c.save_process_guide('process-a')
        self.assertTrue(guide['historical_private_task_blocked']);self.assertIsNone(guide['handoffs']['claude'])
        self.assertEqual(guide['next_action']['action'],'refresh')
        self.c.submit_agent_analysis('process-a',CopilotHandoffTests().returned(task));self.c.advance('process-a')
        doc=self.c.ledger.get('process-a');self.assertTrue(doc['packet_issued'])
        relative=doc['copilot_task_artifact'];original=self.c.artifact('process-a',relative).read_bytes()
        view=self.c.local_agent_action('process-a','inspect',{})
        self.assertIsNone(view['task_file']);self.assertTrue(view['historical_private_task_blocked'])
        self.assertEqual(self.c.artifact('process-a',relative).read_bytes(),original)
        self.assertEqual(self.c.ledger.get('process-a'),doc)

    def test_private_missing_receipt_reason_is_local_and_does_not_reissue_or_leak(self):
        self.create(True);self.c.start('process-a');self.c.advance('process-a')
        view=self.c.local_agent_action('process-a','inspect',{})
        request=view['retrieval'];folder=self.root/request['return_folder'];marker='123-45-6789'
        provenance={'origin':'zowe_cli','tool':'zowe files download data-set','locator':'APP.COBOL(ELIGIBLE)',
                    'retrieved_at':'2026-10-08T00:00:00Z'}
        response={'request_id':request['request_id'],'items':[{'need_id':need['need_id'],'status':'NOT_FOUND',
                  'reason':marker,'provenance':provenance} for need in request['needs']]}
        (folder/'response.json').write_bytes(encode(response))
        result=self.c.local_agent_action('process-a','continue',{})
        self.assertNotIn(marker,json.dumps(result));self.assertEqual(result['retrieval_state']['missing_item_count'],len(request['needs']))
        self.assertIn(marker,json.dumps(self.c.ledger.get('process-a')['retrieval_request']))
        state=self.c.ledger.get('process-a')
        for _ in range(3):
            repeat=self.c.local_agent_action('process-a','continue',{})
            self.assertNotIn(marker,json.dumps(repeat));self.assertEqual(repeat['retrieval']['request_id'],request['request_id'])
        self.assertEqual(self.c.ledger.get('process-a'),state)

    def test_private_dynamic_lookup_and_unsupported_display_stay_out_of_model_views(self):
        from workbench.runner import summary
        markers=('123-45-6789','private@example.invalid')
        for index,operand in enumerate(markers):
            for statement in ("EXEC CICS LINK PROGRAM('"+operand+"') END-EXEC.","DISPLAY '"+operand+"'."):
                with self.subTest(statement=statement):
                    pid='private-'+str(index)+'-'+('link' if statement.startswith('EXEC') else 'display')
                    manifest=MANIFEST.replace('process-a',pid)
                    source=COBOL.replace('PROCEDURE DIVISION USING INPUT-RECORD.',
                                        'PROCEDURE DIVISION USING INPUT-RECORD.\n    '+statement)
                    self.c.create(manifest,{'JOBA.jcl':'//JOBA JOB\n//S010 EXEC PGM=ELIGIBLE\n','ELIGIBLE.cbl':source},assistant_mode='claude_files')
                    self.c.start(pid);self.c.advance(pid)
                    doc=self.c.ledger.get(pid)
                    view=self.c.local_agent_action(pid,'inspect',{})
                    before=encode(self.c.ledger.get(pid))
                    self.assertNotIn(operand.upper(),json.dumps(view).upper());self.assertNotIn(operand.upper(),json.dumps(summary(self.c,doc)).upper())
                    self.assertEqual(self.c.sources(doc)['ELIGIBLE.cbl'],source)
                    if statement.startswith('EXEC'):
                        self.assertIn(operand.upper(),json.dumps(doc['lineage']['closure']['gaps']).upper())
                        self.assertTrue(view['retrieval']['needs']);self.assertFalse(doc['lineage']['closure']['complete'])
                        if operand==markers[0]:
                            self.assertTrue(any(need.get('status')=='dynamic_unknown' for need in view['retrieval']['needs']))
                    self.assertEqual(encode(self.c.ledger.get(pid)),before)

    def test_claude_task_guide_and_prompt_withhold_private_source_comments_literals_and_context(self):
        ssn='123-45-6789';email='private@example.invalid'
        source=COBOL.replace('PROCEDURE DIVISION USING INPUT-RECORD.',
                            '*> '+ssn+' '+email+'\nPROCEDURE DIVISION USING INPUT-RECORD.').replace('MOVE "Y"','MOVE "'+email+'"')
        files={'JOBA.jcl':"//JOBA JOB (TEST),'FICTIONAL'\n//S010 EXEC PGM=ELIGIBLE\n",'ELIGIBLE.cbl':source}
        self.c.create(MANIFEST,files,assistant_mode='claude_files',prompt=ssn+' '+email)
        self.c.start('process-a');self.c.advance('process-a')
        task=self.c.agent_task('process-a');guide=self.c.save_process_guide('process-a')
        serialized=encode(task).decode()+encode(guide).decode()+Path(guide['markdown']['path']).read_text()
        self.assertNotIn(ssn,serialized);self.assertNotIn(email,serialized)
        self.assertEqual(task['context_character_count'],0);self.assertFalse(task['context_complete'])
        self.assertFalse(task['data_policy']['source_text_allowed']);self.assertFalse(task['data_policy']['business_records_allowed'])
        self.assertTrue(all('text' not in excerpt for excerpt in task['source_excerpts']))
        self.assertEqual(self.c.sources(self.c.ledger.get('process-a')),files)
        from workbench.copilot import source_excerpt
        with self.assertRaisesRegex(ValidationError,'approved sanitized view'):
            source_excerpt(self.c.ledger.get('process-a'),files,'ELIGIBLE.cbl',1,2)

    def test_initial_source_directory_aliases_are_rejected_before_storage(self):
        for first,second in [('LIB/ELIGIBLE.cbl','lib/OTHER.cpy'),
                             ('caf\u00e9/ELIGIBLE.cbl','cafe\u0301/OTHER.cpy'),
                             ('JOBA.jcl','joba.JCL/ELIGIBLE.cbl')]:
            with self.subTest(paths=(first,second)):
                with self.assertRaisesRegex(ValidationError,'colli'):
                    self.c.create(MANIFEST,{first:COBOL,second:'01 OTHER PIC X.\n'},assistant_mode='claude_files')
                self.assertEqual(self.c.ledger.list(True),[])
                self.assertFalse(self.c.process_root('process-a').exists())

    def test_initial_shared_directory_preserves_each_original_source_path(self):
        files={'LIB/ELIGIBLE.cbl':COBOL,'LIB/OTHER.cpy':'01 OTHER PIC X.\n'}
        doc=self.c.create(MANIFEST,files,assistant_mode='claude_files')
        self.assertEqual(self.c.sources(doc),files)

    def test_new_local_mode_never_uses_mainframe_connectors(self):
        self.create()
        with patch('workbench.connectors.ReadOnlyLineageResolver.from_environment',side_effect=AssertionError('network forbidden')),patch('workbench.connectors.read_only_discovery',side_effect=AssertionError('network forbidden')):
            self.c.start('process-a');self.c.advance('process-a')
        view=self.c.local_agent_action('process-a','inspect',{})
        self.assertEqual(view['status'],'WAITING_COPILOT')
        self.assertEqual(view['host_roles']['analysis'],'Claude Code, accepted local evidence, development, testing and review')
        self.assertTrue(Path(view['task_file']).is_file())
        self.assertIn('approved Db2 MCP',self.c.agent_task('process-a')['host_roles']['retrieval'])

    def test_missing_program_produces_copyable_retrieval_prompt_and_known_inbox(self):
        self.create(True);self.c.start('process-a');self.c.advance('process-a')
        view=self.c.local_agent_action('process-a','inspect',{})
        self.assertEqual(view['status'],'WAITING_DISCOVERY')
        self.assertNotIn('ELIGIBLE',view['retrieval']['agent_prompt'])
        self.assertEqual(view['retrieval']['metadata_identity_gate'],'UNAPPROVED_MODEL_METADATA')
        self.assertIn('response.json',view['retrieval']['agent_prompt'])
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
        provenance={'origin':'zowe_cli','tool':'zowe files view ds','locator':'TEST.SOURCE(ELIGIBLE)','retrieved_at':'2026-10-06T12:00:00Z'}
        items=[]
        for need in request['needs']:
            item={'need_id':need['need_id'],'status':'FOUND' if found else 'NOT_FOUND','provenance':provenance}
            if found:
                dest=inbox/'files'/path;dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes(text.encode('utf-8'))
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

    def test_colliding_return_is_rejected_before_acceptance_and_remains_correctable(self):
        view=self.ready(True);before=self.c.ledger.get('process-a')
        original=self.c.sources(before)
        self.response(view,path='JOBA.jcl/ELIGIBLE.cbl')
        with self.assertRaisesRegex(ValidationError,'colli'):
            self.c.continue_retrieval('process-a')
        self.assertEqual(self.c.ledger.get('process-a'),before)
        self.assertEqual(self.c.sources(before),original)
        self.assertFalse(list((self.c.process_root('process-a')/'analysis').glob('discovery-*.json')))
        self.assertFalse(list((self.root/view['retrieval']['return_folder']).parent.glob('accepted-*.json')))
        # Only the mutable rejected return is corrected; source evidence is intact.
        (self.root/view['retrieval']['return_folder']/'files/JOBA.jcl/ELIGIBLE.cbl').unlink()
        self.response(view)
        self.assertEqual(self.c.continue_retrieval('process-a')['status'],'WAITING_COPILOT')
        self.assertEqual(self.c.sources(self.c.ledger.get('process-a'))['JOBA.jcl'],original['JOBA.jcl'])

    def test_merged_source_bounds_are_checked_before_accepted_receipt(self):
        view=self.ready(True);before=self.c.ledger.get('process-a');self.response(view)
        with patch('workbench.coordinator.MAX_SOURCE_FILES',1):
            with self.assertRaisesRegex(ValidationError,'source bounds'):
                self.c.continue_retrieval('process-a')
        self.assertEqual(self.c.ledger.get('process-a'),before)
        self.assertFalse(list((self.root/view['retrieval']['return_folder']).parent.glob('accepted-*.json')))

    def test_historical_pinned_collision_preserves_receipt_journal_and_originals(self):
        view=self.ready(True);self.response(view,path='JOBA.jcl/ELIGIBLE.cbl')
        # Simulate the former validators only to create its fictional interrupted
        # ledger state. Production recovery must use the preserved pinned bytes.
        with patch('workbench.retrieval.validate_source_paths'),patch.object(self.c,'_validate_discovered_sources'):
            with self.assertRaises(FileExistsError):self.c.continue_retrieval('process-a')
        before=self.c.ledger.get('process-a')
        pinned=[before['retrieval_request']['response_artifact'],before['pending_discovery']['artifact']]
        snapshots={p:(self.c.process_root('process-a')/p).read_bytes() for p in pinned}
        original=(self.c.process_root('process-a')/'input/sources/JOBA.jcl').read_bytes()
        self.c.close();self.c=Coordinator(self.root)
        with self.assertRaisesRegex(ValidationError,'Pinned discovery.*colli'):
            self.c.local_agent_action('process-a','continue',{})
        self.assertEqual(self.c.ledger.get('process-a'),before)
        self.assertEqual({p:(self.c.process_root('process-a')/p).read_bytes() for p in pinned},snapshots)
        self.assertEqual((self.c.process_root('process-a')/'input/sources/JOBA.jcl').read_bytes(),original)

    def test_direct_discovery_rejects_entire_colliding_batch_before_journal(self):
        self.ready(True);before=self.c.ledger.get('process-a')
        paths=['valid/EXTRA.cpy','JOBA.jcl/ELIGIBLE.cbl']
        entries=[{'path':p,'text':COBOL,'source_hash':sha(COBOL),'provenance':{'origin':'synthetic_fixture'}} for p in paths]
        with self.assertRaisesRegex(ValidationError,'colli'):
            self.c.freeze_discovered_sources(before,entries)
        self.assertEqual(self.c.ledger.get('process-a'),before)
        self.assertFalse(list((self.c.process_root('process-a')/'analysis').glob('discovery-*.json')))
        self.assertFalse((self.c.process_root('process-a')/'input/sources/valid').exists())

    def test_missing_requested_metadata_stays_blocked_without_repeated_prompts(self):
        self.ready()
        view=self.c.request_retrieval('process-a',[{'kind':'control','name':'BUSINESS-METADATA','reason':'Required mapping evidence'}])
        self.response(view,False)
        result=self.c.local_agent_action('process-a','continue',{})
        self.assertEqual(result['status'],'WAITING_DISCOVERY')
        self.assertEqual(result['retrieval_state']['status'],'CONSUMED')
        self.assertGreater(result['retrieval_state']['missing_item_count'],0)
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
                from workbench.copilot import opaque_reference
                self.assertIn(opaque_reference('PROGRAM',name),self.c.agent_task(pid)['program_catalog'])
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
