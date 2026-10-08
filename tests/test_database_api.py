"""Exact browser routes reuse the real registry and retain typed read-only filters."""
import json
from pathlib import Path
import unittest
import test_api
import test_database_workflow

class DatabaseApiTests(unittest.IsolatedAsyncioTestCase):
    asyncSetUp=test_api.ApiTests.asyncSetUp
    asyncTearDown=test_api.ApiTests.asyncTearDown
    request=test_api.ApiTests.request
    process=test_database_workflow.DatabaseWorkflowTests.process

    async def headers(self):
        _,raw=await self.request('/api/state')
        return [(b'origin',b'http://127.0.0.1:8765'),(b'x-workbench-token',json.loads(raw)['token'].encode())]

    async def test_registered_schema_and_typed_query_routes_are_wired_and_same_origin(self):
        self.c=self.app.state.coordinator;self.root=Path(self.tmp.name)
        self.process();headers=await self.headers()
        status,raw=await self.request('/api/process/process-a/database');self.assertEqual(status,200)
        self.assertTrue(json.loads(raw)['can_prepare'])
        status,_=await self.request('/api/process/process-a/database/prepare','POST',{});self.assertEqual(status,403)
        status,raw=await self.request('/api/process/process-a/database/prepare','POST',{},headers);self.assertEqual(status,200)
        model=json.loads(raw);database=model['databases'][0]
        self.assertFalse(model['native_database_verified'])
        query='/api/process/process-a/database/'+database['id']+'/query'
        body={'table':'APP.SALE','after':0,'limit':20,'filters':{'ID':{'type':'text','value':'00000001'}}}
        status,raw=await self.request(query,'POST',body,headers);self.assertEqual(status,200)
        self.assertEqual(json.loads(raw)['display_rows'],[])
        for change in ({'sql':'DROP TABLE APP.SALE'},{'table':'APP.SALE;DELETE'},{'filters':{'ID':{'type':'integer','value':'00000001'}}}):
            status,_=await self.request(query,'POST',{**body,**change},headers);self.assertEqual(status,400)
        status,_=await self.request('/api/process/process-a/database/compare','POST',{'rows':[]},headers);self.assertEqual(status,400)
        status,_=await self.request('/api/process/process-a/database/snapshot','POST',{},headers);self.assertEqual(status,400)
        self.assertFalse(self.c.ledger.get('process-a')['packet_issued'])

if __name__=='__main__':unittest.main()
