"""R601–R700: new bounded-source, evidence-isolation and campaign scenarios.

Each method has a distinct failure mode or behavioral assertion. Expected
records are manually stated; generated-campaign expectations are separate from
the parser IR. Neither establishes native mainframe parity.
"""
import ast
import copy
from decimal import Decimal
import unittest
from unittest.mock import patch

from workbench.domain import ValidationError, encode
from workbench.source import analyze_program, condition, normalized_lines
from workbench.target import emit_program, prepare_generated, check_generated, layout_nodes, rule_nodes
from workbench.reference import run_reference, input_errors
from workbench.fixtures import plan_cases, verify_program, adversarial_review, comparisons
from tools import scenario_campaign as campaign


LAYOUT = '''01 LEFT-RECORD.
05 A PIC 9(3).
05 S PIC X(3).
05 OUT PIC X(3).
01 RIGHT-RECORD.
05 B PIC 9(3).
05 T PIC X(3).
'''
BODY = '''IF A = B AND S = T
MOVE "YES" TO OUT
ELSE
MOVE "NO" TO OUT
END-IF.
'''
ROW = {'A': 18, 'B': 18, 'S': 'A  ', 'T': 'A  ', 'OUT': '   '}


def source(body=BODY, layout=LAYOUT):
    return ('IDENTIFICATION DIVISION.\nPROGRAM-ID. NEWSEM.\nDATA DIVISION.\n'
            'LINKAGE SECTION.\n' + layout +
            'PROCEDURE DIVISION USING LEFT-RECORD RIGHT-RECORD.\n' + body + 'GOBACK.\n')


