#!/usr/bin/env python3
"""Copilot-only read-only MCP transport for the current retrieval request.

Claude Code has no MCP integration. Local development, analysis, testing and
Coordinator actions belong to its file/CLI workflow. This process owns no ledger,
Coordinator or worker and cannot mutate the running service.
"""
import argparse
import json
import re
from pathlib import Path
import sys
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit, quote
from urllib.request import Request, build_opener, ProxyHandler, HTTPRedirectHandler

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from workbench.domain import ValidationError, decode, identity, require
from workbench.limits import MAX_HTTP_BODY_BYTES, MAX_JSON_DOCUMENT_BYTES

MAX_MESSAGE_BYTES = MAX_HTTP_BODY_BYTES
MAX_RESPONSE_BYTES = MAX_JSON_DOCUMENT_BYTES
PROTOCOL_VERSIONS = ('2025-06-18', '2025-03-26', '2024-11-05')
PROCESS_ID = {'type': 'string', 'pattern': '^[a-zA-Z][a-zA-Z0-9_-]{0,79}$', 'maxLength': 80}
TOOLS = {'workbench_retrieval_task': (
    'Deprecated retrieval-only compatibility bridge. Read the current safe request projection and preserve identity qualification gates. The current workflow uses Claude Code with approved Db2 MCP and read-only Zowe CLI directly. This bridge performs no development, analysis, testing or workflow mutations.',
    {'type': 'object', 'properties': {'process_id': PROCESS_ID}, 'required': ['process_id'], 'additionalProperties': False}, True)}


