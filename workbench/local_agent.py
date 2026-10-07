"""Bounded local-file control for Claude; no MCP or network client.

The existing Coordinator worker is the sole consumer. Durable start markers
prevent automatic mutation replay when an action's final outcome is uncertain.
"""
import os
from pathlib import Path
import re
import time
import uuid

from .domain import ValidationError, decode, encode, identity, require, safe_path, sha

MAX_COMMAND_BYTES = 256000
MAX_RESULT_BYTES = 8 * 1024 * 1024
MAX_BATCH = 16
MAX_SCAN_ENTRIES = 10000
ACTIONS = frozenset({'inspect', 'continue', 'refresh', 'analysis', 'request', 'measurement'})
COMMANDS = '.migration/agent-commands'
RESULTS = '.migration/agent-results'
REJECTED = '.migration/agent-rejected'
_COMMAND_FILE = re.compile(r'^[0-9a-f]{32}\.json$')


def validate_command(document):
    require(isinstance(document, dict) and set(document) ==
            {'version', 'command_id', 'process_id', 'action', 'payload', 'command_hash'},
            'Invalid local agent command')
    require(type(document['version']) is int and document['version'] == 1,
            'Unsupported local agent command version')
    require(isinstance(document['command_id'], str) and re.fullmatch('[0-9a-f]{32}', document['command_id']),
            'Invalid local command ID')
    identity(document['process_id'])
    require(isinstance(document['action'], str) and document['action'] in ACTIONS
            and isinstance(document['payload'], dict), 'Invalid local agent action')
    raw = encode({k: v for k, v in document.items() if k != 'command_hash'}, limit=MAX_COMMAND_BYTES)
    require(document['command_hash'] == sha(raw), 'Local agent command integrity differs')
    encode(document, limit=MAX_COMMAND_BYTES)
    return document


def _read(path, limit, label):
    path = safe_path(path.parent, path.name)
    require(path.is_file() and path.stat().st_size <= limit, label + ' exceeds bound or is not a regular file')
    with path.open('rb') as stream:
        raw = stream.read(limit + 1)
    require(len(raw) <= limit, label + ' exceeds bound')
    return raw


def _publish(path, data):
    """Atomically publish complete bytes without replacing an existing identity.

    A private temporary file and an exclusive hard-link publication avoid both a
    partial JSON read and overwrite races between producers. This uses the local
    filesystem, including NTFS on Windows; unsupported filesystems fail closed.
    """
    path = safe_path(Path(path).parent, Path(path).name)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = safe_path(path.parent, '.' + path.name + '.' + uuid.uuid4().hex + '.tmp')
    try:
        with temporary.open('xb') as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        try:
            os.link(temporary, path)
        except FileExistsError:
            return False
        if os.name != 'nt':
            descriptor = os.open(path.parent, os.O_RDONLY)
            try:
                os.fsync(descriptor)
            finally:
                os.close(descriptor)
        return True
    finally:
        temporary.unlink(missing_ok=True)


def _result(path, doc):
    value = decode(_read(path, MAX_RESULT_BYTES, 'Local command result'), MAX_RESULT_BYTES)
    require(isinstance(value, dict), 'Local command result must be an object')
    require(value.get('command_id') == doc['command_id'] and value.get('command_hash') == doc['command_hash'],
            'Local command ID already refers to a different operation')
    status = value.get('status')
    require(status in ('DONE', 'REJECTED', 'INDETERMINATE'), 'Invalid local command result status')
    required = {'command_id', 'command_hash', 'status', 'result' if status == 'DONE' else 'error'}
    require(set(value) == required, 'Invalid local command result fields')
    if status != 'DONE':
        require(isinstance(value['error'], str) and len(value['error']) <= 2000, 'Invalid local command result error')
    return value


def submit_command(root, pid, action, payload, timeout=30, command_id=None):
    """Write a command for the existing service; never acquire another writer."""
    require(type(timeout) in (int, float) and 0 < timeout <= 60,
            'Local command wait must be positive and at most 60 seconds')
    doc = {'version': 1, 'command_id': uuid.uuid4().hex if command_id is None else command_id,
           'process_id': pid, 'action': action, 'payload': payload}
    doc['command_hash'] = sha(encode(doc, limit=MAX_COMMAND_BYTES))
    # Freeze caller-owned payload data before publication and polling.
    doc = validate_command(decode(encode(doc, limit=MAX_COMMAND_BYTES), MAX_COMMAND_BYTES))
    pending = safe_path(Path(root), COMMANDS + '/' + doc['command_id'] + '.json')
    completed = safe_path(Path(root), RESULTS + '/' + doc['command_id'] + '.json')
    if completed.exists():
        return _result(completed, doc)
    data = encode(doc, limit=MAX_COMMAND_BYTES)
    try:
        published = _publish(pending, data)
    except OSError:
        # Publication can succeed before a later directory-sync/cleanup error.
        # Preserve the visible command identity instead of inviting a new ID.
        if not pending.exists() or _read(pending, MAX_COMMAND_BYTES, 'Local agent command') != data:
            raise
        published = False
    if not published:
        try:
            require(_read(pending, MAX_COMMAND_BYTES, 'Local agent command') == data,
                    'Local command ID already refers to a different operation')
        except (FileNotFoundError, ValidationError):
            # The service can finish and retire a matching pending request
            # between exclusive publication and this read. The final identity
            # must still match; an unrelated result never masks a conflict.
            if completed.exists():
                return _result(completed, doc)
            raise
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        if completed.exists():
            return _result(completed, doc)
        time.sleep(min(.05, max(0, end - time.monotonic())))
    return {'command_id': doc['command_id'], 'status': 'PENDING', 'result_file': str(completed),
            'message': 'Command preserved for the running service. Retry the same command with --command-id; '
                       'do not start another writer. Restart an older service through its existing launcher '
                       'if it does not support local commands.'}


