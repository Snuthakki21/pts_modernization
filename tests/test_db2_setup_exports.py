import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest.mock import patch

from workbench.connectors import catalog_sql, export_table_rows
from workbench.db2_setup import initialize_db2, load_connection, PLACEHOLDER
from workbench.domain import ValidationError
from workbench.zowe_setup import import_project_config

GATEWAY_PATH=Path(__file__).resolve().parents[1]/'tools/db2_mcp_server.py'
spec=importlib.util.spec_from_file_location('db2_export_fixture_gateway',GATEWAY_PATH)
gateway=importlib.util.module_from_spec(spec);spec.loader.exec_module(gateway)


class FakeCursor:
    description=[('ID',)]
    def __init__(self,rows):self.rows=list(rows);self.executed=[];self.closed=False
    def execute(self,sql,*args):self.executed.append((sql,args))
    def fetchmany(self,count):rows=self.rows[:count];self.rows=self.rows[count:];return rows
    def close(self):self.closed=True


class FakeConnection:
    def __init__(self,rows):self.reader=FakeCursor(rows);self.closed=False
    def cursor(self):return self.reader
    def close(self):self.closed=True


class DirectReadClient:
    timeout=20
    def __init__(self):self.calls=[]
    def read_table_rows(self,schema,table,limit=100,max_rows=1000,cursor=None,cancel=False):
        args={'schema':schema,'table':table,'limit':limit,'max_rows':max_rows}
        if cursor:args['cursor']=cursor
        if cancel:args['cancel']=True
        self.calls.append(args);return gateway.execute('db2_read_table_rows',args)


