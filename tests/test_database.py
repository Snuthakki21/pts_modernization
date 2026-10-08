"""Actual bounded SQLite storage and frozen keyed-export comparison tests."""
from copy import deepcopy
from datetime import datetime,timezone
from pathlib import Path
import random
import secrets
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from workbench.database import (schema_candidate,create_application_database,sqlite_schema,sqlite_rows,
                                validate_snapshot,sqlite_snapshot,compare_snapshots as _compare_snapshots,_value_valid,SNAPSHOT_FIELDS,decode_filters)
from workbench.domain import ValidationError,encode,sha

DDL='''CREATE TABLE APP.SALE (
 ID CHAR(8) NOT NULL,
 NAME VARCHAR(16),
 SMALL SMALLINT NOT NULL,
 NUMBER INTEGER NOT NULL,
 BIG BIGINT NOT NULL,
 AMOUNT DECIMAL(9,2),
 PRIMARY KEY(ID)
);'''
CONTEXT={'db2_run_id':'JOB_Z001_RUN_42','sqlite_run_id':'TARGET_42','input_hashes':{'input/sale.txt':sha('same input')},
         'db2_environment':'Z_PROD','sqlite_environment':'LOCAL_POC'}


def receipt(rows,phase,side='db2',consistent=True):
    value={'schema_version':1,'kind':'DB2_RECORD_SNAPSHOT' if side=='db2' else 'SQLITE_RECORD_SNAPSHOT',
           'schema':'APP','table':'SALE','column_names':['ID','VALUE'],'key_columns':['ID'],'rows':rows,'phase':phase,
           'run_id':CONTEXT[side+'_run_id'],'input_hashes':deepcopy(CONTEXT['input_hashes']),'environment':CONTEXT[side+'_environment'],
           'scope':{'kind':'full_table','keys':[],'complete':True},
           'provenance':{'origin':'configured_mcp' if side=='db2' else 'local_sqlite','tool':'db2_read_table_rows' if side=='db2' else 'workbench.database.sqlite_snapshot',
                         'locator':'APP.SALE','retrieved_at':'2026-10-07T16:00:00Z' if phase=='before' else '2026-10-07T17:00:00Z'},
           'consistency':{'status':'consistent' if consistent else 'unverified','evidence':[{'path':'synthetic/consistent-export.json','sha256':sha('synthetic fixture')} ] if consistent else []}}
    return validate_snapshot(encode(value).decode())


def raw(snapshot):return {k:deepcopy(v) for k,v in snapshot.items() if k in SNAPSHOT_FIELDS}


def fixture_evidence(snapshot):
    # This verifier accepts only these isolated synthetic witness bytes and the
    # actual SQLite files created by this test. It is not production approval.
    for item in snapshot['consistency']['evidence']:
        if item['path']=='synthetic/consistent-export.json':
            if item['sha256']!=sha('synthetic fixture'):return False
        else:
            path=Path(item['path'])
            if not path.is_file() or sha(path.read_bytes())!=item['sha256']:return False
    return bool(snapshot['consistency']['evidence'])


def compare_snapshots(*args,**kwargs):
    return _compare_snapshots(*args,evidence_verifier=fixture_evidence,**kwargs)


class DatabaseTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.path=Path(self.tmp.name)/'application.sqlite'

    def test_generated_schema_actually_preserves_twenty_randomized_states_per_type(self):
        seed=secrets.randbits(63);rng=random.Random(seed);schema=schema_candidate(DDL,source_path='db2/SALE.ddl');rows=[]
        small=rng.sample(range(-32768,32768),20)
        for number in range(20):
            while True:
                amount=str(rng.randrange(1000000))+'.'+str(rng.randrange(100)).zfill(2)
                row={'ID':str(number).zfill(8),'NAME':'N'+str(number)+'-'+str(rng.randrange(100000000)), 'SMALL':small[number],
                     'NUMBER':rng.randrange(-2**31,2**31),'BIG':rng.randrange(-2**63,2**63),'AMOUNT':amount}
                if all(all(row[name]!=other[name] for other in rows) for name in row):break
            rows.append(row)
        self.assertTrue(schema['can_build']);self.assertFalse(schema['native_database_verified'])
        result=create_application_database(self.path,[schema],{'APP.SALE':rows});page=sqlite_rows(self.path,result['sha256'],'APP.SALE')
        self.assertEqual(page['rows'],rows);self.assertEqual(result['sha256'],sha(self.path.read_bytes()))
        for name in rows[0]:self.assertEqual(len({row[name] for row in rows}),20,(seed,name))
        self.assertEqual(page['rows'][0]['ID'],'00000000');self.assertIsInstance(page['rows'][0]['BIG'],int)
        self.assertEqual(page['display_rows'][0]['BIG'],str(rows[0]['BIG']))
        self.assertEqual(sqlite_schema(self.path,result['sha256'])['tables'][0]['rows'],20)
        self.assertTrue(all(column['type']=='ANY' for column in sqlite_schema(self.path,result['sha256'])['tables'][0]['columns']))

    def test_actual_target_constraints_match_independent_source_value_domains(self):
        schema=schema_candidate(DDL);created=create_application_database(self.path,[schema]);db=sqlite3.connect(self.path);self.addCleanup(db.close)
        valid={'ID':'00000001','NAME':'A','SMALL':1,'NUMBER':2,'BIG':3,'AMOUNT':'1.00'}
        columns=schema['tables'][0]['columns'];names=[c['name'] for c in columns]
        invalid={'ID':[1,True,'123','é'*8,'\n'*8,None], 'NAME':[1,'A'*17,'é', '\n'],
                 'SMALL':[-32769,32768,'1',True,1.1,None],'NUMBER':[-2**31-1,2**31,'1',None],
                 'BIG':['9223372036854775808',1.0,None],'AMOUNT':[1,1.0,'1.1','01.00','-0.00','10000000.00','1.000','--1.00','1..00','0.00\x00hidden','é.00','']}
        checked=0
        for column in columns:
            for value in invalid[column['name']]:
                with self.subTest(column=column['name'],value=value):
                    row={**valid,column['name']:value};self.assertFalse(_value_valid(column,value))
                    # SQLite's interface binds bool as int; the application helper must
                    # reject bool before binding. All other supported binding types are
                    # actually challenged against the exported generated CHECKs.
                    if type(value) is bool:continue
                    with self.assertRaises((sqlite3.IntegrityError,sqlite3.DataError)):
                        db.execute('INSERT INTO "APP.SALE" VALUES (?,?,?,?,?,?)',[row[n] for n in names])
                    db.rollback();checked+=1
        self.assertGreaterEqual(checked,30)
        for column in columns:
            if column['nullable']:
                row={**valid,column['name']:None};db.execute('INSERT INTO "APP.SALE" VALUES (?,?,?,?,?,?)',[row[n] for n in names]);db.rollback()
        bad={**valid,'SMALL':True}
        with self.assertRaises(ValidationError):create_application_database(Path(self.tmp.name)/'bool.sqlite',[schema],{'APP.SALE':[bad]})
        self.assertFalse((Path(self.tmp.name)/'bool.sqlite').exists())

    def test_decimal_precision_scale_zero_and_all_fractional_states_are_preserved(self):
        seed=secrets.randbits(63);rng=random.Random(seed)
        for p,s in ((1,0),(4,0),(4,4),(31,7)):
            with self.subTest(precision=p,scale=s):
                source=f'CREATE TABLE APP.DECIMALTEST (ID INTEGER NOT NULL PRIMARY KEY,V DECIMAL({p},{s}));';schema=schema_candidate(source)
                values=[]
                for index in range(20):
                    digits=max(1,p-s);integral=0 if p==s else rng.randrange(10**digits)
                    value=str(integral)+('.'+str(rng.randrange(10**s)).zfill(s) if s else '')
                    values.append({'ID':index,'V':value})
                path=Path(self.tmp.name)/f'decimal-{p}-{s}.sqlite';created=create_application_database(path,[schema],{'APP.DECIMALTEST':values})
                self.assertEqual(sqlite_rows(path,created['sha256'],'APP.DECIMALTEST')['rows'],values)

    def test_adversarial_schema_mutation_is_denied_and_actual_check_mutants_have_witnesses(self):
        schema=schema_candidate(DDL);mutant=deepcopy(schema);mutant['sqlite_ddl']='ATTACH DATABASE "/tmp/private" AS stolen;'
        with self.assertRaises(ValidationError):create_application_database(self.path,[mutant])
        self.assertFalse(self.path.exists());db=sqlite3.connect(':memory:');self.addCleanup(db.close)
        ddl=schema['sqlite_ddl'];mutant=ddl.replace('length("ID") = 8','length("ID") <= 8')
        db.execute(mutant);db.execute('INSERT INTO "APP.SALE" VALUES (?,?,?,?,?,?)',('1','A',1,2,3,'1.00'))
        self.assertEqual(db.execute('SELECT ID FROM "APP.SALE"').fetchone()[0],'1')
        self.assertFalse(_value_valid(schema['tables'][0]['columns'][0],'1'))
        db.close();db=sqlite3.connect(':memory:');db.execute(ddl)
        with self.assertRaises(sqlite3.IntegrityError):db.execute('INSERT INTO "APP.SALE" VALUES (?,?,?,?,?,?)',('1','A',1,2,3,'1.00'))
        db.close()

    def test_declared_composite_and_unique_keys_have_twenty_actual_states_and_mutant_witness(self):
        seed=secrets.randbits(63);rng=random.Random(seed)
        schema=schema_candidate('CREATE TABLE APP.KEYS (ID INTEGER NOT NULL, PART CHAR(4) NOT NULL, ALT INTEGER NOT NULL UNIQUE, PRIMARY KEY(ID,PART));')
        alt=rng.sample(range(-1000000,1000000),20)
        rows=[{'ID':index,'PART':str(rng.randrange(10000)).zfill(4),'ALT':alt[index]} for index in range(20)]
        result=create_application_database(self.path,[schema],{'APP.KEYS':rows})
        self.assertEqual(sqlite_rows(self.path,result['sha256'],'APP.KEYS')['rows'],rows,(seed,rows))
        db=sqlite3.connect(':memory:');self.addCleanup(db.close);db.execute(schema['sqlite_ddl'])
        db.execute('INSERT INTO \"APP.KEYS\" VALUES (?,?,?)',(1,'0001',3))
        with self.assertRaises(sqlite3.IntegrityError):db.execute('INSERT INTO \"APP.KEYS\" VALUES (?,?,?)',(2,'0002',3))
        with self.assertRaises(sqlite3.IntegrityError):db.execute('INSERT INTO \"APP.KEYS\" VALUES (?,?,?)',(1,'0001',4))
        mutant=sqlite3.connect(':memory:');self.addCleanup(mutant.close)
        mutant.execute(schema['sqlite_ddl'].replace(',\n  UNIQUE (\"ALT\")',''))
        mutant.execute('INSERT INTO \"APP.KEYS\" VALUES (?,?,?)',(1,'0001',3));mutant.execute('INSERT INTO \"APP.KEYS\" VALUES (?,?,?)',(2,'0002',3))
        self.assertEqual(mutant.execute('SELECT count(*) FROM \"APP.KEYS\" WHERE ALT=3').fetchone()[0],2)

    def test_granular_ddl_source_spans_and_explicit_key_snapshot_types(self):
        model=schema_candidate(DDL)
        units={u['column']:u for u in model['units'] if u['kind']=='database_column'}
        self.assertEqual((units['ID']['start_line'],units['ID']['end_line']),(2,2))
        self.assertEqual((units['AMOUNT']['start_line'],units['AMOUNT']['end_line']),(7,7))
        source=raw(receipt([{'ID':'00000001','VALUE':'a'}],'after'));source['scope']={'kind':'explicit_keys','keys':[['00000001'],['00000002']],'complete':True}
        source=validate_snapshot(encode(source).decode())
        schema=schema_candidate('CREATE TABLE APP.SALE (ID CHAR(8) NOT NULL PRIMARY KEY,VALUE VARCHAR(40));')
        created=create_application_database(self.path,[schema],{'APP.SALE':[{'ID':'00000001','VALUE':'a'},{'ID':'00000003','VALUE':'unrelated'}]})
        target=sqlite_snapshot(self.path,created['sha256'],'APP.SALE',source,CONTEXT['sqlite_run_id'],CONTEXT['input_hashes'],CONTEXT['sqlite_environment'],'after')
        self.assertEqual(target['rows'],[{'ID':'00000001','VALUE':'a'}]);self.assertEqual(target['scope'],source['scope'])

    def test_unsupported_source_features_are_named_and_never_executed(self):
        for definition in ('V DECFLOAT(34)','V FLOAT','V DATE','V TIMESTAMP','V BLOB(100)','V VARCHAR(20) DEFAULT \'secret\'',
                           'V INTEGER GENERATED ALWAYS AS IDENTITY','V INTEGER, FOREIGN KEY(V) REFERENCES APP.X(ID)',
                           'V INTEGER CHECK(V>0)'):
            with self.subTest(definition=definition):
                schema=schema_candidate('CREATE TABLE APP.X ('+definition+');')
                self.assertFalse(schema['can_build']);self.assertTrue(any(g['kind']!='database_native_gap' for g in schema['gaps']))
        source='CREATE TABLE APP.X (ID INTEGER); DROP TABLE APP.X; CREATE TRIGGER EVIL AFTER INSERT ON APP.X BEGIN SELECT 1; END;'
        schema=schema_candidate(source);self.assertTrue(schema['can_build']);self.assertNotIn('TRIGGER',schema['sqlite_ddl']);self.assertNotIn('DROP',schema['sqlite_ddl'])
        self.assertTrue(any('DROP' in g['message'] for g in schema['gaps']))
        self.assertTrue(any('TRIGGER' in g['message'] for g in schema['gaps']))

    def test_empty_column_segments_are_named_gaps_and_cannot_create_a_database(self):
        for body in ('ID INTEGER NOT NULL PRIMARY KEY,', ',ID INTEGER', 'ID INTEGER,,V CHAR(1)'):
            with self.subTest(body=body):
                schema=schema_candidate('CREATE TABLE APP.T ('+body+');',source_path='db2/invalid.ddl')
                self.assertFalse(schema['can_build']);self.assertEqual(schema['sqlite_ddl'],'')
                self.assertTrue(all(table['support']=='unsupported' for table in schema['tables']))
                self.assertTrue(all(unit['support']=='unsupported' for unit in schema['units']))
                gaps=[gap for gap in schema['gaps'] if gap['kind']=='database_column_gap']
                self.assertTrue(any('Empty column/constraint definition' in gap['message'] for gap in gaps))
                self.assertTrue(all(gap['source_path']=='db2/invalid.ddl' and gap['table']=='APP.T' for gap in gaps))
                with self.assertRaisesRegex(ValidationError,'No supported storage tables'):
                    create_application_database(self.path,[schema])
                self.assertFalse(self.path.exists())

    def test_repeated_table_definitions_block_every_declaration_and_preserve_other_tables(self):
        seed=secrets.randbits(63);rng=random.Random(seed);states=set()
        for index,width in enumerate(rng.sample(range(1,256),20)):
            value='X'*width
            source=('CREATE TABLE APP.T (ID INTEGER NOT NULL PRIMARY KEY);\n'
                    f'CREATE TABLE APP.T (ID CHAR({width}) NOT NULL PRIMARY KEY);\n'
                    'CREATE TABLE APP.KEPT (ID INTEGER NOT NULL PRIMARY KEY,V VARCHAR(255));')
            schema=schema_candidate(source,source_path='db2/repeated.ddl')
            states.add(sha(source));affected=[table for table in schema['tables'] if table['name']=='APP.T']
            self.assertEqual([table['support'] for table in affected],['unsupported','unsupported'])
            self.assertTrue(all(unit['support']=='unsupported' for unit in schema['units'] if unit.get('table')=='APP.T'))
            gaps=[gap for gap in schema['gaps'] if gap['kind']=='database_structure_gap' and gap.get('table')=='APP.T']
            self.assertEqual(len(gaps),2);self.assertEqual({gap['start_line'] for gap in gaps},{1,2})
            self.assertTrue(all(gap['declarations']==[{'start_line':1,'end_line':1},{'start_line':2,'end_line':2}] for gap in gaps))
            self.assertNotIn('CREATE TABLE "APP.T"',schema['sqlite_ddl']);self.assertTrue(schema['can_build'])
            path=Path(self.tmp.name)/f'kept-{index}.sqlite'
            created=create_application_database(path,[schema],{'APP.KEPT':[{'ID':index,'V':value}]})
            actual=sqlite_schema(path,created['sha256']);self.assertEqual([table['name'] for table in actual['tables']],['APP.KEPT'])
            self.assertEqual(sqlite_rows(path,created['sha256'],'APP.KEPT')['rows'],[{'ID':index,'V':value}],(seed,index))
        self.assertEqual(len(states),20)
        for duplicate in ('CREATE TABLE APP.T(ID INTEGER); CREATE TABLE APP.T(ID INTEGER);',
                          'CREATE TABLE APP.T(ID CHAR(2)); CREATE TABLE APP.T(ID INTEGER);'):
            schema=schema_candidate(duplicate)
            self.assertFalse(schema['can_build']);self.assertEqual(schema['sqlite_ddl'],'')
            with self.assertRaisesRegex(ValidationError,'No supported storage tables'):
                create_application_database(self.path,[schema])
            self.assertFalse(self.path.exists())

    def test_catalog_decoded_identity_is_spelling_independent_and_storage_only(self):
        from workbench.db2_catalog import table_description
        seed=secrets.randbits(63);rng=random.Random(seed);states=set();kind='DB2_TABLE_DESCRIPTION'
        for index,width in enumerate(rng.sample(range(1,256),20)):
            body={'schema_version':1,'kind':kind,'schema':'APP','table':'X',
                  'columns':[{'NAME':'ID','COLNO':0,'COLTYPE':'CHAR','LENGTH':width,'NULLS':'N'}],
                  'description_complete':True,'ddl':None,'constraints':None,'indexes':None,'triggers':None,
                  'provenance':{'origin':'configured_mcp','tool':'db2_describe_table','locator':'APP.X','retrieved_at':'2026-10-07T16:00:00Z'}}
            plain=encode(body).decode();spelling=''.join((r'\u%04x'%ord(character)) for character in kind)
            escaped=plain.replace('"kind"',r'"\u006bind"').replace(kind,spelling)
            first=table_description(plain,body['provenance']);second=table_description(escaped,body['provenance'])
            self.assertEqual({k:v for k,v in first.items() if k!='source_hash'},{k:v for k,v in second.items() if k!='source_hash'})
            self.assertNotEqual(first['source_hash'],second['source_hash']);self.assertEqual(second['source_hash'],sha(escaped))
            original=schema_candidate(plain);target=schema_candidate(escaped)
            self.assertEqual(original['sqlite_ddl'],target['sqlite_ddl']);self.assertFalse(target['native_database_verified'])
            self.assertIn('NATIVE_SQL_TRANSACTION_TYPE_AND_AUTHORIZATION_EQUIVALENCE',second['missing_semantics'])
            path=Path(self.tmp.name)/f'escaped-{index}.sqlite';row={'ID':'0'*width}
            created=create_application_database(path,[target],{'APP.X':[row]})
            self.assertEqual(sqlite_rows(path,created['sha256'],'APP.X')['rows'],[row],(seed,index,width));states.add(sha(escaped))
        self.assertEqual(len(states),20)

    def test_twenty_bom_catalogs_preserve_hashes_facts_and_actual_storage_without_native_credit(self):
        from workbench.db2_catalog import table_description
        seed=secrets.randbits(63);rng=random.Random(seed);states=set()
        for index,width in enumerate(rng.sample(range(1,256),20)):
            with self.subTest(seed=seed,index=index,width=width):
                body={'schema_version':1,'kind':'DB2_TABLE_DESCRIPTION','schema':'APP','table':'X',
                      'columns':[{'NAME':'ID','COLNO':0,'COLTYPE':'CHAR','LENGTH':width,'NULLS':'N'}],
                      'description_complete':True,'ddl':None,'constraints':None,'indexes':None,'triggers':None,
                      'provenance':{'origin':'configured_mcp','tool':'db2_describe_table','locator':'APP.X','retrieved_at':'2026-10-07T16:00:00Z'}}
                plain=encode(body).decode();bom='\ufeff'+plain.replace('"kind"',r'"\u006bind"').replace('DB2_TABLE_DESCRIPTION',r'\u0044B2_TABLE_DESCRIPTION')
                first=table_description(plain,body['provenance']);actual=table_description(bom,body['provenance'])
                self.assertEqual({k:v for k,v in first.items() if k!='source_hash'},{k:v for k,v in actual.items() if k!='source_hash'})
                self.assertEqual(actual['source_hash'],sha(bom.encode('utf-8')));self.assertNotEqual(actual['source_hash'],sha(bom[1:]))
                schema=schema_candidate(bom);self.assertEqual(schema['source_hash'],actual['source_hash'])
                self.assertEqual(schema['sqlite_ddl'],schema_candidate(plain)['sqlite_ddl']);self.assertFalse(schema['native_database_verified'])
                self.assertIn('NATIVE_SQL_TRANSACTION_TYPE_AND_AUTHORIZATION_EQUIVALENCE',actual['missing_semantics'])
                target=Path(self.tmp.name)/f'bom-catalog-{index}.sqlite';row={'ID':'0'*width}
                created=create_application_database(target,[schema],{'APP.X':[row]})
                self.assertEqual(sqlite_rows(target,created['sha256'],'APP.X')['rows'],[row]);states.add(actual['source_hash'])
        self.assertEqual(len(states),20)

    def test_bom_catalog_malformed_claims_block_and_unrelated_json_stays_unknown(self):
        from workbench.db2_catalog import MAX_CATALOG_BYTES,table_description
        marker='DB2_TABLE_DESCRIPTION'
        for ordinary in (encode({'kind':'OTHER','note':marker}).decode(),
                         '{"kind":"OTHER","note":"DB2_TABLE_DESCRIPTION",broken',
                         encode({'kind':'OTHER','note':marker+'X'*MAX_CATALOG_BYTES}).decode()):
            self.assertIsNone(table_description('\ufeff'+ordinary))
        for broken in ('{"kind":"DB2_TABLE_DESCRIPTION",broken',
                       '{"'+r'\u006bind'+'":"'+r'\u0044'+'B2_TABLE_DESCRIPTION",broken',
                       '{"kind":"DB2_TABLE_DESCRIPTION","kind":"OTHER"}'):
            with self.subTest(broken=broken),self.assertRaises(ValidationError):table_description('\ufeff'+broken)
        with self.assertRaisesRegex(ValidationError,'512 KiB'):
            table_description('\ufeff'+encode({'kind':marker,'note':'X'*MAX_CATALOG_BYTES}).decode())
        body={'schema_version':1,'kind':marker,'schema':'APP','table':'X',
              'columns':[{'NAME':'ID','COLNO':0,'COLTYPE':'CHAR','LENGTH':8,'NULLS':'N'}],
              'description_complete':True,'ddl':None,'constraints':None,'indexes':None,'triggers':None,
              'provenance':{'origin':'configured_mcp','tool':'db2_describe_table','locator':'APP.X','retrieved_at':'2026-10-07T16:00:00Z'}}
        for changes in ({'schema_version':True},{'columns':[]},{'kind':marker+'_INVALID'}):
            with self.subTest(changes=changes),self.assertRaises(ValidationError):table_description('\ufeff'+encode({**body,**changes}).decode())
        with self.assertRaises(ValidationError):table_description('\ufeff'+encode(body).decode(),{**body['provenance'],'tool':'zowe'})

    def test_catalog_unrelated_json_stays_unknown_and_typed_errors_stay_blocked(self):
        from workbench.db2_catalog import MAX_CATALOG_BYTES,table_description
        from workbench.limits import MAX_SOURCE_FILE_BYTES
        marker='DB2_TABLE_DESCRIPTION'
        for text in ('{"kind":"OTHER","note":"DB2_TABLE_DESCRIPTION"}',
                     '{"kind":"OTHER","note":"DB2_TABLE_DESCRIPTION",broken',
                     encode({'kind':'OTHER','note':marker+'X'*MAX_CATALOG_BYTES}).decode()):
            self.assertLess(len(text.encode()),MAX_SOURCE_FILE_BYTES);self.assertIsNone(table_description(text))
        broken='{"'+r'\u006bind'+'":"'+r'\u0044'+'B2_TABLE_DESCRIPTION",broken'
        with self.assertRaises(ValidationError):table_description(broken)
        oversized=encode({'kind':marker,'note':'X'*MAX_CATALOG_BYTES}).decode()
        with self.assertRaisesRegex(ValidationError,'512 KiB'):table_description(oversized)
        body={'schema_version':1,'kind':marker,'schema':'APP','table':'X',
              'columns':[{'NAME':'ID','COLNO':0,'COLTYPE':'CHAR','LENGTH':8,'NULLS':'N'}],
              'description_complete':True,'ddl':None,'constraints':None,'indexes':None,'triggers':None,
              'provenance':{'origin':'configured_mcp','tool':'db2_describe_table','locator':'APP.X','retrieved_at':'2026-10-07T16:00:00Z'}}
        for changes in ({'schema_version':True},{'columns':[]},{'kind':marker+'_INVALID'}):
            with self.subTest(changes=changes),self.assertRaises(ValidationError):table_description(encode({**body,**changes}).decode())
        with self.assertRaises(ValidationError):table_description(encode(body).decode(),{**body['provenance'],'tool':'zowe'})

    def test_typed_catalog_emits_column_candidate_without_invented_metadata(self):
        catalog={'schema_version':1,'kind':'DB2_TABLE_DESCRIPTION','schema':'APP','table':'X',
                 'columns':[{'NAME':'ID','COLNO':0,'COLTYPE':'CHAR','LENGTH':8,'NULLS':'N'},
                            {'NAME':'MONEY','COLNO':1,'COLTYPE':'DECIMAL','LENGTH':9,'SCALE':2,'NULLS':'Y'}],
                 'description_complete':True,'ddl':None,'constraints':None,'indexes':None,'triggers':None,
                 'provenance':{'origin':'configured_mcp','tool':'db2_describe_table','locator':'APP.X','retrieved_at':'2026-10-07T16:00:00Z'}}
        schema=schema_candidate(encode(catalog).decode());self.assertTrue(schema['can_build'])
        self.assertEqual(schema['tables'][0]['columns'][1]['precision'],9);self.assertEqual(schema['tables'][0]['key_columns'],[])
        self.assertTrue(any('CONSTRAINTS' in g['message'] for g in schema['gaps']))
        create_application_database(self.path,[schema],{'APP.X':[{'ID':'00000001','MONEY':'10.00'}]})
        catalog['description_complete']=False;self.assertFalse(schema_candidate(encode(catalog).decode())['can_build'])

    def test_read_browser_hash_filter_and_injection_boundaries(self):
        schema=schema_candidate('CREATE TABLE APP.X (ID INTEGER NOT NULL PRIMARY KEY,V VARCHAR(20));')
        created=create_application_database(self.path,[schema],{'APP.X':[{'ID':i,'V':'v'+str(i)} for i in range(25)]})
        digest=created['sha256'];before=self.path.read_bytes();page=sqlite_rows(self.path,digest,'APP.X',limit=20)
        self.assertTrue(page['has_more']);self.assertEqual(page['next_after'],20)
        self.assertEqual(sqlite_rows(self.path,digest,'APP.X',after=20)['rows'][0]['ID'],20)
        self.assertEqual(sqlite_rows(self.path,digest,'APP.X',filters={'ID':3})['rows'],[{'ID':3,'V':'v3'}])
        for call in (lambda:sqlite_rows(self.path,digest,'APP.X; DROP TABLE "APP.X"'),lambda:sqlite_rows(self.path,digest,'APP.X',filters={'unknown':1}),
                     lambda:sqlite_rows(self.path,digest,'APP.X',limit=101),lambda:sqlite_schema(self.path,'0'*64)):
            with self.assertRaises(ValidationError):call()
        self.assertEqual(before,self.path.read_bytes())
        link=Path(self.tmp.name)/'linked.sqlite';link.symlink_to(self.path)
        with self.assertRaises(ValidationError):sqlite_schema(link,digest)
        with self.assertRaises(ValidationError):create_application_database(self.path,[schema])

    def test_keyed_delta_does_not_ignore_twenty_historical_source_only_rows(self):
        historical=[{'ID':str(i).zfill(8),'VALUE':'old'} for i in range(20)]
        added=[{'ID':str(i).zfill(8),'VALUE':'new'} for i in range(20,25)]
        comparison=compare_snapshots(receipt(historical,'before'),receipt(historical+added,'after'),receipt([],'before','sqlite'),receipt(added,'after','sqlite'),CONTEXT)
        self.assertEqual(comparison['summary']['db2_after_rows'],25);self.assertEqual(comparison['summary']['sqlite_after_rows'],5)
        self.assertTrue(comparison['summary']['run_delta_matches']);self.assertFalse(comparison['summary']['complete_exported_scope_match'])
        self.assertEqual(comparison['summary']['baseline_gap_records'],20);self.assertEqual(comparison['summary']['historical_records'],20)
        self.assertEqual(comparison['summary']['matching_changed_records'],5)
        self.assertEqual(len([r for r in comparison['records'] if r['historical'] and 'Historical' in r['reason']]),20)
        self.assertFalse(comparison['native_database_verified']);self.assertFalse(comparison['observed_program_parity'])

    def test_twenty_randomized_full_record_runs_compare_actual_sqlite_baseline_and_outputs(self):
        seed=secrets.randbits(63);rng=random.Random(seed);schema=schema_candidate('CREATE TABLE APP.SALE (ID CHAR(8) NOT NULL PRIMARY KEY, VALUE VARCHAR(40));')
        for index in range(20):
            with self.subTest(seed=seed,run=index):
                old=[{'ID':str(index*10).zfill(8),'VALUE':'old'+str(rng.randrange(10**9))}]
                after=[{'ID':old[0]['ID'],'VALUE':'changed'+str(rng.randrange(10**9))},{'ID':str(index*10+1).zfill(8),'VALUE':'new'+str(rng.randrange(10**9))}]
                bp=Path(self.tmp.name)/f'before-{index}.sqlite';ap=Path(self.tmp.name)/f'after-{index}.sqlite'
                br=create_application_database(bp,[schema],{'APP.SALE':old});ar=create_application_database(ap,[schema],{'APP.SALE':after})
                source_before=receipt(old,'before');source_after=receipt(after,'after')
                # Synthetic capture chronology must not depend on OS clock tick resolution.
                capture_times=(datetime(2026,10,7,16,tzinfo=timezone.utc),datetime(2026,10,7,17,tzinfo=timezone.utc))
                with patch('workbench.database.datetime',wraps=datetime) as clock:
                    clock.now.side_effect=capture_times
                    target_before=sqlite_snapshot(bp,br['sha256'],'APP.SALE',source_before,CONTEXT['sqlite_run_id'],CONTEXT['input_hashes'],CONTEXT['sqlite_environment'],'before')
                    target_after=sqlite_snapshot(ap,ar['sha256'],'APP.SALE',source_after,CONTEXT['sqlite_run_id'],CONTEXT['input_hashes'],CONTEXT['sqlite_environment'],'after')
                self.assertEqual(clock.now.call_count,2)
                self.assertEqual([s['provenance']['retrieved_at'] for s in (target_before,target_after)],[t.isoformat() for t in capture_times])
                result=compare_snapshots(source_before,source_after,target_before,target_after,CONTEXT)
                self.assertTrue(result['summary']['complete_exported_scope_match']);self.assertEqual({r['db2_operation'] for r in result['records']},{'INSERT','UPDATE'})
                bad=raw(target_after);bad['rows'][0]['VALUE']='adversarial mismatch'
                mutant=validate_snapshot(encode(bad).decode());result=compare_snapshots(source_before,source_after,target_before,mutant,CONTEXT)
                self.assertFalse(result['summary']['complete_exported_scope_match']);self.assertTrue(result['gaps'])

    def test_same_totals_different_keys_operations_and_values_are_specific_gaps(self):
        before=[{'ID':'00000001','VALUE':'a'},{'ID':'00000002','VALUE':'b'}];after=[{'ID':'00000001','VALUE':'changed'},{'ID':'00000003','VALUE':'c'}]
        target=[{'ID':'00000001','VALUE':'wrong'},{'ID':'00000004','VALUE':'c'}]
        comparison=compare_snapshots(receipt(before,'before'),receipt(after,'after'),receipt(before,'before','sqlite'),receipt(target,'after','sqlite'),CONTEXT)
        self.assertFalse(comparison['summary']['run_delta_matches']);self.assertEqual(comparison['summary']['db2_after_rows'],comparison['summary']['sqlite_after_rows'])
        self.assertEqual({r['db2_operation'] for r in comparison['records']},{'INSERT','UPDATE','DELETE','ABSENT'})
        changed=next(r for r in comparison['records'] if r['key']==['00000001']);self.assertEqual(changed['changed_columns'],['VALUE']);self.assertFalse(changed['final_match'])

    def test_binding_scope_consistency_and_exact_export_tampering_revoke_equality(self):
        rows=[{'ID':'00000001','VALUE':'a'}];snapshots=[receipt(rows,'before'),receipt(rows,'after'),receipt(rows,'before','sqlite'),receipt(rows,'after','sqlite')]
        for field,value in (('run_id','wrong'),('environment','I_NONPROD'),('input_hashes',{'input/sale.txt':sha('different version')}),
                            ('scope',{'kind':'full_table','keys':[],'complete':False}),('consistency',{'status':'unverified','evidence':[]})):
            with self.subTest(field=field):
                changed=raw(snapshots[1]);changed[field]=value
                result=compare_snapshots(snapshots[0],validate_snapshot(encode(changed).decode()),snapshots[2],snapshots[3],CONTEXT)
                self.assertFalse(result['summary']['complete_exported_scope_match']);self.assertFalse(result['summary']['run_delta_matches'])
        changed=deepcopy(snapshots[1]);changed['rows'][0]['VALUE']='tampered'
        with self.assertRaises(ValidationError):compare_snapshots(snapshots[0],changed,snapshots[2],snapshots[3],CONTEXT)
        for field,value in (('rows',[rows[0],rows[0]]),('rows',[{'ID':None,'VALUE':'a'}]),('rows',[{'ID':1.0,'VALUE':'a'}]),
                            ('provenance',{'origin':'zowe_cli','tool':'zowe files view ds','locator':'APP.SALE','retrieved_at':'2026-10-07T16:00:00Z'})):
            changed=raw(snapshots[1]);changed[field]=value
            with self.subTest(field=field,value=value),self.assertRaises(ValidationError):validate_snapshot(encode(changed).decode())

    def test_ui_filter_codec_preserves_bigint_and_identifier_types(self):
        filters=decode_filters({'ID':{'type':'text','value':'00000001'},'BIG':{'type':'integer','value':'9223372036854775807'},'VALUE':{'type':'null','value':None}})
        self.assertEqual(filters,{'ID':'00000001','BIG':2**63-1,'VALUE':None})
        self.assertEqual(decode_filters({'BIG':{'type':'integer','value':'-9223372036854775808'}})['BIG'],-2**63)
        for value in ('+1','01','-0','',1,True,'9223372036854775808','-9223372036854775809',' 1','1.0'):
            with self.subTest(value=value),self.assertRaises(ValidationError):decode_filters({'BIG':{'type':'integer','value':value}})
        schema=schema_candidate('CREATE TABLE APP.FILTER (ID CHAR(8) NOT NULL PRIMARY KEY,BIG BIGINT NOT NULL);')
        created=create_application_database(self.path,[schema],{'APP.FILTER':[{'ID':'00000001','BIG':2**63-1}]})
        self.assertEqual(sqlite_rows(self.path,created['sha256'],'APP.FILTER',filters=decode_filters({'BIG':{'type':'integer','value':str(2**63-1)}}))['display_rows'],[{'ID':'00000001','BIG':str(2**63-1)}])
        self.assertEqual(sqlite_rows(self.path,created['sha256'],'APP.FILTER',filters=decode_filters({'BIG':{'type':'text','value':str(2**63-1)}}))['rows'],[])

    def test_single_file_snapshots_reject_unhashed_wal_and_sidecars(self):
        db=sqlite3.connect(self.path);self.addCleanup(db.close)
        db.execute('PRAGMA journal_mode=WAL');db.execute('CREATE TABLE X (V TEXT)');db.commit()
        digest=sha(self.path.read_bytes());db.execute('INSERT INTO X VALUES (?)',('unhashed row',));db.commit()
        self.assertEqual(digest,sha(self.path.read_bytes()))
        with self.assertRaisesRegex(ValidationError,'sidecars'):sqlite_rows(self.path,digest,'X')
        db.close()
        sqlite_schema(self.path,sha(self.path.read_bytes()))

    def test_exact_typed_filters_do_not_coerce_legacy_affinity(self):
        db=sqlite3.connect(self.path);db.execute('CREATE TABLE X (V TEXT)');db.execute('INSERT INTO X VALUES (?)',('1',));db.commit();db.close()
        digest=sha(self.path.read_bytes())
        self.assertEqual(sqlite_rows(self.path,digest,'X',filters={'V':1})['rows'],[])
        self.assertEqual(sqlite_rows(self.path,digest,'X',filters={'V':'1'})['rows'],[{'V':'1'}])

    def test_nullable_db2_keys_and_malformed_snapshot_shapes_fail_closed(self):
        for source in ('CREATE TABLE APP.X (ID INTEGER PRIMARY KEY);','CREATE TABLE APP.X (ID INTEGER UNIQUE);',
                       'CREATE TABLE APP.X (ID INTEGER, PRIMARY KEY(ID));'):
            model=schema_candidate(source);self.assertFalse(model['can_build']);self.assertTrue(any(g['kind']=='database_constraint_gap' for g in model['gaps']))
        for field,value in [('column_names',[['ID']]),('key_columns',[['ID']]),('column_names',[1]),('key_columns',[{}])]:
            malformed=raw(receipt([],'before'));malformed[field]=value
            with self.subTest(field=field,value=value),self.assertRaises(ValidationError):validate_snapshot(encode(malformed).decode())
        before=receipt([{'ID':1,'VALUE':'a'}],'before');mutant=deepcopy(before);mutant['rows'][0]['ID']=True
        with self.assertRaises(ValidationError):_compare_snapshots(mutant,receipt([],'after'),receipt([],'before','sqlite'),receipt([],'after','sqlite'),CONTEXT)

    def test_consistency_references_require_accepted_evidence_and_time_order(self):
        snapshots=[receipt([],'before'),receipt([],'after'),receipt([],'before','sqlite'),receipt([],'after','sqlite')]
        result=_compare_snapshots(*snapshots,CONTEXT)
        self.assertFalse(result['summary']['complete_exported_scope_match']);self.assertEqual(len(result['gaps']),4)
        for side,after_index in (('db2',1),('sqlite',3)):
            for timestamp in ('2026-10-07T15:00:00Z','2026-10-07T16:00:00Z'):
                with self.subTest(side=side,after_timestamp=timestamp):
                    after=raw(snapshots[after_index]);after['provenance']['retrieved_at']=timestamp
                    changed=list(snapshots);changed[after_index]=validate_snapshot(encode(after).decode())
                    result=compare_snapshots(*changed,CONTEXT)
                    self.assertFalse(result['summary']['complete_exported_scope_match']);self.assertFalse(result['summary']['run_delta_matches'])
                    self.assertTrue(any(g.get('field')=='retrieved_at' and g.get('side')==side for g in result['gaps']))

    def test_create_and_read_operations_propagate_cancellation_without_partial_database(self):
        schema=schema_candidate(DDL)
        class Cancelled(Exception):pass
        count=[0]
        def cancel():
            count[0]+=1
            if count[0]>2:raise Cancelled('operator cancelled')
        row={'ID':'00000001','NAME':'A','SMALL':1,'NUMBER':2,'BIG':3,'AMOUNT':'1.00'}
        with self.assertRaises(Cancelled):create_application_database(self.path,[schema],{'APP.SALE':[row]},checkpoint=cancel)
        self.assertFalse(self.path.exists())
        rows=[{'ID':str(i).zfill(8),'NAME':'A','SMALL':1,'NUMBER':2,'BIG':3,'AMOUNT':'1.00'} for i in range(300)]
        created=create_application_database(self.path,[schema],{'APP.SALE':rows});count[0]=0
        def cancel_read():
            count[0]+=1
            raise Cancelled('read cancelled')
        with self.assertRaises(Cancelled):sqlite_rows(self.path,created['sha256'],'APP.SALE',checkpoint=cancel_read)
        self.assertEqual(sha(self.path.read_bytes()),created['sha256']);self.assertEqual(count[0],1)

if __name__=='__main__':unittest.main()
