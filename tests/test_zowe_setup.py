import io
import json
from pathlib import Path
import tempfile
import unittest
from contextlib import redirect_stdout
from unittest.mock import patch

from workbench.domain import ValidationError
from workbench.zowe_setup import import_project_config, initialize_profile, main


def multiple_profiles():
    """Fictional counterpart to the supplied multi-service project structure."""
    def service(kind, host, port, secure=None, **properties):
        value = {'type': kind, 'properties': {'host': host, 'port': port, **properties}}
        if secure is not None:
            value['secure'] = secure
        return value

    secure = ['user', 'password']
    return {
        '$schema': './zowe.schema.json',
        'profiles': {
            'zosmf_development': service('zosmf', 'dev.example.invalid', 443, secure,
                                         protocol='https', rejectUnauthorized=False),
            'zosmf_secondary': service('zosmf', 'prod.example.invalid', 443,
                                       rejectUnauthorized=False),
            'zosmf_service': service('zosmf', 'dev.example.invalid', 443, secure,
                                     rejectUnauthorized=False),
            'zosmf_production': service('zosmf', 'prod.example.invalid', 443,
                                        rejectUnauthorized=False),
            'tso': {'type': 'tso', 'properties': {'account': 'TEST001', 'codePage': '1047',
                                                 'logonProcedure': 'TESTPROC'}, 'secure': []},
            'ssh': service('ssh', 'ssh.example.invalid', 1149, secure),
            'base': service('base', 'gateway.example.invalid', 7554,
                            ['user', 'password', 'tokenValue'], rejectUnauthorized=False,
                            tokenType='apimlAuthenticationToken'),
            'base_apiml': service('base', 'gateway.example.invalid', 7554, ['tokenValue'],
                                  tokenType='apimlAuthenticationToken'),
            'endevor_development': service('endevor', 'endevor.example.invalid', 1857, secure,
                                           protocol='https', basePath='EndevorService/api/v2',
                                           rejectUnauthorized=False, reportDir='.'),
            'endevor_location': {'type': 'endevor-location', 'properties': {
                'instance': 'ENDEVOR', 'environment': 'PROD', 'system': 'TEST', 'stageNumber': '1'}},
        },
        'defaults': {'zosmf': 'zosmf_development', 'tso': 'tso', 'ssh': 'ssh', 'base': 'base',
                     'endevor': 'endevor_development', 'endevor-location': 'endevor_location'},
        'autoStore': True,
    }


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
             patch('workbench.zowe_setup.zowe_command',side_effect=lambda command, env: command), \
             patch('workbench.zowe_setup.subprocess.call',return_value=0) as secure,redirect_stdout(io.StringIO()) as output:
            self.assertEqual(main(['--workspace',directory,'--secure','--host','zos.example.invalid']),0)
        self.assertEqual(secure.call_args.args[0],['zowe','config','secure']);self.assertFalse(secure.call_args.kwargs['shell'])
        self.assertEqual(json.loads(output.getvalue())['connectivity'],'UNVERIFIED')

    def test_exact_import_preserves_ten_profiles_schema_bytes_and_is_idempotent(self):
        with tempfile.TemporaryDirectory() as directory, patch('workbench.zowe_setup.subprocess.call') as secure:
            root = Path(directory).resolve()
            source, destination = root / 'selected', root / 'workspace'
            source.mkdir()
            destination.mkdir()
            original = multiple_profiles()
            config_bytes = (json.dumps(original, indent=4) + '\n').replace('\n', '\r\n').encode()
            # Property names in a schema describe credentials; they are not stored credentials.
            schema_bytes = b'{ "type": "object", "properties": { "password": {"type": "string"} } }\n'
            (source / 'config.json').write_bytes(config_bytes)
            (source / 'schema.json').write_bytes(schema_bytes)
            first = import_project_config(destination, source / 'config.json', source / 'schema.json')
            second = import_project_config(destination, source / 'config.json', source / 'schema.json')
            self.assertEqual(first, second)
            self.assertEqual((destination / 'zowe.config.json').read_bytes(), config_bytes)
            self.assertEqual((destination / 'zowe.schema.json').read_bytes(), schema_bytes)
            imported = json.loads((destination / 'zowe.config.json').read_bytes())
            self.assertEqual(len(imported['profiles']), 10)
            self.assertEqual(imported, original)
            self.assertFalse(imported['profiles']['zosmf_development']['properties']['rejectUnauthorized'])
            self.assertNotIn('secure', imported['profiles']['zosmf_secondary'])
            self.assertEqual(imported['profiles']['base_apiml']['secure'], ['tokenValue'])
            self.assertEqual(first['credentials'], 'UNVERIFIED')
            self.assertEqual(first['connectivity'], 'UNVERIFIED')
            self.assertTrue(first['content_preserved'])
            secure.assert_not_called()

    def test_exact_import_conflicting_schema_does_not_partially_install_config(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            source, destination = root / 'selected', root / 'workspace'
            source.mkdir()
            destination.mkdir()
            (source / 'config.json').write_text(json.dumps(multiple_profiles()))
            (source / 'schema.json').write_text('{"type":"object"}')
            original = b'{"description":"preserve this existing schema"}\n'
            (destination / 'zowe.schema.json').write_bytes(original)
            with self.assertRaisesRegex(ValidationError, 'existing different project file'):
                import_project_config(destination, source / 'config.json', source / 'schema.json')
            self.assertFalse((destination / 'zowe.config.json').exists())
            self.assertEqual((destination / 'zowe.schema.json').read_bytes(), original)

    def test_exact_import_conflicting_config_is_preserved(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            source, destination = root / 'selected', root / 'workspace'
            source.mkdir()
            destination.mkdir()
            (source / 'config.json').write_text(json.dumps(multiple_profiles()))
            (source / 'schema.json').write_text('{}')
            original = b'{"profiles":{"existing":{"type":"base"}}}\n'
            (destination / 'zowe.config.json').write_bytes(original)
            with self.assertRaises(ValidationError):
                import_project_config(destination, source / 'config.json', source / 'schema.json')
            self.assertEqual((destination / 'zowe.config.json').read_bytes(), original)
            self.assertFalse((destination / 'zowe.schema.json').exists())

    def test_exact_import_rejects_nested_inline_credentials_without_echoing_values(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            source, destination = root / 'selected', root / 'workspace'
            source.mkdir()
            destination.mkdir()
            for key in ('user', 'password', 'tokenValue', 'certKeyFile'):
                with self.subTest(key=key):
                    document = multiple_profiles()
                    document['profiles']['base']['profiles'] = {
                        'child': {'type': 'base', 'properties': {key: 'fictional-sensitive-value'}}}
                    content = json.dumps(document).encode()
                    (source / 'config.json').write_bytes(content)
                    with self.assertRaises(ValidationError) as failure:
                        import_project_config(destination, source / 'config.json')
                    self.assertNotIn('fictional-sensitive-value', str(failure.exception))
                    self.assertEqual((source / 'config.json').read_bytes(), content)
                    self.assertFalse((destination / 'zowe.config.json').exists())

    def test_exact_import_user_config_selection_preserves_project_config(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            source, destination = root / 'selected', root / 'workspace'
            source.mkdir()
            destination.mkdir()
            content = (json.dumps(multiple_profiles(), indent=2) + '\n').encode()
            (source / 'config.json').write_bytes(content)
            original = b'{"profiles":{},"defaults":{}}\n'
            (destination / 'zowe.config.json').write_bytes(original)
            result = import_project_config(destination, source / 'config.json', user_config=True)
            self.assertEqual((destination / 'zowe.config.json').read_bytes(), original)
            self.assertEqual((destination / 'zowe.config.user.json').read_bytes(), content)
            self.assertEqual(result['files'], [str(destination / 'zowe.config.user.json')])


if __name__ == '__main__': unittest.main()
