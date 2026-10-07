"""One editable, plain-language SME packet with immutable question identities."""
from .domain import path_is_link
from io import BytesIO
from pathlib import Path
import html
import json
import re
import tempfile
import shutil
from .domain import require, sha, encode, decode, checked_zip, write_new, ValidationError, MAX_UPLOAD

GLOBAL_QUESTIONS = [
 ('G_SCOPE','Does the listed program/job/step inventory cover this process?'),
 ('G_LAYOUT','Are the listed field names, lengths, numeric limits and record groups correct?'),
 ('G_ORDER','Are the listed job/step sequence, conditions, and input/output links correct?'),
 ('G_MATCH','Are the listed matching relationships and intentional missing-match cases interpreted correctly?'),
 ('G_TARGET','Is Python with SQLite/JSON files acceptable for this non-production POC?')]

CHECKLIST_HEADER = ['Item ID','What we understood','Source evidence','Category','Answer','If No, what should it be?','Reviewer']
CONTEXT_CHUNK_SIZE = 16000
CHECKLIST_TEXT_LIMIT = 4000
SME_ITEM_LIMIT = 2000
TECHNICAL_GAP_KINDS = frozenset(('unsupported_source','unsupported_jcl','unsupported_utility','source_classification'))
PROGRAM_LIST_TEXT_LIMIT = 240

# Review wording, not semantic support claims. These categories are deliberately
# conservative; unknown or compound obligations are never guessed from messages.
CONSTRUCT_ASSUMPTIONS = {
    'iteration': 'Confirm loop bounds, termination, ordering and repeated effects.',
    'embedded_sql': 'Confirm SQL inputs, results, NULL handling, errors and transaction boundaries.',
    'cics': 'Confirm transaction, screen, state, resource and error behavior.',
    'file_io': 'Confirm record layouts, access order, keys, EOF, missing records and I/O errors.',
    'arithmetic': 'Confirm precision, rounding, overflow and arithmetic error behavior.',
    'string_handling': 'Confirm string boundaries, delimiters, padding and overflow behavior.',
    'control_flow': 'Confirm branches, transfers of control, scope and termination.',
    'data_layout': 'Confirm storage, record groups, occurrences, redefinitions and condition names.',
    'numeric_representation': 'Confirm signs, decimals, binary/packed representation and encoding.',
    'initialization': 'Confirm initial values, storage lifetime and reset behavior.',
    'procedure_call': 'Confirm called program bindings, parameters, state and return behavior.',
    'copy_dependency': 'Confirm the exact COPY member, replacements and included declarations or logic.',
    'terminal_io': 'Confirm displayed or accepted values, devices and error behavior.',
    'jcl_io': 'Confirm DD bindings, allocation, disposition, records and dataset lifecycle.',
    'jcl_control': 'Confirm step order, conditions, symbols, procedure expansion and restart behavior.',
    'utility': 'Confirm the invoked utility, control cards, inputs, outputs and return codes.',
    'source_classification': 'Confirm the authoritative source type and resolve classification conflicts.',
    'unlocated_source': 'Provide the missing source or exact source binding before interpreting behavior.',
    'unknown': 'Identify the source construct and required behavior from the complete referenced evidence.',
    'mixed': 'Review every construct in this compound obligation and its interactions.',
}


