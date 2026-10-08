/** Keep visible form feedback associated with the field that needs correction. */
export function fieldErrorFeedback(id:string,invalidField:string,errorId:string,help?:string){
 return {'aria-invalid':invalidField===id||undefined,'aria-describedby':[help,invalidField===id?errorId:undefined].filter(Boolean).join(' ')||undefined};
}
