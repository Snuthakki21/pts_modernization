"""Unverified estate declarations alongside observed, provenance-bound process scope.

Declarations never create source assets or conversion credit. Cumulative credit
deduplicates immutable versions and retains process memberships separately.
"""
from copy import deepcopy
from pathlib import Path
import re
from .domain import decode, encode, require, safe_path, sha

INVENTORY_TEMPLATE = Path(__file__).resolve().parent.parent/'examples/inventory-baseline.json'
INVENTORY_RELATIVE = 'knowledge/inventory-baseline.json'
CATEGORY_KEYS = ('batch_cobol','jcl_jobs','jcl_procs','copybooks','cics_screens','db2_tables','ca7_schedules','mq')
STATUS = 'USER_REPORTED_UNVERIFIED'
KINDS = {'cobol_program':'batch_cobol','jcl_job':'jcl_jobs','jcl_proc':'jcl_procs',
         'copybook':'copybooks','bms_map':'cics_screens','db2_table':'db2_tables',
         'ca7_schedule':'ca7_schedules','mq_object':'mq'}


def validate_inventory(document):
    require(isinstance(document,dict) and set(document)=={'schema_version','application','status','provenance','declared_total','categories','application_locations'},'Inventory baseline fields are missing or unsupported')
    require(type(document['schema_version']) is int and document['schema_version']==1,'Unsupported inventory baseline schema')
    require(document['status']==STATUS,'Declared inventory must remain user-reported and unverified')
    for key in ('application','provenance'):
        require(isinstance(document[key],str) and 0<len(document[key])<=4000,'Invalid inventory '+key)
    require(type(document['declared_total']) is int and document['declared_total']>=0,'Inventory declared total must be a nonnegative integer')
    categories=document['categories']
    require(isinstance(categories,list) and len(categories)==8,'Inventory must contain the eight declared categories')
    keys=[]
    for item in categories:
        require(isinstance(item,dict) and set(item)=={'key','label','count'},'Invalid inventory category fields')
        require(item['key'] in CATEGORY_KEYS,'Unknown inventory category')
        require(isinstance(item['label'],str) and 0<len(item['label'])<=160,'Invalid inventory category label')
        require(type(item['count']) is int and item['count']>=0,'Inventory category count must be a nonnegative integer')
        keys.append(item['key'])
    require(set(keys)==set(CATEGORY_KEYS) and len(set(keys))==8,'Inventory categories must occur exactly once')
    locations=document['application_locations']
    require(isinstance(locations,list) and len(locations)<=100,'Invalid application staging locations')
    names=[]
    for location in locations:
        require(isinstance(location,dict) and set(location)=={'name','role','status'},'Invalid application staging location')
        require(location['status']==STATUS,'Application staging availability is unverified context')
        for key in ('name','role'):require(isinstance(location[key],str) and 0<len(location[key])<=160,'Invalid application staging '+key)
        names.append(location['name'])
    require(len(names)==len(set(names)),'Duplicate application staging locations')
    return document


def default_inventory():
    return validate_inventory(decode(INVENTORY_TEMPLATE.read_bytes(),limit=64*1024))


def load_inventory(workspace):
    path=safe_path(workspace,INVENTORY_RELATIVE)
    if not path.exists():return default_inventory()
    require(path.is_file() and path.stat().st_size<=64*1024,'Inventory baseline must be a bounded JSON file')
    with path.open('rb') as source:raw=source.read(64*1024+1)
    require(len(raw)<=64*1024,'Inventory baseline exceeds its size limit')
    return validate_inventory(decode(raw,limit=64*1024))


def snapshot_inventory(workspace):
    document=deepcopy(load_inventory(workspace))
    return {'schema_version':1,'status':STATUS,'source':INVENTORY_RELATIVE,
            'sha256':sha(encode(document)),'document':document}


def validate_snapshot(snapshot):
    require(isinstance(snapshot,dict) and set(snapshot)=={'schema_version','status','source','sha256','document'},'Invalid frozen inventory baseline')
    require(type(snapshot['schema_version']) is int and snapshot['schema_version']==1 and snapshot['status']==STATUS and snapshot['source']==INVENTORY_RELATIVE,'Invalid frozen inventory baseline metadata')
    validate_inventory(snapshot['document'])
    require(snapshot['sha256']==sha(encode(snapshot['document'])),'Frozen inventory baseline hash changed')
    return snapshot


