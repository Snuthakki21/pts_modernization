"""Source-order analysis for a deliberately bounded COBOL/JCL/BMS POC subset.

Supported executable COBOL: flat IF/ELSE with typed comparisons joined by
AND/OR, literal MOVE, CONTINUE and terminal GOBACK/STOP RUN. Every other
executable construct is an explicit blocker. No inference from target code.
"""
import re
from .domain import sha, require, ValidationError, encode

NAME = r'[A-Z][A-Z0-9-]*'
TOKEN = re.compile(r'"(?:[^"]|"")*"|\'(?:[^\']|\'\')*\'|>=|<=|<>|=|>|<|-?\d+|[A-Z][A-Z0-9-]*', re.I)


def literal(token):
    if re.fullmatch(r'"(?:[^"\n]|"")*"|\'(?:[^\'\n]|\'\')*\'', token): return token[1:-1].replace(token[0]*2, token[0])
    if re.fullmatch(r'-?[0-9]+', token):
        require(len(token)<=128, 'Numeric literal exceeds supported parsing bound')
        return int(token)
    if token.upper() in ('SPACE','SPACES'): return ' '
    if token.upper() in ('ZERO','ZEROS','ZEROES'): return 0
    raise ValidationError('Only explicit numeric/string literal values are supported')


def condition(text, fields):
    stripped = text.strip().rstrip('.')
    tokens = TOKEN.findall(stripped)
    require(len(tokens)<=767, 'Condition exceeds supported comparison bound')
    require(''.join(tokens).replace(' ', '').upper() == re.sub(r'\s+', '', stripped).upper(), 'Unsupported condition syntax')
    pos = 0
    def operand():
        nonlocal pos
        require(pos < len(tokens), 'Missing condition operand')
        token = tokens[pos];pos += 1
        if token.upper() in fields: return {'field':token.upper()}
        return literal(token)
    def comparison():
        nonlocal pos
        left=operand()
        require(pos < len(tokens) and tokens[pos] in ('=','<>','>','<','>=','<='), 'Unsupported comparison')
        op=tokens[pos];pos+=1;right=operand()
        if not isinstance(left,dict) and not isinstance(right,dict):
            require(type(left) is type(right), 'Condition operand types differ')
            if isinstance(left,str):
                require(op in ('=','<>'), 'String ordering needs the verified source collation')
                width=max(len(left),len(right));left=left.ljust(width);right=right.ljust(width)
        if isinstance(left,dict) and isinstance(right,dict):
            a,b=fields[left['field']],fields[right['field']]
            require(a['type']==b['type'] and (a['type']!='string' or a['width']==b['width']), 'Differing operand layouts need an exact comparison adapter')
            require(a['type']!='string' or op in ('=','<>'),'String ordering needs the verified source collation')
        for operand_value,other,other_side in [(left,right,'right'),(right,left,'left')]:
            if isinstance(operand_value,dict) and not isinstance(other,dict):
                spec=fields[operand_value['field']]
                require(type(other) is (int if spec['type']=='integer' else str),'Condition operand types differ')
                if spec['type']=='string':
                    require(op in ('=','<>'),'String ordering needs the verified source collation')
                    require(len(other)<=spec['width'],'Over-width literal comparison needs an adapter')
                    if other_side=='right':right=other.ljust(spec['width'])
                    else:left=other.ljust(spec['width'])
        return {'op':op,'left':left,'right':right}
    def conjunction():
        nonlocal pos
        result=comparison()
        while pos<len(tokens) and tokens[pos].upper()=='AND':
            pos+=1;result={'op':'AND','left':result,'right':comparison()}
        return result
    result=conjunction()
    while pos<len(tokens) and tokens[pos].upper()=='OR':
        pos+=1;result={'op':'OR','left':result,'right':conjunction()}
    require(pos==len(tokens), 'Unsupported condition suffix')
    return result


