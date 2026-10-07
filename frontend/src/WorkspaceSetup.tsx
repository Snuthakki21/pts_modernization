import React,{useEffect,useRef,useState} from 'react';

export type WorkstationSettings={source_mode:'folder'|'upload';source_folder:string|null;process_notes:string|null;wedlx_folder:string|null;tran_repository_folder:string|null;zowe_profile:string|null;zowe_zosmf_profile:string|null;db2_metadata_url:string|null};
export type WorkstationSetupModel={version:number;saved:boolean;settings:WorkstationSettings;readiness:{status:'NEEDS_SETUP'|'READY_FOR_INTAKE';remaining:string[];connectivity_verified:boolean;source_verified:boolean;conversion_verified:boolean};checks:{id:string;status:string;message:string;action?:string}[];workflow:{assistant_mode:'claude_files';copilot_role:'retrieval_only';claude_mcp_servers:number};metrics:{network_requests:number;[key:string]:unknown}};

// Empty fields have one representation across the form and the local settings API.
export function setupSettingsPayload(settings:WorkstationSettings):{settings:WorkstationSettings}{
 const clean=(value:string|null)=>value?.trim()||null;
 return {settings:{source_mode:settings.source_mode,source_folder:settings.source_mode==='folder'?clean(settings.source_folder):null,process_notes:clean(settings.process_notes),wedlx_folder:clean(settings.wedlx_folder),tran_repository_folder:clean(settings.tran_repository_folder),zowe_profile:clean(settings.zowe_profile),zowe_zosmf_profile:clean(settings.zowe_zosmf_profile),db2_metadata_url:clean(settings.db2_metadata_url)}};
}
export function intakeSetupDefaults(settings?:Pick<WorkstationSettings,'source_mode'|'source_folder'|'process_notes'>|null,localExport=false){
 return {sourceMode:settings?.source_mode==='folder'?'folder':settings?.source_mode==='upload'?'upload':localExport?'local':'upload',sourceFolder:settings?.source_folder||'',processNotes:settings?.process_notes||''};
}

export function intakeSourceSelection(mode:string,folder:string,notes:string,sources:Record<string,string>){
 return {...(mode==='upload'?{sources}:{}),source_folder:mode==='folder'?folder.trim():null,process_notes:notes.trim()||null};
}

