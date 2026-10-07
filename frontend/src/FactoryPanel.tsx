import React,{useEffect,useState} from 'react';
import {artifactUrl} from './workflow';
import {ProgramKnowledge} from './ProgramInsights';
export {ProgramKnowledge} from './ProgramInsights';

type ValidationView={minimum_distinct_records_per_logic:number;fixture_contract_version:number;seed:string|null;status:'NOT_RUN'|'PASSED'|'RECORDED_PASS'|'GAPS';program_count:number;unit_tests_run:number;unit_tests_passed:boolean|null;job_cases:number|null;evidence:string|null};
type ArchitectureView={title:string;rationale:string;status:string;active_backend:{name:string;implemented:boolean};candidates:{name:string;title:string;selectable:boolean;implementation_status:string;scope:string;rationale:string}[];evidence:{kind:string;path:string;start_line:number;end_line:number;source_hash:string;reason:string;object?:string}[];evidence_count:number;evidence_complete:boolean;obligations:{id:string;title:string;status:string;required_evidence:string[];reference_ids:string[]}[];references:{id:string;title:string;url:string}[];service_design:{default:string;extraction_requires:string[]}};
const validationLabel={NOT_RUN:'Not run yet',PASSED:'Supported scope passed',RECORDED_PASS:'Recorded pass · not freshly verified',GAPS:'Validation gaps remain'};

