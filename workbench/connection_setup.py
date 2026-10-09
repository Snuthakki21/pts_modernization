"""Prepare approved Claude Code MCP and Zowe configuration without executing tools.

The Coordinator owns saves. Credentials and VS Code activation remain in their
native secure clients; neither configuration nor CLI presence proves host access.
"""
import copy
import os
from pathlib import Path
import shlex
import shutil
import sys
from urllib.parse import urlsplit

from .domain import (ValidationError, atomic_bytes, decode, encode, path_is_link,
                     require, safe_path, sha)
from .zowe_setup import prepare_import, prepare_profile, project_schema_path

MAX_CONFIG = 1024 * 1024
CHOICE_KEYS = {'mode', 'host', 'port', 'config_file', 'schema_file'}
DB2_KEYS = {'mode','host','port','database','location','driver','certificate_file','mcp_port','row_limit'}
SERVER = 'workbench-retrieval'
DB2_SERVER = 'workbench-db2'
TOKEN_ENV = 'WB_DB2_MCP_TOKEN'
# Frozen v1 setup metadata is read for explicit migration, never reused as Claude config.
TOKEN_INPUT = 'workbenchDb2Token'


def default_choices(settings):
    return {'claude':True, 'db2_auth':'bearer_env', 'zowe':{'mode':'existing' if settings.get('zowe_profile') else 'off',
            'host':None, 'port':None, 'config_file':None, 'schema_file':None},
            'db2':{'mode':'existing' if settings.get('db2_metadata_url') else 'off',
                   **{key:None for key in DB2_KEYS-{'mode'}}}}


def validate_choices(value):
    require(isinstance(value,dict),'Supply nonsecret Claude, Zowe and Db2 setup choices')
    value=copy.deepcopy(value)
    # One explicit Save migrates historical Copilot choices; no GET rewrites files.
    if 'copilot' in value and 'claude' not in value:
        value['claude']=value.pop('copilot')
    value.setdefault('db2_auth','bearer_env')
    require(set(value) in ({'claude','db2_auth','zowe'},{'claude','db2_auth','zowe','db2'}) and type(value['claude']) is bool,
            'Supply only the nonsecret Claude, Zowe and Db2 MCP setup choices')
    require(value['db2_auth'] in ('bearer_env','oauth'),'Choose private environment token or approved OAuth for Db2 MCP')
    zowe=value['zowe']
    require(isinstance(zowe,dict) and set(zowe)==CHOICE_KEYS and zowe['mode'] in ('off','existing','create','import'),
            'Choose off, existing, create or import for Zowe configuration')
    for key in ('host','config_file','schema_file'):
        v=zowe[key]
        require(v is None or isinstance(v,str) and 0<len(v)<=2048 and v==v.strip()
                and not any(ord(c)<32 or ord(c)==127 for c in v), 'Use bounded nonsecret setup values')
    port=zowe['port'];require(port is None or type(port) is int and 1<=port<=65535, 'Zowe port must be 1..65535')
    if zowe['mode']=='create':
        from .zowe_setup import _host
        _host(zowe['host']);require(port is not None,'Supply the actual z/OSMF port')
        require(zowe['config_file'] is None and zowe['schema_file'] is None,'Choose profile creation or exact import separately')
    elif zowe['mode']=='import':
        require(zowe['config_file'] is not None,'Select the exact local Zowe config file')
        require(zowe['host'] is None and port is None,'Exact import preserves supplied host and port')
    else:
        require(all(zowe[k] is None for k in ('host','port','config_file','schema_file')),
                'Inactive Zowe options must be empty')
    if 'db2' in value:
        db2=value['db2']
        require(isinstance(db2,dict) and set(db2)==DB2_KEYS and db2['mode'] in ('off','existing','gateway'),
                'Choose off, existing or gateway for the approved Db2 MCP server')
        for key in ('host','database','location','driver','certificate_file'):
            item=db2[key]
            require(item is None or isinstance(item,str) and 0<len(item)<=2048 and item==item.strip()
                    and not any(ord(c)<32 or ord(c)==127 for c in item),'Use bounded nonsecret Db2 setup values')
        for key,upper in (('port',65535),('mcp_port',65535),('row_limit',500000)):
            require(db2[key] is None or type(db2[key]) is int and 1<=db2[key]<=upper,'Invalid Db2 port or row budget')
        if db2['mode']=='gateway':
            from .zowe_setup import _host
            _host(db2['host'])
            require(all(db2[key] is not None for key in ('port','database','location','driver','mcp_port','row_limit')),
                    'Supply the actual Db2 host, port, database, location, driver and local MCP limits')
            require(value['claude'],'Prepare the approved Claude MCP binding for the Db2 gateway')
            require(value['db2_auth']=='bearer_env','The local Db2 gateway requires a private bearer token')
        else:require(all(db2[key] is None for key in DB2_KEYS-{'mode'}),'Inactive Db2 gateway fields must be empty')
    return copy.deepcopy(value)


