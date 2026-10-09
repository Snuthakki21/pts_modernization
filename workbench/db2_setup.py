"""Nonsecret local Db2 settings; runtime credentials come from private environment."""
from .domain import path_is_link
import argparse
import json
from pathlib import Path

from .domain import ValidationError, atomic_bytes, decode, encode, require, safe_path
from .layout import require_layout
from .zowe_setup import _host

CERTIFICATE='certificates/DB2-CA.cert'
PLACEHOLDER=b'PLACEHOLDER ONLY - replace locally with your approved Db2 CA certificate.\nThis file is not a valid certificate and must never establish connectivity.\n'
ENVIRONMENT={'user':'WB_DB2_USER','password':'WB_DB2_PASSWORD'}
CONFIG_KEYS=frozenset({'server_name','location','database','host','port','ssl','certificate','driver',
                       'max_rows','default_row_budget','credential_environment'})


def _text(value):
    require(isinstance(value,str) and 0<len(value)<=253 and not any(ord(c)<32 for c in value),
            'Db2 connection fields must contain bounded local text')
    return value


def _config(config):
    require(isinstance(config,dict) and set(config)<=CONFIG_KEYS,
            'Db2 configuration permits only the documented nonsecret connection fields')
    require(config.get('credential_environment')==ENVIRONMENT,
            'Db2 credentials must use the fixed private environment variable names')
    require(config.get('ssl') is True and config.get('certificate')==CERTIFICATE,
            'Db2 SSL and the fixed certificate path are required')
    maximum=config.get('max_rows');default=config.get('default_row_budget')
    require(type(maximum)is int and 1<=maximum<=500000,'Db2 row budget must be 1..500000')
    require(type(default)is int and 1<=default<=maximum,'Default Db2 read budget must fit the configured maximum')
    for key in ('server_name','location','database','driver'):
        if config.get(key) is not None:_text(config[key])
    if config.get('host') is not None:_host(config['host'])
    port=config.get('port');require(port is None or type(port)is int and 1<=port<=65535,'Db2 port must be 1..65535')
    return config


def prepare_db2(workspace,server_name=None,location=None,database=None,host=None,port=None,max_rows=None,certificate_source=None,driver=None):
    workspace=Path(workspace).absolute();require_layout(workspace)
    path=safe_path(workspace,'.migration/db2-config.json')
    require(not path.exists() or path.is_file() and path.stat().st_size<=1024*1024,
            'Selected Db2 config must be a regular bounded JSON file')
    from .db2_env import _read, MAX_CERT_BYTES, validate_certificate
    config=decode(_read(path,1024*1024),1024*1024) if path.exists() else {}
    require(isinstance(config,dict) and set(config)<=CONFIG_KEYS,
            'Db2 configuration permits only the documented nonsecret connection fields')
    defaults={'server_name':None,'location':None,'database':None,'host':None,'port':None,'ssl':True,
              'certificate':CERTIFICATE,'driver':'IBM DB2 ODBC DRIVER','max_rows':500000,
              'default_row_budget':1000,'credential_environment':ENVIRONMENT.copy()}
    for key,value in defaults.items():config.setdefault(key,value)
    for key,value in (('server_name',server_name),('location',location),('database',database),('driver',driver)):
        if value is not None:config[key]=_text(value)
    if host is not None:config['host']=_host(host)
    if port is not None:config['port']=port
    if max_rows is not None:
        require(type(max_rows)is int and 1<=max_rows<=500000,'Db2 row budget must be 1..500000')
        config['max_rows']=max_rows
        if type(config['default_row_budget'])is int:config['default_row_budget']=min(config['default_row_budget'],max_rows)
    require(config.get('ssl') is True and config.get('certificate')==CERTIFICATE,
            'SSL must remain enabled with the fixed approved CA certificate path')
    require(config['port'] is None or type(config['port']) is int and 1<=config['port']<=65535,'Db2 port must be 1..65535')
    _config(config)
    certificate=safe_path(workspace,CERTIFICATE)
    require(not certificate.exists() or certificate.is_file() and certificate.stat().st_size<=1024*1024,
            'Certificate must be a regular bounded file')
    prepared=[]
    certificate_bytes=_read(certificate,MAX_CERT_BYTES) if certificate.exists() else PLACEHOLDER
    if certificate_source is not None:
        certificate_bytes=_read(Path(certificate_source),MAX_CERT_BYTES)
        validate_certificate(certificate_bytes)
    if not certificate.exists() or certificate_source is not None:prepared.append((certificate,certificate_bytes))
    prepared.append((path,encode(config)))
    return {'status':'NEEDS_LOCAL_CONFIGURATION','config_file':str(path),'certificate':str(certificate),
            'certificate_placeholder':certificate_bytes==PLACEHOLDER,'ssl':True,'max_rows':config['max_rows'],
            'credentials':'UNVERIFIED','connectivity':'UNVERIFIED',
            'environment':{'WB_DB2_CONFIG':str(path),'user_variable':'WB_DB2_USER','password_variable':'WB_DB2_PASSWORD'},
            'guidance':'Fill actual nonsecret server/location/database/host/port locally. Replace DB2-CA.cert with '
                       'the approved CA certificate. Set credentials only in private local environment or the '
                       'approved external driver. Start the typed read-only gateway separately; this template does not authenticate.'},prepared


