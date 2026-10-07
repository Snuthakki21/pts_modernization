"""Typed, bounded read-only source access. No free-form shell or SQL tool."""
import json
import hashlib
import os
import re
import subprocess
import threading
import time
from datetime import datetime, timezone
import urllib.request
from urllib.parse import urlsplit
from .domain import require, decode, encode, ValidationError
from .limits import MAX_SOURCE_FILE_BYTES, MAX_JSON_DOCUMENT_BYTES

READ_TOOLS={'db2_list_schemas','db2_list_tables','db2_describe_table','db2_sample_rows','db2_read_table_rows'}
SEARCH_TOOLS={'db2_search_start','db2_search_continue','db2_search_status','db2_search_results','db2_search_cancel'}
MCP_VERSIONS=('2025-06-18','2025-03-26')
MAX_RESPONSE_BYTES=1024*1024
MAX_ZOWE_SOURCE_RESPONSE_BYTES=MAX_JSON_DOCUMENT_BYTES


def endpoint(url):
    require(isinstance(url,str) and 0<len(url)<=8192 and not any(c.isspace() or ord(c)<32 or ord(c)==127 or c=='\\' for c in url),'Use an unambiguous HTTP(S) endpoint')
    try:
        parts=urlsplit(url)
        port=parts.port
    except ValueError as exc:raise ValidationError('Invalid HTTP(S) endpoint authority or port') from exc
    require(parts.scheme in ('http','https') and parts.hostname and not parts.username and not parts.password and not parts.fragment,'Use a configured HTTP(S) endpoint without embedded credentials')
    require(port is None or 1<=port<=65535,'Invalid HTTP(S) endpoint port')
    require(parts.scheme=='https' or parts.hostname in ('localhost','127.0.0.1','::1'),'Plain HTTP is allowed only on loopback')
    return url


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,*args,**kwargs):raise ValidationError('Endpoint redirects require explicit configuration; credentials will not be forwarded')


def _sse_response(response,request_id):
    """Consume bounded SSE events until this request's response, not stream EOF."""
    total=0;fields=[]
    while True:
        line=response.readline(MAX_RESPONSE_BYTES-total+1)
        total+=len(line);require(total<=MAX_RESPONSE_BYTES,'Remote response exceeds bound')
        if line.strip()==b'' or not line:
            if fields:
                message=decode(b'\n'.join(fields),MAX_RESPONSE_BYTES);fields=[]
                require(isinstance(message,dict),'Invalid SSE JSON-RPC message')
                if type(message.get('id')) is type(request_id) and message.get('id')==request_id and ('result' in message or 'error' in message):return message
                require('id' not in message,'Unsolicited server requests are unsupported')
            if not line:break
        elif line.startswith(b'data:'):fields.append(line[5:].lstrip(b' ').rstrip(b'\r\n'))
    raise ValidationError('SSE stream ended without the matching response')


def post_json(url,body,token='',headers=None,timeout=20):
    endpoint(url)
    h={'Content-Type':'application/json','Accept':'application/json, text/event-stream',**(headers or {})}
    if token:h['Authorization']='Bearer '+token
    request=urllib.request.Request(url,data=encode(body),headers=h,method='POST')
    try:
        with urllib.request.build_opener(NoRedirect()).open(request,timeout=timeout) as response:
            response_headers={k.lower():v for k,v in response.headers.items()}
            content_type=response_headers.get('content-type','').split(';',1)[0].strip().lower()
            if content_type=='text/event-stream':
                require('id' in body,'Notification response must not open an SSE stream')
                return _sse_response(response,body['id']),response_headers
            data=response.read(MAX_RESPONSE_BYTES+1);require(len(data)<=MAX_RESPONSE_BYTES,'Remote response exceeds bound')
            if not data:return {},response_headers
            require(content_type=='application/json','Unsupported response content type')
            return decode(data,MAX_RESPONSE_BYTES),response_headers
    except ValidationError:raise
    except Exception as exc:raise ValidationError('Configured endpoint could not complete the bounded request; check private endpoint/auth/trust settings') from exc


