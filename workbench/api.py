"""Loopback control API; explicit bounds and same-origin mutation protection."""
import json
import base64
import secrets
import asyncio
import html
import re
from contextlib import asynccontextmanager
from pathlib import Path
from urllib.parse import quote, urlencode
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import Response, JSONResponse
from .coordinator import Coordinator
from .domain import decode, ValidationError, require, safe_path
from .reports import portfolio
from .limits import MAX_HTTP_BODY_BYTES, MAX_UI_SOURCE_BYTES

def create_app(root, origin='http://127.0.0.1:8765'):
    c=Coordinator(root)
    @asynccontextmanager
    async def lifespan(app):
        c.launch_worker()
        try:yield
        finally:await asyncio.to_thread(c.close)
    app=FastAPI(docs_url=None,redoc_url=None,openapi_url=None,lifespan=lifespan)
    app.state.coordinator=c;token=secrets.token_urlsafe(32)
    static=Path(__file__).with_name('static')
    @app.middleware('http')
    async def boundary(request, call_next):
        if request.headers.getlist('host')!=[origin.split('://',1)[1]]:
            response=JSONResponse({'error':'Invalid host'},400)
        elif request.method not in ('GET','HEAD') and (request.headers.getlist('origin')!=[origin] or request.headers.getlist('x-workbench-token')!=[token]):
            response=JSONResponse({'error':'Same-origin session required'},403)
        else:
            try:response=await call_next(request)
            except Exception:response=JSONResponse({'error':'Operation failed; inspect the local event ledger'},500)
        response.headers['Cache-Control']='no-store'
        response.headers['X-Content-Type-Options']='nosniff'
        if 'Content-Security-Policy' not in response.headers:
            response.headers['Content-Security-Policy']="default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'"
        return response
    @app.exception_handler(ValidationError)
    async def invalid(request,exc):return JSONResponse({'error':str(exc)},400)
    async def body(request, limit=MAX_HTTP_BODY_BYTES):
        raw=bytearray()
        async for chunk in request.stream():
            if len(raw)+len(chunk)>limit:raise HTTPException(413,'Request exceeds the permitted size')
            raw.extend(chunk)
        result=decode(bytes(raw),limit);require(isinstance(result,dict),'Request must be a JSON object');return result
    def display_process(doc):
        # Polling never repeats full synthetic record bodies. Evidence is downloaded on demand.
        result={k:v for k,v in doc.items() if k!='process_context'}
        if doc.get('requirements'):
            result['requirements']={k:v for k,v in doc['requirements'].items() if k!='excluded_ids'}
            result['requirements']['excluded_count']=len(doc['requirements']['excluded_ids'])
        result.pop('requirements_draft_exclusions',None)
        result['blocker_count']=len(doc.get('blockers',[]))
        result['blockers']=doc.get('blockers',[])[:50]
        result['blockers_truncated']=result['blocker_count']>50
        result['runs']=[{k:v for k,v in run.items() if k!='programs'}|{'programs':{name:{k:v for k,v in r.items() if k not in ('actual','differences')}|{'case_count':len(r['actual']),'difference_count':len(r['differences'])} for name,r in run['programs'].items()}} for run in doc['runs']]
        if doc.get('cics_contract_version')==1:
            for projected,run in zip(result['runs'],doc['runs']):
                projected['screens']={ident:{key:value for key,value in receipt.items() if key not in ('actual','differences','coverage','adversarial','linked_controller_witness')}|
                    {'case_count':len(receipt.get('actual',[])),'difference_count':len(receipt.get('differences',[])),
                     'coverage_complete':receipt.get('coverage',{}).get('complete'),
                     'adversarial_passed':receipt.get('adversarial',{}).get('passed'),
                     'mutation_count':len(receipt.get('adversarial',{}).get('mutations',[]))} for ident,receipt in run.get('screens',{}).items()}
            result.pop('screen_versions',None);result['screen_target_count']=len(doc.get('screen_versions',{}))
            if doc.get('logic_validation'):
                result['logic_validation']={key:value for key,value in doc['logic_validation'].items() if key!='screen_layouts'}
                result['logic_validation']['screen_layout_count']=len(doc['logic_validation'].get('screen_layouts',[]))
        if doc.get('analysis'):
            accounting=doc['analysis'].get('source_accounting')
            result['analysis']={k:v for k,v in doc['analysis'].items() if k not in ('programs','source_accounting')}
            result['analysis']['assets']=[{k:v for k,v in asset.items() if k not in ('source_text','coverage','rules','fields')} for asset in doc['analysis'].get('assets',[])]
            if doc['analysis'].get('cics_contract_version')==1:
                cics=doc['analysis']['cics']
                result['analysis']['cics']=({key:cics.get(key) for key in ('schema_version','profile','native_cics_verified','limitations')}|
                    {'screen_count':len(cics['screens']),'unit_count':len(cics['units']),'gap_count':len(cics['gaps'])})
            result['analysis']['rule_count']=len(doc['analysis'].get('rules',[]))
            result['analysis']['rules']=doc['analysis'].get('rules',[])[:50]
            result['analysis']['rules_truncated']=result['analysis']['rule_count']>50
            if doc['analysis'].get('requirements'):
                result['analysis']['requirements']={'catalog_hash':doc['analysis']['requirements']['catalog_hash'],'excluded_count':len(doc['analysis']['requirements']['excluded_units'])}
            result['analysis']['blocker_count']=len(doc['analysis'].get('blockers',[]))
            result['analysis']['blockers']=doc['analysis'].get('blockers',[])[:50]
            result['analysis'].update(source_accounted_file_count=len(accounting) if isinstance(accounting,dict) else None,
                                      source_accounted_line_count=sum(len(rows) for rows in accounting.values()) if isinstance(accounting,dict) else None)
        from .executive import accepted_executive
        try:result.update(accepted_executive(c,doc))
        except (ValidationError,OSError):
            result.update(executive=None,executive_report=None,executive_error='Accepted executive report integrity could not be verified.')
        return result
    @app.get('/api/state')
    async def state():
        from .provider import empty_usage_summary
        from .inventory import load_inventory
        from .setup import workstation_environment, intake_defaults
        environment=workstation_environment(c.root)
        source_folder=intake_defaults(c.root)['source_folder']
        return {'processes':[display_process(p) for p in c.ledger.list(True)],'portfolio':portfolio(c.ledger),'token':token,
                'inventory_baseline':load_inventory(c.root),
                'provider_usage':c.provider.usage_summary() if c.provider else empty_usage_summary(),
                'capability':'Local Endeavor discovery first, approved Claude retrieval for missing evidence, and tested modernization with visible gaps.',
                'connections':{'zowe_profile_configured':bool(environment.get('WB_ZOWE_PROFILE')),'db2_endpoint_configured':bool(environment.get('WB_DB2_MCP_URL')),'llm_configured':bool(c.provider),'local_source_export':(c.root/'Endeavor').is_dir(),'saved_folder_available':bool(source_folder and Path(source_folder).is_dir())}}
    @app.get('/api/session-token')
    async def session_token():
        # Developer-role mutations need CSRF material, not the operational state.
        return {'token': token}

    @app.get('/api/setup')
    async def setup():
        from .setup import inspect_setup
        return inspect_setup(c.root)
    @app.post('/api/setup')
    async def update_setup(request:Request):
        from .setup import MAX_SETUP_BYTES, save_setup
        b=await body(request,MAX_SETUP_BYTES)
        require(set(b)=={'answers'},'Supply only the nonsecret setup answers object')
        return save_setup(c.root,b['answers'])
    @app.get('/api/setup/workstation')
    async def workstation_setup():
        from .setup import inspect_workstation
        return await asyncio.to_thread(inspect_workstation,c.root,origin=origin)
    @app.post('/api/setup/workstation')
    async def update_workstation_setup(request:Request):
        from .setup import MAX_WORKSTATION_BYTES, save_workstation
        b=await body(request,MAX_WORKSTATION_BYTES*2)
        require(set(b) in ({'settings'},{'settings','connections'}),'Supply only nonsecret workstation settings and connection choices')
        return await asyncio.to_thread(c.configure_workstation,b['settings'],b.get('connections'),origin)
    @app.get('/api/templates/intake')
    async def template():
        path=Path(__file__).parent.parent/'examples/intake-template.xlsx'
        return Response(path.read_bytes(),media_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',headers={'Content-Disposition':'attachment; filename="intake-template.xlsx"'})
    @app.get('/api/process-template')
    async def process_template():
        path=Path(__file__).resolve().parents[1]/'examples/process-specific.md'
        return Response(path.read_bytes(),media_type='text/markdown',
                        headers={'Content-Disposition':'attachment; filename="Process.md"'})
    @app.get('/api/preflight')
    async def preflight():
        from .preflight import inspect_workspace
        return await asyncio.to_thread(inspect_workspace,c.root,coordinator_owned=True)
    @app.get('/api/knowledge')
    async def knowledge():
        from .mainframe import load_knowledge
        package=Path(__file__).parent.parent
        return {'snapshot':load_knowledge(c.root),'application_template_path':str(package/'examples/application-knowledge.json'),
                'application_path':str(c.root/'knowledge/application-knowledge.json'),'reference_path':str(package/'knowledge/README.md')}
    @app.post('/api/intake')
    @app.post('/api/intake/prepare')
    async def intake(request:Request):
        b=await body(request)
        if b.get('xlsx'):
            from .intake import parse_intake_xlsx
            from .intake import HEADERS
            require(isinstance(b['xlsx'],str),'Intake workbook must be base64 text')
            try:data=base64.b64decode(b['xlsx'],validate=True)
            except ValueError as exc:raise ValidationError('Invalid intake workbook encoding') from exc
            m=parse_intake_xlsx(data);rows=[]
            for j in m['jobs']:
                for s in j['steps']:rows.append([j['order'],j['name'],s['order'],s['name'],s['program'],';'.join(s['inputs']),';'.join(s['outputs']),s['condition']])
            b['manifest']='- Process ID: '+m['id']+'\n- Process name: '+m['name']+'\n| '+' | '.join(HEADERS)+' |\n'+'\n'.join('| '+' | '.join(map(str,r))+' |' for r in rows)
        require(isinstance(b.get('manifest'),str),'Provide a Markdown or Excel process manifest')
        sources=b.get('sources')
        if sources is not None:
            require(isinstance(sources,dict) and all(isinstance(v,str) for v in sources.values()),'Uploaded sources must be text files')
            require(sum(len(v.encode('utf-8')) for v in sources.values())<=MAX_UI_SOURCE_BYTES,'Browser source upload exceeds 32 MiB; retain the complete repository in local Endeavor instead')
        from .setup import intake_defaults
        defaults=intake_defaults(c.root)
        source_folder=b.get('source_folder',None if request.url.path=='/api/intake/prepare' else defaults['source_folder']) if sources is None else b.get('source_folder')
        process_notes=b.get('process_notes',None if request.url.path=='/api/intake/prepare' else defaults['process_notes'])
        if request.url.path=='/api/intake/prepare':
            require(b.get('assistant_mode','claude_files')=='claude_files','Prepared intake uses the local Claude workflow')
            return await asyncio.to_thread(c.prepare_process,b['manifest'],sources,b.get('prompt',''),source_folder,process_notes,b.get('demo',False))
        return await asyncio.to_thread(c.create,b['manifest'],sources,False,b.get('prompt',''),b.get('assistant_mode','claude_files'),source_folder,process_notes,True)

    @app.get('/api/process/{pid}/guide')
    async def process_guide(pid:str):
        return await asyncio.to_thread(c.process_guide,pid)

    @app.post('/api/process/{pid}/guide/save')
    async def save_process_guide(pid:str,request:Request):
        require(await body(request,4096)=={},'Save current process instructions with an empty object')
        return await asyncio.to_thread(c.save_process_guide,pid)

    @app.get('/api/process/{pid}/database')
    async def database(pid:str):
        from .database_workflow import database_view
        return await asyncio.to_thread(database_view,c,pid)

    @app.post('/api/process/{pid}/database/prepare')
    async def prepare_database(pid:str,request:Request):
        from .database_workflow import prepare_database
        return await asyncio.to_thread(prepare_database,c,pid,await body(request,4096))

    @app.get('/api/process/{pid}/database/{ident}/rows')
    async def database_rows(pid:str,ident:str,request:Request,table:str,after:int=0,limit:int=100):
        from .database_workflow import database_rows
        allowed={'table','after','limit'}
        require(set(request.query_params)<=allowed and all(len(request.query_params.getlist(k))==1 for k in request.query_params),'Unknown or repeated database filter')
        return await asyncio.to_thread(database_rows,c,pid,ident,table,after,limit)

    @app.post('/api/process/{pid}/database/{ident}/query')
    async def database_query(pid:str,ident:str,request:Request):
        from .database_workflow import database_rows
        from .database import decode_filters
        b=await body(request,8192)
        require(set(b)<={'table','after','limit','filters'} and 'table' in b,'Supply table, cursor, limit and typed equality filters only')
        return await asyncio.to_thread(database_rows,c,pid,ident,b['table'],b.get('after',0),b.get('limit',100),decode_filters(b.get('filters',{})))

    @app.post('/api/process/{pid}/database/snapshot')
    async def database_snapshot(pid:str,request:Request):
        from .database_workflow import database_snapshot
        return await asyncio.to_thread(database_snapshot,c,pid,await body(request,32768))

    @app.post('/api/process/{pid}/database/compare')
    async def database_compare(pid:str,request:Request):
        from .database_workflow import database_comparison
        return await asyncio.to_thread(database_comparison,c,pid,await body(request,32768))

    @app.get('/api/process/{pid}/requirements/source')
    async def requirements_source(pid:str,path:str):
        doc=c.ledger.get(pid);sources=await asyncio.to_thread(c.sources,doc)
        require(path in sources,'Source file is outside this process snapshot')
        return Response(sources[path],media_type='text/plain',headers={'Content-Disposition':"attachment; filename=\"source.txt\"; filename*=UTF-8''"+quote(Path(path).name,safe='')})

    @app.get('/api/process/{pid}/requirements')
    async def requirements(pid:str,request:Request,after:int=0,path:str|None=None,program:str|None=None,screen:str|None=None,kind:str|None=None):
        allowed={'after','path','program','screen','kind'}
        require(set(request.query_params)<=allowed and all(len(request.query_params.getlist(k))==1 for k in request.query_params),'Unknown or duplicate requirements filter')
        return await asyncio.to_thread(c.requirements_view,pid,after,path,program,screen,kind)

    @app.post('/api/process/{pid}/requirements')
    async def save_requirements(pid:str,request:Request):
        return display_process(await asyncio.to_thread(c.save_requirements,pid,await body(request,4*1024*1024)))

    @app.get('/api/economics')
    async def economics(process_id:str|None=None):
        return await asyncio.to_thread(c.economics,process_id)

    @app.post('/api/economics/forecast')
    async def preview_forecast(request:Request):
        b=await body(request,65536);require(set(b)<={'process_id','plan'} and 'plan' in b,'Supply a forecast plan')
        return await asyncio.to_thread(c.economics,b.get('process_id'),b['plan'])

    @app.post('/api/economics/work/start')
    async def start_work(request:Request):return c.begin_work(await body(request,4096))

    @app.post('/api/economics/work/stop')
    async def stop_work(request:Request):
        b=await body(request,4096);require(set(b)<={'id','abandon'} and isinstance(b.get('id'),str) and type(b.get('abandon',False)) is bool,'Supply work session ID and optional abandon boolean')
        return c.end_work(b['id'],b.get('abandon',False))

    @app.post('/api/economics/receipts')
    async def record_measurement(request:Request):
        return await asyncio.to_thread(c.record_measurement,await body(request,65536))

    @app.get('/api/process/{pid}/factory')
    async def factory(pid:str,after:int=0,program_after:int=0):
        from .factory import bounded_view
        return bounded_view(c.ledger.get(pid),after,program_after)

    @app.get('/api/process/{pid}/agent/rules')
    async def agent_rules(pid:str,after:int=0):
        from .copilot import opaque_reference
        from .domain import sha,encode
        require(after>=0,'Invalid rule cursor')
        task=c.agent_task(pid)
        frozen=json.loads(c.artifact(pid,task['analysis_reference']['path']).read_text(encoding='utf-8'))
        rules=frozen['rules'];require(after<=len(rules),'Invalid rule cursor')
        entries=[{'id':opaque_reference('RULE',rule['id']),
                  'source_references_sha256':sha(encode(rule['source_refs'])),
                  'start_line':rule['source_start'],'end_line':rule['source_end'],
                  'description':'Private decision literals withheld; approved sanitized semantic context is required.'}
                 for rule in rules[after:after+50]]
        return {'process_id':pid,'task_hash':task['task_hash'],'items':entries,'total':len(rules),'next_after':after+len(entries),'has_more':after+len(entries)<len(rules)}

    @app.get('/api/process/{pid}/agent/obligations')
    async def agent_obligations(pid:str,after:int=0):
        from .domain import sha,encode
        require(after>=0,'Invalid obligation cursor')
        task=c.agent_task(pid)
        frozen=json.loads(c.artifact(pid,task['analysis_reference']['path']).read_text(encoding='utf-8'))
        blockers=frozen['blockers'];require(after<=len(blockers),'Invalid obligation cursor')
        entries=blockers[after:after+50]
        return {'process_id':pid,'task_hash':task['task_hash'],
                'items':[{'index':after+i,'evidence_sha256':sha(encode(entry)),
                          'status':'UNVERIFIED_OBLIGATION','message':'Private source details require approved sanitized context.'}
                         for i,entry in enumerate(entries)],
                'total':len(blockers),'next_after':after+len(entries),'has_more':after+len(entries)<len(blockers)}

    @app.get('/api/process/{pid}/agent/context')
    async def agent_context(pid:str,document_id:str,start_line:int=1,end_line:int|None=None):
        from .process_context import excerpt
        snapshot=json.loads(c.artifact(pid,'analysis/process-context.json').read_text(encoding='utf-8'))
        value=excerpt(snapshot,document_id,start_line,end_line)
        return {key:field for key,field in value.items() if key in {'document_id','sha256','start_line','end_line'}} | {
            'authority':'UNVERIFIED_INPUT','private_contents_allowed':False}

    @app.get('/api/process/{pid}/local-agent')
    async def local_agent(pid:str):return await asyncio.to_thread(c.local_agent_view,pid)

    @app.post('/api/process/{pid}/local-agent/{action}')
    async def local_agent_action(pid:str,action:str,request:Request):
        return await asyncio.to_thread(c.local_agent_action,pid,action,await body(request,256000))

    @app.get('/api/process/{pid}/retrieval')
    async def retrieval_task(pid:str):
        view=await asyncio.to_thread(c.local_agent_view,pid)
        return {'process_id':pid,'retrieval':view['retrieval'],'retrieval_state':view['retrieval_state'],
                'retrieval_context':view.get('retrieval_context'),
                'instruction':'Claude uses approved read-only Zowe CLI and Db2 MCP for request-bound retrieval, then local analysis, development, testing and review. Raw records stay local for programmatic comparisons.'}

    @app.get('/api/process/{pid}/development')
    async def development_view(pid:str):return await asyncio.to_thread(c.development_view,pid)

    @app.post('/api/process/{pid}/development')
    async def prepare_development(pid:str,request:Request):
        require(await body(request,1024)=={},'Development preparation accepts no source or custom instructions')
        return await asyncio.to_thread(c.prepare_development,pid)

    @app.post('/api/process/{pid}/development/revise')
    async def revise_development(pid:str,request:Request):
        payload=await body(request,1024);require(set(payload)=={'reason','handoff_id'},'Supply the current handoff ID and revision reason')
        return await asyncio.to_thread(c.revise_development,pid,payload['reason'],payload['handoff_id'])

    @app.get('/api/development/{handoff_id}')
    async def development_task(handoff_id:str):return await asyncio.to_thread(c.development_task,handoff_id)

    @app.post('/api/development/{handoff_id}/return')
    async def development_return(handoff_id:str,request:Request):
        from .development import MAX_RETURN_BYTES
        return await asyncio.to_thread(c.submit_development,handoff_id,await body(request,MAX_RETURN_BYTES))

    @app.get('/api/process/{pid}/agent/task')
    async def agent_task(pid:str):
        task=await asyncio.to_thread(c.agent_task,pid)
        require((task.get('data_policy') or {}).get('source_identity_mode')=='OPAQUE_HASH_REFERENCES',
                'Historical private task is preserved; refresh through the local agent before model access')
        return task
    @app.get('/api/process/{pid}/agent/lineage')
    async def agent_lineage(pid:str):
        doc=c.ledger.get(pid);c.sources(doc)
        require(doc.get('lineage_artifact'),'Start this process to map its lineage')
        task=c.agent_task(pid)
        require((task.get('data_policy') or {}).get('source_identity_mode')=='OPAQUE_HASH_REFERENCES',
                'Historical private lineage is preserved; refresh through the local agent before model access')
        return task['lineage']
    @app.get('/api/process/{pid}/agent/source')
    async def agent_source(pid:str,path:str,start_line:int=1,end_line:int|None=None):
        raise ValidationError('Raw source requires an explicitly approved sanitized view before model access')
    @app.post('/api/process/{pid}/agent/analysis')
    async def agent_analysis(pid:str,request:Request):
        submitted=await body(request,128*1024)
        return await asyncio.to_thread(c.submit_agent_analysis,pid,submitted)
    @app.post('/api/demo')
    async def demo():
        examples=Path(__file__).parent.parent/'examples';pid='demo-'+secrets.token_hex(4)
        manifest=(examples/'process-input.md').read_bytes().decode('utf-8').replace('example-referral',pid)
        sources={p.name:p.read_bytes().decode('utf-8') for p in (examples/'Endeavor').iterdir() if p.is_file()}
        doc=c.create(manifest,sources,True);return c.start(doc['id'])
    @app.post('/api/process/{pid}/{action}')
    async def action(pid:str,action:str,request:Request):
        if action=='start':return c.start(pid)
        if action=='refresh-analysis':return c.refresh_analysis(pid)
        if action in ('pause','resume','cancel'):return c.control(pid,action)
        require(action=='answers','Unknown action')
        from .review import MAX_HTML_REVIEW_BYTES
        b=await body(request,MAX_HTML_REVIEW_BYTES*4//3+4096)
        field='html' if 'html' in b else 'xlsx'
        require(not ('html' in b and 'xlsx' in b) and isinstance(b.get(field),str),'Supply the returned checklist as base64 text in exactly one xlsx or html field')
        try:data=base64.b64decode(b[field],validate=True)
        except (ValueError,KeyError) as exc:raise ValidationError('Supply the actual returned checklist file') from exc
        return c.import_answers(pid,data,b.get('reviewer',''))
    @app.get('/api/process/{pid}/events')
    async def events(pid:str):return c.ledger.events(pid)
    @app.get('/api/process/{pid}/comparison')
    async def comparison(pid:str,request:Request,program:str='',status:str='all',after:int=0,limit:int=25):
        allowed={'program','status','after','limit'}
        require(all(key in allowed and len(request.query_params.getlist(key))==1 for key in request.query_params),
                'Comparison query contains an unknown or repeated parameter')
        return await asyncio.to_thread(c.program_comparison,pid,program=program,status=status,after=after,limit=limit)

    @app.get('/api/process/{pid}/coverage')
    async def coverage(pid:str):
        from .coverage import build_coverage
        return await asyncio.to_thread(build_coverage,c.ledger.get(pid),c.root)
    @app.get('/api/process/{pid}/artifact')
    async def artifact(pid:str,path:str,request:Request,inline:bool=False):
        if inline:
            from .executive import accepted_executive
            require(request.query_params.getlist('path')==[path] and len(request.query_params.getlist('inline'))==1,
                    'Inline report parameters must be unambiguous')
            published=accepted_executive(c,c.ledger.get(pid))
            require(published['executive_report']==path,'Only the accepted primary executive report can be opened inline')
            p=c.artifact(pid,path)
            # The accepted report keeps relative links for downloaded bundles. The
            # browser view points the fixed evidence links at verified local
            # artifact reads, leaving the frozen report bytes unchanged.
            from .executive import EVIDENCE_FILES
            allowed=EVIDENCE_FILES
            def evidence_link(match):
                name=match.group(1)
                require(name in allowed,'Unsupported inline report evidence link')
                relative='analysis/source-analysis.json' if name.startswith('../../') else str(Path(path).parent/name).replace('\\','/')
                url='/api/process/'+quote(pid,safe='')+'/artifact?'+urlencode({'path':relative})
                return 'href="'+html.escape(url,quote=True)+'"'
            content=re.sub(r'href="([^"]+)"',evidence_link,p.read_text(encoding='utf-8'))
            return Response(content,media_type='text/html',headers={
                'Content-Disposition':'inline; filename="executive-report.html"',
                'Content-Security-Policy':"default-src 'none'; style-src 'unsafe-inline'; script-src 'none'; connect-src 'none'; form-action 'none'; frame-ancestors 'none'; base-uri 'none'"})
        p=c.artifact(pid,path);return Response(p.read_bytes(),media_type='application/octet-stream',headers={'Content-Disposition':'attachment; filename="'+p.name+'"'})
    @app.get('/{asset:path}')
    async def frontend(asset:str):
        if not asset:asset='index.html'
        p=safe_path(static,asset);require(p.is_file(),'Build the frontend first; see START_HERE.md')
        types={'.html':'text/html','.js':'text/javascript','.css':'text/css','.png':'image/png'}
        return Response(p.read_bytes(),media_type=types.get(p.suffix,'application/octet-stream'))
    return app