def initialize_db2(workspace,server_name=None,location=None,database=None,host=None,port=None,max_rows=None):
    result,prepared=prepare_db2(workspace,server_name,location,database,host,port,max_rows)
    for path,payload in prepared:atomic_bytes(path,payload)
    require_layout(workspace)
    return result


def _odbc(value):return '{'+str(value).replace('}','}}')+'}'


def connection_fields(config):
    """Require usable nonsecret driver fields before requesting credentials."""
    _config(config)
    host=_host(config.get('host'));database=_text(config.get('database'));driver=_text(config.get('driver'))
    port=config.get('port');require(type(port)is int and 1<=port<=65535,'Supply the actual Db2 port locally')
    return host,database,driver,port


def load_connection(config_file,env=None):
    """Build an in-memory SSL connection string. Never persist or return it in diagnostics."""
    import os
    env=os.environ if env is None else env
    path=Path(config_file).absolute()
    require(not path_is_link(path) and not any(path_is_link(parent) for parent in path.parents)
            and path.is_file() and path.stat().st_size<=1024*1024,'Select a regular bounded local Db2 config')
    config=_config(decode(path.read_bytes(),1024*1024))
    host,database,driver,port=connection_fields(config)
    workspace=path.parent.parent if path.parent.name=='.migration' else path.parent
    certificate=safe_path(workspace,CERTIFICATE)
    require(certificate.is_file() and certificate.stat().st_size<=1024*1024,'Supply the approved bounded Db2 CA certificate')
    from .db2_env import _read, MAX_CERT_BYTES, validate_certificate
    try:validate_certificate(_read(certificate,MAX_CERT_BYTES))
    except ValidationError:raise ValidationError('Replace the certificate placeholder with the actual approved PEM or DER CA certificate') from None
    user=env.get('WB_DB2_USER');password=env.get('WB_DB2_PASSWORD')
    require(isinstance(user,str) and 0<len(user)<=2048 and isinstance(password,str) and 0<len(password)<=8192,
            'Supply Db2 credentials only through the private local credential environment')
    require(not any(ord(c)<32 for c in user+password),'Unsupported credential control character')
    values={'DRIVER':driver,'DATABASE':database,'HOSTNAME':host,'PORT':port,'PROTOCOL':'TCPIP',
            'SECURITY':'SSL','SSLServerCertificate':str(certificate),'SSLClientHostnameValidation':'Basic',
            'UID':user,'PWD':password}
    return ';'.join(key+'='+_odbc(value) for key,value in values.items())+';'


