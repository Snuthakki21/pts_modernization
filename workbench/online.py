"""Package an existing verified record adapter as a bounded online candidate."""
import inspect
import json
from pathlib import Path
from .domain import encode, sha, write_new, require, path_is_link
from .target import run_generated

LIMITATIONS=['Local JSON record API and generated form; BMS layout, AID keys and native CICS behavior are not replaced',
             'Bearer token is local operator access, not RACF or enterprise user/role equivalence',
             'SQLite session/idempotency transactions do not implement Db2, VSAM, IMS or distributed commits']


def packaged_runtime():
    """Embed the shared path guard in the independently runnable target package."""
    # Normalize implementation checkout line endings only; source exports stay byte-exact.
    source = Path(__file__).with_name('online_runtime.py').read_text(encoding='utf-8')
    dependency = 'from .domain import path_is_link\n'
    require(source.count(dependency) == 1, 'Online runtime path guard dependency differs')
    return source.replace(dependency, inspect.getsource(path_is_link) + '\n', 1).encode('utf-8')


def deliver(coordinator, doc, run):
    """Freeze code and compare HTTP execution with independently frozen source cases."""
    from fastapi.testclient import TestClient
    from .online_runtime import create_app
    root=coordinator.process_root(doc['id'])
    output=root/'target'/run['id']/'online';output.mkdir(parents=True,exist_ok=True)
    spec={};codes={};transactions={}
    for tx in doc.get('transactions',[]):
        name=tx['program'];p=doc['analysis']['programs'].get(name);result=run['programs'].get(name)
        if not p or p['blockers'] or not result or result['differences'] or not result['coverage']['complete'] or not result.get('adversarial',{}).get('passed'):continue
        code=(coordinator.root/'shared/target/python'/(doc['program_versions'][name]+'.py')).read_text(encoding='utf-8')
        codes[name]=code
        spec[tx['id']]={'program':name,'source_path':p['path'],'source_hash':p['source_hash'],'target_hash':sha(code),'fields':p['fields'],'mapset':tx.get('mapset'),'map':tx.get('map'),'limitations':LIMITATIONS}
        transactions[tx['id']]={'api':'/api/transactions/'+tx['id'],'screen':'/','state':'IMPLEMENTED_UNVERIFIED','limitations':LIMITATIONS}
    screen_codes={}; screen_contracts={}
    if doc.get('cics_contract_version')==1:
        from .cics import selected_screens, emit_screen, LIMITATIONS as screen_limitations
        for screen in selected_screens(doc['analysis']):
            result=run.get('screens',{}).get(screen['id'])
            if not result or not result['passed'] or not result.get('adversarial',{}).get('passed') or not result.get('unit_tests',{}).get('passed'):continue
            code=emit_screen(screen); version=doc['screen_versions'].get(screen['id'])
            require(version==sha(code),'Screen target changed before HTTP delivery')
            screen_codes[screen['id']]=code
            screen_contracts[screen['id']]={**screen,'target_hash':version,'limitations':screen_limitations}
        for tx in doc.get('transactions',[]):
            bound=[screen for screen in screen_contracts.values() if screen['mapset']==tx.get('mapset') and screen['map']==tx.get('map') and tx['program'] in screen['owners']]
            if not bound:continue
            item=spec.setdefault(tx['id'],{'program':tx['program'],'fields':{},'mapset':tx.get('mapset'),'map':tx.get('map'),'record_supported':False,'limitations':screen_limitations})
            item['screens']=bound;item['limitations']=[*screen_limitations,*LIMITATIONS[1:]];item['controller_status']='UNVERIFIED';item['native_cics_verified']=False
            transactions.setdefault(tx['id'],{'api':None,'screen':'/','state':'LAYOUT_TESTED_CONTROLLER_UNVERIFIED','limitations':screen_limitations})
            transactions[tx['id']]['screen_apis']=['/api/screens/'+tx['id']+'/'+screen['id'] for screen in bound]
    if not spec:return {'transactions':{},'status':'BLOCKED','reason':'No fully tested business module or screen layout available'}
    delivery_limitations=([*screen_limitations,*LIMITATIONS[1:]] if screen_codes else LIMITATIONS)
    files={'contract.json':encode(spec),'runtime.py':packaged_runtime()}
    for name,code in codes.items():files['modules/'+sha(code)+'.py']=code.encode()
    for ident,code in screen_codes.items():files['screens/'+sha(code)+'.py']=code.encode()
    files['application.py']=b'''# Local target launcher; never connects to a mainframe.
import hashlib, importlib.util, json, os
from pathlib import Path
from runtime import create_app
from fastapi.responses import FileResponse
root=Path(__file__).resolve().parent
spec=json.loads((root/'contract.json').read_text(encoding='utf-8'))
programs={}
for item in spec.values():
    if item.get('record_supported') is False:continue
    name=item['program']; path=root/'modules'/(item['target_hash']+'.py')
    if path.resolve().parent!=root/'modules' or hashlib.sha256(path.read_bytes()).hexdigest()!=item['target_hash']:raise ValueError('Target integrity failed')
    module_spec=importlib.util.spec_from_file_location('business_'+name,path)
    module=importlib.util.module_from_spec(module_spec);module_spec.loader.exec_module(module)
    programs[name]=module.run_program
screens={}
for item in spec.values():
    for screen in item.get('screens',[]):
        path=root/'screens'/(screen['target_hash']+'.py')
        if path.resolve().parent!=root/'screens' or hashlib.sha256(path.read_bytes()).hexdigest()!=screen['target_hash']:raise ValueError('Screen integrity failed')
        module_spec=importlib.util.spec_from_file_location('screen_'+screen['id'],path)
        module=importlib.util.module_from_spec(module_spec);module_spec.loader.exec_module(module)
        screens[screen['id']]=module.run_screen
app=create_app(programs,spec,Path(os.environ.get('ONLINE_STATE',str(Path.home()/'.pts-online-state'/hashlib.sha256(json.dumps(spec,sort_keys=True).encode()).hexdigest())))/'sessions.sqlite',os.environ.get('ONLINE_TOKEN',''),screens=screens)
@app.get('/')
def screen():return FileResponse(root/'index.html')
@app.get('/app.js')
def script():return FileResponse(root/'app.js',media_type='text/javascript')
if __name__=='__main__':
    import uvicorn
    uvicorn.run(app,host='127.0.0.1',port=int(os.environ.get('ONLINE_PORT','8766')))
'''
    files['index.html']=b'<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Process screen and transaction pilot</title><div id="root"></div><script src="/app.js" defer></script></html>'
    # The React bundle is built once with the existing locked frontend toolchain.
    bundle=Path(__file__).with_name('static')/'online.js';require(bundle.is_file(),'Build the online React client before delivery')
    files['app.js']=bundle.read_bytes()
    files['launch.sh']=b'#!/bin/sh\ncd "$(dirname "$0")" || exit 1\nexec "${WB_PYTHON:-python}" application.py\n'
    files['launch.cmd']=b'@echo off\r\ncd /d "%~dp0"\r\nif not defined WB_PYTHON set WB_PYTHON=python\r\n"%WB_PYTHON%" application.py\r\n'
    receipt={'passed':True,'cases':0,'transactions':{},'limitations':delivery_limitations,'observed_mainframe_parity':False}
    functions={name:(lambda row,code=code:run_generated(code,row)) for name,code in codes.items()}
    if screen_codes:receipt['screens']={}
    from .cics import prepare_screen
    screen_functions={ident:prepare_screen(code) for ident,code in screen_codes.items()}
    # Runtime data is private development state; issued target files stay immutable.
    import tempfile
    scratch=coordinator.root/'.implementation/tmp';scratch.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(dir=scratch) as temp:
        app=create_app(functions,spec,Path(temp)/'test.sqlite','fixture-token-'+'x'*32,screens=screen_functions)
        files['openapi.json']=encode(app.openapi())
        with TestClient(app) as client:
            headers={'Authorization':'Bearer '+'fixture-token-'+'x'*32}
            for tx,item in spec.items():
                for screen in item.get('screens',[]):
                    suite=json.loads((root/'synthetic'/run['id']/screen['id']/'expected.json').read_text(encoding='utf-8'))
                    comparison=compare_screen_http(client,headers,tx,screen,suite,checkpoint=lambda:coordinator.checkpoint(doc,persist=False))
                    receipt['screens'][tx+':'+screen['id']]=comparison
                    receipt['cases']+=comparison['cases'];receipt['passed'] &= comparison['passed']
                if item.get('record_supported') is False:continue
                suite=json.loads((root/'synthetic'/run['id']/item['program']/'expected.json').read_text(encoding='utf-8'))
                total=0;differences=[]
                for case in suite['cases']:
                    coordinator.checkpoint(doc,persist=False)
                    session=client.post('/api/sessions',json={'transaction':tx},headers=headers).json()
                    response=client.post('/api/transactions/'+tx,headers={**headers,'X-Session-ID':session['session_id'],'Idempotency-Key':case['id']},json={'record':case['record'],'revision':0})
                    expected=case['expected']
                    matched=response.status_code==422 if expected.get('input_status')=='REJECT_INPUT' else response.status_code==200 and response.json().get('result')==expected
                    if not matched:differences.append(case['id'])
                    client.delete('/api/sessions/'+session['session_id'],headers=headers);total+=1
                receipt['transactions'][tx]={'cases':total,'differences':differences};receipt['cases']+=total;receipt['passed'] &= total>0 and not differences
    files['verification.json']=encode(receipt)
    files['package.json']=encode({'schema_version':1,'profile':'LOCAL_ONLINE_CANDIDATE','files':{name:sha(data) for name,data in files.items()},'limitations':delivery_limitations})
    for name,data in files.items():
        coordinator.checkpoint(doc,persist=False)
        path=output/name;write_new(path,data);coordinator.register(doc,path.relative_to(root).as_posix())
    return {'transactions':transactions,'status':'HTTP_COMPARISON_PASSED' if receipt['passed'] else 'HTTP_COMPARISON_FAILED','evidence':(output/'verification.json').relative_to(root).as_posix(),'package':(output/'package.json').relative_to(root).as_posix(),'cases':receipt['cases'],'native_cics_verified':False}


