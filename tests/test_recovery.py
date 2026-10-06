"""Controls remain responsive and recovery never consumes another SME round."""
import threading
import time
from unittest.mock import patch
import unittest
import test_workflow
from workbench.coordinator import Coordinator


class RecoveryTests(unittest.TestCase):
    setUp=test_workflow.WorkflowTests.setUp
    create=test_workflow.WorkflowTests.create
    answer=test_workflow.WorkflowTests.answer
    def prepared(self):
        self.create();self.c.start('process-a');self.c.advance('process-a')
        self.c.import_answers('process-a',self.answer(),'Example reviewer')

    def test_pause_during_fixture_is_immediate_and_durable(self):
        self.prepared();entered=threading.Event();release=threading.Event()
        from workbench.coordinator import plan_cases
        def blocked(*args):
            entered.set();release.wait(3);return plan_cases(*args)
        with patch('workbench.coordinator.plan_cases',side_effect=blocked):
            task=threading.Thread(target=self.c.advance,args=('process-a',));task.start()
            self.assertTrue(entered.wait(2))
            control=threading.Thread(target=self.c.control,args=('process-a','pause'));control.start();control.join(.3)
            responsive=not control.is_alive();release.set();task.join(3);control.join(3)
        self.assertTrue(responsive,'Pause waited for long-running fixture stage')
        doc=self.c.ledger.get('process-a');self.assertEqual(doc['status'],'PAUSED');self.assertEqual(doc['resume_status'],'QUEUED_VERIFY')
        self.c.control('process-a','resume');self.c.advance('process-a')
        self.assertEqual(len(self.c.ledger.get('process-a')['runs']),1)

    def test_cancel_observed_before_target_prevents_execution(self):
        self.prepared();entered=threading.Event();release=threading.Event()
        from workbench.coordinator import plan_cases
        def blocked(*args):entered.set();release.wait(3);return plan_cases(*args)
        with patch('workbench.coordinator.plan_cases',side_effect=blocked),patch('workbench.coordinator.verify_program') as execute:
            task=threading.Thread(target=self.c.advance,args=('process-a',));task.start();self.assertTrue(entered.wait(2))
            control=threading.Thread(target=self.c.control,args=('process-a','cancel'));control.start();control.join(.3)
            responsive=not control.is_alive();release.set();task.join(3);control.join(3)
        self.assertTrue(responsive);execute.assert_not_called()
        self.c.advance('process-a');doc=self.c.ledger.get('process-a')
        self.assertEqual(doc['status'],'COMPLETED_WITH_BLOCKERS');self.assertTrue(doc['report_verified']);self.assertTrue(doc['packet_imported'])

    def test_transient_fixture_retries_automatically_with_bounded_attempts(self):
        self.prepared()
        with patch('workbench.coordinator.plan_cases',side_effect=OSError('temporary fixture read failure')) as fixture:
            self.c.launch_worker();deadline=time.monotonic()+3
            while self.c.ledger.get('process-a')['status']!='FAILED' and time.monotonic()<deadline:time.sleep(.02)
            doc=self.c.ledger.get('process-a')
        self.assertEqual(doc['status'],'FAILED');self.assertEqual(fixture.call_count,3)
        self.assertEqual(doc['stage_attempts']['QUEUED_VERIFY'],3);self.assertIn('temporary fixture',doc['last_failure']['message'])

    def test_report_failure_replays_without_duplicate_history(self):
        self.prepared();self.c.advance('process-a')
        from workbench.reports import generate_reports
        def interrupted(*args,**kwargs):generate_reports(*args,**kwargs);raise OSError('after report snapshot')
        with patch('workbench.reports.generate_reports',side_effect=interrupted):
            try:self.c.advance('process-a')
            except OSError:pass
        self.assertFalse(self.c.ledger.get('process-a').get('report_verified',False))
        self.assertEqual(self.c.ledger.history('process-a'),[])
        doc=self.c.ledger.get('process-a');doc['next_retry_at']=0;self.c.ledger.save(doc)
        self.c.advance('process-a');self.assertEqual(len(self.c.ledger.history('process-a')),1)

    def test_constructor_failure_releases_workspace_lock(self):
        self.c.close()
        with patch('workbench.provider.configured_provider',side_effect=ValueError('invalid provider')):
            with self.assertRaises(ValueError):Coordinator(self.root)
        self.c=Coordinator(self.root)

    def test_restart_interrupted_verification_retains_one_packet_and_one_return(self):
        self.prepared();before=self.c.ledger.get('process-a')
        from workbench.coordinator import verify_program
        with patch('workbench.coordinator.verify_program',side_effect=OSError('crash after frozen fixtures')):
            with self.assertRaises(OSError):self.c.advance('process-a')
        self.c.close();self.c=Coordinator(self.root)
        doc=self.c.ledger.get('process-a');doc['next_retry_at']=0;self.c.ledger.save(doc)
        self.c.advance('process-a');self.c.advance('process-a');doc=self.c.ledger.get('process-a')
        self.assertEqual(doc['status'],'COMPLETED');self.assertEqual(len(doc['runs']),1)
        self.assertEqual(doc['packet_hash'],before['packet_hash']);self.assertTrue(doc['packet_imported'])
        self.assertEqual(len(list((self.root/'processes/process-a/synthetic').glob('run-*'))),2)
        self.assertTrue(any('/run-0001/' in path for path in doc['artifacts']))

    def test_permanent_stage_validation_is_not_automatically_retried(self):
        self.prepared()
        from workbench.domain import ValidationError
        with patch('workbench.coordinator.plan_cases',side_effect=ValidationError('unsupported contract')) as fixture:
            with self.assertRaises(ValidationError):self.c.advance('process-a')
            self.c.advance('process-a')
        doc=self.c.ledger.get('process-a');self.assertEqual(doc['status'],'FAILED');self.assertEqual(fixture.call_count,1)

    def test_missing_report_outputs_cannot_certify_completion(self):
        self.prepared();self.c.advance('process-a')
        from workbench.domain import ValidationError
        with patch('workbench.reports.generate_reports',return_value=[]):
            with self.assertRaises(ValidationError):self.c.advance('process-a')
        doc=self.c.ledger.get('process-a');self.assertEqual(doc['status'],'REPORTING_FAILED');self.assertFalse(doc.get('report_verified',False))

    def test_cancel_during_report_rebuilds_blocked_terminal_artifacts(self):
        self.prepared();self.c.advance('process-a')
        from workbench.reports import generate_reports
        def cancelled(*args,**kwargs):
            outputs=generate_reports(*args,**kwargs);self.c.control('process-a','cancel');return outputs
        with patch('workbench.reports.generate_reports',side_effect=cancelled):self.c.advance('process-a')
        doc=self.c.ledger.get('process-a');self.assertEqual(doc['status'],'QUEUED_REPORT');self.assertFalse(doc.get('report_verified',False))
        self.c.advance('process-a');doc=self.c.ledger.get('process-a')
        self.assertEqual(doc['status'],'COMPLETED_WITH_BLOCKERS')
        from workbench.domain import decode
        metrics=next(path for path in doc['report_hashes'] if path.endswith('/metrics.json'))
        model=decode(self.c.artifact('process-a',metrics).read_bytes())
        self.assertTrue(any(b['kind']=='cancelled' for b in model['blockers']))

    def test_local_export_never_silently_drops_unknown_text_extension(self):
        folder=self.root/'Endeavor';folder.mkdir();(folder/'ELIGIBLE.cbl').write_text(test_workflow.COBOL)
        (folder/'UNKNOWN.export').write_text('EXEC SOME-UNSUPPORTED-PLATFORM\n')
        doc=self.c.create(test_workflow.MANIFEST)
        self.assertIn('UNKNOWN.export',doc['source_files'])

    def test_close_returns_bounded_and_keeps_lock_until_active_checkpoint(self):
        self.prepared();entered=threading.Event();release=threading.Event()
        from workbench.coordinator import plan_cases
        def blocked(*args):entered.set();release.wait(3);return plan_cases(*args)
        with patch('workbench.coordinator.plan_cases',side_effect=blocked):
            self.c.launch_worker();self.assertTrue(entered.wait(2));started=time.monotonic();self.c.close()
            self.assertLess(time.monotonic()-started,1)
            from workbench.domain import ValidationError
            with self.assertRaises(ValidationError):Coordinator(self.root)
            release.set();self.c.worker.join(3)
        self.c=Coordinator(self.root);self.assertEqual(self.c.ledger.get('process-a')['status'],'QUEUED_VERIFY')

    def test_changed_sme_return_is_blocked_before_target_execution(self):
        self.prepared();returned=self.root/'processes/process-a/input/sme-return.xlsx'
        returned.write_bytes(b'changed preserved workbook')
        with patch('workbench.coordinator.verify_program') as execute:self.c.advance('process-a')
        execute.assert_not_called();self.c.advance('process-a');doc=self.c.ledger.get('process-a')
        self.assertEqual(doc['status'],'COMPLETED_WITH_BLOCKERS')
        self.assertTrue(any(b['kind']=='evidence_integrity' for b in doc['blockers']))

    def test_packet_issue_crash_recovery_registers_packet_without_extra_quota(self):
        self.create();self.c.start('process-a');issue=self.c.ledger.issue_packet
        def crash(*args):issue(*args);raise OSError('crash after quota commit')
        with patch.object(self.c.ledger,'issue_packet',side_effect=crash):
            with self.assertRaises(OSError):self.c.advance('process-a')
        first=self.c.ledger.get('process-a');self.assertTrue(first['packet_issued'])
        self.c.close();self.c=Coordinator(self.root)
        doc=self.c.ledger.get('process-a');doc['next_retry_at']=0;self.c.ledger.save(doc)
        self.c.advance('process-a');doc=self.c.ledger.get('process-a')
        self.assertEqual(doc['status'],'WAITING_SME');self.assertEqual(doc['packet_hash'],first['packet_hash'])
        self.assertTrue(self.c.artifact('process-a','review/sme-checklist.xlsx').is_file())

    def test_terminal_commit_failure_cannot_leave_accepted_history(self):
        self.prepared();self.c.advance('process-a')
        self.c.ledger.db.executescript("CREATE TRIGGER reject_completion BEFORE UPDATE ON processes WHEN NEW.status IN ('COMPLETED','COMPLETED_WITH_BLOCKERS') BEGIN SELECT RAISE(ABORT,'simulated ledger interruption'); END;")
        import sqlite3
        with self.assertRaises(sqlite3.IntegrityError):self.c.advance('process-a')
        doc=self.c.ledger.get('process-a');self.assertEqual(doc['status'],'REPORTING_FAILED')
        self.assertFalse(doc['report_verified']);self.assertEqual(self.c.ledger.history('process-a'),[])
        self.c.ledger.db.executescript('DROP TRIGGER reject_completion;')
        self.c.control('process-a','resume');self.c.advance('process-a')
        self.assertEqual(self.c.ledger.get('process-a')['status'],'COMPLETED')
        self.assertEqual(len(self.c.ledger.history('process-a')),1)

    def test_failed_stage_cannot_be_paused_into_unrecoverable_status(self):
        self.prepared()
        from workbench.domain import ValidationError
        with patch('workbench.coordinator.plan_cases',side_effect=ValidationError('unsupported contract')):
            with self.assertRaises(ValidationError):self.c.advance('process-a')
        with self.assertRaises(ValidationError):self.c.control('process-a','pause')
        doc=self.c.ledger.get('process-a');self.assertEqual(doc['status'],'FAILED');self.assertEqual(doc['resume_status'],'QUEUED_VERIFY')
        self.c.control('process-a','resume');self.c.advance('process-a')
        self.assertEqual(self.c.ledger.get('process-a')['status'],'QUEUED_REPORT')

    def test_report_failure_cannot_be_paused_into_unrecoverable_status(self):
        self.prepared();self.c.advance('process-a')
        from workbench.domain import ValidationError
        with patch('workbench.reports.generate_reports',side_effect=ValidationError('inspection failed')):
            with self.assertRaises(ValidationError):self.c.advance('process-a')
        with self.assertRaises(ValidationError):self.c.control('process-a','pause')
        doc=self.c.ledger.get('process-a');self.assertEqual(doc['status'],'REPORTING_FAILED');self.assertEqual(doc['resume_status'],'QUEUED_REPORT')
        self.c.control('process-a','resume');self.c.advance('process-a')
        self.assertEqual(self.c.ledger.get('process-a')['status'],'COMPLETED')

    def test_local_crlf_export_snapshot_preserves_exact_original_bytes(self):
        folder=self.root/'Endeavor';folder.mkdir();raw=test_workflow.COBOL.replace('\n','\r\n').encode('utf-8')
        (folder/'ELIGIBLE.cbl').write_bytes(raw)
        doc=self.c.create(test_workflow.MANIFEST)
        from workbench.domain import sha
        self.assertEqual(doc['source_files']['ELIGIBLE.cbl'],sha(raw))
        self.assertEqual((self.root/'processes/process-a/input/sources/ELIGIBLE.cbl').read_bytes(),raw)

    def test_malformed_or_unencodable_source_map_fails_before_state_creation(self):
        from workbench.domain import ValidationError
        for sources in ({'ELIGIBLE.cbl':None},{'ELIGIBLE.cbl':5},['not a mapping'],
                        {'ELIGIBLE.cbl':'bad\ud800source'},{'bad\ud800.cbl':'text'},{}):
            with self.subTest(sources=repr(sources)):
                with self.assertRaises(ValidationError):self.c.create(test_workflow.MANIFEST,sources)
                self.assertEqual(self.c.ledger.list(True),[])

    def test_changed_manifest_is_blocked_before_target_execution_and_completion(self):
        self.prepared();manifest=self.root/'processes/process-a/input/process-input.md'
        manifest.write_text(test_workflow.MANIFEST.replace('Always','RC=999'))
        with patch('workbench.coordinator.verify_program') as execute:self.c.advance('process-a')
        execute.assert_not_called();self.c.advance('process-a');doc=self.c.ledger.get('process-a')
        self.assertEqual(doc['status'],'COMPLETED_WITH_BLOCKERS');self.assertFalse(doc['coverage_summary']['completion_eligible'])
        self.assertTrue(any(b['kind']=='evidence_integrity' for b in doc['blockers']))

    def test_missing_manifest_baseline_is_never_pinned_on_resume(self):
        self.prepared();doc=self.c.ledger.get('process-a');doc.pop('manifest_hash',None);self.c.ledger.save(doc)
        with patch('workbench.coordinator.verify_program') as execute:self.c.advance('process-a')
        execute.assert_not_called();doc=self.c.ledger.get('process-a')
        self.assertNotIn('manifest_hash',doc);self.assertEqual(doc['status'],'QUEUED_REPORT')
        self.assertTrue(any('baseline' in b['message'].lower() for b in doc['blockers']))

    def test_registered_review_artifact_tamper_is_rejected_without_repinning(self):
        self.create();self.c.start('process-a');self.c.advance('process-a')
        original=self.c.ledger.get('process-a')
        path=self.root/'processes/process-a/review/sme-checklist.docx';path.write_bytes(path.read_bytes()+b'tampered')
        from workbench.domain import ValidationError
        with self.assertRaises(ValidationError):self.c.artifact('process-a','review/sme-checklist.docx')
        with self.assertRaises(ValidationError):self.c.register(original,'review/sme-checklist.docx')

    def test_target_database_is_pinned_after_connection_closes(self):
        self.prepared();self.c.advance('process-a');doc=self.c.ledger.get('process-a')
        relative='target/'+doc['runs'][-1]['id']+'/target.sqlite'
        self.assertIn(relative,doc.get('artifact_hashes',{}))
        import sqlite3
        with sqlite3.connect(self.root/'processes/process-a'/relative) as db:db.execute('DELETE FROM results')
        from workbench.domain import ValidationError
        with self.assertRaises(ValidationError):self.c.artifact('process-a',relative)

    def test_completed_manifest_tamper_invalidates_current_certification_on_restart(self):
        self.prepared();self.c.advance('process-a');self.c.advance('process-a')
        manifest=self.root/'processes/process-a/input/process-input.md';manifest.write_text(test_workflow.MANIFEST.replace('Always','RC=999'))
        self.c.close();self.c=Coordinator(self.root)
        doc=self.c.ledger.get('process-a');self.assertEqual(doc['status'],'QUEUED_REPORT');self.assertFalse(doc['report_verified'])
        self.c.advance('process-a');self.assertEqual(self.c.ledger.get('process-a')['status'],'COMPLETED_WITH_BLOCKERS')

    def test_constructor_never_repins_changed_companion_review_artifact(self):
        self.create();self.c.start('process-a');self.c.advance('process-a');self.c.close()
        path=self.root/'processes/process-a/review/sme-checklist.html';path.write_text('changed frozen companion')
        from workbench.domain import ValidationError
        with self.assertRaisesRegex(ValidationError,'changed'):Coordinator(self.root)
        from workbench.instance import InstanceLock
        lock=InstanceLock(self.root);lock.close()

    def test_blocked_reports_remain_downloadable_when_manifest_is_corrupt(self):
        self.prepared();manifest=self.root/'processes/process-a/input/process-input.md';manifest.write_text(test_workflow.MANIFEST.replace('Always','RC=999'))
        self.c.advance('process-a');self.c.advance('process-a');doc=self.c.ledger.get('process-a')
        self.assertEqual(doc['status'],'COMPLETED_WITH_BLOCKERS')
        relative=next(p for p in doc['report_hashes'] if p.endswith('/management.pptx'))
        path=self.c.artifact('process-a',relative);self.assertTrue(path.read_bytes().startswith(b'PK'))
        coverage=next(p for p in doc['report_hashes'] if p.endswith('/coverage.json'))
        self.assertTrue(self.c.artifact('process-a',coverage).is_file())
        path.write_bytes(path.read_bytes()+b'changed report')
        from workbench.domain import ValidationError
        with self.assertRaises(ValidationError):self.c.artifact('process-a',relative)
        with self.assertRaises(ValidationError):self.c.artifact('process-a','review/sme-checklist.xlsx')

    def test_legacy_missing_baselines_restarts_service_and_emits_pinned_blocked_reports(self):
        self.prepared();self.c.advance('process-a');self.c.advance('process-a')
        doc=self.c.ledger.get('process-a');old_files={p:(self.root/'processes/process-a'/p).read_bytes() for p in doc['artifacts']}
        doc.pop('manifest_hash');doc.pop('artifact_hashes');self.c.ledger.save(doc);self.c.close()
        self.c=Coordinator(self.root);legacy=self.c.ledger.get('process-a')
        self.assertEqual(legacy['status'],'QUEUED_REPORT');self.assertFalse(legacy['report_verified'])
        self.assertNotIn('manifest_hash',legacy);self.assertFalse(legacy.get('artifact_hashes'))
        self.c.create(test_workflow.MANIFEST.replace('process-a','process-b'),{'ELIGIBLE.cbl':test_workflow.COBOL})
        with patch('workbench.fixtures.verify_program') as target,patch('workbench.target.run_generated') as execute:
            self.c.advance('process-a')
        target.assert_not_called();execute.assert_not_called()
        legacy=self.c.ledger.get('process-a');self.assertEqual(legacy['status'],'COMPLETED_WITH_BLOCKERS')
        self.assertTrue(any(b['kind']=='legacy_missing_baseline' for b in legacy['blockers']))
        self.assertTrue(legacy['packet_issued']);self.assertTrue(legacy['packet_imported'])
        from workbench.domain import ValidationError
        with self.assertRaises(ValidationError):self.c.artifact('process-a','review/sme-checklist.xlsx')
        output=next(p for p in legacy['report_hashes'] if p.endswith('/management.pptx'))
        self.assertTrue(self.c.artifact('process-a',output).read_bytes().startswith(b'PK'))
        for relative,raw in old_files.items():self.assertEqual((self.root/'processes/process-a'/relative).read_bytes(),raw)
        report_hashes=legacy['report_hashes'];history_count=len(self.c.ledger.history('process-a'))
        self.c.close();self.c=Coordinator(self.root);self.c.advance('process-a')
        self.assertEqual(self.c.ledger.get('process-a')['status'],'COMPLETED_WITH_BLOCKERS')
        self.assertEqual(self.c.ledger.get('process-a')['report_hashes'],report_hashes)
        self.assertEqual(len(self.c.ledger.history('process-a')),history_count)
