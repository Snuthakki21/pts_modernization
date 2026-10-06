"""Large technical-gap inventories keep one bounded, evidence-complete SME packet."""
import copy
from io import BytesIO
import json
from pathlib import Path
import tempfile
import unittest

from openpyxl import load_workbook

from workbench.domain import ValidationError, encode, sha
from workbench.intake import parse_manifest
from workbench.review import export_packet, packet_document, read_answers
from workbench.source import analyze_sources
from test_source import COBOL
from test_workflow import MANIFEST


def process_with_unsupported_lines(count=21509, version=2):
    process = parse_manifest(MANIFEST)
    if version is not None:
        process['sme_packet_version'] = version
    source = COBOL.replace('  GOBACK.', 'DISPLAY X\n' * count + '  GOBACK.')
    process['analysis'] = analyze_sources({'ELIGIBLE.cbl': source}, process)
    return process


def expand_spans(spans):
    return [number for first, last in spans for number in range(first, last + 1)]


class ReviewCompactionTests(unittest.TestCase):
    def test_21509_unsupported_lines_issue_one_technical_gap_without_losing_evidence(self):
        process = process_with_unsupported_lines()
        original = copy.deepcopy(process['analysis'])
        self.assertEqual(len(original['blockers']), 21509)
        packet = packet_document(process)
        self.assertEqual(packet['version'], 2)
        self.assertLessEqual(len(packet['items']), 2000)
        rules = [item for item in packet['items'] if item['kind'] == 'business_rule']
        self.assertEqual([item['id'] for item in rules], [rule['id'] for rule in original['rules']])
        self.assertEqual([item['question'] for item in rules], [rule['plain'] for rule in original['rules']])
        gaps = [item for item in packet['items'] if item['kind'] == 'technical_gap']
        self.assertEqual(len(gaps), 1)
        self.assertIn('semantic adapter', gaps[0]['question'])
        self.assertIn('unsupported', gaps[0]['question'])
        context = json.loads(packet['context'])
        analysis_ref = context['source_analysis']
        self.assertEqual(analysis_ref['path'], 'analysis/source-analysis.json')
        self.assertEqual(analysis_ref['sha256'], sha(encode(original)))
        self.assertEqual(analysis_ref['raw_blocker_count'], 21509)
        group = context['technical_gaps'][gaps[0]['id']]
        self.assertEqual(group['program'], 'ELIGIBLE')
        self.assertEqual(group['kind'], 'unsupported_source')
        indices = expand_spans(group['blocker_index_spans'])
        self.assertEqual(indices, list(range(21509)))
        self.assertEqual(group['blockers_sha256'], sha(encode([original['blockers'][i] for i in indices])))
        expected_lines = sorted({line for blocker in original['blockers'] for line in blocker['lines']})
        self.assertEqual(expand_spans(group['source_line_spans']['ELIGIBLE.cbl']), expected_lines)
        program_ref = analysis_ref['programs']['ELIGIBLE']
        self.assertEqual(program_ref['source_sha256'], original['programs']['ELIGIBLE']['source_hash'])
        self.assertEqual(program_ref['coverage_sha256'], sha(encode(original['programs']['ELIGIBLE']['coverage'])))
        self.assertEqual(process['analysis'], original)
        blocked_lines = set(expected_lines)
        self.assertTrue(all(line['disposition'] == 'unsupported' for line in original['programs']['ELIGIBLE']['coverage'] if line['line'] in blocked_lines))

    def test_new_packet_compacts_by_program_and_gap_kind_while_preserving_other_human_items(self):
        process = process_with_unsupported_lines(2001)
        analysis = process['analysis']
        analysis['blockers'].extend([
            {'kind': 'unsupported_source', 'path': 'SECOND.cbl', 'lines': [17, 19], 'message': 'Different program needs an adapter'},
            {'kind': 'unsupported_jcl', 'path': 'job.jcl', 'message': 'Dataset allocation needs an I/O adapter'},
            {'kind': 'unresolved_condition', 'message': 'Ask the owner what this job condition means'},
        ])
        second = copy.deepcopy(analysis['programs']['ELIGIBLE'])
        second.update({'name': 'SECOND', 'path': 'SECOND.cbl'})
        analysis['programs']['SECOND'] = second
        process['llm'] = {'analysis': {'questions': ['Which business date should the process use?']}}
        packet = packet_document(process)
        groups = json.loads(packet['context'])['technical_gaps'].values()
        self.assertEqual({(group['program'], group['kind']) for group in groups}, {
            ('ELIGIBLE', 'unsupported_source'), ('SECOND', 'unsupported_source'), ('job.jcl', 'unsupported_jcl')})
        self.assertEqual(len([item for item in packet['items'] if item['kind'] == 'technical_gap']), 3)
        human_item = next(item for item in packet['items'] if item['kind'] == 'unresolved_item')
        self.assertEqual(human_item['id'], 'B_2003')
        self.assertIn('Ask the owner', human_item['question'])
        self.assertEqual(next(item for item in packet['items'] if item['kind'] == 'provider_suggestion')['id'], 'LLM_000')

    def test_business_rule_overflow_still_blocks_instead_of_truncating(self):
        process = process_with_unsupported_lines(2001)
        rule = process['analysis']['rules'][0]
        process['analysis']['rules'] = [dict(rule, id='ACTUAL_R%04d' % i) for i in range(2001)]
        with self.assertRaisesRegex(ValidationError, 'business rules'):
            packet_document(process)
        self.assertEqual(len(process['analysis']['rules']), 2001)

    def test_many_distinct_gap_groups_still_fail_the_actual_human_item_limit(self):
        process = process_with_unsupported_lines(0)
        process['analysis']['blockers'] = [
            {'kind': 'unsupported_source', 'path': 'member-%04d.cbl' % i, 'message': 'Distinct source adapter required'}
            for i in range(2001)]
        with self.assertRaisesRegex(ValidationError, 'SME packet exceeds supported size'):
            packet_document(process)
        self.assertEqual(len(process['analysis']['blockers']), 2001)

    def test_two_thousand_actual_human_items_are_retained_and_one_extra_blocks(self):
        process = process_with_unsupported_lines(2001)
        rule = process['analysis']['rules'][0]
        process['analysis']['rules'] = [dict(rule, id='ACTUAL_R%04d' % i) for i in range(1994)]
        packet = packet_document(process)
        self.assertEqual(len(packet['items']), 2000)
        self.assertEqual(len([item for item in packet['items'] if item['kind'] == 'business_rule']), 1994)
        process['analysis']['rules'].append(dict(rule, id='ONE_EXTRA_REAL_RULE'))
        with self.assertRaisesRegex(ValidationError, 'SME packet exceeds supported size'):
            packet_document(process)
        self.assertEqual(len(process['analysis']['rules']), 1995)

    def test_compacted_packet_replay_survives_canonical_persistence(self):
        from workbench.domain import decode
        process = process_with_unsupported_lines(2001)
        packet = packet_document(process)
        self.assertEqual(packet_document(decode(encode(process))), packet)
        source_blocker = process['analysis']['blockers'][0]
        source_blocker['message'] += '; exact correction evidence'
        corrected = packet_document(process)
        self.assertNotEqual(corrected['packet_hash'], packet['packet_hash'])
        self.assertNotEqual(json.loads(corrected['context'])['source_analysis']['sha256'],
                            json.loads(packet['context'])['source_analysis']['sha256'])

    def test_v1_fingerprint_is_unchanged_and_historical_large_packets_still_fail_closed(self):
        process = process_with_unsupported_lines(0, version=None)
        historical = packet_document(process)
        self.assertEqual(historical['version'], 1)
        self.assertEqual(historical['packet_hash'], 'b61caeb11f1910c14fac6cc3ee5689b0975d22dbce4327e68df0f6d7db858c89')
        process['sme_packet_version'] = 1
        self.assertEqual(packet_document(process), historical)
        old_large = process_with_unsupported_lines(2001, version=None)
        with self.assertRaisesRegex(ValidationError, 'SME packet exceeds supported size'):
            packet_document(old_large)

    def test_compacted_export_round_trips_answers_and_rejects_context_tampering(self):
        process = process_with_unsupported_lines(2001)
        with tempfile.TemporaryDirectory() as folder:
            packet = export_packet(process, Path(folder) / 'review')
            self.assertEqual(export_packet(process, Path(folder) / 'review'), packet)
            book = load_workbook(Path(folder) / 'review/sme-checklist.xlsx')
            for row in book['Checklist'].iter_rows(min_row=2):
                row[4].value = 'Yes'
            output = BytesIO(); book.save(output)
            answers = read_answers(output.getvalue(), packet, 'Actual reviewer')
            self.assertEqual(len(answers['items']), len(packet['items']))
            self.assertEqual(answers['packet_hash'], packet['packet_hash'])
            book['Context']['A2'] = 'changed technical gap evidence'
            altered = BytesIO(); book.save(altered); book.close()
            with self.assertRaisesRegex(ValidationError, 'Frozen Context changed'):
                read_answers(altered.getvalue(), packet, 'Actual reviewer')

    def test_coordinator_preserves_frozen_analysis_and_yes_does_not_support_the_gap(self):
        from workbench.coordinator import Coordinator
        from workbench.domain import decode
        source = COBOL.replace('  GOBACK.', 'DISPLAY X\n' * 2001 + '  GOBACK.')
        with tempfile.TemporaryDirectory() as folder:
            coordinator = Coordinator(Path(folder))
            try:
                process = coordinator.create(MANIFEST, {'ELIGIBLE.cbl': source})
                process['sme_packet_version'] = 2
                coordinator.ledger.save(process)
                coordinator.start('process-a'); coordinator.advance('process-a')
                issued = coordinator.ledger.get('process-a')
                self.assertEqual(issued['status'], 'WAITING_SME')
                packet = decode(coordinator.artifact('process-a', 'review/packet.json').read_bytes())
                analysis_bytes = coordinator.artifact('process-a', 'analysis/source-analysis.json').read_bytes()
                self.assertEqual(json.loads(packet['context'])['source_analysis']['sha256'], sha(analysis_bytes))
                self.assertEqual(len(decode(analysis_bytes)['blockers']), 2001)
                book = load_workbook(coordinator.artifact('process-a', 'review/sme-checklist.xlsx'))
                for row in book['Checklist'].iter_rows(min_row=2):
                    row[4].value = 'Yes'
                returned = BytesIO(); book.save(returned); book.close()
                coordinator.import_answers('process-a', returned.getvalue(), 'Test fixture reviewer')
                coordinator.advance('process-a')
                verified = coordinator.ledger.get('process-a')
                self.assertEqual(len([blocker for blocker in verified['blockers'] if blocker['kind'] == 'unsupported_source']), 2001)
                self.assertEqual(verified['program_versions'], {})
                self.assertEqual(coordinator.artifact('process-a', 'analysis/source-analysis.json').read_bytes(), analysis_bytes)
            finally:
                coordinator.close()


if __name__ == '__main__':
    unittest.main()
