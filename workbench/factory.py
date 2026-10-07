"""Evidence-only factory projections; the Coordinator remains the sole engine."""
import re
from .domain import encode, sha

# Recognition is deliberately independent of executable adapter support.
CAPABILITIES = {
    'cobol': ('COBOL control, data and lifetime', r'cobol|perform|paragraph|linkage'),
    'languages': ('Other languages and wrappers', r'assembler|pli|pl/i|rexx|easytrieve|wrapper'),
    'online': ('CICS, BMS, session and transaction behavior', r'cics|bms|commarea|channel|aid'),
    'jobs': ('JCL, PROC, allocation and restart', r'jcl|proc|dd |gdg|disp|restart'),
    'utilities': ('Utilities, control cards and exits', r'utility|sort|idcams|ikjeft|ieb|bpxbatch'),
    'db2': ('Db2 types, SQL and transaction boundaries', r'db2|sql|cursor|commit|rollback'),
    'files': ('Datasets, VSAM and record semantics', r'vsam|dataset|file |record|lrecl'),
    'ims': ('IMS database and transaction services', r'\bims\b|\bdli\b'),
    'mq': ('MQ, delivery and recovery', r'\bmq\b|message|queue'),
    'interfaces': ('External APIs, transfers and protocols', r'interface|http|ftp|socket|external'),
    'encoding': ('CCSID, numeric formats and collation', r'ccsid|ebcdic|comp-3|packed|decimal|collat|encoding'),
    'security': ('Identity, authorization and audit', r'racf|security|authoriz|authentic'),
    'scheduling': ('Calendars, triggers and business dates', r'ca7|scheduler|calendar|cutoff|business.date'),
    'operations': ('Recovery, availability and operations', r'abend|recover|checkpoint|availability'),
}
STAGES = ('assessment','discovery','target_design','implementation','human_review','verification','delivery')
STAGE_BY_STATUS = {
    'READY':'assessment', 'QUEUED_ANALYSIS':'discovery','ANALYZING':'discovery',
    'WAITING_DISCOVERY':'discovery','WAITING_REQUIREMENTS':'target_design','WAITING_COPILOT':'implementation','WAITING_SME':'human_review',
    'QUEUED_VERIFY':'verification','VERIFYING':'verification','QUEUED_REPORT':'delivery',
    'REPORTING':'delivery','REPORTING_FAILED':'delivery','COMPLETED':'delivery','COMPLETED_WITH_BLOCKERS':'delivery',
}
INVESTIGATION = ['Retrieve cited source and release/site-specific documentation',
                 'Inspect existing verified adapters and dependency contracts',
                 'Implement and independently test an equivalent or compatibility adapter',
                 'Evaluate an explicit target design change; retain behavior differences',
                 'Record exact missing evidence or unsupported semantics if unresolved']


def consistency_findings(doc):
    """Cheap invariants at stage boundaries. Disk integrity remains Coordinator-owned."""
    findings=[]
    def flag(code, message):findings.append({'id':code,'severity':'BLOCKING','message':message})
    if doc.get('packet_imported') and not doc.get('packet_issued'):flag('RETURN_WITHOUT_PACKET','Imported return has no issued packet')
    if doc.get('packet_imported') and not doc.get('answers'):flag('RETURN_WITHOUT_ANSWERS','Imported return has no attributed answers')
    if doc.get('status')=='COMPLETED' and (doc.get('blockers') or not doc.get('report_verified')):
        flag('INVALID_COMPLETION','Completed status conflicts with blockers or report acceptance')
    analysis=doc.get('analysis') or {}
    programs=analysis.get('programs',{})
    for name in doc.get('program_versions',{}):
        if name not in programs or programs[name].get('blockers'):flag('TARGET_WITHOUT_SUPPORTED_SOURCE:'+name,'Target version lacks supported source analysis: '+name)
    rules=analysis.get('rules',[])
    if len({r['id'] for r in rules})!=len(rules):flag('DUPLICATE_RULE_ID','Rule IDs are not unique')
    for tx in doc.get('transactions',[]):
        if analysis and tx['program'] not in programs:flag('TRANSACTION_PROGRAM_MISSING:'+tx['id'],'Transaction entry program is absent from selected analysis')
    return findings


