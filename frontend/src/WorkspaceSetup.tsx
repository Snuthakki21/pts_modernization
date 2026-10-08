import React,{useEffect,useRef,useState} from 'react';

export type WorkstationSettings={source_mode:'folder'|'upload';source_folder:string|null;process_notes:string|null;wedlx_folder:string|null;tran_repository_folder:string|null;zowe_profile:string|null;zowe_zosmf_profile:string|null;db2_metadata_url:string|null};
type ZoweMode='off'|'existing'|'create'|'import';
type Db2Mode='off'|'existing'|'gateway';
type Db2Choices={mode:Db2Mode;host:string|null;port:number|null;database:string|null;location:string|null;certificate_file:string|null;mcp_port:number|null;row_limit:number|null;driver:string|null};
type Db2Draft={mode:Db2Mode;host:string;port:string;database:string;location:string;certificate_file:string;mcp_port:string;row_limit:string;driver:string};
export type WorkstationConnections={copilot:boolean;zowe:{mode:ZoweMode;host:string|null;port:number|null;config_file:string|null;schema_file:string|null};db2?:Db2Choices};
export type WorkstationConnectionDraft={copilot:boolean;zowe:{mode:ZoweMode;host:string;port:string;config_file:string;schema_file:string};db2?:Db2Draft};
export type ConnectionSetup={choices:WorkstationConnections;status:string;checks:{id:string;status:string;message:string;action?:string}[];commands:{id:string;label:string;command:string;required:boolean}[];files:{kind:string;path:string;status:string}[];remaining:{id:string;message:string}[];runtime:{platform:string;zowe_cli:string};claude_mcp_servers:number;connectivity:string};
export type WorkstationSetupModel={version:number;saved:boolean;settings:WorkstationSettings;readiness:{status:'NEEDS_SETUP'|'READY_FOR_INTAKE';remaining:string[];connectivity_verified:boolean;source_verified:boolean;conversion_verified:boolean};checks:{id:string;status:string;message:string;action?:string}[];workflow:{assistant_mode:'claude_files';copilot_role:'retrieval_only';claude_mcp_servers:number};metrics:{network_requests:number;[key:string]:unknown};connection_setup?:ConnectionSetup;instructions?:{markdown_path:string;sha256:string;text:string;next_step:string}};

export function workstationReady(model:WorkstationSetupModel|null|undefined,{loading=false,error='',disabled=false}:{loading?:boolean;error?:string;disabled?:boolean}={}){
 return !loading&&!error&&!disabled&&model?.saved===true&&model.readiness?.status==='READY_FOR_INTAKE'&&Array.isArray(model.readiness.remaining)&&model.readiness.remaining.length===0&&Array.isArray(model.checks)&&!model.checks.some(check=>check.status==='BLOCKED');
}