def _construct_families(source):
    """Collect source constructs without losing later verbs on the same line."""
    from .source import normalized_lines
    kind, line = normalized_lines(source)[0] if source else ('blank', '')
    if kind != 'code':
        return {'unknown'}
    line = re.sub(r'"(?:[^"\n]|"")*"|\'(?:[^\'\n]|\'\')*\'', ' ', line).upper().strip()
    if line.startswith('//*'):
        return {'unknown'}
    if re.match(r'//\S*\s+DD(?![A-Z0-9-])', line):
        return {'jcl_io'}
    if re.match(r'//\S*\s+(?:JOB|EXEC|PROC|PEND|INCLUDE|SET|IF|ELSE|ENDIF)(?![A-Z0-9-])', line):
        return {'jcl_control'}
    # Treat SQL/CICS bodies as their own language, so SQL CALL or CICS READ
    # does not manufacture an additional COBOL verb. Scan after END-EXEC too.
    families = set()
    exec_pattern = r'(?<![A-Z0-9-])EXEC\s+(SQL|CICS)(?![A-Z0-9-])'
    while match := re.search(exec_pattern, line):
        families.add('embedded_sql' if match[1] == 'SQL' else 'cics')
        end = re.search(r'(?<![A-Z0-9-])END-EXEC(?![A-Z0-9-])', line[match.end():])
        stop = match.end()+end.end() if end else len(line)
        line = line[:match.start()]+' '*(stop-match.start())+line[stop:]
    line = re.sub(r'^[\s.]+', '', line).strip()
    if not line:
        return families or {'unknown'}
    patterns = (
        ('iteration', r'(?:PERFORM|END-PERFORM|SEARCH|END-SEARCH)(?![A-Z0-9-])'),
        ('file_io', r'(?:OPEN|CLOSE|READ|WRITE|REWRITE|DELETE|START|SORT|MERGE|RELEASE|RETURN)(?![A-Z0-9-])'),
        ('arithmetic', r'(?:ADD|SUBTRACT|MULTIPLY|DIVIDE|COMPUTE)(?![A-Z0-9-])'),
        ('string_handling', r'(?:STRING|UNSTRING|INSPECT)(?![A-Z0-9-])'),
        ('control_flow', r'(?:IF|ELSE|END-IF|EVALUATE|WHEN|END-EVALUATE|GO\s+TO|ALTER|EXIT|GOBACK|STOP\s+RUN)(?![A-Z0-9-])'),
        ('initialization', r'INITIALIZE(?![A-Z0-9-])'),
        ('procedure_call', r'(?:CALL|CANCEL)(?![A-Z0-9-])'),
        ('copy_dependency', r'COPY(?![A-Z0-9-])'),
        ('terminal_io', r'(?:DISPLAY|ACCEPT)(?![A-Z0-9-])'),
    )
    if re.match(r'\d{1,2}\s+[A-Z][A-Z0-9-]*\b', line):
        if re.search(r'\b(?:COMP(?:-[1-5])?|COMPUTATIONAL(?:-[1-5])?|BINARY|PACKED-DECIMAL|SIGN)\b|\bPIC(?:TURE)?\s+[SX9()0-9]*[SV]', line):
            return families | {'numeric_representation'}
        return families | {'data_layout'}
    if not any(re.match(pattern, line) for _, pattern in patterns):
        families.add('unknown')
    for family, pattern in patterns:
        if re.search(r'(?<![A-Z0-9-])'+pattern, line):
            families.add(family)
    return families


def _classify_construct(source):
    """Return the sole family, or explicitly mark a compound/unknown line."""
    families = _construct_families(source)
    if 'unknown' in families:
        return 'unknown'
    return next(iter(families)) if len(families) == 1 else 'mixed'


def _program_list(programs):
    shown = []
    for program in programs:
        if len(', '.join(shown + [program])) > PROGRAM_LIST_TEXT_LIMIT:
            break
        shown.append(program)
    result = ', '.join(shown) or 'See Context'
    if len(shown) < len(programs):
        result += f' (+{len(programs)-len(shown)} more; {len(programs)} programs total)'
    return result



def _celltext(text):
    return "'"+text if text.lstrip().startswith(('=','+','-','@')) else text


def _validate_cell_capacity(text, label):
    require(not isinstance(text,str) or len(text.encode('utf-16-le'))//2<=32767,
            label+' exceeds Excel cell capacity; shorten the identifier/metadata before issuing the review')


def _display_text(item, field):
    return item.get('display_'+field,item[field])


def _metadata_rows(packet):
    return [['Process ID',packet['process_id']],['Packet hash',packet['packet_hash']],
            ['Source snapshot',packet['source_snapshot']],
            ['Evidence class','SOURCE_DERIVED_EXPECTED; no mainframe execution']]


def _context_rows(packet):
    context = packet['context']
    return [['Process information']] + [[context[i:i+CONTEXT_CHUNK_SIZE]]
                                         for i in range(0,len(context),CONTEXT_CHUNK_SIZE)]


def _number_spans(numbers):
    """Lossless inclusive spans for source lines and zero-based blocker indices."""
    spans=[]
    for number in sorted(set(numbers)):
        if spans and number==spans[-1][1]+1:spans[-1][1]=number
        else:spans.append([number,number])
    return spans


