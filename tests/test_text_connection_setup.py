"""Text-prepared bindings survive source-default saves and safe UI inspection."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from workbench.connection_setup import configure_connections, inspect_connections, default_choices
from workbench.db2_setup import prepare_environment, stdio_binding
from workbench.setup import load_workstation_settings
from tests.test_db2_env import CERTIFICATE

class TextConnectionSetupTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(dir=Path.cwd()/'.implementation/tmp');self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)
        (self.root/'certificates').mkdir()
        (self.root/'certificates/DB2-CA.cert').write_bytes(CERTIFICATE.encode())
        (self.root/'.env').write_text('DB2_LOCATION_NAME=TESTLOC\nDB2_DATABASE=TESTLOC\nDB2_HOSTNAME=db2.example.invalid\nDB2_PORT=5116\nDB2_USERNAME=fictional-private-user\nDB2_PASSWORD=fictional-private-password\nDB2_SSL_CONNECTION=true\nDB2_SSL_SERVER_CERTIFICATE=certificates/DB2-CA.cert\n')
        prepare_environment(self.root,self.root/'.env')
        self.settings=load_workstation_settings(self.root)

    def test_source_defaults_save_preserves_prepared_stdio_binding(self):
        original=(self.root/'.mcp.json').read_bytes()
        view=configure_connections(self.root,{'source_mode':'upload'},default_choices(self.settings))
        self.assertEqual((self.root/'.mcp.json').read_bytes(),original)
        self.assertEqual(view['connection_setup']['transport'],'stdio')
        self.assertNotIn('WB_DB2_MCP_TOKEN',json.dumps(view['connection_setup']))

    def test_recheck_uses_stdio_instead_of_invalid_legacy_db2_file(self):
        (self.root/'.migration').mkdir(exist_ok=True)
        (self.root/'.migration/db2-config.json').write_text('{"certificate":".migration/wrong-ca"}')
        view=inspect_connections(self.root,self.settings)
        self.assertEqual(view['transport'],'stdio')
        self.assertEqual(view['claude_mcp_servers'],1)
        self.assertTrue(any(v['kind']=='db2_env' for v in view['files']))
        self.assertFalse(any(v['id'] in {'db2_start','db2_authentication'} for v in view['commands']+view['remaining']))
        self.assertEqual(view['connectivity'],'UNVERIFIED')
        serialized=json.dumps(view)
        self.assertNotIn('fictional-private',serialized)
        self.assertNotIn('wrong-ca',serialized)

    def test_missing_env_and_changed_ca_are_named_local_gaps_not_connectivity(self):
        (self.root/'.env').unlink()
        view=inspect_connections(self.root,self.settings)
        self.assertEqual(view['transport'],'stdio')
        self.assertTrue(any(v['id']=='db2_env' for v in view['remaining']))
        self.assertEqual(view['connectivity'],'UNVERIFIED')

    def test_unrelated_mcp_bindings_remain_saved_and_inactive(self):
        path=self.root/'.mcp.json';d=json.loads(path.read_text())
        d['mcpServers']['unrelated']={'type':'http','url':'https://example.invalid/mcp'}
        path.write_text(json.dumps(d))
        configure_connections(self.root,{'source_mode':'upload'},default_choices(self.settings))
        self.assertEqual(json.loads(path.read_text())['mcpServers']['unrelated'],d['mcpServers']['unrelated'])
        self.assertEqual(inspect_connections(self.root,self.settings)['claude_mcp_servers'],1)

    def test_tampered_managed_stdio_is_not_repaired_or_removed_on_source_save(self):
        path=self.root/'.mcp.json';d=json.loads(path.read_text());d['mcpServers']['workbench-db2']['command']='arbitrary.exe'
        path.write_text(json.dumps(d));before=path.read_bytes()
        with self.assertRaises(Exception):configure_connections(self.root,{'source_mode':'upload'},default_choices(self.settings))
        self.assertEqual(path.read_bytes(),before)

    def test_legacy_optional_db2_choice_can_save_source_without_removing_stdio(self):
        choices=default_choices(self.settings);choices.pop('db2')
        before=(self.root/'.mcp.json').read_bytes()
        view=configure_connections(self.root,{'source_mode':'upload'},choices)
        self.assertEqual((self.root/'.mcp.json').read_bytes(),before)
        self.assertEqual(view['connection_setup']['transport'],'stdio')

    def test_text_zowe_is_inspected_alongside_stdio_without_secret_projection(self):
        from tests.test_text_db2_setup import FIELDS
        from workbench.zowe_setup import initialize_environment
        (self.root/'.env').write_text(FIELDS)
        (self.root/'certificates/ZOWE-CA.pem').write_bytes(CERTIFICATE.encode())
        initialize_environment(self.root,self.root/'.env')
        with patch('workbench.connection_setup.shutil.which',return_value=None):
            view=inspect_connections(self.root,self.settings)
        self.assertEqual(view['runtime']['zowe_cli'],'NOT_FOUND')
        self.assertTrue(any(v['kind']=='zowe' for v in view['files']))
        self.assertTrue(any(v['id']=='zowe_cli' for v in view['remaining']))
        self.assertNotIn('fictional-zowe',json.dumps(view))
