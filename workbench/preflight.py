"""Offline setup and intake diagnostics; no source requests or workflow mutations."""
import argparse
import importlib
from importlib import metadata
import json
import os
from pathlib import Path
import platform
import re
import shutil
import socket
import sys
import unicodedata

from .domain import MAX_UPLOAD, ValidationError, require, safe_path
from .limits import (MAX_SOURCE_BYTES, MAX_SOURCE_ENTRIES, MAX_SOURCE_FILE_BYTES,
                     MAX_SOURCE_FILES, MAX_SOURCE_LINES, source_line_count)
from .layout import validate_workspace
from .setup import deterministic_metrics

REPOSITORY = Path(__file__).resolve().parent.parent
STATIC_ROOT = Path(__file__).with_name('static')
MIN_FREE_BYTES = 256 * 1024 * 1024


def initialize_knowledge(workspace):
    """Explicit setup only: install the editable template once, preserving all edits."""
    root = Path(workspace).absolute()
    require(root.is_dir() and not root.is_symlink() and not any(p.is_symlink() for p in root.parents),
            'Use an existing workspace directory with no symlink parents')
    destination = safe_path(root, 'knowledge/application-knowledge.json')
    if destination.exists():
        require(destination.is_file(), 'Application knowledge must be a regular JSON file')
        return destination
    template = REPOSITORY / 'examples/application-knowledge.json'
    require(template.is_file() and not template.is_symlink(), 'Application knowledge template is missing; restore the repository release')
    raw = template.read_bytes()
    destination.parent.mkdir(parents=True, exist_ok=True)
    try:
        with destination.open('xb') as out: out.write(raw)
    except FileExistsError:
        require(destination.is_file() and not destination.is_symlink(), 'Application knowledge destination changed during setup')
    return destination


def _locked(path):
    """Probe only an existing OS lock; do not create or modify lock files."""
    if not path.exists(): return False
    require(path.is_file() and not path.is_symlink(), 'Unsafe workspace lock path')
    with path.open('r+b' if os.name == 'nt' else 'rb') as handle:
        if os.name == 'nt':
            import msvcrt
            # InstanceLock always writes one byte before obtaining a Windows lock.
            if path.stat().st_size == 0: return False
            try: msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            except OSError: return True
            msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            import fcntl
            try: fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError: return True
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
    return False


def _read_sources(root):
    folder = safe_path(root, 'Endeavor')
    require(folder.is_dir(), 'Endeavor is missing; provide the complete UTF-8 text export')
    files, portable, size, lines = {}, {}, 0, 0
    # Count entries before sorting, and never follow a directory symlink. A
    # materialized rglob() could exhaust memory before its limit was checked.
    pending, paths, entries = [folder], [], 0
    while pending:
        current = pending.pop()
        if current != folder: safe_path(folder, current.relative_to(folder).as_posix())
        require(current.is_dir() and not current.is_symlink(), 'Source directories must be regular directories without symlinks')
        with os.scandir(current) as children:
            for child in children:
                entries += 1
                require(entries <= MAX_SOURCE_ENTRIES,
                        f'Source directory traversal exceeds {MAX_SOURCE_ENTRIES:,} entries; use a process-scoped export')
                path = Path(child.path)
                require(not child.is_symlink(), 'Source exports must not contain symlinks')
                paths.append(path)
                if child.is_dir(follow_symlinks=False): pending.append(path)
    for path in sorted(paths):
        require(not path.is_symlink(), 'Source exports must not contain symlinks')
        relative = path.relative_to(folder).as_posix()
        safe_path(folder, relative)
        key = unicodedata.normalize('NFC', relative).casefold()
        require(key not in portable, 'Source names collide on case-insensitive filesystems; disambiguate the export')
        portable[key] = relative
        if path.is_dir(): continue
        require(path.is_file(), 'Source exports must contain only regular files and directories')
        require(len(files) < MAX_SOURCE_FILES, f'Source export exceeds the {MAX_SOURCE_FILES:,} file limit')
        require(path.stat().st_size <= MAX_SOURCE_FILE_BYTES,
                f'Source file exceeds the {MAX_SOURCE_FILE_BYTES:,} byte limit: ' + relative)
        read_limit = min(MAX_SOURCE_FILE_BYTES, MAX_SOURCE_BYTES - size)
        with path.open('rb') as source: raw = source.read(read_limit + 1)
        require(len(raw) <= MAX_SOURCE_FILE_BYTES,
                f'Source file changed or exceeds the {MAX_SOURCE_FILE_BYTES:,} byte limit: ' + relative)
        size += len(raw)
        require(size <= MAX_SOURCE_BYTES, f'Source export exceeds the {MAX_SOURCE_BYTES:,} byte combined limit')
        try: text = raw.decode('utf-8')
        except UnicodeError as exc: raise ValidationError('Source export contains non-UTF-8 bytes; decode using the original CCSID before intake') from exc
        require('\x00' not in text, 'Source export contains NUL/binary content; export readable source separately from data/load modules')
        lines += source_line_count(text)
        require(lines <= MAX_SOURCE_LINES,
                f'Source export exceeds the {MAX_SOURCE_LINES:,} combined physical-line limit; use a process-scoped export')
        files[relative] = text
    require(files, 'Endeavor is empty; provide the complete UTF-8 text export')
    return files, size


