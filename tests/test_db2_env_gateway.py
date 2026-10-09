"""Canonical z/OS .env configuration without reading operator credentials."""
import os
import json
import random
import subprocess
from types import SimpleNamespace
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

from workbench import db2_env
from workbench.domain import ValidationError
from tools import db2_mcp_server as gateway

from tests.test_db2_env import CERTIFICATE

CANONICAL = '''DB2_LOCATION_NAME=DEMOLOC
DB2_DATABASE=DEMOLOC
DB2_HOSTNAME=db2.example.invalid
DB2_PORT=5116
DB2_USERNAME="0000123"
DB2_PASSWORD='fictional space # dollar $HOME; brace }'
DB2_SSL_CONNECTION=true
DB2_SSL_SERVER_CERTIFICATE="certs/db2 test.cer"
'''


class CanonicalDb2EnvTests(unittest.TestCase):
    def setUp(self):
        scratch = Path(__file__).resolve().parents[1] / '.implementation/tmp'
        scratch.mkdir(parents=True, exist_ok=True)
        self.directory = tempfile.TemporaryDirectory(dir=scratch)
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name).resolve()
        self.env_file = self.root / 'db2.env'
        self.env_file.write_bytes(CANONICAL.replace('\n', '\r\n').encode())
        self.certificate = self.root / 'certs/db2 test.cer'
        self.certificate.parent.mkdir()
        self.certificate.write_text(CERTIFICATE)

    def test_canonical_eight_fields_are_literal_and_connection_is_private_tls(self):
        config = db2_env.settings({}, self.env_file)
        self.assertEqual(config.location, config.database)
        self.assertEqual(config.username, '0000123')
        self.assertEqual(config.password, 'fictional space # dollar $HOME; brace }')
        self.assertEqual(config.certificate, self.certificate)
        self.assertNotIn(config.password, repr(config))
        connection = db2_env.connection_string({}, self.env_file)
        self.assertIn('DATABASE={DEMOLOC}', connection)
        self.assertIn('SECURITY={SSL}', connection)
        self.assertIn('SSLClientHostnameValidation={Basic}', connection)
        self.assertIn('PWD={fictional space # dollar $HOME; brace }}}', connection)


    def test_matching_certificate_aliases_and_conflicts(self):
        self.env_file.write_text(CANONICAL + 'DB2_SSL_CERT_LOCATION="certs/db2 test.cer"\n')
        self.assertEqual(db2_env.settings({}, self.env_file).certificate, self.certificate)
        self.env_file.write_text(CANONICAL + 'DB2_SSL_CERT_LOCATION=certs/other.cer\n')
        with self.assertRaisesRegex(ValidationError, 'aliases'):
            db2_env.settings({}, self.env_file)
        with self.assertRaisesRegex(ValidationError, 'aliases'):
            db2_env.settings({'DB2_SSL_SERVER_CERTIFICATE':'one.cer', 'DB2_SSL_CERT_LOCATION':'two.cer'}, self.env_file)

    def test_shell_certificate_alias_overrides_file_without_fallback(self):
        config = db2_env.settings({'DB2_SSL_CERT_LOCATION':'certs/shell.cer'}, self.env_file)
        self.assertEqual(config.certificate, self.root / 'certs/shell.cer')
        with self.assertRaises(ValidationError):
            db2_env.settings({'DB2_SSL_SERVER_CERTIFICATE':''}, self.env_file)

    def test_canonical_location_database_equality_and_legacy_preservation(self):
        different = CANONICAL.replace('DB2_DATABASE=DEMOLOC', 'DB2_DATABASE=OTHERDB')
        self.env_file.write_text(different)
        with self.assertRaisesRegex(ValidationError, 'must equal'):
            db2_env.settings({}, self.env_file)
        self.env_file.write_text(different.replace('DB2_SSL_SERVER_CERTIFICATE','DB2_SSL_CERT_LOCATION'))
        self.assertEqual(db2_env.settings({}, self.env_file).database, 'OTHERDB')
        with self.assertRaisesRegex(ValidationError, 'must equal'):
            db2_env.settings({}, self.env_file, canonical=True)

    def test_blank_missing_credentials_and_invalid_certificate_errors_are_private(self):
        for key in ('DB2_USERNAME','DB2_PASSWORD'):
            lines=[line for line in CANONICAL.splitlines() if not line.startswith(key+'=')]
            self.env_file.write_text('\n'.join(lines)+'\n')
            with self.assertRaisesRegex(ValidationError, 'credentials') as failure:
                db2_env.connection_string({}, self.env_file, canonical=True)
            self.assertNotIn('fictional space', str(failure.exception))
            self.assertNotIn(str(self.env_file), str(failure.exception))
        self.env_file.write_text(CANONICAL)
        self.certificate.write_bytes(b'FICTIONAL_PRIVATE_CERTIFICATE_SENTINEL')
        with self.assertRaises(ValidationError) as failure:
            db2_env.connection_string({}, self.env_file, canonical=True)
        self.assertNotIn('FICTIONAL_PRIVATE_CERTIFICATE_SENTINEL', str(failure.exception))

    def test_randomized_literal_credentials_remain_unexpanded_and_brace_escaped(self):
        rng=random.Random(20261009)
        for number in range(64):
            value='fictional-'+str(number)+'-'+''.join(rng.choice('ab09 #$;{}()[]') for _ in range(40))
            lines=[line for line in CANONICAL.splitlines() if not line.startswith('DB2_PASSWORD=')]
            self.env_file.write_bytes(('\n'.join(lines)+'\nDB2_PASSWORD="'+value+'" # trailing comment\n').replace('\n','\r\n').encode())
            with self.subTest(number=number):
                self.assertEqual(db2_env.settings({},self.env_file,canonical=True).password,value)
                self.assertIn('PWD={'+value.replace('}','}}')+'}',db2_env.connection_string({},self.env_file,canonical=True))

    def test_alias_unknown_duplicate_and_env_limits_reject_with_generic_errors(self):
        for suffix in ('DB2_USERNAME=PRIVATE_DUPLICATE_SENTINEL\n','UNKNOWN_SECRET=PRIVATE_UNKNOWN_SENTINEL\n','DB2_SSL_SERVER_CERTIFICATE="unfinished\n'):
            self.env_file.write_text(CANONICAL+suffix)
            with self.assertRaises(ValidationError) as failure:
                db2_env.settings({},self.env_file,canonical=True)
            self.assertNotIn('PRIVATE_',str(failure.exception))
        self.env_file.write_text(CANONICAL)
        for values in ({'DB2_SSL_CONNECTION':'false'},{'DB2_PORT':'0'},{'DB2_PORT':'65536'},{'DB2_QUERY_ROW_LIMIT':'500001'},{'DB2_QUERY_ROW_LIMIT':'0'}):
            with self.subTest(values=values), self.assertRaises(ValidationError):
                db2_env.settings(values,self.env_file,canonical=True)

    def config_file(self, maximum=100, driver='IBM DB2 ODBC DRIVER'):
        path=self.root/'.migration/db2-config.json';path.parent.mkdir(exist_ok=True)
        path.write_text(json.dumps({'server_name':'demo','location':'STALELOC','database':'STALEDB','host':'stale.example.invalid','port':1,'ssl':True,'certificate':'certificates/DB2-CA.cert','driver':driver,'max_rows':maximum,'default_row_budget':min(maximum,100),'credential_environment':{'user':'WB_DB2_USER','password':'WB_DB2_PASSWORD'}}))
        return path

    def test_explicit_env_route_overrides_stale_legacy_connection_and_restores_state(self):
        observed={};before=os.environ.copy();raw=self.env_file.read_bytes()
        def run(**kwargs):
            observed.update(kwargs)
            self.assertIn('DATABASE={DEMOLOC}', gateway.connection_string())
            self.assertNotIn('STALE_ODBC_SENTINEL',gateway.connection_string())
            self.assertEqual(gateway.configured_row_limit(),500000)
        server=SimpleNamespace(run=run)
        private={'WB_DB2_CONFIG':'nonexistent-private-config','WB_DB2_ODBC_CONNECTION':'STALE_ODBC_SENTINEL'}
        with patch.dict(os.environ,private,clear=True),patch('sys.argv',['db2_mcp_server.py','--env-file',str(self.env_file),'--workspace',str(self.root)]),patch.object(gateway,'create_server',return_value=server) as create,patch.object(gateway,'connect',side_effect=AssertionError('No startup connection')):
            gateway.main()
            self.assertEqual(dict(os.environ),private)
            create.assert_called_once_with(search_root=None,workspace=self.root)
        self.assertEqual(observed['transport'],'stdio')
        self.assertIsNone(gateway._SELECTED_ENV_FILE)
        self.assertIsNone(gateway._SELECTED_CONFIG_FILE)
        self.assertEqual(self.env_file.read_bytes(),raw)
        self.assertEqual(dict(os.environ),before)

    def test_both_routes_keep_driver_and_stricter_config_row_cap(self):
        config=self.config_file(maximum=25,driver='Approved IBM Driver')
        self.env_file.write_text(CANONICAL+'DB2_QUERY_ROW_LIMIT=40\n')
        def run(**kwargs):
            self.assertIn('DRIVER={Approved IBM Driver}',gateway.connection_string())
            self.assertIn('HOSTNAME={db2.example.invalid}',gateway.connection_string())
            self.assertEqual(gateway.configured_row_limit(),25)
        with patch.dict(os.environ,{},clear=True),patch('sys.argv',['db2_mcp_server.py','--config',str(config),'--env-file',str(self.env_file)]),patch.object(gateway,'create_server',return_value=SimpleNamespace(run=run)):
            gateway.main()
        self.assertIsNone(gateway._SELECTED_ENV_FILE)

    def test_env_row_cap_can_be_lower_than_saved_config(self):
        config=self.config_file(maximum=25)
        self.env_file.write_text(CANONICAL+'DB2_QUERY_ROW_LIMIT=10\n')
        with patch.object(gateway,'_SELECTED_ENV_FILE',self.env_file),patch.object(gateway,'_SELECTED_CONFIG_FILE',config),patch.dict(os.environ,{},clear=True):
            self.assertEqual(gateway.configured_row_limit(),10)

    def test_interactive_missing_credentials_prompt_locally_and_never_rewrite_env(self):
        self.env_file.write_text(CANONICAL.replace('DB2_USERNAME="0000123"','DB2_USERNAME=').replace("DB2_PASSWORD='fictional space # dollar $HOME; brace }'",'DB2_PASSWORD='))
        config=self.config_file();original=self.env_file.read_bytes();calls={}
        def run(**kwargs):
            calls.update(kwargs)
            self.assertIn('UID={0000999}',gateway.connection_string())
            self.assertIn('PWD={fictional entered secret}',gateway.connection_string())
            self.assertEqual(gateway.configured_row_limit(),100)
        driver=SimpleNamespace(drivers=lambda:['IBM DB2 ODBC DRIVER'])
        with patch.dict(os.environ,{},clear=True),patch.dict(sys.modules,{'pyodbc':driver}),patch('sys.argv',['db2_mcp_server.py','--transport','http','--config',str(config),'--env-file',str(self.env_file),'--interactive']),patch('sys.stdin.isatty',return_value=True),patch('builtins.input',return_value='0000999') as username,patch('getpass.getpass',side_effect=['fictional entered secret','fictional-approved-token']) as secret,patch.object(gateway,'create_server',return_value=SimpleNamespace(run=run)),patch.object(gateway,'connect',side_effect=AssertionError('No startup connection')):
            gateway.main()
            username.assert_called_once();self.assertEqual(secret.call_count,2)
            self.assertEqual(dict(os.environ),{})
            self.assertTrue(all('VS Code' not in item.args[0] for item in secret.call_args_list))
        self.assertEqual(self.env_file.read_bytes(),original)
        self.assertEqual(calls['host'],'127.0.0.1')
        self.assertEqual(calls['transport'],'http')
        self.assertTrue(calls['host_origin_protection'])

    def test_interactive_populated_env_only_prompts_for_missing_mcp_token(self):
        with patch.dict(os.environ,{},clear=True),patch.dict(sys.modules,{'pyodbc':SimpleNamespace(drivers=lambda:['IBM DB2 ODBC DRIVER'])}),patch('sys.argv',['db2_mcp_server.py','--transport','http','--env-file',str(self.env_file),'--interactive']),patch('sys.stdin.isatty',return_value=True),patch('builtins.input') as username,patch('getpass.getpass',return_value='fictional-token') as secret,patch.object(gateway,'create_server',return_value=SimpleNamespace(run=lambda **kwargs:None)):
            gateway.main();username.assert_not_called();secret.assert_called_once()
            self.assertEqual(dict(os.environ),{})

    def test_invalid_tls_location_or_driver_stops_before_prompt_or_server(self):
        for modification,registered in ((('DB2_SSL_CONNECTION=true','DB2_SSL_CONNECTION=false'),True),(('DB2_DATABASE=DEMOLOC','DB2_DATABASE=DIFFERENT'),True),(None,False)):
            self.env_file.write_text(CANONICAL if modification is None else CANONICAL.replace(*modification))
            with patch.dict(os.environ,{},clear=True),patch.dict(sys.modules,{'pyodbc':SimpleNamespace(drivers=lambda:['IBM DB2 ODBC DRIVER'] if registered else [])}),patch('sys.argv',['db2_mcp_server.py','--transport','http','--env-file',str(self.env_file),'--interactive']),patch('sys.stdin.isatty',return_value=True),patch('builtins.input') as username,patch('getpass.getpass') as secret,patch.object(gateway,'create_server') as create:
                with self.assertRaises(ValidationError):gateway.main()
                username.assert_not_called();secret.assert_not_called();create.assert_not_called()
                self.assertIsNone(gateway._SELECTED_ENV_FILE)
                self.assertEqual(dict(os.environ),{})

    def test_noninteractive_missing_credentials_fails_without_prompts(self):
        self.env_file.write_text(CANONICAL.replace('DB2_USERNAME="0000123"','DB2_USERNAME='))
        with patch.dict(os.environ,{},clear=True),patch('sys.argv',['db2_mcp_server.py','--env-file',str(self.env_file)]),patch('builtins.input') as username,patch('getpass.getpass') as secret,patch.object(gateway,'create_server') as create:
            with self.assertRaises(ValidationError):gateway.main()
            username.assert_not_called();secret.assert_not_called();create.assert_not_called()
            self.assertEqual(dict(os.environ),{})

    def test_prompt_cancellation_restores_selected_paths_and_process_environment(self):
        self.env_file.write_text(CANONICAL.replace('DB2_USERNAME="0000123"','DB2_USERNAME='))
        config=self.config_file()
        with patch.dict(os.environ,{'WB_DB2_CONFIG':'old-private-config'},clear=True),patch.dict(sys.modules,{'pyodbc':SimpleNamespace(drivers=lambda:['IBM DB2 ODBC DRIVER'])}),patch('sys.argv',['db2_mcp_server.py','--transport','http','--config',str(config),'--env-file',str(self.env_file),'--interactive']),patch('sys.stdin.isatty',return_value=True),patch('builtins.input',side_effect=EOFError),patch.object(gateway,'create_server') as create:
            with self.assertRaises(EOFError):gateway.main()
            create.assert_not_called();self.assertEqual(dict(os.environ),{'WB_DB2_CONFIG':'old-private-config'})
            self.assertIsNone(gateway._SELECTED_ENV_FILE)
            self.assertIsNone(gateway._SELECTED_CONFIG_FILE)

    def test_explicit_env_missing_cannot_use_stale_complete_shell_settings(self):
        values=db2_env._parse(self.env_file.read_bytes())
        self.env_file.unlink()
        with self.assertRaises(ValidationError):
            db2_env.settings(values,self.env_file,canonical=True)

    def test_missing_saved_driver_is_rejected_before_prompt(self):
        config=self.config_file(driver=None)
        with patch.dict(os.environ,{},clear=True),patch('sys.argv',['db2_mcp_server.py','--transport','http','--config',str(config),'--env-file',str(self.env_file),'--interactive']),patch('sys.stdin.isatty',return_value=True),patch('builtins.input') as username,patch('getpass.getpass') as secret,patch.object(gateway,'create_server') as create:
            with self.assertRaises(ValidationError):gateway.main()
            username.assert_not_called();secret.assert_not_called();create.assert_not_called()

    def test_actual_cli_invalid_secret_emits_only_generic_startup_failure(self):
        self.env_file.write_text(CANONICAL.replace("DB2_PASSWORD='fictional space # dollar $HOME; brace }'",'DB2_PASSWORD="FICTIONAL_SECRET_SENTINEL\nunknown-private-part"'))
        result=subprocess.run([sys.executable,str(Path(gateway.__file__).resolve()),'--env-file',str(self.env_file)],env={'PATH':os.defpath},capture_output=True,text=True,timeout=20)
        self.assertEqual(result.returncode,2)
        self.assertEqual(result.stdout,'')
        self.assertIn('Db2 MCP startup blocked.',result.stderr)
        for value in ('FICTIONAL_SECRET_SENTINEL','unknown-private-part',str(self.env_file),'Traceback'):
            self.assertNotIn(value,result.stderr)

    def test_explicit_env_symlink_refused_without_prompt_or_server(self):
        link=self.root/'linked.env';link.symlink_to(self.env_file)
        with patch.dict(os.environ,{},clear=True),patch('sys.argv',['db2_mcp_server.py','--env-file',str(link)]),patch('builtins.input') as username,patch('getpass.getpass') as secret,patch.object(gateway,'create_server') as create:
            with self.assertRaises(ValidationError):gateway.main()
            username.assert_not_called();secret.assert_not_called();create.assert_not_called()



if __name__ == '__main__':
    unittest.main()
