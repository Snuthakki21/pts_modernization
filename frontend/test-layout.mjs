import assert from 'node:assert/strict';
import test from 'node:test';
import {readFile} from 'node:fs/promises';
import {fileURLToPath} from 'node:url';
import path from 'node:path';

const here=path.dirname(fileURLToPath(import.meta.url));
const stylesheet=await readFile(process.env.UI_LAYOUT_STYLES||path.join(here,'src/style.css'),'utf8');
const onlineSource=await readFile(path.join(here,'src/online.tsx'),'utf8');
const onlineStyles=onlineSource.match(/<style>\{`([^`]+)`\}<\/style>/)?.[1];
assert.ok(onlineStyles,'Online pilot must provide its delivered styles.');
// Resolve top-level declarations only; media variants are exercised in the browser matrix.
function declarations(css,selector){
 const source=css.replace(/\/\*[\s\S]*?\*\//g,'');
 const result={};let cursor=0;
 while(cursor<source.length){
  const open=source.indexOf('{',cursor);if(open<0)break;
  const name=source.slice(cursor,open).trim();let depth=1,end=open+1;
  while(end<source.length&&depth){if(source[end]==='{')depth++;else if(source[end]==='}')depth--;end++;}
  assert.equal(depth,0,'CSS block must close.');
  if(name===selector)for(const entry of source.slice(open+1,end-1).split(';').filter(Boolean)){const cut=entry.indexOf(':');result[entry.slice(0,cut).trim()]=entry.slice(cut+1).trim();}
  cursor=end;
 }
 return result;
}
const tokens=declarations(stylesheet,':root');
function resolve(value){return value.replace(/var\((--[^),]+)(?:,[^)]+)?\)/g,(_,name)=>{assert.ok(tokens[name],`Missing token ${name}`);return tokens[name];});}
function hex(value){const match=resolve(value).match(/#([0-9a-f]{6}|[0-9a-f]{3})(?![0-9a-f])/i);assert.ok(match,`Missing hex color in ${value}`);return match[1].length===3?match[1].split('').map(c=>c+c).join(''):match[1];}
function luminance(value){const colors=hex(value).match(/../g).map(channel=>parseInt(channel,16)/255).map(channel=>channel<=.04045?channel/12.92:((channel+.055)/1.055)**2.4);return colors[0]*.2126+colors[1]*.7152+colors[2]*.0722;}
function contrast(first,second){const values=[luminance(first),luminance(second)].sort((a,b)=>a-b);return (values[1]+.05)/(values[0]+.05);}
function expectContrast(foreground,background,minimum,description){const actual=contrast(foreground,background);assert.ok(actual>=minimum,`${description}: ${actual.toFixed(3)} < ${minimum}`);}

test('interactive field boundaries are visible against white and application canvas',()=>{
 const fields=declarations(stylesheet,'input,textarea,select');
 for(const surface of ['#ffffff',tokens['--canvas']])expectContrast(fields.border,surface,3,'Input boundary');
});
test('normal text and informative placeholders meet AA on their actual surface',()=>{
 const root=declarations(stylesheet,':root');
 expectContrast(root.color,root.background,4.5,'Body copy');
 expectContrast(declarations(stylesheet,'input,textarea,select').color,'#ffffff',4.5,'Input value');
 const placeholder=declarations(stylesheet,'input::placeholder,textarea::placeholder');
 expectContrast(placeholder.color,'#ffffff',4.5,'Placeholder text');
 assert.equal(placeholder.opacity,'1','Placeholder contrast must not be weakened by browser opacity.');
 for(const selector of ['.badge','.badge.attention','.comparison-status','.comparison-status.gap','.comparison-status.omitted','.error']){
  const style=declarations(stylesheet,selector);expectContrast(style.color,style.background,4.5,selector);
 }
});
test('primary text and the shared keyboard focus indicator meet contrast thresholds',()=>{
 const primary=declarations(stylesheet,'button.primary,.button.primary');
 expectContrast(primary.color,primary.background,4.5,'Primary button text');
 for(const surface of ['#ffffff',tokens['--canvas']])expectContrast(tokens['--focus'],surface,3,'Focus indicator');
});
test('Windows system typography is available without an external font download',()=>{
 assert.match(declarations(stylesheet,':root')['font-family'],/^"Segoe UI",/);
 assert.doesNotMatch(stylesheet,/@font-face|@import\s+(?:url\()?['"]?https?:/i);
});
test('delivered online pilot uses the canonical system typography and control colors',()=>{
 const pilot=declarations(onlineStyles,'.online-pilot');
 assert.equal(pilot['font-family'],declarations(stylesheet,':root')['font-family']);
 assert.equal(hex(pilot.color),hex(tokens['--ink']));
 const fields=declarations(onlineStyles,'.online-pilot input,.online-pilot select,.online-pilot button');
 expectContrast(fields.border,fields.background,3,'Online control boundary');
 expectContrast(fields.color,fields.background,4.5,'Online control text');
 const preview=declarations(onlineStyles,'.online-pilot .bms-preview');
 assert.equal(hex(preview.background),hex(tokens['--canvas']));
 expectContrast(pilot.color,preview.background,4.5,'BMS character layout');
});
test('scrollbar contrast remains visible where data owns horizontal scroll',()=>{
 expectContrast(tokens['--scrollbar-thumb'],tokens['--scrollbar-track'],3,'Scrollbar thumb');
});

test('four-phase controls and long lineage labels have explicit intrinsic sizing and readable space',()=>{assert.equal(declarations(stylesheet,'.process-guide-steps li>button')['min-height'],'78px');assert.equal(declarations(stylesheet,'.process-guide-steps li>button').width,'100%');assert.equal(declarations(stylesheet,'.guide-read-status')['min-height'],'24px');assert.equal(declarations(stylesheet,'.lineage>div').padding,'16px');assert.equal(declarations(stylesheet,'.lineage>div>small')['grid-column'],'1/-1');assert.match(stylesheet,/@media\(max-width:620px\).*?\.lineage>div\{grid-template-columns:minmax\(0,1fr\)/s);});
