import React,{useCallback,useEffect,useRef,useState} from 'react';
import {readUtf8Source} from './intakeFiles';

type DevelopmentPacket={handoff_id:string;instructions:string[];work_items:{id:string;title:string;objective:string;count:number}[];development_prompt:string;binding:{task_hash:string;lineage_hash:string;requirements_hash:string|null;adapter_fingerprint:string}};
export type DevelopmentView={status:'NOT_PREPARED'|'READY'|'RETURNED_FOR_REVIEW'|'STALE';packet:DevelopmentPacket|null;result:unknown;next_action:string};
const revisionReasons={REVIEW_FINDINGS:'Review findings',PATCH_NOT_INTEGRATED:'Patch not integrated',ADDITIONAL_WORK:'Additional work'};
type RevisionReason=keyof typeof revisionReasons;
const statuses=['NOT_PREPARED','READY','RETURNED_FOR_REVIEW','STALE'];
const currentPacket=(model:DevelopmentView|null)=>model&&(model.status==='READY'||model.status==='RETURNED_FOR_REVIEW')?model.packet:null;

/** Unknown state fails closed; refresh must retire the current handoff first. */
export function developmentBlocksAnalysis(model:DevelopmentView|null){return model?.status!=='NOT_PREPARED'&&model?.status!=='STALE';}
export function developmentPrompt(packet:Pick<DevelopmentPacket,'development_prompt'|'handoff_id'>){return `${packet.development_prompt}\n\nHandoff ID: ${packet.handoff_id}`;}
export function developmentRevision(handoffId:string,reason:string){
 if(!/^[a-f0-9]{64}$/.test(handoffId))throw Error('A current development handoff is required.');
 if(!Object.hasOwn(revisionReasons,reason))throw Error('Choose a defined development revision reason.');
 return {handoff_id:handoffId,reason};
}
export function DevelopmentRevisionControls({model,processStatus,disabled,reason,onReason,onRevise}:{model:DevelopmentView|null;processStatus:string;disabled:boolean;reason:RevisionReason;onReason:(reason:RevisionReason)=>void;onRevise:()=>void}){
 if(model?.status!=='RETURNED_FOR_REVIEW'||!model.packet||processStatus!=='WAITING_COPILOT')return null;
 return <div className="run-summary"><h4>Send development back for revision</h4><p>Request further work without integrating a rejected patch. This creates a new immutable handoff and preserves the previous packet and receipt.</p><label>Revision reason<select disabled={disabled} value={reason} onChange={event=>onReason(event.target.value as RevisionReason)}>{Object.entries(revisionReasons).map(([value,label])=><option key={value} value={value}>{label}</option>)}</select></label><button disabled={disabled} onClick={onRevise}>Request development revision</button></div>;
}
export function parseDevelopmentReturn(text:string,handoffId:string):Record<string,unknown>{
 const result:unknown=JSON.parse(text);
 if(!result||typeof result!=='object'||Array.isArray(result))throw Error('Return a structured development receipt JSON object.');
 if(!('handoff_id' in result)||result.handoff_id!==handoffId)throw Error('This receipt belongs to a different handoff. Check the current development packet.');
 return result as Record<string,unknown>;
}
export async function readDevelopmentReturn(file:File,handoffId:string){return parseDevelopmentReturn(await readUtf8Source(file,65536),handoffId);}
function DevelopmentReturnEvidence({result}:{result:unknown}){
 if(!result||typeof result!=='object'||Array.isArray(result))return <p>No development receipt details are available.</p>;
 const submission='submission' in result&&result.submission&&typeof result.submission==='object'?result.submission:null;
 const summary=submission&&'summary' in submission&&typeof submission.summary==='string'?submission.summary:null;
 const revision=submission&&'revision' in submission&&typeof submission.revision==='string'?submission.revision:null;
 return <details><summary>Inspect self-reported development receipt</summary><p>These are unverified claims from the development host. Copilot must inspect the actual code and run tests; reported counts and review status do not establish conversion success.</p>{summary&&<p>{summary}</p>}{revision&&<p>Reported revision: <code>{revision}</code></p>}<pre className="development-receipt">{JSON.stringify(result,null,2)}</pre></details>;
}
export function DevelopmentHandoffSummary({model}:{model:DevelopmentView}){
 const packet=currentPacket(model);
 const label={NOT_PREPARED:'Development handoff not prepared',READY:'Ready for standalone Claude Code',RETURNED_FOR_REVIEW:'Returned for Copilot review',STALE:'Previous handoff is stale'}[model.status];
 return <div className="run-summary">
  <p role="status"><strong>{label}</strong></p><p>{model.next_action}</p>
  {model.status==='RETURNED_FOR_REVIEW'&&<p className="notice">The development receipt has not verified the code or cleared any source gaps. Copilot must review the returned work. If changes need more work or were not integrated, request a development revision below. Integrate approved changes, run the required tests, restart the workbench if its loaded adapters changed, then call <code>workbench_refresh_analysis</code> and retrieve a fresh task.</p>}
  {model.status==='RETURNED_FOR_REVIEW'&&<DevelopmentReturnEvidence result={model.result}/>}
  {model.status==='STALE'&&<p>The previous packet cannot be reused for the current analysis. Prepare a new handoff if further development is needed.</p>}
  {packet&&<><p>Handoff <code>{packet.handoff_id.slice(0,12)}</code> · framework and synthetic examples only</p>
   <ul className="compact-list">{packet.work_items.map(item=><li key={item.id}><strong>{item.title}</strong> · {item.count} obligation{item.count===1?'':'s'}<p>{item.objective}</p></li>)}</ul>
   <details><summary>Inspect the development instructions</summary><ul className="compact-list">{packet.instructions.map((instruction,index)=><li key={index}>{instruction}</li>)}</ul><label>Standalone Claude Code prompt<textarea readOnly rows={8} value={developmentPrompt(packet)}/></label></details>
  </>}
 </div>;
}

