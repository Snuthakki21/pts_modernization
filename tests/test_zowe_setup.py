import io
import json
from pathlib import Path
import tempfile
import unittest
from contextlib import redirect_stdout
from unittest.mock import patch

from workbench.domain import ValidationError
from workbench.zowe_setup import initialize_profile, main


class ZoweSetupTests(unittest.TestCase):
    def test_missing_host_creates_secure_declarations_without_credentials(self):
        with tempfile.TemporaryDirectory() as directory:
            result = initialize_profile(directory)
            config = json.loads((Path(directory) / 'zowe.config.json').read_text())
            base = config['profiles']['workbench_base']
            self.assertEqual(base['type'], 'base')
            self.assertEqual(base['secure'], ['user', 'password'])
            self.assertNotIn('host', base['properties'])
            self.assertNotIn('password', base['properties'])
            self.assertEqual(result['status'], 'NEEDS_HOST')
            self.assertEqual(result['connectivity'], 'UNVERIFIED')
            self.assertEqual(result['secure_command'], ['zowe', 'config', 'secure'])

    def test_merges_existing_profile_without_replacing_other_configuration(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'zowe.config.json'
            original = {'profiles': {'other': {'type': 'zosmf', 'properties': {'port': 8443}},
                                     'approved': {'type': 'base', 'properties': {'host': 'zos.example.invalid'}, 'secure': ['tokenValue']}},
                        'defaults': {'zosmf': 'other'}, 'autoStore': False, 'custom': {'keep': True}}
            path.write_text(json.dumps(original))
            result = initialize_profile(directory, profile='approved')
            config = json.loads(path.read_text())
            self.assertEqual(config['profiles']['other'], original['profiles']['other'])
            self.assertEqual(config['defaults']['zosmf'], 'other')
            self.assertEqual(config['custom'], original['custom'])
            self.assertFalse(config['autoStore'])
            self.assertEqual(config['profiles']['approved']['secure'], ['tokenValue', 'user', 'password'])
            self.assertEqual(result['environment']['WB_ZOWE_ZOSMF_PROFILE'], 'approved_zosmf')
            self.assertEqual(result['status'], 'READY_FOR_SECURE_INPUT')

    def test_existing_plaintext_credential_is_not_echoed_or_rewritten(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'zowe.config.json'
            content = json.dumps({'profiles': {'approved': {'type': 'base', 'properties': {'password': 'fictional-secret'}}}})
            path.write_text(content)
            with self.assertRaises(ValidationError) as failure:
                initialize_profile(directory, profile='approved')
            self.assertNotIn('fictional-secret', str(failure.exception))
            self.assertEqual(path.read_text(), content)

    def test_missing_config_is_local_only_and_never_authenticates(self):
        with tempfile.TemporaryDirectory() as directory, patch('workbench.connectors.subprocess.Popen') as process:
            result = initialize_profile(directory, host='zos.example.invalid', port=10443, profile='approved', user_config=True)
            self.assertTrue((Path(directory) / 'zowe.config.user.json').exists())
            self.assertEqual(result['secure_command'], ['zowe', 'config', 'secure', '--user-config'])
            self.assertEqual(result['credentials'], 'UNVERIFIED')
            process.assert_not_called()

    def test_conflicting_type_host_and_symlink_are_refused(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'zowe.config.json'
            path.write_text('{"profiles":{"approved":{"type":"zosmf","properties":{}}}}')
            with self.assertRaises(ValidationError): initialize_profile(directory, profile='approved')
            path.unlink()
            for host in ('https://host', 'user:pass@host', '--password', 'host\nsecret'):
                with self.assertRaises(ValidationError): initialize_profile(directory, host=host)
            target = Path(directory) / 'target.json'; target.write_text('{}'); path.symlink_to(target)
            with self.assertRaises(ValidationError): initialize_profile(directory)

    def test_cli_has_no_secret_argument_and_prints_only_safe_summary(self):
        with tempfile.TemporaryDirectory() as directory, redirect_stdout(io.StringIO()) as output:
            self.assertEqual(main(['--workspace', directory, '--profile', 'approved']), 0)
        summary = json.loads(output.getvalue())
        self.assertEqual(summary['status'], 'NEEDS_HOST')
        with redirect_stdout(io.StringIO()), patch('sys.stderr', new=io.StringIO()):
            with self.assertRaises(SystemExit): main(['--password', 'fictional-secret'])

    def test_guided_profile_prompts_only_nonsecret_fields(self):
        with tempfile.TemporaryDirectory() as directory, patch('workbench.zowe_setup.sys.stdin.isatty',return_value=True), \
             patch('builtins.input',side_effect=['approved','approved_zosmf','zos.example.invalid','10443']) as prompts, \
             redirect_stdout(io.StringIO()) as output:
            self.assertEqual(main(['--workspace',directory,'--interactive']),0)
            config=json.loads((Path(directory)/'zowe.config.json').read_text())
        self.assertEqual(config['profiles']['approved']['properties']['host'],'zos.example.invalid')
        self.assertEqual(config['profiles']['approved']['properties']['port'],10443)
        self.assertEqual(len(prompts.call_args_list),4)
        self.assertFalse(any('password' in call.args[0].lower() or 'username' in call.args[0].lower() for call in prompts.call_args_list))
        self.assertEqual(json.loads(output.getvalue())['connectivity'],'UNVERIFIED')

    def test_guided_setup_requires_tty_before_any_file_write(self):
        with tempfile.TemporaryDirectory() as directory, patch('workbench.zowe_setup.sys.stdin.isatty',return_value=False),redirect_stdout(io.StringIO()):
            self.assertEqual(main(['--workspace',directory,'--interactive']),2)
            self.assertFalse((Path(directory)/'zowe.config.json').exists())

    def test_secure_prompts_use_argv_and_never_claim_live_connectivity(self):
        with tempfile.TemporaryDirectory() as directory, patch('workbench.zowe_setup.sys.stdin.isatty',return_value=True), \
             patch('workbench.zowe_setup.subprocess.call',return_value=0) as secure,redirect_stdout(io.StringIO()) as output:
            self.assertEqual(main(['--workspace',directory,'--secure','--host','zos.example.invalid']),0)
        self.assertEqual(secure.call_args.args[0],['zowe','config','secure']);self.assertFalse(secure.call_args.kwargs['shell'])
        self.assertEqual(json.loads(output.getvalue())['connectivity'],'UNVERIFIED')


if __name__ == '__main__': unittest.main()
