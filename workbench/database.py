"""Bounded local Db2 storage candidates and hash-bound record comparisons.

This is an adapter used by the Coordinator, not a workflow or a Db2 client.
Only generated SQLite schema executes. Export equality never proves native SQL,
transaction, constraint, collation, authorization or whole-program equivalence.
"""
from contextlib import contextmanager
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
import re
import sqlite3
import stat

from .domain import ValidationError, decode, encode, require, sha
from .layout import path_is_link

PROFILE = 'DB2_STORAGE_SCHEMA_V1'
NAME = r'[A-Z@$#][A-Z0-9@$#_]{0,127}'
QUALIFIED = NAME + r'\.' + NAME
MAX_BYTES = 1024 * 1024
MAX_ROWS = 10000
MAX_COLUMNS = 256
MAX_VALUE_CHARS = 32704
MAX_DB_BYTES = 128 * 1024 * 1024
INTEGER_RANGES = {'SMALLINT': (-32768,32767), 'INTEGER': (-2147483648,2147483647), 'BIGINT': (-2**63,2**63-1)}
NATIVE_GAPS = ['NATIVE_SQL_ARITHMETIC_AND_ERROR_BEHAVIOR', 'TRANSACTION_ISOLATION_LOCKING_AND_RECOVERY',
               'CCSID_COLLATION_AND_ASSIGNMENT_PADDING', 'AUTHORIZATION_AND_DEPENDENT_PROGRAM_EFFECTS']
SNAPSHOT_FIELDS = {'schema_version','kind','schema','table','column_names','key_columns','rows','phase',
                   'run_id','input_hashes','environment','scope','provenance','consistency'}


def _name(value):
    require(isinstance(value,str) and re.fullmatch(NAME,value), 'Exact uppercase unquoted database identity required')
    return value


def _hash(value):
    require(isinstance(value,str) and re.fullmatch(r'[a-f0-9]{64}',value), 'Exact SHA-256 required')
    return value


def _text(value, label, maximum=2000):
    require(isinstance(value,str) and 0<len(value)<=maximum and not any(ord(c)<32 for c in value),label+' must be bounded text')
    return value


def _timestamp(value):
    _text(value,'Observation timestamp')
    try: result=datetime.fromisoformat(value.replace('Z','+00:00'))
    except ValueError: raise ValidationError('Observation timestamp must be ISO with timezone')
    require(result.tzinfo is not None,'Observation timestamp requires timezone')
    return result


def _quote(value):
    return '"'+value.replace('"','""')+'"'


def _split(text, separator=','):
    out=[];start=0;depth=0;quote=None;i=0
    while i<len(text):
        c=text[i]
        if quote:
            if c==quote:
                if i+1<len(text) and text[i+1]==quote:i+=2;continue
                quote=None
        elif c in "'\"":quote=c
        elif c=='(':depth+=1
        elif c==')':depth-=1;require(depth>=0,'Unbalanced SQL operands')
        elif c==separator and depth==0:out.append(text[start:i]);start=i+1
        i+=1
    require(not quote and depth==0,'Unclosed SQL literal or operands')
    # Empty final comma operands are invalid DDL and must remain visible to
    # the column parser. A trailing statement semicolon is ordinary syntax.
    if text[start:].strip() or separator==',':out.append(text[start:])
    return out


def _gap(kind,message,source_path,source_hash,first=1,last=1,**extra):
    return {'kind':kind,'message':message,'source_path':source_path,'source_hash':source_hash,
            'start_line':first,'end_line':last,**extra}


def _column(name, datatype, nullable=True):
    _name(name);datatype=re.sub(r'\s+','',datatype.upper())
    c={'name':name,'source_type':datatype,'nullable':nullable,'sqlite_type':'ANY'}
    alias={'INT':'INTEGER','CHARACTER':'CHAR','DEC':'DECIMAL','NUMERIC':'DECIMAL'}
    m=re.fullmatch(r'([A-Z]+)(?:\((\d+)(?:,(\d+))?\))?',datatype)
    require(m is not None,'Unsupported datatype '+datatype)
    base=alias.get(m[1],m[1]);p=int(m[2]) if m[2] else None;s=int(m[3]) if m[3] else None
    c['type']=base
    if base in INTEGER_RANGES:
        require(p is None,'Integer datatype cannot have length');c.update(minimum=INTEGER_RANGES[base][0],maximum=INTEGER_RANGES[base][1])
    elif base in ('CHAR','VARCHAR'):
        p=p if p is not None else 1 if base=='CHAR' else None
        require(type(p) is int and 1<=p<=(255 if base=='CHAR' else 32704) and s is None,'Unsupported character length')
        c['length']=p;c['representation']='PRINTABLE_ASCII_EXACT_NO_PADDING_OR_TRIMMING'
    elif base=='DECIMAL':
        p=5 if p is None else p;s=0 if s is None else s
        require(1<=p<=31 and 0<=s<=p,'Unsupported decimal precision/scale')
        c.update(precision=p,scale=s,representation='CANONICAL_FIXED_SCALE_TEXT_NO_FLOAT_OR_ARITHMETIC')
    else:raise ValidationError('Datatype '+datatype+' needs a source-supported replacement (consider exact text/binary storage and explicit codecs; no lossy fallback)')
    return c


