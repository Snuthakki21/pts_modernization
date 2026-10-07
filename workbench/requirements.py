"""Operator-selected conversion scope, with a canonical Markdown input.

Selections are requirements, never SME answers or proof of translation. Source
exports remain whole. Only independently parsed rule units can be omitted from
executable IR; excluding required platform/layout behavior leaves dependency gaps.
"""
from copy import deepcopy
from datetime import datetime
import re
import html
import json
from .domain import encode, decode, require, sha, identity, ValidationError

NO_REASON='Not converted because selected No in requirements.'
DRAFT='analysis/requirements.md'


def _screen_units(analysis):
    """New-intake screen descriptors only; old canonical selections stay byte-exact."""
    version=analysis.get('cics_contract_version')
    if version is None:return {},{}
    require(type(version) is int and version==1,'Unsupported frozen CICS selection contract')
    cics=analysis.get('cics') or {}
    require(cics.get('schema_version')==1 and isinstance(cics.get('units'),list) and isinstance(cics.get('screens'),list),'Invalid frozen CICS source descriptors')
    assets={a['path']:a for a in analysis.get('assets',[])};units={};owners={};source_facts={}
    for screen in cics['screens']:
        require(isinstance(screen,dict) and isinstance(screen.get('mapset'),str) and isinstance(screen.get('map'),str) and isinstance(screen.get('owners',[]),list),'Invalid frozen screen identity')
        key=screen['mapset']+'/'+screen['map']
        require(all(isinstance(name,str) for name in screen.get('owners',[])),'Invalid screen program ownership')
        owners[key]=sorted(set(owners.get(key,[])+screen.get('owners',[])))
    for row in cics['units']:
        require(isinstance(row,dict) and row.get('kind') in ('screen_definition','screen_field','screen_action'),'Invalid frozen screen unit')
        path=row.get('source_path');asset=assets.get(path)
        if asset is not None and path not in source_facts:source_facts[path]=(sha(asset.get('source_text','')),len(asset.get('source_text','').splitlines()))
        require(asset is not None and row.get('source_hash')==asset['source_hash'] and source_facts[path][0]==asset['source_hash'],'Screen source identity differs from retained export')
        start,end=row.get('start_line'),row.get('end_line')
        require(type(start) is int and type(end) is int and 1<=start<=end<=source_facts[path][1],'Invalid screen source span')
        require(isinstance(row.get('description'),str) and isinstance(row.get('replacement'),str) and type(row.get('required')) is bool and row.get('support') in ('layout_supported','unverified_controller','unsupported'),'Invalid frozen screen interpretation')
        require(row.get('program') is None or isinstance(row.get('program'),str),'Invalid screen program identity')
        require(isinstance(row.get('diagnostics',[]),list),'Invalid screen diagnostics')
        for number in range(start,end+1):
            require(number not in units.setdefault(path,{}),'Overlapping frozen screen source units')
            units[path][number]=row
    return units,owners


