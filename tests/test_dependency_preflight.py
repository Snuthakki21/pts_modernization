"""Release readiness must check only the host's strictly parsed lock entries."""
from importlib.metadata import PackageNotFoundError
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from packaging.markers import default_environment

from workbench.preflight import inspect_workspace


HASH = '--hash=sha256:' + 'a' * 64


def pin(requirement):
    return requirement + ' \\\n    ' + HASH + '\n'


class DependencyPreflightTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()

    def dependencies(self, content, versions, environment=None):
        (self.root / 'requirements.lock').write_text(content)

        def installed(name):
            if name not in versions:
                raise PackageNotFoundError(name)
            return versions[name]

        env = default_environment() if environment is None else environment
        with patch('workbench.preflight.REPOSITORY', self.root), \
                patch('workbench.preflight.metadata.version', side_effect=installed) as requested, \
                patch('packaging.markers.default_environment', return_value=env), \
                patch('workbench.preflight.importlib.import_module'):
            result = inspect_workspace(self.root / 'absent', environ={})
        check = next(item for item in result['checks'] if item['id'] == 'dependencies')
        return check, [call.args[0] for call in requested.call_args_list]

    def test_only_host_platform_requirements_are_checked(self):
        lock = (pin('common==1.0') + pin('windows==2.0; sys_platform == "win32"') +
                pin('linux==3.0; sys_platform == "linux"'))
        for platform, extra in [('darwin', {}), ('linux', {'linux':'3.0'}), ('win32', {'windows':'2.0'})]:
            with self.subTest(platform=platform):
                env = dict(default_environment(), sys_platform=platform)
                versions = {'common':'1.0', **extra}
                check, requested = self.dependencies(lock, versions, env)
                self.assertEqual(check['status'], 'READY', check)
                self.assertEqual(set(requested), set(versions))
                self.assertIn(str(len(versions)) + ' installed', check['message'])

    def test_missing_active_dependency_blocks(self):
        check, requested = self.dependencies(pin('required==1.0'), {})
        self.assertEqual(check['status'], 'BLOCKED')
        self.assertIn('required is missing', check['message'])
        self.assertEqual(requested, ['required'])

    def test_active_version_mismatch_blocks(self):
        check, _ = self.dependencies(pin('required==1.0'), {'required':'2.0'})
        self.assertEqual(check['status'], 'BLOCKED')
        self.assertIn('version differs', check['message'])

    def test_malformed_marker_blocks_instead_of_being_ignored(self):
        check, _ = self.dependencies(pin('required==1.0; sys_platform ==== "win32"'), {'required':'1.0'})
        self.assertEqual(check['status'], 'BLOCKED')

    def test_semantically_invalid_marker_blocks_without_crashing(self):
        check, _ = self.dependencies(pin('required==1.0; os_name ~= "not-a-version"'), {'required':'1.0'})
        self.assertEqual(check['status'], 'BLOCKED')
        self.assertIn('Invalid dependency lock marker', check['message'])

    def test_invalid_entries_cannot_hide_beside_valid_pin(self):
        for invalid in [pin('other>=1'), pin('other==1.*'), pin('other @ https://example.invalid/file.whl'),
                        pin('other[extra]==1'), 'not a requirement\n', '--index-url https://example.invalid\n',
                        'other==1.0\n', 'other==1.0 \\\n    --hash=sha256:bad\n',
                        pin('other==1.0; sys_platform == "never"').replace(HASH, '--hash=md5:' + 'a'*32)]:
            with self.subTest(invalid=invalid):
                check, _ = self.dependencies(pin('required==1.0') + invalid, {'required':'1.0'})
                self.assertEqual(check['status'], 'BLOCKED', check)

    def test_duplicate_normalized_names_block(self):
        check, _ = self.dependencies(pin('my-package==1.0') + pin('my_package==1.0'), {'my-package':'1.0', 'my_package':'1.0'})
        self.assertEqual(check['status'], 'BLOCKED')

    def test_incomplete_continuation_blocks(self):
        check, _ = self.dependencies(pin('required==1.0') + 'other==2.0 \\\n', {'required':'1.0'})
        self.assertEqual(check['status'], 'BLOCKED')

    def test_blank_or_comment_only_lock_blocks(self):
        for lock in ['', '# No entries\n\n']:
            with self.subTest(lock=lock):
                check, requested = self.dependencies(lock, {})
                self.assertEqual(check['status'], 'BLOCKED')
                self.assertEqual(requested, [])

    def test_comments_crlf_and_multiple_hashes_are_accepted(self):
        lock = '# Release lock\r\n\r\nrequired==1.0 \\\r\n    ' + HASH + ' \\\r\n    ' + HASH + '\r\n'
        check, requested = self.dependencies(lock, {'required':'1.0'})
        self.assertEqual(check['status'], 'READY', check)
        self.assertEqual(requested, ['required'])

    def test_python_and_os_markers_use_host_environment(self):
        lock = pin('required==1.0; python_version == "3.12" and os_name == "nt"')
        for os_name, versions in [('nt', {'required':'1.0'}), ('posix', {})]:
            with self.subTest(os_name=os_name):
                env = dict(default_environment(), python_version='3.12', os_name=os_name)
                check, requested = self.dependencies(lock, versions, env)
                self.assertEqual(check['status'], 'READY', check)
                self.assertEqual(requested, list(versions))


if __name__ == '__main__':
    unittest.main()
