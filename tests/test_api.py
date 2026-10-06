import asyncio
import tempfile
import unittest
import json
from pathlib import Path
from workbench.api import create_app

class ApiTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.app=create_app(self.tmp.name)
    async def asyncTearDown(self):
        self.app.state.coordinator.close();self.tmp.cleanup()
    async def request(self,path,method='GET',payload=None,headers=None):
        messages=[];received=False
        async def receive():
            nonlocal received
            if not received:received=True;return {'type':'http.request','body':json.dumps(payload or {}).encode(),'more_body':False}
            await asyncio.Future()
        async def send(m):messages.append(m)
        scope={'type':'http','asgi':{'version':'3.0'},'http_version':'1.1','scheme':'http','method':method,'path':path,'raw_path':path.encode(),'query_string':b'','root_path':'','server':('127.0.0.1',8765),'client':('127.0.0.1',1000),'headers':[(b'host',b'127.0.0.1:8765'),*(headers or [])]}
        await self.app(scope,receive,send)
        return messages[0]['status'],b''.join(m.get('body',b'') for m in messages[1:])
    async def test_cross_origin_mutation_denied(self):
        status,_=await self.request('/api/demo','POST');self.assertEqual(status,403)
        _,raw=await self.request('/api/state');token=json.loads(raw)['token']
        status,_=await self.request('/api/demo','POST',headers=[(b'origin',b'http://evil.example'),(b'x-workbench-token',token.encode())]);self.assertEqual(status,403)
    async def test_malformed_intake_and_oversized_body_fail_with_validation(self):
        _,raw=await self.request('/api/state');token=json.loads(raw)['token']
        headers=[(b'origin',b'http://127.0.0.1:8765'),(b'x-workbench-token',token.encode())]
        status,_=await self.request('/api/intake','POST',{'xlsx':'not-base64'},headers)
        self.assertEqual(status,400)
        status,_=await self.request('/api/intake','POST',{'manifest':'x'},headers)
        self.assertEqual(status,400)
        from unittest.mock import patch
        # Exercise the actual streaming body gate without allocating 128 MiB.
        with patch('workbench.api.MAX_HTTP_BODY_BYTES',1024):
            limited=create_app(Path(self.tmp.name)/'body-limit');prior=self.app;self.app=limited
            try:
                _,limited_raw=await self.request('/api/state');limited_token=json.loads(limited_raw)['token']
                limited_headers=[(b'origin',b'http://127.0.0.1:8765'),(b'x-workbench-token',limited_token.encode())]
                status,_=await self.request('/api/intake','POST',{'prompt':'a'*1025},limited_headers)
                self.assertEqual(status,413)
            finally:self.app=prior;limited.state.coordinator.close()
    async def test_real_demo_enters_single_review_stage_and_static_is_local(self):
        status,raw=await self.request('/api/state');self.assertEqual(status,200);token=json.loads(raw)['token']
        status,raw=await self.request('/api/demo','POST',headers=[(b'origin',b'http://127.0.0.1:8765'),(b'x-workbench-token',token.encode())]);self.assertEqual(status,200)
        doc=json.loads(raw);self.app.state.coordinator.advance(doc['id'])
        self.assertEqual(self.app.state.coordinator.ledger.get(doc['id'])['status'],'WAITING_SME')
        status,raw=await self.request('/');self.assertEqual(status,200);self.assertIn(b'/app.js',raw)
    async def test_nontext_review_and_unencodable_source_have_named_validation_errors(self):
        _,raw=await self.request('/api/state');token=json.loads(raw)['token']
        headers=[(b'origin',b'http://127.0.0.1:8765'),(b'x-workbench-token',token.encode())]
        for value in (123,[],None):
            status,raw=await self.request('/api/process/missing/answers','POST',{'xlsx':value,'reviewer':'A'},headers)
            self.assertEqual(status,400);self.assertIn(b'base64 text',raw)
        manifest=(Path(__file__).parent.parent/'examples/process-input.md').read_text()
        status,raw=await self.request('/api/intake','POST',{'manifest':manifest,'sources':{'BAD.cbl':'\ud800'}},headers)
        self.assertEqual(status,400);self.assertIn(b'UTF-8',raw)

if __name__=='__main__':unittest.main()
