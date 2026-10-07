"""One serialized ledger writer, versioned events and an atomic one-packet quota."""
from .domain import path_is_link
from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3
import threading
from .domain import ValidationError, identity, encode, require


def now(): return datetime.now(timezone.utc).isoformat()


class Ledger:
    def __init__(self, root):
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        state = self.root / '.migration'
        require(not path_is_link(state), 'Unsafe ledger path')
        state.mkdir(exist_ok=True)
        self.lock = threading.RLock()
        require(not path_is_link(state/'ledger.sqlite'), 'Unsafe ledger database path')
        self.db = sqlite3.connect(state/'ledger.sqlite', check_same_thread=False, timeout=10)
        try:
            self.db.row_factory = sqlite3.Row
            self.db.execute('PRAGMA foreign_keys=ON')
            # Rollback journaling avoids WAL-reset bugs and filesystem assumptions.
            self.db.execute('PRAGMA journal_mode=DELETE')
            self.db.executescript(Path(__file__).with_name('schema.sql').read_text(encoding='utf-8'))
        except Exception:
            self.db.close();raise

    def create(self, manifest, demo=False):
        pid = identity(manifest['id'])
        doc = {**manifest, 'demo': bool(demo), 'analysis': None, 'artifacts': [], 'blockers': [], 'runs': [], 'answers': None, 'revision': 1}
        with self.lock, self.db:
            try:
                stamp=now()
                self.db.execute('INSERT INTO processes(id,name,status,demo,document,created,updated) VALUES(?,?,?,?,?,?,?)', (pid, manifest['name'], 'READY', int(demo), encode(doc).decode(), stamp, stamp))
                self._transition(pid,'READY',stamp)
            except sqlite3.IntegrityError as exc: raise ValidationError('Process already exists; select it or use a new process ID') from exc
        return self.get(pid)

    def get(self, pid):
        identity(pid)
        with self.lock: row = self.db.execute('SELECT * FROM processes WHERE id=?', (pid,)).fetchone()
        require(row is not None, 'Process not found')
        doc = json.loads(row['document'])
        return {**doc, 'status': row['status'], 'packet_issued': bool(row['packet_issued']), 'packet_imported': bool(row['packet_imported']), 'packet_hash': row['packet_hash'], 'created': row['created'], 'updated': row['updated']}

    def list(self, include_demo=False):
        with self.lock: rows = self.db.execute('SELECT id FROM processes WHERE demo=0 OR ?=1 ORDER BY created', (int(include_demo),)).fetchall()
        return [self.get(r['id']) for r in rows]

    def save_development_handoff(self, doc, handoff_id):
        """Index an opaque handoff and commit its single-writer event atomically."""
        with self.lock, self.db:
            self.db.execute('INSERT INTO development_handoffs(id,process_id) VALUES(?,?)', (handoff_id, doc['id']))
            self._save(doc)
            self._event(doc['id'], 'development', 'Source-free standalone development handoff prepared', {'handoff_id': handoff_id})
        return self.get(doc['id'])

    def development_owner(self, handoff_id):
        with self.lock:
            row = self.db.execute('SELECT process_id FROM development_handoffs WHERE id=?', (handoff_id,)).fetchone()
        require(row is not None, 'Development handoff is unavailable or stale')
        return row['process_id']

    def controls(self, pid):
        """Read durable operator controls without materializing synthetic results.

        SQLite's JSON projection keeps per-record cancellation checks small.
        Older SQLite builds without JSON support retain the safe full-read path.
        """
        identity(pid)
        with self.lock:
            try:
                row=self.db.execute("SELECT status, json_extract(document,'$.control_revision') AS control_revision, json_extract(document,'$.cancel_requested') AS cancel_requested, json_extract(document,'$.resume_status') AS resume_status FROM processes WHERE id=?",(pid,)).fetchone()
            except sqlite3.OperationalError as exc:
                if 'no such function: json_extract' not in str(exc):raise
                return self.get(pid)
        require(row is not None,'Process not found')
        result={key:row[key] for key in row.keys() if row[key] is not None}
        result['blockers']=[{'kind':'cancelled','message':'Operator cancelled this process'}] if result.get('cancel_requested') else []
        return result

    def _save(self, doc, status=None):
        """Write inside the caller's transaction without committing it early."""
        pid = identity(doc['id'])
        canonical = {k:v for k,v in doc.items() if k not in {'status','packet_issued','packet_imported','packet_hash','created','updated'}}
        require(self.db.execute('SELECT 1 FROM processes WHERE id=?', (pid,)).fetchone(), 'Process not found')
        stamp=now()
        if status and self.get(pid)['status']!=status:self._transition(pid,status,stamp)
        self.db.execute('UPDATE processes SET document=?,status=COALESCE(?,status),updated=? WHERE id=?', (encode(canonical).decode(), status, stamp, pid))

    def save(self, doc, status=None):
        with self.lock, self.db:
            self._save(doc, status)
        return self.get(doc['id'])

    def save_event(self, doc, status, stage, message, payload=None):
        """Commit an operator transition and its audit record as one unit."""
        with self.lock, self.db:
            self._save(doc, status)
            self._event(doc['id'], stage, message, payload)
        return self.get(doc['id'])

    def _event(self, pid, stage, message, payload=None):
        self.db.execute('INSERT INTO events(process_id,stage,message,payload,created) VALUES(?,?,?,?,?)', (pid,stage,message,encode(payload or {}).decode(),now()))

    def event(self, pid, stage, message, payload=None):
        with self.lock, self.db:
            self._event(pid, stage, message, payload)

    def events(self, pid, after=0):
        with self.lock: rows = self.db.execute('SELECT * FROM events WHERE process_id=? AND seq>? ORDER BY seq LIMIT 2000', (pid,after)).fetchall()
        return [{**dict(r),'payload':json.loads(r['payload'])} for r in rows]

    def issue_packet(self, pid, fingerprint):
        with self.lock, self.db:
            cur = self.db.execute('UPDATE processes SET packet_issued=1,packet_hash=? WHERE id=? AND packet_issued=0', (fingerprint,pid))
            require(cur.rowcount == 1, 'This process has already issued its one SME questionnaire')

    def consume_return(self, pid, answers):
        with self.lock, self.db:
            doc = self.get(pid)
            require(doc['packet_issued'] and not doc['packet_imported'], 'SME return already consumed or packet not issued')
            require(isinstance(answers,dict) and answers.get('packet_hash')==doc['packet_hash'],
                    'SME return does not match the issued packet')
            require(answers.get('source_snapshot')==(doc.get('analysis') or {}).get('source_snapshot')
                    and bool(answers.get('source_snapshot')),'SME return does not match the frozen source snapshot')
            require(isinstance(answers.get('reviewer'),str) and 0<len(answers['reviewer'].strip())<=160,
                    'SME return requires reviewer attribution')
            require(isinstance(answers.get('return_hash'),str) and len(answers['return_hash'])==64,
                    'SME return requires its preserved file fingerprint')
            require(isinstance(answers.get('items'),dict),'SME return requires an answer mapping')
            doc['answers'] = answers
            canonical = {k:v for k,v in doc.items() if k not in {'status','packet_issued','packet_imported','packet_hash','created','updated'}}
            cur = self.db.execute('UPDATE processes SET packet_imported=1,document=?,status=?,updated=? WHERE id=? AND packet_imported=0', (encode(canonical).decode(),'QUEUED_VERIFY',now(),pid))
            require(cur.rowcount == 1, 'SME return already consumed')
            self._transition(pid,'QUEUED_VERIFY',now())
            self._event(pid, 'review', 'One SME return imported; automatic continuation queued')

    def register_assets(self, pid, assets):
        with self.lock, self.db:
            for asset in assets:
                existing=self.db.execute('SELECT document FROM assets WHERE id=?',(asset['id'],)).fetchone()
                # Membership-local paths and parser metadata may differ while the
                # same immutable source version is reused by another process.
                prior=json.loads(existing[0]) if existing is not None else None
                require(prior is None or all(prior.get(key)==asset.get(key)
                        for key in ('kind','name','source_hash','source_text')),
                        'Asset identity conflicts with preserved source evidence: '+asset['id'])
                self.db.execute('INSERT OR IGNORE INTO assets VALUES(?,?,?,?,?)',(asset['id'],asset['kind'],asset['name'],asset['source_hash'],encode(asset).decode()))
                self.db.execute('INSERT OR IGNORE INTO process_assets VALUES(?,?)',(pid,asset['id']))

    def assets(self, pid=None, include_demo=False):
        with self.lock:
            if pid: rows = self.db.execute('SELECT a.document FROM assets a JOIN process_assets p ON a.id=p.asset_id WHERE p.process_id=?',(pid,)).fetchall()
            else: rows = self.db.execute('SELECT DISTINCT a.document FROM assets a JOIN process_assets p ON a.id=p.asset_id JOIN processes x ON x.id=p.process_id WHERE x.demo=0 OR ?=1',(int(include_demo),)).fetchall()
        return [json.loads(r[0]) for r in rows]

    def snapshot(self, pid, document):
        canonical=encode(document).decode()
        with self.lock, self.db:
            existing=self.db.execute('SELECT 1 FROM snapshots WHERE process_id=? AND document=?',(pid,canonical)).fetchone()
            if not existing:self.db.execute('INSERT INTO snapshots(process_id,document,created) VALUES(?,?,?)',(pid,canonical,now()))

    def complete_report(self, doc, metrics):
        """Commit accepted history, report certification and terminal event together."""
        pid=identity(doc['id'])
        canonical={k:v for k,v in doc.items() if k not in {'status','packet_issued','packet_imported','packet_hash','created','updated'}}
        metric_text=encode(metrics).decode()
        status='COMPLETED_WITH_BLOCKERS' if doc['blockers'] or doc.get('cancel_requested') else 'COMPLETED'
        with self.lock, self.db:
            current=self.get(pid)
            require(current['status']=='REPORTING','Report completion requires the active reporting stage')
            require(current.get('control_revision',0)==doc.get('control_revision',0)
                    and bool(current.get('cancel_requested'))==bool(doc.get('cancel_requested')),
                    'Report completion cannot replace newer operator controls')
            require(doc.get('report_verified') is True and bool(doc.get('report_hashes')),
                    'Report completion requires inspected report evidence')
            require(all(doc.get('artifact_hashes',{}).get(path)==fingerprint
                        for path,fingerprint in doc['report_hashes'].items()),
                    'Report completion requires pinned inspection fingerprints')
            if not self.db.execute('SELECT 1 FROM snapshots WHERE process_id=? AND document=?',(pid,metric_text)).fetchone():
                self.db.execute('INSERT INTO snapshots(process_id,document,created) VALUES(?,?,?)',(pid,metric_text,now()))
            stamp=now()
            self._transition(pid,status,stamp)
            self.db.execute('UPDATE processes SET document=?,status=?,updated=? WHERE id=?',(encode(canonical).decode(),status,stamp,pid))
            self.db.execute('INSERT INTO events(process_id,stage,message,payload,created) VALUES(?,?,?,?,?)',(pid,'complete','Report inspection passed; technical completion recorded for the stated source-derived POC boundary',encode({}).decode(),now()))
        return self.get(pid)

    def history(self, pid=None):
        with self.lock: rows = self.db.execute('SELECT * FROM snapshots WHERE process_id=? OR ? IS NULL ORDER BY seq',(pid,pid)).fetchall()
        return [{**dict(r),'document':json.loads(r['document'])} for r in rows]

    def _transition(self,pid,status,stamp):
        self.db.execute('INSERT INTO status_transitions(process_id,status,created) VALUES(?,?,?)',(pid,status,stamp))

    def start_timing(self,pid,stage):
        with self.lock,self.db:
            return self.db.execute('INSERT INTO stage_timings(process_id,stage,started) VALUES(?,?,?)',(pid,stage,now())).lastrowid

    def finish_timing(self,seq,elapsed,outcome):
        with self.lock,self.db:
            self.db.execute('UPDATE stage_timings SET ended=?,elapsed_seconds=?,outcome=? WHERE seq=? AND ended IS NULL',(now(),str(max(0,elapsed)),outcome,seq))

    def measurement_timing(self):
        with self.lock:
            return ([dict(r) for r in self.db.execute('SELECT * FROM status_transitions ORDER BY seq')],
                    [dict(r) for r in self.db.execute('SELECT * FROM stage_timings ORDER BY seq')])

    def measurements(self):
        with self.lock:rows=self.db.execute('SELECT * FROM measurement_receipts ORDER BY seq').fetchall()
        return [{**dict(r),'document':json.loads(r['document'])} for r in rows]

    def append_measurement(self,record,fingerprint,path):
        with self.lock,self.db:
            existing=self.db.execute('SELECT fingerprint FROM measurement_receipts WHERE id=?',(record['id'],)).fetchone()
            if existing:
                require(existing[0]==fingerprint,'Measurement ID already belongs to different evidence')
                return False
            self.db.execute('INSERT INTO measurement_receipts(id,process_id,fingerprint,path,document,created) VALUES(?,?,?,?,?,?)',
                            (record['id'],record['process_id'],fingerprint,path,encode(record).decode(),now()))
            return True

    def work_sessions(self):
        with self.lock:rows=self.db.execute('SELECT * FROM work_sessions ORDER BY started').fetchall()
        return [{**dict(r),'document':json.loads(r['document'])} for r in rows]

    def open_work_session(self,document):
        with self.lock,self.db:
            self.db.execute('INSERT INTO work_sessions(id,document,started) VALUES(?,?,?)',(document['id'],encode(document).decode(),now()))

    def close_work_session(self,session_id,receipt_id):
        with self.lock,self.db:self.db.execute('UPDATE work_sessions SET receipt_id=? WHERE id=? AND receipt_id IS NULL',(receipt_id,session_id))

    def close(self):
        with self.lock: self.db.close()
