import React,{useEffect,useRef,useState} from 'react';
import {artifactUrl} from './workflow';

export type Requirement={id:string;kind:string;program:string|null;programs?:string[];screen?:string|null;screens?:string[];component?:string|null;required?:boolean;support?:string;diagnostics?:{message:string}[];rule_id:string|null;source_path:string;source_hash:string;start_line:number;end_line:number;description:string;replacement:string;source_excerpt:string;excerpt_complete:boolean;selected:boolean};
type RequirementFilters={programs:string[];screens:string[];kinds:string[]};
export type RequirementDraft={revision:number;catalog_hash:string;excluded_ids:string[]};
export function requirementsDraftIsCurrent(draft:Pick<RequirementDraft,'revision'|'catalog_hash'>,model:{revision:number;catalog_hash:string}){return draft.revision===model.revision&&draft.catalog_hash===model.catalog_hash;}
export function retainRequirementsDraft(drafts:Map<string,RequirementDraft>,processId:string,draft:RequirementDraft|null,expectedDraft?:RequirementDraft|null):RequirementDraft|null{
 if(draft===null){
  const current=drafts.get(processId)??null;
  // An older Save response cannot discard edits made after its editor unmounted.
  if(expectedDraft!==undefined&&current!==expectedDraft)return current;
  drafts.delete(processId);return null;
 }
 const retained={revision:draft.revision,catalog_hash:draft.catalog_hash,excluded_ids:[...draft.excluded_ids].sort()};
 drafts.set(processId,retained);return retained;
}


export function requirementsEditable(model:any,loading:boolean,loadError:string,saving:boolean,conflict:boolean){
 return !!model?.editable&&!loading&&!loadError&&!saving&&!conflict;
}

export function RequirementFilters({filters,program,screen,kind,disabled,onChange}:{filters:RequirementFilters;program:string;screen:string;kind:string;disabled:boolean;onChange:(name:'program'|'screen'|'kind',value:string)=>void}){
 return <div className="fields requirements-filters">
  <label>Program<select value={program} disabled={disabled} onChange={e=>onChange('program',e.target.value)}><option value="">All programs and shared objects</option>{filters.programs.map(value=><option key={value} value={value}>{value}</option>)}</select></label>
  <label>CICS screen<select value={screen} disabled={disabled} onChange={e=>onChange('screen',e.target.value)}><option value="">All screens and source</option>{filters.screens.map(value=><option key={value} value={value}>{value}</option>)}</select></label>
  <label>Logic or component<select value={kind} disabled={disabled} onChange={e=>onChange('kind',e.target.value)}><option value="">All source units</option>{filters.kinds.map(value=><option key={value} value={value}>{value.replaceAll('_',' ')}</option>)}</select></label>
 </div>;
}

export function RequirementChoices({items,excluded,editable,onChange,processId}:{processId?:string;items:Requirement[];excluded:Set<string>;editable:boolean;onChange:(id:string,yes:boolean)=>void}){
 return <div className="table-scroll" role="region" aria-label="Source logic and conversion choices" tabIndex={0}><table className="requirements-table"><caption>Source logic and conversion choices</caption><thead><tr><th scope="col">Convert</th><th scope="col">Mainframe behavior</th><th scope="col">Source evidence</th><th scope="col">Replacement or omission</th></tr></thead><tbody>{items.map(r=>{
  const selected=!excluded.has(r.id);
  return <tr key={r.id}>
   <td><label className="setup-checkbox requirement-choice"><input type="checkbox" aria-label={'Convert '+r.description+' · '+(r.program||r.source_path)+' · '+r.id} disabled={!editable} checked={selected} onChange={e=>onChange(r.id,e.target.checked)}/><span>{selected?'Yes':'No'}</span></label></td>
   <th scope="row">{r.description}<small>{r.programs?.join(', ')||r.program||r.source_path} · {r.kind.replaceAll('_',' ')}</small>{!!r.screens?.length&&<small>Screen {r.screens.join(', ')}</small>}{r.component&&<small>{r.component}</small>}</th>
   <td><details><summary>{r.source_path}:{r.start_line}–{r.end_line}</summary><p>SHA256 {r.source_hash}</p><pre>{r.source_excerpt}</pre>{!r.excerpt_complete&&<p>Excerpt shortened. Download the complete frozen source below to inspect every line.</p>}{processId&&<p><a href={`/api/process/${encodeURIComponent(processId)}/requirements/source?path=${encodeURIComponent(r.source_path)}`}>Download complete frozen source</a></p>}<small>{r.id}</small></details></td>
   <td>{selected?r.replacement:'Not converted because selected No in requirements.'}{selected&&r.required===true&&<p className="fine-print">Required by the source layout or controller. Excluding it leaves a dependency gap until a verified behavior-preserving replacement exists.</p>}{selected&&!!r.diagnostics?.length&&<details><summary>Unresolved source behavior</summary>{r.diagnostics.map((gap,index)=><p key={index}>{gap.message}</p>)}</details>}</td>
  </tr>;
 })}</tbody></table></div>;
}

