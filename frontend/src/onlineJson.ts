/** JSON numeric literals stay numeric on the wire, including integers beyond 2^53. */
const numberToken=/^-?(?:0|[1-9]\d*)(?:\.\d+)?(?:[eE][+-]?\d+)?$/;
const integerToken=/^-?(?:0|[1-9]\d*)$/;
const maximumDepth=64,maximumNumberLength=256;
export const ONLINE_REQUEST_BYTES=65536;

// Keep decimal/exponent syntax distinct: Python's integer contract rejects 1.0/1e0.
export class OnlineJsonNumber {
 readonly token:string;
 constructor(token:string){
  if(!numberToken.test(token)||integerToken.test(token)||token.length>maximumNumberLength||!Number.isFinite(Number(token)))throw new Error('Invalid decimal JSON number');
  this.token=token;Object.freeze(this);
 }
 toString(){return this.token;}
}
function checkSize(text:string,limit:number){
 if(!Number.isSafeInteger(limit)||limit<1||new TextEncoder().encode(text).length>limit)throw new Error('Online JSON exceeds its byte limit');
}

export function parseOnlineJSON(source:string,limit=1024*1024):any {
 if(typeof source!=='string')throw new TypeError('Online JSON must be text');
 checkSize(source,limit);let position=0;
 const fail=():never=>{throw new SyntaxError('Invalid online JSON at position '+position);};
 const space=()=>{while(/[\x20\t\r\n]/.test(source[position]||'')&&position<source.length)position++;};
 function string():string{
  const start=position++;while(position<source.length){
   const char=source[position++];
   if(char==='"')return JSON.parse(source.slice(start,position));
   if(char==='\\')position++;else if(char.charCodeAt(0)<32)fail();
  }return fail();
 }
 function read(depth:number):any {
  if(depth>maximumDepth)throw new Error('Online JSON nesting exceeds its limit');
  space();const char=source[position];
  if(char==='"')return string();
  if(char==='{'||char==='['){
   const object=char==='{',end=object?'}':']',result:any=object?{}:[],keys=new Set<string>();position++;space();
   if(source[position]===end){position++;return result;}
   for(;;){
    if(object){
     if(source[position]!=='"')fail();const key=string();space();if(source[position++]!==':'||keys.has(key))fail();keys.add(key);
     Object.defineProperty(result,key,{value:read(depth+1),writable:true,enumerable:true,configurable:true});
    }else result.push(read(depth+1));
    space();if(source[position]===end){position++;return result;}
    if(source[position++]!==',')fail();space();
   }
  }
  for(const [literal,value] of [['true',true],['false',false],['null',null]] as const){if(source.startsWith(literal,position)){position+=literal.length;return value;}}
  const match=source.slice(position).match(/^-?(?:0|[1-9]\d*)(?:\.\d+)?(?:[eE][+-]?\d+)?/);
  if(!match)return fail();const token=match[0];position+=token.length;
  if(token.length>maximumNumberLength)throw new Error('Online JSON number exceeds its limit');
  if(!integerToken.test(token))return new OnlineJsonNumber(token);
  const integer=BigInt(token);return integer>=BigInt(Number.MIN_SAFE_INTEGER)&&integer<=BigInt(Number.MAX_SAFE_INTEGER)?Number(token):integer;
 }
 const result=read(0);space();if(position!==source.length)fail();return result;
}

