#!/usr/bin/env python3
"""FastMCP read-only Db2 server: fixed .env, stdio or authenticated loopback HTTP.

The retained Handler is a legacy protocol compatibility fixture; production
launches FastMCP. Both use the same fixed SELECT executor and driver boundary.
"""
import json
import os
import secrets
import threading
import time
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from workbench.connectors import READ_TOOLS,MCP_VERSIONS,MAX_RESPONSE_BYTES,catalog_sql
from workbench.domain import decode,encode,require,ValidationError,identity,safe_path,sha

_EXPORT_LOCK=threading.RLock()
# Selected only by this process' explicit CLI arguments, never a path env var.
_SELECTED_ENV_FILE=None
_SELECTED_CONFIG_FILE=None
_SELECTED_DRIVER_NAME=None
_SELECTED_ENV_ONLY=False


def _private_request(workspace,process_id,request_id,need_id):
    """Read Coordinator authorization without creating another ledger writer."""
    import re
    import sqlite3
    from contextlib import closing
    from workbench.retrieval import _verify_request,validate_binding,_snapshot_request,MAX_PACKET_BYTES
    require(workspace is not None,'Protected export needs the approved local workspace')
    root=Path(workspace).absolute();identity(process_id)
    require(isinstance(request_id,str) and re.fullmatch('[0-9a-f]{64}',request_id),'Invalid retrieval request ID')
    require(isinstance(need_id,str) and re.fullmatch('N[0-9a-f]{16}',need_id),'Invalid retrieval need ID')
    relative='analysis/retrieval/'+request_id+'/request.json'
    request_path=safe_path(root,'processes/'+process_id+'/'+relative)
    require(request_path.is_file() and request_path.stat().st_size<=MAX_PACKET_BYTES,'Registered bounded retrieval request required')
    raw=request_path.read_bytes();request=decode(raw,MAX_PACKET_BYTES);_verify_request(request)
    require(request['process_id']==process_id and request['request_id']==request_id,'Retrieval identity differs')
    ledger=safe_path(root,'.migration/ledger.sqlite')
    require(ledger.is_file(),'Existing Coordinator ledger required')
    with closing(sqlite3.connect(ledger.as_uri()+'?mode=ro',uri=True,timeout=10)) as db:
        db.execute('PRAGMA query_only=ON')
        row=db.execute('SELECT document,status,packet_issued FROM processes WHERE id=?',(process_id,)).fetchone()
    require(row is not None and not row[2] and row[1] in ('WAITING_DISCOVERY','WAITING_REQUIREMENTS','WAITING_COPILOT'),
            'Protected export requires an idle pre-review Coordinator checkpoint')
    doc=decode(row[0]);state=doc.get('retrieval_request') or {}
    require(state.get('status')=='WAITING' and state.get('id')==request_id and state.get('artifact')==relative
            and relative in doc.get('artifacts',[]) and doc.get('artifact_hashes',{}).get(relative)==sha(raw),
            'Protected export requires the exact registered outstanding request')
    validate_binding(request,doc)
    need=next((need for need in request['needs'] if need['need_id']==need_id),None)
    require(need is not None and need['kind']=='db2_snapshot','Protected export requires explicit Db2 snapshot authorization')
    context=_snapshot_request(need)
    require(context['scope']['kind']=='full_table' and not context['scope']['keys'],
            'Record key values cannot enter the model-facing export request')
    return root,request,need,context