def _value_valid(column,value):
    if value is None:return column['nullable']
    if column['type'] in INTEGER_RANGES:return type(value) is int and column['minimum']<=value<=column['maximum']
    if column['type'] in ('CHAR','VARCHAR'):
        return type(value) is str and all(32<=ord(c)<=126 for c in value) and (len(value)==column['length'] if column['type']=='CHAR' else len(value)<=column['length'])
    if column['type']=='DECIMAL':
        if type(value) is not str:return False
        scale=column['scale'];integer_digits=column['precision']-scale
        integral=r'0' if integer_digits==0 else r'(?:0|[1-9][0-9]{0,'+str(integer_digits-1)+'})'
        pattern=r'-?'+integral+(r'\.[0-9]{'+str(scale)+'}' if scale else '')
        return bool(re.fullmatch(pattern,value)) and value!='-0'+('.'+'0'*scale if scale else '')
    return False


def _check(column):
    q=_quote(column['name']);kind=column['type']
    if kind in INTEGER_RANGES:condition=f"typeof({q})='integer' AND {q} BETWEEN {column['minimum']} AND {column['maximum']}"
    elif kind in ('CHAR','VARCHAR'):
        op='=' if kind=='CHAR' else '<='
        condition=f"typeof({q})='text' AND length({q}) {op} {column['length']} AND length(CAST({q} AS BLOB))=length({q}) AND {q} NOT GLOB '*[^ -~]*'"
    else:
        base=f"ltrim({q},'-')";scale=column['scale'];digits=column['precision']-scale
        integral=f"substr({base},1,instr({base},'.')-1)" if scale else base
        parts=[f"typeof({q})='text'",f"length(CAST({q} AS BLOB))=length({q})",f"{q} NOT GLOB '*[^0-9.-]*'",f"length({q})-length(replace({q},'-',''))=CASE WHEN substr({q},1,1)='-' THEN 1 ELSE 0 END"]
        if scale:parts += [f"length({base})-length(replace({base},'.',''))=1",f"length(substr({base},instr({base},'.')+1))={scale}"]
        else:parts += [f"instr({base},'.')=0"]
        parts += [f"length({integral}) BETWEEN 1 AND {max(1,digits)}",f"{integral}='0'" if digits==0 else f"(length({integral})=1 OR substr({integral},1,1)!='0')",f"{q}!='-0"+('.'+'0'*scale if scale else '')+"'"]
        condition=' AND '.join(parts)
    return f'CHECK ({q} IS NULL OR ({condition}))'


def _emit_table(table):
    columns=[]
    for column in table['columns']:
        columns.append('  '+_quote(column['name'])+' ANY'+(' NOT NULL' if not column['nullable'] else '')+' '+_check(column))
    for constraint in table['constraints']:
        columns.append('  '+('PRIMARY KEY' if constraint['kind']=='PRIMARY_KEY' else 'UNIQUE')+' ('+', '.join(_quote(c) for c in constraint['columns'])+')')
    return 'CREATE TABLE '+_quote(table['sqlite_name'])+' (\n'+',\n'.join(columns)+'\n) STRICT;'