def configured_max_rows(config_file):
    path=Path(config_file).absolute()
    require(not path_is_link(path) and not any(path_is_link(parent) for parent in path.parents)
            and path.is_file() and path.stat().st_size<=1024*1024,'Select a regular bounded local Db2 config')
    return _config(decode(path.read_bytes(),1024*1024))['max_rows']


# The local file-first path does not use a listening HTTP port or bearer token.
DEFAULT_DRIVER = 'IBM DB2 ODBC DRIVER'


def _stdio_driver(value):
    from .db2_env import _text
    value = _text(value, 253)
    require('${' not in value, 'The approved registered driver must be literal text')
    return value


def stdio_binding(workspace, driver=DEFAULT_DRIVER, *, repository=None):
    """A fixed installed repository program; no arbitrary commands or env grants."""
    import os
    from .db2_env import _path
    root = _path(Path(workspace))
    repo = _path(Path(repository) if repository is not None else Path(__file__).resolve().parents[1])
    python = repo / ('.venv/Scripts/python.exe' if os.name == 'nt' else '.venv/bin/python')
    script = safe_path(repo, 'tools/db2_mcp_server.py')
    env = safe_path(root, '.env')
    arguments = [str(script), '--transport', 'stdio']
    if driver != DEFAULT_DRIVER:
        arguments += ['--driver', _stdio_driver(driver)]
    arguments += ['--env-file', str(env), '--workspace', str(root)]
    require(not any('${' in value for value in [str(python), *arguments]),
            'Managed stdio paths must not contain environment expansion syntax')
    return {'type': 'stdio', 'command': str(python), 'args': arguments}


def validate_stdio_binding(entry, workspace, *, repository=None):
    """Validate one exact managed command, return only noncredential facts."""
    require(isinstance(entry, dict) and set(entry) == {'type', 'command', 'args'}
            and entry.get('type') == 'stdio' and isinstance(entry.get('args'), list),
            'The managed Db2 stdio binding requires the fixed repository program')
    args = entry['args']
    driver = DEFAULT_DRIVER
    if len(args) == 9 and args[3] == '--driver':
        driver = _stdio_driver(args[4])
    require(entry == stdio_binding(workspace, driver, repository=repository),
            'The managed Db2 stdio binding differs from the fixed repository program or workspace')
    return {'transport': 'stdio', 'driver': driver, 'authentication': 'UNVERIFIED',
            'connectivity': 'UNVERIFIED'}


def validate_managed_mcp(document, workspace, *, repository=None):
    """Select only the approved typed Db2 entry; saved other bindings stay inert."""
    from urllib.parse import urlsplit
    from .connectors import endpoint as validate_endpoint
    require(isinstance(document, dict) and set(document) == {'mcpServers'}
            and isinstance(document['mcpServers'], dict), 'Correct the local Claude MCP structure')
    entry = document['mcpServers'].get('workbench-db2')
    if entry is None:
        return {'mcpServers': {}}
    require(isinstance(entry, dict), 'Correct the managed typed Db2 binding')
    if entry.get('type') == 'stdio':
        validate_stdio_binding(entry, workspace, repository=repository)
    else:
        require(entry.get('type') == 'http' and set(entry) <= {'type', 'url', 'headers'}
                and isinstance(entry.get('url'), str), 'Use the approved typed Db2 HTTP or managed stdio binding')
        validate_endpoint(entry['url'])
        endpoint = urlsplit(entry['url'])
        require(not endpoint.query, 'The approved MCP endpoint must not include credential or query parameters')
        headers = entry.get('headers')
        require(headers is None or headers == {'Authorization': 'Bearer ${WB_DB2_MCP_TOKEN}'},
                'Private bearer credentials must remain in process memory')
        require(endpoint.scheme != 'http' or headers is not None,
                'Loopback Db2 HTTP must retain its private bearer authentication')
    return {'mcpServers': {'workbench-db2': entry}}


