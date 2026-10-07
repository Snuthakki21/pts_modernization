import asyncio
from contextlib import redirect_stdout
from io import StringIO
import os
import re
from pathlib import Path
import shutil
import shlex
import signal
import json
import socket
import sys
import time
import urllib.error
import urllib.request
import subprocess
import tempfile
import unittest
from unittest.mock import Mock, patch


REPOSITORY = Path(__file__).resolve().parents[1]


class LaunchTests(unittest.TestCase):
    def test_environment_check_reports_missing_lock_dependencies_without_starting_ui(self):
        from workbench import launch
        output = StringIO()
        with patch.object(launch, 'check_environment', return_value={'ready': False, 'problems': ['uvicorn is missing']}), \
                patch.object(launch, 'start_ui') as start, redirect_stdout(output):
            self.assertEqual(launch.main(['--check-environment']), 1)
        self.assertIn('uvicorn is missing', output.getvalue())
        start.assert_not_called()

    def test_ready_environment_check_does_not_read_exports_or_start_coordinator(self):
        from workbench import launch
        with patch.object(launch, 'check_environment', return_value={'ready': True, 'problems': []}), \
                patch.object(launch, 'inspect_workspace', side_effect=AssertionError('Do not inspect source for dependency checks')), \
                patch.object(launch, 'start_ui') as start:
            self.assertEqual(launch.main(['--check-environment']), 0)
        start.assert_not_called()

    def test_preflight_blockers_stop_before_starting_ui(self):
        from workbench import launch
        output = StringIO()
        blocked = {'status': 'BLOCKED', 'checks': [{'id': 'ui_port', 'status': 'BLOCKED',
                   'message': 'Port is occupied', 'action': 'Choose another --port'}]}
        with patch.object(launch, 'inspect_workspace', return_value=blocked), \
                patch.object(launch, 'start_ui') as start, redirect_stdout(output):
            self.assertEqual(launch.main(['--port', '9876', '--no-browser']), 1)
        self.assertIn('Port is occupied', output.getvalue())
        self.assertIn('Choose another --port', output.getvalue())
        start.assert_not_called()

    def test_launch_reuses_preflight_with_selected_port_and_browser_preference(self):
        from workbench import launch
        with tempfile.TemporaryDirectory() as root:
            with patch.object(launch, 'inspect_workspace', return_value={'status': 'READY', 'checks': []}) as inspect, \
                    patch.object(launch, 'start_ui') as start:
                self.assertEqual(launch.main(['--root', root, '--port', '9876', '--no-browser']), 0)
            inspect.assert_called_once_with(Path(root).absolute(), port=9876, workstation_defaults=False)
            start.assert_called_once_with(Path(root).absolute(), port=9876, open_browser=False)

    def test_ctrl_c_stops_cleanly_after_transport_releases_coordinator(self):
        from workbench import launch
        output = StringIO()
        with patch.object(launch, 'inspect_workspace', return_value={'status': 'READY', 'checks': []}), \
                patch.object(launch, 'start_ui', side_effect=KeyboardInterrupt), redirect_stdout(output):
            self.assertEqual(launch.main(['--no-browser']), 0)
        self.assertIn('Workbench stopped.', output.getvalue())

    def test_browser_opens_only_once_after_server_is_ready(self):
        from workbench import launch
        class Server:
            started = False
            def __init__(self, config): self.config = config
            async def startup(self, sockets=None): self.started = True
            def run(self):
                self.assert_before = opener.call_count
                asyncio.run(self.startup())
                asyncio.run(self.startup())
        coordinator = Mock()
        with patch('uvicorn.Server', Server), patch('uvicorn.Config', return_value=object()), \
                patch.object(launch, 'create_app', return_value=Mock(state=Mock(coordinator=coordinator))) as create, \
                patch.object(launch.webbrowser, 'open', return_value=True) as opener:
            launch.start_ui('/fictional/local/workspace', port=9876)
        opener.assert_called_once_with('http://127.0.0.1:9876', new=2)
        create.assert_called_once_with('/fictional/local/workspace', 'http://127.0.0.1:9876')
        coordinator.close.assert_called_once()

    def test_browser_is_not_opened_when_startup_fails_to_bind(self):
        from workbench import launch
        class Server:
            started = False
            def __init__(self, config): pass
            async def startup(self, sockets=None): raise SystemExit(1)
            def run(self): asyncio.run(self.startup())
        coordinator = Mock()
        with patch('uvicorn.Server', Server), patch('uvicorn.Config', return_value=object()), \
                patch.object(launch, 'create_app', return_value=Mock(state=Mock(coordinator=coordinator))), \
                patch.object(launch.webbrowser, 'open') as opener:
            with self.assertRaises(SystemExit): launch.start_ui('/fictional/local/workspace')
        opener.assert_not_called()
        coordinator.close.assert_called_once()

    def test_browser_error_keeps_server_available_with_manual_url(self):
        from workbench import launch
        class Server:
            started = False
            def __init__(self, config): pass
            async def startup(self, sockets=None): self.started = True
            def run(self): asyncio.run(self.startup())
        output = StringIO()
        with patch('uvicorn.Server', Server), patch('uvicorn.Config', return_value=object()), \
                patch.object(launch, 'create_app', return_value=Mock()), \
                patch.object(launch.webbrowser, 'open', side_effect=RuntimeError('browser unavailable')), \
                redirect_stdout(output):
            launch.start_ui('/fictional/local/workspace', port=9876)
        self.assertIn('http://127.0.0.1:9876', output.getvalue())
        self.assertIn('Open', output.getvalue())


