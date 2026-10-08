import assert from 'node:assert/strict';
import test from 'node:test';
import {build} from './node_modules/esbuild/lib/main.js';
import {mkdir,readFile} from 'node:fs/promises';
import {createRequire} from 'node:module';
import {fileURLToPath} from 'node:url';
import path from 'node:path';

const here=path.dirname(fileURLToPath(import.meta.url));
const output=path.resolve(here,'../.implementation/tmp/ui-accessibility-tests/ui.cjs');
await mkdir(path.dirname(output),{recursive:true});
await build({stdin:{contents:`import React from 'react';import {renderToStaticMarkup} from 'react-dom/server';export const render=(C,props)=>renderToStaticMarkup(React.createElement(C,props));export * from './src/main';export * from './src/RequirementsPanel';export * from './src/DatabasePanel';export * from './src/EconomicsPanel';export * from './src/WorkSessionControls';export * from './src/LineagePanel';export * from './src/online';export * from './src/onlineJson';`,resolveDir:here,loader:'tsx'},bundle:true,platform:'node',format:'cjs',outfile:output,logLevel:'silent'});
const api=createRequire(import.meta.url)(output);

// Inspect the actual App element tree before rendering children. Duplicate sibling
// keys can orphan a previous process's DOM during a selected-process transition.
const appTreeOutput=path.resolve(here,'../.implementation/tmp/ui-accessibility-tests/app-tree.cjs');
await build({stdin:{contents:`import {seed} from 'react';import {App} from './src/main';export function appTree(state,processId,view,evidenceView){seed([state,processId,view,evidenceView]);return App();}`,resolveDir:here,loader:'tsx'},bundle:true,platform:'node',format:'cjs',outfile:appTreeOutput,logLevel:'silent',plugins:[{name:'inspect-app-tree',setup(builder){
 builder.onResolve({filter:/^react$/},()=>({path:'react',namespace:'app-tree'}));
 builder.onResolve({filter:/^react\/jsx-runtime$/},()=>({path:'jsx',namespace:'app-tree'}));
 builder.onResolve({filter:/^react-dom\/client$/},()=>({path:'client',namespace:'app-tree'}));
 builder.onLoad({filter:/.*/,namespace:'app-tree'},args=>({loader:'js',contents:args.path==='client'?'export function createRoot(){return {render(){}}}':args.path==='jsx'?`export const Fragment=Symbol('Fragment');export function jsx(type,props,key){return {type,key:key??null,props};}export const jsxs=jsx;`:`let values=[],index=0;export function seed(next){values=next;index=0;}export function useState(initial){const i=index++;return [i<values.length?values[i]:typeof initial==='function'?initial():initial,()=>{}];}export function useEffect(){}export function useId(){return "fixture-id";}export function useRef(value){return {current:value};}export const Fragment=Symbol('Fragment');export function createElement(type,props,...children){return {type,key:props?.key??null,props:{...props,children}};}export default {createElement,Fragment};`}));
}}]});
const appTreeApi=createRequire(import.meta.url)(appTreeOutput);

test('process navigation has unique sibling keys for the guide and compact database panel',()=>{
 const process={id:'fictional-a',name:'Fictional A',status:'WAITING_REQUIREMENTS',demo:true,artifacts:[],blockers:[],analysis:{rules:[]}};
 const state={processes:[process,{...process,id:'fictional-b',name:'Fictional B'}],portfolio:{},connections:{},token:'private-fixture'};
 const flatten=children=>[children].flat(Infinity).filter(child=>child&&typeof child==='object');
 function check(element){if(!element?.props)return;const children=flatten(element.props.children||[]),keys=new Set();for(const child of children){if(child.key!==null){assert.equal(keys.has(child.key),false,`Duplicate sibling key ${child.key}`);keys.add(child.key);}check(child);}}
 for(const processId of ['fictional-a','fictional-b'])for(const view of ['Overview','Evidence'])check(appTreeApi.appTree(state,processId,view,'SME review'));
});

