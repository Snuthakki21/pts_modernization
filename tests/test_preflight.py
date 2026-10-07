import json
import os
import socket
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from test_source import COBOL
from test_workflow import MANIFEST
from workbench.preflight import inspect_workspace, initialize_knowledge


class PreflightTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        (self.root / 'Endeavor').mkdir()
        (self.root / 'Endeavor/ELIGIBLE.cbl').write_text(COBOL)
        self.manifest = self.root / 'process-input.md'
        self.manifest.write_text(MANIFEST)

    def inspect(self, **kwargs):
        return inspect_workspace(self.root, self.manifest, environ={}, **kwargs)

    def check(self, result, name):
        return next(c for c in result['checks'] if c['id'] == name)

    def test_offline_preflight_preserves_sources_and_creates_no_files(self):
        before = {p.relative_to(self.root).as_posix(): p.read_bytes() for p in self.root.rglob('*') if p.is_file()}
        with patch('urllib.request.build_opener', side_effect=AssertionError('No network')):
            result = self.inspect()
        after = {p.relative_to(self.root).as_posix(): p.read_bytes() for p in self.root.rglob('*') if p.is_file()}
        self.assertEqual(before, after)
        self.assertEqual(result['status'], 'READY')
        self.assertEqual(result['conversion_status'], 'UNVERIFIED')
        self.assertEqual(self.check(result, 'db2')['status'], 'NOT_CONFIGURED')

    def test_unknown_program_is_explicit_conversion_blocker_not_setup_failure(self):
        self.manifest.write_text(MANIFEST.replace('ELIGIBLE', 'APPWRAP'))
        result = self.inspect()
        self.assertEqual(result['status'], 'READY')
        self.assertEqual(result['conversion_status'], 'BLOCKED')
        self.assertTrue(result['conversion_blockers'])

    def test_recognized_mainframe_utility_requires_verified_adapter(self):
        self.manifest.write_text(MANIFEST.replace('ELIGIBLE', 'SORT'))
        result = self.inspect()
        self.assertEqual(result['status'], 'READY')
        self.assertEqual(result['conversion_status'], 'BLOCKED')
        self.assertTrue(any(b['kind'] == 'unsupported_utility' for b in result['conversion_blockers']))

    def test_invalid_utf8_and_binary_source_are_blocked(self):
        for body in (b'\xff\xfe', b'COBOL\x00binary'):
            with self.subTest(body=body):
                (self.root / 'Endeavor/ELIGIBLE.cbl').write_bytes(body)
                self.assertEqual(self.check(self.inspect(), 'source_export')['status'], 'BLOCKED')

    def assert_source_collision(self, paths, directories=()):
        # Supply filesystem entries directly: macOS/Windows cannot physically
        # create case/normalization-equivalent names. The real scanner still
        # validates and reads the first entry before rejecting the collision.
        from contextlib import contextmanager
        from workbench.preflight import _read_sources
        from workbench.domain import ValidationError
        folder=self.root/'Endeavor';real_is_dir=Path.is_dir
        class Entry:
            def __init__(self,path):self.path=str(path)
            def is_symlink(self):return False
            def is_dir(self,follow_symlinks=False):return Path(self.path) in directories
        @contextmanager
        def scanned(path):
            yield iter(Entry(p) for p in (paths if Path(path)==folder else ()))
        def is_dir(path):return path in directories or real_is_dir(path)
        with patch('workbench.preflight.os.scandir',scanned),patch.object(Path,'is_dir',is_dir):
            with self.assertRaisesRegex(ValidationError,'collide'):_read_sources(self.root)

    def test_case_collisions_are_blocked(self):
        self.assert_source_collision([self.root/'Endeavor/ELIGIBLE.cbl',self.root/'Endeavor/eligible.CBL'])

    def test_unicode_normalization_and_file_directory_collisions_are_blocked(self):
        nfd=self.root/'Endeavor/cafe\u0301.cbl';nfd.write_text('A')
        self.assert_source_collision([nfd,self.root/'Endeavor/caf\u00e9.cbl'])
        directory=self.root/'Endeavor/ELIGIBLE.CBL'
        self.assert_source_collision([directory,self.root/'Endeavor/ELIGIBLE.cbl'],[directory])

    def test_source_symlink_is_blocked_without_following_it(self):
        try: (self.root / 'Endeavor/other.cbl').symlink_to(self.manifest)
        except OSError: self.skipTest('Symlinks unavailable')
        result = self.inspect()
        self.assertEqual(result['status'], 'BLOCKED')

    def test_boundaries_are_checked_before_source_read(self):
        from workbench.limits import MAX_SOURCE_FILE_BYTES
        with (self.root / 'Endeavor/ELIGIBLE.cbl').open('wb') as source:
            source.truncate(MAX_SOURCE_FILE_BYTES + 1)
        self.assertEqual(self.check(self.inspect(), 'source_export')['status'], 'BLOCKED')

    def test_physical_line_limit_rejects_newline_only_source_before_analysis(self):
        from workbench.domain import MAX_SOURCE_LINES
        (self.root / 'Endeavor/ELIGIBLE.cbl').write_bytes(b'\n' * (MAX_SOURCE_LINES + 1))
        with patch('workbench.source.analyze_sources', side_effect=AssertionError('Oversized source must never be analyzed')):
            result = self.inspect()
        self.assertEqual(self.check(result, 'source_export')['status'], 'BLOCKED')
        self.assertIn('physical-line', self.check(result, 'source_export')['message'])

    def test_physical_line_limit_applies_to_combined_export(self):
        from workbench.domain import MAX_SOURCE_LINES
        (self.root / 'Endeavor/ELIGIBLE.cbl').write_bytes(b'\n' * (MAX_SOURCE_LINES // 2))
        (self.root / 'Endeavor/SECOND.cbl').write_bytes(b'\n' * (MAX_SOURCE_LINES // 2 + 1))
        with patch('workbench.source.analyze_sources', side_effect=AssertionError('Oversized source must never be analyzed')):
            self.assertEqual(self.check(self.inspect(), 'source_export')['status'], 'BLOCKED')

    def test_manifest_missing_and_invalid_are_actionable(self):
        self.manifest.unlink()
        self.assertEqual(self.check(self.inspect(), 'manifest')['status'], 'BLOCKED')
        self.manifest.write_text('not a manifest')
        self.assertEqual(self.check(self.inspect(), 'manifest')['status'], 'BLOCKED')

    def test_missing_dependency_and_bundle_are_blocked(self):
        from importlib.metadata import PackageNotFoundError
        with patch('workbench.preflight.metadata.version', side_effect=PackageNotFoundError):
            result = self.inspect()
        self.assertEqual(self.check(result, 'dependencies')['status'], 'BLOCKED')
        with patch('workbench.preflight.STATIC_ROOT', self.root / 'absent'):
            self.assertEqual(self.check(self.inspect(), 'frontend')['status'], 'BLOCKED')

    def test_connector_settings_never_prove_connectivity_or_echo_secrets(self):
        env = {'WB_DB2_MCP_URL':'https://example.invalid/mcp?secret=PRIVATE',
               'WB_DB2_MCP_TOKEN':'PRIVATE_TOKEN', 'WB_LLM_URL':'https://example.invalid/completions',
               'WB_LLM_MODEL':'PRIVATE_MODEL', 'WB_LLM_TOKEN':'PRIVATE_LLM', 'WB_ALLOW_SOURCE_EGRESS':'true'}
        result = inspect_workspace(self.root, self.manifest, environ=env)
        self.assertEqual(self.check(result, 'db2')['status'], 'UNVERIFIED')
        self.assertEqual(self.check(result, 'llm')['status'], 'UNVERIFIED')
        self.assertNotIn('PRIVATE', json.dumps(result))

    def test_bad_endpoint_and_partial_provider_configuration_are_blocked(self):
        env = {'WB_DB2_MCP_URL':'http://remote.invalid/mcp', 'WB_LLM_URL':'https://example.invalid/completions'}
        result = inspect_workspace(self.root, self.manifest, environ=env)
        self.assertEqual(self.check(result, 'db2')['status'], 'BLOCKED')
        self.assertEqual(self.check(result, 'llm')['status'], 'BLOCKED')

    def test_existing_instance_lock_and_occupied_port_are_reported(self):
        from workbench.instance import InstanceLock
        lock = InstanceLock(self.root)
        try:
            self.assertEqual(self.check(self.inspect(), 'workspace_lock')['status'], 'BLOCKED')
            self.assertEqual(self.check(self.inspect(coordinator_owned=True), 'workspace_lock')['status'], 'READY')
        finally: lock.close()
        self.assertEqual(self.check(self.inspect(), 'workspace_lock')['status'], 'READY')
        with socket.socket() as sock:
            sock.bind(('127.0.0.1', 0)); sock.listen(1)
            result = self.inspect(port=sock.getsockname()[1])
            self.assertEqual(self.check(result, 'ui_port')['status'], 'BLOCKED')

    def test_low_disk_and_os_permission_denial_are_blocked(self):
        with patch('workbench.preflight.shutil.disk_usage', return_value=type('Usage', (), {'free':1})()):
            self.assertEqual(self.check(self.inspect(), 'disk_space')['status'], 'BLOCKED')
        with patch('workbench.preflight.os.access', return_value=False):
            self.assertEqual(self.check(self.inspect(), 'workspace_access')['status'], 'BLOCKED')

    def test_context_bounds_are_checked_before_any_workflow(self):
        context = self.root / 'knowledge/inbox/context.md'; context.parent.mkdir(parents=True)
        from workbench.process_context import MAX_CONTEXT_BYTES
        context.write_bytes(b'x' * (MAX_CONTEXT_BYTES+1))
        self.assertEqual(self.check(self.inspect(), 'background_context')['status'], 'BLOCKED')

    def test_initialization_is_explicit_and_never_overwrites_custom_knowledge(self):
        destination = initialize_knowledge(self.root)
        original = destination.read_bytes()
        initialize_knowledge(self.root)
        self.assertEqual(destination.read_bytes(), original)
        destination.write_bytes(b'PRIVATE APPLICATION KNOWLEDGE')
        initialize_knowledge(self.root)
        self.assertEqual(destination.read_bytes(), b'PRIVATE APPLICATION KNOWLEDGE')

    def test_cli_json_has_machine_readable_exit_status(self):
        result = subprocess.run([sys.executable, '-m', 'workbench.preflight', '--workspace', str(self.root),
                                 '--manifest', str(self.manifest), '--json'], capture_output=True, text=True,
                                env={k:v for k,v in os.environ.items() if not k.startswith('WB_')}, timeout=30)
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        self.assertEqual(json.loads(result.stdout)['status'], 'READY')

    def test_malformed_excel_and_application_knowledge_produce_diagnostics(self):
        excel = self.root / 'intake-template.xlsx'; excel.write_bytes(b'not a workbook')
        result = inspect_workspace(self.root, excel, environ={})
        self.assertEqual(self.check(result, 'manifest')['status'], 'BLOCKED')
        initialize_knowledge(self.root).write_text('{"utilities":NaN}')
        self.assertEqual(self.check(self.inspect(), 'mainframe_knowledge')['status'], 'BLOCKED')

    def test_source_and_file_count_limits(self):
        for index in range(200): (self.root / f'Endeavor/F{index}').write_text('A')
        with patch('workbench.preflight.MAX_SOURCE_FILES', 200):
            self.assertEqual(self.check(self.inspect(), 'source_export')['status'], 'BLOCKED')

    def test_missing_zowe_command_and_invalid_egress_setting_block(self):
        with patch('workbench.preflight.shutil.which', return_value=None):
            result = inspect_workspace(self.root, environ={'WB_ZOWE_PROFILE':'approved'})
        self.assertEqual(self.check(result, 'zowe')['status'], 'BLOCKED')
        result = inspect_workspace(self.root, environ={'WB_LLM_URL':'https://example.invalid/chat',
            'WB_LLM_MODEL':'approved', 'WB_ALLOW_SOURCE_EGRESS':'YES'})
        self.assertEqual(self.check(result, 'llm')['status'], 'BLOCKED')


    def test_unusable_native_zowe_entry_point_blocks_without_executing_cli(self):
        from workbench.domain import ValidationError
        with patch('workbench.preflight.shutil.which', return_value='private/zowe.cmd'), \
                patch('workbench.connectors.zowe_command', side_effect=ValidationError('Private malformed launcher')) as command, \
                patch('subprocess.Popen', side_effect=AssertionError('Offline checks must not execute Zowe')):
            result = inspect_workspace(self.root, environ={'WB_ZOWE_PROFILE': 'approved'})
        self.assertEqual(self.check(result, 'zowe')['status'], 'BLOCKED')
        self.assertNotIn('Private', json.dumps(result))
        command.assert_called_once()


if __name__ == '__main__': unittest.main()
