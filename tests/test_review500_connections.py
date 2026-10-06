"""R321-R400: local boundary reviews; no live credentials or services are used."""
import asyncio
import http.client
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from tools import db2_mcp_server as gateway
from workbench import connectors as con
from workbench import provider as prov
from workbench.api import create_app
from workbench.domain import ValidationError, encode
from workbench.preflight import inspect_workspace
from test_connectors import server
from test_source import COBOL
from test_workflow import MANIFEST


def reply(analysis=None, **extra):
    analysis = analysis or {'summary':'Unverified source suggestion', 'assumptions':[], 'questions':[]}
    return {'choices':[{'message':{'content':json.dumps(analysis)}}], **extra}


class FakeResponse(io.BytesIO):
    def __init__(self, data, content_type='application/json'):
        super().__init__(data)
        self.headers = {'Content-Type':content_type}


class ConnectionReviews(unittest.TestCase):
    def client(self):
        client = con.Db2MCP('http://localhost:8766')
        client.protocol = con.MCP_VERSIONS[0]
        client.tools = set(con.READ_TOOLS)
        return client

    def initialize(self, listings, initialization=None, notification=None):
        client = con.Db2MCP('http://localhost:8766')
        initialization = initialization if initialization is not None else {'protocolVersion':con.MCP_VERSIONS[0], 'capabilities':{'tools':{}}}
        pages = iter(listings)
        def post(url, body, *args, **kwargs):
            if body['method']=='notifications/initialized': return (notification or {}), {}
            result = initialization if body['method']=='initialize' else next(pages)
            return {'jsonrpc':'2.0','id':body['id'],'result':result}, {}
        with patch.object(con, 'post_json', side_effect=post): return client.initialize()

    def provider(self, allow=True):
        return prov.StructuredProvider('https://provider.invalid/chat','review-model','private',allow)

    def page_client(self, pages):
        return SimpleNamespace(timeout=20,list_schemas=Mock(side_effect=pages))

    def gateway_request(self, body, headers=None, duplicates=None):
        with patch.dict(os.environ, {'WB_DB2_MCP_TOKEN':'fixture-token'}, clear=True), server(gateway.Handler) as url:
            connection = http.client.HTTPConnection('127.0.0.1', int(url.rsplit(':',1)[1]),timeout=3)
            raw = json.dumps(body).encode()
            connection.putrequest('POST','/')
            request_headers = {'Authorization':'Bearer fixture-token','Content-Type':'application/json','Content-Length':str(len(raw))}
            request_headers.update(headers or {})
            for key,value in request_headers.items():
                if value is not None: connection.putheader(key,value)
            for key,value in duplicates or []: connection.putheader(key,value)
            connection.endheaders(raw)
            response = connection.getresponse()
            result = response.status, json.loads(response.read())
            connection.close()
            return result

    def gateway_execute(self, name, args, names, rows):
        cursor=Mock();cursor.description=[(n,) for n in names];cursor.fetchmany.return_value=rows
        database=Mock();database.__enter__=Mock(return_value=database);database.__exit__=Mock(return_value=None);database.cursor.return_value=cursor
        driver=SimpleNamespace(connect=Mock(return_value=database))
        with patch.dict(sys.modules,{'pyodbc':driver}),patch.dict(os.environ,{'WB_DB2_ODBC_CONNECTION':'fixture-secret'}):
            result=gateway.execute(name,args)
        return result,driver,cursor

    def test_r321_endpoint_rejects_nontext_configuration(self):
        """A nontext endpoint becomes named validation before urllib parses it."""
        with self.assertRaises(ValidationError): con.endpoint(123)

    def test_r322_endpoint_rejects_parser_stripped_controls(self):
        """An embedded newline cannot be silently removed to change endpoint authority."""
        with self.assertRaises(ValidationError): con.endpoint('https://trusted.invalid\n.evil.invalid/mcp')

    def test_r323_endpoint_rejects_unbalanced_ipv6_as_validation(self):
        """Malformed IPv6 configuration remains a controlled configuration error."""
        with self.assertRaises(ValidationError): con.endpoint('http://[::1/mcp')

    def test_r324_endpoint_rejects_out_of_range_port(self):
        """A syntactically impossible port cannot be reported as configured."""
        with self.assertRaises(ValidationError): con.endpoint('https://db.invalid:99999/mcp')

    def test_r325_endpoint_rejects_embedded_credentials(self):
        """URL credentials are denied before any authentication can be forwarded."""
        with self.assertRaises(ValidationError): con.endpoint('https://alice:private@db.invalid/mcp')

    def test_r326_endpoint_limits_plain_http_to_loopback(self):
        """A public HTTP endpoint cannot receive connector credentials."""
        with self.assertRaises(ValidationError): con.endpoint('http://db.invalid/mcp')
        self.assertEqual(con.endpoint('http://[::1]:8766/mcp'),'http://[::1]:8766/mcp')

    def test_r327_endpoint_rejects_client_only_fragment(self):
        """A fragment cannot ambiguously distinguish otherwise identical endpoints."""
        with self.assertRaises(ValidationError): con.endpoint('https://db.invalid/mcp#credential')

    def test_r328_redirects_never_forward_bearer_credentials(self):
        """Redirect handling refuses changing destinations with a bearer token."""
        with self.assertRaises(ValidationError): con.NoRedirect().redirect_request(None,None,302,'',{},'https://other.invalid/')

    def test_r329_remote_response_byte_limit_is_enforced(self):
        """A remote JSON response over 1 MiB stops before JSON interpretation."""
        response=FakeResponse(b' '*(con.MAX_RESPONSE_BYTES+1))
        with patch.object(con.urllib.request,'build_opener',return_value=SimpleNamespace(open=lambda *a,**k:response)):
            with self.assertRaisesRegex(ValidationError,'exceeds bound'): con.post_json('https://db.invalid/',{})

    def test_r330_remote_html_is_not_interpreted_as_json(self):
        """A login HTML response does not become an apparent connector result."""
        with patch.object(con.urllib.request,'build_opener',return_value=SimpleNamespace(open=lambda *a,**k:FakeResponse(b'{}','text/html'))):
            with self.assertRaisesRegex(ValidationError,'content type'): con.post_json('https://db.invalid/',{})

    def test_r331_transport_failures_redact_private_endpoint_details(self):
        """Transport exceptions expose a safe message without the credential-bearing URL."""
        opener=SimpleNamespace(open=Mock(side_effect=OSError('https://private.invalid/?secret=PRIVATE')))
        with patch.object(con.urllib.request,'build_opener',return_value=opener):
            with self.assertRaises(ValidationError) as caught: con.post_json('https://private.invalid/?secret=PRIVATE',{},'SECRET')
        self.assertNotIn('PRIVATE',str(caught.exception));self.assertNotIn('SECRET',str(caught.exception))

    def test_r332_notification_cannot_open_response_stream(self):
        """An initialized notification must not leave an unbounded SSE response open."""
        with patch.object(con.urllib.request,'build_opener',return_value=SimpleNamespace(open=lambda *a,**k:FakeResponse(b'','text/event-stream'))):
            with self.assertRaisesRegex(ValidationError,'Notification'): con.post_json('https://db.invalid/',{'method':'notifications/initialized'})

    def test_r333_sse_progress_and_multiline_result(self):
        """Progress notifications and SSE comments do not replace the matching multiline reply."""
        raw=b':keepalive\n\ndata: {"jsonrpc":"2.0","method":"notifications/progress"}\n\ndata: {"jsonrpc":"2.0",\ndata: "id":5,"result":{"rows":[]}}\n\n'
        self.assertEqual(con._sse_response(io.BytesIO(raw),5)['result'],{'rows':[]})

    def test_r334_sse_boolean_identity_cannot_match_integer_request(self):
        """JSON true is not accepted as integer request ID 1 even though Python compares them equal."""
        raw=b'data: {"jsonrpc":"2.0","id":true,"result":{}}\n\n'
        with self.assertRaises(ValidationError): con._sse_response(io.BytesIO(raw),1)

    def test_r335_sse_rejects_unsolicited_execution_request(self):
        """A server sampling request cannot acquire client execution authority."""
        raw=b'data: {"jsonrpc":"2.0","id":8,"method":"sampling/createMessage"}\n\n'
        with self.assertRaisesRegex(ValidationError,'Unsolicited'): con._sse_response(io.BytesIO(raw),1)

    def test_r336_sse_stream_bound_includes_comment_bytes(self):
        """Keepalive comments still consume the finite response byte budget."""
        with self.assertRaisesRegex(ValidationError,'exceeds bound'): con._sse_response(io.BytesIO(b':'+b'x'*con.MAX_RESPONSE_BYTES),1)

    def test_r337_sql_rejects_unlisted_mutating_operation(self):
        """An arbitrary SQL tool name never generates a command."""
        with self.assertRaises(ValidationError): con.catalog_sql('execute_sql',{'sql':'DROP TABLE ACCOUNT'})

    def test_r338_sql_catalog_filter_stays_bound_parameter(self):
        """Quote/comment injection in a discovery filter remains data in a SELECT parameter."""
        value="A' OR 1=1 --";sql,params=con.catalog_sql('db2_list_tables',{'schema':value,'after_table':value})
        self.assertNotIn(value,sql);self.assertEqual(params,[value,'','',value]);self.assertTrue(sql.startswith('SELECT'))

    def test_r339_sql_sampling_identifier_injection_is_denied(self):
        """A quoted table identifier cannot introduce another SQL statement."""
        with self.assertRaises(ValidationError): con.catalog_sql('db2_sample_rows',{'schema':'A','table':'T";DELETE FROM T--'})

    def test_r340_sql_boolean_cannot_bypass_integer_row_limit(self):
        """Boolean true cannot masquerade as a one-row numeric bound."""
        with self.assertRaises(ValidationError): con.catalog_sql('db2_list_schemas',{'limit':True})

    def test_r341_sql_unknown_arguments_do_not_expand_capability(self):
        """An otherwise read-only request cannot smuggle custom SQL through an extra field."""
        with self.assertRaises(ValidationError): con.catalog_sql('db2_list_schemas',{'where':'1=1'})

    def test_r342_sql_false_schema_does_not_widen_discovery(self):
        """A malformed falsy schema must be rejected instead of silently becoming wildcard scope."""
        with self.assertRaises(ValidationError): con.catalog_sql('db2_list_tables',{'schema':False})

    def test_r343_sql_column_cursor_requires_integer_ordinal(self):
        """Fractional metadata cursors cannot skip columns through implicit coercion."""
        with self.assertRaises(ValidationError): con.catalog_sql('db2_describe_table',{'schema':'A','table':'T','after_column':1.5})

    def test_r344_sql_description_binds_names_and_fetches_sentinel(self):
        """Column paging binds schema/table values and requests one sentinel row beyond the limit."""
        sql,params=con.catalog_sql('db2_describe_table',{'schema':'A','table':'T','after_column':8,'limit':4})
        self.assertEqual(params,['A','T',8]);self.assertIn('FETCH FIRST 5 ROWS ONLY',sql);self.assertIn('WITH UR',sql)

    def test_r345_sql_sample_is_bounded_and_has_no_sentinel(self):
        """Sampling never fetches an extra row or accepts an unbounded limit."""
        sql,params=con.catalog_sql('db2_sample_rows',{'schema':'A','table':'T','limit':100})
        self.assertIn('SELECT * FROM "A"."T" FETCH FIRST 100 ROWS ONLY',sql);self.assertEqual(params,[])
        with self.assertRaises(ValidationError): con.catalog_sql('db2_sample_rows',{'schema':'A','table':'T','limit':101})

    def test_r346_mcp_requires_negotiation_before_tool_calls(self):
        """A fresh client cannot invoke read tools before protocol negotiation."""
        with patch.object(con,'post_json') as transport:
            with self.assertRaises(ValidationError): con.Db2MCP('http://localhost:8766').rpc('tools/list',{})
        transport.assert_not_called()

    def test_r347_mcp_rejects_boolean_response_identity(self):
        """A JSON-RPC boolean response ID is rejected independently of result presence."""
        with patch.object(con,'post_json',return_value=({'jsonrpc':'2.0','id':True,'result':{}},{})):
            with self.assertRaisesRegex(ValidationError,'identity'): self.client().rpc('tools/list',{})

    def test_r348_mcp_unsupported_negotiated_version_stops_initialization(self):
        """Unknown protocol semantics do not receive initialized notification or tool requests."""
        with self.assertRaisesRegex(ValidationError,'Unsupported MCP'): self.initialize([],{'protocolVersion':'2099-01-01','capabilities':{'tools':{}}})

    def test_r349_mcp_requires_advertised_tools_capability(self):
        """A server without tools capability cannot be reported connected for Db2 discovery."""
        with self.assertRaisesRegex(ValidationError,'advertise tools'): self.initialize([],{'protocolVersion':con.MCP_VERSIONS[0],'capabilities':{}})

    def test_r350_mcp_notification_response_cannot_inject_result(self):
        """A result returned to notifications/initialized is a protocol failure."""
        with self.assertRaisesRegex(ValidationError,'notification'): self.initialize([],notification={'result':{'tools':[]}})

    def test_r351_mcp_tool_listing_entry_must_have_text_name(self):
        """Malformed tool entries do not reach set membership or capability dispatch."""
        with self.assertRaisesRegex(ValidationError,'tool entry'): self.initialize([{'tools':[{'name':['db2_list_schemas']}]}])

    def test_r352_mcp_tools_cursor_cycle_is_rejected(self):
        """Repeating a tools continuation fails before an infinite enumeration loop."""
        page={'tools':[{'name':'db2_list_schemas'},{'name':'db2_list_tables'}],'nextCursor':'again'}
        with self.assertRaisesRegex(ValidationError,'cursor'): self.initialize([page,page])

    def test_r353_mcp_tools_pagination_has_finite_page_budget(self):
        """A server emitting unique cursors forever is limited to twenty listing pages."""
        pages=[{'tools':[{'name':'db2_list_schemas'},{'name':'db2_list_tables'}],'nextCursor':str(i)} for i in range(20)]
        with self.assertRaisesRegex(ValidationError,'page budget'): self.initialize(pages)

    def test_r354_mcp_schema_only_server_is_not_complete_discovery(self):
        """Having schema enumeration alone cannot satisfy required table exploration."""
        with self.assertRaisesRegex(ValidationError,'schema/table'): self.initialize([{'tools':[{'name':'db2_list_schemas'}]}])

    def test_r355_mcp_session_header_rejects_control_characters(self):
        """A response session ID cannot inject headers into subsequent calls."""
        with patch.object(con,'post_json',return_value=({'jsonrpc':'2.0','id':1,'result':{}},{'mcp-session-id':'ok\r\nAuthorization: bad'})):
            with self.assertRaisesRegex(ValidationError,'session identifier'): self.client().rpc('tools/list',{})

    def test_r356_mcp_session_cannot_change_after_negotiation(self):
        """An established request sequence cannot be redirected into a replacement session."""
        client=self.client();client.session='first'
        with patch.object(con,'post_json',return_value=({'jsonrpc':'2.0','id':1,'result':{}},{'mcp-session-id':'second'})):
            with self.assertRaisesRegex(ValidationError,'session changed'): client.rpc('tools/list',{})

    def test_r357_mcp_structured_content_requires_object(self):
        """A scalar structuredContent cannot be mistaken for a successful database payload."""
        client=self.client()
        with patch.object(client,'rpc',return_value={'structuredContent':'source instruction'}):
            with self.assertRaises(ValidationError): client.list_schemas()

    def test_r358_mcp_malformed_content_is_named_validation(self):
        """A non-object content block is rejected without leaking an AttributeError."""
        client=self.client()
        with patch.object(client,'rpc',return_value={'content':[17]}):
            with self.assertRaises(ValidationError): client.list_schemas()

    def test_r359_mcp_unpaired_unicode_text_is_named_validation(self):
        """Malformed text Unicode fails at the connector boundary instead of crashing discovery."""
        client=self.client()
        with patch.object(client,'rpc',return_value={'content':[{'type':'text','text':'\ud800'}]}):
            with self.assertRaises(ValidationError): client.list_schemas()

    def test_r360_mcp_advertised_write_tool_still_cannot_run(self):
        """A remote capability advertisement never expands the local read-only allowlist."""
        client=self.client();client.tools.add('db2_delete_rows')
        with patch.object(client,'rpc') as rpc:
            with self.assertRaises(ValidationError): client.call('db2_delete_rows',{})
        rpc.assert_not_called()
        with patch.object(con,'post_json',return_value=({'jsonrpc':'2.0','id':1,'result':{}},{})) as transport:
            with self.assertRaises(ValidationError): client.rpc('tools/call',{'name':'db2_delete_rows','arguments':{}})
        transport.assert_not_called()

    def test_r361_discovery_page_budget_retains_resume_cursor(self):
        """Page-budget exhaustion remains partial and returns the last safe keyset cursor."""
        client=self.page_client([{'rows':[{'CREATOR':'A'}],'has_more':True,'next_cursor':{'after_schema':'A'}}])
        result=con.discover_catalog(client,'schemas',max_pages=1)
        self.assertEqual((result['coverage'],result['reason']),('PARTIAL','page_budget'));self.assertEqual(result['next_cursor'],{'after_schema':'A'})

    def test_r362_discovery_byte_budget_discards_unaccepted_page(self):
        """A page crossing the cumulative byte budget contributes no rows or completion credit."""
        client=self.page_client([{'rows':[{'CREATOR':'A','notes':'x'*2048}],'has_more':False}])
        result=con.discover_catalog(client,'schemas',max_bytes=1024)
        self.assertEqual(result['reason'],'byte_budget');self.assertEqual(result['rows'],[]);self.assertEqual(result['pages'],0)

    def test_r363_discovery_rejects_scalar_rows(self):
        """A malformed catalog row leaves traversal partial and records invalid_page."""
        result=con.discover_catalog(self.page_client([{'rows':[False],'has_more':False}]),'schemas')
        self.assertEqual((result['coverage'],result['reason']),('PARTIAL','invalid_page'))

    def test_r364_discovery_repeated_cursor_does_not_duplicate_rows(self):
        """A repeated continuation is detected before duplicate row evidence is appended."""
        page={'rows':[{'CREATOR':'A'}],'has_more':True,'next_cursor':{'after_schema':'A'}}
        result=con.discover_catalog(self.page_client([page,page]),'schemas')
        self.assertEqual(result['rows'],[{'CREATOR':'A'}]);self.assertEqual(result['reason'],'repeated_cursor')

    def test_r365_discovery_second_page_failure_preserves_first(self):
        """A later read failure retains accepted rows and their retry cursor without completion credit."""
        client=self.page_client([{'rows':[{'CREATOR':'A'}],'has_more':True,'next_cursor':{'after_schema':'A'}},ValidationError('offline')])
        result=con.discover_catalog(client,'schemas')
        self.assertEqual(result['reason'],'page_read_failed');self.assertEqual(result['rows'],[{'CREATOR':'A'}]);self.assertEqual(result['next_cursor'],{'after_schema':'A'})

    def test_r366_discovery_restores_client_timeout_after_deadline(self):
        """A shared client regains its original timeout after a bounded traversal returns."""
        client=self.page_client([{'rows':[],'has_more':False}]);client.timeout=99
        result=con.discover_catalog(client,'schemas',max_seconds=1)
        self.assertEqual(client.timeout,99);self.assertEqual(result['coverage'],'COMPLETE')

    def test_r367_discovery_time_budget_requires_numeric_duration(self):
        """A string duration is rejected explicitly before arithmetic can raise TypeError."""
        with self.assertRaises(ValidationError): con.discover_catalog(self.page_client([]),'schemas',max_seconds='60')

    def test_r368_discovery_malformed_unicode_page_stays_partial(self):
        """A non-serializable page is recorded as invalid_page while preserving timeout and bounds."""
        client=self.page_client([{'rows':[{'CREATOR':'\ud800'}],'has_more':False}])
        result=con.discover_catalog(client,'schemas')
        self.assertEqual(result['reason'],'invalid_page');self.assertEqual(result['coverage'],'PARTIAL');self.assertEqual(client.timeout,20)

    def test_r369_zowe_nontext_profile_is_named_validation(self):
        """A typed connector refuses malformed profile configuration before regex evaluation."""
        with self.assertRaises(ValidationError): con.ZoweReader(['approved'])

    def test_r370_zowe_dataset_cannot_inject_option(self):
        """Dataset text beginning with an option never reaches the Zowe process."""
        with patch.object(con,'bounded_command') as run:
            with self.assertRaises(ValidationError): con.ZoweReader('approved').read_member('--password')
        run.assert_not_called()

    def test_r371_zowe_member_reads_require_explicit_dataset(self):
        """A wildcard cannot turn a member read into broad source retrieval."""
        with self.assertRaises(ValidationError): con.ZoweReader('approved').read_member('APP.*(MEMBER)')

    def test_r372_zowe_write_operation_is_not_dispatchable(self):
        """A valid dataset name cannot make the typed reader submit or upload content."""
        with self.assertRaises(ValidationError): con.ZoweReader('approved').operation('submit_job','APP.JCL(JOB)')

    def test_r373_zowe_subprocess_uses_argv_and_filtered_environment(self):
        """Read dispatch keeps dataset text in one argument and omits unrelated secrets from environment."""
        with patch.dict(os.environ,{'PATH':'/approved/bin','HOME':'/operator','PRIVATE_TOKEN':'secret'},clear=True),patch.object(con,'bounded_command',return_value={}) as run:
            con.ZoweReader('approved').read_member('APP.SOURCE(MEMBER)')
        command,environment=run.call_args.args
        self.assertEqual(command[:5],['zowe','zos-files','view','data-set','APP.SOURCE(MEMBER)']);self.assertNotIn('PRIVATE_TOKEN',environment)

    def test_r374_command_timeout_kills_and_reaps_child(self):
        """An over-time source read terminates its process and returns a bounded validation error."""
        process=Mock(stdout=io.BytesIO(b''));process.wait.side_effect=[subprocess.TimeoutExpired('zowe',1),-9]
        with patch.object(con.subprocess,'Popen',return_value=process):
            with self.assertRaisesRegex(ValidationError,'timed out'): con.bounded_command(['zowe'],{},timeout=0.01)
        process.kill.assert_called_once();self.assertEqual(process.wait.call_count,2)

    def test_r375_command_output_overflow_stops_before_decode(self):
        """A noisy source command cannot accumulate or decode bytes beyond its approved output bound."""
        process=Mock(stdout=io.BytesIO(b'x'*8192));process.wait.return_value=0
        with patch.object(con.subprocess,'Popen',return_value=process):
            with self.assertRaisesRegex(ValidationError,'output bound'): con.bounded_command(['zowe'],{},limit=100)
        process.kill.assert_called_once()

    def test_r376_provider_truthy_string_does_not_approve_egress(self):
        """The string false cannot authorize source transfer via Python truthiness."""
        with patch.object(prov,'post_json',return_value=(reply(),{})) as transport:
            with self.assertRaises(ValidationError): self.provider(allow='false').analyze('SOURCE','review')
        transport.assert_not_called()

    def test_r377_provider_malformed_source_unicode_never_transfers(self):
        """Invalid source Unicode is refused as input before fingerprinting or network transfer."""
        with patch.object(prov,'post_json') as transport:
            with self.assertRaises(ValidationError): self.provider().analyze('\ud800','review')
        transport.assert_not_called()

    def test_r378_provider_missing_message_is_named_validation(self):
        """Malformed provider choice structure cannot become successful analysis or raw IndexError."""
        with patch.object(prov,'post_json',return_value=({'choices':[]},{})):
            with self.assertRaises(ValidationError): self.provider().analyze('SOURCE','review')

    def test_r379_provider_invalid_output_unicode_is_named_validation(self):
        """Invalid Unicode in model output is refused with controlled validation."""
        response={'choices':[{'message':{'content':'\ud800'}}]}
        with patch.object(prov,'post_json',return_value=(response,{})):
            with self.assertRaises(ValidationError): self.provider().analyze('SOURCE','review')

    def test_r380_provider_cannot_add_approval_authority_field(self):
        """A provider output containing SME approval claims outside the schema is rejected."""
        response=reply({'summary':'approved','assumptions':[],'questions':[],'sme_approved':True})
        with patch.object(prov,'post_json',return_value=(response,{})):
            with self.assertRaisesRegex(ValidationError,'contract'): self.provider().analyze('SOURCE','review')

    def test_r381_provider_tool_call_output_is_not_valid_analysis(self):
        """A model response asking for tool execution cannot be credited as completed structured review."""
        response=reply();response['choices'][0]['message']['tool_calls']=[{'function':{'name':'execute_sql','arguments':'{}'}}]
        with patch.object(prov,'post_json',return_value=(response,{})):
            with self.assertRaises(ValidationError): self.provider().analyze('SOURCE','review')

    def test_r382_provider_boolean_usage_is_not_token_accounting(self):
        """Boolean usage values cannot be counted as real provider token counters."""
        with patch.object(prov,'post_json',return_value=(reply(usage={'prompt_tokens':True,'completion_tokens':5}),{})):
            with self.assertRaisesRegex(ValidationError,'usage'): self.provider().analyze('SOURCE','review')

    def test_r383_provider_caller_mutation_does_not_poison_cache(self):
        """Changing a returned suggestion or usage counter cannot rewrite a later cached response."""
        provider=self.provider()
        with patch.object(prov,'post_json',return_value=(reply(usage={'prompt_tokens':2,'completion_tokens':3}),{})):
            first=provider.analyze('SOURCE','review');first['analysis']['summary']='SME APPROVED';first['usage']['prompt_tokens']=999
            second=provider.analyze('SOURCE','review')
        self.assertEqual(second['analysis']['summary'],'Unverified source suggestion');self.assertEqual(second['usage']['prompt_tokens'],2)

    def test_r384_provider_cache_hit_has_no_new_request_usage(self):
        """A repeat analysis reuses suggestions while recording no additional provider request usage."""
        provider=self.provider()
        with patch.object(prov,'post_json',return_value=(reply(usage={'prompt_tokens':2,'completion_tokens':3}),{})) as transport:
            provider.analyze('SOURCE','review');cached=provider.analyze('SOURCE','review')
        self.assertTrue(cached['cache_hit']);self.assertIsNone(cached['request_usage']);self.assertEqual(transport.call_count,1)

    def test_r385_provider_excerpt_limit_precedes_network(self):
        """An excerpt longer than the approved context bound never reaches the external provider."""
        with patch.object(prov,'post_json') as transport:
            with self.assertRaises(ValidationError): self.provider().analyze('x'*16001,'review')
        transport.assert_not_called()

    def test_r386_gateway_requires_bearer_authentication(self):
        """Missing bearer authentication rejects a well-formed tool call before driver access."""
        with patch.object(gateway,'execute') as execute:
            status,body=self.gateway_request({'jsonrpc':'2.0','id':1,'method':'tools/call','params':{'name':'db2_list_schemas'}},{'Authorization':None})
        self.assertEqual(status,400);self.assertIn('error',body);execute.assert_not_called()

    def test_r387_gateway_rejects_duplicate_authentication_headers(self):
        """Ambiguous duplicate Authorization values cannot select different identities across HTTP layers."""
        status,body=self.gateway_request({'jsonrpc':'2.0','id':1,'method':'tools/list'},duplicates=[('Authorization','Bearer another')])
        self.assertEqual(status,400);self.assertIn('error',body)

    def test_r388_gateway_rejects_transfer_encoding_content_length_conflict(self):
        """Unsupported transfer encoding cannot bypass the gateway's exact Content-Length framing."""
        status,body=self.gateway_request({'jsonrpc':'2.0','id':1,'method':'tools/list'},{'Transfer-Encoding':'chunked'})
        self.assertEqual(status,400);self.assertIn('error',body)

    def test_r389_gateway_requires_json_content_type(self):
        """A text/plain request is not treated as an authenticated JSON-RPC invocation."""
        status,body=self.gateway_request({'jsonrpc':'2.0','id':1,'method':'tools/list'},{'Content-Type':'text/plain'})
        self.assertEqual(status,400);self.assertIn('error',body)

    def test_r390_gateway_driver_requests_read_only_with_finite_timeouts(self):
        """ODBC connection and query execution preserve read-only flags and timeout limits."""
        result,driver,cursor=self.gateway_execute('db2_list_schemas',{'limit':1},['CREATOR'],[('A',),('B',)])
        self.assertEqual(driver.connect.call_args.kwargs,{'autocommit':True,'attrs_before':{101:1},'timeout':10});self.assertEqual(cursor.timeout,15)
        self.assertEqual(result['next_cursor'],{'after_schema':'A'});self.assertTrue(result['read_only'])

    def test_r391_gateway_mismatched_row_width_cannot_drop_values(self):
        """Database row/column shape disagreement cannot be silently truncated by zip."""
        with self.assertRaises(ValidationError): self.gateway_execute('db2_list_schemas',{},['CREATOR'],[('A','UNACCOUNTED')])

    def test_r392_gateway_oversize_encoded_envelope_returns_safe_error(self):
        """JSON string escaping cannot expand a near-limit result into an oversized wire success."""
        content={'rows':[{'value':'"'*600000}]}
        with patch.object(gateway,'execute',return_value=content):
            status,body=self.gateway_request({'jsonrpc':'2.0','id':1,'method':'tools/call','params':{'name':'db2_list_schemas'}})
        self.assertEqual(status,400);self.assertIn('error',body)

    def test_r393_gateway_nonfinite_database_value_is_named_validation(self):
        """NaN from a driver cannot leak nonstandard JSON or raw serialization failures."""
        with self.assertRaises(ValidationError): self.gateway_execute('db2_sample_rows',{'schema':'A','table':'T'},['AMOUNT'],[(float('nan'),)])

    def test_r394_gateway_unknown_protocol_does_not_execute_reads(self):
        """An unsupported MCP version stops before dispatching a valid read operation."""
        with patch.object(gateway,'execute') as execute:
            status,body=self.gateway_request({'jsonrpc':'2.0','id':1,'method':'tools/call','params':{'name':'db2_list_schemas'}},{'MCP-Protocol-Version':'2099-01-01'})
        self.assertEqual(status,400);execute.assert_not_called()


