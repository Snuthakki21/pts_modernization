"""Coordinator-bound local database artifacts; no live Db2 or second engine."""
from copy import deepcopy
from pathlib import Path
import re
import sqlite3
import tempfile

from .database import (schema_candidate,create_application_database,sqlite_schema,sqlite_rows,
                       validate_snapshot,sqlite_snapshot,compare_snapshots,SNAPSHOT_FIELDS)
from .domain import encode,decode,require,safe_path,sha,write_new
from .layout import output_path,require_layout

BOUNDARY=('Schema-only SQLite storage candidate from approved frozen Db2 MCP metadata. '
          'Business SQL, native Db2 transactions, collation, authorization and whole-program parity remain unverified.')


def _sources(c,doc):
    files=c.sources(doc)
    selected=set(doc.get('lineage',{}).get('scope',{}).get('selected_files',[]))
    excluded=(doc.get('analysis') or {}).get('requirements',{}).get('excluded_units',[])
    omitted={unit['source_path'] for unit in excluded}
    schemas=[]
    from .db2_catalog import table_description
    for path,text in files.items():
        provenance=doc.get('discovery_provenance',{}).get(path)
        catalog=table_description(text,provenance)
        if not (Path(path).suffix.lower() in ('.sql','.ddl') or re.match(r'\s*CREATE\s+TABLE\b',text,re.I) or catalog):continue
        candidate=schema_candidate(text,provenance,source_path=path)
        approved=(isinstance(provenance,dict) and provenance.get('origin')=='configured_mcp' and
                  provenance.get('tool')=='db2_describe_table' and
                  {table['name'] for table in candidate['tables']}=={provenance.get('locator')})
        extra=[]
        if not approved:extra.append({'kind':'database_provenance_gap','source_path':path,'source_hash':doc['source_files'][path],
              'message':'Retrieve this exact table schema/catalog through approved Copilot Db2 MCP; a manual file or self-declared JSON origin is insufficient.'})
        if path not in selected:extra.append({'kind':'database_scope_gap','source_path':path,'source_hash':doc['source_files'][path],
              'message':'Retained schema is outside the job-led discovered process scope; it is not built automatically.'})
        if path in omitted:extra.append({'kind':'database_requirements_exclusion','source_path':path,'source_hash':doc['source_files'][path],
              'message':'Not converted because selected No in requirements. Any No touching this source file excludes its complete schema candidate.'})
        schemas.append({'source_path':path,'source_hash':doc['source_files'][path],'can_build':candidate['can_build'] and not extra,
                        'gaps':candidate['gaps']+extra,'candidate':candidate})
    return schemas


def _record(c,doc,record):
    receipt=decode(c.artifact(doc['id'],record['receipt']).read_bytes())
    require(receipt['id']==record['id'] and receipt['artifact']==record['artifact'] and receipt['sha256']==record['sha256'],
            'Database index differs from immutable receipt')
    path=c.artifact(doc['id'],record['artifact'])
    require(sha(path.read_bytes())==record['sha256'],'Database differs from receipt')
    return {**receipt,'tables':sqlite_schema(path,record['sha256'])['tables'],'receipt':record['receipt']}


def database_view(c,pid):
    with c.lock:
        doc=c.ledger.get(pid);schemas=_sources(c,doc)
        databases=[_record(c,doc,record) for record in doc.get('application_databases',[])]
        comparisons=[]
        for record in doc.get('database_comparisons',[]):
            result=decode(c.artifact(pid,record['artifact']).read_bytes())
            comparisons.append({'id':record['id'],'artifact':record['artifact'],'sha256':doc['artifact_hashes'][record['artifact']],
                                'status':result['status'],'summary':result['summary'],'gaps':result['gaps']})
        snapshots=[]
        for name,text in c.sources(doc).items():
            provenance=doc.get('discovery_provenance',{}).get(name,{})
            if provenance.get('content_kind')!='DB2_RECORD_SNAPSHOT':continue
            observed=validate_snapshot(text,provenance)
            snapshots.append(_snapshot_view(observed,'input/sources/'+name))
        for record in doc.get('database_snapshots',[]):
            observed=validate_snapshot(c.artifact(pid,record['artifact']).read_text(encoding='utf-8'))
            require(observed['source_hash']==record['sha256'],'Snapshot index differs from frozen bytes')
            snapshots.append({**_snapshot_view(observed,record['artifact']),'database_id':record['database_id']})
        return {'process_id':pid,'databases':databases,'snapshots':snapshots,'schemas':[{k:v for k,v in s.items() if k!='candidate'} for s in schemas],
                'comparisons':comparisons,'native_database_verified':False,'boundary':BOUNDARY,
                'can_prepare':not doc['packet_issued'] and pid not in c.active and doc['status']=='WAITING_COPILOT' and bool(doc.get('requirements')) and
                              bool(doc.get('lineage',{}).get('closure',{}).get('complete')) and not doc.get('retrieval_unresolved') and any(s['can_build'] for s in schemas)}