def catalog(analysis):
    items=[];files=[]
    programs={p['path']:p for p in analysis.get('programs',{}).values()}
    screen_units,screen_owners=_screen_units(analysis)
    screen_contract=analysis.get('cics_contract_version')==1
    source_owners={};screens_by_program={};screens_by_mapset={}
    if screen_contract:
        for program in programs.values():
            paths={dependency.get('path') for dependency in program.get('dependencies',[])}|{field.get('source_ref','').rsplit(':',1)[0] for field in program.get('fields',{}).values()}
            for path in paths:source_owners.setdefault(path,set()).add(program['name'])
        for key,names in screen_owners.items():
            screens_by_mapset.setdefault(key.split('/',1)[0],[]).append(key)
            for name in names:screens_by_program.setdefault(name,[]).append(key)
    for asset in sorted(analysis.get('assets',[]),key=lambda r:r['path']):
        path=asset['path'];lines=asset.get('source_text','').splitlines();p=programs.get(path)
        file={'path':path,'source_hash':asset['source_hash'],'kind':analysis.get('classifications',{}).get(path,{}).get('kind',asset['kind']),
              'physical_lines':len(lines),'in_process_scope':asset.get('selected',True),'scope_reason':asset.get('scope_reason'),'item_count':0}
        files.append(file)
        if not file['in_process_scope']:continue
        coverage={r['line']:r for r in (p or {}).get('coverage',[])}
        modeled={n:r for r in (p or {}).get('rules',[])+ (p or {}).get('omitted_rules',[]) for n in range(r['source_start'],r['source_end']+1)}
        native=screen_units.get(path,{})
        require(not set(modeled).intersection(native),'Screen action overlaps independently parsed rule logic')
        n=1
        while n<=len(lines):
            rule=modeled.get(n);screen=native.get(n);start=n
            if rule:
                end=rule['source_end'];kind='rule';description=rule['plain'];rid=rule['id']
            elif screen:
                end=screen['end_line'];kind=screen['kind'];description=screen['description'];rid=None
            else:
                rid=None;kind=coverage.get(n,{}).get('disposition','platform_behavior')
                if not lines[n-1].strip():kind='blank'
                end=n
                # Group only contiguous lines of the same source-accounting kind.
                while end<len(lines) and end+1 not in modeled and end+1 not in native and coverage.get(end+1,{}).get('disposition','platform_behavior')==kind:end+=1
                description={'structure':'Source declarations and structural headers','paragraph':'COBOL paragraph identity',
                    'comment':'Source comments','blank':'Blank source lines','data_layout':'Record layout and value constraints',
                    'copybook':'COPY dependency and shared record layout','terminal':'Program return behavior',
                    'unsupported':'Mainframe behavior requiring a verified semantic adapter','platform_behavior':'Mainframe file or platform behavior requiring evidence'}.get(kind,'Unclassified source behavior')
            identity='REQ_'+sha(encode([path,asset['source_hash'],start,end,rid,kind]))[:24]
            replacement=screen['replacement'] if screen else {'rule':'Python decision and assignment statements; preserve ordered effects, outcomes and record validation.',
                'data_layout':'Explicit Python record validation and field constraints; native encoding/numeric layouts still need verified adapters.',
                'copybook':'Reuse the resolved field layout in Python validation; preserve COPY/version evidence.',
                'terminal':'Return the target record, trace and return code through run_program; native process/session exit semantics are separate.',
                'structure':'No standalone executable replacement for declarations already represented by the parsed module/layout.',
                'paragraph':'No standalone executable replacement for an unused label in the supported flat profile; PERFORM/GO TO require adapters.',
                'comment':'No executable replacement is needed for source comments; preserve them as evidence.',
                'blank':'No executable replacement is needed for blank lines; preserve line accounting.'}.get(kind,'No verified replacement is established. Inspect the frozen mainframe catalog and dependencies; implement and test the specific Python/SQLite adapter before crediting conversion.')
            item={'id':identity,'kind':kind,'rule_id':rid,'program':screen.get('program') if screen else (p or {}).get('name'),'source_path':path,
                'source_hash':asset['source_hash'],'start_line':start,'end_line':end,'description':description,'replacement':replacement,
                'not_required':kind in ('blank','comment','structure','paragraph'),
                'source_excerpt':'\n'.join(lines[start-1:min(end,start+19)])[:4000],'excerpt_complete':end-start<20 and len('\n'.join(lines[start-1:end]))<=4000}
            if screen_contract:
                if screen:
                    related=[screen['mapset']+'/'+screen['map']] if screen.get('mapset') and screen.get('map') else screens_by_mapset.get(screen.get('mapset'),[])
                else:
                    names=[item['program']] if item['program'] else source_owners.get(path,[])
                    related=[key for name in names for key in screens_by_program.get(name,[])]
                item['screens']=sorted(set(related));item['screen']=item['screens'][0] if len(item['screens'])==1 else None
                item['programs']=[item['program']] if item['program'] else sorted(set(source_owners.get(path,set()))|{name for key in item['screens'] for name in screen_owners.get(key,[])})
                if screen:
                    item.update({key:screen.get(key) for key in ('mapset','map','field','operation','component','required','support','diagnostics')})
                    item['not_required']=not screen['required'] and screen['kind']=='screen_field' and screen['support']=='layout_supported'
            items.append(item)
            file['item_count']+=1;n=end+1
    contract={'source_snapshot':analysis.get('source_snapshot'),'items':[{k:v for k,v in r.items() if k not in ('source_excerpt','excerpt_complete')} for r in items], 'files':files}
    result={'schema_version':1,'hash':sha(encode(contract)),**contract,'items':items}
    if screen_contract:result['cics_contract_version']=1
    return result


