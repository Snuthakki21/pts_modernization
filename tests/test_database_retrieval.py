"""Explicit guided row-export opt-in; no live Db2 execution or parity assertion."""
from copy import deepcopy
import json
from pathlib import Path
import random
import secrets
import tempfile
import unittest

from workbench.coordinator import Coordinator
from workbench.database import schema_candidate,create_application_database,sqlite_snapshot,sqlite_rows
from workbench.database_workflow import database_view,prepare_database,database_snapshot,database_comparison
from workbench.domain import ValidationError,encode,sha,write_new
from workbench.layout import output_path
from workbench.retrieval import build_request,write_request,inspect_response,unresolved_after_mapping
from test_database import CONTEXT,receipt,raw
from test_source import COBOL
from test_workflow import MANIFEST


def snapshot_need(snapshot):
    contract={key:deepcopy(snapshot[key]) for key in ('phase','run_id','input_hashes','environment','column_names','key_columns','scope')}
    return {'kind':'db2_snapshot','name':'APP.SALE','source':snapshot['run_id'],'relationship':snapshot['phase'],
            'reason':json.dumps(contract,sort_keys=True,separators=(',',':'))}


def export(snapshot):
    body=raw(snapshot);body['consistency']={'status':'unverified','evidence':[]}
    return encode(body).decode()


class SnapshotRetrievalTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name)
        self.doc={'id':'sample','source_files':{},'copilot_iteration':0,'guided_contract_version':1,'guided_workspace':str(self.root)}
        self.before=receipt([{'ID':'00000001','VALUE':'old'}],'before');self.after=receipt([{'ID':'00000001','VALUE':'old'},{'ID':'00000002','VALUE':'new'}],'after')

    def response(self,request,snapshots):
        write_request(self.root,request);folder=self.root/request['return_folder'];items=[]
        for need,snapshot in zip(request['needs'],snapshots):
            text=export(snapshot);path='db2/'+snapshot['phase']+'.json';f=folder/'files'/path;f.parent.mkdir(parents=True,exist_ok=True);f.write_bytes(text.encode('utf-8'))
            items.append({'need_id':need['need_id'],'status':'FOUND','path':path,'sha256':sha(text),'provenance':raw(snapshot)['provenance']})
        (folder/'response.json').write_bytes(encode({'request_id':request['request_id'],'items':items}));return folder,items

    def test_opt_in_exact_before_after_receipts_are_immutable_and_remain_unverified(self):
        request=build_request(self.doc,[snapshot_need(self.before),snapshot_need(self.after)]);self.response(request,[self.before,self.after])
        result=inspect_response(self.root,request);self.assertTrue(result['complete']);self.assertEqual(len(result['entries']),2)
        self.assertIn('only named db2_snapshot needs authorize',request['copilot_prompt']);self.assertIn('never submit/execute',request['copilot_prompt'])
        for entry in result['entries']:
            self.assertEqual(entry['provenance']['content_kind'],'DB2_RECORD_SNAPSHOT')
            self.assertEqual(json.loads(entry['text'])['consistency'],{'status':'unverified','evidence':[]})
            self.assertEqual(entry['source_hash'],sha(entry['text']))
        self.assertEqual(result,inspect_response(self.root,request))

    def test_twenty_runtime_randomized_receipts_preserve_leading_zeros_and_typed_values(self):
        seed=secrets.randbits(63);rng=random.Random(seed)
        request=build_request(self.doc,[snapshot_need(self.before)])
        for i in range(20):
            with self.subTest(seed=seed,index=i):
                snapshot=receipt([{'ID':str(i).zfill(8),'VALUE':'v'+str(rng.randrange(10**15))}],'before')
                self.response(request,[snapshot]);result=inspect_response(self.root,request)
                observed=json.loads(result['entries'][0]['text'])
                self.assertEqual(observed['rows'],snapshot['rows']);self.assertIsInstance(observed['rows'][0]['ID'],str)

    def test_twenty_escaped_json_typed_snapshots_require_explicit_row_requests(self):
        seed=secrets.randbits(63);rng=random.Random(seed);kind='DB2_RECORD_SNAPSHOT'
        masks=rng.sample(range(1,2**len(kind)),20);states=set()
        explicit=build_request(self.doc,[snapshot_need(self.before)])
        ordinary=build_request(self.doc,[{'kind':'db2_table','name':'APP.SALE','reason':'Schema only'}])
        for index,mask in enumerate(masks):
            with self.subTest(seed=seed,index=index,mask=mask):
                snapshot=receipt([{'ID':str(index).zfill(8),'VALUE':'escaped-'+str(rng.randrange(10**15))}],'before')
                spelling=''.join((r'\u%04x'%ord(character)) if mask&(1<<offset) else character for offset,character in enumerate(kind))
                for request,allow in ((explicit,True),(ordinary,False)):
                    folder,items=self.response(request,[snapshot]);path=folder/'files/db2/before.json'
                    text=path.read_text().replace('"kind"',r'"\u006bind"').replace(kind,spelling)
                    self.assertEqual(json.loads(text)['kind'],kind);path.write_bytes(text.encode('utf-8'))
                    items[0]['sha256']=sha(text)
                    if not allow:items[0]['provenance']['tool']='db2_describe_table'
                    (folder/'response.json').write_bytes(encode({'request_id':request['request_id'],'items':items}))
                    if allow:
                        actual=inspect_response(self.root,request);observed=json.loads(actual['entries'][0]['text'])
                        self.assertEqual(observed['rows'],snapshot['rows']);self.assertEqual(actual['entries'][0]['source_hash'],sha(text))
                        states.add(sha(text))
                    else:
                        with self.assertRaisesRegex(ValidationError,'explicit guided snapshot'):
                            inspect_response(self.root,request)
        self.assertEqual(len(states),20)

    def test_twenty_bom_typed_snapshots_require_exact_row_authorization_and_preserve_actual_bytes(self):
        seed=secrets.randbits(63);rng=random.Random(seed);kind='DB2_RECORD_SNAPSHOT';states=set()
        masks=rng.sample(range(1,2**len(kind)),20)
        explicit=build_request(self.doc,[snapshot_need(self.before)])
        unrelated=[build_request(self.doc,[{'kind':kind,'name':'APP.SALE','reason':'Metadata only'}])
                   for kind in ('db2_table','db2_view','db2_stored_procedure')]
        schema=schema_candidate('CREATE TABLE APP.SALE (ID CHAR(8) NOT NULL PRIMARY KEY, VALUE VARCHAR(40));')
        for index,mask in enumerate(masks):
            with self.subTest(seed=seed,index=index,mask=mask):
                snapshot=receipt([{'ID':str(index).zfill(8),'VALUE':'bom-'+str(rng.randrange(10**15))}],'before')
                spelling=''.join((r'\u%04x'%ord(character)) if mask&(1<<offset) else character for offset,character in enumerate(kind))
                for request in (explicit,*unrelated):
                    folder,items=self.response(request,[snapshot]);path=folder/'files/db2/before.json'
                    text='\ufeff'+path.read_bytes().decode('utf-8').replace('"kind"',r'"\u006bind"').replace(kind,spelling)
                    path.write_bytes(text.encode('utf-8'));items[0]['sha256']=sha(text)
                    if request is not explicit:items[0]['provenance']['tool']='db2_describe_table'
                    (folder/'response.json').write_bytes(encode({'request_id':request['request_id'],'items':items}))
                    if request is explicit:
                        result=inspect_response(self.root,request);entry=result['entries'][0]
                        self.assertTrue(result['complete']);self.assertEqual(entry['text'],text);self.assertEqual(entry['source_hash'],sha(path.read_bytes()))
                        self.assertEqual(entry['provenance']['content_kind'],kind);self.assertEqual(path.read_bytes(),text.encode('utf-8'))
                        self.assertEqual(json.loads(entry['text'].encode('utf-8').decode('utf-8-sig'))['rows'],snapshot['rows'])
                        target=self.root/f'bom-local-{index}.sqlite';created=create_application_database(target,[schema],{'APP.SALE':snapshot['rows']})
                        self.assertEqual(sqlite_rows(target,created['sha256'],'APP.SALE')['rows'],snapshot['rows'])
                        self.assertFalse(schema['native_database_verified']);states.add(entry['source_hash'])
                    else:
                        with self.assertRaisesRegex(ValidationError,'explicit guided snapshot'):
                            inspect_response(self.root,request)
        self.assertEqual(len(states),20)

    def test_bom_unrelated_json_is_retained_without_snapshot_identity(self):
        request=build_request(self.doc,[{'kind':'db2_table','name':'APP.SALE','reason':'Schema only'}])
        folder,items=self.response(request,[self.before]);path=folder/'files/db2/before.json'
        text='\ufeff'+encode({'kind':'OTHER','note':'DB2_RECORD_SNAPSHOT DB2_TABLE_DESCRIPTION'}).decode()
        path.write_bytes(text.encode('utf-8'));items[0]['sha256']=sha(text);items[0]['provenance']['tool']='db2_describe_table'
        (folder/'response.json').write_bytes(encode({'request_id':request['request_id'],'items':items}))
        result=inspect_response(self.root,request);entry=result['entries'][0]
        self.assertEqual(entry['text'],text);self.assertEqual(entry['source_hash'],sha(path.read_bytes()))
        self.assertNotIn('content_kind',entry['provenance']);self.assertNotIn('phase',entry['provenance'])

    def test_bom_typed_receipts_do_not_weaken_malformed_hash_transport_or_context_checks(self):
        explicit=build_request(self.doc,[snapshot_need(self.before)])
        ordinary=build_request(self.doc,[{'kind':'db2_table','name':'APP.SALE','reason':'Schema only'}])
        for request in (explicit,ordinary):
            folder,items=self.response(request,[self.before]);path=folder/'files/db2/before.json'
            text='\ufeff'+export(self.before)[:-2];path.write_bytes(text.encode('utf-8'));items[0]['sha256']=sha(text)
            if request is ordinary:items[0]['provenance']['tool']='db2_describe_table'
            (folder/'response.json').write_bytes(encode({'request_id':request['request_id'],'items':items}))
            with self.subTest(kind=request['needs'][0]['kind']),self.assertRaises(ValidationError):inspect_response(self.root,request)
        for alteration in ('hash','transport','phase'):
            folder,items=self.response(explicit,[self.before]);path=folder/'files/db2/before.json';snapshot=self.before
            if alteration=='phase':snapshot=self.after
            text='\ufeff'+export(snapshot);path.write_bytes(text.encode('utf-8'));items[0]['sha256']=sha(text)
            if alteration=='hash':items[0]['sha256']=sha(text[1:])
            if alteration=='transport':items[0]['provenance']['tool']='db2_describe_table'
            (folder/'response.json').write_bytes(encode({'request_id':explicit['request_id'],'items':items}))
            with self.subTest(alteration=alteration),self.assertRaises(ValidationError):inspect_response(self.root,explicit)

    def test_wrong_phase_run_input_environment_scope_key_transport_or_consistency_is_denied(self):
        request=build_request(self.doc,[snapshot_need(self.before)]);folder,items=self.response(request,[self.before])
        original=json.loads((folder/'files/db2/before.json').read_text())
        alterations=[('phase','after'),('run_id','different'),('input_hashes',{'input/sale.txt':sha('wrong')}),('environment','I_NONPROD'),
            ('key_columns',['VALUE']),('scope',{'kind':'explicit_keys','keys':[['00000001']],'complete':True}),
            ('consistency',{'status':'consistent','evidence':[{'path':'fake.json','sha256':sha('fake')}]}),
            ('rows',[{'ID':1.0,'VALUE':'old'}])]
        for field,value in alterations:
            body={**deepcopy(original),field:value};text=encode(body).decode();(folder/'files/db2/before.json').write_bytes(text.encode('utf-8'))
            item={**items[0],'sha256':sha(text)};(folder/'response.json').write_bytes(encode({'request_id':request['request_id'],'items':[item]}))
            with self.subTest(field=field),self.assertRaises(ValidationError):inspect_response(self.root,request)
        self.response(request,[self.before]);items[0]['provenance']['tool']='db2_describe_table'
        (folder/'response.json').write_bytes(encode({'request_id':request['request_id'],'items':items}))
        with self.assertRaises(ValidationError):inspect_response(self.root,request)

    def test_partial_export_is_retained_as_partial_and_never_invents_missing_rows(self):
        request=build_request(self.doc,[snapshot_need(self.before)]);partial=deepcopy(self.before);partial['scope']['complete']=False
        # Raw observed bytes are rebuilt deliberately; this fixture is not a
        # modification of immutable Coordinator input or accepted evidence.
        self.response(request,[partial]);result=inspect_response(self.root,request)
        self.assertFalse(json.loads(result['entries'][0]['text'])['scope']['complete'])
        self.assertEqual(json.loads(result['entries'][0]['text'])['rows'],self.before['rows'])

    def test_unguided_or_unsolicited_business_rows_and_unbound_need_rejected(self):
        for doc in ({k:v for k,v in self.doc.items() if k not in ('guided_contract_version','guided_workspace')},):
            with self.assertRaises(ValidationError):build_request(doc,[snapshot_need(self.before)])
        for altered in ({**snapshot_need(self.before),'source':'wrong'}, {**snapshot_need(self.before),'relationship':'after'},
                        {**snapshot_need(self.before),'reason':'freeform guess'}, {**snapshot_need(self.before),'name':'app.sale'}):
            with self.subTest(need=altered),self.assertRaises(ValidationError):build_request(self.doc,[altered])
        ordinary=build_request(self.doc,[{'kind':'db2_table','name':'APP.SALE','reason':'Schema only'}])
        folder,items=self.response(ordinary,[self.before]);items[0]['provenance']['tool']='db2_describe_table'
        (folder/'response.json').write_bytes(encode({'request_id':ordinary['request_id'],'items':items}))
        with self.assertRaisesRegex(ValidationError,'explicit guided snapshot'):inspect_response(self.root,ordinary)


class SnapshotCoordinatorTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name)
        self.c=Coordinator(self.root);self.addCleanup(self.c.close)

    def stage(self,request,returned):
        folder=self.root/request['return_folder'];items=[]
        for need,path,text,provenance in returned:
            destination=folder/'files'/path;destination.parent.mkdir(parents=True,exist_ok=True);destination.write_bytes(text.encode('utf-8'))
            items.append({'need_id':need['need_id'],'status':'FOUND','path':path,'sha256':sha(text),'provenance':provenance})
        (folder/'response.json').write_bytes(encode({'request_id':request['request_id'],'items':items}))
        self.c.continue_retrieval('process-a')

    def test_actual_guided_request_continue_save_capture_and_keyed_gap_report(self):
        source=COBOL.replace('  GOBACK.','  EXEC SQL SELECT ID FROM APP.SALE END-EXEC.\n  GOBACK.')
        self.c.prepare_process(MANIFEST,source_files={'ELIGIBLE.cbl':source,'JOBA.jcl':'//JOBA JOB\n//S010 EXEC PGM=ELIGIBLE\n'})
        self.c.start('process-a');self.c.advance('process-a');request=self.c.request_retrieval('process-a')['retrieval']
        ddl='CREATE TABLE APP.SALE (ID CHAR(8) NOT NULL PRIMARY KEY, VALUE VARCHAR(40));'
        schema_provenance={'origin':'configured_mcp','tool':'db2_describe_table','locator':'APP.SALE','retrieved_at':'2026-10-07T15:00:00Z'}
        self.stage(request,[(request['needs'][0],'db2/SALE.ddl',ddl,schema_provenance)])
        self.assertEqual(self.c.ledger.get('process-a')['status'],'WAITING_REQUIREMENTS')
        old=[{'ID':str(i).zfill(8),'VALUE':'old'} for i in range(20)];new=[{'ID':str(i).zfill(8),'VALUE':'new'} for i in range(20,25)]
        before=receipt(old,'before');after=receipt(old+new,'after')
        request=self.c.request_retrieval('process-a',[snapshot_need(before),snapshot_need(after)])['retrieval']
        self.stage(request,[(need,'db2/'+snap['phase']+'.json',export(snap),snap['provenance']) for need,snap in zip(request['needs'],(before,after))])
        doc=self.c.ledger.get('process-a');self.assertFalse(doc.get('retrieval_unresolved'));self.assertEqual(doc['status'],'WAITING_REQUIREMENTS')
        model=self.c.requirements_view('process-a');self.c.save_requirements('process-a',{'catalog_hash':model['catalog_hash'],'revision':model['revision'],'excluded_ids':[],'saved_by':'Fictional snapshot scope operator'})
        self.c.advance('process-a');view=prepare_database(self.c,'process-a');database=view['databases'][0]
        self.assertEqual({snap['phase'] for snap in view['snapshots']},{'before','after'})
        local_before=database_snapshot(self.c,'process-a',{'database_id':database['id'],'source_snapshot':'input/sources/db2/before.json','context':CONTEXT,'phase':'before'})
        local_after=database_snapshot(self.c,'process-a',{'database_id':database['id'],'source_snapshot':'input/sources/db2/after.json','context':CONTEXT,'phase':'after'})
        self.assertEqual(local_before['rows'],0);self.assertEqual(local_after['rows'],0)
        self.assertEqual(database_snapshot(self.c,'process-a',{'database_id':database['id'],'source_snapshot':'input/sources/db2/before.json','context':CONTEXT,'phase':'before'}),local_before)
        body={'db2_before':'input/sources/db2/before.json','db2_after':'input/sources/db2/after.json',
              'sqlite_before':local_before['artifact'],'sqlite_after':local_after['artifact'],'context':CONTEXT}
        result=database_comparison(self.c,'process-a',body)
        self.assertEqual(result['summary']['db2_after_rows'],25);self.assertEqual(result['summary']['historical_records'],20)
        self.assertEqual(result['summary']['baseline_gap_records'],20);self.assertEqual(result['summary']['final_gap_records'],25)
        self.assertFalse(result['summary']['complete_exported_scope_match']);self.assertFalse(result['summary']['run_delta_matches'])
        self.assertEqual(len([g for g in result['gaps'] if g['kind']=='database_consistency_gap']),2)
        self.assertFalse(result['native_database_verified']);self.assertFalse(result['observed_program_parity'])
        self.assertEqual(database_comparison(self.c,'process-a',body)['id'],result['id'])
        self.assertEqual(len(database_view(self.c,'process-a')['comparisons']),1)
        doc=self.c.ledger.get('process-a');self.assertEqual(doc['status'],'WAITING_COPILOT');self.assertFalse(doc['packet_issued'])
        self.assertTrue(any(b['kind']=='unsupported_source' for b in doc['blockers']))
        self.assertIn(result['artifact'],doc['artifacts']);self.assertEqual(sha(self.c.artifact('process-a',result['artifact']).read_bytes()),result['sha256'])
        with self.assertRaises(ValidationError):database_snapshot(self.c,'process-a',{'database_id':database['id'],'source_snapshot':'input/sources/db2/before.json','context':CONTEXT,'phase':'after'})

if __name__=='__main__':unittest.main()