def _retire(root, path, quarantine=False):
    # Never follow a rejected symlink. The rejection result records its cause.
    if path.is_symlink():
        path.unlink()
    elif quarantine:
        rejected = safe_path(root, REJECTED + '/' + path.name + '.' + uuid.uuid4().hex + '.rejected')
        rejected.parent.mkdir(parents=True, exist_ok=True)
        path.rename(rejected)
    else:
        path.unlink()


def _output(command_id, doc, status, **fields):
    return {'command_id': command_id, 'command_hash': doc.get('command_hash'), 'status': status, **fields}


def _consume(coordinator, path):
    """Isolate a single request so malformed input cannot terminate the worker."""
    command_id = path.stem
    try:
        dest = safe_path(coordinator.root, RESULTS + '/' + path.name)
    except ValidationError:
        # An unsafe result path cannot be followed or replaced. Preserve the
        # command outside the active queue so it cannot starve later requests.
        _retire(coordinator.root, path, quarantine=True)
        return
    doc = {}
    try:
        source = safe_path(coordinator.root, COMMANDS + '/' + path.name)
        doc = validate_command(decode(_read(source, MAX_COMMAND_BYTES, 'Local agent command'), MAX_COMMAND_BYTES))
        require(doc['command_id'] == command_id, 'Local command filename differs')
        if dest.exists():
            _result(dest, doc)
            _retire(coordinator.root, path)
            return
        started = safe_path(coordinator.root, RESULTS + '/' + command_id + '.started.json')
        marker = {'version': 1, 'command_id': command_id, 'command_hash': doc['command_hash']}
        marker_bytes = encode(marker)
        if started.exists() or not _publish(started, marker_bytes):
            require(_read(started, MAX_COMMAND_BYTES, 'Local action start marker') == marker_bytes,
                    'Local action start marker belongs to another operation')
            output = _output(command_id, doc, 'INDETERMINATE', error=
                'This command previously started without a durable final result. It may have changed local state. '
                'Inspect the process before deciding on a new command; this command will not execute again.')
        else:
            try:
                value = coordinator.local_agent_action(doc['process_id'], doc['action'], doc['payload'])
                output = _output(command_id, doc, 'DONE', result=value)
            except ValidationError as exc:
                output = _output(command_id, doc, 'REJECTED', error=str(exc)[:2000])
            except Exception as exc:
                output = _output(command_id, doc, 'INDETERMINATE', error=
                    ('Local action raised ' + type(exc).__name__ + ': ' + str(exc)
                     + '. Inspect process state; the same command will not execute again.')[:2000])
    except (ValidationError, OSError, ValueError, KeyError) as exc:
        output = _output(command_id, doc, 'REJECTED', error=str(exc)[:2000])
        # Preserve an existing result and quarantine the conflicting request.
        if not dest.exists():
            _publish(dest, encode(output, limit=MAX_RESULT_BYTES))
        _retire(coordinator.root, path, quarantine=True)
        return
    # Publication failure deliberately leaves the command + start marker intact.
    # The next drain reports INDETERMINATE instead of replaying the action.
    raw = encode(output, limit=MAX_RESULT_BYTES)
    if not _publish(dest, raw):
        require(_read(dest, MAX_RESULT_BYTES, 'Local command result') == raw, 'Local command result differs')
    _retire(coordinator.root, path)


def drain_commands(coordinator):
    """Called only by the Coordinator's existing worker, at stage boundaries."""
    folder = safe_path(coordinator.root, COMMANDS)
    if not folder.exists():
        return
    require(folder.is_dir(), 'Local agent command inbox is not a directory')
    consumed = 0
    for scanned, path in enumerate(folder.iterdir(), 1):
        require(scanned <= MAX_SCAN_ENTRIES, 'Local command inbox exceeds directory-entry bound')
        if not _COMMAND_FILE.fullmatch(path.name):
            continue
        try:
            _consume(coordinator, path)
        except Exception:
            # A failed filesystem write retains pending evidence; other requests
            # and the normal Coordinator stages must still be able to progress.
            pass
        consumed += 1
        if consumed >= MAX_BATCH:
            break