export function WorkspaceSetup({model,loading,error,disabled=false,onRetry,onSave,onContinue}:{model:WorkstationSetupModel|null;loading:boolean;error:string;disabled?:boolean;onRetry:()=>void;onSave:(settings:WorkstationSettings)=>Promise<WorkstationSetupModel>;onContinue:()=>void}){
 const [draft,setDraft]=useState<WorkstationSettings|null>(model?.settings||null),[saving,setSaving]=useState(false),[saveError,setSaveError]=useState(''),[feedback,setFeedback]=useState('');
 const submitting=useRef(false),result=useRef<HTMLDivElement>(null);
 useEffect(()=>{setDraft(model?.settings||null);setSaveError('');setFeedback('');},[model]);
 const locked=disabled||loading||saving;
 async function save(){
  if(!draft||locked||submitting.current)return;
  submitting.current=true;setSaving(true);setSaveError('');setFeedback('');
  try{const updated=await onSave(setupSettingsPayload(draft).settings);setDraft(updated.settings);setFeedback(updated.readiness.status==='READY_FOR_INTAKE'?'Setup saved. You’re ready to add a process.':'Settings saved. Resolve the items shown below.');result.current?.focus();}
  catch(failure){setSaveError(failure instanceof Error?failure.message:'Setup could not be saved. Try again.');}
  finally{submitting.current=false;setSaving(false);}
 }
 if(error)return <section className="setup-card"><h2>Load your saved setup</h2><p className="error" role="alert">{error}</p><p>Your saved values are preserved.</p><button onClick={onRetry} disabled={loading}>Try loading setup again</button></section>;
 if(!model||!draft)return <section className="setup-card" aria-busy="true"><p className="eyebrow">WORKSPACE SETUP</p><h2>Loading your setup</h2><p role="status">Reading the settings for this workspace…</p></section>;
 const dirty=JSON.stringify(setupSettingsPayload(draft))!==JSON.stringify(setupSettingsPayload(model.settings));
 const ready=model.saved&&!dirty&&!loading&&!saving&&!saveError&&model.readiness.status==='READY_FOR_INTAKE';
 const field=(key:Exclude<keyof WorkstationSettings,'source_mode'>,value:string)=>{setDraft({...draft,[key]:value});setSaveError('');setFeedback('');};
 return <section className="setup-card workstation-setup" aria-labelledby="workstation-setup-title" aria-busy={loading||saving}>
  <div className="sectionhead"><div><p className="eyebrow">WORKSPACE SETUP</p><h2 id="workstation-setup-title">Your folders. One save.</h2></div>{ready&&<span className="status-pill">Setup saved</span>}</div>
  <p className="intro">Choose where your source comes from. Save once; these values carry into each new process.</p>
  <form onSubmit={event=>{event.preventDefault();void save();}}>
   <fieldset className="source-mode setup-source"><legend>Source export</legend>
    <label><input type="radio" name="setup-source-mode" value="folder" checked={draft.source_mode==='folder'} disabled={locked} onChange={()=>{setDraft({...draft,source_mode:'folder'});setFeedback('');}}/>Use a folder on this workstation</label>
    <label><input type="radio" name="setup-source-mode" value="upload" checked={draft.source_mode==='upload'} disabled={locked} onChange={()=>{setDraft({...draft,source_mode:'upload'});setFeedback('');}}/>I’ll upload the export when I add a process</label>
   </fieldset>
   {draft.source_mode==='folder'?<label htmlFor="setup-source-folder">Complete source export folder<input id="setup-source-folder" type="text" value={draft.source_folder||''} onChange={event=>field('source_folder',event.target.value)} required disabled={locked} maxLength={2048} autoComplete="off" spellCheck={false} aria-describedby="setup-source-help" placeholder="C:\exports\Endeavor or /data/exports/Endeavor"/><span className="field-help" id="setup-source-help">Use a full path on the computer running this workspace. The original files stay unchanged.</span></label>:<p className="notice">No source folder is needed now. You’ll choose your files when you add a process.</p>}
   <label htmlFor="setup-process-notes">Process notes file <span className="optional-label">optional</span><input id="setup-process-notes" type="text" value={draft.process_notes||''} onChange={event=>field('process_notes',event.target.value)} disabled={locked} maxLength={2048} autoComplete="off" spellCheck={false} placeholder="Full path to your process .md file" aria-describedby="setup-notes-help"/><span className="field-help" id="setup-notes-help">Your supplied process knowledge is included with new processes. You can change it for an individual process.</span></label>
   <details className="setup-advanced"><summary>Optional source locations and approved retrieval settings</summary><p className="fine-print">Use values your organization has already approved for Copilot retrieval.</p>
    <div className="fields">
     <label htmlFor="setup-wedlx">WEDLX folder<input id="setup-wedlx" type="text" value={draft.wedlx_folder||''} onChange={event=>field('wedlx_folder',event.target.value)} disabled={locked} maxLength={2048} autoComplete="off" spellCheck={false}/></label>
     <label htmlFor="setup-tran">Tran Repository folder<input id="setup-tran" type="text" value={draft.tran_repository_folder||''} onChange={event=>field('tran_repository_folder',event.target.value)} disabled={locked} maxLength={2048} autoComplete="off" spellCheck={false}/></label>
     <label htmlFor="setup-zowe">Existing Zowe base profile<input id="setup-zowe" type="text" value={draft.zowe_profile||''} onChange={event=>field('zowe_profile',event.target.value)} disabled={locked} maxLength={80} autoComplete="off" spellCheck={false}/></label>
     <label htmlFor="setup-zosmf">Existing z/OSMF profile<input id="setup-zosmf" type="text" value={draft.zowe_zosmf_profile||''} onChange={event=>field('zowe_zosmf_profile',event.target.value)} disabled={locked} maxLength={80} autoComplete="off" spellCheck={false}/></label>
    </div>
    <label htmlFor="setup-db2">Approved Db2 metadata endpoint<input id="setup-db2" type="url" value={draft.db2_metadata_url||''} onChange={event=>field('db2_metadata_url',event.target.value)} disabled={locked} maxLength={8192} autoComplete="off" spellCheck={false} placeholder="https://approved-host/metadata" aria-describedby="setup-db2-help"/><span className="field-help" id="setup-db2-help">Endpoint only. Keep credentials in your existing secure configuration.</span></label>
   </details>
   <p className="notice setup-workflow"><strong>Claude Code builds and tests from local files.</strong> Copilot retrieves missing evidence through your approved connections. Claude uses no MCP servers.</p>
   {saveError&&<p className="error" role="alert">{saveError}</p>}
   {loading&&<p role="status">Refreshing saved settings…</p>}
   <div className="form-actions"><button className="primary" type="submit" disabled={locked||draft.source_mode==='folder'&&!draft.source_folder?.trim()}>{saving?'Saving setup…':'Save setup'} <span aria-hidden="true">✓</span></button>{dirty&&<span className="fine-print">Unsaved changes</span>}{disabled&&!loading&&<span className="fine-print">Wait for the local workspace connection.</span>}</div>
  </form>
  <div ref={result} tabIndex={-1} className="setup-result" role="status" aria-live="polite">{feedback}{ready&&<><h3>Setup is done</h3><p>Your settings are saved for this workspace and survive a restart.</p><button type="button" onClick={onContinue} disabled={locked}>Add a process <span aria-hidden="true">→</span></button></>}</div>
  {model.saved&&!dirty&&!loading&&model.readiness.status==='NEEDS_SETUP'&&<div className="notice"><h3>Settings need attention</h3><ul className="compact-list">{model.checks.filter(check=>check.status==='BLOCKED').map(check=><li key={check.id}>{check.message}{check.action&&<> {check.action}</>}</li>)}</ul></div>}
  <p className="fine-print setup-scope">Setup checks local settings only. Connectivity and conversion are verified separately when the relevant evidence is available.</p>
 </section>;
}
