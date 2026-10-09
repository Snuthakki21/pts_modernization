"""Execute the shipping shell on this host against an isolated native interpreter."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time
import unittest


REPOSITORY = Path(__file__).resolve().parents[1]


class _PlatformLauncherFixture:
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
        out.write(json.dumps({'kind': kind, 'args': sys.argv[1:], 'pip_user': os.environ.get('PIP_USER')}) + '\\n')
'''
        (package / 'launch.py').write_text(common + '''record('launch')
if '--check-environment' in sys.argv:
    raise SystemExit(0 if Path('.venv/ready').exists() and os.environ.get('FAKE_READINESS_FAIL') != '1' else 1)
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
    if os.environ.get('FAKE_CONFIG_USER') == '1' and '--no-user' not in sys.argv: raise SystemExit(25)
    if os.environ.get('FAKE_INSTALL_ENTERED'):
        import time
        Path(os.environ['FAKE_INSTALL_ENTERED']).touch()
        deadline = time.monotonic() + 10
        while not Path(os.environ['FAKE_INSTALL_RELEASE']).exists():
            if time.monotonic() > deadline: raise SystemExit(26)
            time.sleep(0.05)
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
        self.environment = {key: value for key, value in os.environ.items() if not key.startswith(('WB_', 'PIP_'))}
        self.environment['FAKE_LOG'] = str(self.log)
        self.environment.pop('PYTHONPATH', None)

    def script_command(self, name, *arguments, native_errors=False, restore_receipt=None):
        if os.name == 'nt':
            shell = shutil.which('powershell.exe')
            self.assertIsNotNone(shell, 'Windows PowerShell is a required native launcher test')
            prefix = [shell, '-NoLogo', '-NoProfile', '-NonInteractive', '-ExecutionPolicy', 'Bypass']
            script = self.root / 'scripts' / {'start': 'Start.ps1', 'setup': 'Setup.ps1'}[name]
            command = [*prefix, '-File', str(script), *arguments]
            if native_errors or restore_receipt:
                if native_errors:
                    shell = shutil.which('pwsh.exe')
                    self.assertIsNotNone(shell, 'PowerShell 7 must exercise native failure preferences on Windows CI')
                wrapper = self.root / 'scripts/native-preference.ps1'
                quoted_script = str(script).replace("'", "''")
                contents = "$PSNativeCommandUseErrorActionPreference = $true\n" if native_errors else ''
                if restore_receipt:
                    quoted_receipt = str(restore_receipt).replace("'", "''")
                    contents += ("$outcome = 0\ntry { & '" + quoted_script + "' @args; $outcome = $LASTEXITCODE }\n"
                                 "catch { Write-Host $_.Exception.Message; $outcome = 1 }\n"
                                 "finally { [IO.File]::WriteAllText('" + quoted_receipt + "', [string]$env:PIP_USER) }\n"
                                 "exit $outcome\n")
                else:
                    contents += "& '" + quoted_script + "' @args\n"
                wrapper.write_text(contents, encoding='utf-8-sig')
                command = [shell, *prefix[1:], '-File', str(wrapper), *arguments]
        else:
            command = ['/bin/bash', str(self.root / 'scripts' / (name + '.sh')), *arguments]
        return command

    def run_script(self, name, *arguments, native_errors=False, restore_receipt=None, **environment):
        command = self.script_command(name, *arguments, native_errors=native_errors, restore_receipt=restore_receipt)
        return subprocess.run(command, cwd=self.tmp.name, env=dict(self.environment, **environment),
                              capture_output=True, text=True, errors='replace', timeout=30)

    def calls(self):
        return [json.loads(line) for line in self.log.read_text(encoding='utf-8').splitlines()] if self.log.exists() else []

    def start_arguments(self):
        return ('-NoBrowser', '-Port', '9876') if os.name == 'nt' else ('--no-browser', '--port', '9876')


class PlatformLauncherTests(_PlatformLauncherFixture, unittest.TestCase):
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


class WindowsPipConfigurationTests(unittest.TestCase):
    def test_shipping_install_overrides_user_mode_without_discarding_index_or_ca(self):
        import shlex
        setup = (REPOSITORY / 'scripts/Setup.ps1').read_text(encoding='utf-8')
        command = next(line.strip() for line in setup.splitlines() if '-m pip ' in line and ' install ' in line)
        arguments = shlex.split(command.split('-m pip ', 1)[1])
        scratch = REPOSITORY / '.implementation/tmp'
        scratch.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=scratch) as directory:
            config = Path(directory) / 'pip.ini'
            config.write_text('[install]\nuser = true\n[global]\nindex-url = https://approved.example/simple\ncert = approved-ca.cert\n', encoding='utf-8')
            environment = {key: value for key, value in os.environ.items() if not key.startswith('PIP_')}
            environment.update(PIP_USER='1', PIP_CONFIG_FILE=str(config))
            code = ('import json,sys; from pip._internal.commands.install import InstallCommand; '
                    'c=InstallCommand(name="install",summary=""); o,_=c.parse_args(json.loads(sys.argv[1])); '
                    'print(json.dumps({"user":o.use_user_site,"index":o.index_url,"cert":o.cert}))')
            result = subprocess.run([sys.executable, '-c', code, json.dumps([arg for arg in arguments if arg != 'install'])],
                                    env=environment, capture_output=True, text=True, timeout=10)
            self.assertEqual(result.returncode, 0, result.stderr)
            options = json.loads(result.stdout)
            self.assertIs(options['user'], False, 'Inherited PIP_USER/config user=true must not redirect the locked install')
            self.assertEqual(options['index'], 'https://approved.example/simple')
            self.assertEqual(options['cert'], 'approved-ca.cert')


# These execute the shipping Windows scripts on the required Windows CI job.
# They are deliberately not substituted with a POSIX simulation on other hosts.
if os.name == 'nt':
    class WindowsBootstrapTests(_PlatformLauncherFixture, unittest.TestCase):
        def candidates(self, codes):
            bin_path = self.root / 'candidate launchers'
            bin_path.mkdir()
            dispatch = REPOSITORY / 'tests/fixtures/windows_bootstrap_candidate.py'
            for name in ('py', 'python', 'python3'):
                (bin_path / (name + '.cmd')).write_text(
                    '@echo off\r\n"%FAKE_REAL_PYTHON%" "%FAKE_CANDIDATE_DISPATCH%" ' + name + ' %*\r\n', encoding='utf-8')
            self.environment.update(FAKE_REAL_PYTHON=sys.executable, FAKE_CANDIDATE_DISPATCH=str(dispatch),
                                    FAKE_CANDIDATE_CODES=json.dumps(codes), PATH=str(bin_path) + os.pathsep + self.environment['PATH'])
            shutil.rmtree(self.root / '.venv')

        def test_failed_registered_py_falls_back_to_actual_path_cpython(self):
            self.candidates({'py': 103, 'python': 0, 'python3': 1})
            result = self.run_script('setup', native_errors=True)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            candidates = [row for row in self.calls() if row['kind'] == 'candidate']
            self.assertEqual([row['name'] for row in candidates], ['py', 'python', 'python'])
            self.assertIn('-3.12', candidates[0]['args'])
            self.assertEqual(candidates[-1]['args'], ['-m', 'venv', '.venv'])

        def test_wrong_python_falls_back_to_python3(self):
            self.candidates({'py': 103, 'python': 'wrong-version', 'python3': 0})
            result = self.run_script('setup')
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            candidates = [row for row in self.calls() if row['kind'] == 'candidate']
            self.assertEqual([row['name'] for row in candidates], ['py', 'python', 'python3', 'python3'])

        def test_all_wrong_versions_and_implementations_fail_closed(self):
            self.candidates({'py': 103, 'python': 'wrong-version', 'python3': 'wrong-implementation'})
            result = self.run_script('setup')
            self.assertNotEqual(result.returncode, 0)
            self.assertFalse((self.root / '.venv').exists())
            self.assertEqual([row['name'] for row in self.calls()], ['py', 'python', 'python3'])

        def test_pip_user_is_restored_after_success_and_install_failure(self):
            (self.root / '.venv/pip-ready').touch()
            receipt = self.root / '.implementation/tmp/restored.txt'
            for fail in ('0', '1'):
                with self.subTest(fail=fail):
                    self.log.unlink(missing_ok=True)
                    result = self.run_script('setup', restore_receipt=receipt, PIP_USER='1', FAKE_CONFIG_USER='1', FAKE_INSTALL_FAIL=fail)
                    self.assertEqual(result.returncode == 0, fail == '0', result.stdout + result.stderr)
                    self.assertEqual(receipt.read_text(encoding='utf-8'), '1')
                    install = next(row for row in self.calls() if row['kind'] == 'pip' and 'install' in row['args'])
                    self.assertIn('--no-user', install['args'])
                    self.assertIn(install['pip_user'], (None, '0'))

        def test_simultaneous_setup_and_start_are_refused_without_second_install_or_ui(self):
            (self.root / '.venv/pip-ready').touch()
            entered = self.root / '.implementation/tmp/install-entered'
            release = self.root / '.implementation/tmp/install-release'
            environment = dict(self.environment, FAKE_INSTALL_ENTERED=str(entered), FAKE_INSTALL_RELEASE=str(release))
            first = subprocess.Popen(self.script_command('setup'), cwd=self.tmp.name, env=environment,
                                     stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            try:
                deadline = time.monotonic() + 10
                while not entered.exists() and first.poll() is None and time.monotonic() < deadline: time.sleep(0.05)
                self.assertTrue(entered.exists(), 'First setup did not reach the bounded install witness')
                for name, arguments in (('setup', ()), ('start', self.start_arguments())):
                    result = self.run_script(name, *arguments)
                    self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
                    self.assertIn('already', (result.stdout + result.stderr).lower())
                self.assertEqual(sum(row['kind'] == 'pip' and 'install' in row['args'] for row in self.calls()), 1)
                self.assertFalse(any(row['kind'] == 'launch' and '--port' in row['args'] for row in self.calls()))
            finally:
                release.touch()
                stdout, stderr = first.communicate(timeout=15)
            self.assertEqual(first.returncode, 0, stdout + stderr)
            result = self.run_script('start', *self.start_arguments())
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertEqual(sum(row['kind'] == 'launch' and '--port' in row['args'] for row in self.calls()), 1)

        def test_setup_success_with_failed_readiness_stops_before_ui(self):
            (self.root / '.venv/pip-ready').touch()
            result = self.run_script('start', *self.start_arguments(), FAKE_READINESS_FAIL='1')
            self.assertNotEqual(result.returncode, 0)
            self.assertIn('readiness', (result.stdout + result.stderr).lower())
            self.assertEqual(sum(row['kind'] == 'preflight' for row in self.calls()), 1)
            self.assertEqual(sum(row['kind'] == 'launch' and '--check-environment' in row['args'] for row in self.calls()), 2)
            self.assertFalse(any(row['kind'] == 'launch' and '--port' in row['args'] for row in self.calls()))

        def test_failed_setup_releases_exclusive_handle_for_retry(self):
            (self.root / '.venv/pip-ready').touch()
            result = self.run_script('setup', FAKE_INSTALL_FAIL='1')
            self.assertNotEqual(result.returncode, 0)
            result = self.run_script('setup')
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


class PlatformWorkflowTests(unittest.TestCase):
    def test_workflow_is_parseable_and_executes_shipping_platform_setup(self):
        import yaml
        workflow = yaml.safe_load((REPOSITORY / '.github/workflows/platform-smoke.yml').read_text(encoding='utf-8'))
        job = workflow['jobs']['offline-workflow']
        self.assertEqual(set(job['strategy']['matrix']['os']), {'windows-latest'})
        steps = job['steps']
        self.assertTrue(any(step.get('shell') == 'powershell' and 'Setup.ps1' in step.get('run', '') for step in steps))
        self.assertFalse(any('setup.sh' in step.get('run', '') for step in steps))
        smoke = next(step['run'] for step in steps if step.get('name') == 'Exercise native intake, ledger, reports and CLI')
        self.assertIn('test_platform*.py', smoke)
        self.assertIn('test_preflight.py', smoke)
        bootstrap = next(step['run'] for step in steps if step.get('name') == 'Exercise Windows bootstrap regressions before installation')
        self.assertIn('WindowsBootstrapTests', bootstrap)
        self.assertIn('WindowsPipConfigurationTests', bootstrap)
        self.assertIn('result.skipped', bootstrap)
        self.assertLess(next(index for index, step in enumerate(steps) if step.get('name') == 'Exercise Windows bootstrap regressions before installation'),
                        next(index for index, step in enumerate(steps) if 'Setup.ps1' in step.get('run', '')))


if __name__ == '__main__': unittest.main()
