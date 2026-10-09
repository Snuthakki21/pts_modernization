"""Private file-first Db2 setup and fixed Claude stdio binding boundaries."""
import json
import os
from pathlib import Path
import random
import tempfile
import unittest
from unittest.mock import patch
from workbench import db2_env, db2_setup
from workbench.domain import ValidationError, encode, sha
from tests.test_db2_env import CERTIFICATE

FIELDS = '''DB2_LOCATION_NAME=TESTLOC
DB2_DATABASE=TESTLOC
DB2_HOSTNAME=db2.example.invalid
DB2_PORT=5116
DB2_USERNAME=fictional-user
DB2_PASSWORD="fictional # $HOME } value"
DB2_SSL_CONNECTION=true
DB2_SSL_SERVER_CERTIFICATE=certificates/DB2-CA.cert
ZOWE_ENVIRONMENT=dev
ZOWE_DEV_HOST=dev.example.invalid
ZOWE_DEV_PORT=443
ZOWE_PROD_HOST=prod.example.invalid
ZOWE_PROD_PORT=443
ZOWE_TSO_ACCOUNT=fictional-account
ZOWE_TSO_CODE_PAGE=1047
ZOWE_TSO_LOGON_PROCEDURE=FICTION
ZOWE_CA_CERTIFICATE=certificates/ZOWE-CA.pem
ZOWE_USERNAME=fictional-zowe-user
ZOWE_PASSWORD='fictional zowe # $HOME'
'''

