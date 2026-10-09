"""One local save prepares the approved Db2 MCP route, without live access."""
import json
import os
from pathlib import Path
from unittest.mock import patch
import unittest

import test_workstation_setup as workstation_tests
from test_db2_env import CERTIFICATE
from workbench.domain import ValidationError
from tools import db2_mcp_server as gateway


class Db2ConnectionSetupTests(unittest.IsolatedAsyncioTestCase):
    asyncSetUp = workstation_tests.WorkstationApiTests.asyncSetUp
    request = workstation_tests.WorkstationApiTests.request

    def choices(self, mode='gateway'):
        inactive = {key: None for key in ('host', 'port', 'database', 'location', 'driver', 'certificate_file', 'mcp_port', 'row_limit')}
        db2 = {'mode': mode, **inactive}
        if mode == 'gateway':
            db2.update(host='db2.example.invalid', port=5116, database='TESTDB', location='TESTLOC', driver='IBM DB2 ODBC DRIVER', mcp_port=8776, row_limit=250)
        return {'claude': True, 'db2_auth':'bearer_env', 'zowe': {'mode': 'off', 'host': None, 'port': None, 'config_file': None, 'schema_file': None}, 'db2': db2}

    async def configure(self, choices=None, **settings):
        return await self.request('/api/setup/workstation', 'POST', {'settings': {'source_mode': 'upload', **settings}, 'connections': choices or self.choices()})

    async def test_single_save_prepares_gateway_and_only_claude_mcp_binding(self):
        source = self.export / 'approved CA.cer'
        source.write_text(CERTIFICATE, encoding='utf-8')
        choices = self.choices(); choices['db2']['certificate_file'] = str(source)
        with patch('subprocess.Popen', side_effect=AssertionError('No CLI during Save')), patch('urllib.request.urlopen', side_effect=AssertionError('No network during Save')):
            status, result = await self.configure(choices)
        self.assertEqual(status, 200)
        self.assertEqual(result['settings']['db2_metadata_url'], 'http://127.0.0.1:8776/mcp')
        config = json.loads((self.root / '.migration/db2-config.json').read_bytes())
        self.assertEqual((config['host'], config['port'], config['database'], config['location'], config['max_rows']), ('db2.example.invalid', 5116, 'TESTDB', 'TESTLOC', 250))
        self.assertTrue(config['ssl']); self.assertEqual(config['credential_environment'], {'user': 'WB_DB2_USER', 'password': 'WB_DB2_PASSWORD'})
        self.assertEqual((self.root / 'certificates/DB2-CA.cert').read_bytes(), source.read_bytes())
        mcp = json.loads((self.root / '.mcp.json').read_bytes())
        self.assertEqual(mcp['mcpServers']['workbench-db2']['url'], result['settings']['db2_metadata_url'])
        self.assertEqual(mcp['mcpServers']['workbench-db2']['headers']['Authorization'],'Bearer ${WB_DB2_MCP_TOKEN}')
        self.assertEqual(set(mcp['mcpServers']),{'workbench-db2'})
        self.assertNotIn('inputs',mcp)
        self.assertFalse((self.root / '.claude/mcp.json').exists())
        command = next(item['command'] for item in result['connection_setup']['commands'] if item['id'] == 'db2_start')
        self.assertIn('--interactive', command); self.assertIn('--config', command); self.assertIn('--transport', command); self.assertIn('http', command)
        self.assertEqual(result['connection_setup']['connectivity'], 'UNVERIFIED')
        _, reloaded = await self.request('/api/setup/workstation')
        self.assertEqual(reloaded['connection_setup']['choices'], result['connection_setup']['choices'])

    async def test_missing_certificate_is_an_explicit_prerequisite(self):
        status, result = await self.configure()
        self.assertEqual(status, 200)
        self.assertIn('db2_certificate', [item['id'] for item in result['connection_setup']['remaining']])
        self.assertFalse(result['readiness']['connectivity_verified'])

    async def test_invalid_certificate_and_secret_fields_write_nothing(self):
        source = self.export / 'untrusted.cer'; source.write_text('not a certificate', encoding='utf-8')
        for field, value in [('certificate_file', str(source)), ('password', 'fictional private sentinel'), ('token', 'fictional private sentinel'), ('ssl', False), ('sql', 'DELETE FROM T')]:
            choices = self.choices(); choices['db2'][field] = value
            with self.subTest(field=field):
                status, response = await self.configure(choices)
                self.assertEqual(status, 400); self.assertNotIn('fictional private sentinel', json.dumps(response))
                self.assertFalse((self.root / '.migration/db2-config.json').exists())
                self.assertFalse((self.root / '.mcp.json').exists())

    async def test_existing_server_never_prepares_driver_configuration(self):
        status, result = await self.configure(self.choices('existing'), db2_metadata_url='https://approved.example.invalid/mcp')
        self.assertEqual(status, 200)
        self.assertFalse((self.root / '.migration/db2-config.json').exists())
        self.assertEqual(result['settings']['db2_metadata_url'], 'https://approved.example.invalid/mcp')

    async def test_off_retires_only_managed_binding_and_preserves_gateway_files(self):
        await self.configure(); path = self.root / '.migration/db2-config.json'; original = path.read_bytes()
        status, result = await self.configure(self.choices('off'), db2_metadata_url='https://discard.example.invalid/mcp')
        self.assertEqual(status, 200); self.assertIsNone(result['settings']['db2_metadata_url'])
        self.assertEqual(path.read_bytes(), original)
        self.assertNotIn('workbench-db2', json.loads((self.root / '.mcp.json').read_bytes())['mcpServers'])


    async def test_numeric_limits_empty_fields_and_port_collision_are_rejected(self):
        for field, value in [('port', True), ('port', 0), ('mcp_port', 65536), ('mcp_port', 8765),
                             ('row_limit', 500001), ('row_limit', True), ('host', 'https://bad.invalid'),
                             ('database', ''), ('location', 'bad\nlocation'), ('driver', None)]:
            choices = self.choices(); choices['db2'][field] = value
            with self.subTest(field=field, value=value):
                status, _ = await self.configure(choices)
                self.assertEqual(status, 400)
                self.assertFalse((self.root / '.migration/db2-config.json').exists())

    async def test_existing_requires_endpoint_and_inactive_fields_are_rejected(self):
        status, _ = await self.configure(self.choices('existing'))
        self.assertEqual(status, 400)
        choices = self.choices('off'); choices['db2']['host'] = 'unexpected.invalid'
        status, _ = await self.configure(choices)
        self.assertEqual(status, 400)
        choices = self.choices(); choices['claude'] = False
        status, _ = await self.configure(choices)
        self.assertEqual(status, 400)

    async def test_failed_save_restores_every_configuration_destination(self):
        from workbench.domain import atomic_bytes
        writes = 0
        def fail(path, payload):
            nonlocal writes
            writes += 1
            if writes == 3: raise OSError('fictional disk failure')
            atomic_bytes(path, payload)
        with patch('workbench.connection_setup.atomic_bytes', side_effect=fail):
            status, _ = await self.configure()
        self.assertEqual(status, 500)
        for name in ('certificates/DB2-CA.cert', '.migration/db2-config.json', '.mcp.json', '.migration/workstation.json', '.migration/connections.json'):
            self.assertFalse((self.root / name).exists(), name)

    async def test_concurrent_config_edit_is_preserved_and_blocks_other_writes(self):
        from workbench.connection_setup import _claude_plan
        path = self.root / '.migration/db2-config.json'
        concurrent = b'{"concurrent":"fictional operator change"}'
        def change(*args):
            plan = _claude_plan(*args)
            path.parent.mkdir(exist_ok=True); path.write_bytes(concurrent)
            return plan
        with patch('workbench.connection_setup._claude_plan', side_effect=change):
            status, _ = await self.configure()
        self.assertEqual(status, 400); self.assertEqual(path.read_bytes(), concurrent)
        self.assertFalse((self.root / '.mcp.json').exists())
        self.assertFalse((self.root / 'certificates/DB2-CA.cert').exists())

    async def test_changed_certificate_source_blocks_save_without_partial_writes(self):
        from workbench.db2_setup import prepare_db2
        source = self.export / 'selected.cer'; source.write_text(CERTIFICATE, encoding='utf-8')
        choices = self.choices(); choices['db2']['certificate_file'] = str(source)
        changed = b'fictional concurrent change'
        def change(*args, **kwargs):
            plan = prepare_db2(*args, **kwargs)
            source.write_bytes(changed)
            return plan
        with patch('workbench.db2_setup.prepare_db2', side_effect=change):
            status, _ = await self.configure(choices)
        self.assertEqual(status, 400); self.assertEqual(source.read_bytes(), changed)
        self.assertFalse((self.root / '.migration/db2-config.json').exists())
        self.assertFalse((self.root / 'certificates/DB2-CA.cert').exists())

    async def test_der_certificate_bytes_and_config_drift_are_accounted(self):
        import ssl
        source = self.export / 'approved.der'; raw = ssl.PEM_cert_to_DER_cert(CERTIFICATE)
        source.write_bytes(raw)
        choices = self.choices(); choices['db2']['certificate_file'] = str(source)
        status, _ = await self.configure(choices)
        self.assertEqual(status, 200); self.assertEqual((self.root / 'certificates/DB2-CA.cert').read_bytes(), raw)
        from types import SimpleNamespace
        from unittest.mock import Mock
        server = Mock()
        with patch.dict(os.environ, {}, clear=True), patch.dict('sys.modules', {'pyodbc': SimpleNamespace(drivers=lambda: ['IBM DB2 ODBC DRIVER'])}), \
             patch('sys.argv', ['server', '--transport', 'http', '--config', str(self.root / '.migration/db2-config.json'), '--port', '8776', '--interactive']), \
             patch('sys.stdin.isatty', return_value=True), patch('builtins.input', return_value='fictional'), \
             patch('getpass.getpass', side_effect=['fictional secret', 'fictional-token']), patch.object(gateway, 'create_server', return_value=server):
            gateway.main()
            server.run.assert_called_once()
            self.assertEqual(dict(os.environ), {})
        self.assertEqual((self.root / 'certificates/DB2-CA.cert').read_bytes(), raw)
        path = self.root / '.migration/db2-config.json'; config = json.loads(path.read_bytes())
        config['host'] = 'changed.invalid'; path.write_text(json.dumps(config), encoding='utf-8')
        _, result = await self.request('/api/setup/workstation')
        self.assertIn('db2_config', [item['id'] for item in result['connection_setup']['remaining']])
        self.assertNotIn('db2_config', [item['kind'] for item in result['connection_setup']['files'] if item['status'] == 'PREPARED'])

    async def test_certificate_private_keys_and_redirects_are_refused(self):
        source = self.export / 'bad.cer'
        for raw in (CERTIFICATE.encode() + b'-----BEGIN PRIVATE KEY-----\nfictional\n', b'', b'-----BEGIN CERTIFICATE-----\ninvalid\n-----END CERTIFICATE-----'):
            source.write_bytes(raw); choices = self.choices(); choices['db2']['certificate_file'] = str(source)
            status, _ = await self.configure(choices)
            self.assertEqual(status, 400)
        source.write_text(CERTIFICATE, encoding='utf-8')
        from workbench import setup
        real = setup.path_is_link
        with patch('workbench.setup.path_is_link', side_effect=lambda path: Path(path) == source or real(path)):
            choices = self.choices(); choices['db2']['certificate_file'] = str(source)
            status, _ = await self.configure(choices)
        self.assertEqual(status, 400)