export function stringifyOnlineJSON(value:unknown,indent=0,limit=ONLINE_REQUEST_BYTES):string {
 if(!Number.isInteger(indent)||indent<0||indent>8)throw new Error('Invalid JSON indentation');
 const parents=new Set<object>(),padding=(depth:number)=>' '.repeat(depth*indent);
 function write(item:unknown,depth:number):string{
  if(depth>maximumDepth)throw new Error('Online JSON nesting exceeds its limit');
  if(item===null)return 'null';
  if(typeof item==='string'||typeof item==='boolean')return JSON.stringify(item);
  if(typeof item==='bigint'){
   const token=item.toString();if(token.length>maximumNumberLength)throw new Error('Online JSON number exceeds its limit');return token;
  }
  if(typeof item==='number'){
   if(!Number.isFinite(item)||Number.isInteger(item)&&!Number.isSafeInteger(item))throw new Error('An exact integer is required; unsafe JavaScript numbers cannot be sent');
   return Object.is(item,-0)?'-0':JSON.stringify(item);
  }
  if(item instanceof OnlineJsonNumber)return item.token;
  if(typeof item!=='object')throw new TypeError('Unsupported online JSON value');
  if(parents.has(item))throw new TypeError('Circular online JSON value');
  const array=Array.isArray(item);if(!array&&Object.getPrototypeOf(item)!==Object.prototype&&Object.getPrototypeOf(item)!==null)throw new TypeError('Online JSON requires plain objects');
  parents.add(item);const parts:string[]=[];
  if(array){for(let index=0;index<item.length;index++)parts.push(write(item[index],depth+1));}
  else {for(const key of Object.keys(item)){
   const descriptor=Object.getOwnPropertyDescriptor(item,key)!;if(!('value' in descriptor))throw new TypeError('Online JSON properties must be data');
   parts.push(JSON.stringify(key)+(indent?': ':':')+write(descriptor.value,depth+1));
  }}
  parents.delete(item);const open=array?'[':'{',close=array?']':'}';
  return parts.length&&indent?open+'\n'+parts.map(part=>padding(depth+1)+part).join(',\n')+'\n'+padding(depth)+close:open+parts.join(',')+close;
 }
 const result=write(value,0);checkSize(result,limit);return result;
}

export type OnlineField={type:'integer'|'string';width:number;min?:number|bigint;max?:number|bigint;default?:unknown};
function exactInteger(value:unknown):bigint {
 if(typeof value==='bigint')return value;
 if(typeof value==='number'&&Number.isSafeInteger(value))return BigInt(value);
 throw new Error('The integer contract must contain exact numeric bounds');
}
export function onlineInteger(raw:string,field:OnlineField,name='Value'):number|bigint {
 if(typeof raw!=='string'||!/^[-+]?\d+$/.test(raw.trim())||raw.trim().length>maximumNumberLength)throw new Error(name+' requires a whole number in decimal digits');
 const integer=BigInt(raw.trim()),minimum=exactInteger(field.min??0),maximum=exactInteger(field.max);
 if(minimum>maximum)throw new Error('Invalid integer contract bounds');
 if(integer<minimum||integer>maximum)throw new Error(name+' must be between '+minimum+' and '+maximum);
 return integer>=BigInt(Number.MIN_SAFE_INTEGER)&&integer<=BigInt(Number.MAX_SAFE_INTEGER)?Number(integer):integer;
}
export function onlineRecord(fields:Record<string,OnlineField>,values:Record<string,string>):Record<string,unknown>{
 return Object.fromEntries(Object.entries(fields).map(([name,field])=>{
  const raw=values[name]??'';
  if(field.type==='integer')return [name,onlineInteger(raw,field,name)];
  if(field.type!=='string'||!Number.isInteger(field.width)||field.width<1||field.width>256||typeof raw!=='string')throw new Error('Unsupported field contract: '+name);
  if(Array.from(raw).length!==field.width)throw new Error(name+' requires exactly '+field.width+' characters, including spaces');
  return [name,raw];
 }));
}
export function onlineDefaults(fields:Record<string,OnlineField>):Record<string,string>{
 return Object.fromEntries(Object.entries(fields).map(([name,field])=>{
  if(field.type==='integer'){
   const raw=String(exactInteger(field.default??0));onlineInteger(raw,field,name);return [name,raw];
  }
  if(field.type!=='string'||!Number.isInteger(field.width)||field.width<1||field.width>256||field.default!==undefined&&typeof field.default!=='string')throw new Error('Unsupported field contract: '+name);
  const raw=field.default===undefined?' '.repeat(field.width):field.default as string;
  if(Array.from(raw).length!==field.width)throw new Error('Invalid default for '+name);return [name,raw];
 }));
}