/** Read-only projection; candidate architectures never act as backend selectors. */
export function FactoryAssurance({view}:{view:{process_id?:string;validation?:ValidationView;target_architecture?:ArchitectureView}}){
 const validation=view.validation,architecture=view.target_architecture;
 return <>{validation&&<div className="run-summary">
  <h3>Logic validation</h3>
  <p><strong>{validationLabel[validation.status]}</strong> · {validation.program_count} programs in the recorded run</p>
  <dl className="usage-grid">
   <div><dt>Minimum distinct valid states per logic item</dt><dd>{validation.minimum_distinct_records_per_logic>0?validation.minimum_distinct_records_per_logic:'Historical contract'}</dd></div>
   <div><dt>Generated unit tests executed</dt><dd>{validation.unit_tests_run} · {validation.unit_tests_passed===null?'Not run':validation.unit_tests_passed?'Passed':'Failed'}</dd></div>
   <div><dt>Job integration cases</dt><dd>{validation.job_cases===null?'Not recorded':validation.job_cases}</dd></div>
   <div><dt>Fixture contract</dt><dd>{validation.fixture_contract_version}</dd></div>
  </dl>
  <p>Expected results are frozen before target execution. Validation requires actual comparisons and adversarial checks; it does not establish observed mainframe parity.</p>
  <details><summary>Replay and validation evidence</summary>
   <p>{validation.fixture_contract_version===4?'Synthetic values are generated at runtime from a recorded random seed. Replay uses that same seed and frozen expectations.':'This process preserves its historical fixture contract and frozen expectations.'}</p>
   <p>Recorded seed: <code>{validation.seed??'Not recorded'}</code></p>
   {validation.evidence&&view.process_id?<a className="download" href={artifactUrl(view.process_id,validation.evidence)}>Download validation evidence</a>:<p>No validation evidence artifact is available yet.</p>}
  </details>
 </div>}
 {architecture&&<div className="run-summary">
  <h3>Target architecture</h3><p><strong>{architecture.title}</strong></p><p>{architecture.rationale}</p>
  <p>Recorded backend: <code>{architecture.active_backend.name}</code> · {architecture.active_backend.implemented?'Bounded adapter available':'Unimplemented target contract'}</p>
  <div className="table-scroll"><table><caption>Current implementation and future target candidate</caption><thead><tr><th scope="col">Target</th><th scope="col">Availability</th><th scope="col">Evidence boundary</th></tr></thead><tbody>{architecture.candidates.map(candidate=><tr key={candidate.name}><th scope="row">{candidate.title}</th><td>{candidate.selectable?'Available for bounded POC':'Future candidate · not implemented'}</td><td>{candidate.scope}<p>{candidate.rationale}</p></td></tr>)}</tbody></table></div>
  <details><summary>Database qualification and source evidence ({architecture.evidence_count})</summary>
   <p>These are qualification requirements for a database target decision. They do not claim that each feature exists in this source or that Oracle is ready to run.</p>
   {architecture.evidence_count===0?<p>No qualifying database source evidence is recorded. This does not prove the application has no database behavior.</p>:<><p>{architecture.evidence_complete?'All recorded architecture evidence is shown.':`Showing ${architecture.evidence.length} of ${architecture.evidence_count} references. Full source dispositions remain in the process reports.`}</p><ul className="compact-list">{architecture.evidence.map((e,index)=><li key={`${e.path}:${e.start_line}:${e.kind}:${index}`}><strong>{e.path}:{e.start_line}–{e.end_line}</strong>{e.object&&<> · {e.object}</>}<p>{e.reason}</p><code>SHA256 {e.source_hash}</code></li>)}</ul></>}
   {architecture.obligations.map(obligation=><div key={obligation.id}><h4>{obligation.title} · Unverified</h4><ul className="compact-list">{obligation.required_evidence.map(item=><li key={item}>{item}</li>)}</ul></div>)}
   <h4>Service boundaries</h4><p>Keep a modular application by default. Extract a service when the following evidence supports it:</p><ul className="compact-list">{architecture.service_design.extraction_requires.map(item=><li key={item}>{item}</li>)}</ul>
   <h4>Platform references</h4><ul className="compact-list">{architecture.references.filter(ref=>/^https:\/\//.test(ref.url)).map(ref=><li key={ref.id}><a href={ref.url} target="_blank" rel="noreferrer">{ref.title}<span className="sr-only"> (opens in a new tab)</span></a></li>)}</ul>
  </details>
 </div>}</>;
}

export function FactoryPanel({processId,status}:{processId:string,status:string}){
 const [view,setView]=useState<any>(null),[error,setError]=useState(''),[cursor,setCursor]=useState(0),[programCursor,setProgramCursor]=useState(0),[revision,setRevision]=useState(0),[loading,setLoading]=useState(true);
 useEffect(()=>{
  const controller=new AbortController();setView(null);setError('');setLoading(true);
  fetch('/api/process/'+encodeURIComponent(processId)+'/factory?after='+cursor+'&program_after='+programCursor,{signal:controller.signal})
   .then(async response=>{if(!response.ok)throw new Error('Factory evidence is unavailable. Refresh to try again.');return response.json();})
   .then(value=>{if(!controller.signal.aborted)setView(value);})
   .catch(reason=>{if(!controller.signal.aborted)setError(reason instanceof Error?reason.message:'Factory evidence is unavailable. Refresh to try again.');})
   .finally(()=>{if(!controller.signal.aborted)setLoading(false);});
  return()=>controller.abort();
 },[processId,status,cursor,programCursor,revision]);
 useEffect(()=>{setCursor(0);setProgramCursor(0);},[processId,status]);
 return <section aria-busy={loading}><h2>Modernization factory</h2><p>Capabilities, prerequisites and delivery evidence for this process.</p>
  <button disabled={loading} onClick={()=>{setCursor(0);setProgramCursor(0);setRevision(x=>x+1);}}>Refresh factory evidence</button>
  {loading&&<p role="status">Loading factory evidence…</p>}{error&&<p role="alert" className="error">{error}</p>}
  {view&&<><p>Stage: {view.stage.replaceAll('_',' ')} · {view.total} unresolved obligations · {view.transactions.length} declared transactions</p><p>{view.scope}</p>
   <FactoryAssurance view={view}/>
   {view.program_insights&&<ProgramKnowledge view={view.program_insights} onPage={setProgramCursor} busy={loading}/>}
   <div className="table-scroll"><table><caption>Mainframe capability evidence</caption><thead><tr><th scope="col">Capability</th><th scope="col">Evidence state</th><th scope="col">Sources</th><th scope="col">Gaps</th></tr></thead><tbody>{view.capabilities.map((item:any)=><tr key={item.id}><th scope="row">{item.label}</th><td>{item.state.replaceAll('_',' ')}</td><td>{item.source_count}</td><td>{item.gap_count}</td></tr>)}</tbody></table></div>
   {view.transactions.map((tx:any)=><p key={tx.id}><strong>{tx.id} → {tx.program}</strong>: {tx.state.replaceAll('_',' ')} {tx.api||''}. Native CICS equivalence unverified.</p>)}
   <details><summary>Open obligations ({view.total})</summary>{view.obligations.length===0?<p>No obligations are recorded in this view. The verification and report gates still apply.</p>:view.obligations.map((item:any)=><p key={item.id}><strong>{item.kind}</strong>: {item.requirement}</p>)}<p>Showing {view.obligations.length?cursor+1:0}–{cursor+view.obligations.length} of {view.total}</p><button disabled={cursor===0} onClick={()=>setCursor(Math.max(0,cursor-50))}>Previous obligations</button> <button disabled={!view.has_more} onClick={()=>setCursor(view.next_after)}>Next obligations</button></details>
   {view.consistency.length>0&&<div role="alert" className="error">{view.consistency.map((finding:any)=><p key={finding.id}>{finding.message}</p>)}</div>}
  </>}
 </section>;
}
