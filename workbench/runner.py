"""Agent and operator CLI over the same persistent Coordinator as the UI."""
import argparse
from io import BytesIO
import json
from pathlib import Path
import shlex
import time
import zipfile
from .coordinator import Coordinator
from .domain import ValidationError, require, sha, write_new
from .intake import parse_manifest
from .layout import require_layout, output_path
from .executive import accepted_executive, PRIMARY_REPORT

TERMINAL = frozenset({'COMPLETED', 'COMPLETED_WITH_BLOCKERS', 'CANCELLED'})
STOPPED = frozenset({'PAUSED', 'FAILED', 'REPORTING_FAILED'})
INBOX = 'input/sme-return-inbox.xlsx'


def manifest_integrity(coordinator, doc, supplied=None):
    recorded = doc.get('manifest_hash')
    require(isinstance(recorded, str) and len(recorded) == 64,
            'Recorded manifest hash is missing; historical evidence cannot be silently recertified. Use a separately authorized new process ID.')
    pinned = output_path(coordinator.root, doc['id'], 'input/process-input.md')
    require(pinned.is_file() and sha(pinned.read_bytes()) == recorded,
            'Frozen manifest snapshot changed from its recorded manifest hash')
    if supplied is not None:
        require(sha(supplied) == recorded,
                'Process ID already exists with a different manifest hash; use its original manifest or a new process ID')


def start_process(coordinator, manifest_path, assistant_mode=None):
    path = Path(manifest_path)
    require(path.is_file() and not path.is_symlink() and not any(p.is_symlink() for p in path.absolute().parents),
            'Manifest must be a regular Markdown file with no symlink parents')
    require(path.stat().st_size <= 128000, 'Markdown intake is too large')
    raw = path.read_bytes()
    try: text = raw.decode('utf-8')
    except UnicodeDecodeError as exc: raise ValidationError('Manifest must be UTF-8 Markdown') from exc
    manifest = parse_manifest(text)
    existing = next((p for p in coordinator.ledger.list(True) if p['id'] == manifest['id']), None)
    if existing:
        manifest_integrity(coordinator, existing, raw)
        coordinator.sources(existing)  # Never credit a modified input snapshot.
        return coordinator.start(existing['id']) if existing['status'] == 'READY' else existing
    doc = coordinator.create(text,assistant_mode=assistant_mode)
    return coordinator.start(doc['id'])


def import_return(coordinator, pid, path, reviewer):
    require(isinstance(reviewer, str) and 0 < len(reviewer.strip()) <= 160,
            'Supply --reviewer with the person responsible for this returned workbook')
    path = Path(path)
    require(path.is_file() and not path.is_symlink() and not any(p.is_symlink() for p in path.parents),
            'SME return must be a regular file with no symlink parents')
    require(path.stat().st_size <= 8 * 1024 * 1024, 'SME workbook exceeds upload bound')
    data = path.read_bytes(); doc = coordinator.ledger.get(pid)
    if doc['packet_imported']:
        require(sha(data) == (doc.get('answers') or {}).get('return_hash'),
                'The one SME return is already consumed; this workbook differs from preserved evidence')
        require(reviewer.strip() == (doc.get('answers') or {}).get('reviewer'),
                'Reviewer attribution differs from the consumed return')
        return doc
    return coordinator.import_answers(pid, data, reviewer.strip())


def wait_for_process(coordinator, pid, timeout=120, watch=False, reviewer=''):
    require(0 < timeout <= 3600, 'Timeout must be greater than zero and at most 3600 seconds')
    require(not watch or bool(reviewer.strip()), '--watch requires --reviewer attribution before an automatic import')
    deadline = time.monotonic() + timeout
    coordinator.launch_worker()
    while True:
        doc = coordinator.ledger.get(pid)
        if doc['status'] in TERMINAL or doc['status'] in STOPPED: return doc, False
        if doc['status'] in ('WAITING_DISCOVERY','WAITING_COPILOT'):return doc,False
        if doc['status'] == 'WAITING_SME':
            inbox = output_path(coordinator.root, pid, INBOX)
            if inbox.exists():
                # A single designated inbox is detected. Coordinator records return_hash and
                # atomically consumes the quota; retries cannot create another SME round.
                import_return(coordinator, pid, inbox, reviewer)
                continue
            if not watch: return doc, False
        if time.monotonic() >= deadline: return doc, True
        time.sleep(min(.1, max(0, deadline - time.monotonic())))