def export_snapshot_to_inbox(workspace,process_id,request_id,need_id):
    """Raw records go only to a derived local file; return metadata, never values."""
    from workbench.retrieval import private_snapshot_path,_snapshot_return
    from workbench.database import validate_snapshot,MAX_BYTES,MAX_ROWS
    from workbench.local_agent import _publish
    with _EXPORT_LOCK:
        root,request,need,context=_private_request(workspace,process_id,request_id,need_id)
        relative=private_snapshot_path(need_id)
        path=safe_path(root,request['return_folder']+'/files/'+relative)
        if path.exists():
            require(path.is_file() and path.stat().st_size<=MAX_BYTES,'Private snapshot must be regular and bounded')
            raw=path.read_bytes();snapshot=_snapshot_return(raw.decode('utf-8'),None,need)
            require(snapshot['provenance']['tool']=='db2_export_snapshot_to_inbox','Existing private export has a different origin')
        else:
            schema,table=need['name'].split('.');maximum=min(configured_row_limit(),MAX_ROWS)
            rows=[];cursor=None;complete=False;reason='row_budget';deadline=time.monotonic()+60
            # Reserve envelope overhead and estimate encoded row bytes before
            # final bounded validation; a cap remains an explicit partial export.
            size=len(encode(context))+8192
            try:
                while len(rows)<maximum:
                    require(time.monotonic()<deadline,'Private export time budget reached')
                    args={'schema':schema,'table':table,'limit':min(100,maximum-len(rows)),'max_rows':maximum}
                    if cursor:args['cursor']=cursor
                    page=ROW_READS.read(args);cursor=page['next_cursor']
                    for row in page['rows']:
                        require(list(row)==context['column_names'],'Actual private export column order differs from request')
                        row_size=len(encode(row))
                        if size+row_size>MAX_BYTES:reason='byte_budget';break
                        rows.append(row);size+=row_size
                    if reason=='byte_budget':break
                    if not page['has_more']:
                        complete=page['reason']=='end_of_cursor';reason=page['reason'];break
                provenance={'origin':'configured_mcp','tool':'db2_export_snapshot_to_inbox','locator':need['name'],
                            'retrieved_at':datetime.now(timezone.utc).isoformat()}
                snapshot={**context,'scope':{**context['scope'],'complete':complete},'schema_version':1,
                          'kind':'DB2_RECORD_SNAPSHOT','schema':schema,'table':table,'rows':rows,
                          'provenance':provenance,'consistency':{'status':'unverified','evidence':[]}}
                raw=encode(snapshot,MAX_BYTES);snapshot=validate_snapshot(raw.decode('utf-8'))
                # A changed/stale request cannot publish private records.
                _private_request(root,process_id,request_id,need_id)
                require(_publish(path,raw),'Private export already exists; inspect the preserved receipt')
            finally:
                if cursor:ROW_READS.close(cursor)
        item={'need_id':need_id,'status':'FOUND','path':relative,'sha256':sha(raw),
              'provenance':snapshot['provenance']}
        # Snapshot-only requests can be finalized deterministically without the
        # model seeing private catalog identities in provenance. Mixed requests
        # retain a named local receipt-binding gap; do not guess other items.
        response_ready=False;response_path=safe_path(root,request['return_folder']+'/response.json')
        if all(entry['kind']=='db2_snapshot' for entry in request['needs']):
            items=[]
            for entry in request['needs']:
                exported=private_snapshot_path(entry['need_id'])
                existing=safe_path(root,request['return_folder']+'/files/'+exported)
                if not existing.exists():break
                require(existing.is_file() and existing.stat().st_size<=MAX_BYTES,'Private snapshot must be regular and bounded')
                content=existing.read_bytes();record=_snapshot_return(content.decode('utf-8'),None,entry)
                items.append({'need_id':entry['need_id'],'status':'FOUND','path':exported,'sha256':sha(content),
                              'provenance':record['provenance']})
            if len(items)==len(request['needs']):
                receipt=encode({'request_id':request_id,'items':items})
                _private_request(root,process_id,request_id,need_id)
                if response_path.exists():require(response_path.read_bytes()==receipt,'Existing private response differs; preserve its original evidence')
                else:require(_publish(response_path,receipt),'Private response already exists; inspect the preserved receipt')
                response_ready=True
        safe_item={key:value for key,value in item.items() if key!='provenance'}
        safe_item['provenance_reference_sha256']=sha(encode(item['provenance']))
        return {'request_id':request_id,'item':safe_item,'row_count':len(snapshot['rows']),
                'complete':snapshot['scope']['complete'],'consistency':'unverified',
                'private_file':str(path),'read_only':True,'data_policy':'LOCAL_PRIVATE_RECORDS_NO_MODEL_VALUES',
                'response_ready':response_ready,'response_file':str(response_path),
                'receipt_status':'SAVED_PRIVATE_RESPONSE' if response_ready else 'NEEDS_LOCAL_PROTECTED_RECEIPT_BINDING'}


def protected_metadata(name,result):
    """Only structural catalog fields cross the Claude MCP boundary."""
    fields={'db2_list_schemas':{'CREATOR'},'db2_list_tables':{'CREATOR','NAME','TYPE'},
            'db2_describe_table':{'NAME','COLTYPE','LENGTH','SCALE','NULLS','COLNO','CCSID'}}[name]
    require(isinstance(result,dict) and isinstance(result.get('rows'),list),'Typed metadata response required')
    allowed={'rows','has_more','next_cursor','bounded','read_only','snapshot_consistent'}
    return {**{key:value for key,value in result.items() if key in allowed and key!='rows'},
            'rows':[{key:value for key,value in row.items() if key in fields} for row in result['rows']],
            'data_policy':'STRUCTURAL_METADATA_ONLY_NO_REMARKS_DEFAULTS_OR_RECORDS'}


