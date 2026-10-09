"""Execute the shipping Claude PowerShell launcher only on native Windows.

Portable command/schema checks live in test_text_db2_setup. These cases are not
substituted with POSIX emulation and do not assert native Windows acceptance on
another host. The CI job requires discovery of all six native tests explicitly.
"""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

REPOSITORY = Path(__file__).resolve().parents[1]

if os.name == 'nt':
    class WindowsClaudeLauncherTests(unittest.TestCase):
        def setUp(self):
            scratch=REPOSITORY/'.implementation/tmp'
            scratch.mkdir(parents=True,exist_ok=True)
            self.directory=tempfile.TemporaryDirectory(prefix='claude native ',dir=scratch)
            self.addCleanup(self.directory.cleanup)
            self.root=Path(self.directory.name).resolve()/'repository café [draft]'
            (self.root/'scripts').mkdir(parents=True)
            shutil.copy(REPOSITORY/'scripts/Start-Claude.ps1',self.root/'scripts/Start-Claude.ps1')
            shutil.copytree(REPOSITORY/'workbench',self.root/'workbench',ignore=shutil.ignore_patterns('static','__pycache__'))
            (self.root/'tools').mkdir()
            (self.root/'tools/db2_mcp_server.py').write_text('# Fixed program path only; no server started by the fixture.\n',encoding='utf-8')
            subprocess.run([sys.executable,'-m','venv','--without-pip',str(self.root/'.venv')],capture_output=True,check=True,timeout=30)
            self.workspace=self.root/'.implementation/tmp/operator workspace'
            self.workspace.mkdir(parents=True)
            self.binding={'type':'stdio','command':str(self.root/'.venv/Scripts/python.exe'),
                          'args':[str(self.root/'tools/db2_mcp_server.py'),'--transport','stdio','--env-file',str(self.workspace/'.env'),'--workspace',str(self.workspace)]}
            self.config=self.workspace/'.mcp.json'
            self.config.write_text(json.dumps({'mcpServers':{'workbench-db2':self.binding}}),encoding='utf-8')
            bin_path=self.root/'.implementation/tmp/client bin';bin_path.mkdir()
            self.log=self.root/'.implementation/tmp/client-result.json'
            fake=bin_path/'client.py'
            fake.write_text('''import json, os, sys
from pathlib import Path
args=sys.argv[1:]
runtime=Path(args[args.index('--mcp-config')+1])
Path(os.environ['CLAUDE_FIXTURE_LOG']).write_text(json.dumps({'args':args,'runtime':json.loads(runtime.read_text(encoding='utf-8'))}),encoding='utf-8')
raise SystemExit(int(os.environ.get('CLAUDE_FIXTURE_EXIT','0')))
''',encoding='utf-8')
            (bin_path/'claude.cmd').write_text('@echo off\r\n"%CLAUDE_FIXTURE_PYTHON%" "%CLAUDE_FIXTURE_SCRIPT%" %*\r\n',encoding='utf-8')
            self.environment={key:value for key,value in os.environ.items() if not key.startswith(('WB_','DB2_','CLAUDE_FIXTURE_'))}
            self.environment.update(PATH=str(bin_path)+os.pathsep+self.environment['PATH'],CLAUDE_FIXTURE_PYTHON=sys.executable,
                                    CLAUDE_FIXTURE_SCRIPT=str(fake),CLAUDE_FIXTURE_LOG=str(self.log),WB_DB2_MCP_TOKEN='synthetic-existing-token')

        def launch(self, **changes):
            shell=shutil.which('powershell.exe')
            self.assertIsNotNone(shell,'Windows PowerShell must execute the shipping launcher')
            return subprocess.run([shell,'-NoLogo','-NoProfile','-NonInteractive','-ExecutionPolicy','Bypass','-File',str(self.root/'scripts/Start-Claude.ps1'),'-Workspace',str(self.workspace)],
                                  cwd=self.directory.name,env=dict(self.environment,**changes),capture_output=True,text=True,errors='replace',timeout=30)

        def assert_runtime_cleaned(self):
            self.assertEqual(list((self.workspace/'.migration').glob('claude-runtime-*.json')),[])

        def test_stdio_launch_uses_fixed_binding_without_token_prompt(self):
            result=self.launch()
            self.assertEqual(result.returncode,0,result.stdout+result.stderr)
            recorded=json.loads(self.log.read_text(encoding='utf-8'))
            self.assertEqual(recorded['runtime'],{'mcpServers':{'workbench-db2':self.binding}})
            self.assertIn('--strict-mcp-config',recorded['args'])
            self.assertIn('--add-dir',recorded['args'])
            self.assertNotIn('synthetic-existing-token',result.stdout+result.stderr+json.dumps(recorded))
            self.assert_runtime_cleaned()

        def test_unrelated_saved_bindings_and_private_env_are_never_exposed_to_client(self):
            original=json.dumps({'mcpServers':{'workbench-db2':self.binding,'never-active':{'command':'arbitrary.exe','env':{'SECRET':'synthetic-sensitive-sentinel'}}}}).encode()
            self.config.write_bytes(original)
            private=self.workspace/'.env';private.write_bytes(b'PRIVATE_RAW_NEVER_READ=synthetic-sensitive-sentinel')
            result=self.launch()
            self.assertEqual(result.returncode,0,result.stdout+result.stderr)
            recorded=json.loads(self.log.read_text(encoding='utf-8'))
            self.assertEqual(recorded['runtime'],{'mcpServers':{'workbench-db2':self.binding}})
            self.assertEqual(self.config.read_bytes(),original)
            self.assertNotIn('synthetic-sensitive-sentinel',result.stdout+result.stderr+json.dumps(recorded))
            self.assert_runtime_cleaned()

        def test_arbitrary_program_cannot_be_authorized_as_managed_stdio(self):
            bad=dict(self.binding,command='arbitrary.exe')
            original=json.dumps({'mcpServers':{'workbench-db2':bad}}).encode();self.config.write_bytes(original)
            result=self.launch()
            self.assertNotEqual(result.returncode,0)
            self.assertFalse(self.log.exists())
            self.assertEqual(self.config.read_bytes(),original)
            self.assert_runtime_cleaned()

        def test_missing_config_names_text_setup_action_before_client_launch(self):
            self.config.unlink()
            result=self.launch()
            self.assertNotEqual(result.returncode,0)
            self.assertIn('workbench.db2_setup',result.stdout+result.stderr)
            self.assertIn('certificates',result.stdout+result.stderr)
            self.assertFalse(self.log.exists())

        def test_native_client_failure_cleans_private_runtime_file(self):
            result=self.launch(CLAUDE_FIXTURE_EXIT='9')
            self.assertNotEqual(result.returncode,0)
            self.assertIn('code 9',result.stdout+result.stderr)
            self.assertTrue(self.log.exists())
            self.assert_runtime_cleaned()

        def test_offline_and_remote_oauth_do_not_prompt_for_local_transport_token(self):
            for document in ({'mcpServers':{}},{'mcpServers':{'workbench-db2':{'type':'http','url':'https://approved.example.invalid/mcp'}}}):
                with self.subTest(document=document):
                    self.config.write_text(json.dumps(document),encoding='utf-8')
                    result=self.launch()
                    self.assertEqual(result.returncode,0,result.stdout+result.stderr)
                    self.assertEqual(json.loads(self.log.read_text(encoding='utf-8'))['runtime'],document)
                    self.assert_runtime_cleaned()

if __name__ == '__main__':unittest.main()