def bundle_process(coordinator, pid):
    with coordinator.lock:
        doc = coordinator.ledger.get(pid)
        manifest_integrity(coordinator, doc)
        require(doc['status'] in TERMINAL, 'Bundle requires completed or cancelled evidence; inspect status first')
        require(doc.get('report_verified'), 'Bundle requires inspected report artifacts')
        report_hashes = doc.get('report_hashes')
        required_reports = {'metrics.json','metrics.csv','metrics.xlsx','management.pptx','inspection.json',
                            'coverage.json','coverage.csv','coverage.xlsx','coverage.html'}
        require(isinstance(report_hashes, dict) and bool(report_hashes)
                and required_reports.issubset({Path(name).name for name in report_hashes}),
                'Bundle requires the complete inspected report hash baseline')
        require(all(name in doc['artifacts'] and name.startswith('reports/') for name in report_hashes)
                and len({str(Path(name).parent) for name in report_hashes}) == 1,
                'Bundle report hashes contain missing, orphaned or inconsistent inspected artifacts')
        report_folder=Path(next(iter(report_hashes))).parent
        inspection_name=(report_folder/'inspection.json').as_posix()
        inspection=json.loads(coordinator.artifact(pid,inspection_name).read_text(encoding='utf-8'))
        if inspection.get('primary_report') == PRIMARY_REPORT:
            require((report_folder/PRIMARY_REPORT).as_posix() in report_hashes,
                    'Bundle requires the accepted executive report hash baseline')
        coordinator.review_integrity(doc)
        names = sorted(set(['input/process-input.md'] +
                           ['input/sources/' + name for name in doc['source_files']] +
                           (['input/sme-return.xlsx'] if doc['packet_imported'] else []) +
                           [name for name in doc['artifacts'] if not name.endswith('.zip')]))
        entries = {}
        for name in names:
            path = output_path(coordinator.root, pid, name)
            if name in doc['artifacts']: path = coordinator.artifact(pid, name)
            require(path.is_file(), 'Bundle evidence is missing: ' + name)
            entries[name] = path.read_bytes()
        require(sha(entries['input/process-input.md']) == doc['manifest_hash'],
                'Bundle manifest bytes differ from the recorded manifest hash')
        for name, recorded in doc['source_files'].items():
            require(sha(entries['input/sources/' + name]) == recorded,
                    'Bundle source bytes differ from their recorded snapshot: ' + name)
        if doc['packet_imported']:
            require(sha(entries['input/sme-return.xlsx']) == doc['answers']['return_hash'],
                    'Bundle SME return bytes differ from the accepted return')
        for name, recorded in report_hashes.items():
            require(name in entries and sha(entries[name]) == recorded,
                    'Bundle report bytes differ from inspected evidence: ' + name)
        coordinator.sources(doc)
        fingerprint = sha(json.dumps({name: sha(data) for name, data in entries.items()}, sort_keys=True))
        relative = 'reports/bundle-' + fingerprint[:16] + '.zip'
        stream = BytesIO()
        with zipfile.ZipFile(stream, 'w', compression=zipfile.ZIP_DEFLATED) as archive:
            for name, data in entries.items():
                item = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
                item.compress_type = zipfile.ZIP_DEFLATED
                archive.writestr(item, data)
        path = output_path(coordinator.root, pid, relative)
        data = stream.getvalue()
        if path.exists(): require(path.read_bytes() == data, 'Bundle version integrity failed')
        else: write_new(path, data)
        coordinator.register(doc, relative); coordinator.ledger.save(doc)
        return str(path)