def _manifest(path):
    from .intake import parse_manifest, parse_intake_xlsx
    path = Path(path).absolute()
    require(path.is_file() and not path.is_symlink() and not any(p.is_symlink() for p in path.parents),
            'Manifest must be a regular Markdown or XLSX file with no symlink parents')
    limit = MAX_UPLOAD if path.suffix.lower() == '.xlsx' else 128000
    require(path.stat().st_size <= limit, 'Intake file exceeds its size limit')
    with path.open('rb') as manifest: raw = manifest.read(limit + 1)
    require(len(raw) <= limit, 'Intake file changed or exceeds its size limit')
    if path.suffix.lower() == '.xlsx':
        try: return parse_intake_xlsx(raw)
        except ValidationError: raise
        except Exception as exc: raise ValidationError('Excel intake could not be parsed; use the supplied editable XLSX template') from exc
    try: text = raw.decode('utf-8')
    except UnicodeError as exc: raise ValidationError('Markdown manifest must be valid UTF-8') from exc
    return parse_manifest(text)


def inspect_workspace(workspace, manifest=None, *, port=None, environ=None, coordinator_owned=False):
    """Return setup readiness separately from conversion support and live connectivity.

    This is a point-in-time diagnostic. It deliberately does not call connectors,
    generate evidence, import SME answers, or acquire a persistent writer lock.
    """
    env = dict(os.environ if environ is None else environ)
    root = Path(workspace).absolute()
    checks = []
    result = {'status':'READY', 'conversion_status':'UNVERIFIED', 'checks':checks,
              'conversion_blockers':[], 'network_requests':0, 'metrics':deterministic_metrics(),
              'scope':'Offline local setup/intake check. READY permits analysis; it is not conversion, parity, or connectivity certification.'}

    def add(name, status, message, action=''):
        checks.append({'id':name, 'status':status, 'message':message, 'action':action})

    compatible = sys.version_info[:2] == (3, 12) and platform.python_implementation() == 'CPython'
    add('python', 'READY' if compatible else 'BLOCKED', 'CPython 3.12 is required by the release lock.',
        '' if compatible else 'Run scripts/Setup.ps1 or bash scripts/setup.sh with CPython 3.12 installed.')
    try:
        locked = re.findall(r'^([A-Za-z0-9_-]+)==([^\s\\]+)', (REPOSITORY / 'requirements.lock').read_text(), re.M)
        require(bool(locked), 'Dependency lock is missing or empty')
        problems = []
        for name, expected in locked:
            try:
                if metadata.version(name) != expected: problems.append(name + ' version differs from the lock')
            except metadata.PackageNotFoundError: problems.append(name + ' is missing')
        for module in ('fastapi', 'uvicorn', 'openpyxl', 'docx', 'pptx'):
            try: importlib.import_module(module)
            except Exception: problems.append(module + ' cannot be imported')
        require(not problems, '; '.join(problems))
        add('dependencies', 'READY', str(len(locked)) + ' installed dependency versions match the release lock; core imports succeeded.')
    except (ValidationError, OSError, UnicodeError) as exc:
        add('dependencies', 'BLOCKED', str(exc), 'Run the setup script using the release requirements.lock and its verified wheels.')
    try:
        frontend = all((STATIC_ROOT / name).is_file() and not (STATIC_ROOT / name).is_symlink()
                       and (STATIC_ROOT / name).stat().st_size > 0 for name in ('index.html', 'app.js', 'style.css'))
    except OSError: frontend = False
    add('frontend', 'READY' if frontend else 'BLOCKED', 'Committed UI bundle is present.' if frontend else 'The committed UI bundle is incomplete.',
        '' if frontend else 'Restore workbench/static from the release, or run npm ci and npm run build in frontend.')
    safe_root = root.is_dir() and not root.is_symlink() and not any(p.is_symlink() for p in root.parents)
    add('workspace', 'READY' if safe_root else 'BLOCKED', 'Existing workspace path is a directory without symlink parents.' if safe_root else 'Workspace is missing, is not a directory, or uses a symlink.',
        '' if safe_root else 'Create a dedicated local-disk workspace directory and use its direct path.')
    if safe_root:
        try:
            issues = validate_workspace(root)
            add('layout', 'BLOCKED' if issues else 'READY', '; '.join(issues[:20]) if issues else 'Workspace follows the required folder structure.',
                'Move misplaced inputs to their documented categories; never move frozen process evidence.' if issues else '')
            writable = os.access(root, os.R_OK | os.W_OK | os.X_OK)
            add('workspace_access', 'READY' if writable else 'BLOCKED',
                'OS access check permits reading, traversal and writes; no probe file was created.' if writable else 'OS access check denied workspace access.',
                'Keep sufficient local permissions; actual writes and quota are still enforced during the run.')
            free = shutil.disk_usage(root).free
            add('disk_space', 'READY' if free >= MIN_FREE_BYTES else 'BLOCKED',
                f'{free // (1024 * 1024)} MiB free; the preflight reserve is 256 MiB.',
                'Allow additional capacity for exports, synthetic cases, reports and backups; this reserve is not a total-size estimate.')
            if coordinator_owned:
                add('workspace_lock', 'READY', 'This running Coordinator already owns the workspace lock.')
            else:
                locked = _locked(safe_path(root, '.migration/coordinator.lock'))
                add('workspace_lock', 'BLOCKED' if locked else 'READY',
                    'Another workbench owns the workspace.' if locked else 'No other writer held the existing workspace lock when checked.',
                    'Stop the UI before running a separate CLI Coordinator.' if locked else 'The Coordinator acquires the authoritative lock at startup.')
        except (ValidationError, OSError) as exc:
            add('workspace_io', 'BLOCKED', 'Workspace checks could not finish: ' + str(exc), 'Check local permissions, locked files and filesystem availability.')
    add('filesystem', 'UNVERIFIED', 'Filesystem reliability, network-drive locking, backup recovery and hardware capacity are not certified by this check.',
        'Use local disk, one writer, and a tested backup of the entire stopped workspace; avoid network shares and live cloud-sync folders.')
    add('platform', 'UNVERIFIED', 'Native Windows/PowerShell and browser rendering require validation on the operator machine.',
        'Open the UI after launch and confirm downloads, Excel return import and the generated PPT on the target machine.')
    if port is not None:
        try:
            require(type(port) is int and 1 <= port <= 65535, 'Port must be 1..65535')
            with socket.socket() as sock: sock.bind(('127.0.0.1', port))
            add('ui_port', 'READY', 'The requested loopback port was available when checked.')
        except (ValidationError, OSError):
            add('ui_port', 'BLOCKED', 'The requested loopback port is invalid, occupied or unavailable.', 'Stop the existing server or choose another --port; startup will recheck the bind.')

    snapshot = None
    if safe_root:
        try:
            from .mainframe import load_knowledge
            snapshot = load_knowledge(root)
            add('mainframe_knowledge', 'READY', 'Standard and application knowledge passed strict validation. Recognition does not grant conversion support.')
            if not (root / 'knowledge/application-knowledge.json').exists():
                add('application_knowledge', 'NOT_CONFIGURED', 'No application-specific utility catalog is present.',
                    'Run preflight --initialize-knowledge once, then edit knowledge/application-knowledge.json before starting a new process.')
        except (ImportError, ValidationError, OSError, UnicodeError) as exc:
            add('mainframe_knowledge', 'BLOCKED', 'Mainframe knowledge could not be validated: ' + str(exc),
                'Restore the standard catalog or correct knowledge/application-knowledge.json; never overwrite frozen process snapshots.')
        try:
            context = safe_path(root, 'knowledge/inbox/context.md')
            if context.exists():
                require(context.is_file() and context.stat().st_size <= 16000, 'Background context must be a regular UTF-8 Markdown file of at most 16,000 bytes')
                with context.open('rb') as background: raw = background.read(16001)
                require(len(raw) <= 16000, 'Background context exceeds 16,000 bytes'); raw.decode('utf-8')
                add('background_context', 'READY', 'Background context is within the UTF-8 text bound; its content remains unverified.')
            else: add('background_context', 'NOT_CONFIGURED', 'Optional background context was not supplied.', 'Put application articles in knowledge/inbox/context.md, at most 16,000 UTF-8 bytes.')
        except (ValidationError, OSError, UnicodeError):
            add('background_context', 'BLOCKED', 'Background context is not readable UTF-8, exceeds its size bound, or has an unsafe path.', 'Correct knowledge/inbox/context.md before Start.')
    if manifest is None:
        add('manifest', 'NOT_CONFIGURED', 'No process intake was checked.', 'Use --manifest process-input.md, or upload the intake and source files in the UI.')
        add('source_export', 'NOT_CONFIGURED', 'No process export was checked because no intake was supplied.', 'Supply --manifest to check Endeavor files and offline converter support before starting.')
    elif safe_root:
        parsed, files = None, None
        try:
            parsed = _manifest(manifest)
            add('manifest', 'READY', 'Process intake structure and job/step order passed validation.')
            if safe_path(root, 'processes/' + parsed['id']).exists():
                add('existing_process', 'UNVERIFIED', 'This process ID already has preserved evidence. This preview checks the supplied export, not its frozen historical snapshot.',
                    'Use runner status/resume with the original manifest; changed intake or knowledge requires a new process ID. Never edit historical inputs.')
        except (ValidationError, OSError, UnicodeError, ImportError) as exc:
            add('manifest', 'BLOCKED', str(exc), 'Correct the Markdown intake or Excel template; the agent runner accepts Markdown, while the UI accepts both.')
        try:
            files, size = _read_sources(root)
            result['input'] = {'files':len(files), 'bytes':size}
            add('source_export', 'READY', f'{len(files)} source files passed path, count, UTF-8 and byte-limit checks.',
                'Include referenced COPY/PROC/INCLUDE/control-card members and preserve export CCSID/record-format metadata separately.')
        except (ValidationError, OSError, UnicodeError) as exc:
            add('source_export', 'BLOCKED', str(exc), 'Correct the complete local Endeavor export; do not discard unreadable or unknown files to inflate coverage.')
        if parsed is not None and files is not None and snapshot is not None:
            try:
                from .source import analyze_sources
                parsed['mainframe_knowledge'] = snapshot
                analysis = analyze_sources(files, parsed)
                result['conversion_blockers'] = analysis['blockers']
                if analysis['blockers']: result['conversion_status'] = 'BLOCKED'
                add('conversion_scope', 'UNVERIFIED',
                    str(len(analysis['blockers'])) + ' known conversion blockers found; analysis and the single SME packet can still proceed.' if analysis['blockers'] else 'No blocker was found in offline analysis; SME approval and execution-based verification are still required.',
                    'Review all named blockers in the process coverage report. Recognized utilities need implemented, tested adapters before receiving conversion credit.')
            except (ValidationError, OSError, UnicodeError) as exc:
                add('conversion_scope', 'BLOCKED', 'Offline analysis could not complete: ' + str(exc), 'Correct ambiguous source identities or input structure before starting.')
                result['conversion_status'] = 'BLOCKED'

    # Validate configuration only. Do not print endpoint, profile, model or token values.
    from .connectors import endpoint, ZoweReader
    if env.get('WB_DB2_MCP_URL'):
        try:
            endpoint(env['WB_DB2_MCP_URL'])
            add('db2', 'UNVERIFIED', 'Db2 MCP endpoint configuration is syntactically valid; authentication, TLS trust, protocol and read capabilities have not been contacted.',
                'Use a read-only account and compatible typed MCP gateway; inspect bounded discovery results during analysis.')
        except (ValidationError, ValueError):
            add('db2', 'BLOCKED', 'Db2 MCP endpoint configuration is invalid.', 'Use HTTPS or loopback HTTP without embedded credentials or fragments.')
    else: add('db2', 'NOT_CONFIGURED', 'Optional Db2 MCP endpoint is not configured.', 'Set WB_DB2_MCP_URL and private authentication if live discovery is needed.')
    if env.get('WB_ZOWE_PROFILE'):
        try:
            ZoweReader(env['WB_ZOWE_PROFILE'], env.get('WB_ZOWE_ZOSMF_PROFILE'))
            require(shutil.which('zowe', path=env.get('PATH', os.defpath)), 'Zowe CLI is not on PATH')
            hint = env.get('WB_DATASET_HINT', '*')
            require(isinstance(hint,str) and re.fullmatch(r'[A-Za-z0-9@$#.*()_-]{1,150}', hint) and not hint.startswith('-'), 'Invalid dataset hint')
            add('zowe', 'UNVERIFIED', 'Zowe CLI and profile syntax are configured; credentials, profile existence, access and catalog completeness are unverified.',
                'Authenticate the approved read-only profile locally; review discovery errors or truncation during analysis.')
        except ValidationError:
            add('zowe', 'BLOCKED', 'Configured Zowe CLI/profile/dataset hint failed a local check.', 'Install the approved Zowe CLI on PATH; use a valid existing profile alias and dataset hint.')
    else: add('zowe', 'NOT_CONFIGURED', 'Optional Zowe profile is not configured.', 'Set WB_ZOWE_PROFILE after local authentication if live discovery is needed.')
    if env.get('WB_LLM_URL'):
        try:
            from .provider import StructuredProvider
            StructuredProvider(env['WB_LLM_URL'],env.get('WB_LLM_MODEL'),env.get('WB_LLM_TOKEN',''))
            require(env.get('WB_ALLOW_SOURCE_EGRESS', 'false') in ('true', 'false'), 'Invalid source egress setting')
            egress = env.get('WB_ALLOW_SOURCE_EGRESS') == 'true'
            add('llm', 'UNVERIFIED', 'Provider configuration is syntactically valid; reachability and response compatibility are unverified. ' +
                ('Source egress is explicitly enabled.' if egress else 'Source egress is disabled; configured LLM analysis will remain blocked.'),
                'Use an approved chat-completions provider and model. Enable WB_ALLOW_SOURCE_EGRESS=true only when source transfer is authorized, or omit WB_LLM_URL for deterministic operation.')
        except (ValidationError, ValueError):
            add('llm', 'BLOCKED', 'LLM endpoint/model/egress configuration is incomplete or invalid.', 'Set an approved HTTPS endpoint and model; use true/false for WB_ALLOW_SOURCE_EGRESS, or omit WB_LLM_URL.')
    else: add('llm', 'NOT_CONFIGURED', 'Optional LLM suggestions are disabled; deterministic analysis does not require an LLM.')
    if env.get('WB_DB2_ODBC_CONNECTION'):
        try: importlib.import_module('pyodbc')
        except (ImportError, OSError): add('db2_gateway', 'BLOCKED', 'An ODBC connection is configured but pyodbc cannot be imported.', 'Provision the optional gateway environment and IBM ODBC driver; the base lock does not install them.')
        else: add('db2_gateway', 'UNVERIFIED', 'pyodbc is installed; IBM driver, connection credentials and database access have not been tested.', 'Run the read-only gateway with private credentials; do not expose it beyond the approved network.')
    if safe_root and (root / '.env').exists():
        add('environment_file', 'UNVERIFIED', '.env is present but is not auto-loaded.', 'Export the required variables in the shell before launch; preflight never reads or prints .env contents.')
    result['status'] = 'BLOCKED' if any(c['status'] == 'BLOCKED' for c in checks) else 'READY'
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--workspace', '--root', default=str(Path.cwd()))
    parser.add_argument('--manifest', help='Optional Markdown or UI XLSX intake; also checks the local Endeavor export. The agent runner requires Markdown.')
    parser.add_argument('--port', type=int, help='Check a loopback UI port without starting a server')
    parser.add_argument('--json', action='store_true', help='Print machine-readable diagnostics')
    parser.add_argument('--initialize-knowledge', action='store_true', help='Explicitly copy the application template if absent; never replace edits')
    args = parser.parse_args(argv)
    try:
        if args.initialize_knowledge: initialize_knowledge(args.workspace)
        result = inspect_workspace(args.workspace, args.manifest, port=args.port)
    except (ValidationError, OSError, UnicodeError) as exc:
        result = {'status':'BLOCKED', 'conversion_status':'UNVERIFIED', 'checks':[{'id':'preflight', 'status':'BLOCKED',
                  'message':str(exc), 'action':'Correct the reported local setup error and rerun preflight.'}], 'conversion_blockers':[]}
    if args.json: print(json.dumps(result, indent=2))
    else:
        print('Setup: ' + result['status'] + '; conversion: ' + result['conversion_status'])
        for check in result['checks']:
            print(f"[{check['status']}] {check['id']}: {check['message']}")
            if check['action']: print('  Action: ' + check['action'])
        for blocker in result['conversion_blockers']:
            print('[CONVERSION BLOCKER] ' + blocker.get('message', blocker.get('kind', 'Unresolved source behavior')))
    return 2 if result['status'] == 'BLOCKED' else 0


if __name__ == '__main__': raise SystemExit(main())
