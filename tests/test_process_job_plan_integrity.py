"""Frozen simple intake roots and source-derived jobs share one integrity gate."""
import copy
from pathlib import Path
import tempfile
import unittest

from workbench.coordinator import Coordinator
from workbench.coverage import _manifest_integrity
from workbench.domain import ValidationError, encode, sha
from workbench.intake import verify_job_plan
from test_source import COBOL

PROCESS='Process ID: sample-a\nProcess name: Synthetic program flow\n## Jobs\n1. REFJOB\n## Notes\nUnknown partner date window.'
JCL="//REFJOB JOB (TEST),'FICTIONAL'\n//CHECK EXEC PGM=ELIGIBLE\n"


class ProcessJobPlanIntegrityTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name);self.c=Coordinator(self.root);self.addCleanup(self.c.close)
        self.doc=self.c.create(PROCESS,{'REFJOB.jcl':JCL,'ELIGIBLE.cbl':COBOL},assistant_mode='claude_files',requirements_selection=True)
        self.c.start(self.doc['id']);self.c.advance(self.doc['id']);self.doc=self.c.ledger.get(self.doc['id'])
        self.base=self.c.process_root(self.doc['id'])

    def test_original_roots_remain_frozen_and_only_unique_source_cards_supply_steps(self):
        self.assertEqual(self.doc['status'],'WAITING_REQUIREMENTS')
        self.assertEqual(self.doc['declared_jobs'],[{'name':'REFJOB','order':1,'steps':[]}])
        self.assertEqual(self.doc['jobs'][0]['steps'][0]['program'],'ELIGIBLE')
        self.assertEqual((self.base/'input/process-input.md').read_bytes(),PROCESS.encode())
        self.assertEqual(self.doc['process_context']['documents'][0]['text'],PROCESS)
        self.assertEqual(self.doc['review_html_contract_version'],2)
        self.c.manifest_integrity(self.doc);_manifest_integrity(self.doc,self.base)
        self.assertTrue(verify_job_plan(self.doc,self.base)['complete'])

    def test_both_transition_and_report_reject_declared_or_derived_job_mutations(self):
        variants=[]
        for target in ('declared_jobs','jobs'):
            doc=copy.deepcopy(self.doc);doc[target][0]['name']='OTHERJOB';variants.append(doc)
        for value in (True,1.0,2):
            doc=copy.deepcopy(self.doc);doc['jobs'][0]['order']=value;variants.append(doc)
        for doc in variants:
            for check in (self.c.manifest_integrity,lambda d:_manifest_integrity(d,self.base)):
                with self.subTest(value=doc['jobs'][0]['order'],check=check),self.assertRaises(ValidationError):check(doc)

    def test_source_hash_canonical_artifact_registration_and_binding_mutations_fail(self):
        variants=[]
        doc=copy.deepcopy(self.doc);doc['source_files']['REFJOB.jcl']='f'*64;variants.append(doc)
        doc=copy.deepcopy(self.doc);doc['artifacts'].remove(doc['job_plan_artifact']);variants.append(doc)
        doc=copy.deepcopy(self.doc);doc['artifact_hashes'][doc['job_plan_artifact']]='f'*64;variants.append(doc)
        for doc in variants:
            for check in (self.c.manifest_integrity,lambda d:_manifest_integrity(d,self.base)):
                with self.assertRaises(ValidationError):check(doc)
        raw=(self.base/self.doc['job_plan_artifact']).read_bytes()
        alternate='analysis/job-plan-other.json';(self.base/alternate).write_bytes(raw)
        doc=copy.deepcopy(self.doc);doc['job_plan_artifact']=alternate;doc['artifacts'].append(alternate);doc['artifact_hashes'][alternate]=sha(raw)
        with self.assertRaisesRegex(ValidationError,'noncanonical'):verify_job_plan(doc,self.base)

    def test_frozen_exact_gap_projection_cannot_be_emptied_or_corrected_by_ledger(self):
        import json
        plan=json.loads((self.base/self.doc['job_plan_artifact']).read_bytes())
        gap={'reason':'Synthetic unverified condition','path':'REFJOB.jcl','line':2,'status':'UNVERIFIED'}
        plan['gaps']=[gap];plan['complete']=False;raw=encode(plan)
        relative='analysis/job-plan-'+sha(raw)+'.json';(self.base/relative).write_bytes(raw)
        doc=copy.deepcopy(self.doc);doc['job_plan_artifact']=relative;doc['artifacts'].append(relative);doc['artifact_hashes'][relative]=sha(raw)
        doc['job_plan_gaps']=[{'kind':'unsupported_jcl','message':gap['reason'],'object':gap,'path':gap['path'],'line':gap['line']}]
        self.c.manifest_integrity(doc);_manifest_integrity(doc,self.base)
        for changed in ([],[{**doc['job_plan_gaps'][0],'message':'Assumed unnecessary'}]):
            bad=copy.deepcopy(doc);bad['job_plan_gaps']=changed
            for check in (self.c.manifest_integrity,lambda d:_manifest_integrity(d,self.base)):
                with self.assertRaisesRegex(ValidationError,'gaps differ'):check(bad)

    def test_preplanning_stage_cannot_supply_derived_jobs_or_invent_plan_gaps(self):
        doc=copy.deepcopy(self.doc);doc.pop('job_plan_artifact');doc['jobs']=copy.deepcopy(doc['declared_jobs']);doc['job_plan_gaps']=[]
        self.assertIsNone(verify_job_plan(doc,self.base))
        for jobs,gaps in ((self.doc['jobs'],[]),(doc['jobs'],[{'message':'unbound'}])):
            bad=copy.deepcopy(doc);bad['jobs']=jobs;bad['job_plan_gaps']=gaps
            with self.assertRaises(ValidationError):verify_job_plan(bad,self.base)


if __name__=='__main__':unittest.main()
