"""Adversarial, source-derived regressions for bounded job-led discovery."""
import unittest
from unittest.mock import patch

from workbench.domain import encode
from workbench.lineage import map_lineage
from workbench.domain import ValidationError


class LineageDiscoveryTests(unittest.TestCase):
    def manifest(self, program='MAIN', job='NIGHT'):
        return {'id': 'Example', 'name': 'Example', 'jobs': [{'name': job, 'order': 1,
                 'steps': [{'name': 'S1', 'order': 1, 'program': program, 'inputs': [], 'outputs': []}]}]}

    def basic(self, program='MAIN'):
        return {'jobs/NIGHT': '//NIGHT JOB\n//S1 EXEC PGM=' + program,
                'cobol/' + program: 'PROGRAM-ID. ' + program + '.\nGOBACK.'}

    def selected(self, result, kind):
        return [n for n in result['nodes'] if n['kind'] == kind and n['selected']]

    def test_job_led_extensionless_case_insensitive_transitive_closure(self):
        files = {'jobs/Night': '//NIGHT JOB\n//S1 EXEC PROC=RUNPROC',
                 'procs/runproc': '//RUNPROC PROC\n//A EXEC PGM=MAIN\n// PEND',
                 'source/weird-file': 'PROGRAM-ID. MAIN.\nCOPY "REC".\nCALL "SUB".\nGOBACK.',
                 'copy/Rec': '01 INPUT-RECORD.\nCOPY LEAF.',
                 'copy/Leaf': '01 LEAF-RECORD.\n05 A PIC X.',
                 'source/sub': 'PROGRAM-ID. SUB.\nGOBACK.',
                 'other/unused': 'PROGRAM-ID. UNUSED.\nCALL "NOTINPROCESS".',
                 'other/data': 'unclassified original export'}
        result = map_lineage(files, self.manifest('RUNPROC'))
        self.assertEqual(result['closure']['status'], 'COMPLETE')
        self.assertEqual(result['scope']['selected_files'], sorted(set(files) - {'other/unused', 'other/data'}))
        self.assertEqual(result['scope']['retained_files'], sorted(files))
        self.assertFalse(any(g['name'] == 'NOTINPROCESS' for g in result['closure']['gaps']))
        copies = [e for e in result['edges'] if e['kind'] == 'copies']
        self.assertEqual(len(copies), 2)
        self.assertEqual(copies[0]['evidence'][0]['line'], 2)
        self.assertFalse(result['closure']['estate_complete'])

    def test_all_822_relevant_exports_retained_and_selected(self):
        files = {'JOB': '//NIGHT JOB\n' + '\n'.join('//S%03d EXEC PGM=P%03d' % (i, i) for i in range(821))}
        files.update({'P%03d' % i: 'PROGRAM-ID. P%03d.\nGOBACK.' % i for i in range(821)})
        result = map_lineage(files, self.manifest('P000'))
        self.assertEqual(result['scope']['original_file_count'], 822)
        self.assertEqual(result['scope']['selected_file_count'], 822)
        self.assertEqual(result['parser']['indexed_files'], 822)
        self.assertEqual(len(result['scope']['retained_files']), 822)

    def test_local_export_above_browser_32_mib_limit_is_retained_in_full(self):
        files = self.basic()
        files['cobol/MAIN'] += '\nCOPY BIGA.\nCOPY BIGB.\nCOPY BIGC.'
        comment = '*>' + 'X' * (11 * 1024 * 1024)
        files.update({'large/' + name: comment + '\n01 ' + name + '-RECORD.' for name in ['BIGA', 'BIGB', 'BIGC']})
        result = map_lineage(files, self.manifest())
        self.assertEqual(result['scope']['original_file_count'], 5)
        self.assertEqual(result['scope']['retained_files'], sorted(files))
        self.assertEqual(result['scope']['selected_files'], sorted(files))
        self.assertEqual(result['closure']['status'], 'COMPLETE')

    def test_mapper_enforces_shared_file_and_line_capacity_guards(self):
        files = self.basic()
        for constant, limit in [('MAX_SOURCE_FILES', 1), ('MAX_SOURCE_FILE_BYTES', 2),
                                ('MAX_SOURCE_BYTES', 2), ('MAX_SOURCE_LINES', 1)]:
            with self.subTest(constant=constant), patch('workbench.lineage.' + constant, limit), self.assertRaises(ValidationError):
                map_lineage(files, self.manifest())

    def test_comments_literals_and_instream_payload_do_not_create_programs(self):
        files = self.basic()
        files['cobol/MAIN'] = '\n'.join(['PROGRAM-ID. MAIN.', '000100*CALL "COMMENT".',
            '*> COPY BAD.', 'MOVE "CALL \'DISPLAYED\' COPY FAKE" TO TEXT.',
            'CALL "REAL". *> CALL "INLINE".', 'GOBACK.'])
        files['REAL'] = 'PROGRAM-ID. REAL.\nGOBACK.'
        files['jobs/NIGHT'] += '\n//* EXEC PGM=COMMENT\n//IN DD DATA\n//FAKE EXEC PGM=PAYLOAD\n/*'
        result = map_lineage(files, self.manifest())
        self.assertEqual({n['name'] for n in self.selected(result, 'program')}, {'MAIN', 'REAL'})
        self.assertFalse(any(g['name'] in {'COMMENT', 'INLINE', 'FAKE', 'BAD', 'PAYLOAD'} for g in result['closure']['gaps']))
        self.assertTrue(any(g['name'] == 'INSTREAM_CONTROL_DIALECT' for g in result['closure']['gaps']))

    def test_dynamic_calls_and_symbolic_jcl_are_visible_not_fetched(self):
        files = self.basic(); files['cobol/MAIN'] += '\nCALL TARGET-NAME.\nEXEC CICS LINK PROGRAM(PGM-VAR) END-EXEC.'
        files['jobs/NIGHT'] += '\n//S2 EXEC PGM=&PGMNAME'
        calls = []
        result = map_lineage(files, self.manifest(), resolver=lambda r: calls.append(r))
        self.assertEqual(calls, [])
        self.assertEqual(result['closure']['status'], 'PARTIAL')
        names = {g['name'] for g in result['closure']['gaps']}
        self.assertTrue({'TARGET-NAME', 'PGM-VAR', '&PGMNAME'}.issubset(names))
        self.assertTrue(all(g['status'] == 'dynamic_unknown' for g in result['closure']['gaps']))

    def test_copy_and_proc_cycles_terminate_and_are_reported(self):
        files = {'JOB': '//NIGHT JOB\n//S EXEC PROC=PA',
                 'PA': '//PA PROC\n//A EXEC PROC=PB\n// PEND',
                 'PB': '//PB PROC\n//B EXEC PROC=PA\n//M EXEC PGM=MAIN\n// PEND',
                 'MAIN': 'PROGRAM-ID. MAIN.\nCOPY CA.',
                 'CA': '01 A.\nCOPY CB.', 'CB': '01 B.\nCOPY CA.'}
        result = map_lineage(files, self.manifest('PA'))
        self.assertEqual(result['closure']['status'], 'COMPLETE')
        self.assertEqual(len(result['scope']['selected_files']), 6)
        cycles = result['closure']['cycles']
        self.assertTrue(any(any('proc:' in x for x in c) for c in cycles))
        self.assertTrue(any(any('copybook:' in x for x in c) for c in cycles))

    def test_ambiguous_local_libraries_never_choose_first(self):
        files = self.basic(); files['cobol/MAIN'] += '\nCOPY REC.'
        files.update({'LIBA/REC': '01 RECORD-A.', 'LIBB/REC': '01 RECORD-B.'})
        calls = []
        result = map_lineage(files, self.manifest(), resolver=lambda r: calls.append(r))
        self.assertEqual(result['closure']['status'], 'BLOCKED')
        self.assertEqual(calls, [])
        gap = next(g for g in result['missing_objects'] if g['name'] == 'REC')
        self.assertEqual(gap['status'], 'ambiguous')
        self.assertEqual(len(gap['candidates']), 2)
        self.assertFalse('LIBA/REC' in result['scope']['selected_files'])

    def test_explicit_copy_library_selects_actual_member(self):
        files = self.basic(); files['cobol/MAIN'] += '\nCOPY REC OF LIBB.'
        files.update({'LIBA/REC': '01 RECORD-A.', 'LIBB/REC': '01 RECORD-B.'})
        result = map_lineage(files, self.manifest())
        self.assertEqual(result['closure']['status'], 'COMPLETE')
        self.assertIn('LIBB/REC', result['scope']['selected_files'])
        self.assertNotIn('LIBA/REC', result['scope']['selected_files'])

    def test_missing_object_local_first_resolver_source_provenance_and_closure(self):
        files = self.basic(); files['cobol/MAIN'] += '\nCALL "FETCHED".'
        requests = []
        def resolve(request):
            requests.append(request)
            return {'status': 'RESOLVED', 'content': 'PROGRAM-ID. FETCHED.\nCOPY NEWREC.',
                    'filename': 'remote/FETCHED', 'provenance': {'adapter': 'zowe', 'dataset': 'APP.COBOL'}, 'coverage': 'COMPLETE'} if request['name'] == 'FETCHED' else {
                    'status': 'RESOLVED', 'content': '01 NEWREC.', 'filename': 'remote/NEWREC',
                    'provenance': {'adapter': 'zowe', 'dataset': 'APP.COPY'}, 'coverage': 'COMPLETE'}
        result = map_lineage(files, self.manifest(), resolver=resolve)
        self.assertEqual([r['name'] for r in requests], ['FETCHED', 'NEWREC'])
        self.assertTrue(all(r['local_repository_checked'] and r['operation'] == 'read_only_lookup' for r in requests))
        self.assertEqual(result['closure']['status'], 'COMPLETE')
        self.assertEqual(len(result['source_snapshots']), 2)
        self.assertIn('remote/NEWREC', result['scope']['selected_files'])
        self.assertEqual(result['scope']['retained_files'], sorted(files))
        self.assertEqual(set(files), {'jobs/NIGHT', 'cobol/MAIN'})

    def test_untrusted_or_wrong_source_response_does_not_resolve_missing_call(self):
        files = self.basic(); files['cobol/MAIN'] += '\nCALL "MISSING".'
        for response in ({'status': 'RESOLVED', 'content': 'PROGRAM-ID. MISSING.', 'filename': 'MISSING'},
                         {'status': 'RESOLVED', 'content': 'PROGRAM-ID. OTHER.', 'filename': 'MISSING', 'provenance': {'adapter': 'zowe'}}):
            with self.subTest(response=response):
                result = map_lineage(files, self.manifest(), resolver=lambda _: response)
                self.assertEqual(result['closure']['status'], 'BLOCKED')
                self.assertTrue(any(g['name'] == 'MISSING' for g in result['missing_objects']))

    def test_source_lookup_conflict_and_traversal_are_not_materialized(self):
        files = self.basic(); files['cobol/MAIN'] += '\nCALL "MISSING".'
        response = {'status': 'RESOLVED', 'files': {'../escape': 'PROGRAM-ID. MISSING.',
                    'cobol/MAIN': 'PROGRAM-ID. MISSING.'}, 'provenance': {'adapter': 'zowe'}}
        result = map_lineage(files, self.manifest(), resolver=lambda _: response)
        self.assertEqual(result['source_snapshots'], [])
        self.assertTrue(any(g['status'] == 'source_conflict' for g in result['closure']['gaps']))

    def test_failed_read_only_connection_preserves_bounded_local_findings(self):
        files = self.basic(); files['cobol/MAIN'] += '\nCOPY LOST.'
        def offline(_): raise ConnectionError('private endpoint and credential')
        result = map_lineage(files, self.manifest(), resolver=offline)
        self.assertEqual(result['closure']['status'], 'BLOCKED')
        self.assertEqual(result['read_only_lookups'][0]['status'], 'UNAVAILABLE')
        self.assertNotIn('private endpoint', str(result))
        self.assertIn('cobol/MAIN', result['scope']['selected_files'])

    def test_static_sql_tables_comments_and_displayed_queries(self):
        files = self.basic(); files['cobol/MAIN'] += '\n'.join(['', 'MOVE "SELECT * FROM FAKE.T" TO TEXT.',
            'EXEC SQL', 'SELECT X FROM APP.T -- JOIN BAD.T', 'JOIN APP.U ON U.X = T.X', 'END-EXEC.',
            '*> EXEC SQL SELECT * FROM COMMENT.T END-EXEC.'])
        files['DDL'] = 'CREATE TABLE APP.T (X INTEGER);\nCREATE TABLE APP.U (X INTEGER);'
        result = map_lineage(files, self.manifest())
        tables = self.selected(result, 'db2_table')
        self.assertEqual({n['name'] for n in tables}, {'APP.T', 'APP.U'})
        self.assertEqual(result['closure']['status'], 'COMPLETE')
        sql_edges = [e for e in result['edges'] if e['kind'] == 'sql_table']
        self.assertEqual([e['evidence'][0]['line'] for e in sql_edges], [5, 6])

    def test_dynamic_sql_and_quoted_identifiers_remain_explicit(self):
        files = self.basic(); files['cobol/MAIN'] += '\nEXEC SQL PREPARE S FROM TEXT END-EXEC.\nEXEC SQL SELECT X FROM "APP"."T" END-EXEC.'
        result = map_lineage(files, self.manifest())
        self.assertEqual(result['closure']['status'], 'PARTIAL')
        self.assertTrue(any(g['name'] == '<DYNAMIC SQL>' for g in result['closure']['gaps']))
        self.assertTrue(any(g['name'] == '<DELIMITED SQL IDENTIFIER>' for g in result['closure']['gaps']))

    def test_dd_datasets_are_data_evidence_and_never_missing_programs(self):
        files = self.basic(); files['jobs/NIGHT'] += '\n//IN DD DSN=APP.INPUT,DISP=SHR\n//OUT DD DSN=APP.OUTPUT,DISP=(NEW,CATLG)'
        result = map_lineage(files, self.manifest())
        self.assertEqual(result['closure']['status'], 'PARTIAL')
        self.assertEqual({g['kind'] for g in result['closure']['gaps']}, {'dataset'})
        self.assertEqual(result['missing_objects'], [])
        self.assertEqual({n['name'] for n in self.selected(result, 'program')}, {'MAIN'})
        self.assertEqual(result['closure']['input_data_readiness'], 'Unknown')

    def test_dataset_metadata_never_marks_actual_input_ready(self):
        files = self.basic(); files['jobs/NIGHT'] += '\n//IN DD DSN=APP.INPUT,DISP=SHR'
        result = map_lineage(files, self.manifest(), resolver=lambda r: {'status': 'RESOLVED',
            'coverage': 'COMPLETE', 'metadata': {'cataloged': True}, 'provenance': {'adapter': 'zowe', 'operation': 'list'}})
        self.assertEqual(result['closure']['status'], 'COMPLETE')
        datasets = self.selected(result, 'dataset')
        self.assertEqual(len(datasets), 1)
        self.assertEqual(datasets[0]['readiness'], 'Unknown')
        self.assertEqual(result['closure']['input_data_readiness'], 'Unknown')

    def test_dd_member_must_resolve_library_as_well_as_dataset(self):
        files = self.basic(); files['jobs/NIGHT'] += '\n//SYSIN DD DSN=APP.CNTL(CARD),DISP=SHR'
        files['APP/CNTL/CARD'] = 'SORT FIELDS=COPY'
        result = map_lineage(files, self.manifest(), resolver=lambda r: {'status': 'RESOLVED', 'coverage': 'COMPLETE',
                          'provenance': {'adapter': 'zowe'}, 'metadata': {}})
        self.assertEqual(result['closure']['status'], 'COMPLETE')
        self.assertIn('APP/CNTL/CARD', result['scope']['selected_files'])
        self.assertTrue(any(e['kind'] == 'dd_member' for e in result['edges']))

    def test_cics_bms_ca7_mq_relationships_and_unknown_queue_binding(self):
        files = self.basic(); files['cobol/MAIN'] += '\nEXEC CICS SEND MAP("SCREEN") MAPSET("MAPS") END-EXEC.\nEXEC CICS LINK PROGRAM("SUB") END-EXEC.\nCALL "MQPUT".'
        files.update({'SUB': 'PROGRAM-ID. SUB.\nGOBACK.',
                      'MAPS': 'MAPS DFHMSD TYPE=MAP\nSCREEN DFHMDI SIZE=(24,80)',
                      'CSD': 'DEFINE TRANSACTION(T001) GROUP(APP) PROGRAM(MAIN)',
                      'CA7': 'LJOB,JOB=NIGHT', 'MQ': 'DEFINE QLOCAL(APP.QUEUE)'})
        result = map_lineage(files, self.manifest())
        self.assertEqual({n['name'] for n in self.selected(result, 'bms_map')}, {'SCREEN'})
        self.assertEqual({n['name'] for n in self.selected(result, 'cics_transaction')}, {'T001'})
        self.assertEqual({n['name'] for n in self.selected(result, 'ca7_definition')}, {'NIGHT'})
        self.assertTrue(any(g['kind'] == 'mq_interface' for g in result['closure']['gaps']))
        self.assertFalse(any(g['kind'] == 'program' and g['name'] == 'MQPUT' for g in result['closure']['gaps']))
        self.assertEqual(result['closure']['status'], 'PARTIAL')

    def test_explicit_cics_mapset_resolves_repeated_screen_names(self):
        files = self.basic(); files['cobol/MAIN'] += '\nEXEC CICS SEND MAP("SCREEN") MAPSET("MAPB") END-EXEC.'
        files.update({'MAPA': 'MAPA DFHMSD TYPE=MAP\nSCREEN DFHMDI SIZE=(24,80)',
                      'MAPB': 'MAPB DFHMSD TYPE=MAP\nSCREEN DFHMDI SIZE=(24,80)'})
        result = map_lineage(files, self.manifest())
        self.assertEqual(result['closure']['status'], 'COMPLETE')
        self.assertEqual({n['path'] for n in self.selected(result, 'bms_map')}, {'MAPB'})
        self.assertNotIn('MAPA', result['scope']['selected_files'])

    def test_multiline_csd_transaction_binding_reaches_application_context(self):
        files = self.basic(); files['CSD'] = 'DEFINE TRANSACTION(T001)\n GROUP(APP)\n PROGRAM(MAIN)\nDEFINE TRANSACTION(T002) PROGRAM(UNRELATED)'
        result = map_lineage(files, self.manifest())
        self.assertEqual({n['name'] for n in self.selected(result, 'cics_transaction')}, {'T001', 'T002'})
        self.assertTrue(any(e['kind'] == 'binds_program' and e['evidence'][0].get('end_line') == 3 for e in result['edges']))
        # The whole shared definition member is retained, so its second binding cannot disappear.
        self.assertTrue(any(g['name'] == 'UNRELATED' for g in result['closure']['gaps']))

    def test_continued_cics_link_operand_is_visible_before_conversion(self):
        files = self.basic(); files['cobol/MAIN'] += '\nEXEC CICS LINK\n PROGRAM("SUB") END-EXEC.'
        result = map_lineage(files, self.manifest())
        self.assertEqual(result['closure']['status'], 'PARTIAL')
        self.assertTrue(any(g['name'] == '<CONTINUED CICS PROGRAM OPERAND>' for g in result['closure']['gaps']))

    def test_user_supplied_staging_locations_are_not_business_programs_or_dsns(self):
        manifest = self.manifest(); manifest['jobs'][0]['steps'][0]['inputs'] = ['WEDLX', 'Tran Repository', 'A file not yet identified']
        result = map_lineage(self.basic(), manifest)
        self.assertEqual({n['name'] for n in self.selected(result, 'input_location')}, {'WEDLX', 'Tran Repository'})
        self.assertEqual({n['name'] for n in self.selected(result, 'program')}, {'MAIN'})
        self.assertTrue(all(n['dataset_name'] == 'Unknown' and n['readiness'] == 'Unknown' for n in self.selected(result, 'input_location')))
        self.assertEqual(result['application_input_locations'][0]['basis'], 'user_supplied_application_context')

    def test_configured_input_folder_needs_actual_availability_evidence(self):
        manifest = self.manifest(); manifest['application_input_locations'] = {
            'WEDLX': {'path': '/mnt/input-share', 'availability': 'Available', 'readiness': 'Ready'}}
        result = map_lineage(self.basic(), manifest)
        location = result['application_input_locations'][0]
        self.assertEqual(location['physical_path'], '/mnt/input-share')
        self.assertEqual(location['availability'], 'Unknown')
        self.assertEqual(location['readiness'], 'Unknown')
        manifest['application_input_locations']['WEDLX']['evidence'] = [{'operation': 'list_directory', 'path': '/mnt/input-share', 'files': ['one.dat']}]
        manifest['application_input_locations']['WEDLX']['readiness'] = 'Unknown'
        result = map_lineage(self.basic(), manifest)
        self.assertEqual(result['application_input_locations'][0]['availability'], 'Available')
        self.assertEqual(result['application_input_locations'][0]['readiness'], 'Unknown')

    def test_exact_file_share_binding_resolves_data_without_program_lookup(self):
        files = self.basic(); files['jobs/NIGHT'] += '\n//IN DD DSN=APP.INPUT,DISP=SHR'
        manifest = self.manifest(); manifest['jobs'][0]['steps'][0]['inputs'] = ['TranRepository']
        manifest['application_input_locations'] = {'TranRepository': {'path': '/mounted/tran', 'availability': 'AVAILABLE',
            'evidence': [{'folder_observed': True, 'bindings': [{'logical_id': 'APP.INPUT', 'relative_path': 'input.dat',
                'available': True, 'size_bytes': 7, 'readiness': 'Unknown', 'basis': 'READ_ONLY_FILE_METADATA_NO_BUSINESS_READINESS_CLAIM'}]}]}}
        calls = []; result = map_lineage(files, manifest, resolver=lambda request: calls.append(request))
        self.assertEqual(calls, [])
        self.assertEqual(result['closure']['status'], 'COMPLETE')
        dataset = self.selected(result, 'dataset')[0]
        self.assertEqual(dataset['resolution'], 'read_only_input_metadata')
        self.assertEqual(dataset['readiness'], 'Unknown')
        self.assertEqual(result['application_input_locations'][1]['physical_path'], '/mounted/tran')
        self.assertEqual({n['name'] for n in self.selected(result, 'input_location')}, {'Tran Repository'})
        manifest['application_input_locations']['TranRepository']['evidence'][0]['bindings'][0]['available'] = False
        result = map_lineage(files, manifest, resolver=lambda request: calls.append(request))
        self.assertEqual(result['closure']['status'], 'PARTIAL')
        self.assertEqual(result['missing_objects'], [])
        self.assertTrue(any(g['status'] == 'input_unavailable' and g['kind'] == 'dataset' for g in result['closure']['gaps']))

    def test_retrieved_source_hash_includes_provenance(self):
        files = self.basic(); files['cobol/MAIN'] += '\nCALL "REMOTE".'
        response = {'status': 'RESOLVED', 'filename': 'REMOTE', 'content': 'PROGRAM-ID. REMOTE.', 'provenance': {'dataset': 'APP.COBOL'}}
        first = map_lineage(files, self.manifest(), resolver=lambda _: response)
        response['provenance'] = {'dataset': 'OTHER.COBOL'}
        second = map_lineage(files, self.manifest(), resolver=lambda _: response)
        self.assertNotEqual(first['source_snapshot_hash'], second['source_snapshot_hash'])

    def test_resume_preserves_fetched_origin_and_original_export_count(self):
        files = self.basic(); files['cobol/MAIN'] += '\nCALL "REMOTE".'
        original_paths = dict(files)
        response = {'status': 'RESOLVED', 'filename': 'REMOTE', 'content': 'PROGRAM-ID. REMOTE.',
                    'provenance': {'dataset': 'APP.COBOL', 'source_hash': 'retained connector evidence'}}
        first = map_lineage(files, self.manifest(), resolver=lambda _: response)
        manifest = self.manifest(); manifest['authorization'] = {'scope': original_paths}
        manifest['discovery_provenance'] = {'REMOTE': response['provenance']}
        files['REMOTE'] = response['content']
        second = map_lineage(files, manifest)
        self.assertEqual(first['source_snapshot_hash'], second['source_snapshot_hash'])
        self.assertEqual(second['scope']['original_file_count'], 2)
        self.assertEqual(second['scope']['retained_file_count'], 3)
        self.assertEqual(second['scope']['discovered_file_count'], 1)
        self.assertEqual(second['source_snapshots'], [])
        remote_file = next(n for n in second['nodes'] if n['id'] == 'source_file:REMOTE')
        self.assertEqual(remote_file['provenance']['dataset'], 'APP.COBOL')

    def test_all_eight_asset_counts_have_visible_unknowns_and_reconcile_observed_scope(self):
        result = map_lineage(self.basic(), self.manifest())
        assets = {a['kind']: a for a in result['process_assets']}
        self.assertEqual(set(assets), {'batch_cobol', 'jcl_jobs', 'jcl_procs', 'copybooks', 'cics_screens', 'db2_tables', 'ca7_schedules', 'mq'})
        self.assertEqual(assets['batch_cobol']['observed_count'], 1)
        self.assertEqual(assets['jcl_jobs']['observed_count'], 1)
        self.assertEqual(assets['mq']['count'], 'Unknown')
        self.assertEqual(assets['db2_tables']['count'], 'Unknown')
        self.assertFalse(result['closure']['estate_complete'])

    def test_unresolved_job_blocks_even_when_manifest_program_exists(self):
        result = map_lineage({'MAIN': 'PROGRAM-ID. MAIN.\nGOBACK.'}, self.manifest())
        self.assertEqual(result['closure']['status'], 'BLOCKED')
        self.assertTrue(any(g['kind'] == 'job' and g['name'] == 'NIGHT' for g in result['missing_objects']))
        self.assertEqual(result['scope']['selected_files'], ['MAIN'])

    def test_unknown_selected_include_blocks_without_excluding_its_source(self):
        files = self.basic(); files['jobs/NIGHT'] += '\n// INCLUDE MEMBER=UNCLEAR'
        files['UNCLEAR'] = 'unknown source text without a structural signature'
        calls = []; result = map_lineage(files, self.manifest(), resolver=lambda request: calls.append(request))
        self.assertEqual(result['closure']['status'], 'BLOCKED')
        self.assertIn('UNCLEAR', result['scope']['retained_files'])
        self.assertIn('UNCLEAR', result['scope']['selected_files'])
        self.assertEqual(calls, [])
        self.assertTrue(any(g['status'] == 'unresolved_parser' for g in result['closure']['gaps']))

    def test_multiline_sql_retains_start_and_end_line_evidence(self):
        files = self.basic(); files['cobol/MAIN'] += '\nEXEC SQL\nSELECT X FROM\n APP.T\nEND-EXEC.'
        files['DDL'] = 'CREATE TABLE\n APP.T (X INTEGER);'
        result = map_lineage(files, self.manifest())
        self.assertEqual(result['closure']['status'], 'COMPLETE')
        table_edge = next(e for e in result['edges'] if e['kind'] == 'sql_table')
        self.assertEqual(table_edge['evidence'][0]['line'], 4)
        self.assertEqual(table_edge['evidence'][0]['end_line'], 5)

    def test_multiline_quoted_sql_identifier_cannot_disappear_from_gaps(self):
        files = self.basic(); files['cobol/MAIN'] += '\nEXEC SQL\nSELECT X FROM\n "APP"."T"\nEND-EXEC.'
        result = map_lineage(files, self.manifest())
        self.assertEqual(result['closure']['status'], 'PARTIAL')
        self.assertTrue(any(g['name'] == '<DELIMITED SQL IDENTIFIER>' for g in result['closure']['gaps']))

    def test_missing_proc_role_comes_from_actual_job_step_before_fetch(self):
        files = {'JOB': '//NIGHT JOB\n//S1 EXEC PROC=REMOTE', 'MAIN': 'PROGRAM-ID. MAIN.\nGOBACK.'}
        requests = []
        def resolve(request):
            requests.append(request)
            return {'status': 'RESOLVED', 'filename': 'REMOTE.proc', 'content': '//REMOTE PROC\n//M EXEC PGM=MAIN\n// PEND',
                    'coverage': 'COMPLETE', 'provenance': {'dataset': 'APP.PROCLIB'}}
        result = map_lineage(files, self.manifest('REMOTE'), resolver=resolve)
        self.assertEqual(result['closure']['status'], 'COMPLETE')
        self.assertEqual([(r['kind'], r['name']) for r in requests], [('proc', 'REMOTE')])

    def test_continuation_and_complex_sql_are_explicit_parser_gaps(self):
        files = self.basic(); files['jobs/NIGHT'] += '\n//S2 EXEC PGM=MAIN,\n// PARM=X'
        files['cobol/MAIN'] += '\nCALL\n "SUB".\nEXEC SQL WITH TEMP AS (SELECT X FROM APP.T) SELECT X FROM TEMP END-EXEC.'
        files['DDL'] = 'CREATE TABLE APP.T (X INTEGER);'
        result = map_lineage(files, self.manifest())
        self.assertEqual(result['closure']['status'], 'PARTIAL')
        self.assertTrue({'JCL_EXEC_CONTINUATION', '<CONTINUED CALL OPERAND>', 'SQL_CTE_SCOPE'}.issubset({g['name'] for g in result['closure']['gaps']}))
        self.assertFalse(any(g['name'] == 'TEMP' and g['kind'] == 'db2_table' for g in result['closure']['gaps']))

    def test_result_is_deterministic_for_input_order_and_has_no_llm_calls(self):
        files = self.basic(); files.update({'Z': 'unclassified', 'A': 'PROGRAM-ID. UNRELATED.'})
        first = map_lineage(files, self.manifest())
        second = map_lineage(dict(reversed(list(files.items()))), self.manifest())
        self.assertEqual(encode(first), encode(second))
        self.assertTrue(first['parser']['no_llm'])
        self.assertFalse(first['parser']['observed_legacy_parity'])