class Db2SetupExportTests(unittest.TestCase):
    def tearDown(self):
        for token in list(gateway.ROW_READS.sessions):gateway.ROW_READS.close(token)

    def test_template_records_true_ssl_and_real_certificate_is_required(self):
        with tempfile.TemporaryDirectory() as directory:
            result=initialize_db2(directory,server_name='DEV',location='DDF',database='ACTUALDB',host='db2.example.invalid',port=50001)
            config=Path(result['config_file']);data=json.loads(config.read_text())
            self.assertTrue(data['ssl']);self.assertEqual(data['max_rows'],500000)
            self.assertNotIn('password',data);self.assertEqual(Path(result['certificate']).read_bytes(),PLACEHOLDER)
            with self.assertRaisesRegex(ValidationError,'placeholder'):
                load_connection(config,{'WB_DB2_USER':'fictional','WB_DB2_PASSWORD':'fictional-secret'})
            self.assertEqual(result['connectivity'],'UNVERIFIED')

    def test_private_credentials_are_used_only_in_memory_and_escaped_for_odbc(self):
        with tempfile.TemporaryDirectory() as directory:
            result=initialize_db2(directory,database='ACTUALDB',host='db2.example.invalid',port=50001)
            config=Path(result['config_file']);before=config.read_bytes()
            with patch('workbench.db2_setup.ssl.create_default_context') as ssl_check:
                connection=load_connection(config,{'WB_DB2_USER':'fictional','WB_DB2_PASSWORD':'secret;PWD=bad}'})
            self.assertIn('SECURITY={SSL}',connection);self.assertIn('PWD={secret;PWD=bad}}}',connection)
            self.assertIn('SSLClientHostnameValidation={Basic}',connection)
            self.assertEqual(config.read_bytes(),before);ssl_check.assert_called_once()

    def test_ssl_off_and_excessive_row_limit_are_refused(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(ValidationError):initialize_db2(directory,max_rows=500001)
            result=initialize_db2(directory)
            path=Path(result['config_file']);config=json.loads(path.read_text());config['ssl']=False;path.write_text(json.dumps(config))
            with self.assertRaises(ValidationError):initialize_db2(directory)

    def test_exact_zowe_import_preserves_selected_bytes_and_existing_files(self):
        with tempfile.TemporaryDirectory() as directory, tempfile.TemporaryDirectory() as input_directory:
            source=Path(input_directory)/'selected-config.json';schema=Path(input_directory)/'selected-schema.json'
            content=b'{ "profiles": { "approved": { "type":"base", "secure":["user","password"] } } }\n'
            source.write_bytes(content);schema.write_bytes(b'{"title":"fictional schema"}\n')
            result=import_project_config(directory,source,schema)
            self.assertEqual((Path(directory)/'zowe.config.json').read_bytes(),content)
            self.assertTrue(result['content_preserved'])
            source.write_bytes(b'{"profiles":{}}')
            with self.assertRaises(ValidationError):import_project_config(directory,source,schema)
            self.assertEqual((Path(directory)/'zowe.config.json').read_bytes(),content)

    def test_typed_export_sql_accepts_500000_without_expanding_small_sample_api(self):
        sql,params=catalog_sql('db2_read_table_rows',{'schema':'ANYSCHEMA','table':'ANYTABLE','max_rows':500000,'limit':1000})
        self.assertEqual(params,[]);self.assertIn('FETCH FIRST 500000 ROWS ONLY WITH UR',sql)
        for args in ({'schema':'A','table':'T','max_rows':500001},{'schema':'A','table':'T','sql':'DELETE FROM T'}):
            with self.assertRaises(ValidationError):catalog_sql('db2_read_table_rows',args)
        with self.assertRaises(ValidationError):catalog_sql('db2_sample_rows',{'schema':'A','table':'T','limit':101})

    def test_paginated_export_uses_one_read_query_and_streams_file(self):
        db=FakeConnection([(1,),(2,),(3,)])
        driver=types.SimpleNamespace(connect=lambda *args,**kwargs:db)
        with tempfile.TemporaryDirectory() as directory, patch.dict(sys.modules,{'pyodbc':driver}),patch.dict('os.environ',{'WB_DB2_ODBC_CONNECTION':'private'},clear=True):
            result=export_table_rows(DirectReadClient(),'ANYSCHEMA','ANYTABLE',Path(directory)/'rows.ndjson',max_rows=5,page_size=2)
            self.assertEqual(result['status'],'READ_COMPLETED');self.assertEqual(result['rows'],3)
            self.assertEqual([json.loads(line)['ID'] for line in Path(result['output']).read_text().splitlines()],[1,2,3])
            self.assertEqual(len(db.reader.executed),1);self.assertTrue(db.closed);self.assertTrue(db.reader.closed)
            self.assertFalse(result['snapshot_consistent'])

    def test_row_budget_and_byte_budget_are_partial_and_close_cursor(self):
        for maximum,byte_budget,expected in ((3,1024,'row_budget'),(10,1024,'byte_budget')):
            rows=[(1,),(2,),(3,),(4,)] if expected=='row_budget' else [('x'*900,),('y'*900,),('z'*900,)]
            db=FakeConnection(rows);driver=types.SimpleNamespace(connect=lambda *args,**kwargs:db)
            with tempfile.TemporaryDirectory() as directory, patch.dict(sys.modules,{'pyodbc':driver}),patch.dict('os.environ',{'WB_DB2_ODBC_CONNECTION':'private'},clear=True):
                result=export_table_rows(DirectReadClient(),'A','T',Path(directory)/'rows.ndjson',max_rows=maximum,page_size=2,max_bytes=byte_budget)
            self.assertEqual(result['status'],'PARTIAL');self.assertEqual(result['reason'],expected)
            self.assertTrue(db.closed);self.assertFalse(gateway.ROW_READS.sessions)

    def test_cursor_cannot_switch_table_or_outlive_expiration(self):
        db=FakeConnection([(1,),(2,),(3,)]);driver=types.SimpleNamespace(connect=lambda *args,**kwargs:db)
        with patch.dict(sys.modules,{'pyodbc':driver}),patch.dict('os.environ',{'WB_DB2_ODBC_CONNECTION':'private'},clear=True):
            args={'schema':'A','table':'T','max_rows':10,'limit':1};page=gateway.execute('db2_read_table_rows',args);token=page['next_cursor']
            with self.assertRaises(ValidationError):gateway.execute('db2_read_table_rows',{**args,'table':'OTHER','cursor':token})
            gateway.ROW_READS.close(token)
            with self.assertRaises(ValidationError):gateway.execute('db2_read_table_rows',{**args,'cursor':token})
        self.assertTrue(db.closed)

    def test_configured_row_policy_cannot_be_exceeded_by_gateway_arguments(self):
        db=FakeConnection([(1,)])
        driver=types.SimpleNamespace(connect=lambda *args,**kwargs:db)
        with tempfile.TemporaryDirectory() as directory:
            result=initialize_db2(directory,max_rows=10)
            with patch.dict(sys.modules,{'pyodbc':driver}),patch.dict('os.environ',{'WB_DB2_CONFIG':result['config_file']},clear=True):
                with self.assertRaises(ValidationError):gateway.execute('db2_read_table_rows',{'schema':'A','table':'T','max_rows':11})
            self.assertFalse(db.reader.executed)

    def test_omitted_cap_preserves_saved_local_row_policy(self):
        with tempfile.TemporaryDirectory() as directory:
            result=initialize_db2(directory,max_rows=10)
            initialize_db2(directory)
            self.assertEqual(json.loads(Path(result['config_file']).read_text())['max_rows'],10)

    def test_nonsecret_config_refuses_password_aliases_and_changed_env_mapping(self):
        with tempfile.TemporaryDirectory() as directory:
            result=initialize_db2(directory)
            path=Path(result['config_file']);clean=json.loads(path.read_text())
            for mutated in ({**clean,'PWD':'FICTIONAL_PRIVATE_SENTINEL'},
                            {**clean,'credential_environment':{'user':'WB_DB2_USER','password':'FICTIONAL_PRIVATE_SENTINEL'}}):
                original=json.dumps(mutated);path.write_text(original)
                with self.assertRaises(ValidationError) as failure:initialize_db2(directory)
                self.assertNotIn('FICTIONAL_PRIVATE_SENTINEL',str(failure.exception))
                self.assertEqual(path.read_text(),original)

    def test_local_row_cap_overrides_endpoint_end_of_cursor_claim(self):
        class EndClaimClient:
            timeout=20
            def read_table_rows(self,*args,**kwargs):
                return {'rows':[{'ID':1},{'ID':2}],'has_more':False,'reason':'end_of_cursor'}
        with tempfile.TemporaryDirectory() as directory:
            result=export_table_rows(EndClaimClient(),'A','T',Path(directory)/'rows.ndjson',max_rows=2,page_size=2)
        self.assertEqual(result['status'],'PARTIAL');self.assertEqual(result['coverage'],'PARTIAL')
        self.assertEqual(result['reason'],'row_budget')


if __name__=='__main__':unittest.main()
