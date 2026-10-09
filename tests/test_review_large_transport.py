"""Large local HTML reaches the same Coordinator quota through CLI or UI."""
import base64
import json
from pathlib import Path
import tempfile
import unittest

from workbench.coordinator import Coordinator
from workbench.domain import ValidationError, decode, sha
from workbench.review import _html_response, render_html_packet
from workbench.runner import import_return
from test_source import COBOL
from test_workflow import MANIFEST


def ready(coordinator):
    doc=coordinator.create(MANIFEST,{'ELIGIBLE.cbl':COBOL},assistant_mode='deterministic')
    coordinator.start(doc['id']);coordinator.advance(doc['id'])
    doc=coordinator.ledger.get(doc['id'])
    assert doc['status']=='WAITING_SME'
    packet=decode(coordinator.artifact(doc['id'],'review/packet.json').read_bytes())
    response=_html_response(packet);response['reviewer']='Synthetic reviewer'
    # Blank answers remain unresolved. Padding exercises actual local transport
    # independently of the meaningful 2000-item payload in large-HTML tests.
    data=render_html_packet(packet,response).replace(b'</body>',b' '*(9*1024*1024)+b'</body>')
    return doc,data


class LargeReviewCLITransportTests(unittest.TestCase):
    def test_large_html_import_is_hash_bound_idempotent_and_consumes_one_return(self):
        with tempfile.TemporaryDirectory() as tmp:
            c=Coordinator(Path(tmp))
            try:
                doc,data=ready(c);path=c.process_root(doc['id'])/'input/sme-return-inbox.html';path.write_bytes(data)
                imported=import_return(c,doc['id'],path,'Synthetic reviewer')
                self.assertTrue(imported['packet_imported']);self.assertEqual(imported['answers']['return_hash'],sha(data))
                self.assertTrue(all(v['answer']=='Unanswered' for v in imported['answers']['items'].values()))
                self.assertEqual(import_return(c,doc['id'],path,'Synthetic reviewer'),imported)
                path.write_bytes(data+b' ')
                with self.assertRaisesRegex(ValidationError,'already consumed'):
                    import_return(c,doc['id'],path,'Synthetic reviewer')
            finally:c.close()

    def test_large_workbook_is_rejected_without_expansion_or_quota_consumption(self):
        with tempfile.TemporaryDirectory() as tmp:
            c=Coordinator(Path(tmp))
            try:
                doc,_=ready(c);path=c.process_root(doc['id'])/'input/sme-return-inbox.xlsx';path.write_bytes(b'PK'+b'x'*(9*1024*1024))
                with self.assertRaisesRegex(ValidationError,'format-specific'):
                    import_return(c,doc['id'],path,'Synthetic reviewer')
                self.assertFalse(c.ledger.get(doc['id'])['packet_imported'])
            finally:c.close()


class LargeReviewAPITransportTests(unittest.IsolatedAsyncioTestCase):
    from test_api import ApiTests as _fixture
    asyncSetUp=_fixture.asyncSetUp
    asyncTearDown=_fixture.asyncTearDown
    request=_fixture.request

    async def test_large_html_is_local_same_origin_and_changed_second_return_is_refused(self):
        c=self.app.state.coordinator;doc,data=ready(c)
        _,raw=await self.request('/api/state');token=json.loads(raw)['token']
        headers=[(b'origin',b'http://127.0.0.1:8765'),(b'x-workbench-token',token.encode())]
        payload={'html':base64.b64encode(data).decode(),'reviewer':'Synthetic reviewer'}
        route='/api/process/'+doc['id']+'/answers'
        status,_=await self.request(route,'POST',payload);self.assertEqual(status,403)
        self.assertFalse(c.ledger.get(doc['id'])['packet_imported'])
        status,raw=await self.request(route,'POST',payload,headers);self.assertEqual(status,200,raw[:200])
        accepted=c.ledger.get(doc['id']);self.assertTrue(accepted['packet_imported'])
        self.assertEqual(accepted['answers']['return_hash'],sha(data))
        self.assertEqual((c.process_root(doc['id'])/'input/sme-return.html').read_bytes(),data)
        status,_=await self.request(route,'POST',{**payload,'html':base64.b64encode(data+b' ').decode()},headers)
        self.assertEqual(status,400);self.assertEqual(c.ledger.get(doc['id'])['answers'],accepted['answers'])


if __name__=='__main__':unittest.main()
