"""Mocked HTTP/ODBC contracts; these do not assert live Db2 or Zowe success."""
import io
import json
import os
import threading
import unittest
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from types import SimpleNamespace
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from tools import db2_mcp_server as gateway
from workbench.connectors import Db2MCP, _sse_response, catalog_sql, discover_catalog, read_only_discovery
from workbench.domain import ValidationError


@contextmanager
def server(handler):
    http=ThreadingHTTPServer(('127.0.0.1',0),handler)
    thread=threading.Thread(target=http.serve_forever,daemon=True);thread.start()
    try:yield f'http://127.0.0.1:{http.server_port}'
    finally:http.shutdown();http.server_close();thread.join(2)


def wire_handler(version='2025-06-18',sse=False):
    class Wire(BaseHTTPRequestHandler):
        calls=[]
        def log_message(self,*args):pass
        def do_POST(self):
            body=json.loads(self.rfile.read(int(self.headers['Content-Length'])))
            self.calls.append((body,dict(self.headers)))
            method=body['method']
            if method!='initialize' and (self.headers.get('Mcp-Session-Id')!='session-123' or self.headers.get('MCP-Protocol-Version')!=version):
                self.send_response(400);self.end_headers();return
            if method=='notifications/initialized':
                self.send_response(202);self.end_headers();return
            if method=='initialize':result={'protocolVersion':version,'capabilities':{'tools':{}}}
            elif method=='tools/list':
                result=({'tools':[{'name':'db2_list_schemas'}],'nextCursor':'tool-page-2'} if not body['params'] else {'tools':[{'name':'db2_list_tables'}]})
            else:result={'structuredContent':{'rows':[{'CREATOR':'NEW_SCHEMA','NAME':'UNLISTED_TABLE'}],'has_more':False,'next_cursor':None}}
            response={'jsonrpc':'2.0','id':body['id'],'result':result}
            if sse and method=='tools/call':
                data=('data: {"jsonrpc":"2.0","method":"notifications/progress"}\n\n'+''.join('data: '+line+'\n' for line in json.dumps(response,indent=2).splitlines())+'\n'+'data: {"jsonrpc":"2.0","method":"notifications/progress"}\n\n').encode()
                content_type='text/event-stream'
            else:data=json.dumps(response).encode();content_type='application/json'
            self.send_response(200);self.send_header('Content-Type',content_type)
            self.send_header('mCp-SeSsIoN-iD','session-123');self.send_header('Content-Length',str(len(data)));self.end_headers();self.wfile.write(data)
    return Wire


class MCPProtocolTests(unittest.TestCase):
    def test_negotiated_older_version_mixed_case_session_and_tool_pagination(self):
        handler=wire_handler('2025-03-26')
        with server(handler) as url:
            client=Db2MCP(url);status=client.initialize()
            self.assertEqual(status['protocol_version'],'2025-03-26')
            self.assertEqual(client.session,'session-123')
            self.assertEqual(client.list_tables()['rows'][0]['NAME'],'UNLISTED_TABLE')
        self.assertEqual(handler.calls[0][0]['params']['protocolVersion'],'2025-06-18')
        self.assertNotIn('mcp-protocol-version',{k.lower() for k in handler.calls[0][1]})
        self.assertEqual(handler.calls[3][0]['params'],{'cursor':'tool-page-2'})

    def test_unsupported_returned_version_stops_before_initialized_notification(self):
        handler=wire_handler('2026-07-28')
        with server(handler) as url:
            with self.assertRaisesRegex(ValidationError,'Unsupported MCP protocol'):Db2MCP(url).initialize()
        self.assertEqual(len(handler.calls),1)

    def test_sse_multiline_matching_response_ignores_progress_notifications(self):
        handler=wire_handler(sse=True)
        with server(handler) as url:
            client=Db2MCP(url);client.initialize()
            self.assertEqual(client.list_tables()['rows'][0]['CREATOR'],'NEW_SCHEMA')

    def test_unsolicited_server_request_is_not_executed(self):
        stream=io.BytesIO(b'data: {"jsonrpc":"2.0","id":8,"method":"sampling/createMessage"}\n\n')
        with self.assertRaisesRegex(ValidationError,'Unsolicited'):_sse_response(stream,1)

    def test_session_replacement_and_invalid_response_identity_are_rejected(self):
        client=Db2MCP('http://localhost:8766');client.protocol='2025-06-18';client.session='original'
        with patch('workbench.connectors.post_json',return_value=({'jsonrpc':'2.0','id':1,'result':{}},{'MCP-SESSION-ID':'replacement'})):
            with self.assertRaisesRegex(ValidationError,'session changed'):client.rpc('tools/list',{})
        with patch('workbench.connectors.post_json',return_value=({'jsonrpc':'2.0','id':999,'result':{}},{})):
            with self.assertRaisesRegex(ValidationError,'identity'):client.rpc('tools/list',{})