class Db2MCP:
    def __init__(self,url,token=''):
        self.url=endpoint(url);self.token=token;self.counter=0;self.session=None;self.tools=set();self.protocol=None;self.timeout=20;self.deadline=None
    def bounded_timeout(self):
        if self.deadline is None:return self.timeout
        remaining=self.deadline-time.monotonic();require(remaining>0,'Db2 read deadline reached')
        return min(self.timeout,remaining)
    def headers(self):
        # Initialization negotiates in its body. Only subsequent requests send
        # the negotiated header, so an older server can return its own version.
        headers={'MCP-Protocol-Version':self.protocol} if self.protocol else {}
        if self.session:headers['Mcp-Session-Id']=self.session
        return headers
    def rpc(self,method,params):
        require(method in ('initialize','tools/list','tools/call') and isinstance(params,dict),'Only the read-only MCP protocol operations are allowed')
        if method=='tools/call':
            require(set(params)<={'name','arguments'} and isinstance(params.get('name'),str),'Invalid MCP read operation')
            validate_read_operation(params['name'],params.get('arguments',{}))
        require(method=='initialize' or self.protocol in MCP_VERSIONS,'Initialize and negotiate MCP before calling tools')
        self.counter+=1
        result,h=post_json(self.url,{'jsonrpc':'2.0','id':self.counter,'method':method,'params':params},self.token,self.headers(),timeout=self.bounded_timeout())
        require(isinstance(result,dict) and result.get('jsonrpc')=='2.0' and type(result.get('id')) is int and result['id']==self.counter and 'result' in result and 'error' not in result,'Invalid MCP response identity or operation failure')
        session=next((v for k,v in h.items() if k.lower()=='mcp-session-id'),None)
        if session is not None:
            require(isinstance(session,str) and 0<len(session)<=512 and all(33<=ord(c)<=126 for c in session),'Invalid MCP session identifier')
            require(method=='initialize' or session==self.session,'MCP session changed unexpectedly')
            self.session=session
        return result['result']
    def initialize(self):
        self.protocol=None;self.session=None;self.tools=set()
        result=self.rpc('initialize',{'protocolVersion':MCP_VERSIONS[0],'capabilities':{},'clientInfo':{'name':'mainframe-workbench','version':'0.1.0'}})
        require(isinstance(result,dict) and result.get('protocolVersion') in MCP_VERSIONS,'Unsupported MCP protocol version returned by server')
        require(isinstance(result.get('capabilities'),dict) and isinstance(result['capabilities'].get('tools'),dict),'MCP server does not advertise tools')
        self.protocol=result['protocolVersion']
        notification,_=post_json(self.url,{'jsonrpc':'2.0','method':'notifications/initialized'},self.token,self.headers(),timeout=self.bounded_timeout())
        require(not notification,'Initialized notification must not return a JSON-RPC result')
        cursor=None;seen=set()
        for _ in range(20):
            listing=self.rpc('tools/list',{'cursor':cursor} if cursor else {})
            require(isinstance(listing,dict) and isinstance(listing.get('tools'),list),'Invalid MCP tool listing')
            require(all(isinstance(x,dict) and isinstance(x.get('name'),str) for x in listing['tools']),'Invalid MCP tool entry')
            self.tools.update(x['name'] for x in listing['tools'])
            require(len(self.tools)<=2000,'MCP tool listing exceeds bound')
            cursor=listing.get('nextCursor')
            if cursor is None:break
            require(isinstance(cursor,str) and 0<len(cursor)<=2048 and cursor not in seen,'Invalid or repeated MCP tool cursor')
            seen.add(cursor)
        else:raise ValidationError('MCP tool listing exceeds page budget')
        require({'db2_list_schemas','db2_list_tables'}<=self.tools,'MCP server needs exploratory schema/table tools; configure the supplied read-only gateway or a compatible server')
        return {'status':'CONNECTED','protocol_version':self.protocol,'read_tools':sorted(self.tools & (READ_TOOLS | SEARCH_TOOLS))}
    def call(self,name,args):
        require(name in READ_TOOLS | SEARCH_TOOLS,'Only the explicit read-only Db2 operations are allowed')
        require(name in self.tools,'Required read capability is unavailable')
        validate_read_operation(name,args)
        result=self.rpc('tools/call',{'name':name,'arguments':args})
        require(isinstance(result,dict) and result.get('isError',False) is False,'Db2 read failed')
        if 'structuredContent' in result:
            require(isinstance(result['structuredContent'],dict),'Db2 structured data must be an object')
            return result['structuredContent']
        content=result.get('content',[])
        require(isinstance(content,list) and all(isinstance(c,dict) for c in content),'Invalid Db2 content blocks')
        for c in content:
            if c.get('type')=='text':
                require(isinstance(c.get('text'),str),'Db2 text content must be a string')
                try:data=decode(c['text'].encode(),MAX_RESPONSE_BYTES)
                except UnicodeError as exc:raise ValidationError('Db2 text content must be valid UTF-8') from exc
                require(isinstance(data,dict),'Db2 structured data must be an object')
                return data
        raise ValidationError('Db2 tool returned no structured data')
    def list_schemas(self,after_schema=''):return self.call('db2_list_schemas',{'after_schema':after_schema,'limit':100})
    def list_tables(self,schema=None,after_schema='',after_table=''):
        return self.call('db2_list_tables',{'schema':schema,'after_schema':after_schema,'after_table':after_table,'limit':100})
    def describe(self,schema,table,after_column=-1):return self.call('db2_describe_table',{'schema':schema,'table':table,'after_column':after_column})
    def sample(self,schema,table,limit=10):return self.call('db2_sample_rows',{'schema':schema,'table':table,'limit':limit})
    def read_table_rows(self,schema,table,limit=100,max_rows=1000,cursor=None,cancel=False):
        require(type(cancel)is bool,'Typed cancellation must be boolean')
        return self.call('db2_read_table_rows',{'schema':schema,'table':table,'limit':limit,'max_rows':max_rows,
                         **({'cursor':cursor} if cursor is not None else {}),**({'cancel':True} if cancel else {})})

    def search_start(self,query):return self.call('db2_search_start',{'query':query})
    def search_continue(self,search_id,row_budget=1000):return self.call('db2_search_continue',{'search_id':search_id,'row_budget':row_budget})
    def search_status(self,search_id):return self.call('db2_search_status',{'search_id':search_id})
    def search_results(self,search_id,after=0,limit=100,kind='matches'):
        return self.call('db2_search_results',{'search_id':search_id,'after':after,'limit':limit,'kind':kind})
    def search_cancel(self,search_id):return self.call('db2_search_cancel',{'search_id':search_id})


