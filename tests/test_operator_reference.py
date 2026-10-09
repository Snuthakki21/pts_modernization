"""Navigation references fail closed on drift, unsafe paths and malformed spans."""
import copy
import base64
from html.parser import HTMLParser
import re
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


class IllustratedGuideParser(HTMLParser):
    """Inspect navigation/captions, never display embedded image pixels."""
    def __init__(self):
        super().__init__()
        self.phase='';self.step=None;self.heading=False;self.title=[];self.steps=[]
        self.figures=[];self.caption=False;self.captions=[];self.caption_text=[]
    def handle_starttag(self,tag,attrs):
        attributes=dict(attrs)
        if tag=='section' and attributes.get('class')=='phase':self.phase=attributes.get('id','')
        if tag=='article' and attributes.get('class')=='step':self.step=int(attributes['id'][5:])
        if tag=='h3' and self.step is not None:self.heading=True;self.title=[]
        if tag=='img' and attributes.get('id','').startswith('figure-'):self.figures.append(attributes)
        if tag=='figcaption':self.caption=True;self.caption_text=[]
    def handle_data(self,value):
        if self.heading:self.title.append(value)
        if self.caption:self.caption_text.append(value)
    def handle_endtag(self,tag):
        if tag=='h3' and self.heading:
            self.steps.append({'id':self.step,'title':re.sub(r'^Step \d+\. ','',''.join(self.title)),'phase':self.phase});self.heading=False
        if tag=='article':self.step=None
        if tag=='figcaption':self.captions.append(''.join(self.caption_text));self.caption=False