def _selected_env_driver():
    if _SELECTED_DRIVER_NAME is not None:
        return _SELECTED_DRIVER_NAME
    if _SELECTED_CONFIG_FILE is None:
        return 'IBM DB2 ODBC DRIVER'
    from workbench.db2_env import _read,_text
    from workbench.db2_setup import _config
    config=_config(decode(_read(_SELECTED_CONFIG_FILE,1024*1024),1024*1024))
    return _text(config.get('driver'),253)


def connection_string():
    if _SELECTED_ENV_FILE is not None:
        from workbench.db2_env import connection_string as from_env
        return from_env({} if _SELECTED_ENV_ONLY else os.environ,_SELECTED_ENV_FILE,canonical=True,driver=_selected_env_driver())
    if os.environ.get('WB_DB2_CONFIG'):
        from workbench.db2_setup import load_connection
        return load_connection(os.environ['WB_DB2_CONFIG'],os.environ)
    if os.environ.get('WB_DB2_ODBC_CONNECTION'):
        return os.environ['WB_DB2_ODBC_CONNECTION']
    from workbench.db2_env import connection_string as from_env
    return from_env()


def configured_row_limit():
    if _SELECTED_ENV_FILE is not None:
        from workbench.db2_env import settings
        limit=settings({} if _SELECTED_ENV_ONLY else os.environ,_SELECTED_ENV_FILE,canonical=True).row_limit
        if _SELECTED_CONFIG_FILE is not None:
            from workbench.db2_setup import configured_max_rows
            limit=min(limit,configured_max_rows(_SELECTED_CONFIG_FILE))
        return min(500000,limit)
    if os.environ.get('WB_DB2_CONFIG'):
        from workbench.db2_setup import configured_max_rows
        return min(500000, configured_max_rows(os.environ['WB_DB2_CONFIG']))
    if os.environ.get('WB_DB2_ODBC_CONNECTION'):
        value=os.environ.get('DB2_QUERY_ROW_LIMIT','500000')
        require(value.isdigit() and 1<=int(value)<=500000,'Invalid configured row budget')
        return int(value)
    from workbench.db2_env import settings
    return settings().row_limit


def connect():
    import pyodbc
    return pyodbc.connect(connection_string(),autocommit=True,attrs_before={101:1},timeout=10)


class RowReadSessions:
    """Short-lived read cursors; no SQL mutation or caller-supplied SQL exists."""
    def __init__(self):self.sessions={};self.lock=threading.RLock()
    def close(self,token):
        with self.lock:
            entry=self.sessions.pop(token,None)
            if entry:
                entry['timer'].cancel()
                # Driver close failures must not print connection/credential text
                # from a background expiry timer. Attempt both resources.
                for resource in (entry['cursor'],entry['connection']):
                    try:resource.close()
                    except Exception:pass
    def read(self,args):
        import pyodbc
        sql,params=catalog_sql('db2_read_table_rows',args)
        with self.lock:
            token=args.get('cursor');entry=self.sessions.get(token) if token else None
            maximum=args.get('max_rows',1000);limit=args.get('limit',100)
            if token:
                require(entry is not None and entry['identity']==(args['schema'],args['table'],maximum),
                        'Table read cursor expired or differs from its exact table/row budget')
                if args.get('cancel'):
                    self.close(token)
                    return {'rows':[],'has_more':False,'next_cursor':None,'reason':'client_cancelled',
                            'bounded':True,'read_only':True,'snapshot_consistent':False}
                if maximum>configured_row_limit():
                    self.close(token)
                    return {'rows':[],'has_more':False,'next_cursor':None,'reason':'row_budget',
                            'rows_read':entry['read'],'max_rows':maximum,'bounded':True,'read_only':True,'snapshot_consistent':False}
            else:
                require(maximum<=configured_row_limit(),'Table read exceeds the configured local row budget')
                require(len(self.sessions)<16,'Concurrent table read cursor budget reached')
                if _SELECTED_ENV_FILE is None and os.environ.get('WB_DB2_CONFIG'):
                    from workbench.db2_setup import configured_max_rows
                    require(maximum<=configured_max_rows(os.environ['WB_DB2_CONFIG']),
                            'Table read exceeds the configured local row budget')
                db=pyodbc.connect(connection_string(),autocommit=True,attrs_before={101:1},timeout=10)
                try:
                    cursor=db.cursor();cursor.timeout=15;cursor.execute(sql,*params)
                    names=[column[0] for column in cursor.description]
                    require(names and all(isinstance(name,str) for name in names) and len(names)==len(set(names)),
                            'Invalid or duplicate database column names')
                except Exception:
                    db.close();raise
                token=secrets.token_hex(32)
                timer=threading.Timer(300,self.close,args=(token,));timer.daemon=True
                entry={'connection':db,'cursor':cursor,'names':names,'read':0,'maximum':maximum,
                       'identity':(args['schema'],args['table'],maximum),'timer':timer}
                self.sessions[token]=entry;timer.start()
            try:
                count=min(limit,maximum-entry['read']);rows=entry['cursor'].fetchmany(count)
                require(len(rows)<=count and all(len(row)==len(entry['names']) for row in rows),'Invalid table read row width/count')
                records=[dict(zip(entry['names'],[value if value is None or type(value)in(str,int,float,bool) else str(value) for value in row])) for row in rows]
                entry['read']+=len(records)
                capped=entry['read']>=maximum;ended=len(records)<count
                result={'rows':records,'has_more':not(capped or ended),'next_cursor':None if capped or ended else token,
                        'reason':'row_budget' if capped else 'end_of_cursor' if ended else None,
                        'rows_read':entry['read'],'max_rows':maximum,'bounded':True,'read_only':True,
                        'snapshot_consistent':False,'coverage':'account_visible_cursor_read'}
                require(len(encode(result))<=MAX_RESPONSE_BYTES-4096,'Table read page exceeds byte bound')
                if capped or ended:self.close(token)
                return result
            except Exception:
                self.close(token);raise


