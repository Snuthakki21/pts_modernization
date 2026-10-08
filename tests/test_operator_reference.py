"""Navigation references fail closed on drift, unsafe paths and malformed spans."""
import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from tools.check_handoff import check_operator_reference


class OperatorReferenceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        authority = {'operator_guide':'START_HERE.md', 'technical_contract':'docs/TECHNICAL_REFERENCE.md', 'workflow':'prompts/START_MODERNIZATION.md'}
        self.data = {'schema_version':1, 'kind':'OPERATOR_GUIDE_REFERENCE', 'authority':authority,
                     'use':{k:'Bounded navigation only.' for k in ('read_order','invalidate','current_state','not_authorization')},
                     'sources':[], 'job_aid':{'filename':'mainframe-modernization-job-aid.html', 'sha256':'a'*64, 'status':'REVIEW_DRAFT',
                     'steps':[{'id':i,'title':f'Step {i}', 'phase':'Review'} for i in range(1,47)]},
                     'topics':[{'id':'setup','match':['setup'], 'answer':'Read the guide.', 'steps':[1,2], 'read':[{'path':'START_HERE.md','lines':[1,2]}]}]}
        for name in authority.values():
            path = self.root/name
            path.parent.mkdir(parents=True,exist_ok=True)
            path.write_text('Guide evidence.\n'*100)
            self.data['sources'].append({'path':name, 'sha256':hashlib.sha256(path.read_bytes()).hexdigest()})
        self.path = self.root/'prompts/OPERATOR_GUIDE.json'

    def check(self, data=None):
        self.path.write_text(json.dumps(self.data if data is None else data))
        return check_operator_reference(self.root)

    def test_valid_cache_has_no_workspace_or_external_html_dependency(self):
        self.assertEqual(self.check(), [])
        self.assertFalse((self.root/'processes').exists())

    def test_changed_source_invalidates_even_if_spans_still_fit(self):
        (self.root/'START_HERE.md').write_text('Changed.\n'*100)
        self.assertIn('stale source binding', ' '.join(self.check()))

    def test_missing_reference_is_reported(self):
        self.assertIn('missing or unsafe', ' '.join(check_operator_reference(self.root)))

    def test_rejects_duplicate_json_keys(self):
        self.path.write_text('{"schema_version":1,"schema_version":1}')
        self.assertIn('duplicate JSON key', ' '.join(check_operator_reference(self.root)))

    def test_oversized_reference_rejected_before_parse(self):
        self.path.write_text(' '*32769)
        self.assertIn('32,768', ' '.join(check_operator_reference(self.root)))

    def test_rejects_escape_private_and_windows_paths(self):
        for name in ('../START_HERE.md','/etc/passwd','.implementation/private.json','.migration/state.json','processes/p/ledger.db','docs\\TECHNICAL_REFERENCE.md','docs/../START_HERE.md'):
            with self.subTest(name=name):
                changed=copy.deepcopy(self.data);changed['sources'][0]['path']=name
                self.assertTrue(self.check(changed))

    def test_parent_symlink_is_rejected(self):
        (self.root/'linked').symlink_to(self.root/'docs',target_is_directory=True)
        changed=copy.deepcopy(self.data);changed['sources'][1]['path']='linked/TECHNICAL_REFERENCE.md'
        self.assertTrue(self.check(changed))

    def test_source_and_topic_ids_cannot_duplicate(self):
        self.data['sources'].append(self.data['sources'][0].copy())
        self.assertTrue(self.check())
        self.data['sources'].pop();self.data['topics'].append(copy.deepcopy(self.data['topics'][0]))
        self.assertTrue(self.check())

    def test_unbound_and_out_of_range_spans_rejected(self):
        for span in ({'path':'unknown.py','lines':[1,2]},{'path':'START_HERE.md','lines':[0,2]},{'path':'START_HERE.md','lines':[2,1]},{'path':'START_HERE.md','lines':[99,101]},{'path':'START_HERE.md','lines':[1,81]},{'path':'START_HERE.md','lines':[True,2]}):
            with self.subTest(span=span):
                changed=copy.deepcopy(self.data);changed['topics'][0]['read']=[span]
                self.assertTrue(self.check(changed))

    def test_duplicate_missing_and_bool_step_ids_rejected(self):
        for value in (1,47,True):
            changed=copy.deepcopy(self.data);changed['job_aid']['steps'][1]['id']=value
            self.assertTrue(self.check(changed))

    def test_unknown_topic_step_and_duplicate_references_rejected(self):
        for values in ([47],[1,1],[True],[]):
            changed=copy.deepcopy(self.data);changed['topics'][0]['steps']=values
            self.assertTrue(self.check(changed))

    def test_missing_authority_binding_rejected(self):
        changed=copy.deepcopy(self.data);changed['authority']['workflow']='another.md'
        self.assertTrue(self.check(changed))

    def test_schema_and_draft_cannot_imply_acceptance(self):
        for section,key,value in ((None,'schema_version',True),('job_aid','status','COMPLETE'),('job_aid','sha256','invalid')):
            changed=copy.deepcopy(self.data)
            (changed if section is None else changed[section])[key]=value
            self.assertTrue(self.check(changed))

    def test_invalid_json_and_utf8_are_actionable_errors(self):
        for raw in (b'{',b'\xff'):
            self.path.write_bytes(raw)
            self.assertTrue(check_operator_reference(self.root))
