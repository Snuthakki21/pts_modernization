import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch
from workbench.domain import ValidationError, safe_path
from workbench.layout import validate_workspace, output_path


class LayoutTests(unittest.TestCase):
    def test_actual_layout_cli_keeps_private_filenames_local_and_failure_exit_intact(self):
        import json,subprocess,sys
        from workbench.domain import sha
        marker='123-45-6789';path=self.root/(marker+'.dat');path.write_text('fictional private operator file')
        original=path.read_bytes();private=validate_workspace(self.root)
        self.assertIn(marker,json.dumps(private))
        actual=subprocess.run([sys.executable,'-m','workbench.layout','--workspace',str(self.root)],
                              capture_output=True,text=True,timeout=20)
        self.assertEqual(actual.returncode,2);self.assertNotIn(marker,actual.stdout+actual.stderr)
        result=json.loads(actual.stdout);self.assertFalse(result['valid']);self.assertEqual(result['issue_count'],len(private))
        self.assertEqual([entry['evidence_sha256'] for entry in result['issues']],[sha(issue) for issue in private])
        self.assertEqual(path.read_bytes(),original);self.assertEqual(validate_workspace(self.root),private)

    def test_layout_cli_errors_are_hash_bound_and_never_print_private_paths(self):
        import io,json
        from contextlib import redirect_stdout
        from workbench.domain import sha
        from workbench.layout import main
        marker='123-45-6789 private@example.invalid'
        for detail in (marker,marker+'\udcff'):
            stream=io.StringIO()
            with patch('workbench.layout.validate_workspace',side_effect=OSError(detail)),redirect_stdout(stream):
                self.assertEqual(main(['--workspace',str(self.root)]),2)
            self.assertNotIn(marker,stream.getvalue());result=json.loads(stream.getvalue())
            self.assertFalse(result['valid']);self.assertEqual(result['issue_count'],1)
            self.assertEqual(result['issues'][0]['evidence_sha256'],sha(detail.encode('utf-8',errors='surrogatepass')))

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

    def test_relative_paths_reject_aliases_before_creating_outputs(self):
        aliases = ('analysis//new.json', 'analysis/./new.json',
                   './analysis/new.json', 'analysis/new.json/')
        for relative in aliases:
            with self.subTest(relative=relative):
                with self.assertRaisesRegex(ValidationError, 'canonical'):
                    safe_path(self.root, relative)
                with self.assertRaisesRegex(ValidationError, 'canonical'):
                    output_path(self.root, 'process-a', relative)
        self.assertEqual(list(self.root.iterdir()), [])
        self.assertEqual(safe_path(self.root, 'analysis/new.json'),
                         self.root / 'analysis/new.json')

    def test_registration_cannot_duplicate_evidence_using_path_aliases(self):
        from workbench.coordinator import Coordinator
        from test_source import COBOL
        from test_workflow import MANIFEST
        c = Coordinator(self.root); self.addCleanup(c.close)
        doc = c.create(MANIFEST, {'ELIGIBLE.cbl': COBOL})
        before_artifacts = list(doc['artifacts'])
        before_hashes = dict(doc['artifact_hashes'])
        canonical = c.process_root('process-a') / 'analysis/source-origin.json'
        original = canonical.read_bytes()
        for relative in ('analysis//source-origin.json',
                         'analysis/./source-origin.json',
                         './analysis/source-origin.json',
                         'analysis/source-origin.json/'):
            with self.subTest(relative=relative):
                with self.assertRaisesRegex(ValidationError, 'canonical'):
                    c.register(doc, relative)
        self.assertEqual(doc['artifacts'], before_artifacts)
        self.assertEqual(doc['artifact_hashes'], before_hashes)
        self.assertEqual(canonical.read_bytes(), original)

    def test_windows_reserved_aliases_block_source_intake_without_partial_evidence(self):
        from workbench.coordinator import Coordinator
        from test_source import COBOL
        from test_workflow import MANIFEST
        c = Coordinator(self.root); self.addCleanup(c.close)
        for name in ('COM¹.cbl', 'com².cbl', 'COM³.cbl',
                     'LPT¹.cbl', 'lpt².cbl', 'LPT³.cbl',
                     'CONIN$.cbl', 'CONOUT$.cbl', 'CON .cbl'):
            with self.subTest(name=name):
                with self.assertRaisesRegex(ValidationError, 'reserved'):
                    c.create(MANIFEST, {'library/' + name: COBOL})
                self.assertEqual(c.ledger.list(True), [])
                self.assertFalse(c.process_root('process-a').exists())
        self.assertEqual(validate_workspace(self.root), [])

    def test_windows_reserved_aliases_block_archive_intake(self):
        from io import BytesIO
        import zipfile
        from workbench.domain import checked_zip
        for name in ('COM¹', 'com².cpy', 'COM³.txt', 'LPT¹',
                     'lpt².cpy', 'LPT³.txt', 'CONIN$',
                     'CONOUT$.cbl', 'CON .txt'):
            with self.subTest(name=name):
                payload = BytesIO()
                with zipfile.ZipFile(payload, 'w') as archive:
                    archive.writestr('library/' + name, 'source')
                with self.assertRaisesRegex(ValidationError, 'reserved'):
                    checked_zip(payload.getvalue())
        # Similar ordinary names are portable and must not be over-rejected.
        for name in ('COM10.cbl', 'COM⁴.cbl', 'LPT10.cbl',
                     'CONNECTION.cbl', 'NULLED.cbl'):
            with self.subTest(name=name):
                self.assertEqual(safe_path(self.root, 'library/' + name).name, name)

    def test_historical_aliases_are_named_blockers_on_restart_without_rewriting(self):
        from copy import deepcopy
        from workbench.coordinator import Coordinator
        from test_source import COBOL
        from test_workflow import MANIFEST
        cases = (('artifacts', 'analysis//source-origin.json'),
                 ('artifact_hashes', 'analysis/./source-origin.json'),
                 ('report_hashes', 'reports//report-0001/metrics.json'))
        for field, alias in cases:
            with self.subTest(field=field), tempfile.TemporaryDirectory() as folder:
                c = Coordinator(folder)
                try:
                    doc = c.create(MANIFEST, {'ELIGIBLE.cbl': COBOL})
                    if field == 'artifacts': doc[field].append(alias)
                    else: doc.setdefault(field, {})[alias] = doc['artifact_hashes']['analysis/source-origin.json']
                    c.ledger.save(doc)
                    before = {key: deepcopy(doc.get(key)) for key in
                              ('artifacts', 'artifact_hashes', 'report_hashes')}
                    source = c.process_root('process-a') / 'input/sources/ELIGIBLE.cbl'
                    original = source.read_bytes()
                    c.close(); c = Coordinator(folder)
                    current = c.ledger.get('process-a')
                    blockers = [b for b in current['blockers'] if b['kind'] == 'evidence_integrity']
                    self.assertTrue(any(alias in b['message'] for b in blockers), blockers)
                    with self.assertRaisesRegex(ValidationError, 'reference'):
                        c.start('process-a')
                    self.assertEqual(current['status'], 'READY')
                    for key, value in before.items(): self.assertEqual(current.get(key), value)
                    self.assertEqual(source.read_bytes(), original)
                    self.assertFalse(current['packet_issued'])
                finally: c.close()

    def test_historical_hash_only_alias_blocks_target_before_verification(self):
        from workbench.coordinator import Coordinator
        from test_source import COBOL
        from test_workflow import MANIFEST, WorkflowTests
        from types import SimpleNamespace
        c = Coordinator(self.root); self.addCleanup(c.close)
        c.create(MANIFEST, {'ELIGIBLE.cbl': COBOL})
        c.start('process-a'); c.advance('process-a')
        returned = WorkflowTests.answer(SimpleNamespace(c=c))
        c.import_answers('process-a', returned, 'Example reviewer')
        doc = c.ledger.get('process-a')
        alias = 'analysis/./source-origin.json'
        original_hash = doc['artifact_hashes']['analysis/source-origin.json']
        doc['artifact_hashes'][alias] = original_hash
        c.ledger.save(doc)
        with patch('workbench.coordinator.verify_program') as target:
            c.advance('process-a')
        target.assert_not_called()
        current = c.ledger.get('process-a')
        self.assertEqual(current['status'], 'QUEUED_REPORT')
        self.assertTrue(any(b['kind'] == 'evidence_integrity' and alias in b['message']
                            for b in current['blockers']))
        self.assertEqual(current['artifact_hashes'][alias], original_hash)
        self.assertEqual(current['runs'], [])
        self.assertFalse((c.process_root('process-a') / 'synthetic').exists())

    def test_historical_artifact_alias_cannot_receive_unblocked_report(self):
        from workbench.coordinator import Coordinator
        from test_source import COBOL
        from test_workflow import MANIFEST, WorkflowTests
        from types import SimpleNamespace
        c = Coordinator(self.root); self.addCleanup(c.close)
        c.create(MANIFEST, {'ELIGIBLE.cbl': COBOL})
        c.start('process-a'); c.advance('process-a')
        returned = WorkflowTests.answer(SimpleNamespace(c=c))
        c.import_answers('process-a', returned, 'Example reviewer')
        c.advance('process-a')
        doc = c.ledger.get('process-a')
        alias = 'analysis//source-origin.json'
        original_hash = doc['artifact_hashes']['analysis/source-origin.json']
        doc['artifacts'].append(alias); doc['artifact_hashes'][alias] = original_hash
        c.ledger.save(doc); c.advance('process-a')
        current = c.ledger.get('process-a')
        self.assertEqual(current['status'], 'COMPLETED_WITH_BLOCKERS')
        self.assertTrue(any(b['kind'] == 'evidence_integrity' and alias in b['message']
                            for b in current['blockers']))
        self.assertFalse(current['coverage_summary']['completion_eligible'])
        self.assertIn(alias, current['artifacts'])
        self.assertEqual(current['artifact_hashes'][alias], original_hash)
        c.close(); c = Coordinator(self.root); self.addCleanup(c.close)
        current = c.ledger.get('process-a')
        self.assertFalse(current['report_verified'])
        self.assertEqual(current['status'], 'QUEUED_REPORT')
        self.assertIn(alias, current['artifacts'])
        self.assertEqual(current['artifact_hashes'][alias], original_hash)

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