ROW_READS=RowReadSessions()


def execute(name,args):
    if name=='db2_read_table_rows':return ROW_READS.read(args)
    import pyodbc
    sql,params=catalog_sql(name,args)
    policy=configured_row_limit();limit=args.get('limit',100)
    require(limit<=policy,'Read exceeds configured local row budget')
    fetch_count=min(limit if name=='db2_sample_rows' else limit+1,policy)
    if name!='db2_sample_rows':
        sql=sql.replace(f'FETCH FIRST {limit+1} ROWS ONLY',f'FETCH FIRST {fetch_count} ROWS ONLY')
    from contextlib import closing
    with closing(connect()) as db:
        cursor=db.cursor();cursor.timeout=15;cursor.execute(sql,*params)
        limit=args.get('limit',100);names=[x[0] for x in cursor.description]
        require(names and all(isinstance(name,str) for name in names) and len(names)==len(set(names)),'Invalid or duplicate database column names')
        rows=cursor.fetchmany(fetch_count)
        require(len(rows)<=fetch_count,'Database returned more than the requested row bound')
        require(all(len(row)==len(names) for row in rows),'Database row width differs from its column description')
        more=len(rows)>limit or (name!='db2_sample_rows' and fetch_count==policy and len(rows)==fetch_count);rows=rows[:limit]
        records=[dict(zip(names,[v if v is None or type(v)in(str,int,float,bool) else str(v) for v in row])) for row in rows]
        next_cursor=None
        if more:
            last=records[-1]
            if name=='db2_list_schemas':next_cursor={'after_schema':last['CREATOR']}
            elif name=='db2_list_tables':next_cursor={'after_schema':last['CREATOR'],'after_table':last['NAME']}
            elif name=='db2_describe_table':next_cursor={'after_column':last['COLNO']}
        result={'rows':records,'has_more':more if name!='db2_sample_rows' else None,'next_cursor':next_cursor,
                'bounded':True,'read_only':True,'snapshot_consistent':False,
                'coverage':'sample_only' if name=='db2_sample_rows' else 'catalog_page'}
        try:encoded=encode(result)
        except (ValueError,TypeError,UnicodeError) as exc:raise ValidationError('Database response contains invalid JSON values') from exc
        require(len(encoded)<=MAX_RESPONSE_BYTES-4096,'Database response exceeds byte bound')
        return result


def tool_schema(name):
    text={'type':'string','maxLength':128}
    properties={'limit':{'type':'integer','minimum':1,'maximum':100}}
    required=[]
    if name=='db2_list_schemas':properties['after_schema']=text
    elif name=='db2_list_tables':properties.update(schema={'type':['string','null'],'maxLength':128},after_schema=text,after_table=text)
    else:
        properties.update(schema=text,table=text);required=['schema','table']
        if name=='db2_describe_table':properties['after_column']={'type':'integer','minimum':-1,'maximum':32767}
        if name=='db2_read_table_rows':
            properties['limit']={'type':'integer','minimum':1,'maximum':1000}
            properties['max_rows']={'type':'integer','minimum':1,'maximum':500000}
            properties['cursor']={'type':'string','pattern':'^[0-9a-f]{64}$'}
            properties['cancel']={'type':'boolean'}
    return {'type':'object','properties':properties,'required':required,'additionalProperties':False}


