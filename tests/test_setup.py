"""Operator setup must preserve the enterprise host roles and saved preferences."""
import json
from pathlib import Path
import tempfile
import unittest

from workbench.setup import inspect_setup, save_setup


class LocalClaudeSetupTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def test_unanswered_setup_recommends_local_claude_without_claiming_consent(self):
        result = inspect_setup(self.root, environ={})
        self.assertEqual(result['configuration']['assistant_mode'], 'claude_files')
        question = next(q for q in result['questions'] if q['id'] == 'llm')
        self.assertIsNone(question['answer'])
        self.assertEqual(question['status'], 'UNANSWERED')
        self.assertEqual(question['options'][0]['value'], 'copilot_chat')
        self.assertIn('Claude Code', question['options'][0]['label'])
        self.assertIn('end-to-end', question['options'][0]['label'])

    def test_saved_v1_copilot_choice_routes_to_local_claude_without_rewriting_state(self):
        choices = {'source': 'upload', 'manifest': 'ready', 'zowe': 'not_needed',
                   'db2': 'not_needed', 'llm': 'copilot_chat', 'reviewer': 'available'}
        path = self.root / '.migration/setup.json'
        path.parent.mkdir()
        original = json.dumps({'version': 1, 'answers': choices}).encode()
        path.write_bytes(original)
        result = inspect_setup(self.root, environ={})
        self.assertEqual(result['configuration']['assistant_mode'], 'claude_files')
        self.assertEqual(result['answers']['llm'], 'copilot_chat')
        self.assertEqual(result['readiness']['status'], 'READY_FOR_INTAKE')
        self.assertEqual(path.read_bytes(), original)
        action = next(q['action'] for q in result['questions'] if q['id'] == 'llm')
        self.assertIn('Claude Code', action)
        self.assertIn('approved MCP', action)
        self.assertNotIn('Copilot', action)
        self.assertIn('retriev', action)
        self.assertIn('testing', action)
        self.assertNotIn('submit source-grounded suggestions', action)

    def test_explicit_alternatives_keep_existing_provider_and_consent_gates(self):
        deterministic = save_setup(self.root, {'llm': 'disabled'}, environ={})
        self.assertEqual(deterministic['configuration']['assistant_mode'], 'deterministic')
        blocked = save_setup(self.root, {'llm': 'opt_in'}, environ={})
        self.assertEqual(blocked['configuration']['assistant_mode'], 'opt_in')
        question = next(q for q in blocked['questions'] if q['id'] == 'llm')
        self.assertEqual(question['status'], 'NEEDS_ACTION')
        self.assertIn('WB_ALLOW_SOURCE_EGRESS=true', question['action'])
        self.assertFalse(blocked['configuration']['source_egress_approved'])


if __name__ == '__main__':
    unittest.main()
