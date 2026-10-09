"""Exercise the actual FastMCP SDK transport, not the legacy protocol fixture."""
import asyncio
from contextlib import contextmanager
import json
from pathlib import Path
import socket
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch
from urllib.request import Request, urlopen
from urllib.error import HTTPError

from fastmcp import Client
from starlette.middleware import Middleware
import uvicorn
from tools import db2_mcp_server as gateway
from workbench.connectors import Db2MCP
from tests.test_db2_search import Connection


@contextmanager
def http_server(app_builder):
    sock=socket.socket(); sock.bind(('127.0.0.1',0)); port=sock.getsockname()[1]
    app=app_builder(port)
    server=uvicorn.Server(uvicorn.Config(app,log_level='critical',lifespan='on'))
    worker=threading.Thread(target=lambda:server.run(sockets=[sock]),daemon=True); worker.start()
    until=time.monotonic()+10
    while not server.started and worker.is_alive() and time.monotonic()<until: time.sleep(.01)
    if not server.started: raise AssertionError('FastMCP HTTP failed to start')
    try: yield f'http://127.0.0.1:{port}/mcp'
    finally: server.should_exit=True; worker.join(10); sock.close()


class FastMCPTests(unittest.TestCase):
    def test_sdk_content_search_and_fixed_read_tools(self):
        async def run(directory):
            sql=[]
            with patch.object(gateway,'connect',side_effect=lambda:Connection(sql)),patch.object(gateway,'configured_row_limit',return_value=500000):
                async with Client(gateway.create_server(Path(directory)/'search',protected=False)) as client:
                    tools=await client.list_tools()
                    self.assertTrue({'db2_search_start','db2_search_continue','db2_read_table_rows'}<={t.name for t in tools})
                    self.assertTrue(all(t.annotations.read_only_hint for t in tools))
                    result=await client.call_tool('db2_search_start',{'query':'needle'}); token=result.data['search_id']
                    for _ in range(100):
                        result=await client.call_tool('db2_search_continue',{'search_id':token})
                        if result.data['status']!='RUNNING':break
                    self.assertEqual(result.data['status'],'PARTIAL')
                    rows=(await client.call_tool('db2_search_results',{'search_id':token})).data['rows']
                    self.assertTrue(any(r['location']=='REMOTE' and r['kind']=='content' for r in rows))
                    result=await client.call_tool('db2_search_continue',{'search_id':token,'row_budget':True},raise_on_error=False)
                    self.assertTrue(result.is_error)
        with tempfile.TemporaryDirectory() as directory: asyncio.run(run(directory))

    def test_real_http_negotiates_with_workbench_client_and_rejects_wrong_token_origin(self):
        with tempfile.TemporaryDirectory() as directory:
            mcp=gateway.create_server(Path(directory)/'search',protected=False)
            def app(port):
                return mcp.http_app(path='/mcp',json_response=True,stateless_http=True,
                    middleware=[Middleware(gateway.LocalSecurity,port=port,token='fixture-token')])
            with http_server(app) as url:
                client=Db2MCP(url,'fixture-token'); status=client.initialize()
                self.assertIn('db2_search_start',status['read_tools'])
                for headers in ({'Authorization':'Bearer wrong'}, {'Authorization':'Bearer fixture-token','Origin':'http://evil.invalid'}):
                    with self.assertRaises(HTTPError) as failure:
                        urlopen(Request(url,data=b'{}',headers={'Content-Type':'application/json',**headers}),timeout=5)
                    self.assertEqual(failure.exception.code,403)
                with patch.object(gateway,'execute',side_effect=RuntimeError('SECRET SENTINEL')):
                    with self.assertRaises(Exception) as failure: client.list_schemas()
                    self.assertNotIn('SECRET',str(failure.exception))

    def test_stdio_sdk_handshake_and_tool_listing_without_db_credentials(self):
        async def run():
            from fastmcp.client.transports import StdioTransport
            transport=StdioTransport(command=sys.executable,args=[str(Path(gateway.__file__).absolute()),'--transport','stdio'])
            async with Client(transport) as client:
                tools=await client.list_tools()
                names={t.name for t in tools}
                self.assertEqual(names,{'db2_list_schemas','db2_list_tables','db2_describe_table','db2_export_snapshot_to_inbox'})
                self.assertFalse({'db2_sample_rows','db2_read_table_rows','db2_search_results'}&names)
        asyncio.run(run())


if __name__=='__main__':unittest.main()
