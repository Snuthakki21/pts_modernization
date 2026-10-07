"""Focused source-backed BMS replacement tests; no native controller claim."""
from copy import deepcopy
import unittest

from workbench.cics import (parse_bms, analyze_cics, selected_screens, screen_reference,
                           emit_screen, prepare_screen, plan_screen_cases,
                           verify_screen, adversarial_screen, screen_target_mappings)
from workbench.domain import ValidationError, encode, sha
from workbench.source import analyze_program, analyze_sources

BMS = '''MAPS DFHMSD TYPE=MAP,LANG=COBOL,MODE=INOUT
SCREEN DFHMDI SIZE=(24,80)
 DFHMDF POS=(1,1),LENGTH=8,ATTRB=(ASKIP,NORM),
 INITIAL='Customer'
ACCT DFHMDF POS=(3,1),LENGTH=8,ATTRB=(UNPROT,NORM,IC)
MSG DFHMDF POS=(5,1),LENGTH=12,ATTRB=(PROT,BRT),
 INITIAL='Ready'
 DFHMSD TYPE=FINAL
 END
'''
COBOL = '''IDENTIFICATION DIVISION.
PROGRAM-ID. PGM.
DATA DIVISION.
LINKAGE SECTION.
01 DATA-RECORD.
  05 VALUE PIC X(8).
  05 RESULT PIC X.
PROCEDURE DIVISION USING DATA-RECORD.
  IF VALUE = "00000001"
    MOVE "Y" TO RESULT
  ELSE
    MOVE "N" TO RESULT
  END-IF.
  EXEC CICS RECEIVE MAP("SCREEN") MAPSET("MAPS")
    INTO(SCREENI) END-EXEC.
  EXEC CICS SEND MAP("SCREEN") MAPSET("MAPS")
    FROM(SCREENO) END-EXEC.
  EXEC CICS RETURN END-EXEC.
'''
MANIFEST = {'jobs': [], 'transactions': [{'id': 'T001', 'program': 'PGM', 'mapset': 'MAPS', 'map': 'SCREEN'}], 'cics_contract_version': 1}


def fixture():
    parsed = parse_bms('maps/FORM.bms', BMS)
    assert not parsed['gaps'], parsed['gaps']
    return parsed['screens'][0]