def prepare_database(c,pid,body=None):
    """One explicit pre-SME checkpoint publishes only generated empty schemas."""
    body={} if body is None else body;require(isinstance(body,dict) and not body,'Schema preparation accepts no arbitrary SQL/rows')
    with c.lock:
        require_layout(c.root);doc=c.ledger.get(pid)
        require(pid not in c.active and not doc['packet_issued'] and doc['status']=='WAITING_COPILOT',
                'Database preparation requires the idle local-analysis checkpoint before the single SME packet')
        require(doc.get('requirements'),'Save explicit requirements before database preparation')
        require(doc.get('lineage',{}).get('closure',{}).get('complete') and not doc.get('retrieval_unresolved'),
                'Resolve job-led discovery before database preparation')
        c.target_checkpoint(doc);entries=_sources(c,doc);selected=[entry['candidate'] for entry in entries if entry['can_build']]
        require(selected,'No approved selected source-supported SQLite schema candidate; inspect the exact schema gaps')
        binding={'schema_version':1,'process_id':pid,'manifest_hash':doc['manifest_hash'],
                 'requirements_artifact':doc['requirements_artifact'],'requirements_hash':doc['artifact_hashes'][doc['requirements_artifact']],
                 'source_hashes':{s['source_path']:s['source_hash'] for s in selected},'sqlite_runtime':sqlite3.sqlite_version,
                 'profile':'DB2_STORAGE_SCHEMA_V1','schema_only':True}
        ident=sha(encode(binding));relative='target/database/'+ident+'/application.sqlite';receipt_relative='target/database/'+ident+'/receipt.json'
        existing=next((r for r in doc.get('application_databases',[]) if r['id']==ident),None)
        if existing:
            _record(c,doc,existing);return database_view(c,pid)
        scratch=safe_path(c.root,'.implementation/tmp');scratch.mkdir(parents=True,exist_ok=True)
        with tempfile.TemporaryDirectory(prefix='database-',dir=scratch) as temporary:
            built=create_application_database(Path(temporary)/'application.sqlite',selected,checkpoint=lambda:c.target_checkpoint(doc))
            raw=Path(built['path']).read_bytes()
        # Materialize bytes before publication. A lost response can recover only
        # the same deterministic intent and exact generated bytes, never repin an
        # arbitrary unregistered database already present at this path.
        receipt={**binding,'id':ident,'artifact':relative,'sha256':sha(raw),'tables':built['tables'],
                 'gaps':[gap for entry in entries for gap in entry['gaps']],'boundary':BOUNDARY,'native_database_verified':False}
        for name,payload in ((relative,raw),(receipt_relative,encode(receipt))):
            c.target_checkpoint(doc);path=output_path(c.root,pid,name)
            if path.exists():require(path.read_bytes()==payload,'Preserved database artifact differs from deterministic intent')
            else:write_new(path,payload)
            c.register(doc,name)
        doc.setdefault('application_databases',[]).append({'id':ident,'artifact':relative,'sha256':receipt['sha256'],'receipt':receipt_relative})
        c.ledger.save_event(doc,None,'database','Schema-only local application database prepared; native/business SQL remains unverified',
                            {'id':ident,'artifact':relative,'sources':len(selected)})
        return database_view(c,pid)