def schema_candidate(text,provenance=None,source_path=None):
    """Parse literal CREATE TABLE or typed columns; never execute source SQL."""
    require(isinstance(text,str) and len(text.encode())<=MAX_BYTES,'Schema source exceeds bounded UTF-8 limit')
    source_hash=sha(text);gaps=[];units=[];tables=[]
    from .db2_catalog import table_description
    catalog=table_description(text,provenance)
    def gap(kind,message,first=1,last=None,**extra):
        item=_gap(kind,message,source_path,source_hash,first,last or first,**extra);gaps.append(item);return item
    def table_model(name,first,last):
        schema,table=name.split('.')
        return {'name':name,'schema':schema,'table':table,'sqlite_name':name,'columns':[],'constraints':[],
                'key_columns':[],'source_path':source_path,'source_hash':source_hash,'start_line':first,'end_line':last,'support':'storage_supported'}
    if catalog:
        table=table_model(catalog['schema']+'.'+catalog['table'],1,len(text.splitlines()) or 1);tables.append(table)
        if not catalog['description_complete']:
            table['support']='unsupported';gap('database_catalog_gap','Partial columns cannot emit a complete application table',table=table['name'])
        for observed in catalog['columns']:
            datatype=observed['COLTYPE'].strip()
            if datatype in ('CHAR','VARCHAR'):datatype+='('+str(observed['LENGTH'])+')'
            if datatype=='DECIMAL':
                if 'SCALE' not in observed:datatype='DECIMAL_WITH_UNKNOWN_SCALE'
                else:datatype+='('+str(observed['LENGTH'])+','+str(observed['SCALE'])+')'
            try:column=_column(observed['NAME'],datatype,observed['NULLS']=='Y');table['columns'].append(column)
            except ValidationError as exc:table['support']='unsupported';gap('database_type_gap',str(exc),column=observed['NAME'],table=table['name'])
            if observed.get('DEFAULTVALUE') is not None or observed.get('DEFAULT') not in (None,'N',''):
                table['support']='unsupported';gap('database_default_gap','Observed column default requires explicit assignment/default semantics before schema emission',column=observed['NAME'])
        for kind in ('constraints','indexes','triggers'):
            if catalog[kind] is None:gap('database_metadata_gap',kind.upper()+' not observed; column-only candidate earns no complete schema credit',table=table['name'])
            elif catalog[kind]:
                table['support']='unsupported';gap('database_feature_gap','Observed '+kind+' require an exact supported descriptor or source DDL; do not discard them',table=table['name'])
        if catalog['ddl'] is not None:gap('database_ddl_review_gap','Nested DDL is preserved but is not executed or silently credited by this column-only candidate; its native/default/constraint effects require separate exact adapters',ddl_hash=sha(catalog['ddl']),table=table['name'])
        for column in table['columns']:
            units.append({'kind':'database_column','table':table['name'],'column':column['name'],'source_path':source_path,'source_hash':source_hash,'start_line':1,'end_line':len(text.splitlines()) or 1,
                          'source_pointer':'/columns/'+str(next(i for i,c in enumerate(catalog['columns']) if c['NAME']==column['name'])),
                          'support':table['support'],'replacement':column.get('representation','Exact bounded signed integer storage; no SQLite affinity coercion.')})
        units.append({'kind':'database_table','table':table['name'],'source_path':source_path,'source_hash':source_hash,'start_line':1,'end_line':len(text.splitlines()) or 1,'support':table['support'],'replacement':'Column-only SQLite storage candidate; complete constraints/indexes/triggers and native SQL remain unverified.'})
    else:
        # Strip comments while preserving offsets/physical lines; quoted SQL cannot
        # turn into executable statements. Delimited identifiers remain unsupported.
        cleaned=re.sub(r'/\*.*?\*/',lambda m:''.join('\n' if c=='\n' else ' ' for c in m[0]),text,flags=re.S)
        cleaned=re.sub(r'--[^\n]*',lambda m:' '*len(m[0]),cleaned)
        try:statements=_split(cleaned,';')
        except ValidationError as exc:gap('database_ddl_gap',str(exc),1,len(text.splitlines()) or 1);statements=[]
        cursor=0
        for statement in statements:
            start=cleaned.find(statement,cursor);cursor=start+len(statement);first=cleaned.count('\n',0,start)+1;last=cleaned.count('\n',0,cursor)+1
            statement_start=start+len(statement)-len(statement.lstrip());statement=statement.strip()
            first=cleaned.count('\n',0,statement_start)+1
            if not statement:continue
            match=re.fullmatch(r'CREATE\s+TABLE\s+('+QUALIFIED+r')\s*\((.*)\)\s*',statement,re.I|re.S)
            if not match:
                gap('database_ddl_gap','Statement is not supported literal CREATE TABLE: '+statement[:200],first,last);units.append({'kind':'database_feature','source_path':source_path,'source_hash':source_hash,'start_line':first,'end_line':last,'support':'unsupported','replacement':'Named DDL obligation; original statement retained and never executed.'});continue
            name=match[1].upper()
            if not re.fullmatch(QUALIFIED,name):
                gap('database_identity_gap','Source table requires exact supported uppercase unquoted identity',first,last);continue
            table=table_model(name,first,last);tables.append(table)
            definition_cursor=0;body_start=statement_start+match.start(2)
            for definition in _split(match[2]):
                offset=match[2].find(definition,definition_cursor);definition_cursor=offset+len(definition)
                offset+=len(definition)-len(definition.lstrip());definition=definition.strip()
                dfirst=cleaned.count('\n',0,body_start+offset)+1;dlast=cleaned.count('\n',0,body_start+offset+len(definition))+1
                constraint=re.fullmatch(r'(?:CONSTRAINT\s+('+NAME+r')\s+)?(PRIMARY\s+KEY|UNIQUE)\s*\(([^()]*)\)',definition,re.I)
                if constraint:
                    try:columns=[_name(c.strip().upper()) for c in constraint[3].split(',')];require(len(columns)==len(set(columns)) and columns,'Repeated/empty constraint columns');table['constraints'].append({'kind':'PRIMARY_KEY' if constraint[2].upper().startswith('PRIMARY') else 'UNIQUE','columns':columns})
                    except ValidationError as exc:table['support']='unsupported';gap('database_constraint_gap',str(exc),dfirst,dlast,table=name)
                    units.append({'kind':'database_constraint','table':name,'source_path':source_path,'source_hash':source_hash,'start_line':dfirst,'end_line':dlast,'support':table['support'],'replacement':'Exact primary/unique value constraint on source-declared nonnull keys; native indexes remain separate obligations.'})
                    continue
                column_match=re.fullmatch(r'('+NAME+r')\s+([A-Z]+(?:\s*\(\s*\d+(?:\s*,\s*\d+)?\s*\))?)\s*(NOT\s+NULL|NULL)?\s*(PRIMARY\s+KEY|UNIQUE)?',definition,re.I)
                if not column_match:
                    message=('Empty column/constraint definition (leading, repeated or trailing comma)' if not definition else
                             'Unsupported column/constraint/default/generated expression: '+definition[:200])
                    table['support']='unsupported';gap('database_column_gap',message,dfirst,dlast,table=name);continue
                try:
                    column=_column(column_match[1].upper(),column_match[2],not bool(column_match[3] and column_match[3].upper().startswith('NOT')))
                    table['columns'].append(column)
                    if column_match[4]:table['constraints'].append({'kind':'PRIMARY_KEY' if column_match[4].upper().startswith('PRIMARY') else 'UNIQUE','columns':[column['name']]})
                    units.append({'kind':'database_column','table':name,'column':column['name'],'source_path':source_path,'source_hash':source_hash,'start_line':dfirst,'end_line':dlast,'support':'storage_supported','replacement':column['representation'] if 'representation' in column else 'Exact bounded signed integer storage; no SQLite affinity coercion.'})
                except ValidationError as exc:table['support']='unsupported';gap('database_type_gap',str(exc),dfirst,dlast,table=name,column=column_match[1].upper())
            units.append({'kind':'database_table','table':name,'source_path':source_path,'source_hash':source_hash,'start_line':first,'end_line':last,'support':table['support'],'replacement':'Generated SQLite STRICT/ANY storage with explicit domain checks; native SQL effects remain unverified.'})
    declarations={}
    for table in tables:declarations.setdefault(table['name'],[]).append(table)
    for table in tables:
        names=[c['name'] for c in table['columns']]
        if len(declarations[table['name']])>1:
            table['support']='unsupported'
            gap('database_structure_gap','Multiple CREATE TABLE definitions for '+table['name']+'; no definition is selected or emitted',
                table['start_line'],table['end_line'],table=table['name'],
                declaration_count=len(declarations[table['name']]),
                declarations=[{'start_line':item['start_line'],'end_line':item['end_line']} for item in declarations[table['name']][:2]])
        if not names or len(names)>MAX_COLUMNS or len(names)!=len(set(names)):
            table['support']='unsupported';gap('database_structure_gap','Duplicate column identity or invalid column count',table['start_line'],table['end_line'],table=table['name'])
        primary=[c for c in table['constraints'] if c['kind']=='PRIMARY_KEY']
        if len(primary)>1 or any(not set(c['columns'])<=set(names) for c in table['constraints']):
            table['support']='unsupported';gap('database_constraint_gap','Primary key repeated or constraint columns missing',table=table['name'])
        key_names=set().union(*(set(c['columns']) for c in table['constraints'])) if table['constraints'] else set()
        if any(column['nullable'] and column['name'] in key_names for column in table['columns']):
            table['support']='unsupported';gap('database_constraint_gap','Db2 primary/unique key columns require explicit NOT NULL; never invent source nullability',table=table['name'])
        if len(primary)==1:table['key_columns']=primary[0]['columns']
    support_by_table={table['name']:table['support'] for table in tables}
    for unit in units:
        if unit.get('table') in support_by_table:unit['support']=support_by_table[unit['table']]
    for obligation in NATIVE_GAPS:gap('database_native_gap',obligation+' has no verified native database replacement')
    supported=[table for table in tables if table['support']=='storage_supported']
    return {'schema_version':1,'profile':PROFILE,'source_path':source_path,'source_hash':source_hash,'source_text':text,
            'provenance':deepcopy(provenance),'tables':tables,'units':units,'gaps':gaps,'can_build':bool(supported),
            'sqlite_ddl':'\n\n'.join(_emit_table(table) for table in supported)+'\n' if supported else '',
            'native_database_verified':False,'basis':'SOURCE_DERIVED_STORAGE_CANDIDATE'}


