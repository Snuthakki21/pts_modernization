"""Read-only UI diagnostics must describe real local readiness and frozen evidence."""
import asyncio
import json
import tempfile
import unittest
from pathlib import Path

from workbench.api import create_app


class KnowledgeApiTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.app = create_app(self.tmp.name)

    async def asyncTearDown(self):
        self.app.state.coordinator.close()
        self.tmp.cleanup()

    async def request(self, path, method='GET', payload=None, headers=None):
        messages = []
        received = False

        async def receive():
            nonlocal received
            if not received:
                received = True
                return {'type': 'http.request', 'body': json.dumps(payload or {}).encode(), 'more_body': False}
            await asyncio.Future()

        async def send(message):
            messages.append(message)

        scope = {
            'type': 'http', 'asgi': {'version': '3.0'}, 'http_version': '1.1',
            'scheme': 'http', 'method': method, 'path': path, 'raw_path': path.encode(),
            'query_string': b'', 'root_path': '', 'server': ('127.0.0.1', 8765),
            'client': ('127.0.0.1', 1000),
            'headers': [(b'host', b'127.0.0.1:8765'), *(headers or [])],
        }
        await self.app(scope, receive, send)
        return messages[0]['status'], b''.join(m.get('body', b'') for m in messages[1:])

    async def test_catalog_is_visible_with_editable_application_and_reference_paths(self):
        status, raw = await self.request('/api/knowledge')
        self.assertEqual(status, 200, raw)
        doc = json.loads(raw)
        self.assertIsInstance(doc['snapshot'], dict)
        self.assertTrue(doc['snapshot'])
        self.assertEqual(Path(doc['application_path']).name, 'application-knowledge.json')
        self.assertTrue(Path(doc['application_template_path']).is_file())
        self.assertTrue(Path(doc['reference_path']).is_file())
        self.assertEqual(self.app.state.coordinator.ledger.list(True), [])

    async def test_setup_diagnostics_do_not_treat_serving_coordinator_as_other_writer(self):
        status, raw = await self.request('/api/preflight')
        self.assertEqual(status, 200, raw)
        doc = json.loads(raw)
        self.assertIn(doc['status'], ('READY', 'BLOCKED'))
        self.assertIsInstance(doc['checks'], list)
        self.assertTrue(doc['checks'])
        for check in doc['checks']:
            self.assertTrue(check['id'])
            self.assertTrue(check['status'])
            self.assertTrue(check['message'])
            if 'lock' in check['id'] or 'writer' in check['id']:
                self.assertNotEqual(check['status'], 'BLOCKED', check)
        self.assertEqual(self.app.state.coordinator.ledger.list(True), [])

    async def test_current_catalog_edits_leave_ui_process_snapshot_frozen(self):
        examples = Path(__file__).parent.parent / 'examples'
        source_files = {p.name: p.read_text() for p in (examples / 'Endeavor').iterdir() if p.is_file()}
        process = self.app.state.coordinator.create((examples / 'process-input.md').read_text(), source_files)
        frozen_hash = process['mainframe_knowledge']['content_hash']
        knowledge = Path(self.tmp.name) / 'knowledge'
        knowledge.mkdir(exist_ok=True)
        (knowledge / 'application-knowledge.json').write_text(json.dumps({
            'schema_version': 1, 'application': 'Updated application context', 'utilities': [],
            'notes': ['This note applies to new processes only.'],
        }))
        status, raw = await self.request('/api/knowledge')
        self.assertEqual(status, 200, raw)
        self.assertNotEqual(json.loads(raw)['snapshot']['content_hash'], frozen_hash)
        status, raw = await self.request('/api/state')
        self.assertEqual(status, 200, raw)
        displayed = json.loads(raw)['processes'][0]
        self.assertEqual(displayed['mainframe_knowledge']['content_hash'], frozen_hash)
        self.assertEqual(displayed['mainframe_knowledge']['application']['notes'], [])
        self.assertIn('analysis/mainframe-knowledge.json', displayed['artifacts'])

    async def test_omitting_empty_uploaded_sources_uses_local_endeavor_export(self):
        examples = Path(__file__).parent.parent / 'examples'
        local_export = Path(self.tmp.name) / 'Endeavor'
        local_export.mkdir()
        for source in (examples / 'Endeavor').iterdir():
            if source.is_file():
                (local_export / source.name).write_bytes(source.read_bytes())
        _, raw = await self.request('/api/state')
        token = json.loads(raw)['token']
        status, raw = await self.request('/api/intake', 'POST',
            {'manifest': (examples / 'process-input.md').read_text(), 'prompt': ''},
            [(b'origin', b'http://127.0.0.1:8765'), (b'x-workbench-token', token.encode())])
        self.assertEqual(status, 200, raw)
        process = json.loads(raw)
        self.assertEqual(process['status'], 'READY')
        self.assertTrue(process['source_files'])
        frozen = Path(self.tmp.name) / 'processes' / process['id'] / 'input' / 'sources'
        self.assertEqual(sorted(p.name for p in frozen.iterdir()), sorted(p.name for p in local_export.iterdir()))


if __name__ == '__main__':
    unittest.main()
