"""Resumable account-visible Db2 for z/OS discovery and literal content search.

Only catalog-derived identifiers enter fixed SELECT statements. A local journal
is operational state, never conversion/parity evidence. WITH UR is not a snapshot.
"""
from datetime import date, datetime, time as daytime
from decimal import Decimal
import json
import os
from pathlib import Path
import re
import secrets
import sqlite3
import threading
import time

MAX_ROW_BYTES = 1024 * 1024
MAX_STATE_BYTES = 256 * 1024 * 1024


class StorageBudget(ValueError):
    pass


def check(value, message):
    if not value: raise ValueError(message)


def quoted(value):
    check(isinstance(value, str) and 0 < len(value) <= 128 and
          not any(ord(c) < 32 or ord(c) == 127 for c in value), 'Invalid catalog identifier')
    return '"' + value.replace('"', '""') + '"'


def qualified(location, schema, name):
    return '.'.join(quoted(v) for v in ([location] if location else []) + [schema, name])


def failure(exc):
    # Never publish driver diagnostics (they may contain account/connection data).
    state = str(exc.args[0])[:5] if exc.args else ''
    if state == '42501': return 'permission_denied'
    if state.startswith('08'): return 'location_unreachable'
    if state.startswith('HYT'): return 'query_timeout'
    return 'read_failed'


def text_value(value):
    if value is None: return ''
    if isinstance(value, bytes): return value.hex()
    if isinstance(value, (str, int, float, bool, Decimal, date, datetime, daytime)):
        return str(value)
    raise ValueError('unsupported_value_type')