def validate_selection(selection,model):
    keys={'schema_version','process_id','source_snapshot','catalog_hash','revision','excluded_ids','saved_at','saved_by'}
    require(isinstance(selection,dict) and set(selection)==keys and type(selection['schema_version']) is int and selection['schema_version']==1,'Invalid requirements selection')
    require(selection['source_snapshot']==model['source_snapshot'] and selection['catalog_hash']==model['hash'], 'Requirements no longer match the source analysis; review and save the current breakdown')
    require(type(selection['revision']) is int and selection['revision']>0,'Invalid requirements revision')
    identity(selection['process_id'])
    require(isinstance(selection['saved_at'],str),'Invalid requirements timestamp')
    try:stamp=datetime.fromisoformat(selection['saved_at'])
    except ValueError as exc:raise ValidationError('Invalid requirements timestamp') from exc
    require(stamp.tzinfo is not None,'Requirements timestamp must include a timezone')
    ids=selection['excluded_ids'];known={r['id'] for r in model['items']}
    require(isinstance(ids,list) and all(isinstance(r,str) for r in ids) and len(ids)==len(set(ids)) and set(ids)<=known,'Requirements contain duplicate or unknown selections')
    require(isinstance(selection['saved_by'],str) and 0<len(selection['saved_by'].strip())<=160,'Requirements attribution is required')
    return selection


def render_markdown(selection,model):
    validate_selection(selection,model);excluded=set(selection['excluded_ids'])
    def cell(value):return html.escape(str(value or ''),quote=False).replace('|','&#124;').replace('\n',' ')
    screen_contract=model.get('cics_contract_version')==1
    rows=['# Conversion requirements','', 'This is the saved operator scope. Yes requests conversion; it is not SME approval or verification evidence.',
          'No items retain the reason: '+NO_REASON,'', '## Machine-readable conversion input','',
          '```json',encode(selection).decode(),'```','', '## Source breakdown and choices','',
          '| Requirement | Convert | Source evidence | Description | Replacement / omission commentary |', '|---|---|---|---|---|']
    if screen_contract:rows[-2:]=['| Requirement | Convert | Program / screen / component | Source evidence | Description | Replacement / omission commentary |','|---|---|---|---|---|---|']
    for r in model['items']:
        chosen=r['id'] not in excluded
        values=[r['id'],'Yes' if chosen else 'No',r['source_path']+':'+str(r['start_line'])+'–'+str(r['end_line'])+' SHA256 '+r['source_hash'],r['description'],r['replacement'] if chosen else NO_REASON]
        if screen_contract:values.insert(2,'; '.join(r.get('programs',[])+r.get('screens',[])+[r.get('component') or r['kind']]))
        rows.append('| '+' | '.join(cell(x) for x in values)+' |')
    rows+=['','## Retained files','']
    for file in model['files']:rows.append('- '+cell(file['path'])+' — '+str(file['physical_lines'])+' lines; '+('in process scope' if file['in_process_scope'] else 'outside the discovered process: '+str(file['scope_reason'])))
    return '\n'.join(rows)+'\n'


def parse_markdown(raw,model):
    require(isinstance(raw,bytes) and len(raw)<=32*1024*1024,'Requirements Markdown exceeds 32 MiB')
    try:value=raw.decode('utf-8')
    except UnicodeDecodeError as exc:raise ValidationError('Requirements Markdown must be UTF-8') from exc
    chunks=value.split('```json\n',1)
    require(len(chunks)==2 and '\n```' in chunks[1],'Requirements Markdown machine-readable selection is missing')
    selection=decode(chunks[1].split('\n```',1)[0].encode(),32*1024*1024)
    require(raw==render_markdown(selection,model).encode(),'Requirements Markdown differs from its canonical selections; save changes through the UI')
    return selection


