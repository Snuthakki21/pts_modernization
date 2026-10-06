import io
import subprocess
import unittest
from unittest.mock import Mock, patch

from workbench.connectors import ZoweReader, ReadOnlyLineageResolver, bounded_command, _zowe_content
from workbench.domain import ValidationError


class FakeZowe:
    profile = 'fictional'
    def __init__(self, datasets, members=None, content=''):
        self.datasets = datasets; self.members = members or {}; self.content = content; self.calls = []
    def list_datasets(self, hint, **kwargs):
        self.calls.append(('list', hint, kwargs)); return {'success': True, 'data': {'apiResponse': {'items': self.datasets}}}
    def list_members(self, dataset, **kwargs):
        self.calls.append(('members', dataset, kwargs)); return {'success': True, 'data': {'apiResponse': {'items': self.members.get(dataset, [])}}}
    def read_member(self, member): self.calls.append(('read', member)); return {'success': True, 'data': self.content}
    def read_dataset(self, dataset): self.calls.append(('dataset', dataset)); return {'success': True, 'data': self.content}


class FakeDb2:
    timeout = 20
    def __init__(self, pages=None, columns=None): self.pages = list(pages or []); self.columns = columns or {'rows':[{'NAME':'ID','COLNO':0}], 'has_more':False}; self.calls=[]
    def list_tables(self, **cursor): self.calls.append(('tables', cursor)); return self.pages.pop(0)
    def describe(self, schema, table, after_column=-1): self.calls.append(('describe',schema,table,after_column)); return self.columns


