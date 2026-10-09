"""Real CICS intake/scope API tests; no fabricated ledger, SME return or parity."""
from pathlib import Path
import tempfile
import unittest

from fastapi.testclient import TestClient
from workbench.api import create_app
from workbench.domain import sha
from workbench.requirements import catalog,parse_markdown,NO_REASON
from test_cics import BMS,COBOL

MANIFEST='''Process ID: cics-ui
Process name: Fictional CICS screen requirements
| Transaction | Program | Mapset | Map |
|---|---|---|---|
| T001 | PGM | MAPS | SCREEN |
'''
CSD='DEFINE TRANSACTION(T001) PROGRAM(PGM)\nDEFINE PROGRAM(PGM)\nDEFINE MAPSET(MAPS)\n'


def many_fields():
    labels=''.join(f" DFHMDF POS={600+i*10},LENGTH=8,ATTRB=(ASKIP,NORM),INITIAL='Label{i:02d}'\n" for i in range(60))
    return BMS.replace(' DFHMSD TYPE=FINAL\n',labels+' DFHMSD TYPE=FINAL\n')


class CicsRequirementsWorkflowTests(unittest.TestCase):
    def setUp(self):
        staging=Path('.implementation/tmp');staging.mkdir(parents=True,exist_ok=True)
        self.temp=tempfile.TemporaryDirectory(dir=staging);self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);self.app=create_app(self.root);self.c=self.app.state.coordinator
        self.addCleanup(self.c.close)
        self.client=TestClient(self.app,base_url='http://127.0.0.1:8765');self.addCleanup(self.client.close)
        self.sources={'PGM.cbl':COBOL,'FORM.bms':many_fields(),'T001.csd':CSD}
        token=self.client.get('/api/state').json()['token']
        self.headers={'Origin':'http://127.0.0.1:8765','X-Workbench-Token':token}
        response=self.client.post('/api/intake',json={'manifest':MANIFEST,'sources':self.sources,'assistant_mode':'claude_files'},headers=self.headers)
        self.assertEqual(response.status_code,200,response.text)
        self.c.start('cics-ui');self.c.advance('cics-ui')
        self.assertEqual(self.c.ledger.get('cics-ui')['status'],'WAITING_REQUIREMENTS')

    def fields(self,**extra):
        response=self.client.get('/api/process/cics-ui/requirements',params={'program':'PGM','screen':'MAPS/SCREEN','kind':'screen_field',**extra})
        self.assertEqual(response.status_code,200,response.text)
        return response.json()

    def test_filters_apply_to_complete_catalog_before_paging(self):
        first=self.fields();second=self.fields(after=first['next_after'])
        self.assertEqual(first['total'],63);self.assertEqual(len(first['items']),50);self.assertTrue(first['has_more'])
        self.assertEqual(len(second['items']),13);self.assertFalse(second['has_more'])
        self.assertEqual(first['inventory_total'],len(catalog(self.c.ledger.get('cics-ui')['analysis'])['items']))
        self.assertGreater(first['inventory_total'],first['total'])
        self.assertFalse(set(r['id'] for r in first['items'])&set(r['id'] for r in second['items']))
        self.assertEqual(len({r['id'] for r in first['items']+second['items']}),63)
        self.assertTrue(all(r['kind']=='screen_field' and r['source_path']=='FORM.bms' and r['screens']==['MAPS/SCREEN'] and r['programs']==['PGM'] for r in first['items']+second['items']))
        self.assertEqual(first['filters'],second['filters']);self.assertIn('screen_action',first['filters']['kinds'])
        by_path=self.fields(path='PGM.cbl');self.assertEqual(by_path['total'],0);self.assertEqual(by_path['items'],[])

    def test_unknown_duplicate_filters_and_out_of_range_cursor_fail_without_save(self):
        before=self.c.ledger.get('cics-ui');artifacts=list(before['artifacts'])
        for query in ('program=MISSING','screen=MAPS/MISSING','kind=not-a-kind','program=PGM&program=PGM','screen=MAPS%2FSCREEN&screen=MAPS%2FSCREEN','kind=screen_field&kind=rule','extra=1','kind=screen_field&after=64','after=-1'):
            with self.subTest(query=query):
                response=self.client.get('/api/process/cics-ui/requirements?'+query)
                self.assertEqual(response.status_code,400,response.text)
        after=self.c.ledger.get('cics-ui');self.assertEqual(after['artifacts'],artifacts);self.assertFalse(after['packet_issued']);self.assertNotIn('requirements',after)

    def test_save_keeps_hidden_page_and_filter_exclusions_in_one_pinned_markdown(self):
        first=self.fields();last=self.fields(after=50)
        hidden_page=next(row for row in last['items'] if row['required'] is False)
        hidden_filter=next(row for row in first['items'] if row['required'] is False)
        exclusions=sorted([hidden_page['id'],hidden_filter['id']])
        # Operator now inspects actions; both choices are hidden but remain in the Save.
        action_view=self.client.get('/api/process/cics-ui/requirements',params={'program':'PGM','kind':'screen_action'}).json()
        self.assertFalse(set(exclusions)&{row['id'] for row in action_view['items']})
        before=self.c.ledger.get('cics-ui');source_hashes=dict(before['source_files'])
        response=self.client.post('/api/process/cics-ui/requirements',json={'catalog_hash':action_view['catalog_hash'],'revision':action_view['revision'],'excluded_ids':exclusions,'saved_by':'Fictional CICS scope operator'},headers=self.headers)
        self.assertEqual(response.status_code,200,response.text)
        saved=self.c.ledger.get('cics-ui');self.assertEqual(saved['requirements']['excluded_ids'],exclusions)
        frozen=self.c.artifact('cics-ui',saved['requirements_artifact']).read_bytes()
        selection=parse_markdown(frozen,catalog(before['analysis']));self.assertEqual(selection,saved['requirements'])
        self.assertEqual(frozen,(self.root/'processes/cics-ui/analysis/requirements.md').read_bytes())
        self.assertEqual(sha(frozen),saved['artifact_hashes'][saved['requirements_artifact']])
        for row in (hidden_page,hidden_filter):
            choice=next(line for line in frozen.decode().splitlines() if line.startswith('| '+row['id']+' |'))
            self.assertIn('| No |',choice);self.assertIn(NO_REASON,choice);self.assertIn('MAPS/SCREEN',choice)
        self.assertEqual(saved['source_files'],source_hashes);self.assertEqual(self.c.sources(saved),self.sources)
        self.assertFalse(saved['packet_issued']);self.assertEqual(saved['status'],'QUEUED_ANALYSIS')
        self.c.advance('cics-ui');continued=self.c.ledger.get('cics-ui')
        self.assertEqual(continued['status'],'WAITING_COPILOT');self.assertFalse(continued['packet_issued'])
        self.assertEqual({unit['id'] for unit in continued['analysis']['requirements']['excluded_units']},set(exclusions))
        self.assertTrue(any(gap['kind']=='cics_controller_gap' for gap in continued['blockers']))
        self.assertFalse(any(gap['kind']=='requirements_dependency' for gap in continued['blockers']))
        local=self.c.local_agent_view('cics-ui');self.assertIsNone(local['requirements_file'])
        self.assertEqual(local['requirements']['sha256'],sha(frozen))
        self.assertEqual(local['requirements']['excluded_count'],len(exclusions))
        self.assertFalse(local['requirements']['private_contents_allowed'])
        self.assertEqual(local['host_roles']['analysis'],'Claude Code, accepted local evidence, development, testing and review')

    def test_required_action_no_retains_exact_source_dependency_in_existing_coordinator(self):
        view=self.client.get('/api/process/cics-ui/requirements',params={'kind':'screen_action'}).json()
        action=next(row for row in view['items'] if row['operation']=='RECEIVE')
        response=self.client.post('/api/process/cics-ui/requirements',json={'catalog_hash':view['catalog_hash'],'revision':view['revision'],'excluded_ids':[action['id']],'saved_by':'Fictional CICS scope operator'},headers=self.headers)
        self.assertEqual(response.status_code,200,response.text)
        self.c.advance('cics-ui');doc=self.c.ledger.get('cics-ui')
        gaps=[gap for gap in doc['blockers'] if gap['kind']=='requirements_dependency']
        self.assertEqual(len(gaps),1);self.assertEqual(gaps[0]['path'],action['source_path'])
        self.assertEqual(gaps[0]['lines'],list(range(action['start_line'],action['end_line']+1)));self.assertIn(NO_REASON,gaps[0]['message'])
        self.assertFalse(doc['packet_issued']);self.assertFalse(doc.get('program_versions',{}))
        self.assertTrue(any(gap['kind']=='cics_controller_gap' for gap in doc['blockers']))
