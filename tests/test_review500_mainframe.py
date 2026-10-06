"""R081–R160: independent mainframe recognition, evidence and gating scenarios."""
import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from workbench.domain import ValidationError, encode, sha
from workbench.mainframe import classify_files, load_knowledge, utility_findings, validate_snapshot
from workbench.source import analyze_sources
from workbench.intake import parse_manifest
from test_source import COBOL
from test_workflow import MANIFEST


class MainframeReview500Tests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.snapshot = load_knowledge(self.root)

    def classify(self, text, path='MEMBER', extra=None):
        return classify_files({path: text, **(extra or {})}, {'jobs': []}, self.snapshot)[path]

    def find(self, text='', manifest=None, files=None, snapshot=None):
        return utility_findings(manifest or {'jobs': []}, snapshot or self.snapshot,
                                files if files is not None else {'JOB': text})

    def rehash(self, value):
        value['content_hash'] = sha(encode({k: v for k, v in value.items() if k != 'content_hash'}))
        return value

    def bad(self, change):
        value = copy.deepcopy(self.snapshot)
        change(value)
        with self.assertRaises(ValidationError):
            validate_snapshot(self.rehash(value))

    def custom(self):
        value = copy.deepcopy(self.snapshot)
        value['application'] = {'schema_version': 1, 'application': 'Test application', 'notes': [],
            'utilities': [{'id': 'APP_MATCH', 'name': 'MATCHREF', 'aliases': ['MRUN'],
                'category': 'application_wrapper', 'behavior': 'Matches records using owner-supplied rules.',
                'required_evidence': ['Source and controls'], 'risks': ['Duplicate keys'],
                'references': ['Owner guide'], 'owner': 'Application owner', 'version': 'Not yet confirmed',
                'record_formats': ['Not yet confirmed'], 'return_codes': ['Not yet confirmed'],
                'side_effects': ['Not yet confirmed'], 'dependencies': ['Not yet confirmed']}]}
        value['source_hashes']['application'] = sha(encode(value['application']))
        return self.rehash(value)

    def native(self, text, path='NATIVE', manifest=None):
        manifest = manifest or parse_manifest(MANIFEST)
        manifest['mainframe_knowledge'] = self.snapshot
        analysis = analyze_sources({'ELIGIBLE.cbl': COBOL, path: text}, manifest)
        self.assertTrue(any(b.get('path') == path for b in analysis['blockers']))
        self.assertEqual(next(a for a in analysis['assets'] if a['path'] == path)['source_text'], text)
        return analysis

    def test_r081_blank_sequence_debug_line_recognition(self):
        """A column-seven debug indicator must not conceal an extensionless PROGRAM-ID."""
        self.assertEqual(self.classify('      DPROGRAM-ID. DEBUGPG.')['kind'], 'cobol_program')
        self.assertEqual(self.classify('      DELETE FROM APP.T;')['kind'], 'sql')

    def test_r082_blank_sequence_identification_area_is_not_code(self):
        """Text after fixed-format column 72 cannot manufacture a source declaration."""
        self.assertEqual(self.classify('       ' + ' ' * 65 + 'PROGRAM-ID. FALSE.')['kind'], 'unknown')

    def test_r083_blank_sequence_comment_does_not_supply_rexx_marker(self):
        """A fixed-format COBOL comment containing a REXX-looking marker remains a comment."""
        self.assertEqual(self.classify('      * /* REXX */')['kind'], 'unknown')

    def test_r084_rexx_marker_inside_literal_is_not_source_header(self):
        """An arbitrary string containing a REXX comment cannot establish a script language."""
        self.assertEqual(self.classify('MOVE "/* REXX */" TO MESSAGE')['kind'], 'unknown')

    def test_r085_real_rexx_header_keeps_line_number(self):
        """A genuine REXX header after blank lines retains its original evidence location."""
        row = self.classify('\n\n/* REXX */\nsay "hello"')
        self.assertEqual(row['kind'], 'rexx')
        self.assertEqual(row['evidence'][0]['line'], 3)

    def test_r086_icetool_select_not_confused_with_sql_select(self):
        """ICETOOL SELECT FROM(...) control syntax is not a second SQL classification."""
        for space in (' ', '  ', '\t'):
            self.assertEqual(self.classify('SELECT' + space + 'FROM(INPUT) TO(OUTPUT) ON(1,5,CH) FIRST')['kind'], 'utility_control')

    def test_r087_icetool_copy_does_not_create_copybook_dependency(self):
        """COPY FROM(...) must not promote an unrelated member named FROM to a copybook."""
        self.assertEqual(self.classify('unrecognized data', 'FROM', {'TOOLIN': 'COPY FROM(INPUT) TO(OUTPUT)'})['kind'], 'unknown')

    def test_r088_national_character_copy_dependency(self):
        """A national-character COPY member receives dependency evidence without conversion support."""
        row = self.classify('IF FLAG = "Y"\nCONTINUE\nEND-IF', '$RULES', {'PGM': 'PROGRAM-ID. P.\nCOPY $RULES.'})
        self.assertEqual(row['kind'], 'copybook')
        self.assertEqual(row['conversion_support'], 'not_established')

    def test_r089_malformed_copy_operand_does_not_truncate_identity(self):
        """A parenthesized unrecognized COPY operand must not be truncated to a member name."""
        self.assertEqual(self.classify('unrecognized data', 'RULES', {'PGM': 'COPY RULES(BAD).'})['kind'], 'unknown')

    def test_r090_program_copybook_suffix_conflict(self):
        """A program declared in a copybook-suffixed export retains conflicting evidence."""
        row = self.classify('PROGRAM-ID. MAIN.', 'MAIN.cpy')
        self.assertEqual(row['kind'], 'ambiguous')
        self.assertTrue(row['conflicts'])

    def test_r091_embedded_source_in_dd_data_does_not_reclassify_job(self):
        """COBOL supplied as in-stream data does not become a second top-level language."""
        row = self.classify('//J JOB\n//S EXEC PGM=IEBGENER\n//SYSUT1 DD DATA\nPROGRAM-ID. PAYLOAD.\n/*')
        self.assertEqual(row['kind'], 'jcl_job')

    def test_r092_custom_data_delimiter_hides_inner_job_identity(self):
        """A JOB inside DD DATA with a custom delimiter is data until that delimiter."""
        row = self.classify('//SYSIN DD DATA,DLM=ZZ\n//INNER JOB\n//S EXEC PGM=IDCAMS\nZZ')
        self.assertEqual(row['kind'], 'jcl_fragment')
        self.assertEqual(row['utility_ids'], [])

    def test_r093_multiline_block_comment_cannot_supply_program(self):
        """A program-looking line inside a block comment does not establish executable source."""
        for header in ('/* commentary', '/*'):
            self.assertEqual(self.classify(header + '\nPROGRAM-ID. FALSE.\n*/')['kind'], 'unknown')
        row = self.classify('/* commentary\n//J JOB\n//S EXEC PGM=IDCAMS\n*/')
        self.assertEqual(row['kind'], 'unknown')
        self.assertEqual(row['utility_ids'], [])

    def test_r094_block_comment_ends_before_real_sql(self):
        """A closed comment does not conceal a following structural SQL statement."""
        self.assertEqual(self.classify('/* comment\nnot code */\nSELECT A FROM APP.T;')['kind'], 'sql')

    def test_r095_jcl_delimiter_does_not_start_unclosed_comment(self):
        """The JCL data delimiter must allow the next real utility EXEC to remain visible."""
        row = self.classify('//J JOB\n//D DD *\ntext\n/*\n//S EXEC PGM=IDCAMS')
        self.assertEqual(row['utility_ids'], ['IDCAMS'])

    def test_r096_empty_export_has_explicit_unknown_evidence(self):
        """An empty export remains accounted with unresolved classification evidence."""
        row = self.classify('')
        self.assertEqual(row['kind'], 'unknown')
        self.assertTrue(row['evidence'])

    def test_r097_evidence_cap_is_declared_without_changing_classification(self):
        """More than 200 structural witnesses are explicitly truncated, not silently discarded."""
        row = self.classify('\n'.join('01 REC%03d.' % n for n in range(205)))
        self.assertEqual(row['kind'], 'copybook')
        self.assertEqual(len(row['evidence']), 200)
        self.assertTrue(row['evidence_truncated'])

    def test_r098_nontext_export_fails_with_validation_error(self):
        """A bytes export is rejected before dependency pre-scanning can raise an incidental error."""
        with self.assertRaises(ValidationError):
            classify_files({'A': b'PROGRAM-ID. A.'}, {'jobs': []}, self.snapshot)

    def test_r099_mixed_type_path_keys_fail_before_sort(self):
        """Invalid path identity types produce a validation error rather than a sorting TypeError."""
        with self.assertRaises(ValidationError):
            classify_files({'A': '', 2: ''}, {'jobs': []}, self.snapshot)

    def test_r100_comment_copy_statement_does_not_create_dependency(self):
        """A COPY in a fixed-format comment must not promote an unrelated file to reusable source."""
        self.assertEqual(self.classify('unrecognized data', 'RULES', {'COMMENT': '000100* COPY RULES.'})['kind'], 'unknown')

    def test_r101_iefbr14_allocation_risk_remains_blocking(self):
        """IEFBR14 recognition retains dataset create/delete behavior and adapter requirement."""
        row = self.find('//S EXEC PGM=IEFBR14')[0]
        self.assertIn('create or delete', row['behavior'])
        self.assertEqual(row['conversion_support'], 'adapter_required')

    def test_r102_sort_site_alias_not_product_certification(self):
        """SORT recognition retains the requirement to identify the installed sorting product."""
        row = self.find('//S EXEC PGM=SORT')[0]
        self.assertIn('site-resolved', row['behavior'])
        self.assertTrue(any('Product/version' in x for x in row['required_evidence']))

    def test_r103_tso_variants_preserve_actual_program_identity(self):
        """TSO driver variants share family context while retaining the exact invoked program."""
        rows = self.find('//A EXEC PGM=IKJEFT1A\n//B EXEC PGM=IKJEFT1B')
        self.assertEqual([x['program'] for x in rows], ['IKJEFT1A', 'IKJEFT1B'])
        self.assertTrue(all(x['utility_id'] == 'TSO_BATCH' for x in rows))

    def test_r104_icegener_fallback_is_not_plain_copy(self):
        """ICEGENER findings preserve fallback/default evidence rather than claiming a simple copy."""
        row = self.find('//S EXEC PGM=ICEGENER')[0]
        self.assertIn('transfer to IEBGENER', row['behavior'])
        self.assertTrue(any('fallback' in x for x in row['required_evidence']))

    def test_r105_iebcopy_library_member_semantics_retained(self):
        """Library copy evidence distinguishes member/alias and unload semantics from text copying."""
        row = self.find('//S EXEC PGM=IEBCOPY')[0]
        self.assertTrue(any('aliases' in x for x in row['required_evidence']))
        self.assertTrue(any('CSV' in x for x in row['risks']))

    def test_r106_db2_driver_alias_is_not_read_only_certification(self):
        """A Db2 sample-program alias preserves its concrete identity and prohibited-write context."""
        row = self.find('//S EXEC PGM=DSNTIAD')[0]
        self.assertEqual(row['program'], 'DSNTIAD')
        self.assertTrue(any('updates' in x.lower() for x in row['risks']))

    def test_r107_dd_data_embedded_exec_is_not_an_invocation(self):
        """JCL-looking EXEC cards within DD DATA must not create utility invocations."""
        rows = self.find('//J JOB\n//SYSIN DD DATA\n//FAKE EXEC PGM=IDCAMS\n/*\n//REAL EXEC PGM=IEBGENER')
        self.assertEqual([x['program'] for x in rows], ['IEBGENER'])

    def test_r108_quoted_custom_delimiter_resumes_real_invocations(self):
        """Quoted DD DATA delimiters hide payload and restore the following real step."""
        rows = self.find("//J JOB\n//D DD DATA,DLM='@@'\n//F EXEC PGM=IDCAMS\n@@\n//R EXEC PGM=IEFBR14")
        self.assertEqual([x['program'] for x in rows], ['IEFBR14'])
        self.assertEqual(rows[0]['source_refs'], [{'path': 'JOB', 'line': 5}])

    def test_r109_default_dd_star_ends_at_next_jcl_statement(self):
        """A default DD * input stream ends at the next JCL card even without a delimiter card."""
        rows = self.find('//J JOB\n//D DD *\ncontrol\n//S EXEC PGM=IDCAMS')
        self.assertEqual([x['program'] for x in rows], ['IDCAMS'])

    def test_r110_two_unnamed_steps_remain_two_invocations(self):
        """Repeated unnamed utility steps have distinct source locations and must not collapse."""
        rows = self.find('//J JOB\n// EXEC PGM=IDCAMS\n// EXEC PGM=IDCAMS')
        self.assertEqual(len(rows), 2)
        self.assertEqual([x['source_refs'][0]['line'] for x in rows], [2, 3])

    def test_r111_separate_procedure_members_keep_own_invocations(self):
        """Matching step/program names in different PROC members are distinct evidence occurrences."""
        rows = self.find(files={'P1': '//P1 PROC\n//S EXEC PGM=IDCAMS', 'P2': '//P2 PROC\n//S EXEC PGM=IDCAMS'})
        self.assertEqual(len(rows), 2)
        self.assertEqual([x['source_refs'][0]['path'] for x in rows], ['P1', 'P2'])

    def test_r112_duplicate_named_source_steps_are_not_silently_merged(self):
        """Even invalid repeated named steps must preserve each exported source occurrence."""
        rows = self.find('//J JOB\n//S EXEC PGM=IDCAMS\n//S EXEC PGM=IDCAMS')
        self.assertEqual(len(rows), 2)

    def test_r113_manifest_source_exact_match_has_single_row(self):
        """One declared invocation and its matching actual source card share a single finding."""
        manifest = {'jobs': [{'name': 'J', 'steps': [{'name': 'S', 'program': 'IDCAMS'}]}]}
        rows = self.find('//J JOB\n//S EXEC PGM=IDCAMS', manifest)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['source_refs'], [{'path': 'JOB', 'line': 2}])

    def test_r114_manifest_match_does_not_swallow_second_export_occurrence(self):
        """A second exported job occurrence cannot be hidden behind the manifest/source dedup key."""
        manifest = {'jobs': [{'name': 'J', 'steps': [{'name': 'S', 'program': 'IDCAMS'}]}]}
        rows = self.find(manifest=manifest, files={'A': '//J JOB\n//S EXEC PGM=IDCAMS', 'B': '//J JOB\n//S EXEC PGM=IDCAMS'})
        self.assertEqual(len(rows), 2)

    def test_r115_jcl_comment_does_not_invoke_program(self):
        """An EXEC text inside a JCL comment is not a utility invocation."""
        self.assertEqual(self.find('//*S EXEC PGM=IDCAMS'), [])

    def test_r116_symbolic_program_does_not_guess_utility(self):
        """Unresolved PGM symbols do not receive a fabricated concrete utility identity."""
        self.assertEqual(self.find('//S EXEC PGM=&UTILITY'), [])

    def test_r117_procedure_named_like_utility_is_not_program_invocation(self):
        """EXEC PROC=IDCAMS names a procedure and must not be treated as PGM=IDCAMS."""
        self.assertEqual(self.find('//S EXEC PROC=IDCAMS'), [])

    def test_r118_finding_risk_edits_do_not_mutate_frozen_snapshot(self):
        """Editing consumer-visible finding lists must not alter the frozen catalog object."""
        before = encode(self.snapshot)
        self.find('//S EXEC PGM=IDCAMS')[0]['risks'].append('consumer note')
        self.assertEqual(encode(self.snapshot), before)
        validate_snapshot(self.snapshot)

    def test_r119_application_details_are_detached_from_snapshot(self):
        """Application dependency lists in findings cannot mutate the source knowledge snapshot."""
        snapshot = self.custom()
        before = encode(snapshot)
        row = self.find('//S EXEC PGM=MRUN', snapshot=snapshot)[0]
        row['application_details']['dependencies'].append('consumer note')
        self.assertEqual(encode(snapshot), before)
        self.assertEqual(row['application_details']['evidence_status'], 'unverified_application_context')

    def test_r120_malformed_manifest_program_type_is_validation_error(self):
        """An invalid program field fails with an intentional validation error before uppercasing."""
        with self.assertRaises(ValidationError):
            self.find(manifest={'jobs': [{'name': 'J', 'steps': [{'name': 'S', 'program': 3}]}]})

    def test_r121_impossible_catalog_date_is_rejected(self):
        """A syntactically shaped but impossible review date cannot pass catalog validation."""
        self.bad(lambda s: s['catalog'].update(reviewed_on='2026-02-30'))

    def test_r122_boolean_schema_is_not_integer_schema(self):
        """JSON true must not pass the application's integer schema version contract."""
        self.bad(lambda s: s['application'].update(schema_version=True))

    def test_r123_unknown_execution_field_is_rejected(self):
        """A knowledge utility cannot smuggle an executable command field through the schema."""
        self.bad(lambda s: s['catalog']['utilities'][0].update(command='run arbitrary code'))

    def test_r124_conversion_support_claim_is_rejected(self):
        """Declarative catalog entries cannot assert their own conversion-support status."""
        self.bad(lambda s: s['catalog']['utilities'][0].update(conversion_support='verified'))

    def test_r125_missing_required_evidence_is_rejected(self):
        """Removing the utility evidence requirement cannot create a knowledge shortcut."""
        self.bad(lambda s: s['catalog']['utilities'][0].pop('required_evidence'))

    def test_r126_empty_utility_risks_are_rejected(self):
        """A utility entry must retain substantive risk context rather than an empty checklist."""
        self.bad(lambda s: s['catalog']['utilities'][0].update(risks=[]))

    def test_r127_alias_shadowing_standard_utility_is_rejected(self):
        """An application wrapper cannot capture a standard utility's executable name."""
        snapshot = self.custom()
        snapshot['application']['utilities'][0]['aliases'] = ['IDCAMS']
        with self.assertRaises(ValidationError): validate_snapshot(self.rehash(snapshot))

    def test_r128_duplicate_utility_identity_is_rejected(self):
        """Distinct names cannot share a utility identity and collapse downstream lineage."""
        snapshot = self.custom()
        snapshot['application']['utilities'][0]['id'] = 'IDCAMS'
        with self.assertRaises(ValidationError): validate_snapshot(self.rehash(snapshot))

    def test_r129_self_alias_is_rejected(self):
        """An executable name duplicated inside its own aliases is invalid knowledge."""
        self.bad(lambda s: s['catalog']['utilities'][0]['aliases'].append(s['catalog']['utilities'][0]['name']))

    def test_r130_topic_duplicate_identity_is_rejected(self):
        """Duplicate knowledge topics cannot create ambiguous context identities."""
        self.bad(lambda s: s['catalog']['topics'].append(copy.deepcopy(s['catalog']['topics'][0])))

    def test_r131_missing_classification_category_is_rejected(self):
        """The snapshot cannot silently omit the unknown/ambiguous accountability vocabulary."""
        self.bad(lambda s: s['catalog']['categories'].pop())

    def test_r132_duplicate_category_is_rejected(self):
        """Duplicated category rows do not satisfy the exact classification coverage schema."""
        self.bad(lambda s: s['catalog']['categories'].append(copy.deepcopy(s['catalog']['categories'][0])))

    def test_r133_identifier_control_character_is_rejected(self):
        """A newline inside a utility identifier cannot produce multi-line identity spoofing."""
        self.bad(lambda s: s['catalog']['utilities'][0].update(name='ICEMAN\n'))

    def test_r134_nul_in_free_text_is_rejected(self):
        """Knowledge prose rejects NUL controls while remaining data-only review context."""
        self.bad(lambda s: s['application']['notes'].append('owner\x00note'))

    def test_r135_oversized_note_is_rejected(self):
        """Individual free-text facts retain the 4000-character bound."""
        self.bad(lambda s: s['application']['notes'].append('x' * 4001))

    def test_r136_excessive_note_count_is_rejected(self):
        """The application note count cannot exceed the explicit ingestion budget."""
        self.bad(lambda s: s['application'].update(notes=['note %d' % n for n in range(201)]))

    def test_r137_raw_application_size_is_bounded(self):
        """An oversized application JSON file is rejected before unbounded ingestion."""
        path = self.root / 'knowledge' / 'application-knowledge.json'
        path.parent.mkdir()
        path.write_bytes(b' ' * (2 * 1024 * 1024 + 1))
        with self.assertRaises(ValidationError): load_knowledge(self.root)

    def test_r138_application_duplicate_json_keys_are_rejected(self):
        """Duplicate raw JSON keys cannot overwrite an application knowledge field silently."""
        path = self.root / 'knowledge' / 'application-knowledge.json'
        path.parent.mkdir()
        path.write_text('{"schema_version":1,"schema_version":1}')
        with self.assertRaises(ValidationError): load_knowledge(self.root)

    def test_r139_application_directory_is_not_json_file(self):
        """An application-knowledge path that is a directory fails as invalid input."""
        (self.root / 'knowledge' / 'application-knowledge.json').mkdir(parents=True)
        with self.assertRaises(ValidationError): load_knowledge(self.root)

    def test_r140_application_parent_symlink_is_rejected(self):
        """A knowledge-directory symlink cannot redirect intake outside the expected workspace path."""
        actual = self.root / 'actual'
        actual.mkdir()
        (self.root / 'knowledge').symlink_to(actual, target_is_directory=True)
        with self.assertRaises(ValidationError): load_knowledge(self.root)

    def test_r141_application_content_requires_provenance_hash(self):
        """Nonempty application context cannot claim that no application source was loaded."""
        self.bad(lambda s: s['application']['notes'].append('application fact without provenance'))

    def test_r142_standard_hash_format_is_validated(self):
        """A source hash must be a SHA256 identity, not a human annotation."""
        self.bad(lambda s: s['source_hashes'].update(standard='unconfirmed'))

    def test_r143_snapshot_tampering_is_detected(self):
        """Changing frozen behavior without updating the content digest fails replay validation."""
        snapshot = copy.deepcopy(self.snapshot)
        snapshot['catalog']['utilities'][0]['behavior'] = 'modified'
        with self.assertRaises(ValidationError): validate_snapshot(snapshot)

    def test_r144_absent_standard_catalog_is_validation_error(self):
        """A missing standard catalog produces a named validation failure rather than raw filesystem error."""
        with patch('workbench.mainframe.CATALOG_PATH', self.root / 'missing.json'):
            with self.assertRaises(ValidationError): load_knowledge(self.root)

    def test_r145_bms_definition_does_not_establish_business_ui(self):
        """Recognized BMS source retains all text and an unsupported screen-behavior blocker."""
        result = self.native('MAPSET DFHMSD TYPE=MAP\nSCREEN DFHMDI SIZE=(24,80)', 'MAP')
        self.assertEqual(result['classifications']['MAP']['kind'], 'bms_map')

    def test_r146_db2_ddl_does_not_establish_sqlite_equivalence(self):
        """Db2 DDL remains blocked while static table-reference evidence stays explicitly bounded."""
        result = self.native('CREATE TABLE APP.T (AMOUNT DECIMAL(9,2));', 'DDL')
        asset = next(a for a in result['assets'] if a['path'] == 'DDL')
        self.assertEqual(asset['table_evidence_basis'], 'STATIC_UNQUOTED_REFERENCES_NOT_CATALOG_INVENTORY')

    def test_r147_dclgen_does_not_become_supported_layout(self):
        """DCLGEN null/host declarations remain separate unsupported source rather than plain layouts."""
        result = self.native('EXEC SQL DECLARE APP.T TABLE\nEND-EXEC.\n01 HOST.\n05 N PIC 9.', 'HOST.cpy')
        self.assertEqual(result['classifications']['HOST.cpy']['kind'], 'dclgen')

    def test_r148_sort_cards_do_not_create_sort_adapter(self):
        """Sort control recognition preserves unsupported record-transform semantics."""
        result = self.native('JOINKEYS FILE=F1,FIELDS=(1,10,A)\nREFORMAT FIELDS=(F1:1,10,F2:1,10)', 'CARDS')
        self.assertEqual(result['classifications']['CARDS']['kind'], 'utility_control')

    def test_r149_cics_resource_definition_does_not_replace_transaction(self):
        """A CICS transaction binding is accounted but cannot earn a converted transaction."""
        result = self.native('DEFINE TRANSACTION(T001) GROUP(APP) PROGRAM(MAIN)', 'CSD')
        self.assertEqual(result['classifications']['CSD']['kind'], 'cics_definition')

    def test_r150_scheduler_definition_does_not_establish_calendar_parity(self):
        """Scheduler source is preserved without treating Python step order as calendar semantics."""
        result = self.native('LJOB,JOB=NIGHTLY', 'CALENDAR')
        self.assertEqual(result['classifications']['CALENDAR']['kind'], 'scheduler_definition')

    def test_r151_rexx_host_commands_remain_unsupported(self):
        """Recognized REXX with a host-command environment stays blocked and is never executed."""
        result = self.native('/* REXX */\nADDRESS TSO "ALLOCATE DATASET(APP.FILE)"', 'SCRIPT')
        self.assertEqual(result['classifications']['SCRIPT']['kind'], 'rexx')

    def test_r152_clist_nested_command_semantics_remain_unsupported(self):
        """CLIST positional arguments do not supply an executable target adapter."""
        result = self.native('PROC 0 INPUT\nWRITE &INPUT', 'COMMAND')
        self.assertEqual(result['classifications']['COMMAND']['kind'], 'clist')

    def test_r153_pli_procedure_is_not_cobol_translation(self):
        """A PL/I procedure is recognized independently and cannot enter the COBOL converter."""
        result = self.native('MAIN: PROCEDURE OPTIONS(MAIN);\nEND MAIN;', 'PLIPGM')
        self.assertEqual(result['classifications']['PLIPGM']['kind'], 'pli')

    def test_r154_assembler_section_is_not_retired_platform_code(self):
        """Assembler source cannot be silently retired as mainframe-only behavior."""
        result = self.native('MAIN CSECT\n BR 14', 'ASM')
        self.assertEqual(result['classifications']['ASM']['kind'], 'assembler')

    def test_r155_proc_symbol_expansion_requires_adapter(self):
        """Procedure/symbol source is preserved with unsupported expansion semantics."""
        result = self.native('//P PROC UTILITY=IDCAMS\n//S EXEC PGM=&UTILITY\n// PEND', 'PROC')
        self.assertEqual(result['classifications']['PROC']['kind'], 'jcl_proc')

    def test_r156_dd_gdg_lifecycle_is_not_verified_allocation(self):
        """A GDG allocation and DISP lifecycle cannot gain native behavior credit from JCL parsing."""
        result = self.native('//JOBA JOB\n//S010 EXEC PGM=ELIGIBLE\n//OUT DD DSN=APP.GDG(+1),DISP=(NEW,CATLG,DELETE)', 'JOBA')
        self.assertTrue(any(b['kind'] == 'unsupported_jcl' and b.get('path') == 'JOBA' for b in result['blockers']))

    def test_r157_cond_bypass_is_not_manifest_execute_if(self):
        """Native COND bypass semantics remain unsupported instead of being guessed as execute-if."""
        result = self.native('//JOBA JOB\n//S010 EXEC PGM=ELIGIBLE,COND=(4,LT)', 'JOBA')
        self.assertTrue(any(b['kind'] == 'unsupported_jcl' for b in result['blockers']))

    def test_r158_ims_controller_recognition_does_not_supply_ims_adapter(self):
        """An IMS controller invocation retains an unsupported utility blocker and required context."""
        result = self.native('//J JOB\n//S EXEC PGM=DFSRRC00,PARM=\'DLI,MAIN,PSB\'', 'IMS')
        self.assertTrue(any(b['kind'] == 'unsupported_utility' and b.get('utility_id') == 'DFSRRC00' for b in result['blockers']))

    def test_r159_uss_command_driver_never_executes_collected_text(self):
        """USS driver recognition preserves shell side-effect risk without executing PARM text."""
        result = self.native('//J JOB\n//S EXEC PGM=BPXBATCH,PARM=\'SH echo unsafe\'', 'USS')
        self.assertTrue(any(b['kind'] == 'unsupported_utility' and b.get('utility_id') == 'BPXBATCH' for b in result['blockers']))

    def test_r160_custom_owner_fact_never_grants_conversion_support(self):
        """Owner/version context on a custom utility remains unverified and adapter-required."""
        self.snapshot = self.custom()
        result = self.native('//J JOB\n//S EXEC PGM=MATCHREF', 'WRAPPER')
        row = next(x for x in result['utility_findings'] if x['utility_id'] == 'APP_MATCH')
        self.assertEqual(row['conversion_support'], 'adapter_required')
        self.assertEqual(row['application_details']['evidence_status'], 'unverified_application_context')


if __name__ == '__main__':
    unittest.main()