def _analysis_reference(analysis):
    return {
        'path':'analysis/source-analysis.json','sha256':sha(encode(analysis)),
        'source_snapshot':analysis['source_snapshot'],
        'evidence_basis':analysis.get('evidence_basis','SOURCE_DERIVED_EXPECTED'),
        'raw_blocker_count':len(analysis['blockers']),'blockers_json_pointer':'/blockers',
        'blocker_index_base':0,'source_line_index_base':1,
        'files':{asset['path']:{'source_sha256':asset['source_hash'],
                               'physical_lines':asset.get('loc',{}).get('physical')}
                 for asset in analysis.get('assets',[])},
        'programs':{name:{'path':program['path'],'source_sha256':program['source_hash'],
                          'coverage_json_pointer':'/programs/'+name+'/coverage',
                          'coverage_sha256':sha(encode(program.get('coverage',[]))),
                          'coverage_line_count':len(program.get('coverage',[]))}
                    for name,program in analysis['programs'].items()},
    }


def _compact_technical_gaps(analysis, context_data):
    # The coordinator freezes and registers this complete artifact before issuing
    # the packet. Referencing its canonical hash avoids duplicating millions of
    # source/coverage rows into Excel while retaining every original blocker.
    context_data['source_analysis']=_analysis_reference(analysis)
    program_by_path={program['path']:name for name,program in analysis['programs'].items()}
    groups={};items=[]
    for index,blocker in enumerate(analysis['blockers']):
        if blocker['kind'] not in TECHNICAL_GAP_KINDS:
            items.append({'id':f'B_{index:03d}','question':'Is this unresolved item described correctly? If no, explain what it should do. '+blocker['message'],
                          'evidence':blocker.get('path','Source/intake evidence'),'kind':'unresolved_item'})
            continue
        path=blocker.get('path','Source/intake evidence')
        program=program_by_path.get(path) or blocker.get('program') or blocker.get('utility_id') or path
        key=(program,path,blocker['kind'])
        group=groups.setdefault(key,{'program':program,'path':path,'kind':blocker['kind'],
                                     'indices':[],'source_lines':{}})
        group['indices'].append(index)
        if blocker.get('lines'):
            group['source_lines'].setdefault(path,[]).extend(blocker['lines'])
        for reference in blocker.get('source_refs',[]):
            if isinstance(reference,dict) and isinstance(reference.get('line'),int):
                group['source_lines'].setdefault(reference.get('path',path),[]).append(reference['line'])
    context_data['technical_gaps']={}
    for key,group in sorted(groups.items()):
        item_id='TG_'+sha(encode(list(key)))[:16]
        indices=group.pop('indices');source_lines=group.pop('source_lines')
        group.update({'blocker_count':len(indices),'blocker_index_spans':_number_spans(indices),
                      'blockers_sha256':sha(encode([analysis['blockers'][i] for i in indices])),
                      'source_line_spans':{path:_number_spans(lines) for path,lines in sorted(source_lines.items())}})
        context_data['technical_gaps'][item_id]=group
        items.append({'id':item_id,
                      'question':f"Are these technical gaps for {group['program']} described correctly? "
                                 f"{group['blocker_count']} {group['kind']} blocker records need a reviewed semantic adapter. "
                                 'Confirm or correct the required source behavior. These gaps remain unsupported until the adapter is implemented and verified; Yes confirms the description only.',
                      'evidence':group['path']+'; see Context > technical_gaps > '+item_id+
                                 ' and source_analysis for exact blocker records, source spans, hashes and complete coverage.',
                      'kind':'technical_gap'})
    return items


def _blocker_lines(blocker):
    """Index valid source coordinates; the hash-bound raw record retains all data."""
    path = blocker.get('path')
    refs = {}
    if path:
        refs[path] = [line for line in blocker.get('lines', []) if type(line) is int and line > 0]
    for reference in blocker.get('source_refs', []):
        if isinstance(reference, dict):
            target = reference.get('path', path)
            line = reference.get('line')
            if target:
                refs.setdefault(target, [])
                if type(line) is int and line > 0:
                    refs[target].append(line)
    return refs


