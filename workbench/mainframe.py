"""Declarative mainframe knowledge and conservative, evidence-based classification.

Catalog text is context, never executable instructions or proof of conversion. A
process freezes this snapshot so later catalog edits cannot change old evidence.
"""
from pathlib import Path
from copy import deepcopy
from datetime import date
import re
from .domain import ValidationError, decode, encode, require, safe_path, sha

CATALOG_PATH = Path(__file__).resolve().parent.parent / 'knowledge' / 'mainframe-catalog.json'
CATALOG_LIMIT = 2 * 1024 * 1024
KINDS = {'cobol_program', 'copybook', 'jcl_job', 'jcl_proc', 'jcl_fragment',
         'bms_map', 'sql', 'dclgen', 'utility_control', 'rexx', 'clist', 'pli',
         'assembler', 'cics_definition', 'scheduler_definition', 'unknown', 'ambiguous'}
UTILITY_FIELDS = {'id', 'name', 'aliases', 'category', 'behavior', 'required_evidence',
                  'risks', 'references'}
APPLICATION_FIELDS = UTILITY_FIELDS | {'owner', 'version', 'record_formats', 'return_codes',
                                        'side_effects', 'dependencies'}
TOKEN = re.compile(r'^[A-Z@$#][A-Z0-9@$#_-]{0,63}$')
JCL_EXEC = re.compile(r'^//([A-Z0-9@$#]+)?\s+EXEC\s+PGM\s*=\s*([A-Z@$#][A-Z0-9@$#_-]*)(?:\s|,|$)', re.I)
HEX = re.compile(r'^[a-f0-9]{64}$')


def _keys(value, expected, label):
    require(isinstance(value, dict) and set(value) == set(expected), label + ': unexpected or missing fields')


def _string(value, label, limit=4000, empty=False):
    require(isinstance(value, str) and len(value) <= limit and (empty or bool(value.strip())), label + ': invalid text')
    require(not any(ord(c) < 32 and c not in '\n\t\r' for c in value), label + ': control characters are not accepted')


def _strings(value, label, maximum=100, empty=True):
    require(isinstance(value, list) and len(value) <= maximum and (empty or bool(value)), label + ': invalid list')
    for item in value: _string(item, label)
    require(len(value) == len(set(value)), label + ': duplicate entries')


def _utility(value, application=False):
    _keys(value, APPLICATION_FIELDS if application else UTILITY_FIELDS, 'Utility')
    for field in ('id', 'name'):
        require(isinstance(value[field], str) and TOKEN.fullmatch(value[field]), 'Utility ' + field + ': use an uppercase portable identifier')
    _strings(value['aliases'], 'Utility aliases', 50)
    require(all(TOKEN.fullmatch(x) for x in value['aliases']), 'Utility aliases: invalid identifier')
    require(value['name'] not in value['aliases'], 'Utility name must not be repeated as an alias')
    for field in ('category', 'behavior'): _string(value[field], 'Utility ' + field)
    for field in ('required_evidence', 'risks', 'references'): _strings(value[field], 'Utility ' + field, empty=False)
    if application:
        for field in ('owner', 'version'): _string(value[field], 'Application utility ' + field)
        for field in ('record_formats', 'return_codes', 'side_effects', 'dependencies'):
            _strings(value[field], 'Application utility ' + field, empty=False)