def assignments(lines, fields):
    effects=[]
    for line in lines:
        line=line.strip().rstrip('.')
        if not line or line.upper()=='CONTINUE':continue
        m=re.fullmatch(r'MOVE\s+(.+?)\s+TO\s+('+NAME+r')',line,re.I)
        require(m is not None, f'Unsupported effect: {line[:80]}')
        name=m.group(2).upper();require(name in fields,'Unknown MOVE destination')
        value=literal(m.group(1).strip())
        spec=fields[name]
        require(type(value) is (int if spec['type']=='integer' else str), 'MOVE literal and field type differ')
        require(spec['type']!='integer' or 0<=value<=spec['max'], 'Numeric MOVE outside PICTURE range')
        require(spec['type']!='string' or len(value)<=spec['width'], 'String MOVE exceeds PICTURE width')
        effects.append({'field':name,'value':value.ljust(spec['width']) if spec['type']=='string' else value})
    return effects


def without_comment(line):
    # COBOL inline comment markers have no effect within quoted literals.
    quote=None;i=0
    while i<len(line):
        c=line[i]
        if quote:
            if c==quote:
                if i+1<len(line) and line[i+1]==quote:i+=2;continue
                quote=None
        elif c in ('"', "'"):quote=c
        elif line[i:i+2]=='*>':return line[:i]
        i+=1
    return line


def normalized_lines(text):
    result=[]
    for raw in text.splitlines():
        line=raw
        # Blank indentation is not evidence of fixed format. Never silently discard nonblank content.
        if len(line)>6 and re.fullmatch('[ 0-9]{6}',line[:6]) and (line[:6].isdigit() or line[6] in '*/-') and line[6] in ' */-':
            if line[6] in '*/': result.append(('comment',''));continue
            if line[6]=='-':result.append(('unsupported',line));continue
            if line[72:].strip():result.append(('unsupported',line));continue
            line=line[7:72]
        if line.lstrip().startswith('*>'):result.append(('comment',''));continue
        line=without_comment(line).strip()
        result.append(('blank' if not line else 'code',line))
    return result


def sql_table_references(text):
    """Conservative unquoted SQL reference candidates, never live catalog facts.

    Literals, delimited identifiers and both comment forms are masked before
    matching. Delimited identifiers and dynamic SQL need the database adapter;
    extracting apparent SQL inside a string would manufacture table evidence.
    """
    masked=[];i=0;quote=None;comment_depth=0;line_comment=False
    while i<len(text):
        char=text[i];pair=text[i:i+2]
        if line_comment:
            masked.append('\n' if char=='\n' else ' ')
            if char=='\n':line_comment=False
            i+=1;continue
        if comment_depth:
            if pair=='/*':comment_depth+=1;masked.extend('  ');i+=2;continue
            if pair=='*/':comment_depth-=1;masked.extend('  ');i+=2;continue
            masked.append('\n' if char=='\n' else ' ');i+=1;continue
        if quote:
            masked.append('\n' if char=='\n' else ' ')
            if char==quote:
                if i+1<len(text) and text[i+1]==quote:masked.append(' ');i+=2;continue
                quote=None
            i+=1;continue
        if pair=='--':line_comment=True;masked.extend('  ');i+=2;continue
        if pair=='/*':comment_depth=1;masked.extend('  ');i+=2;continue
        # Keep a non-identifier barrier where a quoted token began. Pure spaces
        # could otherwise turn FROM "T" JOIN REAL into a false FROM JOIN match.
        if char in ('\'', '"'):quote=char;masked.append('?');i+=1;continue
        masked.append(char);i+=1
    candidates=re.findall(r'\b(?:FROM|JOIN|INTO|UPDATE|CREATE\s+TABLE)\s+([A-Z][A-Z0-9_@$#]*(?:\.[A-Z][A-Z0-9_@$#]*)*)(?![A-Z0-9_@$#.])',''.join(masked),re.I)
    # These names introduce expressions or data-change table references, rather
    # than naming an actual table. This is deliberately not a SQL parser.
    expression_words={'FINAL','OLD','NEW','TABLE','SELECT','VALUES','UNNEST','XMLTABLE','LATERAL','SET','JOIN','WHERE','ON','GROUP','ORDER'}
    return sorted({name.upper() for name in candidates if name.upper() not in expression_words})