def _blocker_construct(blocker, sources):
    refs = _blocker_lines(blocker)
    if blocker['kind'] == 'missing_source' or not refs or any(path not in sources for path in refs):
        return 'unlocated_source', [], 'Source binding is missing.'
    if blocker['kind'] == 'source_classification':
        return 'source_classification', [], 'Source classification needs human resolution.'
    families = set()
    for path, lines in refs.items():
        source = sources[path]
        if not source or not lines or any(line not in source for line in lines):
            return 'unknown', [], 'Referenced source span is unavailable or not trustworthy.'
        for line in lines:
            families.update(source[line])
    if 'unknown' in families or not families:
        return 'unknown', sorted(families), 'At least one referenced line has no unambiguous construct classification.'
    if blocker['kind'] == 'unsupported_utility' and families == {'jcl_control'}:
        return 'utility', sorted(families), 'Utility finding references JCL invocation evidence.'
    if len(families) > 1:
        return 'mixed', sorted(families), 'One blocker spans multiple construct families.'
    return next(iter(families)), sorted(families), 'Classified from the referenced original source lines.'


def _compact_construct_gaps(analysis, context_data):
    """v3 only: share questions across programs, never merge away raw evidence."""
    context_data['source_analysis'] = _analysis_reference(analysis)
    program_by_path = {program['path']: name for name, program in analysis['programs'].items()}
    needed = {}
    for blocker in analysis['blockers']:
        if blocker['kind'] in TECHNICAL_GAP_KINDS | {'missing_source'}:
            for path, lines in _blocker_lines(blocker).items():
                needed.setdefault(path, set()).update(lines)
    sources = {}
    assets = {asset['path']: asset for asset in [*analysis.get('assets', []), *analysis['programs'].values()]}
    for path in needed.keys() & assets.keys():
        asset = assets[path]; text = asset.get('source_text')
        # File extensions, blocker prose and utility names are not source proof.
        trusted = (isinstance(text, str) and sha(text) == asset['source_hash']
                   and asset.get('kind') in ('cobol_program', 'copybook', 'jcl_job'))
        sources[path] = {i: _construct_families(line) for i, line in enumerate(text.splitlines(), 1)
                         if i in needed[path]} if trusted else None
    groups = {}; items = []
    for index, blocker in enumerate(analysis['blockers']):
        if blocker['kind'] not in TECHNICAL_GAP_KINDS | {'missing_source'}:
            items.append({'id': f'B_{index:03d}',
                          'question': 'Is this unresolved item described correctly? If no, explain what it should do. '+blocker['message'],
                          'evidence': blocker.get('path', 'Source/intake evidence'), 'kind': 'unresolved_item'})
            continue
        family, observed, reason = _blocker_construct(blocker, sources)
        group = groups.setdefault(family, {'family': family, 'indices': [], 'programs': set(),
                                          'source_lines': {}, 'kinds': {}, 'observed_constructs': set(),
                                          'classification_reasons': {}})
        group['indices'].append(index)
        group['observed_constructs'].update(observed)
        group['kinds'][blocker['kind']] = group['kinds'].get(blocker['kind'], 0) + 1
        group['classification_reasons'][reason] = group['classification_reasons'].get(reason, 0) + 1
        if blocker.get('program'):
            group['programs'].add(blocker['program'])
        for path, lines in _blocker_lines(blocker).items():
            group['source_lines'].setdefault(path, []).extend(lines)
            if path in program_by_path:
                group['programs'].add(program_by_path[path])
    context_data['technical_gaps'] = {}
    for family, group in sorted(groups.items()):
        item_id = 'TG_'+sha(encode(['construct', family]))[:16]
        indices = group.pop('indices'); source_lines = group.pop('source_lines')
        group['programs'] = sorted(group['programs'])
        group['observed_constructs'] = sorted(group['observed_constructs'])
        group.update({'program_count': len(group['programs']), 'paths': sorted(source_lines),
                      'blocker_count': len(indices), 'blocker_index_spans': _number_spans(indices),
                      'blockers_sha256': sha(encode([analysis['blockers'][i] for i in indices])),
                      'source_line_spans': {path: _number_spans(lines) for path, lines in sorted(source_lines.items())}})
        context_data['technical_gaps'][item_id] = group
        items.append({'id': item_id,
                      'question': f"ASSUMPTION - {family}: {CONSTRUCT_ASSUMPTIONS[family]} "
                                  f"Programs: {_program_list(group['programs'])}. "
                                  f"{group['blocker_count']} blocker records remain an unverified obligation. "
                                  'Yes confirms the description only; the behavior remains unsupported until a semantic adapter is implemented and verified.',
                      'evidence': 'See Context > technical_gaps > '+item_id+
                                  ' and source_analysis for every program, exact blocker records, source spans, hashes and complete coverage.',
                      'kind': 'technical_gap'})
    return items