def _source_entities(process):
    """Use exact logical names when present; files are never assumed to be entities."""
    analysis=process.get('analysis') or {};classifications=analysis.get('classifications',{})
    entities={key:{} for key in CATEGORY_KEYS}
    observed={key:False for key in CATEGORY_KEYS}
    for asset in analysis.get('assets',[]):
        if not asset.get('selected',True):continue
        kind=classifications.get(asset['path'],{}).get('kind',asset.get('kind'))
        path=asset['path'];digest=asset.get('source_hash','');text=asset.get('source_text','')
        for table in asset.get('tables',[]):
            observed['db2_tables']=True;name=table.upper();version=sha('db2_tables:'+name+':'+digest)
            entities['db2_tables'][version]={'id':version,'logical_id':'db2_tables:'+name,'name':name,'path':path,'source_hash':digest,'basis':'STATIC_SOURCE_REFERENCE_NOT_VERIFIED_CATALOG_TABLE'}
        category=KINDS.get(kind)
        if category is None:continue
        names=[]
        if kind=='cobol_program':
            # Selected batch manifest membership provides the batch-role evidence.
            batch_names={step['program'].upper() for job in process.get('jobs',[]) for step in job.get('steps',[])}
            if asset.get('name','').upper() in batch_names:names=[asset['name'].upper()]
            elif any(edge.get('kind')=='calls' and edge.get('to')==asset.get('name') for edge in analysis.get('graph',[])):names=[asset['name'].upper()]
        elif kind in ('jcl_job','jcl_proc'):
            token='JOB' if kind=='jcl_job' else 'PROC'
            names=re.findall(r'^//([A-Z@$#][A-Z0-9@$#]*)\s+'+token+r'\b',text,re.I|re.M)
        elif kind=='copybook':names=[asset.get('name',path)]
        elif kind=='bms_map':names=asset.get('screens',[])
        if names:observed[category]=True
        for name in names:
            name=name.upper();version=sha(category+':'+name+':'+digest)
            entities[category][version]={'id':version,'logical_id':category+':'+name,'name':name,'path':path,'source_hash':digest}
    return entities,observed


def _lineage_entities(process):
    entities,observed=_source_entities(process)
    lineage=process.get('lineage') or {}
    executable_links={'selects_job','manifest_step','contains_step','executes','invokes_proc','calls','includes','defined_in','declares'}
    outgoing={}
    for edge in lineage.get('edges',[]):
        if edge.get('kind') in executable_links and edge.get('resolution')=='resolved':outgoing.setdefault(edge['source'],[]).append(edge['target'])
    batch_reachable={node['id'] for node in lineage.get('nodes',[]) if node.get('kind')=='manifest_job' and node.get('selected')}
    pending=list(batch_reachable)
    while pending:
        for target in outgoing.get(pending.pop(),[]):
            if target not in batch_reachable:batch_reachable.add(target);pending.append(target)
    hashes={asset['path']:asset.get('source_hash') for asset in (process.get('analysis') or {}).get('assets',[])}
    node_kinds={'program':'batch_cobol','job':'jcl_jobs','proc':'jcl_procs','copybook':'copybooks',
                'bms_map':'cics_screens','db2_table':'db2_tables','ca7_definition':'ca7_schedules','mq_interface':'mq'}
    for node in lineage.get('nodes',[]):
        category=node_kinds.get(node.get('kind'))
        if category is None or node.get('selected') is False or node.get('resolution')!='local_source':continue
        if category=='batch_cobol' and node.get('id') not in batch_reachable:continue
        path=node.get('path');digest=hashes.get(path)
        if not digest:continue
        name=str(node.get('name','')).upper()
        if not name:continue
        observed[category]=True;version=sha(category+':'+name+':'+digest)
        entities[category][version]={'id':version,'logical_id':category+':'+name,'name':name,'path':path,'source_hash':digest}
    for membership in lineage.get('process_assets',[]):
        if membership.get('selected') is False or membership.get('scope_disposition')=='out_of_scope':continue
        kind=membership.get('source_kind',membership.get('kind'));category=membership.get('category') or KINDS.get(kind)
        if category not in entities:continue
        # Only source-backed logical membership rows qualify. Unknown/missing
        # source nodes and staging locations cannot inflate observed assets.
        digest=membership.get('source_hash',membership.get('source_version'))
        if not isinstance(digest,str) or not re.fullmatch(r'[a-f0-9]{64}',digest):continue
        logical=membership.get('logical_id') or membership.get('name')
        if not logical:continue
        if category=='batch_cobol' and membership.get('role') in ('online','cics'):continue
        observed[category]=True;version=sha(category+':'+str(logical)+':'+digest)
        entities[category][version]={'id':version,'logical_id':category+':'+str(logical),'name':membership.get('name',str(logical)),
                                    'path':membership.get('path',membership.get('source_path')),'source_hash':digest}
    return entities,observed


