export type ProcessState = {status:string;assistant_mode?:string;resume_status?:string;cancel_requested?:boolean;artifacts?:string[];executive_report?:string|null;executive_error?:string|null;source_files?:Record<string,string>;packet_issued?:boolean;packet_imported?:boolean;verification_finished?:boolean;report_verified?:boolean};
export type NextAction = {title:string;description:string;label?:string;action?:'start'|'resume'|'review'|'report'|'evidence'|'copilot'|'requirements';tone:'neutral'|'attention'|'success';stage:number};

/** Operational states stay explicit: a completed run is not a parity claim. */
export function nextAction(process:ProcessState):NextAction {
 if(process.executive_error)return {title:'Report evidence needs attention',description:'The accepted report could not be validated. Inspect the integrity issue below before using its results.',label:'Inspect evidence',action:'evidence',tone:'attention',stage:4};
 if(process.cancel_requested&&['COMPLETED','COMPLETED_WITH_BLOCKERS','CANCELLED'].includes(process.status))return {title:'Cancelled · evidence is ready',description:'Processing has stopped. Preserved evidence records what ran and what remains unresolved.',label:process.executive_report?'Open executive report':'View available evidence',action:process.executive_report?'report':'evidence',tone:'attention',stage:-1};
 if(process.cancel_requested)return {title:'Cancellation requested',description:'The worker will stop at a safe checkpoint. Existing evidence is preserved.',tone:'attention',stage:-1};
 const checkpoint:Record<string,number>={READY:0,QUEUED_ANALYSIS:1,ANALYZING:1,WAITING_DISCOVERY:1,WAITING_REQUIREMENTS:1,WAITING_COPILOT:1,WAITING_SME:2,QUEUED_VERIFY:3,VERIFYING:3,QUEUED_REPORT:4,REPORTING:4};
 switch(process.status){
  case 'READY':return {title:'Your inputs are ready',description:process.assistant_mode==='copilot_chat'?'Map the selected jobs and their dependencies first, then let Claude analyze the local evidence before the one SME packet.':'Start source analysis to prepare the single SME review packet.',label:'Start analysis',action:'start',tone:'neutral',stage:0};
  case 'WAITING_DISCOVERY':return {title:'Lineage discovery needs evidence',description:'Selected-job dependencies have named gaps. Resolve the source or read-only lookup issues, then retry discovery. Changed original inputs require a new process; the SME packet has not been issued.',label:'Open retrieval request',action:'copilot',tone:'attention',stage:1};
  case 'WAITING_REQUIREMENTS':return {title:'Choose what to convert',description:'Review the complete source breakdown. All items default to Yes. Save your Yes/No choices to the requirements Markdown before conversion begins.',label:'Select requirements',action:'requirements',tone:'attention',stage:1};
  case 'WAITING_COPILOT':return {title:'Ready for Claude Code analysis',description:'Claude reads the frozen local files and handles analysis, development, testing and review without MCP. Copilot retrieves missing files only.',label:'Open Claude workspace',action:'copilot',tone:'attention',stage:1};
  case 'WAITING_SME':return {title:'Ready for a human review',description:'Download the one review packet, then import the completed workbook with the actual reviewer’s name.',label:'Review the packet',action:'review',tone:'attention',stage:2};
  case 'PAUSED':return {title:'This process is paused',description:'Resume from its recorded checkpoint when you are ready.',label:'Resume process',action:'resume',tone:'attention',stage:checkpoint[process.resume_status||'']??-1};
  case 'FAILED':return {title:'This process needs attention',description:'Inspect the recorded issue below, resolve its cause, then resume.',label:'Resume process',action:'resume',tone:'attention',stage:checkpoint[process.resume_status||'']??-1};
  case 'REPORTING_FAILED':return {title:'The report needs attention',description:'Resolve the recorded issue, then retry reporting. Recorded evidence is preserved.',label:'Retry reporting',action:'resume',tone:'attention',stage:4};
  case 'COMPLETED':return {title:'The local review is complete',description:'The supported source-derived profile passed its recorded gates. Review the executive report and remaining scope limits.',label:process.executive_report?'Open executive report':'View reports',action:process.executive_report?'report':'evidence',tone:'success',stage:5};
  case 'COMPLETED_WITH_BLOCKERS':return {title:'Results are ready, with open gaps',description:'Processing is finished. The report keeps unsupported behavior and unresolved evidence visible.',label:process.executive_report?'Open executive report':'View reports',action:process.executive_report?'report':'evidence',tone:'attention',stage:5};
  case 'CANCELLED':return {title:'This process was cancelled',description:'Recorded evidence remains available. Start a new process for changed inputs.',label:'View available evidence',action:'evidence',tone:'attention',stage:0};
  case 'QUEUED_ANALYSIS':case 'ANALYZING':return {title:'Understanding your source',description:'The worker is analyzing the frozen export and preparing the review packet. You can leave this page open.',tone:'neutral',stage:1};
  case 'QUEUED_VERIFY':case 'VERIFYING':return {title:'Checking the generated behavior',description:'The worker is comparing synthetic results with expectations frozen from the source.',tone:'neutral',stage:3};
  case 'QUEUED_REPORT':case 'REPORTING':return {title:'Preparing the decision report',description:'The worker is assembling coverage, test results and management evidence.',tone:'neutral',stage:4};
  default:return {title:'Process status is available',description:'Inspect its recorded activity and evidence before taking the next step.',label:'View available evidence',action:'evidence',tone:'neutral',stage:0};
 }
}

export function recordedStages(process:ProcessState):boolean[]{return [Object.keys(process.source_files||{}).length>0,!!process.packet_issued,!!process.packet_imported,!!process.verification_finished,!!process.report_verified&&!process.executive_error];}
export function processStatusLabel(process:ProcessState):string{return process.cancel_requested?(['COMPLETED','COMPLETED_WITH_BLOCKERS','CANCELLED'].includes(process.status)?'Cancelled · evidence ready':'Cancellation requested'):statusLabel(process.status);}

export function statusLabel(status:string):string {
 const labels:Record<string,string>={READY:'Ready to start',WAITING_DISCOVERY:'Needs lineage evidence',WAITING_REQUIREMENTS:'Select requirements',WAITING_COPILOT:'Needs Claude analysis',WAITING_SME:'Needs SME review',PAUSED:'Paused',FAILED:'Needs attention',REPORTING_FAILED:'Report needs attention',COMPLETED:'Local review complete',COMPLETED_WITH_BLOCKERS:'Complete with gaps',CANCELLED:'Cancelled',QUEUED_ANALYSIS:'Analysis queued',ANALYZING:'Mapping lineage and source',QUEUED_VERIFY:'Verification queued',VERIFYING:'Verifying',QUEUED_REPORT:'Report queued',REPORTING:'Creating report'};
 return labels[status]||status.replaceAll('_',' ').toLowerCase();
}

export function artifactUrl(processId:string,file:string,inline=false):string {
 return `/api/process/${encodeURIComponent(processId)}/artifact?path=${encodeURIComponent(file)}${inline?'&inline=true':''}`;
}

/** File reads can finish in any order; only the newest selection may publish. */
export function createSelectionGate(){let revision=0;return {begin:()=>++revision,isCurrent:(ticket:number)=>ticket===revision,invalidate:()=>{revision++;}};}