if __name__ == '__main__': unittest.main()


class CicsDiscoveryContractTests(unittest.TestCase):
    def manifest(self, mapset=None):
        return {'id':'cics-audit','jobs':[], 'cics_contract_version':1,
                'transactions':[{'id':'TEST','program':'MAIN','mapset':mapset,'map':'SCREEN' if mapset else None}]}

    def files(self, command, extra=None):
        return {'MAIN.cbl':'IDENTIFICATION DIVISION.\nPROGRAM-ID. MAIN.\nPROCEDURE DIVISION.\n'+command+'\n',
                'resources.csd':'DEFINE TRANSACTION(TEST) GROUP(APP) PROGRAM(MAIN)\n', **(extra or {})}

    def test_literal_multiline_map_and_link_dependencies_are_transitive(self):
        command='EXEC CICS RECEIVE\n MAP("SCREEN")\n MAPSET("FORM") END-EXEC.\nEXEC CICS LINK\n PROGRAM("SUB") END-EXEC.'
        files=self.files(command,{'FORM.bms':'FORM DFHMSD TYPE=MAP\nSCREEN DFHMDI SIZE=(24,80)\n DFHMSD TYPE=FINAL\n END\n',
                                  'SUB.cbl':'PROGRAM-ID. SUB.\nCOPY RECORD.\nGOBACK.\n', 'RECORD.cpy':'01 RECORD.\n05 DATA PIC X.\n'})
        result=map_lineage(files,self.manifest())
        self.assertTrue(result['closure']['complete'])
        self.assertEqual(result['scope']['selected_files'],sorted(files))
        maps=[e for e in result['edges'] if e['kind']=='uses_map']
        self.assertEqual(maps[0]['evidence'][0]['line'],4)
        self.assertEqual(maps[0]['evidence'][0]['end_line'],6)
        self.assertFalse(any(n.get('conversion_support')=='VERIFIED' for n in result['nodes']))

    def test_static_file_tdqueue_transid_channel_container_obligations_are_visible(self):
        command='\n'.join(['EXEC CICS READ\n FILE("CUSTOMER") END-EXEC.',
                           'EXEC CICS READQ TD QUEUE("FEED") END-EXEC.',
                           'EXEC CICS READQ TS QUEUE("STATE") END-EXEC.',
                           'EXEC CICS START TRANSID("NEXT") END-EXEC.',
                           'EXEC CICS RETURN TRANSID("BACK") END-EXEC.',
                           'EXEC CICS GET CONTAINER("PAYLOAD") CHANNEL("CHANNEL1") END-EXEC.'])
        result=map_lineage(self.files(command),self.manifest())
        gaps={(g['kind'],g['name']) for g in result['closure']['gaps']}
        self.assertTrue({('cics_file_definition','CUSTOMER'),('cics_tdqueue_definition','FEED'),
                         ('cics_tsqueue','STATE'),('cics_transaction','NEXT'),('cics_transaction','BACK'),
                         ('cics_container','PAYLOAD'),('cics_channel','CHANNEL1')} <= gaps)
        self.assertFalse(result['closure']['complete'])

    def test_cics_dataset_qname_and_remote_system_aliases_remain_explicit(self):
        result=map_lineage(self.files('EXEC CICS READ DATASET("CUSTOMER") SYSID("REM1") END-EXEC.\n'
                                     'EXEC CICS READQ TS QNAME("STATE") END-EXEC.'),self.manifest())
        gaps={(g['kind'],g['name']) for g in result['closure']['gaps']}
        self.assertTrue({('cics_file_definition','CUSTOMER'),('cics_tsqueue','STATE'),('cics_system','REM1')} <= gaps)

    def test_dynamic_or_missing_mapset_cannot_clear_literal_map_binding(self):
        files=self.files('EXEC CICS RECEIVE MAP("SCREEN")\n MAPSET(MAPSET-NAME) END-EXEC.',
                         {'FORM.bms':'FORM DFHMSD TYPE=MAP\nSCREEN DFHMDI SIZE=(24,80)\n DFHMSD TYPE=FINAL\n END\n'})
        result=map_lineage(files,self.manifest())
        self.assertTrue(any(g['kind']=='bms_map' and g['status']=='dynamic_unknown' for g in result['closure']['gaps']))
        self.assertTrue(any(g['name']=='MAPSET-NAME' and g['status']=='dynamic_unknown' for g in result['closure']['gaps']))

    def test_missing_required_cics_operand_and_incomplete_command_remain_gaps(self):
        for command in ('EXEC CICS READ INTO(REC) END-EXEC.', 'EXEC CICS RECEIVE MAP("SCREEN")',
                        'EXEC CICS LINK PROGRAM("SUB")\nEXEC CICS RETURN END-EXEC.'):
            with self.subTest(command=command):
                result=map_lineage(self.files(command),self.manifest())
                self.assertFalse(result['closure']['complete'])
                self.assertTrue(any(g['kind']=='unknown_dependency' for g in result['closure']['gaps']))

    def test_csd_file_dataset_and_indirect_tdqueue_dependencies_are_transitive(self):
        files=self.files('EXEC CICS READ FILE("CUSTOMER") END-EXEC.\nEXEC CICS READQ TD QUEUE("FEED") END-EXEC.')
        files['files.csd']='DEFINE FILE(CUSTOMER) GROUP(APP)\n DSNAME(APP.CUSTOMER)\nDEFINE TDQUEUE(FEED) GROUP(APP)\n INDIRECTNAME(REALFEED)\nDEFINE TDQUEUE(REALFEED) GROUP(APP)\n'
        result=map_lineage(files,self.manifest())
        self.assertTrue(any(g['kind']=='dataset' and g['name']=='APP.CUSTOMER' for g in result['closure']['gaps']))
        self.assertFalse(any(g['name'] in ('CUSTOMER','FEED','REALFEED') for g in result['closure']['gaps']))
        self.assertTrue(any(e['kind']=='cics_indirect_queue' for e in result['edges']))

    def test_manifest_resource_program_conflict_and_missing_binding_stop_discovery(self):
        for resource in ('DEFINE TRANSACTION(TEST) PROGRAM(OTHER)', 'DEFINE TRANSACTION(TEST) GROUP(APP)'):
            files=self.files('GOBACK.',{'resources.csd':resource,'OTHER.cbl':'PROGRAM-ID. OTHER.\nGOBACK.\n'})
            result=map_lineage(files,self.manifest())
            self.assertFalse(result['closure']['complete'])
            self.assertTrue(any('BINDING CONFLICT' in g['name'] for g in result['closure']['gaps']))

    def test_native_root_requires_resource_but_flat_record_candidate_does_not(self):
        files={'MAIN.cbl':'PROGRAM-ID. MAIN.\nEXEC CICS RETURN END-EXEC.\n'}
        result=map_lineage(files,self.manifest())
        self.assertTrue(any(g['kind']=='cics_transaction' and g['name']=='TEST' for g in result['closure']['gaps']))
        flat=map_lineage({'MAIN.cbl':'PROGRAM-ID. MAIN.\nGOBACK.\n'},self.manifest())
        self.assertTrue(flat['closure']['complete'])

    def test_historical_parser_graph_is_unchanged_without_contract(self):
        files={'MAIN.cbl':'PROGRAM-ID. MAIN.\nEXEC CICS READ FILE("MISSING") END-EXEC.\n'}
        manifest=self.manifest();manifest.pop('cics_contract_version')
        self.assertTrue(map_lineage(files,manifest)['closure']['complete'])
        self.assertFalse(map_lineage(files,self.manifest())['closure']['complete'])

    def test_literals_and_comments_do_not_create_fake_cics_requests(self):
        files={'MAIN.cbl':'PROGRAM-ID. MAIN.\nDISPLAY "EXEC CICS READ FILE(""FAKE"") END-EXEC".\n*> EXEC CICS LINK PROGRAM("OTHER") END-EXEC.\nGOBACK.\n'}
        result=map_lineage(files,self.manifest())
        self.assertTrue(result['closure']['complete'])
        self.assertFalse(any(n['name'] in ('FAKE','OTHER') for n in result['nodes']))

    def test_command_scan_is_bounded_and_does_not_skip_later_program_owner(self):
        files=self.files('EXEC CICS READ '+('X '*33000)+'FILE("CUSTOMER") END-EXEC.\nPROGRAM-ID. SECOND.\nEXEC CICS LINK PROGRAM("MISSING") END-EXEC.')
        result=map_lineage(files,self.manifest())
        self.assertTrue(any('OVERSIZED' in g['name'] for g in result['closure']['gaps']))
        # Whole exported compilation unit remains retained, including the second declaration.
        self.assertTrue(any(g['name']=='MISSING' and g['source'].endswith(':SECOND') for g in result['closure']['gaps']))


    def test_omitted_mapset_uses_map_name_and_cannot_borrow_unique_other_mapset(self):
        maps='MAPS DFHMSD TYPE=MAP\nSCREEN DFHMDI SIZE=(24,80)\n DFHMSD TYPE=FINAL\n'
        for verb in ('SEND','RECEIVE'):
            with self.subTest(verb=verb):
                files=self.files('EXEC CICS '+verb+' MAP("SCREEN") END-EXEC.',{'MAPS.bms':maps})
                result=map_lineage(files,self.manifest('MAPS'))
                self.assertFalse(result['closure']['complete'])
                self.assertTrue(any(g['kind']=='bms_mapset' and g['name']=='SCREEN' for g in result['closure']['gaps']))
                self.assertTrue(any(g['kind']=='bms_map' and g['name']=='SCREEN' for g in result['closure']['gaps']))
                files['MAPS.bms']=maps.replace('MAPS DFHMSD','SCREEN DFHMSD')
                result=map_lineage(files,self.manifest())
                self.assertTrue(result['closure']['complete'])
                self.assertTrue(any(e['kind']=='uses_default_mapset' for e in result['edges']))

    def test_malformed_explicit_mapset_never_takes_default_or_unique_binding(self):
        maps='SCREEN DFHMSD TYPE=MAP\nSCREEN DFHMDI SIZE=(24,80)\n DFHMSD TYPE=FINAL\n'
        for operand in ('MAPSET','MAPSET "MAPS"','MAPSET()','MAPSET("SCREEN") MAPSET'):
            with self.subTest(operand=operand):
                result=map_lineage(self.files('EXEC CICS SEND MAP("SCREEN") '+operand+' END-EXEC.',{'SCREEN.bms':maps}),self.manifest())
                self.assertFalse(result['closure']['complete'])
                self.assertTrue(any(g['kind']=='unknown_dependency' and 'MALFORMED MAPSET' in g['name'] or g['kind']=='bms_map' and g['status']=='dynamic_unknown' for g in result['closure']['gaps']))
        result=map_lineage(self.files('EXEC CICS SEND MAP("SCREEN") FROM(MAPSET) END-EXEC.',{'SCREEN.bms':maps}),self.manifest())
        self.assertTrue(result['closure']['complete'])
        self.assertFalse(any('MALFORMED MAPSET' in g['name'] for g in result['closure']['gaps']))

    def test_text_form_and_nested_operand_names_do_not_create_map_dependencies(self):
        for command in ('EXEC CICS SEND TEXT FROM(MAP) END-EXEC.',
                        'EXEC CICS SEND TEXT FROM(MAP(OFFSET:LENGTH)) END-EXEC.',
                        'EXEC CICS RECEIVE INTO(MAP) LENGTH(LENGTH) END-EXEC.',
                        'EXEC CICS SEND CONTROL RESP(MAP) END-EXEC.'):
            with self.subTest(command=command):
                result=map_lineage(self.files(command),self.manifest())
                self.assertTrue(result['closure']['complete'],result['closure']['gaps'])
                self.assertFalse(any(n['kind'] in ('bms_map','bms_mapset') for n in result['nodes']))
        result=map_lineage(self.files('EXEC CICS SEND MAP FROM(REC) END-EXEC.'),self.manifest())
        self.assertTrue(any(g['name']=='<CICS SEND MISSING MAP>' for g in result['closure']['gaps']))

    def test_all_csd_program_operands_are_observed_and_duplicate_binding_stops(self):
        for operands in (' PROGRAM(MAIN) PROGRAM(OTHER)', '\n PROGRAM(MAIN)\n PROGRAM(OTHER)',
                         ' PROGRAM(MAIN) PROGRAM(MAIN)', ' PROGRAM(MAIN) PROGRAM(PROG-NAME(1))'):
            with self.subTest(operands=operands):
                files=self.files('EXEC CICS RETURN END-EXEC.',{'resources.csd':'DEFINE TRANSACTION(TEST)'+operands+'\n',
                                                                 'OTHER.cbl':'PROGRAM-ID. OTHER.\nGOBACK.\n'})
                result=map_lineage(files,self.manifest())
                self.assertFalse(result['closure']['complete'])
                self.assertTrue(any('DUPLICATE PROGRAM BINDING' in g['name'] for g in result['closure']['gaps']))
                if 'OTHER' in operands:
                    conflict=next(g for g in result['closure']['gaps'] if 'PROGRAM BINDING CONFLICT' in g['name'])
                    self.assertEqual(set(conflict['evidence'][0]['observed_programs']),{'MAIN','OTHER'})
                    self.assertTrue(all(e['path']=='resources.csd' for e in conflict['evidence'][0]['binding_source_refs']))