class PreflightReviews(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name)
        (self.root/'Endeavor').mkdir();(self.root/'Endeavor/ELIGIBLE.cbl').write_text(COBOL)
        self.manifest=self.root/'process-input.md';self.manifest.write_text(MANIFEST)

    def check(self,env,name):
        result=inspect_workspace(self.root,self.manifest,environ=env)
        self.assertEqual(result['network_requests'],0)
        return next(row for row in result['checks'] if row['id']==name)

    def test_r395_preflight_invalid_port_cannot_be_unverified_valid(self):
        """Offline configuration validation blocks invalid port syntax without contacting the endpoint."""
        self.assertEqual(self.check({'WB_DB2_MCP_URL':'https://db.invalid:invalid/mcp'},'db2')['status'],'BLOCKED')

    def test_r396_preflight_nontext_dataset_hint_is_diagnostic(self):
        """Malformed connector configuration yields a blocked Zowe diagnostic instead of TypeError."""
        with patch('workbench.preflight.shutil.which',return_value='/approved/zowe'):
            self.assertEqual(self.check({'WB_ZOWE_PROFILE':'approved','WB_DATASET_HINT':[]},'zowe')['status'],'BLOCKED')

    def test_r397_preflight_model_identifier_must_be_text(self):
        """A truthy nontext model value cannot be reported as valid provider configuration."""
        self.assertEqual(self.check({'WB_LLM_URL':'https://provider.invalid/chat','WB_LLM_MODEL':True},'llm')['status'],'BLOCKED')