type Scope={active:boolean;controller:AbortController;version:number;locked:boolean};
export function DevelopmentHandoff({processId,status,token,busy,onBlockedChange}:{processId:string;status:string;token:string;busy:boolean;onBlockedChange:(blocked:boolean)=>void}){
 const [model,setModel]=useState<DevelopmentView|null>(null),[loading,setLoading]=useState(true),[saving,setSaving]=useState(false),[error,setError]=useState(''),[statusError,setStatusError]=useState(''),[feedback,setFeedback]=useState(''),[file,setFile]=useState<File|null>(null),[revisionReason,setRevisionReason]=useState<RevisionReason>('REVIEW_FINDINGS');
 const scopeRef=useRef<Scope|null>(null),notify=useRef(onBlockedChange);notify.current=onBlockedChange;
 const endpoint=`/api/process/${encodeURIComponent(processId)}/development`;
 const load=useCallback(async(scope:Scope,showLoading=false)=>{
  if(!scope.active||scope.locked)return;
  const version=++scope.version;
  if(showLoading){setLoading(true);notify.current(true);}
  try{
   const response=await fetch(endpoint,{signal:scope.controller.signal});const value=await response.json();
   if(!response.ok)throw Error(value.error||'Development handoff is unavailable. Check the running workbench and retry.');
   if(!value||!statuses.includes(value.status))throw Error('The workbench returned an unrecognized development state.');
   if(scope.active&&version===scope.version){setModel(value);setStatusError('');notify.current(developmentBlocksAnalysis(value));}
  }catch(reason){if(scope.active&&version===scope.version){setStatusError(reason instanceof Error?reason.message:'Development status could not be read.');notify.current(true);}}
  finally{if(scope.active&&version===scope.version)setLoading(false);}
 },[endpoint]);
 useEffect(()=>{
  const scope:Scope={active:true,controller:new AbortController(),version:0,locked:false};scopeRef.current=scope;
  setModel(null);setFile(null);setRevisionReason('REVIEW_FINDINGS');setFeedback('');setError('');setStatusError('');setSaving(false);setLoading(true);notify.current(true);
  void load(scope,true);
  const timer=window.setInterval(()=>{if(status==='WAITING_COPILOT')void load(scope);},5000);
  return()=>{scope.active=false;scope.controller.abort();window.clearInterval(timer);};
 },[load,status]);
 async function mutate(kind:'prepare'|'return'|'revise'){
  const scope=scopeRef.current;if(!scope?.active||scope.locked||busy||loading||status!=='WAITING_COPILOT')return;
  const packet=currentPacket(model);
  if(kind==='return'&&(!file||model?.status!=='READY'||!packet))return;
  if(kind==='revise'&&(model?.status!=='RETURNED_FOR_REVIEW'||!packet))return;
  if(kind==='prepare'&&model?.status!=='NOT_PREPARED'&&model?.status!=='STALE')return;
  scope.locked=true;++scope.version;setSaving(true);setError('');setFeedback('');notify.current(true);
  try{
   const body=kind==='return'?await readDevelopmentReturn(file!,packet!.handoff_id):kind==='revise'?developmentRevision(packet!.handoff_id,revisionReason):{};
   if(!scope.active)return;
   const url=kind==='return'?`/api/development/${encodeURIComponent(packet!.handoff_id)}/return`:kind==='revise'?`${endpoint}/revise`:endpoint;
   const response=await fetch(url,{method:'POST',signal:scope.controller.signal,headers:{'Content-Type':'application/json','X-Workbench-Token':token},body:JSON.stringify(body)});
   const value=await response.json();if(!response.ok)throw Error(value.error||'The workbench could not record the development handoff.');
   if(scope.active){setFile(null);setFeedback(kind==='revise'?'Development revision requested. Use the new packet and prompt; the previous receipt remains preserved.':kind==='prepare'?'Development packet prepared. Open standalone Claude Code in an approved framework-only checkout.':'Development receipt recorded for Copilot review. Conversion gates remain in place.');}
  }catch(reason){if(scope.active)setError(reason instanceof Error?reason.message:'The development handoff could not be recorded.');}
  finally{if(scope.active){scope.locked=false;setSaving(false);await load(scope);}}
 }
 const packet=currentPacket(model),working=busy||loading||saving,disabled=working||!!statusError;
 async function copyPrompt(){const scope=scopeRef.current;if(!packet||!scope?.active)return;setFeedback('');try{await navigator.clipboard.writeText(developmentPrompt(packet));if(scope.active)setFeedback('Standalone development prompt copied.');}catch{if(scope.active)setError('Clipboard access is unavailable. Copy the prompt from the development instructions.');}}
 function download(){if(!packet)return;const blob=new Blob([JSON.stringify(packet,null,2)+'\n'],{type:'application/json'}),url=URL.createObjectURL(blob),link=document.createElement('a');link.href=url;link.download=`development-${packet.handoff_id.slice(0,8)}.json`;link.click();window.setTimeout(()=>URL.revokeObjectURL(url),1000);}
 return <div className="knowledge-section" aria-busy={loading||saving}>
  <h3>Development outside VS Code</h3><p>Copilot gathers source evidence in VS Code. Standalone Claude Code develops framework adapters with synthetic examples in an approved framework-only checkout. Copilot then integrates and verifies the returned work.</p>
  <p className="fine-print">Use the development role in <code>examples/claude-mcp.json</code> from an external OS terminal. The MCP role limits bridge tools; it does not isolate local files. Keep exports, credentials and private process evidence out of the Claude checkout.</p>
  {loading&&<p role="status">Checking development status…</p>}
  {model&&<DevelopmentHandoffSummary model={model}/>}
  <div className="form-actions">
   {status==='WAITING_COPILOT'&&(model?.status==='NOT_PREPARED'||model?.status==='STALE')&&<button className="primary" disabled={disabled||!!statusError} onClick={()=>void mutate('prepare')}>{saving?'Preparing…':'Prepare development handoff'}</button>}
   {packet&&<><button disabled={disabled} onClick={download}>Download development packet</button><button disabled={disabled} onClick={()=>void copyPrompt()}>Copy Claude Code prompt</button></>}
   <button disabled={working} onClick={()=>{const scope=scopeRef.current;if(scope)void load(scope,true);}}>Check development status</button>
  </div>
  <DevelopmentRevisionControls model={model} processStatus={status} disabled={disabled} reason={revisionReason} onReason={setRevisionReason} onRevise={()=>void mutate('revise')}/>
  {model?.status==='READY'&&status==='WAITING_COPILOT'&&<details><summary>Import a development receipt manually</summary><p>Prefer the standalone development MCP return tool. This fallback records its structured receipt; it does not apply code, accept test claims, or submit Copilot’s source analysis.</p><label>Development receipt (.json, at most 65,536 bytes)<input key={`${processId}:${packet?.handoff_id}`} type="file" accept=".json" disabled={disabled} onChange={event=>{setFile(event.target.files?.[0]||null);setError('');}}/></label><button disabled={disabled||!file} onClick={()=>void mutate('return')}>Record development receipt</button></details>}
  {feedback&&<p role="status">{feedback}</p>}{statusError&&<p className="error" role="alert">{statusError}</p>}{error&&<p className="error" role="alert">{error}</p>}
 </div>;
}
