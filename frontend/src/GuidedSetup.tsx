import React,{useEffect,useRef,useState} from 'react';
import {SetupGuidance} from './SetupGuidance';

export type SetupQuestion={id:string;title:string;prompt:string;options:{value:string;label:string}[];answer:string|null;status:'UNANSWERED'|'NEEDS_ACTION'|'ANSWERED';action:string};
export type SetupModel={version:number;answers:Record<string,string|null>;questions:SetupQuestion[];actions:{id:string;title:string;action:string}[];next_step:string|null;readiness:{status:'NEEDS_SETUP'|'READY_FOR_INTAKE';answered:number;total:number;remaining:string[]};scope:string};

export function SetupQuestionCard({question,value,onChange,number,total}:{question:SetupQuestion;value:string;onChange:(value:string)=>void;number:number;total:number}){
 return <fieldset className="question-options"><legend><span className="eyebrow">QUESTION {number} OF {total}</span><span className="question-title">{question.title}</span></legend><p id={`help-${question.id}`} className="question-prompt">{question.prompt}</p><div role="group" aria-describedby={`help-${question.id}`}>{question.options.map(option=><label className={`choice ${value===option.value?'selected':''}`} key={option.value}><input type="radio" name={`setup-${question.id}`} value={option.value} checked={value===option.value} onChange={()=>onChange(option.value)}/><span>{option.label}</span><span className="choice-check" aria-hidden="true">{value===option.value?'✓':''}</span></label>)}</div></fieldset>;
}

export function GuidedSetup({model,loading,error,onRetry,onSave,onContinue}:{model:SetupModel|null;loading:boolean;error:string;onRetry:()=>void;onSave:(answers:Record<string,string|null>)=>Promise<SetupModel>;onContinue:()=>void}){
 const [index,setIndex]=useState<number|null>(null),[value,setValue]=useState(''),[saving,setSaving]=useState(false),[feedback,setFeedback]=useState(''),[saveError,setSaveError]=useState('');
 const title=useRef<HTMLHeadingElement>(null);
 const initial=model?Math.max(0,model.questions.findIndex(q=>q.status==='UNANSWERED')):0;
 const activeIndex=index??initial,question=model?.questions[activeIndex];
 useEffect(()=>{setValue(question?.answer||'');setSaveError('');},[question?.id,question?.answer]);
 async function save(){
  if(!question||!value)return;setSaving(true);setSaveError('');
  try{const updated=await onSave({[question.id]:value});const following=updated.questions.findIndex((q,i)=>i>activeIndex&&q.status==='UNANSWERED');setFeedback(`${question.title}: answer saved.`);if(following>=0)setIndex(following);else if(updated.questions.some(q=>q.status==='UNANSWERED'))setIndex(updated.questions.findIndex(q=>q.status==='UNANSWERED'));else setIndex(null);title.current?.focus();}
  catch(error){setSaveError(error instanceof Error?error.message:'The answer could not be saved. Try again.');}finally{setSaving(false);}
 }
 if(loading&&!model)return <section className="setup-card" aria-busy="true"><p className="eyebrow">GUIDED SETUP</p><h2>Loading your setup</h2><p role="status">Checking the saved answers for this workspace…</p></section>;
 if(error)return <section><h2>Refresh setup before continuing</h2><p role="alert" className="error">{error}</p><p>Current readiness could not be confirmed. Your saved answers remain preserved.</p><button onClick={onRetry}>Try loading setup again</button></section>;
 if(!model)return null;
 const allAnswered=model.questions.every(q=>q.status!=='UNANSWERED');
 const editing=index!==null;
 return <section className="setup-card"><div className="sectionhead"><div><p className="eyebrow">GUIDED SETUP</p><h2 ref={title} tabIndex={-1}>{allAnswered&&!editing?'Your setup at a glance':'A few questions. A clear starting point.'}</h2></div><span className="counter">{model.readiness.answered} / {model.readiness.total} answered</span></div><progress className="setup-progress" value={model.readiness.answered} max={model.readiness.total} aria-label="Setup questions answered"/>
 <p className="muted">Your answers stay in this workspace. This guide uses no model requests or tokens.</p>
 <div className="sr-only" role="status">{feedback}</div>{saveError&&<p className="error" role="alert">{saveError}</p>}
 {(!allAnswered||editing)&&question?<><SetupQuestionCard question={question} value={value} onChange={setValue} number={activeIndex+1} total={model.questions.length}/><p className="fine-print">{question.action}</p><SetupGuidance questionId={question.id}/><div className="form-actions"><button className="primary" disabled={!value||saving} onClick={()=>void save()}>{saving?'Saving answer…':editing&&allAnswered?'Save answer':'Save and continue'}<span aria-hidden="true"> →</span></button>{activeIndex>0&&<button disabled={saving} onClick={()=>setIndex(activeIndex-1)}>Previous question</button>}{allAnswered&&editing&&<button disabled={saving} onClick={()=>setIndex(null)}>Back to summary</button>}</div></>:<div className="setup-summary"><div className={`notice ${model.readiness.status==='READY_FOR_INTAKE'?'success':''}`}><h3>{model.readiness.status==='READY_FOR_INTAKE'?'Ready to provide your process':'There are a few setup actions to resolve'}</h3><p>{model.readiness.status==='READY_FOR_INTAKE'?'The questions are complete. Add the process manifest and source export to begin analysis.':'Your answers are saved. Review the actions below and update any answer when its prerequisite is ready.'}</p></div>{model.actions.length>0&&<ul className="action-list">{model.actions.map(action=><li key={action.id}><strong>{action.title}</strong><p>{action.action}</p><SetupGuidance questionId={action.id}/><button className="text-button" onClick={()=>setIndex(model.questions.findIndex(q=>q.id===action.id))}>Update answer<span className="sr-only"> for {action.title}</span></button></li>)}</ul>}<button className="primary" onClick={model.readiness.status==='READY_FOR_INTAKE'?onContinue:()=>setIndex(Math.max(0,model.questions.findIndex(q=>q.id===model.next_step)))}>{model.readiness.status==='READY_FOR_INTAKE'?'Continue to process intake':'Review the next setup action'} <span aria-hidden="true">→</span></button></div>}
 <details className="setup-answers"><summary>Review all setup answers</summary><ul className="answer-list">{model.questions.map((q,i)=><li key={q.id}><div><strong>{q.title}</strong><span>{q.options.find(o=>o.value===q.answer)?.label||'Not answered yet'}{q.status==='NEEDS_ACTION'?' · Action needed':''}</span></div><button disabled={saving} onClick={()=>setIndex(i)}>Edit<span className="sr-only"> {q.title}</span></button></li>)}</ul></details><p className="fine-print">{model.scope}</p>
 </section>;
}