def _validated_schema(schema):
    require(isinstance(schema,dict) and schema.get('profile')==PROFILE,'Unsupported database schema contract')
    require(isinstance(schema.get('source_text'),str),'Database schema requires its exact source bytes')
    expected=schema_candidate(schema['source_text'],schema.get('provenance'),schema.get('source_path'))
    require(encode(expected)==encode(schema),'Database schema differs from source-owned deterministic candidate')
    return schema


def create_application_database(path,schemas,rows_by_table=None,checkpoint=None):
    """Create a new process-owned candidate using only our exact emitted DDL."""
    path=Path(path).absolute();require(not path.exists() and not any(path_is_link(p) for p in (path,*path.parents)),'Application database requires a new nonlinked path')
    require(isinstance(schemas,list) and 0<len(schemas)<=100,'Bounded schema candidates required')
    tables={}
    for schema in schemas:
        if checkpoint:checkpoint()
        _validated_schema(schema)
        for table in schema['tables']:
            if table['support']=='storage_supported':require(table['name'] not in tables,'Duplicate application table');tables[table['name']]=table
    require(tables,'No supported storage tables');rows_by_table=rows_by_table or {};require(isinstance(rows_by_table,dict) and set(rows_by_table)<=set(tables),'Unknown application table rows')
    path.parent.mkdir(parents=True,exist_ok=True);path.touch(exist_ok=False);db=None
    try:
        db=sqlite3.connect(path);db.execute('PRAGMA journal_mode=DELETE');db.execute('PRAGMA foreign_keys=ON')
        with db:
            for name,table in tables.items():
                if checkpoint:checkpoint()
                db.execute(_emit_table(table));rows=rows_by_table.get(name,[])
                require(isinstance(rows,list) and len(rows)<=MAX_ROWS,'Application rows exceed bound')
                columns=table['columns'];names=[c['name'] for c in columns]
                for row in rows:
                    if checkpoint:checkpoint()
                    require(isinstance(row,dict) and set(row)==set(names) and all(_value_valid(c,row[c['name']]) for c in columns),'Application row violates exact source storage domain')
                    db.execute('INSERT INTO '+_quote(name)+' ('+', '.join(_quote(n) for n in names)+') VALUES ('+', '.join('?' for _ in names)+')',[row[n] for n in names])
        db.close();db=None
        return {'path':str(path),'sha256':sha(path.read_bytes()),'tables':[{'name':name,'rows':len(rows_by_table.get(name,[])),'source_hash':table['source_hash']} for name,table in tables.items()],
                'profile':PROFILE,'native_database_verified':False,'gaps':[gap for schema in schemas for gap in schema['gaps']]}
    except BaseException:
        if db:db.close()
        if path.exists():path.unlink()
        for suffix in ('-journal','-wal','-shm'):
            extra=Path(str(path)+suffix)
            if extra.exists():extra.unlink()
        raise


