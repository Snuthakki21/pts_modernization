"""Explicit read-only application file-share bindings; no guessed dataset paths."""
from .domain import path_is_link
from pathlib import Path
from .domain import decode, require, safe_path, sha

def input_locations(workspace):
    config=safe_path(workspace,'knowledge/input-locations.json')
    raw=b''
    if config.exists():
        require(config.is_file() and config.stat().st_size<=65536,'Input location configuration must be a bounded JSON file')
        with config.open('rb') as handle:raw=handle.read(65537)
        document=decode(raw,65536)
    else:document={'schema_version':1,'locations':[]}

    require(isinstance(document,dict) and set(document)=={'schema_version','locations'} and document['schema_version']==1,'Invalid input location configuration')
    locations=document['locations'];require(isinstance(locations,list) and len(locations)<=2,'Configure WEBELX and TranRepository explicitly')
    # Form paths supply explicit mounted-folder bindings for future processes;
    # retain every existing exact logical-id/file binding without rewriting it.
    from .setup import load_workstation_settings
    settings=load_workstation_settings(workspace)
    primary='WEDLX' if any(isinstance(item,dict) and item.get('name')=='WEDLX' for item in locations) else 'WEBELX'
    overrides={name:settings[field] for name,field in ((primary,'wedlx_folder'),('TranRepository','tran_repository_folder')) if settings[field]}
    locations=[dict(item) if isinstance(item,dict) else item for item in locations]
    for name,path in overrides.items():
        matches=[item for item in locations if isinstance(item,dict) and item.get('name')==name]
        if matches:
            for item in matches:item['path']=path
        else:locations.append({'name':name,'path':path,'bindings':[]})
    require(len(locations)<=2,'Configure WEBELX and TranRepository explicitly')
    require(not ({'WEBELX','WEDLX'} <= {item.get('name') for item in locations if isinstance(item,dict)}),
            'WEBELX and its historical WEDLX alias cannot name separate locations')
    result={}
    for item in locations:
        require(isinstance(item,dict) and set(item)=={'name','path','bindings'},'Location requires name, path and bindings')
        name=item['name'];require(name in ('WEBELX','WEDLX','TranRepository') and name not in result,'Unknown or duplicate input location')
        require(isinstance(item['path'],str) and item['path'],'Provide the actual mounted folder path')
        folder=Path(item['path']).absolute()
        require(not any(path_is_link(p) for p in (folder,*folder.parents)),'Input locations must not use symlinks')
        bindings=item['bindings'];require(isinstance(bindings,list) and len(bindings)<=10000,'Input bindings must be bounded')
        facts=[];ids=set()
        for binding in bindings:
            require(isinstance(binding,dict) and set(binding)=={'logical_id','file'},'Binding requires exact logical_id and relative file')
            logical=binding['logical_id'];require(isinstance(logical,str) and 0<len(logical)<=253 and logical not in ids,'Invalid or duplicate dataset identity')
            ids.add(logical);path=safe_path(folder,binding['file'])
            require(not path.exists() or path.is_file(),'Input binding must reference a regular file')
            facts.append({'logical_id':logical,'relative_path':binding['file'],'available':path.is_file(),'size_bytes':path.stat().st_size if path.is_file() else None,'readiness':'Unknown','basis':'READ_ONLY_FILE_METADATA_NO_BUSINESS_READINESS_CLAIM'})
        result[name]={'path':str(folder),'location_type':'local_or_mounted_file_share','availability':'AVAILABLE' if folder.is_dir() else 'UNAVAILABLE','readiness':'Unknown','evidence':[{'config_hash':sha(raw) if raw else None,'workstation_path_override':name in overrides,'folder_observed':folder.is_dir(),'bindings':facts}]}
    return result
