import React,{useEffect,useState} from 'react';
import {artifactUrl} from './workflow';

type Counts={total:number;selected:number;verified:number;gaps:number;excluded:number;unclassified:number};
type Filter='all'|'gaps'|'verified'|'excluded';
type TraceabilitySummary={source_units:number;identified_logic_units:number;linked_scope_requirements:number;unclassified_obligations:number;selected:number;excluded:number;verified_source_derived:number;unmet_selected:number;target_mapping_links:number;unique_target_spans:number;requirements_linked_units:number;requirements_unlinked_units:number;observed_mainframe_parity:string};
type RequirementLink={id:string;kind:string;selected:boolean;status:string;source_start:number;source_end:number};
type Requirement={id:string;inventory_id:string;kind:string;selection:string;selection_basis:string;linked_requirements:RequirementLink[];linked_requirement_count:number;links_complete:boolean;markdown:string|null;revision:string|null;sme_approval:string};
type TraceabilityGap={kind:string;reason:string;resolution:string;owner:string;risk:string};
type Fulfillment={state:string;explanation:string;observed_mainframe_parity:string;risk:string;owner:string};
type Gate={id:string;kind:string;scope:string;program?:string;source_rule_id?:string;reason:string;resolution:string;facts?:Record<string,unknown>;evidence?:string[];details_complete:boolean;classification?:string;closure_evidence?:string[];owner?:string;risk?:string};
type Rule={requirement?:Requirement;fulfillment?:Fulfillment;traceability_missing?:TraceabilityGap[];evidence_matrix?:Record<string,unknown>;cics_screens?:string[];id:string;source_rule_id:string;category:string;status:string;description:string;description_complete:boolean;modernized_behavior:string;behavior_complete:boolean;source_path:string;source_version:string;source_start:number;source_end:number;source_excerpt:string;source_excerpt_complete:boolean;targets:{file:string;version:string;start:number;end:number;text:string;excerpt_complete:boolean;excerpt_available:boolean}[];target_count:number;targets_complete:boolean;tests:string[];tests_count:number;tests_complete:boolean;evidence:Record<string,unknown>[];evidence_count:number;evidence_complete:boolean;memberships:{job:string;step:string;program:string}[];memberships_count:number;memberships_complete:boolean;programs:string[];gaps:Gate[];gap_count:number;gaps_complete:boolean;program_gates:Gate[];program_gate_count:number;program_gates_complete:boolean;diagnostics_recorded:boolean};
export type ComparisonModel={traceability_contract_version?:number;traceability_summary?:TraceabilitySummary;inventory_traceability_summary?:TraceabilitySummary;cics_contract_version?:number|null;downloadable_evidence:string[];process_id:string;basis:string;programs:{key:string;program:string;source_path:string;source_version:string;counts:Counts;traceability_summary?:TraceabilitySummary}[];unassigned_count:number;inventory_counts:Counts;counts:Counts;matching_total:number;after:number;limit:number;next_after:number|null;rules:Rule[];process_gates:Gate[];process_gate_count:number;process_gates_complete:boolean;snapshot:{report:string;inventory:string;html:string;coverage:string;inventory_sha256:string;created:string|null}};
const labels:Record<string,string>={converted_verified:'Verified at report acceptance',implemented_unverified:'Python candidate · unverified',identified:'No implementation evidence',blocked:'Verification blocked',excluded_by_requirements:'Selected No · intentionally omitted'};
const filterLabels:[Filter,string][]=[['all','All'],['gaps','Gaps only'],['verified','Verified'],['excluded','Selected No']];

