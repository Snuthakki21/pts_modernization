"""Agent and operator CLI over the same persistent Coordinator as the UI."""
from .domain import path_is_link
import argparse
from io import BytesIO
import json
import re
from pathlib import Path
import shlex
import time
import zipfile
from .coordinator import Coordinator
from .domain import decode, ValidationError, require, sha, write_new
from .intake import parse_manifest
from .layout import require_layout, output_path
from .executive import accepted_executive, PRIMARY_REPORT

TERMINAL = frozenset({'COMPLETED', 'COMPLETED_WITH_BLOCKERS', 'CANCELLED'})
STOPPED = frozenset({'PAUSED', 'FAILED', 'REPORTING_FAILED'})
INBOX = 'input/sme-return-inbox.xlsx'
HTML_INBOX = 'input/sme-return-inbox.html'


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


def start_process(coordinator, manifest_path, assistant_mode=None, source_folder=None, process_notes=None, requirements_selection=False):
    path = Path(manifest_path)
    require(path.is_file() and not path_is_link(path) and not any(path_is_link(p) for p in path.absolute().parents),
            'Manifest must be a regular Markdown file with no symlink parents')
    require(path.stat().st_size <= 128000, 'Markdown intake is too large')
    raw = path.read_bytes()
    try: text = raw.decode('utf-8')
    except UnicodeDecodeError as exc: raise ValidationError('Manifest must be UTF-8 Markdown') from exc
    manifest = parse_manifest(text)
    existing = next((p for p in coordinator.ledger.list(True) if p['id'] == manifest['id']), None)
    if existing:
        if source_folder is not None:
            from .preflight import _read_sources
            supplied,_=_read_sources(coordinator.root,source_folder)
            original=existing.get('authorization',{}).get('scope',existing['source_files'])
            require({p:sha(t) for p,t in supplied.items()}==original,'Supplied folder differs from the frozen source; use a new process ID')
        if process_notes is not None:
            from .process_context import read_markdown
            require(read_markdown(process_notes)['sha256'] in {d['sha256'] for d in existing.get('process_context',{}).get('documents',[])},'Process notes changed; use a new process ID')
        manifest_integrity(coordinator, existing, raw)
        coordinator.sources(existing)  # Never credit a modified input snapshot.
        return coordinator.start(existing['id']) if existing['status'] == 'READY' else existing
    options={'assistant_mode':assistant_mode,'requirements_selection':requirements_selection}
    if source_folder is not None:options['source_folder']=source_folder
    if process_notes is not None:options['process_notes']=process_notes
    doc = coordinator.create(text,**options)
    return coordinator.start(doc['id'])


