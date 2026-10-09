"""Persistent Start → one SME exchange → verification → reports coordinator."""
from .domain import path_is_link
import json
from pathlib import Path
import sqlite3
import threading
import time
from .domain import require, identity, safe_path, write_new, encode, decode, sha, ValidationError
from .intake import parse_manifest
from .ledger import Ledger, now
from .source import analyze_sources
from .target import emit_jobs, check_generated
from .backends import get_backend, adapter_fingerprint
from .fixtures import plan_cases, verify_program
from .review import export_packet
from .knowledge import update_knowledge
from .layout import require_layout, output_path
from .limits import (MAX_SOURCE_FILES, MAX_SOURCE_ENTRIES, MAX_SOURCE_FILE_BYTES,
                     MAX_SOURCE_BYTES, MAX_SOURCE_LINES, source_line_count)


_UNSET = object()


class StageInterrupted(Exception):
    pass


class Coordinator:
    def __init__(self, root):
        from .instance import InstanceLock
        require_layout(root)
        self.root=Path(root).resolve();self.instance=InstanceLock(self.root)
        self.adapter_fingerprint=adapter_fingerprint()
        self.lock=threading.RLock();self.provider_lock=threading.RLock();self.stopped=threading.Event();self.worker=None;self.closed=False;self.active=set();self.work_clocks={};self.ledger=None
        try:
            self.ledger=Ledger(self.root)
            from .provider import configured_provider
            self.provider=configured_provider()
            from .setup import load_workstation_settings
            self.workstation_settings=load_workstation_settings(self.root)
            for p in self.ledger.list(True):
                try:self.artifact_reference_integrity(p)
                except ValidationError as exc:
                    p['report_verified']=False
                    if not any(b['kind']=='evidence_integrity' for b in p['blockers']):p['blockers'].append({'kind':'evidence_integrity','message':str(exc)})
                    status='QUEUED_REPORT' if p['status'] in ('COMPLETED','COMPLETED_WITH_BLOCKERS','ANALYZING','VERIFYING','REPORTING') else None
                    self.ledger.save(p,status)
                    continue # Preserve unsafe historical keys and their original baselines.
                prior_artifacts=len(p['artifacts'])
                hashes=p.get('artifact_hashes') or {}
                review_paths=['review/'+f for f in ('packet.json','sme-checklist.xlsx','sme-checklist.docx','sme-checklist.html')]
                legacy=not p.get('manifest_hash') or any(relative not in hashes for relative in p['artifacts']) or (p['packet_issued'] and any(relative not in hashes for relative in review_paths))
                if legacy:
                    already_flagged=any(b['kind']=='legacy_missing_baseline' for b in p['blockers'])
                    if not already_flagged:p['blockers'].append({'kind':'legacy_missing_baseline','message':'This preserved older process lacks immutable manifest/artifact baselines; original evidence is uncredited and target execution is prohibited. Preserve the old process; create a new intake from original exports to establish baselines.'})
                    final_hashes=p.get('report_hashes') or {}
                    accepted=p['status']=='COMPLETED_WITH_BLOCKERS' and p.get('report_verified') and already_flagged and bool(final_hashes)
                    if accepted:
                        for relative,fingerprint in final_hashes.items():
                            path=output_path(self.root,p['id'],relative)
                            if hashes.get(relative)!=fingerprint or not path.is_file() or sha(path.read_bytes())!=fingerprint:accepted=False;break
                    if not accepted:p['report_verified']=False;self.ledger.save(p,'QUEUED_REPORT')
                    continue # Never restore or repin mutable legacy artifacts.
                if p['status'] in ('COMPLETED','COMPLETED_WITH_BLOCKERS'):
                    try:self.manifest_integrity(p)
                    except (ValidationError,FileNotFoundError) as exc:
                        p['report_verified']=False
                        if not any(b['kind']=='evidence_integrity' for b in p['blockers']):p['blockers'].append({'kind':'evidence_integrity','message':str(exc)})
                        p=self.ledger.save(p,'QUEUED_REPORT')
                if p['packet_issued']:
                    for file in ['packet.json','sme-checklist.xlsx','sme-checklist.docx','sme-checklist.html']:
                        require(safe_path(self.process_root(p['id']),'review/'+file).is_file(),'Issued packet is incomplete; recover its preserved snapshot')
                        self.register(p,'review/'+file)
                if p['status'] in ('ANALYZING','VERIFYING','REPORTING'):
                    status='QUEUED_REPORT' if p['status']=='REPORTING' or p.get('cancel_requested') or p.get('verification_finished') else 'QUEUED_ANALYSIS' if not p['packet_issued'] else 'QUEUED_VERIFY' if p['packet_imported'] else 'WAITING_SME'
                    self.ledger.save(p,status)
                elif len(p['artifacts'])!=prior_artifacts:self.ledger.save(p)
        except Exception:
            try:
                if self.ledger:self.ledger.close()
            finally:self.instance.close()
            raise

    def configure_workstation(self,settings,connections=None,origin='http://127.0.0.1:8765'):
        from .setup import save_workstation
        with self.lock:
            if connections is None:result=save_workstation(self.root,settings)
            else:
                from .connection_setup import configure_connections
                result=configure_connections(self.root,settings,connections,origin=origin)
            self.workstation_settings=result['settings']
            return result

    def process_root(self,pid):return safe_path(self.root,'processes/'+identity(pid))

    def create(self, manifest_text, source_files=None, demo=False, prompt='', assistant_mode=None, source_folder=_UNSET, process_notes=_UNSET, requirements_selection=False, *, _prepare=False):
        require_layout(self.root)
        from .setup import intake_defaults
        defaults=intake_defaults(self.root)
        if source_folder is _UNSET:source_folder=defaults['source_folder'] if source_files is None else None
        if process_notes is _UNSET:process_notes=defaults['process_notes']
        manifest=parse_manifest(manifest_text)
        require(type(requirements_selection) is bool,'Requirements selection mode must be a boolean')
        require(source_folder is None or isinstance(source_folder,(str,Path)) and bool(str(source_folder).strip()),'Source folder must be a nonempty path')
        require(process_notes is None or isinstance(process_notes,(str,Path)) and bool(str(process_notes).strip()),'Process notes must be a nonempty path')
        require(source_folder is None or source_files is None,'Choose uploaded sources or one source folder')
        if source_files is None:
            from .preflight import _read_sources
            source_files,_=_read_sources(self.root,source_folder)
        require(isinstance(source_files,dict) and (0 if _prepare else 1)<=len(source_files)<=MAX_SOURCE_FILES,f'Provide a source folder with 1 to {MAX_SOURCE_FILES:,} supported text files')
        require(all(isinstance(k,str) and isinstance(v,str) for k,v in source_files.items()),'Source filenames and contents must be text')
        require(all('\x00' not in value for value in source_files.values()),'Source contains NUL/binary content; provide readable source separately from data/load modules')
        require(sum(source_line_count(value) for value in source_files.values())<=MAX_SOURCE_LINES,f'Source export exceeds {MAX_SOURCE_LINES:,} physical lines')
        import os
        assistant_mode=assistant_mode or os.environ.get('WB_ASSISTANT_MODE','deterministic')
        local_files=assistant_mode=='claude_files'
        require(not _prepare or local_files and requirements_selection,'Prepared retrieval intake requires the local Claude workflow and explicit requirements selection')
        agent_mode=assistant_mode in ('agent','claude_files')
        if agent_mode:assistant_mode='copilot_chat'
        require(assistant_mode in ('deterministic','disabled','copilot_chat','opt_in'),'Choose the Claude workflow, deterministic analysis, or the explicitly configured legacy provider')
        require(isinstance(prompt,str),'Analysis prompt must be text')
        try:
            encoded_sources={path:text.encode('utf-8') for path,text in source_files.items()}
            for path in source_files:path.encode('utf-8')
            encoded_manifest=manifest_text.encode('utf-8');prompt.encode('utf-8')
        except UnicodeError as exc:raise ValidationError('Source filenames, source text, manifest and prompt must be valid UTF-8 text without unpaired surrogates') from exc
        require(sum(len(raw) for raw in encoded_sources.values())<=MAX_SOURCE_BYTES,'Source export exceeds combined size bound')
        # Reject collisions before any immutable process evidence is created.
        from .retrieval import validate_source_paths
        validate_source_paths(source_files)
        from .mainframe import load_knowledge
        knowledge=load_knowledge(self.root)
        from .process_context import freeze_context
        context_snapshot=freeze_context(self.root,process_notes)
        with self.lock:
            require_layout(self.root)
            require(not self.process_root(manifest['id']).exists(),'Process directory already exists')
            require(not any(p.name.casefold()==manifest['id'].casefold() for p in (self.root/'processes').glob('*')),'Process ID collides on case-insensitive platforms; use a unique ID')
            for path,text in source_files.items():
                output_path(self.root,manifest['id'],'input/sources/'+path)
                require(len(encoded_sources[path])<=MAX_SOURCE_FILE_BYTES,'Source file exceeds bounds: '+path)
            doc=self.ledger.create(manifest,demo)
            try:
                base=self.process_root(doc['id']);write_new(base/'input'/'process-input.md',encoded_manifest)
                hashes={}
                for path,raw in encoded_sources.items():hashes[path]=write_new(output_path(self.root,doc['id'],'input/sources/'+path),raw)
                doc['source_files']=hashes
                if _prepare:doc['intake_source_files']=dict(hashes)
                doc['manifest_hash']=sha(encoded_manifest);doc['prompt']=prompt[:16000]
                doc['requirements_selection']=requirements_selection
                if _prepare:
                    doc['guided_contract_version']=1;doc['guided_workspace']=str(self.root)
                    doc['source_intake_pending']=True
                doc['assistant_mode']=assistant_mode;doc['sme_packet_version']=4 if agent_mode else 3
                doc['agent_host']='external' if agent_mode else assistant_mode
                doc['development_contract_version']=2 if local_files else 1
                if local_files:doc['agent_transport']='local_files'
                if agent_mode or manifest.get('transactions'):doc['factory_contract_version']=1
                if manifest.get('transactions'):doc['cics_contract_version']=1
                doc['target_backend']={'name':'python-sqlite','contract_version':1}
                doc['process_context']=context_snapshot
                write_new(base/'analysis'/'process-context.json',encode(context_snapshot))
                self.register(doc,'analysis/process-context.json')
                doc['source_origin']={'kind':'pending_retrieval' if _prepare and not source_files else 'folder' if source_folder is not None else 'workspace_or_upload', 'location':str(Path(source_folder).absolute()) if source_folder is not None else None}
                write_new(base/'analysis'/'source-origin.json',encode(doc['source_origin']))
                self.register(doc,'analysis/source-origin.json')
                doc['logic_validation_min_records']=64
                doc['fixture_contract_version']=5
                from .inventory import snapshot_inventory
                doc['inventory_baseline']=snapshot_inventory(self.root)
                write_new(base/'analysis'/'inventory-baseline.json',encode(doc['inventory_baseline']))
                self.register(doc,'analysis/inventory-baseline.json')
                from .locations import input_locations
                doc['application_input_locations']=input_locations(self.root)
                write_new(base/'analysis'/'input-locations.json',encode(doc['application_input_locations']))
                self.register(doc,'analysis/input-locations.json')
                doc['mainframe_knowledge']=knowledge
                write_new(base/'analysis'/'mainframe-knowledge.json',encode(knowledge))
                self.register(doc,'analysis/mainframe-knowledge.json')
                if _prepare:
                    self.ledger.save(doc)
                    from .guide import snapshot
                    snapshot(self,doc)
                return self.ledger.save(doc)
            except Exception:
                doc['blockers']=[{'kind':'intake_storage','message':'Input storage failed; preserved available evidence.'}];self.ledger.save(doc,'FAILED');raise

    def prepare_process(self,manifest_text,source_files=None,prompt='',source_folder=None,process_notes=None,demo=False):
        """Prepare a manifest before source arrives; explicit demos retain portfolio exclusion."""
        require(type(demo) is bool,'Fictional process intent must be a boolean')
        require(isinstance(prompt,str) and len(prompt)<=16000,'Analysis prompt must be text with at most 16,000 characters')
        if source_files is None and source_folder is None:source_files={}
        manifest=parse_manifest(manifest_text)
        with self.lock:
            existing=next((p for p in self.ledger.list(True) if p['id']==manifest['id']),None)
            if existing:
                require(existing.get('guided_contract_version')==1,'Process already exists; select it or use a new process ID')
                self.sources(existing)
                if source_files is None:
                    from .preflight import _read_sources
                    source_files,_=_read_sources(self.root,source_folder)
                require(isinstance(source_files,dict) and all(isinstance(k,str) and isinstance(v,str) for k,v in source_files.items()),'Prepared sources must be text files')
                from .process_context import freeze_context
                require(sha(manifest_text)==existing['manifest_hash'] and
                        {path:sha(text) for path,text in source_files.items()}==existing.get('intake_source_files') and
                        freeze_context(self.root,process_notes)==existing['process_context'] and prompt==existing['prompt'] and demo==existing['demo'],
                        'Process input changed; select the existing process or use a new process ID')
                return existing
            return self.create(manifest_text,source_files,demo,prompt,'claude_files',source_folder,process_notes,True,_prepare=True)

    def process_guide(self,pid):
        from .guide import view
        with self.lock:
            doc=self.ledger.get(pid);self.sources(doc)
            return view(self,doc)

    def save_process_guide(self,pid):
        from .guide import snapshot,view
        with self.lock:
            doc=self.ledger.get(pid);self.sources(doc)
            require(pid not in self.active and doc['status'] not in ('ANALYZING','VERIFYING','REPORTING'),
                    'Wait for the current stage before saving process instructions')
            snapshot(self,doc);self.ledger.save(doc)
            return view(self,doc)

    def start(self,pid):
        with self.lock:
            require_layout(self.root)
            doc=self.ledger.get(pid);self.manifest_integrity(doc);require(doc['status']=='READY','Process already started; use Resume when applicable')
            import secrets
            seed=secrets.randbits(63) if doc.get('fixture_contract_version') in (4,5) else 21
            doc['authorization']={'recorded':now(),'scope':dict(doc['source_files']),'target':'verified-adapters/python-sqlite','seed':seed,'max_cases_per_program':4096 if doc.get('logic_validation_min_records') else 256,'max_repair_attempts':1,'source_operations':'read-only','mainframe_execution':False}
            if doc.get('fixture_contract_version') in (4,5):doc['authorization']['fixture_contract_version']=doc['fixture_contract_version']
            return self.ledger.save_event(doc,'QUEUED_ANALYSIS','start','Start authorization recorded; source writes and mainframe execution are prohibited')

    def control(self,pid,action):
        with self.lock:
            doc=self.ledger.get(pid)
            require(doc['status'] not in ('COMPLETED','COMPLETED_WITH_BLOCKERS'),'Terminal evidence cannot be changed in place')
            if action=='pause':
                require(doc['status'] in ('QUEUED_ANALYSIS','ANALYZING','WAITING_DISCOVERY','WAITING_REQUIREMENTS','WAITING_COPILOT','WAITING_SME','QUEUED_VERIFY','VERIFYING','QUEUED_REPORT','REPORTING'),'There is no running stage to pause; use Resume to recover a failed stage')
                doc['resume_status']={'ANALYZING':'QUEUED_ANALYSIS','VERIFYING':'QUEUED_VERIFY','REPORTING':'QUEUED_REPORT'}.get(doc['status'],doc['status']);status='PAUSED'
            elif action=='resume':
                require(doc['status'] in ('PAUSED','FAILED','REPORTING_FAILED','WAITING_DISCOVERY'),'Nothing eligible to resume')
                status=doc.pop('resume_status','QUEUED_REPORT' if doc['packet_imported'] else 'WAITING_SME' if doc['packet_issued'] else 'QUEUED_ANALYSIS')
                if doc['status'] in ('FAILED','REPORTING_FAILED'):doc.setdefault('stage_attempts',{})[status]=0
                if status=='QUEUED_ANALYSIS' and doc['packet_issued']:status='QUEUED_VERIFY' if doc['packet_imported'] else 'WAITING_SME'
                if status=='QUEUED_VERIFY' and doc.get('verification_finished'):status='QUEUED_REPORT'
                doc['next_retry_at']=0
            elif action=='cancel':
                if not any(b['kind']=='cancelled' for b in doc['blockers']):doc['blockers'].append({'kind':'cancelled','message':'Operator cancelled this process'})
                doc['cancel_requested']=True;status='QUEUED_REPORT'
            else:raise ValidationError('Unknown control')
            doc['control_revision']=doc.get('control_revision',0)+1
            return self.ledger.save_event(doc,status,action,'Operator '+action+' recorded; existing SME quota retained')

    def checkpoint(self,doc,status=None,persist=True):
        """Accept durable controls under a short lock; workers never overwrite them."""
        with self.lock:
            current=self.ledger.get(doc['id']) if persist or status else self.ledger.controls(doc['id'])
            interrupted=current['status']=='PAUSED' or (current.get('cancel_requested') and doc.get('_active_stage')!='QUEUED_REPORT') or self.closed
            for key in ('control_revision','cancel_requested','resume_status'):
                if key in current:doc[key]=current[key]
            for blocker in current['blockers']:
                if blocker['kind']=='cancelled' and blocker not in doc['blockers']:doc['blockers'].append(blocker)
            if interrupted:
                target=current['status']
                if self.closed and target not in ('PAUSED','QUEUED_REPORT'):target=doc['_active_stage']
                self.ledger.save(doc,target);raise StageInterrupted()
            if status in ('COMPLETED','COMPLETED_WITH_BLOCKERS'):status='COMPLETED_WITH_BLOCKERS' if doc['blockers'] else 'COMPLETED'
            return self.ledger.save(doc,status) if persist or status else current

    def stage_success(self,doc,stage):
        doc['blockers']=[b for b in doc['blockers'] if not (b['kind']=='stage_failure' and b.get('stage')==stage)]
        doc.pop('last_failure',None);doc.pop('last_error',None);doc.pop('resume_status',None);doc['next_retry_at']=0

    def artifact(self,pid,relative):
        doc=self.ledger.get(pid);require(relative in doc['artifacts'],'Artifact not registered for this process')
        path=output_path(self.root,pid,relative)
        final_report=Path(relative).parts[0]=='reports' and relative in doc.get('report_hashes',{})
        if not final_report:self.manifest_integrity(doc)
        require(path.is_file(),'Artifact unavailable')
        fingerprint=doc.get('artifact_hashes',{}).get(relative)
        require(fingerprint,'Registered artifact baseline is missing; preserved evidence cannot be certified or silently repinned')
        require(sha(path.read_bytes())==fingerprint,'Registered artifact changed after freezing: '+relative)
        if relative in doc.get('report_hashes',{}):require(fingerprint==doc['report_hashes'][relative],'Report artifact differs from its inspected version')
        return path

    def program_comparison(self,pid,*,program='',status='all',after=0,limit=25):
        """Read the accepted report snapshot; never run conversion or verification."""
        from .executive import accepted_executive
        from .comparison import comparison_page
        with self.lock:
            doc=self.ledger.get(pid)
            accepted=accepted_executive(self,doc)
            relative=accepted['executive_report']
            require(relative is not None,'Program comparison requires an accepted report from the Coordinator')
            folder=Path(relative).parent.as_posix()
            def frozen(name):
                require(name in doc.get('report_hashes',{}),'Comparison evidence is missing from the accepted report baseline')
                path=self.artifact(pid,name)
                require(path.stat().st_size<=128*1024*1024,'Accepted comparison artifact exceeds the bounded reader limit; use the complete report download')
                raw=path.read_bytes()
                require(len(raw)<=128*1024*1024 and sha(raw)==doc['report_hashes'][name],
                        'Accepted comparison evidence changed while reading: '+name)
                return raw
            # Bind the exact bytes being parsed, including the accepted generation gates.
            frozen(relative)
            metrics_raw=frozen(folder+'/metrics.json'); raw=frozen(folder+'/rules.json')
            try:
                metrics=json.loads(metrics_raw); inventory=json.loads(raw)
            except (ValueError,UnicodeError) as exc:
                raise ValidationError('Accepted comparison evidence is not valid JSON') from exc
            require(inventory.get('process_id')==pid,'Accepted rule inventory belongs to another process')
            context=metrics.get('executive_context') or {}
            require(context.get('rule_inventory')=={k:v for k,v in inventory.items() if k not in ('rules','requirements_comparison')},
                    'Accepted comparison inventory differs from the executive report context')
            if 'process_gates' not in inventory:
                # Historical details come only from accepted frozen coverage/context, never live replay.
                from .comparison import freeze_process_gates
                coverage_raw=frozen(folder+'/coverage.json')
                try:historical_coverage=json.loads(coverage_raw)
                except (ValueError,UnicodeError) as exc:raise ValidationError('Accepted coverage details are not valid JSON') from exc
                inventory={**inventory,'process_gates':freeze_process_gates(context,historical_coverage)}
            page=comparison_page(inventory,program=program,status=status,after=after,limit=limit)
            gates=page['process_gates']+[gate for rule in page['rules'] for field in ('gaps','program_gates') for gate in rule[field]]
            references={ref for gate in gates for ref in gate.get('evidence',[])}
            # Preserved inputs use their frozen receipt hash, not the artifact download route.
            page['downloadable_evidence']=sorted(references.intersection(doc.get('artifacts',[]),doc.get('artifact_hashes',{})))
            page['snapshot']={'report':relative,'inventory':folder+'/rules.json','html':folder+'/rules.html',
                              'coverage':folder+'/coverage.html','inventory_sha256':sha(raw),'created':metrics.get('created')}
            return page

    def register(self,doc,relative):
        path=output_path(self.root,doc['id'],relative)
        require(path.is_file(),'Artifact registration requires an existing regular file: '+relative)
        fingerprint=sha(path.read_bytes());hashes=doc.setdefault('artifact_hashes',{})
        if relative in doc['artifacts'] or relative in hashes:
            require(relative in hashes,'Registered artifact baseline is missing; preserved evidence cannot be silently repinned: '+relative)
            require(hashes[relative]==fingerprint,'Registered artifact changed after freezing: '+relative)
        else:hashes[relative]=fingerprint
        if relative not in doc['artifacts']:doc['artifacts'].append(relative)

    def import_answers(self,pid,data,reviewer):
        with self.lock:
            require_layout(self.root)
            doc=self.ledger.get(pid);self.sources(doc);require(doc['status']=='WAITING_SME','Process is not waiting for SME answers')
            packet=decode(self.artifact(pid,'review/packet.json').read_bytes())
            require(packet.get('packet_hash')==doc['packet_hash'] and sha(encode({k:v for k,v in packet.items() if k!='packet_hash'}))==doc['packet_hash'],'Frozen SME packet integrity failed')
            require(packet.get('process_id')==pid and packet.get('source_snapshot')==doc['analysis']['source_snapshot'],
                    'Frozen SME packet does not belong to this process and source snapshot')
            from .review import read_return
            answers=read_return(data,packet,reviewer)
            extension='html' if answers.get('return_format')=='html' else 'xlsx'
            other=self.process_root(pid)/'input'/('sme-return.xlsx' if extension=='html' else 'sme-return.html')
            require(not other.exists(),'A different return format was already preserved; recover that exact receipt')
            returned=self.process_root(pid)/'input'/('sme-return.'+extension)
            if returned.exists():require(returned.read_bytes()==data,'Recovery return differs from the preserved SME file')
            else:write_new(returned,data)
            self.ledger.consume_return(pid,answers)
            return self.ledger.get(pid)

    def artifact_reference_integrity(self,doc):
        # Historical registrations may predate portable path guards. Validate
        # identities without reading, normalizing or repinning their evidence.
        references=[*(doc.get('artifacts') or []), *(doc.get('artifact_hashes') or {}),
                    *(doc.get('report_hashes') or {})]
        require(all(isinstance(relative,str) for relative in references),'Frozen evidence references must be text')
        for relative in dict.fromkeys(references):
            try:output_path(self.root,doc['id'],relative)
            except ValidationError as exc:
                raise ValidationError('Frozen evidence reference '+repr(relative)+' is invalid; preserve its original key and baseline: '+str(exc)) from exc

    def manifest_integrity(self,doc):
        self.artifact_reference_integrity(doc)
        require(doc.get('manifest_hash'),'Frozen manifest baseline is missing; preserve this process and create a new intake with an original manifest baseline; never pin an existing mutable file on Resume')
        raw=output_path(self.root,doc['id'],'input/process-input.md').read_bytes()
        require(sha(raw)==doc['manifest_hash'],'Frozen process manifest changed; existing evidence cannot be credited')
        frozen=parse_manifest(raw.decode('utf-8'))
        require(all(frozen.get(key)==doc.get(key) for key in ('id','name','jobs','transactions','workload')),'Process metadata differs from the frozen manifest')
        if 'mainframe_knowledge' in doc or 'analysis/mainframe-knowledge.json' in doc.get('artifact_hashes',{}):
            from .mainframe import validate_snapshot
            snapshot=doc.get('mainframe_knowledge');validate_snapshot(snapshot)
            relative='analysis/mainframe-knowledge.json'
            raw=output_path(self.root,doc['id'],relative).read_bytes()
            require(raw==encode(snapshot) and sha(raw)==doc.get('artifact_hashes',{}).get(relative),'Frozen mainframe knowledge changed; preserve the original process evidence')
        context_relative='analysis/process-context.json'
        if 'process_context' in doc or context_relative in doc.get('artifact_hashes',{}) or context_relative in doc.get('artifacts',[]):
            snapshot=doc.get('process_context')
            require(isinstance(snapshot,dict) and context_relative in doc.get('artifacts',[]),
                    'Frozen process context baseline is missing; preserve the original process evidence')
            expected=encode(snapshot);path=output_path(self.root,doc['id'],context_relative)
            require(path.is_file() and path.stat().st_size==len(expected),'Frozen process context is missing or changed')
            with path.open('rb') as stream:raw=stream.read(len(expected)+1)
            require(raw==expected and sha(raw)==doc.get('artifact_hashes',{}).get(context_relative),
                    'Frozen process context changed or lacks its registered hash; preserve the original process evidence')
        if 'inventory_baseline' in doc:
            from .inventory import validate_snapshot
            validate_snapshot(doc['inventory_baseline'])
            relative='analysis/inventory-baseline.json';raw=output_path(self.root,doc['id'],relative).read_bytes()
            require(raw==encode(doc['inventory_baseline']) and sha(raw)==doc.get('artifact_hashes',{}).get(relative),'Frozen inventory baseline changed')
        if 'application_input_locations' in doc:
            relative='analysis/input-locations.json';raw=output_path(self.root,doc['id'],relative).read_bytes()
            require(raw==encode(doc['application_input_locations']) and sha(raw)==doc.get('artifact_hashes',{}).get(relative),'Frozen input location evidence changed')
        if doc.get('lineage_artifact'):
            relative=doc['lineage_artifact'];raw=output_path(self.root,doc['id'],relative).read_bytes()
            require(raw==encode(doc.get('lineage')) and sha(raw)==doc.get('artifact_hashes',{}).get(relative),'Frozen lineage scope changed; discovery cannot be bypassed')
        origins={}
        pending=doc.get('pending_discovery',{}).get('artifact')
        for relative in doc.get('artifacts',[]):
            if not relative.startswith('analysis/discovery-') or relative==pending:continue
            raw=output_path(self.root,doc['id'],relative).read_bytes()
            require(sha(raw)==doc.get('artifact_hashes',{}).get(relative),'Frozen discovery provenance changed')
            for entry in decode(raw)['files']:
                require(doc['source_files'].get(entry['path'])==entry['source_hash'],'Retrieved source baseline differs from discovery journal')
                origins[entry['path']]=entry['provenance']
        require(origins==doc.get('discovery_provenance',{}),'Retrieved source provenance differs from frozen journals')

    def review_integrity(self,doc):
        self.manifest_integrity(doc)
        if not doc['packet_issued']:return
        for file in ('packet.json','sme-checklist.xlsx','sme-checklist.docx','sme-checklist.html'):self.artifact(doc['id'],'review/'+file)
        packet=decode((self.process_root(doc['id'])/'review'/'packet.json').read_bytes())
        require(packet.get('packet_hash')==doc['packet_hash'] and sha(encode({k:v for k,v in packet.items() if k!='packet_hash'}))==doc['packet_hash'],'Frozen SME packet integrity failed')
        require(packet['source_snapshot']==doc['analysis']['source_snapshot'],'SME packet differs from the frozen source snapshot')
        if doc['packet_imported']:
            answers=doc.get('answers') or {}
            relative='input/sme-return.html' if answers.get('return_format')=='html' else 'input/sme-return.xlsx'
            raw=safe_path(self.process_root(doc['id']),relative).read_bytes()
            require(sha(raw)==answers.get('return_hash'),'Preserved SME return changed')
            from .review import read_return
            require(read_return(raw,packet,answers.get('reviewer',''))==answers,'SME answers differ from the preserved return')

    def target_checkpoint(self,doc):
        self.checkpoint(doc,persist=False)
        require(not doc.get('cancel_requested'),'Cancelled: target execution is prohibited')
        require(not any(b['kind']=='legacy_missing_baseline' for b in doc['blockers']),'Legacy immutable baselines are missing: target execution is prohibited')

    def sources(self,doc):
        self.manifest_integrity(doc)
        if doc.get('requirements'):
            from .requirements import verify_snapshot
            verify_snapshot(doc,self.root)
        self.recover_discovered_sources(doc)
        source_root=self.process_root(doc['id'])/'input'/'sources'
        inventory=set()
        for count,path in enumerate(source_root.rglob('*'),1):
            require(count<=MAX_SOURCE_ENTRIES,'Frozen source traversal exceeds entry bound')
            require(not path_is_link(path) and (path.is_file() or path.is_dir()),
                    'Source snapshot contains an unsafe file')
            if path.is_file():inventory.add(path.relative_to(source_root).as_posix())
        require(inventory==set(doc['source_files']),
                'Source snapshot file inventory changed; every exported file must retain its frozen accounting')
        result={}
        for path,h in doc['source_files'].items():
            raw=safe_path(self.process_root(doc['id'])/'input'/'sources',path).read_bytes()
            require(sha(raw)==h,'Source snapshot changed; existing evidence cannot be credited')
            result[path]=raw.decode('utf-8')
        return result

    def recover_discovered_sources(self,doc):
        """Replay only a ledger-pinned, content-addressed read-only fetch journal."""
        pending=doc.get('pending_discovery')
        if not pending:return
        relative=pending['artifact'];raw=output_path(self.root,doc['id'],relative).read_bytes()
        require(sha(raw)==doc.get('artifact_hashes',{}).get(relative),'Discovery journal integrity failed')
        entries=decode(raw)['files'];require(sha(encode(entries))==pending['hash'],'Discovery journal differs from recorded intent')
        # Validate the complete pinned intent before publishing even its first
        # file. Older versions could pin an impossible source-tree collision.
        existing={}
        for path,digest in doc['source_files'].items():
            content=output_path(self.root,doc['id'],'input/sources/'+path).read_bytes()
            require(sha(content)==digest,'Source snapshot changed; pending discovery cannot be recovered')
            existing[path]=content.decode('utf-8')
        try:self._validate_discovered_sources(doc,entries,existing)
        except ValidationError as exc:
            raise ValidationError('Pinned discovery cannot be applied; preserve its accepted evidence and create a separately identified process from intact exports: '+str(exc)) from exc
        for item in entries:
            path=item['path'];data=item['text'].encode('utf-8')
            require(sha(data)==item['source_hash'] and item.get('provenance'),'Retrieved source lacks immutable origin evidence')
            destination=output_path(self.root,doc['id'],'input/sources/'+path)
            if destination.exists():require(destination.read_bytes()==data,'Retrieved source conflicts with preserved input: '+path)
            else:write_new(destination,data)
            doc['source_files'][path]=item['source_hash']
        doc.setdefault('discovery_provenance',{}).update({e['path']:e['provenance'] for e in entries})
        doc.pop('pending_discovery');self.ledger.save(doc)

    def _validate_discovered_sources(self,doc,entries,existing):
        """Check the merged source intent without pinning or writing evidence."""
        from .retrieval import validate_source_paths
        require(isinstance(entries,list) and all(isinstance(e,dict) for e in entries),'Retrieved source entries must be objects')
        validate_source_paths([*existing, *[entry['path'] for entry in entries]])
        merged=dict(existing)
        for entry in entries:
            path=entry['path'];text=entry['text']
            require(isinstance(text,str) and '\x00' not in text,'Retrieved source must be readable text')
            require(Path(path).as_posix()==path and all(p not in ('','.','..') for p in path.split('/')),'Retrieved source path must be canonical')
            output_path(self.root,doc['id'],'input/sources/'+path)
            require(path not in merged or merged[path]==text,'Retrieved source conflicts with original export')
            require(sha(text)==entry['source_hash'] and entry.get('provenance'),'Retrieved source hash/provenance missing')
            merged[path]=text
        require(len(merged)<=MAX_SOURCE_FILES and sum(len(t.encode('utf-8')) for t in merged.values())<=MAX_SOURCE_BYTES,'Retrieved closure exceeds source bounds')
        require(all(len(t.encode('utf-8'))<=MAX_SOURCE_FILE_BYTES for t in merged.values()) and sum(source_line_count(t) for t in merged.values())<=MAX_SOURCE_LINES,'Retrieved closure exceeds file/line bounds')

    def freeze_discovered_sources(self,doc,entries):
        if not entries:return
        self._validate_discovered_sources(doc,entries,self.sources(doc))
        fingerprint=sha(encode(entries));relative='analysis/discovery-'+fingerprint+'.json'
        destination=output_path(self.root,doc['id'],relative);data=encode({'files':entries})
        if destination.exists():require(destination.read_bytes()==data,'Discovery evidence collision')
        else:write_new(destination,data)
        self.register(doc,relative);doc['pending_discovery']={'artifact':relative,'hash':fingerprint}
        self.checkpoint(doc)
        self.recover_discovered_sources(doc)

    def requirements_view(self,pid,after=0,path=None,program=None,screen=None,kind=None):
        from .requirements import catalog,verify_snapshot
        with self.lock:
            doc=self.ledger.get(pid);require(doc.get('analysis'),'Analysis is being prepared; refresh when the requirements stage is ready')
            if doc.get('requirements'):verify_snapshot(doc,self.root)
            model=catalog(doc['analysis']);require(path is None or path in {f['path'] for f in model['files']},'Unknown source file');require(type(after) is int and after>=0,'Invalid requirements cursor')
            def memberships(row,key,single):
                values=row.get(key)
                return values if isinstance(values,list) else [row[single]] if row.get(single) else []
            filters={'programs':sorted({v for row in model['items'] for v in memberships(row,'programs','program')}),
                     'screens':sorted({v for row in model['items'] for v in memberships(row,'screens','screen')}),
                     'kinds':sorted({row['kind'] for row in model['items']})}
            for value,key in ((program,'programs'),(screen,'screens'),(kind,'kinds')):
                require(value is None or isinstance(value,str) and value in filters[key],'Unknown requirements '+key+' filter')
            excluded=set((doc.get('requirements') or {}).get('excluded_ids',doc.get('requirements_draft_exclusions',[])))
            rows=[{**r,'selected':r['id'] not in excluded} for r in model['items']
                  if (path is None or r['source_path']==path)
                  and (program is None or program in memberships(r,'programs','program'))
                  and (screen is None or screen in memberships(r,'screens','screen'))
                  and (kind is None or r['kind']==kind)]
            require(after<=len(rows),'Invalid requirements cursor')
            return {'process_id':pid,'status':doc['status'],'catalog_hash':model['hash'],'source_snapshot':model['source_snapshot'],
                'revision':(doc.get('requirements') or {}).get('revision',doc.get('requirements_revision',0)),'files':model['files'],
                'filters':filters,'inventory_total':len(model['items']),'items':rows[after:after+50],'total':len(rows),'next_after':after+len(rows[after:after+50]),'has_more':after+50<len(rows),
                'excluded_ids':sorted(excluded),'editable':not doc['packet_issued'] and doc['status'] in ('WAITING_REQUIREMENTS','WAITING_COPILOT'),
                'markdown':doc.get('requirements_artifact'),'boundary':'Requirements select conversion scope. Default Yes is not SME approval. Every Yes needs verified implementation; every No remains source-accounted.'}

    def save_requirements(self,pid,body):
        from .requirements import catalog,render_markdown,parse_markdown,DRAFT
        from .domain import atomic_bytes
        with self.lock:
            doc=self.ledger.get(pid);self.sources(doc)
            require(isinstance(body,dict) and set(body)=={'catalog_hash','revision','excluded_ids','saved_by'},'Supply catalog hash, revision, excluded IDs and requirements attribution')
            saved=doc.get('requirements')
            if saved and type(body['revision']) is int and body['revision']==saved['revision']-1 and all(body[k]==saved[k] for k in ('catalog_hash','excluded_ids','saved_by')):
                atomic_bytes(output_path(self.root,pid,DRAFT),self.artifact(pid,doc['requirements_artifact']).read_bytes())
                return doc
            require((doc.get('retrieval_request') or {}).get('status')!='IMPORTING','Complete importing retrieval evidence before changing requirements')
            require(pid not in self.active and not doc['packet_issued'] and doc['status'] in ('WAITING_REQUIREMENTS','WAITING_COPILOT'),'Requirements are locked after the single review packet or while a stage is active; use a new process for changed scope')
            current_revision=(doc.get('requirements') or {}).get('revision',doc.get('requirements_revision',0))
            require(type(body['revision']) is int and body['revision']==current_revision,'Requirements changed in another session; reload before saving')
            model=catalog(doc['analysis']);require(body['catalog_hash']==model['hash'],'Source analysis changed; reload requirements before saving')
            selection={'schema_version':1,'process_id':pid,'source_snapshot':model['source_snapshot'],'catalog_hash':model['hash'],
                'revision':current_revision+1,'excluded_ids':body['excluded_ids'],'saved_at':now(),'saved_by':body['saved_by']}
            raw=render_markdown(selection,model).encode();require(len(raw)<=32*1024*1024,'Requirements exceed the Markdown size bound')
            relative='analysis/requirements/'+sha(raw)+'.md';write_new(output_path(self.root,pid,relative),raw);self.register(doc,relative)
            # The exact Markdown bytes are parsed as conversion input and pinned.
            doc['requirements']=parse_markdown(raw,model);doc['requirements_artifact']=relative;doc['requirements_selection']=True
            doc.pop('requirements_draft_exclusions',None);doc.pop('requirements_revision',None)
            doc['analysis']=None;doc['llm']={'status':'NOT_CONFIGURED','live_ready':False}
            doc['copilot_iteration']=doc.get('copilot_iteration',0)+1
            if (doc.get('retrieval_request') or {}).get('status')=='WAITING':doc['retrieval_request']={**doc['retrieval_request'],'status':'STALE'}
            for key in ('copilot_task_artifact','copilot_return_artifact','analysis_artifact'):doc.pop(key,None)
            doc.setdefault('stage_attempts',{})['QUEUED_ANALYSIS']=0
            result=self.ledger.save_event(doc,'QUEUED_ANALYSIS','requirements','Operator requirements saved as Markdown; selected scope queued for conversion',{'revision':selection['revision'],'excluded':len(selection['excluded_ids']),'artifact':relative})
            atomic_bytes(output_path(self.root,pid,DRAFT),raw)
            if result.get('guided_contract_version') or result.get('guide_artifact'):
                from .guide import snapshot
                snapshot(self,result);result=self.ledger.save(result)
            return result

    def agent_task(self,pid):
        with self.lock:
            doc=self.ledger.get(pid);sources=self.sources(doc)
            require(doc.get('copilot_task_artifact'),'Complete object discovery before requesting agent analysis')
            return decode(self.artifact(pid,doc['copilot_task_artifact']).read_bytes())

    def local_agent_view(self, pid):
        from .retrieval import request_prompt,model_request,model_need
        from .copilot import model_requirements
        with self.lock:
            doc=self.ledger.get(pid);self.sources(doc)
            request=None
            if doc.get('retrieval_request'):
                frozen_request=decode(self.artifact(pid,doc['retrieval_request']['artifact']).read_bytes())
                request=model_request(frozen_request)
                request.update(agent_prompt=request_prompt(frozen_request),retrieval_agent='claude',
                               historical_request=frozen_request.get('privacy_contract_version')!=1)
            from .setup import inspect_workstation
            current_setup=inspect_workstation(self.root)['settings']
            retrieval_context={key:current_setup[key] for key in ('zowe_profile','zowe_zosmf_profile','db2_metadata_url')}
            retrieval_context.update(status='CONFIGURATION_ONLY',connectivity_verified=False,
                                     role='Claude approved Db2 MCP and read-only Zowe CLI retrieval')
            task_file=None
            if doc.get('copilot_task_artifact'):
                task=decode(self.artifact(pid,doc['copilot_task_artifact']).read_bytes())
                if (task.get('data_policy') or {}).get('source_identity_mode')=='OPAQUE_HASH_REFERENCES':
                    task_file=str(self.artifact(pid,doc['copilot_task_artifact']))
            return {'process_id':pid,'status':doc['status'],'retrieval_context':retrieval_context,'host_roles':{
                'retrieval':'Claude Code, approved Db2 MCP and read-only Zowe CLI into the request inbox',
                'analysis':'Claude Code, accepted local evidence, development, testing and review'},
                'task_file':task_file,
                'historical_private_task_blocked':bool(doc.get('copilot_task_artifact') and task_file is None),
                'source_directory':str(self.process_root(pid)/'input/sources'),
                'requirements_file':None,
                'requirements':model_requirements(doc),
                'analysis_return_inbox':str(output_path(self.root,pid,'analysis/agent-return-inbox.json')),
                'retrieval':request,'retrieval_state':None if not doc.get('retrieval_request') else
                    {key:value for key,value in doc['retrieval_request'].items() if key in
                     {'id','artifact','status','total_need_count','remaining_need_count','response_artifact'}} |
                    {'missing_item_count':len(doc['retrieval_request'].get('missing_items',[]))},
                'unresolved_retrieval':[{'need':model_need(record['need']),
                    'request_id':record['request_id'],'reason':'Unresolved local evidence; private details remain in the ledger',
                    **({'status':record['status']} if record.get('status') in {'RECEIVED','NOT_FOUND','AMBIGUOUS'} else {})}
                    for record in list(doc.get('retrieval_unresolved',{}).values())[:128]],
                'unresolved_retrieval_count':len(doc.get('retrieval_unresolved',{})),
                'message':'Claude retrieves named evidence through approved read-only connections into the exact inbox. Continue validates and freezes its return before local analysis, coding, testing and review. Requirements Save and the one actual SME return remain human gates.'}

    @staticmethod
    def _retrieval_need_key(need):
        return sha(encode({k:need.get(k) for k in ('kind','name','source','relationship')}))

    def request_retrieval(self, pid, needs=None):
        from .retrieval import build_request,write_request,validate_binding,MAX_NEEDS
        with self.lock:
            doc=self.ledger.get(pid);self.sources(doc)
            require(not doc['packet_issued'] and pid not in self.active and doc['status'] in ('WAITING_DISCOVERY','WAITING_COPILOT','WAITING_REQUIREMENTS'),
                    'Request missing evidence only at a pre-review checkpoint')
            existing=doc.get('retrieval_request')
            if existing and existing.get('status') in ('WAITING','IMPORTING'):
                require(needs is None,'Finish the outstanding retrieval before replacing it')
                if existing['status']=='WAITING':validate_binding(decode(self.artifact(pid,existing['artifact']).read_bytes()),doc)
                return self.local_agent_view(pid)
            total=None
            if needs is None:
                fields=('kind','name','reason','source','relationship','status')
                gaps=doc.get('lineage',{}).get('closure',{}).get('gaps',[])
                candidates=[{k:g[k] for k in fields if k in g} for g in gaps]
                candidates.extend(v['need'] for v in doc.get('retrieval_unresolved',{}).values())
                unique={self._retrieval_need_key(n):n for n in candidates}
                total=len(unique);needs=list(unique.values())[:MAX_NEEDS]
            request=build_request(doc,needs);relative=write_request(self.root,request)
            self.register(doc,relative)
            doc['retrieval_request']={'id':request['request_id'],'artifact':relative,'status':'WAITING',
                'total_need_count':total if total is not None else len(request['needs']),
                'remaining_need_count':max(0,(total or len(request['needs']))-len(request['needs']))}
            unresolved=doc.setdefault('retrieval_unresolved',{})
            for need in request['needs']:
                unresolved[self._retrieval_need_key(need)]={'need':{k:v for k,v in need.items() if k!='need_id'},
                    'request_id':request['request_id'],'reason':'Awaiting requested local evidence'}
            self.ledger.save_event(doc,None,'retrieval','Claude retrieval request prepared; Continue validates the exact returned evidence',{'request_id':request['request_id']})
            if doc.get('guided_contract_version') or doc.get('guide_artifact'):
                from .guide import snapshot
                snapshot(self,doc);self.ledger.save(doc)
            return self.local_agent_view(pid)

    def continue_retrieval(self, pid):
        from .retrieval import inspect_response,validate_binding
        with self.lock:
            doc=self.ledger.get(pid);existing=self.sources(doc);record=doc.get('retrieval_request')
            require(not doc['packet_issued'] and pid not in self.active and doc['status'] in ('WAITING_DISCOVERY','WAITING_COPILOT','WAITING_REQUIREMENTS'),
                    'Continue retrieval only at a pre-review checkpoint')
            require(record and record['status'] in ('WAITING','IMPORTING'),'No outstanding retrieval request')
            request=decode(self.artifact(pid,record['artifact']).read_bytes())
            if record['status']=='WAITING':
                validate_binding(request,doc)
                result=inspect_response(self.root,request,doc['source_files'])
                if result['status']=='WAITING_FOR_RESPONSE':return self.local_agent_view(pid)
                self._validate_discovered_sources(doc,result['entries'],existing)
                relative='analysis/retrieval/'+request['request_id']+'/accepted-'+result['response_hash']+'.json'
                data=encode(result);destination=output_path(self.root,pid,relative)
                if destination.exists():require(destination.read_bytes()==data,'Retrieval response changed after acceptance')
                else:write_new(destination,data)
                self.register(doc,relative)
                record={**record,'status':'IMPORTING','response_artifact':relative,'missing_items':result['missing_items']}
                doc['retrieval_request']=record
                self.ledger.save(doc)
            else:
                # Resume only the ledger-pinned acceptance, even if staging changes.
                result=decode(self.artifact(pid,record['response_artifact']).read_bytes())
            self.freeze_discovered_sources(doc,result['entries'])
            doc=self.ledger.get(pid)
            unresolved=doc.setdefault('retrieval_unresolved',{})
            needs={n['need_id']:n for n in request['needs']}
            for item in result['items']:
                need=needs[item['need_id']];key=self._retrieval_need_key(need)
                if item['status']=='FOUND':unresolved[key]={'need':{k:v for k,v in need.items() if k!='need_id'},
                    'request_id':request['request_id'],'status':'RECEIVED','path':item['path'],'source_hash':item['sha256'],
                    'reason':'Retrieved bytes require matching object type, identity and source evidence'}
                else:unresolved[key]={'need':{k:v for k,v in need.items() if k!='need_id'},
                    'request_id':request['request_id'],'reason':item['reason'],'status':item['status']}
            doc['retrieval_request']={**record,'status':'CONSUMED'}
            doc['analysis']=None;doc['llm']={'status':'NOT_CONFIGURED','live_ready':False}
            doc['copilot_iteration']=doc.get('copilot_iteration',0)+1
            for key in ('lineage','lineage_artifact','lineage_scope','copilot_task_artifact','copilot_return_artifact','analysis_artifact'):doc.pop(key,None)
            doc.setdefault('stage_attempts',{})['QUEUED_ANALYSIS']=0
            self.ledger.save_event(doc,'QUEUED_ANALYSIS','retrieval','Returned files frozen; reassessing local lineage and preserving unresolved retrieval results',{'request_id':request['request_id'],'accepted_files':len(result['entries']),'missing_items':len(result['missing_items'])})
        self.advance(pid)
        # Partial/unsuccessful retrieval is a visible checkpoint, not an automatic prompt loop.
        if self.ledger.get(pid)['status']=='WAITING_DISCOVERY' and not self.ledger.get(pid).get('retrieval_unresolved') and result['complete'] and result['entries']:
            return self.request_retrieval(pid)
        return self.local_agent_view(pid)

    def local_agent_action(self, pid, action, payload):
        from .local_agent import ACTIONS
        require(isinstance(action,str) and action in ACTIONS and isinstance(payload,dict),'Invalid local agent action')
        expected={'analysis'} if action=='analysis' else {'receipt'} if action=='measurement' else set()
        require(set(payload)==expected or action=='request' and set(payload)<={'needs'},'Unexpected local agent payload')
        if action=='measurement':require(isinstance(payload['receipt'],dict) and payload['receipt'].get('process_id') in (pid,None),'Receipt must belong to this process or explicitly to the workspace')
        migrated=False
        with self.lock:
            doc=self.ledger.get(pid);self.sources(doc)
            require(pid not in self.active,'Wait for the current Coordinator stage to reach a checkpoint')
            if action=='measurement':return self.record_measurement(payload['receipt'])
            if action=='request' and 'needs' in payload:
                from .retrieval import build_request
                require(isinstance(payload['needs'],list),'Retrieval needs must be an array')
                build_request(doc,payload['needs'])  # Validate nested input before changing host/task state.
            if action=='analysis':
                require(doc.get('agent_transport')=='local_files','Inspect this process with runner agent first, then return its fresh local analysis task')
            if doc.get('agent_transport')!='local_files' and not doc['packet_issued']:

                require(doc['status'] in ('READY','WAITING_DISCOVERY','WAITING_REQUIREMENTS','WAITING_COPILOT'),'Enable local-file analysis at a stable checkpoint')
                doc['agent_transport']='local_files';doc['assistant_mode']='copilot_chat';doc['development_contract_version']=2
                if doc.get('development_handoff'):doc['historical_development_handoff']=doc.pop('development_handoff')
                self.ledger.save_event(doc,None,'agent','Claude workflow selected for approved retrieval and local analysis; prior handoff evidence preserved')
                if doc['status']=='WAITING_COPILOT':self.refresh_analysis(pid);migrated=True
        if migrated:self.advance(pid)
        if action=='request':return self.request_retrieval(pid,payload.get('needs'))
        if action=='refresh' and not migrated:self.refresh_analysis(pid)
        if action=='analysis':
            current=self.ledger.get(pid)
            if current['status']!='WAITING_COPILOT':
                require((current.get('llm') or {}).get('provenance',{}).get('returned_analysis_hash')==sha(encode(payload['analysis'])),'Process is not awaiting this analysis')
            else:self.submit_agent_analysis(pid,payload['analysis'])
        if action=='continue':
            current=self.ledger.get(pid)
            if (current.get('retrieval_request') or {}).get('status') in ('WAITING','IMPORTING'):return self.continue_retrieval(pid)
            inbox=output_path(self.root,pid,'analysis/agent-return-inbox.json')
            if current['status']=='WAITING_COPILOT' and inbox.exists():
                require(inbox.is_file() and inbox.stat().st_size<=128000,'Local analysis return exceeds bound')
                self.submit_agent_analysis(pid,decode(inbox.read_bytes(),128000))
        current=self.ledger.get(pid)
        if current['status'] in ('QUEUED_ANALYSIS','QUEUED_VERIFY','QUEUED_REPORT'):self.advance(pid)
        current=self.ledger.get(pid)
        if current['status']=='WAITING_DISCOVERY' and (current.get('retrieval_request') or {}).get('status') in (None,'STALE'):
            return self.request_retrieval(pid)
        return self.local_agent_view(pid)

    def _current_development(self, doc, task):
        handoff = doc.get('development_handoff')
        return bool(handoff and handoff['task_hash'] == task['task_hash'])

    def prepare_development(self, pid):
        from .development import build_packet
        with self.lock:
            doc = self.ledger.get(pid)
            require(doc.get('agent_transport')!='local_files','Claude uses local files without a development MCP handoff')
            require(doc['status'] == 'WAITING_COPILOT' and not doc['packet_issued'],
                    'Complete discovery and requirements before preparing development')
            task = self.agent_task(pid)
            if self._current_development(doc, task): return self.development_view(pid)
            require(adapter_fingerprint() == self.adapter_fingerprint == doc.get('analysis_adapter_fingerprint'),
                    'Restart the existing service if code changed, then refresh analysis before preparing development')
            packet = build_packet(task, (doc.get('analysis') or {}).get('blockers', []), self.adapter_fingerprint)
            raw = encode(packet); relative = 'analysis/development-handoff-' + packet['handoff_id'] + '.json'
            destination = output_path(self.root, pid, relative)
            if destination.exists(): require(destination.read_bytes() == raw, 'Development handoff evidence differs')
            else: write_new(destination, raw)
            self.register(doc, relative)
            doc['development_handoff'] = {'id': packet['handoff_id'], 'task_hash': task['task_hash'],
                                          'artifact': relative, 'return_artifact': None}
            self.ledger.save_development_handoff(doc, packet['handoff_id'])
            return self.development_view(pid)

    def revise_development(self, pid, reason, handoff_id):
        from .development import build_packet, REVISION_REASONS
        with self.lock:
            require(isinstance(reason, str) and reason in REVISION_REASONS, 'Choose a development revision reason')
            doc = self.ledger.get(pid); view = self.development_view(pid)
            require(view['status'] in ('READY', 'RETURNED_FOR_REVIEW') and not doc['packet_issued'],
                    'Only a current development handoff can be revised')
            previous = view['packet']; task = self.agent_task(pid)
            prior_revision = previous.get('revision') or {}
            if prior_revision.get('previous_handoff_id') == handoff_id and prior_revision.get('reason') == reason:
                return view  # Retry of the already committed revision.
            require(previous['handoff_id'] == handoff_id, 'Development handoff changed; reload before revising')
            revision = {'number': (previous.get('revision') or {}).get('number', 0) + 1,
                        'previous_handoff_id': previous['handoff_id'], 'reason': reason}
            # Retain the analysis baseline while reworking a rejected patch; no code is credited.
            packet = build_packet(task, (doc.get('analysis') or {}).get('blockers', []),
                                  previous['binding']['adapter_fingerprint'], revision)
            raw = encode(packet); relative = 'analysis/development-handoff-' + packet['handoff_id'] + '.json'
            destination = output_path(self.root, pid, relative)
            if destination.exists(): require(destination.read_bytes() == raw, 'Development revision evidence differs')
            else: write_new(destination, raw)
            self.register(doc, relative)
            doc['development_handoff'] = {'id': packet['handoff_id'], 'task_hash': task['task_hash'],
                                          'artifact': relative, 'return_artifact': None}
            self.ledger.save_development_handoff(doc, packet['handoff_id'])
            return self.development_view(pid)

    def development_view(self, pid):
        with self.lock:
            doc = self.ledger.get(pid); record = doc.get('development_handoff')
            empty = {'packet': None, 'result': None}
            if not record:
                return {**empty, 'status': 'NOT_PREPARED', 'next_action': 'Copilot inspects source, then prepares standalone development when needed.'}
            if doc['status'] != 'WAITING_COPILOT' or not doc.get('copilot_task_artifact'):
                return {**empty, 'status': 'STALE', 'next_action': 'The previous handoff is preserved. Retrieve the current Copilot task after analysis.'}
            task = self.agent_task(pid)
            if not self._current_development(doc, task):
                return {**empty, 'status': 'STALE', 'next_action': 'Previous handoff is stale. Copilot uses the refreshed task or prepares a new development handoff.'}
            packet = decode(self.artifact(pid, record['artifact']).read_bytes())
            require(packet['handoff_id'] == record['id'] and
                    packet['handoff_id'] == sha(encode({k:v for k,v in packet.items() if k != 'handoff_id'})),
                    'Development handoff integrity differs')
            result = decode(self.artifact(pid, record['return_artifact']).read_bytes()) if record.get('return_artifact') else None
            return {'status': 'RETURNED_FOR_REVIEW' if result else 'READY', 'packet': packet, 'result': result,
                    'next_action': 'Copilot reviews and integrates the returned patch, verifies it, restarts the existing service if code changed and refreshes analysis.' if result else 'Standalone Claude implements the source-free work items and returns evidence or unresolved obligations.'}

    def _development_by_id(self, handoff_id):
        from .development import valid_hash
        require(valid_hash(handoff_id), 'Development handoff is unavailable or stale')
        pid = self.ledger.development_owner(handoff_id)
        view = self.development_view(pid)
        require(view['packet'] and view['packet']['handoff_id'] == handoff_id, 'Development handoff is unavailable or stale')
        return pid, view

    def development_task(self, handoff_id):
        with self.lock:
            try:
                _, view = self._development_by_id(handoff_id)
                return {'status': view['status'], 'packet': view['packet'],
                        'return_hash': view['result']['submission_hash'] if view['result'] else None}
            except (ValidationError, OSError, KeyError) as exc:
                # Developer consumers must not receive operational integrity paths/names.
                raise ValidationError('Development handoff is unavailable or stale; ask Copilot to check the operational workspace') from exc

    def submit_development(self, handoff_id, submitted):
        from .development import validate_return
        with self.lock:
            try: pid, view = self._development_by_id(handoff_id)
            except (ValidationError, OSError, KeyError) as exc:
                raise ValidationError('Development handoff is unavailable or stale; ask Copilot to check the operational workspace') from exc
            result = validate_return(view['packet'], submitted)
            if view['result']:
                require(view['result'] == result, 'Development return conflicts with the immutable recorded return')
                return self.development_task(handoff_id)
            doc = self.ledger.get(pid)
            data = encode(result); relative = 'analysis/development-return-' + sha(data) + '.json'
            destination = output_path(self.root, pid, relative)
            if destination.exists(): require(destination.read_bytes() == data, 'Development return evidence differs')
            else: write_new(destination, data)
            self.register(doc, relative); doc['development_handoff']['return_artifact'] = relative
            self.ledger.save_event(doc, None, 'development', 'Standalone development return recorded as unverified; Copilot integration and refresh required',
                                   {'handoff_id': handoff_id, 'return_hash': result['submission_hash']})
            return self.development_task(handoff_id)

    def submit_agent_analysis(self,pid,submitted):
        from .copilot import validate_submission
        with self.lock:
            doc=self.ledger.get(pid);require(doc['status']=='WAITING_COPILOT','Process is not waiting for agent analysis')
            require(not doc.get('retrieval_unresolved') and (doc.get('retrieval_request') or {}).get('status') not in ('WAITING','IMPORTING'),'Finish outstanding retrieval before submitting analysis')
            task=self.agent_task(pid)
            require(not self._current_development(doc,task),'Development handoff requires a return, integration review and refresh before final analysis')
            if doc.get('development_contract_version'):
                require(adapter_fingerprint()==self.adapter_fingerprint==doc.get('analysis_adapter_fingerprint'),'Adapter code changed; restart the existing service and refresh analysis before final analysis')
            result=validate_submission(task,submitted,doc.get('analysis'),doc['source_files'])
            data=encode(result);relative='analysis/copilot-return-'+sha(data)+'.json'
            write_new(output_path(self.root,pid,relative),data);self.register(doc,relative)
            doc['llm']=result;doc['copilot_return_artifact']=relative
            return self.ledger.save_event(doc,'QUEUED_ANALYSIS','agent','Agent analysis accepted as review context; no conversion gaps cleared')

    def refresh_analysis(self,pid):
        """Reassess actual adapter changes before the sole SME packet is issued."""
        with self.lock:
            doc=self.ledger.get(pid);self.sources(doc)
            require((doc.get('retrieval_request') or {}).get('status') not in ('WAITING','IMPORTING'),'Finish outstanding retrieval before refreshing analysis')
            require(doc['status']=='WAITING_COPILOT' and not doc['packet_issued'],'Adapter reassessment is permitted only before the single SME packet')
            if doc.get('development_handoff') and doc.get('copilot_task_artifact'):
                view=self.development_view(pid)
                if view['status'] in ('READY','RETURNED_FOR_REVIEW'):
                    require(view['result'] is not None,'Record a development return, including unresolved work, before refresh')
                    from .development import check_integrated_changes
                    check_integrated_changes(view['result'])
            if doc.get('sme_packet_version',1)>=4 or doc.get('development_handoff'):
                require(adapter_fingerprint()==self.adapter_fingerprint,'Adapter code changed on disk. Restart the workbench service through its existing launcher, then refresh through the same workspace; never run a second writer.')
                doc['previous_analysis_hash']=sha(encode(doc.get('analysis')))
            doc['analysis']=None;doc['llm']={'status':'NOT_CONFIGURED','live_ready':False}
            doc['copilot_iteration']=doc.get('copilot_iteration',0)+1
            for key in ('copilot_task_artifact','copilot_return_artifact','analysis_artifact'):doc.pop(key,None)
            doc.setdefault('stage_attempts',{})['QUEUED_ANALYSIS']=0
            return self.ledger.save_event(doc,'QUEUED_ANALYSIS','adapters','Reassessing actual adapter code; previous tasks/evidence preserved and SME quota unchanged')

    def begin_work(self,document):
        from .economics import fields, STAGES, text
        fields(document,('id','process_id','actor','stage'))
        require(isinstance(document['id'],str) and __import__('re').fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,99}',document['id']),'Invalid work session ID')
        text(document['actor'],'actor');require(isinstance(document['stage'],str) and document['stage'] in STAGES and document['stage']!='pilot_total','Invalid work stage')
        with self.lock:
            if document['process_id'] is not None:self.ledger.get(document['process_id'])
            require((document['process_id'] is None)==(document['stage']=='framework'),'Framework sessions are workspace-wide; other work requires a process')
            sessions=self.ledger.work_sessions();existing=next((r for r in sessions if r['id']==document['id']),None)
            if existing:
                require(existing['document']==document,'Work session identity conflicts')
                return existing
            require(not any(r['document']['actor']==document['actor'] and not r['receipt_id'] for r in sessions),'Actor already has an open work session; account for it before starting another')
            self.ledger.open_work_session(document);self.work_clocks[document['id']]=time.monotonic()
            return next(r for r in self.ledger.work_sessions() if r['id']==document['id'])

    def end_work(self,session_id,abandon=False):
        from .economics import number
        from decimal import Decimal
        with self.lock:
            session=next((r for r in self.ledger.work_sessions() if r['id']==session_id),None)
            require(session is not None,'Work session not found')
            if session['receipt_id']:return session
            if abandon:
                self.ledger.close_work_session(session_id,'UNMEASURED');self.work_clocks.pop(session_id,None)
                return {'id':session_id,'state':'UNMEASURED','hours':None}
            prior=next((r for r in self.ledger.measurements() if r['id']=='session-'+session_id),None)
            if prior:
                require(prior['document'].get('recorded_by')=='workbench work-session clock','Work clock receipt identity conflicts')
                self.ledger.close_work_session(session_id,prior['id']);self.work_clocks.pop(session_id,None)
                return {'id':prior['id'],'sha256':prior['fingerprint'],'path':prior['path'],'recorded':True}
            # A lost clock after restart is not permission to count downtime as work.
            require(session_id in self.work_clocks,'Session clock was lost on restart; abandon as unmeasured, then import actual work evidence if available')
            doc=session['document'];hours=str(Decimal(str(time.monotonic()-self.work_clocks[session_id]))/3600)
            receipt={'id':'session-'+session_id,'kind':'work','process_id':doc['process_id'],'actor':doc['actor'],
                     'stage':doc['stage'],'hours':hours,'started_at':session['started'],'ended_at':now(),
                     'evidence':'Observed agent work-session window; stop before human waits. Includes thinking and tool execution, not an attendance attestation.',
                     'recorded_by':'workbench work-session clock'}
            result=self.record_measurement(receipt,observed=True)
            self.ledger.close_work_session(session_id,receipt['id']);self.work_clocks.pop(session_id,None)
            return result

    def record_measurement(self,record,observed=False):
        from .economics import validate_receipt
        validate_receipt(record,observed=observed)
        require(observed or not record['id'].startswith(('session-','provider-')),'Receipt ID prefix is reserved for observed clocks and calls')
        raw=encode(record);require(len(raw)<=65536,'Measurement exceeds 64 KiB')
        if record['kind']=='usage' and record['provider']=='configured_api':require(not {'input_tokens','output_tokens','cached_input_tokens'}.intersection(record['quantities']),'Configured API token counters are already observed; import only actual credits')
        fingerprint=sha(raw);pid=record['process_id'];relative=None
        with self.lock:
            if pid is not None:self.ledger.get(pid)
            if record['kind']=='plan':self.economics(plan=record['plan'])
            rows=self.ledger.measurements();by_id={r['id']:r for r in rows}
            if record['id'] in by_id:
                require(by_id[record['id']]['fingerprint']==fingerprint,'Measurement ID already belongs to different evidence')
            if record.get('supersedes'):
                previous=by_id.get(record['supersedes'])
                require(previous is not None and previous['process_id']==pid and previous['document']['kind']==record['kind'], 'Correction must supersede the same kind and scope')
                if record['kind'] in ('usage','budget'):require(all(record.get(k)==previous['document'].get(k) for k in ('provider','account','unit')),'Billing correction must retain provider/account/unit')
                require(not any(r['document'].get('supersedes')==record['supersedes'] and r['id']!=record['id'] for r in rows),'Receipt already superseded')
                require(record['supersedes']!=record['id'],'Receipt cannot supersede itself')
            if pid is not None:
                relative='analysis/measurements/'+fingerprint+'.json';path=output_path(self.root,pid,relative)
                if path.exists():require(path.read_bytes()==raw,'Measurement evidence changed')
                else:write_new(path,raw)
            self.ledger.append_measurement(record,fingerprint,relative)
        return {'id':record['id'],'sha256':fingerprint,'path':relative,'recorded':True}

    def economics(self,pid=None,plan=None):
        from .economics import economics_view
        with self.lock:return economics_view(self.ledger,pid,plan)

    def observed_analysis(self,doc,excerpts):
        from uuid import uuid4
        # Preserve real charges even when structured suggestions fail validation.
        with self.provider_lock:
            before=self.provider.usage_summary();started=now()
            try:return self.provider.analyze(excerpts,doc.get('prompt') or 'Review this process and identify assumptions for its one SME checklist.')
            finally:
                after=self.provider.usage_summary()
                counters={key:after[key]-before[key] for key in before if type(before[key]) is int}
                if counters.get('requests') or counters.get('cache_hits'):
                    self.record_measurement({'id':'provider-'+uuid4().hex,'kind':'provider_call','process_id':doc['id'],
                        'provider':'configured_api','account':'configured_endpoint:'+sha(self.provider.url)[:16], 'model':self.provider.model,
                        'started_at':started,'ended_at':now(),'counters':counters,'recorded_by':'workbench',
                        'evidence':'Observed structured provider counters for this call; endpoint and credentials omitted.'},observed=True)

    def advance(self,pid):
        with self.lock:
            require_layout(self.root)
            doc=self.ledger.get(pid);stage=doc['status']
            if pid in self.active or stage not in ('QUEUED_ANALYSIS','QUEUED_VERIFY','QUEUED_REPORT') or doc.get('next_retry_at',0)>time.time():return doc
            if doc.get('factory_contract_version'):
                from .factory import consistency_findings
                findings=consistency_findings(doc)
                if findings:
                    doc['factory_findings']=findings;doc['resume_status']=stage
                    doc['blockers'].append({'kind':'factory_consistency','message':'Factory invariant failed; inspect factory_findings'})
                    return self.ledger.save_event(doc,'REPORTING_FAILED' if stage=='QUEUED_REPORT' else 'FAILED','consistency','Factory transition blocked',{'findings':findings})
            self.active.add(pid);doc['_active_stage']=stage
            doc.setdefault('stage_attempts',{})[stage]=doc.get('stage_attempts',{}).get(stage,0)+1
            self.ledger.save(doc,{'QUEUED_ANALYSIS':'ANALYZING','QUEUED_VERIFY':'VERIFYING','QUEUED_REPORT':'REPORTING'}[stage])
        timing_id=self.ledger.start_timing(pid,stage);timing_started=time.monotonic();timing_outcome='interrupted'
        try:
            {'QUEUED_ANALYSIS':self.analyze,'QUEUED_VERIFY':self.verify,'QUEUED_REPORT':self.report}[stage](doc)
            timing_outcome='returned'
        except StageInterrupted:pass
        except Exception as exc:
            timing_outcome='failed'
            with self.lock:
                current=self.ledger.get(pid)
                if current['status']=='PAUSED' or (current.get('cancel_requested') and stage!='QUEUED_REPORT') or self.closed:
                    try:self.checkpoint(doc)
                    except StageInterrupted:return self.ledger.get(pid)
                else:
                    if stage=='QUEUED_REPORT':doc['report_verified']=False
                    doc['last_error']=type(exc).__name__;doc['last_failure']={'stage':stage,'attempt':doc['stage_attempts'][stage],'type':type(exc).__name__,'message':str(exc)[:1000],'recorded':now()};doc['resume_status']=stage
                    transient=isinstance(exc,(OSError,TimeoutError,sqlite3.OperationalError)) and not isinstance(exc,(FileNotFoundError,PermissionError))
                    retry=transient and doc['stage_attempts'][stage]<3
                    doc['blockers']=[b for b in doc['blockers'] if not (b['kind']=='stage_failure' and b.get('stage')==stage)]
                    doc['blockers'].append({'kind':'stage_failure','stage':stage,'message':'Stage failed; successful recovery is required before completion','failure':doc['last_failure']})
                    doc['next_retry_at']=time.time()+.1*doc['stage_attempts'][stage] if retry else 0
                    self.ledger.save(doc,stage if retry else 'REPORTING_FAILED' if stage=='QUEUED_REPORT' else 'FAILED')
                    self.ledger.event(pid,'error','Transient stage retry queued' if retry else 'Stage failed safely; evidence retained',doc['last_failure'])
            raise
        finally:
            with self.lock:
                self.ledger.finish_timing(timing_id,time.monotonic()-timing_started,timing_outcome)
                self.active.discard(pid)
                if not self.closed and self.ledger is not None:
                    current=self.ledger.get(pid)
                    if current.get('guided_contract_version') or current.get('guide_artifact'):
                        # Issue only the initial discovery request automatically;
                        # NOT_FOUND and ambiguous returns require a new explicit request.
                        if current['status']=='WAITING_DISCOVERY' and not current.get('retrieval_request'):
                            self.request_retrieval(pid);current=self.ledger.get(pid)
                        from .guide import snapshot
                        snapshot(self,current);self.ledger.save(current)
                if self.closed and (not self.worker or not self.worker.is_alive()):self._release()
        return self.ledger.get(pid) if self.ledger is not None else doc

    def analyze(self,doc):
        pid=doc['id'];self.checkpoint(doc,'ANALYZING');self.ledger.event(pid,'lineage','Indexing the retained export and resolving the selected job dependency closure before conversion')
        source_files=self.sources(doc)
        from .lineage import map_lineage
        from .connectors import ReadOnlyLineageResolver
        strict=doc.get('assistant_mode')=='copilot_chat'
        if not doc.get('lineage') or (strict and not doc['lineage']['closure']['complete']):
            lineage=map_lineage(source_files,doc,doc.get('mainframe_knowledge'),resolver=ReadOnlyLineageResolver.from_environment(workspace=self.root) if strict and doc.get('agent_transport')!='local_files' else None)
            self.freeze_discovered_sources(doc,lineage.get('source_snapshots',[]))
            source_files=self.sources(doc)
            # Fetched text is retained in immutable source snapshots and journal,
            # not repeatedly copied into polling/status documents.
            lineage={k:v for k,v in lineage.items() if k!='source_snapshots'}
            data=encode(lineage);relative='analysis/lineage-'+sha(data)+'.json';path=output_path(self.root,pid,relative)
            if path.exists():require(path.read_bytes()==data,'Lineage recovery differs from frozen evidence')
            else:write_new(path,data)
            self.register(doc,relative);doc['lineage']=lineage;doc['lineage_artifact']=relative
        if doc.get('retrieval_unresolved'):
            from .retrieval import unresolved_after_mapping
            doc['retrieval_unresolved']=unresolved_after_mapping(doc,doc['lineage'])
        if strict and (not doc['lineage']['closure']['complete'] or doc.get('retrieval_unresolved')):
            doc['blockers']=[{'kind':'lineage_unresolved','message':g.get('reason',g.get('message','Missing or ambiguous dependency')),'object':g} for g in doc['lineage']['closure']['gaps']]
            doc['blockers'].extend({'kind':'retrieval_unresolved','message':v['reason'],'object':v['need'],'request_id':v['request_id']} for v in doc.get('retrieval_unresolved',{}).values())
            self.stage_success(doc,'QUEUED_ANALYSIS');self.checkpoint(doc,'WAITING_DISCOVERY')
            self.ledger.event(pid,'lineage','Discovery is incomplete; no conversion or SME packet has started',{'gaps':len(doc['blockers'])})
            return
        if strict:doc['lineage_scope']=doc['lineage']['scope']['selected_files']
        if doc.get('guided_contract_version'):doc['source_intake_pending']=False
        self.ledger.event(pid,'analysis','Extracting atomic source logic within the discovered job scope; unsupported semantics remain explicit adapter obligations')
        analysis=doc.get('analysis')
        if analysis is None:
            # Reassess the current adapter catalog before applying saved selections.
            # Changed granularity needs a fresh operator Save, never silent defaults.
            analysis=analyze_sources(source_files,{k:v for k,v in doc.items() if k!='requirements'})
            if doc.get('requirements'):
                from .requirements import catalog,project
                model=catalog(analysis);saved=doc['requirements']
                if model['hash']!=saved['catalog_hash']:
                    doc['requirements_revision']=saved['revision']
                    doc['requirements_draft_exclusions']=sorted(set(saved['excluded_ids']) & {r['id'] for r in model['items']})
                    doc.pop('requirements');doc['requirements_selection']=True
                    self.ledger.event(pid,'requirements','Adapter source breakdown changed; review retained choices and explicitly save a new scope revision. Previous Markdown evidence is preserved.')
                else:analysis=project(analysis,saved,doc.get('jobs',[]))
        self.checkpoint(doc);doc['analysis']=analysis;doc['blockers']=list(analysis['blockers'])
        if doc.get('requirements_selection') and not doc.get('requirements'):
            self.stage_success(doc,'QUEUED_ANALYSIS');self.checkpoint(doc,'WAITING_REQUIREMENTS')
            self.ledger.event(pid,'requirements','Mainframe breakdown ready; all choices default to Yes. Save actual requirements before conversion.')
            return
        context_path=self.root/'knowledge'/'inbox'/'context.md'
        if doc.get('process_context',{}).get('documents') and 'knowledge_context' not in doc:
            doc['knowledge_context']={'status':'UNVERIFIED_INPUT','artifact':'analysis/process-context.json', 'sha256':sha(encode(doc['process_context'])), 'documents':[{k:v for k,v in d.items() if k!='text'} for d in doc['process_context']['documents']]}
        if context_path.exists() and 'knowledge_context' not in doc and 'process_context' not in doc:
            require(not path_is_link(context_path) and context_path.stat().st_size<=16000,'Knowledge context must be a regular Markdown file of at most 16 KB')
            doc['knowledge_context']={'text':context_path.read_bytes().decode('utf-8'),'sha256':sha(context_path.read_bytes()),'status':'UNVERIFIED_INPUT'}
        from .connectors import read_only_discovery
        if 'discovery' not in doc:doc['discovery']={'status':'CLAUDE_APPROVED_RETRIEVAL_REQUIRED','operations':[]} if doc.get('agent_transport')=='local_files' else read_only_discovery()
        doc.setdefault('llm',{'status':'NOT_CONFIGURED','live_ready':False})
        if strict and doc['llm']['status']!='AGENT_ANALYSIS_RETURNED':
            analysis_bytes=encode(analysis);analysis_relative='analysis/source-analysis-'+sha(analysis_bytes)+'.json'
            frozen=output_path(self.root,pid,analysis_relative)
            if frozen.exists():require(frozen.read_bytes()==analysis_bytes,'Analysis differs from frozen agent evidence')
            else:write_new(frozen,analysis_bytes)
            self.register(doc,analysis_relative);doc['analysis_artifact']=analysis_relative
            from .copilot import build_task, unknown_usage
            doc['analysis_adapter_fingerprint']=self.adapter_fingerprint
            task=build_task(doc,source_files,analysis);data=encode(task);relative='analysis/copilot-task-'+sha(data)+'.json'
            destination=output_path(self.root,pid,relative)
            if destination.exists():require(destination.read_bytes()==data,'Agent task recovery differs')
            else:write_new(destination,data)
            self.register(doc,relative);doc['copilot_task_artifact']=relative
            doc['llm']={'status':'WAITING_COPILOT','live_ready':False,'usage':task.get('usage',unknown_usage())}
            self.stage_success(doc,'QUEUED_ANALYSIS');self.checkpoint(doc,'WAITING_COPILOT')
            self.ledger.event(pid,'agent','Frozen metadata task ready for Claude Code; approved retrieval and private local verification remain gated' if doc.get('agent_transport')=='local_files' else 'Frozen task ready for external agent analysis')
            return
        if self.provider and not strict and doc['llm']['status']=='NOT_CONFIGURED':
            try:
                context=''
                if doc.get('mainframe_knowledge'):
                    facts={'status':'UNVERIFIED_CONTEXT_NOT_CONVERSION_PROOF',
                           'classifications':{path:record['kind'] for path,record in analysis.get('classifications',{}).items()},
                           'utility_findings':analysis.get('utility_findings',[]),
                           'application':doc['mainframe_knowledge']['application']}
                    context='Frozen mainframe context (bounded excerpt; full facts are in the SME packet):\n'+json.dumps(facts,ensure_ascii=False)[:4000]+'\nSource excerpts:\n'
                excerpts=(context+'\n'.join(p['source_text'] for p in analysis['programs'].values())+'\nUnverified background knowledge:\n'+doc.get('knowledge_context',{}).get('text',''))[:16000]
                doc['llm']={'status':'ANALYSIS_RETURNED',**self.observed_analysis(doc,excerpts)}
            except ValidationError as exc:
                doc['llm']={'status':'UNAVAILABLE','message':str(exc),'live_ready':False}
                doc['blockers'].append({'kind':'llm_unavailable','message':str(exc)})
        self.checkpoint(doc)
        self.ledger.register_assets(pid,analysis['assets'])
        root=self.process_root(pid)
        analysis_path=root/'analysis'/'source-analysis.json'
        if analysis_path.exists():require(analysis_path.read_bytes()==encode(analysis),'Analysis recovery disagrees with frozen evidence')
        else:write_new(analysis_path,encode(analysis))
        self.register(doc,'analysis/source-analysis.json')
        doc['program_versions']={}
        for name,program in analysis['programs'].items():
            self.checkpoint(doc)
            if program['blockers']:continue
            code=get_backend(doc.get('target_backend',{}).get('name','python-sqlite')).generate(program);check_generated(code)
            version=sha(code);doc['program_versions'][name]=version
            path=self.root/'shared'/'target'/'python'/(version+'.py')
            if not path.exists():write_new(path,code.encode())
            require(path.read_text(encoding='utf-8')==code,'Shared target version integrity failed')
        if self.ledger.get(pid)['packet_issued']:
            packet=decode((root/'review'/'packet.json').read_bytes())
            require(packet.get('packet_hash')==self.ledger.get(pid)['packet_hash'] and sha(encode({k:v for k,v in packet.items() if k!='packet_hash'}))==packet['packet_hash'],'Issued packet integrity failed')
            require(packet['source_snapshot']==analysis['source_snapshot'] and packet['process_id']==pid,'Issued packet does not belong to the frozen process')
        else:packet=export_packet(doc,root/'review')
        for file in ['packet.json','sme-checklist.xlsx','sme-checklist.docx','sme-checklist.html']:self.register(doc,'review/'+file)
        self.checkpoint(doc,'ANALYZING')
        with self.lock:
            self.checkpoint(doc)
            if not self.ledger.get(pid)['packet_issued']:self.ledger.issue_packet(pid,packet['packet_hash'])
            else:require(self.ledger.get(pid)['packet_hash']==packet['packet_hash'],'Recovered packet differs from issued quota')
        self.ledger.event(pid,'review','The single comprehensive checklist is ready for download',{'rules':len(analysis['rules']),'blockers':len(analysis['blockers'])})
        self.stage_success(doc,'QUEUED_ANALYSIS');self.checkpoint(doc,'WAITING_SME')

    def verify(self,doc):
        pid=doc['id'];root=self.process_root(pid);self.checkpoint(doc,'VERIFYING')
        try:self.sources(doc);self.review_integrity(doc)
        except (ValidationError,FileNotFoundError) as exc:
            doc['blockers'].append({'kind':'evidence_integrity','message':str(exc)});self.checkpoint(doc,'QUEUED_REPORT');return
        if doc.get('verification_finished'):
            doc['knowledge_records']=update_knowledge(self.ledger,doc)
            self.stage_success(doc,'QUEUED_VERIFY');self.checkpoint(doc,'QUEUED_REPORT');return
        require(doc['packet_imported'] and doc['answers'],'Verification requires the frozen SME return')
        require(decode((root/'analysis'/'source-analysis.json').read_bytes())==doc['analysis'],'Analysis snapshot changed')
        doc['blockers']=[b for b in doc['blockers'] if b['kind'] not in ('sme_unresolved','verification_gap','job_integration_gap')]
        for rid,answer in doc['answers']['items'].items():
            if answer['answer']!='Yes' or answer['correction']:doc['blockers'].append({'kind':'sme_unresolved','item_id':rid,'message':'SME item '+rid+': '+answer['answer']+'. '+answer['correction'],'correction_preserved':bool(answer['correction'])})
        prior=[int(p.name[4:]) for p in (root/'synthetic').glob('run-*') if p.name[4:].isdigit()]
        run_id=f'run-{max([len(doc["runs"]),*prior])+1:04d}';runroot=root/'synthetic'/run_id;runroot.mkdir(parents=True,exist_ok=False)
        run={'id':run_id,'created':now(),'programs':{},'evidence_basis':'SOURCE_DERIVED_EXPECTED','observed_legacy_parity':False,'target_profile':'verified-adapters/python-sqlite-json'}
        logic_summaries=[]
        self.ledger.event(pid,'synthetic','Generating source-derived boundaries, matching records and interaction witnesses; freezing expectations before target execution')
        for name,p in doc['analysis']['programs'].items():
            if p['blockers']:continue
            self.checkpoint(doc)
            args=(p,doc['authorization']['seed'],doc['authorization']['max_cases_per_program'])
            options={'min_records_per_logic':doc['logic_validation_min_records']} if doc.get('logic_validation_min_records') else {}
            if doc.get('fixture_contract_version') in (4,5):options['fixture_contract_version']=doc['fixture_contract_version']
            suite=plan_cases(*args,**options)
            self.checkpoint(doc)
            expected_path=runroot/name/'expected.json';write_new(expected_path,encode(suite));self.register(doc,f'synthetic/{run_id}/{name}/expected.json')
            target_path=self.root/'shared'/'target'/'python'/(doc['program_versions'][name]+'.py')
            code=target_path.read_text(encoding='utf-8');require(sha(code)==doc['program_versions'][name],'Target version changed')
            write_new(root/'target'/run_id/(name+'.py'),code.encode());self.register(doc,f'target/{run_id}/{name}.py')
            self.checkpoint(doc)
            result=verify_program(p,code,suite,checkpoint=lambda:self.checkpoint(doc,persist=False));self.checkpoint(doc)
            from .fixtures import adversarial_review
            adversarial=adversarial_review(p,code,suite,checkpoint=lambda:self.checkpoint(doc,persist=False));self.checkpoint(doc)
            result['adversarial']=adversarial
            unit_result=None
            if doc.get('fixture_contract_version') in (4,5):
                from .unit_evidence import generate_unit_tests, run_unit_tests
                script=generate_unit_tests(p,suite,sha(code))
                unit_relative=f'tests/{run_id}/{name}/test_generated.py'
                unit_path=output_path(self.root,pid,unit_relative)
                write_new(unit_path,script.encode());self.register(doc,unit_relative)
                unit_result=run_unit_tests(script,unit_path,checkpoint=lambda:self.checkpoint(doc,persist=False))
                receipt_relative=f'tests/{run_id}/{name}/unit-results.json'
                write_new(output_path(self.root,pid,receipt_relative),encode(unit_result));self.register(doc,receipt_relative)
                result['unit_tests']={**unit_result,'module':unit_relative,'receipt':receipt_relative}
                if not unit_result['passed']:doc['blockers'].append({'kind':'verification_gap','program':name,'message':'Generated unit comparison tests failed'})
            if suite['coverage'].get('logic_validation'):
                logic_summaries.append({'program':name,**suite['coverage']['logic_validation'],
                    'complete':suite['coverage']['complete'] and not result['differences'] and adversarial['passed'] and (unit_result is None or unit_result['passed']),
                    'target_matched':not result['differences'],'adversarial_passed':adversarial['passed']})
            write_new(runroot/name/'actual-and-comparison.json',encode(result));self.register(doc,f'synthetic/{run_id}/{name}/actual-and-comparison.json')
            self.checkpoint(doc)
            run['programs'][name]=result
            if result['differences'] or not result['coverage']['complete'] or not adversarial['passed']:doc['blockers'].append({'kind':'verification_gap','program':name,'message':'Mismatch, uncovered branch or adversarial witness gap remains'})
        if doc.get('cics_contract_version') == 1:
            from .screen_delivery import verify_layouts
            verify_layouts(self,doc,run)
        # Real local target database records actual computed outputs; never a source Db2 database.
        dbpath=root/'target'/run_id/'target.sqlite';dbpath.parent.mkdir(parents=True,exist_ok=True)
        db=sqlite3.connect(dbpath)
        try:
            with db:
                db.execute('CREATE TABLE results(program TEXT,case_id TEXT,result TEXT,PRIMARY KEY(program,case_id))')
                for name,result in run['programs'].items():db.executemany('INSERT INTO results VALUES(?,?,?)',[(name,r['case_id'],json.dumps(r['result'])) for r in result['actual']])
        finally:db.close()
        self.register(doc,f'target/{run_id}/target.sqlite')
        job_validation=None
        if doc['jobs'] and len(doc['program_versions'])==len(doc['analysis']['programs']) and not any(b['kind'] in ('missing_source','unresolved_condition','unsupported_jcl','scope_mismatch','unsupported_utility','source_classification','unsupported_source','requirements_dependency') for b in doc['blockers']):
            jobs=emit_jobs(doc,doc['program_versions']);write_new(root/'target'/run_id/'jobs.py',jobs.encode());self.register(doc,f'target/{run_id}/jobs.py')
            from .orchestration import verify_jobs
            self.checkpoint(doc)
            result=verify_jobs(doc,self.root,jobs,checkpoint=lambda:self.checkpoint(doc,persist=False));self.checkpoint(doc)
            write_new(root/'target'/run_id/'job-comparison.json',encode(result));self.register(doc,f'target/{run_id}/job-comparison.json')
            job_validation=result.get('validation')
            if job_validation:job_validation={**job_validation,'complete':job_validation['complete'] and bool(result['matched'])}
            if not result['matched']:doc['blockers'].append({'kind':'job_integration_gap','message':result['reason']})
        self.checkpoint(doc)
        if doc.get('logic_validation_min_records'):
            unsupported=len(doc['analysis']['blockers'])
            summary={'minimum_distinct_records_per_logic':doc['logic_validation_min_records'],'programs':logic_summaries,'unsupported_obligations':unsupported,'complete':bool(logic_summaries) and not unsupported and all(s.get('complete') for s in logic_summaries),'basis':'SOURCE_DERIVED_EXPECTED','observed_legacy_parity':False}
            if doc.get('fixture_contract_version') in (4,5):
                if doc.get('cics_contract_version')==1:
                    summary['screen_layouts']=[{'screen_id':ident,'coverage':value['coverage'],'target_matched':not value['differences'],
                        'adversarial_passed':value['adversarial']['passed'],'unit_test_count':value['unit_tests']['tests_run'],
                        'local_layout_passed':value['passed'] and value['adversarial']['passed'] and value['unit_tests']['passed'],
                        'native_controller_verified':False,'http_evidence':'target/'+run_id+'/online/verification.json'} for ident,value in run.get('screens',{}).items()]
                summary.update(fixture_contract_version=doc['fixture_contract_version'],seed=doc['authorization']['seed'],jobs=job_validation,
                               unit_test_count=sum(r.get('unit_tests',{}).get('tests_run',0) for r in run['programs'].values())+sum(r.get('unit_tests',{}).get('tests_run',0) for r in run.get('screens',{}).values()))
                summary['complete']=summary['complete'] and (not doc['jobs'] or bool(job_validation and job_validation['complete']))
            if doc.get('fixture_contract_version')==5:
                summary.update(risk_minimum=128,risk_qualified_logic=sum(len(s.get('validation_policy',{}).get('risk_inputs',[])) for s in logic_summaries))
            relative=f'synthetic/{run_id}/logic-validation.json';write_new(output_path(self.root,pid,relative),encode(summary));self.register(doc,relative)
            doc['logic_validation']={'minimum_distinct_records_per_logic':doc['logic_validation_min_records'],'validated_programs':len(logic_summaries),'unsupported_obligations':unsupported,'complete':summary['complete'],'evidence':relative}
            if doc.get('cics_contract_version')==1:doc['logic_validation']['screen_layouts']=summary.get('screen_layouts',[])
            if doc.get('fixture_contract_version') in (4,5):
                doc['logic_validation'].update(fixture_contract_version=doc['fixture_contract_version'],seed=doc['authorization']['seed'],unit_test_count=summary['unit_test_count'],job_cases=result.get('integration_cases') if job_validation else None)
            if doc.get('fixture_contract_version')==5:doc['logic_validation'].update(risk_minimum=summary['risk_minimum'],risk_qualified_logic=summary['risk_qualified_logic'])
            if not summary['complete']:doc['blockers'].append({'kind':'logic_validation_gap','message':'Every applicable source logic item requires distinct records and reproducible target evidence; unsupported, unreachable or undersampled obligations remain unverified'})
        if doc.get('transactions'):
            from .online import deliver
            doc['online_delivery']=deliver(self,doc,run)
            if doc['online_delivery']['status']!='HTTP_COMPARISON_PASSED':doc['blockers'].append({'kind':'online_delivery_gap','message':'Online HTTP comparison or executable module is incomplete'})
            if not any(b['kind']=='online_semantics_gap' for b in doc['blockers']):
                doc['blockers'].append({'kind':'online_semantics_gap','message':'Generated record APIs/forms do not prove native CICS/BMS session, AID, navigation, security or transaction equivalence; verify source-specific adapters'})
        doc['runs'].append(run);doc['verification_finished']=True;self.checkpoint(doc)
        doc['knowledge_records']=update_knowledge(self.ledger,doc)
        self.ledger.event(pid,'verification','Local target comparisons complete; source-derived expectations remain distinct from observed mainframe results',{'programs':len(run['programs']),'unresolved':len(doc['blockers'])})
        doc['blockers']=[b for b in doc['blockers'] if not (b['kind']=='stage_failure' and b.get('stage')=='QUEUED_VERIFY')]
        doc['verification_finished']=True
        self.stage_success(doc,'QUEUED_VERIFY');self.checkpoint(doc,'QUEUED_REPORT')

    def report(self,doc):
        require_layout(self.root)
        from .reports import generate_reports
        from .coverage import build_coverage
        self.checkpoint(doc,'REPORTING')
        try:self.review_integrity(doc)
        except (ValidationError,FileNotFoundError) as exc:
            if not any(b['kind']=='evidence_integrity' for b in doc['blockers']):doc['blockers'].append({'kind':'evidence_integrity','message':str(exc)})
        if not doc.get('verification_finished') and not any(b['kind']=='verification_incomplete' for b in doc['blockers']):doc['blockers'].append({'kind':'verification_incomplete','message':'Verification did not finish; no unblocked completion is permitted'})
        self.stage_success(doc,'QUEUED_REPORT')
        doc['blockers']=[b for b in doc['blockers'] if b['kind']!='source_accountability']
        coverage=build_coverage(doc,self.root,checkpoint=lambda:self.target_checkpoint(doc));doc['coverage_summary']=coverage['summary']
        if not coverage['summary']['completion_eligible']:doc['blockers'].append({'kind':'source_accountability','message':'Source accounting, applicable verification or evidence integrity gate remains unmet'})
        if doc.get('sme_packet_version',1)>=4:
            from .rule_inventory import build_rule_inventory
            inventory=build_rule_inventory(doc,coverage)
            doc['blockers']=[b for b in doc['blockers'] if b['kind']!='unclassified_rules']
            if inventory['summary']['unclassified']['selected']:
                doc['blockers'].append({'kind':'unclassified_rules','message':'Source behavior remains unclassified; semantic rule totals are incomplete'})
        self.ledger.event(doc['id'],'report','Generating management metrics, source accounting and editable PowerPoint')
        root=self.process_root(doc['id']);versions=[int(p.name[7:]) for p in (root/'reports').glob('report-*') if p.name[7:].isdigit()]
        output=root/'reports'/f'report-{max([0,*versions])+1:04d}'
        generated_cancelled=bool(doc.get('cancel_requested'))
        try:paths=generate_reports(self.ledger,doc,output,checkpoint=lambda:self.target_checkpoint(doc),coverage=coverage)
        finally:
            # Even an interrupted writer's partial files remain reviewable evidence.
            if output.exists():
                for partial in output.rglob('*'):
                    if partial.is_file() and not path_is_link(partial):self.register(doc,partial.relative_to(root).as_posix())
        self.checkpoint(doc)
        required={'economics.json','economics.html','economics.csv','metrics.json','metrics.csv','metrics.xlsx','management.pptx','inspection.json','coverage.json','coverage.csv','coverage.xlsx','coverage.html','executive-report.html','rules.html','rules.json','rules.csv'}
        if doc.get('factory_contract_version'):required.update({'factory.json','factory.html','program-insights.json','program-insights.html'})
        require(required.issubset({Path(p).name for p in paths}),'Mandatory report or source coverage outputs missing')
        hashes={}
        for path in paths:
            path=Path(path);relative=path.relative_to(root).as_posix();safe_path(root,relative)
            require(path.is_file() and path.stat().st_size>0,'Generated report artifact missing or empty')
            self.register(doc,relative);hashes[relative]=sha(path.read_bytes())
        inspection=decode((output/'inspection.json').read_bytes());require(inspection.get('verified') is True,'Report inspection did not pass')
        require(inspection.get('primary_report')=='executive-report.html'
                and inspection.get('executive_schema_version')==1
                and inspection.get('executive_html_checked') is True,
                'Executive report inspection did not pass')
        require((required-{'inspection.json'}).issubset(inspection.get('sha256',{})),'Report inspection omitted mandatory artifact hashes')
        for name,fingerprint in inspection.get('sha256',{}).items():require(sha((output/name).read_bytes())==fingerprint,'Report inspection hash differs')
        with self.lock:
            self.checkpoint(doc)
            if bool(doc.get('cancel_requested'))!=generated_cancelled:
                doc['report_verified']=False;self.checkpoint(doc,'QUEUED_REPORT');raise StageInterrupted()
            doc['report_hashes']=hashes;doc['report_verified']=True
            metrics=decode((output/'metrics.json').read_bytes())['metrics']
            if metrics.get('estate_inventory_json'):doc['accepted_inventory']=json.loads(metrics['estate_inventory_json'])
            self.ledger.complete_report(doc,metrics)

    def launch_worker(self):
        if self.worker:return
        def loop():
            try:
                while not self.stopped.wait(.1):
                    from .local_agent import drain_commands
                    try:drain_commands(self)
                    except (ValidationError,OSError):pass
                    for p in self.ledger.list(True):
                        if self.stopped.is_set():break
                        if p['status'] not in ('QUEUED_ANALYSIS','QUEUED_VERIFY','QUEUED_REPORT'):continue
                        try:self.advance(p['id'])
                        except Exception:pass # advance persists bounded retry/failure.
            finally:
                if self.closed:self._release()
        self.worker=threading.Thread(target=loop,daemon=True);self.worker.start()

    def _release(self):
        with self.lock:
            if self.active:return
            if self.ledger is not None:
                ledger=self.ledger;self.ledger=None
                try:ledger.close()
                finally:self.instance.close()

    def close(self):
        if self.closed:return
        self.closed=True;self.stopped.set()
        if self.worker:self.worker.join(timeout=.5)
        if not self.worker or not self.worker.is_alive():self._release()
