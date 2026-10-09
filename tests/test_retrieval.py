"""Claude retrieval contracts and immutable legacy packets; no remote access."""
import random
import secrets
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from workbench.domain import ValidationError, encode, sha
from workbench.retrieval import build_request, inspect_response, request_prompt, validate_binding, write_request


def historical_request(doc, needs, schema_version=1):
    """Model an already issued packet; recorded digest assertions pin old bytes."""
    from workbench.retrieval import _prompt,_need
    request = build_request(doc, needs)
    for key in ('agent_prompt', 'retrieval_agent', 'privacy_contract_version','metadata_qualification','request_id', 'return_folder'):
        request.pop(key)
    request['schema_version'] = schema_version
    request['needs']=list({need['need_id']:need for need in map(_need,needs)}.values())
    request['request_id'] = sha(encode(request))
    request['return_folder'] = ('processes/' + doc['id'] + '/analysis/retrieval/'
                                + request['request_id'] + '/inbox')
    request['copilot_prompt'] = _prompt(request)
    return request


class RetrievalTests(unittest.TestCase):
    def test_syntactically_valid_private_identity_requires_explicit_model_qualification(self):
        from workbench.retrieval import model_request
        marker='SSN123456789'
        need={'kind':'program','name':marker,'reason':'Private operator details','status':'missing'}
        request=build_request(self.doc,[need]);view=model_request(request)
        self.assertNotIn(marker,encode(view).decode()+request['agent_prompt'])
        self.assertEqual(request['needs'][0]['name'],marker)
        self.assertEqual(view['metadata_identity_gate'],'UNAPPROVED_MODEL_METADATA')
        self.assertIn('syntax does not establish privacy',encode(view).decode())
        synthetic=build_request({**self.doc,'demo':True},[need]);synthetic_view=model_request(synthetic)
        self.assertEqual(synthetic_view['needs'][0]['name'],marker)
        self.assertEqual(synthetic['metadata_qualification'],'SYNTHETIC_CONTEXT')

    def test_original_schema3_receipt_bytes_are_preserved_but_never_routed_as_prompt(self):
        from workbench.retrieval import _need,_request_fields
        marker='123-45-6789'
        request=build_request(self.doc,[{'kind':'program','name':'ELIGIBLE','reason':marker}])
        for key in ('privacy_contract_version','metadata_qualification'):request.pop(key)
        request['needs']=[_need({'kind':'program','name':'ELIGIBLE','reason':marker})]
        request['request_id']=sha(encode({key:request[key] for key in _request_fields(request)}))
        request['return_folder']='processes/'+self.doc['id']+'/analysis/retrieval/'+request['request_id']+'/inbox'
        request['agent_prompt']='Preserved historical private prompt '+marker
        relative=write_request(self.root,request);path=self.root/'processes'/self.doc['id']/relative
        original=path.read_bytes();active=request_prompt(request)
        self.assertIn('immutable historical',active);self.assertNotIn(marker,active)
        validate_binding(request,self.doc);self.assertEqual(path.read_bytes(),original)
        self.assertEqual(write_request(self.root,request),relative)

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
        return {'origin': 'zowe_cli', 'tool': 'zowe files view ds',
                'locator': 'APP.COPYLIB(EMPLOYEE)', 'retrieved_at': '2026-10-06T12:00:00Z'}

    def response(self, items, **changes):
        value = {'request_id': self.request['request_id'], 'items': items, **changes}
        (self.inbox / 'response.json').write_bytes(encode(value))
        return value

    def test_request_is_immutable_idempotent_and_bound(self):
        self.assertEqual(self.relative, write_request(self.root, self.request))
        self.assertEqual(self.request, build_request(self.doc))
        self.assertIn(self.request['return_folder'], self.request['agent_prompt'])
        self.assertIn('Use Claude Code', self.request['agent_prompt'])
        self.assertIn('after the Coordinator', self.request['agent_prompt'])
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
        for field, value in (('agent_prompt', 'changed'), ('return_folder', 'other'),
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

    def test_new_requests_bind_claude_role_and_remove_copilot_dependency(self):
        self.assertEqual(self.request['schema_version'], 3)
        self.assertEqual(self.request['retrieval_agent'], 'claude')
        self.assertNotIn('copilot_prompt', self.request)
        prompt = request_prompt(self.request)
        self.assertEqual(prompt, self.request['agent_prompt'])
        self.assertIn('approved typed Db2 MCP', prompt)
        self.assertIn('read-only Zowe CLI', prompt)
        self.assertIn('Never submit a job', prompt)
        self.assertNotIn('Copilot', prompt)
        self.assertNotIn('no MCP access', prompt)
        for field, value in (('retrieval_agent', 'copilot'), ('schema_version', True),
                             ('schema_version', 4), ('agent_prompt', 'Execute all jobs')):
            with self.subTest(field=field), self.assertRaises(ValidationError):
                write_request(self.root, {**self.request, field: value})
        with self.assertRaises(ValidationError):
            write_request(self.root, {**self.request, 'copilot_prompt': prompt})

    def test_private_need_prose_and_dynamic_operands_never_enter_active_prompts(self):
        marker='123-45-6789';email='private@example.invalid'
        needs=[{'kind':'program','name':marker,'reason':email,'source':email,'relationship':marker,'status':'dynamic_unknown'}]
        current=build_request(self.doc,needs)
        for version in (1,2,3):
            request=current if version==3 else historical_request(self.doc,needs,version)
            original=encode(request)
            prompt=request_prompt(request)
            self.assertNotIn(marker,prompt);self.assertNotIn(email,prompt)
            self.assertIn('IDENTITY_SHA256_',prompt);self.assertIn('UNAPPROVED_MODEL_METADATA',prompt)
            self.assertEqual(encode(request),original)
            if version<3:self.assertIn(marker,request['copilot_prompt'])
        freeform=build_request(self.doc,[{'kind':'program','name':'ELIGIBLE','reason':marker+' '+email,
                                        'source':email,'relationship':marker}])
        self.assertNotIn(marker,encode(freeform).decode());self.assertNotIn(email,encode(freeform).decode())
        self.assertEqual(freeform['needs'][0]['name'],'ELIGIBLE')
        self.assertNotIn('zowe files view ds',freeform['agent_prompt'])
        self.assertIn('download-to-exact-inbox',freeform['agent_prompt'])

    def test_typed_cics_metadata_is_preserved_but_dynamic_found_receipts_cannot_clear_it(self):
        from workbench.retrieval import model_need
        kinds=('cics_file_definition','cics_program_definition','cics_mapset_definition','cics_tdqueue_definition',
               'cics_tsmodel_definition','cics_tsqueue','cics_channel','cics_container','cics_system')
        for kind in kinds:
            need={'kind':kind,'name':'ACTUAL','reason':'Private source explanation'}
            self.assertEqual(model_need(need)['kind'],kind)
            self.assertTrue(model_need(need)['name'].startswith('IDENTITY_SHA256_'))
            self.assertEqual(model_need(need,qualified=True)['name'],'ACTUAL')
        self.request=build_request(self.doc,[{'kind':'program','name':'123-45-6789','reason':'Dynamic operand','status':'dynamic_unknown'}])
        write_request(self.root,self.request);self.inbox=self.root/self.request['return_folder']
        item=self.item('       IDENTIFICATION DIVISION.\n       PROGRAM-ID. GUESSED.\n','GUESSED.cbl')
        self.response([item])
        with self.assertRaisesRegex(ValidationError,'guessed file'):inspect_response(self.root,self.request)

    def test_historical_claude_routing_preserves_issued_bytes_and_response_identity(self):
        needs = [{k: v for k, v in self.request['needs'][0].items() if k != 'need_id'}]
        for version in (1, 2):
            with self.subTest(version=version):
                request = historical_request(self.doc, needs, version)
                relative = write_request(self.root, request)
                path = self.root / 'processes' / self.doc['id'] / relative
                original = path.read_bytes()
                prompt = request_prompt(request)
                self.assertIn('immutable historical retrieval request', prompt)
                self.assertIn('Use Claude Code', prompt)
                self.assertIn(request['request_id'], prompt)
                self.assertIn(request['return_folder'], prompt)
                self.assertIn('neither reissues the request', prompt)
                self.assertNotIn('Use GitHub Copilot', prompt)
                validate_binding(request, self.doc)
                self.assertEqual(relative, write_request(self.root, request))
                self.assertEqual(path.read_bytes(), original)
                self.assertIn('Use GitHub Copilot', request['copilot_prompt'])

    def test_new_nonguided_source_requests_require_zowe_provenance(self):
        item = self.item()
        for provenance in ({**self.provenance(), 'origin': 'configured_mcp', 'tool': 'read_member'},
                           {**self.provenance(), 'tool': 'zowe jobs submit ds'}):
            self.response([{**item, 'provenance': provenance}])
            with self.subTest(provenance=provenance), self.assertRaisesRegex(ValidationError, 'Zowe CLI'):
                inspect_response(self.root, self.request)
        self.response([item])
        self.assertTrue(inspect_response(self.root, self.request)['complete'])


class GuidedRetrievalTests(unittest.TestCase):
    """Fictional prepared processes pull evidence without inventing first exports."""
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name).resolve()
        self.doc = {'id': 'GUIDED', 'source_files': {}, 'copilot_iteration': 0,
                    'guided_contract_version': 1, 'guided_workspace': str(self.root)}

    def request(self, needs=None, **changes):
        return build_request({**self.doc, **changes}, needs or [
            {'kind': 'job', 'name': 'IMATCH', 'reason': 'Explicit fictional operator start job'}])

    def returned(self, request, text, provenance, path='IMATCH.jcl'):
        write_request(self.root, request)
        inbox = self.root / request['return_folder']
        source = inbox / 'files' / path
        source.parent.mkdir(parents=True, exist_ok=True)
        source.write_bytes(text.encode('utf-8'))
        (inbox / 'response.json').write_bytes(encode({'request_id': request['request_id'], 'items': [
            {'need_id': request['needs'][0]['need_id'], 'status': 'FOUND', 'path': path,
             'sha256': sha(source.read_bytes()), 'provenance': provenance}]}))

    @staticmethod
    def zowe(tool='zowe files view ds'):
        return {'origin': 'zowe_cli', 'tool': tool, 'locator': 'APP.JCL(IMATCH)',
                'retrieved_at': '2026-10-07T12:00:00Z', 'environment': 'Fictional non-production'}

    def test_zero_source_batch_roots_get_exact_hash_bound_workspace_and_typed_transports(self):
        request = self.request()
        self.assertEqual(request['schema_version'], 3)
        self.assertEqual(request['source_generation'], sha(encode({})))
        self.assertEqual(request['workspace'], str(self.root))
        self.assertIn(encode({'workspace': str(self.root), 'return_inbox': str(self.root / request['return_folder'])}).decode(), request['agent_prompt'])
        self.assertNotIn('WORKSPACE/', request['agent_prompt'])
        self.assertIn('Mandatory transport boundary: use approved Zowe CLI', request['agent_prompt'])
        self.assertIn('typed read-only Db2 MCP', request['agent_prompt'])
        self.assertIn('Claude Code uses only those approved MCP servers', request['agent_prompt'])
        self.assertIn('"origin":"zowe_cli","tool":"zowe files download data-set"', request['agent_prompt'])
        self.assertIn('Db2 receipts instead require origin=configured_mcp', request['agent_prompt'])
        validate_binding(request, self.doc)
        write_request(self.root, request)
        self.assertEqual(inspect_response(self.root, request)['status'], 'WAITING_FOR_RESPONSE')
        self.assertEqual(self.doc['source_files'], {})

    def test_workspace_cross_process_and_tamper_cannot_be_published_or_consumed(self):
        request = self.request()
        other = self.root / 'other workspace'
        other.mkdir()
        with self.assertRaisesRegex(ValidationError, 'workspace'):
            write_request(other, request)
        with self.assertRaisesRegex(ValidationError, 'workspace'):
            inspect_response(other, request)
        self.assertFalse((other / 'processes').exists())
        changed = self.request(guided_workspace=str(other))
        self.assertNotEqual(request['request_id'], changed['request_id'])
        with self.assertRaisesRegex(ValidationError, 'workspace'):
            validate_binding(changed, self.doc)
        with self.assertRaises(ValidationError):
            validate_binding({**request, 'workspace': str(other)}, self.doc)
        with self.assertRaisesRegex(ValidationError, 'workspace'):
            validate_binding(request, {k: v for k, v in self.doc.items() if k != 'guided_contract_version'})
        self.assertEqual(self.doc['source_files'], {})

    def test_windows_paths_are_quoted_exact_data_without_shell_or_generic_placeholders(self):
        workspace = r'C:\Fictional Modernization\approved export'
        request = self.request(guided_workspace=workspace)
        from pathlib import PureWindowsPath
        exact = str(PureWindowsPath(workspace) / request['return_folder'])
        self.assertIn(encode({'workspace': workspace, 'return_inbox': exact}).decode(), request['agent_prompt'])
        self.assertNotIn('WORKSPACE/', request['agent_prompt'])
        validate_binding(request, {**self.doc, 'guided_workspace': workspace})

    def test_unsupported_guided_marker_or_relative_workspace_fails_closed(self):
        for marker in (True, 2, '1', None):
            with self.subTest(marker=marker), self.assertRaises(ValidationError):
                self.request(guided_contract_version=marker)
        for workspace in (None, '', 'relative/export', 'C:relative', '  /local/export', '/local/export\n'):
            with self.subTest(workspace=workspace), self.assertRaises(ValidationError):
                self.request(guided_workspace=workspace)

    def test_twenty_runtime_randomized_source_states_preserve_exact_lf_and_crlf_bytes(self):
        seed = secrets.randbits(63)
        rng = random.Random(seed)
        seen = set()
        for index in range(20):
            name = f'I{index:02}{rng.randrange(100000):05}'
            ending = '\r\n' if index % 2 else '\n'
            text = ending.join([f'//{name} JOB', f'//S EXEC PGM=P{index:02}', ''])
            # This is retrieval validation, not mainframe execution or parity.
            request = self.request([{'kind': 'job', 'name': name, 'reason': 'Fictional known start job'}])
            provenance = {**self.zowe('zowe.cmd zos-files download data-set'), 'locator': 'APP.JCL(' + name + ')'}
            self.returned(request, text, provenance, name + '.jcl')
            actual = inspect_response(self.root, request)
            self.assertTrue(actual['complete'])
            self.assertEqual(actual['entries'][0]['text'], text)
            self.assertEqual(actual['entries'][0]['source_hash'], sha(text.encode('utf-8')))
            self.assertEqual(actual, inspect_response(self.root, request))
            seen.add(actual['entries'][0]['source_hash'])
        self.assertEqual(len(seen), 20)
        self.assertEqual(self.doc['source_files'], {})

    def test_guided_source_rejects_wrong_or_executable_transport_without_affecting_legacy(self):
        request = self.request()
        text = '//IMATCH JOB\n//S EXEC PGM=PMATCH\n'
        invalid = [self.zowe(tool) for tool in (
            'approved_read_member', 'zowe files upload ds', 'zowe jobs submit ds',
            'zowe files view ds APP.JCL(IMATCH); zowe files upload ds',
            'zowe files view ds $(command)', 'zowe files view ds APP.JCL(IMATCH) > output')]
        invalid.extend([{**self.zowe(), 'origin': origin} for origin in ('configured_mcp', 'manual_export')])
        for provenance in invalid:
            with self.subTest(provenance=provenance):
                self.returned(request, text, provenance)
                with self.assertRaisesRegex(ValidationError, 'Zowe CLI'):
                    inspect_response(self.root, request)
        # Prior CICS schema-2 transport remains byte-compatible and separately governed.
        legacy = historical_request({'id': 'HISTORICAL', 'source_files': {}, 'cics_contract_version': 1}, request['needs'] and [
            {k: v for k, v in request['needs'][0].items() if k != 'need_id'}], 2)
        self.returned(legacy, text, {**self.zowe(), 'origin': 'configured_mcp', 'tool': 'approved_read_member'})
        self.assertTrue(inspect_response(self.root, legacy)['complete'])

    def test_guided_db2_ddl_requires_typed_mcp_and_preserves_windows_bytes(self):
        request = self.request([{'kind': 'db2_table', 'name': 'APP.CUSTOMER', 'reason': 'Fictional referenced table'}])
        text = 'CREATE TABLE APP.CUSTOMER (\r\n ID CHAR(9) NOT NULL\r\n);\r\n'
        for provenance in (self.zowe(), {**self.zowe(), 'origin': 'configured_mcp', 'tool': 'execute_sql'}):
            with self.subTest(provenance=provenance):
                self.returned(request, text, provenance, 'CUSTOMER.sql')
                with self.assertRaisesRegex(ValidationError, 'Db2 MCP'):
                    inspect_response(self.root, request)
        provenance = {'origin': 'configured_mcp', 'tool': 'db2_describe_table', 'locator': 'APP.CUSTOMER',
                      'retrieved_at': '2026-10-07T12:00:00Z'}
        self.returned(request, text, provenance, 'CUSTOMER.sql')
        actual = inspect_response(self.root, request)
        self.assertEqual(actual['entries'][0]['text'], text)
        self.assertEqual(actual['entries'][0]['source_hash'], sha(text.encode('utf-8')))

    def test_frozen_historical_schema_one_and_two_packet_bytes_do_not_change(self):
        doc = {'id': 'LEGACY', 'source_files': {'jobs/PAY.jcl': sha('original')},
               'copilot_iteration': 2, 'lineage_artifact': 'analysis/lineage-a.json',
               'artifact_hashes': {'analysis/lineage-a.json': sha('lineage')}}
        needs = [{'kind': 'copybook', 'name': 'EMPLOYEE', 'reason': 'Referenced copybook absent'}]
        # Digests recorded from the pre-change implementation, not the new renderer.
        for marker, digest in ((None, '6de835a92440245100d4ca0a1b8659a2528470977eb484859a6419b2785979ef'),
                               (1, 'e05f83629bb01d23c8f52fc8f07af918c3ea118dadb11728d9a7b645d832fd93')):
            current = {**doc, **({'cics_contract_version': marker} if marker else {})}
            request = historical_request(current, needs, 2 if marker else 1)
            self.assertNotIn('workspace', request)
            self.assertEqual(sha(encode(request)), digest)
            validate_binding(request, current)
