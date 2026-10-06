import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch
from workbench.domain import ValidationError
from workbench.layout import validate_workspace, output_path


class LayoutTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def test_allowed_process_categories_and_private_paths(self):
        for name in ('input/sources/ELIGIBLE.cbl', 'analysis/source-analysis.json',
                     'review/sme-checklist.xlsx', 'synthetic/run-0001/expected.json',
                     'target/run-0001/jobs.py', 'reports/report-0001/coverage.csv',
                     'tests/regression.json'):
            path = output_path(self.root, 'process-a', name)
            path.parent.mkdir(parents=True, exist_ok=True); path.write_text('evidence')
        (self.root / '.env').write_text('PRIVATE=value')
        (self.root / 'release-private').mkdir()
        self.assertEqual(validate_workspace(self.root), [])

    def test_misplaced_output_and_sibling_escape_are_rejected(self):
        for name in ('../process-b/reports/file.txt', '/tmp/file.txt',
                     'analysis/../../process-b/file.txt', 'misc/rule.md',
                     'analysis/jobs.py', 'input/actual-results.json'):
            with self.assertRaises(ValidationError): output_path(self.root, 'process-a', name)
        (self.root / 'unexpected.md').write_text('wrong location')
        self.assertTrue(validate_workspace(self.root))

    def test_screenshot_local_environment_entries_pass_without_reading_private_contents(self):
        for name in ('.events','.gradle','logs','plugins','settings'):
            (self.root/name).mkdir();(self.root/name/'private-config').write_text('LOCAL_ONLY')
        for name in ('extenders.json','.npmrc','pip.conf','pip.ini','NuGet.Config'):
            (self.root/name).write_text('LOCAL_ONLY')
        from unittest.mock import patch
        with patch.object(Path,'read_text',side_effect=AssertionError('No private content reads')), patch.object(Path,'read_bytes',side_effect=AssertionError('No private content reads')):
            self.assertEqual(validate_workspace(self.root),[])

    def test_operational_roots_are_accepted_by_real_coordinator_and_preserved(self):
        from workbench.coordinator import Coordinator
        from test_source import COBOL
        from test_workflow import MANIFEST
        for name in ('logs','plugins','settings','.events'):(self.root/name).mkdir()
        config=self.root/'extenders.json';config.write_bytes(b'LOCAL_ONLY_CONFIGURATION')
        c=Coordinator(self.root);self.addCleanup(c.close)
        c.create(MANIFEST,{'ELIGIBLE.cbl':COBOL});c.start('process-a');c.advance('process-a')
        self.assertEqual(c.ledger.get('process-a')['status'],'WAITING_SME')
        self.assertEqual(config.read_bytes(),b'LOCAL_ONLY_CONFIGURATION')

    def test_new_private_roots_do_not_allow_symlinks_or_arbitrary_outputs(self):
        (self.root/'logs').symlink_to(self.root/'outside',target_is_directory=True)
        self.assertTrue(any('logs: symlinks' in issue for issue in validate_workspace(self.root)))
        (self.root/'logs').unlink();(self.root/'unregistered-output').mkdir()
        self.assertTrue(any('not allowlisted' in issue for issue in validate_workspace(self.root)))

    def test_sensitive_build_and_local_configuration_paths_are_git_ignored(self):
        import subprocess
        repo=Path(__file__).resolve().parents[1]
        paths=['.gradle/config','.npmrc','pip.conf','pip.ini','NuGet.Config','tools/dq3g_mcp/.env',
               'logs/local.dat','plugins/local.json','settings/local.json','.events/trace','extenders.json']
        result=subprocess.run(['git','check-ignore','--no-index','--stdin'],input='\n'.join(paths)+'\n',
                              cwd=repo,text=True,capture_output=True,check=True)
        self.assertEqual(result.stdout.splitlines(),paths)

    def test_symlink_parent_workspace_is_rejected(self):
        from workbench.layout import require_layout
        actual = self.root / 'real'; actual.mkdir()
        alias = self.root / 'alias'; alias.symlink_to(actual, target_is_directory=True)
        with self.assertRaises(ValidationError): require_layout(alias / 'nested')

    def test_shared_versions_require_content_addressed_location(self):
        bad = self.root / 'shared/target/python/jobs.py'
        bad.parent.mkdir(parents=True); bad.write_text('code')
        self.assertTrue(validate_workspace(self.root))
        bad.rename(bad.with_name('a' * 64 + '.py'))
        self.assertEqual(validate_workspace(self.root), [])

    def test_root_tmp_prefix_cannot_hide_misplaced_process_outputs(self):
        bad = self.root / 'tmp-business-output'; bad.mkdir()
        (bad / 'results.json').write_text('{}')
        self.assertTrue(validate_workspace(self.root))
        bad.rename(self.root / '.implementation')
        self.assertEqual(validate_workspace(self.root), [])

    def test_programmatic_intake_and_start_enforce_layout(self):
        from workbench.coordinator import Coordinator
        from test_source import COBOL
        from test_workflow import MANIFEST
        c = Coordinator(self.root); self.addCleanup(c.close)
        bad = self.root / 'misplaced-results.json'; bad.write_text('{}')
        with self.assertRaises(ValidationError): c.create(MANIFEST, {'ELIGIBLE.cbl': COBOL})
        self.assertEqual(c.ledger.list(True), [])
        bad.unlink(); c.create(MANIFEST, {'ELIGIBLE.cbl': COBOL})
        bad = self.root / 'processes/process-a/results.json'; bad.write_text('{}')
        with self.assertRaises(ValidationError): c.start('process-a')
        self.assertEqual(c.ledger.get('process-a')['status'], 'READY')

    def test_programmatic_registration_rejects_sibling_and_misplaced_outputs(self):
        from workbench.coordinator import Coordinator
        from test_source import COBOL
        from test_workflow import MANIFEST
        c = Coordinator(self.root); self.addCleanup(c.close)
        doc = c.create(MANIFEST, {'ELIGIBLE.cbl': COBOL})
        before=list(doc['artifacts'])
        for name in ('../process-b/reports/metrics.json', 'analysis/jobs.py', 'rogue/results.json'):
            with self.assertRaises(ValidationError): c.register(doc, name)
        self.assertEqual(doc['artifacts'], before)

    def test_core_constructor_rejects_misplaced_outputs_before_state_creation(self):
        from workbench.coordinator import Coordinator
        (self.root / 'misplaced.json').write_text('{}')
        with self.assertRaises(ValidationError):
            c = Coordinator(self.root); self.addCleanup(c.close)
        self.assertFalse((self.root / '.migration').exists())

    def test_programmatic_stage_and_report_refuse_new_misplacement_before_writes(self):
        from workbench.coordinator import Coordinator
        from test_source import COBOL
        from test_workflow import MANIFEST
        c = Coordinator(self.root); self.addCleanup(c.close)
        c.create(MANIFEST, {'ELIGIBLE.cbl': COBOL}); c.start('process-a')
        misplaced = self.root / 'processes/process-a/output.json'; misplaced.write_text('{}')
        with self.assertRaisesRegex(ValidationError, 'layout'):
            c.advance('process-a')
        self.assertEqual(c.ledger.get('process-a')['status'], 'QUEUED_ANALYSIS')
        self.assertFalse((self.root / 'processes/process-a/analysis/source-analysis.json').exists())
        self.assertTrue((self.root / 'processes/process-a/analysis/mainframe-knowledge.json').is_file())
        misplaced.unlink(); c.advance('process-a')
        doc = c.ledger.get('process-a')
        misplaced.write_text('{}')
        with self.assertRaisesRegex(ValidationError, 'layout'):
            c.report(doc)
        self.assertEqual(c.ledger.get('process-a')['status'], 'WAITING_SME')
        self.assertFalse((self.root / 'processes/process-a/reports').exists())

    def test_agent_entrypoints_reference_one_existing_shared_prompt(self):
        repo = Path(__file__).resolve().parents[1]
        for relative in ('AGENTS.md', 'CLAUDE.md', '.github/copilot-instructions.md'):
            text = (repo / relative).read_text()
            self.assertIn('prompts/START_MODERNIZATION.md', text)
        self.assertTrue((repo / 'prompts/START_MODERNIZATION.md').is_file())

    def test_failed_packet_draft_stays_private_and_can_recover(self):
        from workbench.coordinator import Coordinator
        from test_source import COBOL
        from test_workflow import MANIFEST
        c = Coordinator(self.root); self.addCleanup(c.close)
        c.create(MANIFEST, {'ELIGIBLE.cbl': COBOL}); c.start('process-a')
        with patch('openpyxl.workbook.workbook.Workbook.save', side_effect=OSError('temporary packet save failure')):
            with self.assertRaises(OSError): c.advance('process-a')
        self.assertEqual(validate_workspace(self.root), [])
        self.assertFalse(c.ledger.get('process-a')['packet_issued'])
        time.sleep(.2); c.advance('process-a')
        self.assertEqual(c.ledger.get('process-a')['status'], 'WAITING_SME')
        self.assertFalse(any(p.name.startswith('.review-draft-') for p in c.process_root('process-a').iterdir()))

    def test_symlink_and_new_markdown_per_rule_are_rejected(self):
        path = self.root / 'processes/process-a/analysis/rule-1.md'
        path.parent.mkdir(parents=True); path.write_text('wrong location')
        self.assertTrue(validate_workspace(self.root))
        path.unlink(); path.symlink_to(self.root / 'external.md')
        self.assertTrue(validate_workspace(self.root))
