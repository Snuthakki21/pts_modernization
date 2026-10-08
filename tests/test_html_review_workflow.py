"""Fictional returns exercise the real quota, knowledge, coverage and report gates."""
from pathlib import Path
import json
import unittest
from workbench.domain import ValidationError, sha
from workbench.review import render_html_packet
from workbench.runner import import_return,bundle_process,wait_for_process
import test_workflow

class HTMLReviewWorkflowTests(unittest.TestCase):
    setUp=test_workflow.WorkflowTests.setUp
    create=test_workflow.WorkflowTests.create

    def issued(self):
        self.create();self.c.start('process-a');self.c.advance('process-a')
        return json.loads(self.c.artifact('process-a','review/packet.json').read_bytes())

    def returned(self,packet,answer='Yes',commentary=''):
        response={'version':1,'kind':'SME_HTML_RETURN','process_id':packet['process_id'],
                  'packet_hash':packet['packet_hash'],'source_snapshot':packet['source_snapshot'],
                  'reviewer':'Fictional HTML reviewer','items':[{'id':item['id'],'answer':answer,'correction':commentary} for item in packet['items']]}
        return render_html_packet(packet,response)

    def test_html_single_return_survives_knowledge_coverage_report_bundle_and_tamper(self):
        packet=self.issued();raw=self.returned(packet)
        self.c.import_answers('process-a',raw,'Fictional HTML reviewer')
        self.assertEqual(self.c.ledger.get('process-a')['answers']['return_format'],'html')
        preserved=self.c.process_root('process-a')/'input/sme-return.html'
        self.assertEqual(preserved.read_bytes(),raw)
        self.assertFalse((preserved.parent/'sme-return.xlsx').exists())
        self.c.advance('process-a');self.c.advance('process-a')
        doc=self.c.ledger.get('process-a');self.assertEqual(doc['status'],'COMPLETED')
        self.c.review_integrity(doc)
        self.assertEqual(import_return(self.c,'process-a',preserved,'Fictional HTML reviewer'),doc)
        import zipfile
        with zipfile.ZipFile(bundle_process(self.c,'process-a')) as archive:
            self.assertEqual(archive.read('input/sme-return.html'),raw)
            self.assertNotIn('input/sme-return.xlsx',archive.namelist())
        self.assertTrue((self.root/'knowledge/records.json').is_file())
        preserved.write_bytes(raw+b'changed')
        with self.assertRaisesRegex(ValidationError,'changed'):self.c.review_integrity(self.c.ledger.get('process-a'))

    def test_blank_answers_are_preserved_unresolved_without_second_round(self):
        packet=self.issued();raw=self.returned(packet,'')
        self.c.import_answers('process-a',raw,'Fictional HTML reviewer')
        self.c.advance('process-a');self.c.advance('process-a')
        doc=self.c.ledger.get('process-a')
        self.assertEqual(doc['status'],'COMPLETED_WITH_BLOCKERS')
        self.assertTrue(all(item['answer']=='Unanswered' for item in doc['answers']['items'].values()))
        self.assertTrue(doc['packet_imported'])
        with self.assertRaises(ValidationError):self.c.import_answers('process-a',self.returned(packet),'Fictional HTML reviewer')

    def test_html_correction_is_exact_gap_evidence_not_implicit_approval(self):
        packet=self.issued();raw=self.returned(packet,'Yes','Fictional correction: do not assume product-wide employee matching')
        self.c.import_answers('process-a',raw,'Fictional HTML reviewer')
        self.c.advance('process-a');self.c.advance('process-a')
        doc=self.c.ledger.get('process-a');self.assertEqual(doc['status'],'COMPLETED_WITH_BLOCKERS')
        comparison=self.c.program_comparison('process-a',status='gaps')
        refs={ref for gate in comparison['process_gates'] for ref in gate['evidence']}
        refs.update(ref for rule in comparison['rules'] for gate in rule['gaps']+rule['program_gates'] for ref in gate.get('evidence',[]))
        self.assertIn('input/sme-return.html',refs);self.assertNotIn('input/sme-return.xlsx',refs)

    def test_runner_detects_exact_html_inbox_and_rejects_two_returns(self):
        packet=self.issued();raw=self.returned(packet)
        inbox=self.c.process_root('process-a')/'input/sme-return-inbox.html';inbox.write_bytes(raw)
        doc,timed_out=wait_for_process(self.c,'process-a',timeout=10,reviewer='Fictional HTML reviewer')
        self.assertFalse(timed_out);self.assertTrue(doc['packet_imported'])
        self.assertEqual(doc['answers']['return_hash'],sha(raw))

    def test_wrong_attribution_and_changed_shell_do_not_consume_quota(self):
        packet=self.issued();raw=self.returned(packet)
        for content,name in [(raw,'Different reviewer'),(raw.replace(b'Process review',b'Changed shell'),'Fictional HTML reviewer')]:
            with self.assertRaises(ValidationError):self.c.import_answers('process-a',content,name)
            self.assertFalse(self.c.ledger.get('process-a')['packet_imported'])
        self.assertFalse((self.c.process_root('process-a')/'input/sme-return.html').exists())

if __name__=='__main__':unittest.main()