class SearchStore:
    """One writer per private journal, bounded work per call, no background scans.

    Table cursors live for five idle minutes. A server restart/expiry records an
    explicit partial table; continuation resumes remaining objects without
    pretending that an unordered table can be resumed at the same row.
    """
    def __init__(self, root, connect, row_limit):
        self.root = Path(root).absolute()
        check(not self.root.is_symlink() and not any(p.is_symlink() for p in self.root.parents),
              'Search state must use a regular private directory')
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
        os.chmod(self.root, 0o700)
        self.path = self.root / 'search.sqlite3'
        for name in ('search.sqlite3','search.sqlite3-journal','search.sqlite3-wal','search.sqlite3-shm'):
            p = self.root / name
            check(not p.is_symlink() and (not p.exists() or p.is_file()), 'Invalid search state path')
        self.connect, self.row_limit = connect, row_limit
        self.lock = threading.RLock(); self.live = {}; self.closed = False
        # Another process cannot share this journal; lifetime lock is OS released.
        # Portable SQLite exclusive transaction held in a separate lock database.
        lock_path = self.root / 'owner.sqlite3'
        check(all(not (self.root/n).is_symlink() for n in ('owner.sqlite3','owner.sqlite3-journal','owner.sqlite3-wal','owner.sqlite3-shm')), 'Invalid search lock path')
        self.owner = sqlite3.connect(lock_path, timeout=0, check_same_thread=False)
        os.chmod(lock_path, 0o600)
        try:
            self.owner.execute('BEGIN EXCLUSIVE')
        except sqlite3.OperationalError:
            self.owner.close()
            raise ValueError('Search journal already has a writer') from None
        self.db = sqlite3.connect(self.path, check_same_thread=False)
        os.chmod(self.path, 0o600)
        self.db.row_factory = sqlite3.Row
        self.db.execute(f'PRAGMA max_page_count={MAX_STATE_BYTES // 4096}')
        self.db.executescript('''
          CREATE TABLE IF NOT EXISTS searches(id TEXT PRIMARY KEY, query TEXT, maximum INTEGER, status TEXT);
          CREATE TABLE IF NOT EXISTS objects(id INTEGER PRIMARY KEY, search_id TEXT, kind TEXT,
            location TEXT, schema_name TEXT, name TEXT, object_type TEXT, status TEXT DEFAULT 'PENDING',
            rows_read INTEGER DEFAULT 0, reason TEXT, UNIQUE(search_id,kind,location,schema_name,name));
          CREATE TABLE IF NOT EXISTS matches(id INTEGER PRIMARY KEY, search_id TEXT, object_id INTEGER,
            kind TEXT, location TEXT, schema_name TEXT, name TEXT, column_name TEXT, row_number INTEGER, excerpt TEXT);
          CREATE INDEX IF NOT EXISTS object_search ON objects(search_id,status,id);
          CREATE INDEX IF NOT EXISTS match_search ON matches(search_id,id);
        ''')
        self.db.execute("UPDATE objects SET status='PARTIAL',reason='server_restarted' WHERE status='RUNNING'")
        self.db.commit()
        self.timer = threading.Timer(30, self._expire); self.timer.daemon=True; self.timer.start()

    def _expire(self):
        with self.lock:
            if self.closed: return
            now = time.monotonic()
            for oid, entry in list(self.live.items()):
                if now-entry['used'] > 300:
                    self._end(oid, 'PARTIAL', 'cursor_expired')
            self.db.commit()
            self.timer = threading.Timer(30, self._expire); self.timer.daemon=True; self.timer.start()

    def _search(self, token):
        check(isinstance(token,str) and re.fullmatch('[0-9a-f]{64}',token), 'Invalid search identity')
        row = self.db.execute('SELECT * FROM searches WHERE id=?',(token,)).fetchone()
        check(row is not None, 'Unknown search identity')
        return row

    def _storage_guard(self):
        size=self.db.execute('PRAGMA page_count').fetchone()[0]*self.db.execute('PRAGMA page_size').fetchone()[0]
        if size >= MAX_STATE_BYTES-max(16384,min(4*1024*1024,MAX_STATE_BYTES//4)):
            raise StorageBudget('storage_budget')

    def _add(self, token, kind, location='', schema='', name='', object_type=''):
        self._storage_guard()
        self.db.execute('INSERT OR IGNORE INTO objects(search_id,kind,location,schema_name,name,object_type) VALUES(?,?,?,?,?,?)',
                        (token,kind,location,schema,name,object_type))

    def start(self, query):
        check(isinstance(query,str) and bool(query.strip()) and len(query) <= 256 and '\x00' not in query,
              'Search needs a literal phrase of 1..256 characters')
        with self.lock:
            maximum = self.row_limit()
            check(type(maximum) is int and 1 <= maximum <= 500000, 'Invalid configured query row limit')
            count = self.db.execute("SELECT COUNT(*) FROM searches WHERE status='RUNNING'").fetchone()[0]
            check(count < 8, 'Eight active searches already exist; finish or cancel one')
            check(self.path.stat().st_size < MAX_STATE_BYTES, 'Private search storage budget reached')
            token = secrets.token_hex(32)
            with self.db:
                self._storage_guard()
                self.db.execute('INSERT INTO searches VALUES(?,?,?,?)',(token,query,maximum,'RUNNING'))
                self._add(token,'locations'); self._add(token,'catalog')
            return self.status(token)

    def status(self, token):
        with self.lock:
            search = self._search(token)
            counts = {r[0]:r[1] for r in self.db.execute('SELECT status,COUNT(*) FROM objects WHERE search_id=? GROUP BY status',(token,))}
            status = search['status']
            if status == 'RUNNING' and not counts.get('PENDING') and not counts.get('RUNNING'):
                status = 'PARTIAL' if counts.get('PARTIAL') else 'COMPLETE'
                self.db.execute('UPDATE searches SET status=? WHERE id=?',(status,token)); self.db.commit()
            return {'search_id':token,'status':status,'objects':counts,'max_rows_per_query':search['maximum'],
                    'matches':self.db.execute('SELECT COUNT(*) FROM matches WHERE search_id=?',(token,)).fetchone()[0],
                    'rows_read':self.db.execute('SELECT COALESCE(SUM(rows_read),0) FROM objects WHERE search_id=?',(token,)).fetchone()[0],
                    'read_only':True,'snapshot_consistent':False,
                    'scope':'Account-visible SYSIBM catalogs and selectable contents, including catalog-advertised DDF locations. COMPLETE describes only that traversal; it is not enterprise inventory or parity.',
                    'next_action':'db2_search_continue' if status=='RUNNING' else 'db2_search_results'}

    def _open(self, obj, maximum):
        target = qualified(obj['location'], 'SYSIBM', 'LOCATIONS' if obj['kind']=='locations' else 'SYSTABLES')
        if obj['kind']=='locations':
            sql=f'SELECT LOCATION FROM {target} WHERE LOCATION > ? ORDER BY LOCATION FETCH FIRST {maximum} ROWS ONLY WITH UR'; params=['']
        elif obj['kind']=='catalog':
            sql=f'SELECT CREATOR,NAME,TYPE FROM {target} WHERE CREATOR > ? ORDER BY CREATOR,NAME FETCH FIRST {maximum} ROWS ONLY WITH UR'; params=['']
        else:
            sql=f'SELECT * FROM {qualified(obj["location"],obj["schema_name"],obj["name"])} FETCH FIRST {maximum} ROWS ONLY WITH UR'; params=[]
        db = self.connect()
        try:
            cursor=db.cursor(); cursor.timeout=15; cursor.execute(sql,*params)
            names=[c[0] for c in cursor.description]
            check(names and len(names)==len(set(names)) and all(isinstance(n,str) for n in names),'Invalid database column names')
            if obj['kind'] in ('locations','catalog'):
                expected=['LOCATION'] if obj['kind']=='locations' else ['CREATOR','NAME','TYPE']
                check(names==expected,'Invalid fixed catalog shape')
        except Exception:
            db.close(); raise
        self.live[obj['id']]={'db':db,'cursor':cursor,'names':names,'used':time.monotonic()}
        self.db.execute("UPDATE objects SET status='RUNNING' WHERE id=?",(obj['id'],))

    def _end(self, oid, status, reason=None):
        entry=self.live.pop(oid,None)
        if entry:
            for resource in (entry['cursor'],entry['db']):
                try: resource.close()
                except Exception: pass
        self.db.execute('UPDATE objects SET status=?,reason=? WHERE id=?',(status,reason,oid))

    def _match(self, obj, kind, column, number, value, needle):
        folded=value.casefold()
        if needle not in folded: return
        # Excerpts are bounded; matching uses the entire supported cell value.
        index=folded.index(needle)
        # Case folding can expand characters (e.g. ß -> ss). Map the match
        # back to original character offsets before choosing its excerpt.
        offset=0; start=0; end=len(value); found=False
        for i,char in enumerate(value):
            next_offset=offset+len(char.casefold())
            if not found and next_offset>index: start=i; found=True
            if next_offset>=index+len(needle): end=i+1; break
            offset=next_offset
        excerpt=value[max(0,start-80):end+160]
        self._storage_guard()
        self.db.execute('INSERT INTO matches(search_id,object_id,kind,location,schema_name,name,column_name,row_number,excerpt) VALUES(?,?,?,?,?,?,?,?,?)',
                        (obj['search_id'],obj['id'],kind,obj['location'],obj['schema_name'],obj['name'],column,number,excerpt))

    def advance(self, token, row_budget=1000):
        check(type(row_budget) is int and 1 <= row_budget <= 1000,'Call row budget must be 1..1000')
        with self.lock:
            search=self._search(token)
            if search['status']!='RUNNING': return self.status(token)

            deadline=time.monotonic()+2; needle=search['query'].casefold()
            for _ in range(row_budget):
                if time.monotonic()>=deadline: break
                obj=self.db.execute("SELECT * FROM objects WHERE search_id=? AND status IN ('PENDING','RUNNING') ORDER BY id LIMIT 1",(token,)).fetchone()
                if obj is None: break
                maximum=min(search['maximum'],self.row_limit())
                if obj['rows_read']>=maximum:
                    self._end(obj['id'],'PARTIAL','row_budget'); continue
                try:
                    self._storage_guard()
                    if obj['id'] not in self.live:
                        self._open(obj,maximum)
                        if obj['kind']=='table':
                            for column in self.live[obj['id']]['names']:
                                self._match(obj,'metadata',column,0,column,needle)
                    entry=self.live[obj['id']]; entry['used']=time.monotonic()
                    rows=entry['cursor'].fetchmany(1)
                    check(len(rows)<=1,'Invalid fetch count')
                    if not rows:
                        self._end(obj['id'],'DONE'); continue
                    row=rows[0]; check(len(row)==len(entry['names']),'Invalid database row width')
                    if obj['kind'] in ('locations','catalog'):
                        check(all(type(v)is str for v in row),'Invalid fixed catalog value types')
                    values=[text_value(v) for v in row]
                    check(sum(len(v.encode('utf-8')) for v in values)<=MAX_ROW_BYTES,'row_byte_budget')
                    number=obj['rows_read']+1
                    if obj['kind']=='locations':
                        location=values[0].strip(); quoted(location)
                        self._add(token,'locations',location); self._add(token,'catalog',location)
                    elif obj['kind']=='catalog':
                        schema,name,otype=[v.rstrip() for v in values]; quoted(schema); quoted(name)
                        self._add(token,'table',obj['location'],schema,name,otype)
                        child=dict(obj); child.update(schema_name=schema,name=name)
                        self._match(child,'metadata','',0,f'{obj["location"]}.{schema}.{name}',needle)
                    else:
                        for column,value in zip(entry['names'],values):
                            self._match(obj,'content',column,number,value,needle)
                    self.db.execute('UPDATE objects SET rows_read=? WHERE id=?',(number,obj['id']))
                    if number>=maximum: self._end(obj['id'],'PARTIAL','row_budget')
                except StorageBudget:
                    for pending in self.db.execute("SELECT id FROM objects WHERE search_id=? AND status IN ('PENDING','RUNNING')",(token,)).fetchall():
                        self._end(pending['id'],'PARTIAL','storage_budget')
                    break
                except Exception as exc:
                    reason=str(exc) if isinstance(exc,ValueError) and str(exc) in ('row_byte_budget','unsupported_value_type') else failure(exc)
                    self._end(obj['id'],'PARTIAL',reason)
                self.db.commit()
            self.db.commit()
            return self.status(token)

    def results(self, token, after=0, limit=100, kind='matches'):
        check(type(after)is int and after>=0 and type(limit)is int and 1<=limit<=100,'Invalid result page')
        check(kind in ('matches','objects'),'Unknown result kind')
        with self.lock:
            self._search(token)
            columns = ('id,kind,location,schema_name AS schema,name AS table_name,column_name AS column,row_number,excerpt' if kind=='matches' else
                       'id,kind,location,schema_name AS schema,name AS table_name,object_type,status,rows_read,reason')
            rows=[dict(r) for r in self.db.execute(f'SELECT {columns} FROM {kind if kind=="matches" else "objects"} WHERE search_id=? AND id>? ORDER BY id LIMIT ?', (token,after,limit+1))]
            more=len(rows)>limit; rows=rows[:limit]
            return {'rows':rows,'has_more':more,'next_after':rows[-1]['id'] if rows else after,'search_id':token}

    def cancel(self, token):
        with self.lock:
            self._search(token)
            for obj in self.db.execute("SELECT id FROM objects WHERE search_id=? AND status IN ('PENDING','RUNNING')",(token,)).fetchall():
                self._end(obj['id'],'PARTIAL','client_cancelled')
            self.db.execute("UPDATE searches SET status='CANCELLED' WHERE id=?",(token,)); self.db.commit()
            return self.status(token)

    def close(self):
        with self.lock:
            if self.closed: return
            self.closed=True; self.timer.cancel()
            for oid in list(self.live): self._end(oid,'PARTIAL','server_stopped')
            self.db.commit(); self.db.close(); self.owner.close()
