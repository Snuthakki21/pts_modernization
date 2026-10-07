"""Knowledge changes cannot rewrite a process or its one human review."""
import json
from pathlib import Path
import tempfile
import unittest

from workbench.coordinator import Coordinator
from workbench.coverage import build_coverage
from workbench.domain import ValidationError, encode, sha
from workbench.layout import validate_workspace
from test_source import COBOL
from test_workflow import MANIFEST


class KnowledgeWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name);self.c=Coordinator(self.root)
        self.addCleanup(self.c.close)

    def test_snapshot_is_frozen_before_start_and_custom_edits_do_not_change_packet(self):
        doc=self.c.create(MANIFEST,{'ELIGIBLE.cbl':COBOL})
        pinned=encode(doc['mainframe_knowledge'])
        self.assertEqual((self.c.process_root(doc['id'])/'analysis/mainframe-knowledge.json').read_bytes(),pinned)
        # An invalid future catalog may block future intake, never mutate a prior run.
        (self.root/'knowledge').mkdir(exist_ok=True)
        (self.root/'knowledge/application-knowledge.json').write_text('{bad json')
        self.c.start(doc['id']);self.c.advance(doc['id'])
        doc=self.c.ledger.get(doc['id']);self.assertEqual(doc['status'],'WAITING_SME')
        self.assertEqual(encode(doc['mainframe_knowledge']),pinned)
        packet=json.loads(self.c.artifact(doc['id'],'review/packet.json').read_bytes())
        context=json.loads(packet['context'])
        self.assertIn('ELIGIBLE.cbl',context['file_classifications'])
        self.assertEqual(context['mainframe_knowledge_sha256'],sha(pinned))
        self.assertTrue({'G_FILE_TYPES','G_UTILITIES','G_NATIVE_DATA','G_NATIVE_RUNTIME'} <= {i['id'] for i in packet['items']})
        with self.assertRaises(ValidationError):
            self.c.create(MANIFEST.replace('process-a','process-b'),{'ELIGIBLE.cbl':COBOL})
        self.assertFalse(self.c.process_root('process-b').exists())

    def test_changed_frozen_catalog_prevents_start_and_credit(self):
        doc=self.c.create(MANIFEST,{'ELIGIBLE.cbl':COBOL})
        path=self.c.process_root(doc['id'])/'analysis/mainframe-knowledge.json'
        path.write_bytes(path.read_bytes()+b' ')
        with self.assertRaisesRegex(ValidationError,'knowledge changed'):self.c.start(doc['id'])
        coverage=build_coverage(self.c.ledger.get(doc['id']),self.root)
        self.assertIn('knowledge',json.dumps(coverage).lower())
        self.assertFalse(any(row['disposition'] in ('mapped_verified','platform_replaced_verified') for row in coverage['rows']))

    def test_ambiguous_source_paths_are_rejected_before_intake(self):
        for sources in ({'ELIGIBLE.cbl':COBOL,'eligible.CBL':COBOL},
                        {'FILE':'a','file/child':'b'},
                        {'./ELIGIBLE.cbl':COBOL},
                        {'A//ELIGIBLE.cbl':COBOL},
                        {'caf\u00e9.cbl':COBOL,'cafe\u0301.cbl':COBOL}):
            with self.subTest(paths=list(sources)),self.assertRaises(ValidationError):self.c.create(MANIFEST,sources)
        self.assertEqual(self.c.ledger.list(),[])

    def test_visible_catalog_placement_is_allowed_but_scattered_notes_are_not(self):
        knowledge=self.root/'knowledge';knowledge.mkdir()
        for name in ('mainframe-catalog.json','application-knowledge.json','README.md'):(knowledge/name).write_text('{}')
        self.assertEqual(validate_workspace(self.root),[])
        (knowledge/'one-rule.md').write_text('misplaced')
        self.assertTrue(validate_workspace(self.root))

    def test_line_capacity_and_binary_source_are_rejected_before_intake(self):
        from workbench.limits import MAX_SOURCE_LINES
        for sources in ({'empty.txt':'\n'*(MAX_SOURCE_LINES+1)}, {'A':'\n'*(MAX_SOURCE_LINES//2+1),'B':'\n'*(MAX_SOURCE_LINES//2+1)}, {'binary.cbl':'\x00'}):
            with self.subTest(paths=list(sources)),self.assertRaises(ValidationError):self.c.create(MANIFEST,sources)
        self.assertEqual(self.c.ledger.list(),[])

    def test_optional_provider_receives_bounded_frozen_classification_context(self):
        from types import SimpleNamespace
        calls=[]
        from workbench.provider import empty_usage_summary
        self.c.provider=SimpleNamespace(usage_summary=empty_usage_summary,analyze=lambda source,prompt: calls.append(source) or {'analysis':{'questions':[],'assumptions':[]}})
        doc=self.c.create(MANIFEST,{'ELIGIBLE.cbl':COBOL})
        self.c.start(doc['id']);self.c.advance(doc['id'])
        self.assertEqual(len(calls),1)
        self.assertIn('UNVERIFIED_CONTEXT_NOT_CONVERSION_PROOF',calls[0])
        self.assertIn('cobol_program',calls[0]);self.assertLessEqual(len(calls[0]),16000)

    def test_frequent_control_check_is_small_and_still_observes_durable_pause(self):
        from unittest.mock import patch
        from workbench.coordinator import StageInterrupted
        doc=self.c.create(MANIFEST,{'ELIGIBLE.cbl':COBOL})
        doc=self.c.start(doc['id']);doc['_active_stage']='QUEUED_ANALYSIS'
        with patch.object(self.c.ledger,'get',side_effect=AssertionError('full document read')):
            controls=self.c.checkpoint(doc,persist=False)
        self.assertNotIn('mainframe_knowledge',controls);self.assertNotIn('runs',controls)
        self.c.control(doc['id'],'pause')
        with self.assertRaises(StageInterrupted):self.c.checkpoint(doc,persist=False)
        self.assertEqual(self.c.ledger.get(doc['id'])['status'],'PAUSED')