class DiscoveryTests(unittest.TestCase):
    def gateway_pages(self,name,args):
        self.operations.append((name,args))
        if name=='db2_list_schemas':
            return {'rows':[{'CREATOR':'SECOND' if args.get('after_schema') else 'FIRST'}],
                    'has_more':not bool(args.get('after_schema')),
                    'next_cursor':None if args.get('after_schema') else {'after_schema':'FIRST'}}
        return {'rows':[{'CREATOR':'SECOND' if args.get('after_schema') else 'FIRST','NAME':'TABLE'}],
                'has_more':not bool(args.get('after_schema')),
                'next_cursor':None if args.get('after_schema') else {'after_schema':'FIRST','after_table':'TABLE'}}

    def setUp(self):self.operations=[]

    def test_read_only_discovery_traverses_both_catalogs_without_prelisted_names_or_samples(self):
        with patch.dict(os.environ,{'WB_DB2_MCP_TOKEN':'fixture-token'},clear=True),patch.object(gateway,'execute',side_effect=self.gateway_pages):
            with server(gateway.Handler) as url,patch.dict(os.environ,{'WB_DB2_MCP_URL':url}):
                result=read_only_discovery()['db2']
        self.assertEqual(result['coverage'],'COMPLETE')
        self.assertEqual(result['schemas']['pages'],2);self.assertEqual(result['tables']['pages'],2)
        self.assertEqual(len(result['tables']['rows']),2)
        self.assertFalse(result['tables']['snapshot_consistent'])
        self.assertEqual({name for name,args in self.operations},{'db2_list_schemas','db2_list_tables'})
        self.assertIsNone(self.operations[2][1]['schema'])

    def test_page_budget_preserves_resume_cursor_and_partial_coverage(self):
        with patch.dict(os.environ,{'WB_DB2_MCP_TOKEN':'fixture-token'},clear=True),patch.object(gateway,'execute',side_effect=self.gateway_pages),server(gateway.Handler) as url:
            client=Db2MCP(url,'fixture-token');client.initialize()
            result=discover_catalog(client,'tables',max_pages=1)
        self.assertEqual(result['coverage'],'PARTIAL');self.assertEqual(result['reason'],'page_budget')
        self.assertEqual(result['next_cursor'],{'after_schema':'FIRST','after_table':'TABLE'})

    def test_repeated_cursor_and_missing_continuation_never_claim_complete(self):
        repeated={'rows':[{'CREATOR':'A'}],'has_more':True,'next_cursor':{'after_schema':'A'}}
        client=SimpleNamespace(timeout=20,list_schemas=lambda **kwargs:repeated)
        result=discover_catalog(client,'schemas')
        self.assertEqual(result['coverage'],'PARTIAL');self.assertEqual(result['reason'],'repeated_cursor')
        self.assertEqual(result['rows'],[{'CREATOR':'A'}])
        client.list_schemas=lambda **kwargs:{'rows':[]}
        self.assertEqual(discover_catalog(client,'schemas')['reason'],'continuation_unavailable')

    def test_second_page_failure_preserves_evidence_and_retry_cursor(self):
        pages=iter([{'rows':[{'CREATOR':'A'}],'has_more':True,'next_cursor':{'after_schema':'A'}}])
        def read(**kwargs):
            if kwargs:raise ValidationError('Unreachable')
            return next(pages)
        result=discover_catalog(SimpleNamespace(timeout=20,list_schemas=read),'schemas')
        self.assertEqual(result['rows'],[{'CREATOR':'A'}]);self.assertEqual(result['reason'],'page_read_failed')
        self.assertEqual(result['next_cursor'],{'after_schema':'A'})

    def test_byte_budget_and_malformed_rows_remain_partial(self):
        client=SimpleNamespace(timeout=20,list_schemas=lambda **kwargs:{'rows':[{'CREATOR':'A','extra':'x'*2048}],'has_more':False})
        result=discover_catalog(client,'schemas',max_bytes=1024)
        self.assertEqual(result['reason'],'byte_budget');self.assertEqual(result['rows'],[])
        client.list_schemas=lambda **kwargs:{'rows':['not a record'],'has_more':False}
        self.assertEqual(discover_catalog(client,'schemas')['reason'],'invalid_page')