class ApiBoundaryReviews(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        ledger=SimpleNamespace(list=lambda *args:[])
        self.coordinator=SimpleNamespace(root=Path(self.temp.name),ledger=ledger,provider=None)
        with patch('workbench.api.Coordinator',return_value=self.coordinator):self.app=create_app(self.temp.name)

    async def request(self,path,method='GET',raw=b'{}',headers=None):
        messages=[];received=False
        async def receive():
            nonlocal received
            if not received:received=True;return {'type':'http.request','body':raw,'more_body':False}
            await asyncio.Future()
        async def send(message):messages.append(message)
        scope={'type':'http','asgi':{'version':'3.0'},'http_version':'1.1','scheme':'http','method':method,'path':path,'raw_path':path.encode(),'query_string':b'','root_path':'','server':('127.0.0.1',8765),'client':('127.0.0.1',1),'headers':[(b'host',b'127.0.0.1:8765'),*(headers or [])]}
        with patch('workbench.api.portfolio',return_value={}):await self.app(scope,receive,send)
        return messages[0],b''.join(message.get('body',b'') for message in messages[1:])

    async def test_r398_api_duplicate_host_does_not_pass_origin_gate(self):
        """Duplicate Host fields are rejected even when the first matches configured loopback authority."""
        start,body=await self.request('/api/state',headers=[(b'host',b'evil.invalid')])
        self.assertEqual(start['status'],400);self.assertNotIn(b'"token"',body)

    async def test_r399_api_duplicate_json_keys_rejected_before_intake(self):
        """Conflicting manifest keys cannot resolve differently between the API and downstream intake."""
        _,body=await self.request('/api/state');token=json.loads(body)['token']
        headers=[(b'origin',b'http://127.0.0.1:8765'),(b'x-workbench-token',token.encode())]
        start,body=await self.request('/api/intake','POST',b'{"manifest":"one","manifest":"two"}',headers)
        self.assertEqual(start['status'],400);self.assertIn(b'Invalid JSON',body)

    async def test_r400_api_denied_mutation_has_security_response_headers(self):
        """Early same-origin rejection still receives no-store, nosniff and anti-framing policy headers."""
        start,body=await self.request('/api/intake','POST')
        self.assertEqual(start['status'],403)
        headers=dict(start['headers'])
        self.assertEqual(headers.get(b'cache-control'),b'no-store');self.assertEqual(headers.get(b'x-content-type-options'),b'nosniff');self.assertIn(b"frame-ancestors 'none'",headers.get(b'content-security-policy',b''))


if __name__=='__main__':unittest.main()
