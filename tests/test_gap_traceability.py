"""Synthetic accepted report traceability; no raw exports or new semantic adapter."""
import copy
import unittest

from workbench.comparison import comparison_page, render_comparison_report, program_key
from workbench.domain import ValidationError, encode
from workbench.rule_inventory import _counts


def inventory():
    rules=[]
    for index, status in enumerate(('converted_verified','implemented_unverified','identified','blocked','excluded_by_requirements'),1):
        mapped=status in ('converted_verified','implemented_unverified')
        rules.append({'id':f'RULE_{index}','source_rule_id':f'R{index}',
            'category':'unclassified' if index==4 else 'business_rule', 'status':status,
            'description':f'Fictional ordered decision {index}', 'source_path':'SYNTHETIC.cbl','source_version':'source-hash',
            'source':[{'line':index*2,'text':f'IF FIELD = {index}'},{'line':index*2+1,'text':'CONTINUE END-IF'}],
            'modernized_behavior':'Not converted because selected No in requirements.' if index==5 else 'Preserve the ordered decision.' if mapped else 'Not implemented',
            'targets':[{'file':'shared/target/python/module.py','version':'target-hash','start':1,'end':2,
                        'text':'if record["FIELD"] == 1:\n    pass'}] if mapped else [],
            'tests':['case-true','case-false'] if mapped else [],
            'evidence':[{'file':'synthetic/run-0001/actual-and-comparison.json','version':'comparison-hash'}] if mapped else [],
            'reasons':['Source-derived comparison passed'] if mapped else ['Specific source operation lacks a verified replacement'],
            'gap_reasons':[] if index in (1,5) else ['Specific source operation lacks a verified replacement'],
            'memberships':[{'job':'JOB1','step':'STEP1','program':'SYNTHETIC'}],
            'requirements_excluded':index==5})
    program={'program':'SYNTHETIC','source_path':'SYNTHETIC.cbl','source_version':'source-hash',
             'rule_ids':[r['id'] for r in rules],'counts':_counts(rules)}
    requirements=[]
    for index, rule in enumerate(rules,1):
        requirements.append({'id':f'REQ_{index}','kind':'rule','rule_id':rule['source_rule_id'],
            'source_path':rule['source_path'],'source_hash':rule['source_version'],
            'start_line':rule['source'][0]['line'],'end_line':rule['source'][-1]['line'],
            'selected':index!=5,'status':rule['status'] if index in (1,5) else 'unverified','commentary':'Synthetic scope comparison',
            'description':rule['description'],'source_excerpt':'Synthetic source excerpt',
            'replacement_status':'candidate_only','replacement':rule['modernized_behavior'],
            'targets':rule['targets'],'evidence':rule['evidence'],'tests':rule['tests']})
    return {'schema_version':1,'comparison_contract_version':2,'process_id':'synthetic',
        'rules':rules,'programs':[program],'summary':_counts(rules),'jobs':[],'job_programs':[],
        'basis':'Synthetic accepted source-derived fixture; observed parity Unknown.',
        'program_gates':[],'process_gates':[],
        'requirements_comparison':{'markdown':'analysis/requirements/'+('a'*64)+'.md','revision':1,'items':requirements}}