class RepositoryOperatorGuideTests(unittest.TestCase):
    """Verify checked navigation against real template, contracts and retained history."""
    root=Path(__file__).resolve().parents[1]
    original_zip_sha256='4e8d26cada1adfbe62931db2258758bf05e4cd476289977e5871597773d7ef03'
    original_image_sha256={'figure-1': '279f4de303240ef7e29c8893d981850f5a319290daa61167e797d686593e22ed', 'figure-2': '0576fb2145f882bab1c1d9fac36a035f92b69b481ebdbfff17fe9fd5a2c50594', 'figure-3': 'c1ed2596626c74f38afe8866a21124a60740756fca54c44d3b4e592fa5f4a3e2', 'figure-4': '8821770971f0b21959f47190f996f886f7cf859f0980c81bad0eee0a590465d5', 'figure-5': '596682dd16604910c0e607c9bf3312ab426636ce0a6c349732d9b92f5ef336c5', 'figure-28': 'e73b356ae0a5142c0b78ece6d33429da2fd9d157de768a1df19236635add9ddf', 'figure-32': '768cb961f658f4283009ef79107fb311d84bcdf1bf975733faba19e3eca732b2', 'figure-33': 'aaa9d6dcc112d3616571c1b263e791f37f9021e9681fb6b9ad498e1511a502d2', 'figure-6': '92b14b435b204b1aee96ae7ac84b4a56fc01da2223c89974f6870d910942dfbb', 'figure-7': '3c008507b6341746039683bfc5890ed5d549e72527c2fa1540d569d8ef23d16a', 'figure-8': '6a0c2c95166a668728d20c2e8a7130efadbd0760c6899d2a08867d050f1c8eba', 'figure-29': '7fbc0d6b7c0bf01db4b915c55ce502bc8fc8be3459b34ed1d928498d5aafc8ea', 'figure-9': '5bc511f3583287c9624bef6de52d011850bc5aa3ca66cc66414fe6e709d7c588', 'figure-10': '974844ea1b2a2cf7adbb34c0817bc90f3fb4772ec0c224dcb5cfd5c6c4ec0bd1', 'figure-11': 'b81503de0b4a536f794547d800dcafbe755a04fbd0d17bfba919e47db28b2c2d', 'figure-12': '2fb249dc76dc1152bf1d42ea5b72d287ef28b01d82e6c26e71e3964d6e19b917', 'figure-13': 'f6bbab757ccd6c2490b0e661e831ab07603b150fa4e3e787b10b6e3407929911', 'figure-14': '8ab28053e6ddd1f269b2f43ffc1ce2382a63ce66d3577d4a1f0832e144fbca00', 'figure-15': '2843409f3398a6a15218ae4e4538500d33fccaaf02bd927b8502863d875f9d5a', 'figure-16': '192dba751377f64096d1047935ad140585073ed783241cbf3503c7d60b06ad80', 'figure-17': '0f87bf935630422fa5b3bed6d23beb31632f358b9e1f55f7102ecdca5a2720ed', 'figure-18': '295075a3fa3003870675e028815b65f06e023026b7b9f13727817a899fdc6216', 'figure-19': '005e72cd4bca89c22c5254ace58290ce79ec6665dfe3b58ca6764f78c2e5d19e', 'figure-20': '93cd6e177c831ef8a8867424844db07721d7dd0d175acf248b8162361296e197', 'figure-30': '40c6b03f649a4842877302768d164933ac5e600d5fd397e9959dce349dfff57b', 'figure-21': '3fe76167b93eafb4aadab88e22b2d896272c61f6b544c399b543d2c518868cfb', 'figure-22': 'd97545fc9b99af0e8667b47e5d2b25f18f6fbc501a21081ac2f8a3cf91507335', 'figure-31': 'b3b1b1e12f921f80b42a199f0413b03a05161d85e448ab824c3bc690c3738082', 'figure-23': 'e81433827f4ab47a879206a49c3de82032ba4892d7052d35021096d81454331c', 'figure-24': '2c8faed1ccd6a47933a8cea460d1240ab31fabd61a040d4a95e1d4a192db6259', 'figure-25': 'ba971570392fdc76e98d6eb5bb50729e556dd0e92239684a80228949e065b112', 'figure-26': '439f58720c610e548f0197cfcbe13130000123ec17fae135a941cbb6e59b9236', 'figure-27': 'b5320c330437d3cb5f4e18b15e502b6b5a221a7c3d67b49531cb1fae2c7d40f1'}

    @classmethod
    def setUpClass(cls):
        cls.reference=json.loads((cls.root/'prompts/OPERATOR_GUIDE.json').read_text())
        cls.html=(cls.root/'examples/mainframe-modernization-job-aid.html').read_text()
        cls.parsed=IllustratedGuideParser();cls.parsed.feed(cls.html)
        cls.topics={t['id']:t for t in cls.reference['topics']}

    def test_repository_reference_hashes_and_all_spans_validate(self):
        self.assertEqual(check_operator_reference(self.root),[])

    def test_real_job_aid_steps_and_titles_equal_navigation_cache(self):
        self.assertEqual(self.parsed.steps,self.reference['job_aid']['steps'])
        self.assertEqual([step['id'] for step in self.parsed.steps],list(range(1,47)))
        self.assertEqual(hashlib.sha256(self.html.encode()).hexdigest(),self.reference['job_aid']['sha256'])

    def test_existing_offline_sample_and_33_images_remain_intact_and_historical(self):
        zip_match=re.search(r'id="sample-package"[^>]*href="data:application/zip;base64,([^"]+)"',self.html)
        self.assertIsNotNone(zip_match)
        self.assertEqual(hashlib.sha256(base64.b64decode(zip_match[1],validate=True)).hexdigest(),self.original_zip_sha256)
        figures={figure['id']:figure for figure in self.parsed.figures}
        for image_id,expected in self.original_image_sha256.items():
            with self.subTest(image=image_id):
                value=figures[image_id]['src'].split(',',1)[1]
                self.assertEqual(hashlib.sha256(base64.b64decode(value,validate=True)).hexdigest(),expected)
        historical=[caption for caption in self.parsed.captions if 'HISTORICAL ACCELERATOR REFERENCE.' in caption]
        self.assertEqual(len(historical),33)
        self.assertTrue(all('not Windows 11 or live-host acceptance' in caption for caption in historical))
        current=[caption for caption in self.parsed.captions if 'CURRENT ACCELERATOR UI.' in caption]
        self.assertEqual(len(current),4)
        self.assertEqual(len(self.parsed.figures),37)
        self.assertTrue(all('not Windows 11 desktop' in caption for caption in current))
        self.assertTrue(any('before Save' in caption for caption in current))
        self.assertTrue(any('No SME answer was filled' in caption for caption in current))

    def test_single_template_works_as_root_only_process_without_guessed_steps(self):
        from workbench.intake import parse_manifest
        text=(self.root/'examples/process-specific.md').read_text().replace('replace-with-a-stable-id','documentation-check').replace('Replace with the name people use for this process','Documentation check').replace('REPLACEJOB','IZERO007')
        parsed=parse_manifest(text)
        self.assertEqual(parsed['id'],'documentation-check')
        self.assertEqual(parsed['process_intake_version'],2)
        self.assertEqual([job['name'] for job in parsed['jobs']],['IZERO007'])
        self.assertEqual(parsed['jobs'][0]['steps'],[])
        self.assertIn('Unknown',text)
        self.assertIn('one Process.md',self.topics['manifest']['answer'])
        self.assertIn('no separate notes upload is required',self.topics['process-context-template']['answer'])

    def test_cached_primary_navigation_uses_default_folders_and_current_stage_labels(self):
        for name in ('Process.md','Endeavor','certificates','workspace_inputs'):
            self.assertIn(name,self.topics['folder-contract']['answer'] if name!='workspace_inputs' else str(self.topics['folder-contract']['match']))
        for label in ('Source & mapping','Choose rules','Build & test','Review & compare'):
            self.assertIn(label,(self.root/'START_HERE.md').read_text())
            self.assertIn(label,(self.root/'frontend/src/GuidedProcess.tsx').read_text())
        self.assertIn('No Save setup',self.topics['setup-next']['answer'])
        self.assertIn('Reconnect to this workspace',self.topics['blocked-recovery']['answer'])
        self.assertIn('declared roots stay unchanged',self.topics['manifest']['answer'])

    def test_capacity_faq_distinguishes_process_source_and_frozen_review_contracts(self):
        from workbench.intake import MAX_PROCESS_MARKDOWN_BYTES
        from workbench.review import MAX_HTML_REVIEW_BYTES
        from workbench.domain import MAX_UPLOAD
        self.assertEqual(MAX_PROCESS_MARKDOWN_BYTES,1024**2)
        self.assertEqual(MAX_HTML_REVIEW_BYTES,128*1024**2)
        self.assertEqual(MAX_UPLOAD,8*1024**2)
        answer=self.topics['input-capacity']['answer']
        for term in ('1 MiB','16 MiB/file','512 MiB','32 MiB','128 MiB','8 MiB','frozen','Stop UI'):
            self.assertIn(term,answer)
        self.assertIn('not memory/stress',answer)

    def test_primary_job_aid_keeps_atomic_help_optional_and_gate_language_truthful(self):
        self.assertIn('id="quick-path"',self.html)
        self.assertRegex(self.html,r'<details class="atomic-guide" id="detailed-help">')
        self.assertNotRegex(self.html,r'<details class="atomic-guide"[^>]*\bopen')
        for key in ('privacy-safe-input','legacy-fidelity','sme-return','retrieval'):
            self.assertTrue(self.topics[key]['read'])
        self.assertIn('Agents never fill answers',self.topics['sme-return']['answer'])
        self.assertIn('actual',self.topics['sme-return']['answer'])
        self.assertIn('Never query fictional names live',self.topics['retrieval']['answer'])
        self.assertIn('including apparent source defects',self.topics['legacy-fidelity']['answer'])
