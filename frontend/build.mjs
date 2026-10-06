import {build} from 'esbuild';
import {mkdir,copyFile} from 'node:fs/promises';
await mkdir('../workbench/static',{recursive:true});
await build({entryPoints:['src/main.tsx'],bundle:true,minify:true,outfile:'../workbench/static/app.js',legalComments:'external',define:{'process.env.NODE_ENV':'"production"'}});
await copyFile('index.html','../workbench/static/index.html');
await copyFile('src/style.css','../workbench/static/style.css');