def project(analysis,selection,jobs=()):
    """Pure replay of saved choices; native semantics never disappear as support."""
    model=catalog(analysis);validate_selection(selection,model);out=deepcopy(analysis)
    excluded={r['id']:r for r in model['items'] if r['id'] in selection['excluded_ids']}
    omitted_rules={r['rule_id'] for r in excluded.values() if r['kind']=='rule'}
    omitted_lines={path:{n for r in excluded.values() if r['source_path']==path for n in range(r['start_line'],r['end_line']+1)} for path in {r['source_path'] for r in excluded.values()}}
    out['requirements']={'selection':selection,'excluded_units':list(excluded.values()),'catalog_hash':model['hash']}
    def cosmetic(unit):
        return type(analysis.get('cics_contract_version')) is int and analysis.get('cics_contract_version')==1 and unit['kind']=='screen_field' and unit.get('required') is False and unit.get('support')=='layout_supported'
    for name,p in out['programs'].items():
        p['omitted_rules']=[r for r in p['rules'] if r['id'] in omitted_rules]
        p['rules']=[r for r in p['rules'] if r['id'] not in omitted_rules]
        p['requirements_hash']=sha(encode(selection))
        p['semantic_hash']=sha(encode({'source_semantics':p['semantic_hash'],'requirements':p['requirements_hash']}))
        p['coverage']=[{**r,'requirements_excluded':r['line'] in omitted_lines.get(p['path'],set())} for r in p['coverage']]
        # An excluded predecessor may initialize a field used by retained logic.
        # Keep this as a dependency obligation, not a silent semantic change.
        original=analysis['programs'][name]['rules'];written=set()
        def reads(node):
            if not isinstance(node,dict):return set()
            return {node['field']} if 'field' in node else reads(node.get('left'))|reads(node.get('right'))
        for rule in original:
            if rule['id'] in omitted_rules:written.update(e['field'] for e in rule['then']+rule['else'])
            elif written & reads(rule['predicate']):
                gap={'kind':'requirements_dependency','program':name,'path':p['path'],'lines':list(range(rule['source_start'],rule['source_end']+1)),
                     'message':'Selected Yes rule '+rule['id']+' reads fields written by a selected No predecessor: '+', '.join(sorted(written & reads(rule['predicate'])))+'. A verified redesign or revised requirements is needed.'}
                p['blockers'].append(gap);out['blockers'].append(gap)
        for unit in excluded.values():
            if unit['source_path']==p['path'] and unit['kind'] not in ('rule','blank','comment','structure','paragraph') and not cosmetic(unit):
                gap={'kind':'requirements_dependency','program':name,'path':p['path'],'lines':list(range(unit['start_line'],unit['end_line']+1)),
                     'message':NO_REASON+' Required layout/return/platform behavior was excluded; retained program semantics need a verified redesign before target generation.'}
                p['blockers'].append(gap);out['blockers'].append(gap)
    upstream=set()
    for job in jobs:
        for step in job['steps']:
            p=out['programs'].get(step['program'].upper())
            if p is None:continue  # Existing missing/dynamic-source gates remain.
            for rule in p['rules']:
                dependencies=upstream & reads(rule['predicate'])
                if dependencies:
                    gap={'kind':'requirements_dependency','program':p['name'],'path':p['path'],
                        'lines':list(range(rule['source_start'],rule['source_end']+1)),
                        'message':'Selected Yes rule '+rule['id']+' in '+job['name']+'/'+step['name']+' reads fields written by a selected No upstream job step: '+', '.join(sorted(dependencies))+'. A verified redesign or revised requirements is needed.'}
                    p['blockers'].append(gap);out['blockers'].append(gap)
            # Conservatively preserve possible effects across conditional steps,
            # repeated program invocations and jobs sharing the target record.
            upstream.update(e['field'] for r in p['omitted_rules'] for e in r['then']+r['else'])
    for unit in excluded.values():
        if unit['program'] is not None or unit['kind'] in ('blank','comment') or cosmetic(unit):continue
        dependents=[p for p in out['programs'].values() if unit['source_path'] in {d.get('path') for d in p.get('dependencies',[])} or any(f.get('source_ref','').rsplit(':',1)[0]==unit['source_path'] for f in p.get('fields',{}).values()) or p['name'] in unit.get('programs',[])]
        gap={'kind':'requirements_dependency','path':unit['source_path'],'lines':list(range(unit['start_line'],unit['end_line']+1)),
             'message':NO_REASON+' This source file participates in the selected process; its consumers need a verified redesign before execution.'}
        out['blockers'].append(gap)
        for p in dependents:p['blockers'].append({**gap,'program':p['name']})
    out['rules']=[r for p in out['programs'].values() for r in p['rules']]
    out['source_accounting']={p['name']:p['coverage'] for p in out['programs'].values()}
    return out