def validate_read_operation(name,args):
    if name in READ_TOOLS:return catalog_sql(name,args)
    require(name in SEARCH_TOOLS and isinstance(args,dict),'Unsupported read operation')
    allowed={'db2_search_start':{'query'},'db2_search_continue':{'search_id','row_budget'},
             'db2_search_status':{'search_id'},'db2_search_results':{'search_id','after','limit','kind'},
             'db2_search_cancel':{'search_id'}}
    require(set(args)<=allowed[name],'Unsupported search argument')
    if name=='db2_search_start':
        q=args.get('query');require(isinstance(q,str) and bool(q.strip()) and len(q)<=256 and '\x00' not in q,'Invalid literal search phrase')
    else:
        token=args.get('search_id');require(isinstance(token,str) and re.fullmatch('[0-9a-f]{64}',token),'Invalid search identity')
    if name=='db2_search_continue':
        n=args.get('row_budget',1000);require(type(n)is int and 1<=n<=1000,'Invalid search batch limit')
    if name=='db2_search_results':
        n=args.get('limit',100);a=args.get('after',0)
        require(type(n)is int and 1<=n<=100 and type(a)is int and a>=0 and args.get('kind','matches') in ('matches','objects'),'Invalid search page')


def sql_name(value):
    require(isinstance(value,str) and re.fullmatch(r'[A-Za-z@$#][A-Za-z0-9_@$#]{0,127}',value),'Unsupported/unsafe SQL identifier')
    return '"'+value+'"'


def catalog_sql(operation,args):
    require(operation in READ_TOOLS,'No arbitrary or mutating SQL operations are exposed')
    require(isinstance(args,dict),'Read arguments must be an object')
    allowed={
        'db2_list_schemas':{'limit','after_schema'},
        'db2_list_tables':{'limit','schema','after_schema','after_table'},
        'db2_describe_table':{'limit','schema','table','after_column'},
        'db2_sample_rows':{'limit','schema','table'},
        'db2_read_table_rows':{'limit','schema','table','max_rows','cursor','cancel'},
    }
    require(set(args)<=allowed[operation],'Unsupported read argument')
    limit=args.get('limit',100);upper=1000 if operation=='db2_read_table_rows' else 100
    require(type(limit)is int and 1<=limit<=upper,'Read row limit is outside its typed operation bound')
    if operation=='db2_list_schemas':
        after=args.get('after_schema','');require(isinstance(after,str) and len(after)<=128,'Invalid schema cursor')
        return f'SELECT DISTINCT CREATOR FROM SYSIBM.SYSTABLES WHERE CREATOR > ? ORDER BY CREATOR FETCH FIRST {limit+1} ROWS ONLY WITH UR',[after]
    if operation=='db2_list_tables':
        schema=args.get('schema')
        require(schema is None or isinstance(schema,str) and len(schema)<=128,'Invalid schema pattern')
        pattern=schema if schema else '%'
        a,b=args.get('after_schema',''),args.get('after_table','')
        require(isinstance(a,str) and isinstance(b,str) and len(a)<=128 and len(b)<=128,'Invalid catalog cursor')
        return f"SELECT CREATOR,NAME,TYPE FROM SYSIBM.SYSTABLES WHERE CREATOR LIKE ? AND (CREATOR > ? OR (CREATOR = ? AND NAME > ?)) ORDER BY CREATOR,NAME FETCH FIRST {limit+1} ROWS ONLY WITH UR",[pattern,a,a,b]
    schema,table=args.get('schema'),args.get('table');s,t=sql_name(schema),sql_name(table)
    if operation=='db2_read_table_rows':
        maximum=args.get('max_rows',1000);cursor=args.get('cursor')
        require(type(maximum)is int and 1<=maximum<=500000,'Table export row budget must be 1..500000')
        require(cursor is None or isinstance(cursor,str) and re.fullmatch(r'[0-9a-f]{64}',cursor),'Invalid table export continuation')
        require(type(args.get('cancel',False)) is bool and (not args.get('cancel') or cursor is not None),'Cancel requires an existing typed table continuation')
        return f'SELECT * FROM {s}.{t} FETCH FIRST {maximum} ROWS ONLY WITH UR',[]
    if operation=='db2_describe_table':
        after=args.get('after_column',-1);require(type(after)is int and -1<=after<=32767,'Invalid column cursor')
        return f'SELECT NAME,COLTYPE,LENGTH,SCALE,NULLS,COLNO FROM SYSIBM.SYSCOLUMNS WHERE TBCREATOR=? AND TBNAME=? AND COLNO > ? ORDER BY COLNO FETCH FIRST {limit+1} ROWS ONLY WITH UR',[schema,table,after]
    return f'SELECT * FROM {s}.{t} FETCH FIRST {limit} ROWS ONLY WITH UR',[]