def inspect_stdio_binding(workspace):
    """Safe operator projection without reading .env credentials or calling tools."""
    from .db2_env import _read
    root = Path(workspace).absolute()
    path = safe_path(root, '.mcp.json')
    document = decode(_read(path, 1024 * 1024), 1024 * 1024)
    require(isinstance(document, dict) and set(document) == {'mcpServers'}
            and isinstance(document['mcpServers'], dict), 'Correct the local Claude MCP structure')
    result = validate_stdio_binding(document['mcpServers'].get('workbench-db2'), root)
    return {**result, 'configured': True, 'config_file': str(path),
            'env_file': str(safe_path(root, '.env')), 'certificate': str(safe_path(root, CERTIFICATE))}


def prepare_environment(workspace, env_file=None, *, driver=DEFAULT_DRIVER, replace_managed_http=False):
    """Validate private local files and prepare Claude stdio, without a connection.

    Existing unrelated bindings and file bytes are preserved. A different managed
    entry requires an explicit hash-bound HTTP migration; arbitrary entries can
    never be authorized with that switch. This helper never writes credentials,
    changes process evidence, launches clients or starts a second Coordinator.
    """
    from .db2_env import _path, _read, read_workspace_env, settings, validate_certificate, MAX_CERT_BYTES
    from .domain import sha
    from .local_agent import _publish
    root = _path(Path(workspace)); require_layout(root)
    require(root.is_dir(), 'Create the local workspace directory before Db2 setup')
    selected = safe_path(root, '.env')
    require(env_file is None or _path(Path(env_file)) == selected,
            'Keep the shared private .env at the workspace root, outside .migration')
    require(selected.is_file(), 'Create the private .env at the workspace root using .env.example')
    values = read_workspace_env(selected)
    required = ('DB2_LOCATION_NAME', 'DB2_DATABASE', 'DB2_HOSTNAME', 'DB2_PORT', 'DB2_SSL_CONNECTION', 'DB2_SSL_SERVER_CERTIFICATE')
    missing_fields = [key for key in required if not values.get(key)]
    require(not missing_fields, 'Fill the required fields locally in the private .env: ' + ', '.join(missing_fields))
    require(values.get('DB2_SSL_SERVER_CERTIFICATE') == CERTIFICATE,
            'Set DB2_SSL_SERVER_CERTIFICATE=certificates/DB2-CA.cert relative to the workspace .env')
    configured = settings({}, selected, canonical=True)
    certificate = safe_path(root, CERTIFICATE)
    try:
        validate_certificate(_read(certificate, MAX_CERT_BYTES))
    except (ValidationError, OSError):
        raise ValidationError('Place the actual approved PEM or DER Db2 CA certificate in certificates/DB2-CA.cert; .migration is not the CA folder') from None
    entry = stdio_binding(root, driver)
    path = safe_path(root, '.mcp.json')
    original = _read(path, 1024 * 1024) if path.exists() else None
    document = decode(original, 1024 * 1024) if original is not None else {'mcpServers': {}}
    require(isinstance(document, dict) and set(document) == {'mcpServers'}
            and isinstance(document['mcpServers'], dict), 'Correct the local Claude MCP structure; existing bytes are preserved')
    old = document['mcpServers'].get('workbench-db2')
    state_path = safe_path(root, '.migration/connections.json')
    backup_path = safe_path(root, '.migration/db2-previous-http.json')
    state_raw = None
    state = None
    migration = old is not None and old != entry
    if migration:
        require(replace_managed_http, 'Existing Db2 binding is preserved; use --replace-managed-http only for the unchanged Workbench-managed HTTP binding')
        require(isinstance(old, dict) and old.get('type') == 'http', 'Only an unchanged Workbench-managed HTTP binding may migrate to stdio')
        validate_managed_mcp({'mcpServers': {'workbench-db2': old}}, root)
        state_raw = _read(state_path, 1024 * 1024)
        state = decode(state_raw, 1024 * 1024)
        require(isinstance(state, dict) and set(state) == {'version', 'choices', 'managed'}
                and state['version'] == 2 and isinstance(state['choices'], dict) and isinstance(state['managed'], dict)
                and state['managed'].get('workbench-db2') == sha(encode(old)),
                'The existing HTTP binding no longer matches its Workbench ownership receipt; preserve and resolve it locally')
        backup = encode({'mcpServers': {'workbench-db2': old}})
        require(not backup_path.exists() or _read(backup_path, 1024 * 1024) == backup,
                'A different prior HTTP backup exists; preserve and resolve it locally')
        from .connection_setup import validate_choices
        validate_choices(state['choices'])
        state['managed']['workbench-db2'] = sha(encode(entry))
    document['mcpServers']['workbench-db2'] = entry
    payload = encode(document, 1024 * 1024)
    written = []
    backup_owned = False
    try:
        require((_read(path, 1024 * 1024) if path.exists() else None) == original,
                'Claude MCP configuration changed during preparation; preserve the concurrent edit and retry')
        if migration:
            require(_read(state_path, 1024 * 1024) == state_raw,
                    'The connection ownership receipt changed during preparation; preserve the concurrent edit and retry')
            if not backup_path.exists():
                backup_owned = _publish(backup_path, backup)
                require(backup_owned or _read(backup_path, 1024 * 1024) == backup,
                        'The previous HTTP backup changed during preparation')
        if original is None:
            require(_publish(path, payload), 'Claude MCP configuration appeared during preparation; preserve it and retry')
            written.append((path, None, payload))
        elif old != entry:
            atomic_bytes(path, payload); written.append((path, original, payload))
        if migration:
            state_payload = encode(state)
            atomic_bytes(state_path, state_payload); written.append((state_path, state_raw, state_payload))
        require_layout(root)
    except BaseException:
        for changed, baseline, current in reversed(written):
            if changed.exists() and _read(changed, 1024 * 1024) == current:
                if baseline is None: changed.unlink()
                else: atomic_bytes(changed, baseline)
        if backup_owned and backup_path.exists() and _read(backup_path, 1024 * 1024) == backup:
            backup_path.unlink()
        raise
    missing = [key for key, value in (('DB2_USERNAME', configured.username), ('DB2_PASSWORD', configured.password)) if not value]
    return {'status': 'ACTION_REQUIRED' if missing else 'CONFIGURATION_PREPARED',
            'transport': 'stdio', 'config_file': str(path), 'env_file': str(selected),
            'certificate': str(certificate), 'driver': _stdio_driver(driver),
            'missing_credentials': missing, 'replaced_managed_http': migration,
            'authentication': 'UNVERIFIED', 'connectivity': 'UNVERIFIED',
            'guidance': 'Fill only missing DB2_USERNAME/DB2_PASSWORD locally in .env. Install the approved IBM Db2 ODBC driver and pyodbc, then run scripts/Start-Claude.ps1 and check /mcp. Stdio uses no bearer token or second server terminal.'}


