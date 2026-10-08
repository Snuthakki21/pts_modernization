"""Configuration preparation is distinct from authentication and client activation."""
import json
import random
import secrets
from pathlib import Path
from unittest.mock import patch

import unittest
import test_workstation_setup as workstation_tests


class ConnectionSetupTests(unittest.IsolatedAsyncioTestCase):
    asyncSetUp = workstation_tests.WorkstationApiTests.asyncSetUp
    request = workstation_tests.WorkstationApiTests.request
    def choices(self, mode='create', copilot=True):
        return {'copilot':copilot,'zowe':{'mode':mode,'host':'zosmf.example.test','port':443,
                                         'config_file':None,'schema_file':None}}

    async def configure(self, choices=None, **settings):
        return await self.request('/api/setup/workstation', 'POST', {
            'settings':{'source_mode':'upload','zowe_profile':'factory_base',
                        'zowe_zosmf_profile':'factory_zosmf',**settings},
            'connections':choices or self.choices()})

    async def test_one_save_prepares_profiles_and_only_copilot_retrieval_mcp(self):
        status, result = await self.configure()
        self.assertEqual(status,200)
        config=json.loads((self.root/'zowe.config.json').read_bytes())
        self.assertEqual(config['profiles']['factory_base']['properties']['host'],'zosmf.example.test')
        self.assertEqual(config['profiles']['factory_base']['secure'],['user','password'])
        self.assertTrue(config['profiles']['factory_zosmf']['properties']['rejectUnauthorized'])
        mcp=json.loads((self.root/'.vscode/mcp.json').read_bytes())
        bridge=mcp['servers']['workbench-retrieval']
        self.assertEqual(bridge['args'][-2:],['--role','retrieval'])
        self.assertTrue(Path(bridge['command']).is_absolute())
        self.assertFalse((self.root/'.claude/mcp.json').exists())
        self.assertEqual(result['connection_setup']['connectivity'],'UNVERIFIED')
        self.assertEqual(result['connection_setup']['claude_mcp_servers'],0)
        self.assertEqual(result['connection_setup']['status'],'ACTION_REQUIRED')
        _, reloaded=await self.request('/api/setup/workstation')
        self.assertEqual(reloaded['connection_setup']['choices'],result['connection_setup']['choices'])

    async def test_twenty_runtime_randomized_profiles_round_trip_with_existing_settings(self):
        rng=random.Random(secrets.randbits(63)); witnesses=set()
        for _ in range(20):
            suffix=str(rng.randrange(10**8,10**9));choices=self.choices()
            choices['zowe'].update(host='host-'+suffix+'.example.test',port=rng.randrange(1024,65536))
            status, result=await self.configure(choices,zowe_profile='b_'+suffix,zowe_zosmf_profile='s_'+suffix)
            self.assertEqual(status,200)
            config=json.loads((self.root/'zowe.config.json').read_bytes())
            self.assertEqual(config['profiles']['b_'+suffix]['properties'],{'host':choices['zowe']['host'],'port':choices['zowe']['port']})
            witnesses.add(suffix)
        self.assertEqual(len(witnesses),20)
        self.assertEqual(len(config['profiles']),40)

    async def test_existing_approved_jsonc_servers_and_secret_placeholders_are_preserved(self):
        p=self.root/'.vscode/mcp.json';p.parent.mkdir()
        p.write_text('{// supplied organization binding\n"servers":{"approved":{"type":"http","url":"https://approved.test/mcp","headers":{"X-Private":"keep-private"},},},"inputs":[],}',encoding='utf-8')
        status, result=await self.configure()
        self.assertEqual(status,200)
        self.assertEqual(json.loads(p.read_bytes())['servers']['approved']['headers']['X-Private'],'keep-private')
        self.assertNotIn('keep-private',json.dumps(result))

    async def test_rejected_invalid_config_preserves_all_prior_files(self):
        await self.configure();files=[self.root/'.migration/workstation.json',self.root/'.migration/connections.json',self.root/'zowe.config.json',self.root/'.vscode/mcp.json']
        before={p:p.read_bytes() for p in files};choices=self.choices();choices['zowe']['port']=True
        status,_=await self.configure(choices)
        self.assertEqual(status,400)
        self.assertEqual({p:p.read_bytes() for p in files},before)

    async def test_conflicting_managed_server_is_preserved_without_partial_profile_write(self):
        p=self.root/'.vscode/mcp.json';p.parent.mkdir()
        raw=b'{"servers":{"workbench-retrieval":{"type":"http","url":"https://approved.test/mcp"}}}'
        p.write_bytes(raw);status,_=await self.configure()
        self.assertEqual(status,400);self.assertEqual(p.read_bytes(),raw)
        self.assertFalse((self.root/'zowe.config.json').exists())
        self.assertFalse((self.root/'.migration/workstation.json').exists())

    async def test_exact_config_and_schema_import_requires_selected_aliases(self):
        config=self.export/'supplied.json';schema=self.export/'schema.json'
        raw=b'{\r\n "profiles": {"factory_base":{"type":"base","properties":{"host":"zosmf.test","port":443},"secure":["user","password"]},"factory_zosmf":{"type":"zosmf","properties":{"protocol":"https","rejectUnauthorized":true}}},"defaults":{"base":"factory_base","zosmf":"factory_zosmf"}\r\n}\r\n'
        config.write_bytes(raw);schema.write_bytes(b'{"type":"object","required":["profiles"]}\r\n')
        choices=self.choices('import');choices['zowe'].update(config_file=str(config),schema_file=str(schema),host=None,port=None)
        status,_=await self.configure(choices)
        self.assertEqual(status,200);self.assertEqual((self.root/'zowe.config.json').read_bytes(),raw)
        self.assertEqual((self.root/'zowe.schema.json').read_bytes(),schema.read_bytes())
        _, result=await self.request('/api/setup/workstation')
        self.assertTrue(any(file['kind']=='zowe_schema' and file['path']==str(self.root/'zowe.schema.json') for file in result['connection_setup']['files']))

    async def test_import_with_missing_alias_or_inline_credentials_writes_nothing(self):
        config=self.export/'bad.json';choices=self.choices('import');choices['zowe'].update(config_file=str(config),host=None,port=None)
        for doc in [{'profiles':{}},{'profiles':{'factory_base':{'type':'base','properties':{'password':'private'}}}}]:
            config.write_bytes(json.dumps(doc).encode());status, response=await self.configure(choices)
            self.assertEqual(status,400);self.assertNotIn('private',json.dumps(response))
            self.assertFalse((self.root/'zowe.config.json').exists())

    async def test_turning_off_removes_only_unchanged_managed_server(self):
        await self.configure();p=self.root/'.vscode/mcp.json';doc=json.loads(p.read_bytes())
        doc['servers']['approved']={'type':'http','url':'https://approved.test/mcp'};p.write_bytes(json.dumps(doc).encode())
        choices=self.choices('off',False);choices['zowe'].update(host=None,port=None)
        status,_=await self.configure(choices,zowe_profile=None,zowe_zosmf_profile=None)
        self.assertEqual(status,200);self.assertEqual(json.loads(p.read_bytes())['servers'],{'approved':doc['servers']['approved']})

    async def test_setup_never_runs_a_cli_or_network_call(self):
        with patch('subprocess.Popen',side_effect=AssertionError('No CLI in setup')),patch('urllib.request.urlopen',side_effect=AssertionError('No host access')):
            status,_=await self.configure();self.assertEqual(status,200)

    async def test_disk_failure_rolls_back_generated_configuration(self):
        from workbench.domain import atomic_bytes
        count=0
        def failed(path,payload):
            nonlocal count
            count+=1
            if count==3:raise OSError('disk full')
            atomic_bytes(path,payload)
        with patch('workbench.connection_setup.atomic_bytes',side_effect=failed):
            status,_=await self.configure()
        self.assertEqual(status,500)
        self.assertFalse((self.root/'zowe.config.json').exists())
        self.assertFalse((self.root/'.vscode/mcp.json').exists())
        self.assertFalse((self.root/'.migration/workstation.json').exists())

    async def test_secret_and_claude_server_fields_are_rejected(self):
        for field in ['password','token','claude_mcp_servers','command']:
            choices=self.choices();choices[field]='private'
            status,response=await self.configure(choices)
            self.assertEqual(status,400);self.assertNotIn('private',json.dumps(response))

    async def test_generated_db2_binding_uses_vscode_password_prompt(self):
        status,_=await self.configure(db2_metadata_url='https://approved.test/mcp')
        self.assertEqual(status,200);config=json.loads((self.root/'.vscode/mcp.json').read_bytes())
        self.assertEqual(config['servers']['workbench-db2']['headers']['Authorization'],'Bearer ${input:workbenchDb2Token}')
        self.assertTrue(config['inputs'][0]['password'])

    async def test_symlink_config_destination_rejected_without_target_access(self):
        p=self.root/'.vscode';p.symlink_to(self.export,target_is_directory=True)
        status,_=await self.configure();self.assertEqual(status,400)
        self.assertEqual(list(self.export.iterdir()),[])
        self.assertFalse((self.root/'zowe.config.json').exists())

    async def test_inherited_insecure_tls_and_invalid_native_port_fail_closed(self):
        config=self.export/'security.json';choices=self.choices('import');choices['zowe'].update(config_file=str(config),host=None,port=None)
        for props in [{'host':'zosmf.test','port':True},{'host':'zosmf.test','port':443,'protocol':'http'},
                      {'host':'zosmf.test','port':443,'rejectUnauthorized':False}]:
            doc={'profiles':{'factory_base':{'type':'base','properties':props,'secure':['user','password']},
                              'factory_zosmf':{'type':'zosmf','properties':{}}}}
            config.write_bytes(json.dumps(doc).encode());status,_=await self.configure(choices)
            self.assertEqual(status,400)
            self.assertFalse((self.root/'zowe.config.json').exists())

    async def test_broken_connector_file_does_not_hide_repairable_setup_form(self):
        await self.configure();p=self.root/'.vscode/mcp.json';p.write_bytes(b'not valid json')
        status,result=await self.request('/api/setup/workstation')
        self.assertEqual(status,200)
        self.assertEqual(result['connection_setup']['status'],'ACTION_REQUIRED')
        self.assertTrue(result['connection_setup']['remaining'])
        self.assertEqual(result['settings']['zowe_profile'],'factory_base')

    async def test_nested_inherited_host_config_is_preserved_and_selected(self):
        config=self.export/'nested.json';raw=json.dumps({'profiles':{
            'parent':{'type':'base','properties':{'host':'zosmf.test','port':443},'profiles':{
                'b':{'type':'base','secure':['user','password']},'s':{'type':'zosmf','properties':{'protocol':'https'}}}}}}).encode()
        config.write_bytes(raw);choices=self.choices('import');choices['zowe'].update(config_file=str(config),host=None,port=None)
        status,_=await self.configure(choices,zowe_profile='parent.b',zowe_zosmf_profile='parent.s')
        self.assertEqual(status,200);self.assertEqual((self.root/'zowe.config.json').read_bytes(),raw)

    async def test_external_dynamic_schema_reference_is_never_fetched(self):
        config=self.export/'selected.json';schema=self.export/'schema.json'
        config.write_bytes(b'{"profiles":{"factory_base":{"type":"base","properties":{"host":"zosmf.test","port":443}},"factory_zosmf":{"type":"zosmf"}}}')
        choices=self.choices('import');choices['zowe'].update(config_file=str(config),schema_file=str(schema),host=None,port=None)
        for key in ['$ref','$dynamicRef','$recursiveRef']:
            schema.write_bytes(json.dumps({key:'http://127.0.0.1:1/should-not-fetch'}).encode())
            with patch('urllib.request.urlopen',side_effect=AssertionError('No schema download')):
                status,_=await self.configure(choices)
            self.assertEqual(status,400);self.assertFalse((self.root/'zowe.config.json').exists())

    async def test_connector_disabled_preserves_shared_vscode_input_references(self):
        await self.configure(db2_metadata_url='https://approved.test/mcp')
        p=self.root/'.vscode/mcp.json';doc=json.loads(p.read_bytes())
        doc['servers']['approved']={'type':'http','url':'https://other.test/mcp','headers':{'Authorization':'Bearer ${input:workbenchDb2Token}'}}
        p.write_bytes(json.dumps(doc).encode());choices=self.choices('off',False);choices['zowe'].update(host=None,port=None)
        status,_=await self.configure(choices,zowe_profile=None,zowe_zosmf_profile=None,db2_metadata_url=None)
        self.assertEqual(status,200);saved=json.loads(p.read_bytes())
        self.assertEqual([item['id'] for item in saved['inputs']],['workbenchDb2Token'])
        self.assertEqual(set(saved['servers']),{'approved'})

    async def test_turning_zowe_off_clears_saved_retrieval_aliases(self):
        await self.configure();choices=self.choices('off',False);choices['zowe'].update(host=None,port=None)
        status,result=await self.configure(choices)
        self.assertEqual(status,200)
        self.assertIsNone(result['settings']['zowe_profile'])
        self.assertIsNone(result['settings']['zowe_zosmf_profile'])
        from workbench.setup import workstation_environment
        self.assertNotIn('WB_ZOWE_PROFILE',workstation_environment(self.root))

    async def test_file_changed_during_planning_is_preserved_without_any_write(self):
        await self.configure();p=self.root/'.vscode/mcp.json';before_settings=(self.root/'.migration/workstation.json').read_bytes()
        from workbench.connection_setup import _copilot_plan
        def concurrent(*args):
            result=_copilot_plan(*args)
            config=json.loads(p.read_bytes());config['servers']['concurrent-approved']={'type':'http','url':'https://approved.test/mcp'}
            p.write_bytes(json.dumps(config).encode())
            return result
        with patch('workbench.connection_setup._copilot_plan',side_effect=concurrent):
            status,_=await self.configure(source_mode='folder',source_folder=str(self.export))
        self.assertEqual(status,400)
        self.assertIn('concurrent-approved',json.loads(p.read_bytes())['servers'])
        self.assertEqual((self.root/'.migration/workstation.json').read_bytes(),before_settings)

    async def test_unknown_schema_dialect_is_rejected_before_publication(self):
        config=self.export/'selected.json';schema=self.export/'schema.json'
        config.write_bytes(b'{"profiles":{"factory_base":{"type":"base","properties":{"host":"zosmf.test","port":443}},"factory_zosmf":{"type":"zosmf"}}}')
        schema.write_bytes(b'{"$schema":"https://unsupported.test/schema","type":"object"}')
        choices=self.choices('import');choices['zowe'].update(config_file=str(config),schema_file=str(schema),host=None,port=None)
        status,_=await self.configure(choices)
        self.assertEqual(status,400);self.assertFalse((self.root/'zowe.config.json').exists())

    async def test_cli_inspection_reports_unsupported_schema_dialect(self):
        await self.configure();(self.root/'zowe.schema.json').write_bytes(b'{"$schema":"https://unsupported.test/schema"}')
        from workbench.zowe_setup import inspect_project_config
        result=inspect_project_config(self.root)
        self.assertEqual(result['schema'],'UNSUPPORTED_DIALECT')
        self.assertIn('Unsupported project schema dialect',result['issues'])

    async def test_windows_copy_commands_quote_paths_and_use_native_zowe_node(self):
        from workbench.connection_setup import inspect_connections
        await self.configure()
        argv=['C:\\Approved Node\\node.exe','C:\\Zowe CLI\\lib\\main.js','config','secure']
        with patch('workbench.connection_setup.sys.platform','win32'),patch('workbench.connection_setup.shutil.which',return_value='zowe.cmd'),patch('workbench.connectors.zowe_command',return_value=argv):
            result=inspect_connections(self.root,{'zowe_profile':'factory_base','zowe_zosmf_profile':'factory_zosmf','db2_metadata_url':None})
        secure=next(c['command'] for c in result['commands'] if c['id']=='zowe_secure')
        self.assertIn("& 'C:\\Approved Node\\node.exe' 'C:\\Zowe CLI\\lib\\main.js' 'config' 'secure'",secure)
        self.assertTrue(secure.startswith('Set-Location -LiteralPath '))
        with patch('workbench.connection_setup.sys.platform','win32'),patch('workbench.connection_setup.shutil.which',return_value=None):
            result=inspect_connections(self.root,{'zowe_profile':'factory_base','zowe_zosmf_profile':'factory_zosmf','db2_metadata_url':None})
        self.assertEqual(next(c['command'] for c in result['commands'] if c['id']=='zowe_install'),'npm.cmd install --global @zowe/cli@zowe-v3-lts')

    async def test_missing_node_npm_is_an_explicit_cli_install_prerequisite(self):
        await self.configure()
        from workbench.connection_setup import inspect_connections
        with patch('workbench.connection_setup.shutil.which',return_value=None):
            result=inspect_connections(self.root,{'zowe_profile':'factory_base','zowe_zosmf_profile':'factory_zosmf','db2_metadata_url':None})
        self.assertIn('node_npm',[item['id'] for item in result['remaining']])
        self.assertTrue(any(check['id']=='node_npm' and check['status']=='NOT_FOUND' for check in result['checks']))

    async def test_jsonc_empty_container_leading_commas_are_rejected_and_preserved(self):
        p=self.root/'.vscode/mcp.json';p.parent.mkdir()
        for raw in [b'{"servers":{},"inputs":[,]}',b'{"servers":{,}}',b'{"servers":{},"inputs":[true,,]}']:
            p.write_bytes(raw);status,_=await self.configure()
            self.assertEqual(status,400);self.assertEqual(p.read_bytes(),raw)
            self.assertFalse((self.root/'zowe.config.json').exists())

    async def test_jsonc_valid_comments_trailing_commas_and_string_delimiters_preserved(self):
        p=self.root/'.vscode/mcp.json';p.parent.mkdir()
        text='https://approved.test/a//b/*c*/?list=[,]'
        p.write_text('{/*approved*/"servers":{"approved":{"type":"http","url":'+json.dumps(text)+',},},"inputs":[{"id":"existing","type":"promptString",},],}',encoding='utf-8')
        status,_=await self.configure();self.assertEqual(status,200)
        doc=json.loads(p.read_bytes());self.assertEqual(doc['servers']['approved']['url'],text)
        self.assertEqual(doc['inputs'],[{'id':'existing','type':'promptString'}])

    async def test_exact_import_preserves_supplied_local_schema_filename_binding(self):
        config=self.export/'selected.json';schema=self.export/'selected-schema.json'
        raw=b'{"$schema":"./zowe.config.schema.json","profiles":{"factory_base":{"type":"base","properties":{"host":"zosmf.test","port":443}},"factory_zosmf":{"type":"zosmf"}}}'
        config.write_bytes(raw);schema.write_bytes(b'{"type":"object","required":["profiles"]}\r\n')
        choices=self.choices('import');choices['zowe'].update(config_file=str(config),schema_file=str(schema),host=None,port=None)
        status,_=await self.configure(choices)
        self.assertEqual(status,200);self.assertEqual((self.root/'zowe.config.json').read_bytes(),raw)
        self.assertEqual((self.root/'zowe.config.schema.json').read_bytes(),schema.read_bytes())
        from workbench.zowe_setup import inspect_project_config
        self.assertEqual(inspect_project_config(self.root)['schema'],'VALID')

    async def test_literal_dotted_profile_keys_are_not_accepted_as_nested_aliases(self):
        config=self.export/'literal.json';raw=json.dumps({'profiles':{
            'parent.b':{'type':'base','properties':{'host':'zosmf.test','port':443}},'parent.s':{'type':'zosmf'}}}).encode()
        config.write_bytes(raw);choices=self.choices('import');choices['zowe'].update(config_file=str(config),host=None,port=None)
        status,_=await self.configure(choices,zowe_profile='parent.b',zowe_zosmf_profile='parent.s')
        self.assertEqual(status,400);self.assertFalse((self.root/'zowe.config.json').exists())

    async def test_declared_local_schema_missing_or_unsupported_pointer_blocks_import(self):
        config=self.export/'declared.json';choices=self.choices('import');choices['zowe'].update(config_file=str(config),host=None,port=None)
        for pointer in ['./zowe.schema.json','../outside.json','./other.schema.json']:
            config.write_bytes(json.dumps({'$schema':pointer,'profiles':{'factory_base':{'type':'base','properties':{'host':'zosmf.test','port':443}},'factory_zosmf':{'type':'zosmf'}}}).encode())
            status,_=await self.configure(choices)
            self.assertEqual(status,400);self.assertFalse((self.root/'zowe.config.json').exists())


