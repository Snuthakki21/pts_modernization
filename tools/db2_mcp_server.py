#!/usr/bin/env python3
"""Optional loopback Streamable-HTTP MCP gateway with four fixed read-only Db2 tools.

Requires an approved pyodbc/Db2 driver installation and a read-only account.
Credentials stay in WB_DB2_ODBC_CONNECTION. No arbitrary SQL endpoint exists.
"""
import json
import os
import secrets
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from workbench.connectors import READ_TOOLS,MCP_VERSIONS,MAX_RESPONSE_BYTES,catalog_sql
from workbench.domain import decode,encode,require,ValidationError


def connection_string():
    if os.environ.get('WB_DB2_CONFIG'):
        from workbench.db2_setup import load_connection
        return load_connection(os.environ['WB_DB2_CONFIG'],os.environ)
    connection=os.environ.get('WB_DB2_ODBC_CONNECTION')
    require(connection,'Configure a private read-only Db2 ODBC connection')
    return connection


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
            else:
                require(len(self.sessions)<16,'Concurrent table read cursor budget reached')
                if os.environ.get('WB_DB2_CONFIG'):
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
    connection=connection_string()
    sql,params=catalog_sql(name,args)
    with pyodbc.connect(connection,autocommit=True,attrs_before={101:1},timeout=10) as db:
        cursor=db.cursor();cursor.timeout=15;cursor.execute(sql,*params)
        limit=args.get('limit',100);names=[x[0] for x in cursor.description]
        require(names and all(isinstance(name,str) for name in names) and len(names)==len(set(names)),'Invalid or duplicate database column names')
        rows=cursor.fetchmany(limit if name=='db2_sample_rows' else limit+1)
        require(all(len(row)==len(names) for row in rows),'Database row width differs from its column description')
        more=len(rows)>limit;rows=rows[:limit]
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


if __name__=='__main__':
    require(os.environ.get('WB_DB2_MCP_TOKEN'),'Set WB_DB2_MCP_TOKEN before launching the gateway')
    ThreadingHTTPServer(('127.0.0.1',int(os.environ.get('WB_DB2_MCP_PORT','8766'))),Handler).serve_forever()
