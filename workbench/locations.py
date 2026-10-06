"""Explicit read-only application file-share bindings; no guessed dataset paths."""
from pathlib import Path
from .domain import decode, require, safe_path, sha

def input_locations(workspace):
    config=safe_path(workspace,'knowledge/input-locations.json')
    if not config.exists():return {}
    require(config.is_file() and config.stat().st_size<=65536,'Input location configuration must be a bounded JSON file')
    with config.open('rb') as handle:raw=handle.read(65537)
    document=decode(raw,65536)
    require(isinstance(document,dict) and set(document)=={'schema_version','locations'} and document['schema_version']==1,'Invalid input location configuration')
    locations=document['locations'];require(isinstance(locations,list) and len(locations)<=2,'Configure WEDLX and TranRepository explicitly')
    result={}
    for item in locations:
        require(isinstance(item,dict) and set(item)=={'name','path','bindings'},'Location requires name, path and bindings')
        name=item['name'];require(name in ('WEDLX','TranRepository') and name not in result,'Unknown or duplicate input location')
        require(isinstance(item['path'],str) and item['path'],'Provide the actual mounted folder path')
        folder=Path(item['path']).absolute()
        require(not any(p.is_symlink() for p in (folder,*folder.parents)),'Input locations must not use symlinks')
        bindings=item['bindings'];require(isinstance(bindings,list) and len(bindings)<=10000,'Input bindings must be bounded')
        facts=[];ids=set()
        for binding in bindings:
            require(isinstance(binding,dict) and set(binding)=={'logical_id','file'},'Binding requires exact logical_id and relative file')
            logical=binding['logical_id'];require(isinstance(logical,str) and 0<len(logical)<=253 and logical not in ids,'Invalid or duplicate dataset identity')
            ids.add(logical);path=safe_path(folder,binding['file'])
            require(not path.exists() or path.is_file(),'Input binding must reference a regular file')
            facts.append({'logical_id':logical,'relative_path':binding['file'],'available':path.is_file(),'size_bytes':path.stat().st_size if path.is_file() else None,'readiness':'Unknown','basis':'READ_ONLY_FILE_METADATA_NO_BUSINESS_READINESS_CLAIM'})
        result[name]={'path':str(folder),'location_type':'local_or_mounted_file_share','availability':'AVAILABLE' if folder.is_dir() else 'UNAVAILABLE','readiness':'Unknown','evidence':[{'config_hash':sha(raw),'folder_observed':folder.is_dir(),'bindings':facts}]}
    return result
