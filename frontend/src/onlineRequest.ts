import {parseOnlineJSON,stringifyOnlineJSON} from './onlineJson';

/** Preserve an uncertain operation and its exact transport bytes until it has a known outcome. */
export type OnlineAttempt={readonly transaction:string;readonly key:string;readonly body:{readonly record:unknown;readonly revision:number};readonly serializedBody:string;readonly session:{readonly session_id:string;readonly revision:number}};
function freeze(value:any):any{if(value&&typeof value==='object'){for(const child of Object.values(value))freeze(child);Object.freeze(value);}return value;}
export class PendingTransaction {
 attempt:OnlineAttempt|null=null;
 prepare(transaction:string,session:OnlineAttempt['session'],record:unknown,makeKey=()=>crypto.randomUUID()):OnlineAttempt {
  if(this.attempt){if(this.attempt.transaction!==transaction||this.attempt.session.session_id!==session.session_id)throw new Error('End the pending session before changing transaction');return this.attempt;}
  if(typeof transaction!=='string'||!transaction||typeof session.session_id!=='string'||!session.session_id||!Number.isSafeInteger(session.revision)||session.revision<0)throw new Error('Invalid online transaction session');
  const key=makeKey();if(typeof key!=='string'||!key)throw new Error('Invalid request identity');
  const serializedBody=stringifyOnlineJSON({record,revision:session.revision});
  this.attempt=freeze({transaction,key,body:parseOnlineJSON(serializedBody),serializedBody,session:{...session}});
  return this.attempt!;
 }
 received(status:number){if(status>=200&&status<300||status>=400&&status<500&&![408,429].includes(status))this.clear();}
 clear(){this.attempt=null;}
}

export class OnlineHttpError extends Error {constructor(public status:number,message:string){super(message);}}
export async function callOnline(path:string,token:string,options:{body?:unknown;serializedBody?:string;headers?:Record<string,string>;method?:string}={},fetcher:typeof fetch=fetch){
 if(options.body!==undefined&&options.serializedBody!==undefined)throw new Error('Supply one online request body');
 const body=options.serializedBody??(options.body===undefined?undefined:stringifyOnlineJSON(options.body));
 if(body!==undefined)parseOnlineJSON(body,65536);
 const response=await fetcher(path,{method:options.method||(body===undefined?'GET':'POST'),headers:{Authorization:'Bearer '+token,'Content-Type':'application/json',...options.headers},body});
 const data=parseOnlineJSON(await response.text());
 if(!response.ok)throw new OnlineHttpError(response.status,typeof data.detail==='string'?data.detail:stringifyOnlineJSON(data.detail??data));
 return data;
}