function GateDetails({gate,processId,downloadableEvidence}:{gate:Gate;processId:string;downloadableEvidence:string[]}){
 const facts=gate.facts||{};
 return <div className="comparison-gate"><p><strong>{gate.program&&`${gate.program} · `}{gate.scope==='process'?`Whole-process gate${gate.source_rule_id?` · ${gate.source_rule_id}`:''}`:gate.scope==='program'?'Whole-program gate':gate.scope==='rule'?`Rule gate · ${gate.source_rule_id}`:'Affected source span'}</strong><br/>{gate.reason}</p>
 {gate.kind==='sme_unresolved'&&<p><strong>Returned answer:</strong> {typeof facts.answer==='string'?facts.answer:'Unknown'}<br/><strong>Correction:</strong> {typeof facts.correction==='string'?(facts.correction||'None recorded'):'Unknown'}<br/><strong>Reviewer:</strong> {typeof facts.reviewer==='string'?facts.reviewer:'Unknown'}</p>}
 {facts.credit_scope==='whole_program'&&<p className="fine-print">This rule’s unresolved review prevents whole-program verification credit.</p>}
 {typeof facts.required==='number'&&typeof facts.observed==='number'&&<p className="gap-fact">{facts.observed} of {facts.required} required distinct states observed.</p>}
 {typeof facts.branch==='string'&&<p>Missing branch witness: <strong>{facts.branch}</strong>.</p>}
 {typeof facts.difference_count==='number'&&<p>{facts.difference_count} differing target cases. {Array.isArray(facts.case_ids)&&<>Case IDs: {facts.case_ids.join(', ')}{facts.case_ids_complete===false?' (preview)':''}.</>}</p>}
 <p><strong>Evidence needed to resolve:</strong> {gate.resolution}</p>
 {gate.classification&&<p className="fine-print">Gap class: {gate.classification.replaceAll('_',' ')} · Owner: {gate.owner||'Unknown'} · Risk: {gate.risk||'Unknown'}</p>}
 {gate.closure_evidence&&gate.closure_evidence.length>0&&<details><summary>Required closure evidence</summary><ul>{gate.closure_evidence.map((item,index)=><li key={index}>{item}</li>)}</ul><p className="fine-print">Closure guidance describes required evidence; it does not mark the gap resolved.</p></details>}
 {gate.evidence&&gate.evidence.length>0&&<ul className="comparison-receipts">{gate.evidence.map((path,i)=><li key={i}>{downloadableEvidence.includes(path)?<a href={artifactUrl(processId,path)}>{path}</a>:<span>{path} · preserved local reference</span>}</li>)}</ul>}
 {Object.keys(facts).length>0&&<details><summary>Recorded gate facts</summary><pre>{JSON.stringify(facts,null,2)}</pre></details>}
 {!gate.details_complete&&<p className="fine-print">Some details are abbreviated. The full frozen inventory and receipts retain the evidence.</p>}
 </div>;
}

function comparisonTone(rule:Rule){
 if(rule.status==='excluded_by_requirements')return 'omitted';
 if(rule.gap_count>0||rule.program_gate_count>0||rule.status==='blocked')return 'gap';
 return rule.status==='converted_verified'?'verified':'pending';
}