def _validate_catalog(catalog):
    _keys(catalog, {'schema_version', 'reviewed_on', 'categories', 'utilities', 'topics'}, 'Standard catalog')
    require(type(catalog['schema_version']) is int and catalog['schema_version'] == 1, 'Unsupported standard catalog schema')
    require(isinstance(catalog['reviewed_on'], str) and re.fullmatch(r'\d{4}-\d{2}-\d{2}', catalog['reviewed_on']), 'Invalid catalog review date')
    try:
        date.fromisoformat(catalog['reviewed_on'])
    except ValueError as exc:
        raise ValidationError('Invalid catalog review date') from exc
    require(isinstance(catalog['categories'], list) and len(catalog['categories']) <= 40, 'Invalid classification categories')
    kinds=[]
    for entry in catalog['categories']:
        _keys(entry, {'kind', 'description', 'required_evidence'}, 'Classification category')
        require(isinstance(entry['kind'], str) and entry['kind'] in KINDS, 'Unknown classification category')
        kinds.append(entry['kind']); _string(entry['description'], 'Category description')
        _strings(entry['required_evidence'], 'Category evidence', empty=False)
    require(set(kinds) == KINDS and len(kinds) == len(KINDS), 'Catalog must describe every classification exactly once')
    require(isinstance(catalog['utilities'], list) and len(catalog['utilities']) <= 200, 'Invalid utility catalog')
    for item in catalog['utilities']: _utility(item)
    require(isinstance(catalog['topics'], list) and len(catalog['topics']) <= 100, 'Invalid knowledge topics')
    ids=[]
    for topic in catalog['topics']:
        _keys(topic, {'id', 'title', 'checks', 'references'}, 'Knowledge topic')
        _string(topic['id'], 'Topic identity'); ids.append(topic['id'])
        _string(topic['title'], 'Topic title')
        _strings(topic['checks'], 'Topic checks', empty=False)
        _strings(topic['references'], 'Topic references', empty=False)
    require(len(ids) == len(set(ids)), 'Duplicate knowledge topic')


def _validate_application(application):
    _keys(application, {'schema_version', 'application', 'utilities', 'notes'}, 'Application knowledge')
    require(type(application['schema_version']) is int and application['schema_version'] == 1, 'Unsupported application knowledge schema')
    _string(application['application'], 'Application name', empty=True)
    _strings(application['notes'], 'Application notes', 200)
    require(isinstance(application['utilities'], list) and len(application['utilities']) <= 200, 'Too many application utilities')
    for item in application['utilities']: _utility(item, application=True)


def _check_aliases(catalog, application):
    identifiers=set(); aliases=set()
    for utility in catalog['utilities'] + application['utilities']:
        require(utility['id'] not in identifiers, 'Duplicate utility identity: ' + utility['id'])
        identifiers.add(utility['id'])
        for name in [utility['name'], *utility['aliases']]:
            require(name not in aliases, 'Utility name or alias shadows another entry: ' + name)
            aliases.add(name)


def load_knowledge(workspace: Path):
    """Load standard knowledge plus optional local application overlay, without writes."""
    require(not CATALOG_PATH.is_symlink(), 'Standard catalog must not be a symlink')
    require(CATALOG_PATH.is_file(), 'Standard catalog must be an existing JSON file')
    require(CATALOG_PATH.stat().st_size <= CATALOG_LIMIT, 'Standard catalog exceeds size limit')
    standard_bytes=CATALOG_PATH.read_bytes(); catalog=decode(standard_bytes, CATALOG_LIMIT)
    path=safe_path(Path(workspace), 'knowledge/application-knowledge.json')
    application={'schema_version':1, 'application':'', 'utilities':[], 'notes':[]}
    application_hash=None
    if path.exists():
        require(path.is_file() and path.stat().st_size <= CATALOG_LIMIT, 'Application knowledge must be a bounded JSON file')
        raw=path.read_bytes(); application=decode(raw, CATALOG_LIMIT); application_hash=sha(raw)
    snapshot={'schema_version':1, 'catalog':catalog, 'application':application,
              'source_hashes':{'standard':sha(standard_bytes), 'application':application_hash}}
    snapshot['content_hash']=sha(encode(snapshot))
    validate_snapshot(snapshot)
    return snapshot