def validation_view(doc, coverage=None):
    run=(doc.get('runs') or [{}])[-1]
    programs=list(run.get('programs',{}).values())
    unit=[r.get('unit_tests') for r in programs]
    validation=doc.get('logic_validation') or {}
    intact=coverage is not None and not coverage['summary']['integrity_errors']
    status='NOT_RUN' if not doc.get('verification_finished') else 'GAPS' if not validation.get('complete') or coverage is not None and not intact else 'PASSED' if intact else 'RECORDED_PASS'
    return {'minimum_distinct_records_per_logic':doc.get('logic_validation_min_records',0),
            'fixture_contract_version':doc.get('fixture_contract_version'),
            'seed':str(doc['authorization']['seed']) if 'seed' in (doc.get('authorization') or {}) else None,
            'status':status,'evidence_state':'REPLAYED' if coverage is not None else 'RECORDED_NOT_RECHECKED',
            'program_count':len(programs),'unit_tests_run':sum((item or {}).get('tests_run',0) for item in unit),
            'unit_tests_passed':(all(item and item.get('passed') for item in unit) and (coverage is None or intact)) if unit else None,
            'job_cases':validation.get('job_cases'),'evidence':validation.get('evidence')}


def factory_view(doc, coverage=None):
    analysis=doc.get('analysis') or {}
    blockers=doc.get('blockers',[])
    assets=[a for a in analysis.get('assets',[]) if a.get('selected',True)]
    capabilities=[]
    for key,(label,pattern) in CAPABILITIES.items():
        paths=sorted({a['path'] for a in assets if re.search(pattern,a.get('kind','')+' '+a.get('source_text',''),re.I)})
        gaps=[b for b in blockers if re.search(pattern,b.get('kind','')+' '+b.get('message',''),re.I)]
        capabilities.append({'id':key,'label':label,'state':'ANALYZED_WITH_GAPS' if gaps else 'RECOGNIZED' if paths else 'NOT_ASSESSED',
                             'source_count':len(paths),'source_paths':paths[:20],'source_paths_complete':len(paths)<=20,'gap_count':len(gaps),
                             'verification_scope':None})
    obligations=[]
    for b in blockers:
        basis={k:v for k,v in b.items() if k not in ('recorded','failure')}
        obligations.append({'id':'OBL_'+sha(encode(basis))[:24],'kind':b.get('kind','unknown'),
                            'requirement':b.get('message','Unresolved obligation'),'evidence':{k:b[k] for k in ('path','lines','source_refs','program','object') if k in b},
                            'status':'UNRESOLVED'})
    current=STAGE_BY_STATUS.get(doc.get('status'),STAGE_BY_STATUS.get(doc.get('resume_status'),'assessment'))
    attempts=doc.get('stage_attempts',{})
    transactions=[]
    for tx in doc.get('transactions',[]):
        delivery=(doc.get('online_delivery') or {}).get('transactions',{}).get(tx['id'],{})
        transactions.append({**tx,'api':delivery.get('api'),'screen':delivery.get('screen'),
                             'state':delivery.get('state','IDENTIFIED'),'native_cics_verified':False,
                             'limitations':delivery.get('limitations',['Source transaction semantics require verified replacements'])})
    from .backends import target_architecture
    return {'target_architecture':target_architecture(doc),'validation':validation_view(doc,coverage),'schema_version':1,'process_id':doc['id'],'process_revision':doc.get('revision'),
            'source_snapshot':analysis.get('source_snapshot'),'stage':current,'stages':list(STAGES),
            'capabilities':capabilities,'obligations':obligations,'transactions':transactions,
            'attempts':attempts,'last_failure':doc.get('last_failure'),
            'continuation':{'progress':'UNCHANGED' if doc.get('previous_analysis_hash')==sha(encode(analysis)) else 'CHANGED_OR_INITIAL',
                            'automatic_work':'Continue independent eligible tasks through the existing Coordinator; never repeat an unchanged failed approach',
                            'human_return_required':doc.get('status')=='WAITING_SME'},
            'service_design':{'default':'modular_application','extraction_requires':['independent business responsibility','data ownership','verified transaction boundary'],'database':'SQLite; unsupported semantics remain gaps'},
            'consistency':consistency_findings(doc),
            'counts':{'obligations':len(obligations),'transactions':len(transactions),'verified_capabilities':0,
                      'implemented_api_candidates':sum(t['state']=='IMPLEMENTED_UNVERIFIED' for t in transactions)},
            'investigation_strategy':INVESTIGATION,
            'scope':'Capability recognition is not complete support. Source-derived verification is distinct from observed mainframe parity.'}