@contextmanager
def _read_database(path,expected_hash,checkpoint=None):
    path=Path(path).absolute();_hash(expected_hash)
    require(not any(path_is_link(p) for p in (path,*path.parents)) and path.is_file() and stat.S_ISREG(path.stat().st_mode),'Database must be a regular nonlinked registered file')
    require(path.stat().st_size<=MAX_DB_BYTES,'Database exceeds local read bound')
    def check_file():
        require(not any(path_is_link(p) for p in (path,*path.parents)) and path.is_file(),'Database replaced by missing/linked file')
        require(not any(Path(str(path)+suffix).exists() or path_is_link(Path(str(path)+suffix)) for suffix in ('-wal','-shm','-journal')),'Database has unregistered journal/WAL sidecars; export a closed single-file snapshot')
        require(path.stat().st_size<=MAX_DB_BYTES and sha(path.read_bytes())==expected_hash,'Database changed from immutable artifact hash')
    check_file()
    # immutable avoids journal recovery/sidecar writes; checks reject sidecars
    # rather than silently dropping committed WAL content from the snapshot.
    db=sqlite3.connect(path.as_uri()+'?mode=ro&immutable=1',uri=True,timeout=1)
    db.enable_load_extension(False);db.execute('PRAGMA query_only=ON');db.execute('PRAGMA trusted_schema=OFF')
    steps=[0];interrupted=[]
    def progress():
        steps[0]+=1
        if checkpoint:
            try:checkpoint()
            except BaseException as exc:interrupted.append(exc);return 1
        return 1 if steps[0]>10000 else 0
    db.set_progress_handler(progress,1000)
    try:
        yield db
        check_file()
    except sqlite3.OperationalError:
        if interrupted:raise interrupted[0]
        raise
    finally:db.close()


def _tables(db):
    require(not db.execute("SELECT 1 FROM sqlite_schema WHERE type='table' AND upper(ltrim(sql)) LIKE 'CREATE VIRTUAL TABLE%' LIMIT 1").fetchone(),'Virtual tables require an explicit reviewed read adapter')
    names=[row[0] for row in db.execute("SELECT name FROM sqlite_schema WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name")]
    require(len(names)<=100 and all(isinstance(n,str) and len(n)<=256 for n in names),'SQLite table inventory exceeds bounded profile')
    return names


def _info(db,table):
    require(table in _tables(db),'Unknown registered SQLite table')
    return list(db.execute('PRAGMA table_info('+_quote(table)+')'))


def sqlite_schema(path,expected_hash,checkpoint=None):
    with _read_database(path,expected_hash,checkpoint) as db:
        tables=[]
        for name in _tables(db):
            if checkpoint:checkpoint()
            info=_info(db,name);tables.append({'name':name,'columns':[{'name':r[1],'type':r[2],'nullable':not bool(r[3]),'primary_key_order':r[5]} for r in info],
                'rows':db.execute('SELECT count(*) FROM '+_quote(name)).fetchone()[0]})
    return {'sha256':expected_hash,'tables':tables,'read_only':True}


def _typed_filter(name,value):
    kind='null' if value is None else 'integer' if type(value) is int else 'text'
    q=_quote(name)
    return 'typeof('+q+')=? AND '+q+' IS ?', [kind,value]


def _scalar(value):
    return value is None or type(value) is int and -2**63<=value<2**63 or type(value) is str and len(value)<=MAX_VALUE_CHARS


def decode_filters(value):
    """Bounded UI filter values preserve integer precision before SQLite binding."""
    require(isinstance(value,dict) and len(value)<=16,'Bounded typed equality filters required')
    result={}
    for name,item in value.items():
        require(isinstance(name,str) and 0<len(name)<=256 and isinstance(item,dict) and set(item)=={'type','value'},
                'Each equality filter requires a known column plus exact type/value fields')
        kind=item['type'];content=item['value']
        if kind=='null':require(content is None,'Null filter value must be null');result[name]=None
        elif kind=='text':require(type(content) is str and len(content)<=MAX_VALUE_CHARS,'Text filter must preserve exact bounded string');result[name]=content
        elif kind=='integer':
            require(type(content) is str and len(content)<=20 and re.fullmatch(r'(?:0|-[1-9][0-9]*|[1-9][0-9]*)',content),
                    'Integer filter requires canonical signed decimal text, without plus/leading zeros/negative zero')
            number=int(content);require(-2**63<=number<2**63,'Integer filter exceeds exact signed BIGINT range');result[name]=number
        else:raise ValidationError('Equality filter type must be text, integer or null')
    return result