def _verified_versions(entities,coverage):
    verified={key:set() for key in CATEGORY_KEYS}
    if not coverage or coverage.get('summary',{}).get('integrity_errors'):return verified
    file_status={}
    for row in coverage.get('rows',[]):
        status=file_status.setdefault(row['source_path'],{'applicable':0,'complete':True})
        if row['disposition'] in ('out_of_scope','non_executable'):continue
        status['applicable']+=1
        status['complete'] &= row['disposition'] in ('mapped_verified','platform_replaced_verified')
    # No CICS/Db2/CA7/MQ semantic adapters exist yet. Only fully evidenced
    # program, layout and bounded JCL dispatch versions can receive POC credit.
    for category in ('batch_cobol','jcl_jobs','copybooks'):
        for version,entity in entities[category].items():
            status=file_status.get(entity.get('path'),{})
            if status.get('applicable',0)>0 and status.get('complete'):verified[category].add(version)
    return verified


def report_inventory(process, portfolio_documents=(), coverage=None):
    snapshot=process.get('inventory_baseline')
    if snapshot is not None:baseline=validate_snapshot(snapshot)['document'];baseline_hash=snapshot['sha256'];frozen=True
    else:baseline=default_inventory();baseline_hash=sha(encode(baseline));frozen=False
    entities,observed=_lineage_entities(process);verified=_verified_versions(entities,coverage)
    cumulative={key:set() for key in CATEGORY_KEYS};versions={key:set() for key in CATEGORY_KEYS};logical={key:set() for key in CATEGORY_KEYS};memberships={key:0 for key in CATEGORY_KEYS}
    documents={doc['id']:doc for doc in portfolio_documents if not doc.get('demo')}
    if not process.get('demo'):documents[process['id']]=process
    locals_by_id={doc['id']:_lineage_entities(doc)[0] for doc in documents.values()}
    logical_by_version={key:{} for key in CATEGORY_KEYS}
    for doc in documents.values():
        local=locals_by_id[doc['id']]
        accepted=(doc.get('accepted_inventory') or {}).get('verified_version_ids',{})
        for category in CATEGORY_KEYS:
            versions[category].update(local[category]);logical[category].update(entity['logical_id'] for entity in local[category].values())
            logical_by_version[category].update({version:entity['logical_id'] for version,entity in local[category].items()})
            memberships[category]+=len(local[category])
            # An accepted report is the only source of historical conversion credit.
            if doc.get('report_verified'):
                cumulative[category].update(value for value in accepted.get(category,[]) if value in local[category])
        if doc['id']==process['id']:
            for category in CATEGORY_KEYS:cumulative[category].update(verified[category])
    counts={item['key']:item for item in baseline['categories']};rows=[]
    lineage_counts={row.get('kind'):row for row in (process.get('lineage') or {}).get('process_assets',[])}
    for category in CATEGORY_KEYS:
        declaration=counts[category];observed_count=len({entity['logical_id'] for entity in entities[category].values()}) if observed[category] else None
        reported=lineage_counts.get(category,{})
        if category!='batch_cobol' and type(reported.get('observed_count')) is int and (reported['observed_count']>0 or reported.get('status')=='OBSERVED_STATIC_CLOSURE'):
            observed_count=reported['observed_count']
        converted_logical={entities[category][version]['logical_id'] for version in verified[category]}
        cumulative_logical={logical_by_version[category][version] for version in cumulative[category] if version in logical_by_version[category]}
        rows.append({'key':category,'label':declaration['label'],'baseline_count':declaration['count'],
                     'baseline_status':STATUS,'process_observed_count':observed_count,'process_unique_versions':len(entities[category]) if observed[category] else None,
                     'process_scope_status':reported.get('status','UNVERIFIED'),'process_unresolved_gaps':reported.get('gaps'),
                     'process_converted_count':len(converted_logical),'cumulative_converted_count':len(cumulative_logical),
                     'remaining_vs_baseline':declaration['count']-len(cumulative_logical),'portfolio_unique_assets':len(logical[category]),
                     'portfolio_unique_versions':len(versions[category]),'portfolio_memberships':memberships[category],
                     'observed_basis':'Source-backed process logical entities; DB2 entries are static references and MQ entries are referenced interfaces; unknown is not zero',
                     'conversion_basis':'Verified bounded local POC source coverage; no native estate parity credit'})
    category_total=sum(item['count'] for item in baseline['categories'])
    return {'schema_version':1,'baseline_status':STATUS,'baseline_hash':baseline_hash,'baseline_frozen':frozen,
            'declared_total':baseline['declared_total'],'category_total':category_total,'unreconciled_count':baseline['declared_total']-category_total,
            'reconciliation':'Declared total and category sum are preserved separately; unreconciled items have no invented category or conversion credit',
            'rows':rows,'verified_version_ids':{key:sorted(value) for key,value in verified.items()},
            'application_locations':deepcopy(baseline['application_locations']),
            'availability_basis':'WEDELX and TranRepository are application staging/availability locations; they provide no source-program or conversion credit',
            'scope_boundary':'CICS/BMS screen definitions are separate from CICS transactions. Observed DB2 counts are distinct source references; observed MQ counts are referenced interfaces, not verified catalog objects. Workbench UI and control APIs are excluded. Demonstrations are excluded from cumulative progress.'}