function RequirementSatisfaction({rule}:{rule:Rule}){
 const no=rule.status==='excluded_by_requirements';
 const verified=rule.status==='converted_verified'&&rule.gap_count===0&&rule.program_gate_count===0;
 const requirement=rule.requirement;
 return <section className="comparison-satisfaction" aria-label="Requirement satisfaction">
  <h4>How the requirement is addressed</h4>
  <p><strong>{no?'Intentionally omitted':verified?'Satisfied within accepted source-derived evidence':'Not yet verified'}</strong></p>
  <p>{no?'Not converted because selected No in requirements.':rule.fulfillment?.explanation||rule.modernized_behavior||'No implementation explanation was recorded.'}</p>
  {!rule.behavior_complete&&<p className="fine-print">The recorded explanation is abbreviated; the frozen inventory retains the full text.</p>}
  <dl className="comparison-facts">
   <dt>Source logic obligation</dt><dd>{rule.source_rule_id} · {rule.category.replaceAll('_',' ')}</dd>
   <dt>Saved selection</dt><dd>{requirement?.selection||(no?'No':'Unknown')} · {requirement?.selection_basis||'Saved requirement linkage was not recorded in this historical report.'}</dd>
   <dt>SME approval</dt><dd>{requirement?.sme_approval||'Unknown'} · default scope is not reviewer approval</dd>
   <dt>Observed mainframe parity</dt><dd>Unknown · source-derived verification does not establish live parity</dd>
  </dl>
  {requirement?.markdown&&<p className="comparison-location">Saved requirements: {requirement.markdown}{requirement.revision?` · revision ${requirement.revision}`:''}</p>}
  {requirement&&requirement.linked_requirement_count>0&&<details><summary>Linked requirements ({requirement.linked_requirement_count})</summary><ul>{requirement.linked_requirements.map((item,index)=><li key={`${item.id}-${index}`}>{item.id} · {item.kind} · {item.selected?'Yes':'No'} · source lines {item.source_start}–{item.source_end}</li>)}</ul>{!requirement.links_complete&&<p className="fine-print">Showing {requirement.linked_requirements.length} of {requirement.linked_requirement_count} saved links.</p>}</details>}
  {rule.traceability_missing&&rule.traceability_missing.length>0&&<div className="comparison-traceability-gap"><strong>Evidence detail unavailable</strong><ul>{rule.traceability_missing.map((missing,index)=><li key={index}><strong>{missing.kind.replaceAll('_',' ')}</strong>: {missing.reason}<p>Evidence needed: {missing.resolution}</p><p className="fine-print">Owner: {missing.owner||'Unknown'} · Risk: {missing.risk||'Unknown'}</p></li>)}</ul><p className="fine-print">These detail gaps do not rewrite the frozen report’s acceptance status.</p></div>}
 </section>;
}

