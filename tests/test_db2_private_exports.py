"""Fictional private records stay local; actual MCP responses contain metadata only."""
import asyncio
import json
from pathlib import Path
import random
import secrets
import sys
import tempfile
import types
import unittest
from unittest.mock import patch

from fastmcp import Client
from tools import db2_mcp_server as gateway
from workbench.coordinator import Coordinator
from workbench.database import create_application_database, schema_candidate, sqlite_rows, validate_snapshot
from workbench.domain import ValidationError, encode, sha
from workbench.retrieval import inspect_response, private_snapshot_path
from test_database import receipt
from test_database_retrieval import snapshot_need
from test_source import COBOL
from test_workflow import MANIFEST


class Cursor:
    description=[('ID',),('VALUE',)]
    def __init__(self,rows):self.rows=list(rows);self.closed=False;self.sql=[]
    def execute(self,sql,*args):self.sql.append(sql)
    def fetchmany(self,count):rows=self.rows[:count];self.rows=self.rows[count:];return rows
    def close(self):self.closed=True


class Connection:
    def __init__(self,rows):self.reader=Cursor(rows);self.closed=False
    def cursor(self):return self.reader
    def close(self):self.closed=True


class PrivateExportTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name).resolve();self.c=Coordinator(self.root);self.addCleanup(self.c.close)
        self.addCleanup(lambda:[gateway.ROW_READS.close(token) for token in list(gateway.ROW_READS.sessions)])

    def request(self,index=0):
        manifest=MANIFEST.replace('process-a','private-'+str(index))
        doc=self.c.prepare_process(manifest,{'JOBA.jcl':'//JOBA JOB\n//S010 EXEC PGM=ELIGIBLE\n','ELIGIBLE.cbl':COBOL})
        pid=doc['id'];self.c.start(pid);self.c.advance(pid)
        request=self.c.request_retrieval(pid,[snapshot_need(receipt([],'before'))])['retrieval']
        return request,{'process_id':pid,'request_id':request['request_id'],'need_id':request['needs'][0]['need_id']}

    def call(self,arguments,rows,limit=10000):
        db=Connection(rows);driver=types.SimpleNamespace(connect=lambda *args,**kwargs:db)
        with patch.dict(sys.modules,{'pyodbc':driver}),patch.object(gateway,'connection_string',return_value='fictional-local-read'), \
             patch.object(gateway,'configured_row_limit',return_value=limit):
            result=gateway.export_snapshot_to_inbox(self.root,**arguments)
        self.assertTrue(db.closed);self.assertTrue(db.reader.closed)
        self.assertTrue(all(sql.startswith('SELECT ') and 'WITH UR' in sql for sql in db.reader.sql))
        return result

    def test_twenty_randomized_private_exports_keep_values_off_mcp_and_match_actual_sqlite(self):
        rng=random.Random(secrets.randbits(63));states=set()
        async def run():
            for index in range(20):
                request,arguments=self.request(index)
                # Deliberately invalid-for-real-use IDs and fictional values;
                # they are markers for egress, not real customer records.
                rows=[('000'+str(rng.randrange(10**5)).zfill(5),'private-fixture-'+str(index)+'-'+str(rng.randrange(10**10)))]
                db=Connection(rows);driver=types.SimpleNamespace(connect=lambda *args,**kwargs:db)
                with patch.dict(sys.modules,{'pyodbc':driver}),patch.object(gateway,'connection_string',return_value='fictional-local-read'), \
                     patch.object(gateway,'configured_row_limit',return_value=10000):
                    async with Client(gateway.create_server(workspace=self.root)) as client:
                        exported=(await client.call_tool('db2_export_snapshot_to_inbox',arguments)).data
                output=json.dumps(exported);self.assertNotIn(rows[0][0],output);self.assertNotIn(rows[0][1],output)
                self.assertNotIn('rows',exported);self.assertEqual(exported['row_count'],1)
                path=self.root/request['return_folder']/'files'/private_snapshot_path(arguments['need_id'])
                self.assertEqual(Path(exported['private_file']),path);raw=path.read_bytes();states.add(sha(raw))
                snapshot=validate_snapshot(raw.decode());expected=[dict(zip(('ID','VALUE'),rows[0]))]
                self.assertEqual(snapshot['rows'],expected);self.assertTrue(snapshot['scope']['complete'])
                self.assertEqual(snapshot['consistency'],{'status':'unverified','evidence':[]})
                target=self.root/'.implementation/tmp'/('comparison-'+str(index)+'.sqlite');target.parent.mkdir(parents=True,exist_ok=True)
                schema=schema_candidate('CREATE TABLE APP.SALE (ID CHAR(8) NOT NULL PRIMARY KEY, VALUE VARCHAR(40));')
                built=create_application_database(target,[schema],{'APP.SALE':snapshot['rows']})
                self.assertEqual(sqlite_rows(target,built['sha256'],'APP.SALE')['rows'],expected)
                self.assertTrue(exported['response_ready']);self.assertEqual(exported['receipt_status'],'SAVED_PRIVATE_RESPONSE')
                self.assertNotIn('provenance',exported['item'])
                frozen=self.c.artifact(arguments['process_id'],self.c.ledger.get(arguments['process_id'])['retrieval_request']['artifact']).read_bytes()
                from workbench.domain import decode
                self.assertTrue(inspect_response(self.root,decode(frozen))['complete'])
        asyncio.run(run());self.assertEqual(len(states),20)

    def test_default_sdk_catalog_denies_raw_rows_samples_and_content_search(self):
        async def run():
            with patch.object(gateway.ROW_READS,'read',side_effect=AssertionError('raw MCP forbidden')) as reader:
                async with Client(gateway.create_server(workspace=self.root)) as client:
                    names={tool.name for tool in await client.list_tools()}
                    self.assertEqual(names,{'db2_list_schemas','db2_list_tables','db2_describe_table','db2_export_snapshot_to_inbox'})
                    for name in ('db2_read_table_rows','db2_sample_rows','db2_search_start','db2_search_results'):
                        result=await client.call_tool(name,{},raise_on_error=False)
                        self.assertTrue(result.is_error)
                reader.assert_not_called()
        asyncio.run(run())

    def test_metadata_response_suppresses_remarks_defaults_and_unknown_payloads(self):
        marker='private-customer-value@example.invalid'
        async def run():
            value={'rows':[{'NAME':'ID','COLTYPE':'CHAR','LENGTH':8,'SCALE':0,'NULLS':'N','COLNO':0,
                            'REMARKS':marker,'DEFAULT':marker,'DEFAULTVALUE':marker,'CUSTOMER_DATA':marker}],
                   'has_more':False,'next_cursor':None,'unrelated_private':marker,'coverage':{'private':marker},'read_only':True}
            with patch.object(gateway,'execute',return_value=value):
                async with Client(gateway.create_server(workspace=self.root)) as client:
                    result=(await client.call_tool('db2_describe_table',{'schema':'APP','table':'SALE'})).data
            self.assertNotIn(marker,json.dumps(result));self.assertEqual(result['rows'][0]['NAME'],'ID')
            self.assertEqual(set(result['rows'][0]),{'NAME','COLTYPE','LENGTH','SCALE','NULLS','COLNO'})
        asyncio.run(run())

    def test_unauthorized_stale_or_path_injected_requests_never_query_or_write(self):
        request,arguments=self.request()
        invalid=[{**arguments,'process_id':'../outside'},{**arguments,'request_id':'0'*64},
                 {**arguments,'need_id':'N'+'0'*16},{**arguments,'request_id':arguments['request_id']+'/escape'}]
        with patch.object(gateway.ROW_READS,'read',side_effect=AssertionError('no query')) as reader:
            for value in invalid:
                with self.subTest(value=value),self.assertRaises((ValidationError,FileNotFoundError)):
                    gateway.export_snapshot_to_inbox(self.root,**value)
            doc=self.c.ledger.get(arguments['process_id']);doc['retrieval_request']['status']='CONSUMED';self.c.ledger.save(doc)
            with self.assertRaises(ValidationError):gateway.export_snapshot_to_inbox(self.root,**arguments)
            reader.assert_not_called()
        self.assertFalse(list((self.root/request['return_folder']/'files').rglob('*.private-rows.json')))

    def test_retry_preserves_private_bytes_and_does_not_repeat_database_read(self):
        request,arguments=self.request();result=self.call(arguments,[('00000001','fictional-private')])
        path=Path(result['private_file']);original=path.read_bytes()
        with patch.object(gateway.ROW_READS,'read',side_effect=AssertionError('retry must not reread')):
            self.assertEqual(gateway.export_snapshot_to_inbox(self.root,**arguments),result)
        self.assertEqual(path.read_bytes(),original)

    def test_private_lookup_identity_and_provenance_are_bound_locally_without_model_values(self):
        from workbench.domain import decode
        marker='SSN123456789'
        doc=self.c.prepare_process(MANIFEST,{'JOBA.jcl':'//JOBA JOB\n//S010 EXEC PGM=ELIGIBLE\n','ELIGIBLE.cbl':COBOL})
        self.c.start(doc['id']);self.c.advance(doc['id'])
        need={**snapshot_need(receipt([],'before')),'name':'APP.'+marker}
        request=self.c.request_retrieval(doc['id'],[need])['retrieval']
        args={'process_id':doc['id'],'request_id':request['request_id'],'need_id':request['needs'][0]['need_id']}
        exported=self.call(args,[('00000001','fictional-private')])
        self.assertNotIn(marker,json.dumps(exported));self.assertTrue(exported['response_ready'])
        response=Path(exported['response_file']).read_bytes();self.assertIn(marker,response.decode())
        authoritative=decode(self.c.artifact(doc['id'],self.c.ledger.get(doc['id'])['retrieval_request']['artifact']).read_bytes())
        self.assertTrue(inspect_response(self.root,authoritative)['complete'])
        before=response
        with patch.object(gateway.ROW_READS,'read',side_effect=AssertionError('retry must not reread')):
            repeated=gateway.export_snapshot_to_inbox(self.root,**args)
        self.assertEqual(repeated,exported);self.assertEqual(Path(exported['response_file']).read_bytes(),before)

    def test_snapshot_response_is_finalized_only_after_all_exact_needs_and_mixed_requests_stay_named(self):
        from workbench.domain import decode
        doc=self.c.prepare_process(MANIFEST,{'JOBA.jcl':'//JOBA JOB\n//S010 EXEC PGM=ELIGIBLE\n','ELIGIBLE.cbl':COBOL})
        self.c.start(doc['id']);self.c.advance(doc['id'])
        needs=[snapshot_need(receipt([],'before')),snapshot_need(receipt([],'after'))]
        request=self.c.request_retrieval(doc['id'],needs)['retrieval']
        args={'process_id':doc['id'],'request_id':request['request_id']}
        first=self.call({**args,'need_id':request['needs'][0]['need_id']},[('00000001','fictional-before')])
        self.assertFalse(first['response_ready']);self.assertFalse(Path(first['response_file']).exists())
        second=self.call({**args,'need_id':request['needs'][1]['need_id']},[('00000002','fictional-after')])
        self.assertTrue(second['response_ready'])
        authoritative=decode(self.c.artifact(doc['id'],self.c.ledger.get(doc['id'])['retrieval_request']['artifact']).read_bytes())
        accepted=inspect_response(self.root,authoritative)
        self.assertTrue(accepted['complete']);self.assertEqual(len(accepted['entries']),2)
        # A separate synthetic process has mixed needs. The tool must not invent
        # a source receipt or claim its model projection is valid provenance.
        pid='mixed';manifest=MANIFEST.replace('process-a',pid)
        self.c.prepare_process(manifest,{'JOBA.jcl':'//JOBA JOB\n//S010 EXEC PGM=ELIGIBLE\n','ELIGIBLE.cbl':COBOL})
        self.c.start(pid);self.c.advance(pid)
        mixed=self.c.request_retrieval(pid,[needs[0],{'kind':'program','name':'MORE','reason':'Fictional missing dependency'}])['retrieval']
        exported=self.call({'process_id':pid,'request_id':mixed['request_id'],'need_id':mixed['needs'][0]['need_id']},[('00000003','fictional-mixed')])
        self.assertFalse(exported['response_ready']);self.assertEqual(exported['receipt_status'],'NEEDS_LOCAL_PROTECTED_RECEIPT_BINDING')
        self.assertFalse(Path(exported['response_file']).exists());self.assertNotIn('provenance',exported['item'])

    def test_partial_rows_remain_unverified_and_arbitrary_tool_fields_are_refused(self):
        request,arguments=self.request();result=self.call(arguments,[('00000001','first'),('00000002','second')],limit=1)
        self.assertFalse(result['complete']);self.assertEqual(result['row_count'],1)
        self.assertEqual(result['consistency'],'unverified');self.assertNotIn('second',json.dumps(result))
        async def run():
            async with Client(gateway.create_server(workspace=self.root)) as client:
                for key,value in (('path','outside.json'),('sql','SELECT * FROM APP.SALE'),('rows',[{'ID':'private'}])):
                    result=await client.call_tool('db2_export_snapshot_to_inbox',{**arguments,key:value},raise_on_error=False)
                    self.assertTrue(result.is_error)
        asyncio.run(run())

    def test_driver_error_values_are_not_returned_and_no_partial_file_is_published(self):
        request,arguments=self.request();marker='123-45-6789 private@example.invalid'
        async def run():
            with patch.object(gateway.ROW_READS,'read',side_effect=RuntimeError(marker)):
                async with Client(gateway.create_server(workspace=self.root)) as client:
                    result=await client.call_tool('db2_export_snapshot_to_inbox',arguments,raise_on_error=False)
                    self.assertTrue(result.is_error);self.assertNotIn(marker,str(result))
        asyncio.run(run())
        self.assertFalse(list((self.root/request['return_folder']/'files').rglob('*.private-rows.json')))


if __name__=='__main__':unittest.main()
