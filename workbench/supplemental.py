"""Exact manual source fallback after a frozen failed read-only retrieval.

This local deterministic helper never scans by default, writes a source, executes
an export or returns protected content to a model. The Coordinator alone accepts
its original-byte intents through the existing immutable discovery journal.
"""
from datetime import datetime, timezone
import os
from pathlib import Path
import re
import unicodedata

from .domain import ValidationError, decode, encode, require, safe_path, sha, path_is_link
from .limits import (MAX_JSON_DOCUMENT_BYTES, MAX_SOURCE_ENTRIES, MAX_SOURCE_FILES,
                     MAX_SOURCE_FILE_BYTES, MAX_SOURCE_BYTES, MAX_SOURCE_LINES,
                     source_line_count)
from .mainframe import classify_files, load_knowledge, validate_snapshot, _lines
from .connectors import zowe_dataset
from .retrieval import (_verify_request, _provenance, _zowe_transport, _source_generation,
                        validate_source_paths)

_BUCKETS={'job':('JCL','JCLPlus'), 'proc':('PROCConverted','JCLPlus','JCL'),
          'jcl_include':('JCLPlus','JCL','PROCConverted'),
          'copybook':('Copybooks',), 'dclgen':('Copybooks',),
          'control':('ControlCards',), 'control_member':('ControlCards',)}
_KINDS={'job':{'jcl_job'}, 'proc':{'jcl_proc'}, 'jcl_include':{'jcl_fragment'},
        'copybook':{'copybook','dclgen'}, 'dclgen':{'dclgen'},
        'control':{'utility_control'}, 'control_member':{'utility_control'}}
_MEMBER=re.compile(r'[A-Z@$#][A-Z0-9@$#_-]{0,127}',re.I)
# A NOT_FOUND label alone does not prove absence; denied/unsafe/unavailable reads
# are never authorization to cross to another source route.
_DENIED=re.compile(r'\b(?:auth|authentication|authorization|unauthori[sz]ed|denied|denial|forbidden|permission|security|untrusted|'
                   r'configuration|unavailable|timeout|expired)\b|'
                   r'\b(?:connection|connectivity|profile|certificate|tls|ssl)\b.*'
                   r'\b(?:fail(?:ed|ure)?|error|invalid|untrusted|reject(?:ed)?|not.configured|missing)\b|'
                   r'\b(?:not.configured|unable.to.connect|failed.to.connect|timed.out)\b',re.I)
_ABSENT=re.compile(r'not[ -]found|does[ -]not[ -]exist|no[ -]matching[ -](?:member|dataset|data.set|file)|'
                   r'(?:member|dataset|data.set|file)[ -](?:is[ -])?absent',re.I)


def _read(path,limit,label):
    require(path.is_file() and not path_is_link(path),label+' must be a regular local file')
    require(path.stat().st_size<=limit,label+' exceeds the bounded local reader')
    with path.open('rb') as stream:raw=stream.read(limit+1)
    require(len(raw)<=limit,label+' changed or exceeds the bounded local reader')
    return raw


def _artifact(root,doc,relative):
    require(isinstance(relative,str) and relative in doc.get('artifacts',[]), 'Manual fallback needs registered failed retrieval evidence')
    path=safe_path(root,'processes/'+doc['id']+'/'+relative)
    raw=_read(path,MAX_JSON_DOCUMENT_BYTES,'Frozen retrieval evidence')
    require(sha(raw)==doc.get('artifact_hashes',{}).get(relative),'Frozen retrieval evidence changed before manual fallback')
    return decode(raw)