class TextDb2SetupTests(unittest.TestCase):
    def setUp(self):
        scratch = Path(__file__).resolve().parents[1] / '.implementation/tmp'
        scratch.mkdir(parents=True, exist_ok=True)
        self.directory = tempfile.TemporaryDirectory(dir=scratch)
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name).resolve()
        self.env_file = self.root / '.env'
        self.env_file.write_text(FIELDS)
        self.cert = self.root / 'certificates/DB2-CA.cert'
        self.cert.parent.mkdir()
        self.cert.write_text(CERTIFICATE)

    def test_shared_env_is_literal_and_only_exact_zowe_keys_are_ignored_by_db2(self):
        values = db2_env.read_workspace_env(self.env_file)
        config = db2_env.settings({}, self.env_file, canonical=True)
        self.assertEqual(values['ZOWE_PASSWORD'], 'fictional zowe # $HOME')
        self.assertEqual(config.password, 'fictional # $HOME } value')
        with self.assertRaises(ValidationError):
            db2_env._parse(FIELDS.encode())
        for suffix in ('ZOWE_ARBITRARY_PRIVATE=secret\n', 'ZOWE_USERNAME=secret\n', 'WB_ASSIST_MODE=cloud_files\n'):
            self.env_file.write_text(FIELDS + suffix)
            with self.assertRaises(ValidationError) as failure:
                db2_env.settings({}, self.env_file, canonical=True)
            self.assertNotIn('secret', str(failure.exception))

    def test_preparation_creates_exact_no_token_binding_and_preserves_env_ca(self):
        before = {self.env_file: self.env_file.read_bytes(), self.cert: self.cert.read_bytes()}
        with patch('urllib.request.urlopen', side_effect=AssertionError('No network')), patch('subprocess.Popen', side_effect=AssertionError('No client or second writer')):
            result = db2_setup.prepare_environment(self.root)
        document = json.loads((self.root / '.mcp.json').read_bytes())
        entry = document['mcpServers']['workbench-db2']
        self.assertEqual(entry, db2_setup.stdio_binding(self.root))
        self.assertEqual(entry['type'], 'stdio')
        self.assertEqual(entry['args'][-4:], ['--env-file', str(self.env_file), '--workspace', str(self.root)])
        self.assertNotIn('env', entry)
        self.assertNotIn('token', json.dumps(document).lower())
        self.assertNotIn('fictional-user', json.dumps(document))
        self.assertNotIn('fictional #', json.dumps(result))
        self.assertEqual(result['connectivity'], 'UNVERIFIED')
        self.assertEqual(result['authentication'], 'UNVERIFIED')
        self.assertEqual(before, {path: path.read_bytes() for path in before})

    def test_preparation_is_idempotent_and_preserves_unrelated_saved_server(self):
        path = self.root / '.mcp.json'
        unrelated = {'type': 'http', 'url': 'https://approved.example.invalid/mcp', 'headers': {'X-Private': 'fictional-sensitive-sentinel'}}
        path.write_bytes(encode({'mcpServers': {'other-approved': unrelated}}))
        db2_setup.prepare_environment(self.root)
        first = path.read_bytes()
        result = db2_setup.prepare_environment(self.root)
        self.assertEqual(path.read_bytes(), first)
        self.assertEqual(json.loads(first)['mcpServers']['other-approved'], unrelated)
        self.assertNotIn('fictional-sensitive-sentinel', json.dumps(result))

    def test_conflicting_managed_binding_is_never_overwritten(self):
        path = self.root / '.mcp.json'
        original = encode({'mcpServers': {'workbench-db2': {'type': 'stdio', 'command': 'malicious.exe', 'args': []}}})
        path.write_bytes(original)
        with self.assertRaisesRegex(ValidationError, 'binding'):
            db2_setup.prepare_environment(self.root)
        self.assertEqual(path.read_bytes(), original)

    def test_missing_or_misplaced_ca_reports_exact_local_action_before_config_write(self):
        for content in (FIELDS.replace('certificates/DB2-CA.cert', '.migration/DB2-CA.cert'), FIELDS.replace('certificates/DB2-CA.cert', '../secret.cert')):
            self.env_file.write_text(content)
            with self.assertRaises(ValidationError):
                db2_setup.prepare_environment(self.root)
            self.assertFalse((self.root / '.mcp.json').exists())
        self.env_file.write_text(FIELDS)
        self.cert.unlink()
        with self.assertRaisesRegex(ValidationError, 'certificates/DB2-CA.cert'):
            db2_setup.prepare_environment(self.root)
        self.assertFalse((self.root / '.mcp.json').exists())

    def test_invalid_certificate_private_key_and_empty_ca_are_not_prepared(self):
        for content in (b'', b'fictional-private-sentinel', CERTIFICATE.encode() + b'-----BEGIN PRIVATE KEY-----\nfictional-secret\n-----END PRIVATE KEY-----\n'):
            self.cert.write_bytes(content)
            with self.assertRaises(ValidationError) as failure:
                db2_setup.prepare_environment(self.root)
            self.assertNotIn('fictional-', str(failure.exception))
            self.assertFalse((self.root / '.mcp.json').exists())

    def test_credentials_are_required_only_at_stdio_start_not_to_prepare(self):
        self.env_file.write_text(FIELDS.replace('DB2_USERNAME=fictional-user', 'DB2_USERNAME=').replace('DB2_PASSWORD="fictional # $HOME } value"', 'DB2_PASSWORD='))
        result = db2_setup.prepare_environment(self.root)
        self.assertEqual(result['missing_credentials'], ['DB2_USERNAME', 'DB2_PASSWORD'])
        self.assertEqual(result['status'], 'ACTION_REQUIRED')
        with self.assertRaisesRegex(ValidationError, 'credentials'):
            db2_env.connection_string({}, self.env_file, canonical=True)

    def test_selected_env_must_be_workspace_root_not_migration_or_external(self):
        selected = self.root / '.migration/.env'
        selected.parent.mkdir()
        selected.write_text(FIELDS)
        with self.assertRaisesRegex(ValidationError, 'workspace root'):
            db2_setup.prepare_environment(self.root, selected)
        self.assertFalse((self.root / '.mcp.json').exists())

    def test_runtime_selection_excludes_preserved_servers_and_validates_exact_command(self):
        binding = db2_setup.stdio_binding(self.root)
        source = {'mcpServers': {'workbench-db2': binding, 'preserved': {'command': 'never-activated.exe'}}}
        self.assertEqual(db2_setup.validate_managed_mcp(source, self.root), {'mcpServers': {'workbench-db2': binding}})
        for mutate in (
            lambda entry: entry.update(command='python'),
            lambda entry: entry.update(env={'DB2_PASSWORD': 'fictional-secret'}),
            lambda entry: entry['args'].append('--interactive'),
            lambda entry: entry['args'].__setitem__(0, str(self.root / 'other.py')),
            lambda entry: entry['args'].__setitem__(-1, str(self.root.parent)),
        ):
            entry = json.loads(json.dumps(binding)); mutate(entry)
            with self.assertRaises(ValidationError) as failure:
                db2_setup.validate_managed_mcp({'mcpServers': {'workbench-db2': entry}}, self.root)
            self.assertNotIn('fictional-secret', str(failure.exception))

    def test_http_compatibility_remains_authenticated_or_approved_remote_oauth(self):
        entries = (
            {'type': 'http', 'url': 'https://approved.example.invalid/mcp'},
            {'type': 'http', 'url': 'http://127.0.0.1:8766/mcp', 'headers': {'Authorization': 'Bearer ${WB_DB2_MCP_TOKEN}'}},
        )
        for entry in entries:
            self.assertEqual(db2_setup.validate_managed_mcp({'mcpServers': {'workbench-db2': entry}}, self.root), {'mcpServers': {'workbench-db2': entry}})
        for entry in (
            {'type': 'http', 'url': 'http://remote.example.invalid/mcp'},
            {'type': 'http', 'url': 'http://127.0.0.1:8766/mcp'},
            {'type': 'http', 'url': 'https://user:secret@approved.example.invalid/mcp'},
            {'type': 'http', 'url': 'https://approved.example.invalid/mcp?token=secret'},
            {'type': 'http', 'url': 'https://approved.example.invalid/mcp', 'headers': {'Authorization': 'secret'}},
        ):
            with self.assertRaises(ValidationError) as failure:
                db2_setup.validate_managed_mcp({'mcpServers': {'workbench-db2': entry}}, self.root)
            self.assertNotIn('secret', str(failure.exception))

    def test_64_distinct_literal_credentials_never_enter_managed_binding_or_result(self):
        rng = random.Random(20261010); witnesses = set()
        for index in range(64):
            secret = 'synthetic-secret-' + str(index) + '-' + ''.join(rng.choice('ab09 #$;{}()[]') for _ in range(40))
            self.env_file.write_text(FIELDS.replace('fictional # $HOME } value', secret))
            result = db2_setup.prepare_environment(self.root)
            binding = json.loads((self.root / '.mcp.json').read_bytes())
            self.assertNotIn(secret, json.dumps(result))
            self.assertNotIn(secret, json.dumps(binding))
            self.assertEqual(db2_env.settings({}, self.env_file, canonical=True).password, secret)
            self.assertEqual(db2_setup.validate_managed_mcp(binding, self.root), binding)
            witnesses.add(secret)
        self.assertEqual(len(witnesses), 64)

    def test_shared_env_read_does_not_modify_shell_environment(self):
        before = dict(os.environ)
        db2_env.read_workspace_env(self.env_file)
        self.assertEqual(dict(os.environ), before)

    def test_explicit_managed_http_migration_requires_hash_bound_owner_receipt(self):
        path = self.root / '.mcp.json'
        entry = {'type':'http','url':'http://127.0.0.1:8766/mcp','headers':{'Authorization':'Bearer ${WB_DB2_MCP_TOKEN}'}}
        path.write_bytes(encode({'mcpServers': {'workbench-db2': entry}}))
        self.env_file.write_text(FIELDS)
        original=path.read_bytes()
        with self.assertRaises(ValidationError):db2_setup.prepare_environment(self.root, replace_managed_http=True)
        self.assertEqual(path.read_bytes(),original)
        state=self.root/'.migration/connections.json';state.parent.mkdir()
        from workbench.connection_setup import default_choices
        state.write_bytes(encode({'version':2,'choices':default_choices({'db2_metadata_url':entry['url']}),'managed':{'workbench-db2':sha(encode(entry))}}))
        result=db2_setup.prepare_environment(self.root, replace_managed_http=True)
        self.assertEqual(json.loads(path.read_bytes())['mcpServers']['workbench-db2'],db2_setup.stdio_binding(self.root))
        self.assertEqual(result['replaced_managed_http'],True)
        self.assertEqual(json.loads(state.read_bytes())['managed']['workbench-db2'],sha(encode(db2_setup.stdio_binding(self.root))))

    def test_optional_registered_driver_is_literal_and_part_of_exact_binding(self):
        driver = 'IBM DB2 ODBC DRIVER - APPROVEDCOPY'
        result = db2_setup.prepare_environment(self.root, driver=driver)
        document = json.loads((self.root / '.mcp.json').read_bytes())
        self.assertEqual(document['mcpServers']['workbench-db2']['args'][3:5], ['--driver', driver])
        self.assertEqual(db2_setup.validate_managed_mcp(document, self.root), document)
        self.assertEqual(result['driver'], driver)
        for invalid in ('', 'x' * 254, '${PRIVATE_DRIVER}', 'driver\nsecret'):
            with self.assertRaises(ValidationError): db2_setup.stdio_binding(self.root, invalid)

    def test_runtime_file_filters_saved_bindings_and_never_reads_env(self):
        db2_setup.prepare_environment(self.root)
        config=self.root/'.mcp.json'
        document=json.loads(config.read_bytes())
        document['mcpServers']['other']={'command':'do-not-run.exe','env':{'PRIVATE':'synthetic-sensitive-sentinel'}}
        config.write_bytes(encode(document));before=config.read_bytes()
        self.env_file.write_bytes(b'PRIVATE_RAW_NEVER_READ=synthetic-sensitive-sentinel')
        output=self.root/'.migration/claude-runtime-example.json'
        result=db2_setup._write_runtime(self.root,output)
        self.assertEqual(json.loads(output.read_bytes()), {'mcpServers':{'workbench-db2':document['mcpServers']['workbench-db2']}})
        self.assertEqual(config.read_bytes(),before)
        self.assertNotIn('synthetic-sensitive-sentinel',json.dumps(result))
        with self.assertRaises(ValidationError):db2_setup._write_runtime(self.root,output)
        for path in (self.root/'outside.json', self.root/'.migration/other-runtime.json'):
            with self.assertRaises(ValidationError):db2_setup._write_runtime(self.root,path)

    def test_offline_is_explicit_and_never_overwrites_existing_live_binding(self):
        self.env_file.unlink();self.cert.unlink()
        result=db2_setup.prepare_offline(self.root)
        self.assertEqual(result['connectivity'],'NOT_REQUESTED')
        self.assertEqual(json.loads((self.root/'.mcp.json').read_bytes()),{'mcpServers':{}})
        binding=db2_setup.stdio_binding(self.root)
        original=encode({'mcpServers':{'workbench-db2':binding}})
        (self.root/'.mcp.json').write_bytes(original)
        with self.assertRaises(ValidationError):db2_setup.prepare_offline(self.root)
        self.assertEqual((self.root/'.mcp.json').read_bytes(),original)

    def test_cli_specific_ca_error_is_safe_and_names_required_folder(self):
        import io
        from contextlib import redirect_stdout
        self.cert.write_bytes(b'synthetic-sensitive-sentinel')
        output=io.StringIO()
        with redirect_stdout(output):
            code=db2_setup.main(['--workspace',str(self.root),'--env-file',str(self.env_file)])
        self.assertEqual(code,2)
        result=json.loads(output.getvalue())
        self.assertIn('certificates/DB2-CA.cert',result['message'])
        self.assertNotIn('synthetic-sensitive-sentinel',output.getvalue())
        self.assertNotIn('fictional #',output.getvalue())

    def test_gateway_explicit_driver_and_stale_config_cannot_override_shared_env(self):
        import sys
        from types import SimpleNamespace
        from tools import db2_mcp_server as gateway
        observed={}
        def run(**arguments):
            observed.update(arguments)
            self.assertIn('DRIVER={IBM DB2 ODBC DRIVER - APPROVEDCOPY}',gateway.connection_string())
            self.assertEqual(gateway.configured_row_limit(),500000)
        original=self.env_file.read_bytes()
        environment={'WB_DB2_CONFIG':'invalid-private-legacy-config','WB_DB2_ODBC_CONNECTION':'synthetic-sensitive-sentinel',
                     'DB2_DATABASE':'STALE_INVALID_DATABASE','DB2_PASSWORD':'stale-sensitive-sentinel','DB2_SSL_CONNECTION':'false'}
        args=['db2_mcp_server.py','--transport','stdio','--driver','IBM DB2 ODBC DRIVER - APPROVEDCOPY','--env-file',str(self.env_file),'--workspace',str(self.root)]
        with patch.dict(os.environ,environment,clear=True),patch('sys.argv',args),patch.object(gateway,'create_server',return_value=SimpleNamespace(run=run)),patch('builtins.input',side_effect=AssertionError('No stdin prompts')),patch('getpass.getpass',side_effect=AssertionError('No token or password prompts')),patch.object(gateway,'connect',side_effect=AssertionError('No startup network')):
            gateway.main()
            self.assertEqual(dict(os.environ),environment)
        self.assertEqual(observed['transport'],'stdio')
        self.assertIsNone(gateway._SELECTED_DRIVER_NAME)
        self.assertEqual(self.env_file.read_bytes(),original)

    def test_failed_file_publication_preserves_existing_mcp_and_ownership_receipt(self):
        path=self.root/'.mcp.json'
        original=encode({'mcpServers':{'other-approved':{'type':'http','url':'https://approved.example.invalid/mcp'}}})
        path.write_bytes(original)
        with patch.object(db2_setup,'atomic_bytes',side_effect=OSError('synthetic-write-failure')):
            with self.assertRaises(OSError):db2_setup.prepare_environment(self.root)
        self.assertEqual(path.read_bytes(),original)

    def test_symlink_config_and_certificate_are_rejected_without_following(self):
        target=self.root/'.migration/synthetic-private-file';target.parent.mkdir()
        target.write_bytes(b'synthetic-sensitive-sentinel')
        self.cert.unlink()
        self.cert.symlink_to(target)
        with self.assertRaises(ValidationError):db2_setup.prepare_environment(self.root)
        self.cert.unlink();self.cert.write_text(CERTIFICATE)
        config=self.root/'.mcp.json';config.symlink_to(target)
        with self.assertRaises(ValidationError):db2_setup.prepare_environment(self.root)
        self.assertEqual(target.read_bytes(),b'synthetic-sensitive-sentinel')

    def test_64_distinct_registered_driver_bindings_validate_exact_arguments(self):
        rng=random.Random(20261011);witnesses=set()
        for number in range(64):
            driver='IBM DB2 ODBC DRIVER - COPY'+str(number)+'-'+str(rng.randrange(10**8,10**9))
            entry=db2_setup.stdio_binding(self.root,driver)
            self.assertEqual(db2_setup.validate_stdio_binding(entry,self.root)['driver'],driver)
            changed=json.loads(json.dumps(entry));changed['args'][4]=driver+' altered'
            self.assertEqual(db2_setup.validate_stdio_binding(changed,self.root)['driver'],driver+' altered')
            # Driver names are literal configuration, never shell commands; the
            # fixed program and workspace must still match regardless of name.
            changed['command']='arbitrary-program.exe'
            with self.assertRaises(ValidationError):db2_setup.validate_stdio_binding(changed,self.root)
            witnesses.add(driver)
        self.assertEqual(len(witnesses),64)

    def test_real_stdio_sdk_lists_only_typed_protected_tools_from_shared_env(self):
        import asyncio
        import sys
        from fastmcp import Client
        from fastmcp.client.transports import StdioTransport
        from tools import db2_mcp_server as gateway
        async def run():
            transport=StdioTransport(command=sys.executable,args=[str(Path(gateway.__file__).absolute()),'--transport','stdio','--env-file',str(self.env_file),'--workspace',str(self.root)])
            async with Client(transport) as client:
                tools=await client.list_tools()
                self.assertEqual({tool.name for tool in tools},{'db2_list_schemas','db2_list_tables','db2_describe_table','db2_export_snapshot_to_inbox'})
                self.assertTrue(all(tool.annotations.read_only_hint for tool in tools))
        asyncio.run(run())


if __name__ == '__main__':unittest.main()