def rule_classifications(process):
    """Explicit program defaults and per-rule exceptions, never inferred categories."""
    submitted=process.get('llm',{}).get('analysis',{})
    defaults=submitted.get('rule_classification_defaults',{})
    result={r['id']:defaults[name] for name,p in process['analysis']['programs'].items() if name in defaults for r in p['rules']}
    result.update(submitted.get('rule_classifications',{}))
    return result


def _group_business_items(process, items, context):
    """Group proven repeated decisions; hash input effects incrementally in source order."""
    def predicate_fields(value):
        if not isinstance(value,dict):return set()
        return ({value['field']} if 'field' in value else set()) | predicate_fields(value.get('left')) | predicate_fields(value.get('right'))
    fingerprints={}
    for name,program in process['analysis']['programs'].items():
        invocations=[(j['name'],s['program'],s.get('condition'),s.get('inputs'),s.get('outputs'))
                     for j in process['jobs'] for s in j['steps'] if s['program']==name]
        invocations += [{'transaction':t['id'],'mapset':t.get('mapset'),'map':t.get('map')} for t in process.get('transactions',[]) if t['program']==name]
        semantics=[{k:r.get(k) for k in ('predicate','then','else')} for r in program['rules']]
        base=sha(encode({'program':name,'source':program['path'],'version':program['source_hash'],
            'fields':program['fields'],'dependencies':program.get('dependencies',[]),
            'invocations':invocations,'program_semantics':semantics}))
        effects={}
        for rule,semantic in zip(program['rules'],semantics):
            inputs={field:effects.get(field,'initial') for field in sorted(predicate_fields(semantic['predicate']))}
            fingerprints[rule['id']]=sha(encode([base,inputs,semantic,rule['id'] if program.get('blockers') else None]))
            for field in {a['field'] for a in (semantic['then'] or [])+(semantic['else'] or [])}:
                effects[field]=sha(encode([effects.get(field,'initial'),semantic]))
    buckets={}
    for item in items:
        fingerprint=sha(encode([fingerprints[item['id']],item['kind'],item['question']]))
        buckets.setdefault(fingerprint,[]).append(item)
    grouped=[];context['rule_groups']={}
    for fingerprint,members in buckets.items():
        if len(members)==1:
            grouped.extend(members);continue
        ident='GROUP_'+fingerprint[:24]
        context['rule_groups'][ident]={'members':[m['id'] for m in members],'equivalence_sha256':fingerprint,
            'basis':'Same source, program semantics, preceding input effects, layouts, dependencies and invocation context'}
        grouped.append({'id':ident,'kind':members[0]['kind'],
            'question':members[0]['question']+' Applies to every listed occurrence; corrections leave the group unresolved.',
            'evidence':'; '.join(m['evidence'] for m in members)})
    return grouped