def _handled(root,doc,request,need,current):
    """Prove a prior manual acceptance from frozen originals and its journal."""
    paths=[path for path,provenance in doc.get('discovery_provenance',{}).items()
           if isinstance(provenance,dict) and provenance.get('origin')=='operator_export'
           and provenance.get('tool')=='local_manual_export'
           and provenance.get('retrieval_request_id')==request['request_id']
           and need['need_id'] in provenance.get('retrieval_need_ids',[])]
    if not paths:return False
    require(len(paths)==1,'Several prior manual originals bind the same failed need')
    path=paths[0];provenance=doc['discovery_provenance'][path]
    require(path.startswith('supplemental/') and provenance.get('failed_receipt_status')=='NOT_FOUND',
            'Prior manual source lacks its exact failed-read binding')
    digest=doc.get('source_files',{}).get(path)
    raw=_read(safe_path(root,'processes/'+doc['id']+'/input/sources/'+path),MAX_SOURCE_FILE_BYTES,'Frozen manual source')
    require(digest==sha(raw),'Previously accepted manual original changed')
    if current is not None:
        require(current.get('status')=='RECEIVED' and current.get('request_id')==request['request_id']
                and current.get('path')==path and current.get('source_hash')==digest
                and encode(current.get('need'))==encode({k:v for k,v in need.items() if k!='need_id'}),
                'Prior manual unresolved receipt differs from its accepted original')
    for relative in doc.get('artifacts',[]):
        if not re.fullmatch(r'analysis/discovery-[0-9a-f]{64}\.json',relative):continue
        journal=_artifact(root,doc,relative);entries=journal.get('files')
        require(isinstance(entries,list) and relative=='analysis/discovery-'+sha(encode(entries))+'.json',
                'Manual discovery journal content address changed')
        for entry in entries:
            if entry.get('path')==path and entry.get('source_hash')==digest:
                require(sha(entry.get('text',''))==digest and encode(entry.get('provenance'))==encode(provenance),
                        'Manual discovery journal differs from preserved source provenance')
                return True
    require(False,'Previously accepted manual source has no registered discovery journal')


def _binding(root,doc,failed_items,needs):
    record=doc.get('retrieval_request')
    require(isinstance(record,dict) and record.get('status')=='CONSUMED', 'Manual source fallback follows the current consumed failed retrieval only')
    request=_artifact(root,doc,record.get('artifact'));_verify_request(request)
    accepted=_artifact(root,doc,record.get('response_artifact'))
    require(isinstance(accepted,dict),'Manual fallback accepted response must be an object')
    require(request.get('process_id')==doc.get('id') and request['request_id']==record.get('id')
            and accepted.get('request_id')==record['id'] and accepted.get('status')=='VALIDATED', 'Manual source fallback does not match the current failed request')
    require(isinstance(needs,list) and encode(needs)==encode(request['needs']), 'Manual fallback needs differ from the frozen request')
    require(isinstance(failed_items,list) and encode(failed_items)==encode(accepted.get('missing_items'))
            and encode(failed_items)==encode(record.get('missing_items')), 'Manual fallback failures differ from the accepted response')
    items=accepted.get('items')
    require(isinstance(items,list) and all(isinstance(item,dict) and isinstance(item.get('need_id'),str)
            for item in items),'Manual fallback accepted item receipts are invalid')
    actual={item['need_id']:item for item in items}
    require(len(actual)==len(items)==len(request['needs']) and set(actual)=={n['need_id'] for n in needs}
            and all(item.get('need_id') in actual
            and encode(item)==encode(actual[item['need_id']]) for item in failed_items), 'Manual fallback has no matching failed item receipt')
    require(record['artifact']=='analysis/retrieval/'+record['id']+'/request.json'
            and record['response_artifact']=='analysis/retrieval/'+record['id']+'/accepted-'+accepted.get('response_hash','')+'.json',
            'Manual fallback evidence uses a different request folder')
    require(request.get('workspace')==str(root) and doc.get('guided_workspace')==str(root),
            'Manual fallback must stay in its frozen retrieval workspace')
    require(record.get('manual_request_source_generation')==request['source_generation']
            and record.get('manual_failure_source_generation')==_source_generation(doc),
            'Manual fallback source generation changed or lacks a pinned failed-read binding')
    unresolved=doc.get('retrieval_unresolved',{})
    require(isinstance(unresolved,dict),'Manual fallback has no current unresolved need mapping')
    by_id={n['need_id']:n for n in needs};handled=set()
    for failed in failed_items:
        need=by_id[failed['need_id']]
        fields={k:need.get(k) for k in ('kind','name','source','relationship')}
        fields.update({k:need[k] for k in ('library','source_library_hints') if k in need})
        current=unresolved.get(sha(encode(fields)))
        require(current is None or isinstance(current,dict),'Manual unresolved need receipt must be an object')
        if (current is None or current.get('status')=='RECEIVED') and _handled(root,doc,request,need,current):
            handled.add(need['need_id']);continue
        require(isinstance(current,dict) and current.get('request_id')==record['id']
                and current.get('status')==failed['status'] and current.get('reason')==failed['reason']
                and encode(current.get('need'))==encode({k:v for k,v in need.items() if k!='need_id'}),
                'Manual fallback does not match an exact current unresolved failed need')
    return request,accepted,handled


