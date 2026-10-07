"""Prepare nonsecret project Zowe profiles; credentials remain interactive in Zowe."""
from .domain import path_is_link
import argparse
import copy
import ipaddress
import json
import os
from pathlib import Path
import re
import subprocess
import sys

from .domain import ValidationError, atomic_json, decode, require, safe_path, write_new
from .layout import require_layout
from .connectors import zowe_command


def _profile(value):
    require(isinstance(value, str) and re.fullmatch(r'[A-Za-z0-9_-]{1,80}', value),
            'Use a Zowe profile alias containing letters, digits, underscores or hyphens')
    return value


def _host(value):
    require(isinstance(value, str) and 0 < len(value) <= 253 and not value.startswith('-'),
            'Supply the actual z/OSMF host name without URL, credentials or whitespace')
    try:
        ipaddress.ip_address(value)
    except ValueError:
        require(all(re.fullmatch(r'[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?', label)
                    for label in value.rstrip('.').split('.')),
                'Supply the actual z/OSMF host name without URL, credentials or whitespace')
    return value


def _merge_profile(profiles, name, kind):
    if name not in profiles: profiles[name] = {'type': kind, 'properties': {}}
    value = profiles[name]
    require(isinstance(value, dict) and value.get('type') == kind,
            'Existing selected profile has a different type; choose a new alias')
    value.setdefault('properties', {})
    require(isinstance(value['properties'], dict), 'Selected profile properties must be an object')
    # Never print, copy to a new field, delete, or silently bless inline credentials.
    require(not any(key in value['properties'] for key in ('user', 'password', 'tokenValue', 'certKeyFile')),
            'Selected profile contains inline credentials; secure them locally with Zowe before using this helper')
    return value


def prepare_profile(workspace, profile='workbench_base', host=None, port=None,
                       zosmf_profile=None, user_config=False):
    """Merge only a caller-selected project's config. Does not read home or run Zowe.

    A missing host intentionally stays absent. `zowe config secure` requires
    field names in each profile's `secure` array, not property paths or values.
    """
    profile = _profile(profile)
    zosmf_profile = _profile(zosmf_profile or profile[:73] + '_zosmf')
    require(profile != zosmf_profile, 'Base and z/OSMF profiles need distinct aliases')
    if host is not None: host = _host(host)
    require(port is None or type(port) is int and 1 <= port <= 65535, 'Port must be 1..65535')
    require(type(user_config) is bool, 'User-config selection must be a boolean')
    workspace = Path(workspace).absolute()
    require_layout(workspace)
    config_name = 'zowe.config.user.json' if user_config else 'zowe.config.json'
    path = safe_path(workspace, config_name)
    require(not path.exists() or path.is_file(), 'Selected Zowe config must be a regular file')
    require(not path.exists() or path.stat().st_size<=1024*1024,'Selected Zowe config exceeds its byte bound')
    config = decode(path.read_bytes(), 1024 * 1024) if path.exists() else {}
    require(isinstance(config, dict), 'Zowe config must be a JSON object')
    config = copy.deepcopy(config)
    config.setdefault('profiles', {})
    config.setdefault('defaults', {})
    require(isinstance(config['profiles'], dict) and isinstance(config['defaults'], dict),
            'Zowe profiles and defaults must be JSON objects')
    base = _merge_profile(config['profiles'], profile, 'base')
    service = _merge_profile(config['profiles'], zosmf_profile, 'zosmf')
    base.setdefault('secure', [])
    require(isinstance(base['secure'], list) and all(isinstance(item, str) for item in base['secure']),
            'Selected base profile secure declarations must be a list of field names')
    for name in ('user', 'password'):
        if name not in base['secure']: base['secure'].append(name)
    if host is not None: base['properties']['host'] = host
    if port is not None: base['properties']['port'] = port
    # New profiles use certificate validation; existing explicit settings are preserved.
    service['properties'].setdefault('rejectUnauthorized', True)
    service['properties'].setdefault('protocol', 'https')
    config['defaults'].setdefault('base', profile)
    config['defaults'].setdefault('zosmf', zosmf_profile)
    config.setdefault('autoStore', True)
    effective_host = service['properties'].get('host') or base['properties'].get('host')
    if effective_host is not None: _host(effective_host)
    command = ['zowe', 'config', 'secure'] + (['--user-config'] if user_config else [])
    result = {'status': 'READY_FOR_SECURE_INPUT' if effective_host else 'NEEDS_HOST',
            'config_file': str(path), 'profile': profile, 'zosmf_profile': zosmf_profile,
            'secure_fields': ['user', 'password'], 'secure_command': command,
            'run_from': str(workspace), 'credentials': 'UNVERIFIED', 'connectivity': 'UNVERIFIED',
            'environment': {'WB_ZOWE_PROFILE': profile, 'WB_ZOWE_ZOSMF_PROFILE': zosmf_profile},
            'guidance': 'From this workspace, run the secure command interactively in your local terminal. '
                        'Enter credentials only at Zowe prompts. Supply your actual z/OSMF host and port '
                        'if absent. Profile declarations do not establish authentication or read access.'}


    from .domain import encode
    return result, [(path, encode(config, 1024 * 1024))]