def packet_document(process):
    a=process['analysis']
    # Marker-absent historical documents must reproduce the original v1 packet
    # bytes/hash, including their original size gate. New intake opts into v3.
    packet_version=process.get('sme_packet_version',1)
    require(type(packet_version) is int and packet_version in (1,2,3,4),'Unsupported SME packet version')
    if packet_version in (2,3):
        require(len(a['rules'])<=SME_ITEM_LIMIT,
                'SME packet exceeds supported size; business rules require individual human items; narrow the process scope before issuing')
    items=[{'id':r['id'],'question':r['plain'],'evidence':'; '.join(r['source_refs']),'kind':'business_rule'} for r in a['rules']]
    context_data={'jobs':process['jobs'],'layouts':{n:p['fields'] for n,p in a['programs'].items()},'relationships':a['relationships'],'knowledge_input':process.get('knowledge_context')}
    if process.get('transactions'):context_data['transactions']=process['transactions']
    if packet_version == 4:
        categories=rule_classifications(process)
        for item in items:
            category=categories.get(item['id'],{})
            item['kind']=category.get('category','unclassified')
            item['question']='['+item['kind']+'] '+item['question']
            if category.get('reason'):item['evidence']+='; classification: '+category['reason']
        items=_group_business_items(process,items,context_data)
    items += [{'id':k,'question':q,'evidence':'See process inventory/layout/relationship context','kind':'process_assumption'} for k,q in GLOBAL_QUESTIONS]
    if process.get('knowledge_context'):items.append({'id':'G_KNOWLEDGE','question':'Is the supplied background knowledge correct and applicable to this process? If No, describe the correction.','evidence':'See knowledge_input context and its SHA256','kind':'process_assumption'})
    if process.get('mainframe_knowledge'):
        context_data['file_classifications']=a.get('classifications',{})
        context_data['utility_findings']=a.get('utility_findings',[])
        context_data['application_knowledge']={'status':'UNVERIFIED_INPUT',**process['mainframe_knowledge']['application']}
        context_data['mainframe_knowledge_snapshot']='analysis/mainframe-knowledge.json'
        context_data['mainframe_knowledge_sha256']=sha(encode(process['mainframe_knowledge']))
        checks=[
            ('G_FILE_TYPES','Are the listed file types and dependencies correct, including source, copybooks, JCL/PROCs, control cards, screens and data definitions? If No, name the missing or misclassified file.'),
            ('G_UTILITIES','Does the utility list include every standard, vendor and application utility this process calls? If No, give its name, purpose, inputs, outputs and return codes.'),
            ('G_NATIVE_DATA','Do the provided layouts fully describe record formats, encodings, keys, signs, decimal precision and matching rules? If No, describe the missing format or rule, including empty, duplicate and missing records.'),
            ('G_NATIVE_RUNTIME','Do the listed jobs fully describe runtime behavior, including control cards, DD allocation/deletion, conditional steps, restart, transactions, scheduling and external calls? If No, describe the missing behavior.'),
        ]
        items += [{'id':key,'question':question,'evidence':'See file_classifications, utility_findings, jobs and layouts in Context; recognition alone is not conversion proof.','kind':'mainframe_assumption'} for key,question in checks]
    if process.get('transactions'):
        for item in items:
            if item['id']=='G_ORDER':item['question']='Are the transaction entry programs, mapsets/maps and dependency boundaries in Context correct? Unknown bindings remain unresolved.'
            if item['id']=='G_NATIVE_RUNTIME':item['question']='Does Context describe online runtime behavior, including AID/navigation, session state, COMMAREA/channels, authorization, storage, commits/rollback, recovery and downstream calls? If No, describe missing behavior.'
        items.append({'id':'G_ONLINE_TARGET','question':'Is the stated local record-API/form candidate scope understood? Native CICS/BMS, identity and enterprise transaction behavior require independent verified replacements; approval does not clear those gaps.','evidence':'See transactions and source-specific unresolved obligations in Context','kind':'process_assumption'})
    suggestions=process.get('llm',{}).get('analysis',{})
    for n,text in enumerate(suggestions.get('questions',[])+suggestions.get('assumptions',[])):
        items.append({'id':f'LLM_{n:03d}','question':text,'evidence':'Unverified LLM suggestion; validate against source/context','kind':'provider_suggestion'})
    if packet_version in (3,4):
        items += _compact_construct_gaps(a,context_data)
    elif packet_version==2 and len(items)+len(a['blockers'])>SME_ITEM_LIMIT:
        items += _compact_technical_gaps(a,context_data)
    else:
        for i,b in enumerate(a['blockers']):items.append({'id':f'B_{i:03d}','question':'Is this unresolved item described correctly? If no, explain what it should do. '+b['message'],'evidence':b.get('path','Source/intake evidence'),'kind':'unresolved_item'})
    require(len(items)<=SME_ITEM_LIMIT,'SME packet exceeds supported size; retain a scope blocker before issuing')
    require(len({item['id'] for item in items})==len(items),'SME packet contains duplicate question identities')
    details={}
    for item in items:
        for field in ('question','evidence'):
            if len(item[field])>CHECKLIST_TEXT_LIMIT:
                details.setdefault(item['id'],{})[field]=item[field]
                item['display_'+field]=(item[field][:1500]+'\n[Read the complete '+field+' for '+item['id']+
                                       ' in Context > checklist_details before answering.]')
        for field in ('id','kind'):
            _validate_cell_capacity(item[field],'Checklist '+field)
        for field in ('question','evidence'):
            _validate_cell_capacity(_celltext(_display_text(item,field)),'Checklist '+field)
    if details:context_data['checklist_details']=details
    context=json.dumps(context_data,ensure_ascii=False,indent=2,sort_keys=True)
    doc={'version':packet_version,'process_id':process['id'],'source_snapshot':a['source_snapshot'],'items':items,'context':context}
    doc['packet_hash']=sha(encode(doc))
    for row in _metadata_rows(doc):
        for value in row:_validate_cell_capacity(value,'Review metadata')
    require(len(encode(doc))<=MAX_UPLOAD,'SME packet exceeds the supported document size; narrow the process scope before issuing')
    return doc


