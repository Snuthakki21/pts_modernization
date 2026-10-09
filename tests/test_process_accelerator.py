"""Synthetic accelerator boundaries; no live host access or human approvals."""
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from workbench.coordinator import Coordinator
from workbench.domain import ValidationError
from test_workflow import MANIFEST
from test_source import COBOL

class ProcessAcceleratorTests(unittest.TestCase):
    def test_default_prepare_uses_endeavor_before_remote_retrieval(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);export=root/'Endeavor';export.mkdir()
            (export/'ELIGIBLE.cbl').write_text(COBOL)
            (export/'JOBA.jcl').write_text("//JOBA JOB (TEST),'FICTIONAL'\n//S010 EXEC PGM=ELIGIBLE\n")
            c=Coordinator(root)
            try:
                doc=c.prepare_process(MANIFEST)
                self.assertEqual(set(doc['source_files']),{'ELIGIBLE.cbl','JOBA.jcl'})
                self.assertEqual(doc['source_origin'],{'kind':'folder','location':str(export)})
                self.assertFalse(doc['packet_issued'])
            finally:c.close()

    def test_explicit_retrieve_preserves_empty_intake_even_with_local_export(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);(root/'Endeavor').mkdir()
            (root/'Endeavor'/'ELIGIBLE.cbl').write_text(COBOL)
            c=Coordinator(root)
            try:self.assertEqual(c.prepare_process(MANIFEST,{})['source_files'],{})
            finally:c.close()

    def test_input_scaffold_preserves_operator_files_and_is_idempotent(self):
        from workbench.workspace_inputs import initialize_inputs
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);(root/'Process.md').write_text('operator prose\n')
            first=initialize_inputs(root);second=initialize_inputs(root)
            self.assertEqual((root/'Process.md').read_text(),'operator prose\n')
            for rel in ('Endeavor','certificates','supplemental/JCL','supplemental/JCLPlus','supplemental/PROCConverted','supplemental/Copybooks','supplemental/ControlCards'):
                self.assertTrue((root/rel).is_dir(),rel)
            self.assertFalse(second['created'])
            from workbench.layout import validate_workspace
            self.assertEqual(validate_workspace(root),[])

    def test_input_scaffold_never_creates_credentials_or_certificate_bytes(self):
        from workbench.workspace_inputs import initialize_inputs
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);initialize_inputs(root)
            self.assertFalse((root/'.env').exists())
            self.assertEqual(list((root/'certificates').iterdir()),[])
            self.assertEqual((root/'Process.md').read_bytes(),(Path(__file__).resolve().parents[1]/'examples/process-specific.md').read_bytes())

    def test_input_scaffold_rejects_invalid_existing_destination(self):
        from workbench.workspace_inputs import initialize_inputs
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);(root/'certificates').write_text('not a directory')
            with self.assertRaises(ValidationError):initialize_inputs(root)
            self.assertFalse((root/'Process.md').exists())

    def test_process_template_route_uses_one_public_owner(self):
        from fastapi.testclient import TestClient
        from workbench.api import create_app
        with tempfile.TemporaryDirectory() as tmp:
            app=create_app(tmp)
            try:
                with TestClient(app,base_url='http://127.0.0.1:8765') as client:
                    result=client.get('/api/process-template')
                    self.assertEqual(result.status_code,200)
                    self.assertIn('Process.md',result.headers['content-disposition'])
                    self.assertEqual(result.content,(Path(__file__).resolve().parents[1]/'examples/process-specific.md').read_bytes())
            finally:app.state.coordinator.close()

    def test_refresh_rederives_jobs_and_preserves_the_previous_immutable_plan(self):
        from workbench.lineage import derive_job_plan
        from workbench.domain import sha
        import json
        process='Process ID: refresh-plan\nProcess name: Fictional refresh\n## Jobs\n1. JOBA\n'
        files={'JOBA.jcl':"//JOBA JOB (TEST),'FICTIONAL'\n//S010 EXEC PGM=ELIGIBLE\n",'ELIGIBLE.cbl':COBOL}
        def prior_adapter(*args):
            plan=derive_job_plan(*args)
            plan['gaps']=[{'reason':'Prior adapter lacks a verified source card','path':'JOBA.jcl','line':2,'status':'UNVERIFIED'}]
            plan['complete']=False
            return plan
        with tempfile.TemporaryDirectory() as tmp:
            c=Coordinator(tmp)
            try:
                doc=c.create(process,files,assistant_mode='claude_files',requirements_selection=True)
                c.start(doc['id'])
                with patch('workbench.lineage.derive_job_plan',side_effect=prior_adapter):c.advance(doc['id'])
                doc=c.ledger.get(doc['id']);old=doc['job_plan_artifact'];original=c.artifact(doc['id'],old).read_bytes()
                view=c.requirements_view(doc['id'])
                c.save_requirements(doc['id'],{'catalog_hash':view['catalog_hash'],'revision':view['revision'],'excluded_ids':[],'saved_by':'Fictional test operator'})
                c.advance(doc['id'])
                self.assertEqual(c.ledger.get(doc['id'])['status'],'WAITING_COPILOT')
                c.refresh_analysis(doc['id']);c.advance(doc['id']);new=c.ledger.get(doc['id'])
                self.assertNotEqual(new['job_plan_artifact'],old)
                self.assertIn(old,new['artifacts']);self.assertEqual(c.artifact(doc['id'],old).read_bytes(),original)
                self.assertEqual(new['artifact_hashes'][old],sha(original));self.assertEqual(new['job_plan_gaps'],[])
                self.assertTrue(json.loads(c.artifact(doc['id'],new['job_plan_artifact']).read_bytes())['complete'])
                self.assertEqual(new['declared_jobs'],doc['declared_jobs']);self.assertFalse(new['packet_issued'])
                c.manifest_integrity(new)
            finally:c.close()

    def test_plain_process_errors_identify_the_missing_template_field(self):
        from workbench.intake import parse_manifest
        for text,message in (('# Notes only','Process ID'),('Process ID: simple\n','Process name'),('Process ID: simple\nProcess name: Example\n','Jobs')):
            with self.subTest(message=message),self.assertRaisesRegex(ValidationError,message):parse_manifest(text)

    def test_text_setup_is_optional_in_new_process_guide(self):
        with tempfile.TemporaryDirectory() as tmp:
            c=Coordinator(tmp)
            try:
                process='Process ID: simple-guide\nProcess name: Synthetic guide\n## Jobs\n1. JOBA\n'
                doc=c.prepare_process(process,{'JOBA.jcl':"//JOBA JOB (TEST),'FICTIONAL'\n//S010 EXEC PGM=ELIGIBLE\n",'ELIGIBLE.cbl':COBOL})
                c.start(doc['id']);c.advance(doc['id']);guide=c.process_guide(doc['id'])
                source_steps=[step for step in guide['steps'] if step['id'] in ('setup','process','retrieve')]
                self.assertEqual([step['id'] for step in source_steps],['process','retrieve'])
                self.assertTrue(all(step['state']=='complete' for step in source_steps));self.assertFalse(guide['setup']['saved'])
            finally:c.close()

    def test_fresh_online_process_uses_the_same_text_setup_and_compact_guide(self):
        with tempfile.TemporaryDirectory() as tmp:
            c=Coordinator(tmp)
            try:
                process='Process ID: online-guide\nProcess name: Synthetic screen\n| Transaction | Program | Mapset | Map |\n| --- | --- | --- | --- |\n| T001 | ELIGIBLE | | |\n'
                doc=c.prepare_process(process,{})
                guide=c.process_guide(doc['id'])
                self.assertEqual(doc.get('accelerator_contract_version'),1)
                self.assertNotIn('setup',[step['id'] for step in guide['steps']])
                self.assertEqual(doc['transactions'][0]['id'],'T001')
                self.assertFalse(doc['packet_issued'])
                c.manifest_integrity(doc)
            finally:c.close()