def sqlite_rows(path,expected_hash,table,after=0,limit=100,filters=None,checkpoint=None):
    require(type(after) is int and 0<=after<=MAX_ROWS and type(limit) is int and 1<=limit<=100,'Invalid SQLite row page')
    filters={} if filters is None else filters;require(isinstance(filters,dict) and len(filters)<=16,'Bounded equality filters required')
    with _read_database(path,expected_hash,checkpoint) as db:
        info=_info(db,table);names=[r[1] for r in info];require(set(filters)<=set(names) and all(_scalar(v) for v in filters.values()),'Unknown or invalid SQLite equality filter')
        clauses=[];params=[]
        for name,value in filters.items():
            clause,bound=_typed_filter(name,value);clauses.append('('+clause+')');params.extend(bound)
        where=' WHERE '+' AND '.join(clauses) if clauses else ''
        order=[r[1] for r in sorted(info,key=lambda r:r[5]) if r[5]] or names
        total=db.execute('SELECT count(*) FROM '+_quote(table)+where,params).fetchone()[0]
        require(after<=total,'SQLite cursor exceeds filtered rows')
        raw=db.execute('SELECT '+', '.join(_quote(n) for n in names)+' FROM '+_quote(table)+where+' ORDER BY '+', '.join(_quote(n) for n in order)+' LIMIT ? OFFSET ?',[*params,limit+1,after]).fetchall()
        rows=[dict(zip(names,row)) for row in raw[:limit]]
        require(all(all(_scalar(v) for v in row.values()) for row in rows),'SQLite row contains unsupported binary/float or oversized values; use an explicit codec')
        encode(rows,limit=MAX_BYTES)  # Reduce page size rather than silently truncate fields.
    return {'sha256':expected_hash,'table':table,'columns':names,'rows':rows,'display_rows':[{k:str(v) if type(v) is int else v for k,v in row.items()} for row in rows],
            'after':after,'next_after':after+len(rows),'has_more':len(raw)>limit,'total':total,'read_only':True,'filter_semantics':'Exact typed equality; no arbitrary SQL execution'}


def validate_snapshot(text,provenance=None):
    require(isinstance(text,str) and len(text.encode())<=MAX_BYTES,'Database snapshot exceeds bounded UTF-8 limit')
    value=decode(text.encode(),MAX_BYTES);require(isinstance(value,dict) and set(value)==SNAPSHOT_FIELDS,'Snapshot requires exact versioned fields')
    require(type(value['schema_version']) is int and value['schema_version']==1 and value['kind'] in ('DB2_RECORD_SNAPSHOT','SQLITE_RECORD_SNAPSHOT'),'Unsupported snapshot contract')
    name=_name(value['schema'])+'.'+_name(value['table']);_text(value['run_id'],'Run identity',128);_text(value['environment'],'Environment',128)
    require(value['phase'] in ('before','after'),'Snapshot phase must be before or after')
    columns=value['column_names'];keys=value['key_columns']
    require(isinstance(columns,list) and 0<len(columns)<=MAX_COLUMNS and all(type(c) is str for c in columns) and len(columns)==len(set(columns)),'Unique bounded snapshot columns required')
    for c in columns:_name(c)
    require(isinstance(keys,list) and 0<len(keys)<=32 and all(type(k) is str for k in keys) and len(keys)==len(set(keys)) and set(keys)<=set(columns),'Exact nonempty snapshot key columns required')
    inputs=value['input_hashes'];require(isinstance(inputs,dict) and 0<len(inputs)<=1000,'Exact run input hashes required')
    for path,digest in inputs.items():_text(path,'Run input identity',1000);_hash(digest)
    rows=value['rows'];require(isinstance(rows,list) and len(rows)<=MAX_ROWS,'Bounded snapshot rows required');seen=set()
    for row in rows:
        require(isinstance(row,dict) and set(row)==set(columns) and all(_scalar(v) for v in row.values()),'Snapshot rows must preserve exact columns and scalar types (no float/bool coercion)')
        require(all(row[k] is not None for k in keys),'Null snapshot key cannot establish record identity')
        key=encode([row[k] for k in keys]);require(key not in seen,'Duplicate snapshot record key');seen.add(key)
    scope=value['scope'];require(isinstance(scope,dict) and set(scope)=={'kind','keys','complete'} and scope['kind'] in ('full_table','explicit_keys') and type(scope['complete']) is bool,'Explicit snapshot scope/completeness required')
    require(isinstance(scope['keys'],list) and len(scope['keys'])<=MAX_ROWS,'Bounded scope keys required')
    if scope['kind']=='full_table':require(not scope['keys'],'Full-table scope cannot have hidden key filtering')
    else:
        requested=set()
        for key in scope['keys']:
            require(isinstance(key,list) and len(key)==len(keys) and all(v is not None and _scalar(v) for v in key),'Invalid explicit scope key')
            token=encode(key);require(token not in requested,'Repeated explicit scope key');requested.add(token)
        require(requested and seen<=requested,'Rows lie outside explicit requested key scope')
    consistency=value['consistency'];require(isinstance(consistency,dict) and set(consistency)=={'status','evidence'} and consistency['status'] in ('consistent','unverified'),'Explicit snapshot consistency required')
    evidence=consistency['evidence'];require(isinstance(evidence,list) and len(evidence)<=20,'Bounded consistency evidence required')
    for item in evidence:
        require(isinstance(item,dict) and set(item)=={'path','sha256'},'Consistency requires hash-bound evidence references');_text(item['path'],'Consistency evidence path',1000);_hash(item['sha256'])
    require(consistency['status']!='consistent' or evidence,'Consistent snapshot requires actual external consistency evidence; ordinary WITH UR reads do not establish it')
    origin=value['provenance'];require(isinstance(origin,dict) and set(origin)=={'origin','tool','locator','retrieved_at'},'Snapshot provenance requires exact read identity and timestamp')
    _timestamp(origin['retrieved_at']);require(origin['locator']==name,'Snapshot locator differs from table identity')
    if value['kind']=='DB2_RECORD_SNAPSHOT':require(origin['origin']=='configured_mcp' and origin['tool']=='db2_read_table_rows','Db2 records require the approved read-only Copilot MCP export')
    else:require(origin['origin']=='local_sqlite' and origin['tool']=='workbench.database.sqlite_snapshot','SQLite snapshot must come from the registered local read helper')
    if provenance is not None:
        require(isinstance(provenance,dict) and all(provenance.get(k)==v for k,v in origin.items()),'Snapshot provenance differs from accepted retrieval evidence')
        require(provenance.get('environment') in (None,value['environment']),'Snapshot environment differs from accepted retrieval observation')
    return {**value,'source_hash':sha(text),'source_text':text,'basis':'EXACT_FROZEN_EXPORTED_RECORDS_NOT_NATIVE_SQL_PARITY'}