def _read(path):
    require(not any(path_is_link(p) for p in (path,*path.parents)), 'Use direct local configuration paths')
    if not path.exists():return None
    require(path.is_file() and path.stat().st_size<=MAX_CONFIG,'Select a regular bounded configuration file')
    data=path.read_bytes();require(len(data)<=MAX_CONFIG,'Configuration exceeds its byte bound')
    return data


def _state(root, settings):
    raw=_read(safe_path(root,'.migration/connections.json'))
    if raw is None:return default_choices(settings),{}
    doc=decode(raw,MAX_CONFIG)
    require(isinstance(doc,dict) and set(doc)=={'version','choices','managed'} and type(doc['version']) is int
            and doc['version'] in (1,2) and isinstance(doc['managed'],dict),'Unsupported local connection setup state')
    allowed={SERVER,DB2_SERVER,TOKEN_INPUT} if doc['version']==1 else {DB2_SERVER}
    require(set(doc['managed'])<=allowed and all(isinstance(h,str) and len(h)==64
            and all(c in '0123456789abcdef' for c in h) for h in doc['managed'].values()),'Invalid managed configuration identities')
    # The former VS Code config belongs to another client and remains untouched.
    return validate_choices(doc['choices']),doc['managed'] if doc['version']==2 else {}


def _claude_plan(root, choices, settings, managed, origin):
    path=safe_path(root,'.mcp.json');raw=_read(path)
    # Text-first stdio survives an intake/source-only Save. A deliberate change
    # to the optional HTTP choices may still use the existing managed-hash route.
    if raw is not None:
        candidate=decode(raw,MAX_CONFIG)
        entry=candidate.get('mcpServers',{}).get(DB2_SERVER) if isinstance(candidate,dict) and isinstance(candidate.get('mcpServers'),dict) else None
        if isinstance(entry,dict) and entry.get('type')=='stdio':
            from .db2_setup import validate_stdio_binding
            validate_stdio_binding(entry,root)
            previous,_=_state(root,settings)
            if (choices.get('db2',{'mode':'off'})==previous.get('db2',{'mode':'off'}) and choices['claude']==previous['claude']) or choices.get('db2',{'mode':'off'})['mode']=='off':
                return [],{DB2_SERVER:sha(encode(entry))}
    if not choices['claude'] and not managed:return [],{}
    config=decode(raw,MAX_CONFIG) if raw is not None else {'mcpServers':{}}
    require(isinstance(config,dict) and set(config)=={'mcpServers'} and isinstance(config['mcpServers'],dict),
            'Claude MCP config must contain mcpServers; preserve and correct any incompatible client format')
    config=copy.deepcopy(config);servers=config['mcpServers'];expected={}
    if choices['claude'] and settings['db2_metadata_url']:
        entry={'type':'http','url':settings['db2_metadata_url']}
        if choices['db2_auth']=='bearer_env':entry['headers']={'Authorization':'Bearer ${'+TOKEN_ENV+'}'}
        expected[DB2_SERVER]=entry
    old=servers.get(DB2_SERVER);wanted=expected.get(DB2_SERVER)
    if old is not None and old!=wanted:
        require(DB2_SERVER in managed and sha(encode(old))==managed[DB2_SERVER],
                'Existing Claude MCP binding '+DB2_SERVER+' is preserved; resolve the conflicting binding locally')
    if wanted is not None:servers[DB2_SERVER]=wanted
    elif DB2_SERVER in managed:servers.pop(DB2_SERVER,None)
    return [(path,encode(config,MAX_CONFIG))],{name:sha(encode(value)) for name,value in expected.items()}