def discover_catalog(client,kind,max_pages=10,max_bytes=2*1024*1024,max_seconds=60,continuation=None):
    """Follow the supplied gateway's keyset cursors within explicit budgets."""
    require(kind in ('schemas','tables') and type(max_pages)is int and 1<=max_pages<=50,'Invalid catalog page budget')
    require(type(max_bytes)is int and 1024<=max_bytes<=8*1024*1024 and type(max_seconds) in (int,float) and 0<max_seconds<=300,'Invalid catalog resource budget')
    output={'rows':[],'pages':0,'coverage':'PARTIAL','reason':'page_budget','next_cursor':None,
            'bounded':True,'snapshot_consistent':False,'scope':'Account-visible catalog traversal, not an authorization inventory or consistent snapshot',
            'budgets':{'max_pages':max_pages,'max_bytes':max_bytes,'max_seconds':max_seconds}}
    cursor=continuation or {}
    require(isinstance(cursor,dict),'Invalid initial catalog continuation')
    catalog_sql('db2_list_schemas' if kind=='schemas' else 'db2_list_tables',cursor)
    output['next_cursor']=cursor or None
    seen=set();size=0;deadline=time.monotonic()+max_seconds;old_timeout=client.timeout
    try:
        for _ in range(max_pages):
            remaining=deadline-time.monotonic()
            if remaining<=0:output['reason']='time_budget';break
            client.timeout=min(old_timeout,remaining)
            try:page=client.list_schemas(**cursor) if kind=='schemas' else client.list_tables(**cursor)
            except ValidationError:
                output['reason']='page_read_failed';break
            if not isinstance(page,dict) or not isinstance(page.get('rows'),list) or len(page['rows'])>100 or not all(isinstance(row,dict) for row in page['rows']):
                output['reason']='invalid_page';break
            try:page_size=len(encode(page))
            except (ValueError,TypeError,UnicodeError,RecursionError):
                output['reason']='invalid_page';break
            if size+page_size>max_bytes:output['reason']='byte_budget';break
            # Reject a repeated continuation before adding the repeated page.
            if page.get('has_more') is True and isinstance(page.get('next_cursor'),dict) and encode(page['next_cursor']) in seen:
                output.update(reason='repeated_cursor',next_cursor=None);break
            size+=page_size;output['pages']+=1;output['rows'].extend(page['rows'])
            more=page.get('has_more')
            if more is False:
                output.update(coverage='COMPLETE',reason=None,next_cursor=None);break
            if more is not True:
                output.update(reason='continuation_unavailable',next_cursor=None);break
            next_cursor=page.get('next_cursor');keys={'after_schema'} if kind=='schemas' else {'after_schema','after_table'}
            if not isinstance(next_cursor,dict) or set(next_cursor)!=keys or not all(isinstance(v,str) and 0<len(v)<=128 for v in next_cursor.values()):
                output.update(reason='invalid_cursor',next_cursor=None);break
            fingerprint=encode(next_cursor)
            if fingerprint in seen or next_cursor==cursor:
                output.update(reason='repeated_cursor',next_cursor=None);break
            seen.add(fingerprint);cursor=next_cursor;output['next_cursor']=cursor
        output['bytes']=size
        return output
    finally:client.timeout=old_timeout


def export_table_rows(client,schema,table,output,max_rows=1000,page_size=100,
                      max_bytes=512*1024*1024,max_seconds=300):
    """Explicitly stream one bounded table read to a new local NDJSON file.

    No allowlist or automatic sampling is involved. An open Db2 cursor avoids
    re-querying unordered OFFSET pages, but WITH UR is not a consistent snapshot.
    Hitting any limit remains partial and does not establish table completeness.
    """
    from pathlib import Path
    catalog_sql('db2_read_table_rows',{'schema':schema,'table':table,'limit':page_size,'max_rows':max_rows})
    require(type(max_bytes)is int and 1024<=max_bytes<=2*1024*1024*1024,'Invalid table export byte budget')
    require(type(max_seconds) in (int,float) and 0<max_seconds<=3600,'Invalid table export time budget')
    path=Path(output).absolute()
    require(not path.exists() and not path.is_symlink() and not any(p.is_symlink() for p in path.parents),
            'Table export requires a new regular output path')
    path.parent.mkdir(parents=True,exist_ok=True)
    result={'status':'PARTIAL','coverage':'PARTIAL','reason':'row_budget','schema':schema,'table':table,
            'rows':0,'pages':0,'bytes':0,'max_rows':max_rows,'max_bytes':max_bytes,'max_seconds':max_seconds,
            'read_only':True,'snapshot_consistent':False,'output':str(path),
            'scope':'One account-visible cursor read; uncommitted reads do not establish a consistent business snapshot'}
    cursor=None;deadline=time.monotonic()+max_seconds;digest=hashlib.sha256()
    old_timeout=client.timeout
    try:
        with path.open('xb') as out:
            while result['rows']<max_rows:
                remaining=deadline-time.monotonic()
                if remaining<=0:result['reason']='time_budget';break
                client.timeout=min(old_timeout,remaining)
                try:page=client.read_table_rows(schema,table,limit=page_size,max_rows=max_rows,cursor=cursor)
                except (ValidationError,OSError):result['reason']='page_read_failed';break
                require(isinstance(page,dict) and isinstance(page.get('rows'),list) and len(page['rows'])<=page_size
                        and all(isinstance(row,dict) for row in page['rows']),'Invalid typed table read page')
                require(result['rows']+len(page['rows'])<=max_rows,'Table read exceeds its row budget')
                more=page.get('has_more');require(type(more)is bool,'Table read must declare continuation')
                continuation=page.get('next_cursor')
                require(not more or isinstance(continuation,str) and re.fullmatch(r'[0-9a-f]{64}',continuation),
                        'Invalid typed table read continuation')
                if more:
                    require(page['rows'],'Empty table read page cannot continue')
                    # A stable token is the same cursor, not a keyset page cursor.
                    require(cursor is None or cursor==continuation,'Table cursor identity changed during export')
                    cursor=continuation
                payload=b''.join((json.dumps(row,ensure_ascii=False,allow_nan=False,separators=(',',':'))+'\n').encode('utf-8') for row in page['rows'])
                if result['bytes']+len(payload)>max_bytes:result['reason']='byte_budget';break
                out.write(payload);digest.update(payload);result['bytes']+=len(payload)
                result['rows']+=len(page['rows']);result['pages']+=1
                if result['rows']>=max_rows:
                    result['reason']='row_budget'
                    if not more:cursor=None
                    break
                if not more:
                    cursor=None
                    if page.get('reason')=='end_of_cursor':result.update(status='READ_COMPLETED',coverage='COMPLETE',reason=None)
                    else:result['reason']=page.get('reason','continuation_unavailable')
                    break
    except (ValidationError,ValueError,TypeError,UnicodeError):result['reason']='invalid_page'
    finally:
        client.timeout=old_timeout
        if cursor is not None:
            try:client.read_table_rows(schema,table,limit=page_size,max_rows=max_rows,cursor=cursor,cancel=True)
            except (ValidationError,OSError):pass
    result['sha256']=digest.hexdigest()
    return result