def compare_screen_http(client, headers, transaction, screen, suite, checkpoint=None):
    """Compare complete actual HTTP outcomes, including invalid source requests."""
    actual=[]; differences=[]
    for case in suite['cases']:
        if checkpoint:checkpoint()
        response=client.post('/api/screens/'+transaction+'/'+screen['id'],headers=headers,json={'values':case['values']})
        expected_status=200 if case['expected']['input_status']=='ACCEPT_INPUT' else 422
        body=response.json()
        expected={'result':case['expected'],'evidence_basis':'SOURCE_DERIVED_EXPECTED','native_controller_verified':False}
        if response.status_code!=expected_status or encode(body)!=encode(expected):differences.append(case['id'])
        actual.append({'case_id':case['id'],'status':response.status_code,'body':body})
    return {'passed':bool(actual) and not differences and suite['coverage']['complete'],'cases':len(actual),'differences':differences,
            'actual':actual,'screen_hash':sha(encode(screen)),'suite_hash':sha(encode(suite)),'native_controller_verified':False}


def replay_screen_http(doc, root, base, screen, suite, checkpoint=None):
    """Reproduce authenticated transport receipts from the pinned package."""
    import tempfile
    from fastapi.testclient import TestClient
    from .coverage import _read
    from .cics import prepare_screen, emit_screen
    from .online_runtime import create_app
    from .domain import safe_path
    run=doc['runs'][-1]['id'];folder=base/'target'/run/'online'
    package_raw=_read(folder/'package.json')
    require(sha(package_raw)==doc.get('artifact_hashes',{}).get((folder/'package.json').relative_to(base).as_posix()),'Online package receipt changed')
    package=json.loads(package_raw)
    require(package.get('profile')=='LOCAL_ONLINE_CANDIDATE' and isinstance(package.get('files'),dict),'Online package contract differs')
    for name,version in package['files'].items():
        path=safe_path(folder,name);raw=_read(path)
        require(sha(raw)==version and doc.get('artifact_hashes',{}).get(path.relative_to(base).as_posix())==version,'Online package artifact changed: '+name)
    require(_read(folder/'runtime.py')==packaged_runtime(),'Packaged runtime differs from the audited adapter')
    spec=json.loads(_read(folder/'contract.json'));receipt=json.loads(_read(folder/'verification.json'))
    code=emit_screen(screen); require(_read(folder/'screens'/(sha(code)+'.py'))==code.encode(),'Packaged screen target differs')
    matched=[]
    scratch=root/'.implementation/tmp';scratch.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(dir=scratch) as temp:
        app=create_app({},spec,Path(temp)/'http-replay.sqlite','fixture-token-'+'x'*32,screens={screen['id']:prepare_screen(code)})
        with TestClient(app) as client:
            for tx,item in spec.items():
                pinned=next((s for s in item.get('screens',[]) if s['id']==screen['id']),None)
                if pinned is None:continue
                from .cics import LIMITATIONS as limitations
                require(pinned=={**screen,'target_hash':sha(code),'limitations':limitations},'HTTP screen contract differs from selected source')
                require(any(t['id']==tx and t['program'] in screen['owners'] and t.get('mapset')==screen['mapset'] and t.get('map')==screen['map'] for t in doc['transactions']),'HTTP screen binding differs from process')
                result=compare_screen_http(client,{'Authorization':'Bearer '+'fixture-token-'+'x'*32},tx,pinned,suite,checkpoint=checkpoint)
                require(result['passed'] and result==receipt.get('screens',{}).get(tx+':'+screen['id']),'HTTP screen comparisons do not reproduce')
                matched.append(tx)
    require(bool(matched),'Screen has no verified transaction-bound HTTP route')
    return [(folder/'verification.json','reproduced_fastapi_screen_comparison'),(folder/'contract.json','source_bound_screen_http_contract'),(folder/'package.json','immutable_online_package')]