class GapTraceabilityTests(unittest.TestCase):
    def test_unique_summary_includes_verified_excluded_and_unclassified(self):
        page=comparison_page(inventory())
        summary=page['traceability_summary']
        self.assertEqual(page['traceability_contract_version'],1)
        self.assertEqual(summary['source_units'],5)
        self.assertEqual(summary['identified_logic_units'],4)
        self.assertEqual(summary['unclassified_obligations'],1)
        self.assertEqual(summary['selected'],4)
        self.assertEqual(summary['excluded'],1)
        self.assertEqual(summary['verified_source_derived'],1)
        self.assertEqual(summary['unmet_selected'],3)
        self.assertEqual(summary['observed_mainframe_parity'],'Unknown')

    def test_requirement_drilldown_binds_exact_source_target_and_test_receipts(self):
        rule=comparison_page(inventory())['rules'][0]
        self.assertEqual(rule['requirement']['linked_requirements'][0]['id'],'REQ_1')
        self.assertEqual(rule['requirement']['selection'],'Yes')
        self.assertEqual(rule['fulfillment']['state'],'converted_verified')
        self.assertEqual(rule['fulfillment']['observed_mainframe_parity'],'Unknown')
        self.assertEqual(rule['evidence_matrix']['source']['start'],2)
        self.assertEqual(rule['evidence_matrix']['target']['unique_span_count'],1)
        self.assertEqual(rule['evidence_matrix']['validation']['test_count'],2)
        self.assertIn('source-derived',rule['fulfillment']['explanation'])


    def test_historical_inventory_has_unknown_scope_without_inferred_yes(self):
        model=inventory();model.pop('requirements_comparison');model.pop('comparison_contract_version')
        page=comparison_page(model)
        self.assertEqual(page['rules'][0]['requirement']['selection'],'Unknown')
        self.assertEqual(page['traceability_summary']['requirements_unlinked_units'],5)
        self.assertFalse(page['rules'][0]['diagnostics_recorded'])
        self.assertEqual(page['rules'][0]['status'],'converted_verified')

    def test_unpinned_default_scope_never_becomes_saved_yes(self):
        for field, value in (('markdown',None),('markdown','analysis/requirements.md'),('revision',None)):
            with self.subTest(field=field,value=value):
                model=inventory();model['requirements_comparison'][field]=value
                row=comparison_page(model)['rules'][0]
                self.assertEqual(row['requirement']['selection'],'Unknown')
                self.assertIn('scope_snapshot_unknown',[g['kind'] for g in row['traceability_missing']])

    def test_wrong_source_version_cannot_link_scope(self):
        model=inventory();model['requirements_comparison']['items'][0]['source_hash']='different-source'
        row=comparison_page(model)['rules'][0]
        self.assertEqual(row['requirement']['linked_requirement_count'],0)
        self.assertEqual(row['requirement']['selection'],'Unknown')

    def test_wrong_source_path_cannot_link_scope(self):
        model=inventory();model['requirements_comparison']['items'][0]['source_path']='OTHER.cbl'
        self.assertFalse(comparison_page(model)['rules'][0]['requirement']['linked_requirements'])

    def test_same_rule_name_without_source_span_is_not_traceability(self):
        model=inventory();model['requirements_comparison']['items'][0].update(start_line=90,end_line=91)
        self.assertEqual(comparison_page(model)['rules'][0]['requirement']['linked_requirement_count'],0)

    def test_overlapping_historical_scopes_keep_many_to_many_links(self):
        model=inventory();items=model['requirements_comparison']['items']
        items.extend([{**items[0],'id':'REQ_LONG','start_line':1,'end_line':100},
                      {**items[0],'id':'REQ_PREFIX','start_line':1,'end_line':1}])
        row=comparison_page(model)['rules'][1]
        self.assertEqual({r['id'] for r in row['requirement']['linked_requirements']},{'REQ_LONG','REQ_2'})

    def test_noncontiguous_source_does_not_link_a_missing_physical_line(self):
        model=inventory();model['rules'][0]['source']=[{'line':2,'text':'IF FIELD = 1'},{'line':4,'text':'END-IF'}]
        items=model['requirements_comparison']['items'];items[0].update(start_line=3,end_line=3)
        self.assertEqual(comparison_page(model)['rules'][0]['requirement']['linked_requirement_count'],1)
        self.assertEqual(comparison_page(model)['rules'][0]['requirement']['linked_requirements'][0]['id'],'REQ_2')

    def test_conflicting_yes_no_scope_is_unknown_and_named(self):
        model=inventory();item=model['requirements_comparison']['items'][0]
        model['requirements_comparison']['items'].append({**item,'id':'REQ_CONFLICT','selected':False})
        row=comparison_page(model)['rules'][0]
        self.assertEqual(row['requirement']['selection'],'Unknown')
        self.assertIn('scope_selection_conflict',[g['kind'] for g in row['traceability_missing']])
        self.assertEqual(row['status'],'converted_verified')

    def test_selected_no_is_explicit_omission_not_success_or_conversion_gap(self):
        row=comparison_page(inventory(),status='excluded')['rules'][0]
        self.assertEqual(row['requirement']['selection'],'No')
        self.assertIn('selected No in requirements',row['fulfillment']['explanation'])
        self.assertEqual(row['fulfillment']['state'],'excluded_by_requirements')
        self.assertFalse(row['gaps'])

    def test_shared_program_ownership_never_inflates_unique_process_total(self):
        model=inventory();second=copy.deepcopy(model['programs'][0]);second.update(program='OTHER',source_path='OTHER.cbl')
        model['programs'].append(second)
        page=comparison_page(model)
        self.assertEqual(page['traceability_summary']['source_units'],5)
        self.assertEqual(sum(p['traceability_summary']['source_units'] for p in page['programs']),10)
        self.assertEqual(page['rules'][0]['programs'],['SYNTHETIC','OTHER'])

    def test_program_filter_and_status_page_have_distinct_totals(self):
        model=inventory();p=model['programs'][0];p['rule_ids']=p['rule_ids'][:2];p['counts']=_counts(model['rules'][:2])
        page=comparison_page(model,program=program_key(p),status='verified',limit=1)
        self.assertEqual(page['inventory_traceability_summary']['source_units'],5)
        self.assertEqual(page['traceability_summary']['source_units'],2)
        self.assertEqual(page['matching_total'],1)
        self.assertEqual(len(page['rules']),1)
        self.assertEqual(page['traceability_summary']['linked_scope_requirements'],2)

    def test_unassigned_source_remains_accounted(self):
        model=inventory();model['programs']=[]
        page=comparison_page(model,program='unassigned',status='gaps')
        self.assertEqual(page['traceability_summary']['source_units'],5)
        self.assertEqual(page['matching_total'],3)

    def test_duplicate_target_links_and_shared_target_spans_are_separate_counts(self):
        model=inventory();target=copy.deepcopy(model['rules'][0]['targets'][0]);model['rules'][0]['targets'].append(target)
        summary=comparison_page(model)['traceability_summary']
        self.assertEqual(summary['target_mapping_links'],3)
        self.assertEqual(summary['unique_target_spans'],1)
        self.assertEqual(comparison_page(model)['rules'][0]['target_count'],2)

    def test_target_version_changes_are_not_deduplicated(self):
        model=inventory();model['rules'][1]['targets'][0]['version']='other-version'
        self.assertEqual(comparison_page(model)['traceability_summary']['unique_target_spans'],2)

    def test_missing_target_excerpt_is_unknown_even_when_span_is_verified(self):
        model=inventory();model['rules'][0]['targets'][0].pop('text')
        row=comparison_page(model)['rules'][0]
        self.assertFalse(row['evidence_matrix']['target']['excerpt_complete'])
        self.assertIn('target_excerpt_unknown',[g['kind'] for g in row['traceability_missing']])
        self.assertEqual(row['status'],'converted_verified')
        report=render_comparison_report(model)
        self.assertIn('Target excerpt was not recorded',report)

    def test_test_evidence_preview_limits_keep_full_counts(self):
        model=inventory();rule=model['rules'][0];rule['tests']=[f'CASE-{n}' for n in range(23)]
        rule['evidence']=[{'file':f'tests/receipt-{n}.json'} for n in range(15)]
        row=comparison_page(model)['rules'][0]
        self.assertEqual(row['evidence_matrix']['validation']['test_count'],23)
        self.assertEqual(row['evidence_matrix']['validation']['evidence_count'],15)
        self.assertFalse(row['evidence_matrix']['validation']['preview_complete'])
        self.assertEqual(len(row['tests']),20)

    def test_target_preview_limit_keeps_unique_span_count(self):
        model=inventory();rule=model['rules'][0];target=rule['targets'][0]
        rule['targets']=[{**target,'start':n,'end':n} for n in range(1,7)]
        row=comparison_page(model)['rules'][0]
        self.assertEqual(row['evidence_matrix']['target']['unique_span_count'],6)
        self.assertFalse(row['evidence_matrix']['target']['preview_complete'])
        self.assertEqual(len(row['targets']),4)

    def test_source_and_target_clipping_are_not_silently_complete(self):
        model=inventory();model['rules'][0]['source'][0]['text']='X'*2500
        model['rules'][0]['targets'][0]['text']='Y'*2500
        row=comparison_page(model)['rules'][0]
        self.assertFalse(row['evidence_matrix']['source']['excerpt_complete'])
        self.assertFalse(row['evidence_matrix']['target']['excerpt_complete'])

    def test_scope_link_preview_limit_reports_every_saved_requirement(self):
        model=inventory();item=model['requirements_comparison']['items'][0]
        model['requirements_comparison']['items']=[{**item,'id':f'REQ_{n}'} for n in range(23)]
        row=comparison_page(model)['rules'][0]
        self.assertEqual(row['requirement']['linked_requirement_count'],23)
        self.assertEqual(len(row['requirement']['linked_requirements']),20)
        self.assertFalse(row['requirement']['links_complete'])

    def test_missing_tests_are_named_without_guidance_becoming_evidence(self):
        model=inventory();model['rules'][2]['targets']=copy.deepcopy(model['rules'][0]['targets'])
        row=comparison_page(model)['rules'][2]
        self.assertIn('verification_receipt_unknown',[g['kind'] for g in row['traceability_missing']])
        self.assertEqual(row['status'],'identified')

    def test_gate_classes_retain_exact_obligation_and_closure(self):
        model=inventory();key=program_key(model['programs'][0])
        issue={'id':'GATE_DIFF','kind':'target_difference','scope':'program','program':'SYNTHETIC','source_rule_id':None,
               'reason':'Case CASE-X has a different target return code','resolution':'Compare CASE-X expected/actual return code and rerun the accepted target.',
               'facts':{'case_ids':['CASE-X']},'evidence':['synthetic/run-0001/actual-and-comparison.json']}
        model['program_gates']=[{'key':key,'program':'SYNTHETIC','issues':[issue]}]
        gate=comparison_page(model)['rules'][1]['program_gates'][0]
        self.assertEqual(gate['classification'],'behavioral_difference')
        self.assertEqual(gate['closure_evidence'],[issue['resolution']])
        self.assertEqual(gate['risk'],'Unknown');self.assertEqual(gate['owner'],'Unknown')

    def test_process_gate_survives_empty_gap_filter_and_does_not_forge_unit_gap(self):
        model=inventory();gate={'id':'PROCESS_GATE','kind':'integrity_gate','scope':'process','program':None,'source_rule_id':None,
              'reason':'Original receipt missing','resolution':'Recover the original receipt','facts':{},'evidence':[]}
        model['process_gates']=[gate]
        p=model['programs'][0];p['rule_ids']=['RULE_1'];p['counts']=_counts(model['rules'][:1])
        page=comparison_page(model,program=program_key(p),status='gaps')
        self.assertEqual(page['matching_total'],0)
        self.assertEqual(page['process_gates'][0]['classification'],'evidence_integrity')

    def test_unverified_recorded_prose_cannot_claim_parity_owner_or_risk(self):
        model=inventory();model['rules'][1].update(observed_mainframe_parity='Verified',owner='Invented',risk='Low')
        row=comparison_page(model)['rules'][1]
        self.assertEqual(row['fulfillment']['observed_mainframe_parity'],'Unknown')
        self.assertEqual(row['fulfillment']['owner'],'Unknown');self.assertEqual(row['fulfillment']['risk'],'Unknown')
        self.assertEqual(row['requirement']['sme_approval'],'Unknown')

    def test_malformed_scope_records_fail_closed(self):
        for change in ({'selected':'Yes'},{'start_line':True},{'end_line':0},{'source_hash':None},{'id':''}):
            with self.subTest(change=change):
                model=inventory();model['requirements_comparison']['items'][0].update(change)
                with self.assertRaises(ValidationError):comparison_page(model)

    def test_duplicate_saved_scope_ids_fail_closed(self):
        model=inventory();model['requirements_comparison']['items'].append(copy.deepcopy(model['requirements_comparison']['items'][0]))
        with self.assertRaisesRegex(ValidationError,'Duplicate accepted scope'):comparison_page(model)

    def test_malformed_comparison_schema_and_query_fail_with_validation_error(self):
        model=inventory();model['schema_version']=True
        with self.assertRaises(ValidationError):comparison_page(model)
        for status in (None,[],{},True):
            with self.subTest(status=status),self.assertRaises(ValidationError):comparison_page(inventory(),status=status)

    def test_malformed_core_source_mapping_and_missing_receipts_fail_closed(self):
        changes=({'source':[{'line':True,'text':'X'}]}, {'targets':[{'file':'x.py','version':'h','start':2,'end':1}]}, {'tests':[]})
        for change in changes:
            with self.subTest(change=change):
                model=inventory();model['rules'][0].update(change)
                with self.assertRaises(ValidationError):comparison_page(model)

    def test_duplicate_program_identity_is_rejected(self):
        model=inventory();model['programs'].append(copy.deepcopy(model['programs'][0]))
        with self.assertRaisesRegex(ValidationError,'Duplicate accepted program'):comparison_page(model)

    def test_report_is_aggregate_then_collapsed_exact_source_target_satisfaction(self):
        report=render_comparison_report(inventory())
        self.assertLess(report.index('Gap analysis at a glance'),report.index('<article class="comparison"'))
        self.assertIn('data-program-key="PROGRAM_',report)
        self.assertEqual(report.count('<article class="comparison"'),5)
        self.assertIn('<details><summary><strong>Fictional ordered decision',report)
        self.assertIn('How the requirement is satisfied',report)
        self.assertIn('Saved scope requirement links:',report)
        self.assertIn('Observed mainframe parity:</strong> Unknown',report)

    def test_report_escapes_code_scope_and_description(self):
        model=inventory();model['rules'][0]['description']='</summary><script>bad()</script>'
        model['rules'][0]['source'][0]['text']='</pre><img src=x onerror=bad()>'
        model['requirements_comparison']['items'][0]['id']='REQ_<script>bad()</script>'
        report=render_comparison_report(model)
        self.assertNotIn('<script>bad()</script>',report)
        self.assertIn('&lt;script&gt;bad()&lt;/script&gt;',report)
        self.assertIn('&lt;img src=x onerror=bad()&gt;',report)

    def test_projection_and_html_never_mutate_original_accepted_inventory(self):
        model=inventory();before=encode(model)
        comparison_page(model,status='gaps',limit=1);render_comparison_report(model)
        self.assertEqual(encode(model),before)

    def test_empty_inventory_counts_are_zero_with_unknown_parity(self):
        model=inventory();model.update(rules=[],programs=[],summary=_counts([]));model['requirements_comparison']['items']=[]
        page=comparison_page(model)
        self.assertEqual(page['traceability_summary']['source_units'],0)
        self.assertEqual(page['traceability_summary']['unique_target_spans'],0)
        self.assertEqual(page['traceability_summary']['observed_mainframe_parity'],'Unknown')


    def test_partial_scope_overlap_does_not_become_full_saved_selection(self):
        model=inventory();model['requirements_comparison']['items'][0]['end_line']=2
        row=comparison_page(model)['rules'][0]
        self.assertEqual(row['requirement']['linked_requirement_count'],1)
        self.assertEqual(row['requirement']['selection'],'Unknown')
        self.assertFalse(row['requirement']['source_span_complete'])
        self.assertIn('scope_span_incomplete',[g['kind'] for g in row['traceability_missing']])

    def test_program_gate_ownership_cannot_be_relabelled(self):
        model=inventory();key=program_key(model['programs'][0])
        model['program_gates']=[{'key':key,'program':'UNRELATED','issues':[]}]
        with self.assertRaisesRegex(ValidationError,'program gate ownership'):comparison_page(model)

    def test_unknown_saved_scope_status_cannot_be_presented_as_success(self):
        model=inventory();model['requirements_comparison']['items'][0]['status']='Fully migrated'
        with self.assertRaises(ValidationError):comparison_page(model)

    def test_randomized_scope_index_matches_exact_naive_line_witnesses(self):
        import random
        from workbench.comparison import _scope_index,_scope_links
        rng=random.Random(20261008)
        for trial in range(128):
            model=inventory();items=[]
            for index in range(rng.randrange(1,70)):
                first=rng.randrange(1,130);last=first+rng.randrange(0,150)
                items.append({**model['requirements_comparison']['items'][0], 'id':f'REQ_RANDOM_{index}',
                    'source_path':rng.choice(('SYNTHETIC.cbl','OTHER.cbl')),
                    'source_hash':rng.choice(('source-hash','other-version')),
                    'start_line':first,'end_line':last})
            model['requirements_comparison']['items']=items
            index,_,_=_scope_index(model)
            rule=copy.deepcopy(model['rules'][0]);lines=sorted(rng.sample(range(1,280),rng.randrange(1,20)))
            rule['source']=[{'line':line,'text':'SYNTHETIC'} for line in lines]
            expected={r['id'] for r in items if r['source_path']==rule['source_path'] and r['source_hash']==rule['source_version']
                      and any(r['start_line']<=line<=r['end_line'] for line in lines)}
            with self.subTest(trial=trial):self.assertEqual({r['id'] for r in _scope_links(rule,index)},expected)


    def test_identified_with_historical_candidate_span_does_not_claim_no_mapping(self):
        model=inventory();model['rules'][2]['targets']=copy.deepcopy(model['rules'][0]['targets'])
        row=comparison_page(model)['rules'][2]
        self.assertIn('retains candidate target mappings',row['fulfillment']['explanation'])
        self.assertNotIn('no recorded target implementation',row['fulfillment']['explanation'])
        self.assertEqual(row['status'],'identified')

    def test_partial_candidate_without_mapping_is_named_unverified(self):
        model=inventory();model['rules'][1]['targets']=[]
        row=comparison_page(model)['rules'][1]
        self.assertIn('no target mapping is available',row['fulfillment']['explanation'])
        self.assertIn('target_mapping_unknown',[g['kind'] for g in row['traceability_missing']])
        self.assertEqual(row['status'],'implemented_unverified')


    def test_randomized_full_span_qualification_matches_physical_line_coverage(self):
        import random
        from workbench.comparison import _span_is_covered
        rng=random.Random(741)
        for trial in range(128):
            rule={'source':[{'line':line} for line in sorted(rng.sample(range(1,70),rng.randrange(1,20)))]}
            linked=[]
            for index in range(rng.randrange(0,25)):
                first=rng.randrange(1,70);linked.append({'start_line':first,'end_line':first+rng.randrange(0,20)})
            linked.sort(key=lambda row:(row['start_line'],row['end_line']))
            expected=all(any(row['start_line']<=s['line']<=row['end_line'] for row in linked) for s in rule['source'])
            with self.subTest(trial=trial):self.assertEqual(_span_is_covered(rule,linked),expected)

    def test_nineteen_thousand_scope_units_keep_exact_bounded_drilldown(self):
        model=inventory();rule=model['rules'][0];model['rules']=[rule]
        rule['source']=[{'line':line,'text':'SYNTHETIC'} for line in range(1,19001)]
        unit=model['requirements_comparison']['items'][0]
        model['requirements_comparison']['items']=[{**unit,'id':f'REQ_{line}','start_line':line,'end_line':line} for line in range(1,19001)]
        model['summary']=_counts([rule]);model['programs'][0].update(rule_ids=[rule['id']],counts=_counts([rule]))
        page=comparison_page(model,limit=1);row=page['rules'][0]
        self.assertEqual(page['traceability_summary']['linked_scope_requirements'],19000)
        self.assertEqual(row['requirement']['linked_requirement_count'],19000)
        self.assertEqual(len(row['requirement']['linked_requirements']),20)
        self.assertEqual(row['requirement']['selection'],'Yes')
        self.assertFalse(row['source_excerpt_complete'])


if __name__=='__main__':unittest.main()