def analyze_program(path, text, files, classifications=None):
    source_hash=sha(text)
    originals=text.splitlines();lines=normalized_lines(text)
    program_matches=[re.fullmatch(r'PROGRAM-ID\.\s*('+NAME+r')\.', line,re.I) for kind,line in lines if kind=='code']
    program_matches=[m for m in program_matches if m]
    program_match=program_matches[0] if program_matches else None
    name=program_match.group(1).upper() if program_match else path.rsplit('/',1)[-1].split('.')[0].upper()
    p={'name':name,'path':path,'source_hash':source_hash,'id':sha('program:'+name+':'+source_hash),'kind':'cobol_program','fields':{},'rules':[], 'copybooks':[], 'dependencies':[], 'blockers':[], 'coverage':[], 'source_text':text, 'relationships':[]}
    for i,(kind,line) in enumerate(lines,1):p['coverage'].append({'line':i,'disposition':kind if kind in ('blank','comment') else 'unaccounted','source':line,'original':originals[i-1]})
    procedure=False
    proc=[]
    group=None;groups=set();division_order=[];section=None;sections=set()
    def block(msg, indices):
        p['blockers'].append({'kind':'unsupported_source','message':msg,'path':path,'lines':indices})
        for n in indices:p['coverage'][n-1]['disposition']='unsupported'
    def field_line(line, origin):
        nonlocal group
        gm=re.fullmatch(r'01\s+('+NAME+r')\.',line,re.I)
        if gm:
            group=gm.group(1).upper()
            require(group!='FILLER', 'Unnamed FILLER groups need a layout adapter')
            require(group not in groups and group not in p['fields'],'Duplicate record group names need qualification support');groups.add(group);return True
        fm=re.fullmatch(r'(?:05|77)\s+('+NAME+r')\s+PIC(?:TURE)?\s+(X|9)(?:\((\d+)\))?(?:\s+VALUE\s+(.+?))?\.',line,re.I)
        if not fm:return False
        require(not re.match(r'77\s',line), 'Standalone level-77 linkage items need an explicit USING/layout adapter')
        require(group is not None, 'Level-05 field requires a preceding level-01 record group')
        key,typ,width,value=fm.groups();key=key.upper();typ=typ.upper()
        require(key!='FILLER', 'Unnamed FILLER fields need a layout adapter')
        require(len(width or '1')<=32, 'PICTURE width token exceeds supported parsing bound')
        width=int(width or 1)
        require(1<=width<=18 if typ=='9' else 1<=width<=256,'PICTURE width outside supported limit')
        require(key not in p['fields'] and key not in groups, 'Duplicate field names need qualification support')
        spec={'type':'integer' if typ=='9' else 'string','width':width,'group':group,'source_ref':origin,'storage_section':section,'default':0 if typ=='9' else ' '*width}
        if typ=='9':spec.update({'min':0,'max':10**width-1})
        if value:
            v=literal(value);require(type(v) is (int if typ=='9' else str),'VALUE type mismatch')
            require(0<=v<=10**width-1 if typ=='9' else len(v)<=width,'VALUE exceeds PICTURE bounds')
            spec['default']=v if typ=='9' else v.ljust(width)
        p['fields'][key]=spec;return True
    if len(program_matches)!=1:block('Exactly one unambiguous PROGRAM-ID is required',[])
    try:
        for i,(kind,line) in enumerate(lines,1):
            if kind in ('comment','blank'):continue
            if kind=='unsupported':block('Fixed-format continuation or nonblank content beyond column 72 is unsupported',[i]);continue
            upper=line.upper()
            if upper.startswith('PROCEDURE DIVISION'):
                pm=re.fullmatch(r'PROCEDURE DIVISION(?: USING ('+NAME+r'(?:\s+'+NAME+r')*))?\.',upper)
                if procedure or not pm:block('Unsupported or repeated PROCEDURE DIVISION',[i]);continue
                if 0 not in division_order or 2 not in division_order:block('IDENTIFICATION and DATA DIVISION are required before PROCEDURE',[i])
                if not pm[1] or set(pm[1].split())!=groups or len(pm[1].split())!=len(groups):block('PROCEDURE USING must map each declared record group exactly once',[i])
                if groups-{f['group'] for f in p['fields'].values()}:block('Every LINKAGE group requires a supported field layout',[i])
                elif p['coverage'][i-1]['disposition']!='unsupported':p['coverage'][i-1]['disposition']='structure'
                procedure=True;continue
            if procedure:proc.append((i,line));continue
            if upper in ('LINKAGE SECTION.','WORKING-STORAGE SECTION.','FILE SECTION.'):
                section=upper.split()[0]
                if section in sections:block('Repeated record SECTION is unsupported',[i])
                elif section!='LINKAGE':block('Storage lifetime or file binding needs an adapter; only caller-owned LINKAGE records are supported',[i])
                elif not division_order or division_order[-1]!=2:block('Record SECTION requires DATA DIVISION',[i])
                else:p['coverage'][i-1]['disposition']='structure'
                sections.add(section)
                continue
            cm=re.fullmatch(r'COPY\s+('+NAME+r')\.',line,re.I)
            if cm:
                if section!='LINKAGE':block('COPY layout must belong to the supported LINKAGE record section',[i])
                book=cm.group(1).upper();p['copybooks'].append(book)
                matches=[(fp,ft) for fp,ft in files.items()
                         if (classifications.get(fp, {}).get('kind')=='copybook'
                             if classifications is not None else fp.lower().endswith(('.cpy','.copy')))
                         and fp.rsplit('/',1)[-1].rsplit('.',1)[0].upper()==book]
                if len(matches)!=1:
                    p['dependencies'].extend({'name':book,'path':fp,'source_hash':sha(ft),'resolution':'ambiguous'} for fp,ft in matches)
                    block('Copybook missing or ambiguous: '+book,[i]);continue
                p['dependencies'].append({'name':book,'path':matches[0][0],'source_hash':sha(matches[0][1])})
                before=len(p['blockers'])
                for ci,(ck,cl) in enumerate(normalized_lines(matches[0][1]),1):
                    if ck in ('comment','blank'):continue
                    if not field_line(cl,f'{matches[0][0]}:{ci}'):block('Unsupported copybook layout: '+book,[i])
                if len(p['blockers'])==before and p['coverage'][i-1]['disposition']!='unsupported':p['coverage'][i-1]['disposition']='copybook'
                continue
            if field_line(line,f'{path}:{i}'):
                if section!='LINKAGE':block('Data field must belong to the supported LINKAGE record section',[i])
                else:p['coverage'][i-1]['disposition']='data_layout'
                continue
            if re.fullmatch(r'(IDENTIFICATION|ENVIRONMENT|DATA) DIVISION\.|(LINKAGE|WORKING-STORAGE|FILE) SECTION\.|PROGRAM-ID\.\s*'+NAME+r'\.',upper):
                if upper.startswith('PROGRAM-ID.') and (not division_order or division_order[-1]!=0):
                    block('PROGRAM-ID must belong to IDENTIFICATION DIVISION',[i]);continue
                if upper.endswith(' DIVISION.'):
                    rank={'IDENTIFICATION DIVISION.':0,'ENVIRONMENT DIVISION.':1,'DATA DIVISION.':2}[upper]
                    if division_order and rank<=division_order[-1]:block('Repeated or out-of-order DIVISION',[i]);continue
                    division_order.append(rank)
                p['coverage'][i-1]['disposition']='structure';continue
            block('Unsupported declaration: '+line[:100],[i])
    except ValidationError as exc: block(str(exc),[i])
    if not procedure:block('Missing PROCEDURE DIVISION',[])
    if not p['fields']:block('No supported source field layout',[])
    cursor=0;terminated=False
    while cursor<len(proc):
        i,line=proc[cursor];upper=line.upper().removesuffix('.')
        if terminated:block('Executable source after terminal statement',[i]);cursor+=1;continue
        if upper in ('GOBACK','STOP RUN'):
            p['coverage'][i-1]['disposition']='terminal';terminated=True;cursor+=1;continue
        reserved={'ACCEPT','ADD','ALTER','CALL','CANCEL','CLOSE','COMPUTE','CONTINUE','DELETE','DISPLAY','DIVIDE','ELSE','END-IF','EVALUATE','EXIT','GO','GOBACK','IF','INITIALIZE','INSPECT','MERGE','MOVE','MULTIPLY','OPEN','PERFORM','READ','RELEASE','RETURN','REWRITE','SEARCH','SET','SORT','START','STOP','STRING','SUBTRACT','UNSTRING','WRITE'}
        if re.fullmatch(NAME+r'\.',line,re.I) and upper not in reserved:p['coverage'][i-1]['disposition']='paragraph';cursor+=1;continue
        if not upper.startswith('IF '):block('Unsupported executable statement: '+line[:100],[i]);cursor+=1;continue
        start=cursor;depth=1;cursor+=1;else_at=None;nested=False
        while cursor<len(proc) and depth:
            u=proc[cursor][1].upper().removesuffix('.')
            if u.startswith('IF '):depth+=1;nested=True
            if u=='END-IF':depth-=1
            if u=='ELSE' and depth==1:else_at=cursor
            if depth:cursor+=1
        indices=[x[0] for x in proc[start:min(cursor+1,len(proc))]]
        if depth or nested:block('Unclosed or nested IF requires a parser extension',indices);cursor+=1;continue
        try:
            require(not any(x[1].rstrip().endswith('.') for x in proc[start:cursor]), 'Sentence period inside IF changes implicit scope; unsupported')
            require(sum(x[1].upper().rstrip('.')=='ELSE' for x in proc[start:cursor])<=1,'Repeated ELSE is unsupported')
            require((else_at if else_at is not None else cursor)>start+1, 'Empty IF body is unsupported; use explicit CONTINUE')
            require(else_at is None or cursor>else_at+1, 'Empty ELSE body is unsupported; use explicit CONTINUE')
            pred=condition(line[3:],p['fields'])
            then=assignments([x[1] for x in proc[start+1:else_at if else_at is not None else cursor]],p['fields'])
            otherwise=assignments([x[1] for x in proc[else_at+1:cursor]],p['fields']) if else_at is not None else []
            rid=f'{name}_R{len(p["rules"])+1:03d}'
            rule={'id':rid,'predicate':pred,'then':then,'else':otherwise,'source_refs':[f'{path}:{i}-{proc[cursor][0]}'],'source_start':i,'source_end':proc[cursor][0], 'plain':f'If {line[3:].strip()}, '+(' and '.join(f"set {a['field']} to {a['value']!r}" for a in then) or 'keep the current values')+'. Otherwise '+(' and '.join(f"set {a['field']} to {a['value']!r}" for a in otherwise) or 'keep the current values')+'.'}
            p['rules'].append(rule)
            for n in indices:p['coverage'][n-1].update({'disposition':'modeled','rule_id':rid})
            if pred['op']=='=' and isinstance(pred['left'],dict) and isinstance(pred['right'],dict):p['relationships'].append({'left':pred['left']['field'],'right':pred['right']['field'],'kind':'conditional_match','source_refs':rule['source_refs']})
        except ValidationError as exc:block(str(exc),indices)
        cursor+=1
    if not terminated:block('No supported terminal statement',[])
    for entry in p['coverage']:
        if entry['disposition']=='unaccounted':block('Unaccounted source line',[entry['line']])
    p['loc']={'physical':len(lines),'blank':sum(k=='blank' for k,_ in lines),'comment':sum(k=='comment' for k,_ in lines),'code':sum(k not in ('blank','comment') for k,_ in lines)}
    p['dependency_hash']=sha(encode(p['dependencies']))
    p['semantic_hash']=sha(encode({'source_hash':p['source_hash'],'dependencies':p['dependencies']}))
    return p