class Handler(BaseHTTPRequestHandler):
    def log_message(self,*args):pass
    def do_GET(self):
        self.send_response(405);self.send_header('Allow','POST');self.send_header('Content-Length','0');self.end_headers()
    def do_POST(self):
        request_id=None;status=400
        try:
            # Duplicate security/framing headers are ambiguous across HTTP layers.
            for header in ('Host','Origin','Authorization','Content-Length','Content-Type','MCP-Protocol-Version'):
                require(len(self.headers.get_all(header,[]))<=1,'Duplicate request header')
            require(self.headers.get('Transfer-Encoding') is None,'Transfer encoding is unsupported')
            require(self.headers.get('Content-Type','').split(';',1)[0].strip().lower()=='application/json','JSON content type required')
            port=self.server.server_port
            require(self.headers.get('Host') in (f'127.0.0.1:{port}',f'localhost:{port}',f'[::1]:{port}'),'Invalid local host')
            origin=self.headers.get('Origin')
            require(origin is None or origin in (f'http://127.0.0.1:{port}',f'http://localhost:{port}',f'http://[::1]:{port}'),'Invalid origin')
            token=os.environ.get('WB_DB2_MCP_TOKEN');require(token and self.headers.get('Authorization')=='Bearer '+token,'Authentication required')
            length=int(self.headers.get('Content-Length','0'));require(0<length<=64000,'Invalid request length')
            body=decode(self.rfile.read(length));require(isinstance(body,dict) and body.get('jsonrpc')=='2.0','Invalid JSON-RPC envelope')
            method=body.get('method');params=body.get('params',{});require(isinstance(params,dict),'Invalid parameters')
            if 'id' in body:
                require(type(body['id']) in (int,str),'Invalid request identity');request_id=body['id']
            protocol=self.headers.get('MCP-Protocol-Version','2025-03-26')
            require(protocol in MCP_VERSIONS,'Unsupported protocol header')
            if method=='notifications/initialized':
                require('id' not in body,'Initialized is a notification')
                self.send_response(202);self.send_header('Content-Length','0');self.end_headers();return
            require('id' in body,'Request identity required')
            if method=='initialize':
                requested=params.get('protocolVersion');require(isinstance(requested,str),'Protocol version required')
                protocol=requested if requested in MCP_VERSIONS else MCP_VERSIONS[0]
                result={'protocolVersion':protocol,'capabilities':{'tools':{}},'serverInfo':{'name':'workbench-db2-read-only','version':'0.2.0'}}
            elif method=='tools/list':
                require(not params,'Tool list is a single page')
                result={'tools':[{'name':name,'description':'Bounded read-only Db2 metadata/sample operation','inputSchema':tool_schema(name),'annotations':{'readOnlyHint':True,'destructiveHint':False}} for name in sorted(READ_TOOLS)]}
            elif method=='tools/call':
                require(set(params)<= {'name','arguments'} and params.get('name') in READ_TOOLS,'Unsupported operation')
                args=params.get('arguments',{});catalog_sql(params['name'],args)
                try:
                    content=execute(params['name'],args)
                    result={'content':[{'type':'text','text':encode(content).decode()}]}
                    if protocol=='2025-06-18':result['structuredContent']=content
                except Exception:result={'isError':True,'content':[{'type':'text','text':'Read operation failed. Check private driver/account settings.'}]}
            else:raise ValidationError('Unsupported protocol operation')
            data=encode({'jsonrpc':'2.0','id':request_id,'result':result});require(len(data)<=MAX_RESPONSE_BYTES,'Response exceeds byte bound');status=200
        except Exception:
            data=encode({'jsonrpc':'2.0','id':request_id,'error':{'code':-32000,'message':'Read operation failed. Check private protocol/driver/account settings.'}})
        self.send_response(status)
        self.send_header('Content-Type','application/json');self.send_header('Content-Length',str(len(data)));self.end_headers();self.wfile.write(data)