def import_return(coordinator, pid, path, reviewer):
    require(isinstance(reviewer, str) and 0 < len(reviewer.strip()) <= 160,
            'Supply --reviewer with the person responsible for this returned review file')
    path = Path(path)
    require(path.is_file() and not path_is_link(path) and not any(path_is_link(p) for p in path.parents),
            'SME return must be a regular file with no symlink parents')
    require(path.stat().st_size <= 8 * 1024 * 1024, 'SME review file exceeds upload bound')
    data = path.read_bytes(); doc = coordinator.ledger.get(pid)
    if doc['packet_imported']:
        require(sha(data) == (doc.get('answers') or {}).get('return_hash'),
                'The one SME return is already consumed; this review file differs from preserved evidence')
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
        if doc['status'] in ('WAITING_DISCOVERY','WAITING_REQUIREMENTS','WAITING_COPILOT'):return doc,False
        if doc['status'] == 'WAITING_SME':
            available=[output_path(coordinator.root,pid,name) for name in (INBOX,HTML_INBOX) if output_path(coordinator.root,pid,name).exists()]
            require(len(available)<=1,'Both review return inboxes exist; keep only the actual chosen single return')
            inbox=available[0] if available else output_path(coordinator.root,pid,INBOX)
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
                           ([('input/sme-return.html' if doc['answers'].get('return_format')=='html' else 'input/sme-return.xlsx')] if doc['packet_imported'] else []) +
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
            require(sha(entries['input/sme-return.html' if doc['answers'].get('return_format')=='html' else 'input/sme-return.xlsx']) == doc['answers']['return_hash'],
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


def _recorded_number(value):
    if value is None or type(value) in (int,float):return value
    if isinstance(value,str) and re.fullmatch(r'[0-9]+(?:\.[0-9]+)?',value):return value
    return None


def _model_error(error):
    # Exceptions may include source statements, private filenames or driver
    # values. Expose fixed categories and a digest, never arbitrary error prose.
    text=str(error)
    topics=[label for label in ('manifest hash','manifest','missing','layout','reviewer','already consumed',
            'source','retrieval','requirements','hash','workspace','command','timeout','configuration')
            if label in text.casefold()]
    return {'error':'Local validation failed ('+', '.join(topics or ['private input'])+
                    '); private details are withheld. Preserve evidence and use deterministic local diagnostics.',
            'error_sha256':sha(text)}


def _model_economics(model):
    """Explicit measurement fields, never recursive source/spec/prose values."""
    usage=model.get('usage') or {}
    accounts=(usage.get('credits') or {}).get('accounts',[])
    credits=[{'account_reference_sha256':sha(json.dumps({key:row.get(key) for key in ('provider','account')},sort_keys=True)),
              'credits_used':_recorded_number(row.get('credits_used'))} for row in accounts]
    return {'receipt_count':model.get('receipt_count',0),'learning_count':model.get('learning_count',0),
            'integrity_error_count':len(model.get('integrity_errors',[])),
            'forecast_error_count':len(model.get('forecast_errors',[])),
            'credits':{'status':'RECORDED' if credits else 'UNKNOWN','accounts':credits},
            'budgets':[{'account_reference_sha256':sha(json.dumps({key:row.get(key) for key in ('provider','account')},sort_keys=True)),
                        **{key:_recorded_number(row.get(key)) for key in ('remaining','tracked_since_snapshot','conditional_remaining')}}
                       for row in usage.get('budgets',[])],
            'processes':[{'work':{key:_recorded_number((row.get('work') or {}).get(key))
                                 for key in ('recorded_detail_hours','total_effort_hours')},
                          'timing':{key:_recorded_number((row.get('timing') or {}).get(key))
                                    for key in ('elapsed_hours','service_hours')}} for row in model.get('processes',[])],
            'boundary':'Actual attributed measurements only; private account labels and notes stay local.'}


def _model_executive(model):
    if not model:return None
    return {'status':model['status'],'observed_mainframe_parity':model.get('observed_mainframe_parity') is True,
            'scope':{key:_recorded_number((model.get('scope') or {}).get(key))
                     for key in ('source_files','physical_lines','in_scope_lines','excluded_lines','non_executable_lines','applicable_lines')},
            'progress':{key:_recorded_number((model.get('progress') or {}).get(key))
                        for key in ('converted_lines','blocked_lines','unverified_lines','verification_percent','open_blockers')},
            'before_after':[{'before':_recorded_number(row.get('before')),'after':_recorded_number(row.get('after'))}
                            for row in model.get('before_after',[])[:7]]}


def summary(coordinator, doc, timed_out=False):
    pid = doc['id']; root = coordinator.process_root(pid)
    result = {k: doc[k] for k in ('id', 'status', 'packet_hash', 'packet_issued', 'packet_imported')}
    result.update({'workspace': str(coordinator.root), 'timed_out': timed_out,
                   'blockers': doc.get('blockers', []),
                   'packet': [str(root / name) for name in doc['artifacts'] if name.startswith('review/')],
                   'reports': [str(root / name) for name in doc['artifacts'] if name.startswith('reports/')],
                   'sme_return_inbox': str(root / INBOX),
                   'sme_html_return_inbox': str(root / HTML_INBOX),
                   'continuation': shlex.join(['python', '-m', 'workbench.runner', 'resume', pid,
                                              '--workspace', str(coordinator.root), '--reviewer', 'ACTUAL REVIEWER'])})
    result['economics']=_model_economics(coordinator.economics(pid))
    accepted=accepted_executive(coordinator,doc)
    primary=accepted['executive_report']
    result['primary_report']=str(root/primary) if primary else None
    result['executive']=_model_executive(accepted['executive'])
    result['supporting_reports']=[path for path in result['reports'] if path!=result['primary_report']] if primary else []
    if primary:result['reports']=[result['primary_report']]
    if doc.get('factory_contract_version'):
        result['factory']={'obligation_count':len(doc.get('blockers',[])),
                           'transaction_count':len(doc.get('transactions',[])),
                           'source_file_count':len(doc['source_files']),
                           'dependency_node_count':len((doc.get('lineage') or {}).get('nodes',[])),
                           'dependency_edge_count':len((doc.get('lineage') or {}).get('edges',[])),
                           'fixture_contract_version':doc.get('fixture_contract_version'),
                           'minimum_distinct_records_per_logic':doc.get('logic_validation_min_records')}
    if doc['status'] == 'WAITING_SME':
        result['message'] = 'Deliver the issued checklist for the one SME review. Preserve Context/questions. Place the actual returned HTML in sme_html_return_inbox or workbook in sme_return_inbox, exactly one format, and resume with reviewer attribution. Never generate SME answers.'
    elif doc['status']=='WAITING_REQUIREMENTS':result['message']='Open the UI requirements breakdown, choose Yes/No and Save. The saved Markdown is the conversion input. Default Yes is scope, not SME approval.'
    elif doc['status']=='WAITING_DISCOVERY':result['message']='Read-only object discovery is incomplete. Inspect lineage gaps, supply original missing exports or local connector configuration, then resume. Conversion and the SME packet have not started.'
    elif doc['status']=='WAITING_COPILOT':result['message']='Claude Code uses approved metadata and sanitized source views for analysis, development, testing and review. Use python -m workbench.runner agent PROCESS_ID --workspace WORKSPACE. Missing evidence uses approved read-only Db2 MCP and Zowe CLI; private records remain in local deterministic verification.'
    elif timed_out: result['message'] = 'Bounded wait expired; evidence is preserved. Inspect status and run resume to continue.'
    elif doc['status'] in STOPPED: result['message'] = 'Stage stopped; inspect blockers and event ledger, correct the cause, then explicitly resume.'
    # CLI output can be consumed by Claude even for a historical process.
    # Preserve private originals in the ledger; emit no source statement/prose.
    result['blockers']=[{'kind':blocker.get('kind') if re.fullmatch(r'[a-z_]{1,64}',str(blocker.get('kind',''))) else 'unverified',
                        'evidence_sha256':sha(json.dumps(blocker,sort_keys=True)),
                        'message':'Private source-derived gap; inspect locally through deterministic evidence checks',
                        'source_refs':[{'source_hash':doc['source_files'][ref['path']],
                                        **{key:ref[key] for key in ('start_line','end_line') if type(ref.get(key)) is int}}
                                       for ref in blocker.get('source_refs',[]) if isinstance(ref,dict) and ref.get('path') in doc['source_files']]}
                       for blocker in doc.get('blockers',[])]
    result['data_policy']='METADATA_ONLY_PRIVATE_PROSE_WITHHELD'
    if doc.get('agent_transport')=='local_files':result['local_agent']=coordinator.local_agent_view(pid)
    return result


def parser():
    p = argparse.ArgumentParser(description=__doc__)
    commands = p.add_subparsers(dest='command', required=True)
    for name in ('run', 'start', 'resume', 'status', 'import', 'report', 'bundle'):
        c = commands.add_parser(name)
        c.add_argument('--workspace', '--workspace-path', '--root', required=True, help='Workspace containing the read-only Endeavor export')
        if name in ('run', 'start'):
            c.add_argument('--manifest', '--manifest-path', required=True)
            c.add_argument('--assistant',choices=['claude_files','agent','copilot_chat','deterministic','opt_in'],default=None,help='claude_files uses Claude approved read-only retrieval and local analysis; private source and records stay in deterministic local verification')
            c.add_argument('--select-requirements',action='store_true',help='Wait for explicit UI Yes/No scope Save before conversion')
            c.add_argument('--source-folder',help='Complete local or mounted export to snapshot without altering originals')
            c.add_argument('--process-notes',help='Original process Markdown to freeze as cited context')
        else: c.add_argument('process_id')
        if name in ('run', 'start', 'resume', 'import', 'report'):
            c.add_argument('--timeout', type=float, default=120, help='Bounded worker/watch wait, at most 3600 seconds')
            c.add_argument('--reviewer', default='', help='Actual person responsible for a returned SME review file')
            c.add_argument('--watch', action='store_true', help='Wait locally for the designated SME inbox until timeout')
        if name == 'import': c.add_argument('--file', required=True)
    c=commands.add_parser('measure')
    c.add_argument('--workspace',required=True)
    c.add_argument('--file',required=True,help='Actual attributed JSON receipt or explicit forecast plan; use runner agent --measurement-file when the UI is running')
    c=commands.add_parser('agent',help='Claude local-file analysis and retrieval continuation; never uses MCP or HTTP')
    c.add_argument('process_id');c.add_argument('--workspace',required=True)
    action=c.add_mutually_exclusive_group()
    action.add_argument('--continue',dest='agent_continue',action='store_true')
    action.add_argument('--refresh',action='store_true')
    action.add_argument('--analysis-file')
    action.add_argument('--request-file',help='JSON object containing a needs array with kind, name and reason')
    action.add_argument('--measurement-file',help='Actual attributed usage/work receipt; no estimated host credits')
    c.add_argument('--timeout',type=float,default=30)
    c.add_argument('--command-id',help='Retry the same queued command after a bounded wait')
    return p


def agent_command(args):
    from .local_agent import submit_command
    require(0<args.timeout<=60,'Local agent wait must be 1–60 seconds')
    action='continue' if args.agent_continue else 'refresh' if args.refresh else 'analysis' if args.analysis_file else 'request' if args.request_file else 'measurement' if args.measurement_file else 'inspect'
    payload={};filename=args.analysis_file or args.request_file or args.measurement_file
    if filename:
        path=Path(filename).absolute()
        require(not path_is_link(path) and not any(path_is_link(p) for p in path.parents) and path.is_file() and path.stat().st_size<=128000,'Agent input must be a bounded regular JSON file without symlinks')
        value=decode(path.read_bytes(),128000)
        if action=='request':
            require(isinstance(value,dict) and set(value)=={'needs'},'Request file must contain only a needs array');payload=value
        else:payload={'analysis' if action=='analysis' else 'receipt':value}
    if args.command_id:
        result=submit_command(Path(args.workspace),args.process_id,action,payload,args.timeout,args.command_id)
    else:
        coordinator=None
        try:
            try:coordinator=Coordinator(args.workspace)
            except ValidationError as exc:
                if 'Another workbench owns this workspace' not in str(exc):raise
                result=submit_command(Path(args.workspace),args.process_id,action,payload,args.timeout)
            else:result={'status':'DONE','result':coordinator.local_agent_action(args.process_id,action,payload)}
        finally:
            if coordinator:coordinator.close()
    if result['status'] in ('REJECTED','INDETERMINATE'):
        result={**result,**_model_error(result['error'])}
    if result['status']=='DONE' and action=='measurement':
        record=result['result'];document=record.get('document') or {}
        result={**result,'result':{'id':record.get('id'),'kind':record.get('kind'),
                                 'document':{'process_id':document.get('process_id')},
                                 'receipt_sha256':sha(json.dumps(record,sort_keys=True))}}
    print(json.dumps(result,indent=2))
    return 3 if result['status']=='PENDING' else 2 if result['status'] in ('REJECTED','INDETERMINATE') else 0


def main(argv=None):
    args = parser().parse_args(argv)
    coordinator = None
    try:
        require_layout(args.workspace)
        if args.command=='agent':return agent_command(args)
        if hasattr(args, 'timeout'):
            require(0 < args.timeout <= 3600, 'Timeout must be greater than zero and at most 3600 seconds')
            require(not args.watch or bool(args.reviewer.strip()), '--watch requires --reviewer attribution')
        coordinator = Coordinator(args.workspace)
        if args.command=='measure':
            data=Path(args.file).read_bytes();require(len(data)<=65536,'Measurement exceeds 64 KiB')
            record=coordinator.record_measurement(decode(data,65536))
            print(json.dumps({'id':record.get('id'),'kind':record.get('kind'),
                              'receipt_sha256':sha(json.dumps(record,sort_keys=True))},indent=2));return 0
        if args.command in ('run', 'start'): doc = start_process(coordinator, args.manifest,args.assistant,args.source_folder,args.process_notes,args.select_requirements)
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
        print(json.dumps({**_model_error(exc), 'continuation': 'Inspect status/layout and correct the named cause through deterministic local checks; preserve all existing evidence.'}, indent=2))
        return 2
    finally:
        if coordinator: coordinator.close()


if __name__ == '__main__': raise SystemExit(main())
