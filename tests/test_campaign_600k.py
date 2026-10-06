"""The explicit 600k recipe expands records, preserving the default campaign."""
from collections import Counter
import io
import unittest
from unittest.mock import patch

from tools import scenario_campaign as campaign


class Campaign600kTests(unittest.TestCase):
    def test_default_thousand_record_sequences_keep_prechange_hashes(self):
        pinned = {
            0: '2207e622565b1ebfcd4f44cf9a5d803e7d6d0199b50791c3391ac677440b5c55',
            143: 'd31b4a1a3908ca7abccc50d6dffaa616d8852030771b80572ea0a45acbea9a51',
            183: '8d28defed8cc5b6c105e2a7cddc16fe75839317f4c6858aa30c19e0cfb80781a',
        }
        self.assertEqual(campaign.CASES_PER_PROGRAM, 1000)
        for program_index, expected_hash in pinned.items():
            with self.subTest(program_index=program_index):
                spec = campaign.specification(program_index)
                records = list(campaign.program_records(spec))
                self.assertEqual(len(records), 1000)
                self.assertEqual(campaign.digest(records), expected_hash)
                self.assertEqual(records, list(campaign.program_records(spec, cases_per_program=1000)))

    def test_expanded_generator_is_unique_eighty_twenty_for_all_ten_families(self):
        scenario_hashes = set()
        observed_families = set()
        rejected_collisions = 0
        invalid_labels = {
            'negative_numeric', 'numeric_overflow', 'boolean_numeric',
            'fractional_type_numeric', 'short_character', 'long_character',
            'missing_numeric_field', 'extra_field', 'null_character',
            'multiple_layout_errors',
        }
        for program_index in range(0, 200, 20):
            with self.subTest(program_index=program_index):
                spec = campaign.specification(program_index)
                observed_families.add(spec['family'])
                source, files = campaign.source_program(spec)
                program_hash = campaign.digest({'source': source, 'copybooks': files})
                generated = list(campaign.program_records(spec, cases_per_program=3000))
                self.assertEqual([index for index, _, _, _ in generated], list(range(3000)))
                fingerprints = {campaign.digest(record) for _, record, _, _ in generated}
                self.assertEqual(len(fingerprints), 3000)
                statuses = Counter()
                labels = Counter()
                for index, record, label, retries in generated:
                    statuses[campaign.independent_expected(spec, record)['input_status']] += 1
                    labels[label] += 1
                    rejected_collisions += retries
                    self.assertIs(type(retries), int)
                    self.assertGreaterEqual(retries, 0)
                    if index < 2400:
                        self.assertEqual(set(record), {'A', 'B', 'TEXT-A', 'TEXT-B', 'FLAG'})
                        self.assertIs(type(record['A']), int)
                        self.assertIs(type(record['B']), int)
                        self.assertTrue(0 <= record['A'] <= spec['maximum'])
                        self.assertTrue(0 <= record['B'] <= spec['maximum'])
                        self.assertEqual(len(record['TEXT-A']), spec['text_width'])
                        self.assertEqual(len(record['TEXT-B']), spec['text_width'])
                        self.assertEqual(len(record['FLAG']), 1)
                        self.assertTrue(label.startswith('valid_'))
                    else:
                        self.assertIn(label, invalid_labels)
                    scenario_hashes.add(campaign.digest({'program_hash': program_hash, 'record': record}))
                self.assertEqual(statuses, {'ACCEPT_INPUT': 2400, 'REJECT_INPUT': 600})
                self.assertEqual({label: labels[label] for label in invalid_labels},
                                 {label: 60 for label in invalid_labels})
        self.assertEqual(observed_families, set(campaign.FAMILIES))
        self.assertEqual(len(scenario_hashes), 30000)
        self.assertGreater(rejected_collisions, 0)

    def test_expansion_adds_records_without_repeating_the_default_seed_recipe(self):
        spec = campaign.specification(143)
        default = list(campaign.program_records(spec))
        expanded = list(campaign.program_records(spec, cases_per_program=3000))
        self.assertEqual(expanded[:800], default[:800])
        self.assertTrue(all(label.startswith('valid_') for _, _, label, _ in expanded[800:2400]))
        self.assertTrue(all(not label.startswith('valid_') for _, _, label, _ in expanded[2400:]))
        self.assertNotEqual([row for _, row, _, _ in expanded[1000:2000]],
                            [row for _, row, _, _ in expanded[:1000]])
        self.assertNotEqual([row for _, row, _, _ in expanded[2000:]],
                            [row for _, row, _, _ in expanded[:1000]])

    def test_generator_length_rejects_unadvertised_and_nonstrict_values(self):
        spec = campaign.specification(0)
        for value in (-1, 0, 999, 1001, 2000, 2999, 3001, True, False, 1000.0, '3000'):
            with self.subTest(cases_per_program=value):
                with self.assertRaises(ValueError):
                    next(campaign.program_records(spec, cases_per_program=value))
        for seed in (True, False, 1.5, '23'):
            with self.subTest(seed=seed):
                with self.assertRaises(ValueError):
                    next(campaign.program_records(spec, seed=seed, cases_per_program=3000))

    def test_campaign_recipe_and_limit_validation_precede_any_compilation(self):
        with patch.object(campaign, 'analyze_program') as analyze:
            for total in (-1, 0, 200001, 400000, 599999, 600001, True, False, 600000.0, '600000'):
                with self.subTest(total_scenarios=total):
                    with self.assertRaises(ValueError):
                        campaign.campaign(limit=1, total_scenarios=total)
            for total in (200000, 600000):
                for limit in (-1, 0, total + 1, True, False, 1.5, '1'):
                    with self.subTest(total_scenarios=total, limit=limit):
                        with self.assertRaises(ValueError):
                            campaign.campaign(limit=limit, total_scenarios=total)
            for seed in (True, False, 1.5, '21'):
                with self.subTest(seed=seed):
                    with self.assertRaises(ValueError):
                        campaign.campaign(seed=seed, limit=1, total_scenarios=600000)
            analyze.assert_not_called()

    def test_expanded_single_program_smoke_executes_all_three_thousand_records(self):
        original = campaign.prepare_generated
        calls = Counter()
        def prepare(code):
            execute = original(code)
            def wrapped(record):
                calls['executed'] += 1
                return execute(record)
            return wrapped
        with patch.object(campaign, 'prepare_generated', side_effect=prepare) as compiler:
            result = campaign.campaign(limit=3000, total_scenarios=600000)
        self.assertTrue(result['passed'], result['divergences'])
        self.assertEqual(result['requested'], 3000)
        self.assertEqual(result['executed'], 3000)
        self.assertEqual(result['unique_scenarios'], 3000)
        self.assertEqual(result['duplicate_executions'], 0)
        self.assertEqual(result['valid_inputs'], 2400)
        self.assertEqual(result['invalid_inputs'], 600)
        self.assertEqual(result['total_scenarios'], 600000)
        self.assertEqual(result['cases_per_program'], 3000)
        self.assertEqual(result['expected_valid_inputs'], 2400)
        self.assertEqual(result['expected_invalid_inputs'], 600)
        self.assertTrue(result['input_mix_verified'])
        self.assertEqual(result['divergence_count'], 0)
        self.assertEqual(result['compiled_programs'], 1)
        self.assertEqual(compiler.call_count, 1)
        self.assertEqual(calls['executed'], 3000)
        self.assertEqual(result['programs'][0]['executed'], 3000)
        self.assertTrue(result['source_unchanged_during_campaign'])
        self.assertEqual(result['replay']['case_index_range'], [0, 2999])
        self.assertIn('--total-scenarios 600000', result['replay']['command'])
        self.assertIn('--total-scenarios 600000', result['replay']['single_scenario'])

    def test_expanded_duplicate_generator_cannot_earn_a_passing_receipt(self):
        row = next(campaign.program_records(campaign.specification(0), cases_per_program=3000))[1]
        corrupt = iter([(0, row, 'repeated', 0), (1, row, 'repeated', 0)])
        with patch.object(campaign, 'program_records', return_value=corrupt):
            result = campaign.campaign(limit=2, total_scenarios=600000)
        self.assertEqual(result['executed'], 2)
        self.assertEqual(result['unique_scenarios'], 1)
        self.assertEqual(result['duplicate_executions'], 1)
        self.assertEqual(result['divergence_count'], 0)
        self.assertFalse(result['passed'])

    def test_unique_matching_records_with_wrong_input_mix_cannot_pass(self):
        rows = iter((index, {'A': index % 1000, 'B': index // 1000,
                             'TEXT-A': ' A', 'TEXT-B': ' B', 'FLAG': ' '}, 'valid_corruption', 0)
                    for index in range(3000))
        with patch.object(campaign, 'program_records', return_value=rows):
            result = campaign.campaign(limit=3000, total_scenarios=600000)
        self.assertEqual(result['executed'], 3000)
        self.assertEqual(result['unique_scenarios'], 3000)
        self.assertEqual(result['divergence_count'], 0)
        self.assertEqual(result['duplicate_executions'], 0)
        self.assertEqual(result['valid_inputs'], 3000)
        self.assertEqual(result['invalid_inputs'], 0)
        self.assertEqual(result['expected_valid_inputs'], 2400)
        self.assertEqual(result['expected_invalid_inputs'], 600)
        self.assertFalse(result['input_mix_verified'])
        self.assertFalse(result['passed'])

    def test_expanded_last_record_replays_copybook_feedback_and_three_way_expectation(self):
        result = campaign.replay(183, 2999, total_scenarios=600000)
        self.assertTrue(result['copybooks'])
        self.assertEqual(result['case_index'], 2999)
        expected_record = list(campaign.program_records(
            campaign.specification(183), cases_per_program=3000))[-1][1]
        self.assertEqual(result['record'], expected_record)
        self.assertEqual(result['reference'], result['target'])
        self.assertEqual(campaign.projection(result['target']), result['independent_expected'])
        self.assertEqual(result['target']['input_status'], 'REJECT_INPUT')
        self.assertEqual(result['scenario_sha256'], campaign.digest({
            'program_hash': campaign.digest({'source': result['source'], 'copybooks': result['copybooks']}),
            'record': result['record']}))
        valid = campaign.replay(183, 2399, total_scenarios=600000)
        self.assertEqual(valid['target']['input_status'], 'ACCEPT_INPUT')
        self.assertEqual(valid['reference'], valid['target'])
        self.assertEqual(campaign.projection(valid['target']), valid['independent_expected'])
        self.assertEqual(len(valid['target']['trace']), 3)

    def test_replay_bounds_depend_on_explicit_campaign_recipe(self):
        for total, invalid_indices in ((200000, (-1, 1000, 2999)), (600000, (-1, 3000))):
            for index in (*invalid_indices, True, False, 1.5, '2999'):
                with self.subTest(total_scenarios=total, case_index=index):
                    with self.assertRaises(ValueError):
                        campaign.replay(0, index, total_scenarios=total)
        with self.assertRaises(ValueError):
            campaign.replay(0, 2999)
        for program_index in (-1, 200, True, False, 1.5):
            with self.subTest(program_index=program_index):
                with self.assertRaises(ValueError):
                    campaign.replay(program_index, 2999, total_scenarios=600000)
        for total in (0, 599999, True, False, 600000.0):
            with self.subTest(total_scenarios=total):
                with self.assertRaises(ValueError):
                    campaign.replay(0, 0, total_scenarios=total)
        for seed in (True, False, 1.5, '23'):
            with self.subTest(seed=seed):
                with self.assertRaises(ValueError):
                    campaign.replay(0, 0, seed=seed, total_scenarios=600000)

    def test_cli_replay_routes_explicit_expansion_and_preserves_default_recipe(self):
        for total_args, case_index, total in (([], '999', 200000),
                                             (['--total-scenarios', '600000'], '2999', 600000)):
            argv = ['scenario_campaign.py', *total_args,
                    '--program-index', '183', '--case-index', case_index]
            with patch('sys.argv', argv), patch.object(campaign, 'replay', return_value={}) as replay, \
                    patch('sys.stdout', io.StringIO()):
                self.assertEqual(campaign.main(), 0)
            replay.assert_called_once_with(183, int(case_index), campaign.DEFAULT_SEED, total)

    def test_expanded_generator_is_deterministic_and_changes_for_a_new_seed(self):
        spec = campaign.specification(143)
        first = list(campaign.program_records(spec, seed=23, cases_per_program=3000))
        repeated = list(campaign.program_records(spec, seed=23, cases_per_program=3000))
        changed = list(campaign.program_records(spec, seed=24, cases_per_program=3000))
        self.assertEqual(first, repeated)
        self.assertNotEqual(campaign.digest(first), campaign.digest(changed))
        self.assertEqual(len({campaign.digest(row) for _, row, _, _ in changed}), 3000)


if __name__ == '__main__':
    unittest.main()