def prepare_offline(workspace):
    """Prepare a no-server synthetic session without implying remote setup."""
    from .db2_env import _path, _read
    from .local_agent import _publish
    root = _path(Path(workspace)); require_layout(root)
    require(root.is_dir(), 'Create the local workspace directory before offline setup')
    path = safe_path(root, '.mcp.json')
    original = _read(path, 1024 * 1024) if path.exists() else None
    document = decode(original, 1024 * 1024) if original is not None else {'mcpServers': {}}
    require(isinstance(document, dict) and set(document) == {'mcpServers'}
            and isinstance(document['mcpServers'], dict), 'Correct the local Claude MCP structure')
    require('workbench-db2' not in document['mcpServers'],
            'Offline setup preserves the existing Db2 binding; choose a fresh synthetic workspace')
    if original is None:
        require(_publish(path, encode(document)), 'Claude MCP configuration appeared during preparation; preserve it and retry')
    require_layout(root)
    return {'status': 'OFFLINE_PREPARED', 'transport': 'none', 'config_file': str(path),
            'authentication': 'NOT_REQUESTED', 'connectivity': 'NOT_REQUESTED',
            'guidance': 'This is a synthetic session with no active Db2 MCP server. Run scripts/Start-Claude.ps1 for the approved local client.'}