def bounded_command(command,env,timeout=20,limit=1024*1024):
    process=subprocess.Popen(command,stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,env=env,shell=False)
    chunks=[];size=[0];overflow=[False]
    def drain():
        while True:
            chunk=process.stdout.read(4096)
            if not chunk:break
            size[0]+=len(chunk)
            if size[0]>limit:overflow[0]=True;process.kill();break
            chunks.append(chunk)
    thread=threading.Thread(target=drain,daemon=True);thread.start()
    try:code=process.wait(timeout=timeout)
    except subprocess.TimeoutExpired as exc:process.kill();process.wait();thread.join(1);raise ValidationError('Source read timed out') from exc
    thread.join(2);process.stdout.close()
    require(not overflow[0] and code==0,'Source read failed or exceeded its output bound')
    return decode(b''.join(chunks),limit)


class ZoweReader:
    def __init__(self,profile,zosmf_profile=None):
        self.profile=profile;self.zosmf_profile=zosmf_profile;self.timeout=20
        for name in (profile,) if zosmf_profile is None else (profile,zosmf_profile):
            require(isinstance(name,str) and re.fullmatch(r'[A-Za-z0-9_-]{1,80}',name),'Unsafe Zowe profile alias')
    def operation(self,op,value,*,pattern=None,max_items=100):
        require(op in ('list_data_sets','list_members','read_member','read_dataset'),'Zowe source operations are strictly read-only')
        require(type(max_items)is int and 1<=max_items<=1000,'Zowe item bound must be 1..1000')
        if op=='list_data_sets':zowe_dataset(value,pattern=True)
        elif op=='read_member':zowe_dataset(value,member=True)
        else:zowe_dataset(value)
        require(pattern is None or op=='list_members','Member patterns are limited to metadata member lists')
        if pattern is not None:
            require(isinstance(pattern,str) and re.fullmatch(r'[A-Za-z@$#][A-Za-z0-9@$#]{0,7}',pattern),'Use an exact member name')
        commands={'list_data_sets':['list','data-set'],'list_members':['list','all-members'],
                  'read_member':['view','data-set'],'read_dataset':['view','data-set']}
        command=['zowe','zos-files',*commands[op],value,'--base-profile',self.profile]
        if self.zosmf_profile:command+=['--zosmf-profile',self.zosmf_profile]
        if op.startswith('list_'):command+=['--attributes','--max-length',str(max_items)]
        if pattern is not None:command+=['--pattern',pattern]
        command+=['--response-format-json']
        allowed=['PATH','HOME','USERPROFILE','APPDATA','SystemRoot','ZOWE_CLI_HOME','NODE_EXTRA_CA_CERTS']
        env={k:os.environ[k] for k in allowed if k in os.environ}
        try:
            source_read=op in ('read_member','read_dataset')
            response=bounded_command(command,env,timeout=self.timeout,
                                     limit=MAX_ZOWE_SOURCE_RESPONSE_BYTES if source_read else MAX_RESPONSE_BYTES)
            require(isinstance(response,dict) and response.get('success',True) is True,
                    'Zowe read failed; check the selected local profile, secure credentials and read access')
            if source_read:
                _zowe_not_truncated(response)
                if isinstance(_zowe_payload(response),str):_zowe_content(response)
            return response
        except OSError as exc:raise ValidationError('Zowe CLI unavailable; configure its approved local installation/profile') from exc
    def list_datasets(self,hint='*',*,max_items=100):return self.operation('list_data_sets',hint,max_items=max_items)
    def list_members(self,dataset,*,pattern=None,max_items=100):return self.operation('list_members',dataset,pattern=pattern,max_items=max_items)
    def read_member(self,member):return self.operation('read_member',member)
    def read_dataset(self,dataset):return self.operation('read_dataset',dataset)


def zowe_dataset(value,pattern=False,member=False):
    require(isinstance(value,str) and 0<len(value)<=150 and not value.startswith('-'),'Unsafe dataset/member value')
    qualifier=r'[A-Za-z@$#][A-Za-z0-9@$#-]{0,7}'
    dataset=qualifier+r'(?:\.'+qualifier+r')*'
    if pattern:
        require(re.fullmatch(r'[A-Za-z0-9@$#.*-]{1,44}',value),'Unsafe dataset discovery pattern')
    elif member:
        require(re.fullmatch(dataset+r'\([A-Za-z@$#][A-Za-z0-9@$#]{0,7}\)',value) and len(value.split('(')[0])<=44,
                'Member reads require one explicit dataset and member')
    else:require(re.fullmatch(dataset,value) and len(value)<=44,'Use one explicit dataset name')
    return value.upper()


