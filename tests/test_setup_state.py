"""Supplemental bounded polling regressions outside numbered review accounting."""
import copy
import unittest

from test_expanded_setup import SetupApiFixtures


class StateProjectionApiTests(SetupApiFixtures, unittest.IsolatedAsyncioTestCase):
    async def test_state_keeps_rule_graph_and_counts_without_full_source_rows(self):
        document={'id':'process','runs':[],'analysis':{
            'programs':{'P':{'source_text':'PRIVATE PROGRAM'}},
            'source_accounting':{'P':[{'line':1,'source':'PRIVATE LINE 1'},{'line':2,'source':'PRIVATE LINE 2'}],
                                 'COPY':[{'line':1,'source':'PRIVATE COPY'}]},
            'rules':[{'id':'rule-one','plain':'An extracted rule'}],
            'graph':[{'from':'JOB','to':'P','kind':'executes'}],
            'blockers':[{'kind':'unsupported','message':'An explicit gap'}]}}
        original=copy.deepcopy(document);self.coordinator.ledger.list=lambda *a:[document]
        start,response=await self.request('/api/state');self.assertEqual(start['status'],200)
        analysis=response['processes'][0]['analysis']
        self.assertNotIn('source_accounting',analysis);self.assertNotIn('programs',analysis)
        self.assertEqual(analysis['source_accounted_file_count'],2);self.assertEqual(analysis['source_accounted_line_count'],3)
        for field in ('rules','graph','blockers'):self.assertEqual(analysis[field],document['analysis'][field])
        self.assertEqual(document,original)

    async def test_state_missing_historical_accounting_is_unknown_not_zero(self):
        document={'id':'process','runs':[],'analysis':{'rules':[],'graph':[]}}
        self.coordinator.ledger.list=lambda *a:[document]
        start,response=await self.request('/api/state');self.assertEqual(start['status'],200)
        self.assertIsNone(response['processes'][0]['analysis']['source_accounted_file_count'])
        self.assertIsNone(response['processes'][0]['analysis']['source_accounted_line_count'])


if __name__=='__main__':unittest.main()
