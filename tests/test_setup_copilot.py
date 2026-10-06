import tempfile
from pathlib import Path
import unittest
from unittest.mock import patch

from workbench.setup import inspect_setup, save_setup

READY = {'source':'upload','manifest':'ready','zowe':'not_needed','db2':'not_needed','llm':'copilot_chat','reviewer':'available'}


class CopilotSetupTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def test_copilot_is_recommended_without_inferred_operator_answer(self):
        result = inspect_setup(self.root, environ={})
        question = next(item for item in result['questions'] if item['id'] == 'llm')
        self.assertIsNone(question['answer'])
        self.assertEqual(question['options'][0]['value'], 'copilot_chat')
        self.assertIn('Recommended', question['options'][0]['label'])
        self.assertEqual(result['configuration']['assistant_mode'], 'copilot_chat')

    def test_copilot_choice_needs_no_endpoint_and_makes_no_network_call(self):
        with patch('urllib.request.build_opener', side_effect=AssertionError('No network during setup')):
            result = save_setup(self.root, READY, environ={})
        self.assertEqual(result['readiness']['status'], 'READY_FOR_INTAKE')
        self.assertFalse(result['configuration']['llm_configured'])
        self.assertFalse(result['configuration']['source_egress_approved'])
        question = next(item for item in result['questions'] if item['id'] == 'llm')
        self.assertIn('lineage', question['action'])
        self.assertIn('Unknown', question['action'])
        self.assertEqual(inspect_setup(self.root, environ={})['answers']['llm'], 'copilot_chat')

    def test_legacy_choices_remain_valid_and_require_their_original_gates(self):
        disabled = save_setup(self.root, {**READY, 'llm':'disabled'}, environ={})
        self.assertEqual(disabled['configuration']['assistant_mode'], 'deterministic')
        self.assertEqual(disabled['readiness']['status'], 'READY_FOR_INTAKE')
        provider = save_setup(self.root, {**READY, 'llm':'opt_in'}, environ={})
        self.assertEqual(provider['configuration']['assistant_mode'], 'opt_in')
        self.assertEqual(provider['next_step'], 'llm')

    def test_invalid_paired_zowe_alias_cannot_claim_configuration(self):
        env = {'WB_ZOWE_PROFILE':'workbench_base', 'WB_ZOWE_ZOSMF_PROFILE':'bad profile'}
        with patch('workbench.setup.shutil.which', return_value='/approved/zowe'):
            result = save_setup(self.root, {**READY, 'zowe':'configured'}, environ=env)
        self.assertFalse(result['configuration']['zowe_configured'])
        self.assertEqual(result['next_step'], 'zowe')


if __name__ == '__main__': unittest.main()
