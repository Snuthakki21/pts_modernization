"""Versioned concise retrieval direction with exact bindings and protected identities."""
import copy
import random
import unittest
from workbench.domain import ValidationError,sha,encode
from workbench.retrieval import build_request,request_prompt,model_request,_verify_request

class AcceleratorPromptTests(unittest.TestCase):
    def doc(self,qualified=False):
        return {'id':'REFERRAL','source_files':{},'accelerator_contract_version':1,
                'guided_contract_version':1,'guided_workspace':r'C:\Factory\Evidence folder',
                'copilot_iteration':0,'demo':qualified}

    def test_sixty_four_distinct_requests_keep_exact_ids_and_windows_inbox(self):
        rng=random.Random(20261009);seen=set()
        for _ in range(64):
            name='PROC'+str(rng.randrange(1000000,9999999))
            request=build_request(self.doc(True),[{'kind':'proc','name':name,'reason':'missing source',
                'source_library_hints':['DEV.PROCLIB','TEST.PROCLIB']}])
            _verify_request(request);prompt=request_prompt(request);seen.add(request['request_id'])
            self.assertEqual(request['retrieval_prompt_version'],2)
            self.assertIn('retained local intake',prompt)
            self.assertIn('Normal intake checks workspace/Endeavor first',prompt)
            self.assertIn('read-only Zowe CLI',prompt);self.assertIn('typed Db2 MCP',prompt)
            self.assertIn('response.json LAST',prompt);self.assertIn(name,prompt)
            self.assertIn('download-to-file command without printing source',prompt)
            self.assertIn(encode({'workspace':self.doc()['guided_workspace'],
                'return_inbox':self.doc()['guided_workspace']+'\\'+request['return_folder'].replace('/','\\')}).decode(),prompt)
            self.assertFalse('Copilot' in prompt)
        self.assertEqual(len(seen),64)

    def test_unapproved_libraries_and_names_are_masked_in_model_view(self):
        request=build_request(self.doc(),[{'kind':'proc','name':'PRIVATEPROC','reason':'private comments',
            'library':'PRIVATE.PROCLIB','source_library_hints':['PRIVATE.SECOND']}])
        prompt=request_prompt(request);safe=encode(model_request(request)).decode()
        for value in ('PRIVATEPROC','PRIVATE.PROCLIB','PRIVATE.SECOND','private comments'):
            self.assertNotIn(value,prompt);self.assertNotIn(value,safe)
        self.assertIn('UNAPPROVED_MODEL_METADATA',prompt)
        self.assertEqual(request['needs'][0]['library'],'PRIVATE.PROCLIB')

    def test_new_hints_upgrade_fresh_request_without_rewriting_old_prompt(self):
        doc=self.doc(True);doc.pop('accelerator_contract_version')
        old=build_request(doc,[{'kind':'proc','name':'REFPROC','reason':'missing'}])
        original=encode(old);self.assertNotIn('retrieval_prompt_version',old)
        new=build_request(doc,[{'kind':'proc','name':'REFPROC','reason':'missing','library':'DEV.PROCLIB'}])
        self.assertEqual(new['retrieval_prompt_version'],2);_verify_request(new)
        self.assertEqual(encode(old),original);_verify_request(old)

    def test_hint_mutations_and_wildcards_cannot_substitute_lookup_scope(self):
        request=build_request(self.doc(True),[{'kind':'proc','name':'REFPROC','reason':'missing','library':'DEV.PROCLIB'}])
        changed=copy.deepcopy(request);changed['needs'][0]['library']='PROD.PROCLIB'
        with self.assertRaises(ValidationError):_verify_request(changed)
        for hints in (['DEV.*'],['DEV.LIB','dev.lib'],[],['&HLQ.PROC'],['X'*45]):
            with self.subTest(hints=hints),self.assertRaises(ValidationError):
                build_request(self.doc(True),[{'kind':'proc','name':'REFPROC','reason':'missing','source_library_hints':hints}])
        changed=copy.deepcopy(request);changed['retrieval_prompt_version']=True
        with self.assertRaises(ValidationError):_verify_request(changed)