// Empty settings have one representation. An explicit Off choice also clears retrieval aliases.
export function setupSettingsPayload(settings:WorkstationSettings,connections?:WorkstationConnections):{settings:WorkstationSettings;connections?:WorkstationConnections}{
 const clean=(value:string|null)=>value?.trim()||null,db2=connections?.db2;
 const db2_metadata_url=db2?.mode==='off'?null:db2?.mode==='gateway'?'http://127.0.0.1:'+db2.mcp_port+'/mcp':clean(settings.db2_metadata_url);
 if(db2?.mode==='existing'&&!db2_metadata_url)throw new Error('Enter the approved Db2 MCP endpoint.');
 return {settings:{source_mode:settings.source_mode,source_folder:settings.source_mode==='folder'?clean(settings.source_folder):null,process_notes:clean(settings.process_notes),wedlx_folder:clean(settings.wedlx_folder),tran_repository_folder:clean(settings.tran_repository_folder),zowe_profile:connections?.zowe.mode==='off'?null:clean(settings.zowe_profile),zowe_zosmf_profile:connections?.zowe.mode==='off'?null:clean(settings.zowe_zosmf_profile),db2_metadata_url},...(connections===undefined?{}:{connections})};
}
const emptyDb2Draft=(mode:Db2Mode='off'):Db2Draft=>({mode,host:'',port:'',database:'',location:'',certificate_file:'',mcp_port:'',row_limit:'',driver:''});
export function setupConnectionDraft(model:WorkstationSetupModel|null):WorkstationConnectionDraft{
 const choices=model?.connection_setup?.choices,db2=choices?.db2;
 return {copilot:choices?.copilot??false,zowe:{mode:choices?.zowe.mode??(model?.settings.zowe_profile?'existing':'off'),host:choices?.zowe.host??'',port:choices?.zowe.port===null||choices?.zowe.port===undefined?'':String(choices.zowe.port),config_file:choices?.zowe.config_file??'',schema_file:choices?.zowe.schema_file??''},...(db2?{db2:{mode:db2.mode,host:db2.host??'',port:db2.port===null?'':String(db2.port),database:db2.database??'',location:db2.location??'',certificate_file:db2.certificate_file??'',mcp_port:db2.mcp_port===null?'':String(db2.mcp_port),row_limit:db2.row_limit===null?'':String(db2.row_limit),driver:db2.driver??''}}:{})};
}
export function selectSetupConnectionMode(settings:WorkstationSettings,connections:WorkstationConnectionDraft,mode:ZoweMode){
 return {settings:mode==='create'?{...settings,zowe_profile:settings.zowe_profile?.trim()?settings.zowe_profile:'workbench_base',zowe_zosmf_profile:settings.zowe_zosmf_profile?.trim()?settings.zowe_zosmf_profile:'workbench_zosmf'}:settings,connections:{...connections,zowe:{...connections.zowe,mode,port:mode==='create'?connections.zowe.port||'443':connections.zowe.port}}};
}
export function selectSetupDb2Mode(settings:WorkstationSettings,connections:WorkstationConnectionDraft,mode:Db2Mode){
 const current=connections.db2??emptyDb2Draft(settings.db2_metadata_url?'existing':'off');
 return {settings,connections:{...connections,copilot:mode==='gateway'?true:connections.copilot,db2:{...current,mode,...(mode==='gateway'?{mcp_port:current.mcp_port||'8766',row_limit:current.row_limit||'500000',driver:current.driver||'IBM DB2 ODBC DRIVER'}:{})}}};
}
function wholeSetupValue(value:string,maximum:number,label:string){
 if(typeof value!=='string'||!/^\d+$/.test(value.trim())||Number(value)<1||Number(value)>maximum)throw new Error('Enter a whole-number '+label+' from 1 to '+maximum+'.');
 return Number(value);
}
function requiredSetupValue(value:string,label:string){
 if(typeof value!=='string'||!value.trim())throw new Error('Enter the actual Db2 '+label+'.');
 return value.trim();
}
export function setupConnectionPayload(draft:WorkstationConnectionDraft):WorkstationConnections{
 const zowe=draft.zowe;let selected:WorkstationConnections['zowe'];
 if(zowe.mode==='create'){
  const host=zowe.host.trim();if(!host)throw new Error('Enter the actual z/OSMF host.');
  selected={mode:'create',host,port:wholeSetupValue(zowe.port,65535,'z/OSMF port'),config_file:null,schema_file:null};
 }else if(zowe.mode==='import'){
  const config_file=zowe.config_file.trim(),schema_file=zowe.schema_file.trim()||null;
  if(!config_file)throw new Error('Enter the exact local Zowe config file path.');
  selected={mode:'import',host:null,port:null,config_file,schema_file};
 }else selected={mode:zowe.mode,host:null,port:null,config_file:null,schema_file:null};
 const result:WorkstationConnections={copilot:draft.copilot,zowe:selected},db2=draft.db2;
 if(db2){
  if(db2.mode==='gateway'){
   result.db2={mode:'gateway',host:requiredSetupValue(db2.host,'host'),port:wholeSetupValue(db2.port,65535,'Db2 port'),database:requiredSetupValue(db2.database,'database'),location:requiredSetupValue(db2.location,'DDF location'),certificate_file:db2.certificate_file.trim()||null,mcp_port:wholeSetupValue(db2.mcp_port,65535,'MCP loopback port'),row_limit:wholeSetupValue(db2.row_limit,500000,'row limit'),driver:requiredSetupValue(db2.driver,'driver name')};result.copilot=true;
  }else result.db2={mode:db2.mode,host:null,port:null,database:null,location:null,certificate_file:null,mcp_port:null,row_limit:null,driver:null};
 }
 return result;
}
export function setupDraftDirty(settings:WorkstationSettings|null,connections:WorkstationConnectionDraft|null,model:WorkstationSetupModel|null){
 return !!settings&&!!connections&&!!model&&(JSON.stringify(setupSettingsPayload(settings))!==JSON.stringify(setupSettingsPayload(model.settings))||JSON.stringify(connections)!==JSON.stringify(setupConnectionDraft(model)));
}
export async function copySetupCommand(command:string,write?:(text:string)=>Promise<void>):Promise<boolean>{
 try{const writer=write??(typeof navigator!=='undefined'&&navigator.clipboard?((text:string)=>navigator.clipboard.writeText(text)):undefined);if(!writer)return false;await writer(command);return true;}catch{return false;}
}
export function intakeSetupDefaults(settings?:Pick<WorkstationSettings,'source_mode'|'source_folder'|'process_notes'>|null,localExport=false){
 return {sourceMode:settings?.source_mode==='folder'?'folder':settings?.source_mode==='upload'?'upload':localExport?'local':'upload',sourceFolder:settings?.source_folder||'',processNotes:settings?.process_notes||''};
}
export function intakeSourceSelection(mode:string,folder:string,notes:string,sources:Record<string,string>){
 return {...(mode==='upload'?{sources}:{}),source_folder:mode==='folder'?folder.trim():null,process_notes:notes.trim()||null};
}
const humanStatus=(status:string)=>status.toLowerCase().replaceAll('_',' ');