class CicsTests(unittest.TestCase):
    def test_literal_map_fields_keep_exact_spans_attributes_and_attribute_byte(self):
        parsed = parse_bms('maps/FORM.bms', BMS); screen = parsed['screens'][0]
        self.assertFalse(parsed['gaps'])
        self.assertEqual((screen['mapset'], screen['map'], screen['rows'], screen['columns']), ('MAPS', 'SCREEN', 24, 80))
        self.assertEqual([u['kind'] for u in parsed['units']].count('screen_field'), 3)
        label = screen['fields'][0]
        self.assertEqual((label['start_line'], label['end_line']), (3, 4))
        self.assertFalse(label['required']); self.assertFalse(label['editable'])
        result = screen_reference(screen, {'ACCT': '00000001'})
        self.assertEqual(result['screen']['fields'][0]['column'], 2)
        self.assertEqual(result['screen']['fields'][1]['row'], 3)
        self.assertEqual(result['screen']['fields'][1]['value'], '00000001')
        self.assertEqual(result['screen']['fields'][2]['value'], 'Ready       ')
        self.assertEqual(result['screen']['fields'][2]['intensity'], 'bright')
        self.assertEqual(result['screen']['cursor_field'], 'ACCT')

    def test_actual_target_runs_twenty_distinct_randomized_states_and_semantic_mutations(self):
        screen = fixture(); code = emit_screen(screen)
        suite = plan_screen_cases(screen, 987654321)
        self.assertGreaterEqual(suite['coverage']['fields']['ACCT'], 20)
        self.assertGreaterEqual(suite['coverage']['layout_randomized_states'], 20)
        self.assertEqual(set(suite['coverage']['constant_fields']),{screen['fields'][0]['id'],'MSG'})
        for witness in suite['coverage']['constant_fields'].values():
            self.assertEqual(witness['distinct_source_display_values'],1)
            self.assertGreaterEqual(witness['randomized_input_context_witnesses'],20)
        self.assertEqual(len({c['values']['ACCT'] for c in suite['cases'] if c['randomized']}), suite['coverage']['fields']['ACCT'])
        receipt = verify_screen(screen, code, suite)
        self.assertTrue(receipt['passed']); self.assertFalse(receipt['native_controller_verified'])
        self.assertFalse(receipt['observed_mainframe_parity']); self.assertFalse(receipt['differences'])
        review = adversarial_screen(screen, code, suite)
        self.assertTrue(review['passed'], review)
        self.assertGreaterEqual(len(review['mutations']), 16)
        self.assertTrue(all(m['witness_count'] > 0 for m in review['mutations']))
        self.assertEqual(suite['coverage']['linked_map_witness']['source_hash'], sha(BMS))
        mappings = screen_target_mappings(code, screen)
        self.assertEqual(set(mappings), {'layout', *[field['id'] for field in screen['fields']]})

    def test_twenty_runtime_seeds_keep_actual_targets_and_source_expectations_in_agreement(self):
        screen = fixture(); code = emit_screen(screen)
        records = set()
        for seed in range(20):
            with self.subTest(seed=seed):
                suite = plan_screen_cases(screen, seed)
                self.assertTrue(verify_screen(screen, code, suite)['passed'])
                self.assertTrue(adversarial_screen(screen, code, suite)['passed'])
                records.update(sha(encode(case['values'])) for case in suite['cases'] if case['randomized'])
        self.assertGreaterEqual(len(records), 400)

    def test_adversarial_mutants_use_one_relevant_actual_witness_and_propagate_cancellation(self):
        screen=fixture();code=emit_screen(screen);suite=plan_screen_cases(screen,18)
        receipt=adversarial_screen(screen,code,suite)
        self.assertTrue(receipt['passed'])
        self.assertTrue(all(m['checked_case_count']==1 and m['witness_count']==1 and not m['capability_denied'] for m in receipt['mutations']))
        indexed={case['id']:case for case in suite['cases']}
        for mutation in receipt['mutations']:
            case=indexed[mutation['witness_cases'][0]]
            self.assertEqual(case['kind']=='invalid_target_request',mutation['id'].startswith('input_guard:'))
        class Cancelled(Exception): pass
        def cancel(): raise Cancelled('operator cancelled')
        with self.assertRaises(Cancelled):plan_screen_cases(screen,18,checkpoint=cancel)
        with self.assertRaises(Cancelled):verify_screen(screen,code,suite,checkpoint=cancel)
        with self.assertRaises(Cancelled):adversarial_screen(screen,code,suite,checkpoint=cancel)
        # Let deterministic source replay finish, then cancel during actual mutation work.
        events=[]
        plan_screen_cases(screen,18,checkpoint=lambda:events.append('source'))
        count=[0]
        def cancel_later():
            count[0]+=1
            if count[0]>len(events)+2: raise Cancelled('cancel during mutant')
        with self.assertRaises(Cancelled):adversarial_screen(screen,code,suite,checkpoint=cancel_later)

    def test_actual_target_rejects_malformed_and_protected_field_input(self):
        run = prepare_screen(emit_screen(fixture()))
        for values in (None, [], {}, {'ACCT': 1}, {'ACCT': True}, {'ACCT': '123'},
                       {'ACCT': 'é' * 8}, {'ACCT': '\n' * 8},
                       {'ACCT': '00000001', 'MSG': 'untrusted'}, {'acct': '00000001'}):
            with self.subTest(values=values):
                self.assertEqual(run(values)['input_status'], 'REJECT_INPUT')
        self.assertEqual(run({'ACCT': '00000001'})['input_status'], 'ACCEPT_INPUT')

    def test_static_only_map_does_not_fabricate_twenty_state_credit(self):
        screen = fixture(); screen['fields'] = [screen['fields'][0]]
        suite = plan_screen_cases(screen, 7)
        self.assertFalse(suite['coverage']['complete'])
        self.assertEqual(suite['coverage']['layout_randomized_states'], 0)
        witness=suite['coverage']['constant_fields'][screen['fields'][0]['id']]
        self.assertEqual(witness['distinct_source_display_values'],1)
        self.assertEqual(witness['randomized_input_context_witnesses'],0)
        self.assertEqual(suite['coverage']['gaps'][0]['required'], 20)
        self.assertFalse(verify_screen(screen, emit_screen(screen), suite)['passed'])

    def test_unsupported_options_preserve_exact_named_field_gaps(self):
        variants = [('PICIN', ',PICIN=\'99999999\''), ('OCCURS', ',OCCURS=2'),
                    ('NUM', ',ATTRB=(UNPROT,NUM,NORM)'), ('JUSTIFY', ',JUSTIFY=RIGHT')]
        for label, operand in variants:
            with self.subTest(label=label):
                text = BMS.replace('ACCT DFHMDF POS=(3,1),LENGTH=8,ATTRB=(UNPROT,NORM,IC)',
                                   'ACCT DFHMDF POS=(3,1),LENGTH=8' + operand)
                parsed = parse_bms('FORM.bms', text)
                self.assertTrue(parsed['gaps']); self.assertEqual(parsed['screens'][0]['support'], 'unsupported')
                self.assertTrue(any(label in gap['message'] for gap in parsed['gaps']))
                with self.assertRaises(ValidationError): emit_screen(parsed['screens'][0])

    def test_ibm_partial_attribute_defaults_have_executed_source_target_witnesses(self):
        for attrb, expected, editable in [('NORM',['UNPROT','NORM'],True), ('BRT',['UNPROT','BRT'],True),
                ('PROT',['PROT','NORM'],False), ('ASKIP',['ASKIP','NORM'],False), ('IC',['UNPROT','IC','NORM'],True)]:
            with self.subTest(attrb=attrb):
                text = BMS.replace('ATTRB=(UNPROT,NORM,IC)', 'ATTRB='+attrb)
                parsed = parse_bms('FORM.bms',text); screen = parsed['screens'][0]
                self.assertFalse(parsed['gaps']); self.assertEqual(screen['fields'][1]['attributes'],expected)
                self.assertEqual(screen['fields'][1]['editable'],editable)
                if editable:
                    suite = plan_screen_cases(screen,121)
                    self.assertGreaterEqual(suite['coverage']['fields']['ACCT'],20)
                    self.assertTrue(verify_screen(screen,emit_screen(screen),suite)['passed'])
                    self.assertTrue(adversarial_screen(screen,emit_screen(screen),suite)['passed'])
                else:
                    result = prepare_screen(emit_screen(screen))({})
                    self.assertFalse(result['screen']['fields'][1]['editable'])
        absent = BMS.replace(',ATTRB=(UNPROT,NORM,IC)', '')
        field = parse_bms('FORM.bms', absent)['screens'][0]['fields'][1]
        self.assertEqual(field['attributes'], ['ASKIP', 'NORM']); self.assertFalse(field['editable'])

    def test_validator_refuses_contradictory_or_unbound_screen_ir(self):
        from workbench.cics import validate_screen
        for attributes in (['ASKIP','UNPROT','NORM'], ['UNPROT','NORM','BRT'], ['NORM'],
                           ['UNPROT','NORM','NORM'], ['PROT','NORM','IC']):
            with self.subTest(attributes=attributes):
                screen = fixture(); screen['fields'][1]['attributes']=attributes
                with self.assertRaises(ValidationError): validate_screen(screen)
                with self.assertRaises(ValidationError): emit_screen(screen)
        screen = fixture(); screen['fields'][1]['required']=False
        with self.assertRaises(ValidationError): emit_screen(screen)

    def test_parser_reports_field_capacity_before_emission(self):
        lines = ['MAPS DFHMSD TYPE=MAP,LANG=COBOL,MODE=INOUT','SCREEN DFHMDI SIZE=(240,240)']
        lines += ['F'+str(index)+' DFHMDF POS='+str(index*2)+',LENGTH=1,ATTRB=(UNPROT,NORM)' for index in range(1024)]
        lines += [' DFHMSD TYPE=FINAL',' END']
        parsed = parse_bms('FORM.bms','\n'.join(lines))
        self.assertTrue(any('1023' in gap['message'] for gap in parsed['gaps']))
        self.assertEqual(len(parsed['screens'][0]['fields']),1024)
        self.assertEqual(parsed['screens'][0]['support'],'unsupported')
        with self.assertRaises(ValidationError): emit_screen(parsed['screens'][0])

    def test_bad_bounds_overlaps_duplicates_and_missing_closure_block_layout(self):
        variants = [BMS.replace('POS=(3,1)', 'POS=(25,1)'), BMS.replace('POS=(3,1)', 'POS=(1,2)'),
                    BMS.replace('LENGTH=8,ATTRB=(UNPROT', 'LENGTH=257,ATTRB=(UNPROT'),
                    BMS.replace('MSG DFHMDF', 'ACCT DFHMDF'), BMS.replace(' DFHMSD TYPE=FINAL\n', ''),
                    BMS.replace(' END\n', ''), BMS.replace('LANG=COBOL,', ''),
                    BMS.replace('TYPE=MAP', 'TYPE=&SYSPARM')]
        for text in variants:
            with self.subTest(text=text):
                parsed = parse_bms('FORM.bms', text)
                self.assertTrue(parsed['gaps']); self.assertEqual(parsed['screens'][0]['support'], 'unsupported')

    def test_controllers_keep_multiline_map_bindings_exact_spans_and_named_gaps(self):
        program = analyze_program('programs/PGM.cbl', COBOL, {})
        parsed = analyze_cics({'programs/PGM.cbl': COBOL, 'maps/FORM.bms': BMS}, MANIFEST, {'PGM': program})
        actions = [unit for unit in parsed['units'] if unit['kind'] == 'screen_action']
        self.assertEqual([unit['operation'] for unit in actions], ['RECEIVE', 'SEND', 'RETURN'])
        self.assertEqual((actions[0]['start_line'], actions[0]['end_line']), (14, 15))
        self.assertEqual((actions[0]['mapset'], actions[0]['map']), ('MAPS', 'SCREEN'))
        self.assertEqual(parsed['screens'][0]['owners'], ['PGM'])
        self.assertTrue(all(unit['support'] == 'unverified_controller' for unit in actions))
        self.assertEqual(sum(g['kind'] == 'cics_controller_gap' for g in parsed['gaps']), 3)
        self.assertFalse(parsed['native_cics_verified'])
        self.assertTrue(next(field for field in parsed['screens'][0]['fields'] if field['id'] == 'MSG')['required'])

    def test_cics_inside_literals_comments_is_not_an_action(self):
        text = COBOL.replace('  EXEC CICS RETURN END-EXEC.', '  DISPLAY "EXEC CICS RETURN END-EXEC".\n*> EXEC CICS SEND MAP("X") END-EXEC.')
        program = analyze_program('PGM.cbl', text, {})
        actions = analyze_cics({'PGM.cbl': text, 'FORM.bms': BMS}, MANIFEST, {'PGM': program})['units']
        self.assertEqual([u['operation'] for u in actions if u['kind'] == 'screen_action'], ['RECEIVE', 'SEND'])

    def test_documented_omitted_mapset_defaults_to_exact_literal_map_name(self):
        import random
        rng = random.Random(384841)
        names = rng.sample(range(1000000), 20)
        for index, number in enumerate(names):
            name = 'M' + str(number).zfill(6)
            with self.subTest(mapset=name):
                bms = BMS.replace('MAPS DFHMSD', name + ' DFHMSD').replace('SCREEN DFHMDI', name + ' DFHMDI')
                text = COBOL.replace('MAP("SCREEN") MAPSET("MAPS")', 'MAP("' + name + '")')
                manifest = deepcopy(MANIFEST); manifest['transactions'][0].update(mapset=name, map=name)
                parsed = analyze_cics({'PGM.cbl':text,'FORM.bms':bms},manifest,{'PGM':analyze_program('PGM.cbl',text,{})})
                actions = [u for u in parsed['units'] if u['kind']=='screen_action' and u['form']=='MAP']
                self.assertEqual(len(actions),2)
                self.assertTrue(all((u['mapset'],u['map'])==(name,name) for u in actions))
                self.assertTrue(all(u['mapset_binding_basis']=='ibm_default_map_name' for u in actions))
                self.assertTrue(all(u['mapset_default_reference'].startswith('https://www.ibm.com/docs/') for u in actions))
                self.assertFalse(any(g['kind']=='cics_binding_gap' for g in parsed['gaps']))
                self.assertEqual(parsed['screens'][0]['owners'],['PGM'])
                self.assertFalse(parsed['native_cics_verified'])
                screen = parsed['screens'][0];suite = plan_screen_cases(screen,index)
                self.assertTrue(verify_screen(screen,emit_screen(screen),suite)['passed'])
                self.assertGreaterEqual(suite['coverage']['layout_randomized_states'],20)
                self.assertTrue(adversarial_screen(screen,emit_screen(screen),suite)['passed'])
        # Unique maps in a different mapset cannot establish the default binding.
        text = COBOL.replace(' MAPSET("MAPS")','')
        parsed = analyze_cics({'PGM.cbl':text,'FORM.bms':BMS},MANIFEST,{'PGM':analyze_program('PGM.cbl',text,{})})
        self.assertTrue(any('missing or ambiguous' in g['message'] for g in parsed['gaps']))
        self.assertEqual({u['mapset'] for u in parsed['units'] if u['kind']=='screen_action' and u['form']=='MAP'},{'SCREEN'})
        for operand in ('MAPSET(MAPSET-NAME)','MAPSET()','MAPSET("MAPS") MAPSET(OTHER)','MAPSET("MAPS") MAPSET','MAPSET "MAPS"','MAPSET'):
            text = COBOL.replace('MAPSET("MAPS")',operand)
            parsed = analyze_cics({'PGM.cbl':text,'FORM.bms':BMS},MANIFEST,{'PGM':analyze_program('PGM.cbl',text,{})})
            self.assertTrue(any(g['kind']=='cics_binding_gap' for g in parsed['gaps']))
        # A buffer called MAPSET cannot suppress the documented default option.
        bms=BMS.replace('MAPS DFHMSD','SCREEN DFHMSD')
        text=COBOL.replace(' MAPSET("MAPS")','').replace('FROM(SCREENO)','FROM(MAPSET)')
        parsed=analyze_cics({'PGM.cbl':text,'FORM.bms':bms},{**MANIFEST,'transactions':[]},{'PGM':analyze_program('PGM.cbl',text,{})})
        actions=[u for u in parsed['units'] if u['kind']=='screen_action' and u['form']=='MAP']
        self.assertTrue(all(u['mapset']=='SCREEN' and u['mapset_binding_basis']=='ibm_default_map_name' for u in actions))
        self.assertFalse(any(g['kind']=='cics_binding_gap' for g in parsed['gaps']))

    def test_dynamic_missing_ambiguous_maps_are_not_invented(self):
        text = COBOL.replace('MAP("SCREEN") MAPSET("MAPS")', 'MAP(MAP-VARIABLE)')
        program = analyze_program('PGM.cbl', text, {})
        parsed = analyze_cics({'PGM.cbl': text, 'FORM.bms': BMS}, MANIFEST, {'PGM': program})
        self.assertTrue(any(g['kind'] == 'cics_binding_gap' for g in parsed['gaps']))
        program = analyze_program('PGM.cbl', COBOL, {})
        duplicated = analyze_cics({'PGM.cbl': COBOL, 'A.bms': BMS, 'B.bms': BMS}, MANIFEST, {'PGM': program})
        self.assertTrue(any('ambiguous' in g['message'] for g in duplicated['gaps']))
        missing = analyze_cics({'PGM.cbl': COBOL}, MANIFEST, {'PGM': program})
        self.assertTrue(any('missing or ambiguous' in g['message'] for g in missing['gaps']))

    def test_cosmetic_no_is_applied_to_target_without_altering_full_source(self):
        program = analyze_program('PGM.cbl', COBOL, {})
        parsed = analyze_cics({'PGM.cbl': COBOL, 'FORM.bms': BMS}, MANIFEST, {'PGM': program})
        unit = next(unit for unit in parsed['units'] if unit['kind'] == 'screen_field' and not unit['required'])
        analysis = {'cics_contract_version': 1, 'cics': parsed, 'requirements': {'excluded_units': [unit], 'selection': {'revision': 1}}}
        before = encode(parsed); screen = selected_screens(analysis)[0]
        self.assertEqual(len(screen['fields']), 2); self.assertEqual(len(screen['omitted_fields']), 1)
        actual = prepare_screen(emit_screen(screen))({'ACCT': '00000001'})
        self.assertEqual(len(actual['screen']['fields']), 2)
        self.assertNotIn('Customer', encode(actual).decode()); self.assertEqual(encode(parsed), before)
        self.assertTrue(verify_screen(screen, emit_screen(screen), plan_screen_cases(screen, 12))['passed'])

    def test_required_field_or_map_no_remains_dependency_gate(self):
        program = analyze_program('PGM.cbl', COBOL, {})
        parsed = analyze_cics({'PGM.cbl': COBOL, 'FORM.bms': BMS}, MANIFEST, {'PGM': program})
        for unit in (next(u for u in parsed['units'] if u['kind'] == 'screen_field' and u['field'] == 'ACCT'),
                     next(u for u in parsed['units'] if u['component'] == 'map')):
            with self.subTest(unit=unit):
                screen = selected_screens({'cics_contract_version': 1, 'cics': parsed, 'requirements': {'excluded_units': [unit]}})[0]
                self.assertEqual(screen['support'], 'unsupported')
                self.assertTrue(any('selected No' in gap['message'] for gap in screen['gaps']))
                with self.assertRaises(ValidationError): emit_screen(screen)

    def test_tampered_expectations_target_and_unsafe_capabilities_fail_closed(self):
        screen = fixture(); code = emit_screen(screen); suite = plan_screen_cases(screen, 9)
        bad = deepcopy(suite); bad['cases'][0]['expected']['return_code'] = 5
        with self.assertRaises(ValidationError): verify_screen(screen, code, bad)
        with self.assertRaises(ValidationError): verify_screen(screen, code.replace("'return_code': 0", "'return_code': 1"), suite)
        for source in ('import os\ndef run_screen(values): return values\n',
                       'def run_screen(values):\n    return values.clear()\n',
                       'def run_screen(values: len("x")):\n    return values\n'):
            with self.assertRaises(ValidationError): prepare_screen(source)

    def test_native_dimension_limit_does_not_credit_256_rows_or_columns(self):
        for size in ('(256,80)', '(24,256)', '(241,80)', '(24,241)'):
            with self.subTest(size=size):
                parsed = parse_bms('FORM.bms', BMS.replace('SIZE=(24,80)', 'SIZE='+size))
                self.assertTrue(parsed['gaps']); self.assertEqual(parsed['screens'][0]['support'], 'unsupported')
                with self.assertRaises(ValidationError): emit_screen(parsed['screens'][0])
        screen = parse_bms('FORM.bms', BMS.replace('SIZE=(24,80)', 'SIZE=(240,240)'))['screens'][0]
        self.assertTrue(verify_screen(screen, emit_screen(screen), plan_screen_cases(screen, 17))['passed'])
        screen['rows'] = 256
        with self.assertRaises(ValidationError): emit_screen(screen)

    def test_budget_cannot_silently_omit_malformed_field_witnesses(self):
        screen = fixture()
        suite = plan_screen_cases(screen, 13, minimum=20, budget=20)
        self.assertFalse(suite['coverage']['complete'])
        self.assertTrue(any(gap['kind']=='screen_negative_budget_deficit' for gap in suite['coverage']['gaps']))
        self.assertFalse(verify_screen(screen, emit_screen(screen), suite)['passed'])

    def test_map_keywords_inside_send_text_are_never_bindings(self):
        text = COBOL.replace('  EXEC CICS RECEIVE MAP("SCREEN") MAPSET("MAPS")\n    INTO(SCREENI) END-EXEC.\n  EXEC CICS SEND MAP("SCREEN") MAPSET("MAPS")\n    FROM(SCREENO) END-EXEC.',
                            "  EXEC CICS SEND TEXT FROM(\"MAP('SCREEN') MAPSET('MAPS')\") END-EXEC.")
        program = analyze_program('PGM.cbl',text,{})
        parsed = analyze_cics({'PGM.cbl':text,'FORM.bms':BMS},{**MANIFEST,'transactions':[]},{'PGM':program})
        action = next(unit for unit in parsed['units'] if unit.get('operation')=='SEND')
        self.assertEqual(action['form'],'TEXT'); self.assertIsNone(action['map']); self.assertIsNone(action['mapset'])
        self.assertEqual(parsed['screens'][0]['owners'],[])
        self.assertFalse(any(gap['kind']=='cics_binding_gap' for gap in action['diagnostics']))

    def test_missing_end_exec_stops_at_next_command_and_shared_lines_are_one_unit(self):
        text = COBOL.replace('  EXEC CICS RETURN END-EXEC.', '  EXEC CICS SEND MAP("SCREEN") MAPSET("MAPS")\n  EXEC CICS RETURN END-EXEC.')
        program = analyze_program('PGM.cbl',text,{})
        parsed = analyze_cics({'PGM.cbl':text,'FORM.bms':BMS},MANIFEST,{'PGM':program})
        actions = [unit for unit in parsed['units'] if unit['kind']=='screen_action']
        self.assertEqual(len(actions),4)
        self.assertTrue(any(gap['kind']=='cics_command_gap' for gap in actions[-2]['diagnostics']))
        self.assertEqual(actions[-2]['end_line'],actions[-1]['start_line']-1)
        text = COBOL.replace('  EXEC CICS RETURN END-EXEC.', '  EXEC CICS SEND TEXT END-EXEC. EXEC CICS RETURN END-EXEC.')
        program = analyze_program('PGM.cbl',text,{})
        parsed = analyze_cics({'PGM.cbl':text,'FORM.bms':BMS},MANIFEST,{'PGM':program})
        actions = [unit for unit in parsed['units'] if unit['kind']=='screen_action']
        self.assertEqual(actions[-1]['operation'],'MULTIPLE')
        self.assertEqual(len(actions[-1]['bindings']),2)
        from workbench.requirements import catalog
        analysis = analyze_sources({'PGM.cbl':text,'FORM.bms':BMS},MANIFEST)
        self.assertTrue(catalog(analysis)['items'])

    def test_typed_db2_catalog_is_retained_as_metadata_without_invented_sql(self):
        receipt = {'schema_version':1,'kind':'DB2_TABLE_DESCRIPTION','schema':'APP','table':'CUSTOMER',
            'columns':[{'NAME':'CUSTOMER_ID','COLNO':0,'COLTYPE':'CHAR','LENGTH':8,'NULLS':'N'}],
            'description_complete':True,'ddl':None,'constraints':None,'indexes':None,'triggers':None,
            'provenance':{'origin':'configured_mcp','tool':'db2_describe_table',
                'locator':'APP.CUSTOMER','retrieved_at':'2026-10-07T12:00:00Z'}}
        raw = encode(receipt).decode()
        analysis = analyze_sources({'PGM.cbl':COBOL,'FORM.bms':BMS,'db2/catalog.json':raw},MANIFEST)
        asset = next(asset for asset in analysis['assets'] if asset['path']=='db2/catalog.json')
        self.assertEqual(asset['kind'],'db2_catalog_evidence'); self.assertFalse(asset['executable_source'])
        self.assertTrue(asset['selected']); self.assertEqual(asset['source_text'],raw)
        self.assertEqual(asset['source_hash'],sha(raw)); self.assertIsNone(asset['catalog_evidence']['ddl'])
        self.assertEqual({gap['obligation'] for gap in analysis['blockers'] if gap['kind']=='db2_catalog_semantics_gap'},
                         {'DDL','CONSTRAINTS','INDEXES','TRIGGERS','NATIVE_SQL_TRANSACTION_TYPE_AND_AUTHORIZATION_EQUIVALENCE'})
        self.assertEqual(analysis['db2_catalog_evidence'][0]['source_path'],'db2/catalog.json')
        bad = deepcopy(receipt); bad['provenance']['origin']='invented'
        with self.assertRaises(ValidationError): analyze_sources({'db2/catalog.json':encode(bad).decode()},MANIFEST)

    def test_source_analysis_contract_is_explicit_and_historical_shape_unchanged(self):
        files = {'PGM.cbl': COBOL, 'FORM.bms': BMS}
        historical = analyze_sources(files, {key: value for key, value in MANIFEST.items() if key != 'cics_contract_version'})
        self.assertNotIn('cics', historical); self.assertNotIn('cics_contract_version', historical)
        current = analyze_sources(files, MANIFEST)
        self.assertEqual(current.get('cics_contract_version'), 1)
        self.assertEqual(current['cics']['screens'][0]['map'], 'SCREEN')
        self.assertTrue(any(g['kind'] == 'cics_controller_gap' for g in current['blockers']))
