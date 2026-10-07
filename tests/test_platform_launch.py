"""Execute the shipping shell on this host against an isolated native interpreter."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest


REPOSITORY = Path(__file__).resolve().parents[1]


class PlatformLauncherTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='native launcher ')
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name) / 'workspace café (draft) & % [copy]'
        (self.root / 'scripts').mkdir(parents=True)
        for name in ('Start.ps1', 'Setup.ps1', 'start.sh', 'setup.sh'):
            shutil.copy(REPOSITORY / 'scripts' / name, self.root / 'scripts' / name)
        # The real interpreter tests native -c/argument passing. Only modules
        # that would install dependencies or start the UI are bounded witnesses.
        subprocess.run([sys.executable, '-m', 'venv', '--without-pip', str(self.root / '.venv')],
                       check=True, capture_output=True, timeout=30)
        package = self.root / 'workbench'
        package.mkdir()
        (package / '__init__.py').write_text('', encoding='utf-8')
        common = '''import json, os, sys
from pathlib import Path
def record(kind):
    with Path(os.environ['FAKE_LOG']).open('a', encoding='utf-8') as out:
        out.write(json.dumps({'kind': kind, 'args': sys.argv[1:]}) + '\\n')
'''
        (package / 'launch.py').write_text(common + '''record('launch')
if '--check-environment' in sys.argv:
    raise SystemExit(0 if Path('.venv/ready').exists() else 1)
raise SystemExit(int(os.environ.get('FAKE_UI_FAIL', '0')))
''', encoding='utf-8')
        (package / 'preflight.py').write_text(common + '''record('preflight')
raise SystemExit(int(os.environ.get('FAKE_PREFLIGHT_FAIL', '0')))
''', encoding='utf-8')
        for name, body in {
            'pip': '''record('pip')
if not Path('.venv/pip-ready').exists():
    print('No module named pip', file=sys.stderr)
    raise SystemExit(1)
if 'install' in sys.argv:
    if os.environ.get('FAKE_INSTALL_FAIL') == '1': raise SystemExit(23)
    Path('.venv/ready').touch()
''',
            'ensurepip': '''record('ensurepip')
if os.environ.get('FAKE_ENSUREPIP_FAIL') == '1': raise SystemExit(24)
Path('.venv/pip-ready').touch()
'''
        }.items():
            stub = self.root / name
            stub.mkdir()
            (stub / '__init__.py').write_text('', encoding='utf-8')
            (stub / '__main__.py').write_text(common + body, encoding='utf-8')
        self.log = self.root / '.implementation/tmp/calls.jsonl'
        self.log.parent.mkdir(parents=True)
        self.environment = {key: value for key, value in os.environ.items() if not key.startswith('WB_')}
        self.environment['FAKE_LOG'] = str(self.log)
        self.environment.pop('PYTHONPATH', None)

    def run_script(self, name, *arguments, native_errors=False, **environment):
        if os.name == 'nt':
            shell = shutil.which('powershell.exe')
            self.assertIsNotNone(shell, 'Windows PowerShell is a required native launcher test')
            prefix = [shell, '-NoLogo', '-NoProfile', '-NonInteractive', '-ExecutionPolicy', 'Bypass']
            script = self.root / 'scripts' / {'start': 'Start.ps1', 'setup': 'Setup.ps1'}[name]
            command = [*prefix, '-File', str(script), *arguments]
            if native_errors:
                shell = shutil.which('pwsh.exe')
                self.assertIsNotNone(shell, 'PowerShell 7 must exercise native failure preferences on Windows CI')
                wrapper = self.root / 'scripts/native-preference.ps1'
                wrapper.write_text("$PSNativeCommandUseErrorActionPreference = $true\n& '" +
                                   str(script).replace("'", "''") + "' @args\n", encoding='utf-8')
                command = [shell, *prefix[1:], '-File', str(wrapper), *arguments]
        else:
            command = ['/bin/bash', str(self.root / 'scripts' / (name + '.sh')), *arguments]
        return subprocess.run(command, cwd=self.tmp.name, env=dict(self.environment, **environment),
                              capture_output=True, text=True, errors='replace', timeout=30)

    def calls(self):
        return [json.loads(line) for line in self.log.read_text(encoding='utf-8').splitlines()] if self.log.exists() else []

    def start_arguments(self):
        return ('-NoBrowser', '-Port', '9876') if os.name == 'nt' else ('--no-browser', '--port', '9876')

    def test_missing_pip_is_repaired_before_locked_install_and_preflight(self):
        result = self.run_script('setup')
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        calls = self.calls()
        self.assertEqual([row['kind'] for row in calls], ['pip', 'ensurepip', 'pip', 'preflight'])
        install = calls[2]['args']
        for option in ('--require-hashes', '--only-binary=:all:', '-r', 'requirements.lock'):
            self.assertIn(option, install)
        self.assertIn('--initialize-knowledge', calls[3]['args'])
        self.assertIn(str(self.root), calls[3]['args'])

    def test_first_start_repairs_environment_and_second_start_reuses_it(self):
        (self.root / '.venv/pip-ready').touch()
        for _ in range(2):
            result = self.run_script('start', *self.start_arguments())
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        calls = self.calls()
        self.assertEqual(sum(row['kind'] == 'preflight' for row in calls), 1)
        launches = [row['args'] for row in calls if row['kind'] == 'launch' and '--port' in row['args']]
        self.assertEqual(launches, [['--port', '9876', '--no-browser']] * 2)

    def test_expected_native_dependency_failure_still_reaches_setup(self):
        (self.root / '.venv/pip-ready').touch()
        result = self.run_script('start', *self.start_arguments(), native_errors=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertTrue(any(row['kind'] == 'preflight' for row in self.calls()))

    def test_install_or_preflight_failure_stops_before_ui(self):
        (self.root / '.venv/pip-ready').touch()
        for environment in ({'FAKE_INSTALL_FAIL': '1'}, {'FAKE_PREFLIGHT_FAIL': '1'}):
            with self.subTest(environment=environment):
                self.log.unlink(missing_ok=True)
                (self.root / '.venv/ready').unlink(missing_ok=True)
                result = self.run_script('start', *self.start_arguments(), **environment)
                self.assertNotEqual(result.returncode, 0)
                self.assertFalse(any(row['kind'] == 'launch' and '--port' in row['args'] for row in self.calls()))

    def test_ui_error_is_returned_after_one_native_launch(self):
        (self.root / '.venv/pip-ready').touch()
        (self.root / '.venv/ready').touch()
        result = self.run_script('start', *self.start_arguments(), FAKE_UI_FAIL='9')
        self.assertNotEqual(result.returncode, 0)
        calls = self.calls()
        self.assertEqual([row['kind'] for row in calls], ['launch', 'launch'])
        self.assertEqual(calls[1]['args'], ['--port', '9876', '--no-browser'])

    def test_invalid_port_stops_before_interpreter_or_installer(self):
        for port in ('0', '65536', 'abc'):
            with self.subTest(port=port):
                arguments = ('-Port', port) if os.name == 'nt' else ('--port', port)
                result = self.run_script('start', *arguments)
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual(self.calls(), [])

    def test_failed_pip_bootstrap_stops_before_install_or_preflight(self):
        result = self.run_script('setup', FAKE_ENSUREPIP_FAIL='1')
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual([row['kind'] for row in self.calls()], ['pip', 'ensurepip'])


class PlatformWorkflowTests(unittest.TestCase):
    def test_workflow_is_parseable_and_executes_shipping_platform_setup(self):
        import yaml
        workflow = yaml.safe_load((REPOSITORY / '.github/workflows/platform-smoke.yml').read_text(encoding='utf-8'))
        job = workflow['jobs']['offline-workflow']
        self.assertEqual(set(job['strategy']['matrix']['os']), {'windows-latest', 'ubuntu-latest'})
        steps = job['steps']
        self.assertTrue(any(step.get('shell') == 'powershell' and 'Setup.ps1' in step.get('run', '') for step in steps))
        self.assertTrue(any(step.get('shell') == 'bash' and 'setup.sh' in step.get('run', '') for step in steps))
        smoke = next(step['run'] for step in steps if step.get('shell') == 'python')
        self.assertIn('test_platform*.py', smoke)
        self.assertIn('test_preflight.py', smoke)


if __name__ == '__main__': unittest.main()
