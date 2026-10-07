"""File-only Copilot retrieval contracts; no host or network is contacted."""
import random
import secrets
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from workbench.domain import ValidationError, encode, sha
from workbench.retrieval import build_request, inspect_response, validate_binding, write_request


class RetrievalTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name).resolve()
        self.doc = {'id': 'PAYROLL', 'source_files': {'jobs/PAY.jcl': sha('original')},
                    'copilot_iteration': 2, 'lineage_artifact': 'analysis/lineage-a.json',
                    'artifact_hashes': {'analysis/lineage-a.json': sha('lineage')},
                    'lineage': {'closure': {'gaps': [
                        {'kind': 'copybook', 'name': 'EMPLOYEE', 'source': 'program:PAY',
                         'relationship': 'copy', 'status': 'missing', 'reason': 'Referenced copybook absent'}]}}}
        self.request = build_request(self.doc)
        self.relative = write_request(self.root, self.request)
        self.inbox = self.root / self.request['return_folder']

    def item(self, text='       01 EMPLOYEE PIC X(20).\n', path='copybooks/EMPLOYEE.cpy', need=None):
        file = self.inbox / 'files' / path
        file.parent.mkdir(parents=True, exist_ok=True)
        file.write_bytes(text.encode('utf-8'))
        return {'need_id': need or self.request['needs'][0]['need_id'], 'status': 'FOUND',
                'path': path, 'sha256': sha(text), 'provenance': self.provenance()}

    @staticmethod
    def provenance():
        return {'origin': 'configured_mcp', 'tool': 'approved_read_member',
                'locator': 'APP.COPYLIB(EMPLOYEE)', 'retrieved_at': '2026-10-06T12:00:00Z'}

    def response(self, items, **changes):
        value = {'request_id': self.request['request_id'], 'items': items, **changes}
        (self.inbox / 'response.json').write_bytes(encode(value))
        return value

    def test_request_is_immutable_idempotent_and_bound(self):
        self.assertEqual(self.relative, write_request(self.root, self.request))
        self.assertEqual(self.request, build_request(self.doc))
        self.assertIn(self.request['return_folder'], self.request['copilot_prompt'])
        self.assertIn('Do not analyze', self.request['copilot_prompt'])
        validate_binding(self.request, self.doc)
        for change in ({'id': 'OTHER'}, {'source_files': {'new': sha('new')}},
                       {'copilot_iteration': 3}, {'artifact_hashes': {}}):
            with self.subTest(change=change), self.assertRaises(ValidationError):
                validate_binding(self.request, {**self.doc, **change})
        path = self.root / 'processes' / self.doc['id'] / self.relative
        path.write_bytes(b'{}')
        with self.assertRaises(ValidationError):
            write_request(self.root, self.request)

    def test_waiting_for_final_manifest_does_not_consume_staged_file(self):
        self.item()
        result = inspect_response(self.root, self.request)
        self.assertEqual(result['status'], 'WAITING_FOR_RESPONSE')
        self.assertEqual(result['entries'], [])
        self.assertFalse(result['complete'])

    def test_twenty_runtime_randomized_valid_sources_replay_identically(self):
        seed = secrets.randbits(63)
        rng = random.Random(seed)
        for index in range(20):
            with self.subTest(seed=seed, case=index):
                name = rng.choice(('I', 'Z')) + f'COPY{rng.randrange(999999):06}'
                text = f'       01 {name} PIC 9({rng.randint(1, 18)}).\n'
                path = f'lib{index}/{name}.cpy'
                item = self.item(text, path)
                self.response([item])
                first = inspect_response(self.root, self.request)
                self.assertEqual(first, inspect_response(self.root, self.request))
                self.assertEqual(first['entries'][0]['text'], text)
                self.assertEqual(first['entries'][0]['source_hash'], sha(text))
                self.assertEqual(first['entries'][0]['path'], path)
                self.assertTrue(first['complete'])
                (self.inbox / 'files' / path).unlink()

    def test_partial_responses_account_for_every_need_without_implying_resolution(self):
        self.request = build_request(self.doc, [
            {'kind': 'copybook', 'name': 'A', 'reason': 'COPY A'},
            {'kind': 'program', 'name': 'B', 'reason': 'CALL B'},
            {'kind': 'proc', 'name': 'C', 'reason': 'EXEC C'}])
        write_request(self.root, self.request)
        self.inbox = self.root / self.request['return_folder']
        found = self.item(need=self.request['needs'][0]['need_id'])
        missing = {'need_id': self.request['needs'][1]['need_id'], 'status': 'NOT_FOUND',
                   'reason': 'No member in approved library', 'provenance': self.provenance()}
        ambiguous = {'need_id': self.request['needs'][2]['need_id'], 'status': 'AMBIGUOUS',
                     'reason': 'Two libraries contain this member', 'candidates': ['A.C', 'B.C'],
                     'provenance': self.provenance()}
        self.response([found, missing, ambiguous])
        result = inspect_response(self.root, self.request)
        self.assertEqual(len(result['entries']), 1)
        self.assertEqual(result['missing_items'], [missing, ambiguous])
        self.assertFalse(result['complete'])
        self.assertEqual(len(result['items']), 3)

    def test_twenty_malformed_returns_cannot_be_consumed(self):
        seed = secrets.randbits(63)
        rng = random.Random(seed)
        token = str(rng.randrange(10**8))
        changes = [
            {'path': '../escape' + token}, {'path': '/absolute' + token},
            {'path': 'dir\\file' + token}, {'path': './copybooks/EMPLOYEE.cpy'},
            {'path': 'copybooks//EMPLOYEE.cpy'}, {'path': 'NUL.cpy'},
            {'path': 'a:drive.cpy'}, {'path': 'space /a.cpy'},
            {'path': 'dot./a.cpy'}, {'path': 'bad?name.cpy'},
            {'sha256': '0' * 64}, {'sha256': 'F' * 64},
            {'need_id': 'unknown' + token}, {'status': 'RESOLVED'},
            {'provenance': {}}, {'provenance': {'origin': 'unknown'}},
            {'provenance': {**self.provenance(), 'retrieved_at': 'today'}},
            {'provenance': {**self.provenance(), 'retrieved_at': '2026-10-06T12:00:00'}},
            {'execute': 'please_run'}, {'path': 3}]
        item = self.item()
        for index, change in enumerate(changes):
            with self.subTest(seed=seed, case=index):
                self.response([{**item, **change}])
                with self.assertRaises(ValidationError):
                    inspect_response(self.root, self.request)

    def test_inventory_must_exactly_match_response(self):
        item = self.item()
        self.response([item])
        rogue = self.inbox / 'files' / 'unlisted.cpy'
        rogue.write_text('DATA')
        with self.assertRaisesRegex(ValidationError, 'unlisted|inventory'):
            inspect_response(self.root, self.request)
        rogue.unlink()
        with self.assertRaises(ValidationError):
            inspect_response(self.root, self.request, {'COPYBOOKS/EMPLOYEE.cpy': sha('different')})
        with self.assertRaises(ValidationError):
            inspect_response(self.root, self.request, {'copybooks/EMPLOYEE.cpy': sha('different')})
        self.assertTrue(inspect_response(self.root, self.request, {item['path']: item['sha256']})['complete'])

    def test_request_and_response_identity_tampering(self):
        item = self.item()
        for change in ({'request_id': '0' * 64}, {'other': True}):
            self.response([item], **change)
            with self.assertRaises(ValidationError):
                inspect_response(self.root, self.request)
        self.response([item, item])
        with self.assertRaises(ValidationError):
            inspect_response(self.root, self.request)
        self.response([])
        with self.assertRaises(ValidationError):
            inspect_response(self.root, self.request)
        self.response([item])
        for field, value in (('copilot_prompt', 'changed'), ('return_folder', 'other'),
                             ('source_generation', '0' * 64)):
            changed = {**self.request, field: value}
            with self.assertRaises(ValidationError):
                inspect_response(self.root, changed)

    def test_binary_symlink_and_size_bounds(self):
        item = self.item()
        path = self.inbox / 'files' / item['path']
        for raw in (b'\xff', b'\x00', b'abc\x07def'):
            path.write_bytes(raw)
            self.response([{**item, 'sha256': sha(raw)}])
            with self.assertRaises(ValidationError):
                inspect_response(self.root, self.request)
        path.unlink()
        external = self.root / 'external.cpy'
        external.write_text('secret')
        path.symlink_to(external)
        self.response([{**item, 'sha256': sha('secret')}])
        with self.assertRaises(ValidationError):
            inspect_response(self.root, self.request)
        path.unlink()
        path.write_text('123456')
        self.response([{**item, 'sha256': sha('123456')}])
        with patch('workbench.retrieval.MAX_FILE_BYTES', 5), self.assertRaises(ValidationError):
            inspect_response(self.root, self.request)

    def test_needs_are_bounded_named_unique_and_nonempty(self):
        for needs in ([], [{'kind': 'program', 'name': '', 'reason': 'missing'}],
                      [{'kind': 'program', 'name': 'A', 'reason': 'missing', 'execute': 'bad'}]):
            with self.subTest(needs=needs), self.assertRaises(ValidationError):
                build_request(self.doc, needs)
        duplicate = {'kind': 'program', 'name': 'A', 'reason': 'missing'}
        self.assertEqual(len(build_request(self.doc, [duplicate, duplicate])['needs']), 1)
        with patch('workbench.retrieval.MAX_NEEDS', 1), self.assertRaises(ValidationError):
            build_request(self.doc, [duplicate, {**duplicate, 'name': 'B'}])

    def test_staged_text_filename_preserves_original_source_identity(self):
        for suffix in ('.md', '.py', '.db', '.sqlite'):
            with self.subTest(suffix=suffix):
                original = 'original/evidence' + suffix
                staged = 'evidence' + suffix + '.txt'
                text = 'Source export, handled only as data.\n'
                item = self.item(text, staged)
                item.update(path=original, staged_path=staged)
                self.response([item])
                result = inspect_response(self.root, self.request)
                self.assertEqual(result['entries'][0]['path'], original)
                self.assertEqual(result['entries'][0]['text'], text)
                self.assertEqual(result['items'][0]['staged_path'], staged)
                from workbench.layout import validate_workspace
                self.assertEqual(validate_workspace(self.root), [])
                (self.inbox / 'files' / staged).unlink()

    def test_staged_paths_reject_layout_violations_and_traversal(self):
        item = self.item(path='original.md')
        self.response([item])
        with self.assertRaises(ValidationError):
            inspect_response(self.root, self.request)
        (self.inbox / 'files' / 'original.md').unlink()
        item = self.item(path='source.txt')
        for staged in ('../source.txt', 'source.py', 'source.md', 'source.db', 'source.sqlite',
                       'source//text.txt', 'NUL.txt'):
            self.response([{**item, 'path': 'original.md', 'staged_path': staged}])
            with self.subTest(staged=staged), self.assertRaises(ValidationError):
                inspect_response(self.root, self.request)

    def test_staged_case_collisions_and_aliases_are_rejected(self):
        self.request = build_request(self.doc, [
            {'kind': 'copybook', 'name': 'A', 'reason': 'COPY A'},
            {'kind': 'copybook', 'name': 'B', 'reason': 'COPY B'}])
        write_request(self.root, self.request)
        self.inbox = self.root / self.request['return_folder']
        first = self.item(path='file.txt', need=self.request['needs'][0]['need_id'])
        first.update(path='original/A.md', staged_path='file.txt')
        second = {**first, 'need_id': self.request['needs'][1]['need_id'], 'path': 'original/B.md'}
        for staged in ('file.txt', 'FILE.TXT'):
            self.response([first, {**second, 'staged_path': staged}])
            with self.subTest(staged=staged), self.assertRaises(ValidationError):
                inspect_response(self.root, self.request)

    def test_original_source_paths_cannot_collide_with_frozen_tree(self):
        cases = [
            ('jobs/PAY.jcl/EMPLOYEE.cpy', {'jobs/PAY.jcl': sha('original')}),
            ('jobs/PAY.jcl', {'jobs/PAY.jcl/EMPLOYEE.cpy': sha('original')}),
            ('JOBS/pay.JCL/EMPLOYEE.cpy', {'jobs/PAY.jcl': sha('original')}),
            ('lib/EMPLOYEE.cpy', {'LIB/OTHER.cpy': sha('original')}),
            ('cafe\u0301/EMPLOYEE.cpy', {'caf\u00e9/OTHER.cpy': sha('original')}),
            ('caf\u00e9.cpy/EMPLOYEE.cpy', {'cafe\u0301.cpy': sha('original')}),
        ]
        for path, existing in cases:
            with self.subTest(path=path, existing=existing):
                item = self.item(path='staged.txt')
                item.update(path=path, staged_path='staged.txt')
                self.response([item])
                with self.assertRaisesRegex(ValidationError, 'colli'):
                    inspect_response(self.root, self.request, existing)

    def test_returned_source_tree_rejects_prefixes_and_directory_aliases(self):
        self.request = build_request(self.doc, [
            {'kind': 'copybook', 'name': 'A', 'reason': 'COPY A'},
            {'kind': 'copybook', 'name': 'B', 'reason': 'COPY B'}])
        write_request(self.root, self.request)
        self.inbox = self.root / self.request['return_folder']
        first = self.item(path='first.txt', need=self.request['needs'][0]['need_id'])
        second = self.item(path='second.txt', need=self.request['needs'][1]['need_id'])
        for paths in [('A.cpy', 'A.cpy/B.cpy'), ('A.cpy/B.cpy', 'a.CPY'),
                      ('LIB/A.cpy', 'lib/B.cpy'), ('caf\u00e9/A.cpy', 'cafe\u0301/B.cpy')]:
            with self.subTest(paths=paths):
                items = [{**item, 'path': path, 'staged_path': item['path']}
                         for item, path in zip((first, second), paths)]
                self.response(items)
                with self.assertRaisesRegex(ValidationError, 'colli'):
                    inspect_response(self.root, self.request)

    def test_staged_directory_aliases_are_not_portable_inventory(self):
        self.request = build_request(self.doc, [
            {'kind': 'copybook', 'name': 'A', 'reason': 'COPY A'},
            {'kind': 'copybook', 'name': 'B', 'reason': 'COPY B'}])
        write_request(self.root, self.request)
        self.inbox = self.root / self.request['return_folder']
        first = self.item(path='LIB/A.txt', need=self.request['needs'][0]['need_id'])
        second = self.item(path='lib/B.txt', need=self.request['needs'][1]['need_id'])
        self.response([first, second])
        with self.assertRaisesRegex(ValidationError, 'colli'):
            inspect_response(self.root, self.request)

    def test_duplicate_json_keys_cannot_override_a_return_identity(self):
        (self.inbox / 'response.json').write_text('{"request_id":"a","request_id":"b","items":[]}')
        with self.assertRaises(ValidationError):
            inspect_response(self.root, self.request)