export function WorkspaceSetup({model,loading,error,disabled=false,onRetry,onSave,onContinue,onDirtyChange}:{model:WorkstationSetupModel|null;loading:boolean;error:string;disabled?:boolean;onRetry:()=>void;onSave:(settings:WorkstationSettings,connections?:WorkstationConnections)=>Promise<WorkstationSetupModel>;onContinue:()=>void;onDirtyChange?:(dirty:boolean)=>void}){
 const [draft,setDraft]=useState<WorkstationSettings|null>(model?.settings||null),[connections,setConnections]=useState<WorkstationConnectionDraft>(setupConnectionDraft(model)),[saving,setSaving]=useState(false),[saveError,setSaveError]=useState(''),[feedback,setFeedback]=useState(''),[copyNotice,setCopyNotice]=useState<{index:number;message:string}|null>(null);
 const submitting=useRef(false),edited=useRef(false),result=useRef<HTMLDivElement>(null),commandFields=useRef(new Map<number,HTMLTextAreaElement>()),copyEpoch=useRef(0);
 useEffect(()=>{if(model&&!edited.current){setDraft(model.settings);setConnections(setupConnectionDraft(model));}copyEpoch.current++;setCopyNotice(null);},[model]);
 const dirty=setupDraftDirty(draft,connections,model),locked=disabled||loading||saving||!!error;
 useEffect(()=>{onDirtyChange?.(dirty);},[dirty,onDirtyChange]);
 function edit(settings:WorkstationSettings,choices=connections){edited.current=setupDraftDirty(settings,choices,model);setDraft(settings);setConnections(choices);setSaveError('');setFeedback('');copyEpoch.current++;setCopyNotice(null);onDirtyChange?.(edited.current);}
 function retry(){setSaveError('');setFeedback('');copyEpoch.current++;setCopyNotice(null);onRetry();}
 async function copy(index:number,command:string){const epoch=copyEpoch.current,copied=await copySetupCommand(command);if(epoch!==copyEpoch.current)return;if(!copied){commandFields.current.get(index)?.focus();commandFields.current.get(index)?.select();}setCopyNotice({index,message:copied?'Command copied.':'Copy is unavailable. The command is selected; press Ctrl+C on Windows or Command+C on Mac.'});}
 async function save(){
  if(!draft||locked||submitting.current)return;
  submitting.current=true;setSaving(true);setSaveError('');setFeedback('');
  try{
   const choices=model?.connection_setup||JSON.stringify(connections)!==JSON.stringify(setupConnectionDraft(model))?setupConnectionPayload(connections):undefined;
   const payload=setupSettingsPayload(draft,choices);
   if(choices&&choices.zowe.mode!=='off'&&(!payload.settings.zowe_profile||!payload.settings.zowe_zosmf_profile))throw new Error('Enter the selected Zowe base and z/OSMF profile aliases.');
   const updated=await onSave(payload.settings,choices);edited.current=false;setDraft(updated.settings);setConnections(setupConnectionDraft(updated));setFeedback('Settings saved. Review the local checks and any connection actions below.');result.current?.focus();
  }catch(failure){setSaveError(failure instanceof Error?failure.message:'Setup could not be saved. Try again.');}
  finally{submitting.current=false;setSaving(false);}
 }
 if(error&&(!model||!draft))return <section className="setup-card"><h2>Load your saved setup</h2><p className="error" role="alert">{error}</p><p>Your saved values are preserved.</p><button onClick={retry} disabled={loading}>Try loading setup again</button></section>;
 if(!model||!draft)return <section className="setup-card" aria-busy="true"><p className="eyebrow">WORKSPACE SETUP</p><h2>Loading your setup</h2><p role="status">Reading the settings for this workspace…</p></section>;
 const ready=!dirty&&!saving&&!saveError&&workstationReady(model,{loading,error,disabled}),info=model.connection_setup;
 const field=(key:Exclude<keyof WorkstationSettings,'source_mode'>,value:string)=>edit({...draft,[key]:value});
 const zoweField=(key:Exclude<keyof WorkstationConnectionDraft['zowe'],'mode'>,value:string)=>edit(draft,{...connections,zowe:{...connections.zowe,[key]:value}});
 const db2=connections.db2??emptyDb2Draft(draft.db2_metadata_url?'existing':'off');
 const db2Field=(key:Exclude<keyof Db2Draft,'mode'>,value:string)=>edit(draft,{...connections,copilot:db2.mode==='gateway'?true:connections.copilot,db2:{...db2,[key]:value}});
 const connectionStatus=info?.remaining.length?'ACTION_REQUIRED':info?.status;
 return <section className="setup-card workstation-setup" aria-labelledby="workstation-setup-title" aria-busy={loading||saving}>
  <div className="sectionhead"><div><p className="eyebrow">WORKSPACE SETUP</p><h2 id="workstation-setup-title">Your folders. One save.</h2></div>{ready&&<span className="status-pill">Intake settings saved</span>}</div>
  <p className="intro">Choose your source defaults and any approved connections. One save prepares the selected local configuration.</p>
  {error&&<div className="error" role="alert"><p>{error}</p><p>Your draft is preserved. Recheck before saving.</p><button type="button" onClick={retry} disabled={loading||saving}>Try loading setup again</button></div>}
  <form onSubmit={event=>{event.preventDefault();void save();}}>
   <fieldset className="source-mode setup-source"><legend>Source export</legend>
    <label><input type="radio" name="setup-source-mode" value="folder" checked={draft.source_mode==='folder'} disabled={locked} onChange={()=>edit({...draft,source_mode:'folder'})}/>Use a folder on this workstation</label>
    <label><input type="radio" name="setup-source-mode" value="upload" checked={draft.source_mode==='upload'} disabled={locked} onChange={()=>edit({...draft,source_mode:'upload'})}/>I’ll retrieve or upload source when I add a process</label>
   </fieldset>
   {draft.source_mode==='folder'?<label htmlFor="setup-source-folder">Complete source export folder<input id="setup-source-folder" type="text" value={draft.source_folder||''} onChange={event=>field('source_folder',event.target.value)} required disabled={locked} maxLength={2048} autoComplete="off" spellCheck={false} aria-describedby="setup-source-help" placeholder="C:\exports\Endeavor or /data/exports/Endeavor"/><span className="field-help" id="setup-source-help">Use a full path on the computer running this workspace. The original files stay unchanged.</span></label>:<p className="notice">No source folder is needed now. Add your process Markdown next. Copilot can retrieve the requested source, or you can upload an existing export.</p>}
   <label htmlFor="setup-process-notes">Process notes file <span className="optional-label">optional</span><input id="setup-process-notes" type="text" value={draft.process_notes||''} onChange={event=>field('process_notes',event.target.value)} disabled={locked} maxLength={2048} autoComplete="off" spellCheck={false} placeholder="Full path to your process .md file" aria-describedby="setup-notes-help"/><span className="field-help" id="setup-notes-help">Your supplied process knowledge is included with new processes. You can change it for an individual process.</span></label>
   <details className="setup-advanced"><summary>Optional source locations and approved retrieval settings</summary><p className="fine-print">Use exact folder bindings approved by your organization.</p><div className="fields">
    <label htmlFor="setup-wedlx">WEDLX folder<input id="setup-wedlx" type="text" value={draft.wedlx_folder||''} onChange={event=>field('wedlx_folder',event.target.value)} disabled={locked} maxLength={2048} autoComplete="off" spellCheck={false}/></label>
    <label htmlFor="setup-tran">Tran Repository folder<input id="setup-tran" type="text" value={draft.tran_repository_folder||''} onChange={event=>field('tran_repository_folder',event.target.value)} disabled={locked} maxLength={2048} autoComplete="off" spellCheck={false}/></label>
   </div></details>
   <fieldset className="setup-connectors"><legend>Approved mainframe connections</legend>
    <p>Db2 catalog/data uses an approved MCP server. Mainframe files/metadata use Zowe CLI. You can defer connections for approved exported-source intake. Credentials stay in their secure clients; saving does not prove host access.</p>
    <label className="setup-checkbox" htmlFor="setup-copilot"><input id="setup-copilot" type="checkbox" checked={connections.copilot} disabled={locked||db2.mode==='gateway'} onChange={event=>edit(draft,{...connections,copilot:event.target.checked})}/>Prepare Copilot retrieval-only MCP</label>
    <p className="field-help">Save prepares this workspace’s VS Code MCP file and preserves other server bindings. You still review trust and start the servers in VS Code.{db2.mode==='gateway'&&' Gateway preparation also selects Copilot’s retrieval-only connection.'}</p>
    <label htmlFor="setup-zowe-mode">Zowe configuration<select id="setup-zowe-mode" value={connections.zowe.mode} disabled={locked} onChange={event=>{const selected=selectSetupConnectionMode(draft,connections,event.target.value as ZoweMode);edit(selected.settings,selected.connections);}}>
     <option value="off">No Zowe setup now</option><option value="existing">Use existing local profiles</option><option value="create">Create secure profile configuration</option><option value="import">Import a supplied config and schema</option>
    </select></label>
    {connections.zowe.mode!=='off'&&<div className="fields">
     <label htmlFor="setup-zowe">Zowe base profile alias<input id="setup-zowe" type="text" value={draft.zowe_profile||''} onChange={event=>field('zowe_profile',event.target.value)} required disabled={locked} maxLength={80} autoComplete="off" spellCheck={false}/></label>
     <label htmlFor="setup-zosmf">z/OSMF profile alias<input id="setup-zosmf" type="text" value={draft.zowe_zosmf_profile||''} onChange={event=>field('zowe_zosmf_profile',event.target.value)} required disabled={locked} maxLength={80} autoComplete="off" spellCheck={false}/></label>
    </div>}
    {connections.zowe.mode==='existing'&&<p className="field-help">Use the exact aliases in this workspace’s approved Zowe project configuration. CLI availability and credentials are checked separately.</p>}
    {connections.zowe.mode==='create'&&<><div className="fields">
     <label htmlFor="setup-zowe-host">Actual z/OSMF host<input id="setup-zowe-host" type="text" value={connections.zowe.host} onChange={event=>zoweField('host',event.target.value)} required disabled={locked} maxLength={2048} autoComplete="off" spellCheck={false} placeholder="zosmf.approved-host.example"/></label>
     <label htmlFor="setup-zowe-port">z/OSMF port<input id="setup-zowe-port" type="number" value={connections.zowe.port} onChange={event=>zoweField('port',event.target.value)} required disabled={locked} min={1} max={65535} step={1}/></label>
    </div><p className="field-help">Use the service host and port supplied by your administrator. Save creates HTTPS profiles with certificate validation and secure credential fields.</p></>}
    {connections.zowe.mode==='import'&&<>
     <label htmlFor="setup-zowe-config">Supplied Zowe config file<input id="setup-zowe-config" type="text" value={connections.zowe.config_file} onChange={event=>zoweField('config_file',event.target.value)} required disabled={locked} maxLength={2048} autoComplete="off" spellCheck={false} placeholder="Full local path to zowe.config.json"/></label>
     <label htmlFor="setup-zowe-schema">Supplied Zowe schema file <span className="optional-label">optional</span><input id="setup-zowe-schema" type="text" value={connections.zowe.schema_file} onChange={event=>zoweField('schema_file',event.target.value)} disabled={locked} maxLength={2048} autoComplete="off" spellCheck={false} placeholder="Full local path to zowe.schema.json"/></label>
     <p className="field-help">Choose the supplied local files and their exact profile aliases. Import preserves the file bytes; conflicting project files produce an error.</p>
    </>}
    <label htmlFor="setup-db2-mode">Db2 MCP setup<select id="setup-db2-mode" value={db2.mode} disabled={locked} onChange={event=>{const selected=selectSetupDb2Mode(draft,connections,event.target.value as Db2Mode);edit(selected.settings,selected.connections);}}><option value="off">No Db2 setup now</option><option value="existing">Use an approved existing MCP server</option><option value="gateway">Prepare the local Db2 MCP gateway</option></select></label>
    {db2.mode==='existing'&&<label htmlFor="setup-db2">Approved Db2 MCP endpoint<input id="setup-db2" type="url" value={draft.db2_metadata_url||''} onChange={event=>field('db2_metadata_url',event.target.value)} required disabled={locked} maxLength={8192} autoComplete="off" spellCheck={false} placeholder="https://approved-host/mcp" aria-describedby="setup-db2-help"/><span className="field-help" id="setup-db2-help">Use the approved server endpoint. With Copilot preparation selected, Save adds its secure VS Code token prompt. Do not paste credentials here.</span></label>}
    {db2.mode==='gateway'&&<>
     <div className="fields">
      <label htmlFor="setup-db2-host">Actual Db2 host<input id="setup-db2-host" type="text" value={db2.host} onChange={event=>db2Field('host',event.target.value)} required disabled={locked} maxLength={253} autoComplete="off" spellCheck={false}/></label>
      <label htmlFor="setup-db2-port">Db2 port<input id="setup-db2-port" type="number" value={db2.port} onChange={event=>db2Field('port',event.target.value)} required disabled={locked} min={1} max={65535} step={1}/></label>
      <label htmlFor="setup-db2-database">Db2 database<input id="setup-db2-database" type="text" value={db2.database} onChange={event=>db2Field('database',event.target.value)} required disabled={locked} maxLength={253} autoComplete="off" spellCheck={false}/></label>
      <label htmlFor="setup-db2-location">DDF location<input id="setup-db2-location" type="text" value={db2.location} onChange={event=>db2Field('location',event.target.value)} required disabled={locked} maxLength={253} autoComplete="off" spellCheck={false}/></label>
     </div>
     <label htmlFor="setup-db2-driver">Registered Db2 ODBC driver name<input id="setup-db2-driver" type="text" value={db2.driver} onChange={event=>db2Field('driver',event.target.value)} required disabled={locked} maxLength={253} autoComplete="off" spellCheck={false}/><span className="field-help">Use the actual registered name for your approved IBM driver. Missing drivers remain a separate installation action.</span></label>
     <label htmlFor="setup-db2-certificate">Approved Db2 CA certificate file <span className="optional-label">optional if already prepared</span><input id="setup-db2-certificate" type="text" value={db2.certificate_file} onChange={event=>db2Field('certificate_file',event.target.value)} disabled={locked} maxLength={2048} autoComplete="off" spellCheck={false} placeholder="Full local path to the approved CA certificate"/><span className="field-help">Save copies the supplied certificate bytes. Leave blank to retain a valid workspace CA; a missing certificate stays an explicit prerequisite.</span></label>
     <div className="fields">
      <label htmlFor="setup-db2-mcp-port">Local MCP loopback port<input id="setup-db2-mcp-port" type="number" value={db2.mcp_port} onChange={event=>db2Field('mcp_port',event.target.value)} required disabled={locked} min={1} max={65535} step={1}/></label>
      <label htmlFor="setup-db2-row-limit">Maximum rows per query<input id="setup-db2-row-limit" type="number" value={db2.row_limit} onChange={event=>db2Field('row_limit',event.target.value)} required disabled={locked} min={1} max={500000} step={1}/></label>
     </div>
     <p className="field-help">The gateway listens only on 127.0.0.1. Save prepares its local configuration and Copilot connection with SSL validation enabled. Run the returned interactive command to enter username, password and token securely. No packages, drivers or servers start here.</p>
    </>}
   </fieldset>
   <p className="notice setup-workflow"><strong>Claude Code builds and tests from local files.</strong> Copilot retrieves missing evidence through your approved connections. Claude uses no MCP servers.</p>
   {saveError&&<p className="error" role="alert">{saveError}</p>}{loading&&<p role="status">Refreshing saved settings…</p>}
   <div className="form-actions"><button className="primary" type="submit" disabled={locked||draft.source_mode==='folder'&&!draft.source_folder?.trim()}>{saving?'Saving setup…':'Save setup'} <span aria-hidden="true">✓</span></button>{dirty&&<span className="fine-print">Unsaved changes</span>}{disabled&&!loading&&<span className="fine-print">Wait for the local workspace connection.</span>}</div>
  </form>
  <div ref={result} tabIndex={-1} className="setup-result" role="status" aria-live="polite">{!dirty&&!loading&&!error&&!disabled&&feedback}{ready&&<><h3>{info?'Intake settings saved':'Setup is done'}</h3>{model?.instructions&&<details className="setup-instructions"><summary>Saved setup Markdown</summary><p><code>{model.instructions.markdown_path}</code></p><label>Workspace instructions<textarea readOnly rows={8} value={model.instructions.text}/></label><p className="fine-print">SHA256 {model.instructions.sha256}</p></details>}<p>{info?'Local intake is ready. ':''}Your settings are saved for this workspace and survive a restart.{connectionStatus==='ACTION_REQUIRED'&&' Finish the connector actions below separately.'}</p><button type="button" onClick={onContinue} disabled={locked}>Add a process <span aria-hidden="true">→</span></button></>}</div>
  {model.saved&&!dirty&&!loading&&!workstationReady(model)&&<div className="notice"><h3>Settings need attention</h3><ul className="compact-list">{model.checks.filter(check=>check.status==='BLOCKED').map(check=><li key={check.id}>{check.message}{check.action&&<> {check.action}</>}</li>)}{model.readiness.remaining.filter(id=>id!=='save'&&!model.checks.some(check=>check.id===id&&check.status==='BLOCKED')).map(id=><li key={id}>Resolve the saved setup item: {id.replaceAll('_',' ')}.</li>)}</ul></div>}
  <div className="setup-connector-result" aria-labelledby="setup-connection-result-title"><h3 id="setup-connection-result-title">Finish MCP and Zowe setup</h3>
   {dirty?<p className="notice">Save your changed choices to prepare configuration and get the matching commands. The previous connection state does not confirm this draft.</p>:info?<>
    {(error||disabled)&&<p className="fine-print">Last loaded local state. Recheck before relying on these instructions.</p>}
    <p>{connectionStatus==='ACTION_REQUIRED'?'Local configuration needs the actions below.':connectionStatus==='CONFIGURATION_READY'?'Selected local configuration is prepared.':connectionStatus==='NOT_CONFIGURED'?'No connector preparation is selected.':'Local connection configuration needs review.'} Host access remains unverified.</p>
    <p className="fine-print">Local checks for {info.runtime.platform}. Zowe CLI: {humanStatus(info.runtime.zowe_cli)}. CLI availability does not verify authentication or read access.</p>
    {info.checks.length>0&&<ul className="compact-list">{info.checks.map(check=><li key={check.id}>{check.message}{check.action&&<> {check.action}</>}</li>)}</ul>}
    {info.files.length>0&&<><h3>Connection files</h3><dl className="setup-connection-files">{info.files.map((file,index)=><React.Fragment key={file.kind+index}><dt>{file.kind==='copilot'?'Copilot MCP':file.kind==='zowe'?'Zowe project configuration':file.kind==='zowe_schema'?'Zowe schema':file.kind==='db2_config'?'Db2 gateway configuration':file.kind==='db2_certificate'?'Db2 CA certificate':file.kind} · {humanStatus(file.status)}</dt><dd><code>{file.path}</code></dd></React.Fragment>)}</dl></>}
    {info.remaining.length>0&&<><h3>Actions still required</h3><ul className="compact-list">{info.remaining.map(item=><li key={item.id}>{item.message}</li>)}</ul></>}
    {info.commands.length>0&&<div className="setup-commands">{info.commands.map((command,index)=><div className="setup-command" key={command.id}><label htmlFor={'setup-command-'+index}>{command.label}{!command.required&&<span className="optional-label">optional</span>}</label><textarea id={'setup-command-'+index} ref={node=>{if(node)commandFields.current.set(index,node);else commandFields.current.delete(index);}} value={command.command} readOnly disabled={locked} rows={Math.max(3,Math.min(6,command.command.split('\n').length+1))} spellCheck={false}/><button type="button" disabled={locked} aria-label={'Copy command: '+command.label} onClick={()=>void copy(index,command.command)}>Copy command</button>{copyNotice?.index===index&&<p className="field-help" role="status">{copyNotice.message}</p>}</div>)}</div>}
   </>:<p className="fine-print">Save the selected choices to prepare local configuration. No connection is being verified.</p>}
   <button type="button" disabled={loading||saving} onClick={retry}>Recheck MCP and Zowe setup</button><p className="fine-print">Recheck inspects local files and prerequisites. Run returned commands for secure credentials and gateway startup, then review or start MCP servers in VS Code.</p>
  </div>
  <p className="fine-print setup-scope">Setup checks local settings only. Connectivity and conversion are verified separately when the relevant evidence is available.</p>
 </section>;
}
