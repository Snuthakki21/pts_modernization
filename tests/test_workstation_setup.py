"""One explicit save configures local intake without six unrelated approvals."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from workbench.api import create_app


class WorkstationApiTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve() / 'workspace'
        self.root.mkdir()
        self.export = Path(self.temp.name).resolve() / 'approved export'
        self.export.mkdir()
        self.app = create_app(self.root)
        self.addCleanup(self.app.state.coordinator.close)
        self.environment = patch.dict('os.environ', {}, clear=True)
        self.environment.start()
        self.addCleanup(self.environment.stop)
        _, session = await self.request('/api/session-token')
        self.token = session['token']

    async def request(self, path, method='GET', payload=None):
        messages = []
        received = False
        async def receive():
            nonlocal received
            if not received:
                received = True
                return {'type': 'http.request', 'body': json.dumps(payload or {}).encode(), 'more_body': False}
            import asyncio
            await asyncio.Future()
        async def send(message):
            messages.append(message)
        headers = [(b'host', b'127.0.0.1:8765')]
        if method == 'POST':
            headers += [(b'origin', b'http://127.0.0.1:8765'), (b'x-workbench-token', self.token.encode())]
        scope = {'type': 'http', 'asgi': {'version': '3.0'}, 'http_version': '1.1',
                 'scheme': 'http', 'method': method, 'path': path, 'raw_path': path.encode(),
                 'query_string': b'', 'root_path': '', 'server': ('127.0.0.1', 8765),
                 'client': ('127.0.0.1', 1), 'headers': headers}
        await self.app(scope, receive, send)
        return messages[0]['status'], json.loads(b''.join(m.get('body', b'') for m in messages[1:]))

    async def save(self, settings):
        return await self.request('/api/setup/workstation', 'POST', {'settings': settings})

    async def test_single_source_save_is_ready_without_manifest_or_reviewer_answers(self):
        status, result = await self.save({'source_mode': 'folder', 'source_folder': str(self.export)})
        self.assertEqual(status, 200)
        self.assertTrue(result['saved'])
        self.assertEqual(result['readiness']['status'], 'READY_FOR_INTAKE')
        self.assertEqual(result['readiness']['remaining'], [])
        self.assertFalse(result['readiness']['connectivity_verified'])
        self.assertFalse(result['readiness']['source_verified'])
        self.assertEqual(result['workflow']['assistant_mode'], 'claude_files')
        self.assertEqual(result['workflow']['claude_mcp_servers'], 0)
        self.assertEqual(result['metrics']['network_requests'], 0)

    async def test_saved_values_supply_actual_intake_defaults(self):
        notes = Path(self.temp.name).resolve() / 'process.md'
        notes.write_text('# Actual supplied context\nUnverified business facts.')
        status, _ = await self.save({'source_mode': 'folder', 'source_folder': str(self.export),
                                     'process_notes': str(notes)})
        self.assertEqual(status, 200)
        observed = []
        def create(*args):
            observed.append(args)
            return {'id': 'example', 'runs': []}
        with patch.object(self.app.state.coordinator, 'create', side_effect=create):
            status, _ = await self.request('/api/intake', 'POST', {'manifest': 'provided process manifest'})
        self.assertEqual(status, 200)
        self.assertEqual(observed[0][5:7], (str(self.export), str(notes)))


    async def test_upload_override_ignores_saved_folder_and_explicit_null_clears_notes(self):
        notes = self.export.parent / 'provided.md'
        notes.write_text('# Supplied context\nOnly used when inherited.')
        await self.save({'source_mode': 'folder', 'source_folder': str(self.export), 'process_notes': str(notes)})
        observed = []
        with patch.object(self.app.state.coordinator, 'create', side_effect=lambda *args: observed.append(args) or {}):
            status, _ = await self.request('/api/intake', 'POST', {'manifest': 'provided', 'sources': {'P.cbl': 'source'},
                                                                  'source_folder': None, 'process_notes': None})
        self.assertEqual(status, 200)
        self.assertEqual(observed[0][5:7], (None, None))

    async def test_existing_workspace_source_override_is_distinct_from_saved_folder(self):
        await self.save({'source_mode': 'folder', 'source_folder': str(self.export)})
        observed = []
        with patch.object(self.app.state.coordinator, 'create', side_effect=lambda *args: observed.append(args) or {}):
            status, _ = await self.request('/api/intake', 'POST', {'manifest': 'provided', 'source_folder': None})
        self.assertEqual(status, 200)
        self.assertIsNone(observed[0][5])

    async def test_restart_loads_saved_defaults_and_real_coordinator_freezes_them(self):
        from workbench.coordinator import Coordinator
        notes = self.export.parent / 'provided.md'
        notes.write_text('# Supplied context\nA business fact, not approval.')
        source = '       IDENTIFICATION DIVISION.\n       PROGRAM-ID. P.\n       PROCEDURE DIVISION.\n           STOP RUN.\n'
        (self.export / 'P.cbl').write_bytes(source.encode('utf-8'))
        await self.save({'source_mode': 'folder', 'source_folder': str(self.export), 'process_notes': str(notes)})
        self.app.state.coordinator.close()
        c = Coordinator(self.root)
        self.addCleanup(c.close)
        manifest = '- Process ID: setup-real\n- Process name: Setup test\n| Job order | Job | Step order | Step | Program or utility | Input files/tables | Output files/tables | Condition or dependency |\n| 1 | J | 1 | S | P | | | Always |'
        document = c.create(manifest, assistant_mode='claude_files')
        self.assertEqual(document['source_origin']['location'], str(self.export))
        self.assertEqual(document['process_context']['documents'][0]['name'], notes.name)
        self.assertEqual(document['agent_transport'], 'local_files')
        self.assertEqual(c.sources(document), {'P.cbl': source})
        frozen = (c.process_root(document['id']) / 'analysis/process-context.json').read_bytes()
        c.configure_workstation({'source_mode': 'upload', 'process_notes': None})
        c.manifest_integrity(c.ledger.get(document['id']))
        self.assertEqual((c.process_root(document['id']) / 'analysis/process-context.json').read_bytes(), frozen)

    async def test_explicit_null_notes_reaches_real_coordinator_without_refilling_defaults(self):
        notes = self.export.parent / 'provided.md'
        notes.write_text('# Supplied notes\nA context fact.')
        await self.save({'source_mode': 'folder', 'source_folder': str(self.export), 'process_notes': str(notes)})
        c = self.app.state.coordinator
        manifest = '- Process ID: clear-notes\n- Process name: Clear notes\n| Job order | Job | Step order | Step | Program or utility | Input files/tables | Output files/tables | Condition or dependency |\n| 1 | J | 1 | S | P | | | Always |'
        doc = c.create(manifest, {'P.cbl': '       IDENTIFICATION DIVISION.\n       PROGRAM-ID. P.\n'}, process_notes=None)
        self.assertEqual(doc['process_context']['documents'], [])

    async def test_failed_write_preserves_prior_values_and_existing_binding_document(self):
        await self.save({'source_mode': 'folder', 'source_folder': str(self.export)})
        path = self.root / '.migration/workstation.json'
        original = path.read_bytes()
        catalog = self.root / 'knowledge/input-locations.json'
        catalog.parent.mkdir(exist_ok=True)
        catalog.write_text('preserved original bindings')
        with patch('workbench.setup.atomic_json', side_effect=OSError('simulated disk full')):
            status, _ = await self.save({'source_mode': 'upload'})
        self.assertEqual(status, 500)
        self.assertEqual(path.read_bytes(), original)
        self.assertEqual(catalog.read_text(), 'preserved original bindings')

    async def test_invalid_field_rejects_entire_save_and_does_not_modify_previous_state(self):
        await self.save({'source_mode': 'folder', 'source_folder': str(self.export)})
        path = self.root / '.migration/workstation.json'
        original = path.read_bytes()
        status, response = await self.save({'source_mode': 'upload', 'password': 'secret'})
        self.assertEqual(status, 400)
        self.assertIn('nonsecret', response['error'])
        self.assertEqual(path.read_bytes(), original)

    async def test_saved_missing_source_reopens_setup_and_can_be_repaired_by_upload_choice(self):
        await self.save({'source_mode': 'folder', 'source_folder': str(self.export)})
        self.export.rmdir()
        status, response = await self.request('/api/setup/workstation')
        self.assertEqual(status, 200)
        self.assertEqual(response['readiness']['remaining'], ['source_folder'])
        self.assertEqual(response['readiness']['status'], 'NEEDS_SETUP')
        status, response = await self.save({'source_mode': 'upload'})
        self.assertEqual(status, 200)
        self.assertIsNone(response['settings']['source_folder'])

    async def test_save_rejects_symlink_export_without_creating_settings(self):
        alias = self.export.parent / 'alias'
        alias.symlink_to(self.export, target_is_directory=True)
        status, response = await self.save({'source_mode': 'folder', 'source_folder': str(alias)})
        self.assertEqual(status, 400)
        self.assertIn('source_folder', response['error'])
        self.assertFalse((self.root / '.migration/workstation.json').exists())

    async def test_changed_source_symlink_is_visible_and_repairable_after_restart(self):
        await self.save({'source_mode': 'folder', 'source_folder': str(self.export)})
        self.export.rmdir()
        target = self.export.parent / 'different export'
        target.mkdir()
        self.export.symlink_to(target, target_is_directory=True)
        status, response = await self.request('/api/setup/workstation')
        self.assertEqual(status, 200)
        self.assertIn('source_folder', response['readiness']['remaining'])
        status, _ = await self.save({'source_mode': 'upload'})
        self.assertEqual(status, 200)

    async def test_workstation_document_symlink_is_rejected_without_reading_target(self):
        path = self.root / '.migration/workstation.json'
        target = self.export.parent / 'private.json'
        target.write_text('private credential')
        path.symlink_to(target)
        status, response = await self.request('/api/setup/workstation')
        self.assertEqual(status, 400)
        self.assertNotIn('private credential', json.dumps(response))
        self.assertEqual(target.read_text(), 'private credential')

    async def test_notes_must_be_utf8_markdown_and_paths_must_exist(self):
        bad = self.export.parent / 'invalid.md'
        bad.write_bytes(b'\xff')
        for field, value in (('source_folder', str(self.export / 'absent')), ('process_notes', str(bad))):
            status, _ = await self.save({'source_mode': 'folder', 'source_folder': str(self.export), field: value})
            self.assertEqual(status, 400)
        self.assertFalse((self.root / '.migration/workstation.json').exists())

    async def test_url_credentials_and_query_secrets_cannot_be_stored(self):
        for value in ('https://user:secret@db.invalid/mcp', 'https://db.invalid/mcp?token=secret', 'http://db.invalid/mcp'):
            status, response = await self.save({'source_mode': 'upload', 'db2_metadata_url': value})
            self.assertEqual(status, 400)
            self.assertNotIn('secret', json.dumps(response))
        self.assertFalse((self.root / '.migration/workstation.json').exists())

    async def test_save_does_not_contact_connectors_or_create_agent_mcp_configuration(self):
        with patch('workbench.connectors.post_json', side_effect=AssertionError('network not authorized')), \
             patch('workbench.connectors.ZoweReader.operation', side_effect=AssertionError('mainframe not authorized')):
            status, response = await self.save({'source_mode': 'upload', 'zowe_profile': 'approved_base',
                                                'zowe_zosmf_profile': 'approved_zosmf', 'db2_metadata_url': 'https://db.invalid/mcp'})
            self.assertEqual(status, 200)
            self.assertEqual(response['metrics']['network_requests'], 0)
            self.assertEqual(response['checks'][-1]['status'], 'UNVERIFIED')
            status, response = await self.request('/api/setup/workstation')
            self.assertEqual(status, 200)
        for filename in ('mcp.json', '.mcp.json', '.vscode/mcp.json'):
            self.assertFalse((self.root / filename).exists())

    async def test_environment_fallback_saved_override_and_null_clear_do_not_mutate_shell(self):
        from workbench.setup import workstation_environment
        env = {'WB_ZOWE_PROFILE': 'shell_base', 'WB_DB2_MCP_URL': 'https://shell.invalid/mcp',
               'WB_DB2_MCP_TOKEN': 'PRIVATE'}
        with patch.dict('os.environ', env):
            _, response = await self.request('/api/setup/workstation')
            self.assertEqual(response['settings']['zowe_profile'], 'shell_base')
            self.assertEqual(response['settings']['db2_metadata_url'], 'https://shell.invalid/mcp')
            self.assertNotIn('PRIVATE', json.dumps(response))
            status, _ = await self.save({'source_mode': 'upload', 'zowe_profile': 'saved_base', 'db2_metadata_url': None})
            self.assertEqual(status, 200)
            effective = workstation_environment(self.root)
            self.assertEqual(effective['WB_ZOWE_PROFILE'], 'saved_base')
            self.assertNotIn('WB_DB2_MCP_URL', effective)
            import os
            self.assertEqual(os.environ['WB_ZOWE_PROFILE'], 'shell_base')
            self.assertEqual(os.environ['WB_DB2_MCP_URL'], 'https://shell.invalid/mcp')

    async def test_bad_environment_endpoint_is_not_echoed_in_new_form(self):
        with patch.dict('os.environ', {'WB_DB2_MCP_URL': 'https://private.invalid/mcp?token=PRIVATE'}):
            status, response = await self.request('/api/setup/workstation')
        self.assertEqual(status, 200)
        self.assertIsNone(response['settings']['db2_metadata_url'])
        self.assertNotIn('PRIVATE', json.dumps(response))

    async def test_existing_exact_dataset_bindings_are_preserved_when_folder_path_is_saved(self):
        from workbench.locations import input_locations
        from workbench.domain import encode
        old = self.export.parent / 'old location'
        old.mkdir()
        (self.export / 'referral.dat').write_text('synthetic fixture')
        path = self.root / 'knowledge/input-locations.json'
        path.parent.mkdir(exist_ok=True)
        path.write_bytes(encode({'schema_version': 1, 'locations': [{'name': 'WEDLX', 'path': str(old),
                                      'bindings': [{'logical_id': 'I.APP.REFERRAL', 'file': 'referral.dat'}]}]}))
        frozen = path.read_bytes()
        status, _ = await self.save({'source_mode': 'upload', 'wedlx_folder': str(self.export)})
        self.assertEqual(status, 200)
        actual = input_locations(self.root)['WEDLX']
        self.assertEqual(actual['path'], str(self.export))
        self.assertEqual(actual['readiness'], 'Unknown')
        self.assertEqual(actual['evidence'][0]['bindings'][0]['logical_id'], 'I.APP.REFERRAL')
        self.assertTrue(actual['evidence'][0]['bindings'][0]['available'])
        self.assertEqual(path.read_bytes(), frozen)

    async def test_no_folder_binding_has_no_invented_logical_dataset_mapping(self):
        from workbench.locations import input_locations
        await self.save({'source_mode': 'upload', 'tran_repository_folder': str(self.export)})
        actual = input_locations(self.root)['TranRepository']
        self.assertEqual(actual['evidence'][0]['bindings'], [])
        self.assertEqual(actual['readiness'], 'Unknown')

    async def test_profile_alias_arguments_and_unpaired_service_are_rejected(self):
        for values in ({'zowe_profile': '--execute'}, {'zowe_profile': 'base; submit'},
                       {'zowe_zosmf_profile': 'service'}):
            status, _ = await self.save({'source_mode': 'upload', **values})
            self.assertEqual(status, 400)

    async def test_old_questionnaire_state_is_not_rewritten_by_new_setup(self):
        from workbench.setup import save_setup
        save_setup(self.root, {'source': 'upload'}, environ={})
        path = self.root / '.migration/setup.json'
        original = path.read_bytes()
        status, _ = await self.save({'source_mode': 'upload'})
        self.assertEqual(status, 200)
        self.assertEqual(path.read_bytes(), original)

    async def test_initial_upload_choice_still_requires_actual_save(self):
        status, response = await self.request('/api/setup/workstation')
        self.assertEqual(status, 200)
        self.assertFalse(response['saved'])
        self.assertEqual(response['settings']['source_mode'], 'upload')
        self.assertEqual(response['readiness']['status'], 'NEEDS_SETUP')
        self.assertIn('save', response['readiness']['remaining'])


    async def test_retrieval_context_is_mutable_without_changing_frozen_source_evidence(self):
        from workbench.domain import encode
        await self.save({'source_mode': 'upload', 'zowe_profile': 'approved_base',
                         'db2_metadata_url': 'https://db.invalid/mcp'})
        c = self.app.state.coordinator
        manifest = '- Process ID: setup-context\n- Process name: Retrieval context\n| Job order | Job | Step order | Step | Program or utility | Input files/tables | Output files/tables | Condition or dependency |\n| 1 | J | 1 | S | P | | | Always |'
        doc = c.create(manifest, {'P.cbl': '       IDENTIFICATION DIVISION.\n       PROGRAM-ID. P.\n'}, assistant_mode='claude_files')
        baseline = encode(c.ledger.get(doc['id']))
        with patch('workbench.connectors.post_json', side_effect=AssertionError('no network')):
            view = c.local_agent_view(doc['id'])
        self.assertEqual(view['retrieval_context']['zowe_profile'], 'approved_base')
        self.assertEqual(view['retrieval_context']['db2_metadata_url'], 'https://db.invalid/mcp')
        self.assertFalse(view['retrieval_context']['connectivity_verified'])
        self.assertEqual(encode(c.ledger.get(doc['id'])), baseline)
        await self.save({'zowe_profile': 'different_base'})
        self.assertEqual(c.local_agent_view(doc['id'])['retrieval_context']['zowe_profile'], 'different_base')
        self.assertEqual(encode(c.ledger.get(doc['id'])), baseline)

    async def test_offline_preflight_uses_selected_defaults_without_connecting(self):
        from workbench.preflight import inspect_workspace
        notes = self.export.parent / 'preflight.md'
        notes.write_text('# Selected notes\nUnverified input.')
        (self.export / 'P.cbl').write_text('       IDENTIFICATION DIVISION.\n       PROGRAM-ID. P.\n')
        status, _ = await self.save({'source_mode': 'folder', 'source_folder': str(self.export),
                                    'process_notes': str(notes), 'db2_metadata_url': 'https://db.invalid/mcp'})
        self.assertEqual(status, 200)
        manifest = self.export.parent / 'manifest.md'
        manifest.write_text('- Process ID: setup-preview\n- Process name: Preflight setup\n| Job order | Job | Step order | Step | Program or utility | Input files/tables | Output files/tables | Condition or dependency |\n| 1 | J | 1 | S | P | | | Always |')
        with patch('workbench.connectors.post_json', side_effect=AssertionError('no network')):
            result = inspect_workspace(self.root, manifest, coordinator_owned=True, environ={})
        checks = {c['id']: c for c in result['checks']}
        self.assertEqual(checks['source_export']['status'], 'READY')
        self.assertEqual(checks['background_context']['status'], 'READY')
        self.assertEqual(checks['db2']['status'], 'UNVERIFIED')
        self.assertEqual(result['network_requests'], 0)

    async def test_launch_preflight_can_open_form_to_repair_removed_saved_notes(self):
        from workbench.preflight import inspect_workspace
        notes = self.export.parent / 'temporary.md'
        notes.write_text('# Selected notes')
        await self.save({'source_mode': 'upload', 'process_notes': str(notes)})
        notes.unlink()
        active = inspect_workspace(self.root, coordinator_owned=True, environ={})
        launch = inspect_workspace(self.root, coordinator_owned=True, environ={}, workstation_defaults=False)
        self.assertEqual(next(c for c in active['checks'] if c['id'] == 'background_context')['status'], 'BLOCKED')
        self.assertEqual(next(c for c in launch['checks'] if c['id'] == 'background_context')['status'], 'NOT_CONFIGURED')
        self.assertFalse(any(c['status'] == 'BLOCKED' for c in launch['checks']))


    async def test_external_saved_export_does_not_claim_workspace_endeavor_exists(self):
        await self.save({'source_mode': 'folder', 'source_folder': str(self.export)})
        status, result = await self.request('/api/state')
        self.assertEqual(status, 200)
        self.assertFalse(result['connections']['local_source_export'])
        self.assertTrue(result['connections']['saved_folder_available'])
        (self.root / 'Endeavor').mkdir()
        _, result = await self.request('/api/state')
        self.assertTrue(result['connections']['local_source_export'])

    async def test_normal_copilot_retrieval_endpoint_preserves_bounded_current_context(self):
        from tools.workbench_mcp import WorkflowBridge
        await self.save({'source_mode': 'upload', 'zowe_profile': 'approved_base',
                         'db2_metadata_url': 'https://db.invalid/mcp'})
        c = self.app.state.coordinator
        manifest = '- Process ID: setup-bridge\n- Process name: Retrieval context\n| Job order | Job | Step order | Step | Program or utility | Input files/tables | Output files/tables | Condition or dependency |\n| 1 | J | 1 | S | P | | | Always |'
        doc = c.create(manifest, {'P.cbl': '       IDENTIFICATION DIVISION.\n       PROGRAM-ID. P.\n'}, assistant_mode='claude_files')
        status, result = await self.request('/api/process/setup-bridge/retrieval')
        self.assertEqual(status, 200)
        self.assertEqual(result['retrieval_context']['zowe_profile'], 'approved_base')
        self.assertIsNone(result['retrieval'])
        with patch.object(WorkflowBridge, 'request', return_value=result):
            projected = WorkflowBridge().call('workbench_retrieval_task', {'process_id': doc['id']})
        self.assertEqual(projected['retrieval_context'], result['retrieval_context'])
        self.assertFalse(projected['retrieval_context']['connectivity_verified'])


if __name__ == '__main__':
    unittest.main()


class WorkstationMarkdownTests(unittest.IsolatedAsyncioTestCase):
    asyncSetUp = WorkstationApiTests.asyncSetUp
    request = WorkstationApiTests.request
    save = WorkstationApiTests.save
    """One private nonsecret Markdown companion follows the actual Save transaction."""
    async def test_saved_markdown_matches_nonsecret_settings_and_inspection_bytes(self):
        from workbench.domain import sha
        notes = self.export.parent / 'fictional-process-notes.md'
        notes.write_bytes(b'# Fictional notes\nPRIVATE_CONTEXT_SENTINEL\n')
        status, view = await self.save({'source_mode': 'upload', 'process_notes': str(notes)})
        self.assertEqual(status, 200)
        instructions = view['instructions'];path = Path(instructions['markdown_path'])
        self.assertEqual(path, self.root / '.migration/workstation.md')
        self.assertEqual(instructions['status'], 'READY')
        self.assertEqual(path.read_bytes(), instructions['text'].encode('utf-8'))
        self.assertEqual(sha(path.read_bytes()), instructions['sha256'])
        self.assertNotIn(b'\r\n', path.read_bytes())
        self.assertNotIn('PRIVATE_CONTEXT_SENTINEL', instructions['text'])
        snapshot = json.loads(instructions['text'].split('```json\n')[1].split('\n```')[0])
        self.assertEqual(snapshot['settings'], view['settings'])
        self.assertEqual(snapshot['connections'], view['connection_setup']['choices'])
        self.assertIn('Add process', instructions['next_step'])
        self.assertIn('Copilot retrieval prompt', instructions['next_step'])
        self.assertNotIn('copilot_prompt', instructions)
        self.assertFalse(view['readiness']['connectivity_verified'])
        _, inspected = await self.request('/api/setup/workstation')
        self.assertEqual(inspected['instructions'], instructions)

    async def test_missing_or_changed_companion_needs_save_without_get_repair(self):
        await self.save({'source_mode': 'upload'})
        path = self.root / '.migration/workstation.md';path.unlink()
        _, view = await self.request('/api/setup/workstation')
        self.assertTrue(view['saved'])
        self.assertEqual(view['instructions']['status'], 'NEEDS_SAVE')
        self.assertIsNone(view['instructions']['sha256'])
        self.assertFalse(path.exists())
        path.write_bytes(b'PRIVATE_CHANGED_SENTINEL')
        _, view = await self.request('/api/setup/workstation')
        self.assertEqual(view['instructions']['status'], 'NEEDS_SAVE')
        self.assertNotIn('PRIVATE_CHANGED_SENTINEL', json.dumps(view))
        self.assertEqual(path.read_bytes(), b'PRIVATE_CHANGED_SENTINEL')
        status, repaired = await self.save({'source_mode': 'upload'})
        self.assertEqual(status, 200)
        self.assertEqual(repaired['instructions']['status'], 'READY')
        self.assertEqual(path.read_bytes(), repaired['instructions']['text'].encode('utf-8'))

    async def test_markdown_write_failure_rolls_back_settings_and_keeps_original_companion(self):
        from workbench.domain import atomic_bytes
        await self.save({'source_mode': 'folder', 'source_folder': str(self.export)})
        settings_path = self.root / '.migration/workstation.json';md = self.root / '.migration/workstation.md'
        before = {p: p.read_bytes() for p in (settings_path, md)}
        def fail(path, raw):
            if Path(path) == md:raise OSError('fictional Markdown disk failure')
            atomic_bytes(path, raw)
        with patch('workbench.setup.atomic_bytes', side_effect=fail):
            status, _ = await self.save({'source_mode': 'upload'})
        self.assertEqual(status, 500)
        self.assertEqual({p: p.read_bytes() for p in before}, before)
        _, view = await self.request('/api/setup/workstation')
        self.assertEqual(view['instructions']['status'], 'READY')

    async def test_first_markdown_write_failure_leaves_no_partially_saved_settings(self):
        with patch('workbench.setup.atomic_bytes', side_effect=OSError('fictional Markdown disk failure')):
            status, _ = await self.save({'source_mode': 'upload'})
        self.assertEqual(status, 500)
        self.assertFalse((self.root / '.migration/workstation.json').exists())
        self.assertFalse((self.root / '.migration/workstation.md').exists())

    async def test_concurrent_markdown_edit_is_preserved_and_blocks_configuration_save(self):
        from workbench.setup import prepare_workstation
        await self.save({'source_mode': 'folder', 'source_folder': str(self.export)})
        settings_path = self.root / '.migration/workstation.json';md = self.root / '.migration/workstation.md'
        settings_before = settings_path.read_bytes()
        def concurrent(*args, **kwargs):
            result = prepare_workstation(*args, **kwargs)
            md.write_bytes(b'fictional concurrent operator edit')
            return result
        with patch('workbench.setup.prepare_workstation', side_effect=concurrent):
            status, _ = await self.save({'source_mode': 'upload'})
        self.assertEqual(status, 400)
        self.assertEqual(md.read_bytes(), b'fictional concurrent operator edit')
        self.assertEqual(settings_path.read_bytes(), settings_before)

    async def test_twenty_randomized_nonsecret_saved_states_are_byte_bound_and_replay(self):
        import random,secrets
        from workbench.domain import sha
        rng = random.Random(secrets.randbits(63));hashes = set()
        for index in range(20):
            alias = f'fictional_{index}_{rng.randrange(1000000)}'
            status, view = await self.save({'source_mode': 'upload', 'zowe_profile': alias, 'zowe_zosmf_profile': alias + '_zosmf'})
            self.assertEqual(status, 200)
            instructions = view['instructions'];raw = Path(instructions['markdown_path']).read_bytes()
            self.assertEqual(instructions['status'], 'READY')
            self.assertEqual(instructions['sha256'], sha(raw))
            snapshot = json.loads(instructions['text'].split('```json\n')[1].split('\n```')[0])
            self.assertEqual(snapshot['settings']['zowe_profile'], alias)
            self.assertEqual(snapshot['connections'], view['connection_setup']['choices'])
            _, again = await self.request('/api/setup/workstation')
            self.assertEqual(again['instructions'], instructions)
            hashes.add(sha(raw))
        self.assertEqual(len(hashes), 20)

    async def test_instruction_readiness_binds_actual_settings_not_stale_caller(self):
        from workbench.domain import encode
        from workbench.setup import inspect_workstation_instructions
        _, saved = await self.save({'source_mode': 'upload'})
        path = self.root / '.migration/workstation.json'
        changed = json.loads(path.read_bytes());changed['settings']['zowe_profile'] = 'fictional_external_base'
        changed['settings']['zowe_zosmf_profile'] = 'fictional_external_service'
        raw = encode(changed);path.write_bytes(raw)
        actual = inspect_workstation_instructions(self.root, saved['settings'])
        self.assertEqual(actual['status'], 'NEEDS_SAVE')
        self.assertIsNone(actual['sha256'])
        self.assertEqual(path.read_bytes(), raw)

    async def test_json_change_during_instruction_inspection_never_reports_ready(self):
        from workbench.domain import encode
        from workbench.setup import _instruction_choices, inspect_workstation_instructions
        _, saved = await self.save({'source_mode': 'upload'})
        path = self.root / '.migration/workstation.json'
        changed = json.loads(path.read_bytes());changed['settings']['db2_metadata_url'] = 'https://fictional-external.test/mcp'
        raw = encode(changed)
        def change(*args):
            result = _instruction_choices(*args);path.write_bytes(raw);return result
        with patch('workbench.setup._instruction_choices', side_effect=change):
            actual = inspect_workstation_instructions(self.root, saved['settings'])
        self.assertEqual(actual['status'], 'NEEDS_SAVE')
        self.assertEqual(path.read_bytes(), raw)

    async def test_late_json_publication_change_is_preserved_and_save_fails(self):
        from workbench.domain import atomic_bytes, encode
        await self.save({'source_mode': 'upload'})
        path = self.root / '.migration/workstation.json';md = self.root / '.migration/workstation.md'
        observed = {}
        def change(destination, raw):
            atomic_bytes(destination, raw)
            if Path(destination) == md:
                current = json.loads(path.read_bytes());current['settings']['zowe_profile'] = 'fictional_external_base'
                observed['raw'] = encode(current);path.write_bytes(observed['raw'])
        with patch('workbench.setup.atomic_bytes', side_effect=change):
            status, _ = await self.save({'zowe_profile': 'fictional_requested_base', 'zowe_zosmf_profile': 'fictional_service'})
        self.assertEqual(status, 400)
        self.assertEqual(path.read_bytes(), observed['raw'])
        _, actual = await self.request('/api/setup/workstation')
        self.assertEqual(actual['instructions']['status'], 'NEEDS_SAVE')

    async def test_late_complete_valid_json_and_markdown_edits_are_both_preserved(self):
        from workbench.domain import atomic_bytes, encode
        from workbench.setup import _instruction_choices, workstation_markdown
        await self.save({'source_mode': 'upload'})
        path = self.root / '.migration/workstation.json';md = self.root / '.migration/workstation.md'
        observed = {}
        def change(destination, raw):
            atomic_bytes(destination, raw)
            if Path(destination) == md:
                current = json.loads(path.read_bytes());current['settings']['zowe_profile'] = 'fictional_external_base'
                observed['json'] = encode(current)
                observed['md'] = workstation_markdown(self.root, current['settings'], _instruction_choices(self.root, current['settings']))
                path.write_bytes(observed['json']);md.write_bytes(observed['md'])
        with patch('workbench.setup.atomic_bytes', side_effect=change):
            status, _ = await self.save({'zowe_profile': 'fictional_requested_base', 'zowe_zosmf_profile': 'fictional_service'})
        self.assertEqual(status, 400)
        self.assertEqual(path.read_bytes(), observed['json'])
        self.assertEqual(md.read_bytes(), observed['md'])
        _, actual = await self.request('/api/setup/workstation')
        self.assertEqual(actual['instructions']['status'], 'READY')
        self.assertEqual(actual['settings']['zowe_profile'], 'fictional_external_base')

    async def test_final_view_inspection_change_is_preserved_and_not_ready(self):
        from workbench.domain import encode
        from workbench.connection_setup import inspect_connections
        await self.save({'source_mode': 'upload'})
        path = self.root / '.migration/workstation.json';observed = {}
        def change(root, settings, *args):
            result = inspect_connections(root, settings, *args)
            if settings['zowe_profile'] == 'fictional_requested_base':
                current = json.loads(path.read_bytes());current['settings']['db2_metadata_url'] = 'https://fictional-late-inspection.test/mcp'
                observed['raw'] = encode(current);path.write_bytes(observed['raw'])
            return result
        with patch('workbench.connection_setup.inspect_connections', side_effect=change):
            status, _ = await self.save({'zowe_profile': 'fictional_requested_base', 'zowe_zosmf_profile': 'fictional_service'})
        self.assertEqual(status, 400)
        self.assertEqual(path.read_bytes(), observed['raw'])

    async def test_twenty_randomized_late_valid_settings_changes_never_false_ready(self):
        import random,secrets
        from workbench.domain import atomic_bytes, encode
        rng = random.Random(secrets.randbits(63));states = set()
        for index in range(20):
            status, _ = await self.save({'source_mode':'upload','zowe_profile':None,'zowe_zosmf_profile':None})
            self.assertEqual(status, 200)
            path = self.root / '.migration/workstation.json';md = self.root / '.migration/workstation.md'
            alias = f'fictional_external_{index}_{rng.randrange(1000000)}';observed = {}
            def change(destination, raw):
                atomic_bytes(destination, raw)
                if Path(destination) == md:
                    current = json.loads(path.read_bytes());current['settings']['zowe_profile'] = alias
                    observed['raw'] = encode(current);path.write_bytes(observed['raw'])
            with patch('workbench.setup.atomic_bytes', side_effect=change):
                status, _ = await self.save({'zowe_profile':'fictional_requested','zowe_zosmf_profile':'fictional_service'})
            self.assertEqual(status, 400)
            self.assertEqual(path.read_bytes(), observed['raw'])
            _, actual = await self.request('/api/setup/workstation')
            self.assertEqual(actual['instructions']['status'], 'NEEDS_SAVE')
            self.assertEqual(actual['settings']['zowe_profile'], alias)
            states.add(alias)
        self.assertEqual(len(states), 20)
