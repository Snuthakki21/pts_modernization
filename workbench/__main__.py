"""Bounded single-machine HTTP transport for the local FastAPI application."""
import asyncio
import argparse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from .api import create_app

def make_server(root,port=8765):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*args):pass
        def dispatch(self):
            self.connection.settimeout(15)
            try:
                if self.headers.get('Transfer-Encoding'):self.send_error(400);return
                n=int(self.headers.get('Content-Length','0'))
                if not 0<=n<=12*1024*1024:self.send_error(413);return
                data=self.rfile.read(n)
                if len(data)!=n:self.send_error(400);return
                path,_,query=self.path.partition('?');sent=[];received=False
                async def receive():
                    nonlocal received
                    if not received:received=True;return {'type':'http.request','body':data,'more_body':False}
                    await asyncio.sleep(3600)
                async def send(message):sent.append(message)
                scope={'type':'http','asgi':{'version':'3.0','spec_version':'2.3'},'http_version':'1.1','method':self.command,'scheme':'http','path':path,'raw_path':path.encode(),'query_string':query.encode(),'root_path':'','headers':[(k.lower().encode(),v.encode()) for k,v in self.headers.items()],'client':self.client_address,'server':('127.0.0.1',port)}
                asyncio.run(app(scope,receive,send));start=next(x for x in sent if x['type']=='http.response.start');body=b''.join(x.get('body',b'') for x in sent if x['type']=='http.response.body')
                self.send_response(start['status'])
                for k,v in start['headers']:
                    if k.lower()!=b'content-length':self.send_header(k.decode(),v.decode())
                self.send_header('Content-Length',str(len(body)));self.end_headers()
                if self.command!='HEAD':self.wfile.write(body)
            except (ValueError,TimeoutError,ConnectionError):self.send_error(400)
        do_GET=dispatch;do_POST=dispatch;do_HEAD=dispatch
    server=ThreadingHTTPServer(('127.0.0.1',port),Handler);server.daemon_threads=True
    port=server.server_port
    app=create_app(root,f'http://127.0.0.1:{port}')
    return server,app.state.coordinator

def serve(root,port=8765):
    # Production transport uses Uvicorn; make_server is only a bounded HTTP test fixture.
    from .domain import require
    require(1<=port<=65535,'Port must be 1..65535')
    try:import uvicorn
    except ImportError as exc:raise SystemExit('Run scripts/Setup.ps1 or scripts/setup.sh to install the locked server dependencies') from exc
    app=create_app(root,f'http://127.0.0.1:{port}')
    print(f'Workbench: http://127.0.0.1:{port}',flush=True)
    uvicorn.run(app,host='127.0.0.1',port=port,access_log=False,log_level='warning')

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--root',default=str(Path.cwd()));p.add_argument('--port',type=int,default=8765);args=p.parse_args();serve(args.root,args.port)