def _profile_checks(config, settings, schema=None):
    require(isinstance(config,dict) and isinstance(config.get('profiles'),dict),'Zowe config needs a profiles object')
    reference=config.get('$schema')
    require(reference is None or isinstance(reference,str),'Project schema reference must be text')
    if reference is not None and not reference.startswith(('https://','http://')):
        require(schema is not None,'Supply the declared local Zowe schema file before preparing this config')
    known={};pending=[(config['profiles'],'',{})]
    while pending:
        profiles,prefix,inherited=pending.pop()
        for alias,node in profiles.items():
            require(isinstance(alias,str) and bool(alias) and '.' not in alias and alias not in {'__proto__','constructor','prototype'},'Zowe profile components must resolve as unambiguous nested names')
            require(isinstance(node,dict) and isinstance(node.get('properties',{}),dict),'Zowe profile must have an object of properties')
            properties=node.get('properties',{})
            require(not any(properties.get(k) not in (None,'') for k in ('user','password','tokenValue','certKeyFile')),
                    'Keep Zowe credentials in the approved secure store')
            secure=node.get('secure',[]);require(isinstance(secure,list) and all(isinstance(v,str) for v in secure),'Zowe secure fields must be names')
            children=node.get('profiles',{});require(isinstance(children,dict),'Nested Zowe profiles must be objects')
            effective={**inherited,**properties}
            known[prefix+alias]=(node,effective);pending.append((children,prefix+alias+'.',effective))
    base=known.get(settings['zowe_profile']);service=known.get(settings['zowe_zosmf_profile'])
    require(base is not None and base[0].get('type')=='base' and service is not None and service[0].get('type')=='zosmf',
            'Select the exact base and z/OSMF aliases in the project config')
    from .zowe_setup import _host
    properties={**base[1],**service[1]}
    _host(properties.get('host'))
    port=properties.get('port',443)
    require(type(port) is int and 1<=port<=65535,'Zowe service port must be 1..65535')
    defaults=config.get('defaults',{})
    require(isinstance(defaults,dict),'Zowe defaults must be an object')
    require(all(isinstance(alias,str) and alias in known and known[alias][0].get('type')==kind for kind,alias in defaults.items()),
            'Preserve and correct the Zowe default profile type bindings')
    require(properties.get('protocol','https')=='https' and properties.get('rejectUnauthorized',True) is True,
            'Use the approved HTTPS service with certificate validation enabled')
    if schema is not None:
        pending=[schema]
        while pending:
            item=pending.pop()
            if isinstance(item,dict):
                require(all(not isinstance(item.get(key),str) or item[key].startswith('#') for key in ('$ref','$dynamicRef','$recursiveRef')),
                        'External schema references are not fetched; supply a self-contained approved Zowe schema')
                pending.extend(item.values())
            elif isinstance(item,list):pending.extend(item)
        from jsonschema.validators import validator_for
        from jsonschema import Draft202012Validator
        try:
            validator=validator_for(schema,default=None) if '$schema' in schema else Draft202012Validator
            require(validator is not None,'Unsupported Zowe schema dialect; supply a recognized self-contained schema')
            validator.check_schema(schema)
            require(not any(validator(schema).iter_errors(config)),'Supplied Zowe config does not satisfy its schema')
        except ValidationError:raise
        except Exception as exc:raise ValidationError('Correct the supplied local Zowe schema') from exc