class LineageConnectorTests(unittest.TestCase):
    def test_exact_member_match_returns_source_and_read_provenance(self):
        zowe = FakeZowe([{'dsname':'APP.COBOL','dsorg':'PO'}], {'APP.COBOL':[{'member':'HELLO'}]}, '       PROGRAM-ID. HELLO.\n')
        result = ReadOnlyLineageResolver(zowe=zowe, dataset_hints=['APP.*']).resolve({'kind':'program','name':'HELLO','source':'ROOT.cbl'})
        self.assertEqual(result['status'], 'RESOLVED')
        self.assertIn('PROGRAM-ID. HELLO', result['content'])
        self.assertEqual(result['provenance']['dataset_member'], 'APP.COBOL(HELLO)')
        self.assertEqual(result['provenance']['operation'], 'read_member')
        self.assertTrue(result['provenance']['read_only'])
        self.assertEqual(zowe.calls[1][2]['pattern'], 'HELLO')

    def test_duplicate_library_members_never_choose_first_source(self):
        zowe = FakeZowe([{'dsname':'APP.COBOL','dsorg':'PO'}, {'dsname':'APP.OLD','dsorg':'PO'}],
                        {'APP.COBOL':[{'member':'HELLO'}], 'APP.OLD':[{'member':'HELLO'}]}, 'source')
        result = ReadOnlyLineageResolver(zowe=zowe,dataset_hints=['APP.*']).resolve({'kind':'copybook','name':'HELLO'})
        self.assertEqual(result['status'], 'AMBIGUOUS'); self.assertEqual(len(result['candidates']), 2)
        self.assertFalse(any(call[0]=='read' for call in zowe.calls))

    def test_dataset_budget_does_not_claim_unique_or_complete_discovery(self):
        zowe = FakeZowe([{'dsname':'APP.COBOL','dsorg':'PO'}, {'dsname':'APP.OLD','dsorg':'PO'}], {'APP.COBOL':[{'member':'HELLO'}]})
        result = ReadOnlyLineageResolver(zowe=zowe,dataset_hints=['APP.*'],max_datasets=1).resolve({'kind':'program','name':'HELLO'})
        self.assertEqual(result['status'], 'UNRESOLVED'); self.assertEqual(result['coverage'], 'PARTIAL')
        self.assertFalse(any(call[0]=='read' for call in zowe.calls))

    def test_db2_qualified_reference_describes_exact_table_without_sampling(self):
        client = FakeDb2()
        result = ReadOnlyLineageResolver(db2=client).resolve({'kind':'db2_table','name':'APP.CUSTOMER'})
        self.assertEqual(result['status'], 'RESOLVED'); self.assertEqual(client.calls, [('describe','APP','CUSTOMER',-1)])
        self.assertEqual(result['provenance']['operation'], 'db2_describe_table')
        self.assertEqual(result['metadata']['columns'][0]['NAME'], 'ID')

    def test_db2_unqualified_duplicate_and_partial_search_remain_unresolved(self):
        client = FakeDb2([{'rows':[{'CREATOR':'A','NAME':'CUSTOMER'}, {'CREATOR':'B','NAME':'CUSTOMER'}], 'has_more':False}])
        result = ReadOnlyLineageResolver(db2=client).resolve({'kind':'db2_table','name':'CUSTOMER'})
        self.assertEqual(result['status'], 'AMBIGUOUS'); self.assertEqual(len(client.calls), 1)
        client = FakeDb2([{'rows':[{'CREATOR':'A','NAME':'CUSTOMER'}], 'has_more':True, 'next_cursor':{'after_schema':'A','after_table':'CUSTOMER'}}])
        result = ReadOnlyLineageResolver(db2=client,max_catalog_pages=1).resolve({'kind':'db2_table','name':'CUSTOMER'})
        self.assertEqual(result['status'], 'UNRESOLVED'); self.assertEqual(result['coverage'], 'PARTIAL')

    def test_explicit_sequential_read_is_opt_in_and_typed(self):
        zowe = FakeZowe([{'dsname':'APP.CONTROL','dsorg':'PS'}],content='control data')
        result = ReadOnlyLineageResolver(zowe=zowe).resolve({'kind':'dataset','name':'APP.CONTROL'})
        self.assertNotIn('content', result); self.assertFalse(any(call[0]=='dataset' for call in zowe.calls))
        result = ReadOnlyLineageResolver(zowe=zowe,allow_dataset_content=True).resolve({'kind':'dataset','name':'APP.CONTROL'})
        self.assertEqual(result['content'], 'control data')
        with patch('workbench.connectors.bounded_command',return_value={}) as command:
            ZoweReader('fictional').read_dataset('APP.CONTROL')
        self.assertEqual(command.call_args.args[0][:5], ['zowe','zos-files','view','data-set','APP.CONTROL'])
        with self.assertRaises(ValidationError): ZoweReader('fictional').read_dataset('APP.*')

    def test_reader_bounds_member_queries_and_hides_missing_profile_errors(self):
        with patch('workbench.connectors.bounded_command',return_value={'success':False,'error':{'message':'fictional-secret password=bad'}}) as command:
            with self.assertRaises(ValidationError) as failure: ZoweReader('missing').list_members('APP.COBOL',pattern='HELLO',max_items=2)
        self.assertNotIn('fictional-secret',str(failure.exception)); self.assertIn('profile',str(failure.exception))
        argv=command.call_args.args[0]; self.assertIn('--max-length',argv); self.assertIn('--pattern',argv)

    def test_fake_subprocess_has_no_shell_or_credential_prompts(self):
        process = Mock(stdout=io.BytesIO(b'{"success":true,"data":{}}')); process.wait.return_value = 0
        with patch('workbench.connectors.subprocess.Popen',return_value=process) as popen:
            bounded_command(['zowe'], {'PATH':'/approved'})
        self.assertFalse(popen.call_args.kwargs['shell']); self.assertEqual(popen.call_args.kwargs['stdin'],subprocess.DEVNULL)
        self.assertEqual(popen.call_args.kwargs['stderr'],subprocess.DEVNULL)

    def test_no_environment_configuration_means_no_session_probing(self):
        with patch.dict('os.environ', {}, clear=True), patch('workbench.connectors.Db2MCP') as db2, patch('workbench.connectors.ZoweReader') as zowe:
            resolver=ReadOnlyLineageResolver.from_environment()
            result=resolver.resolve({'kind':'program','name':'HELLO'})
        self.assertEqual(result['status'],'UNRESOLVED'); db2.assert_not_called(); zowe.assert_not_called()

    def test_zowe_source_and_catalog_have_independent_transport_and_text_ceilings(self):
        with patch('workbench.connectors.MAX_RESPONSE_BYTES',8), \
             patch('workbench.connectors.MAX_ZOWE_SOURCE_RESPONSE_BYTES',128), \
             patch('workbench.connectors.MAX_SOURCE_FILE_BYTES',32), \
             patch('workbench.connectors.bounded_command',return_value={'success':True,'data':'SOURCE TEXT LARGER THAN 8'}) as command:
            result=ZoweReader('fictional').read_member('APP.COBOL(HELLO)')
            self.assertEqual(command.call_args.kwargs['limit'],128)
            self.assertEqual(_zowe_content(result),'SOURCE TEXT LARGER THAN 8')
            ZoweReader('fictional').list_datasets('APP.*')
            self.assertEqual(command.call_args.kwargs['limit'],8)

    def test_oversized_or_explicitly_truncated_source_stays_unresolved(self):
        for response in ({'success':True,'data':'X'*33},
                         {'success':True,'data':{'apiResponse':{'data':'SOURCE','truncated':True}}}):
            zowe=FakeZowe([{'dsname':'APP.COBOL','dsorg':'PO'}],{'APP.COBOL':[{'member':'HELLO'}]})
            zowe.read_member=lambda member:response
            with patch('workbench.connectors.MAX_SOURCE_FILE_BYTES',32):
                result=ReadOnlyLineageResolver(zowe=zowe,dataset_hints=['APP.*']).resolve({'kind':'program','name':'HELLO'})
            self.assertEqual(result['status'],'UNRESOLVED');self.assertEqual(result['coverage'],'PARTIAL')
            self.assertNotIn('content',result)

    def test_resolver_pass_deadline_caps_multiple_reference_reads(self):
        client=FakeDb2()
        with patch('workbench.connectors.time.monotonic',return_value=0):
            resolver=ReadOnlyLineageResolver(db2=client,max_seconds=60,max_total_seconds=90)
            first=resolver.resolve({'kind':'db2_table','name':'APP.CUSTOMER'})
        self.assertEqual(first['status'],'RESOLVED')
        observed=[];original_describe=client.describe
        def observe_timeout(*args,**kwargs):
            observed.append(client.timeout);return original_describe(*args,**kwargs)
        with patch('workbench.connectors.time.monotonic',return_value=80), \
             patch.object(client,'describe',side_effect=observe_timeout) as describe:
            second=resolver.resolve({'kind':'db2_table','name':'APP.CUSTOMER'})
            self.assertEqual(second['status'],'RESOLVED')
            self.assertEqual(describe.call_count,1)
        self.assertEqual(observed,[10]);self.assertEqual(client.timeout,20)
        calls=len(client.calls)
        with patch('workbench.connectors.time.monotonic',return_value=91):
            last=resolver.resolve({'kind':'db2_table','name':'APP.CUSTOMER'})
        self.assertEqual(last['status'],'UNRESOLVED');self.assertEqual(last['reason'],'resolution_pass_time_budget')
        self.assertEqual(last['coverage'],'PARTIAL');self.assertEqual(len(client.calls),calls)


if __name__ == '__main__': unittest.main()