def validate_snapshot(snapshot):
    """Reject malformed, modified or executable/support-claim catalog fields."""
    _keys(snapshot, {'schema_version', 'catalog', 'application', 'source_hashes', 'content_hash'}, 'Knowledge snapshot')
    require(type(snapshot['schema_version']) is int and snapshot['schema_version'] == 1, 'Unsupported knowledge snapshot schema')
    require(len(encode(snapshot)) <= 2 * CATALOG_LIMIT, 'Knowledge snapshot exceeds size limit')
    _validate_catalog(snapshot['catalog']); _validate_application(snapshot['application'])
    _check_aliases(snapshot['catalog'], snapshot['application'])
    _keys(snapshot['source_hashes'], {'standard', 'application'}, 'Knowledge source hashes')
    require(isinstance(snapshot['source_hashes']['standard'], str) and HEX.fullmatch(snapshot['source_hashes']['standard']), 'Invalid standard catalog hash')
    application_hash=snapshot['source_hashes']['application']
    require(application_hash is None or (isinstance(application_hash, str) and HEX.fullmatch(application_hash)), 'Invalid application catalog hash')
    if application_hash is None:
        require(snapshot['application'] == {'schema_version':1, 'application':'', 'utilities':[], 'notes':[]},
                'Application knowledge content requires a source hash')
    require(isinstance(snapshot['content_hash'], str) and HEX.fullmatch(snapshot['content_hash']), 'Invalid knowledge content hash')
    require(snapshot['content_hash'] == sha(encode({k:v for k,v in snapshot.items() if k != 'content_hash'})), 'Knowledge snapshot content changed')


def _utility_index(snapshot):
    return {name:(item, origin) for origin, items in (
        ('standard', snapshot['catalog']['utilities']), ('application', snapshot['application']['utilities']))
        for item in items for name in [item['name'], *item['aliases']]}


def _without_block_comments(raw, depth, quote=None):
    """Remove comments and mask literal continuation lines, retaining locations."""
    result=[]; index=0; continued=quote is not None
    if continued: result.append(quote)
    while index < len(raw):
        pair=raw[index:index+2]; char=raw[index]
        if depth:
            if pair=='/*': depth+=1; index+=2
            elif pair=='*/': depth-=1; index+=2; result.append(' ')
            else: index+=1
        elif quote:
            result.append(' ' if continued and char != quote else char); index+=1
            if char==quote:
                if index < len(raw) and raw[index]==quote:
                    result.append(raw[index]); index+=1
                else: quote=None; continued=False
        elif char in "\"'": quote=char; result.append(char); index+=1
        elif pair in {'--', '*>'}: break
        elif pair=='/*': depth=1; index+=2; result.append(' ')
        else: result.append(char); index+=1
    return ''.join(result), depth, quote


def _lines(text):
    """Preserve locations, excluding comments and literal in-stream input payloads.

    This is recognition only: symbol expansion, continued DD operands and
    product-specific data delimiters still need the native JCL adapter.
    """
    result=[]; data=None; block_depth=0; quote=None; jcl_seen=False
    for number, raw in enumerate(text.splitlines(), 1):
        if data:
            delimiter, ends_at_jcl=data
            if raw.startswith(delimiter):
                data=None; continue
            if ends_at_jcl and raw.startswith('//'): data=None
            else: continue
        # Blank sequence fields must not mistake an indented SQL DELETE for
        # a COBOL debug indicator. Numeric sequence fields are unambiguous;
        # unnumbered debug lines need whitespace or a COBOL declaration marker.
        fixed=(re.match(r'^\d{6}[ */Dd-]',raw) or
               re.match(r'^ {6}(?:[ */-]|[Dd](?=\s|PROGRAM-ID\b|COPY\b|\d{2}\s))',raw,re.I))
        if fixed and not block_depth and not quote:
            if raw[6] in '*/': continue
            raw=raw[7:72]
        if not block_depth and not quote and raw.lstrip().startswith(('*>', '//*', '--')): continue
        # A bare /* is a JCL delimiter, not an unterminated source comment.
        if not block_depth and not quote and raw.startswith('//'): jcl_seen=True
        if raw.strip()=='/*' and not block_depth and not quote and jcl_seen: continue
        if block_depth or quote or not raw.startswith('//'):
            rexx_header=not block_depth and not quote and re.match(r'^\s*/\*\s*REXX\b', raw, re.I)
            raw,block_depth,quote=_without_block_comments(raw,block_depth,quote)
            if rexx_header: result.append((number, '/* REXX */'))
        result.append((number, raw))
        inline=re.match(r'^//(?:[A-Z0-9@$#]+)?\s+DD\s+(DATA|\*)(?=\s|,|$)',raw,re.I)
        if inline:
            delimiter=re.search(r"(?:^|,)\s*DLM\s*=\s*(?:'([^']{1,8})'|([^,\s]{1,8}))(?=\s|,|$)",raw[inline.end():],re.I)
            value=(delimiter[1] or delimiter[2]) if delimiter else '/*'
            data=(value, inline[1]=='*' and delimiter is None)
    return result