class Db2CatalogReceiptTests(unittest.TestCase):
    def receipt(self):
        return {'schema_version':1,'kind':'DB2_TABLE_DESCRIPTION','schema':'APP','table':'CUSTOMER',
                'columns':[{'NAME':'ID','COLNO':0,'COLTYPE':'CHAR','LENGTH':9,'NULLS':'N'}],
                'description_complete':True,'ddl':None,'constraints':None,'indexes':None,'triggers':None,
                'provenance':{'origin':'configured_mcp','tool':'db2_describe_table','locator':'APP.CUSTOMER',
                              'retrieved_at':'2026-10-07T16:00:00Z'}}

    def test_typed_catalog_resolves_table_identity_without_executing_json_or_inventing_ddl(self):
        from workbench.domain import encode, sha
        from workbench.retrieval import unresolved_after_mapping
        receipt=self.receipt();raw=encode(receipt).decode();path='db2/APP.CUSTOMER.json.txt'
        manifest={'id':'db2-audit','jobs':[], 'cics_contract_version':1,
                  'transactions':[{'id':'TEST','program':'MAIN','mapset':None,'map':None}]}
        result=map_lineage({'MAIN.cbl':'PROGRAM-ID. MAIN.\nEXEC SQL SELECT ID FROM APP.CUSTOMER END-EXEC.\n',path:raw},manifest)
        self.assertTrue(result['closure']['complete'])
        table=next(n for n in result['nodes'] if n['kind']=='db2_table')
        self.assertEqual(table['name'],'APP.CUSTOMER');self.assertFalse(table['executable_source'])
        self.assertEqual(table['catalog_evidence']['source_hash'],sha(raw))
        self.assertIn('DDL',table['catalog_evidence']['missing_semantics'])
        self.assertIn('TRIGGERS',table['catalog_evidence']['missing_semantics'])
        self.assertIsNone(table['catalog_evidence']['ddl'])
        doc={'source_files':{path:sha(raw)},'retrieval_unresolved':{'t':{'need':{'kind':'db2_table','name':'APP.CUSTOMER'},
             'status':'RECEIVED','path':path,'source_hash':sha(raw)}}}
        self.assertEqual(unresolved_after_mapping(doc,result),{})
        doc['retrieval_unresolved']['t']['source_hash']='0'*64
        self.assertIn('t',unresolved_after_mapping(doc,result))

    def test_partial_catalog_columns_and_duplicate_table_sources_remain_unresolved(self):
        from workbench.domain import encode
        receipt=self.receipt();receipt['description_complete']=False
        manifest=CicsDiscoveryContractTests().manifest()
        files={'MAIN.cbl':'PROGRAM-ID. MAIN.\nEXEC SQL SELECT ID FROM APP.CUSTOMER END-EXEC.\n',
               'db2/description.txt':encode(receipt).decode()}
        result=map_lineage(files,manifest)
        self.assertTrue(result['closure']['complete'])
        self.assertFalse(any(g['kind']=='db2_catalog_detail' for g in result['closure']['gaps']))
        table=next(n for n in result['nodes'] if n['kind']=='db2_table')
        self.assertFalse(table['executable_source']);self.assertEqual(table['conversion_support'],'UNVERIFIED')
        self.assertIn('COLUMN_DESCRIPTION',table['catalog_evidence']['missing_semantics'])
        from workbench.source import analyze_sources
        analysis=analyze_sources(files,manifest)
        self.assertTrue(any(g['kind']=='db2_catalog_semantics_gap' and g['obligation']=='COLUMN_DESCRIPTION' for g in analysis['blockers']))
        receipt['description_complete']=True;files['db2/description.txt']=encode(receipt).decode();files['db2/second.txt']=encode(receipt).decode()
        result=map_lineage(files,manifest)
        self.assertTrue(any(g['kind']=='db2_table' and g['status']=='ambiguous' for g in result['closure']['gaps']))

    def test_catalog_rejects_twenty_distinct_malformed_claims_and_different_provenance(self):
        from copy import deepcopy
        from workbench.db2_catalog import table_description
        from workbench.domain import encode, ValidationError
        changes=[('extra',True),('schema_version',True),('kind','OTHER'),('schema','app'),('table','APP.T'),
                 ('columns',[]),('description_complete','yes'),('ddl',[]),('constraints',{}),('indexes',[{}]),
                 ('triggers','unknown'),('provenance',{}),('column_NAME','id'),('column_COLNO',True),
                 ('column_COLTYPE','char'),('column_LENGTH',-1),('column_NULLS','maybe'),('column_SCALE',-1),
                 ('column_CCSID',True),('column_COLNO',2)]
        for key,value in changes:
            receipt=deepcopy(self.receipt())
            if key.startswith('column_'):receipt['columns'][0][key[7:]]=value
            else:receipt[key]=value
            with self.subTest(key=key,value=value),self.assertRaises(ValidationError):
                # Explicit typed-contract text remains identifiable even if kind is corrupted.
                raw=encode(receipt).decode()
                if key=='kind':raw=raw.replace('OTHER','DB2_TABLE_DESCRIPTION_INVALID')
                table_description(raw)
        receipt=self.receipt()
        with self.assertRaises(ValidationError):table_description(encode(receipt).decode(),{**receipt['provenance'],'tool':'zowe'})
        self.assertIsNone(table_description('{"unrelated":"data"}'))

    def test_catalog_valid_randomized_column_observations_retain_unknown_native_equivalence(self):
        import random
        from workbench.db2_catalog import table_description
        from workbench.domain import encode
        rng=random.Random(127)
        states=set()
        for index in range(20):
            receipt=self.receipt();receipt['table']='T'+str(index)
            receipt['provenance']['locator']='APP.'+receipt['table']
            receipt['columns'][0].update(LENGTH=rng.randrange(1,1000),NULLS=rng.choice(('Y','N')))
            result=table_description(encode(receipt).decode());states.add((result['table'],result['columns'][0]['LENGTH']))
            self.assertIn('NATIVE_SQL_TRANSACTION_TYPE_AND_AUTHORIZATION_EQUIVALENCE',result['missing_semantics'])
            self.assertIsNone(result['ddl'])
        self.assertEqual(len(states),20)

    def test_catalog_canonical_locator_must_match_exact_observed_table(self):
        from workbench.db2_catalog import table_description
        from workbench.domain import encode,ValidationError
        for locator in ('APP.OTHER','OTHER.CUSTOMER','app.customer','gateway/APP.CUSTOMER'):
            with self.subTest(locator=locator):
                receipt=self.receipt();receipt['provenance']['locator']=locator
                with self.assertRaisesRegex(ValidationError,'qualified schema.table identity'):
                    table_description(encode(receipt).decode())
                with self.assertRaises(ValidationError):
                    map_lineage({'MAIN.cbl':'PROGRAM-ID. MAIN.\n','catalog.txt':encode(receipt).decode()},CicsDiscoveryContractTests().manifest())
        self.assertEqual(table_description(encode(self.receipt()).decode())['provenance']['locator'],'APP.CUSTOMER')
