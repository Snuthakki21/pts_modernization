"""Standalone development handoffs preserve evidence and the existing review gates."""
from copy import deepcopy
from pathlib import Path
import json
import tempfile
import unittest
from unittest.mock import patch

from workbench.coordinator import Coordinator
from workbench.domain import ValidationError, encode, sha
from test_source import COBOL
from test_workflow import MANIFEST


class DevelopmentHandoffTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.c = Coordinator(self.tmp.name)
        self.addCleanup(lambda: self.c.close())
        self.c.create(MANIFEST, {'ELIGIBLE.cbl': COBOL, 'JOBA.jcl': "//JOBA JOB (TEST),'FICTIONAL'\n//S010 EXEC PGM=ELIGIBLE\n"}, assistant_mode='agent',
                      prompt='PRIVATE_OPERATOR_SENTINEL')
        self.c.start('process-a')
        self.c.advance('process-a')
        self.assertEqual(self.c.ledger.get('process-a')['status'], 'WAITING_COPILOT')

    def prepared(self):
        return self.c.prepare_development('process-a')['packet']

    def returned(self, packet):
        return {'handoff_id': packet['handoff_id'],
                'actor': {'name': 'Test developer', 'model': 'unknown', 'session_id': 'fictional-session'},
                'summary': 'Insufficient approved evidence; kept unresolved.', 'revision': 'none',
                'changes': [], 'tests': [],
                'review': {'status': 'NOT_RUN', 'reviewer': '', 'evidence_hash': None},
                'work_items': [{'id': item['id'], 'outcome': 'UNRESOLVED', 'details': 'Needs source-specific evidence in Copilot.'}
                               for item in packet['work_items']]}

    def test_default_packet_contains_no_operational_content_and_is_immutable(self):
        packet = self.prepared()
        raw = encode(packet).decode()
        for secret in ('process-a', 'ELIGIBLE', 'Referral eligibility', 'PRIVATE_OPERATOR_SENTINEL', 'JOBA', COBOL):
            self.assertNotIn(secret, raw)
        self.assertEqual(packet['handoff_id'], sha(encode({k:v for k,v in packet.items() if k != 'handoff_id'})))
        self.assertEqual(self.c.prepare_development('process-a')['packet'], packet)
        self.assertEqual(self.c.development_task(packet['handoff_id'])['packet'], packet)
        self.assertFalse(self.c.ledger.get('process-a')['packet_issued'])

    def test_return_is_idempotent_unverified_and_requires_refresh(self):
        packet = self.prepared(); payload = self.returned(packet)
        first = self.c.submit_development(packet['handoff_id'], payload)
        self.assertEqual(first, self.c.submit_development(packet['handoff_id'], payload))
        self.assertEqual(first['status'], 'RETURNED_FOR_REVIEW')
        self.assertEqual(self.c.ledger.get('process-a')['status'], 'WAITING_COPILOT')
        view = self.c.development_view('process-a')
        self.assertEqual(view['result']['authority'], 'UNVERIFIED_DEVELOPER_RETURN')
        with self.assertRaisesRegex(ValidationError, 'refresh'):
            self.c.submit_agent_analysis('process-a', {})
        changed = deepcopy(payload); changed['summary'] = 'different return'
        with self.assertRaises(ValidationError): self.c.submit_development(packet['handoff_id'], changed)
        self.c.refresh_analysis('process-a'); self.c.advance('process-a')
        with self.assertRaisesRegex(ValidationError, 'unavailable|stale'):
            self.c.submit_development(packet['handoff_id'], payload)
        self.assertEqual(self.c.development_view('process-a')['status'], 'STALE')
        self.assertNotEqual(self.prepared()['handoff_id'], packet['handoff_id'])

    def test_return_rejects_contract_injection_unknown_tasks_and_oversize(self):
        packet = self.prepared()
        for field in ('answers', 'command', 'completion', 'copilot_credits'):
            with self.subTest(field=field), self.assertRaises(ValidationError):
                payload = self.returned(packet); payload[field] = 'Yes'
                self.c.submit_development(packet['handoff_id'], payload)
        for edit in (lambda p:p.update(handoff_id='0'*64), lambda p:p.update(work_items=[]),
                     lambda p:p.update(summary='x'*65537),
                     lambda p:p['work_items'].append(dict(p['work_items'][0]))):
            with self.subTest(edit=edit), self.assertRaises(ValidationError):
                payload=self.returned(packet); edit(payload)
                self.c.submit_development(packet['handoff_id'],payload)

    def test_unknown_blocker_strings_never_become_development_instructions(self):
        from workbench.development import build_packet
        task = self.c.agent_task('process-a')
        packet = build_packet(task, [{'kind': 'PRIVATE_KIND', 'message': 'PRIVATE_MESSAGE', 'path': 'PRIVATE_PATH'}], self.c.adapter_fingerprint)
        raw = encode(packet).decode()
        self.assertNotIn('PRIVATE_', raw)
        self.assertIn('assessment', {item['id'] for item in packet['work_items']})

    def test_tampered_artifact_and_source_have_source_free_developer_errors(self):
        packet = self.prepared()
        path = Path(self.tmp.name)/'processes/process-a/input/sources/ELIGIBLE.cbl'
        path.write_text(COBOL+'\n')
        with self.assertRaises(ValidationError) as caught:self.c.development_task(packet['handoff_id'])
        self.assertNotIn('ELIGIBLE', str(caught.exception))
        self.assertNotIn('process-a', str(caught.exception))
        with self.assertRaises(ValidationError):self.c.submit_development(packet['handoff_id'],self.returned(packet))

    def test_pending_development_blocks_analysis_and_refresh_requires_a_return(self):
        self.prepared()
        with self.assertRaisesRegex(ValidationError, 'refresh'):self.c.submit_agent_analysis('process-a', {})
        with self.assertRaisesRegex(ValidationError, 'return'):self.c.refresh_analysis('process-a')

    def test_restart_preserves_handoff(self):
        packet=self.prepared();self.c.close();self.c=Coordinator(self.tmp.name)
        self.assertEqual(self.c.development_task(packet['handoff_id'])['packet'],packet)

    def test_scope_save_invalidates_old_development_return(self):
        packet = self.prepared()
        view = self.c.requirements_view('process-a')
        self.c.save_requirements('process-a', {'catalog_hash': view['catalog_hash'],
            'revision': view['revision'], 'excluded_ids': [], 'saved_by': 'Fictional operator'})
        with self.assertRaises(ValidationError): self.c.submit_development(packet['handoff_id'], self.returned(packet))
        self.c.advance('process-a')
        self.assertEqual(self.c.development_view('process-a')['status'], 'STALE')
        self.assertNotEqual(self.prepared()['binding']['requirements_hash'], packet['binding']['requirements_hash'])

    def test_development_edits_are_returnable_but_exact_patch_must_be_integrated(self):
        packet = self.prepared(); payload = self.returned(packet)
        payload['changes'] = [{'path': 'workbench/development.py', 'operation': 'modify', 'sha256': '0'*64}]
        with patch('workbench.coordinator.adapter_fingerprint', return_value='1'*64):
            self.assertEqual(self.c.submit_development(packet['handoff_id'], payload)['status'], 'RETURNED_FOR_REVIEW')
        with self.assertRaisesRegex(ValidationError, 'not integrated'):self.c.refresh_analysis('process-a')
        self.assertFalse(self.c.ledger.get('process-a')['packet_issued'])

    def test_rejected_patch_can_be_revised_without_integrating_bad_code(self):
        packet=self.prepared();payload=self.returned(packet)
        payload['changes']=[{'path':'workbench/review.py','operation':'modify','sha256':'0'*64}]
        self.c.submit_development(packet['handoff_id'],payload)
        revised=self.c.revise_development('process-a','REVIEW_FINDINGS',packet['handoff_id'])['packet']
        self.assertNotEqual(revised['handoff_id'],packet['handoff_id'])
        self.assertEqual(self.c.revise_development('process-a','REVIEW_FINDINGS',packet['handoff_id'])['packet'],revised)
        with self.assertRaises(ValidationError):self.c.revise_development('process-a','ADDITIONAL_WORK',packet['handoff_id'])
        self.assertEqual(revised['revision']['previous_handoff_id'],packet['handoff_id'])
        with self.assertRaises(ValidationError):self.c.development_task(packet['handoff_id'])
        self.c.submit_development(revised['handoff_id'],self.returned(revised))
        self.c.refresh_analysis('process-a');self.c.advance('process-a')
        records=self.c.ledger.get('process-a')['artifacts']
        self.assertEqual(sum(path.startswith('analysis/development-return-') for path in records),2)
        self.assertFalse(self.c.ledger.get('process-a')['packet_issued'])

    def test_actual_patch_digest_and_restart_are_required_before_reassessment(self):
        packet=self.prepared();payload=self.returned(packet)
        payload['changes']=[{'path':'workbench/development.py','operation':'modify',
                             'sha256':sha(Path('workbench/development.py').read_bytes())}]
        self.c.submit_development(packet['handoff_id'],payload)
        with patch('workbench.coordinator.adapter_fingerprint',return_value='1'*64):
            with self.assertRaisesRegex(ValidationError,'Restart'):self.c.refresh_analysis('process-a')
        self.c.refresh_analysis('process-a');self.c.advance('process-a')
        fresh=self.c.agent_task('process-a')
        self.assertIn('development_return',fresh)
        self.assertEqual(fresh['development_return']['authority'],'UNVERIFIED_DEVELOPER_RETURN')

    def test_fake_test_counts_unsafe_paths_and_missing_work_evidence_reject(self):
        from workbench.development import validate_return
        packet=self.prepared()
        paths=['../secrets.py','/tmp/test.py','workbench/../secrets.py','workbench\\test.py',
               'processes/private.json','Endeavor/SOURCE.cbl','.env','workbench/CON.py',
               'workbench/test?.py','workbench/test\n.py','workbench//test.py','workbench/file.py.']
        for path in paths:
            with self.subTest(path=path),self.assertRaises(ValidationError):
                payload=self.returned(packet);payload['changes']=[{'path':path,'operation':'modify','sha256':'a'*64}]
                validate_return(packet,payload)
        for count in (True,-1,1.2,10000001):
            with self.subTest(count=count),self.assertRaises(ValidationError):
                payload=self.returned(packet);payload['tests']=[{'name':'unit','passed':count,'failed':0,'skipped':0,'evidence_hash':'b'*64}]
                validate_return(packet,payload)
        payload=self.returned(packet);payload['work_items'][0]['outcome']='IMPLEMENTED'
        with self.assertRaisesRegex(ValidationError,'evidence'):validate_return(packet,payload)

    def test_randomized_private_payloads_never_escape_static_projection(self):
        import random,secrets
        from workbench.development import build_packet
        seed=secrets.randbits(63);rng=random.Random(seed);task=self.c.agent_task('process-a')
        for case in range(20):
            secret='CONFIDENTIAL_'+str(rng.getrandbits(120))
            changed=deepcopy(task);changed['operator_request']=secret;changed['process_id']=secret
            changed['source_excerpts']=[{'text':secret,'path':secret}]
            changed['scope']={'jobs':secret,'relationships':secret}
            packet=build_packet(changed,[{'kind':'unknown_'+secret,'message':secret,'path':secret}],self.c.adapter_fingerprint)
            self.assertNotIn(secret,encode(packet).decode(),f'seed={seed},case={case}')

    def test_integrated_change_checks_reject_symlinks_and_unapplied_deletions(self):
        from workbench.development import check_integrated_changes
        packet=self.prepared();payload=self.returned(packet)
        with tempfile.TemporaryDirectory() as repo:
            root=Path(repo);(root/'workbench').mkdir();file=root/'workbench/logic.py';file.write_text('pass')
            payload['changes']=[{'path':'workbench/logic.py','operation':'modify','sha256':sha(b'pass')}]
            check_integrated_changes({'submission':payload},root)
            payload['changes'][0].update(operation='delete',sha256=None)
            with self.assertRaises(ValidationError):check_integrated_changes({'submission':payload},root)
            file.unlink();check_integrated_changes({'submission':payload},root)
            try:file.symlink_to(root/'outside.py')
            except OSError:return  # Windows may disallow symlinks; deletion assertions still executed.
            with self.assertRaises(ValidationError):check_integrated_changes({'submission':payload},root)


