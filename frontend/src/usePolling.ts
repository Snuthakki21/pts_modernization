import {useEffect,useRef} from 'react';

/** One request at a time, no background-tab traffic, and no stale response writes. */
export function usePolling<T>(url:string|null,onData:(value:T)=>void,onError:(error:Error)=>void,interval=4000,revision:string|number=0){
 const callbacks=useRef({onData,onError});callbacks.current={onData,onError};
 useEffect(()=>{
  if(!url)return;
  let stopped=false,timer:ReturnType<typeof setTimeout>|undefined,controller:AbortController|undefined,inFlight=false,lastPayload:string|undefined,failed=false;
  async function poll(){
   if(stopped||document.hidden||inFlight)return;
   inFlight=true;const request=new AbortController();controller=request;
   try{const response=await fetch(url!,{signal:request.signal});if(!response.ok)throw Error('Connection unavailable. Check that the local workbench is running.');const data=await response.json();if(!stopped&&!request.signal.aborted){const payload=JSON.stringify(data);if(failed||payload!==lastPayload)callbacks.current.onData(data);lastPayload=payload;failed=false;}}
   catch(error){if(!stopped&&!request.signal.aborted){failed=true;callbacks.current.onError(error instanceof Error?error:Error('Connection unavailable.'));}}
   finally{inFlight=false;if(!stopped&&!document.hidden)timer=setTimeout(()=>void poll(),interval);}
  }
  function visibility(){if(timer)clearTimeout(timer);if(document.hidden)controller?.abort();else void poll();}
  document.addEventListener('visibilitychange',visibility);void poll();
  return()=>{stopped=true;if(timer)clearTimeout(timer);controller?.abort();document.removeEventListener('visibilitychange',visibility);};
 },[url,interval,revision]);
}
