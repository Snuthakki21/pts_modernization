CREATE TABLE IF NOT EXISTS processes (
 id TEXT PRIMARY KEY, name TEXT NOT NULL, status TEXT NOT NULL,
 demo INTEGER NOT NULL DEFAULT 0, document TEXT NOT NULL,
 packet_issued INTEGER NOT NULL DEFAULT 0, packet_imported INTEGER NOT NULL DEFAULT 0,
 packet_hash TEXT, created TEXT NOT NULL, updated TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS events (
 seq INTEGER PRIMARY KEY AUTOINCREMENT, process_id TEXT NOT NULL REFERENCES processes(id),
 stage TEXT NOT NULL, message TEXT NOT NULL, payload TEXT NOT NULL, created TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS assets (
 id TEXT PRIMARY KEY, kind TEXT NOT NULL, name TEXT NOT NULL, source_hash TEXT NOT NULL, document TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS process_assets (
 process_id TEXT NOT NULL REFERENCES processes(id), asset_id TEXT NOT NULL REFERENCES assets(id),
 PRIMARY KEY(process_id,asset_id)
);
CREATE TABLE IF NOT EXISTS snapshots (
 seq INTEGER PRIMARY KEY AUTOINCREMENT, process_id TEXT NOT NULL REFERENCES processes(id),
 document TEXT NOT NULL, created TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS knowledge (
 id TEXT PRIMARY KEY, document TEXT NOT NULL, updated TEXT NOT NULL
);
PRAGMA user_version=1;
CREATE TABLE IF NOT EXISTS status_transitions (
 seq INTEGER PRIMARY KEY AUTOINCREMENT, process_id TEXT NOT NULL REFERENCES processes(id),
 status TEXT NOT NULL, created TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS transitions_process ON status_transitions(process_id,seq);
CREATE TABLE IF NOT EXISTS stage_timings (
 seq INTEGER PRIMARY KEY AUTOINCREMENT, process_id TEXT NOT NULL REFERENCES processes(id),
 stage TEXT NOT NULL, started TEXT NOT NULL, ended TEXT, elapsed_seconds TEXT, outcome TEXT
);
CREATE TABLE IF NOT EXISTS measurement_receipts (
 seq INTEGER PRIMARY KEY AUTOINCREMENT, id TEXT UNIQUE NOT NULL,
 process_id TEXT REFERENCES processes(id), fingerprint TEXT NOT NULL,
 path TEXT, document TEXT NOT NULL, created TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS work_sessions (
 id TEXT PRIMARY KEY, document TEXT NOT NULL, started TEXT NOT NULL, receipt_id TEXT
);

CREATE TABLE IF NOT EXISTS development_handoffs (
 id TEXT PRIMARY KEY, process_id TEXT NOT NULL REFERENCES processes(id)
);