def database_rows(c,pid,ident,table,after=0,limit=100,filters=None):
    with c.lock:
        doc=c.ledger.get(pid);c.sources(doc)
        record=next((record for record in doc.get('application_databases',[]) if record['id']==ident),None)
        require(record is not None,'Database ID is not registered to this process');_record(c,doc,record)
        result=sqlite_rows(c.artifact(pid,record['artifact']),record['sha256'],table,after,limit,filters,checkpoint=lambda:c.target_checkpoint(doc))
        return {**result,'process_id':pid,'database_id':ident,'artifact':record['artifact']}


def _frozen_snapshot(c,doc,relative):
    require(isinstance(relative,str),'Comparison requires exact same-process frozen snapshot references')
    if relative.startswith('input/sources/'):
        name=relative[len('input/sources/'):];files=c.sources(doc);require(name in files,'Snapshot source is not frozen for this process')
        provenance=doc.get('discovery_provenance',{}).get(name)
        require(provenance is not None,'Db2 snapshot requires accepted request-bound Copilot MCP retrieval provenance')
        result=validate_snapshot(files[name],provenance)
        require(result['kind']=='DB2_RECORD_SNAPSHOT','Source comparison input must be an approved Db2 record export')
    else:
        require(relative.startswith('target/'),'Local snapshots belong under target and must be registered')
        result=validate_snapshot(c.artifact(doc['id'],relative).read_text(encoding='utf-8'))
        require(result['kind']=='SQLITE_RECORD_SNAPSHOT','Target comparison input must be a local SQLite snapshot')
    return result


def _snapshot_view(snapshot,relative):
    return {'artifact':relative,'sha256':snapshot['source_hash'],'kind':snapshot['kind'],'phase':snapshot['phase'],
            'table':snapshot['schema']+'.'+snapshot['table'],'run_id':snapshot['run_id'],'input_hashes':snapshot['input_hashes'],
            'environment':snapshot['environment'],'rows':len(snapshot['rows']),'column_names':snapshot['column_names'],
            'key_columns':snapshot['key_columns'],'scope':{'kind':snapshot['scope']['kind'],'complete':snapshot['scope']['complete'],'key_count':len(snapshot['scope']['keys'])},
            'consistency':snapshot['consistency']['status'],'native_database_verified':False}


def database_snapshot(c,pid,body):
    require(isinstance(body,dict) and set(body)=={'database_id','source_snapshot','context','phase'},
            'Snapshot requires registered database ID, frozen source snapshot, exact context and phase')
    with c.lock:
        doc=c.ledger.get(pid);c.sources(doc)
        require(pid not in c.active and doc['status'] in ('WAITING_COPILOT','WAITING_SME','COMPLETED','COMPLETED_WITH_BLOCKERS'),
                'Capture local database rows only at an idle Coordinator checkpoint')
        source=_frozen_snapshot(c,doc,body['source_snapshot']);require(source['kind']=='DB2_RECORD_SNAPSHOT','Capture requires the approved Db2 source snapshot')
        context=body['context'];required={'db2_run_id','sqlite_run_id','input_hashes','db2_environment','sqlite_environment'}
        require(isinstance(context,dict) and set(context)==required and body['phase']==source['phase'],
                'Snapshot phase/context must match exact source observation')
        require(context['db2_run_id']==source['run_id'] and context['input_hashes']==source['input_hashes'] and context['db2_environment']==source['environment'],
                'Snapshot context differs from frozen source run/input/environment')
        database=next((r for r in doc.get('application_databases',[]) if r['id']==body['database_id']),None)
        require(database is not None,'Database is not registered to this process');_record(c,doc,database)
        intent={**body,'source_hash':source['source_hash'],'database_hash':database['sha256']}
        ident=sha(encode(intent));relative='target/database/'+database['id']+'/snapshots/'+ident+'.json'
        prior=next((r for r in doc.get('database_snapshots',[]) if r['id']==ident),None)
        if prior:
            frozen=validate_snapshot(c.artifact(pid,prior['artifact']).read_text(encoding='utf-8'))
            require(frozen['source_hash']==prior['sha256'],'Snapshot changed from its receipt')
            return {'process_id':pid,'database_id':database['id'],**_snapshot_view(frozen,relative)}
        observed=sqlite_snapshot(c.artifact(pid,database['artifact']),database['sha256'],source['schema']+'.'+source['table'],source,
                  context['sqlite_run_id'],context['input_hashes'],context['sqlite_environment'],body['phase'],checkpoint=lambda:c.target_checkpoint(doc))
        path=output_path(c.root,pid,relative)
        require(not path.exists(),'Unregistered preserved snapshot exists; inspect it without overwriting or silently repinning evidence')
        write_new(path,observed['source_text'].encode());c.register(doc,relative)
        doc.setdefault('database_snapshots',[]).append({'id':ident,'database_id':database['id'],'artifact':relative,'sha256':observed['source_hash'],
                                                      'source_artifact':body['source_snapshot'],'source_hash':source['source_hash']})
        c.ledger.save_event(doc,None,'database','Actual registered local SQLite rows frozen; this is no application run/effect or native parity claim',
                            {'artifact':relative,'phase':body['phase'],'database_id':database['id']})
        return {'process_id':pid,'database_id':database['id'],**_snapshot_view(observed,relative)}


