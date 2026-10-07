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


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--workspace',default=str(Path.cwd()))
    parser.add_argument('--server-name');parser.add_argument('--location');parser.add_argument('--database')
    parser.add_argument('--host');parser.add_argument('--port',type=int);parser.add_argument('--max-rows',type=int)
    args=parser.parse_args(argv)
    try:result=initialize_db2(args.workspace,args.server_name,args.location,args.database,args.host,args.port,args.max_rows)
    except (ValidationError,OSError):
        print(json.dumps({'status':'BLOCKED','message':'Db2 template setup failed; check local layout, nonsecret fields, row bound and SSL settings.'}));return 2
    print(json.dumps(result,indent=2));return 0


if __name__=='__main__':raise SystemExit(main())