class NoRedirects(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise ValidationError('Workbench API redirects are prohibited')


class WorkflowBridge:
    def __init__(self, origin='http://127.0.0.1:8765', role='retrieval'):
        # Historical discovery config remains a read-only alias, never the old
        # operational tool set. Development is deliberately rejected, not hidden.
        require(isinstance(role, str) and role in ('retrieval', 'discovery'),
                'Only the deprecated retrieval compatibility role is available; workflow-proxy development tools are prohibited')
        self.role = 'retrieval'
        self.tools = dict(TOOLS)
        require(isinstance(origin, str), 'Workbench origin must be a loopback HTTP URL')
        try:
            parsed = urlsplit(origin); port = parsed.port
        except ValueError as exc:
            raise ValidationError('Invalid workbench origin') from exc
        require(parsed.scheme == 'http' and parsed.hostname in ('127.0.0.1', '::1')
                and port is not None and 1 <= port <= 65535 and parsed.path in ('', '/')
                and not parsed.query and not parsed.fragment and parsed.username is None and parsed.password is None,
                'Workbench origin must be an explicit loopback HTTP URL with a port')
        self.origin = origin.rstrip('/')
        self.opener = build_opener(ProxyHandler({}), NoRedirects())

    def request(self, path, data=None):
        require(isinstance(path, str) and data is None and
                re.fullmatch(r'/api/process/[a-zA-Z][a-zA-Z0-9_-]{0,79}/retrieval', path),
                'Only read-only retrieval requests are available through Copilot MCP')
        request = Request(self.origin + path, headers={'Accept': 'application/json'}, method='GET')
        try:
            with self.opener.open(request, timeout=15) as response:
                require(response.geturl() == self.origin + path, 'Workbench API redirects are prohibited')
                raw = response.read(MAX_RESPONSE_BYTES + 1)
                require(len(raw) <= MAX_RESPONSE_BYTES, 'Workbench response exceeds the bound')
                require(response.headers.get_content_type() == 'application/json', 'Workbench API must return JSON')
                return decode(raw, MAX_RESPONSE_BYTES)
        except HTTPError as exc:
            raw = exc.read(4097)
            try:
                detail = decode(raw, 4096)
                message = detail.get('error') if isinstance(detail, dict) else None
            except ValidationError: message = None
            finally: exc.close()
            raise ValidationError(message[:1000] if isinstance(message, str) else 'Workbench API rejected this retrieval request') from exc
        except (URLError, TimeoutError, OSError) as exc:
            raise ValidationError('Workbench UI server is unavailable. Start it, then retry this local retrieval tool.') from exc

    def call(self, name, arguments):
        require(isinstance(name, str) and name in self.tools, 'Workflow tool is unavailable to the retrieval role')
        require(isinstance(arguments, dict) and set(arguments) == {'process_id'}, 'Invalid retrieval tool arguments')
        pid = arguments['process_id']; identity(pid)
        return self.request('/api/process/' + quote(pid, safe='') + '/retrieval')


class StdioServer:
    def __init__(self, bridge):
        self.bridge = bridge; self.initialized = False; self.ready = False; self.protocol = None

    @staticmethod
    def error(request_id, code, message):
        return {'jsonrpc': '2.0', 'id': request_id, 'error': {'code': code, 'message': message}}

    def handle(self, request):
        request_id = request.get('id') if isinstance(request, dict) else None
        if not isinstance(request, dict) or request.get('jsonrpc') != '2.0' or not isinstance(request.get('method'), str):
            return self.error(request_id, -32600, 'Invalid JSON-RPC request')
        if 'id' in request and type(request_id) not in (str, int):
            return self.error(None, -32600, 'Invalid request ID')
        params = request.get('params', {})
        if not isinstance(params, dict): return self.error(request_id, -32602, 'Parameters must be an object')
        method = request['method']
        if 'id' not in request:
            if method == 'notifications/initialized' and self.initialized: self.ready = True
            return None
        if method == 'initialize':
            if self.initialized: return self.error(request_id, -32600, 'Session is already initialized')
            if not isinstance(params.get('protocolVersion'), str) or not isinstance(params.get('capabilities'), dict) or not isinstance(params.get('clientInfo'), dict):
                return self.error(request_id, -32602, 'Initialize requires protocolVersion, capabilities and clientInfo')
            self.protocol = params['protocolVersion'] if params['protocolVersion'] in PROTOCOL_VERSIONS else PROTOCOL_VERSIONS[0]
            self.initialized = True
            result = {'protocolVersion': self.protocol, 'capabilities': {'tools': {}},
                      'serverInfo': {'name': 'workbench-copilot-retrieval', 'version': '2.0.0'},
                      'instructions': 'Deprecated retrieval-only compatibility surface; it is not part of the configured Claude MCP workflow. Preserve safe projection and metadata-approval gates. Claude Code uses approved Db2 MCP and read-only Zowe CLI directly, then local analysis, development, tests and review. Never execute source-system writes, read raw records into model context or answer SME questions.'}
        elif method == 'ping': result = {}
        elif not self.ready: return self.error(request_id, -32002, 'Initialize the MCP session first')
        elif method == 'tools/list':
            if params: return self.error(request_id, -32602, 'Tools are a single page with no parameters')
            result = {'tools': [{'name': name, 'description': spec[0], 'inputSchema': spec[1],
                                 'annotations': {'readOnlyHint': spec[2], 'destructiveHint': False, 'openWorldHint': False}}
                                for name, spec in self.bridge.tools.items()]}
        elif method == 'tools/call':
            if set(params) - {'name', 'arguments', '_meta'} or not isinstance(params.get('name'), str) or params['name'] not in self.bridge.tools:
                return self.error(request_id, -32602, 'Unknown tool or invalid call parameters')
            try:
                value = self.bridge.call(params['name'], params.get('arguments', {}))
                result = {'content': [{'type': 'text', 'text': json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(',', ':'))}]}
                if self.protocol == '2025-06-18': result['structuredContent'] = value
            except (ValidationError, UnicodeError, TypeError, ValueError) as exc:
                result = {'isError': True, 'content': [{'type': 'text', 'text': str(exc)[:1000]}]}
            except Exception:
                result = {'isError': True, 'content': [{'type': 'text', 'text': 'Workflow operation failed safely; inspect the local workbench event ledger.'}]}
        else: return self.error(request_id, -32601, 'Method not found')
        return {'jsonrpc': '2.0', 'id': request_id, 'result': result}

    def serve(self, input_stream, output_stream):
        while True:
            line = input_stream.readline(MAX_MESSAGE_BYTES + 1)
            if not line: return
            if len(line) > MAX_MESSAGE_BYTES:
                if not line.endswith(b'\n'):
                    while True:
                        fragment = input_stream.readline(MAX_MESSAGE_BYTES + 1)
                        if not fragment or fragment.endswith(b'\n'): break
                response = self.error(None, -32700, 'Message exceeds the permitted size')
            else:
                try: response = self.handle(decode(line, MAX_MESSAGE_BYTES))
                except ValidationError: response = self.error(None, -32700, 'Invalid JSON message')
            if response is not None:
                raw = json.dumps(response, ensure_ascii=False, allow_nan=False, separators=(',', ':')).encode('utf-8')
                if len(raw) > MAX_RESPONSE_BYTES:
                    raw = json.dumps(self.error(response.get('id'), -32000, 'Response exceeds the permitted size')).encode('utf-8')
                output_stream.write(raw + b'\n'); output_stream.flush()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--origin', default='http://127.0.0.1:8765', help='Already running workbench loopback UI origin')
    parser.add_argument('--role', choices=('retrieval','discovery'), default='retrieval', help='Copilot retrieval only; discovery is a deprecated equivalent alias')
    args = parser.parse_args(argv)
    try: bridge = WorkflowBridge(args.origin, role=args.role)
    except ValidationError as exc:
        print(str(exc), file=sys.stderr); return 2
    StdioServer(bridge).serve(sys.stdin.buffer, sys.stdout.buffer)
    return 0


if __name__ == '__main__': raise SystemExit(main())