def summary(coordinator, doc, timed_out=False):
    pid = doc['id']; root = coordinator.process_root(pid)
    result = {k: doc[k] for k in ('id', 'status', 'packet_hash', 'packet_issued', 'packet_imported')}
    result.update({'workspace': str(coordinator.root), 'timed_out': timed_out,
                   'blockers': doc.get('blockers', []),
                   'packet': [str(root / name) for name in doc['artifacts'] if name.startswith('review/')],
                   'reports': [str(root / name) for name in doc['artifacts'] if name.startswith('reports/')],
                   'sme_return_inbox': str(root / INBOX),
                   'continuation': shlex.join(['python', '-m', 'workbench.runner', 'resume', pid,
                                              '--workspace', str(coordinator.root), '--reviewer', 'ACTUAL REVIEWER'])})
    accepted=accepted_executive(coordinator,doc)
    primary=accepted['executive_report']
    result['primary_report']=str(root/primary) if primary else None
    result['executive']=accepted['executive']
    result['supporting_reports']=[path for path in result['reports'] if path!=result['primary_report']] if primary else []
    if primary:result['reports']=[result['primary_report']]
    if doc['status'] == 'WAITING_SME':
        result['message'] = 'Deliver the issued checklist for the one SME review. Preserve Context/questions. Place the actual returned workbook in sme_return_inbox and resume with reviewer attribution. Never generate SME answers.'
    elif doc['status']=='WAITING_DISCOVERY':result['message']='Read-only object discovery is incomplete. Inspect lineage gaps, supply original missing exports or local connector configuration, then resume. Conversion and the SME packet have not started.'
    elif doc['status']=='WAITING_COPILOT':result['message']='Open GitHub Copilot Chat in VS Code with examples/mcp.json configured. Request the frozen task using workbench_next_task, inspect sources, implement required adapters with tests, then submit the structured analysis. No LLM endpoint is required.'
    elif timed_out: result['message'] = 'Bounded wait expired; evidence is preserved. Inspect status and run resume to continue.'
    elif doc['status'] in STOPPED: result['message'] = 'Stage stopped; inspect blockers and event ledger, correct the cause, then explicitly resume.'
    return result


def parser():
    p = argparse.ArgumentParser(description=__doc__)
    commands = p.add_subparsers(dest='command', required=True)
    for name in ('run', 'start', 'resume', 'status', 'import', 'report', 'bundle'):
        c = commands.add_parser(name)
        c.add_argument('--workspace', '--workspace-path', '--root', required=True, help='Workspace containing the read-only Endeavor export')
        if name in ('run', 'start'):
            c.add_argument('--manifest', '--manifest-path', required=True)
            c.add_argument('--assistant',choices=['copilot_chat','deterministic','opt_in'],default=None,help='Copilot Chat uses the local MCP bridge; no model endpoint/token')
        else: c.add_argument('process_id')
        if name in ('run', 'start', 'resume', 'import', 'report'):
            c.add_argument('--timeout', type=float, default=120, help='Bounded worker/watch wait, at most 3600 seconds')
            c.add_argument('--reviewer', default='', help='Actual person responsible for a returned SME workbook')
            c.add_argument('--watch', action='store_true', help='Wait locally for the designated SME inbox until timeout')
        if name == 'import': c.add_argument('--file', required=True)
    return p


def main(argv=None):
    args = parser().parse_args(argv)
    coordinator = None
    try:
        require_layout(args.workspace)
        if hasattr(args, 'timeout'):
            require(0 < args.timeout <= 3600, 'Timeout must be greater than zero and at most 3600 seconds')
            require(not args.watch or bool(args.reviewer.strip()), '--watch requires --reviewer attribution')
        coordinator = Coordinator(args.workspace)
        if args.command in ('run', 'start'): doc = start_process(coordinator, args.manifest,args.assistant)
        else: doc = coordinator.ledger.get(args.process_id)
        if args.command == 'import': doc = import_return(coordinator, doc['id'], args.file, args.reviewer)
        if args.command == 'resume' and doc['status'] in STOPPED|{'WAITING_DISCOVERY'}:
            doc = coordinator.control(doc['id'], 'resume')
        if args.command == 'resume':
            require(doc['status'] != 'READY', 'Process is READY; use start with its original manifest to record Start authorization')
        if args.command == 'report' and doc['status'] == 'REPORTING_FAILED':
            doc = coordinator.control(doc['id'], 'resume')
        timed_out = False
        if args.command in ('run', 'start', 'resume', 'import', 'report'):
            doc, timed_out = wait_for_process(coordinator, doc['id'], args.timeout, args.watch, args.reviewer)
        result = summary(coordinator, doc, timed_out)
        if args.command == 'bundle': result['bundle'] = bundle_process(coordinator, doc['id'])
        print(json.dumps(result, indent=2))
        return 3 if timed_out else 2 if doc['status'] in STOPPED else 0
    except (ValidationError, OSError) as exc:
        print(json.dumps({'error': str(exc), 'continuation': 'Inspect status/layout and correct the named cause; preserve all existing evidence.'}, indent=2))
        return 2
    finally:
        if coordinator: coordinator.close()


if __name__ == '__main__': raise SystemExit(main())
