"""Text-first Zowe preparation using fictional values; no live mainframe access."""
from contextlib import redirect_stdout
import io
import json
from pathlib import Path
import random
import ssl
import tempfile
import unittest
from unittest.mock import patch

from jsonschema import Draft202012Validator
from workbench.domain import ValidationError
from workbench import zowe_setup
from tests.test_db2_env import CERTIFICATE


BASE = '''ZOWE_ENVIRONMENT=dev
ZOWE_DEV_HOST=dev.example.invalid
ZOWE_DEV_PORT=10443
ZOWE_PROD_HOST=prod.example.invalid
ZOWE_PROD_PORT=20443
ZOWE_TSO_ACCOUNT=00001234
ZOWE_TSO_CODE_PAGE=1047
ZOWE_TSO_LOGON_PROCEDURE=TESTPROC
ZOWE_CA_CERTIFICATE=certificates/ZOWE-CA.pem
ZOWE_USERNAME="0000123"
ZOWE_PASSWORD='fictional space # dollar $HOME; $(never-run)'
DB2_LOCATION_NAME=TESTLOC
DB2_DATABASE=TESTLOC
DB2_HOSTNAME=db2.example.invalid
DB2_PORT=5116
DB2_USERNAME=
DB2_PASSWORD=
DB2_SSL_CONNECTION=true
DB2_SSL_SERVER_CERTIFICATE=certificates/DB2-CA.cert
'''


