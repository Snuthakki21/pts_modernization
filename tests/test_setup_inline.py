"""Supplemental inline-report regressions, outside numbered review accounting."""
import json
import unittest
from test_expanded_setup import SetupApiFixtures


class InlineExecutiveApiTests(SetupApiFixtures, unittest.IsolatedAsyncioTestCase):
    """Supplemental endpoint regressions, outside the 500 numbered review checks."""
    async def asyncSetUp(self):
        await super().asyncSetUp()
        from workbench.domain import require, safe_path, sha
        self.report='reports/report-0001/executive-report.html'
        self.metrics='reports/report-0001/metrics.json'
        self.source='input/sources/source.html'
        from workbench.executive import executive_summary, render_executive
        metrics={key:0 for key in ('source_accounted_lines source_in_scope_lines source_out_of_scope_lines source_applicable_lines '
            'source_verified_applicable_lines source_blocked_lines source_unverified_mapped_lines source_non_executable_lines '
            'source_integrity_errors source_inventory_files source_programs target_python_programs source_code_loc target_program_code_loc '
            'source_bms_screens target_react_business_screens source_copybooks rules_documented rules_verified target_business_rest_apis '
            'source_db2_table_references').split()}
        metrics['process_id']='process'
        context={'id':'process','name':'Fixture report','fixture_only':True,'artifacts':['analysis/source-analysis.json'],'blockers':[]}
        model=executive_summary(context,metrics)
        files={self.report:render_executive(model).encode(),
               self.metrics:json.dumps({'executive':model,'metrics':metrics,'executive_context':context}).encode(),
               self.source:b'<script>untrusted()</script>', 'analysis/source-analysis.json':b'{}'}
        self.doc={'id':'process','report_verified':True,'artifacts':list(files),'report_hashes':{p:sha(raw) for p,raw in files.items() if p.startswith('reports/')}}
        self.fingerprints={p:sha(raw) for p,raw in files.items()}
        for relative,raw in files.items():
            path=self.root/relative;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(raw)
        def get(pid):require(pid=='process','Unknown process');return self.doc
        def artifact(pid,relative):
            get(pid);require(relative in self.fingerprints,'Unregistered artifact');p=safe_path(self.root,relative);require(sha(p.read_bytes())==self.fingerprints[relative],'Artifact integrity failed');return p
        self.coordinator.ledger.get=get;self.coordinator.artifact=artifact

    async def artifact_request(self,path,inline=True,pid='process',extra=''):
        from urllib.parse import urlencode
        query=urlencode({'path':path,**({'inline':'true'} if inline else {})})+extra
        return await self.request(f'/api/process/{pid}/artifact',query=query.encode(),decode_json=False)

    async def test_inline_accepted_report_has_restrictive_policy_and_valid_links(self):
        original=(self.root/self.report).read_bytes();s,raw=await self.artifact_request(self.report)
        self.assertEqual(s['status'],200);headers=dict(s['headers']);self.assertTrue(headers[b'content-type'].startswith(b'text/html'));self.assertTrue(headers[b'content-disposition'].startswith(b'inline;'))
        for directive in (b"default-src 'none'",b"script-src 'none'",b"connect-src 'none'",b"form-action 'none'",b"style-src 'unsafe-inline'",b"base-uri 'none'",b"frame-ancestors 'none'"):self.assertIn(directive,headers[b'content-security-policy'])
        self.assertIn(b'/api/process/process/artifact?path=reports%2Freport-0001%2Fcoverage.html',raw);self.assertIn(b'/api/process/process/artifact?path=analysis%2Fsource-analysis.json',raw);self.assertEqual((self.root/self.report).read_bytes(),original)

    async def test_source_html_downloads_but_cannot_be_opened_inline(self):
        s,raw=await self.artifact_request(self.source,inline=False);self.assertEqual(s['status'],200);self.assertTrue(dict(s['headers'])[b'content-disposition'].startswith(b'attachment;'));self.assertEqual(raw,b'<script>untrusted()</script>')
        s,_=await self.artifact_request(self.source);self.assertEqual(s['status'],400)

    async def test_modified_executive_bytes_never_render_inline(self):
        (self.root/self.report).write_bytes(b'<script>changed()</script>');s,raw=await self.artifact_request(self.report);self.assertEqual(s['status'],400);self.assertNotIn(b'<script>',raw)

    async def test_inline_route_requires_process_ownership_and_unambiguous_path(self):
        s,_=await self.artifact_request(self.report,pid='other');self.assertEqual(s['status'],400)
        s,_=await self.artifact_request(self.report,extra='&path='+self.report);self.assertEqual(s['status'],400)
        s,_=await self.artifact_request(self.report.replace('/','%2F'));self.assertEqual(s['status'],400)


if __name__=='__main__':unittest.main()
