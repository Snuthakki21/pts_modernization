import json
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from workbench.connectors import Db2MCP, ZoweReader, catalog_sql
from workbench.provider import StructuredProvider
from workbench.domain import ValidationError


class FixtureHandler(BaseHTTPRequestHandler):
    calls=0
    def log_message(self,*args):pass
    def do_POST(self):
        self.__class__.calls+=1
        body=json.loads(self.rfile.read(int(self.headers['Content-Length'])))
        if body.get('method')=='notifications/initialized':
            self.send_response(202);self.end_headers();return
        if 'method' in body:
            result={'tools':[{'name':n} for n in ['db2_list_schemas','db2_list_tables','db2_describe_table','db2_sample_rows']]} if body['method']=='tools/list' else {'structuredContent':{'rows':[{'CREATOR':'DEMO','NAME':'CUSTOMERS'}]}} if body['method']=='tools/call' else {'protocolVersion':'2025-03-26','capabilities':{'tools':{}}}
            response={'jsonrpc':'2.0','id':body['id'],'result':result}
        else:response={'choices':[{'message':{'content':json.dumps({'summary':'Source-based example analysis','assumptions':[],'questions':['Is the stated rule correct?']})}}],'usage':{'prompt_tokens':10,'completion_tokens':12}}
        data=json.dumps(response).encode();self.send_response(200);self.send_header('Content-Type','application/json');self.send_header('Content-Length',str(len(data)));self.end_headers();self.wfile.write(data)


class IntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server=ThreadingHTTPServer(('127.0.0.1',0),FixtureHandler);cls.thread=threading.Thread(target=cls.server.serve_forever,daemon=True);cls.thread.start();cls.url=f'http://127.0.0.1:{cls.server.server_port}'
    @classmethod
    def tearDownClass(cls):cls.server.shutdown();cls.server.server_close()

    def test_mcp_discovery_needs_no_prelisted_table_names(self):
        m=Db2MCP(self.url,'example-token');m.initialize()
        self.assertEqual(m.list_tables()['rows'][0]['NAME'],'CUSTOMERS')
        with self.assertRaises(ValidationError):m.call('execute_sql',{'sql':'DELETE FROM X'})

    def test_zowe_rejects_injected_dataset_and_write_command(self):
        z=ZoweReader('default')
        with self.assertRaises(ValidationError):z.read_member('--password secret')
        with self.assertRaises(ValidationError):z.operation('upload', 'TEST')

    def test_provider_requires_egress_permission_and_records_actual_usage(self):
        p=StructuredProvider(self.url,'test-model','example-token',allow_egress=False)
        before=FixtureHandler.calls
        with self.assertRaises(ValidationError):p.analyze('SOURCE','review')
        self.assertEqual(FixtureHandler.calls,before)
        p.allow_egress=True
        got=p.analyze('SOURCE','review');again=p.analyze('SOURCE','review')
        self.assertEqual(got['usage']['prompt_tokens'],10)
        self.assertTrue(again['cache_hit'])
        self.assertEqual(FixtureHandler.calls,before+1)

    def test_catalog_queries_are_read_only_and_bound_identifiers(self):
        sql,params=catalog_sql('db2_list_tables',{})
        self.assertIn('SYSIBM.SYSTABLES',sql);self.assertTrue(sql.startswith('SELECT'))
        with self.assertRaises(ValidationError):catalog_sql('db2_sample_rows',{'schema':'X;DROP TABLE Y','table':'Z'})
        with self.assertRaises(ValidationError):catalog_sql('execute_sql',{})


if __name__=='__main__':unittest.main()