def initialize_profile(workspace, profile='workbench_base', host=None, port=None,
                       zosmf_profile=None, user_config=False):
    result, prepared = prepare_profile(workspace, profile, host, port, zosmf_profile, user_config)
    from .domain import atomic_bytes
    for path, content in prepared: atomic_bytes(path, content)
    require_layout(workspace)
    return result



def project_schema_path(workspace, config):
    """Honor a supplied local schema pointer without creating arbitrary root files."""
    reference=config.get('$schema')
    if reference is None or isinstance(reference,str) and reference.startswith(('https://','http://')):
        filename='zowe.schema.json'
    else:
        require(isinstance(reference,str),'Project schema reference must be text')
        filename=reference[2:] if reference.startswith('./') else reference
        require(filename in {'zowe.schema.json','zowe.config.schema.json','zowe.config.user.schema.json'},
                'Unsupported local project schema pointer; supply an approved root Zowe schema binding')
    return safe_path(workspace,filename)


def prepare_import(workspace, config_file, schema_file=None, user_config=False):
    """Import exactly selected nonsecret files without rewriting their contents."""
    require(type(user_config)is bool,'User-config selection must be a boolean')
    workspace=Path(workspace).absolute();require_layout(workspace)
    config_name='zowe.config.user.json' if user_config else 'zowe.config.json'
    selections=[(config_file,config_name)]
    prepared=[]
    for supplied,filename in selections:
        source=Path(supplied).absolute()
        require(not path_is_link(source) and not any(path_is_link(parent) for parent in source.parents)
                and source.is_file() and source.stat().st_size<=1024*1024,'Select a regular bounded project JSON file')
        content=source.read_bytes();document=decode(content,1024*1024)
        require(isinstance(document,dict),'Selected project JSON must be an object')
        if filename==config_name:
            pending=[document]
            while pending:
                node=pending.pop()
                if isinstance(node,dict):
                    require(not any(key in node and node[key] not in (None,'') for key in ('user','password','tokenValue','certKeyFile')),
                            'Import only nonsecret project configuration; keep credentials in the local Zowe secure store')
                    pending.extend(node.values())
                elif isinstance(node,list):pending.extend(node)
            if schema_file is not None:selections.append((schema_file,project_schema_path(workspace,document).name))
        destination=safe_path(workspace,filename)
        require(not destination.exists() or destination.is_file() and destination.read_bytes()==content,
                'An existing different project file is preserved; choose a separate workspace or merge it locally')
        prepared.append((destination,content))
    return {'status':'IMPORTED','files':[str(path) for path,_ in prepared],
            'credentials':'UNVERIFIED','connectivity':'UNVERIFIED','content_preserved':True}, prepared