def _db2_env_template(db2):
    """Create only nonsecret canonical z/OS settings; authentication stays empty."""
    require(db2['database']==db2['location'], 'DB2_DATABASE must equal DB2_LOCATION_NAME for the workspace z/OS environment')
    def literal(value):
        value=str(value)
        quote='"' if '"' not in value else "'"
        require(quote not in value, 'Db2 environment fields require a literal value with an available quote delimiter')
        return quote+value+quote
    rows=[('DB2_LOCATION_NAME',db2['location']),('DB2_DATABASE',db2['database']),
          ('DB2_HOSTNAME',db2['host']),('DB2_PORT',db2['port'])]
    text='# Private local Db2 connection. Never commit or paste this file into a model/chat.\n'
    text+='# DB2_DATABASE equals DB2_LOCATION_NAME for this z/OS adapter.\n'
    text+='\n'.join(key+'='+literal(value) for key,value in rows)+'\n'
    text+='DB2_USERNAME=\nDB2_PASSWORD=\nDB2_SSL_CONNECTION=true\nDB2_SSL_SERVER_CERTIFICATE=certificates/DB2-CA.cert\n'
    return text.encode('utf-8')


def _command(argv):
    if sys.platform=='win32':return '& '+' '.join("'"+str(v).replace("'","''")+"'" for v in argv)
    return shlex.join([str(v) for v in argv])