function ComparisonCard({rule,model}:{rule:Rule;model:ComparisonModel}){
 const no=rule.status==='excluded_by_requirements', gap=rule.gap_count>0||rule.program_gate_count>0;
 const tone=comparisonTone(rule);
 const label=rule.status==='converted_verified'&&tone==='gap'?'Recorded verified state · unresolved gates':labels[rule.status]||'Unknown status · unverified';
 return <article className={`comparison-card${gap?' has-gap':''}`} aria-labelledby={`title-${rule.id}`}>
  <details className="comparison-unit">
   <summary className="comparison-unit-summary">
    <span className="comparison-summary-content"><span className="comparison-unit-title"><span id={`title-${rule.id}`} className="comparison-description">{rule.description}{!rule.description_complete?'…':''}</span><span className="comparison-owner">{rule.programs.length?rule.programs.join(' · '):'Source outside parsed program ownership'} · {rule.source_rule_id} · {rule.category.replaceAll('_',' ')}{rule.cics_screens?.length?` · ${rule.cics_screens.join(' · ')}`:''}</span><span className="comparison-disclosure-hint">View source, replacement and evidence</span></span>
    <span className="comparison-unit-state"><span className={`comparison-status ${tone}`}>{label}</span><span className="comparison-unit-counts">{no?'Selected No':`${rule.target_count} target mappings · ${rule.tests_count} test witnesses`}{gap?` · ${rule.gap_count} span gaps${rule.program_gate_count?` · ${rule.program_gate_count} program / rule gates`:''}`:''}</span></span></span>
   </summary>
   <div className="comparison-unit-detail">
    <div className="comparison-columns">
     <section aria-label="Original source"><h4>{model.cics_contract_version===1?'Mainframe / CICS source logic':'COBOL / source logic'}</h4><p className="comparison-location">{rule.source_path}:{rule.source_start}–{rule.source_end}</p><pre>{rule.source_excerpt||'Source excerpt was not recorded. Inspect the frozen source version and span.'}</pre>{!rule.source_excerpt_complete&&<p className="fine-print">Source excerpt abbreviated; full text is in the frozen inventory.</p>}</section>
     <section aria-label="Modernized implementation"><h4>{model.cics_contract_version===1?'Python / FastAPI replacement':'Python / database replacement'}</h4>{no?<p className="comparison-empty">Not converted because selected No in requirements.</p>:rule.targets.length?rule.targets.map((target,i)=><div key={i}><p className="comparison-location">{target.file}:{target.start}–{target.end}</p>{target.excerpt_available?<pre>{target.text||'The recorded target span is empty.'}</pre>:<p className="comparison-empty">Target excerpt was not recorded in this historical report. Inspect the version-bound mapping.</p>}{!target.excerpt_complete&&<p className="fine-print">Python excerpt abbreviated; full text is in the frozen inventory.</p>}</div>):<p className="comparison-empty">No Python implementation evidence is recorded for this span.</p>}{!no&&!rule.targets_complete&&<p className="fine-print">Showing {rule.targets.length} of {rule.target_count} mappings. The full inventory retains all mappings.</p>}{!no&&rule.targets.length>0&&<p className="fine-print">{tone==='verified'?'Satisfied the accepted source-derived verification gates.':'Candidate code has not satisfied the verification gates.'}</p>}</section>
    </div>
    <RequirementSatisfaction rule={rule}/>
    {gap&&<section className="comparison-gap" aria-label="Specific conversion gap"><h4>Specific gap and closure evidence</h4><p className="fine-print">Affected source: {rule.source_path}:{rule.source_start}–{rule.source_end}. This location identifies the affected span; program-wide gates below may be the cause.</p>{rule.gaps.map(g=><GateDetails key={g.id} gate={g} processId={model.process_id} downloadableEvidence={model.downloadable_evidence}/>)}{!rule.gaps_complete&&<p className="fine-print">Showing {rule.gaps.length} of {rule.gap_count} recorded gap reasons and process gates. Download the full frozen inventory for every item.</p>}
     {!rule.diagnostics_recorded&&<p className="notice">Some specific diagnostics were not recorded by this historical inventory. Inspect its referenced receipts; specific missing counts are unknown.</p>}
     {rule.program_gate_count>0&&<details><summary>Recorded program and rule gates ({rule.program_gate_count})</summary>{rule.program_gates.map((g,i)=><GateDetails key={`${g.id}-${i}`} gate={g} processId={model.process_id} downloadableEvidence={model.downloadable_evidence}/>)}{!rule.program_gates_complete&&<p>Showing {rule.program_gates.length} of {rule.program_gate_count} gates. Download the full frozen inventory for every gate.</p>}</details>}
    </section>}
    <details className="comparison-proof"><summary>Versions, tests and evidence</summary><p>Stable comparison ID: {rule.id}</p><p>Source version: <code>{rule.source_version}</code></p>{rule.targets.map((t,i)=><p key={i}>Target version: <code>{t.version}</code> · {t.file}</p>)}<p>{rule.tests_count} recorded test witnesses and {rule.evidence_count} evidence references. Whole-program evidence can be shared across rules.</p>
     {rule.tests.length>0&&<details><summary>Test witness IDs</summary><pre>{rule.tests.join('\n')}</pre>{!rule.tests_complete&&<p>Showing {rule.tests.length} of {rule.tests_count} IDs.</p>}</details>}
     {rule.evidence.length>0&&<details><summary>Evidence references</summary><pre>{JSON.stringify(rule.evidence,null,2)}</pre>{!rule.evidence_complete&&<p>Showing {rule.evidence.length} of {rule.evidence_count} references.</p>}</details>}
     {rule.evidence_matrix&&<details><summary>Traceability evidence matrix</summary><pre>{JSON.stringify(rule.evidence_matrix,null,2)}</pre></details>}
     {rule.memberships.length>0&&<p>Job / step: {rule.memberships.map(m=>`${m.job} / ${m.step||'job source'}${m.program?` / ${m.program}`:''}`).join('; ')}{!rule.memberships_complete?` (showing ${rule.memberships.length} of ${rule.memberships_count})`:''}</p>}
     <a href={artifactUrl(model.process_id,model.snapshot.inventory)}>Download full frozen inventory</a>
    </details>
   </div>
  </details>
 </article>;
}

