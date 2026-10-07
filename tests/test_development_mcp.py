"""Enterprise host split: only Copilot retrieval may expose MCP tools.

Previous development-MCP success expectations are intentionally replaced: the
organization prohibits every Claude Code MCP integration, including this one.
"""
import io
import json
from pathlib import Path
import random
import secrets
import subprocess
import sys
import unittest
from unittest.mock import patch
from email.message import Message

from tools.workbench_mcp import StdioServer, WorkflowBridge, TOOLS
from workbench.domain import ValidationError

RETIRED = ('workbench_prepare_development', 'workbench_revise_development', 'workbench_development_task',
           'workbench_submit_development', 'workbench_next_task', 'workbench_lineage', 'workbench_source_excerpt',
           'workbench_context_excerpt', 'workbench_rules', 'workbench_obligations', 'workbench_submit_analysis',
           'workbench_refresh_analysis', 'workbench_start', 'workbench_resume', 'workbench_intake',
           'workbench_begin_work', 'workbench_end_work', 'workbench_economics', 'workbench_record_measurement',
           'workbench_forecast', 'workbench_factory', 'workbench_status', 'workbench_requirements')


def initialized(bridge):
    server = StdioServer(bridge)
    response = server.handle({'jsonrpc':'2.0','id':1,'method':'initialize','params':{
        'protocolVersion':'2025-06-18','capabilities':{},'clientInfo':{'name':'fixture','version':'1'}}})
    server.handle({'jsonrpc':'2.0','method':'notifications/initialized'})
    return server, response['result']


class RetrievalBridgeTests(unittest.TestCase):
    def test_only_retrieval_is_advertised_and_discovery_alias_cannot_restore_writes(self):
        for role in ('retrieval', 'discovery'):
            server, info = initialized(WorkflowBridge(role=role))
            result = server.handle({'jsonrpc':'2.0','id':2,'method':'tools/list'})['result']
            self.assertEqual({tool['name'] for tool in result['tools']}, {'workbench_retrieval_task'})
            self.assertTrue(all(t['annotations']['readOnlyHint'] for t in result['tools']))
            self.assertIn('Copilot', info['instructions'])
            self.assertIn('no MCP', info['instructions'])

    def test_claude_development_role_is_rejected_before_any_transport(self):
        for role in ('development','claude','all','admin','DEVELOPMENT','',None,True):
            with self.subTest(role=role), self.assertRaises(ValidationError):WorkflowBridge(role=role)

    def test_every_retired_workflow_tool_is_denied_before_http(self):
        bridge = WorkflowBridge(); server, _ = initialized(bridge)
        with patch.object(bridge,'request') as request:
            for name in RETIRED:
                with self.subTest(name=name):
                    with self.assertRaises(ValidationError):bridge.call(name, {'process_id':'process-a'})
                    response = server.handle({'jsonrpc':'2.0','id':3,'method':'tools/call',
                        'params':{'name':name,'arguments':{'process_id':'process-a'}}})
                    self.assertEqual(response['error']['code'], -32602)
            request.assert_not_called()

    def test_direct_request_cannot_bypass_read_only_retrieval_route(self):
        bridge = WorkflowBridge()
        with patch.object(bridge.opener, 'open') as opened:
            for path, data in [('/api/state',None),('/api/session-token',None),('/api/process/p/agent/source',None),
                               ('/api/process/p/retrieval',{}),('/api/process/p/retrieval?source=1',None),
                               ('/api/process/p/retrieval/../start',None),('/api/process/%2e%2e/retrieval',None),
                               ('/api/process/p/start',{}),('/api/development/'+'a'*64,None)]:
                with self.subTest(path=path,data=data), self.assertRaises(ValidationError):bridge.request(path,data)
            opened.assert_not_called()

    def test_tool_validates_exact_process_arguments_before_http(self):
        bridge = WorkflowBridge()
        with patch.object(bridge, 'request') as request:
            for args in ({}, {'process_id':True}, {'process_id':None}, {'process_id':'../secret'},
                         {'process_id':'p','command':'run'}, {'process_id':'p','path':'source.cbl'},
                         {'process_id':'p','analysis':{}}, {'process_id':'p','handoff_id':'a'*64}):
                with self.subTest(args=args), self.assertRaises(ValidationError):bridge.call('workbench_retrieval_task',args)
            request.assert_not_called()

    def test_twenty_randomized_process_identities_route_only_to_retrieval(self):
        seed = secrets.randbits(63); rng = random.Random(seed)
        bridge = WorkflowBridge()
        for _ in range(20):
            pid = 'p-' + ''.join(rng.choice('abcdef0123456789') for _ in range(32))
            with self.subTest(seed=seed, process=pid), patch.object(bridge, 'request', return_value={'process_id':pid}) as request:
                self.assertEqual(bridge.call('workbench_retrieval_task',{'process_id':pid}),{'process_id':pid})
                request.assert_called_once_with('/api/process/'+pid+'/retrieval')

    def test_http_request_is_get_without_session_token_or_credentials(self):
        bridge = WorkflowBridge(); calls=[]
        class Response:
            def __init__(self,url):
                self.url=url; self.headers=Message();self.headers['Content-Type']='application/json'
            def __enter__(self):return self
            def __exit__(self,*args):return False
            def geturl(self):return self.url
            def read(self,limit):return b'{"kind":"RETRIEVAL_REQUEST"}'[:limit]
        def opened(request,timeout):calls.append(request);return Response(request.full_url)
        with patch.object(bridge.opener,'open',side_effect=opened):
            result=bridge.call('workbench_retrieval_task',{'process_id':'p'})
        self.assertEqual(result,{'kind':'RETRIEVAL_REQUEST'})
        self.assertEqual(len(calls),1)
        self.assertEqual(calls[0].get_method(),'GET')
        self.assertIsNone(calls[0].data)
        self.assertIsNone(calls[0].get_header('X-workbench-token'))

    def test_executable_development_profile_fails_without_handshake(self):
        script=Path(__file__).parents[1]/'tools/workbench_mcp.py'
        result=subprocess.run([sys.executable,str(script),'--role','development'], input='',text=True,capture_output=True,timeout=10)
        self.assertNotEqual(result.returncode,0)
        self.assertEqual(result.stdout,'')
        self.assertIn('retrieval',result.stderr)

    def test_claude_template_has_no_mcp_server_and_copilot_selects_retrieval(self):
        root=Path(__file__).parents[1]
        self.assertEqual(json.loads((root/'examples/claude-mcp.json').read_text()),{'mcpServers':{}})
        copilot=json.loads((root/'examples/mcp.json').read_text())
        self.assertEqual(copilot['servers']['workbench']['args'][-2:],['--role','retrieval'])


if __name__=='__main__':unittest.main()
