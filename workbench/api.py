"""Loopback control API; explicit bounds and same-origin mutation protection."""
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
        result=dict(doc)
        result['blocker_count']=len(doc.get('blockers',[]))
        result['blockers']=doc.get('blockers',[])[:50]
        result['blockers_truncated']=result['blocker_count']>50
        result['runs']=[{k:v for k,v in run.items() if k!='programs'}|{'programs':{name:{k:v for k,v in r.items() if k not in ('actual','differences')}|{'case_count':len(r['actual']),'difference_count':len(r['differences'])} for name,r in run['programs'].items()}} for run in doc['runs']]
        if doc.get('analysis'):
            accounting=doc['analysis'].get('source_accounting')
            result['analysis']={k:v for k,v in doc['analysis'].items() if k not in ('programs','source_accounting')}
            result['analysis']['assets']=[{k:v for k,v in asset.items() if k not in ('source_text','coverage','rules','fields')} for asset in doc['analysis'].get('assets',[])]
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
        return {'processes':[display_process(p) for p in c.ledger.list(True)],'portfolio':portfolio(c.ledger),'token':token,
                'inventory_baseline':load_inventory(c.root),
                'provider_usage':c.provider.usage_summary() if c.provider else empty_usage_summary(),
                'capability':'Job-led discovery, Copilot Chat analysis and source accountability; executable credit requires verified semantic adapters.',
                'connections':{'zowe_profile_configured':bool(__import__('os').environ.get('WB_ZOWE_PROFILE')),'db2_endpoint_configured':bool(__import__('os').environ.get('WB_DB2_MCP_URL')),'llm_configured':bool(c.provider),'local_source_export':(c.root/'Endeavor').is_dir()}}
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
    @app.get('/api/templates/intake')
    async def template():
        path=Path(__file__).parent.parent/'examples/intake-template.xlsx'
        return Response(path.read_bytes(),media_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',headers={'Content-Disposition':'attachment; filename="intake-template.xlsx"'})
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
        return await asyncio.to_thread(c.create,b['manifest'],sources,False,b.get('prompt',''),b.get('assistant_mode','copilot_chat'))

    @app.get('/api/process/{pid}/agent/task')
    async def agent_task(pid:str):return await asyncio.to_thread(c.agent_task,pid)
    @app.get('/api/process/{pid}/agent/lineage')
    async def agent_lineage(pid:str):
        doc=c.ledger.get(pid);c.sources(doc)
        require(doc.get('lineage_artifact'),'Start this process to map its lineage')
        return decode(c.artifact(pid,doc['lineage_artifact']).read_bytes())
    @app.get('/api/process/{pid}/agent/source')
    async def agent_source(pid:str,path:str,start_line:int=1,end_line:int|None=None):
        from .copilot import source_excerpt
        doc=c.ledger.get(pid);return source_excerpt(doc,c.sources(doc),path,start_line,end_line)
    @app.post('/api/process/{pid}/agent/analysis')
    async def agent_analysis(pid:str,request:Request):
        submitted=await body(request,128*1024)
        return await asyncio.to_thread(c.submit_agent_analysis,pid,submitted)
    @app.post('/api/demo')
    async def demo():
        examples=Path(__file__).parent.parent/'examples';pid='demo-'+secrets.token_hex(4)
        manifest=(examples/'process-input.md').read_text().replace('example-referral',pid)
        sources={p.name:p.read_text() for p in (examples/'Endeavor').iterdir() if p.is_file()}
        doc=c.create(manifest,sources,True);return c.start(doc['id'])
    @app.post('/api/process/{pid}/{action}')
    async def action(pid:str,action:str,request:Request):
        if action=='start':return c.start(pid)
        if action=='refresh-analysis':return c.refresh_analysis(pid)
        if action in ('pause','resume','cancel'):return c.control(pid,action)
        require(action=='answers','Unknown action')
        b=await body(request)
        require(isinstance(b.get('xlsx'),str),'Supply the returned checklist as base64 text')
        try:data=base64.b64decode(b['xlsx'],validate=True)
        except (ValueError,KeyError) as exc:raise ValidationError('Supply the returned checklist workbook') from exc
        return c.import_answers(pid,data,b.get('reviewer',''))
    @app.get('/api/process/{pid}/events')
    async def events(pid:str):return c.ledger.events(pid)
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
            allowed={'coverage.html','metrics.json','management.pptx','inspection.json','../../analysis/source-analysis.json'}
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
