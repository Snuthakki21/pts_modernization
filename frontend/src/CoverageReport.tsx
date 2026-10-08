import React,{useEffect,useState} from 'react';

type Row={source_path:string;source_line:number;source_text:string;disposition:string;target_file?:string;target_start?:number;target_end?:number;tests:string[];reason:string;replacement?:string};
type Report={summary:any;files:{path:string;selected:boolean;scope_reason?:string}[];rows:Row[];denominators:Record<string,string>};

export function CoverageReport({processId,status}:{processId?:string;status?:string}){
 const [report,setReport]=useState<Report|null>(null),[error,setError]=useState(''),[file,setFile]=useState(''),[disposition,setDisposition]=useState('');
 useEffect(()=>{setFile('');setDisposition('');},[processId]);
 useEffect(()=>{let active=true;setReport(null);setError('');if(!processId)return;fetch(`/api/process/${processId}/coverage`).then(async r=>{const d=await r.json();if(!r.ok)throw Error(d.error||'Coverage unavailable');if(active)setReport(d);}).catch(e=>{if(active)setError(String(e));});return()=>{active=false;};},[processId,status]);
 if(!processId)return <section><h2>Complete source coverage</h2><p>Select a process to see the source-to-target accounting.</p></section>;
 if(error)return <section><h2>Complete source coverage</h2><p role="alert">{error}</p></section>;
 if(!report)return <section><h2>Complete source coverage</h2><p role="status">Checking the frozen source, target and test evidence…</p></section>;
 const s=report.summary,rows=report.rows.filter(r=>(!file||r.source_path===file)&&(!disposition||r.disposition===disposition));
 return <section><h2>Every source line has a disposition</h2><p>{s.fully_accounted?'The frozen export is fully accounted for.':'The source inventory has an integrity or accounting gap.'} {s.completion_eligible?'All applicable in-scope lines meet the supported-profile evidence gates.':'Unverified or blocked behavior remains. It cannot receive completion credit.'}</p>
 <div className="metrics"><article><small>Exported source lines</small><b>{s.source_lines}</b></article><article><small>Applicable in-scope lines</small><b>{s.applicable_lines}</b></article><article><small>Verified applicable lines</small><b>{s.verified_applicable_lines}</b></article><article><small>Line verification</small><b>{s.line_verification_percent===null?'Unknown':s.line_verification_percent+'%'}</b></article></div>
 <p>Non-executable lines: {s.non_executable_lines}. Explicit out-of-scope lines: {s.out_of_scope_lines}. These are shown separately. Unsupported behavior remains in the applicable denominator.</p>
 {s.integrity_errors?.length>0&&<div role="alert" className="error">{s.integrity_errors.map((v:string,i:number)=><p key={i}>{v}</p>)}</div>}
 <div className="fields"><label>Source file<select value={file} onChange={e=>setFile(e.target.value)}><option value="">All files</option>{report.files.map(f=><option value={f.path} key={f.path}>{f.path}{f.selected?'':' (out of scope)'}</option>)}</select></label><label>Disposition<select value={disposition} onChange={e=>setDisposition(e.target.value)}><option value="">All dispositions</option>{Object.entries(s.dispositions).map(([key,count])=><option value={key} key={key}>{key.replaceAll('_',' ')} ({String(count)})</option>)}</select></label></div>
 <p>{rows.length} rows match. The first 250 are shown; download the coverage workbook or HTML report for the complete source-ordered table.</p>
 <div className="table-scroll" role="region" aria-label="Source line coverage" tabIndex={0}><table><thead><tr><th scope="col">Source</th><th scope="col">Disposition</th><th scope="col">Target mapping</th><th scope="col">Why / replacement / proof</th></tr></thead><tbody>{rows.slice(0,250).map(r=><tr key={`${r.source_path}:${r.source_line}`}><td><strong>{r.source_path}:{r.source_line}</strong><br/><code>{r.source_text}</code></td><td>{r.disposition.replaceAll('_',' ')}</td><td>{r.target_file?<><code>{r.target_file}</code><br/>Lines {r.target_start}–{r.target_end}</>:'No verified target mapping'}</td><td>{r.reason}{r.replacement&&<p><strong>Replacement:</strong> {r.replacement}</p>}<small>{r.tests.length} test witnesses</small></td></tr>)}</tbody></table></div>
 <details><summary>How the percentages are calculated</summary>{Object.entries(report.denominators).map(([key,value])=><p key={key}><strong>{key.replaceAll('_',' ')}:</strong> {value}</p>)}</details>
 </section>;
}