def _inspect_connections(root, settings, origin=None):
    root=Path(root).absolute();choices,managed=_state(root,settings)
    checks=[];commands=[];files=[];remaining=[]
    def need(name,message):remaining.append({'id':name,'message':message})
    cli='NOT_REQUIRED'
    mcp_raw=_read(safe_path(root,'.mcp.json'))
    if mcp_raw is not None:
        candidate=decode(mcp_raw,MAX_CONFIG)
        entry=candidate.get('mcpServers',{}).get(DB2_SERVER) if isinstance(candidate,dict) and isinstance(candidate.get('mcpServers'),dict) else None
        if isinstance(entry,dict) and entry.get('type')=='stdio':
            from .db2_setup import inspect_stdio_binding
            from .db2_env import settings as env_settings, _certificate
            configured=inspect_stdio_binding(root)
            files.append({'kind':'claude','path':configured['config_file'],'status':'PREPARED'})
            env_status='PREPARED'
            try:
                private=env_settings({},safe_path(root,'.env'),canonical=True)
                _certificate(private.certificate)
                if not private.username or not private.password:
                    need('db2_credentials','Fill missing DB2_USERNAME and DB2_PASSWORD only in the private local .env, then restart the Claude-owned server.')
            except (ValidationError,OSError):
                env_status='NEEDS_LOCAL_CORRECTION'
                need('db2_env','Check the private workspace .env and certificates/DB2-CA.cert locally. Existing bytes are preserved; never paste their contents into chat.')
            files.append({'kind':'db2_env','path':configured['env_file'],'status':env_status})
            # Shared .env preparation includes Zowe independently of Db2.
            # Do not turn its real local prerequisites into NOT_REQUIRED.
            try:
                from .db2_env import read_workspace_env
                zowe_selected=bool(read_workspace_env(safe_path(root,'.env')).get('ZOWE_ENVIRONMENT'))
            except (ValidationError,OSError):zowe_selected=False
            if zowe_selected:
                from .zowe_setup import environment_profiles
                from .connectors import zowe_command
                try:
                    environment_profiles(root)
                    files.extend([{'kind':'zowe','path':str(safe_path(root,'zowe.config.json')),'status':'PREPARED'},
                                  {'kind':'zowe_schema','path':str(safe_path(root,'zowe.schema.json')),'status':'PREPARED'}])
                except (ValidationError,OSError):
                    need('zowe_config','Prepare the clean Zowe config/schema from the private .env. Existing different files are preserved.')
                cli='NOT_FOUND'
                if shutil.which('zowe'):
                    try:zowe_command(['zowe','config','secure'],dict(os.environ));cli='AVAILABLE'
                    except (ValidationError,OSError):cli='UNUSABLE'
                checks.append({'id':'zowe_cli','status':cli,'message':'Text-prepared Zowe CLI availability is checked separately from authentication or read access.'})
                if cli!='AVAILABLE':need('zowe_cli','Install or repair the organization-approved Zowe CLI and Node runtime, then recheck. No mainframe request was made.')
                need('zowe_credentials','For Zowe Explorer, complete zowe config secure locally and launch the client with the approved CA environment. Private .env credentials support only the bounded local CLI reader; live read access remains unverified.')
            checks.append({'id':'db2_transport','status':'PREPARED','message':'Local stdio configuration prepared from .env. Claude owns the server; no separate HTTP server or transport credential entry is needed.'})
            import importlib.util
            try:driver_module=importlib.util.find_spec('pyodbc') is not None
            except (ValueError,ImportError):driver_module=False
            if not driver_module:need('db2_driver','Install the organization-approved pyodbc package and registered IBM Db2 ODBC driver before the local MCP server can read Db2.')
            launcher=Path(__file__).parent.parent/'scripts/Start-Claude.ps1'
            commands.append({'id':'claude_start','label':'Open Claude Code for this workspace','command':"& '"+str(launcher).replace("'","''")+"' -Workspace '"+str(root).replace("'","''")+"'",'required':True})
            need('claude_activation','Run the displayed Claude launcher and review the approved local server with /mcp. Configuration is not a successful database read.')
            return {'choices':choices,'transport':'stdio','status':'ACTION_REQUIRED' if remaining else 'CONFIGURATION_READY',
                    'checks':checks,'commands':commands,'files':files,'remaining':remaining,
                    'runtime':{'platform':'windows' if sys.platform=='win32' else 'macos' if sys.platform=='darwin' else 'linux','zowe_cli':cli},
                    'claude_mcp_servers':1,'connectivity':'UNVERIFIED'}
    if choices['zowe']['mode']!='off':
        cli='NOT_FOUND'
        from .connectors import zowe_command
        if shutil.which('zowe'):
            try:argv=zowe_command(['zowe','config','secure'],dict(os.environ));cli='AVAILABLE'
            except (ValidationError,OSError):cli='UNUSABLE'
        if cli!='AVAILABLE':
            node_npm=bool(shutil.which('node') and shutil.which('npm.cmd' if sys.platform=='win32' else 'npm'))
            checks.append({'id':'node_npm','status':'AVAILABLE' if node_npm else 'NOT_FOUND',
                'message':'Node/npm launchers available; approved runtime version remains unverified.' if node_npm else 'The Zowe installer requires your organization-approved Node/npm runtime.'})
            if not node_npm:need('node_npm','Install the organization-approved Node/npm runtime before using the Zowe installation command, then recheck.')
            need('zowe_cli','Install your organization-approved Zowe CLI, then recheck setup.')
            # Published Zowe v3 LTS installation channel; organization deployment may replace this command.
            commands.append({'id':'zowe_install','label':'Install approved Zowe CLI','command':('npm.cmd' if sys.platform=='win32' else 'npm')+' install --global @zowe/cli@zowe-v3-lts','required':True})
            argv=['zowe','config','secure']
        checks.append({'id':'zowe_cli','status':cli,'message':'Local Zowe CLI launcher '+cli.lower().replace('_',' ')+'. No CLI or host request was executed.'})
        config=safe_path(root,'zowe.config.json');raw=_read(config)
        try:
            require(raw is not None,'Zowe project configuration is missing')
            config_doc=decode(raw,MAX_CONFIG);schema_raw=_read(project_schema_path(root,config_doc))
            _profile_checks(config_doc,settings,decode(schema_raw,MAX_CONFIG) if schema_raw is not None else None)
            files.append({'kind':'zowe','path':str(config),'status':'PREPARED'})
            if schema_raw is not None:files.append({'kind':'zowe_schema','path':str(project_schema_path(root,config_doc)),'status':'PREPARED'})
        except ValidationError as failure:need('zowe_config',str(failure))
        cd="Set-Location -LiteralPath "+"'"+str(root).replace("'","''")+"'" if sys.platform=='win32' else 'cd '+shlex.quote(str(root))
        commands.append({'id':'zowe_secure','label':'Enter Zowe credentials securely','command':cd+'\n'+_command(argv),'required':True})
        need('zowe_credentials','Run the secure command in your local terminal. Authentication and read access remain unverified.')
    db2=choices.get('db2',{'mode':'existing' if settings['db2_metadata_url'] else 'off'})
    if db2['mode']=='gateway':
        from .db2_setup import _config, CERTIFICATE
        from .db2_env import validate_certificate
        from importlib.util import find_spec
        config_path=safe_path(root,'.migration/db2-config.json')
        try:
            raw=_read(config_path);require(raw is not None,'Db2 MCP configuration is missing')
            config=_config(decode(raw,MAX_CONFIG))
            require(all(config.get(key)==db2[key] for key in ('host','port','database','location','driver'))
                    and config['max_rows']==db2['row_limit'],'Db2 MCP settings changed; reload and Save the selected configuration')
            files.append({'kind':'db2_config','path':str(config_path),'status':'PREPARED'})
        except ValidationError as failure:need('db2_config',str(failure))
        certificate=safe_path(root,CERTIFICATE)
        try:
            validate_certificate(_read(certificate))
            files.append({'kind':'db2_certificate','path':str(certificate),'status':'PREPARED'})
        except ValidationError:need('db2_certificate','Select your approved PEM or DER Db2 CA certificate in this screen and Save again. A placeholder cannot authenticate.')
        try:module_available=find_spec('pyodbc') is not None
        except (ImportError,ValueError):module_available=False
        checks.append({'id':'db2_driver','status':'MODULE_PRESENT' if module_available else 'NOT_FOUND',
                       'message':'The Python ODBC module is present; the selected IBM driver is checked at local server startup.' if module_available else 'Install the organization-approved pyodbc package and IBM Db2 ODBC driver in this Python environment.'})
        if not module_available:need('db2_driver','Install the organization-approved pyodbc package and IBM Db2 ODBC driver; then recheck setup.')
        else:need('db2_driver','Start the local server command to validate the selected registered ODBC driver. No Db2 read has been performed.')
        env_path=safe_path(root,'.env')
        if env_path.exists() or db2['database']==db2['location']:
            env_ready=False
            try:
                from .db2_env import settings as env_settings
                require(env_path.is_file(), 'Prepare the private workspace environment')
                selected=env_settings({},env_path,canonical=True)
                require((selected.host,selected.port,selected.database,selected.location)==(db2['host'],db2['port'],db2['database'],db2['location']),
                        'Private environment differs from the saved form')
                env_ready=True
            except (ValidationError,OSError,UnicodeError):
                need('db2_env','The private workspace .env needs local correction or differs from saved connection settings. Existing bytes are preserved; never paste its contents into chat.')
            files.append({'kind':'db2_env','path':str(env_path),'status':'PREPARED' if env_ready else 'NEEDS_LOCAL_CORRECTION'})
        else:
            need('db2_env','This historical gateway uses a separate database/location. Save the canonical z/OS settings to prepare a workspace .env; existing configuration is preserved.')
        script=Path(__file__).parent.parent/'tools/db2_mcp_server.py'
        argv=[str(Path(sys.executable).absolute()),str(script.absolute()),'--transport','http','--config',str(config_path),'--workspace',str(root),'--port',str(db2['mcp_port']),'--interactive']
        if env_path.exists():argv += ['--env-file',str(env_path)]
        cd="Set-Location -LiteralPath "+"'"+str(root).replace("'","''")+"'" if sys.platform=='win32' else 'cd '+shlex.quote(str(root))
        commands.append({'id':'db2_start','label':'Start the approved read-only Db2 MCP server','command':cd+'\n'+_command(argv),'required':True})
        need('db2_server','Run the displayed local Db2 MCP command. Use DB2_USERNAME and DB2_PASSWORD in the protected local .env, or enter missing credentials at its secure local prompts. Keep transport authentication at the approved Claude launcher and keep the server terminal open.')
    if choices['claude']:
        path=safe_path(root,'.mcp.json');raw=_read(path);actual={}
        if raw is not None:
            doc=decode(raw,MAX_CONFIG)
            require(isinstance(doc,dict) and set(doc)=={'mcpServers'} and isinstance(doc['mcpServers'],dict),
                    'Correct the local Claude MCP server structure')
            actual=doc['mcpServers']
        expected={}
        if settings['db2_metadata_url']:
            expected[DB2_SERVER]={'type':'http','url':settings['db2_metadata_url']}
            if choices['db2_auth']=='bearer_env':expected[DB2_SERVER]['headers']={'Authorization':'Bearer ${'+TOKEN_ENV+'}'}
        valid=raw is not None and managed=={name:sha(encode(value)) for name,value in expected.items()} and all(actual.get(name)==value for name,value in expected.items())
        files.append({'kind':'claude','path':str(path),'status':'PREPARED' if valid else 'NEEDS_SAVE'})
        if not valid:need('claude_config','Save setup to prepare the approved Claude Code MCP configuration.')
        launcher=Path(__file__).parent.parent/'scripts/Start-Claude.ps1'
        command="& '"+str(launcher).replace("'","''")+"' -Workspace '"+str(root).replace("'","''")+"'"
        commands.append({'id':'claude_start','label':'Open Claude Code for this workspace','command':command,'required':True})
        need('claude_activation','Run the displayed Windows Claude launcher, then /mcp. Review the approved server trust and authenticate. Configuration is not connectivity.')
        if settings['db2_metadata_url']:
            need('db2_authentication','Enter the approved token only at the secure Claude launcher prompt.' if choices['db2_auth']=='bearer_env' else 'Use /mcp in Claude Code to authenticate with the approved OAuth server.')
    active=choices['claude'] or choices['zowe']['mode']!='off' or db2['mode']!='off'
    return {'choices':choices,'status':'ACTION_REQUIRED' if remaining else 'CONFIGURATION_READY' if active else 'NOT_CONFIGURED',
            'checks':checks,'commands':commands,'files':files,'remaining':remaining,
            'runtime':{'platform':'windows' if sys.platform=='win32' else 'linux' if sys.platform.startswith('linux') else 'macos', 'zowe_cli':cli},
            'claude_mcp_servers':int(choices['claude'] and bool(settings['db2_metadata_url'])),'connectivity':'UNVERIFIED'}