def _zowe_payload(response):
    require(isinstance(response,dict) and response.get('success',True) is True,
            'Zowe returned no successful read result')
    payload=response
    for _ in range(4):
        if isinstance(payload,dict) and 'apiResponse' in payload:payload=payload['apiResponse']
        elif isinstance(payload,dict) and 'data' in payload:payload=payload['data']
        else:break
    return payload


def _zowe_items(response,bound):
    payload=_zowe_payload(response)
    items=payload.get('items') if isinstance(payload,dict) else payload
    require(isinstance(items,list) and len(items)<=bound and all(isinstance(item,dict) for item in items),
            'Zowe metadata result has an invalid or excessive item list')
    # A full bounded page cannot establish the absence of another candidate.
    more=any(isinstance(obj,dict) and any(obj.get(key) is True for key in ('moreRows','has_more','hasMore','truncated'))
             for obj in (response,response.get('data'),payload))
    return items,not more and len(items)<bound


def _zowe_content(response):
    _zowe_not_truncated(response)
    payload=_zowe_payload(response)
    if isinstance(payload,dict):payload=payload.get('content')
    if not isinstance(payload,str) and isinstance(response.get('stdout'),str):payload=response['stdout']
    require(isinstance(payload,str) and len(payload.encode('utf-8'))<=MAX_SOURCE_FILE_BYTES,
            'Zowe returned no bounded UTF-8 text content')
    return payload


def _zowe_not_truncated(response):
    node=response
    for _ in range(5):
        if not isinstance(node,dict):break
        require(not any(node.get(key) is True for key in ('truncated','has_more','hasMore','moreRows')),
                'Zowe source content is truncated; complete source is required')
        if 'apiResponse' in node:node=node['apiResponse']
        elif 'data' in node:node=node['data']
        else:break


