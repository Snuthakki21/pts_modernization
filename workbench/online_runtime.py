"""Local target runtime. Transport/session behavior is not native CICS parity."""
from .domain import path_is_link
import hashlib
import hmac
import json
import sqlite3
import time
import uuid
from contextlib import closing
from pathlib import Path
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import FileResponse, JSONResponse


def create_app(programs, spec, database, token, clock=time.time, ttl=900, screens=None):
    screens = screens or {}
    if not isinstance(token,str) or len(token)<32:raise ValueError('Set a private ONLINE_TOKEN of at least 32 characters')
    if not 1<=ttl<=86400:raise ValueError('Invalid session lifetime')
    database=Path(database)
    if path_is_link(database) or any(path_is_link(p) for p in database.absolute().parents):raise ValueError('Unsafe local database path')
    database.parent.mkdir(parents=True,exist_ok=True)
    def connect():
        db=sqlite3.connect(database,timeout=5);db.row_factory=sqlite3.Row
        try:
            db.execute('PRAGMA foreign_keys=ON');return db
        except BaseException:
            db.close();raise
    with closing(connect()) as db, db:
        db.executescript('CREATE TABLE IF NOT EXISTS sessions(id TEXT PRIMARY KEY, transaction_id TEXT NOT NULL, expires REAL NOT NULL, revision INTEGER NOT NULL); CREATE TABLE IF NOT EXISTS requests(session_id TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE, key TEXT NOT NULL, request_hash TEXT NOT NULL, response TEXT NOT NULL, PRIMARY KEY(session_id,key));')
    app=FastAPI(title='Modernized business capabilities',version='1.0',docs_url=None,redoc_url=None)
    def authorize(request):
        # Bearer authentication, no cookie authority and no permissive CORS.
        value=request.headers.get('authorization','')
        if not hmac.compare_digest(value.encode('utf-8'),('Bearer '+token).encode('utf-8')):raise HTTPException(401,'Authorization required')
        if request.headers.get('origin') and request.headers['origin']!=str(request.base_url).rstrip('/'):
            raise HTTPException(403,'Cross-origin request denied')
    async def body(request):
        raw=bytearray()
        async for chunk in request.stream():
            raw.extend(chunk)
            if len(raw)>65536:raise HTTPException(413,'Request too large')
        try:
            def pairs(items):
                result={}
                for k,v in items:
                    if k in result:raise ValueError('Duplicate key')
                    result[k]=v
                return result
            result=json.loads(raw,object_pairs_hook=pairs,parse_constant=lambda x:(_ for _ in ()).throw(ValueError(x)))
            if not isinstance(result,dict):raise ValueError('Expected object')
            json.dumps(result,allow_nan=False)
            return result
        except (ValueError,UnicodeError,RecursionError):raise HTTPException(422,'Invalid JSON object')
    @app.get('/health')
    def health():return {'status':'ready','profile':'local-source-derived','native_cics_parity':False}
    @app.get('/api/contracts')
    def contracts(request:Request):authorize(request);return spec
    @app.post('/api/sessions')
    async def session(request:Request):
        authorize(request);data=await body(request)
        if set(data)!={'transaction'} or not isinstance(data['transaction'],str) or data['transaction'] not in spec:raise HTTPException(422,'Unknown transaction')
        if spec[data['transaction']].get('record_supported') is False:raise HTTPException(409,'CICS controller is unverified; layout rendering does not execute a transaction')
        db=connect()
        try:
            db.execute('BEGIN IMMEDIATE');db.execute('DELETE FROM sessions WHERE expires<=?',(clock(),))
            if db.execute('SELECT COUNT(*) FROM sessions').fetchone()[0]>=1000:raise HTTPException(429,'Active session capacity reached')
            sid=uuid.uuid4().hex;db.execute('INSERT INTO sessions VALUES(?,?,?,0)',(sid,data['transaction'],clock()+ttl));db.commit()
            return {'session_id':sid,'revision':0,'expires_in_seconds':ttl}
        except Exception:db.rollback();raise
        finally:db.close()
    @app.delete('/api/sessions/{sid}')
    def close_session(sid:str,request:Request):
        authorize(request)
        with closing(connect()) as db, db:db.execute('DELETE FROM sessions WHERE id=?',(sid,))
        return {'closed':True}
    @app.post('/api/transactions/{transaction}')
    async def execute(transaction:str,request:Request):
        authorize(request)
        if transaction not in spec:raise HTTPException(404,'Unknown transaction')
        if spec[transaction].get('record_supported') is False:raise HTTPException(409,'CICS controller is unverified; layout rendering does not execute a transaction')
        sid=request.headers.get('x-session-id','');key=request.headers.get('idempotency-key','')
        if not sid or not 1<=len(key)<=128 or not key.isascii():raise HTTPException(422,'Session and bounded idempotency key required')
        data=await body(request)
        if set(data)!={'record','revision'} or type(data['revision']) is not int or data['revision']<0:raise HTTPException(422,'Record and integer revision required')
        digest=hashlib.sha256(json.dumps(data,sort_keys=True,separators=(',',':'),ensure_ascii=True).encode()).hexdigest()
        db=connect()
        try:
            db.execute('BEGIN IMMEDIATE')
            session=db.execute('SELECT * FROM sessions WHERE id=?',(sid,)).fetchone()
            if not session or session['expires']<=clock():raise HTTPException(410,'Session expired or absent')
            if session['transaction_id']!=transaction:raise HTTPException(409,'Session belongs to another transaction')
            previous=db.execute('SELECT * FROM requests WHERE session_id=? AND key=?',(sid,key)).fetchone()
            if previous:
                if previous['request_hash']!=digest:raise HTTPException(409,'Idempotency key reused with different input')
                return json.loads(previous['response'])
            if session['revision']!=data['revision']:raise HTTPException(409,'Stale session revision')
            if db.execute('SELECT COUNT(*) FROM requests WHERE session_id=?',(sid,)).fetchone()[0]>=100:raise HTTPException(429,'Session request capacity reached; open a new session')
            output=programs[spec[transaction]['program']](data['record'])
            if output.get('input_status')!='ACCEPT_INPUT':raise HTTPException(422,output.get('errors',['Input rejected']))
            response={'result':output,'revision':session['revision']+1,'evidence_basis':'SOURCE_DERIVED_EXPECTED'}
            db.execute('INSERT INTO requests VALUES(?,?,?,?)',(sid,key,digest,json.dumps(response)))
            db.execute('UPDATE sessions SET revision=revision+1 WHERE id=?',(sid,));db.commit();return response
        except HTTPException:db.rollback();raise
        except sqlite3.OperationalError:db.rollback();raise HTTPException(503,'Local persistence temporarily unavailable')
        except Exception:db.rollback();raise HTTPException(500,'Target execution failed; transaction rolled back')
        finally:db.close()
    @app.post('/api/screens/{transaction}/{screen_id}')
    async def render_screen(transaction:str,screen_id:str,request:Request):
        authorize(request)
        item = spec.get(transaction)
        if not item or not any(screen['id']==screen_id for screen in item.get('screens',[])) or screen_id not in screens:
            raise HTTPException(404,'Screen is not in this transaction contract')
        data=await body(request)
        if set(data)!={'values'}:raise HTTPException(422,'Exactly one values object is required')
        try:result=screens[screen_id](data['values'])
        except Exception:raise HTTPException(500,'Screen target execution failed')
        return JSONResponse({'result':result,'evidence_basis':'SOURCE_DERIVED_EXPECTED','native_controller_verified':False},
                            status_code=200 if result.get('input_status')=='ACCEPT_INPUT' else 422)
    # Publish the same source field constraints enforced by generated programs.
    schema=app.openapi()
    schema.setdefault('components',{}).setdefault('securitySchemes',{})['LocalBearer']={'type':'http','scheme':'bearer'}
    records=[]
    for tx,item in spec.items():
        properties={}
        for name,field in item.get('fields',{}).items():
            properties[name]={'type':'integer','minimum':0,'maximum':field['max']} if field['type']=='integer' else {'type':'string','minLength':field['width'],'maxLength':field['width']}
        record={'type':'object','properties':properties,'required':list(properties),'additionalProperties':False}
        schema['components'].setdefault('schemas',{})[tx+'Record']=record
        if item.get('record_supported') is not False:records.append({'$ref':'#/components/schemas/'+tx+'Record'})
    for path,operations in schema['paths'].items():
        if path=='/health':continue
        for operation in operations.values():
            operation['security']=[{'LocalBearer':[]}]
            operation.setdefault('responses',{})['401']={'description':'Local bearer authorization required'}
    operation=schema['paths']['/api/transactions/{transaction}']['post']
    operation['requestBody']={'required':True,'content':{'application/json':{'schema':{'type':'object','additionalProperties':False,'required':['record','revision'],'properties':{'record':({'anyOf':records} if records else {'not':{}}),'revision':{'type':'integer','minimum':0}}}}}}
    operation['parameters'] += [{'in':'header','name':'X-Session-ID','required':True,'schema':{'type':'string'}},{'in':'header','name':'Idempotency-Key','required':True,'schema':{'type':'string','minLength':1,'maxLength':128}}]
    operation['parameters'][0]['schema']['enum']=list(spec)
    operation['responses'].update({str(code):{'description':description} for code,description in [(409,'Stale revision or conflicting idempotency key'),(410,'Session absent or expired'),(413,'Request exceeds 64 KiB'),(422,'Invalid record'),(429,'Session request capacity reached'),(503,'Persistence unavailable')]})
    schema['paths']['/api/sessions']['post']['requestBody']={'required':True,'content':{'application/json':{'schema':{'type':'object','required':['transaction'],'additionalProperties':False,'properties':{'transaction':{'type':'string','enum':list(spec)}}}}}}
    screen_records=[]
    for tx,item in spec.items():
        for screen in item.get('screens',[]):
            properties={field['id']:{'type':'string','minLength':field['width'],'maxLength':field['width'],'pattern':'^[ -~]*$'} for field in screen['fields'] if field['editable']}
            name=tx+'_'+screen['id']+'Values'
            schema['components']['schemas'][name]={'type':'object','additionalProperties':False,'required':list(properties),'properties':properties}
            screen_records.append({'$ref':'#/components/schemas/'+name})
    operation=schema['paths']['/api/screens/{transaction}/{screen_id}']['post']
    operation['requestBody']={'required':True,'content':{'application/json':{'schema':{'type':'object','additionalProperties':False,'required':['values'],'properties':{'values':{'anyOf':screen_records} if screen_records else {'not':{}}}}}}}
    operation['responses'].update({'404':{'description':'Screen is not bound to transaction'},'413':{'description':'Request exceeds 64 KiB'},'422':{'description':'Rejected source-owned screen input'}})
    app.openapi_schema=schema
    return app