class ZoweEnvironmentSetupTests(unittest.TestCase):
    def setUp(self):
        scratch = Path(__file__).resolve().parents[1] / '.implementation/tmp'
        scratch.mkdir(parents=True, exist_ok=True)
        self.temporary = tempfile.TemporaryDirectory(dir=scratch)
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name).resolve()
        self.env_file = self.root / '.env'
        self.env_file.write_text(BASE)
        self.certificate = self.root / 'certificates/ZOWE-CA.pem'
        self.certificate.parent.mkdir()
        self.certificate.write_text(CERTIFICATE)

    def set_value(self, key, value):
        lines = self.env_file.read_text().splitlines()
        self.env_file.write_text('\n'.join(key+'='+value if line.startswith(key+'=') else line for line in lines)+'\n')

    def prepare(self):
        return zowe_setup.initialize_environment(self.root)

    def test_clean_profiles_schema_and_selected_defaults_without_inline_credentials(self):
        with patch('workbench.zowe_setup.subprocess.call') as live:
            result = self.prepare()
        config = json.loads((self.root/'zowe.config.json').read_bytes())
        schema = json.loads((self.root/'zowe.schema.json').read_bytes())
        Draft202012Validator.check_schema(schema)
        Draft202012Validator(schema).validate(config)
        self.assertEqual(set(config['profiles']), {'project_base','DevPlex','ProdPlex','tso'})
        self.assertEqual(config['profiles']['project_base']['secure'], ['user','password'])
        self.assertEqual(config['profiles']['project_base']['properties'], {})
        self.assertEqual(config['defaults'], {'base':'project_base','zosmf':'DevPlex','tso':'tso'})
        for name in ('DevPlex','ProdPlex'):
            self.assertEqual(config['profiles'][name]['type'], 'zosmf')
            self.assertEqual(config['profiles'][name]['properties']['protocol'], 'https')
            self.assertIs(config['profiles'][name]['properties']['rejectUnauthorized'], True)
        self.assertEqual(config['profiles']['tso']['properties']['account'], '00001234')
        self.assertEqual(config['profiles']['tso']['properties']['codePage'], '1047')
        self.assertEqual(result['connectivity'], 'UNVERIFIED')
        self.assertEqual(result['credentials'], 'UNVERIFIED')
        self.assertEqual(result['environment'], {'WB_ZOWE_PROFILE':'project_base','WB_ZOWE_ZOSMF_PROFILE':'DevPlex'})
        self.assertEqual(result['secure_command'], ['zowe','config','secure'])
        live.assert_not_called()
        combined = (self.root/'zowe.config.json').read_text()+json.dumps(result)
        self.assertNotIn('0000123"', combined)
        self.assertNotIn('fictional space', combined)

    def test_selected_production_and_optional_unused_endpoint(self):
        self.set_value('ZOWE_ENVIRONMENT','prod')
        self.set_value('ZOWE_DEV_HOST','')
        self.set_value('ZOWE_DEV_PORT','')
        result = self.prepare()
        config = json.loads((self.root/'zowe.config.json').read_bytes())
        self.assertNotIn('DevPlex',config['profiles'])
        self.assertEqual(result['zosmf_profile'],'ProdPlex')

    def test_missing_named_fields_and_partial_endpoint_fail_before_publication(self):
        for key in ('ZOWE_DEV_HOST','ZOWE_DEV_PORT','ZOWE_TSO_ACCOUNT','ZOWE_TSO_CODE_PAGE',
                    'ZOWE_TSO_LOGON_PROCEDURE','ZOWE_CA_CERTIFICATE'):
            with self.subTest(key=key):
                self.env_file.write_text(BASE)
                self.set_value(key,'')
                with self.assertRaises(ValidationError): self.prepare()
                self.assertFalse((self.root/'zowe.config.json').exists())
        self.env_file.write_text(BASE)
        self.set_value('ZOWE_PROD_PORT','')
        with self.assertRaisesRegex(ValidationError,'ZOWE_PROD'): self.prepare()

    def test_missing_certificate_reports_exact_relative_file_and_no_secrets(self):
        self.certificate.unlink()
        with self.assertRaisesRegex(ValidationError,'ZOWE_CA_CERTIFICATE') as failure: self.prepare()
        self.assertNotIn('fictional space',str(failure.exception))
        self.assertFalse((self.root/'zowe.config.json').exists())

    def test_env_and_certificate_paths_cannot_escape_or_follow_links(self):
        for value in ('../outside.pem','.migration/ca.pem','C:/private/ca.pem',
                      '/private/ca.pem','certificates\\ca.pem'):
            with self.subTest(value=value):
                self.env_file.write_text(BASE)
                self.set_value('ZOWE_CA_CERTIFICATE',value)
                with self.assertRaises(ValidationError): self.prepare()
        self.env_file.write_text(BASE)
        external=self.root/'.implementation/tmp/external.env';external.parent.mkdir(parents=True)
        external.write_text(BASE)
        with self.assertRaises(ValidationError): zowe_setup.initialize_environment(self.root, external)
        self.certificate.unlink()
        self.certificate.symlink_to(external)
        with self.assertRaises(ValidationError): self.prepare()

    def test_der_private_key_invalid_and_oversize_certificates_are_rejected(self):
        for content in (ssl.PEM_cert_to_DER_cert(CERTIFICATE), b'-----BEGIN PRIVATE KEY-----\nprivate\n',
                        b'not a certificate', b'x'*(1024*1024+1)):
            with self.subTest(content_length=len(content)):
                self.certificate.write_bytes(content)
                with self.assertRaises(ValidationError): self.prepare()
                self.assertFalse((self.root/'zowe.config.json').exists())

    def test_existing_config_and_schema_conflicts_are_preserved_without_partial_writes(self):
        for name in ('zowe.config.json','zowe.schema.json'):
            with self.subTest(name=name):
                original=b'{"private_marker":"fictional-only-do-not-echo"}\n'
                (self.root/name).write_bytes(original)
                with self.assertRaises(ValidationError) as failure:self.prepare()
                self.assertEqual((self.root/name).read_bytes(),original)
                other='zowe.schema.json' if name=='zowe.config.json' else 'zowe.config.json'
                self.assertFalse((self.root/other).exists())
                self.assertNotIn('fictional-only-do-not-echo',str(failure.exception))
                (self.root/name).unlink()

    def test_project_user_config_override_is_preserved_and_blocks_clean_preparation(self):
        override=b'{"profiles":{"DevPlex":{"type":"zosmf","properties":{"protocol":"http","host":"other.example.invalid"}}}}'
        path=self.root/'zowe.config.user.json';path.write_bytes(override)
        with self.assertRaisesRegex(ValidationError,'zowe.config.user.json'):
            self.prepare()
        self.assertEqual(path.read_bytes(),override)
        self.assertFalse((self.root/'zowe.config.json').exists())
        self.assertFalse((self.root/'zowe.schema.json').exists())

    def test_repeat_preparation_preserves_format_and_existing_env_credentials(self):
        before=self.env_file.read_bytes()
        first=self.prepare()
        original=json.loads((self.root/'zowe.config.json').read_bytes())
        formatted=(json.dumps(original,indent=4)+'\r\n').encode()
        (self.root/'zowe.config.json').write_bytes(formatted)
        second=self.prepare()
        self.assertEqual(first,second)
        self.assertEqual((self.root/'zowe.config.json').read_bytes(),formatted)
        self.assertEqual(self.env_file.read_bytes(),before)

    def test_second_file_publication_failure_rolls_back_only_new_owned_file(self):
        from workbench.local_agent import _publish
        def publication(path,content):
            if path.name=='zowe.schema.json': raise OSError('fictional failure')
            return _publish(path,content)
        with patch('workbench.zowe_setup._publish',side_effect=publication):
            with self.assertRaises(OSError): self.prepare()
        self.assertFalse((self.root/'zowe.config.json').exists())
        self.assertFalse((self.root/'zowe.schema.json').exists())

    def test_shared_env_uses_literal_parser_rejects_unknown_duplicates_and_controls(self):
        for suffix in ('ZOWE_PASSWORD=second\n','ZOWE_UNSAFE=private-value\n',
                       'ZOWE_PASSWORD="unterminated\n','\x00'):
            self.env_file.write_text(BASE+suffix)
            with self.assertRaises(ValidationError) as failure:self.prepare()
            self.assertNotIn('private-value',str(failure.exception))

    def test_child_environment_is_scoped_private_and_tls_validation_is_not_bypassed(self):
        self.prepare()
        parent={'PATH':'fictional path','NODE_TLS_REJECT_UNAUTHORIZED':'0','NODE_OPTIONS':'--require evil',
                'ZOWE_OPT_HOST':'unapproved.invalid','ZOWE_OPT_USER':'stale','UNRELATED_SECRET':'private'}
        original=dict(parent)
        child=zowe_setup.zowe_environment(self.root,parent)
        self.assertEqual(parent,original)
        self.assertEqual(child['NODE_EXTRA_CA_CERTS'],str(self.certificate))
        self.assertEqual(child['ZOWE_OPT_USER'],'0000123')
        self.assertEqual(child['ZOWE_OPT_PASSWORD'],'fictional space # dollar $HOME; $(never-run)')
        for key in ('NODE_TLS_REJECT_UNAUTHORIZED','NODE_OPTIONS','ZOWE_OPT_HOST','UNRELATED_SECRET'):
            self.assertNotIn(key,child)
        self.assertFalse((self.root/'never-run').exists())

    def test_partial_credentials_cannot_override_half_of_secure_store_identity(self):
        self.set_value('ZOWE_PASSWORD','')
        with self.assertRaisesRegex(ValidationError,'ZOWE_USERNAME.*ZOWE_PASSWORD'):
            zowe_setup.zowe_environment(self.root,{})

    def test_blank_credentials_leave_zowe_secure_store_in_control(self):
        self.set_value('ZOWE_USERNAME','');self.set_value('ZOWE_PASSWORD','')
        self.prepare()
        child=zowe_setup.zowe_environment(self.root,{})
        self.assertNotIn('ZOWE_OPT_USER',child)
        self.assertNotIn('ZOWE_OPT_PASSWORD',child)

    def test_cli_reports_only_safe_state_and_actionable_field_names(self):
        with redirect_stdout(io.StringIO()) as output:
            self.assertEqual(zowe_setup.main(['--workspace',str(self.root),'--from-env',
                                             '--env-file',str(self.env_file)]),0)
        result=json.loads(output.getvalue())
        self.assertEqual(result['status'],'PREPARED')
        self.assertNotIn('fictional space',output.getvalue())
        self.assertNotIn('0000123"',output.getvalue())
        (self.root/'zowe.config.json').unlink();(self.root/'zowe.schema.json').unlink()
        self.set_value('ZOWE_TSO_ACCOUNT','')
        with redirect_stdout(io.StringIO()) as output:
            self.assertEqual(zowe_setup.main(['--workspace',str(self.root),'--from-env']),2)
        self.assertIn('ZOWE_TSO_ACCOUNT',output.getvalue())
        self.assertNotIn('fictional space',output.getvalue())

    def test_module_cli_prepares_actual_files_with_safe_summary(self):
        import os
        import subprocess
        import sys
        environment={key:value for key,value in os.environ.items() if not key.startswith(('WB_','ZOWE_OPT_'))}
        completed=subprocess.run([sys.executable,'-m','workbench.zowe_setup',
                                  '--workspace',str(self.root),'--from-env',
                                  '--env-file',str(self.env_file)],
                                 cwd=Path(__file__).resolve().parents[1],env=environment,
                                 capture_output=True,text=True,timeout=20,check=False)
        self.assertEqual(completed.returncode,0,completed.stderr)
        result=json.loads(completed.stdout)
        self.assertEqual(result['status'],'PREPARED')
        self.assertEqual(completed.stderr,'')
        self.assertNotIn('fictional space',completed.stdout)
        self.assertNotIn('0000123"',completed.stdout)
        config=json.loads((self.root/'zowe.config.json').read_bytes())
        schema=json.loads((self.root/'zowe.schema.json').read_bytes())
        Draft202012Validator(schema).validate(config)

    def test_module_cli_returns_named_blocker_without_partial_files(self):
        import os
        import subprocess
        import sys
        self.set_value('ZOWE_TSO_ACCOUNT','')
        environment={key:value for key,value in os.environ.items() if not key.startswith(('WB_','ZOWE_OPT_'))}
        completed=subprocess.run([sys.executable,'-m','workbench.zowe_setup',
                                  '--workspace',str(self.root),'--from-env'],
                                 cwd=Path(__file__).resolve().parents[1],env=environment,
                                 capture_output=True,text=True,timeout=20,check=False)
        self.assertEqual(completed.returncode,2,completed.stderr)
        result=json.loads(completed.stdout)
        self.assertEqual(result['status'],'BLOCKED')
        self.assertIn('ZOWE_TSO_ACCOUNT',result['message'])
        self.assertEqual(completed.stderr,'')
        self.assertNotIn('fictional space',completed.stdout)
        self.assertFalse((self.root/'zowe.config.json').exists())
        self.assertFalse((self.root/'zowe.schema.json').exists())

    def test_randomized_configurations_validate_actual_profile_types_and_preserve_leading_zeros(self):
        rng=random.Random(20261011)
        states=set()
        for number in range(64):
            workspace=self.root/'.implementation/tmp'/str(number);workspace.mkdir(parents=True)
            (workspace/'certificates').mkdir()
            (workspace/'certificates/ZOWE-CA.pem').write_text(CERTIFICATE)
            selected=rng.choice(('dev','prod'))
            account='00'+str(rng.randrange(100000,999999))
            values={'ZOWE_ENVIRONMENT':selected,'ZOWE_DEV_HOST':f'dev{number}.example.invalid',
                    'ZOWE_PROD_HOST':f'prod{number}.example.invalid','ZOWE_DEV_PORT':str(rng.randrange(1,65536)),
                    'ZOWE_PROD_PORT':str(rng.randrange(1,65536)),'ZOWE_TSO_ACCOUNT':account,
                    'ZOWE_TSO_CODE_PAGE':str(rng.choice((1047,37,500))),
                    'ZOWE_TSO_LOGON_PROCEDURE':'P'+str(rng.randrange(1000000,9999999))}
            source='\n'.join(key+'='+values.get(key,value) for key,value in
                             (line.split('=',1) for line in BASE.splitlines()))+'\n'
            (workspace/'.env').write_text(source)
            zowe_setup.initialize_environment(workspace)
            config=json.loads((workspace/'zowe.config.json').read_bytes())
            schema=json.loads((workspace/'zowe.schema.json').read_bytes())
            Draft202012Validator(schema).validate(config)
            self.assertEqual(config['profiles']['tso']['properties']['account'],account)
            self.assertEqual(config['defaults']['zosmf'],'DevPlex' if selected=='dev' else 'ProdPlex')
            self.assertEqual(config['profiles']['DevPlex']['properties']['port'],int(values['ZOWE_DEV_PORT']))
            self.assertEqual(config['profiles']['ProdPlex']['properties']['port'],int(values['ZOWE_PROD_PORT']))
            states.add(json.dumps(config,sort_keys=True))
        self.assertEqual(len(states),64)

    def test_reader_uses_exact_workspace_child_environment_and_no_credential_arguments(self):
        from workbench.connectors import ZoweReader
        self.prepare()
        parent={'PATH':'synthetic','NODE_OPTIONS':'--require forbidden'}
        with patch('workbench.connectors.bounded_command',return_value={'success':True,'data':{'items':[]}}) as read:
            reader=ZoweReader('project_base','DevPlex',workspace=self.root,environ=parent)
            reader.list_members('IAPP.COBOL')
        arguments=read.call_args.args[0]
        child=read.call_args.args[1]
        self.assertEqual(read.call_args.kwargs['cwd'],self.root)
        self.assertEqual(child['ZOWE_OPT_USER'],'0000123')
        self.assertIn('--reject-unauthorized',arguments)
        self.assertEqual(arguments[arguments.index('--reject-unauthorized')+1],'true')
        self.assertNotIn('fictional space',str(arguments))
        self.assertNotIn('0000123',str(arguments))
        self.assertEqual(parent,{'PATH':'synthetic','NODE_OPTIONS':'--require forbidden'})

    def test_reader_blocks_missing_config_wrong_alias_and_endpoint_drift_before_process(self):
        from workbench.connectors import ZoweReader
        with patch('workbench.connectors.bounded_command') as read:
            with self.assertRaises(ValidationError):
                ZoweReader('project_base','DevPlex',workspace=self.root).list_members('IAPP.COBOL')
            self.prepare()
            with self.assertRaises(ValidationError):
                ZoweReader('project_base','ProdPlex',workspace=self.root).list_members('IAPP.COBOL')
            reader=ZoweReader('project_base','DevPlex',workspace=self.root)
            self.set_value('ZOWE_DEV_HOST','changed.example.invalid')
            with self.assertRaises(ValidationError):reader.list_members('IAPP.COBOL')
            read.assert_not_called()

    def test_resolver_discovers_only_explicit_workspace_env_without_wb_aliases(self):
        from workbench.connectors import ReadOnlyLineageResolver
        self.prepare()
        with patch('workbench.connectors.bounded_command') as read:
            resolver=ReadOnlyLineageResolver.from_environment({},workspace=self.root)
            self.assertEqual(resolver.zowe.profile,'project_base')
            self.assertEqual(resolver.zowe.zosmf_profile,'DevPlex')
            self.assertEqual(resolver.zowe.workspace,self.root)
            read.assert_not_called()
            unconfigured=ReadOnlyLineageResolver.from_environment({})
            self.assertIsNone(unconfigured.zowe)

    def test_transport_sets_cwd_without_shell_and_keeps_credential_values_out_of_argv(self):
        from workbench.connectors import bounded_command
        from unittest.mock import Mock
        import subprocess
        process=Mock(stdout=io.BytesIO(b'{"success":true,"data":{}}'))
        process.wait.return_value=0
        child={'ZOWE_OPT_PASSWORD':'fictional-secret'}
        with patch('workbench.connectors.zowe_command',side_effect=lambda command,env:command), \
             patch('workbench.connectors.subprocess.Popen',return_value=process) as start:
            bounded_command(['zowe','zos-files','list','all-members','IAPP.COBOL'],child,cwd=self.root)
        self.assertEqual(start.call_args.kwargs['cwd'],self.root)
        self.assertFalse(start.call_args.kwargs['shell'])
        self.assertEqual(start.call_args.kwargs['stdin'],subprocess.DEVNULL)
        self.assertNotIn('fictional-secret',str(start.call_args.args))

    def test_clean_schema_rejects_tls_bypass_plain_credentials_and_unknown_profile_types(self):
        self.prepare()
        config=json.loads((self.root/'zowe.config.json').read_bytes())
        schema=json.loads((self.root/'zowe.schema.json').read_bytes())
        for mutation in ('tls','http','credential','type','default'):
            changed=json.loads(json.dumps(config))
            if mutation=='tls':changed['profiles']['DevPlex']['properties']['rejectUnauthorized']=False
            elif mutation=='http':changed['profiles']['DevPlex']['properties']['protocol']='http'
            elif mutation=='credential':changed['profiles']['project_base']['properties']['password']='fictional'
            elif mutation=='type':changed['profiles']['tso']['type']='TSO'
            else:changed['defaults']['zosmf']='missing'
            self.assertTrue(list(Draft202012Validator(schema).iter_errors(changed)),mutation)


if __name__=='__main__':unittest.main()
