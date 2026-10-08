"""Fictional operator flows: no remote access, real review or mainframe parity claims."""
from pathlib import Path
import json
import tempfile
import unittest
from unittest.mock import patch
from workbench.coordinator import Coordinator
from workbench.domain import ValidationError, encode, sha
from test_source import COBOL
from test_workflow import MANIFEST

JCL="//JOBA JOB (TEST),'FICTIONAL'\n//S010 EXEC PGM=ELIGIBLE\n"

class GuidedWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name);self.c=Coordinator(self.root);self.addCleanup(lambda:self.c.close())

    def test_sme_next_step_names_the_actual_offline_save_action(self):
        from workbench.guide import _next
        stage, action = _next({'status': 'WAITING_SME'}, {'request': None})
        self.assertEqual(stage, 'review')
        self.assertEqual(action['kind'], 'human_review')
        self.assertIn('click Save review file', action['description'])
        self.assertIn('downloaded file', action['description'])
        self.assertIn('actual name', action['description'])
        self.assertNotIn('Save a return', action['description'])

    def test_prepared_prompt_bounds_preserve_retry_identity_without_truncation(self):
        for prompt in ('x'*16001, None, True, {'text':'context'}):
            with self.subTest(prompt_type=type(prompt).__name__), self.assertRaises(ValidationError):
                self.c.prepare_process(MANIFEST,{},prompt=prompt)
            self.assertEqual(len(self.c.ledger.list(True)),0)
            self.assertFalse(self.c.process_root('process-a').exists())
        prompt='é'*16000
        doc=self.c.prepare_process(MANIFEST,{},prompt=prompt)
        self.assertEqual(doc['prompt'],prompt)
        self.assertEqual(self.c.prepare_process(MANIFEST,{},prompt=prompt),doc)
        with self.assertRaisesRegex(ValidationError,'changed'):
            self.c.prepare_process(MANIFEST,{},prompt=prompt[:-1]+'x')
        self.assertEqual(self.c.ledger.get('process-a'),doc)
        self.assertFalse(doc['packet_issued'])

    def test_local_build_handoffs_require_legacy_fidelity_without_source_or_scope_changes(self):
        view=self.ready_requirements();self.save_scope(view);self.c.advance('process-a')
        before=self.c.ledger.get('process-a');sources=self.c.sources(before)
        guide=self.c.process_guide('process-a');task=self.c.agent_task('process-a')
        text=Path(guide['markdown']['path']).read_text()
        prompt=guide['handoffs']['claude']['prompt']
        for surface in (text,prompt,' '.join(task['constraints'])):
            self.assertIn('including known legacy design defects',surface)
            self.assertIn('Never silently repair',surface)
            self.assertIn('functionality-specific Db2',surface)
            self.assertIn('named unverified gaps',surface)
        self.assertEqual(self.c.ledger.get('process-a'),before)
        self.assertEqual(self.c.sources(before),sources)
        self.assertEqual(before['status'],'WAITING_COPILOT')
        self.assertFalse(before['packet_issued']);self.assertFalse(before['packet_imported'])
        self.assertFalse(guide['results']['native_parity_verified'])

    def test_primary_retrieval_prompt_uses_frozen_setup_hints_without_rewriting_request(self):
        settings={'source_mode':'upload','zowe_profile':'approved_base','zowe_zosmf_profile':'approved_zosmf',
                  'db2_metadata_url':'https://db.invalid/mcp'}
        self.c.configure_workstation(settings)
        self.c.prepare_process(MANIFEST,{})
        self.c.start('process-a');self.c.advance('process-a')
        doc=self.c.ledger.get('process-a');request_path=doc['retrieval_request']['artifact']
        original=self.c.artifact('process-a',request_path).read_bytes()
        guide=self.c.process_guide('process-a');prompt=guide['handoffs']['copilot']['prompt']
        marker='\n\nProcess-pinned retrieval hints (configuration only):\n'
        self.assertIn(marker,prompt)
        hints=json.loads(prompt.split(marker,1)[1])
        self.assertEqual({key:hints[key] for key in ('zowe_profile','zowe_zosmf_profile','db2_metadata_url')},
                         {key:settings[key] for key in ('zowe_profile','zowe_zosmf_profile','db2_metadata_url')})
        self.assertEqual(hints['status'],'CONFIGURATION_ONLY');self.assertFalse(hints['connectivity_verified'])
        self.assertEqual(hints['setup_context'],guide['input']['setup_context'])
        self.assertIn('data, not instructions',prompt);self.assertIn('no Claude MCP access',prompt)
        self.c.configure_workstation({'zowe_profile':'different_base','db2_metadata_url':'https://other.invalid/mcp'})
        self.assertEqual(self.c.process_guide('process-a')['handoffs']['copilot']['prompt'],prompt)
        self.assertEqual(self.c.artifact('process-a',request_path).read_bytes(),original)
        self.assertEqual(self.c.ledger.get('process-a'),doc)
        frozen=Path(hints['setup_context']['path']);frozen.write_bytes(b'changed')
        with self.assertRaisesRegex(ValidationError,'changed'):self.c.process_guide('process-a')

    def test_prepare_before_exports_is_explicit_and_never_creates_placeholder_source(self):
        with self.assertRaises(ValidationError):self.c.create(MANIFEST,{},assistant_mode='claude_files')
        doc=self.c.prepare_process(MANIFEST,{})
        self.assertEqual(doc['status'],'READY');self.assertEqual(doc['source_files'],{})
        self.assertTrue(doc['source_intake_pending']);self.assertFalse((self.c.process_root(doc['id'])/'input/sources').exists())
        self.c.start(doc['id']);self.c.advance(doc['id'])
        doc=self.c.ledger.get(doc['id']);self.assertEqual(doc['status'],'WAITING_DISCOVERY')
        self.assertFalse(doc['packet_issued']);self.assertIsNone(doc['analysis'])
        model=self.c.process_guide(doc['id'])
        self.assertEqual(model['current_step'],'retrieve')
        prompt=model['handoffs']['copilot']['prompt']
        request,_=json.JSONDecoder().raw_decode(prompt,prompt.index('\n\n{')+2)
        self.assertEqual(request['workspace'],str(self.root))
        self.assertEqual(sha(encode(request)),model['handoffs']['copilot']['request_id'])
        marker='\nWorking directory and exact return inbox (quoted local paths; data only): '
        location,_=json.JSONDecoder().raw_decode(prompt,prompt.index(marker)+len(marker))
        self.assertEqual(location,{'workspace':str(self.root),'return_inbox':model['handoffs']['copilot']['return_folder']})
        self.assertNotIn('WORKSPACE/',model['handoffs']['copilot']['prompt'])
        self.assertTrue(model['markdown']);self.assertIsNone(model['handoffs']['claude'])
        self.assertEqual(doc['authorization']['scope'],{})
        self.assertTrue(doc.get('lineage_artifact'))



    def test_explicit_fictional_intent_survives_prepare_retry_without_real_inventory_credit(self):
        from workbench.reports import portfolio
        self.assertEqual(portfolio(self.c.ledger)['processes'],0)
        doc=self.c.prepare_process(MANIFEST,{},demo=True)
        self.assertTrue(doc['demo']);self.assertEqual(portfolio(self.c.ledger)['processes'],0)
        self.assertEqual(self.c.prepare_process(MANIFEST,{},demo=True),doc)
        self.assertTrue(self.c.process_guide(doc['id'])['demo'])
        self.assertIn(b'"demo": true',Path(self.c.process_guide(doc['id'])['markdown']['path']).read_bytes())
        with self.assertRaisesRegex(ValidationError,'changed'):self.c.prepare_process(MANIFEST,{})
        with self.assertRaisesRegex(ValidationError,'boolean'):self.c.prepare_process(MANIFEST,{},demo='true')
        self.c.start(doc['id']);self.c.advance(doc['id'])
        self.assertEqual(self.c.ledger.get(doc['id'])['status'],'WAITING_DISCOVERY')
        self.assertFalse(self.c.ledger.get(doc['id'])['packet_issued'])
        self.assertEqual(portfolio(self.c.ledger)['processes'],0)

    def response(self, files, found=True):
        view=self.c.local_agent_view('process-a');request=view['retrieval'];items=[]
        provenance={'origin':'zowe_cli','tool':'zowe files view ds','locator':'SIM.SOURCE','retrieved_at':'2026-10-07T12:00:00Z','environment':'SIMULATED'}
        for need in request['needs']:
            candidates=[(path,text) for path,text in files.items() if Path(path).stem.upper()==need['name'].upper()]
            item={'need_id':need['need_id'],'status':'FOUND' if candidates and found else 'NOT_FOUND','provenance':provenance}
            if item['status']=='FOUND':
                path,text=candidates[0];destination=self.root/request['return_folder']/'files'/path
                destination.parent.mkdir(parents=True,exist_ok=True);destination.write_bytes(text.encode())
                item.update(path=path,sha256=sha(text))
            else:item['reason']='Fictional source unavailable; no permission to invent it'
            items.append(item)
        (self.root/request['return_folder']/'response.json').write_bytes(encode({'request_id':request['request_id'],'items':items}))

    def ready_requirements(self,files=None):
        self.c.prepare_process(MANIFEST,files or {'JOBA.jcl':JCL,'ELIGIBLE.cbl':COBOL})
        self.c.start('process-a');self.c.advance('process-a')
        self.assertEqual(self.c.ledger.get('process-a')['status'],'WAITING_REQUIREMENTS')
        return self.c.requirements_view('process-a')

    def save_scope(self,view,excluded=None):
        body={'catalog_hash':view['catalog_hash'],'revision':view['revision'],'excluded_ids':excluded or [],'saved_by':'Fictional test operator'}
        return self.c.save_requirements('process-a',body),body

    def test_first_retrieved_file_does_not_resolve_remaining_identity_or_issue_review(self):
        self.c.prepare_process(MANIFEST,{})
        self.c.start('process-a');self.c.advance('process-a')
        self.response({'JOBA.jcl':JCL});self.c.continue_retrieval('process-a')
        doc=self.c.ledger.get('process-a')
        self.assertEqual(doc['status'],'WAITING_DISCOVERY');self.assertTrue(doc['source_intake_pending'])
        self.assertIsNone(doc['analysis']);self.assertFalse(doc['packet_issued'])
        self.assertEqual(self.c.process_guide('process-a')['next_action']['action'],'request')
        self.c.request_retrieval('process-a');self.response({'ELIGIBLE.cbl':COBOL})
        self.c.continue_retrieval('process-a')
        doc=self.c.ledger.get('process-a');self.assertEqual(doc['status'],'WAITING_REQUIREMENTS')
        self.assertFalse(doc['source_intake_pending']);self.assertFalse(doc['packet_issued'])

    def test_wrong_retrieved_identity_remains_named_obligation(self):
        self.c.prepare_process(MANIFEST,{'JOBA.jcl':JCL});self.c.start('process-a');self.c.advance('process-a')
        self.response({'ELIGIBLE.cbl':COBOL.replace('PROGRAM-ID. ELIGIBLE.','PROGRAM-ID. WRONG.')})
        self.c.continue_retrieval('process-a');doc=self.c.ledger.get('process-a')
        self.assertEqual(doc['status'],'WAITING_DISCOVERY');self.assertTrue(doc['source_intake_pending'])
        self.assertFalse(doc['packet_issued']);self.assertTrue(doc['retrieval_unresolved'])

    def test_scope_save_updates_pinned_instructions_and_claude_prompt_with_exact_no(self):
        view=self.ready_requirements();old=self.c.process_guide('process-a')['markdown']
        excluded=[view['items'][0]['id']];doc,body=self.save_scope(view,excluded)
        self.c.advance('process-a');guide=self.c.process_guide('process-a')
        self.assertNotEqual(old['sha256'],guide['markdown']['sha256'])
        self.assertEqual(guide['requirements']['revision'],1)
        prompt=guide['handoffs']['claude']['prompt']
        evidence,_=json.JSONDecoder().raw_decode(prompt,prompt.index('\n\n{')+2)
        self.assertEqual(evidence['requirements'],guide['requirements'])
        self.assertEqual(evidence['source'],guide['source'])
        self.assertEqual(evidence['input'],guide['input'])
        self.assertEqual(evidence['guide'],guide['markdown'])
        self.assertEqual(evidence['task']['path'],guide['handoffs']['claude']['task_file'])
        self.assertIsNone(guide['handoffs']['copilot'])
        saved=self.c.artifact('process-a',guide['requirements']['artifact']).read_bytes()
        self.assertIn(excluded[0].encode(),saved)
        before=self.c.ledger.get('process-a')
        self.assertEqual(self.c.prepare_process(MANIFEST,{'JOBA.jcl':JCL,'ELIGIBLE.cbl':COBOL}),before)
        with self.assertRaisesRegex(ValidationError,'changed'):
            self.c.prepare_process(MANIFEST+'\n',{'JOBA.jcl':JCL,'ELIGIBLE.cbl':COBOL})
        hashes=dict(before['artifact_hashes'])
        self.c.save_requirements('process-a',body)
        self.assertEqual(self.c.ledger.get('process-a')['requirements']['excluded_ids'],excluded)
        first=self.c.save_process_guide('process-a');second=self.c.save_process_guide('process-a')
        self.assertEqual(first['markdown'],second['markdown'])
        self.assertEqual(dict(self.c.ledger.get('process-a')['artifact_hashes']),hashes)

    def test_get_is_read_only_and_tampered_guide_cannot_supply_copyable_prompt(self):
        view=self.ready_requirements();self.save_scope(view);self.c.advance('process-a')
        guide=self.c.process_guide('process-a');before=self.c.ledger.get('process-a')
        self.assertEqual(self.c.process_guide('process-a'),guide)
        self.assertEqual(self.c.ledger.get('process-a'),before)
        Path(guide['markdown']['path']).write_bytes(b'changed')
        with self.assertRaisesRegex(ValidationError,'changed'):self.c.process_guide('process-a')
        with self.assertRaisesRegex(ValidationError,'changed'):self.c.save_process_guide('process-a')

    def test_historical_process_opt_in_does_not_rewrite_issued_retrieval(self):
        self.c.create(MANIFEST,{'JOBA.jcl':JCL},assistant_mode='claude_files')
        self.c.start('process-a');self.c.advance('process-a')
        view=self.c.local_agent_action('process-a','inspect',{})
        doc=self.c.ledger.get('process-a');original=self.c.artifact('process-a',doc['retrieval_request']['artifact']).read_bytes()
        self.assertIsNone(self.c.process_guide('process-a')['markdown'])
        self.c.save_process_guide('process-a')
        self.assertEqual(self.c.artifact('process-a',doc['retrieval_request']['artifact']).read_bytes(),original)
        self.assertNotIn('guided_contract_version',self.c.ledger.get('process-a'))

    def test_prepared_intake_does_not_allow_deterministic_zero_source_execution(self):
        with self.assertRaisesRegex(ValidationError,'Prepared'):
            self.c.create(MANIFEST,{},assistant_mode='deterministic',requirements_selection=True,_prepare=True)
        self.assertEqual(len(self.c.ledger.list(True)),0)

    def test_twenty_randomized_programs_follow_source_to_actual_target_without_native_claim(self):
        import random,secrets
        from workbench.source import analyze_program
        from workbench.target import emit_program
        from workbench.fixtures import plan_cases,verify_program
        rng=random.Random(secrets.randbits(63));states=set();thresholds=rng.sample(range(10,990),20)
        for index in range(20):
            threshold=thresholds[index]
            source=COBOL.replace('>= 18','>= '+str(threshold));states.add(sha(source))
            pid='simulation-'+str(index);manifest=MANIFEST.replace('process-a',pid)
            self.c.prepare_process(manifest,{'JOBA.jcl':JCL,'ELIGIBLE.cbl':source})
            self.c.start(pid);self.c.advance(pid)
            scope=self.c.requirements_view(pid)
            self.c.save_requirements(pid,{'catalog_hash':scope['catalog_hash'],'revision':0,'excluded_ids':[],'saved_by':'Fictional randomized operator'})
            self.c.advance(pid);guide=self.c.process_guide(pid)
            self.assertTrue(guide['handoffs']['claude']);self.assertFalse(guide['results']['native_parity_verified'])
            program=analyze_program('ELIGIBLE.cbl',source,{})
            cases=plan_cases(program,seed=rng.randrange(2**31));target=emit_program(program)
            actual=verify_program(program,target,cases)
            self.assertFalse(actual['differences']);self.assertTrue(actual['coverage']['complete'])
            mutated=verify_program(program,target.replace('>= '+str(threshold),'> '+str(threshold)),cases)
            self.assertTrue(mutated['differences']);self.assertFalse(self.c.ledger.get(pid)['packet_issued'])
        self.assertEqual(len(states),20)


