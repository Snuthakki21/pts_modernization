"""Fictional canonical workspace env preparation; no private values are emitted."""
import json,unittest
from unittest.mock import patch
import test_workstation_setup as workstation
from test_db2_env import CERTIFICATE
from workbench.db2_env import _parse

class WorkspaceDb2EnvTests(unittest.IsolatedAsyncioTestCase):
 asyncSetUp=workstation.WorkstationApiTests.asyncSetUp
 request=workstation.WorkstationApiTests.request
 def choices(self):
  return {'claude':True,'db2_auth':'bearer_env','zowe':{'mode':'off','host':None,'port':None,'config_file':None,'schema_file':None},'db2':{'mode':'gateway','host':'db2.example.invalid','port':5116,'database':'TESTLOC','location':'TESTLOC','driver':'IBM DB2 ODBC DRIVER','certificate_file':None,'mcp_port':8776,'row_limit':250}}
 async def save(self,choices=None):
  return await self.request('/api/setup/workstation','POST',{'settings':{'source_mode':'upload'},'connections':choices or self.choices()})
 async def test_canonical_save_creates_exact_eight_key_private_env_and_explicit_command(self):
  status,result=await self.save();self.assertEqual(status,200)
  path=self.root/'.env';self.assertTrue(path.is_file(),'Save must prepare canonical workspace .env')
  values=_parse(path.read_bytes())
  self.assertEqual(set(values),{'DB2_LOCATION_NAME','DB2_DATABASE','DB2_HOSTNAME','DB2_PORT','DB2_USERNAME','DB2_PASSWORD','DB2_SSL_CONNECTION','DB2_SSL_SERVER_CERTIFICATE'})
  self.assertEqual(values['DB2_DATABASE'],values['DB2_LOCATION_NAME']);self.assertEqual(values['DB2_SSL_CONNECTION'],'true')
  self.assertEqual((values['DB2_USERNAME'],values['DB2_PASSWORD']),('',''))
  command=next(x['command'] for x in result['connection_setup']['commands'] if x['id']=='db2_start')
  self.assertIn('--env-file',command);self.assertIn(str(path),command);self.assertIn('--config',command)
  self.assertFalse(result['readiness']['connectivity_verified'])
 async def test_preserved_auth_bytes_are_not_in_status_or_markdown(self):
  await self.save();path=self.root/'.env';self.assertTrue(path.exists())
  raw=path.read_bytes().replace(b'DB2_USERNAME=',b'DB2_USERNAME="PRIVATE_USER_SENTINEL"').replace(b'DB2_PASSWORD=',b'DB2_PASSWORD="PRIVATE_PASSWORD_SENTINEL"')
  path.write_bytes(raw);status,result=await self.save();self.assertEqual(status,200);self.assertEqual(path.read_bytes(),raw)
  text=json.dumps(result)+(self.root/'.migration/workstation.md').read_text()
  self.assertNotIn('PRIVATE_USER_SENTINEL',text);self.assertNotIn('PRIVATE_PASSWORD_SENTINEL',text)
  self.assertIn('db2_env',[x['kind'] for x in result['connection_setup']['files']])
 async def test_existing_env_structure_mismatch_is_preserved_and_named(self):
  await self.save();path=self.root/'.env';self.assertTrue(path.exists());raw=path.read_bytes().replace(b'db2.example.invalid',b'other.example.invalid');path.write_bytes(raw)
  _,result=await self.save();self.assertEqual(path.read_bytes(),raw)
  self.assertIn('db2_env',[x['id'] for x in result['connection_setup']['remaining']])
 async def test_existing_env_unknown_private_fields_report_no_values(self):
  path=self.root/'.env';raw=b'CUSTOM_PRIVATE_KEY=PRIVATE_VALUE_SENTINEL\r\n';path.write_bytes(raw)
  status,result=await self.save();self.assertEqual(status,200);self.assertEqual(path.read_bytes(),raw)
  self.assertIn('db2_env',[x['id'] for x in result['connection_setup']['remaining']]);self.assertNotIn('PRIVATE_VALUE_SENTINEL',json.dumps(result));self.assertNotIn('CUSTOM_PRIVATE_KEY',json.dumps(result))
 async def test_external_server_and_off_do_not_prepare_env(self):
  for mode in ('off','existing'):
   choices=self.choices();choices['db2']={k:(mode if k=='mode' else None) for k in choices['db2']}
   status,_=await self.request('/api/setup/workstation','POST',{'settings':{'source_mode':'upload',**({'db2_metadata_url':'https://approved.example.invalid/mcp'} if mode=='existing' else {})},'connections':choices})
   self.assertEqual(status,200);self.assertFalse((self.root/'.env').exists())
 async def test_env_publication_failure_rolls_back_prepared_config(self):
  from workbench import connection_setup
  original=connection_setup.atomic_bytes
  def fail(path,payload):
   if path.name=='.env':raise OSError('Fictional disk failure')
   return original(path,payload)
  with patch.object(connection_setup,'atomic_bytes',side_effect=fail):
   status,_=await self.save()
  self.assertNotEqual(status,200);self.assertFalse((self.root/'.env').exists());self.assertFalse((self.root/'.mcp.json').exists());self.assertFalse((self.root/'.migration/db2-config.json').exists())
 async def test_valid_certificate_copy_and_canonical_path_are_consistent(self):
  cert=self.export/'approved CA.cer';cert.write_text(CERTIFICATE);choices=self.choices();choices['db2']['certificate_file']=str(cert)
  _,result=await self.save(choices);path=self.root/'.env';self.assertTrue(path.exists());values=_parse(path.read_bytes());self.assertEqual((self.root/values['DB2_SSL_SERVER_CERTIFICATE']).read_bytes(),cert.read_bytes())
  self.assertNotIn('db2_certificate',[x['id'] for x in result['connection_setup']['remaining']])