test('source choices expose behavior in checkbox names and preserve dependency fidelity',()=>{
 const html=api.render(api.RequirementChoices,{items:[{id:'R1',kind:'rule',description:'Keep the employee comparison',program:'APP',source_path:'APP.cbl',source_hash:'a'.repeat(64),start_line:1,end_line:2,replacement:'Verified equivalent required',source_excerpt:'IF EMPLOYEE = REF-EMPLOYEE',excerpt_complete:true,required:true}],excluded:new Set(),editable:true,onChange(){}});
 assert.match(html,/aria-label="Convert Keep the employee comparison/);
 assert.match(html,/behavior-preserving replacement/);
 assert.doesNotMatch(html,/verified redesign/);
});

test('all owned scrolling tables and lineage graphs are named keyboard regions',async()=>{
 const files=['main.tsx','CoverageReport.tsx','RequirementsPanel.tsx','DatabasePanel.tsx','EconomicsPanel.tsx','FactoryPanel.tsx','KnowledgePanel.tsx','ProgramInsights.tsx','SetupDiagnostics.tsx','LineagePanel.tsx'];
 for(const file of files){const source=await readFile(path.join(here,'src',file),'utf8');const regions=source.match(/<div[^>]*className="(?:table-scroll|lineage-graph-scroll)"[^>]*>/g)||[];for(const region of regions){assert.match(region,/role="region"/,file);assert.match(region,/aria-label=/,file);assert.match(region,/tabIndex=\{0\}/,file);}}
});

test('application forms own validation and intake context locks while saving',()=>{
 const review=api.render(api.ReviewPanel,{process:{id:'p',status:'WAITING_SME',artifacts:[]},busy:false,onImport:async()=>{}}),economics=api.render(api.EconomicsPanel,{token:'private-token'}),work=api.render(api.WorkSessionControls,{onStart(){},onStop(){}});
 for(const html of [review,economics,work])assert.match(html,/<form[^>]*novalidate=""/i);
 const intake=api.render(api.Intake,{busy:true,localExport:false,onStart:async()=>{},onError(){}});
 assert.match(intake,/<textarea[^>]*maxLength="16000"[^>]*disabled=""/);
 assert.doesNotMatch(economics,/private-token/);
});

test('protected BMS display values use text semantics while layout previews remain keyboard accessible',()=>{
 const screen={id:'s',mapset:'MAPSET',map:'FORM',rows:24,columns:80,source_path:'FORM.bms',source_hash:'a'.repeat(64),fields:[{id:'STATIC',name:null,width:5,attribute_offset:0,editable:false,initial:'Title',attributes:['PROT']}]};
 const html=api.render(api.ScreenLayout,{screen,values:{},result:{screen:{fields:[{...screen.fields[0],value:'Title'}]}},disabled:false,onChange(){}});
 assert.doesNotMatch(html,/for="screen-STATIC"/);
 assert.match(html,/class="bms-preview"[^>]*role="region"[^>]*aria-label="Rendered BMS character layout"[^>]*tabindex="0"/);
});

test('scope drafts retain independent process choices while source revision changes invalidate their binding',()=>{
 const drafts=new Map(),selected={revision:3,catalog_hash:'a'.repeat(64),excluded_ids:['SECOND','FIRST']};
 api.retainRequirementsDraft(drafts,'process-a',selected);selected.excluded_ids.length=0;
 assert.deepEqual(drafts.get('process-a').excluded_ids,['FIRST','SECOND']);
 api.retainRequirementsDraft(drafts,'process-b',{revision:0,catalog_hash:'b'.repeat(64),excluded_ids:[]});
 assert.equal(api.requirementsDraftIsCurrent(drafts.get('process-a'),{revision:3,catalog_hash:'a'.repeat(64)}),true);
 for(let index=0;index<20;index++){assert.equal(api.requirementsDraftIsCurrent(drafts.get('process-a'),{revision:3,catalog_hash:crypto.randomUUID()}),false);assert.equal(api.requirementsDraftIsCurrent(drafts.get('process-a'),{revision:4+index,catalog_hash:'a'.repeat(64)}),false);}
 api.retainRequirementsDraft(drafts,'process-b',null);assert.equal(drafts.has('process-b'),false);assert.deepEqual(drafts.get('process-a').excluded_ids,['FIRST','SECOND']);
 const source=readFile(path.join(here,'src','main.tsx'),'utf8');return source.then(text=>{assert.equal((text.match(/draft=\{requirementDrafts\.current\.get\(process\.id\)\}/g)||[]).length,2);assert.match(text,/requirementDrafts\.current\.size/);assert.doesNotMatch(text,/localStorage|sessionStorage/);});
});

test('record validation exposes the exact invalid field without changing integer or string behavior',()=>{
 const fields={ACCOUNT:{type:'string',width:8},AMOUNT:{type:'integer',width:18,min:0n,max:999999999999999999n}};
 assert.throws(()=>api.onlineRecord(fields,{ACCOUNT:'421',AMOUNT:'5'}),error=>error instanceof api.OnlineFieldError&&error.field==='ACCOUNT'&&/exactly 8/.test(error.message));
 assert.throws(()=>api.onlineRecord(fields,{ACCOUNT:'00000421',AMOUNT:'NaN'}),error=>error instanceof api.OnlineFieldError&&error.field==='AMOUNT'&&/whole number/.test(error.message));
 const valid=api.onlineRecord(fields,{ACCOUNT:'00000421',AMOUNT:'9007199254740993'});assert.equal(valid.ACCOUNT,'00000421');assert.equal(valid.AMOUNT,9007199254740993n);
 const html=api.render(api.OnlineFields,{fields,values:{ACCOUNT:'421',AMOUNT:'5'},disabled:false,invalidField:'ACCOUNT',onChange(){}});
 assert.match(html,/<input[^>]*id="record-ACCOUNT"[^>]*aria-invalid="true"[^>]*aria-describedby="record-help-ACCOUNT online-error"/);
 assert.doesNotMatch(html,/<input[^>]*id="record-AMOUNT"[^>]*aria-invalid="true"/);
});

test('scenario constraints match backend count/rate domains and validation is presented inline',async()=>{
 const html=api.render(api.EconomicsPanel,{token:''});assert.match(html,/<input[^>]*id="economics-total"[^>]*min="0"[^>]*max="100000000"[^>]*step="1"[^>]*required=""/);
 for(const id of ['low','base','high','capacity'])assert.match(html,new RegExp('<input[^>]*id="economics-'+id+'"[^>]*min="1e-30"[^>]*max="1e15"'));
 const source=await readFile(path.join(here,'src','EconomicsPanel.tsx'),'utf8');assert.match(source,/required=\{!!\(low\|\|base\|\|high\)\}/);assert.match(source,/querySelector<HTMLInputElement>\('input:invalid'\)/);assert.match(source,/economics-form-error/);assert.match(source,/disabled=\{busy\}/);assert.doesNotMatch(source,/reportValidity\(/);
 const database=await readFile(path.join(here,'src','DatabasePanel.tsx'),'utf8');assert.match(database,/fieldErrorFeedback\('database-filter-value'/);assert.match(database,/id="database-filter-error"/);assert.match(database,/if\(filterValueField.current\)filterValueField.current.focus\(\)/);
});

test('online unrelated-operation starts and context changes clear stale record field feedback',async()=>{
 const source=await readFile(path.join(here,'src','online.tsx'),'utf8');
 for(const operation of ['renderScreen','connect','endSession']){
  const start=source.slice(source.indexOf('async function '+operation));const beforeTry=start.slice(0,start.indexOf('try{'));
  assert.match(beforeTry,/setInvalidField\(''\)/,operation);
 }
 const layoutContext=source.slice(source.indexOf('id="online-screen"'));
 assert.match(layoutContext.slice(0,layoutContext.indexOf('</select>')),/setInvalidField\(''\)/);
});

test('late requirement Save completion cannot clear a remounted editor’s newer unsaved draft',async()=>{
 const drafts=new Map();api.retainRequirementsDraft(drafts,'process-a',{revision:3,catalog_hash:'a'.repeat(64),excluded_ids:['OLDER']});
 const submitted=drafts.get('process-a');let settle;const response=new Promise(resolve=>{settle=resolve;});
 const save=response.then(()=>api.retainRequirementsDraft(drafts,'process-a',null,submitted));
 // The old editor unmounts while its request is pending; the new editor edits locally.
 api.retainRequirementsDraft(drafts,'process-a',{revision:3,catalog_hash:'a'.repeat(64),excluded_ids:['NEWER']});const newer=drafts.get('process-a');
 settle();await save;
 assert.strictEqual(drafts.get('process-a'),newer);assert.deepEqual(newer.excluded_ids,['NEWER']);
 assert.equal(api.requirementsDraftIsCurrent(newer,{revision:4,catalog_hash:'a'.repeat(64)}),false,'The preserved older revision must still require conflict recovery.');
});

test('economics unrelated errors cannot select an invalid input from the hidden scenario form',async()=>{
 const source=await readFile(path.join(here,'src','EconomicsPanel.tsx'),'utf8');
 assert.match(source,/const invalid=focusScenario\?scenarioForm\.current\?\.querySelector<HTMLInputElement>\('input:invalid'\):null/);
 assert.match(source,/Save to use it in future reports\.'\);\},true\)/);
 assert.match(source,/retain their original measurements\.'\);\},true\)/);
});

test('a Save with no local draft cannot erase a new default-Yes edit or a newer identical choice set',()=>{
 const drafts=new Map();api.retainRequirementsDraft(drafts,'p',{revision:0,catalog_hash:'a'.repeat(64),excluded_ids:[]});const newer=drafts.get('p');
 api.retainRequirementsDraft(drafts,'p',null,null);assert.strictEqual(drafts.get('p'),newer);
 const submitted=newer;api.retainRequirementsDraft(drafts,'p',{...submitted,excluded_ids:[...submitted.excluded_ids]});const sameChoices=drafts.get('p');
 api.retainRequirementsDraft(drafts,'p',null,submitted);assert.strictEqual(drafts.get('p'),sameChoices,'Equal choice bytes are still a newer edit generation.');
 api.retainRequirementsDraft(drafts,'p',null,sameChoices);assert.equal(drafts.has('p'),false,'The matching completed Save clears only its own draft.');
 api.retainRequirementsDraft(drafts,'p',{revision:0,catalog_hash:'a'.repeat(64),excluded_ids:['NO']});api.retainRequirementsDraft(drafts,'p',null);assert.equal(drafts.has('p'),false,'Explicit Reload saved choices remains an unconditional discard.');
});

test('SME instructions name the actual offline HTML save button in both instructions',()=>{
 const html=api.render(api.ReviewPanel,{process:{id:'p',status:'WAITING_SME',artifacts:[]},busy:false,onImport:async()=>{}});
 assert.equal((html.match(/Save review file/g)||[]).length,2);assert.doesNotMatch(html,/then Save it/);assert.match(html,/return the downloaded file/);
});
