"""Execute record-based job orchestration against independently interpreted rules."""
import re
from .reference import run_reference
from .target import run_generated, emit_jobs
from .domain import encode, sha, require, safe_path

def verify_jobs(doc,root,jobs,checkpoint=None):
    if doc.get('fixture_contract_version') == 4:
        return _verify_jobs_v4(doc,root,jobs,checkpoint)
    require(jobs==emit_jobs(doc,doc['program_versions']), 'Job template differs from validated manifest generation')
    programs=doc['analysis']['programs']
    if not programs:return {'matched':False,'reason':'No supported program to execute'}
    if any(p['blockers'] for p in programs.values()):return {'matched':False,'reason':'Unsupported source program cannot receive integration credit'}
    if not doc['jobs'] or any(not job['steps'] for job in doc['jobs']):
        return {'matched':False,'reason':'No complete ordered job baseline to execute'}
    require(set(doc['program_versions']) == set(programs), 'Program versions do not exactly match analyzed programs')
    first=next(iter(programs.values()));fields=set(first['fields'])
    if any(set(p['fields'])!=fields for p in programs.values()):return {'matched':False,'reason':'Programs have different record layouts; an explicit input/output mapping adapter is required'}
    if any(any((p['fields'][k]['type'],p['fields'][k]['width'])!=(first['fields'][k]['type'],first['fields'][k]['width']) for k in fields) for p in programs.values()):return {'matched':False,'reason':'Record field types or widths differ; explicit record mapping is required'}
    record={k:v['default'] for k,v in first['fields'].items()};row=dict(record);expected={}
    for job in doc['jobs']:
        results=[];rc=0
        for step in job['steps']:
            if checkpoint:checkpoint()
            text=re.sub(r'\s+','',step['condition'].upper());execute=text in ('ALWAYS','')
            if not execute:
                m=re.fullmatch(r'RC(<=|>=|=|<|>)(\d+)',text)
                if not m:return {'matched':False,'reason':'Unresolved job condition'}
                n=int(m[2]);execute={'<=':rc<=n,'>=':rc>=n,'=':rc==n,'<':rc<n,'>':rc>n}[m[1]]
            if execute:
                p=programs[step['program'].upper()];r=run_reference(p,row)
                if r['input_status']!='ACCEPT_INPUT':return {'matched':False,'reason':'Source reference rejected the integration record'}
                row=r['record'];rc=r['return_code'];results.append({'step':step['name'],'version':doc['program_versions'][p['name']],**r})
            else:results.append({'step':step['name'],'status':'SKIPPED'})
        expected[job['name']]=results
    target={}
    for name,v in doc['program_versions'].items():
        require(isinstance(v,str) and re.fullmatch(r'[a-f0-9]{64}',v) is not None,'Invalid pinned target version')
        raw=safe_path(root,'shared/target/python/'+v+'.py').read_bytes()
        require(sha(raw)==v,'Pinned job target changed')
        code=raw.decode('utf-8')
        def execute(record,code=code):
            if checkpoint:checkpoint()
            return run_generated(code,record)
        target[name]=execute
    namespace={'__builtins__':{}};exec(compile(jobs,'<trusted-job-generator>','exec'),namespace)
    actual=namespace['run_process']({'record':record},target)
    return {'matched':encode(expected)==encode(actual),'reason':'Ordered record-adapter job comparison; DSN I/O and external scheduling are outside this profile','expected':expected,'actual':actual,'observed_mainframe_parity':False,'integration_cases':1,'io_adapter':'in_memory_record_only','dataset_io_verified':False}