def _write_runtime(workspace, output):
    """A launcher-only bounded filtered config; all arbitrary bindings stay inert."""
    from .db2_env import _path, _read
    from .local_agent import _publish
    import re
    root = _path(Path(workspace))
    destination = _path(Path(output))
    require(destination.parent == safe_path(root, '.migration')
            and re.fullmatch(r'claude-runtime-[A-Za-z0-9._-]+\.json', destination.name),
            'Claude runtime configuration belongs only in the selected workspace .migration folder')
    document = decode(_read(safe_path(root, '.mcp.json'), 1024 * 1024), 1024 * 1024)
    selected = validate_managed_mcp(document, root)
    require(_publish(destination, encode(selected, 1024 * 1024)), 'Claude runtime configuration already exists; do not overwrite it')
    return {'status': 'RUNTIME_PREPARED', 'transport': next(iter(selected['mcpServers'].values()), {}).get('type', 'none')}


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--workspace',default=str(Path.cwd()))
    parser.add_argument('--server-name');parser.add_argument('--location');parser.add_argument('--database')
    parser.add_argument('--host');parser.add_argument('--port',type=int);parser.add_argument('--max-rows',type=int)
    parser.add_argument('--env-file', help='Private shared .env at the workspace root; prepares local Claude stdio without a token')
    parser.add_argument('--driver', default=DEFAULT_DRIVER, help='Exact organization-approved registered IBM Db2 ODBC driver name')
    parser.add_argument('--replace-managed-http', action='store_true', help='Explicitly migrate only an unchanged hash-bound Workbench HTTP binding')
    parser.add_argument('--claude-runtime', help=argparse.SUPPRESS)
    parser.add_argument('--offline', action='store_true', help='Prepare a synthetic no-server session; no private connector values required')
    args=parser.parse_args(argv)
    try:
        if args.offline:
            require(not args.env_file and not args.claude_runtime and not args.replace_managed_http and args.driver == DEFAULT_DRIVER
                    and all(value is None for value in (args.server_name, args.location, args.database, args.host, args.port, args.max_rows)), 'Offline preparation does not accept live connection fields')
            result = prepare_offline(args.workspace)
        elif args.claude_runtime:
            result = _write_runtime(args.workspace, args.claude_runtime)
        elif args.env_file:
            require(all(value is None for value in (args.server_name, args.location, args.database, args.host, args.port, args.max_rows)), 'File-first setup reads the actual Db2 fields only from the private .env')
            result = prepare_environment(args.workspace, args.env_file, driver=args.driver, replace_managed_http=args.replace_managed_http)
        else:
            require(not args.replace_managed_http and args.driver == DEFAULT_DRIVER, 'Select --env-file for the private local stdio setup')
            result = initialize_db2(args.workspace,args.server_name,args.location,args.database,args.host,args.port,args.max_rows)
    except ValidationError as failure:
        print(json.dumps({'status':'BLOCKED','message':str(failure)}));return 2
    except OSError:
        print(json.dumps({'status':'BLOCKED','message':'Local setup files are unavailable; keep .env at the workspace root and approved CAs in certificates.'}));return 2
    print(json.dumps(result,indent=2));return 0


if __name__=='__main__':raise SystemExit(main())