def _index(root,bucket):
    directory=safe_path(root,'supplemental/'+bucket)
    if not directory.exists():return []
    require(directory.is_dir(),'Manual source category must be a regular directory')
    pending=[directory];files=[];count=0
    while pending:
        folder=pending.pop()
        with os.scandir(folder) as children:
            for entry in children:
                count+=1;require(count<=MAX_SOURCE_ENTRIES,'Manual source traversal exceeds the bounded local limit')
                path=Path(entry.path);relative=path.relative_to(root).as_posix();safe_path(root,relative)
                require(not path_is_link(path),'Manual source folders must not contain symlinks or junctions')
                if entry.is_dir(follow_symlinks=False):pending.append(path)
                else:
                    require(entry.is_file(follow_symlinks=False),'Manual sources must be regular files')
                    files.append(path);require(len(files)<=MAX_SOURCE_FILES,'Manual source category exceeds the file-count bound')
    validate_source_paths([p.relative_to(root).as_posix() for p in files])
    return sorted(files)


def _scope(path,root,bucket,need,failed_library):
    library=need.get('library');hints=need.get('source_library_hints')
    if not library and not hints:return True
    relative=path.relative_to(root/'supplemental'/bucket)
    observed='.'.join(relative.parent.parts).upper()
    return observed==failed_library and (observed==library.upper() if library else observed in {hint.upper() for hint in hints})


def _failed_library(need,provenance):
    try:
        locator=zowe_dataset(provenance['locator'],member=True)
    except ValidationError:return None
    library,member=locator[:-1].split('(')
    if member!=need['name'].upper():return None
    if need.get('library') and library!=need['library'].upper():return None
    if need.get('source_library_hints') and library not in need['source_library_hints']:return None
    # USS is not a dataset(member) proof. If an actual target is present in the
    # source-read command, it must agree with the exact provenance locator.
    command=re.fullmatch(r'zowe(?:\.cmd|\.exe)? +(?:files|zos-files) +(?:view|download) +(ds|data-set)(?: +(.+))?',provenance['tool'])
    if not command:return None
    if re.search(r'--(?:insecure|user|password|token)\b|--(?:reject-unauthorized|rejectUnauthorized)[ =]+false\b|(?:^| )-k(?: |$)',provenance['tool'],re.I):return None
    if command[2]:
        target=command[2].split()[0].strip('\"\'')
        if target.upper()!=locator:return None
    return library


def _declared_identity(text,kind,name):
    if kind not in {'job','proc'}:return True
    word='JOB' if kind=='job' else 'PROC'
    declarations=[m[1].upper() for _,line in _lines(text)
                  if (m:=re.match(r'^//([A-Z@$#][A-Z0-9@$#_-]*)\s+'+word+r'\b',line,re.I))]
    return declarations==[name.upper()]


