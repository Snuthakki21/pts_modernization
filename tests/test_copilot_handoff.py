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

    def test_real_stdio_loopback_api_uses_the_single_coordinator_and_preserves_review_quota(self):
        examples = Path(__file__).parents[1] / 'examples'
        manifest = (examples / 'process-input.md').read_text()
        sources = {path.name: path.read_text() for path in (examples / 'Endeavor').iterdir() if path.is_file()}
        with tempfile.TemporaryDirectory() as workspace:
            http_server, coordinator = make_server(workspace, 0)
            thread = threading.Thread(target=http_server.serve_forever, daemon=True)
            thread.start()
            origin = 'http://127.0.0.1:' + str(http_server.server_port)
            script = Path(__file__).parents[1] / 'tools' / 'workbench_mcp.py'
            try:
                with subprocess.Popen([sys.executable, str(script), '--origin', origin],
                                      stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                      stderr=subprocess.PIPE, text=True, bufsize=1) as agent:
                    responses = queue.Queue()
                    def read_responses():
                        for line in agent.stdout: responses.put(line)
                    reader = threading.Thread(target=read_responses, daemon=True)
                    reader.start()
                    request_id = 0
                    def rpc(method, params=None):
                        nonlocal request_id
                        request_id += 1
                        agent.stdin.write(json.dumps({'jsonrpc': '2.0', 'id': request_id,
                                                     'method': method, 'params': params or {}}) + '\n')
                        agent.stdin.flush()
                        try: line = responses.get(timeout=10)
                        except queue.Empty: self.fail('The real MCP subprocess did not answer')
                        response = json.loads(line)
                        self.assertEqual(response['id'], request_id)
                        self.assertNotIn('error', response)
                        return response['result']
                    def call(name, arguments):
                        response = rpc('tools/call', {'name': name, 'arguments': arguments})
                        self.assertFalse(response.get('isError'), response.get('content'))
                        return response['structuredContent']
                    def returned(task):
                        path, info = next((path, info) for path, info in task['lineage']['sources'].items()
                                          if info['line_count'])
                        return {'process_id': task['process_id'], 'task_hash': task['task_hash'],
                                'lineage_hash': task['lineage_hash'],
                                'summary': 'Fictional example source review; external suggestions remain unverified.',
                                'assumptions': [], 'questions': [],
                                'source_refs': [{'path': path, 'start_line': 1, 'end_line': 1,
                                                 'source_hash': info['source_hash']}],
                                'adapter_tasks': [{'id': item['id'],
                                                   'implementation_plan': 'Retain this named source gap until its implementation and tests pass the existing coordinator.',
                                                   'expected_tests': ['Source-supported valid, invalid and boundary behavior.']}
                                                  for item in task['adapter_tasks']]}
                    try:
                        initialized = rpc('initialize', {'protocolVersion': '2025-06-18', 'capabilities': {},
                                                         'clientInfo': {'name': 'loopback-integration-test', 'version': '1'}})
                        self.assertEqual(initialized['serverInfo']['name'], 'workbench-copilot-workflow')
                        agent.stdin.write(json.dumps({'jsonrpc': '2.0', 'method': 'notifications/initialized'}) + '\n')
                        agent.stdin.flush()
                        intake = call('workbench_intake', {'manifest': manifest, 'sources': sources,
                                                          'prompt': 'Review this fictional selected process.'})
                        pid = intake['id']
                        self.assertEqual(intake['assistant_mode'], 'copilot_chat')
                        self.assertEqual(intake['status'], 'READY')
                        self.assertIsNone(coordinator.worker)
                        self.assertEqual(call('workbench_start', {'process_id': pid})['status'], 'QUEUED_ANALYSIS')
                        waiting = coordinator.advance(pid)
                        self.assertEqual(waiting['status'], 'WAITING_COPILOT')
                        self.assertFalse(waiting['packet_issued'])
                        self.assertFalse((Path(workspace) / 'processes' / pid / 'review').exists())
                        task = call('workbench_next_task', {'process_id': pid})
                        lineage = call('workbench_lineage', {'process_id': pid})
                        self.assertTrue(lineage['closure']['complete'])
                        submission = returned(task)
                        ref = submission['source_refs'][0]
                        excerpt = call('workbench_source_excerpt', {'process_id': pid, 'path': ref['path'],
                                                                   'start_line': 1, 'end_line': 1})
                        self.assertEqual(excerpt['source_hash'], ref['source_hash'])
                        self.assertEqual(excerpt['text'], sources[ref['path']].splitlines()[0])
                        token = WorkflowBridge(origin).request('/api/state')['token']
                        status = call('workbench_status', {'process_id': pid})
                        self.assertNotIn(token, json.dumps(status))
                        self.assertEqual(status['copilot_usage']['status'], 'UNKNOWN')
                        self.assertEqual(call('workbench_refresh_analysis', {'process_id': pid})['status'], 'QUEUED_ANALYSIS')
                        self.assertEqual(coordinator.advance(pid)['status'], 'WAITING_COPILOT')
                        refreshed = call('workbench_next_task', {'process_id': pid})
                        self.assertNotEqual(task['task_hash'], refreshed['task_hash'])
                        stale = rpc('tools/call', {'name': 'workbench_submit_analysis',
                                                  'arguments': {'process_id': pid, 'analysis': submission}})
                        self.assertTrue(stale['isError'])
                        self.assertIn('task_hash', stale['content'][0]['text'])
                        self.assertFalse(coordinator.ledger.get(pid)['packet_issued'])
                        accepted = call('workbench_submit_analysis', {'process_id': pid, 'analysis': returned(refreshed)})
                        self.assertEqual(accepted['status'], 'QUEUED_ANALYSIS')
                        reviewed = coordinator.advance(pid)
                        self.assertEqual(reviewed['status'], 'WAITING_SME')
                        self.assertTrue(reviewed['packet_issued'])
                        self.assertFalse(reviewed['packet_imported'])
                        packet_hash = reviewed['packet_hash']
                        duplicate = rpc('tools/call', {'name': 'workbench_submit_analysis',
                                                      'arguments': {'process_id': pid, 'analysis': returned(refreshed)}})
                        self.assertTrue(duplicate['isError'])
                        self.assertEqual(coordinator.ledger.get(pid)['packet_hash'], packet_hash)
                        self.assertEqual(coordinator.ledger.get(pid)['source_files'], intake['source_files'])
                        self.assertIsNone(coordinator.worker)
                        agent.stdin.close()
                        self.assertEqual(agent.wait(timeout=5), 0)
                        reader.join(timeout=5)
                        self.assertFalse(reader.is_alive())
                        self.assertEqual(agent.stderr.read(), '')
                    finally:
                        if agent.poll() is None:
                            agent.terminate(); agent.wait(timeout=5)
                        reader.join(timeout=5)
            finally:
                http_server.shutdown(); http_server.server_close(); thread.join(timeout=5)
                coordinator.close()

    def test_protocol_errors_and_tool_failures_keep_session_alive(self):
        bridge = WorkflowBridge(); server = StdioServer(bridge)
        self.assertEqual(server.handle({'jsonrpc': '2.0', 'id': 0, 'method': 'tools/list'})['error']['code'], -32002)
        self.initialize(server)
        self.assertEqual(server.handle({'jsonrpc': '2.0', 'id': 2, 'method': 'execute'})['error']['code'], -32601)
        self.assertEqual(server.handle({'jsonrpc': '2.0', 'id': 22, 'method': 'tools/call',
                                        'params': {'name': []}})['error']['code'], -32602)
        response = server.handle({'jsonrpc': '2.0', 'id': 3, 'method': 'tools/call',
                                  'params': {'name': 'workbench_start', 'arguments': {'process_id': '../escape'}}})
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

    def test_status_strips_session_token_and_tools_use_the_running_api(self):
        bridge = WorkflowBridge()
        state = {'token': 'private-session-token', 'processes': [{'id': 'process-a', 'name': 'A', 'status': 'READY'}]}
        with patch.object(bridge, 'request', return_value=state) as request:
            result = bridge.call('workbench_status', {'process_id': 'process-a'})
            self.assertNotIn('private-session-token', json.dumps(result)); request.assert_called_once_with('/api/state')
        with patch.object(bridge, 'request', return_value={'ok': True}) as request:
            bridge.call('workbench_source_excerpt', {'process_id': 'process-a', 'path': 'ELIGIBLE.cbl', 'start_line': 1, 'end_line': 10})
            request.assert_called_once_with('/api/process/process-a/agent/source?path=ELIGIBLE.cbl&start_line=1&end_line=10')
        with patch.object(bridge, 'request') as request:
            with self.assertRaises(ValidationError): bridge.call('workbench_start', {'process_id': 'process-a', 'command': 'rm'})
            request.assert_not_called()
        with patch.object(bridge, 'request', return_value={'status': 'QUEUED_ANALYSIS'}) as request:
            result = bridge.call('workbench_refresh_analysis', {'process_id': 'process-a'})
            request.assert_called_once_with('/api/process/process-a/refresh-analysis', {})
            self.assertEqual(result['status'], 'QUEUED_ANALYSIS')

    def test_vscode_template_contains_no_secret_or_copilot_endpoint(self):
        config = json.loads((Path(__file__).parents[1] / 'examples' / 'mcp.json').read_text())
        server = config['servers']['workbench']
        self.assertEqual(server['type'], 'stdio')
        self.assertEqual(server['command'], '${input:workbenchPython}')
        self.assertIn('${workspaceFolder}/tools/workbench_mcp.py', server['args'])
        self.assertNotIn('token', json.dumps(config).lower())
        self.assertNotIn('githubcopilot.com', json.dumps(config))


if __name__ == '__main__': unittest.main()