function ComparisonOverview({model}:{model:ComparisonModel}){
 const summary=model.traceability_summary;
 const unmet=summary?.unmet_selected??Math.max(0,model.counts.selected-model.counts.verified);
 return <section className="comparison-overview" aria-label="Legacy and modernized overview">
  <div className="comparison-overview-columns">
   <section><h3>Legacy source</h3><dl className="comparison-facts"><dt>Accounted source units</dt><dd>{summary?.source_units??model.counts.total}</dd><dt>Selected for conversion</dt><dd>{summary?.selected??model.counts.selected}</dd><dt>Selected No</dt><dd>{summary?.excluded??model.counts.excluded}</dd><dt>Unclassified obligations</dt><dd>{summary?.unclassified_obligations??model.counts.unclassified}</dd></dl></section>
   <section><h3>Modernized implementation</h3><dl className="comparison-facts"><dt>Verified source-derived units</dt><dd>{summary?.verified_source_derived??model.counts.verified}</dd><dt>Unique target spans</dt><dd>{summary?.unique_target_spans??'Unknown'}</dd><dt>Source-to-target mapping links</dt><dd>{summary?.target_mapping_links??'Unknown'}</dd><dt>Observed mainframe parity</dt><dd>Unknown</dd></dl></section>
  </div>
  <p className="comparison-overview-outcome">{unmet} selected units remain unverified. {summary?`${summary.requirements_unlinked_units??'Unknown'} units lack a saved requirements link.`:'Target mapping totals and saved requirements linkage were not recorded for this historical report.'}</p>
  <p className="fine-print">Counts cover the selected program before status filters and pagination. Target spans can satisfy several source units; fewer Python spans alone do not prove equivalent behavior.</p>
 </section>;
}

export function ComparisonView({model,program,status,loading,error,onProgram,onStatus,onPage,onRetry,onCoverage}:{model:ComparisonModel|null;program:string;status:Filter;loading:boolean;error:string;onProgram:(value:string)=>void;onStatus:(value:Filter)=>void;onPage:(after:number)=>void;onRetry:()=>void;onCoverage:()=>void}){
 return <section className="program-comparison" aria-labelledby="comparison-title"><div className="sectionhead"><div><h2 id="comparison-title">{model?.cics_contract_version===1?'Mainframe and Python / FastAPI, side by side':'COBOL and Python, side by side'}</h2><p>Review the overview, choose a program and open a logic unit to compare its source, replacement and evidence.</p>{model?.cics_contract_version===1&&<p className="fine-print">Screen layout verification covers selected character fields and presentation. CICS controller, AID, session and data gaps remain separate.</p>}</div><button onClick={onCoverage}>Full source coverage</button></div>
 <div className="comparison-controls"><label htmlFor="comparison-program">Program<select id="comparison-program" value={program} onChange={e=>onProgram(e.target.value)} disabled={loading||!model||!!error}><option value="">All programs and source</option>{model?.programs.map(p=><option key={p.key} value={p.key}>{p.program} · {p.source_path}</option>)}<option value="unassigned">Source outside parsed programs ({model?.unassigned_count??'unknown'})</option></select></label><div className="comparison-filters" role="group" aria-label="Comparison status">{filterLabels.map(([value,label])=><button key={value} aria-pressed={status===value} disabled={loading||!model||!!error} onClick={()=>onStatus(value)}>{label}</button>)}</div></div>
 {loading?<p role="status">Loading the accepted comparison evidence…</p>:error?<div className="error" role="alert"><p>{error}</p><button onClick={onRetry}>Try loading comparison again</button></div>:model?<>
 <ComparisonOverview model={model}/>
 <div className="comparison-counts" aria-label="Selected program totals"><div><strong>{model.counts.total}</strong><span>Source units</span></div><div><strong>{model.counts.verified}</strong><span>Verified</span></div><div><strong>{model.counts.gaps}</strong><span>Gaps</span></div><div><strong>{model.counts.excluded}</strong><span>Selected No</span></div></div>
 {program===''&&model.programs.length>0&&<details className="comparison-program-overview"><summary>Compare programs ({model.programs.length})</summary><div className="comparison-program-list">{model.programs.slice(0,10).map(item=><button key={item.key} className="comparison-program-choice" onClick={()=>onProgram(item.key)}><span><strong>{item.program}</strong><span>{item.source_path}</span></span><span>{item.counts.total} source units · {item.counts.verified} verified · {item.counts.gaps} gaps · {item.counts.excluded} selected No</span></button>)}</div>{model.programs.length>10&&<p className="fine-print">Showing 10 of {model.programs.length} programs. Use the Program selector for every program.</p>}</details>}
 <p className="fine-print">{model.basis} {model.counts.unclassified>0&&`${model.counts.unclassified} unclassified spans have unknown semantic rule counts. `}Shared copybook units may belong to several programs; the complete inventory has {model.inventory_counts.total} unique units.</p>
 {model.process_gate_count>0&&<details className="comparison-process-gates"><summary>Process-wide gates ({model.process_gate_count})</summary><p>These obligations remain open even when the selected program has no conversion gaps.</p>{model.process_gates.map(g=><GateDetails key={g.id} gate={g} processId={model.process_id} downloadableEvidence={model.downloadable_evidence}/>)}{!model.process_gates_complete&&<p>Showing {model.process_gates.length} of {model.process_gate_count} process gates; the full frozen inventory retains every item.</p>}</details>}
 <div className="comparison-pagehead"><p role="status">{model.matching_total} units match · {model.rules.length?`showing ${model.after+1}–${model.after+model.rules.length}`:'none to show'}</p><a href={artifactUrl(model.process_id,model.snapshot.html)}>Download comparison report</a></div>
 {model.rules.length===0?<div className="empty-state"><h3>No source units match these filters</h3><p>{status==='gaps'?'No gaps are recorded in this selected scope. This does not establish observed mainframe parity.':'Choose All or another program to inspect the retained evidence.'}</p></div>:model.rules.map(rule=><ComparisonCard key={rule.id} rule={rule} model={model}/>)}
 <div className="comparison-pagination" aria-label="Comparison pages"><button disabled={model.after===0} onClick={()=>onPage(Math.max(0,model.after-model.limit))}>Previous page</button><button disabled={model.next_after===null} onClick={()=>model.next_after!==null&&onPage(model.next_after)}>Next page</button></div>
 <details className="fine-print"><summary>Accepted snapshot</summary><p>{model.snapshot.report} · {model.snapshot.created||'Report date unavailable'}</p><p>Inventory SHA-256: <code>{model.snapshot.inventory_sha256}</code></p></details>
 </>:<p>Select a process with an accepted report to inspect the comparison.</p>}
 </section>;
}