def import_project_config(workspace, config_file, schema_file=None, user_config=False):
    result, prepared = prepare_import(workspace, config_file, schema_file, user_config)
    for destination, content in prepared:
        if not destination.exists():write_new(destination,content)
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check',action='store_true',help='Inspect selected project config with redacted structural diagnostics')
    parser.add_argument('--normalize',action='store_true',help='Deduplicate secure declarations only, preserving all profiles/defaults and a private backup')
    parser.add_argument('--workspace', default=str(Path.cwd()))
    parser.add_argument('--profile', default='workbench_base', help='Base profile alias')
    parser.add_argument('--zosmf-profile', help='Paired z/OSMF service alias')
    parser.add_argument('--host', help='Actual z/OSMF host; omit to prepare a hostless template')
    parser.add_argument('--port', type=int, help='Actual z/OSMF port')
    parser.add_argument('--user-config', action='store_true')
    parser.add_argument('--import-config', help='Exact selected nonsecret Zowe config file')
    parser.add_argument('--import-schema', help='Exact selected Zowe schema file')
    parser.add_argument('--interactive',action='store_true',help='Ask for nonsecret profile, host and port in a local terminal')
    parser.add_argument('--secure',action='store_true',help='Run Zowe secure prompts locally after preparing declarations; requires a terminal')
    args = parser.parse_args(argv)
    try:
        if args.check or args.normalize:
            require(not(args.interactive or args.secure or args.import_config),'Choose inspection/normalization separately from setup')
            result=inspect_project_config(args.workspace,normalize=args.normalize)
            print(json.dumps(result,indent=2));return 2 if result['issues'] else 0
        require(not(args.interactive and args.import_config),'Import selected files first, then run guided profile setup')
        require(not(args.secure and args.import_config),'Import selected files first, then initialize the selected secure profile')
        if args.interactive or args.secure:
            if not sys.stdin.isatty():
                print(json.dumps({'status':'BLOCKED','message':'Guided or secure input requires your local interactive terminal.',
                                  'credentials':'UNVERIFIED','connectivity':'UNVERIFIED'}));return 2
        if args.interactive:
            args.profile=input('Base profile alias ['+args.profile+']: ').strip() or args.profile
            args.zosmf_profile=input('z/OSMF service alias [paired service]: ').strip() or args.zosmf_profile
            args.host=input('Actual z/OSMF host [leave blank to preserve/unset]: ').strip() or args.host
            selected_port=input('Actual z/OSMF port [leave blank to preserve/default]: ').strip()
            if selected_port:
                require(selected_port.isdigit(),'Port must be a positive integer');args.port=int(selected_port)
        require(args.import_config or not args.import_schema,'Schema import requires a selected config file')
        result = import_project_config(args.workspace,args.import_config,args.import_schema,args.user_config) if args.import_config else \
                 initialize_profile(args.workspace, args.profile, args.host, args.port,args.zosmf_profile,args.user_config)
        if args.secure:
            allowed=['PATH','PATHEXT','HOME','USERPROFILE','APPDATA','LOCALAPPDATA','TEMP','TMP','SystemRoot','ZOWE_CLI_HOME','NODE_EXTRA_CA_CERTS']
            environment={key:os.environ[key] for key in allowed if key in os.environ}
            code=subprocess.call(zowe_command(result['secure_command'], environment),cwd=result['run_from'],env=environment,shell=False,stderr=subprocess.DEVNULL)
            result['secure_input']='COMPLETED' if code==0 else 'FAILED'
            # A successful credential-store command is still not a live connection.
            if code!=0:
                result['guidance']='Local secure input failed; run the listed Zowe secure command directly to inspect private credential-store settings.'
                print(json.dumps(result,indent=2));return 2
    except (EOFError,KeyboardInterrupt):
        print(json.dumps({'status':'CANCELLED','credentials':'UNVERIFIED','connectivity':'UNVERIFIED'}));return 2
    except (ValidationError, OSError):
        # Config content, paths and native credential-manager diagnostics stay private.
        print(json.dumps({'status': 'BLOCKED', 'message': 'Project profile setup failed. Check workspace layout, '
                          'selected profile types, host/port and existing secure declarations locally.'}))
        return 2
    print(json.dumps(result, indent=2))
    return 0