def find_entries(root,doc,failed_items,needs):
    """Return local original-byte intents and exact unresolved attempt reasons.

    Only a current NOT_FOUND read receipt enables its relevant manual folder.
    AMBIGUOUS/dynamic needs and every Db2 need remain on their approved route.
    This recognizes source presence, never conversion or mainframe parity.
    """
    result={'entries':[],'gaps':[],'attempts':[]}
    if type(doc.get('accelerator_contract_version')) is not int or doc['accelerator_contract_version']!=1:return result
    root=Path(root).absolute();request,_,handled=_binding(root,doc,failed_items,needs)
    by_id={need['need_id']:need for need in needs};indices={};total_bytes=0;total_lines=0;by_path={}
    knowledge=doc.get('mainframe_knowledge') or load_knowledge(root);validate_snapshot(knowledge)
    def gap(need_id,kind,reason,**facts):
        result['gaps'].append({'need_id':need_id,'kind':kind,'reason':reason,'status':'UNVERIFIED',**facts})
    for failed in failed_items:
        need_id=failed['need_id'];need=by_id[need_id];kind=need['kind']
        if need_id in handled:continue
        if failed['status']!='NOT_FOUND' or kind not in _BUCKETS or need.get('status') in {'dynamic_unknown','unresolved_parser'} or not _MEMBER.fullmatch(need['name']) or need['name'].startswith('UNRESOLVED_'):
            continue
        _provenance(failed.get('provenance'))
        try:_zowe_transport(failed['provenance'])
        except ValidationError:
            gap(need_id,'manual_remote_route_unverified','A matching failed read-only Zowe source receipt is required before using a manual export');continue
        if not _ABSENT.search(failed['reason']) or _DENIED.search(failed['reason']):
            gap(need_id,'manual_remote_absence_unverified','A positive member-not-found result is required; denied, unsafe, unavailable and configuration failures remain on their approved route');continue
        failed_library=_failed_library(need,failed['provenance'])
        if not failed_library:
            gap(need_id,'manual_remote_identity_unverified','The failed read locator must establish the exact requested member and library scope');continue
        attempt={'need_id':need_id,'request_id':request['request_id'],'categories':list(_BUCKETS[kind]),'status':'NOT_FOUND','candidate_count':0}
        result['attempts'].append(attempt);candidates=[];unscoped=0
        for bucket in _BUCKETS[kind]:
            if bucket not in indices:indices[bucket]=_index(root,bucket)
            matches=[p for p in indices[bucket] if p.stem.upper()==need['name'].upper()]
            for path in matches:
                if _scope(path,root,bucket,need,failed_library):candidates.append(path)
                else:unscoped+=1
        attempt['candidate_count']=len(candidates)
        if len(candidates)!=1:
            reason=('Several manual exports match the exact member; identify the authoritative original before continuing' if len(candidates)>1 else
                    'Matching manual members do not establish the requested library scope' if unscoped else
                    'The exact requested member is not present in its supplemental category')
            gap(need_id,'manual_source_ambiguous' if len(candidates)>1 else 'manual_library_scope' if unscoped else 'manual_source_not_found',reason,candidate_count=len(candidates));continue
        path=candidates[0];relative=path.relative_to(root).as_posix()
        raw=_read(path,MAX_SOURCE_FILE_BYTES,'Manual source');digest=sha(raw)
        try:text=raw.decode('utf-8')
        except UnicodeError:gap(need_id,'manual_source_encoding','Manual source needs its original CCSID decoded into complete UTF-8 text');continue
        if any(unicodedata.category(c)=='Cc' and c not in '\t\r\n\f' for c in text):
            gap(need_id,'manual_source_binary','Manual source contains binary controls; provide readable original source separately from data/load modules');continue
        classification=classify_files({relative:text},doc,knowledge)[relative]
        if classification['kind'] not in _KINDS[kind] or not _declared_identity(text,kind,need['name']):
            gap(need_id,'manual_source_classification','Member content, declared identity and requested source kind do not uniquely agree',path=relative,source_hash=digest,classification=classification['kind']);continue
        require(relative not in doc.get('source_files',{}) or doc['source_files'][relative]==digest,'Manual export conflicts with preserved original source')
        if relative in by_path:
            by_path[relative]['provenance']['retrieval_need_ids'].append(need_id);attempt['status']='FOUND';continue
        total_bytes+=len(raw);total_lines+=source_line_count(text)
        require(total_bytes<=MAX_SOURCE_BYTES and total_lines<=MAX_SOURCE_LINES,'Manual source batch exceeds local byte/line bounds')
        provenance={'origin':'operator_export','tool':'local_manual_export','locator':str(path),
                    'retrieved_at':datetime.now(timezone.utc).isoformat(), 'retrieval_request_id':request['request_id'],
                    'retrieval_need_ids':[need_id], 'manual_category':path.relative_to(root).parts[1],
                    'failed_receipt_status':'NOT_FOUND','conversion_support':'not_established'}
        if need.get('library') or need.get('source_library_hints'):
            library='.'.join(path.relative_to(root/'supplemental'/provenance['manual_category']).parent.parts).upper()
            provenance['dataset_member']=library+'('+need['name'].upper()+')'
            provenance['library_binding']='OPERATOR_EXPORT_DIRECTORY_NOT_MAINFRAME_OBSERVATION'
        entry={'path':relative,'text':text,'source_hash':digest,'provenance':provenance}
        by_path[relative]=entry;result['entries'].append(entry);attempt['status']='FOUND'
    validate_source_paths([entry['path'] for entry in result['entries']])
    return result
