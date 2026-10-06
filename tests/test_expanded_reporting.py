"""R801–R900: new executive decision, delivery and cross-artifact checks.

SME answers used here are explicitly fictional local regression data.
"""
import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from workbench import runner
from workbench.domain import ValidationError, sha
import test_review500_reporting as old_reviews


class ExpandedReportingTests(unittest.TestCase):
    setUpClass = classmethod(old_reviews.Review500ReportingTests.setUpClass.__func__)
    tearDownClass = classmethod(old_reviews.Review500ReportingTests.tearDownClass.__func__)
    setUp = old_reviews.Review500ReportingTests.setUp
    coordinator = old_reviews.Review500ReportingTests.coordinator
    coverage = old_reviews.Review500ReportingTests.coverage
    target_path = old_reviews.Review500ReportingTests.target_path

    def model(self, changes=None):
        from workbench.reports import metrics
        from workbench.executive import executive_summary
        coverage = self.coverage()
        m = metrics(self.ledger, self.doc, coverage)
        if changes: m.update(changes)
        return executive_summary(self.doc, m, coverage)

    def test_r801_new_report_has_one_accepted_executive_entry(self):
        """A completed conversion must expose one primary executive file."""
        paths = [p for p in self.doc['report_hashes'] if p.endswith('/executive-report.html')]
        self.assertEqual(len(paths), 1)
        self.assertIn(paths[0], self.doc['artifacts'])

    def frozen(self):
        return json.loads((self.base/'reports/report-0001/metrics.json').read_text())

    def rendered(self, model=None):
        from workbench.executive import render_executive
        return render_executive(model or self.model())

    def executive_doc(self):
        from workbench.executive import accepted_executive
        return accepted_executive(self.coordinator(),self.doc)

    def rewrite_accepted_model(self, edit):
        relative='reports/report-0001/metrics.json'; path=self.base/relative
        model=json.loads(path.read_text()); edit(model); path.write_text(json.dumps(model))
        self.doc['artifact_hashes'][relative]=self.doc['report_hashes'][relative]=sha(path.read_bytes())

    def test_r802_frozen_decision_counts_reconcile_with_exact_lineage(self):
        e=self.frozen()['executive']; c=json.loads((self.base/'reports/report-0001/coverage.json').read_text())
        self.assertEqual(e['progress']['converted_lines'],sum(r['disposition'] in ('mapped_verified','platform_replaced_verified') for r in c['rows']))
        self.assertEqual(e['scope']['physical_lines'],len(c['rows']))

    def test_r803_generated_programs_are_not_called_verified_programs(self):
        e=self.model({'target_python_programs':7})
        self.assertEqual(e['before_after'][0]['after'],7)
        self.assertIn('generation alone',e['before_after'][0]['basis'])

    def test_r804_size_reduction_never_changes_verification_percentage(self):
        before=self.model(); after=self.model({'target_program_code_loc':0})
        self.assertEqual(before['progress'],after['progress'])
        self.assertIn('not parity',after['before_after'][1]['basis'])

    def test_r805_excluded_scope_is_visible_without_inflating_conversion(self):
        c=self.frozen()['metrics']; total=c['source_accounted_lines']
        e=self.model({'source_accounted_lines':total+11,'source_out_of_scope_lines':11})
        self.assertEqual(e['scope']['excluded_lines'],11)
        self.assertEqual(e['progress']['verification_percent'],100)
        self.assertIn('11 excluded',self.rendered(e))

    def test_r806_nonexecutable_lines_are_separate_from_conversion_denominator(self):
        m=self.frozen()['metrics']; n=m['source_non_executable_lines']
        e=self.model({'source_accounted_lines':m['source_accounted_lines']+3,'source_in_scope_lines':m['source_in_scope_lines']+3,'source_non_executable_lines':n+3})
        self.assertEqual(e['scope']['non_executable_lines'],n+3)
        self.assertEqual(e['progress']['verification_percent'],100)

    def test_r807_blocked_lines_reduce_progress_and_drive_action(self):
        m=self.frozen()['metrics']; e=self.model({'source_verified_applicable_lines':m['source_verified_applicable_lines']-2,'source_blocked_lines':2,'source_completion_eligible':False})
        self.assertLess(e['progress']['verification_percent'],100)
        self.assertTrue(any('2 blocked source lines' in a for a in e['next_actions']))

    def test_r808_unverified_mappings_are_not_counted_as_blocked(self):
        m=self.frozen()['metrics']; e=self.model({'source_verified_applicable_lines':m['source_verified_applicable_lines']-3,'source_unverified_mapped_lines':3,'source_completion_eligible':False})
        self.assertEqual((e['progress']['blocked_lines'],e['progress']['unverified_lines']),(0,3))
        self.assertTrue(any('3 mapped but unverified' in a for a in e['next_actions']))

    def test_r809_zero_applicable_lines_render_unknown_not_success_rate(self):
        m=self.frozen()['metrics']; e=self.model({'source_applicable_lines':0,'source_verified_applicable_lines':0,'source_non_executable_lines':m['source_in_scope_lines'],'source_completion_eligible':False})
        self.assertIsNone(e['progress']['verification_percent'])
        self.assertIn('Unknown (no applicable lines)',self.rendered(e))

    def test_r810_same_display_rounding_uses_actual_numerator(self):
        e=self.model({'source_accounted_lines':3,'source_in_scope_lines':3,'source_applicable_lines':3,'source_non_executable_lines':0,'source_verified_applicable_lines':1,'source_blocked_lines':2,'source_completion_eligible':False})
        self.assertEqual(e['progress']['verification_percent'],33.33)
        self.assertIn('1 / 3 lines',self.rendered(e))

    def test_r811_reported_percent_is_recomputed_from_counts(self):
        e=self.model({'source_applicable_line_verification_percent':0})
        self.assertEqual(e['progress']['verification_percent'],100)

    def test_r812_blocker_only_failure_keeps_verified_line_count_honest(self):
        self.doc['blockers']=[{'kind':'external_decision','message':'Pending scope decision'}]
        e=self.model(); self.assertEqual(e['status'],'COMPLETED_WITH_BLOCKERS')
        self.assertEqual(e['progress']['verification_percent'],100)
        self.assertEqual(e['progress']['open_blockers'],1)

    def test_r813_cancel_requested_overrides_eligible_report_label(self):
        self.doc['cancel_requested']=True; e=self.model()
        self.assertEqual(e['status'],'CANCELLED'); self.assertFalse(e['progress']['completion_eligible'])
        self.assertIn('authorize a new process',e['next_actions'][0])

    def test_r814_terminal_cancelled_without_flag_stays_cancelled(self):
        self.doc['status']='CANCELLED'; e=self.model()
        self.assertEqual(e['status'],'CANCELLED')
        self.assertNotIn('before production use',e['next_actions'][0])

    def test_r815_source_integrity_recovery_is_first_next_action(self):
        e=self.model({'source_integrity_errors':2})
        self.assertIn('Recover the original',e['next_actions'][0])
        self.assertIn('do not repin',e['next_actions'][0])

    def test_r816_unreturned_packet_action_preserves_one_human_round(self):
        self.doc['packet_imported']=False; e=self.model()
        self.assertTrue(any('one issued SME checklist' in a and 'actual reviewer' in a for a in e['next_actions']))

    def test_r817_decision_actions_cap_at_three_with_multiple_failures(self):
        self.doc['packet_imported']=False; self.doc['blockers']=[{'kind':'test','message':'a'}]*20
        m=self.frozen()['metrics']; e=self.model({'source_integrity_errors':1,'source_verified_applicable_lines':m['source_verified_applicable_lines']-2,'source_blocked_lines':1,'source_unverified_mapped_lines':1})
        self.assertEqual(len(e['next_actions']),3)
        self.assertIn('Recover',e['next_actions'][0]); self.assertIn('checklist',e['next_actions'][1]); self.assertIn('blocked',e['next_actions'][2])

    def test_r818_cancel_action_does_not_propose_replaying_targets(self):
        self.doc['cancel_requested']=True; self.doc['packet_imported']=False
        e=self.model({'source_integrity_errors':3})
        self.assertEqual(len(e['next_actions']),1)
        self.assertIn('Preserve',e['next_actions'][0])

    def test_r819_verified_result_still_calls_for_next_validation_scope(self):
        e=self.model(); self.assertEqual(e['status'],'COMPLETED')
        self.assertIn('next validation scope',e['next_actions'][0])
        self.assertIn('production readiness are not established',e['boundary'])

    def test_r820_demo_report_is_explicitly_marked_in_primary_view(self):
        self.doc['demo']=True; e=self.model()
        self.assertIn('Demonstration',self.rendered(e)); self.assertTrue(e['demo'])

    def test_r821_fictional_fixture_label_survives_non_demo_mode(self):
        self.doc['fixture_only']=True; self.doc['demo']=False
        self.assertIn('Fictional test fixture',self.rendered())

    def test_r822_rule_metric_cannot_replace_applicable_line_percentage(self):
        e=self.model({'known_rule_verification_percent':0,'rules_verified':0})
        self.assertEqual(e['progress']['verification_percent'],100)
        self.assertIn('physical source lines',e['progress']['denominator'])
        rules=next(r for r in e['before_after'] if r['label']=='Known rules')
        self.assertEqual(rules['after'],0);self.assertIn('documented',rules['basis'])

    def test_r823_business_screen_after_value_excludes_workbench_controls(self):
        e=self.model({'source_bms_screens':4}); row=e['before_after'][2]
        self.assertEqual((row['before'],row['after']),(4,0)); self.assertIn('workbench controls are excluded',row['basis'])
        apis=next(r for r in e['before_after'] if r['label']=='Business REST APIs')
        self.assertIsNone(apis['before']);self.assertEqual(apis['after'],0)

    def test_r824_source_and_target_sizes_keep_different_names(self):
        e=self.model({'source_code_loc':900,'target_program_code_loc':20})
        self.assertEqual((e['before_after'][1]['before'],e['before_after'][1]['after']),(900,20))
        self.assertIn('Selected source code LOC',e['before_after'][1]['basis'])
        rows={r['label']:r for r in e['before_after']}
        self.assertEqual(rows['Copybooks']['before'],self.frozen()['metrics']['source_copybooks'])
        self.assertIsNone(rows['Copybooks']['after'])
        self.assertIn('not an estate inventory',rows['Db2 table references']['basis'])

    def test_r825_program_scope_is_selected_membership_count(self):
        e=self.model({'source_programs':2,'target_python_programs':1,'portfolio_completed_processes':99})
        self.assertEqual((e['before_after'][0]['before'],e['before_after'][0]['after']),(2,1))
        self.assertIn('<th scope="row">Programs</th><td>2</td><td>1</td>',self.rendered(e))
        self.assertNotIn('<th scope="row">Programs</th><td>99</td>',self.rendered(e))

    def test_r826_counts_above_thousand_remain_exact_and_legible(self):
        e=self.model({'source_accounted_lines':12345,'source_in_scope_lines':12345,'source_applicable_lines':12345,'source_non_executable_lines':0,'source_verified_applicable_lines':12345})
        self.assertEqual(e['progress']['converted_lines'],12345)
        self.assertIn('12,345 / 12,345 lines',self.rendered(e))

    def test_r827_missing_analysis_has_no_fabricated_lineage_hash(self):
        from workbench.executive import executive_summary
        m=self.frozen()['metrics']; self.doc['analysis']=None
        e=executive_summary(self.doc,m)
        self.assertIsNone(e['lineage']['source_snapshot'])

    def test_r828_executive_projection_does_not_mutate_frozen_inputs(self):
        from workbench.executive import executive_summary
        m=self.frozen()['metrics']; doc_before=copy.deepcopy(self.doc); before=copy.deepcopy(m)
        executive_summary(self.doc,m)
        self.assertEqual(self.doc,doc_before); self.assertEqual(m,before)

    def test_r829_executive_projection_is_deterministic_without_clock(self):
        self.assertEqual(self.model(),self.model())
        self.assertEqual(self.model()['scope_unknowns'],['CICS transactions','VSAM files','Inbound interfaces','Outbound interfaces'])
        self.assertIn('Unknown scope:',self.rendered())

    def test_r830_cross_process_metric_projection_is_rejected(self):
        with self.assertRaisesRegex(ValidationError,'different process'): self.model({'process_id':'another-process'})

    def test_r831_negative_denominator_is_rejected_before_rendering(self):
        with self.assertRaisesRegex(ValidationError,'nonnegative'):self.model({'source_applicable_lines':-1})

    def test_r832_boolean_counts_cannot_masquerade_as_one_line(self):
        with self.assertRaisesRegex(ValidationError,'integer'):self.model({'source_inventory_files':True})

    def test_r833_fractional_converted_lines_are_rejected(self):
        with self.assertRaisesRegex(ValidationError,'integer'):self.model({'source_verified_applicable_lines':1.5})

    def test_r834_string_denominator_is_not_silently_coerced(self):
        with self.assertRaisesRegex(ValidationError,'integer'):self.model({'source_in_scope_lines':'15'})

    def test_r835_unknown_line_count_is_not_reported_as_zero(self):
        with self.assertRaisesRegex(ValidationError,'integer'):self.model({'source_accounted_lines':None})

    def test_r836_mismatched_scope_partition_blocks_report(self):
        with self.assertRaisesRegex(ValidationError,'reconcile'):self.model({'source_out_of_scope_lines':9})

    def test_r837_unaccounted_applicable_line_blocks_report(self):
        m=self.frozen()['metrics']
        with self.assertRaisesRegex(ValidationError,'reconcile'):self.model({'source_verified_applicable_lines':m['source_verified_applicable_lines']-1})

    def test_r838_double_counted_nonexecutable_line_blocks_report(self):
        m=self.frozen()['metrics']
        with self.assertRaisesRegex(ValidationError,'reconcile'):self.model({'source_non_executable_lines':m['source_non_executable_lines']+1})

    def test_r839_overcredited_converted_lines_cannot_exceed_scope(self):
        m=self.frozen()['metrics']
        with self.assertRaisesRegex(ValidationError,'reconcile'):self.model({'source_verified_applicable_lines':m['source_applicable_lines']+1})

    def test_r840_stale_metrics_final_status_cannot_override_live_blocker(self):
        self.doc['blockers']=[{'kind':'evidence','message':'missing'}]
        self.assertEqual(self.model({'report_final_status':'COMPLETED'})['status'],'COMPLETED_WITH_BLOCKERS')

    def test_r841_markup_in_process_name_cannot_create_executable_html(self):
        self.doc['name']='x</h1><script>alert(1)</script>'
        text=self.rendered(); self.assertNotIn('<script>',text); self.assertIn('&lt;script&gt;',text)

    def test_r842_quotes_in_identity_are_escaped_in_document_title(self):
        e=self.model(); e['process_id']='a"<img src=x onerror=alert(1)>'
        text=self.rendered(e); self.assertIn('&quot;&lt;img',text); self.assertNotIn('<img',text)

    def test_r843_hostile_blocker_prose_stays_in_evidence_not_main_view(self):
        self.doc['blockers']=[{'kind':'fixture','message':'SECRET<script>run()</script>'}]
        self.assertNotIn('SECRET',self.rendered()); self.assertIn('recorded blockers',self.rendered())

    def test_r844_unicode_process_name_is_preserved(self):
        self.doc['name']='Café 日本語 — Δ'
        self.assertIn(self.doc['name'],self.rendered())

    def test_r845_long_name_wraps_without_fixed_card_height(self):
        self.doc['name']='Long process name '*100
        text=self.rendered(); self.assertIn(self.doc['name'],text)
        self.assertNotIn('overflow:hidden',text)

    def test_r846_primary_report_contains_no_external_assets(self):
        from html.parser import HTMLParser
        text=self.rendered()
        self.assertNotIn('https://',text); self.assertNotIn('<script',text); self.assertNotIn('<link',text)

    def test_r847_supporting_evidence_is_collapsed_by_default(self):
        from workbench.executive import _Inspection
        parser=_Inspection();parser.feed(self.rendered())
        self.assertEqual(parser.details,1);self.assertFalse(parser.unsafe)

    def test_r848_primary_view_exposes_lineage_and_slides_inside_disclosure(self):
        text=self.rendered(); disclosure=text[text.index('<details>'):]
        self.assertIn('href="coverage.html"',disclosure); self.assertIn('href="management.pptx"',disclosure)
        self.assertNotIn('href=',text[:text.index('<details>')])

    def test_r849_declared_analysis_evidence_gets_process_relative_link(self):
        links={x['file'] for x in self.model()['evidence']}
        self.assertIn('../../analysis/source-analysis.json',links)

    def test_r850_absent_analysis_artifact_never_gets_dead_link(self):
        self.doc['artifacts'].remove('analysis/source-analysis.json')
        self.assertNotIn('../../analysis/source-analysis.json',{x['file'] for x in self.model()['evidence']})

    def test_r851_blocked_counts_override_stale_completion_eligibility(self):
        m=self.frozen()['metrics']; e=self.model({'source_verified_applicable_lines':m['source_verified_applicable_lines']-1,'source_blocked_lines':1,'source_completion_eligible':True})
        self.assertEqual(e['status'],'COMPLETED_WITH_BLOCKERS')
        self.assertFalse(self.model({'source_full_accounting':False})['progress']['completion_eligible'])
        self.doc['packet_imported']=False
        self.assertFalse(self.model()['progress']['completion_eligible'])
        self.doc['packet_imported']=True;self.doc['verification_finished']=False
        self.assertFalse(self.model()['progress']['completion_eligible'])

    def test_r852_integrity_failure_cannot_retain_completed_label(self):
        e=self.model({'source_integrity_errors':1,'source_completion_eligible':True})
        self.assertFalse(e['progress']['completion_eligible'])

    def test_r853_empty_scope_action_does_not_suggest_accepting_conversion(self):
        m=self.frozen()['metrics']; e=self.model({'source_applicable_lines':0,'source_verified_applicable_lines':0,'source_non_executable_lines':m['source_in_scope_lines'],'source_completion_eligible':False})
        self.assertIn('incomplete',e['next_actions'][0])

    def test_r854_zero_applicable_eligibility_cannot_be_forged(self):
        m=self.frozen()['metrics']; e=self.model({'source_applicable_lines':0,'source_verified_applicable_lines':0,'source_non_executable_lines':m['source_in_scope_lines'],'source_completion_eligible':True})
        self.assertFalse(e['progress']['completion_eligible'])

    def test_r855_inspection_rejects_changed_visible_converted_count(self):
        from workbench.executive import inspect_executive
        e=self.model();text=self.rendered(e).replace('Converted and verified','Fraudulent conversion',1)
        with self.assertRaises(ValidationError):inspect_executive(text,e)

    def test_r856_inspection_rejects_external_evidence_destinations(self):
        from workbench.executive import inspect_executive
        e=self.model(); e['evidence'][0]['file']='https://example.invalid/source'
        with self.assertRaises(ValidationError):inspect_executive(self.rendered(e),e)

    def test_r857_inspection_rejects_traversal_outside_fixed_evidence_targets(self):
        from workbench.executive import inspect_executive
        e=self.model(); e['evidence'][0]['file']='../../../../private.txt'
        with self.assertRaises(ValidationError):inspect_executive(self.rendered(e),e)

    def test_r858_inspection_rejects_script_protocol_links(self):
        from workbench.executive import inspect_executive
        e=self.model();e['evidence'][0]['file']='javascript:alert(1)'
        with self.assertRaises(ValidationError):inspect_executive(self.rendered(e),e)

    def test_r859_inspection_requires_disclosure_to_start_closed(self):
        from workbench.executive import inspect_executive
        e=self.model()
        with self.assertRaises(ValidationError):inspect_executive(self.rendered(e).replace('<details>','<details open>'),e)

    def test_r860_inspection_catches_missing_boundary_statement(self):
        from workbench.executive import inspect_executive
        e=self.model()
        with self.assertRaises(ValidationError):inspect_executive(self.rendered(e).replace(e['boundary'],''),e)

    def test_r861_inspection_catches_missing_evidence_anchor(self):
        from workbench.executive import inspect_executive
        e=self.model();text=self.rendered(e).replace('href="coverage.html"','href="metrics.json"')
        with self.assertRaises(ValidationError):inspect_executive(text,e)

    def test_r862_inspection_catches_event_handler_injected_in_report(self):
        from workbench.executive import inspect_executive
        e=self.model()
        with self.assertRaises(ValidationError):inspect_executive(self.rendered(e).replace('<h1>','<h1 onmouseover="x()">'),e)

    def test_r863_inspection_catches_duplicate_main_heading(self):
        from workbench.executive import inspect_executive
        e=self.model()
        with self.assertRaises(ValidationError):inspect_executive(self.rendered(e).replace('</main>','<h1>Other process</h1></main>'),e)

    def test_r864_report_inspection_records_executive_hash_and_contract(self):
        p=self.base/'reports/report-0001';i=json.loads((p/'inspection.json').read_text())
        self.assertEqual(i['primary_report'],'executive-report.html'); self.assertTrue(i['executive_html_checked'])
        self.assertEqual(i['sha256']['executive-report.html'],sha((p/'executive-report.html').read_bytes()))

    def test_r865_primary_report_is_returned_first_by_report_generator(self):
        from workbench.reports import generate_reports
        p=self.root/'.implementation/tmp/new-report'
        paths=generate_reports(self.ledger,self.doc,p)
        self.assertEqual(paths[0].name,'executive-report.html')

    def test_r866_primary_collision_prevents_any_partial_generation(self):
        from workbench.reports import generate_reports
        p=self.root/'.implementation/tmp/collision';p.mkdir(parents=True);(p/'executive-report.html').write_text('issued')
        with self.assertRaises(ValidationError):generate_reports(self.ledger,self.doc,p)
        self.assertEqual([x.name for x in p.iterdir()],['executive-report.html'])

    def test_r867_primary_symlink_collision_is_not_followed(self):
        from workbench.reports import generate_reports
        p=self.root/'.implementation/tmp/collision';p.mkdir(parents=True);(p/'executive-report.html').symlink_to(p/'missing')
        with self.assertRaises(ValidationError):generate_reports(self.ledger,self.doc,p)
        self.assertTrue((p/'executive-report.html').is_symlink());self.assertFalse((p/'missing').exists())

    def test_r868_inspection_failure_never_issues_passing_receipt(self):
        from workbench.reports import generate_reports
        p=self.root/'.implementation/tmp/inspection-failure'
        with patch('workbench.reports.inspect_executive',side_effect=ValidationError('bad executive')),self.assertRaises(ValidationError):generate_reports(self.ledger,self.doc,p)
        self.assertFalse((p/'inspection.json').exists());self.assertTrue((p/'management.pptx').is_file())

    def test_r869_report_regeneration_preserves_old_executive_bytes(self):
        from workbench.reports import generate_reports
        p=self.base/'reports/report-0001/executive-report.html';before=p.read_bytes()
        generate_reports(self.ledger,self.doc,self.root/'.implementation/tmp/revised-view')
        self.assertEqual(p.read_bytes(),before)

    def test_r870_report_generation_creates_no_new_markdown_artifacts(self):
        self.assertFalse(list((self.base/'reports/report-0001').glob('*.md')))
        self.assertEqual(len(list((self.base/'reports/report-0001').glob('*executive*'))),1)

    def test_r871_acceptance_helper_returns_frozen_view_without_reexecution(self):
        with patch('workbench.coverage.build_coverage',side_effect=AssertionError('replay prohibited')):
            value=self.executive_doc()
        self.assertEqual(value['executive'],self.frozen()['executive'])

    def test_r872_historical_report_without_executive_stays_untouched(self):
        from workbench.executive import accepted_executive
        e='reports/report-0001/executive-report.html';self.doc['report_hashes'].pop(e);self.doc['artifacts'].remove(e)
        c=self.coordinator();v=accepted_executive(c,self.doc)
        self.assertEqual(v,{'executive':None,'executive_report':None});c.artifact.assert_not_called()

    def test_r873_registered_but_unaccepted_retry_is_not_primary(self):
        new='reports/report-0002/executive-report.html';self.doc['artifacts'].append(new)
        self.assertEqual(self.executive_doc()['executive_report'],'reports/report-0001/executive-report.html')

    def test_r874_revoked_inspection_hides_previous_primary(self):
        self.doc['report_verified']=False
        self.assertIsNone(self.executive_doc()['executive_report'])

    def test_r875_two_conflicting_accepted_generations_fail_closed(self):
        path='reports/report-0002/executive-report.html';self.doc['artifacts'].append(path);self.doc['report_hashes'][path]='a'*64
        self.assertIsNone(self.executive_doc()['executive_report'])

    def test_r876_unregistered_executive_hash_is_not_advertised(self):
        self.doc['artifacts'].remove('reports/report-0001/executive-report.html')
        self.assertIsNone(self.executive_doc()['executive_report'])

    def test_r877_malformed_executive_hash_baseline_is_not_advertised(self):
        self.doc['report_hashes']['reports/report-0001/executive-report.html']='invalid'
        self.assertIsNone(self.executive_doc()['executive_report'])

    def test_r878_missing_same_generation_metrics_refuses_summary(self):
        self.doc['report_hashes'].pop('reports/report-0001/metrics.json')
        with self.assertRaisesRegex(ValidationError,'metrics'):self.executive_doc()

    def test_r879_wrong_process_frozen_summary_is_rejected(self):
        self.rewrite_accepted_model(lambda m:m['executive'].update(process_id='other-process'))
        with self.assertRaisesRegex(ValidationError,'inconsistent'):self.executive_doc()
        self.rewrite_accepted_model(lambda m:m['executive'].update(process_id=self.doc['id']))
        self.rewrite_accepted_model(lambda m:m['executive']['progress'].update(converted_lines=999))
        with self.assertRaises(ValidationError):self.executive_doc()

    def test_r880_unknown_executive_schema_is_not_guessed(self):
        self.rewrite_accepted_model(lambda m:m['executive'].update(schema_version=999))
        with self.assertRaisesRegex(ValidationError,'inconsistent'):self.executive_doc()

    def test_r881_missing_summary_is_not_recomputed_from_current_evidence(self):
        original=self.frozen()['executive']
        self.rewrite_accepted_model(lambda m:m.pop('executive'))
        with self.assertRaisesRegex(ValidationError,'missing'):self.executive_doc()
        self.rewrite_accepted_model(lambda m:m.update(executive=original))
        self.rewrite_accepted_model(lambda m:m['metrics'].update(source_programs=999))
        with self.assertRaises(ValidationError):self.executive_doc()

    def test_r882_current_name_edit_does_not_relabel_accepted_snapshot(self):
        before=self.frozen()['executive']['process_name'];self.doc['name']='Changed current state'
        self.assertEqual(self.executive_doc()['executive']['process_name'],before)

    def test_r883_runner_primary_points_only_to_accepted_executive(self):
        value=runner.summary(self.coordinator(),self.doc)
        self.assertEqual(value['reports'],[value['primary_report']]);self.assertTrue(value['primary_report'].endswith('/executive-report.html'))

    def test_r884_runner_keeps_editable_slides_available_on_request(self):
        value=runner.summary(self.coordinator(),self.doc)
        self.assertTrue(any(p.endswith('/management.pptx') for p in value['supporting_reports']))
        self.assertNotIn(value['primary_report'],value['supporting_reports'])

    def test_r885_runner_does_not_offer_partial_retry_as_primary(self):
        self.doc['artifacts'].append('reports/report-0002/executive-report.html')
        value=runner.summary(self.coordinator(),self.doc)
        self.assertIn('report-0001',value['primary_report'])
        self.assertTrue(any('report-0002' in p for p in value['supporting_reports']))

    def test_r886_runner_historical_delivery_keeps_legacy_report_paths(self):
        self.doc['report_hashes'].pop('reports/report-0001/executive-report.html')
        value=runner.summary(self.coordinator(),self.doc)
        self.assertIsNone(value['primary_report']);self.assertTrue(any(p.endswith('management.pptx') for p in value['reports']))

    def test_r887_runner_summary_reads_frozen_metrics_not_live_rule_credit(self):
        self.doc['answers']['items']={}
        value=runner.summary(self.coordinator(),self.doc)
        self.assertEqual(value['executive']['progress']['verification_percent'],100)

    def test_r888_bundle_contains_primary_report_with_frozen_summary(self):
        import zipfile
        with zipfile.ZipFile(runner.bundle_process(self.coordinator(),self.doc['id'])) as z:
            text=z.read('reports/report-0001/executive-report.html').decode()
            model=json.loads(z.read('reports/report-0001/metrics.json'))
        self.assertIn(model['executive']['process_name'],text)

    def test_r889_bundle_refuses_removed_primary_hash_from_new_inspection(self):
        self.doc['report_hashes'].pop('reports/report-0001/executive-report.html')
        with self.assertRaisesRegex(ValidationError,'executive'):runner.bundle_process(self.coordinator(),self.doc['id'])

    def test_r890_cancelled_runner_preserves_primary_with_cancelled_outcome(self):
        self.doc['status']='CANCELLED'
        value=runner.summary(self.coordinator(),self.doc)
        self.assertEqual(value['status'],'CANCELLED')
        self.assertTrue(value['primary_report'].endswith('executive-report.html'))

    def test_r891_read_only_acceptance_helper_never_saves_a_new_snapshot(self):
        from workbench.executive import accepted_executive
        c=self.coordinator()
        with patch.object(self.ledger,'save',side_effect=AssertionError('write')):value=accepted_executive(c,self.doc)
        self.assertIsNotNone(value['executive']);c.register.assert_not_called()

    def test_r892_primary_route_rejects_nonversioned_report_location(self):
        from workbench.executive import executive_report_relative
        old='reports/report-0001/executive-report.html';h=self.doc['report_hashes'].pop(old)
        path='reports/executive-report.html';self.doc['report_hashes'][path]=h;self.doc['artifacts'].append(path)
        self.assertIsNone(executive_report_relative(self.doc))

    def jobs(self):
        from workbench.orchestration import verify_jobs
        from workbench.target import emit_jobs
        return verify_jobs(self.doc,self.root,emit_jobs(self.doc,self.doc['program_versions']))

    def test_r893_job_rc_resets_between_independent_job_dispatches(self):
        from workbench.reference import run_reference
        from workbench.target import run_generated
        def change_rc(fn):
            def call(*a,**kw):
                result=fn(*a,**kw);result['return_code']=4;return result
            return call
        other=copy.deepcopy(self.doc['jobs'][0]);other['name']='JOBB';other['steps'][0]['condition']='RC=0';self.doc['jobs'].append(other)
        with patch('workbench.orchestration.run_reference',side_effect=change_rc(run_reference)),patch('workbench.orchestration.run_generated',side_effect=change_rc(run_generated)):
            result=self.jobs()
        self.assertTrue(result['matched']);self.assertEqual(result['actual']['JOBB'][0]['return_code'],4)

    def test_r894_all_skipped_job_keeps_explicit_steps_without_record_execution(self):
        step=copy.deepcopy(self.doc['jobs'][0]['steps'][0]);step['name']='S020';step['condition']='RC<0'
        self.doc['jobs'][0]['steps'][0]['condition']='RC>0';self.doc['jobs'][0]['steps'].append(step)
        with patch('workbench.orchestration.run_reference',side_effect=AssertionError('skipped')):
            result=self.jobs()
        self.assertEqual(result['actual']['JOBA'],[{'step':'S010','status':'SKIPPED'},{'step':'S020','status':'SKIPPED'}])
        self.assertTrue(result['matched'])

    def test_r895_cancellation_checkpoint_interrupts_before_reference_execution(self):
        from workbench.orchestration import verify_jobs
        from workbench.target import emit_jobs
        def interrupt():raise InterruptedError('cancelled')
        with patch('workbench.orchestration.run_reference') as reference,self.assertRaises(InterruptedError):
            verify_jobs(self.doc,self.root,emit_jobs(self.doc,self.doc['program_versions']),checkpoint=interrupt)
        reference.assert_not_called()

    def test_r896_return_code_difference_revokes_ordered_job_match(self):
        from workbench.target import run_generated
        def changed(*a,**kw):
            result=run_generated(*a,**kw);result['return_code']=8;return result
        with patch('workbench.orchestration.run_generated',side_effect=changed):result=self.jobs()
        self.assertFalse(result['matched']);self.assertNotEqual(result['expected']['JOBA'][0]['return_code'],result['actual']['JOBA'][0]['return_code'])

    def test_r897_rejected_reference_input_never_runs_target_baseline(self):
        with patch('workbench.orchestration.run_reference',return_value={'input_status':'REJECT_INPUT'}),patch('workbench.orchestration.run_generated') as target:
            result=self.jobs()
        target.assert_not_called();self.assertFalse(result['matched']);self.assertIn('rejected',result['reason'])

    def test_r898_program_trace_mismatch_revokes_integration_with_equal_records(self):
        from workbench.target import run_generated
        def changed(*a,**kw):
            result=run_generated(*a,**kw);result['trace']=[];return result
        with patch('workbench.orchestration.run_generated',side_effect=changed):result=self.jobs()
        self.assertFalse(result['matched'])
        self.assertEqual(result['expected']['JOBA'][0]['record'],result['actual']['JOBA'][0]['record'])

    def test_r899_same_source_bytes_in_distinct_files_keep_distinct_units(self):
        original=self.doc['analysis']['assets'][0];other=copy.deepcopy(original);other['path']='OTHER.cbl';other['selected']=False;other['scope_disposition']='out_of_scope';self.doc['analysis']['assets'].append(other)
        self.doc['source_files']['OTHER.cbl']=self.doc['source_files']['ELIGIBLE.cbl'];(self.base/'input/sources/OTHER.cbl').write_bytes((self.base/'input/sources/ELIGIBLE.cbl').read_bytes())
        model=self.coverage();units={p:{r['unit_id'] for r in model['rows'] if r['source_path']==p} for p in ('ELIGIBLE.cbl','OTHER.cbl')}
        self.assertFalse(units['ELIGIBLE.cbl']&units['OTHER.cbl'])
        self.assertEqual(model['summary']['source_files'],2)

    def test_r900_empty_export_retains_file_inventory_without_invented_lines(self):
        self.doc['source_files']['EMPTY.txt']=sha(b'');(self.base/'input/sources/EMPTY.txt').write_bytes(b'')
        model=self.coverage();empty=next(f for f in model['files'] if f['path']=='EMPTY.txt')
        self.assertEqual(empty['physical_lines'],0);self.assertEqual(empty['source_text'],'')
        self.assertFalse(any(r['source_path']=='EMPTY.txt' for r in model['rows']))
        self.assertFalse(model['summary']['completion_eligible'])
