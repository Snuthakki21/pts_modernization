import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from workbench.domain import MAX_UPLOAD, ValidationError, decode, encode
from workbench.layout import output_path, validate_workspace
from workbench.limits import (MAX_HTTP_BODY_BYTES, MAX_JSON_DOCUMENT_BYTES,
                              MAX_SOURCE_BYTES, MAX_SOURCE_ENTRIES,
                              MAX_SOURCE_FILE_BYTES, MAX_SOURCE_FILES,
                              MAX_SOURCE_LINES, MAX_UI_SOURCE_BYTES,
                              source_line_count)
from workbench.preflight import _read_sources


class RepositoryCapacityTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.folder = self.root / 'Endeavor'
        self.folder.mkdir()

    def test_real_export_shape_822_files_including_700570_byte_source(self):
        for index in range(821):
            (self.folder / f'MEMBER{index:04}.cbl').write_bytes(b'      * exported member\n')
        large = b'      * source export\n' + b' ' * (700570 - 22)
        self.assertEqual(len(large), 700570)
        (self.folder / 'LARGE.cbl').write_bytes(large)
        files, size = _read_sources(self.root)
        self.assertEqual(len(files), 822)
        self.assertEqual(len(files['LARGE.cbl'].encode('utf-8')), 700570)
        self.assertEqual(size, 700570 + 821 * len(b'      * exported member\n'))
        from test_workflow import MANIFEST
        from workbench.coordinator import Coordinator
        coordinator = Coordinator(self.root)
        self.addCleanup(coordinator.close)
        doc = coordinator.create(MANIFEST)
        self.assertEqual(len(doc['source_files']), 822)
        self.assertEqual((self.root / 'processes/process-a/input/sources/LARGE.cbl').read_bytes(), large)

    def test_source_file_count_accepts_boundary_with_nested_directories(self):
        # Real filesystem coverage for the advertised bound, including directory
        # entries that must not consume the file allowance.
        for group in range(10):
            folder = self.folder / f'LIB{group}'
            folder.mkdir()
            for index in range(MAX_SOURCE_FILES // 10):
                (folder / f'M{index:04}').write_bytes(b'A')
        files, size = _read_sources(self.root)
        self.assertEqual(len(files), MAX_SOURCE_FILES)
        self.assertEqual(size, MAX_SOURCE_FILES)
        (self.folder / 'ONE_MORE').write_bytes(b'A')
        with self.assertRaisesRegex(ValidationError, 'file limit'):
            _read_sources(self.root)

    def test_source_file_limit_counts_utf8_bytes(self):
        path = self.folder / 'UTF8.cbl'
        with patch('workbench.preflight.MAX_SOURCE_FILE_BYTES', 4):
            path.write_text('éé', encoding='utf-8')
            self.assertEqual(_read_sources(self.root)[1], 4)
            path.write_text('ééa', encoding='utf-8')
            with self.assertRaisesRegex(ValidationError, 'byte limit'):
                _read_sources(self.root)

    def test_source_reads_are_bounded_when_file_grows_after_stat(self):
        path = self.folder / 'GROWING.cbl'
        path.write_bytes(b'A')
        original_open = Path.open
        sizes = []

        class GrowingStream:
            def __enter__(self): return self
            def __exit__(self, *args): return False
            def read(self, size):
                sizes.append(size)
                return b'A' * size

        def opened(selected, *args, **kwargs):
            return GrowingStream() if selected == path else original_open(selected, *args, **kwargs)

        with patch('workbench.preflight.MAX_SOURCE_FILE_BYTES', 16), patch.object(Path, 'open', opened):
            with self.assertRaisesRegex(ValidationError, 'byte limit'):
                _read_sources(self.root)
        self.assertEqual(sizes, [17])

    def test_combined_byte_bound_limits_the_last_read_to_remaining_budget(self):
        first, last = self.folder / 'A.cbl', self.folder / 'B.cbl'
        first.write_bytes(b'1234')
        last.write_bytes(b'1234')
        original_open = Path.open
        sizes = []

        class ObservedStream:
            def __enter__(self):
                self.handle = original_open(last, 'rb')
                return self
            def __exit__(self, *args): self.handle.close()
            def read(self, size):
                sizes.append(size)
                return self.handle.read(size)

        def opened(selected, *args, **kwargs):
            return ObservedStream() if selected == last else original_open(selected, *args, **kwargs)

        with patch('workbench.preflight.MAX_SOURCE_BYTES', 6), patch.object(Path, 'open', opened):
            with self.assertRaisesRegex(ValidationError, 'combined limit'):
                _read_sources(self.root)
        self.assertEqual(sizes, [3])

    def test_directory_entry_limit_stops_enumeration_before_sorting(self):
        consumed = []

        class Entry:
            path = str(self.folder / 'member')
            def is_symlink(self): return False
            def is_dir(self, **kwargs): return False

        class Children:
            def __enter__(self): return self
            def __exit__(self, *args): return False
            def __iter__(self):
                for index in range(5):
                    consumed.append(index)
                    yield Entry()
                raise AssertionError('Traversal consumed past the configured bound')

        with patch('workbench.preflight.MAX_SOURCE_ENTRIES', 4), patch('workbench.preflight.os.scandir', return_value=Children()):
            with self.assertRaisesRegex(ValidationError, 'directory traversal'):
                _read_sources(self.root)
        self.assertEqual(consumed, [0, 1, 2, 3, 4])

    def test_physical_line_count_matches_splitlines_for_all_text_separators(self):
        for text in ('', 'A', '\n', 'A\n', '\r\n', '\r\r\n', '\n\n',
                     'A\nB\rC\r\nD\vE\fF\x1cG\x1dH\x1eI\x85J\u2028K\u2029'):
            with self.subTest(text=repr(text)):
                self.assertEqual(source_line_count(text), len(text.splitlines()))

    def test_combined_physical_line_limit_is_inclusive(self):
        (self.folder / 'A.cbl').write_text('A\nB\n')
        (self.folder / 'B.cbl').write_text('C\nD')
        with patch('workbench.preflight.MAX_SOURCE_LINES', 4):
            self.assertEqual(len(_read_sources(self.root)[0]), 2)
            (self.folder / 'B.cbl').write_text('C\nD\nE')
            with self.assertRaisesRegex(ValidationError, 'physical-line'):
                _read_sources(self.root)

    def test_tooling_root_entries_pass_without_reading_configuration_contents(self):
        for name in ('mcp.json', '.mcp.json', 'zowe.config.json', 'zowe.config.user.json',
                     'zowe.schema.json', 'zowe.config.user.schema.json'):
            (self.root / name).write_text('contents need not be parsed by layout')
        for name in ('.vscode/settings.json', 'Visio/flow.vsdx', 'certificates/DB2-CA.cert'):
            path = self.root / name
            path.parent.mkdir(exist_ok=True)
            path.write_bytes(b'private config or diagram')
        with patch.object(Path, 'open', side_effect=AssertionError('Layout must not read configuration contents')):
            self.assertEqual(validate_workspace(self.root), [])

    def test_tooling_entries_do_not_bypass_process_output_placement(self):
        for name in ('mcp.json', 'zowe.config.json', '.vscode/settings.json', 'Visio/flow.vsdx'):
            with self.subTest(name=name), self.assertRaises(ValidationError):
                output_path(self.root, 'process-a', name)
        path = self.root / 'processes/process-a/.vscode/settings.json'
        path.parent.mkdir(parents=True)
        path.write_text('{}')
        self.assertTrue(any('misplaced process output' in issue for issue in validate_workspace(self.root)))

    def test_nested_tooling_symlink_is_blocked_without_reading_target(self):
        folder = self.root / '.vscode'
        folder.mkdir()
        try: (folder / 'settings.json').symlink_to(self.root / 'outside.json')
        except OSError: self.skipTest('Symlinks unavailable')
        with patch.object(Path, 'open', side_effect=AssertionError('Layout must not read symlink targets')):
            self.assertTrue(any('symlink' in issue for issue in validate_workspace(self.root)))

    def test_certificate_symlink_is_blocked_without_reading_certificate_contents(self):
        folder = self.root / 'certificates'
        folder.mkdir()
        try: (folder / 'DB2-CA.cert').symlink_to(self.root / 'outside.cert')
        except OSError: self.skipTest('Symlinks unavailable')
        with patch.object(Path, 'open', side_effect=AssertionError('Layout must not read certificates')):
            self.assertTrue(any('symlink' in issue for issue in validate_workspace(self.root)))

    def test_json_state_is_independent_of_upload_and_source_bounds(self):
        self.assertEqual(MAX_SOURCE_FILES, 10_000)
        self.assertEqual(MAX_SOURCE_FILE_BYTES, 16 * 1024 * 1024)
        self.assertEqual(MAX_SOURCE_BYTES, 512 * 1024 * 1024)
        self.assertEqual(MAX_SOURCE_LINES, 2_000_000)
        self.assertGreater(MAX_SOURCE_ENTRIES, MAX_SOURCE_FILES)
        self.assertEqual(MAX_UPLOAD, 8 * 1024 * 1024)
        self.assertEqual(MAX_UI_SOURCE_BYTES, 32 * 1024 * 1024)
        self.assertEqual(MAX_HTTP_BODY_BYTES, 128 * 1024 * 1024)
        self.assertEqual(MAX_JSON_DOCUMENT_BYTES, 128 * 1024 * 1024)
        raw = json.dumps({'evidence': 'A' * (MAX_UPLOAD + 1)}).encode('utf-8')
        self.assertEqual(len(decode(raw)['evidence']), MAX_UPLOAD + 1)
        with self.assertRaises(ValidationError): decode(raw, MAX_UPLOAD)
        with self.assertRaises(ValidationError): encode({'evidence': 'A' * 100}, limit=50)


if __name__ == '__main__': unittest.main()