class GuidedApiTests(unittest.IsolatedAsyncioTestCase):
    from test_api import ApiTests as _fixture
    asyncSetUp=_fixture.asyncSetUp
    asyncTearDown=_fixture.asyncTearDown
    request=_fixture.request
    async def test_prepared_api_rejects_overbound_context_before_creation_and_retries_exact_boundary(self):
        _,raw=await self.request('/api/state');token=json.loads(raw)['token']
        headers=[(b'origin',b'http://127.0.0.1:8765'),(b'x-workbench-token',token.encode())]
        payload={'manifest':MANIFEST,'sources':{},'source_folder':None,'process_notes':None,'prompt':'x'*16001}
        status,raw=await self.request('/api/intake/prepare','POST',payload,headers)
        self.assertEqual(status,400,raw)
        self.assertIn('16,000',json.loads(raw)['error'])
        self.assertEqual(self.app.state.coordinator.ledger.list(True),[])
        payload['prompt']='x'*16000
        status,raw=await self.request('/api/intake/prepare','POST',payload,headers);self.assertEqual(status,200,raw)
        first=json.loads(raw)
        status,raw=await self.request('/api/intake/prepare','POST',payload,headers);self.assertEqual(status,200,raw)
        self.assertEqual(json.loads(raw),first)
        self.assertEqual(len(self.app.state.coordinator.ledger.list(True)),1)
        status,_=await self.request('/api/intake/prepare','POST',{**payload,'prompt':payload['prompt']+'y'},headers)
        self.assertEqual(status,400)
        self.assertEqual(self.app.state.coordinator.ledger.get('process-a'),first)

    async def test_exact_prepare_and_guide_routes_keep_same_origin_and_ledger(self):
        _,raw=await self.request('/api/state');token=json.loads(raw)['token']
        headers=[(b'origin',b'http://127.0.0.1:8765'),(b'x-workbench-token',token.encode())]
        payload={'manifest':MANIFEST,'sources':{},'source_folder':None,'process_notes':None}
        status,_=await self.request('/api/intake/prepare','POST',payload);self.assertEqual(status,403)
        status,raw=await self.request('/api/intake','POST',payload,headers);self.assertEqual(status,400)
        status,raw=await self.request('/api/intake/prepare','POST',payload,headers);self.assertEqual(status,200)
        pid=json.loads(raw)['id'];self.app.state.coordinator.start(pid);self.app.state.coordinator.advance(pid)
        status,raw=await self.request('/api/process/'+pid+'/guide');self.assertEqual(status,200)
        self.assertTrue(json.loads(raw)['handoffs']['copilot'])
        status,_=await self.request('/api/process/'+pid+'/guide/save','POST',{'force':True},headers);self.assertEqual(status,400)
        status,_=await self.request('/api/process/'+pid+'/guide/save','POST',{},headers);self.assertEqual(status,200)
        status,_=await self.request('/api/intake/prepare','POST',payload,headers);self.assertEqual(status,200)
        self.assertEqual(len(self.app.state.coordinator.ledger.list(True)),1)
        fictional={**payload,'manifest':MANIFEST.replace('process-a','fictional-api'),'demo':True}
        status,raw=await self.request('/api/intake/prepare','POST',fictional,headers);self.assertEqual(status,200)
        self.assertTrue(json.loads(raw)['demo'])
        _,raw=await self.request('/api/state');self.assertEqual(json.loads(raw)['portfolio']['processes'],1)
        status,_=await self.request('/api/intake/prepare','POST',{**fictional,'demo':'true'},headers);self.assertEqual(status,400)
        status,_=await self.request('/api/intake/prepare','POST',{**fictional,'demo':False},headers);self.assertEqual(status,400)

if __name__=='__main__':unittest.main()