def bounded_view(doc, after=0, program_after=0):
    from .domain import require
    require(type(after) is int and after>=0,'Invalid factory cursor')
    view=factory_view(doc);items=view.pop('obligations');require(after<=len(items),'Invalid factory cursor')
    from .program_insights import program_insights
    view['program_insights']=program_insights(doc,after=program_after)
    view.update(obligations=items[after:after+50],total=len(items),next_after=min(after+50,len(items)),has_more=after+50<len(items))
    return view


def render_factory(view):
    from html import escape
    e=lambda value:escape(str(value))
    rows=''.join('<tr>'+''.join('<td>'+e(item[k])+'</td>' for k in ('label','state','source_count','gap_count'))+'</tr>' for item in view['capabilities'])
    transactions=''.join('<tr>'+''.join('<td>'+e(item.get(k))+'</td>' for k in ('id','program','mapset','map','api','state'))+'</tr>' for item in view['transactions'])
    gaps=''.join('<li><strong>'+e(item['id'])+'</strong> '+e(item['requirement'])+'</li>' for item in view['obligations'])
    architecture=view.get('target_architecture',{})
    candidates=''.join('<tr><td>'+e(c['title'])+'</td><td>'+e(c['implementation_status'])+'</td><td>'+e(c['scope'])+'</td></tr>' for c in architecture.get('candidates',[]))
    architecture_html='<h2>Target architecture</h2><p><strong>'+e(architecture.get('title','Not assessed'))+'</strong></p><p>'+e(architecture.get('rationale',''))+'</p><table><tr><th>Target</th><th>Implementation</th><th>Scope</th></tr>'+candidates+'</table><ul>'+''.join('<li>'+e(o['title'])+': '+e(o['status'])+'</li>' for o in architecture.get('obligations',[]))+'</ul>'
    validation=view.get('validation',{})
    validation_html='<h2>Runtime validation</h2><p>'+e(validation.get('status'))+' · minimum '+e(validation.get('minimum_distinct_records_per_logic'))+' distinct records per supported logic · seed '+e(validation.get('seed'))+' · '+e(validation.get('unit_tests_run'))+' generated unit tests executed. Dataset, scheduler and observed mainframe parity require separate evidence.</p>'
    return '<!doctype html><html lang="en"><meta charset="utf-8"><title>Modernization factory</title><style>body{font:16px system-ui;max-width:1100px;margin:2rem auto;padding:1rem}table{border-collapse:collapse;width:100%}td,th{border-bottom:1px solid #ccc;padding:.5rem;text-align:left;overflow-wrap:anywhere}</style><h1>Modernization factory</h1><p>'+e(view['scope'])+'</p>'+architecture_html+validation_html+'<p><a href="program-insights.html">Explore application inventory and program knowledge</a></p><h2>Capabilities</h2><table><tr><th>Area</th><th>Evidence state</th><th>Sources</th><th>Gaps</th></tr>'+rows+'</table><h2>Online mappings</h2><p>Generated API candidates do not earn CICS or BMS conversion credit.</p><table><tr><th>Transaction</th><th>Program</th><th>Mapset</th><th>Map</th><th>API</th><th>State</th></tr>'+transactions+'</table><h2>Unresolved obligations</h2><ul>'+gaps+'</ul></html>'
