"""Real handoff lineage checks and the wire protocol without a live model."""
from copy import deepcopy
import io
import json
from pathlib import Path
import queue
import subprocess
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch

from workbench.copilot import (build_task, build_lineage, source_excerpt,
                               validate_submission, MAX_ADAPTER_TASKS)
from workbench.domain import ValidationError, encode, sha
from workbench.intake import parse_manifest
from workbench.source import analyze_sources
from workbench.__main__ import make_server
from tools.workbench_mcp import StdioServer, WorkflowBridge, TOOLS
from test_source import COBOL
from test_workflow import MANIFEST


class CopilotHandoffTests(unittest.TestCase):
    def document(self, unsupported=False):
        source = COBOL.replace('GOBACK.', 'EXEC CICS RETURN END-EXEC.') if unsupported else COBOL
        files = {'ELIGIBLE.cbl': source}
        doc = parse_manifest(MANIFEST)
        doc.update(source_files={path: sha(text) for path, text in files.items()},
                   manifest_hash=sha(MANIFEST), prompt='Review matching and boundary behavior.',
                   status='READY', analysis=None, packet_issued=False)
        return doc, files

    def returned(self, task):
        ref = {key: value for key, value in task['source_excerpts'][0].items() if key != 'text'}
        return {'process_id': task['process_id'], 'task_hash': task['task_hash'],
                'lineage_hash': task['lineage_hash'], 'summary': 'Source-supported eligibility review.',
                'assumptions': ['AGE is interpreted as an unsigned integer.'],
                'questions': ['Is the source threshold of 18 correct?'], 'source_refs': [ref],
                'adapter_tasks': [{'id': gap['id'],
                                   'implementation_plan': 'Implement CICS return semantics only after the source action/transaction evidence is available; preserve the gap.',
                                   'expected_tests': ['Action mapping, transaction failure and unmapped-action rejection.']}
                                  for gap in task['adapter_tasks']]}

    def test_ready_process_has_deterministic_task_before_sme(self):
        doc, files = self.document()
        task = build_task(doc, files)
        self.assertEqual(task, build_task(doc, files))
        self.assertFalse(doc['packet_issued'])
        self.assertIsNone(doc['analysis'])
        self.assertEqual(task['lineage']['source_snapshot'], analyze_sources(files, doc)['source_snapshot'])
        self.assertEqual(task['task_hash'], sha(encode({k: v for k, v in task.items() if k != 'task_hash'})))
        self.assertEqual(task['usage']['status'], 'UNKNOWN')
        self.assertIsNone(task['usage']['input_tokens'])
        self.assertLessEqual(task['context_character_count'], 16000)

    def test_unsupported_source_produces_specific_implementation_gap(self):
        doc, files = self.document(True)
        task = build_task(doc, files)
        self.assertTrue(task['adapter_tasks'])
        gap = task['adapter_tasks'][0]
        self.assertIn('source', gap['requested_work'])
        self.assertTrue(gap['source_refs'])
        self.assertTrue(gap['expected_tests'])
        self.assertIn('generic scaffold cannot clear', gap['acceptance'])
        with self.assertRaisesRegex(ValidationError, 'every adapter gap'):
            returned = self.returned(task); returned['adapter_tasks'] = []
            validate_submission(task, returned)

    def test_submission_is_provenanced_and_unverified_not_conversion_credit(self):
        doc, files = self.document(True); task = build_task(doc, files)
        returned = self.returned(task); result = validate_submission(task, returned)
        self.assertEqual(result['status'], 'AGENT_ANALYSIS_RETURNED')
        self.assertEqual(result['provenance']['returned_analysis_hash'], sha(encode(returned)))
        self.assertEqual(result['provenance']['validation'], 'STRUCTURE_AND_FROZEN_SOURCE_LINEAGE_ONLY')
        self.assertEqual(result['provenance']['agent_identity'], 'SELF_REPORTED_NOT_AUTHENTICATED')
        self.assertIsNone(result['usage']['output_tokens'])
        self.assertFalse(result['live_ready'])
        self.assertTrue(analyze_sources(files, doc)['blockers'])
        returned['questions'].append('Injected mutation')
        self.assertNotIn('Injected mutation', result['analysis']['questions'])

    def test_task_references_its_preserved_content_addressed_analysis(self):
        doc, files = self.document(); analysis = analyze_sources(files, doc)
        relative = 'analysis/source-analysis-' + sha(encode(analysis)) + '.json'
        doc['analysis_artifact'] = relative
        task = build_task(doc, files, analysis)
        self.assertEqual(task['analysis_reference']['path'], relative)
        self.assertEqual(task['analysis_reference']['sha256'], sha(encode(analysis)))

    def test_refresh_iteration_rejects_stale_return_even_if_source_analysis_is_identical(self):
        doc, files = self.document(); first = build_task(doc, files)
        returned = self.returned(first); doc['copilot_iteration'] = 1
        refreshed = build_task(doc, files)
        self.assertEqual(first['lineage_hash'], refreshed['lineage_hash'])
        self.assertNotEqual(first['task_hash'], refreshed['task_hash'])
        with self.assertRaisesRegex(ValidationError, 'task_hash'):
            validate_submission(refreshed, returned)

    def test_wrong_process_hash_and_source_references_reject(self):
        doc, files = self.document(); task = build_task(doc, files)
        for key, value in [('process_id', 'other-process'), ('task_hash', '0' * 64), ('lineage_hash', '0' * 64)]:
            with self.subTest(key=key), self.assertRaises(ValidationError):
                returned = self.returned(task); returned[key] = value; validate_submission(task, returned)
        for key, value in [('path', '../secret.env'), ('source_hash', '0' * 64), ('start_line', True), ('end_line', 999999)]:
            with self.subTest(key=key), self.assertRaises(ValidationError):
                returned = self.returned(task); returned['source_refs'][0][key] = value
                validate_submission(task, returned)

    def test_tampered_source_manifest_or_task_cannot_repin_lineage(self):
        doc, files = self.document(); task = build_task(doc, files)
        files['ELIGIBLE.cbl'] += '\n'
        with self.assertRaisesRegex(ValidationError, 'source snapshot changed'): build_lineage(doc, files)
        doc, files = self.document(); doc.pop('manifest_hash')
        with self.assertRaisesRegex(ValidationError, 'manifest baseline'): build_task(doc, files)
        returned = self.returned(task); task['operator_request'] += 'changed'
        with self.assertRaisesRegex(ValidationError, 'task integrity'): validate_submission(task, returned)

    def test_answers_commands_extra_claims_and_oversize_return_reject(self):
        doc, files = self.document(); task = build_task(doc, files)
        for field in ('answers', 'command', 'observed_legacy_parity', 'completion', 'input_tokens'):
            with self.subTest(field=field), self.assertRaisesRegex(ValidationError, 'contract'):
                returned = self.returned(task); returned[field] = 'Yes'; validate_submission(task, returned)
        with self.assertRaisesRegex(ValidationError, '128 KB'):
            returned = self.returned(task); returned['summary'] = 'x' * 128001; validate_submission(task, returned)

    def test_excerpt_bounds_and_source_scope_are_enforced(self):
        doc, files = self.document(); excerpt = source_excerpt(doc, files, 'ELIGIBLE.cbl', 9, 11)
        self.assertEqual(excerpt['text'], '\n'.join(COBOL.splitlines()[8:11]))
        self.assertEqual(excerpt['source_hash'], doc['source_files']['ELIGIBLE.cbl'])
        for path, start, end in [('../secret', 1, 1), ('ELIGIBLE.cbl', 0, 2), ('ELIGIBLE.cbl', True, 2), ('ELIGIBLE.cbl', 1, 999)]:
            with self.subTest(path=path, start=start), self.assertRaises(ValidationError):
                source_excerpt(doc, files, path, start, end)
        files['ELIGIBLE.cbl'] = 'x' * 16001; doc['source_files']['ELIGIBLE.cbl'] = sha(files['ELIGIBLE.cbl'])
        with self.assertRaisesRegex(ValidationError, '16,000'): source_excerpt(doc, files, 'ELIGIBLE.cbl', 1, 1)

    def test_gap_context_is_bounded_and_omissions_remain_visible(self):
        doc, files = self.document(True); analysis = analyze_sources(files, doc)
        analysis['blockers'] = analysis['blockers'] * (MAX_ADAPTER_TASKS + 1)
        task = build_task(doc, files, analysis)
        self.assertEqual(len(task['adapter_tasks']), MAX_ADAPTER_TASKS)
        self.assertFalse(task['adapter_tasks_complete'])
        self.assertGreater(task['remaining_gaps'], 0)
        self.assertEqual(task['adapter_gap_count'], len(analysis['blockers']))
        self.assertLessEqual(task['context_character_count'], 16000)

    def test_822_retained_members_are_indexed_with_bounded_inline_source(self):
        doc, files = self.document()
        files.update({'books/MEMBER_' + str(index) + '.cpy': '01 GROUP-' + str(index) + '.\n' + '*> Retained repository member evidence.\n'
                      for index in range(821)})
        doc['source_files'] = {path: sha(text) for path, text in files.items()}
        task = build_task(doc, files)
        self.assertEqual(len(task['lineage']['sources']), 822)
        self.assertLessEqual(task['context_character_count'], 16000)
        self.assertFalse(task['context_complete'])