class ConnectionMarkdownTests(unittest.IsolatedAsyncioTestCase):
    asyncSetUp = ConnectionSetupTests.asyncSetUp
    request = ConnectionSetupTests.request
    choices = ConnectionSetupTests.choices
    configure = ConnectionSetupTests.configure
    async def test_transaction_markdown_uses_validated_choices_and_no_private_bindings(self):
        from workbench.domain import sha
        path = self.root / '.vscode/mcp.json';path.parent.mkdir()
        path.write_bytes(b'{"servers":{"approved":{"type":"http","url":"https://approved.test/mcp","headers":{"X-Private":"PRIVATE_BINDING_SENTINEL"}}}}')
        status, view = await self.configure()
        self.assertEqual(status, 200)
        instructions = view['instructions'];raw = Path(instructions['markdown_path']).read_bytes()
        self.assertEqual(instructions['status'], 'READY')
        self.assertEqual(instructions['sha256'], sha(raw))
        snapshot = json.loads(instructions['text'].split('```json\n')[1].split('\n```')[0])
        self.assertEqual(snapshot['settings'], view['settings'])
        self.assertEqual(snapshot['connections'], view['connection_setup']['choices'])
        self.assertNotIn('PRIVATE_BINDING_SENTINEL', instructions['text'])
        self.assertNotIn('password', snapshot['connections'])

    async def test_last_markdown_destination_failure_restores_all_existing_configuration(self):
        from workbench.domain import atomic_bytes
        await self.configure()
        names = ['.migration/workstation.json', '.migration/workstation.md', '.migration/connections.json',
                 'zowe.config.json', '.vscode/mcp.json']
        before = {self.root / name: (self.root / name).read_bytes() for name in names}
        md = self.root / '.migration/workstation.md'
        def fail(path, raw):
            if Path(path) == md:raise OSError('fictional final Markdown write failure')
            atomic_bytes(path, raw)
        choices = self.choices();choices['zowe']['host'] = 'changed.example.test'
        with patch('workbench.connection_setup.atomic_bytes', side_effect=fail):
            status, _ = await self.configure(choices)
        self.assertEqual(status, 500)
        self.assertEqual({p: p.read_bytes() for p in before}, before)

    async def test_companion_concurrency_blocks_before_any_other_destination_is_written(self):
        from workbench.connection_setup import _copilot_plan
        await self.configure();md = self.root / '.migration/workstation.md'
        before = {self.root / name: (self.root / name).read_bytes() for name in
                  ['.migration/workstation.json', '.migration/connections.json', 'zowe.config.json', '.vscode/mcp.json']}
        def concurrent(*args):
            result = _copilot_plan(*args)
            md.write_bytes(b'fictional concurrent companion edit')
            return result
        choices = self.choices();choices['zowe']['host'] = 'changed.example.test'
        with patch('workbench.connection_setup._copilot_plan', side_effect=concurrent):
            status, _ = await self.configure(choices)
        self.assertEqual(status, 400)
        self.assertEqual(md.read_bytes(), b'fictional concurrent companion edit')
        self.assertEqual({p: p.read_bytes() for p in before}, before)

    async def test_late_json_publication_change_is_preserved_and_configuration_save_fails(self):
        from workbench.domain import atomic_bytes, encode
        await self.configure()
        path = self.root / '.migration/workstation.json';md = self.root / '.migration/workstation.md'
        observed = {}
        def change(destination, raw):
            atomic_bytes(destination, raw)
            if Path(destination) == md:
                current = json.loads(path.read_bytes());current['settings']['db2_metadata_url'] = 'https://fictional-external.test/mcp'
                observed['raw'] = encode(current);path.write_bytes(observed['raw'])
        choices = self.choices();choices['zowe']['host'] = 'fictional-requested.test'
        with patch('workbench.connection_setup.atomic_bytes', side_effect=change):
            status, _ = await self.configure(choices)
        self.assertEqual(status, 400)
        self.assertEqual(path.read_bytes(), observed['raw'])
        _, actual = await self.request('/api/setup/workstation')
        self.assertEqual(actual['instructions']['status'], 'NEEDS_SAVE')

    async def test_late_valid_profile_or_approved_mcp_binding_edit_never_reports_ready(self):
        from workbench.domain import atomic_bytes, encode
        for index, relative in enumerate(('zowe.config.json', '.vscode/mcp.json', '.migration/connections.json')):
            with self.subTest(relative=relative):
                status, _ = await self.configure();self.assertEqual(status, 200)
                path = self.root / relative;md = self.root / '.migration/workstation.md';observed = {}
                def change(destination, raw):
                    atomic_bytes(destination, raw)
                    if Path(destination) == md:
                        current = json.loads(path.read_bytes())
                        if relative == 'zowe.config.json':current['profiles']['factory_base']['properties']['host'] = 'fictional-concurrent.test'
                        elif relative == '.vscode/mcp.json':current['servers']['fictional-approved'] = {'type':'http','url':'https://fictional-approved.test/mcp'}
                        else:current['choices']['copilot'] = False
                        observed['raw'] = encode(current);path.write_bytes(observed['raw'])
                choices = self.choices();choices['zowe']['host'] = 'fictional-requested-'+str(index)+'.test'
                with patch('workbench.connection_setup.atomic_bytes', side_effect=change):
                    status, _ = await self.configure(choices)
                self.assertEqual(status, 400)
                self.assertEqual(path.read_bytes(), observed['raw'])

    async def test_late_readonly_import_source_change_is_preserved_and_blocks_ready(self):
        from workbench.domain import atomic_bytes, encode
        await self.configure()
        source = self.export / 'fictional-selected-zowe.json'
        source.write_bytes((self.root / 'zowe.config.json').read_bytes())
        choices = self.choices('import');choices['zowe'].update(config_file=str(source),schema_file=None,host=None,port=None)
        md = self.root / '.migration/workstation.md';observed = {}
        def change(destination, raw):
            atomic_bytes(destination, raw)
            if Path(destination) == md:
                current = json.loads(source.read_bytes());current['profiles']['factory_base']['properties']['host'] = 'fictional-concurrent-import.test'
                observed['raw'] = encode(current);source.write_bytes(observed['raw'])
        with patch('workbench.connection_setup.atomic_bytes', side_effect=change):
            status, result = await self.configure(choices)
        self.assertEqual(status, 400)
        self.assertIn('raw', observed, result)
        self.assertEqual(source.read_bytes(), observed['raw'])