class DevelopmentApiTests(unittest.TestCase):
    def setUp(self):
        from workbench.api import create_app
        from fastapi.testclient import TestClient
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        app=create_app(self.tmp.name);self.c=app.state.coordinator;self.addCleanup(self.c.close)
        self.client=TestClient(app,base_url='http://127.0.0.1:8765');self.addCleanup(self.client.close)
        self.c.create(MANIFEST,{'ELIGIBLE.cbl':COBOL,'JOBA.jcl':"//JOBA JOB (TEST),'FICTIONAL'\n//S010 EXEC PGM=ELIGIBLE\n"},assistant_mode='agent')
        self.c.start('process-a');self.c.advance('process-a')
        session=self.client.get('/api/session-token').json();self.assertEqual(set(session),{'token'})
        self.headers={'Origin':'http://127.0.0.1:8765','X-Workbench-Token':session['token']}

    def test_http_role_handoff_end_to_end_and_csrf_bounds(self):
        endpoint='/api/process/process-a/development'
        self.assertEqual(self.client.get(endpoint).json()['status'],'NOT_PREPARED')
        self.assertEqual(self.client.post(endpoint,json={}).status_code,403)
        self.assertEqual(self.client.post(endpoint,json={'source':'PRIVATE'},headers=self.headers).status_code,400)
        response=self.client.post(endpoint,json={},headers=self.headers);self.assertEqual(response.status_code,200)
        packet=response.json()['packet'];route='/api/development/'+packet['handoff_id']
        public=self.client.get(route);self.assertEqual(set(public.json()),{'status','packet','return_hash'})
        self.assertNotIn('process-a',public.text);self.assertNotIn('ELIGIBLE',public.text)
        payload=DevelopmentHandoffTests.returned(self,packet)
        self.assertEqual(self.client.post(route+'/return',json=payload).status_code,403)
        self.assertEqual(self.client.post(route+'/return',content=b'x'*65537,headers=self.headers).status_code,413)
        returned=self.client.post(route+'/return',json=payload,headers=self.headers)
        self.assertEqual(returned.status_code,200);self.assertEqual(returned.json()['status'],'RETURNED_FOR_REVIEW')
        self.assertEqual(self.client.get(endpoint).json()['result']['submission'],payload)
        revision_body={'handoff_id':packet['handoff_id'],'reason':'PATCH_NOT_INTEGRATED'}
        revised=self.client.post(endpoint+'/revise',json=revision_body,headers=self.headers)
        self.assertEqual(revised.status_code,200)
        self.assertEqual(self.client.post(endpoint+'/revise',json=revision_body,headers=self.headers).json(),revised.json())
        self.assertEqual(self.client.get(route).status_code,400)
        replacement=revised.json()['packet'];replacement_route='/api/development/'+replacement['handoff_id']
        self.assertEqual(self.client.post(replacement_route+'/return',json=DevelopmentHandoffTests.returned(self,replacement),headers=self.headers).status_code,200)
        self.c.refresh_analysis('process-a');self.c.advance('process-a')
        stale=self.client.get(route);self.assertEqual(stale.status_code,400);self.assertNotIn('process-a',stale.text)
        self.assertFalse(self.c.ledger.get('process-a')['packet_issued'])


if __name__ == '__main__': unittest.main()