class ExpandedSemantics(unittest.TestCase):
    def program(self, text=None, files=None):
        p = analyze_program('NEWSEM.cbl', source() if text is None else text, files or {})
        p['target_contract_version'] = 2
        return p

    def blocked(self, text, files=None):
        p = self.program(text, files)
        self.assertTrue(p['blockers'], 'Unsupported semantics received an executable target')
        self.assertEqual([c['original'] for c in p['coverage']], text.splitlines())
        self.assertTrue(all(c['disposition'] != 'unaccounted' for c in p['coverage']))
        with self.assertRaises(ValidationError): emit_program(p)
        return p

    def execution(self, text, row, expected, branches):
        p = self.program(text)
        self.assertFalse(p['blockers'], p['blockers'])
        before = copy.deepcopy(row)
        reference = run_reference(p, row)
        target = prepare_generated(emit_program(p))(row)
        self.assertEqual(target, reference)
        self.assertEqual(target['record'], expected)
        self.assertEqual([t['branch'] for t in target['trace']], branches)
        self.assertEqual(target['return_code'], 0)
        self.assertEqual(row, before)
        return p

    def reject(self, row):
        p = self.program()
        expected = run_reference(p, row)
        actual = prepare_generated(emit_program(p))(row)
        self.assertEqual(actual, expected)
        self.assertEqual(actual['input_status'], 'REJECT_INPUT')
        self.assertNotIn('record', actual)
        self.assertNotIn('trace', actual)
        self.assertIsNone(actual['return_code'])
        return actual

    def test_r601_condition_name_level88_is_not_elementary_storage(self):
        """A level-88 condition name follows A => block condition-name semantics rather than manufacture a field."""
        p = self.blocked(source(layout=LAYOUT.replace('05 A PIC 9(3).', '05 A PIC 9(3).\n88 ADULT VALUE 18 THRU 999.')))
        self.assertNotIn('ADULT', p['fields'])

    def test_r602_renames_level66_requires_alias_range(self):
        """A level-66 RENAMES range spans elementary items => reject storage aliasing absent an adapter."""
        self.blocked(source(layout=LAYOUT + '66 COMBINED RENAMES B THRU T.\n'))

    def test_r603_nested_group_requires_flattening_contract(self):
        """A level-02 group wraps a level-05 item => retain an unsupported hierarchy instead of inventing flat ownership."""
        self.blocked(source(layout=LAYOUT.replace('05 A PIC', '02 SUBGROUP.\n05 A PIC')))

    def test_r604_elementary_level01_is_not_record_group(self):
        """A level-01 PICTURE replaces the first group => reject elementary USING arguments outside the flat-group profile."""
        self.blocked(source(layout=LAYOUT.replace('01 LEFT-RECORD.', '01 LEFT-RECORD PIC X(9).')))

    def test_r605_national_character_layout_stays_blocked(self):
        """PIC N replaces a character field => reject unmodeled national character representation."""
        self.blocked(source(layout=LAYOUT.replace('S PIC X(3)', 'S PIC N(3)')))

    def test_r606_implied_decimal_requires_scale(self):
        """PIC 9(2)V9 declares an implied decimal scale => reject coercion to an unsigned integer field."""
        self.blocked(source(layout=LAYOUT.replace('A PIC 9(3)', 'A PIC 9(2)V9')))

    def test_r607_binary_usage_requires_native_layout(self):
        """An elementary field requests USAGE BINARY => require a byte representation adapter."""
        self.blocked(source(layout=LAYOUT.replace('A PIC 9(3).', 'A PIC 9(3) USAGE BINARY.')))

    def test_r608_justified_right_is_not_ordinary_padding(self):
        """A character receiving field is JUSTIFIED RIGHT => block unsupported MOVE alignment."""
        self.blocked(source(layout=LAYOUT.replace('OUT PIC X(3).', 'OUT PIC X(3) JUSTIFIED RIGHT.')))

    def test_r609_synchronized_storage_is_not_ignored(self):
        """A numeric field has SYNCHRONIZED alignment => keep layout semantics visible and unsupported."""
        self.blocked(source(layout=LAYOUT.replace('B PIC 9(3).', 'B PIC 9(3) SYNCHRONIZED.')))

    def test_r610_sign_clause_requires_encoding(self):
        """A numeric field adds a separate trailing sign => reject missing sign-position representation."""
        self.blocked(source(layout=LAYOUT.replace('B PIC 9(3).', 'B PIC 9(3) SIGN TRAILING SEPARATE.')))

    def test_r611_blank_when_zero_is_not_numeric_identity(self):
        """A numeric declaration requests BLANK WHEN ZERO => block formatting semantics absent from JSON integers."""
        self.blocked(source(layout=LAYOUT.replace('A PIC 9(3).', 'A PIC 9(3) BLANK WHEN ZERO.')))

    def test_r612_value_all_requires_repetition_semantics(self):
        """A character VALUE ALL literal initializes repeated text => reject unsupported repetition syntax."""
        self.blocked(source(layout=LAYOUT.replace('S PIC X(3).', 'S PIC X(3) VALUE ALL "A".')))

    def test_r613_group_move_is_not_literal_assignment(self):
        """MOVE names a source record group => block group byte-transfer semantics instead of inventing a literal."""
        self.blocked(source(BODY.replace('MOVE "YES" TO OUT', 'MOVE RIGHT-RECORD TO LEFT-RECORD')))

    def test_r614_reference_modification_is_not_whole_field_move(self):
        """MOVE targets OUT(2:1) => reject unsupported partial-field assignment."""
        self.blocked(source(BODY.replace('MOVE "YES" TO OUT', 'MOVE "Y" TO OUT(2:1)')))

    def test_r615_qualified_operand_needs_name_resolution(self):
        """A condition uses A OF LEFT-RECORD => block qualified-name parsing rather than drop the qualifier."""
        self.blocked(source(BODY.replace('A = B', 'A OF LEFT-RECORD = B')))

    def test_r616_abbreviated_relation_does_not_invent_operand(self):
        """A condition abbreviates A = 18 OR 19 => reject implicit operand expansion."""
        self.blocked(source(BODY.replace('A = B AND S = T', 'A = 18 OR 19')))

    def test_r617_not_condition_requires_explicit_grammar(self):
        """A predicate prefixes NOT to a comparison => reject unavailable unary condition grammar."""
        self.blocked(source(BODY.replace('A = B AND S = T', 'NOT A = B')))

    def test_r618_parenthesized_predicate_does_not_strip_grouping(self):
        """Parentheses change a mixed AND/OR predicate => block unsupported explicit grouping."""
        self.blocked(source(BODY.replace('A = B AND S = T', '(A = B OR A = 0) AND S = T')))

    def test_r619_evaluate_dispatch_stays_unsupported(self):
        """EVALUATE TRUE dispatches alternatives => retain the control-flow blocker instead of extracting an IF approximation."""
        self.blocked(source('EVALUATE TRUE\nWHEN A = B\nMOVE "YES" TO OUT\nEND-EVALUATE.\n'))

    def test_r620_copy_replacing_cannot_reuse_unmodified_layout(self):
        """COPY REPLACING requests a renamed field => block preprocessor transformation instead of resolving the raw book."""
        self.blocked(source(layout=LAYOUT.replace('05 A PIC 9(3).', 'COPY NUMBOOK REPLACING OLD-A BY A.')), {'NUMBOOK.cpy': '05 OLD-A PIC 9(3).\n'})

    def test_r621_cross_group_inequality_preserves_other_group(self):
        """Cross-group numeric inequality fires with unrelated character mismatch => update only OUT and preserve both groups."""
        row = {**ROW, 'A': 19, 'T': 'Z  '}
        self.execution(source(BODY.replace('A = B AND S = T', 'A <> B')), row, {**row, 'OUT': 'YES'}, [True])

    def test_r622_literal_left_numeric_direction(self):
        """A numeric literal is left of a strict less-than comparison => preserve direction on the equality boundary and above it."""
        text = source(BODY.replace('A = B AND S = T', '18 < A'))
        self.execution(text, ROW, {**ROW, 'OUT': 'NO '}, [False])
        row = {**ROW, 'A': 19}
        self.execution(text, row, {**row, 'OUT': 'YES'}, [True])

    def test_r623_negative_threshold_remains_comparison_only(self):
        """Unsigned A is compared above negative one => accept zero while preserving the nonnegative input domain."""
        row = {**ROW, 'A': 0}
        self.execution(source(BODY.replace('A = B AND S = T', 'A > -1')), row, {**row, 'OUT': 'YES'}, [True])

    def test_r624_zero_figurative_literal_numeric_branch(self):
        """ZEROES is used as a comparison and numeric MOVE => decode both as zero without converting caller fields."""
        text = source('IF A = ZEROES\nMOVE ZEROS TO B\nEND-IF.\n')
        row = {**ROW, 'A': 0}
        self.execution(text, row, {**row, 'B': 0}, [True])

    def test_r625_spaces_figurative_move_fills_width(self):
        """A blank text comparison leads to MOVE SPACES => fill all three receiving positions."""
        text = source('IF S = SPACE\nMOVE SPACES TO OUT\nEND-IF.\n')
        row = {**ROW, 'S': '   ', 'OUT': 'OLD'}
        self.execution(text, row, {**row, 'OUT': '   '}, [True])

    def test_r626_literal_only_unequal_width_padding(self):
        """Two literal-only strings differ only by trailing blanks => pad to the longer width before equality."""
        text = source(BODY.replace('A = B AND S = T', '"A" = "A  "'))
        self.execution(text, ROW, {**ROW, 'OUT': 'YES'}, [True])

    def test_r627_numeric_looking_text_keeps_leading_zeroes(self):
        """One condition mixes numeric-looking text and a leading-zero numeric token => compare typed values separately and preserve receiving text zeroes."""
        text = source('IF S = "018" AND A = 018\nMOVE "007" TO OUT\nELSE\nMOVE "BAD" TO OUT\nEND-IF.\n')
        row = {**ROW, 'S': '018'}
        self.execution(text, row, {**row, 'OUT': '007'}, [True])
        row = {**ROW, 'S': '18 '}
        self.execution(text, row, {**row, 'OUT': 'BAD'}, [False])

    def test_r628_trailing_blank_literal_is_significant(self):
        """Two three-character literals differ by leading versus trailing blank => retain exact character positions."""
        text = source(BODY.replace('A = B AND S = T', 'S = " A "'))
        self.execution(text, ROW, {**ROW, 'OUT': 'NO '}, [False])

    def test_r629_longest_supported_character_effect(self):
        """A 256-character receiving field gets a 256-character literal => preserve its final position without truncation."""
        literal = 'A' * 255 + 'Z'
        text = source('IF A = B\nMOVE "' + literal + '" TO OUT\nEND-IF.\n', LAYOUT.replace('OUT PIC X(3)', 'OUT PIC X(256)'))
        row = {**ROW, 'OUT': ' ' * 256}
        self.execution(text, row, {**row, 'OUT': literal}, [True])

    def test_r630_assignment_changes_later_cross_group_join(self):
        """The first rule changes the right-group key and the second joins keys => the join observes the new key."""
        text = source('IF A = 18\nMOVE 19 TO B\nEND-IF.\n' + BODY)
        self.execution(text, ROW, {**ROW, 'B': 19, 'OUT': 'NO '}, [True, False])

    def test_r631_false_arm_write_controls_later_rule(self):
        """An ELSE changes text before another IF => downstream comparison sees the false-arm effect."""
        text = source('IF A = 0\nCONTINUE\nELSE\nMOVE "Z" TO S\nEND-IF.\nIF S = "Z"\nMOVE "YES" TO OUT\nEND-IF.\n')
        self.execution(text, ROW, {**ROW, 'S': 'Z  ', 'OUT': 'YES'}, [False, True])

    def test_r632_earlier_predicate_not_retroactively_recomputed(self):
        """A true arm changes its own comparison operand => retain the original true trace and new output value."""
        text = source('IF A = B\nMOVE 0 TO A\nELSE\nMOVE 999 TO A\nEND-IF.\n')
        self.execution(text, ROW, {**ROW, 'A': 0}, [True])

    def test_r633_three_rule_feedback_has_ordered_trace(self):
        """Three sequential rules feed numeric and string state into each other => retain all three ordered decisions."""
        text = source('IF A = B\nMOVE "YES" TO OUT\nEND-IF.\nIF OUT = "YES"\nMOVE 0 TO B\nEND-IF.\nIF A = B\nMOVE "BAD" TO OUT\nELSE\nMOVE "END" TO OUT\nEND-IF.\n')
        self.execution(text, ROW, {**ROW, 'B': 0, 'OUT': 'END'}, [True, True, False])

    def test_r634_mixed_boolean_precedence_false_control(self):
        """The right conjunction fails while the left OR relation also fails => a true middle atom cannot make the expression true."""
        text = source(BODY.replace('A = B AND S = T', 'A = 0 OR B = 18 AND S <> T'))
        self.execution(text, ROW, {**ROW, 'OUT': 'NO '}, [False])

    def test_r635_two_or_terms_share_no_accidental_conjunction(self):
        """The first AND term fails and the last OR term succeeds => preserve OR grouping across both conjunctions."""
        text = source(BODY.replace('A = B AND S = T', 'A = 0 AND B = 0 OR S <> T AND A = 18 OR B = 18'))
        self.execution(text, ROW, {**ROW, 'OUT': 'YES'}, [True])

    def test_r636_using_group_order_does_not_rename_json_fields(self):
        """PROCEDURE USING lists the two groups in reverse declaration order => preserve named flat transport and group provenance."""
        text = source().replace('USING LEFT-RECORD RIGHT-RECORD', 'USING RIGHT-RECORD LEFT-RECORD')
        p = self.execution(text, ROW, {**ROW, 'OUT': 'YES'}, [True])
        self.assertEqual(p['fields']['A']['group'], 'LEFT-RECORD')
        self.assertEqual(p['fields']['B']['group'], 'RIGHT-RECORD')

    def test_r637_two_copybooks_keep_distinct_group_origins(self):
        """Two included books each own an 01 group => retain each elementary field's book and caller group."""
        left, right = LAYOUT.split('01 RIGHT-RECORD.')
        text = source(layout='COPY LEFTBOOK.\nCOPY RIGHTBOOK.\n')
        p = self.program(text, {'LEFTBOOK.cpy': left, 'RIGHTBOOK.cpy': '01 RIGHT-RECORD.' + right})
        self.assertFalse(p['blockers'])
        self.assertEqual(p['fields']['A']['source_ref'], 'LEFTBOOK.cpy:2')
        self.assertEqual(p['fields']['T']['source_ref'], 'RIGHTBOOK.cpy:3')
        self.assertEqual(prepare_generated(emit_program(p))(ROW)['record']['OUT'], 'YES')

    def test_r638_blank_and_inline_comment_lines_keep_physical_rule_span(self):
        """A blank and a comment interrupt a rule body => retain physical start/end references and original comment dispositions."""
        text = source(BODY.replace('MOVE "YES"', '\n*> arm explanation\nMOVE "YES"'))
        p = self.execution(text, ROW, {**ROW, 'OUT': 'YES'}, [True])
        rule = p['rules'][0]
        self.assertEqual(rule['source_end'] - rule['source_start'], 6)
        self.assertEqual(next(c for c in p['coverage'] if c['original'] == '*> arm explanation')['disposition'], 'comment')

    def test_r639_crlf_and_final_no_newline_preserve_line_accounting(self):
        """The export uses CRLF and no final newline => preserve source hashing and the exact physical line count."""
        text = source().rstrip('\n').replace('\n', '\r\n')
        p = self.execution(text, ROW, {**ROW, 'OUT': 'YES'}, [True])
        self.assertEqual(p['loc']['physical'], len(text.splitlines()))
        self.assertEqual([r['original'] for r in p['coverage']], text.splitlines())

    def test_r640_fixed_comments_do_not_become_executable_cards(self):
        """Fixed-format asterisk and slash cards contain fake MOVE text => account both as comments and execute only the real rule."""
        text = source().replace('IF A = B', '000010*MOVE "BAD" TO OUT\n000020/MOVE "BAD" TO OUT\nIF A = B')
        p = self.execution(text, ROW, {**ROW, 'OUT': 'YES'}, [True])
        self.assertEqual(p['loc']['comment'], 2)

    def test_r641_reference_trace_provenance_does_not_alias_program(self):
        """A caller edits a returned reference trace source-ref list => frozen program provenance remains unchanged."""
        p = self.program(); before = copy.deepcopy(p)
        result = run_reference(p, ROW)
        result['trace'][0]['source_refs'].append('FORGED:1')
        self.assertEqual(p, before)

    def test_r642_reference_results_have_independent_provenance_lists(self):
        """Two reference executions return trace provenance => editing one result cannot rewrite the other result."""
        p = self.program(); first = run_reference(p, ROW); second = run_reference(p, ROW)
        expected = copy.deepcopy(second)
        first['trace'][0]['source_refs'].clear()
        self.assertEqual(second, expected)

    def test_r643_fixture_expected_provenance_is_independent_per_case(self):
        """Two fixture cases share a rule source span => editing one expected trace cannot modify the other case."""
        suite = plan_cases(self.program())
        accepted = [c for c in suite['cases'] if not c['intentional_invalid']]
        self.assertGreaterEqual(len(accepted), 2)
        before = copy.deepcopy(accepted[1])
        accepted[0]['expected']['trace'][0]['source_refs'].append('FORGED:2')
        self.assertEqual(accepted[1], before)

    def test_r644_fixture_expected_provenance_cannot_edit_source_ir(self):
        """A frozen suite trace source-ref is edited => the original source IR retains its independent evidence."""
        p = self.program(); before = copy.deepcopy(p); suite = plan_cases(p)
        accepted = next(c for c in suite['cases'] if not c['intentional_invalid'])
        accepted['expected']['trace'][0]['source_refs'][0] = 'FORGED:3'
        self.assertEqual(p, before)

    def test_r645_decimal_integer_lookalike_is_rejected(self):
        """A Decimal exactly equal to 18 enters the exported target => reject the non-integer Python type directly."""
        self.reject({**ROW, 'A': Decimal(18)})

    def test_r646_integer_subclass_cannot_override_comparison(self):
        """An int subclass defines a comparison hook => reject it without invoking that caller hook."""
        class HookInt(int):
            def __lt__(self, other): raise AssertionError('Caller comparison executed')
            def __ge__(self, other): raise AssertionError('Caller comparison executed')
        self.reject({**ROW, 'A': HookInt(18)})

    def test_r647_string_subclass_cannot_override_length(self):
        """A str subclass raises from length => strict type guards reject it before its method executes."""
        class HookStr(str):
            def __len__(self): raise AssertionError('Caller length executed')
        self.reject({**ROW, 'S': HookStr('A  ')})

    def test_r648_multifield_errors_have_stable_alphabetic_order(self):
        """Several fields fail shape, numeric and text guards simultaneously => report every error in deterministic field order."""
        result = self.reject({'A': -1, 'B': True, 'OUT': '', 'S': None, 'EXTRA': 1})
        self.assertEqual(result['errors'], ['field set differs from source layout', 'A: invalid unsigned integer',
                         'B: invalid unsigned integer', 'OUT: invalid fixed-width string',
                         'S: invalid fixed-width string', 'T: invalid fixed-width string'])

    def test_r649_nested_record_transport_is_not_silently_flattened(self):
        """Caller supplies group-nested dictionaries instead of flat fields => reject transport shape and retain the caller object."""
        row = {'LEFT-RECORD': {k:v for k,v in ROW.items() if k in ('A','S','OUT')},
               'RIGHT-RECORD': {'B':18,'T':'A  '}}
        before = copy.deepcopy(row); self.reject(row); self.assertEqual(row, before)

    def test_r650_bytes_with_exact_length_is_not_character_input(self):
        """A three-byte value matches PIC X width numerically => reject bytes until an explicit character encoding adapter exists."""
        self.reject({**ROW, 'S': b'A  '})

    def test_r651_output_guard_rejects_malformed_field_even_when_overwritten(self):
        """OUT has a wrong width but the first branch would overwrite it => enforce the entire caller layout before execution."""
        self.reject({**ROW, 'OUT': 'will be overwritten'})

    def test_r652_unicode_json_width_is_explicit_codepoint_contract(self):
        """Three Unicode codepoints enter PIC X(3) JSON transport => preserve codepoints under the documented non-EBCDIC profile."""
        row = {**ROW, 'S': 'éΩ中', 'T': 'éΩ中'}
        self.execution(source(), row, {**row, 'OUT':'YES'}, [True])

    def test_r653_fractional_nan_cannot_satisfy_numeric_guard(self):
        """A NaN float enters an unsigned field => reject by exact type before comparisons can hide the invalid value."""
        result = self.reject({**ROW, 'A': float('nan')})
        self.assertEqual(result['errors'], ['A: invalid unsigned integer'])

    def test_r654_huge_integer_rejects_without_string_conversion(self):
        """An integer with 5001 decimal digits reaches the generated guard => return a range rejection without serialization overflow."""
        self.reject({**ROW, 'A': 10 ** 5000})

    def test_r655_rejected_result_error_list_is_fresh(self):
        """A caller clears one exported rejection's errors => a later identical rejection returns the full independent error list."""
        execute = prepare_generated(emit_program(self.program()))
        bad = {**ROW, 'A': -1}
        first = execute(bad); first['errors'].clear()
        self.assertEqual(execute(bad)['errors'], ['A: invalid unsigned integer'])

    def test_r656_fixture_input_record_tamper_is_not_expected_tamper(self):
        """A frozen case input changes while its expected output stays fixed => verification rejects the deterministic contract before target execution."""
        p = self.program(); suite = plan_cases(p); suite['cases'][0]['record']['A'] = 777
        with patch('workbench.fixtures.prepare_generated') as compile_target:
            with self.assertRaises(ValidationError): verify_program(p, emit_program(p), suite)
        compile_target.assert_not_called()

    def test_r657_fixture_case_deletion_cannot_hide_a_boundary(self):
        """A frozen suite drops one case while retaining claimed coverage => regeneration detects the missing witness."""
        p = self.program(); suite = plan_cases(p); suite['cases'].pop()
        with self.assertRaises(ValidationError): verify_program(p, emit_program(p), suite)

    def test_r658_duplicate_fixture_case_cannot_inflate_matches(self):
        """An existing case is duplicated under a second ID => deterministic suite validation rejects inflated case counts."""
        p = self.program(); suite = plan_cases(p); extra = copy.deepcopy(suite['cases'][0]); extra['id'] = 'case_fake'; suite['cases'].append(extra)
        with self.assertRaises(ValidationError): verify_program(p, emit_program(p), suite)

    def test_r659_fixture_group_file_tamper_is_detected(self):
        """Only a fixture's grouped file projection is edited => reject inconsistent transport evidence even when flat input is unchanged."""
        p = self.program(); suite = plan_cases(p); suite['cases'][0]['files']['LEFT-RECORD'][0]['A'] = 777
        with self.assertRaises(ValidationError): verify_program(p, emit_program(p), suite)

    def test_r660_fixture_intentional_invalid_label_cannot_be_forged(self):
        """An invalid case is relabeled valid without changing its input => reject invented valid-execution accounting."""
        p = self.program(); suite = plan_cases(p); next(c for c in suite['cases'] if c['intentional_invalid'])['intentional_invalid'] = False
        with self.assertRaises(ValidationError): verify_program(p, emit_program(p), suite)

    def test_r661_fixture_reason_is_part_of_frozen_evidence(self):
        """A boundary witness's stated reason is edited after freezing => reject changed evidence metadata."""
        p = self.program(); suite = plan_cases(p); suite['cases'][0]['reason'] = 'Human approval was never supplied'
        with self.assertRaises(ValidationError): verify_program(p, emit_program(p), suite)

    def test_r662_fixture_rule_witness_id_cannot_reference_missing_case(self):
        """A branch coverage witness points to a nonexistent case => reject forged rule-to-test linkage."""
        p = self.program(); suite = plan_cases(p); suite['coverage']['rules']['NEWSEM_R001']['true'].append('missing_case')
        with self.assertRaises(ValidationError): verify_program(p, emit_program(p), suite)

    def test_r663_fixture_program_identity_is_pinned(self):
        """A suite is renamed to a different program while retaining the source hash => reject identity tampering."""
        p = self.program(); suite = plan_cases(p); suite['program'] = 'OTHER'
        with self.assertRaises(ValidationError): verify_program(p, emit_program(p), suite)

    def test_r664_fixture_trace_order_is_frozen(self):
        """Two expected trace entries are reversed without changing final output => reject altered execution order evidence."""
        p = self.program(source(BODY + 'IF A = 0\nCONTINUE\nEND-IF.\n')); suite = plan_cases(p)
        next(c for c in suite['cases'] if not c['intentional_invalid'])['expected']['trace'].reverse()
        with self.assertRaises(ValidationError): verify_program(p, emit_program(p), suite)

    def test_r665_required_invalid_candidates_survive_interaction_pressure(self):
        """Many numeric boundary interactions compete for the 256-case budget => every included layout-negative record remains explicitly invalid."""
        p = self.program(source(BODY.replace('A = B AND S = T', 'A > 18 AND B < 40 OR S = "A" AND T = "Z"')))
        suite = plan_cases(p)
        self.assertTrue(any(c['intentional_invalid'] for c in suite['cases']))
        self.assertTrue(all(c['intentional_invalid'] == bool(input_errors(p,c['record'])) for c in suite['cases']))
        self.assertLessEqual(len(suite['cases']),256)

    def test_r666_nonobject_fixture_has_no_invented_group_file(self):
        """Fixture planning creates a non-object input => retain empty group projections rather than invent caller records."""
        suite = plan_cases(self.program())
        cases = [c for c in suite['cases'] if not isinstance(c['record'],dict)]
        self.assertTrue(cases)
        self.assertTrue(all(c['files'] == {} and c['intentional_invalid'] for c in cases))

    def test_r667_terminal_only_program_has_guards_without_business_branches(self):
        """A valid LINKAGE program contains only its terminal statement => report zero business branches while executing and adversarially checking every input guard."""
        p = self.program(source('')); self.assertFalse(p['blockers'])
        suite = plan_cases(p); code = emit_program(p)
        self.assertEqual(suite['coverage']['rule_count'],0)
        self.assertEqual(suite['coverage']['branch_targets'],0)
        result = prepare_generated(code)(ROW)
        self.assertEqual(result['record'],ROW); self.assertEqual(result['trace'],[])
        self.assertEqual(prepare_generated(code)({**ROW,'A':True})['input_status'],'REJECT_INPUT')
        report = adversarial_review(p,code,suite)
        self.assertEqual(len(report['mutations']),len(p['fields'])+3)
        self.assertTrue(all(m['kind']=='input_contract' and m['detected'] for m in report['mutations']))
        self.assertTrue(report['passed'])

    def test_r668_identical_literals_in_separate_rules_keep_mutation_identity(self):
        """Two rules write identical literals and the second always overwrites the first => mark only earlier effects masked and attribute detected later effects to the second rule."""
        body = ('IF S = "A"\nMOVE "YES" TO OUT\nELSE\nMOVE "NO" TO OUT\nEND-IF.\n'
                'IF T = "A"\nMOVE "YES" TO OUT\nELSE\nMOVE "NO" TO OUT\nEND-IF.\n')
        p = self.program(source(body)); report = adversarial_review(p,emit_program(p),plan_cases(p))
        effects = [m for m in report['mutations'] if m['kind']=='effect']
        earlier = [m for m in effects if m['rule_id']=='NEWSEM_R001']
        later = [m for m in effects if m['rule_id']=='NEWSEM_R002']
        self.assertEqual(len(earlier),2); self.assertEqual(len(later),2)
        self.assertTrue(all(not m['detected'] and not m['witnesses'] for m in earlier))
        self.assertTrue(all(m['detected'] and m['witnesses'] for m in later))
        self.assertFalse(report['passed'])

    def test_r669_prior_write_can_make_later_branch_unreachable(self):
        """An unconditional true relation forces A before a later decision => fixture coverage retains the unreachable later false branch."""
        p = self.program(source('IF 1 = 1\nMOVE 18 TO A\nEND-IF.\nIF A = 18\nCONTINUE\nELSE\nMOVE "NO" TO OUT\nEND-IF.\n'))
        suite = plan_cases(p)
        self.assertTrue(any(g['rule_id']=='NEWSEM_R002' and g['branch']=='false' for g in suite['coverage']['gaps']))

    def test_r670_compound_atoms_each_receive_boundary_mutation(self):
        """A four-atom mixed boolean predicate is mutated => record one comparison mutation per atomic relation."""
        p = self.program(source(BODY.replace('A = B AND S = T','A > 18 AND B <= 20 OR S = "A" AND T <> "Z"')))
        report = adversarial_review(p,emit_program(p),plan_cases(p))
        self.assertEqual(len([m for m in report['mutations'] if m['kind']=='comparison']),4)

    def test_r671_false_arm_multiassign_effects_are_separately_reviewed(self):
        """An ELSE writes two different fields => retain two independently named false-arm assignment mutations."""
        p = self.program(source(BODY.replace('MOVE "NO" TO OUT','MOVE "NO" TO OUT\nMOVE 0 TO A')))
        report = adversarial_review(p,emit_program(p),plan_cases(p))
        effects = [m for m in report['mutations'] if m['kind']=='effect' and m['mutation'].startswith('else')]
        self.assertEqual(len(effects),2)
        self.assertTrue(any('OUT' in m['mutation'] for m in effects))
        self.assertTrue(any('A' in m['mutation'] for m in effects))

    def test_r672_empty_effect_arms_still_have_decision_mutation(self):
        """Both IF arms CONTINUE => branch reversal remains observable through trace even with identical record outputs."""
        p = self.program(source('IF A = B\nCONTINUE\nELSE\nCONTINUE\nEND-IF.\n'))
        report = adversarial_review(p,emit_program(p),plan_cases(p))
        self.assertTrue(next(m for m in report['mutations'] if m['kind']=='predicate')['detected'])
        self.assertFalse(any(m['kind']=='effect' for m in report['mutations']))

    def test_r673_mutation_checkpoint_can_abort_before_first_candidate(self):
        """A cancellation checkpoint raises before mutation execution => propagate the cancellation and issue no review receipt."""
        p = self.program()
        def cancelled(): raise InterruptedError('Cancelled synthetic review')
        with self.assertRaises(InterruptedError): adversarial_review(p,emit_program(p),plan_cases(p),checkpoint=cancelled)

    def test_r674_target_trace_only_difference_is_mismatch(self):
        """Generated output fields remain correct but a rule trace ID changes => verification records a mismatch."""
        p = self.program(); code = emit_program(p).replace("'NEWSEM_R001'", "'FORGED_RULE'")
        result = verify_program(p,code,plan_cases(p))
        self.assertEqual(result['status'],'MISMATCH')
        self.assertTrue(result['differences'])

    def test_r675_target_return_code_only_difference_is_mismatch(self):
        """Generated output and trace match while return code is one => verification retains the return-code discrepancy."""
        p = self.program(); code = emit_program(p).replace("'return_code': 0", "'return_code': 1")
        result = verify_program(p,code,plan_cases(p))
        self.assertEqual(result['status'],'MISMATCH')
        self.assertTrue(all(d['actual']['return_code']==1 for d in result['differences']))

    def test_r676_generated_default_argument_cannot_execute_at_definition(self):
        """The target adds an eager default argument expression => reject before compiling the function."""
        code = 'def run_program(record=dict({})):\n    return record\n'
        with self.assertRaises(ValidationError): check_generated(code)

    def test_r677_generated_decorator_cannot_execute_at_definition(self):
        """The target adds a function decorator => reject eager definition-time execution."""
        with self.assertRaises(ValidationError): check_generated('@dict\ndef run_program(record):\n    return record\n')

    def test_r678_generated_keyword_only_argument_is_outside_entrypoint(self):
        """The target changes its entrypoint to a keyword-only record => reject incompatibility with the one-positional-record contract."""
        with self.assertRaises(ValidationError): check_generated('def run_program(*, record):\n    return record\n')

    def test_r679_generated_variadic_argument_cannot_expand_contract(self):
        """The target adds variadic positional arguments => reject broadened callable capability."""
        with self.assertRaises(ValidationError): check_generated('def run_program(record, *row):\n    return record\n')

    def test_r680_generated_lambda_is_not_a_literal_effect(self):
        """A target row assignment stores a lambda => reject executable values in the constrained generator."""
        with self.assertRaises(ValidationError): check_generated('def run_program(record):\n    row = dict(record)\n    row["A"] = lambda: 1\n    return row\n')

    def test_r681_generated_while_loop_has_no_execution_budget(self):
        """A target introduces a while loop => reject unsupported potentially unbounded control flow."""
        with self.assertRaises(ValidationError): check_generated('def run_program(record):\n    while True:\n        record\n    return record\n')

    def test_r682_generated_try_cannot_swallow_input_rejection(self):
        """A target wraps record operations in try/except => reject unmodeled exception control flow."""
        with self.assertRaises(ValidationError): check_generated('def run_program(record):\n    try:\n        return record\n    except:\n        return {}\n')

    def test_r683_generated_dynamic_row_key_is_not_literal_destination(self):
        """A target obtains an assignment key from caller data => reject dynamic destinations outside source field literals."""
        with self.assertRaises(ValidationError): check_generated('def run_program(record):\n    row = dict(record)\n    row[record.get("S")] = 1\n    return row\n')

    def test_r684_generated_chained_assignment_cannot_alias_record(self):
        """A target chains row and trace assignment => reject multi-target assignments before aliasing occurs."""
        with self.assertRaises(ValidationError): check_generated('def run_program(record):\n    row = trace = dict(record)\n    return row\n')

    def test_r685_generated_trace_must_start_empty(self):
        """A target initializes trace with invented content => reject a nonempty synthetic trace seed."""
        with self.assertRaises(ValidationError): check_generated('def run_program(record):\n    trace = [record]\n    return trace\n')

    def test_r686_generated_error_list_cannot_alias_caller_field(self):
        """A target initializes errors from caller data => reject shared mutable error state."""
        with self.assertRaises(ValidationError): check_generated('def run_program(record):\n    errors = record.get("errors")\n    return errors\n')

    def test_r687_generated_append_keyword_arguments_are_rejected(self):
        """A target calls trace.append using a keyword => enforce the exact approved positional call shape."""
        with self.assertRaises(ValidationError): check_generated('def run_program(record):\n    trace = []\n    trace.append(value=record)\n    return trace\n')

    def test_r688_generated_named_expression_cannot_assign_hidden_state(self):
        """A walrus expression assigns state inside a condition => reject hidden assignment syntax."""
        with self.assertRaises(ValidationError): check_generated('def run_program(record):\n    if (row := record):\n        return row\n    return record\n')

    def test_r689_generated_size_bound_precedes_ast_parse(self):
        """Generated target text exceeds 512000 characters => reject before AST parsing consumes the oversized input."""
        with patch('workbench.target.ast.parse') as parse:
            with self.assertRaises(ValidationError): check_generated('#' * 512001)
        parse.assert_not_called()

    def test_r690_layout_guard_slicing_excludes_all_business_rules(self):
        """A five-field v2 target has three business IF statements => expose exactly eight layout guards and three rule nodes."""
        p = self.program(source(BODY + 'IF A = 0\nCONTINUE\nEND-IF.\nIF B = 0\nCONTINUE\nEND-IF.\n'))
        tree = ast.parse(emit_program(p))
        self.assertEqual(len(layout_nodes(tree,p)),8)
        self.assertEqual(len(rule_nodes(tree,p)),3)
        self.assertEqual(len(comparisons(p['rules'][0]['predicate'])),2)

    def test_r691_campaign_independent_oracle_detects_reference_corruption(self):
        """Sixty reference results are corrupted => count all divergences while bounding retained detail to fifty replay records."""
        with patch.object(campaign,'run_reference',return_value={'input_status':'CORRUPTED'}):
            result = campaign.campaign(limit=60)
        self.assertFalse(result['passed']); self.assertEqual(result['divergence_count'],60)
        self.assertEqual(len(result['divergences']),50)

    def test_r692_campaign_independent_oracle_detects_target_corruption(self):
        """Only the prepared target returns an incorrect status => the campaign reports a target divergence."""
        with patch.object(campaign,'prepare_generated',return_value=lambda row:{'input_status':'CORRUPTED'}):
            result = campaign.campaign(limit=1)
        self.assertFalse(result['passed']); self.assertEqual(result['divergence_count'],1)

    def test_r693_campaign_agreeing_wrong_engines_do_not_pass(self):
        """Target and reference agree on the same wrong result => the independent family oracle still fails the scenario."""
        bad = {'input_status':'CORRUPTED'}
        with patch.object(campaign,'prepare_generated',return_value=lambda row:bad), patch.object(campaign,'run_reference',return_value=bad):
            result = campaign.campaign(limit=1)
        self.assertFalse(result['passed']); self.assertEqual(result['divergence_count'],1)

    def test_r694_campaign_duplicate_tuple_cannot_inflate_count(self):
        """A campaign generator repeats the same source/input tuple => duplicate execution is explicit and invalidates the receipt."""
        row = next(campaign.program_records(campaign.specification(0)))[1]
        with patch.object(campaign,'program_records',return_value=iter([(0,row,'repeated',0),(1,row,'repeated',0)])):
            result = campaign.campaign(limit=2)
        self.assertFalse(result['passed']); self.assertEqual(result['unique_scenarios'],1)
        self.assertEqual(result['duplicate_executions'],1)

    def test_r695_campaign_source_change_invalidates_receipt(self):
        """Implementation fingerprint changes while the campaign runs => retain successful comparisons but refuse a passing receipt."""
        with patch.object(campaign,'implementation_fingerprint',side_effect=[{'sha256':'before'},{'sha256':'after'}]):
            result = campaign.campaign(limit=1)
        self.assertFalse(result['passed']); self.assertFalse(result['source_unchanged_during_campaign'])

    def test_r696_campaign_replay_reconstructs_copybook_and_feedback(self):
        """Replay selects a copybook-backed three-rule feedback source => regenerate its concrete record, independent expectation and matching engines."""
        result = campaign.replay(183,37)
        self.assertTrue(result['copybooks'])
        self.assertEqual(result['reference'],result['target'])
        self.assertEqual(campaign.projection(result['target']),result['independent_expected'])
        self.assertEqual(len(result['target']['trace']),3)

    def test_r697_campaign_program_inventory_has_real_layout_and_rule_variation(self):
        """All 200 generated source specifications are enumerated => retain ten semantic families, five numeric widths and concrete unique sources."""
        specs = [campaign.specification(i) for i in range(200)]
        sources = [campaign.source_program(p) for p in specs]
        self.assertEqual(len({campaign.digest({'source':s,'files':f}) for s,f in sources}),200)
        self.assertEqual({p['family'] for p in specs},set(campaign.FAMILIES))
        self.assertEqual({p['width'] for p in specs},{3,4,6,9,18})
        self.assertTrue(any(p['copybook'] for p in specs)); self.assertTrue(any(p['two_groups'] for p in specs))

    def test_r698_campaign_invalid_inputs_enter_compiled_function(self):
        """One thousand generated cases include 200 invalid records => execute every record through the one prepared target function."""
        original = campaign.prepare_generated; called = []
        def prepare(code):
            execute = original(code)
            def wrapped(row): called.append(row); return execute(row)
            return wrapped
        with patch.object(campaign,'prepare_generated',side_effect=prepare) as compiler:
            result = campaign.campaign(limit=1000)
        self.assertTrue(result['passed']); self.assertEqual(len(called),1000)
        self.assertEqual(result['invalid_inputs'],200); self.assertEqual(compiler.call_count,1)

    def test_r699_campaign_replay_bounds_cannot_select_negative_indices(self):
        """Replay indices are negative, fractional or outside the finite campaign => reject accidental Python negative indexing and invalid recipes."""
        for index in (-1,200,True,1.5):
            with self.subTest(program_index=index):
                with self.assertRaises(ValueError): campaign.specification(index)
        for index in (-1,1000,True,1.5):
            with self.subTest(case_index=index):
                with self.assertRaises(ValueError): campaign.replay(0,index)

    def test_r700_campaign_seed_replay_pins_sequence_and_changes_samples(self):
        """The campaign repeats the same seed then changes it => preserve the exact scenario hash sequence only for the original seed."""
        first = campaign.campaign(seed=23,limit=1000)
        repeated = campaign.campaign(seed=23,limit=1000)
        changed = campaign.campaign(seed=24,limit=1000)
        self.assertEqual(first['scenario_sequence_sha256'],repeated['scenario_sequence_sha256'])
        self.assertNotEqual(first['scenario_sequence_sha256'],changed['scenario_sequence_sha256'])
        self.assertEqual(first['unique_scenarios'],1000)


if __name__ == '__main__':
    unittest.main()