export function ProgramComparison({processId,status:processStatus,reportPath,onCoverage}:{processId?:string;status?:string;reportPath?:string|null;onCoverage:()=>void}){
 const [model,setModel]=useState<ComparisonModel|null>(null),[program,setProgram]=useState(''),[status,setStatus]=useState<Filter>('all'),[after,setAfter]=useState(0),[loading,setLoading]=useState(false),[error,setError]=useState(''),[retry,setRetry]=useState(0);
 useEffect(()=>{setModel(null);setProgram('');setStatus('all');setAfter(0);},[processId,reportPath]);
 useEffect(()=>{if(!processId)return;const controller=new AbortController();let active=true;setLoading(true);setError('');const query=new URLSearchParams({program,status,after:String(after)});
 fetch(`/api/process/${encodeURIComponent(processId)}/comparison?${query}`,{signal:controller.signal}).then(async response=>{const data=await response.json();if(!response.ok)throw Error(data.error||'Accepted comparison unavailable.');if(active)setModel(data);}).catch(e=>{if(active)setError(e instanceof Error?e.message:String(e));}).finally(()=>{if(active)setLoading(false);});return()=>{active=false;controller.abort();};
 },[processId,reportPath,processStatus,program,status,after,retry]);
 return <ComparisonView model={model} program={program} status={status} loading={loading} error={error} onProgram={value=>{setProgram(value);setAfter(0);}} onStatus={value=>{setStatus(value);setAfter(0);}} onPage={setAfter} onRetry={()=>setRetry(v=>v+1)} onCoverage={onCoverage}/>;
}