class LocalSecurity:
    """Protect the HTTP transport before SDK parsing, including sessions/streams."""
    def __init__(self, app, port, token):
        self.app,self.port,self.token=app,port,token
    async def __call__(self, scope, receive, send):
        if scope['type']!='http': return await self.app(scope,receive,send)
        headers={}; invalid=False
        for key,value in scope['headers']:
            key=key.lower()
            if key in headers and key in (b'host',b'origin',b'authorization',b'content-length',b'content-type',b'mcp-protocol-version',b'mcp-session-id'):
                invalid=True
            headers[key]=value
        hosts={f'127.0.0.1:{self.port}'.encode(),f'localhost:{self.port}'.encode(),f'[::1]:{self.port}'.encode()}
        origin=headers.get(b'origin')
        authorized=secrets.compare_digest(headers.get(b'authorization',b''),('Bearer '+self.token).encode())
        if invalid or headers.get(b'host') not in hosts or (origin is not None and origin not in {b'http://'+h for h in hosts}) or not authorized:
            await send({'type':'http.response.start','status':403,'headers':[(b'content-length',b'0')]})
            return await send({'type':'http.response.body','body':b''})
        if scope['method']=='POST':
            body=b''
            while True:
                message=await receive()
                if message['type']=='http.disconnect': return
                body+=message.get('body',b'')
                if len(body)>64000:
                    await send({'type':'http.response.start','status':413,'headers':[(b'content-length',b'0')]})
                    return await send({'type':'http.response.body','body':b''})
                if not message.get('more_body'): break
            delivered=False
            original_receive=receive
            async def replay():
                nonlocal delivered
                if not delivered:
                    delivered=True
                    return {'type':'http.request','body':body,'more_body':False}
                return await original_receive()
            receive=replay
        return await self.app(scope,receive,send)


def create_server(search_root=None,*,workspace=None,protected=True):
    from contextlib import asynccontextmanager
    from fastmcp import FastMCP
    from workbench.db2_discovery import SearchStore
    stores=[]; store_lock=threading.RLock()
    def store():
        with store_lock:
            if not stores:
                root=search_root or Path(__file__).resolve().parents[1]/'.migration/db2-search'
                stores.append(SearchStore(root,connect,configured_row_limit))
            return stores[0]
    @asynccontextmanager
    async def lifespan(server):
        try: yield {}
        finally:
            for item in stores: item.close()
            stores.clear()
            for token in list(ROW_READS.sessions): ROW_READS.close(token)
    server=FastMCP('workbench-db2-read-only',version='1.0.0',mask_error_details=True,
                  strict_input_validation=True,lifespan=lifespan,
                  instructions=('Approved structural metadata only. Customer records never enter tool responses. '
                                'Explicit Coordinator snapshot requests use db2_export_snapshot_to_inbox for local private files. '
                                'No raw row/sample/content search tools, free-form SQL, writes or parity claims.' if protected else
                                'Historical read-only compatibility mode; never expose its business records to Claude.'))
    annotations={'readOnlyHint':True,'destructiveHint':False,'openWorldHint':True}
    def register(function):
        if protected and function.__name__ in {'db2_sample_rows','db2_read_table_rows',*{'db2_search_'+suffix for suffix in ('start','continue','status','results','cancel')}}:
            return function
        if not protected and function.__name__=='db2_export_snapshot_to_inbox':return function
        from functools import wraps
        from fastmcp.exceptions import ToolError
        @wraps(function)
        def safe(*args,**kwargs):
            try: return function(*args,**kwargs)
            except Exception:
                raise ToolError('Read operation failed. Check private configuration or search identity and bounds.') from None
        server.tool(safe,annotations=annotations)
        return safe
    @register
    def db2_list_schemas(after_schema: str='', limit: int=100) -> dict:
        """List local schemas with keyset continuation."""
        result=execute('db2_list_schemas',locals())
        return protected_metadata('db2_list_schemas',result) if protected else result
    @register
    def db2_list_tables(schema: str | None=None, after_schema: str='', after_table: str='', limit: int=100) -> dict:
        """List local tables, views and aliases across schemas; no default schema filter."""
        result=execute('db2_list_tables',locals())
        return protected_metadata('db2_list_tables',result) if protected else result
    @register
    def db2_describe_table(schema: str, table: str, after_column: int=-1, limit: int=100) -> dict:
        """Describe a local table's columns."""
        result=execute('db2_describe_table',locals())
        return protected_metadata('db2_describe_table',result) if protected else result
    @register
    def db2_export_snapshot_to_inbox(process_id: str, request_id: str, need_id: str) -> dict:
        """Export authorized private rows into the exact local inbox; return counts/hash/path only."""
        return export_snapshot_to_inbox(workspace,process_id,request_id,need_id)
    @register
    def db2_sample_rows(schema: str, table: str, limit: int=10) -> dict:
        """Small explicit sample; samples do not establish completeness."""
        return execute('db2_sample_rows',locals())
    @register
    def db2_read_table_rows(schema: str, table: str, limit: int=100, max_rows: int=500000, cursor: str | None=None, cancel: bool=False) -> dict:
        """Read one local table through a bounded live cursor. Cap applies across calls."""
        args=locals().copy()
        if cursor is None: args.pop('cursor')
        return execute('db2_read_table_rows',args)
    @register
    def db2_search_start(query: str) -> dict:
        """Search literal phrase in all catalog-visible names and all selectable table contents, across advertised DDF locations. Continue to perform work; page results separately. Numeric/date values use their text representation; binary values use hex. The configured cap applies per query."""
        return store().start(query)
    @register
    def db2_search_continue(search_id: str, row_budget: int=1000) -> dict:
        """Perform the next bounded search batch; keep calling while RUNNING."""
        return store().advance(search_id,row_budget)
    @register
    def db2_search_status(search_id: str) -> dict:
        """Read durable progress counts and honest account-visible coverage."""
        return store().status(search_id)
    @register
    def db2_search_results(search_id: str, after: int=0, limit: int=100, kind: str='matches') -> dict:
        """Page matches or objects (per-object coverage/reason). Pass next_after to continue."""
        return store().results(search_id,after,limit,kind)
    @register
    def db2_search_cancel(search_id: str) -> dict:
        """Close this search's live cursors and retain partial results and outcomes."""
        return store().cancel(search_id)
    return server


