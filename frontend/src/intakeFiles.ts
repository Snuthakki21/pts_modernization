export const MAX_SOURCE_FILES=10_000,MAX_SOURCE_FILE_BYTES=16*1024*1024,MAX_UI_SOURCE_BYTES=32*1024*1024,MAX_SOURCE_LINES=2_000_000;

async function readSource(file:File,limit:number):Promise<{text:string;bytes:number}>{
 if(file.size>limit)throw Error(`${file.name}: file exceeds ${limit} bytes.`);
 let buffer:ArrayBuffer;
 try{buffer=await file.arrayBuffer();}
 catch{throw Error(`${file.name}: file could not be read; provide a UTF-8 text export.`);}
 if(buffer.byteLength>limit)throw Error(`${file.name}: file exceeds ${limit} bytes.`);
 try{return {text:new TextDecoder('utf-8',{fatal:true,ignoreBOM:true}).decode(buffer),bytes:buffer.byteLength};}
 catch{throw Error(`${file.name}: provide a UTF-8 text export; binary or invalid text cannot be analyzed.`);}
}
/** Preserve UTF-8 source exactly, including a BOM and original record endings. */
export async function readUtf8Source(file:File,limit:number):Promise<string>{return (await readSource(file,limit)).text;}

export async function readSourceFiles(files:File[]):Promise<Record<string,string>>{
 if(files.length>MAX_SOURCE_FILES)throw Error('Maximum 10,000 files per process.');
 if(files.reduce((total,file)=>total+file.size,0)>MAX_UI_SOURCE_BYTES)throw Error('Browser upload exceeds 32 MiB. Keep the complete export in the local Endeavor folder for intake up to 512 MiB.');
 // Ordinary objects silently invoke __proto__ instead of retaining that file.
 const result:Record<string,string>=Object.create(null);
 let bytes=0,lines=0;
 for(const file of files){
  const name=file.webkitRelativePath||file.name;
  if(Object.hasOwn(result,name))throw Error('Duplicate filenames have the same relative path; choose a folder that preserves the export paths.');
  const source=await readSource(file,Math.min(MAX_SOURCE_FILE_BYTES,MAX_UI_SOURCE_BYTES-bytes));
  bytes+=source.bytes;
  if(bytes>MAX_UI_SOURCE_BYTES)throw Error('Browser upload exceeds 32 MiB; use the complete local Endeavor export.');
  if(source.text.includes('\0'))throw Error(`${name}: binary/NUL content is not a readable source export.`);
  let end=0;
  for(const match of source.text.matchAll(/\r\n|[\n\r\v\f\x1c-\x1e\x85\u2028\u2029]/g)){
   lines++;end=(match.index??0)+match[0].length;
   if(lines>MAX_SOURCE_LINES)throw Error('Source export exceeds 2,000,000 physical lines.');
  }
  lines+=Number(source.text.length>0&&end<source.text.length);
  if(lines>MAX_SOURCE_LINES)throw Error('Source export exceeds 2,000,000 physical lines.');
  result[name]=source.text;
 }
 return result;
}