class GatewayTests(unittest.TestCase):
    def test_odbc_extra_row_drives_explicit_schema_continuation(self):
        class Cursor:
            description=[('CREATOR',)]
            def execute(self,sql,*params):self.sql=sql;self.params=params
            def fetchmany(self,count):self.count=count;return [('A',),('B',),('C',)][:count]
        cursor=Cursor()
        class Connection:
            def __enter__(self):return self
            def __exit__(self,*args):pass
            def close(self):self.closed=True
            def cursor(self):return cursor
        with patch.dict('sys.modules',{'pyodbc':SimpleNamespace(connect=lambda *a,**k:Connection())}),patch.dict(os.environ,{'WB_DB2_ODBC_CONNECTION':'fixture-only'}):
            page=gateway.execute('db2_list_schemas',{'limit':2,'after_schema':'0'})
        self.assertEqual(cursor.count,3);self.assertEqual(cursor.params,('0',))
        self.assertEqual(page['rows'],[{'CREATOR':'A'},{'CREATOR':'B'}])
        self.assertTrue(page['has_more']);self.assertEqual(page['next_cursor'],{'after_schema':'B'})

    def test_configured_small_cap_also_bounds_catalog_lookahead(self):
        from unittest.mock import Mock
        cursor=Mock();cursor.description=[('CREATOR',)];cursor.fetchmany.return_value=[('A',)]
        connection=Mock();connection.cursor.return_value=cursor
        with patch.object(gateway,'connect',return_value=connection),patch.object(gateway,'configured_row_limit',return_value=1),patch.dict('sys.modules',{'pyodbc':SimpleNamespace()}):
            page=gateway.execute('db2_list_schemas',{'limit':1})
        self.assertIn('FETCH FIRST 1 ROWS ONLY',cursor.execute.call_args.args[0])
        cursor.fetchmany.assert_called_once_with(1)
        self.assertTrue(page['has_more']);self.assertEqual(page['next_cursor'],{'after_schema':'A'})
        connection.close.assert_called_once()

    def test_catalog_cursor_is_parameterized_and_mutation_or_unknown_arguments_rejected(self):
        cursor="X' OR 1=1 --"
        sql,params=catalog_sql('db2_list_tables',{'after_schema':cursor,'after_table':'T'})
        self.assertNotIn(cursor,sql);self.assertIn(cursor,params);self.assertIn('FETCH FIRST 101',sql)
        with self.assertRaises(ValidationError):catalog_sql('db2_list_tables',{'sql':'DELETE FROM X'})
        with self.assertRaises(ValidationError):catalog_sql('execute_sql',{})
        sql,params=catalog_sql('db2_describe_table',{'schema':'A','table':'T','after_column':99})
        self.assertIn('COLNO > ?',sql);self.assertEqual(params,['A','T',99])

    def test_gateway_rejects_unsupported_protocol_origin_and_get_stream(self):
        with patch.dict(os.environ,{'WB_DB2_MCP_TOKEN':'fixture-token'},clear=True),server(gateway.Handler) as url:
            data=json.dumps({'jsonrpc':'2.0','id':3,'method':'tools/list','params':{}}).encode()
            for extra in ({'MCP-Protocol-Version':'2026-07-28'},{'Origin':'https://untrusted.invalid'}):
                request=Request(url,data=data,headers={'Authorization':'Bearer fixture-token','Content-Type':'application/json',**extra})
                with self.assertRaises(HTTPError) as error:urlopen(request)
                self.assertEqual(error.exception.code,400)
            with self.assertRaises(HTTPError) as error:urlopen(url)
            self.assertEqual(error.exception.code,405)

    def test_gateway_older_protocol_returns_text_content_not_new_structured_field(self):
        with patch.dict(os.environ,{'WB_DB2_MCP_TOKEN':'fixture-token'},clear=True),patch.object(gateway,'execute',return_value={'rows':[],'has_more':False}),server(gateway.Handler) as url:
            data=json.dumps({'jsonrpc':'2.0','id':'legacy','method':'tools/call','params':{'name':'db2_list_schemas','arguments':{}}}).encode()
            request=Request(url,data=data,headers={'Authorization':'Bearer fixture-token','MCP-Protocol-Version':'2025-03-26','Content-Type':'application/json'})
            with urlopen(request) as response:body=json.load(response)
        self.assertEqual(body['id'],'legacy');self.assertNotIn('structuredContent',body['result'])
        self.assertEqual(json.loads(body['result']['content'][0]['text'])['rows'],[])


if __name__=='__main__':unittest.main()