class McpBridgeTests(unittest.TestCase):
    def initialize(self, server):
        response = server.handle({'jsonrpc': '2.0', 'id': 1, 'method': 'initialize',
                                  'params': {'protocolVersion': '2025-06-18', 'capabilities': {},
                                             'clientInfo': {'name': 'test', 'version': '1'}}})
        self.assertEqual(response['result']['protocolVersion'], '2025-06-18')
        self.assertIsNone(server.handle({'jsonrpc': '2.0', 'method': 'notifications/initialized'}))

    def test_stdio_executable_has_real_handshake_and_no_stdout_logging(self):
        messages = [{'jsonrpc': '2.0', 'id': 1, 'method': 'initialize', 'params': {
            'protocolVersion': '2025-06-18', 'capabilities': {}, 'clientInfo': {'name': 'test', 'version': '1'}}},
                    {'jsonrpc': '2.0', 'method': 'notifications/initialized'},
                    {'jsonrpc': '2.0', 'id': 2, 'method': 'tools/list'}]
        path = Path(__file__).parents[1] / 'tools' / 'workbench_mcp.py'
        result = subprocess.run([sys.executable, str(path)], input=''.join(json.dumps(message) + '\n' for message in messages),
                                text=True, capture_output=True, timeout=10, check=True)
        responses = [json.loads(line) for line in result.stdout.splitlines()]
        self.assertEqual(len(responses), 2); self.assertEqual(result.stderr, '')
        names = {tool['name'] for tool in responses[1]['result']['tools']}
        self.assertEqual(names, set(TOOLS)); self.assertNotIn('execute_command', names)
        self.assertFalse(any('answer' in name for name in names))

    def test_real_stdio_reads_pinned_retrieval_from_single_coordinator_without_mutations(self):
        examples = Path(__file__).parents[1] / 'examples'
        manifest = (examples / 'process-input.md').read_text()
        sources = {path.name: path.read_text() for path in (examples / 'Endeavor').iterdir() if path.is_file()}
        with tempfile.TemporaryDirectory() as workspace:
            http_server, coordinator = make_server(workspace, 0)
            thread = threading.Thread(target=http_server.serve_forever, daemon=True); thread.start()
            origin = 'http://127.0.0.1:' + str(http_server.server_port)
            try:
                doc = coordinator.create(manifest, sources, assistant_mode='agent', requirements_selection=True)
                pid = doc['id']; coordinator.start(pid); coordinator.advance(pid)
                request = coordinator.request_retrieval(pid, [{'kind':'copybook','name':'MISSING','reason':'Required external declaration is missing.'}])
                before = encode(coordinator.ledger.get(pid))
                messages = [{'jsonrpc':'2.0','id':1,'method':'initialize','params':{'protocolVersion':'2025-06-18','capabilities':{},'clientInfo':{'name':'fixture','version':'1'}}},
                            {'jsonrpc':'2.0','method':'notifications/initialized'},
                            {'jsonrpc':'2.0','id':2,'method':'tools/call','params':{'name':'workbench_retrieval_task','arguments':{'process_id':pid}}},
                            {'jsonrpc':'2.0','id':3,'method':'tools/call','params':{'name':'workbench_submit_analysis','arguments':{'process_id':pid,'analysis':{}}}}]
                result = subprocess.run([sys.executable, str(Path(__file__).parents[1]/'tools/workbench_mcp.py'), '--origin', origin],
                    input=''.join(json.dumps(message)+'\n' for message in messages), text=True, capture_output=True, timeout=10, check=True)
                responses = [json.loads(line) for line in result.stdout.splitlines()]
                self.assertEqual(result.stderr, '')
                self.assertEqual(responses[0]['result']['serverInfo']['name'], 'workbench-copilot-retrieval')
                packet = responses[1]['result']['structuredContent']['retrieval']
                self.assertEqual(packet['request_id'], request['retrieval']['request_id'])
                self.assertTrue(packet['needs'][0]['name'].startswith('IDENTITY_SHA256_'))
                self.assertNotIn('MISSING', json.dumps(packet))
                self.assertEqual(packet['needs'][0]['metadata_identity_status'], 'UNAPPROVED_MODEL_METADATA')
                self.assertEqual(packet['return_folder'], 'processes/'+pid+'/analysis/retrieval/'+packet['request_id']+'/inbox')
                self.assertEqual(responses[2]['error']['code'], -32602)
                self.assertEqual(encode(coordinator.ledger.get(pid)), before)
                self.assertFalse(coordinator.ledger.get(pid)['packet_issued'])
                self.assertIsNone(coordinator.worker)
            finally:
                http_server.shutdown(); http_server.server_close(); thread.join(timeout=5); coordinator.close()

    def test_protocol_errors_and_tool_failures_keep_session_alive(self):
        bridge = WorkflowBridge(); server = StdioServer(bridge)
        self.assertEqual(server.handle({'jsonrpc': '2.0', 'id': 0, 'method': 'tools/list'})['error']['code'], -32002)
        self.initialize(server)
        self.assertEqual(server.handle({'jsonrpc': '2.0', 'id': 2, 'method': 'execute'})['error']['code'], -32601)
        self.assertEqual(server.handle({'jsonrpc': '2.0', 'id': 22, 'method': 'tools/call',
                                        'params': {'name': []}})['error']['code'], -32602)
        response = server.handle({'jsonrpc': '2.0', 'id': 3, 'method': 'tools/call',
                                  'params': {'name': 'workbench_retrieval_task', 'arguments': {'process_id': '../escape'}}})
        self.assertTrue(response['result']['isError'])
        self.assertIn('result', server.handle({'jsonrpc': '2.0', 'id': 4, 'method': 'tools/list'}))
        out = io.BytesIO(); server.serve(io.BytesIO(b'{invalid}\n{"jsonrpc":"2.0","id":5,"method":"ping"}\n'), out)
        rows = [json.loads(line) for line in out.getvalue().splitlines()]
        self.assertEqual(rows[0]['error']['code'], -32700); self.assertEqual(rows[1]['result'], {})

    def test_remote_origins_userinfo_and_ambiguous_ports_reject(self):
        for origin in ('https://api.githubcopilot.com', 'http://evil.example:8765', 'http://localhost:8765',
                       'http://127.0.0.1:8765/path', 'http://user:secret@127.0.0.1:8765',
                       'http://127.0.0.1:8765?redirect=x', 'http://127.0.0.1:bad'):
            with self.subTest(origin=origin), self.assertRaises(ValidationError): WorkflowBridge(origin)

    def test_retrieval_uses_only_read_only_route_and_rejects_hidden_workflow_actions(self):
        bridge = WorkflowBridge()
        with patch.object(bridge, 'request', return_value={'retrieval': None}) as request:
            result = bridge.call('workbench_retrieval_task', {'process_id': 'process-a'})
            request.assert_called_once_with('/api/process/process-a/retrieval')
            self.assertEqual(result, {'retrieval': None})
        with patch.object(bridge, 'request') as request:
            for name in ('workbench_status','workbench_source_excerpt','workbench_start','workbench_refresh_analysis'):
                with self.subTest(name=name), self.assertRaises(ValidationError):bridge.call(name, {'process_id':'process-a'})
            request.assert_not_called()

    def test_vscode_template_contains_no_secret_or_copilot_endpoint(self):
        config = json.loads((Path(__file__).parents[1] / 'examples' / 'mcp.json').read_text())
        server = config['servers']['workbench']
        self.assertEqual(server['type'], 'stdio')
        self.assertEqual(server['command'], '${input:workbenchPython}')
        self.assertIn('${workspaceFolder}/tools/workbench_mcp.py', server['args'])
        self.assertNotIn('token', json.dumps(server).lower())
        db2=config['servers']['db2']
        self.assertEqual(db2['headers']['Authorization'],'Bearer ${input:db2Token}')
        prompt=next(item for item in config['inputs'] if item['id']=='db2Token')
        self.assertTrue(prompt['password']);self.assertNotIn('default',prompt)
        self.assertNotIn('githubcopilot.com', json.dumps(config))


if __name__ == '__main__': unittest.main()
