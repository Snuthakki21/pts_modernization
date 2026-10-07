/** Preserve an uncertain operation until the same request has a known outcome. */
export type OnlineAttempt={transaction:string,key:string,body:{record:unknown,revision:number},session:{session_id:string,revision:number}};
export class PendingTransaction {
 attempt:OnlineAttempt|null=null;
 prepare(transaction:string,session:OnlineAttempt['session'],record:unknown,makeKey=()=>crypto.randomUUID()):OnlineAttempt {
  if(this.attempt){if(this.attempt.transaction!==transaction||this.attempt.session.session_id!==session.session_id)throw new Error('End the pending session before changing transaction');return this.attempt;}
  this.attempt={transaction,key:makeKey(),body:{record:JSON.parse(JSON.stringify(record)),revision:session.revision},session:{...session}};
  return this.attempt;
 }
 received(status:number){if(status>=200&&status<300||status>=400&&status<500&&![408,429].includes(status))this.clear();}
 clear(){this.attempt=null;}
}