def inspect_project_config(workspace, normalize=False):
    """Redacted structural diagnostics; normalize only duplicate secure declarations.

    No profiles/defaults/credentials are renamed or removed. This does not run
    Zowe, read its credential store, or imply successful connectivity.
    """
    root = Path(workspace).absolute(); require_layout(root)
    path = safe_path(root, 'zowe.config.json')
    require(path.is_file() and path.stat().st_size <= 1024*1024, 'Provide a bounded project Zowe config')
    raw = path.read_bytes(); config = decode(raw, 1024*1024)
    require(isinstance(config, dict) and isinstance(config.get('profiles'), dict), 'Project profiles must be an object')
    result = []; known = {}; duplicates = []; inline = False
    def visit(profiles, prefix=''):
        nonlocal inline
        for name, profile in profiles.items():
            require(isinstance(name,str) and bool(name) and '.' not in name and name not in {'__proto__','constructor','prototype'},'Zowe profile components must resolve as unambiguous nested names')
            require(isinstance(profile,dict), 'Profile must be an object')
            alias = prefix+name; properties = profile.get('properties', {}); secure = profile.get('secure', [])
            require(isinstance(properties,dict) and isinstance(secure,list) and all(isinstance(s,str) for s in secure), 'Invalid profile properties or secure fields')
            inline |= any(properties.get(k) not in (None,'') for k in ('user','password','tokenValue','certKeyFile'))
            unique = list(dict.fromkeys(secure))
            if secure != unique:
                duplicates.append(alias)
                if normalize: profile['secure'] = unique
            known[alias] = profile.get('type')
            result.append({'alias':alias,'type':profile.get('type'),'property_names':sorted(properties),'secure_fields':unique})
            children = profile.get('profiles', {})
            require(isinstance(children,dict), 'Nested profiles must be an object')
            visit(children, alias+'.')
    visit(config['profiles'])
    defaults = config.get('defaults', {})
    require(isinstance(defaults,dict), 'Defaults must be an object')
    issues = []
    for kind, alias in defaults.items():
        if not isinstance(alias,str) or known.get(alias) != kind: issues.append('Default '+kind+' does not select a matching profile type')
    if inline: issues.append('Inline credential fields require local secure-store migration')
    schema = project_schema_path(root,config)
    schema_status = 'NOT_PRESENT'
    reference=config.get('$schema')
    if reference is not None and not reference.startswith(('https://','http://')) and not schema.exists():
        schema_status='MISSING_REFERENCED_SCHEMA';issues.append('Supply the declared local project schema file')
    if schema.exists():
        require(schema.is_file() and schema.stat().st_size<=1024*1024,'Invalid project schema file')
        document=decode(schema.read_bytes(),1024*1024)
        pending=[document]; external=False
        while pending:
            item=pending.pop()
            if isinstance(item,dict):
                external |= any(isinstance(item.get(key),str) and not item[key].startswith('#') for key in ('$ref','$dynamicRef','$recursiveRef'))
                pending.extend(item.values())
            elif isinstance(item,list): pending.extend(item)
        if external:schema_status='EXTERNAL_REFERENCES_NOT_FETCHED'
        else:
            from jsonschema.validators import validator_for
            from jsonschema import Draft202012Validator
            validator=validator_for(document,default=None) if '$schema' in document else Draft202012Validator
            if validator is None:
                schema_status='UNSUPPORTED_DIALECT';issues.append('Unsupported project schema dialect')
            else:
                validator.check_schema(document)
                errors=list(validator(document).iter_errors(config))
                schema_status='INVALID' if errors else 'VALID'
                issues.extend('Schema mismatch at '+'.'.join(map(str,e.absolute_path)) for e in errors)
    changed=False
    if normalize and duplicates:
        require(not inline and not issues and schema_status=='VALID','Resolve profile/schema diagnostics before normalization')
        from .domain import sha
        backup=safe_path(root,'.implementation/tmp/zowe-config-'+sha(raw)+'.json')
        if not backup.exists():write_new(backup,raw)
        require(path.read_bytes()==raw,'Project config changed during inspection')
        atomic_json(path,config);changed=True
    return {'profiles':result,'defaults':defaults,'issues':issues,'duplicate_secure_declarations':duplicates,
            'schema':schema_status,'changed':changed,'credentials':'UNVERIFIED','connectivity':'UNVERIFIED',
            'boundary':'Structure only; preserve selected service roles and test an authorized read separately'}


if __name__ == '__main__': raise SystemExit(main())
