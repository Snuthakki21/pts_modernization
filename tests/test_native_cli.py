"""Native Zowe dispatch preserves argv; no mainframe connection is attempted."""
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from unittest.mock import patch

from workbench import connectors, zowe_setup
from workbench.domain import ValidationError


class NativeZoweTests(unittest.TestCase):
    def installation(self, directory):
        prefix = Path(directory).resolve() / 'approved npm (profile) & tools'
        package = prefix / 'node_modules' / '@zowe' / 'cli'
        (package / 'lib').mkdir(parents=True)
        (prefix / 'zowe.cmd').write_text('@echo off\n', encoding='utf-8')
        (prefix / 'node.exe').write_bytes(b'fictional native executable')
        (package / 'package.json').write_text(json.dumps({'name': '@zowe/cli', 'bin': {'zowe': './lib/main.js'}}), encoding='utf-8')
        (package / 'lib' / 'main.js').write_text('console.log(JSON.stringify({success:true,args:process.argv.slice(2)}));', encoding='utf-8')
        return prefix, package

    def test_windows_reader_dispatches_node_bin_without_running_batch_shim(self):
        with tempfile.TemporaryDirectory() as directory:
            prefix, package = self.installation(directory)
            class Child:
                stdout = io.BytesIO(b'{"success":true,"data":"source"}')
                def wait(self, timeout=None): return 0
            with patch('sys.platform', 'win32'), patch('shutil.which', return_value=str(prefix / 'zowe.cmd')), \
                 patch('workbench.connectors.subprocess.Popen', return_value=Child()) as start:
                connectors.ZoweReader('approved').read_member('IABC.SOURCE(HELLO)')
            self.assertEqual(start.call_args.args[0][:2], [str(prefix / 'node.exe'), str(package / 'lib' / 'main.js')])
            self.assertIn('IABC.SOURCE(HELLO)', start.call_args.args[0])
            self.assertFalse(start.call_args.kwargs['shell'])

    def test_windows_secure_input_uses_the_same_native_command_resolver(self):
        with tempfile.TemporaryDirectory() as directory:
            prefix, package = self.installation(directory)
            workspace = Path(directory).resolve() / 'workspace'
            workspace.mkdir()
            with patch('sys.platform', 'win32'), patch('shutil.which', return_value=str(prefix / 'zowe.cmd')), \
                 patch('workbench.zowe_setup.sys.stdin.isatty', return_value=True), \
                 patch('workbench.zowe_setup.subprocess.call', return_value=0) as start, redirect_stdout(io.StringIO()) as output:
                self.assertEqual(zowe_setup.main(['--workspace', str(workspace), '--secure', '--host', 'host.example.invalid']), 0)
            self.assertEqual(start.call_args.args[0], [str(prefix / 'node.exe'), str(package / 'lib' / 'main.js'), 'config', 'secure'])
            self.assertFalse(start.call_args.kwargs['shell'])
            self.assertEqual(json.loads(output.getvalue())['connectivity'], 'UNVERIFIED')


    def test_global_and_local_npm_layouts_resolve_declared_entry(self):
        with tempfile.TemporaryDirectory() as directory:
            prefix, package = self.installation(directory)
            for launcher in (prefix / 'zowe.cmd', package.parent.parent / '.bin' / 'zowe.cmd'):
                launcher.parent.mkdir(exist_ok=True)
                launcher.write_text('unused shim', encoding='utf-8')
                if launcher.parent != prefix: (launcher.parent / 'node.exe').write_bytes(b'fictional native executable')
                with self.subTest(layout=launcher.parent), patch('sys.platform', 'win32'), patch('shutil.which', return_value=str(launcher)):
                    command = connectors.zowe_command(['zowe', 'config', 'secure'], {'PATH': str(prefix)})
                    self.assertEqual(command[1:], [str(package / 'lib' / 'main.js'), 'config', 'secure'])

    def test_native_executable_is_resolved_without_npm_or_shell(self):
        with patch('sys.platform', 'win32'), patch('shutil.which', return_value=str(Path.cwd() / 'approved' / 'zowe.exe')):
            command = connectors.zowe_command(['zowe', 'zos-files', 'view', 'data-set', 'ZAPP.SOURCE(P)'], {'PATH': 'approved'})
        self.assertEqual(command[0], str(Path.cwd() / 'approved' / 'zowe.exe'))
        self.assertEqual(command[-1], 'ZAPP.SOURCE(P)')

    def test_missing_cli_is_a_named_gate(self):
        with patch('sys.platform', 'win32'), patch('shutil.which', return_value=None), patch('subprocess.Popen') as start:
            with self.assertRaisesRegex(ValidationError, 'CLI unavailable'):
                connectors.bounded_command(['zowe', 'config', 'secure'], {})
        start.assert_not_called()

    def test_missing_package_cannot_fall_back_to_batch_execution(self):
        with tempfile.TemporaryDirectory() as directory, patch('sys.platform', 'win32'), \
             patch('shutil.which', return_value=str(Path(directory).resolve() / 'zowe.cmd')), patch('subprocess.Popen') as start:
            with self.assertRaisesRegex(ValidationError, 'package is missing'):
                connectors.bounded_command(['zowe'], {'PATH': directory})
        start.assert_not_called()

    def test_invalid_package_bin_or_identity_never_executes(self):
        with tempfile.TemporaryDirectory() as directory:
            prefix, package = self.installation(directory)
            for declaration in ({'name':'other-cli','bin':{'zowe':'./lib/main.js'}},
                                {'name':'@zowe/cli','bin':{'zowe':'../outside.js'}},
                                {'name':'@zowe/cli','bin':{'zowe':'C:/outside.js'}},
                                {'name':'@zowe/cli','bin':{'zowe':'./lib/main.cmd'}},
                                {'name':'@zowe/cli','bin':'./lib/main.js'},
                                {'name':'@zowe/cli','bin':{'zowe':'./lib/missing.js'}}):
                (package / 'package.json').write_text(json.dumps(declaration), encoding='utf-8')
                with self.subTest(declaration=declaration), patch('sys.platform', 'win32'), \
                     patch('shutil.which', return_value=str(prefix / 'zowe.cmd')), patch('subprocess.Popen') as start:
                    with self.assertRaises(ValidationError): connectors.bounded_command(['zowe'], {'PATH': str(prefix)})
                    start.assert_not_called()

    def test_package_manifest_byte_bound_precedes_json_read(self):
        with tempfile.TemporaryDirectory() as directory:
            prefix, package = self.installation(directory)
            (package / 'package.json').write_bytes(b' ' * 32769)
            with patch('sys.platform', 'win32'), patch('shutil.which', return_value=str(prefix / 'zowe.cmd')):
                with self.assertRaisesRegex(ValidationError, 'bound'): connectors.zowe_command(['zowe'], {'PATH': str(prefix)})

    def test_node_from_path_is_native_and_not_another_batch_shim(self):
        with tempfile.TemporaryDirectory() as directory:
            prefix, package = self.installation(directory)
            (prefix / 'node.exe').unlink()
            for selected in (None, str(prefix / 'zowe.cmd')):
                with self.subTest(node=selected), patch('sys.platform', 'win32'), \
                     patch('shutil.which', side_effect=[str(prefix / 'zowe.cmd'), selected]):
                    with self.assertRaises(ValidationError): connectors.zowe_command(['zowe'], {'PATH': str(prefix)})

    def test_posix_keeps_approved_cli_argument_tokens(self):
        with patch('sys.platform', 'linux'), patch('shutil.which') as lookup:
            self.assertEqual(connectors.zowe_command(['zowe', 'config', 'secure'], {}), ['zowe', 'config', 'secure'])
        lookup.assert_not_called()

    def test_actual_node_preserves_spaces_parentheses_and_metacharacters(self):
        node = shutil.which('node')
        self.assertIsNotNone(node, 'Development verification requires Node; operators use the shipped UI')
        with tempfile.TemporaryDirectory() as directory:
            prefix, package = self.installation(directory)
            (prefix / 'node.exe').unlink()
            if os.name == 'nt': shutil.copy2(node, prefix / 'node.exe')
            else: (prefix / 'node.exe').symlink_to(node)
            arguments = ['IAPP.SOURCE(MEMBER)', 'ZAPP.SOURCE(OTHER)', 'space value', 'x&y', 'x%PATH%', '\"quoted\"', '0000123']
            with patch('sys.platform', 'win32'), patch('shutil.which', return_value=str(prefix / 'zowe.cmd')):
                result = connectors.bounded_command(['zowe', *arguments], {'PATH': os.environ.get('PATH', '')})
            self.assertEqual(result, {'success': True, 'args': arguments})


if __name__ == '__main__':
    unittest.main()