class RealLaunchSmokeTests(unittest.TestCase):
    def test_no_browser_launch_serves_existing_api_and_releases_writer_on_shutdown(self):
        from workbench.coordinator import Coordinator
        with tempfile.TemporaryDirectory(prefix='launch with spaces ') as temporary_root:
            root = Path(temporary_root).resolve()
            with socket.socket() as listener:
                listener.bind(('127.0.0.1', 0)); port = listener.getsockname()[1]
            logs = tempfile.TemporaryFile(); self.addCleanup(logs.close)
            environment = {key: value for key, value in os.environ.items() if not key.startswith('WB_')}
            service = subprocess.Popen([sys.executable, '-m', 'workbench.launch', '--root', str(root),
                                        '--port', str(port), '--no-browser'],
                                       stdout=logs, stderr=subprocess.STDOUT, env=environment)
            try:
                deadline = time.monotonic() + 20
                while True:
                    try:
                        with urllib.request.urlopen(f'http://127.0.0.1:{port}/api/setup', timeout=2) as response:
                            result = json.load(response)
                        break
                    except (urllib.error.URLError, ConnectionError):
                        if service.poll() is not None or time.monotonic() > deadline:
                            logs.seek(0)
                            self.fail('Launcher failed: ' + logs.read().decode(errors='replace')[-4000:])
                        time.sleep(.05)
                self.assertEqual(result['metrics']['network_requests'], 0)
                self.assertIsNotNone(result.get('questions'))
                logs.seek(0)
                self.assertIn('Ctrl+C stops the server safely', logs.read().decode())
            finally:
                service.terminate()
                try:
                    service.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    service.kill(); service.wait(timeout=5)
            recovered = Coordinator(root)
            recovered.close()

    def test_real_ctrl_c_returns_success_without_traceback_and_releases_writer(self):
        from workbench.coordinator import Coordinator
        with tempfile.TemporaryDirectory(prefix='interrupt launch ') as temporary_root:
            root = Path(temporary_root).resolve()
            with socket.socket() as listener:
                listener.bind(('127.0.0.1', 0)); port = listener.getsockname()[1]
            logs = tempfile.TemporaryFile(); self.addCleanup(logs.close)
            command = [sys.executable, '-m', 'workbench.launch', '--root', str(root),
                       '--port', str(port), '--no-browser']
            if os.name == 'nt':
                # Windows subprocess.send_signal cannot send POSIX SIGINT. Invoke
                # the real Python SIGINT handler from a control thread instead.
                wrapper = ("import _thread,sys,threading; from workbench.launch import main; "
                           "threading.Thread(target=lambda: (sys.stdin.read(1), _thread.interrupt_main()), daemon=True).start(); "
                           "raise SystemExit(main(sys.argv[1:]))")
                command = [sys.executable, '-c', wrapper, *command[3:]]
            service = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=logs, stderr=subprocess.STDOUT,
                                       env={key: value for key, value in os.environ.items() if not key.startswith('WB_')})
            try:
                deadline = time.monotonic() + 20
                while True:
                    try:
                        with urllib.request.urlopen(f'http://127.0.0.1:{port}/api/setup', timeout=2) as response:
                            self.assertEqual(response.status, 200)
                        break
                    except (urllib.error.URLError, ConnectionError):
                        if service.poll() is not None or time.monotonic() > deadline:
                            logs.seek(0)
                            self.fail('Launcher did not become ready: ' + logs.read().decode(errors='replace')[-4000:])
                        time.sleep(.05)
                if os.name == 'nt':
                    service.stdin.write(b'!'); service.stdin.flush()
                else:
                    service.send_signal(signal.SIGINT)
                result = service.wait(timeout=10)
                logs.seek(0); output = logs.read().decode(errors='replace')
                self.assertEqual(result, 0, output)
                self.assertIn('Workbench stopped.', output)
                self.assertNotIn('Traceback', output)
                self.assertNotIn('CancelledError', output)
            finally:
                if service.poll() is None:
                    service.terminate()
                    try: service.wait(timeout=10)
                    except subprocess.TimeoutExpired:
                        service.kill(); service.wait(timeout=5)
                service.stdin.close()
            recovered = Coordinator(root)
            recovered.close()

    def test_occupied_port_stops_before_coordinator_or_browser(self):
        with tempfile.TemporaryDirectory() as temporary_root, socket.socket() as listener:
            root = Path(temporary_root).resolve()
            listener.bind(('127.0.0.1', 0)); listener.listen(1)
            result = subprocess.run([sys.executable, '-m', 'workbench.launch', '--root', str(root),
                                     '--port', str(listener.getsockname()[1]), '--no-browser'],
                                    capture_output=True, text=True, timeout=20,
                                    env={key: value for key, value in os.environ.items() if not key.startswith('WB_')})
            self.assertEqual(result.returncode, 1, result.stderr)
            self.assertIn('ui_port:', result.stdout)
            self.assertNotIn('Workbench:', result.stdout)
            self.assertFalse((Path(root) / '.migration/coordinator.lock').exists())


class PosixStartScriptTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name) / 'workspace with spaces'
        (self.root / 'scripts').mkdir(parents=True)
        self.log = Path(self.tmp.name) / 'calls'
        shutil.copy(REPOSITORY / 'scripts/start.sh', self.root / 'scripts/start.sh')
        setup = self.root / 'scripts/setup.sh'
        setup.write_text('''#!/usr/bin/env bash
set -euo pipefail
echo setup >> "$FAKE_LOG"
[[ "${FAKE_SETUP_FAIL:-0}" == 0 ]] || exit 23
mkdir -p .venv/bin
cp "$FAKE_TEMPLATE" .venv/bin/python
touch .venv/ready
''')
        self.interpreter = Path(self.tmp.name) / 'fake-python'
        self.interpreter.write_text('''#!/usr/bin/env bash
echo "$*" >> "$FAKE_LOG"
if [[ "$*" == *--check-environment* ]]; then [[ -f .venv/ready ]]; exit $?; fi
if [[ "$*" == *workbench.launch* ]]; then exit "${FAKE_UI_FAIL:-0}"; fi
exit 9
''')
        self.interpreter.chmod(0o755)
        self.environment = dict(os.environ, FAKE_LOG=str(self.log), FAKE_TEMPLATE=str(self.interpreter))

    def run_start(self, *arguments, **environment):
        return subprocess.run(['/bin/bash', str(self.root / 'scripts/start.sh'), *arguments],
                              cwd=self.tmp.name, env=dict(self.environment, **environment),
                              text=True, capture_output=True, timeout=30)

    def test_single_launch_installs_once_and_preserves_selected_flags(self):
        if os.name == 'nt':
            script = (REPOSITORY / 'scripts/start.sh').read_text()
            self.assertIn('! .venv/bin/python -m workbench.launch --check-environment', script)
            self.assertIn('exec .venv/bin/python -m workbench.launch --port', script)
            return  # POSIX shell is checked statically on Windows, never claimed executed.
        first = self.run_start('--no-browser', '--port', '9876')
        self.assertEqual(first.returncode, 0, first.stderr)
        second = self.run_start('--no-browser', '--port', '9876')
        self.assertEqual(second.returncode, 0, second.stderr)
        calls = self.log.read_text().splitlines()
        self.assertEqual(calls.count('setup'), 1)
        self.assertEqual(sum('workbench.launch --port 9876 --no-browser' in row for row in calls), 2)

    def test_missing_dependencies_reuse_existing_installer(self):
        if os.name == 'nt':
            script = (REPOSITORY / 'scripts/start.sh').read_text()
            self.assertEqual(script.count('bash scripts/setup.sh'), 1)
            self.assertNotIn('pip install', script)
            return
        (self.root / '.venv/bin').mkdir(parents=True)
        shutil.copy(self.interpreter, self.root / '.venv/bin/python')
        result = self.run_start('--no-browser')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.log.read_text().splitlines().count('setup'), 1)

    def test_installer_failure_never_attempts_ui(self):
        if os.name == 'nt':
            script = (REPOSITORY / 'scripts/start.sh').read_text()
            self.assertIn('set -euo pipefail', script)
            self.assertLess(script.index('bash scripts/setup.sh'), script.index('exec .venv'))
            return
        result = self.run_start('--no-browser', FAKE_SETUP_FAIL='1')
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self.log.read_text().splitlines(), ['setup'])

    def test_invalid_options_fail_before_installation(self):
        if os.name == 'nt':
            script = (REPOSITORY / 'scripts/start.sh').read_text()
            self.assertLess(script.index('port <= 65535'), script.index('bash scripts/setup.sh'))
            self.assertIn('Unknown option:', script)
            return
        for arguments in (('--port', 'abc'), ('--port', '0'), ('--port', '65536'),
                          ('--port',), ('--unknown',)):
            with self.subTest(arguments=arguments):
                result = self.run_start(*arguments)
                self.assertNotEqual(result.returncode, 0)
                self.assertFalse(self.log.exists())

    def test_service_error_is_not_reported_as_success(self):
        if os.name == 'nt':
            script = (REPOSITORY / 'scripts/start.sh').read_text()
            self.assertIn('exec .venv/bin/python -m workbench.launch', script)
            self.assertNotIn('|| true', script)
            return
        result = self.run_start('--no-browser', FAKE_UI_FAIL='9')
        self.assertEqual(result.returncode, 9)