def _snapshot(value):
    require(isinstance(value,dict),'Validated database snapshot required')
    require(isinstance(value.get('source_text'),str),'Snapshot requires its exact immutable export bytes')
    expected=validate_snapshot(value['source_text'])
    require(encode({k:value.get(k) for k in expected})==encode(expected),'Snapshot differs from its exact hash-bound export')
    return value


def sqlite_snapshot(path,expected_hash,table,source_snapshot,run_id,input_hashes,environment,phase,checkpoint=None):
    source=_snapshot(source_snapshot);require(table==source['schema']+'.'+source['table'],'SQLite table must match exact source-qualified identity')
    with _read_database(path,expected_hash,checkpoint) as db:
        info=_info(db,table);names=[r[1] for r in info];require(set(names)==set(source['column_names']),'SQLite columns differ from source snapshot')
        order=source['key_columns'];columns=source['column_names']
        if source['scope']['kind']=='full_table':
            raw=db.execute('SELECT '+', '.join(_quote(n) for n in columns)+' FROM '+_quote(table)+' ORDER BY '+', '.join(_quote(n) for n in order)+' LIMIT ?',[MAX_ROWS+1]).fetchall()
            require(len(raw)<=MAX_ROWS,'SQLite snapshot exceeds complete row bound')
        else:
            # Bounded VALUES joins preserve key storage types and avoid a full
            # unrelated-table export. Respect the actual SQLite variable limit.
            width=len(order)*2;batch=max(1,min(100,db.getlimit(sqlite3.SQLITE_LIMIT_VARIABLE_NUMBER)//width));raw=[]
            wanted=source['scope']['keys'];labels=','.join('v'+str(i//2) if i%2==0 else 't'+str(i//2) for i in range(width))
            conditions=' AND '.join('typeof(s.'+_quote(n)+')=w.t'+str(i)+' AND s.'+_quote(n)+' IS w.v'+str(i) for i,n in enumerate(order))
            for offset in range(0,len(wanted),batch):
                if checkpoint:checkpoint()
                group=wanted[offset:offset+batch];parameters=[]
                for key in group:
                    for value in key:parameters.extend([value,'integer' if type(value) is int else 'text'])
                sql='WITH wanted('+labels+') AS (VALUES '+','.join('('+','.join('?' for _ in range(width))+')' for _ in group)+') SELECT '+','.join('s.'+_quote(n) for n in columns)+' FROM '+_quote(table)+' s JOIN wanted w ON '+conditions+' LIMIT ?'
                raw.extend(db.execute(sql,[*parameters,MAX_ROWS+1]).fetchall());require(len(raw)<=MAX_ROWS,'SQLite requested scope exceeds complete row bound')
        rows=[dict(zip(columns,r)) for r in raw]
    value={**{k:deepcopy(v) for k,v in source.items() if k in SNAPSHOT_FIELDS},'kind':'SQLITE_RECORD_SNAPSHOT','rows':rows,'run_id':run_id,'input_hashes':input_hashes,'environment':environment,'phase':phase,
           'provenance':{'origin':'local_sqlite','tool':'workbench.database.sqlite_snapshot','locator':table,'retrieved_at':datetime.now(timezone.utc).isoformat()},
           'consistency':{'status':'consistent','evidence':[{'path':str(Path(path).absolute()),'sha256':expected_hash}]}}
    result=validate_snapshot(encode(value).decode());result['database_hash']=expected_hash;return result


def compare_snapshots(db2_before,db2_after,sqlite_before,sqlite_after,context,checkpoint=None,evidence_verifier=None):
    """Compare all keyed rows and operations; never equate aggregate counts."""
    snapshots=[_snapshot(v) for v in (db2_before,db2_after,sqlite_before,sqlite_after)];a,b,c,d=snapshots
    require(isinstance(context,dict) and set(context)=={'db2_run_id','sqlite_run_id','input_hashes','db2_environment','sqlite_environment'},'Exact comparison run/input/environment context required')
    for key in ('db2_run_id','sqlite_run_id','db2_environment','sqlite_environment'):_text(context[key],'Comparison '+key,128)
    require(isinstance(context['input_hashes'],dict) and 0<len(context['input_hashes'])<=1000,'Exact comparison input hashes required')
    for name,digest in context['input_hashes'].items():_text(name,'Comparison input identity',1000);_hash(digest)
    gaps=[]
    for i,s in enumerate(snapshots):
        if checkpoint:checkpoint()
        side='db2' if i<2 else 'sqlite';phase='before' if i%2==0 else 'after'
        expected_kind='DB2_RECORD_SNAPSHOT' if i<2 else 'SQLITE_RECORD_SNAPSHOT'
        for key,expected in [('kind',expected_kind),('phase',phase),('run_id',context[side+'_run_id']),('input_hashes',context['input_hashes']),('environment',context[side+'_environment'])]:
            if s[key]!=expected:gaps.append({'kind':'database_binding_gap','side':side,'phase':phase,'field':key,'reason':'Export does not match the exact comparison context'})
        if not s['scope']['complete']:gaps.append({'kind':'database_scope_gap','side':side,'phase':phase,'reason':'Export is partial; samples/limits cannot establish full requested scope'})
        accepted=s['consistency']['status']=='consistent' and evidence_verifier is not None and evidence_verifier(s) is True
        if not accepted:gaps.append({'kind':'database_consistency_gap','side':side,'phase':phase,'reason':'Read has no independently accepted consistent-snapshot evidence; self-declared references, WITH UR and pagination are not consistency proof'})
        for key in ('schema','table','column_names','key_columns','scope'):
            if s[key]!=a[key]:gaps.append({'kind':'database_scope_gap','side':side,'phase':phase,'field':key,'reason':'Table, column order, record key or requested scope differs'})
    for side,before,after in (('db2',a,b),('sqlite',c,d)):
        if _timestamp(before['provenance']['retrieved_at'])>=_timestamp(after['provenance']['retrieved_at']):
            gaps.append({'kind':'database_binding_gap','side':side,'field':'retrieved_at','reason':'Before observation must precede its after observation'})
    aligned=all(s['key_columns']==a['key_columns'] and s['column_names']==a['column_names'] for s in snapshots)
    records=[]
    if aligned:
        def indexed(s):return {encode([r[k] for k in s['key_columns']]):r for r in s['rows']}
        maps=[indexed(s) for s in snapshots]
        def operation(before,after):
            if before is None:return 'INSERT' if after is not None else 'ABSENT'
            if after is None:return 'DELETE'
            return 'UNCHANGED' if encode(before)==encode(after) else 'UPDATE'
        for key in sorted(set().union(*(set(m) for m in maps))):
            if checkpoint:checkpoint()
            before,after,tbefore,tafter=[m.get(key) for m in maps];op=operation(before,after);top=operation(tbefore,tafter)
            baseline=encode(before)==encode(tbefore);final=encode(after)==encode(tafter)
            delta=op==top and ((op=='INSERT' and final) or (op=='DELETE' and baseline) or (op=='UPDATE' and baseline and final) or op in ('UNCHANGED','ABSENT'))
            changed=[column for column in a['column_names'] if before is not None and after is not None and encode(before[column])!=encode(after[column])]
            target_changed=[column for column in a['column_names'] if tbefore is not None and tafter is not None and encode(tbefore[column])!=encode(tafter[column])]
            historical=op=='UNCHANGED' and before is not None
            reason='All baseline/final values and operation agree' if baseline and final and op==top else 'Historical source row is absent or different in the target baseline; it remains accounted and cannot be ignored' if historical and not baseline else 'Keyed operation or complete baseline/final values differ'
            records.append({'key':decode(key),'db2_operation':op,'sqlite_operation':top,'db2_before':before,'db2_after':after,'sqlite_before':tbefore,'sqlite_after':tafter,
                            'baseline_match':baseline,'final_match':final,'delta_match':delta,'historical':historical,'changed_columns':changed,'sqlite_changed_columns':target_changed,'reason':reason})
    else:gaps.append({'kind':'database_identity_gap','reason':'Key/column definitions differ; record pairing is withheld'})
    baseline_gaps=sum(not r['baseline_match'] for r in records);final_gaps=sum(not r['final_match'] for r in records)
    relevant=[r for r in records if r['db2_operation'] not in ('UNCHANGED','ABSENT') or r['sqlite_operation'] not in ('UNCHANGED','ABSENT')]
    delta_match=aligned and all(r['delta_match'] for r in relevant)
    if baseline_gaps:gaps.append({'kind':'database_baseline_gap','count':baseline_gaps,'reason':'Every historical baseline difference remains explicit; source totals are not compared directly with new-only target totals'})
    if final_gaps:gaps.append({'kind':'database_record_gap','count':final_gaps,'reason':'Complete keyed final rows differ'})
    bound=not any(g['kind'] in ('database_binding_gap','database_scope_gap','database_consistency_gap','database_identity_gap') for g in gaps)
    return {'schema_version':1,'status':'EXPORTED_SCOPE_MATCHES' if not gaps else 'RUN_DELTA_MATCHES_WITH_GAPS' if delta_match and bound else 'COMPARISON_HAS_GAPS',
            'context':deepcopy(context),'source_hashes':[s['source_hash'] for s in snapshots],'records':records,'gaps':gaps,
            'summary':{'db2_before_rows':len(a['rows']),'db2_after_rows':len(b['rows']),'sqlite_before_rows':len(c['rows']),'sqlite_after_rows':len(d['rows']),
                       'records':len(records),'changed_records':len(relevant),'matching_changed_records':sum(r['delta_match'] for r in relevant),'historical_records':sum(r['historical'] for r in records),
                       'baseline_gap_records':baseline_gaps,'final_gap_records':final_gaps,'run_delta_matches':delta_match and bound,'complete_exported_scope_match':not gaps},
            'native_database_verified':False,'observed_program_parity':False,'basis':'KEYED_BASELINE_AND_OPERATION_COMPARISON_OF_FROZEN_EXPORTS'}