class Db2InteractiveServerTests(unittest.TestCase):
    def test_interactive_server_requires_local_terminal_and_http(self):
        for arguments in (['--transport', 'stdio', '--interactive'], ['--transport', 'http', '--interactive']):
            with self.subTest(arguments=arguments), patch('sys.argv', ['db2_mcp_server.py', *arguments]), patch('sys.stdin.isatty', return_value=False), patch('builtins.input') as username, patch('getpass.getpass') as secret, patch.object(gateway, 'create_server') as server:
                with self.assertRaises(ValidationError): gateway.main()
                username.assert_not_called(); secret.assert_not_called(); server.assert_not_called()


    def configuration(self, directory):
        from workbench.db2_setup import initialize_db2
        result = initialize_db2(directory, location='TESTLOC', database='TESTDB', host='db2.invalid', port=5116)
        Path(result['certificate']).write_text(CERTIFICATE, encoding='utf-8')
        return Path(result['config_file'])

    def test_interactive_start_uses_fixed_mcp_security_and_restores_private_environment(self):
        import tempfile
        from types import SimpleNamespace
        with tempfile.TemporaryDirectory() as directory:
            config = self.configuration(directory); observed = {}
            def run(**kwargs):
                observed.update(kwargs)
                self.assertEqual(os.environ['WB_DB2_USER'], '0000123')
                self.assertEqual(os.environ['WB_DB2_PASSWORD'], 'fictional db2 secret')
                self.assertEqual(os.environ['WB_DB2_CONFIG'], str(config))
            server = SimpleNamespace(run=run)
            with patch.dict(os.environ, {}, clear=True), patch.dict('sys.modules', {'pyodbc': SimpleNamespace(drivers=lambda: ['IBM DB2 ODBC DRIVER'])}), \
                 patch('sys.argv', ['server', '--transport', 'http', '--config', str(config), '--port', '8776', '--interactive']), \
                 patch('sys.stdin.isatty', return_value=True), patch('builtins.input', return_value='0000123'), \
                 patch('getpass.getpass', side_effect=['fictional db2 secret', 'fictional-mcp-token']), \
                 patch.object(gateway, 'create_server', return_value=server) as create, patch.object(gateway, 'connect', side_effect=AssertionError('No mainframe startup read')):
                gateway.main()
                self.assertEqual(dict(os.environ), {})
            create.assert_called_once_with(search_root=config.parent / 'db2-search', workspace=config.parent.parent)
            self.assertEqual(observed['host'], '127.0.0.1'); self.assertEqual(observed['port'], 8776)
            self.assertEqual(observed['path'], '/mcp'); self.assertTrue(observed['host_origin_protection'])
            self.assertTrue(observed['json_response']); self.assertTrue(observed['stateless_http'])

    def test_missing_driver_certificate_and_interrupted_prompts_never_start_server(self):
        import tempfile
        from types import SimpleNamespace
        with tempfile.TemporaryDirectory() as directory:
            config = self.configuration(directory)
            arguments = ['server', '--transport', 'http', '--config', str(config), '--interactive']
            with patch.dict(os.environ, {}, clear=True), patch.dict('sys.modules', {'pyodbc': SimpleNamespace(drivers=lambda: [])}), patch('sys.argv', arguments), patch('sys.stdin.isatty', return_value=True), patch('getpass.getpass') as secret, patch.object(gateway, 'create_server') as create:
                with self.assertRaisesRegex(ValidationError, 'not registered'): gateway.main()
                secret.assert_not_called(); create.assert_not_called(); self.assertEqual(dict(os.environ), {})
            with patch.dict(os.environ, {}, clear=True), patch.dict('sys.modules', {'pyodbc': SimpleNamespace(drivers=lambda: ['IBM DB2 ODBC DRIVER'])}), patch('sys.argv', arguments), patch('sys.stdin.isatty', return_value=True), patch('builtins.input', side_effect=EOFError), patch.object(gateway, 'create_server') as create:
                with self.assertRaises(EOFError): gateway.main()
                create.assert_not_called(); self.assertEqual(dict(os.environ), {})
            (config.parent.parent / 'certificates/DB2-CA.cert').write_bytes(b'placeholder')
            with patch('sys.argv', arguments), patch('sys.stdin.isatty', return_value=True), patch('builtins.input') as username, patch.object(gateway, 'create_server') as create:
                with self.assertRaises(ValidationError): gateway.main()
                username.assert_not_called(); create.assert_not_called()


if __name__ == '__main__': unittest.main()
