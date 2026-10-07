"""Offline lock-closure regressions; package metadata is fictional."""
import importlib.util
from pathlib import Path
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('lock_generator', ROOT/'tools/lock_dependencies.py')
lock = importlib.util.module_from_spec(spec)
spec.loader.exec_module(lock)


def metadata(dependencies=(), python='>=3.12'):
    return {'info': {'requires_dist': list(dependencies), 'requires_python': python}}


class DependencyClosureTests(unittest.TestCase):
    def validate(self, pins, releases, markers=None):
        with patch.object(lock, 'PINS', pins), patch.object(lock, 'MARKERS', markers or {}):
            lock.validate_dependencies(releases)

    def test_requested_extra_missing_dependency_rejected(self):
        with self.assertRaisesRegex(ValueError, 'missing-leaf'):
            self.validate({'root':'1', 'child':'1'}, {
                'root':metadata(['child[feature]>=1']),
                'child':metadata(['missing-leaf>=1; extra == "feature"'])})

    def test_extra_cycle_and_normalized_name_accepted(self):
        self.validate({'root':'1', 'child':'1'}, {
            'root':metadata(['child[my_feature]>=1']),
            'child':metadata(['root[feature]>=1; extra == "my-feature"'])})

    def test_unrequested_extra_does_not_add_requirement(self):
        self.validate({'root':'1'}, {'root':metadata(['absent; extra == "unused"'])})

    def test_wrong_version_rejected(self):
        with self.assertRaisesRegex(ValueError, 'incompatible pin'):
            self.validate({'root':'1','child':'1'}, {
                'root':metadata(['child>=2']), 'child':metadata()})

    def test_direct_url_rejected(self):
        with self.assertRaisesRegex(ValueError, 'incompatible pin'):
            self.validate({'root':'1','child':'1'}, {
                'root':metadata(['child @ https://example.invalid/child.whl']), 'child':metadata()})

    def test_unsupported_python_rejected(self):
        with self.assertRaisesRegex(ValueError, 'Python 3.12'):
            self.validate({'root':'1'}, {'root':metadata(python='>=3.13')})

    def test_windows_os_name_is_native(self):
        with self.assertRaisesRegex(ValueError, 'Windows/AMD64'):
            self.validate({'root':'1'}, {'root':metadata(['absent; os_name == "nt"'])})

    def test_macos_arm64_is_checked(self):
        with self.assertRaisesRegex(ValueError, 'Darwin/arm64'):
            self.validate({'root':'1'}, {'root':metadata(['absent; platform_machine == "arm64"'])})

    def test_linux_pin_not_available_for_windows_dependency(self):
        with self.assertRaisesRegex(ValueError, 'Windows/AMD64'):
            self.validate({'root':'1','linux':'1'}, {
                'root':metadata(['linux']), 'linux':metadata()},
                {'linux':'sys_platform == "linux"'})

    def test_platform_specific_dependency_accepted(self):
        self.validate({'root':'1','win':'1'}, {
            'root':metadata(['win; sys_platform == "win32"']), 'win':metadata()},
            {'win':'sys_platform == "win32"'})

    def test_metadata_mismatch_rejected(self):
        with self.assertRaisesRegex(ValueError, 'match the reviewed pins'):
            self.validate({'root':'1'}, {})

    def test_unknown_marker_pin_rejected(self):
        with self.assertRaisesRegex(ValueError, 'match the reviewed pins'):
            self.validate({'root':'1'}, {'root':metadata()}, {'absent':'sys_platform == "win32"'})


if __name__ == '__main__':
    unittest.main(verbosity=2)