export function RequirementsPanel({processId,status,token,onSaved,draft=null,onDraftChange}:{processId:string;status:string;token:string;onSaved?:()=>void;draft?:RequirementDraft|null;onDraftChange?:(draft:RequirementDraft|null,expectedDraft?:RequirementDraft|null)=>RequirementDraft|null}){
 const [model,setModel]=useState<any>(null),[excluded,setExcluded]=useState(new Set<string>(draft?.excluded_ids||[])),[after,setAfter]=useState(0),[path,setPath]=useState(''),[search,setSearch]=useState(''),[error,setError]=useState(''),[feedback,setFeedback]=useState(draft?'Unsaved scope choices restored for this process. Save requirements to record them.':''),[loading,setLoading]=useState(true),[saving,setSaving]=useState(false),[reload,setReload]=useState(0),[conflict,setConflict]=useState(false),[loadError,setLoadError]=useState(''),[program,setProgram]=useState(''),[screen,setScreen]=useState(''),[kind,setKind]=useState('');
 const dirty=useRef(!!draft),version=useRef<number|null>(draft?.revision??null),catalogHash=useRef<string|null>(draft?.catalog_hash??null),lock=useRef(false),choices=useRef(excluded),draftNotify=useRef(onDraftChange),activeDraft=useRef<RequirementDraft|null>(draft),searchField=useRef<HTMLInputElement>(null);draftNotify.current=onDraftChange;
 useEffect(()=>{
  const controller=new AbortController();setLoading(true);setLoadError('');setError('');
  const query=new URLSearchParams({after:String(after)});
  if(path)query.set('path',path);if(program)query.set('program',program);if(screen)query.set('screen',screen);if(kind)query.set('kind',kind);
  fetch(`/api/process/${encodeURIComponent(processId)}/requirements?${query}`,{signal:controller.signal}).then(async response=>{
   const data=await response.json();if(!response.ok)throw Error(data.error||'Requirements are not ready');return data;
  }).then(data=>{
   if(controller.signal.aborted)return;
   if(version.current!==null&&!requirementsDraftIsCurrent({revision:version.current,catalog_hash:catalogHash.current||''},data)&&dirty.current){setConflict(true);setLoadError('Requirements changed in another session. Reload saved choices before editing again.');return;}
   version.current=data.revision;catalogHash.current=data.catalog_hash;
   if(!dirty.current){choices.current=new Set(data.excluded_ids);setExcluded(choices.current);}setModel(data);
  }).catch(e=>{if(!controller.signal.aborted)setLoadError(e.message);}).finally(()=>{if(!controller.signal.aborted)setLoading(false);});
  return()=>controller.abort();
 },[processId,status,after,path,program,screen,kind,reload]);
 const editable=requirementsEditable(model,loading,loadError,saving,conflict),current=!!model&&!loading&&!loadError&&!conflict;
 function change(id:string,yes:boolean){
  if(!editable)return;
  dirty.current=true;setFeedback('Unsaved scope changes');const next=new Set(choices.current);if(yes)next.delete(id);else next.add(id);choices.current=next;setExcluded(next);const changedDraft={revision:version.current!,catalog_hash:catalogHash.current!,excluded_ids:[...next]};activeDraft.current=draftNotify.current?.(changedDraft)??changedDraft;
 }
 function filter(name:'program'|'screen'|'kind',value:string){
  if(name==='program')setProgram(value);else if(name==='screen')setScreen(value);else setKind(value);setAfter(0);
 }
 function reloadSaved(){dirty.current=false;activeDraft.current=null;draftNotify.current?.(null);version.current=null;catalogHash.current=null;setConflict(false);setAfter(0);setReload(r=>r+1);setFeedback('Loading saved choices; unsaved edits discarded.');}
 async function save(){
  if(lock.current||!editable)return;const submittedDraft=activeDraft.current;lock.current=true;setSaving(true);setError('');
  try{
   const response=await fetch(`/api/process/${encodeURIComponent(processId)}/requirements`,{method:'POST',headers:{'Content-Type':'application/json','X-Workbench-Token':token},body:JSON.stringify({catalog_hash:model.catalog_hash,revision:model.revision,excluded_ids:[...excluded].sort(),saved_by:'local UI operator'})});
   const data=await response.json();if(!response.ok)throw Error(data.error||'Could not save requirements');
   activeDraft.current=draftNotify.current?.(null,submittedDraft)??null;dirty.current=!!activeDraft.current;version.current=data.requirements.revision;setModel({...model,revision:data.requirements.revision,markdown:data.requirements_artifact,editable:false});setFeedback('Requirements saved. Conversion will use this Markdown revision and continue automatically.');onSaved?.();
  }catch(e){setError(e instanceof Error?e.message:String(e));}finally{lock.current=false;setSaving(false);}
 }
 return <section className="panel requirements-panel">
  <div className="sectionhead"><div><p className="eyebrow">CONVERSION SCOPE</p><h2>Mainframe breakdown and requirements</h2></div><button disabled={saving} onClick={reloadSaved}>Reload saved choices</button></div>
  <p>Every checkbox starts checked: Yes, convert this item. Clear a checkbox to select No and exclude it, then Save. Choices from every page and filter are kept together in this process's requirements Markdown, with an immutable version used for conversion.</p>
  <p>Screen fields, actions and COBOL logic are separate source units when supported source descriptors exist. Yes requests a verified implementation; required dependencies and unsupported behavior remain visible. Scope choices do not answer the separate SME review.</p>
  {error&&<p role="alert">{error}</p>}{loadError&&<><p role="alert">{loadError}</p><p>The previous source view is hidden. Retry loading the current view to preserve your unsaved choices, or reload saved choices to discard edits.</p><button disabled={saving||loading} onClick={()=>setReload(r=>r+1)}>Try loading this view again</button></>}{feedback&&<p role="status">{feedback}</p>}{loading&&<p role="status">Loading source breakdown…</p>}
  {current&&<>
   <div className="summary-grid"><div><span>Exported files</span><strong>{model.files.length}</strong></div><div><span>Source lines retained</span><strong>{model.files.reduce((n:number,f:any)=>n+f.physical_lines,0)}</strong></div><div><span>Selected No</span><strong>{excluded.size}</strong><small>All remaining in-scope items are Yes, including hidden pages</small></div></div>
   <button className="primary" disabled={!editable} onClick={()=>void save()}>{saving?'Saving…':'Save requirements and continue'}</button>
   {model.filters&&<RequirementFilters filters={model.filters} program={program} screen={screen} kind={kind} disabled={saving||loading} onChange={filter}/>}
   <label htmlFor="requirements-source-search">Find a source file<input id="requirements-source-search" ref={searchField} type="search" disabled={saving} value={search} onChange={e=>setSearch(e.target.value)} placeholder="Program, BMS map, copybook, JCL or path"/></label>{search&&<button type="button" disabled={saving} aria-label="Clear source file search" onClick={()=>{setSearch('');searchField.current?.focus();}}>Clear search</button>}
   <label>Source file<select value={path} disabled={saving||loading} onChange={e=>{setPath(e.target.value);setAfter(0);}}><option value="">All in-scope source units</option>{model.files.filter((f:any)=>f.path===path||f.path.toLowerCase().includes(search.toLowerCase())).map((f:any)=><option key={f.path} value={f.path}>{f.path} · {f.kind} · {f.physical_lines} lines{f.in_process_scope?'':' · outside discovered process'}</option>)}</select></label>
   {path&&<p>{model.files.find((f:any)=>f.path===path)?.scope_reason}</p>}
   <p>Showing {model.items.length?after+1:0}–{after+model.items.length} of {model.total} source units in this view. Filters narrow the view before paging; they do not change your choices.</p>
   <RequirementChoices processId={processId} items={model.items} excluded={excluded} editable={editable} onChange={change}/>
   <div className="control-row"><button disabled={loading||saving||after===0} onClick={()=>setAfter(Math.max(0,after-50))}>Previous 50</button><button disabled={loading||saving||!model.has_more} onClick={()=>setAfter(model.next_after)}>Next 50</button><button disabled={!editable} onClick={()=>model.items.forEach((r:Requirement)=>change(r.id,true))}>Check this page: Yes</button><button disabled={!editable} onClick={()=>model.items.forEach((r:Requirement)=>change(r.id,false))}>Clear this page: No</button></div>
   <p>Saved revision: {model.revision||'None'}. Requirements lock when the single SME packet is issued.</p>{model.markdown&&<p><a href={artifactUrl(processId,model.markdown)}>Download saved requirements Markdown</a></p>}
  </>}
 </section>;
}