class WindowsStartContractTests(unittest.TestCase):
    def test_installer_python_expression_preserves_cpython_literal_in_shell_quoting(self):
        script = (REPOSITORY / 'scripts/setup.sh').read_text()
        line = next(row for row in script.splitlines() if row.startswith('.venv/bin/python -c '))
        expression = shlex.split(line)[2]
        result = subprocess.run([sys.executable, '-c', expression], capture_output=True, text=True, timeout=5)
        self.assertEqual(result.returncode, 0, result.stderr)
        powershell = (REPOSITORY / 'scripts/Setup.ps1').read_text()
        assignment = next(row for row in powershell.splitlines() if row.startswith('$versionCheck = '))
        literal = re.fullmatch(r"\$versionCheck = '((?:[^']|'')*)'", assignment)
        self.assertIsNotNone(literal, 'Use one PowerShell single-quoted literal with doubled embedded single quotes')
        expression = literal.group(1).replace("''", "'")
        self.assertNotIn('"', expression, 'Avoid embedded double quotes removed by Windows PowerShell legacy native argument handling')
        result = subprocess.run([sys.executable, '-c', expression], capture_output=True, text=True, timeout=5)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_windows_launcher_uses_same_environment_check_and_single_ui(self):
        # Runtime Python tests above are shared across hosts; native PowerShell
        # execution belongs to the Windows CI runner and is not claimed here.
        script = (REPOSITORY / 'scripts/Start.ps1').read_text()
        self.assertIn('param(', script)
        self.assertIn('[switch]$NoBrowser', script)
        self.assertIn('--check-environment', script)
        self.assertIn("'Setup.ps1'", script)
        self.assertIn("'-m', 'workbench.launch'", script)
        self.assertIn('--no-browser', script)
        self.assertNotIn('Start-Process', script)


if __name__ == '__main__': unittest.main()