def database_comparison(c,pid,body):
    """Freeze an exact keyed discrepancy report; current Db2 UR reads cannot pass parity."""
    required={'db2_before','db2_after','sqlite_before','sqlite_after','context'}
    require(isinstance(body,dict) and set(body)==required,'Comparison requires four frozen snapshot refs and exact run context')
    with c.lock:
        doc=c.ledger.get(pid);c.sources(doc)
        require(pid not in c.active and doc['status'] in ('WAITING_COPILOT','WAITING_SME','COMPLETED','COMPLETED_WITH_BLOCKERS'),
                'Freeze comparison only at an idle Coordinator checkpoint')
        snapshots=[_frozen_snapshot(c,doc,body[key]) for key in ('db2_before','db2_after','sqlite_before','sqlite_after')]
        def verified(snapshot):
            # No approved consistent Db2 export contract exists today. Generic
            # registered references are never treated as transaction/UR proof.
            if snapshot['kind']=='DB2_RECORD_SNAPSHOT':return False
            refs=snapshot['consistency']['evidence']
            if len(refs)!=1:return False
            ref=refs[0];path=Path(ref['path'])
            relative=path.relative_to(c.process_root(pid)).as_posix() if path.is_absolute() and path.is_relative_to(c.process_root(pid)) else ref['path']
            if relative not in doc['artifacts'] or not relative.startswith('target/') or not relative.endswith('.sqlite'):return False
            registered=c.artifact(pid,relative)
            if doc['artifact_hashes'][relative]!=ref['sha256']:return False
            actual=sqlite_snapshot(registered,ref['sha256'],snapshot['schema']+'.'+snapshot['table'],snapshot,
                   snapshot['run_id'],snapshot['input_hashes'],snapshot['environment'],snapshot['phase'],checkpoint=lambda:c.target_checkpoint(doc))
            def keyed(rows):return sorted((encode([r[k] for k in snapshot['key_columns']]),encode(r)) for r in rows)
            return keyed(actual['rows'])==keyed(snapshot['rows'])
        result=compare_snapshots(*snapshots,body['context'],checkpoint=lambda:c.target_checkpoint(doc),evidence_verifier=verified)
        result['references']={key:body[key] for key in required if key!='context'}
        result['limitations']=['State deltas describe observed before/after rows, not SQL execution traces.',
              'Db2 read consistency is unverified for current approved WITH UR exports; equality is withheld.',
              'Historical baseline rows are fully retained as individual gaps. No total-count parity or business/native SQL credit is granted.']
        ident=sha(encode(result));relative='analysis/database-comparison/'+ident+'.json';path=output_path(c.root,pid,relative)
        if path.exists():require(path.read_bytes()==encode(result),'Frozen database comparison changed')
        else:write_new(path,encode(result))
        c.register(doc,relative)
        record={'id':ident,'artifact':relative}
        if record not in doc.setdefault('database_comparisons',[]):
            doc['database_comparisons'].append(record)
            c.ledger.save_event(doc,None,'database','Keyed database discrepancy report frozen; native parity remains unverified',record)
        return {'process_id':pid,'id':ident,'artifact':relative,'sha256':doc['artifact_hashes'][relative],**result}