class ReadOnlyLineageResolver:
    """Resolve typed source references using bounded metadata and exact names.

    Results are observations for the lineage mapper, never conversion readiness
    or an estate inventory. Source text stays in memory; the caller owns freezing
    it as immutable evidence. Business dataset content is separately opt-in.
    One resolver instance represents one discovery pass: its shared deadline
    starts at the first reference and never exceeds 300 seconds across references.
    """
    SOURCE_SUFFIXES={'program':'.cbl','copybook':'.cpy','proc':'.proc','job':'.jcl',
                     'jcl_include':'.inc','bms_mapset':'.bms'}
    def __init__(self,zowe=None,db2=None,dataset_hints=(),max_datasets=20,max_catalog_pages=5,
                 max_seconds=60,max_requests=100,allow_dataset_content=False,max_total_seconds=300):
        require(isinstance(dataset_hints,(tuple,list)) and len(dataset_hints)<=20,'Dataset hints must be a bounded list')
        for hint in dataset_hints:zowe_dataset(hint,pattern=True)
        require(type(max_datasets)is int and 1<=max_datasets<=100,'Dataset search budget must be 1..100')
        require(type(max_catalog_pages)is int and 1<=max_catalog_pages<=50,'Catalog search budget must be 1..50')
        require(type(max_seconds) in (int,float) and 0<max_seconds<=300,'Resolver time budget must be 0..300 seconds')
        require(type(max_total_seconds) in (int,float) and 0<max_total_seconds<=300,'Resolver pass time budget must be 0..300 seconds')
        require(type(max_requests)is int and 1<=max_requests<=1000,'Resolver request budget must be 1..1000')
        require(type(allow_dataset_content)is bool,'Dataset content permission must be boolean')
        self.zowe=zowe;self.db2=db2;self.dataset_hints=tuple(dataset_hints)
        self.max_datasets=max_datasets;self.max_catalog_pages=max_catalog_pages
        self.max_seconds=max_seconds;self.max_requests=max_requests;self.requests=0
        self.max_total_seconds=max_total_seconds;self._pass_deadline=None
        self.allow_dataset_content=allow_dataset_content;self._deadline=None

    @classmethod
    def from_environment(cls,env=None,**budgets):
        env=os.environ if env is None else env
        zowe=ZoweReader(env['WB_ZOWE_PROFILE'],env.get('WB_ZOWE_ZOSMF_PROFILE')) if env.get('WB_ZOWE_PROFILE') else None
        db2=Db2MCP(env['WB_DB2_MCP_URL'],env.get('WB_DB2_MCP_TOKEN','')) if env.get('WB_DB2_MCP_URL') else None
        hints=[env['WB_DATASET_HINT']] if env.get('WB_DATASET_HINT') else []
        return cls(zowe=zowe,db2=db2,dataset_hints=hints,**budgets)

    def _call(self,client,method,*args,**kwargs):
        remaining=self._deadline-time.monotonic()
        require(remaining>0,'Read-only resolver time budget reached')
        old_timeout=getattr(client,'timeout',None)
        has_deadline=hasattr(client,'deadline');old_deadline=getattr(client,'deadline',None)
        if old_timeout is not None:client.timeout=min(old_timeout,remaining)
        if has_deadline:client.deadline=self._deadline if old_deadline is None else min(old_deadline,self._deadline)
        try:return getattr(client,method)(*args,**kwargs)
        finally:
            if old_timeout is not None:client.timeout=old_timeout
            if has_deadline:client.deadline=old_deadline

    def _result(self,request,status='UNRESOLVED',reason=None,coverage='PARTIAL',**fields):
        result={'status':status,'kind':request['kind'],'name':request['name'],
                'coverage':coverage,'bounded':True,'snapshot_consistent':False,
                'scope':'Configured account-visible read scope; no full estate inventory or authorization completeness claim',
                **fields}
        if reason:result['reason']=reason
        return result

    def _provenance(self,operation,**fields):
        return {'connector':'zowe' if operation.startswith(('read_','list_')) else 'db2_mcp',
                'operation':operation,'read_only':True,'observed_at':datetime.now(timezone.utc).isoformat(),
                'bounded':True,'snapshot_consistent':False,**fields}

    def resolve(self,request):
        require(isinstance(request,dict) and isinstance(request.get('kind'),str) and
                isinstance(request.get('name'),str) and 0<len(request['name'])<=257,
                'Lineage resolution requires a typed reference kind and name')
        if self.requests>=self.max_requests:return self._result(request,reason='request_budget')
        now=time.monotonic()
        if self._pass_deadline is None:self._pass_deadline=now+self.max_total_seconds
        if now>=self._pass_deadline:return self._result(request,reason='resolution_pass_time_budget')
        self.requests+=1;self._deadline=min(now+self.max_seconds,self._pass_deadline)
        try:
            if request['kind'] in self.SOURCE_SUFFIXES:return self._source(request)
            if request['kind']=='dataset':return self._dataset(request)
            if request['kind']=='db2_table':return self._table(request)
            return self._result(request,reason='No configured typed read operation for this reference kind')
        except (ValidationError,OSError,UnicodeError,TypeError,ValueError,KeyError,AttributeError):
            # Native errors may embed credential material or private connection strings.
            return self._result(request,reason='Read failed or exceeded a bound; check private profile, credentials, access and metadata shape locally')

    __call__=resolve

    def _source(self,request):
        if self.zowe is None:return self._result(request,reason='Zowe profile is not explicitly configured')
        if not self.dataset_hints:return self._result(request,reason='Supply a user-selected dataset scope for member discovery')
        name=request['name'].upper()
        require(re.fullmatch(r'[A-Z@$#][A-Z0-9@$#]{0,7}',name),'Source lookup requires an exact member name')
        datasets={};complete=True
        for hint in self.dataset_hints:
            remaining=self.max_datasets-len(datasets)
            if remaining<=0:complete=False;break
            rows,full=_zowe_items(self._call(self.zowe,'list_datasets',hint,max_items=remaining+1),remaining+1)
            complete=complete and full
            for row in rows:
                dataset=row.get('dsname',row.get('name',row.get('DSNAME')))
                require(isinstance(dataset,str),'Dataset metadata omitted its exact name')
                dataset=zowe_dataset(dataset)
                if dataset in datasets:continue
                if len(datasets)>=self.max_datasets:complete=False;break
                datasets[dataset]=row
        candidates=[]
        for dataset,row in sorted(datasets.items()):
            organization=str(row.get('dsorg',row.get('DSORG',''))).upper()
            if organization not in ('PO','PO-E','PDS','PDSE'):
                # Never guess that a sequential/load/VSAM dataset is a source library.
                if organization not in ('PS','VS','VSAM'):complete=False
                continue
            members,full=_zowe_items(self._call(self.zowe,'list_members',dataset,pattern=name,max_items=2),2)
            complete=complete and full
            exact=[]
            for member in members:
                value=member.get('member',member.get('name',member.get('MEMBER')))
                require(isinstance(value,str),'Member metadata omitted its exact name')
                if value.upper()==name:exact.append(dataset+'('+name+')')
            candidates.extend(exact)
        candidates=sorted(set(candidates))
        coverage='COMPLETE' if complete else 'PARTIAL'
        if len(candidates)>1:return self._result(request,'AMBIGUOUS',reason='Exact member exists in multiple visible libraries; supply verified search-order provenance',coverage=coverage,candidates=candidates)
        if not complete:return self._result(request,reason='Member discovery is incomplete within its configured budgets; uniqueness is unverified',candidates=candidates)
        if not candidates:return self._result(request,reason='Exact member not observed in the configured account-visible scope',coverage=coverage,candidates=[])
        member=candidates[0];content=_zowe_content(self._call(self.zowe,'read_member',member))
        dataset=member.split('(')[0]
        filename='remote/'+dataset+'/'+name+self.SOURCE_SUFFIXES[request['kind']]
        from .domain import sha
        return self._result(request,'RESOLVED',coverage=coverage,content=content,filename=filename,
                            provenance=self._provenance('read_member',profile=self.zowe.profile,
                            dataset_member=member,source_hash=sha(content),discovery_scope=list(self.dataset_hints)))

    def _dataset(self,request):
        if self.zowe is None:return self._result(request,reason='Zowe profile is not explicitly configured')
        name=zowe_dataset(request['name'])
        rows,complete=_zowe_items(self._call(self.zowe,'list_datasets',name,max_items=2),2)
        matches=[row for row in rows if str(row.get('dsname',row.get('name',row.get('DSNAME','')))).upper()==name]
        if len(matches)>1:return self._result(request,'AMBIGUOUS',reason='Dataset metadata is ambiguous',candidates=matches)
        if not matches or not complete:return self._result(request,reason='Exact dataset metadata is unavailable or incomplete')
        fields={'metadata':matches[0],'provenance':self._provenance('list_data_sets',profile=self.zowe.profile,dataset=name)}
        if self.allow_dataset_content:
            organization=str(matches[0].get('dsorg',matches[0].get('DSORG',''))).upper()
            if organization=='PS':
                fields['content']=_zowe_content(self._call(self.zowe,'read_dataset',name))
                fields['provenance']=self._provenance('read_dataset',profile=self.zowe.profile,dataset=name)
            else:fields['content_reason']='Content reads are supported only for explicitly observed sequential PS datasets'
        return self._result(request,'RESOLVED',coverage='COMPLETE',**fields)

    def _table(self,request):
        if self.db2 is None:return self._result(request,reason='Db2 MCP is not explicitly configured')
        if isinstance(self.db2,Db2MCP) and self.db2.protocol is None:self._call(self.db2,'initialize')
        parts=request['name'].upper().split('.')
        require(len(parts) in (1,2),'Use an exact table or schema.table reference')
        for part in parts:sql_name(part)
        if len(parts)==1:
            listing=discover_catalog(self.db2,'tables',max_pages=self.max_catalog_pages,
                                     max_seconds=min(self.max_seconds,max(0.001,self._deadline-time.monotonic())))
            matches=set()
            for row in listing['rows']:
                schema=row.get('CREATOR');table=row.get('NAME')
                require(isinstance(schema,str) and isinstance(table,str),'Table metadata omitted its exact qualified name')
                if table.upper()==parts[0]:matches.add((schema,table))
            candidates=['.'.join(pair) for pair in sorted(matches)]
            if len(matches)>1:return self._result(request,'AMBIGUOUS',reason='Unqualified table exists in multiple visible schemas',coverage=listing['coverage'],candidates=candidates)
            if listing['coverage']!='COMPLETE':return self._result(request,reason='Table search is incomplete; unqualified reference uniqueness is unverified',candidates=candidates)
            if not matches:return self._result(request,reason='Exact table not observed in the configured account-visible catalog',coverage='COMPLETE')
            schema,table=next(iter(matches))
        else:schema,table=parts
        columns=[];cursor=-1;seen=set();ordinals=set();complete=False
        for _ in range(self.max_catalog_pages):
            page=self._call(self.db2,'describe',schema,table,after_column=cursor)
            require(isinstance(page,dict) and isinstance(page.get('rows'),list) and len(page['rows'])<=100
                    and all(isinstance(row,dict) for row in page['rows']),'Invalid bounded table description')
            for column in page['rows']:
                require(isinstance(column.get('NAME'),str) and type(column.get('COLNO'))is int
                        and cursor<column['COLNO']<=32767 and column['COLNO'] not in ordinals,
                        'Table description contains invalid or repeated column identity')
                sql_name(column['NAME']);ordinals.add(column['COLNO'])
            columns.extend(page['rows'])
            if page.get('has_more') is False:complete=True;break
            if page.get('has_more') is not True:break
            next_cursor=page.get('next_cursor')
            require(isinstance(next_cursor,dict) and set(next_cursor)=={'after_column'} and
                    type(next_cursor['after_column'])is int and cursor<next_cursor['after_column']<=32767 and
                    next_cursor['after_column'] not in seen,'Invalid table-description continuation')
            cursor=next_cursor['after_column'];seen.add(cursor)
        metadata={'schema':schema,'table':table,'columns':columns,'description_complete':complete}
        provenance=self._provenance('db2_describe_table',schema=schema,table=table)
        if not columns:return self._result(request,reason='No columns observed; table existence and authorization remain unverified',metadata=metadata,provenance=provenance)
        if not complete:return self._result(request,reason='Table description is incomplete within its configured budgets',metadata=metadata,provenance=provenance)
        return self._result(request,'RESOLVED',coverage='COMPLETE',metadata=metadata,provenance=provenance)