def _verify_jobs_v4(doc,root,jobs,checkpoint=None):
    """Seeded record dispatch evidence; no invented native scheduler/RC behavior."""
    import random
    from .fixtures import plan_cases
    from .reference import input_errors
    from .target import prepare_generated
    seed=doc['authorization']['seed'];budget=doc['authorization']['max_cases_per_program']
    require(type(seed) is int and 0<=seed<2**63 and type(budget) is int and 1<=budget<=10000,'Invalid job validation seed or budget')
    # Preserve all established template/layout/version checks and baseline keys.
    baseline=verify_jobs({k:v for k,v in doc.items() if k!='fixture_contract_version'},root,jobs,checkpoint)
    if 'expected' not in baseline:return baseline
    programs=doc['analysis']['programs'];first=next(iter(programs.values()))
    rng=random.Random(seed);minimum=20;candidates={}
    def add(record,randomized=False):
        if len(candidates)>=budget or any(input_errors(p,record) for p in programs.values()):return
        key=sha(encode(record))
        if key not in candidates:candidates[key]=(record,randomized)
    required={};optional={};candidate_gaps=[]
    default={k:f['default'] for k,f in first['fields'].items()}
    required[sha(encode(default))]=(default,'Source-layout baseline')
    # Reserve randomized capacity before optional Cartesian interactions. Every
    # mandatory boundary that cannot fit remains an explicit gap.
    for program in programs.values():
        source_suite=plan_cases(program,seed,256)
        for case in source_suite['cases']:
            if any(input_errors(p,case['record']) for p in programs.values()):continue
            destination=optional if case['reason']=='Source-predicate interaction witness' else required
            destination[sha(encode(case['record']))]=(case['record'],case['reason'])
        for gap in source_suite['coverage']['obligation_gaps']:
            if gap['reason'].startswith(('Boundary/domain witness','Source-layout baseline')):
                candidate_gaps.append({'program':program['name'],**gap})
    alphabet='0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz '
    random_goal=min(64,budget);random_candidates={}
    for _ in range(max(256,random_goal*16)):
        if len(random_candidates)>=random_goal:break
        record={name:rng.randrange(spec['max']+1) if spec['type']=='integer' else ''.join(rng.choice(alphabet) for _ in range(spec['width']))
                for name,spec in sorted(first['fields'].items())}
        if not any(input_errors(p,record) for p in programs.values()):random_candidates[sha(encode(record))]=record
    random_rows=list(random_candidates.values())
    for record in random_rows[:minimum]:add(record,True)
    for record,_ in required.values():add(record)
    for record in random_rows[minimum:]:add(record,True)
    for record,_ in optional.values():add(record)
    candidate_gaps.extend({'record_hash':key,'reason':reason,'status':'budget_exhausted',
                           'explanation':'Required valid source boundary omitted from job integration budget; no full integration credit.'}
                          for key,(_,reason) in required.items() if key not in candidates)
    targets={}
    for name,version in doc['program_versions'].items():
        raw=safe_path(root,'shared/target/python/'+version+'.py').read_bytes()
        require(sha(raw)==version,'Pinned job target changed')
        prepared=prepare_generated(raw.decode())
        def execute(record,prepared=prepared):
            if checkpoint:checkpoint()
            return prepared(record)
        targets[name]=execute
    namespace={'__builtins__':{}};exec(compile(jobs,'<trusted-job-generator>','exec'),namespace)
    steps={(j['name'],s['name']):{'job':j['name'],'step':s['name'],'program':s['program'],
            'records':set(),'randomized_records':set(),'outcomes':set(),'condition':s['condition']} for j in doc['jobs'] for s in j['steps']}
    cases=[]
    for record,randomized in candidates.values():
        if checkpoint:checkpoint()
        row=dict(record);expected={}
        for job in doc['jobs']:
            results=[];rc=0
            for step in job['steps']:
                if checkpoint:checkpoint()
                text=re.sub(r'\s+','',step['condition'].upper());execute=text in ('ALWAYS','')
                if not execute:
                    match=re.fullmatch(r'RC(<=|>=|=|<|>)(\d+)',text)
                    require(match is not None,'Unresolved job condition')
                    value=int(match[2]);execute={'<=':rc<=value,'>=':rc>=value,'=':rc==value,'<':rc<value,'>':rc>value}[match[1]]
                state=steps[job['name'],step['name']];state['outcomes'].add(execute)
                if execute:
                    fingerprint=sha(encode(row));state['records'].add(fingerprint)
                    if randomized:state['randomized_records'].add(fingerprint)
                    program=programs[step['program'].upper()];result=run_reference(program,row)
                    require(result['input_status']=='ACCEPT_INPUT','Source rejected job validation record')
                    row=result['record'];rc=result['return_code']
                    results.append({'step':step['name'],'version':doc['program_versions'][program['name']],**result})
                else:results.append({'step':step['name'],'status':'SKIPPED'})
            expected[job['name']]=results
        actual=namespace['run_process']({'record':dict(record)},targets)
        cases.append({'id':'job_case_'+str(len(cases)).zfill(4),'record':record,'randomized':randomized,
                      'expected':expected,'actual':actual,'matched':encode(expected)==encode(actual)})
    gaps=list(candidate_gaps);summaries=[]
    for state in steps.values():
        count=len(state['records']);random_count=len(state['randomized_records'])
        if count<minimum or random_count<minimum:
            gaps.append({'job':state['job'],'step':state['step'],'required':minimum,'observed':count,'randomized_observed':random_count,
                         'reason':'Fewer than 20 distinct source-valid executed step states with randomized witnesses; skipped, constrained or budget-limited steps receive no full integration credit.'})
        summaries.append({k:v for k,v in state.items() if k not in ('records','randomized_records','outcomes')} |
                         {'executed_records':count,'randomized_executed_records':random_count,
                          'record_hashes':sorted(state['records']),'condition_outcomes':sorted(state['outcomes']),
                          'unreachable_outcomes':[{'outcome':v,'basis':'Unconditional manifest step always executes.' if state['condition'].strip().upper() in ('ALWAYS','') else 'Supported flat record programs return RC=0; positive/nonzero RC requires a separate source adapter.'}
                                                  for v in (False,True) if v not in state['outcomes']]})
    matched=bool(cases) and all(c['matched'] for c in cases)
    validation={'contract_version':4,'minimum_distinct_records_per_step':minimum,'steps':summaries,'gaps':gaps,
                'source_state_coverage_complete':not gaps,'target_comparisons_matched':matched,'complete':not gaps and matched}
    return {**baseline,'matched':validation['complete'],
            'reason':'Seeded source-valid ordered record comparisons; every credited step needs 20 distinct executed states and randomized witnesses. Native scheduling/dataset I/O remain outside this adapter.',
            'cases':cases,'case_ids':[c['id'] for c in cases],'integration_cases':len(cases),'randomized_cases':sum(c['randomized'] for c in cases),
            'seed':seed,'validation':validation}
