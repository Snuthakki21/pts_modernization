import React,{useState} from 'react';

type Check={id:string;status:string;message:string;action?:string};
type Diagnostics={status:'READY'|'BLOCKED';checks:Check[]};

export function SetupDiagnostics({connections}:{connections:Record<string,boolean>}){
 const [result,setResult]=useState<Diagnostics|null>(null),[checking,setChecking]=useState(false),[error,setError]=useState('');
 async function inspect(){
  setChecking(true);setError('');setResult(null);
  try{const r=await fetch('/api/preflight');const d=await r.json();if(!r.ok)throw Error(d.error||'Setup diagnostics unavailable');if(!Array.isArray(d.checks)||!['READY','BLOCKED'].includes(d.status))throw Error('Setup diagnostics returned an unexpected response');setResult(d);}
  catch(e){setError(String(e));}finally{setChecking(false);}
 }
 return <section><div className="sectionhead"><h2>Check this local setup</h2><button className="primary" disabled={checking} onClick={()=>void inspect()}>{checking?'Checking…':'Run setup diagnostics'}</button></div>
 <p>The check reports local prerequisites and actionable setup issues. Local analysis readiness does not establish mainframe connectivity or support for a particular program.</p>
 {error&&<p role="alert" className="error">{error}</p>}
 {checking&&<p role="status">Checking the workspace and local prerequisites…</p>}
 {result&&<><p role="status" className={result.status==='BLOCKED'?'blocker':'notice'}><strong>{result.status==='READY'?'Local setup ready for analysis':'Local setup has blockers'}</strong>. Read every check below before starting. Configured connections still need separate read-only verification.</p><div className="table-scroll"><table><thead><tr><th>Check</th><th>Status</th><th>Finding</th><th>Next action</th></tr></thead><tbody>{result.checks.map((c,i)=><tr key={`${c.id}-${i}`}><td>{c.id.replaceAll('_',' ')}</td><td><span className={'status-pill '+(c.status==='BLOCKED'?'blocked':'')}>{c.status.replaceAll('_',' ')}</span></td><td>{c.message}</td><td>{c.action||'No action reported.'}</td></tr>)}</tbody></table></div></>}
 <h3>Connection configuration</h3><p>Configuration is read from your local environment at startup. “Configured” does not prove that credentials or connectivity work. These checks do not execute anything on the mainframe.</p>
 {Object.entries(connections).map(([key,value])=><p key={key}><span className="dot"/>{key.replaceAll('_',' ')}: {value?'Configured':'Not configured'}</p>)}
 <p>GitHub Copilot Chat requires no model endpoint in the workbench. Model identity and token usage remain Unknown. Zowe: <code>WB_ZOWE_PROFILE</code> and paired <code>WB_ZOWE_ZOSMF_PROFILE</code>. Db2: <code>WB_DB2_MCP_URL</code> and <code>WB_DB2_MCP_TOKEN</code>. Legacy optional provider: <code>WB_LLM_URL</code>, <code>WB_LLM_MODEL</code>, <code>WB_LLM_TOKEN</code> and explicit <code>WB_ALLOW_SOURCE_EGRESS=true</code>.</p>
 <p>See <code>START_HERE.md</code> for setup and <code>docs/TECHNICAL_REFERENCE.md</code> for recovery and the inputs each process needs. The Knowledge tab shows the application utility file you can edit before intake.</p>
 </section>;
}