def _validate_exports(files):
    require(isinstance(files,dict) and all(isinstance(path,str) and isinstance(text,str)
            for path,text in files.items()), 'Classification requires text exports with path identities')


def classify_files(files: dict[str, str], manifest: dict, snapshot: dict):
    """Classify using structural evidence; suffixes are hints, never proof."""
    validate_snapshot(snapshot); _validate_exports(files); utilities=_utility_index(snapshot)
    copy_refs=set()
    for text in files.values():
        for _, line in _lines(text):
            copy_match=re.match(r'''^\s*COPY\s+(?:(["'])([A-Z@$#][A-Z0-9@$#_-]*)\1|([A-Z@$#][A-Z0-9@$#_-]*))(?=\s|\.|$)''',line,re.I)
            if copy_match: copy_refs.add((copy_match[2] or copy_match[3]).upper())
    suffixes={'.cbl':'cobol_program','.cob':'cobol_program','.cobol':'cobol_program', '.cpy':'copybook','.copy':'copybook',
              '.jcl':'jcl_job','.proc':'jcl_proc','.bms':'bms_map','.sql':'sql','.ddl':'sql','.dclgen':'dclgen',
              '.rexx':'rexx','.rex':'rexx','.clist':'clist','.pli':'pli','.pl1':'pli','.asm':'assembler',
              '.cntl':'utility_control','.ctl':'utility_control','.csd':'cics_definition','.ca7':'scheduler_definition'}
    output={}
    for path, text in sorted(files.items()):
        require(isinstance(path, str) and isinstance(text, str), 'Classification requires text exports with path identities')
        candidates={}; lines=_lines(text); stem=Path(path).stem.upper(); suffix=Path(path).suffix.lower()
        def add(kind, number, reason): candidates.setdefault(kind, []).append({'line':number, 'reason':reason})
        for number,line in lines:
            stripped=line.strip(); upper=stripped.upper()
            if re.match(r'^PROGRAM-ID\s*\.', stripped, re.I): add('cobol_program',number,'COBOL PROGRAM-ID declaration')
            if re.match(r'^//[A-Z0-9@$#]+\s+JOB(?:\s|$)', line, re.I): add('jcl_job',number,'JCL JOB statement')
            if re.match(r'^//[A-Z0-9@$#]+\s+PROC(?:\s|$)', line, re.I): add('jcl_proc',number,'JCL PROC statement')
            if re.match(r'^//(?:[A-Z0-9@$#]+)?\s+(?:EXEC|DD|INCLUDE|SET|PEND|IF)\b', line, re.I): add('jcl_fragment',number,'JCL execution, data definition or control statement')
            if re.match(r'^(?:[A-Z0-9@$#]+\s+)?DFHM(?:SD|DI|DF)\b', stripped, re.I): add('bms_map',number,'CICS BMS macro')
            if re.match(r'^\d{2}\s+[A-Z][A-Z0-9_-]*(?:\s|\.)', stripped, re.I): add('copybook',number,'COBOL data-level declaration')
            if re.match(r'^(?:EXEC\s+SQL\s+)?DECLARE\s+[A-Z][A-Z0-9_.]*\s+TABLE\b', stripped, re.I): add('dclgen',number,'SQL DECLARE TABLE descriptor')
            if re.match(r'^(?:CREATE|ALTER|DROP)\s+(?:TABLE|INDEX|VIEW|SCHEMA|DATABASE|TABLESPACE)\b|^(?:SELECT(?!\s+FROM\s*\()\s+|INSERT\s+INTO\s|UPDATE\s+\S+\s+SET\s|DELETE\s+FROM\s)', stripped, re.I): add('sql',number,'SQL statement')
            if re.match(r'^(?:SORT\s+FIELDS|MERGE\s+FIELDS|JOINKEYS\s|JOIN\s+UNPAIRED|REFORMAT\s+FIELDS|INCLUDE\s+COND|OMIT\s+COND|SUM\s+FIELDS|INREC\s|OUTREC\s|OUTFIL\s|OPTION\s+COPY|(?:COPY|COUNT|DISPLAY|OCCUR|SELECT|STATS|UNIQUE|VERIFY)\s+FROM\s*\(|REPRO\s+(?:IN|OUT)|DEFINE\s+(?:CLUSTER|GDG|AIX)|DELETE\s+[A-Z0-9@$#_-]+\.[A-Z0-9@$#_.-]+|SET\s+(?:MAXCC|LASTCC)\s*=|PRINT\s+INFILE\s*\(|LISTCAT(?:\s|$))', stripped, re.I): add('utility_control',number,'Recognized sort/access-method control statement; dialect still needs resolution')
            if number <= 5 and re.match(r'^\s*/\*\s*REXX\b', line,re.I): add('rexx',number,'REXX identifying comment')
            if re.match(r'^PROC\s+\d+\b', stripped,re.I): add('clist',number,'CLIST positional-parameter declaration')
            if re.match(r'^(?:[A-Z][A-Z0-9_]*\s*:\s*)?(?:PROC|PROCEDURE)\b.*;\s*$', stripped,re.I): add('pli',number,'PL/I procedure declaration')
            if re.match(r'^(?:[A-Z0-9@$#]+\s+)(?:CSECT|DSECT|START)\b', stripped,re.I): add('assembler',number,'Assembler section declaration')
            if re.match(r'^(?:DEFINE|ALTER|DELETE|LIST)\s+(?:TRANSACTION|PROGRAM|FILE|MAPSET|GROUP|LIST)\s*\(', stripped,re.I): add('cics_definition',number,'CICS resource-definition command')
            if re.match(r'^(?:JOB|LJOB|LQ|LPRRN)\s*,\s*JOB=', stripped,re.I): add('scheduler_definition',number,'Scheduler command; product/version must be confirmed')
        # Nested material is expected in its containing language and is not a conflict.
        if 'cobol_program' in candidates:
            for child in ('copybook','sql','dclgen'): candidates.pop(child,None)
        if 'dclgen' in candidates:
            for child in ('copybook','sql'): candidates.pop(child,None)
        if 'bms_map' in candidates: candidates.pop('assembler',None)
        if 'jcl_job' in candidates or 'jcl_proc' in candidates:
            candidates.pop('jcl_fragment',None); candidates.pop('utility_control',None); candidates.pop('sql',None)
        if 'jcl_job' in candidates: candidates.pop('jcl_proc',None) # in-stream PROC belongs to its job
        if not candidates and stem in copy_refs:
            add('copybook',None,'COBOL COPY dependency identifies this member as reusable source; grammar support is assessed separately')
        kinds=sorted(candidates); hint=suffixes.get(suffix); conflicts=[]
        if hint and kinds and hint not in kinds:
            # .jcl can hold a procedure or an include fragment; .cpy can hold DCLGEN.
            compatible=(hint=='jcl_job' and set(kinds)<={'jcl_proc','jcl_fragment'}) or (hint=='copybook' and kinds==['dclgen'])
            if not compatible: conflicts.append('Filename suffix suggests '+hint+' but content suggests '+', '.join(kinds))
        if len(kinds)>1: conflicts.append('Multiple incompatible structural classifications: '+', '.join(kinds))
        evidence=[e for kind in kinds for e in candidates[kind]]
        if hint: evidence.append({'line':None, 'reason':'Filename suffix is a hint for '+hint})
        if stem in copy_refs: evidence.append({'line':None, 'reason':'Member name is referenced by a COBOL COPY statement'})
        if conflicts: kind='ambiguous'; confidence='conflicting'
        elif len(kinds)==1: kind=kinds[0]; confidence='structural'
        else: kind='unknown'; confidence='unresolved'; evidence.append({'line':None,'reason':'No supported structural signature; extension or member name alone is insufficient'})
        used=sorted({utilities[m[2].upper()][0]['id'] for _,line in lines if (m:=JCL_EXEC.match(line)) and m[2].upper() in utilities})
        output[path]={'kind':kind,'confidence':confidence,'candidate_kinds':kinds or ([hint] if hint else []),
                      'evidence':evidence[:200], 'evidence_truncated':len(evidence)>200,
                      'conflicts':conflicts,'utility_ids':used,'conversion_support':'not_established'}
    return output


