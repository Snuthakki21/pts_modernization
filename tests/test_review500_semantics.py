"""R161–R240: distinct bounded COBOL, target, oracle and witness reviews.

Expected records below are specified directly, separately from the shared parser.
These checks establish the documented subset and explicit blockers, not native parity.
"""
import copy
import json
import unittest
from unittest.mock import Mock, patch

from workbench.domain import ValidationError, encode, decode
from workbench.source import analyze_program, condition, literal
from workbench.target import emit_program, run_generated, prepare_generated, check_generated
from workbench.reference import run_reference
from workbench.fixtures import plan_cases, verify_program, adversarial_review
from test_source import COBOL


class Review500Semantics(unittest.TestCase):
    def program(self, text=COBOL, version=2, files=None):
        result = analyze_program('ELIGIBLE.cbl', text, files or {})
        if version != 1:
            result['target_contract_version'] = version
        return result

    def blocked(self, text, reason=None):
        program = self.program(text)
        self.assertTrue(program['blockers'], 'Unsupported source received conversion eligibility')
        self.assertEqual([row['original'] for row in program['coverage']], text.splitlines())
        self.assertTrue(all(row['disposition'] != 'unaccounted' for row in program['coverage']))
        if reason:
            self.assertTrue(any(reason in row['message'] for row in program['blockers']), program['blockers'])
        with self.assertRaises(ValidationError):
            emit_program(program)
        return program

    def body(self, body, fields=None):
        source = COBOL[:COBOL.index('PROCEDURE DIVISION')]
        if fields is not None:
            source = source[:source.index('01 INPUT-RECORD.')] + fields + '\n'
        return source + 'PROCEDURE DIVISION USING INPUT-RECORD.\n' + body + '\nGOBACK.\n'

    def same_result(self, program, record, expected, branches):
        self.assertFalse(program['blockers'], program['blockers'])
        before = copy.deepcopy(record)
        for result in (run_reference(program, record), run_generated(emit_program(program), record)):
            self.assertEqual(result['input_status'], 'ACCEPT_INPUT')
            self.assertEqual(result['record'], expected)
            self.assertEqual([row['branch'] for row in result['trace']], branches)
            self.assertEqual(result['return_code'], 0)
        self.assertEqual(record, before)

    def rejected(self, record):
        program = self.program()
        expected = run_reference(program, record)
        self.assertEqual(expected['input_status'], 'REJECT_INPUT')
        self.assertEqual(run_generated(emit_program(program), record), expected)
        return expected

    def test_r161_orphan_level05_field(self):
        """A level-05 field appears before any record group => block its invented INPUT ownership."""
        self.blocked(COBOL.replace('01 INPUT-RECORD.\n  05 AGE PIC 9(3).', '05 AGE PIC 9(3).\n01 INPUT-RECORD.'), 'preceding level-01')

    def test_r162_repeated_linkage_section(self):
        """A second LINKAGE SECTION reopens storage => preserve both lines and block the duplicate."""
        self.blocked(COBOL.replace('01 INPUT-RECORD.', 'LINKAGE SECTION.\n01 INPUT-RECORD.'), 'Repeated record SECTION')

    def test_r163_filler_field_is_not_a_named_input(self):
        """An unnamed FILLER elementary item is supplied => block rather than require a JSON FILLER key."""
        self.blocked(COBOL.replace('05 ACTIVE PIC X.', '05 FILLER PIC X.'), 'Unnamed FILLER fields')

    def test_r164_filler_group_is_not_a_using_name(self):
        """A FILLER group is named in PROCEDURE USING => reject invented group identity."""
        self.blocked(COBOL.replace('INPUT-RECORD', 'FILLER'), 'Unnamed FILLER groups')

    def test_r165_level77_must_not_inherit_group(self):
        """A standalone level-77 item follows an 01 group => block until standalone USING semantics are modeled."""
        self.blocked(COBOL.replace('05 AGE PIC 9(3).', '77 AGE PIC 9(3).'), 'level-77')

    def test_r166_empty_group_has_no_layout(self):
        """A declared USING group has no elementary fields => reject an unrepresented caller argument."""
        text = COBOL.replace('01 INPUT-RECORD.', '01 EMPTY-RECORD.\n01 INPUT-RECORD.').replace('USING INPUT-RECORD.', 'USING EMPTY-RECORD INPUT-RECORD.')
        self.blocked(text, 'requires a supported field layout')

    def test_r167_program_id_outside_identification(self):
        """PROGRAM-ID is moved into DATA DIVISION => block invalid division ownership."""
        text = COBOL.replace('PROGRAM-ID. ELIGIBLE.\n', '').replace('DATA DIVISION.', 'DATA DIVISION.\nPROGRAM-ID. ELIGIBLE.')
        self.blocked(text, 'must belong to IDENTIFICATION')

    def test_r168_group_and_field_name_collision(self):
        """An elementary field reuses its group name => block qualification ambiguity."""
        self.blocked(COBOL.replace('ACTIVE', 'INPUT-RECORD'), 'Duplicate field names')

    def test_r169_reserved_verb_is_not_a_paragraph(self):
        """EXIT is placed between the final IF and GOBACK => explicitly block unsupported control flow."""
        p = self.blocked(COBOL.replace('GOBACK.', 'EXIT.\nGOBACK.'), 'Unsupported executable statement: EXIT')
        self.assertEqual(next(x for x in p['coverage'] if x['original'] == '  EXIT.')['disposition'], 'unsupported')

    def test_r170_terminal_repeated_period(self):
        """A malformed GOBACK double period is supplied => do not normalize it into a supported terminal."""
        self.blocked(COBOL.replace('GOBACK.', 'GOBACK..'), 'No supported terminal')

    def test_r171_endif_repeated_period(self):
        """END-IF has two sentence periods => do not silently close the branch."""
        self.blocked(COBOL.replace('END-IF.', 'END-IF..'), 'Unclosed or nested IF')

    def test_r172_missing_true_body(self):
        """An IF immediately reaches ELSE => reject a syntactically absent imperative statement."""
        self.blocked(COBOL.replace('    MOVE "Y" TO DECISION\n', ''), 'Empty IF body')

    def test_r173_missing_false_body(self):
        """ELSE immediately reaches END-IF => require an explicit CONTINUE instead of inventing one."""
        self.blocked(COBOL.replace('    MOVE "N" TO DECISION\n', ''), 'Empty ELSE body')

    def test_r174_deep_condition_has_named_bound(self):
        """A 1500-relation OR chain threatens recursive downstream visitors => reject with a named comparison bound."""
        self.blocked(COBOL.replace('AGE >= 18', ' OR '.join(['AGE = 0'] * 1500)), 'comparison bound')
        bounded = self.program(COBOL.replace('AGE >= 18', ' OR '.join(['AGE = 18'] * 192)))
        self.assertEqual(decode(encode(bounded)), bounded)
        frozen = {'process': {'document': {'analysis': {'programs': {'ELIGIBLE': bounded}, 'assets': [bounded]}}}}
        self.assertEqual(decode(encode(frozen)), frozen)
        row = {'AGE': 18, 'ACTIVE': 'Y', 'DECISION': ' '}
        self.same_result(bounded, row, {**row, 'DECISION': 'Y'}, [True, False])

    def test_r175_numeric_literal_parsing_bound(self):
        """A 5000-digit comparison literal exceeds Python integer limits => produce a source blocker rather than ValueError."""
        self.blocked(COBOL.replace('AGE >= 18', 'AGE >= ' + '9' * 5000), 'Numeric literal exceeds')

    def test_r176_picture_width_parsing_bound(self):
        """A 5000-digit PICTURE width is supplied => preserve source and block before integer conversion."""
        self.blocked(COBOL.replace('9(3)', '9(' + '9' * 5000 + ')'), 'width token exceeds')

    def test_r177_fixed_continuation_blocks(self):
        """A fixed-format continuation line carries executable text => retain its exact text and deny translation."""
        self.blocked(COBOL.replace('  IF AGE >= 18', '000100-IF AGE >= 18'), 'Fixed-format continuation')

    def test_r178_fixed_column_overflow_blocks(self):
        """Fixed-format content extends past column 72 => block rather than truncate a hidden condition."""
        self.blocked(COBOL.replace('  IF AGE >= 18', '000100 IF AGE >= 18'.ljust(72) + ' AND ACTIVE = "N"'), 'beyond column 72')

    def test_r179_duplicate_else_blocks(self):
        """One flat IF contains two ELSE tokens => retain a blocker instead of choosing the last arm."""
        self.blocked(COBOL.replace('  ELSE\n', '  ELSE\n    CONTINUE\n  ELSE\n', 1), 'Repeated ELSE')

    def test_r180_inline_statements_are_not_split_by_guess(self):
        """A condition and MOVE share a physical line => block the unsupported statement layout."""
        self.blocked(COBOL.replace('AGE >= 18\n    MOVE "Y" TO DECISION', 'AGE >= 18 MOVE "Y" TO DECISION'), 'Empty IF body')

    def test_r181_perform_requires_control_adapter(self):
        """PERFORM appears before GOBACK => do not silently retire an invocation."""
        self.blocked(COBOL.replace('GOBACK.', 'PERFORM CHECK-AGE\nGOBACK.'), 'Unsupported executable statement: PERFORM')

    def test_r182_file_section_is_not_caller_linkage(self):
        """FILE SECTION replaces LINKAGE => block native file binding and storage lifetime."""
        self.blocked(COBOL.replace('LINKAGE SECTION.', 'FILE SECTION.'), 'Storage lifetime or file binding')

    def test_r183_redefines_aliasing_stays_unsupported(self):
        """A field overlays AGE with REDEFINES => require byte-layout alias semantics before conversion."""
        self.blocked(COBOL.replace('05 ACTIVE PIC X.', '05 ACTIVE REDEFINES AGE PIC X(3).'), 'Unsupported declaration')

    def test_r184_occurs_does_not_become_scalar(self):
        """A field declares OCCURS => block scalar extraction of an array."""
        self.blocked(COBOL.replace('05 AGE PIC 9(3).', '05 AGE PIC 9(3) OCCURS 2 TIMES.'), 'Unsupported declaration')

    def test_r185_signed_picture_does_not_become_unsigned(self):
        """AGE declares PIC S9 => block loss of sign representation."""
        self.blocked(COBOL.replace('PIC 9(3)', 'PIC S9(3)'), 'Unsupported declaration')

    def test_r186_packed_picture_does_not_become_display(self):
        """AGE declares COMP-3 => require a packed-decimal adapter."""
        self.blocked(COBOL.replace('PIC 9(3).', 'PIC 9(3) COMP-3.'), 'Unsupported declaration')

    def test_r187_overwidth_comparison_is_not_truncated(self):
        """A one-character field is compared with a two-character literal => block an unavailable comparison adapter."""
        self.blocked(COBOL.replace('ACTIVE = "N"', 'ACTIVE = "NO"'), 'Over-width literal comparison')

    def test_r188_string_ordering_requires_collation(self):
        """A character comparison uses greater-than => reject Python collation as a native replacement."""
        self.blocked(COBOL.replace('ACTIVE = "N"', 'ACTIVE > "N"'), 'verified source collation')

    def test_r189_unequal_character_layouts_block(self):
        """Different-width character fields are compared => require an exact padding/comparison adapter."""
        text = COBOL.replace('05 ACTIVE PIC X.', '05 ACTIVE PIC X(2).').replace('ACTIVE = "N"', 'ACTIVE = DECISION')
        self.blocked(text, 'Differing operand layouts')

    def test_r190_nested_if_does_not_flatten(self):
        """An IF is nested inside the true arm => reject unsupported control nesting."""
        self.blocked(COBOL.replace('MOVE "Y" TO DECISION', 'IF ACTIVE = "Y"\nMOVE "Y" TO DECISION\nEND-IF'), 'nested IF')

    def test_r191_boolean_precedence_matches_hand_expectation(self):
        """OR combines an age rule with an AND pair => AND binds first and the age-18 row remains true."""
        p = self.program(self.body('IF AGE = 18 OR ACTIVE = "Y" AND DECISION = "N"\nMOVE "Y" TO DECISION\nELSE\nMOVE "N" TO DECISION\nEND-IF.'))
        row = {'AGE': 18, 'ACTIVE': 'N', 'DECISION': ' '}
        self.same_result(p, row, {**row, 'DECISION': 'Y'}, [True])

    def test_r192_left_character_literal_padding(self):
        """The literal is the left operand of a PIC X(3) comparison => pad it before both interpreters compare."""
        p = self.program(COBOL.replace('05 ACTIVE PIC X.', '05 ACTIVE PIC X(3).').replace('ACTIVE = "N"', '"N" = ACTIVE'))
        row = {'AGE': 18, 'ACTIVE': 'N  ', 'DECISION': ' '}
        self.same_result(p, row, {**row, 'DECISION': 'N'}, [True, True])

    def test_r193_doubled_quote_is_one_character(self):
        """A doubled COBOL quote occurs in a literal => decode one quote and preserve exact comparison/effect text."""
        p = self.program(self.body('IF ACTIVE = "A""B"\nMOVE "\'" TO DECISION\nELSE\nCONTINUE\nEND-IF.').replace('05 ACTIVE PIC X.', '05 ACTIVE PIC X(3).'))
        row = {'AGE': 0, 'ACTIVE': 'A"B', 'DECISION': ' '}
        self.same_result(p, row, {**row, 'DECISION': "'"}, [True])

    def test_r194_comment_marker_inside_literal(self):
        """A quoted literal contains the inline-comment marker => retain literal bytes while removing the real trailing comment."""
        p = self.program(self.body('IF ACTIVE = "*>" *> actual comment\nMOVE "Y" TO DECISION\nEND-IF.').replace('05 ACTIVE PIC X.', '05 ACTIVE PIC X(2).'))
        row = {'AGE': 0, 'ACTIVE': '*>', 'DECISION': ' '}
        self.same_result(p, row, {**row, 'DECISION': 'Y'}, [True])

    def test_r195_numeric_field_comparison_widths(self):
        """Unsigned fields with different decimal widths compare numerically => the larger AGE value takes the true arm."""
        fields = '01 INPUT-RECORD.\n05 AGE PIC 9(3).\n05 LIMIT-AGE PIC 9.\n05 DECISION PIC X.'
        p = self.program(self.body('IF AGE > LIMIT-AGE\nMOVE "Y" TO DECISION\nELSE\nMOVE "N" TO DECISION\nEND-IF.', fields))
        row = {'AGE': 10, 'LIMIT-AGE': 9, 'DECISION': ' '}
        self.same_result(p, row, {**row, 'DECISION': 'Y'}, [True])

    def test_r196_later_condition_reads_prior_write(self):
        """The first rule changes AGE and the second tests AGE => the later condition observes the updated record."""
        p = self.program(self.body('IF AGE = 0\nMOVE 18 TO AGE\nEND-IF.\nIF AGE >= 18\nMOVE "Y" TO DECISION\nEND-IF.'))
        row = {'AGE': 0, 'ACTIVE': 'N', 'DECISION': ' '}
        self.same_result(p, row, {**row, 'AGE': 18, 'DECISION': 'Y'}, [True, True])

    def test_r197_assignment_order_in_one_arm(self):
        """Two literal assignments target the same field in one arm => the second assignment determines the output."""
        p = self.program(self.body('IF AGE = 0\nMOVE "Y" TO DECISION\nMOVE "N" TO DECISION\nEND-IF.'))
        row = {'AGE': 0, 'ACTIVE': 'Y', 'DECISION': ' '}
        self.same_result(p, row, {**row, 'DECISION': 'N'}, [True])

    def test_r198_absent_else_preserves_false_record(self):
        """A false IF has no ELSE clause => preserve its input record and emit the false decision trace."""
        p = self.program(self.body('IF AGE >= 18\nMOVE "Y" TO DECISION\nEND-IF.'))
        row = {'AGE': 17, 'ACTIVE': 'Y', 'DECISION': 'X'}
        self.same_result(p, row, row, [False])

    def test_r199_explicit_continue_preserves_true_record(self):
        """CONTINUE is the true imperative statement => preserve values while recording the executed decision."""
        p = self.program(self.body('IF AGE = 18\nCONTINUE\nELSE\nMOVE "N" TO DECISION\nEND-IF.'))
        row = {'AGE': 18, 'ACTIVE': 'Y', 'DECISION': 'X'}
        self.same_result(p, row, row, [True])

    def test_r200_eighteen_digit_integer_exactness(self):
        """The maximum supported decimal integer is compared and moved => retain all 18 digits without floating conversion."""
        p = self.program(self.body('IF AGE = 999999999999999999\nMOVE 999999999999999998 TO AGE\nEND-IF.').replace('9(3)', '9(18)'))
        row = {'AGE': 999999999999999999, 'ACTIVE': 'Y', 'DECISION': ' '}
        self.same_result(p, row, {**row, 'AGE': 999999999999999998}, [True])

    def test_r201_outside_domain_condition_has_unreachable_gap(self):
        """AGE is compared above its maximum domain => reject synthetic overflow inputs and leave the true branch unverified."""
        p = self.program(COBOL.replace('AGE >= 18', 'AGE > 999'))
        suite = plan_cases(p)
        self.assertFalse(suite['coverage']['complete'])
        self.assertTrue(any(g['rule_id'] == 'ELIGIBLE_R001' and g['branch'] == 'true' for g in suite['coverage']['gaps']))
        self.assertTrue(any(c['record'].get('AGE') == 1000 and c['intentional_invalid'] for c in suite['cases'] if isinstance(c['record'], dict)))

    def test_r202_stop_run_is_supported_terminal(self):
        """STOP RUN replaces GOBACK at the end of this bounded callable program => preserve declared zero-RC output semantics."""
        p = self.program(COBOL.replace('GOBACK.', 'STOP RUN.'))
        row = {'AGE': 18, 'ACTIVE': 'Y', 'DECISION': ' '}
        self.same_result(p, row, {**row, 'DECISION': 'Y'}, [True, False])
        self.assertEqual(p['coverage'][-1]['disposition'], 'terminal')

    def test_r203_lowercase_paragraph_case_insensitivity(self):
        """A supported paragraph label is lowercase => retain the label and the following executable rules."""
        p = self.program(COBOL.replace('  IF AGE >= 18', 'evaluate-age.\n  IF AGE >= 18'))
        row = {'AGE': 17, 'ACTIVE': 'Y', 'DECISION': ' '}
        self.same_result(p, row, {**row, 'DECISION': 'N'}, [False, False])
        self.assertEqual(next(x for x in p['coverage'] if x['original'] == 'evaluate-age.')['disposition'], 'paragraph')

    def test_r204_string_literal_case_is_preserved(self):
        """A lowercase comparison literal meets an uppercase caller value => compare case-sensitively and retain literal effects."""
        p = self.program(self.body('IF ACTIVE = "y"\nMOVE "y" TO DECISION\nELSE\nMOVE "n" TO DECISION\nEND-IF.'))
        row = {'AGE': 0, 'ACTIVE': 'Y', 'DECISION': ' '}
        self.same_result(p, row, {**row, 'DECISION': 'n'}, [False])

    def test_r205_copybook_line_provenance(self):
        """AGE comes from the third physical copybook line => preserve exact dependency field provenance."""
        text = COBOL.replace('05 AGE PIC 9(3).', 'COPY AGEBOOK.')
        p = self.program(text, files={'AGEBOOK.cpy': '*> documentation\n\n05 AGE PIC 9(3).\n'})
        self.assertFalse(p['blockers'])
        self.assertEqual(p['fields']['AGE']['source_ref'], 'AGEBOOK.cpy:3')
        self.assertEqual(p['dependencies'][0]['path'], 'AGEBOOK.cpy')

    def test_r206_copybook_change_invalidates_semantic_hash(self):
        """Only the included field width changes => preserve primary source hash but change dependency and semantic hashes."""
        text = COBOL.replace('05 AGE PIC 9(3).', 'COPY AGEBOOK.')
        a = self.program(text, files={'AGEBOOK.cpy': '05 AGE PIC 9(3).\n'})
        b = self.program(text, files={'AGEBOOK.cpy': '05 AGE PIC 9(4).\n'})
        self.assertEqual(a['source_hash'], b['source_hash'])
        self.assertNotEqual(a['dependency_hash'], b['dependency_hash'])
        self.assertNotEqual(a['semantic_hash'], b['semantic_hash'])
        self.assertNotEqual(plan_cases(a)['contract_hash'], plan_cases(b)['contract_hash'])

    def test_r207_self_comparison_does_not_invent_false_witness(self):
        """AGE equals itself for every valid record => expose a false-branch gap instead of claiming full branch coverage."""
        p = self.program(COBOL.replace('AGE >= 18', 'AGE = AGE'))
        suite = plan_cases(p)
        self.assertEqual(suite['coverage']['rules']['ELIGIBLE_R001']['false'], [])
        self.assertFalse(suite['coverage']['complete'])

    def test_r208_literal_only_comparison_is_explicit(self):
        """A constant literal equality replaces the first condition => evaluate its true branch and report the unreachable false path."""
        p = self.program(COBOL.replace('AGE >= 18', '1 = 1'))
        row = {'AGE': 0, 'ACTIVE': 'Y', 'DECISION': ' '}
        self.same_result(p, row, {**row, 'DECISION': 'Y'}, [True, False])
        self.assertFalse(plan_cases(p)['coverage']['complete'])

    def test_r209_bool_is_not_numeric_input(self):
        """Python bool is supplied for unsigned AGE => both direct exported target and oracle reject it."""
        self.assertIn('AGE: invalid unsigned integer', self.rejected({'AGE': True, 'ACTIVE': 'Y', 'DECISION': ' '})['errors'])

    def test_r210_pairs_list_is_not_record_object(self):
        """A list of key/value pairs could be coerced by dict => reject it before target record copying."""
        self.assertEqual(self.rejected([('AGE', 18), ('ACTIVE', 'Y'), ('DECISION', ' ')])['errors'], ['record must be an object'])

    def test_r211_dict_subclass_cannot_execute_get_hook(self):
        """A dict subclass overrides get with a side effect => reject the subtype before invoking its hook."""
        calls = []
        class Hostile(dict):
            def get(self, key, default=None):
                calls.append(key)
                raise AssertionError('get hook executed')
        self.rejected(Hostile(AGE=18, ACTIVE='Y', DECISION=' '))
        self.assertEqual(calls, [])

    def test_r212_equal_size_wrong_field_set(self):
        """An expected field is replaced by an unknown field at the same object size => reject both shape and missing value."""
        errors = self.rejected({'AGE': 18, 'ACTIVE': 'Y', 'EXTRA': ' '})['errors']
        self.assertEqual(errors, ['field set differs from source layout', 'DECISION: invalid fixed-width string'])

    def test_r213_null_integer_input(self):
        """A null numeric field reaches the exported target => short-circuit range comparisons and return a structured rejection."""
        self.assertEqual(self.rejected({'AGE': None, 'ACTIVE': 'Y', 'DECISION': ' '})['return_code'], None)

    def test_r214_exact_fixed_width_includes_trailing_space(self):
        """A two-character field receives an unpadded one-character string => reject transport length instead of silently padding input."""
        p = self.program(COBOL.replace('05 ACTIVE PIC X.', '05 ACTIVE PIC X(2).'))
        row = {'AGE': 18, 'ACTIVE': 'Y', 'DECISION': ' '}
        self.assertEqual(run_generated(emit_program(p), row), run_reference(p, row))
        self.assertEqual(run_reference(p, row)['input_status'], 'REJECT_INPUT')
        self.same_result(p, {**row, 'ACTIVE': 'Y '}, {**row, 'ACTIVE': 'Y ', 'DECISION': 'Y'}, [True, False])

    def test_r215_target_return_record_is_independent(self):
        """The caller edits the returned record after execution => its original record remains unchanged."""
        row = {'AGE': 18, 'ACTIVE': 'Y', 'DECISION': ' '}
        result = run_generated(emit_program(self.program()), row)
        self.assertIsNot(result['record'], row)
        result['record']['AGE'] = 999
        self.assertEqual(row, {'AGE': 18, 'ACTIVE': 'Y', 'DECISION': ' '})

    def test_r216_prepared_target_has_no_cross_call_state(self):
        """One prepared function executes two different rows and its first trace is edited => second execution has independent trace/state."""
        execute = prepare_generated(emit_program(self.program()))
        first = execute({'AGE': 18, 'ACTIVE': 'Y', 'DECISION': ' '})
        first['trace'].clear()
        second = execute({'AGE': 17, 'ACTIVE': 'Y', 'DECISION': ' '})
        self.assertEqual(second['record']['DECISION'], 'N')
        self.assertEqual([x['branch'] for x in second['trace']], [False, False])

    def test_r217_oracle_does_not_cache_mutable_results(self):
        """An oracle result is edited before evaluating the same row again => fresh interpretation retains source behavior."""
        p = self.program()
        row = {'AGE': 18, 'ACTIVE': 'Y', 'DECISION': ' '}
        first = run_reference(p, row)
        first['record']['DECISION'] = 'N'
        first['trace'].clear()
        second = run_reference(p, row)
        self.assertEqual(second['record']['DECISION'], 'Y')
        self.assertEqual(len(second['trace']), 2)
        self.assertEqual(row['DECISION'], ' ')

    def test_r218_unknown_contract_version_blocks_all_paths(self):
        """An unsupported future contract version is supplied => source oracle, fixtures and emission all reject it."""
        p = self.program(version=3)
        for operation in (lambda: emit_program(p), lambda: run_reference(p, {}), lambda: plan_cases(p)):
            with self.assertRaisesRegex(ValidationError, 'Unsupported target contract version'):
                operation()

    def test_r219_boolean_contract_version_is_not_version_one(self):
        """The JSON contract version is boolean true => reject Python integer-equivalence coercion."""
        p = self.program()
        p['target_contract_version'] = True
        with self.assertRaisesRegex(ValidationError, 'Unsupported target contract version'):
            emit_program(p)
        with self.assertRaises(ValidationError):
            run_reference(p, {})

    def test_r220_nested_target_function_is_rejected(self):
        """A target adds a nested function declaration => reject executable structure outside the single generated entrypoint."""
        with self.assertRaisesRegex(ValidationError, 'Nested target functions'):
            check_generated('def run_program(record):\n def run_program(record):\n  return record\n return record\n')

    def test_r221_eager_target_annotation_is_rejected(self):
        """A function parameter annotation calls record.get => reject eager definition-time expressions before execution."""
        with self.assertRaisesRegex(ValidationError, 'exactly one record argument'):
            prepare_generated('def run_program(record: record.get("SECRET")):\n return record\n')

    def test_r222_forbidden_import_is_rejected(self):
        """A target imports an operating-system module => deny capability before compilation/execution."""
        with self.assertRaises(ValidationError):
            prepare_generated('def run_program(record):\n import os\n return record\n')

    def test_r223_comprehension_iteration_is_rejected(self):
        """A target introduces an unbounded comprehension over caller data => deny unsupported executable iteration."""
        with self.assertRaises(ValidationError):
            check_generated('def run_program(record):\n return [record for record in record]\n')

    def test_r224_attribute_escape_is_rejected(self):
        """A target accesses record.__class__ => reject reflection outside approved get/append attributes."""
        with self.assertRaises(ValidationError):
            check_generated('def run_program(record):\n return record.__class__\n')

    def test_r225_direct_caller_assignment_is_rejected(self):
        """A target writes record AGE directly => reject caller-owned assignment targets."""
        with self.assertRaisesRegex(ValidationError, 'Unsafe assignment target'):
            check_generated('def run_program(record):\n record["AGE"] = 18\n return record\n')

    def test_r226_alias_cannot_bypass_caller_write_guard(self):
        """A target aliases row to record then writes row => reject the alias before it mutates caller input."""
        code = emit_program(self.program()).replace('row = dict(record)', 'row = record')
        row = {'AGE': 18, 'ACTIVE': 'Y', 'DECISION': ' '}
        with self.assertRaisesRegex(ValidationError, 'independent record copy'):
            run_generated(code, row)
        self.assertEqual(row['DECISION'], ' ')

    def test_r227_fixture_budget_bound_is_strict(self):
        """The case budget is zero, negative, over 256, fractional or boolean => reject silent truncation/coercion."""
        for budget in (0, -1, 257, 2.5, True):
            with self.subTest(budget=budget), self.assertRaises(ValidationError):
                plan_cases(self.program(), budget=budget)

    def test_r228_seed_replay_is_byte_identical(self):
        """Identical source and seed regenerate fixtures => produce byte-identical frozen cases, witnesses and expected outputs."""
        p = self.program()
        self.assertEqual(encode(plan_cases(p, seed=91)), encode(plan_cases(p, seed=91)))
        self.assertNotEqual(plan_cases(p, seed=91)['contract_hash'], plan_cases(p, seed=92)['contract_hash'])

    def test_r229_ledger_key_order_cannot_change_cases(self):
        """Canonical JSON reorders field mappings before replay => keep v2 target code and deterministic fixture bytes identical."""
        p = self.program()
        restored = json.loads(encode(p))
        self.assertEqual(emit_program(p), emit_program(restored))
        self.assertEqual(encode(plan_cases(p)), encode(plan_cases(restored)))

    def test_r230_cross_group_matching_fixtures(self):
        """Two LINKAGE record groups compare their own keys => fixtures expose correlated group rows with matching and mismatching witnesses."""
        text = COBOL.replace('05 ACTIVE PIC X.', '05 ACTIVE PIC X.\n01 OTHER-RECORD.\n05 OTHER-AGE PIC 9(3).').replace('USING INPUT-RECORD.', 'USING INPUT-RECORD OTHER-RECORD.').replace('AGE >= 18', 'AGE = OTHER-AGE')
        p = self.program(text)
        self.assertFalse(p['blockers'])
        suite = plan_cases(p)
        witnesses = suite['coverage']['rules']['ELIGIBLE_R001']
        self.assertTrue(witnesses['true'] and witnesses['false'])
        for case in suite['cases']:
            if case['intentional_invalid']:
                continue
            self.assertEqual(case['files']['INPUT-RECORD'][0]['AGE'], case['record']['AGE'])
            self.assertEqual(case['files']['OTHER-RECORD'][0]['OTHER-AGE'], case['record']['OTHER-AGE'])
            self.assertNotIn('OTHER-AGE', case['files']['INPUT-RECORD'][0])

    def test_r231_budget_exhaustion_retains_obligations(self):
        """A one-case budget cannot cover mandatory boundaries and malformed inputs => enumerate omitted records and withhold complete credit."""
        suite = plan_cases(self.program(), budget=1)
        self.assertEqual(len(suite['cases']), 1)
        self.assertTrue(suite['coverage']['obligation_gaps'])
        self.assertTrue(all(g['status'] == 'budget_exhausted' and g['record_hash'] for g in suite['coverage']['obligation_gaps']))
        self.assertFalse(suite['coverage']['complete'])

    def test_r232_forged_expected_output_is_rejected(self):
        """A frozen expected output is edited to fit a changed target => reject the suite before execution."""
        p = self.program()
        suite = plan_cases(p)
        case = next(c for c in suite['cases'] if not c['intentional_invalid'])
        case['expected']['record']['DECISION'] = '?'
        with self.assertRaisesRegex(ValidationError, 'Frozen suite or coverage differs'):
            verify_program(p, emit_program(p), suite)

    def test_r233_forged_coverage_credit_is_rejected(self):
        """A budget-limited suite has its complete flag forged => recompute deterministic coverage and reject invented credit."""
        p = self.program()
        suite = plan_cases(p, budget=1)
        suite['coverage']['complete'] = True
        with self.assertRaisesRegex(ValidationError, 'Frozen suite or coverage differs'):
            verify_program(p, emit_program(p), suite)

    def test_r234_stale_source_suite_is_rejected(self):
        """Fixtures from age threshold 18 are reused after source changes to 19 => reject stale source-derived evidence."""
        a = self.program()
        b = self.program(COBOL.replace('AGE >= 18', 'AGE >= 19'))
        with self.assertRaises(ValidationError):
            verify_program(b, emit_program(b), plan_cases(a))

    def test_r235_every_input_guard_has_rejecting_witness(self):
        """Every v2 generated input guard is disabled in turn => each mutation is detected by an executed malformed-input witness."""
        p = self.program()
        report = adversarial_review(p, emit_program(p), plan_cases(p))
        guards = [m for m in report['mutations'] if m['kind'] == 'input_contract']
        self.assertEqual(len(guards), len(p['fields']) + 3)
        self.assertTrue(all(m['detected'] and m['witnesses'] for m in guards))

    def test_r236_each_literal_effect_is_mutated(self):
        """True and false arms each contain a literal effect => adversarial review tests every effect and finds concrete differences."""
        p = self.program()
        report = adversarial_review(p, emit_program(p), plan_cases(p))
        effects = [m for m in report['mutations'] if m['kind'] == 'effect']
        self.assertEqual(len(effects), sum(len(r['then']) + len(r['else']) for r in p['rules']))
        self.assertTrue(all(m['detected'] for m in effects))

    def test_r237_overwritten_effect_has_adversarial_gap(self):
        """A second same-arm assignment masks the first effect mutation => expose a surviving mutation and fail adversarial credit."""
        p = self.program(self.body('IF AGE >= 18\nMOVE "Y" TO DECISION\nMOVE "N" TO DECISION\nELSE\nCONTINUE\nEND-IF.'))
        report = adversarial_review(p, emit_program(p), plan_cases(p))
        self.assertFalse(report['passed'])
        self.assertTrue(any(m['kind'] == 'effect' and 'assignment 1' in m['mutation'] and not m['detected'] for m in report['gaps']))

    def test_r238_runtime_target_error_is_failed_evidence(self):
        """A structurally allowed target reads an absent field on valid records => capture KeyError as mismatch evidence rather than aborting verification."""
        p = self.program()
        code = emit_program(p).replace("row['AGE'] >= 18", "row['MISSING'] >= 18")
        result = verify_program(p, code, plan_cases(p))
        self.assertEqual(result['status'], 'MISMATCH')
        self.assertTrue(any(d['actual'].get('input_status') == 'TARGET_ERROR' and d['actual']['error_type'] == 'KeyError' for d in result['differences']))

    def test_r239_checkpoint_is_retained_per_case(self):
        """The target is compiled once for a fixture suite => cancellation checkpoints still run before every case."""
        p = self.program()
        suite = plan_cases(p)
        checkpoint = Mock()
        with patch('workbench.target.check_generated', wraps=check_generated) as checked:
            result = verify_program(p, emit_program(p), suite, checkpoint)
        self.assertFalse(result['differences'])
        self.assertEqual(checkpoint.call_count, len(suite['cases']))
        self.assertEqual(checked.call_count, 1)

    def test_r240_oracle_does_not_call_target_generation(self):
        """Target generation/execution is unavailable while freezing cases => the source interpreter independently produces fixed expectations."""
        p = self.program()
        with patch('workbench.target.emit_program', side_effect=AssertionError('target generation called')), patch('workbench.fixtures.prepare_generated', side_effect=AssertionError('target execution called')):
            suite = plan_cases(p)
        self.assertTrue(suite['cases'])
        self.assertEqual(suite['evidence_basis'], 'SOURCE_DERIVED_EXPECTED')
        self.assertTrue(all('input_status' in c['expected'] for c in suite['cases']))


if __name__ == '__main__':
    unittest.main()