def main():
    global _SELECTED_ENV_FILE,_SELECTED_CONFIG_FILE,_SELECTED_DRIVER_NAME,_SELECTED_ENV_ONLY
    import argparse
    import getpass
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--transport',choices=('stdio','http'),default='stdio')
    parser.add_argument('--config',help='Exact nonsecret workspace Db2 configuration prepared by setup')
    parser.add_argument('--env-file',help='Exact private workspace .env; supplies literal z/OS connection fields and private credentials')
    parser.add_argument('--port',type=int,help='Approved loopback MCP port')
    parser.add_argument('--driver',help='Exact approved registered IBM Db2 ODBC driver for an explicit private .env')
    parser.add_argument('--workspace',help='Approved local evidence workspace for protected exact-inbox exports')
    parser.add_argument('--interactive',action='store_true',help='Enter credentials privately in this local terminal for HTTP startup')
    args=parser.parse_args()
    require(not args.interactive or args.transport=='http' and (args.config or args.env_file) and sys.stdin.isatty(),
            'Interactive Db2 startup requires HTTP, selected local settings and your local terminal')
    require(args.port is None or 1<=args.port<=65535,'Invalid loopback MCP port')
    require(args.driver is None or args.env_file is not None,'An explicit driver requires the selected private .env')
    changes={}
    previous_selection=(_SELECTED_ENV_FILE,_SELECTED_CONFIG_FILE,_SELECTED_DRIVER_NAME,_SELECTED_ENV_ONLY)
    def local(name,value):
        changes.setdefault(name,os.environ.get(name))
        os.environ[name]=value
    try:
        _SELECTED_ENV_FILE=Path(args.env_file).absolute() if args.env_file else None
        _SELECTED_CONFIG_FILE=Path(args.config).absolute() if args.config else None
        from workbench.db2_setup import _stdio_driver
        _SELECTED_DRIVER_NAME=_stdio_driver(args.driver) if args.driver is not None else None
        _SELECTED_ENV_ONLY=bool(args.env_file and args.transport=='stdio')
        search_root=None
        if args.config:
            from workbench.db2_env import _read
            from workbench.db2_setup import _config, configured_max_rows, connection_fields
            config_path=Path(args.config).absolute()
            configured_max_rows(config_path)
            config=_config(decode(_read(config_path,1024*1024),1024*1024))
            local('WB_DB2_CONFIG',str(config_path))
            search_root=config_path.parent/'db2-search'
            if args.interactive and not args.env_file:
                connection_fields(config)
                from workbench.db2_env import validate_certificate
                from workbench.db2_setup import CERTIFICATE
                workspace=config_path.parent.parent if config_path.parent.name=='.migration' else config_path.parent
                from workbench.domain import safe_path
                validate_certificate(_read(safe_path(workspace,CERTIFICATE),1024*1024))
                try:
                    import pyodbc
                    drivers=pyodbc.drivers()
                except Exception:
                    raise ValidationError('Install the organization-approved pyodbc package and IBM Db2 ODBC driver before starting the MCP server') from None
                require(isinstance(drivers,list) and any(isinstance(driver,str) and driver.casefold()==config['driver'].casefold() for driver in drivers),
                        'The selected Db2 ODBC driver is not registered locally; install the approved driver or correct setup')
                for name,prompt,secret in (('WB_DB2_USER','Read-only Db2 username: ',False),
                                           ('WB_DB2_PASSWORD','Db2 password: ',True),
                                           ('WB_DB2_MCP_TOKEN','Approved MCP token (also enter in the Claude launcher): ',True)):
                    if not os.environ.get(name):local(name,getpass.getpass(prompt) if secret else input(prompt))
                # Validate local TLS and credential representation; never connect here.
                from workbench.db2_setup import load_connection
                load_connection(config_path,os.environ)
        if args.env_file:
            from workbench.db2_env import settings,_certificate
            # Local file parsing and certificate checks precede all prompts.
            # This never connects, writes .env, or exposes its contents as tools.
            configured=settings({} if _SELECTED_ENV_ONLY else os.environ,_SELECTED_ENV_FILE,canonical=True)
            _certificate(configured.certificate)
            configured_row_limit()
            driver=_selected_env_driver()
            if args.interactive:
                try:
                    import pyodbc
                    drivers=pyodbc.drivers()
                except Exception:
                    raise ValidationError('Install the organization-approved pyodbc package and IBM Db2 ODBC driver before starting the MCP server') from None
                require(isinstance(drivers,list) and any(isinstance(value,str) and value.casefold()==driver.casefold() for value in drivers),
                        'The selected Db2 ODBC driver is not registered locally; install the approved driver or correct setup')
                for name,prompt,secret,current in (
                    ('DB2_USERNAME','Read-only Db2 username: ',False,configured.username),
                    ('DB2_PASSWORD','Db2 password: ',True,configured.password),
                    ('WB_DB2_MCP_TOKEN','Approved MCP token (also enter in the Claude launcher): ',True,os.environ.get('WB_DB2_MCP_TOKEN',''))):
                    if not current:local(name,getpass.getpass(prompt) if secret else input(prompt))
            connection_string()
        if args.port is not None:local('WB_DB2_MCP_PORT',str(args.port))
        export_workspace=Path(args.workspace).absolute() if args.workspace else None
        if export_workspace is None and args.config:
            export_workspace=config_path.parent.parent if config_path.parent.name=='.migration' else config_path.parent
        elif export_workspace is None and args.env_file:
            export_workspace=_SELECTED_ENV_FILE.parent
        server=create_server(search_root=search_root,workspace=export_workspace)
        if args.transport=='stdio':server.run(transport='stdio',show_banner=False)
        else:
            from starlette.middleware import Middleware
            token=os.environ.get('WB_DB2_MCP_TOKEN','')
            require(isinstance(token,str) and 0<len(token)<=8192 and all(33<=ord(char)<=126 for char in token),
                    'Set a private printable WB_DB2_MCP_TOKEN before launching HTTP')
            port_text=os.environ.get('WB_DB2_MCP_PORT','8766')
            require(port_text.isdigit() and 1<=int(port_text)<=65535,'Invalid loopback MCP port')
            port=int(port_text)
            server.run(transport='http',host='127.0.0.1',port=port,path='/mcp',show_banner=False,
                       json_response=True,stateless_http=True,
                       middleware=[Middleware(LocalSecurity,port=port,token=token)],
                       host_origin_protection=True,
                       allowed_hosts=[f'127.0.0.1:{port}',f'localhost:{port}',f'[::1]:{port}'],
                       allowed_origins=[f'http://127.0.0.1:{port}',f'http://localhost:{port}',f'http://[::1]:{port}'])
    finally:
        _SELECTED_ENV_FILE,_SELECTED_CONFIG_FILE,_SELECTED_DRIVER_NAME,_SELECTED_ENV_ONLY=previous_selection
        for name,previous in changes.items():
            if previous is None:os.environ.pop(name,None)
            else:os.environ[name]=previous


if __name__=='__main__':
    try:main()
    except (EOFError,KeyboardInterrupt):
        print('Db2 MCP startup cancelled.',file=sys.stderr)
        raise SystemExit(130)
    except (ValidationError,OSError,ImportError):
        print('Db2 MCP startup blocked. Check the local setup, approved driver, certificate and private credentials.',file=sys.stderr)
        raise SystemExit(2)