def utility_findings(manifest: dict, snapshot: dict, files: dict[str, str] | None = None):
    """Recognize utilities in manifest and actual JCL cards without conversion credit."""
    validate_snapshot(snapshot); _validate_exports(files if files is not None else {})
    require(isinstance(manifest,dict) and isinstance(manifest.get('jobs',[]),list), 'Utility findings require a job list')
    index=_utility_index(snapshot); findings=[]; unmatched_manifest={}
    def finding(name, job, step, origin, source_ref=None):
        if name not in index: return
        key=(job.upper(), step.upper(), name)
        # Match each manifest declaration to at most one physical occurrence.
        # Repeated unnamed steps, duplicate exports and procedure members retain
        # separate evidence rows, even when their human-readable names coincide.
        if source_ref and unmatched_manifest.get(key):
            unmatched_manifest[key].pop(0)['source_refs'].append(source_ref)
            return
        item,source=index[name]
        row={'job':job,'step':step,'program':name,'utility_id':item['id'],
            'source':source,'behavior':item['behavior'],'required_evidence':item['required_evidence'],
            'risks':item['risks'],'references':item['references'],'conversion_support':'adapter_required',
            'invocation_origin':origin,'source_refs':[source_ref] if source_ref else [],
            'blocking_reason':'Recognition is not conversion. This invocation needs source/control-card evidence and a tested semantic adapter before it can be credited.'}
        if source=='application':
            row['application_details']={key:item[key] for key in ('owner','version','record_formats','return_codes','side_effects','dependencies')}
            row['application_details']['evidence_status']='unverified_application_context'
        row=deepcopy(row)
        findings.append(row)
        if origin=='manifest': unmatched_manifest.setdefault(key,[]).append(row)
    for job in manifest.get('jobs',[]):
        require(isinstance(job,dict) and isinstance(job.get('steps',[]),list), 'Utility findings require job objects with step lists')
        _string(job.get('name'), 'Utility job identity')
        require(not any(c.isspace() for c in job['name']), 'Utility job identity must be one identifier')
        for step in job.get('steps',[]):
            require(isinstance(step,dict), 'Utility findings require step objects')
            for field in ('name','program'):
                _string(step.get(field), 'Utility step '+field)
                require(not any(c.isspace() for c in step[field]), 'Utility step '+field+' must be one identifier')
            finding(step.get('program','').upper(),job['name'],step['name'],'manifest')
    for path,text in sorted((files or {}).items()):
        job=''
        for number,line in _lines(text):
            if line.strip()=='//': job=''
            match=re.match(r'^//([A-Z0-9@$#]+)\s+JOB(?:\s|$)',line,re.I)
            if match: job=match[1].upper()
            execute=JCL_EXEC.match(line)
            if execute: finding(execute[2].upper(),job,(execute[1] or '').upper(),'source',{'path':path,'line':number})
    return findings