def read_only_discovery():
    result={'db2':{'status':'NOT_CONFIGURED'},'zowe':{'status':'NOT_CONFIGURED'}}
    if os.environ.get('WB_DB2_MCP_URL'):
        try:
            client=Db2MCP(os.environ['WB_DB2_MCP_URL'],os.environ.get('WB_DB2_MCP_TOKEN',''));status=client.initialize()
            schemas=discover_catalog(client,'schemas');tables=discover_catalog(client,'tables')
            result['db2']={**status,'schemas':schemas,'tables':tables,
                          'coverage':'COMPLETE' if schemas['coverage']==tables['coverage']=='COMPLETE' else 'PARTIAL',
                          'truncation':'Bounded keyset catalog traversal; continuation and limits are recorded per catalog. No table sample is fetched by default.'}
        except ValidationError as exc:result['db2']={'status':'UNAVAILABLE','message':str(exc)}
    if os.environ.get('WB_ZOWE_PROFILE'):
        try:result['zowe']={'status':'READ_COMPLETED','datasets':ZoweReader(os.environ['WB_ZOWE_PROFILE'],os.environ.get('WB_ZOWE_ZOSMF_PROFILE')).list_datasets(os.environ.get('WB_DATASET_HINT','*')),'truncation':'Response bounded to 1 MiB; catalogue completeness is not claimed.'}
        except ValidationError as exc:result['zowe']={'status':'UNAVAILABLE','message':str(exc)}
    return result