def export_packet(process, directory):
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill, Alignment
    from openpyxl.worksheet.datavalidation import DataValidation
    from docx import Document
    directory=Path(directory);document=packet_document(process)
    if directory.exists():
        require(all((directory/name).is_file() and not path_is_link(directory/name)
                    for name in ('packet.json','sme-checklist.xlsx','sme-checklist.docx','sme-checklist.html')),
                'Existing packet is incomplete; recover its preserved snapshot')
        existing=decode((directory/'packet.json').read_bytes())
        require(existing==document,'Existing packet differs; cannot issue a second packet')
        original=read_answers((directory/'sme-checklist.xlsx').read_bytes(),existing,'Packet export validation')
        require(all(item['answer']=='Unanswered' and not item['correction']
                    and item['reviewer']=='Packet export validation' for item in original['items'].values()),
                'Existing issued workbook contains answers; preserve the original blank packet')
        return existing
    directory.parent.mkdir(parents=True,exist_ok=True)
    # Process directories contain only registered evidence. A crash may leave a
    # draft behind, so stage on the same filesystem outside that strict layout.
    workspace=directory.parents[2] if directory.parent.parent.name=='processes' else directory.parent
    staging=workspace/'.implementation/tmp';staging.mkdir(parents=True,exist_ok=True)
    temp=Path(tempfile.mkdtemp(prefix='review-draft-',dir=staging))
    try:
        book=Workbook();sheet=book.active;sheet.title='Checklist'
        sheet.append(CHECKLIST_HEADER)
        for item in document['items']:sheet.append([item['id'],_celltext(_display_text(item,'question')),_celltext(_display_text(item,'evidence')),item['kind'],'','',''])
        for c in sheet[1]:c.font=Font(bold=True,color='FFFFFF');c.fill=PatternFill('solid',fgColor='18314F')
        for row in sheet.iter_rows(min_row=2):
            for c in row:c.alignment=Alignment(wrap_text=True,vertical='top')
        for col,width in [('A',26),('B',80),('C',42),('D',22),('E',18),('F',60),('G',24)]:sheet.column_dimensions[col].width=width
        sheet.freeze_panes='E2';sheet.auto_filter.ref=sheet.dimensions
        dv=DataValidation(type='list',formula1='"Yes,No,Not sure"');dv.errorTitle='Choose an answer';dv.error='Use Yes, No or Not sure';dv.showErrorMessage=True;sheet.add_data_validation(dv);dv.add(f'E2:E{sheet.max_row}')
        meta=book.create_sheet('Metadata')
        for row in _metadata_rows(document):meta.append(row)
        context=book.create_sheet('Context');context.column_dimensions['A'].width=120
        for row in _context_rows(document):
            context.append(row);context.cell(context.max_row,1).data_type='s';context.cell(context.max_row,1).alignment=Alignment(wrap_text=True)
        book.save(temp/'sme-checklist.xlsx');book.close()
        # Exercise the actual import contract before publication/quota issuance.
        # This catches writer truncation and archive/cell limits without SME answers.
        read_answers((temp/'sme-checklist.xlsx').read_bytes(),document,'Packet export validation')
        word=Document();word.add_heading(process['name']+' — review checklist',0)
        word.add_paragraph('Check each statement. Answer Yes, No or Not sure in the Excel file. For No, write the correction. This is the only review round for this process. Missing or uncertain answers remain unresolved. Source-derived expectations are predictions, not observed mainframe results.')
        word.add_heading('Process context',1);word.add_paragraph(document['context'])
        for item in document['items']:
            word.add_heading(item['id'],2);word.add_paragraph(item['question']);word.add_paragraph('Evidence: '+item['evidence']);word.add_paragraph('Yes / No / Not sure. If No: __________________')
        word.save(temp/'sme-checklist.docx')
        rendered='<!doctype html><meta charset="utf-8"><title>SME checklist</title><h1>'+html.escape(process['name'])+'</h1><p>Return the Excel workbook. One review round. No mainframe execution.</p><pre>'+html.escape(document['context'])+'</pre>'+''.join('<section><h2>'+html.escape(i['id'])+'</h2><p>'+html.escape(i['question'])+'</p><small>'+html.escape(i['evidence'])+'</small></section>' for i in document['items'])
        write_new(temp/'sme-checklist.html',rendered.encode());write_new(temp/'packet.json',encode(document));temp.rename(directory)
        return document
    finally:
        shutil.rmtree(temp,ignore_errors=True)