def inspect_connections(root, settings, origin=None):
    try:return _inspect_connections(root,settings,origin)
    except (ValidationError,OSError,UnicodeError):
        return {'choices':default_choices(settings),'status':'ACTION_REQUIRED',
                'checks':[{'id':'connection_config','status':'BLOCKED','message':'Local connector configuration needs correction. Existing files are preserved.'}],
                'commands':[],'files':[],'remaining':[{'id':'connection_config','message':'Correct the selected local connector configuration, then recheck setup.'}],
                'runtime':{'platform':'windows' if sys.platform=='win32' else 'linux' if sys.platform.startswith('linux') else 'macos','zowe_cli':'UNVERIFIED'},
                'claude_mcp_servers':0,'connectivity':'UNVERIFIED'}


def configure_connections(root, settings, choices, *, origin='http://127.0.0.1:8765'):
    """Validate every destination first; restore ordinary failed saves without losing other bindings."""
    from .setup import prepare_workstation, workstation_markdown, inspect_workstation_instructions
    choices=validate_choices(choices)
    require(isinstance(settings,dict),'Supply nonsecret workstation settings')
    if choices['zowe']['mode']=='off':settings={**settings,'zowe_profile':None,'zowe_zosmf_profile':None}
    db2=choices.get('db2')
    if db2 is not None:
        if db2['mode']=='off':settings={**settings,'db2_metadata_url':None}
        elif db2['mode']=='gateway':
            require(db2['mcp_port']!=urlsplit(origin).port,'The Db2 MCP port must differ from the running Workbench port')
            settings={**settings,'db2_metadata_url':'http://127.0.0.1:'+str(db2['mcp_port'])+'/mcp'}
    root=Path(root).absolute()
    state_path=safe_path(root,'.migration/connections.json')
    baseline={state_path:_read(state_path)}
    _,managed=_state(root,settings);mode=choices['zowe']['mode']
    selected=['.migration/workstation.json', '.migration/workstation.md']
    if choices['claude'] or managed:selected.append('.mcp.json')
    if mode!='off':selected.append('zowe.config.json')
    if db2 is not None and db2['mode']=='gateway':selected.extend(['.migration/db2-config.json','certificates/DB2-CA.cert','.env'])
    for relative in selected:
        path=safe_path(root,relative);baseline[path]=_read(path)
    if mode=='import':
        from .setup import _local_path
        for field in ('config_file','schema_file'):
            if choices['zowe'][field] is not None:
                choices['zowe'][field]=_local_path(root,choices['zowe'][field],field)
                source=Path(choices['zowe'][field]);baseline.setdefault(source,_read(source))
    if mode!='off':
        config_source=Path(choices['zowe']['config_file']) if mode=='import' else safe_path(root,'zowe.config.json')
        original_config=baseline.get(config_source)
        schema_path=project_schema_path(root,decode(original_config,MAX_CONFIG) if original_config is not None else {})
        baseline[schema_path]=_read(schema_path)
    if db2 is not None and db2['mode']=='gateway' and db2['certificate_file'] is not None:
        from .setup import _local_path
        db2['certificate_file']=_local_path(root,db2['certificate_file'],'certificate_file')
        source=Path(db2['certificate_file']);baseline.setdefault(source,_read(source))
    view, settings_path, settings_doc=prepare_workstation(root,settings)
    settings=view['settings'];prepared=[]
    if mode!='off':
        require(settings['zowe_profile'] and settings['zowe_zosmf_profile'],'Supply the selected Zowe base and z/OSMF profile aliases')
        if mode=='create':
            _,prepared=prepare_profile(root,settings['zowe_profile'],choices['zowe']['host'],choices['zowe']['port'],settings['zowe_zosmf_profile'])
        elif mode=='import':
            _,prepared=prepare_import(root,choices['zowe']['config_file'],choices['zowe']['schema_file'])
        config_path=safe_path(root,'zowe.config.json');plans=dict(prepared)
        raw=plans.get(config_path) if config_path in plans else _read(config_path)
        require(raw is not None,'Import the exact project config or create the selected profiles first')
        config_doc=decode(raw,MAX_CONFIG);schema_path=project_schema_path(root,config_doc)
        schema_raw=plans.get(schema_path) if schema_path in plans else _read(schema_path)
        _profile_checks(config_doc,settings,decode(schema_raw,MAX_CONFIG) if schema_raw is not None else None)
    if db2 is not None:
        if db2['mode']=='existing':require(settings['db2_metadata_url'],'Supply the approved existing Db2 MCP endpoint')
        elif db2['mode']=='gateway':
            from .db2_setup import prepare_db2
            _,gateway_files=prepare_db2(root,location=db2['location'],database=db2['database'],host=db2['host'],port=db2['port'],
                                        max_rows=db2['row_limit'],certificate_source=db2['certificate_file'],driver=db2['driver'])
            prepared+=gateway_files
            env_path=safe_path(root,'.env')
            if baseline[env_path] is None and db2['database']==db2['location']:
                prepared.append((env_path,_db2_env_template(db2)))
    mcp,managed=_claude_plan(root,choices,settings,managed,origin);prepared+=mcp
    prepared += [(settings_path,encode(settings_doc)), (safe_path(root,'.migration/connections.json'),encode({'version':2,'choices':choices,'managed':managed}))]
    prepared.append((safe_path(root,'.migration/workstation.md'), workstation_markdown(root, settings, choices)))
    before={path:baseline[path] for path,_ in prepared};changed=[]
    try:
        require(all(_read(path)==raw for path,raw in baseline.items()),'Configuration changed during planning; reload before retrying Save')
        for path,payload in prepared:
            require(_read(path)==before[path],'Configuration changed during Save; reload before retrying')
            if before[path]!=payload:
                atomic_bytes(path,payload);changed.append((path,payload))
        view['connection_setup']=inspect_connections(root,settings,origin)
        view['workflow']['claude_mcp_servers']=view['connection_setup']['claude_mcp_servers']
        view['instructions']=inspect_workstation_instructions(root,settings)
        expected={**baseline,**dict(prepared)}
        require(all(_read(path)==payload for path,payload in expected.items()) and view['instructions']['status']=='READY',
                'Configuration changed after publication; reload before retrying Save')
    except Exception:
        require(all(_read(path)==payload for path,payload in changed),
                'Configuration changed during failed Save; preserve files and inspect the local setup')
        for path,payload in reversed(changed):
            require(_read(path)==payload,'Configuration changed during rollback; preserve files and inspect the local setup')
            if before[path] is None:path.unlink()
            else:atomic_bytes(path,before[path])
        raise
    return view