def verify_snapshot(doc,root,model=None):
    from .layout import output_path
    selection=doc.get('requirements')
    if not selection:return None
    relative=doc.get('requirements_artifact','')
    require(isinstance(relative,str) and re.fullmatch(r'analysis/requirements/[a-f0-9]{64}\.md',relative),'Requirements snapshot path is invalid')
    require(selection.get('process_id')==doc['id'],'Requirements belong to another process')
    raw=output_path(root,doc['id'],relative).read_bytes()
    require(sha(raw)==relative.rsplit('/',1)[1][:-3] and sha(raw)==doc.get('artifact_hashes',{}).get(relative),'Saved requirements evidence changed')
    if model is not None:require(parse_markdown(raw,model)==selection,'Markdown requirements differ from recorded selections')
    else:
        chunks=raw.decode('utf-8').split('```json\n',1)
        require(len(chunks)==2 and decode(chunks[1].split('\n```',1)[0].encode(),32*1024*1024)==selection,'Requirements selection differs from its saved Markdown input')
    # The immutable version is authoritative; the editable UI copy is a convenience
    # projection and never substitutes a changed input behind an issued packet.
    return selection


def comparison(doc,coverage):
    """Every selected source unit, including non-runtime and omitted behavior."""
    analysis=doc.get('analysis') or {};model=catalog(analysis);rows={}
    for row in coverage['rows']:rows.setdefault(row['source_path'],{})[row['source_line']]=row
    excluded=set((doc.get('requirements') or {}).get('excluded_ids',[]));result=[]
    for unit in model['items']:
        source=[rows.get(unit['source_path'],{}).get(n) for n in range(unit['start_line'],unit['end_line']+1)]
        source=[r for r in source if r];no=unit['id'] in excluded
        intact=len(source)==unit['end_line']-unit['start_line']+1 and not coverage['summary']['integrity_errors']
        status='excluded_by_requirements' if no else 'no_runtime_replacement_required' if intact and all(r['disposition']=='non_executable' for r in source) else 'converted_verified' if intact and all(r['disposition'] in ('mapped_verified','platform_replaced_verified') for r in source) else 'unverified'
        targets=[];evidence=[];tests=set();reasons=[];replacements=[]
        for row in source:
            for value,destination in [(v,targets) for v in row['target_mappings']]+[(v,evidence) for v in row['evidence']]:
                if value not in destination:destination.append(value)
            tests.update(row['tests'])
            if row['reason'] not in reasons:reasons.append(row['reason'])
            if row.get('replacement') and row['replacement'] not in replacements:replacements.append(row['replacement'])
        result.append({**unit,'selected':not no,'status':status,'commentary':NO_REASON if no else ' '.join(reasons),
            'replacement_status':'omitted' if no else 'evidenced' if status in ('converted_verified','no_runtime_replacement_required') else 'candidate_only',
            'replacement':NO_REASON if no else ' '.join(replacements) or unit['replacement'],
            'targets':targets,'evidence':evidence,'tests':sorted(tests)})
    return {'markdown':doc.get('requirements_artifact'),'revision':(doc.get('requirements') or {}).get('revision'),
        'items':result,'files':model['files'],'counts':{status:sum(r['status']==status for r in result) for status in ('converted_verified','no_runtime_replacement_required','unverified','excluded_by_requirements')},
        'basis':'All original exported files and source spans are retained. Selected No is an explicit omission, not conversion success. Replacement guidance is a candidate until replayed evidence verifies it. Tests and adversarial mutations are source-derived, not observed mainframe parity.'}