def read_answers(data, packet, reviewer):
    from openpyxl import load_workbook
    require(isinstance(reviewer,str) and 0<len(reviewer.strip())<=160,'Name the reviewer responsible for this returned file')
    require(packet.get('packet_hash')==sha(encode({k:v for k,v in packet.items() if k!='packet_hash'})),
            'Frozen packet content/hash changed')
    checked_zip(data).close()
    frozen = {'Metadata':_metadata_rows(packet),'Context':_context_rows(packet),
              'Checklist':[CHECKLIST_HEADER]+[[None]*7 for _ in packet['items']]}
    def check_dimensions(book):
        require(set(book.sheetnames)==set(frozen),'Review sheet set changed')
        for name,rows in frozen.items():
            sheet=book[name]
            require(sheet.max_row==len(rows) and sheet.max_column==len(rows[0]),
                    name+' dimensions changed')
    # Check declared dimensions as well as actual cells. A forged XML dimension must
    # neither hide extra cells from streaming reads nor add blank rows/columns.
    declared=load_workbook(BytesIO(data),read_only=True,data_only=False,keep_links=False)
    try:check_dimensions(declared)
    finally:declared.close()
    book=load_workbook(BytesIO(data),read_only=False,data_only=False,keep_links=False)
    try:
        check_dimensions(book)
        require(not any(sheet.merged_cells.ranges for sheet in book),'Merged cells are not accepted in returned review evidence')
        for name in ('Metadata','Context'):
            for cells,row in zip(book[name].iter_rows(),frozen[name]):
                require(all(c.data_type!='f' for c in cells),'Formulas are not accepted in '+name)
                require([c.value for c in cells]==row,'Frozen '+name+' changed')
        sheet=book['Checklist']
        require(all(c.data_type!='f' for c in sheet[1]) and [c.value for c in sheet[1]]==CHECKLIST_HEADER,
                'Checklist headings changed')
        expected={x['id']:x for x in packet['items']};answers={}
        for cells in sheet.iter_rows(min_row=2):
            require(all(c.data_type!='f' for c in cells),'Formulas are not accepted in returned answers')
            values=[c.value for c in cells];rid,q,ref,kind,answer,correction,actor=values
            require(rid in expected and rid not in answers,'Unknown or duplicate question ID')
            original=expected[rid]
            require(q==_celltext(_display_text(original,'question')) and ref==_celltext(_display_text(original,'evidence')) and kind==original['kind'],'Original question/evidence changed')
            require(answer is None or isinstance(answer,str),'Answer must be Yes, No, Not sure or blank')
            require(actor is None or isinstance(actor,str),'Reviewer attribution must be text')
            answer=('' if answer is None else answer).strip()
            correction=('' if correction is None else str(correction)).strip()
            actor=(reviewer if actor is None or actor=='' else actor).strip()
            require(answer in ('Yes','No','Not sure',''),'Answer must be Yes, No, Not sure or blank')
            require(len(correction)<=4000 and 0<len(actor)<=160,'Returned text exceeds supported bounds')
            answers[rid]={'answer':answer or 'Unanswered','correction':correction,'reviewer':actor,'question':original['question'],'kind':kind}
        require(set(answers)==set(expected),'Missing checklist items')
        if packet.get('version') == 4:
            groups=json.loads(packet['context']).get('rule_groups',{})
            for group_id,group in groups.items():
                answer=answers[group_id]
                for member in group['members']:
                    require(member not in answers,'Duplicate grouped rule identity')
                    answers[member]={**answer,'group_id':group_id}
        return {'packet_hash':packet['packet_hash'],'source_snapshot':packet['source_snapshot'],'reviewer':reviewer.strip(),'items':answers,'return_hash':sha(data)}
    finally:book.close()