def analyze_sources(files, manifest):
    from .limits import MAX_SOURCE_FILES, MAX_SOURCE_FILE_BYTES
    require(isinstance(files,dict) and len(files)<=MAX_SOURCE_FILES,'Source export exceeds file-count bound')
    selected_scope=set(manifest.get('lineage_scope',files))
    # A missing snapshot is an intentional historical compatibility boundary:
    # old immutable reports must reproduce their original extension-based analysis.
    classifications=None;findings=[]
    if 'mainframe_knowledge' in manifest:
        from .mainframe import classify_files, utility_findings, validate_snapshot
        for path,text in files.items():
            require(isinstance(text,str) and len(text.encode('utf-8'))<=MAX_SOURCE_FILE_BYTES,'Source file too large')
        validate_snapshot(manifest['mainframe_knowledge'])
        classifications=classify_files(files,manifest,manifest['mainframe_knowledge'])
        findings=utility_findings(manifest,manifest['mainframe_knowledge'],files)
    cics_version=manifest.get('cics_contract_version')
    require(cics_version is None or type(cics_version) is int and cics_version==1, 'Unsupported frozen CICS screen contract')
    catalog_evidence={}
    if cics_version==1:
        from .db2_catalog import table_description
        for path,text in files.items():
            descriptor=table_description(text)
            if descriptor is not None:
                catalog_evidence[path]=descriptor
                if classifications is not None:
                    classifications[path]={'kind':'db2_catalog_evidence','confidence':'observed_metadata','candidate_kinds':['db2_catalog_evidence'],
                        'evidence':[{'line':1,'reason':'Validated typed Db2 MCP table-description receipt; metadata is not executable SQL'}],
                        'evidence_truncated':False,'conflicts':[],'utility_ids':[],'conversion_support':'not_established'}
    programs={};assets=[];blockers=[]
    for path,text in sorted(files.items()):
        require(isinstance(text,str) and len(text.encode('utf-8'))<=MAX_SOURCE_FILE_BYTES,'Source file too large')
        lower=path.lower();stem=path.rsplit('/',1)[-1].rsplit('.',1)[0].upper();h=sha(text)
        if path in catalog_evidence:
            descriptor=catalog_evidence[path]
            assets.append({'id':sha('db2_catalog_evidence:'+path+':'+h),'kind':'db2_catalog_evidence','name':descriptor['schema']+'.'+descriptor['table'],
                'path':path,'source_hash':h,'source_text':text,'catalog_evidence':descriptor,'executable_source':False,
                'tables':[descriptor['schema']+'.'+descriptor['table']], 'loc':{'physical':len(text.splitlines()),'code':0},
                'selected':path in selected_scope,'scope_disposition':'selected' if path in selected_scope else 'out_of_scope',
                'scope_reason':'Observed typed Db2 catalog evidence, retained for local analysis; no executable database replacement is inferred'})
            if path in selected_scope:
                for obligation in descriptor['missing_semantics']:
                    blockers.append({'kind':'db2_catalog_semantics_gap','path':path,'lines':list(range(1,len(text.splitlines())+1)),
                        'object':descriptor['schema']+'.'+descriptor['table'],'obligation':obligation,
                        'message':'Db2 '+descriptor['schema']+'.'+descriptor['table']+': '+obligation+' is not established by this typed catalog receipt. Retain actual DDL/keys/indexes/triggers and implement/test database, transaction, type and authorization semantics before conversion credit; metadata alone is not executable support.'})
            continue
        classification=classifications[path] if classifications is not None else None
        classified_kind=classification['kind'] if classification is not None else None
        is_program=classified_kind=='cobol_program' if classification is not None else lower.endswith(('.cbl','.cob','.cobol'))
        if is_program and path not in selected_scope:
            lines=normalized_lines(text)
            assets.append({'id':sha('cobol_program:'+path+':'+h),'kind':'cobol_program','name':stem,'path':path,'source_hash':h,'source_text':text,'loc':{'physical':len(lines),'code':sum(k not in ('blank','comment') for k,_ in lines)},'selected':False})
            continue
        if is_program:
            p=analyze_program(path,text,files,classifications)
            if classification is not None:p['target_contract_version']=2
            require(p['name'] not in programs,'Duplicate program ID needs disambiguation')
            programs[p['name']]=p;assets.append(dict(p))
        else:
            if classification is not None:
                kind=classified_kind if classified_kind in ('copybook','jcl_job','bms_map','sql') else 'other_source'
            else:
                kind='copybook' if lower.endswith(('.cpy','.copy')) else 'jcl_job' if lower.endswith('.jcl') else 'bms_map' if lower.endswith('.bms') else 'sql' if lower.endswith('.sql') else 'other_source'
            asset={'id':sha(kind+':'+stem+':'+h),'kind':kind,'name':stem,'path':path,'source_hash':h,'source_text':text,'loc':{'physical':len(text.splitlines()),'code':sum(bool(x.strip()) and not x.lstrip().startswith(('*>','--','//*')) for x in text.splitlines())}}
            if classification is not None:
                # Unknown languages cannot inherit another language's comment rules.
                if kind=='copybook':asset['loc']['code']=sum(k not in ('blank','comment') for k,_ in normalized_lines(text))
                else:
                    prefix={'jcl_job':'//*','sql':'--'}.get(kind)
                    asset['loc']['code']=sum(bool(x.strip()) and not (prefix and x.lstrip().startswith(prefix)) for x in text.splitlines())
                if path in selected_scope and (classified_kind in ('unknown','ambiguous') or classification.get('conflicts')):
                    blockers.append({'kind':'source_classification','path':path,'message':'File classification is '+classified_kind+'; resolve the source type using original export metadata and content evidence before conversion. '+('; '.join(classification.get('conflicts',[])))})
                elif path in selected_scope and kind in ('other_source','sql'):
                    blockers.append({'kind':'unsupported_source','path':path,'message':'Recognized '+classified_kind+' source requires a reviewed semantic adapter; recognizing its file type does not convert its behavior.'})
            if kind=='sql':
                asset['tables']=sql_table_references(text) if classification is not None else sorted(set(re.findall(r'\b(?:FROM|JOIN|INTO|UPDATE|CREATE\s+TABLE)\s+([A-Z][A-Z0-9_.]*)',text,re.I)))
                if classification is not None:asset['table_evidence_basis']='STATIC_UNQUOTED_REFERENCES_NOT_CATALOG_INVENTORY'
            if kind=='bms_map':
                asset['screens']=re.findall(r'^(\w+)\s+DFHMDI\b',text,re.M|re.I)
                if path in selected_scope and cics_version!=1:blockers.append({'kind':'unsupported_source','message':'BMS/CICS behavior requires source-supported action mapping; no replacement screen is credited.','path':path})
            assets.append(asset)
    for finding in findings:
        if 'lineage_scope' in manifest and finding.get('source_refs') and not any(r.get('path') in selected_scope for r in finding['source_refs']):continue
        refs=finding.get('source_refs',[]);first_ref=refs[0] if refs else {}
        location=(finding['job']+'.'+finding['step']) if finding.get('job') and finding.get('step') else first_ref.get('path','source export')+(':'+str(first_ref['line']) if first_ref.get('line') else '')
        blocker={'kind':'unsupported_utility','message':'Utility '+finding['program']+' in '+location+' is recognized but has no verified executable adapter. '+finding.get('behavior','')+' Required evidence: '+('; '.join(finding.get('required_evidence',[]))), 'job':finding.get('job',''),'step':finding.get('step',''),'utility_id':finding['utility_id']}
        if first_ref:
            blocker['source_refs']=refs;blocker['path']=first_ref['path']
            blocker['lines']=[r['line'] for r in refs if r['path']==first_ref['path']]
        blockers.append(blocker)
    graph=[]
    used=set()
    for job in manifest['jobs']:
        for step in job['steps']:
            name=step['program'].upper();used.add(name)
            graph.append({'from':job['name']+'.'+step['name'],'to':name,'kind':'calls','inputs':step['inputs'],'outputs':step['outputs']})
            if name not in programs:blockers.append({'kind':'missing_source','message':'Program/utility source or supported adapter missing: '+name})
            if step['condition'].upper() not in ('ALWAYS','') and not re.fullmatch(r'RC\s*(?:<=|>=|=|<|>)\s*\d{1,5}',step['condition'],re.I):blockers.append({'kind':'unresolved_condition','message':'Unknown step condition: '+step['condition']})
    for tx in manifest.get('transactions',[]):
        blockers.append({'kind':'online_semantics_gap','message':'Transaction '+tx['id']+': native CICS/BMS session, map, AID, navigation, security and transaction semantics require explicit source-supported replacements; record APIs alone are insufficient'})
        used.add(tx['program'])
        graph.append({'from':tx['id'],'to':tx['program'],'kind':'transaction_entry','inputs':[],'outputs':[]})
        if tx['program'] not in programs:blockers.append({'kind':'missing_source','message':'Transaction entry program missing: '+tx['program']})
    for p in programs.values():
        for book in p['copybooks']:graph.append({'from':p['name'],'to':book,'kind':'copybook'})
    # Validate the entire supported card grammar and reconcile source step order.
    jcl_job_origins={}
    for path,text in files.items():
        if path not in selected_scope:continue
        if classifications is not None:
            if classifications[path]['kind']!='jcl_job':continue
        elif not path.lower().endswith('.jcl'):continue
        current=None;source_jobs={}
        for raw in text.splitlines():
            if not raw.strip() or raw.startswith('//*'):continue
            card=raw.rstrip()
            job=re.fullmatch(r"//([A-Z][A-Z0-9]{0,7})\s+JOB(?:\s+\([^)]*\)(?:,'[^']*')?)?",card,re.I)
            execute=re.fullmatch(r'//([A-Z][A-Z0-9]{0,7})\s+EXEC\s+PGM=('+NAME+r')',card,re.I)
            dd=re.fullmatch(r'//([A-Z][A-Z0-9]{0,7})\s+DD\s+DSN=[A-Z0-9@$#.-]+(?:,DISP=SHR)?',card,re.I)
            if job:
                current=job[1].upper()
                if current in jcl_job_origins:blockers.append({'kind':'unsupported_jcl','path':path,'message':'Repeated JCL JOB declaration requires explicit identity/scope resolution: '+current})
                jcl_job_origins[current]=path;source_jobs.setdefault(current,[])
            elif execute and current:source_jobs[current].append((execute[1].upper(),execute[2].upper()))
            elif dd and current and source_jobs[current]:blockers.append({'kind':'unsupported_jcl','path':path,'message':'DD dataset allocation/read/write semantics need an explicit I/O adapter: '+card[:100]})
            else:blockers.append({'kind':'unsupported_jcl','path':path,'message':'Unsupported complete JCL card or trailing clause: '+card[:100]})
        manifest_jobs={j['name'].upper():j for j in manifest['jobs']}
        for name,steps in source_jobs.items():
            job=manifest_jobs.get(name)
            expected=[(s['name'].upper(),s['program'].upper()) for s in job['steps']] if job else None
            if steps!=expected:blockers.append({'kind':'scope_mismatch','path':path,'message':'JCL job/step/program order differs from manifest: '+name})
            if job and any(s['condition'].upper() not in ('ALWAYS','') for s in job['steps']):blockers.append({'kind':'scope_mismatch','path':path,'message':'Manifest conditional steps are not evidenced by the supported unconditional JCL grammar: '+name})
    # Unreferenced programs are discovered but do not inflate the selected conversion scope.
    scoped={n:p for n,p in programs.items() if n in used or ('lineage_scope' in manifest and p['path'] in selected_scope)}
    selected_paths={p['path'] for p in scoped.values()} | {d['path'] for p in scoped.values() for d in p['dependencies']}
    for p in scoped.values():blockers+=p['blockers']
    for asset in assets:
        asset['selected']=asset['path'] in selected_scope if 'lineage_scope' in manifest else asset['path'] in selected_paths or asset['kind'] in ('jcl_job','bms_map','sql','other_source','db2_catalog_evidence')
        asset['scope_disposition']='selected' if asset['selected'] else 'out_of_scope'
        asset['scope_reason']='Selected manifest program, resolved dependency, or additional process export requiring accountability' if asset['selected'] else 'Not called by the selected manifest and not a resolved COPY dependency'
    scoped_assets=assets
    result={'programs':scoped,'assets':scoped_assets,'rules':[r for p in scoped.values() for r in p['rules']], 'graph':graph,'blockers':blockers,'source_snapshot':sha('\n'.join(k+':'+sha(v) for k,v in sorted(files.items()))),'source_accounting':{p['name']:p['coverage'] for p in scoped.values()}, 'relationships':[r for p in scoped.values() for r in p['relationships']], 'evidence_basis':'SOURCE_DERIVED_EXPECTED'}
    if classifications is not None:result.update({'classifications':classifications,'utility_findings':findings})
    if cics_version==1:
        from .cics import analyze_cics
        result['cics_contract_version']=1
        result['cics']=analyze_cics(files,manifest,scoped,classifications)
        result['blockers'].extend(result['cics']['gaps'])
        for asset in result['assets']:
            if asset['kind']=='bms_map':
                asset['screens']=[screen['map'] for screen in result['cics']['screens'] if screen['source_path']==asset['path']]
        result['db2_catalog_evidence']=[{'source_path':path,**descriptor} for path,descriptor in sorted(catalog_evidence.items())]
    if manifest.get('requirements'):
        from .requirements import project
        result=project(result,manifest['requirements'],manifest.get('jobs',[]))
    return result
