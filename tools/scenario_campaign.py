"""Deterministic, independently expected checks of the documented JSON subset.

This is an engineering campaign, not another conversion coordinator and not
independent reviews by people/models. Ten explicit source families x twenty source
variants x one thousand distinct records = the default 200,000 scenarios. The
explicit 600,000 mode uses three thousand distinct records per source program,
with 80 percent valid and 20 percent invalid inputs in either mode. The
ordinary per-process fixture budget and immutable historical receipts remain
unchanged. No mainframe, network, credentials, LLM, or SME work is performed.
"""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import random
import sys
import time

from workbench.source import analyze_program
from workbench.reference import run_reference
from workbench.target import emit_program, prepare_generated


FAMILIES = (
    'literal_threshold', 'numeric_peer', 'and_correlation',
    'or_and_precedence', 'write_then_compare', 'ordered_overwrite',
    'character_peer', 'two_group_join', 'reversed_literal',
    'three_rule_feedback',
)
OPERATORS = ('=', '<>', '<', '<=', '>', '>=')
DEFAULT_SEED = 20261003
PROGRAM_COUNT = 200
CASES_PER_PROGRAM = 1000
EXPANDED_CASES_PER_PROGRAM = 3000
TOTAL_SCENARIOS = PROGRAM_COUNT * CASES_PER_PROGRAM
EXPANDED_TOTAL_SCENARIOS = PROGRAM_COUNT * EXPANDED_CASES_PER_PROGRAM


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=True)


def digest(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def relation(operator, left, right):
    # Independent expectation code does not consume the parser's IR or call
    # either evaluator. The six choices are deliberately explicit.
    if operator == '=': return left == right
    if operator == '<>': return left != right
    if operator == '<': return left < right
    if operator == '<=': return left <= right
    if operator == '>': return left > right
    if operator == '>=': return left >= right
    raise ValueError(operator)


def specification(program_index):
    if type(program_index) is not int or not 0 <= program_index < PROGRAM_COUNT:
        raise ValueError('program_index must be an integer in 0..199')
    family, variant = divmod(program_index, 20)
    width = (3, 4, 6, 9, 18)[variant % 5]
    maximum = 10 ** width - 1
    threshold = (0, 1, maximum // 2, maximum - 1, maximum)[(variant // 4) % 5]
    return {'program_index': program_index, 'family': FAMILIES[family],
            'variant': variant, 'width': width, 'maximum': maximum,
            'text_width': 2 + variant % 4, 'operator': OPERATORS[variant % 6],
            'threshold': threshold, 'assignment': (threshold + 1) % (maximum + 1),
            'two_groups': family == 7 or variant % 2 == 1,
            'copybook': variant % 4 == 3}


def source_program(spec):
    p = spec
    op, threshold, assignment = p['operator'], p['threshold'], p['assignment']
    family = p['family']
    predicate = {
        'literal_threshold': f'A {op} {threshold}',
        'numeric_peer': f'A {op} B',
        'and_correlation': f'A {op} {threshold} AND B >= A',
        'or_and_precedence': f'A {op} {threshold} OR B = A AND TEXT-A = TEXT-B',
        'write_then_compare': f'A {op} B',
        'ordered_overwrite': f'A {op} {threshold} AND TEXT-A <> TEXT-B',
        'character_peer': 'TEXT-A = TEXT-B' if p['variant'] % 2 == 0 else 'TEXT-A <> TEXT-B',
        'two_group_join': f'A {op} B AND TEXT-A = TEXT-B',
        'reversed_literal': f'{threshold} {op} A',
        'three_rule_feedback': f'A {op} B',
    }[family]
    def rule(condition, yes, no):
        return ['IF ' + condition] + yes + ['ELSE'] + no + ['END-IF.']
    body = rule(predicate, ['MOVE "T" TO FLAG'], ['MOVE "F" TO FLAG'])
    if family == 'write_then_compare':
        body = rule(predicate, [f'MOVE {assignment} TO A'], [f'MOVE {threshold} TO A'])
        body += rule(f'A = {assignment}', ['MOVE "T" TO FLAG'], ['MOVE "F" TO FLAG'])
    elif family == 'ordered_overwrite':
        body = rule(predicate, ['MOVE "P" TO FLAG', 'MOVE "T" TO FLAG'],
                    ['MOVE "Q" TO FLAG', 'MOVE "F" TO FLAG'])
    elif family == 'three_rule_feedback':
        body += rule('FLAG = "T" AND TEXT-A = TEXT-B',
                     [f'MOVE {assignment} TO B'], [f'MOVE {threshold} TO B'])
        body += rule(f'B = {assignment} OR A = B',
                     ['MOVE "Y" TO FLAG'], ['MOVE "N" TO FLAG'])
    layout = ['01 FIRST-RECORD.', f'05 A PIC 9({p["width"]}).',
              f'05 TEXT-A PIC X({p["text_width"]}).']
    if p['two_groups']: layout.append('01 SECOND-RECORD.')
    layout += [f'05 B PIC 9({p["width"]}).', f'05 TEXT-B PIC X({p["text_width"]}).',
               '05 FLAG PIC X.']
    files = {}
    if p['copybook']:
        files['CAMPLAY.cpy'] = '\n'.join(layout) + '\n'
        layout = ['COPY CAMPLAY.']
    groups = 'FIRST-RECORD SECOND-RECORD' if p['two_groups'] else 'FIRST-RECORD'
    lines = ['IDENTIFICATION DIVISION.', f'PROGRAM-ID. CAM{p["program_index"]:03d}.',
             'DATA DIVISION.', 'LINKAGE SECTION.'] + layout
    lines += ['PROCEDURE DIVISION USING ' + groups + '.'] + body
    lines += ['STOP RUN.' if p['variant'] % 3 == 1 else 'GOBACK.']
    # Physical variants remain evidence dimensions, never the sole scenario
    # distinction: layouts, thresholds, operators and records vary as well.
    if p['variant'] % 4 == 1:
        lines = ['  ' + line.lower() if '"' not in line else '  ' + line for line in lines]
    if p['variant'] % 4 == 2:
        lines.insert(4, '*> campaign synthetic layout; no native execution')
        lines = [f'{(i+1)*10:06d} ' + line for i, line in enumerate(lines)]
    return '\n'.join(lines) + '\n', files


def program_records(spec, seed=DEFAULT_SEED, cases_per_program=CASES_PER_PROGRAM):
    """Yield 80 percent valid and 20 percent invalid distinct concrete inputs.

    The default 1,000-record sequence is preserved exactly. The explicit
    expanded mode creates 3,000 records without concatenating seeded replays.

    Boundary/correlation slots are selected before seeded domain values. Hash
    deduplication retries are recorded by the caller through unique hashes;
    rejected duplicate candidates are not counted as executed scenarios.
    """
    if type(cases_per_program) is not int or cases_per_program not in (CASES_PER_PROGRAM, EXPANDED_CASES_PER_PROGRAM):
        raise ValueError('cases_per_program must be 1000 or 3000')
    if type(seed) is not int: raise ValueError('seed must be an integer')
    p = spec
    rng = random.Random(seed + p['program_index'] * 1000003)
    width, maximum, threshold = p['text_width'], p['maximum'], p['threshold']
    boundaries = sorted({0, 1, maximum - 1, maximum, threshold,
                         max(0, threshold-1), min(maximum, threshold+1)})
    tokens = [' ' * width, 'A'.ljust(width), 'a'.ljust(width),
              'Z' * width, '"'.ljust(width), '*>'.ljust(width),
              '09'.ljust(width), 'A'.rjust(width)]
    seen = set()
    valid_count = cases_per_program * 4 // 5
    for index in range(cases_per_program):
        attempt = 0
        while True:
            slot = index + attempt * 1009
            mode = slot % 8
            a = boundaries[(slot // 8) % len(boundaries)] if mode < 4 else rng.randrange(maximum + 1)
            b = a if mode in (0, 4) else max(0, a-1) if mode in (1, 5) else min(maximum, a+1) if mode in (2, 6) else rng.randrange(maximum+1)
            text_a = tokens[(slot // 3) % len(tokens)]
            text_b = text_a if slot % 3 == 0 else tokens[(slot // 7 + 1) % len(tokens)]
            # Seeded characters expand the meaningful character relation
            # space after a collision, without adding inert identity fields.
            if attempt:
                text_a = ''.join(rng.choice(' Aaz09*>"') for _ in range(width))
                text_b = text_a if slot % 3 == 0 else ''.join(rng.choice(' Aaz09*>"') for _ in range(width))
            row = {'A': a, 'B': b, 'TEXT-A': text_a, 'TEXT-B': text_b,
                   'FLAG': (' ', 'T', 'F', 'Y', 'N')[slot % 5]}
            label = 'valid_' + ('equal_peer', 'lower_peer', 'upper_peer', 'independent_peer')[mode % 4]
            if index >= valid_count:
                bad = (index - valid_count) % 10
                if bad == 0: row['A'] = -1; label = 'negative_numeric'
                elif bad == 1: row['B'] = maximum + 1; label = 'numeric_overflow'
                elif bad == 2: row['A'] = bool(slot % 2); label = 'boolean_numeric'
                elif bad == 3: row['B'] = float(b); label = 'fractional_type_numeric'
                elif bad == 4: row['TEXT-A'] = text_a[:-1]; label = 'short_character'
                elif bad == 5: row['TEXT-B'] = text_b + 'X'; label = 'long_character'
                elif bad == 6: del row['A']; label = 'missing_numeric_field'
                elif bad == 7: row['EXTRA'] = slot; label = 'extra_field'
                elif bad == 8: row['TEXT-A'] = None; label = 'null_character'
                else: row['A'] = -1; row['TEXT-B'] = []; label = 'multiple_layout_errors'
            fingerprint = digest(row)
            if fingerprint not in seen:
                seen.add(fingerprint)
                yield index, row, label, attempt
                break
            attempt += 1
            if attempt > 10000:
                raise RuntimeError('Cannot generate enough distinct meaningful records')


def independent_expected(spec, record):
    """Manual family oracle; no shared field specs, parser IR, or evaluators."""
    p = spec
    fields = ('A', 'B', 'FLAG', 'TEXT-A', 'TEXT-B')
    if type(record) is not dict:
        return {'input_status': 'REJECT_INPUT', 'errors': ['record must be an object'], 'return_code': None}
    errors = []
    if set(record) != set(fields): errors.append('field set differs from source layout')
    for field in fields:
        value = record.get(field)
        if field in ('A', 'B'):
            if type(value) is not int or not 0 <= value <= p['maximum']:
                errors.append(field + ': invalid unsigned integer')
        elif type(value) is not str or len(value) != (1 if field == 'FLAG' else p['text_width']):
            errors.append(field + ': invalid fixed-width string')
    if errors:
        return {'input_status': 'REJECT_INPUT', 'errors': errors, 'return_code': None}
    row = record.copy()
    a, b, ta, tb = row['A'], row['B'], row['TEXT-A'], row['TEXT-B']
    family, op, threshold, assignment = p['family'], p['operator'], p['threshold'], p['assignment']
    if family in ('literal_threshold', 'ordered_overwrite'):
        branch = relation(op, a, threshold)
        if family == 'ordered_overwrite': branch = branch and ta != tb
    elif family in ('numeric_peer', 'write_then_compare', 'three_rule_feedback'):
        branch = relation(op, a, b)
    elif family == 'and_correlation': branch = relation(op, a, threshold) and b >= a
    elif family == 'or_and_precedence': branch = relation(op, a, threshold) or (b == a and ta == tb)
    elif family == 'character_peer': branch = (ta == tb) if p['variant'] % 2 == 0 else (ta != tb)
    elif family == 'two_group_join': branch = relation(op, a, b) and ta == tb
    elif family == 'reversed_literal': branch = relation(op, threshold, a)
    else: raise ValueError(family)
    branches = [branch]
    if family == 'write_then_compare':
        row['A'] = assignment if branch else threshold
        branches.append(row['A'] == assignment)
        row['FLAG'] = 'T' if branches[-1] else 'F'
    else:
        row['FLAG'] = 'T' if branch else 'F'
        if family == 'three_rule_feedback':
            branches.append(row['FLAG'] == 'T' and ta == tb)
            row['B'] = assignment if branches[-1] else threshold
            branches.append(row['B'] == assignment or row['A'] == row['B'])
            row['FLAG'] = 'Y' if branches[-1] else 'N'
    return {'input_status': 'ACCEPT_INPUT', 'record': row, 'branches': branches, 'return_code': 0}


def projection(result):
    if result.get('input_status') == 'ACCEPT_INPUT':
        return {'input_status': result['input_status'], 'record': result['record'],
                'branches': [t['branch'] for t in result['trace']], 'return_code': result['return_code']}
    return result


def implementation_fingerprint():
    root = Path(__file__).resolve().parents[1]
    paths = ['workbench/domain.py', 'workbench/source.py', 'workbench/target.py', 'workbench/reference.py',
             'workbench/fixtures.py', 'tools/scenario_campaign.py']
    hashes = {p: hashlib.sha256((root / p).read_bytes()).hexdigest() for p in paths}
    return {'files': hashes, 'sha256': digest(hashes)}


def _case_count(total_scenarios):
    if type(total_scenarios) is not int or total_scenarios not in (TOTAL_SCENARIOS, EXPANDED_TOTAL_SCENARIOS):
        raise ValueError('total_scenarios must be 200000 or 600000')
    return total_scenarios // PROGRAM_COUNT


def campaign(seed=DEFAULT_SEED, limit=None, total_scenarios=TOTAL_SCENARIOS):
    if type(seed) is not int: raise ValueError('seed must be an integer')
    cases_per_program = _case_count(total_scenarios)
    if limit is not None and (type(limit) is not int or not 1 <= limit <= total_scenarios):
        raise ValueError('limit must be in 1..' + str(total_scenarios))
    requested = total_scenarios if limit is None else limit
    started = time.perf_counter()
    before = implementation_fingerprint()
    scenario_hashes, program_hashes, semantic_hashes = set(), set(), set()
    aggregate = hashlib.sha256()
    labels, families = Counter(), Counter()
    branch_coverage, programs, divergences = [], [], []
    rejected_duplicates = duplicate_executions = executed = valid = invalid = divergence_count = 0
    for program_index in range(PROGRAM_COUNT):
        spec = specification(program_index)
        source, files = source_program(spec)
        program = analyze_program(f'CAM{program_index:03d}.cbl', source, files)
        program['target_contract_version'] = 2
        if program['blockers']: raise RuntimeError(canonical(program['blockers']))
        code = emit_program(program)
        execute = prepare_generated(code)
        program_hash = digest({'source': source, 'copybooks': files})
        semantic_hash = digest({'specification': {k:v for k,v in spec.items() if k not in ('program_index','variant','copybook')},
                                'rule_predicates': [r['predicate'] for r in program['rules']],
                                'effects': [[r['then'], r['else']] for r in program['rules']]})
        program_hashes.add(program_hash); semantic_hashes.add(semantic_hash)
        outcomes = {r['id']: set() for r in program['rules']}
        per_program = per_valid = per_invalid = 0
        for case_index, record, label, retries in program_records(spec, seed, cases_per_program):
            rejected_duplicates += retries
            scenario_hash = digest({'program_hash': program_hash, 'record': record})
            if scenario_hash in scenario_hashes: duplicate_executions += 1
            scenario_hashes.add(scenario_hash)
            aggregate.update(bytes.fromhex(scenario_hash))
            original = canonical(record)
            expected = independent_expected(spec, record)
            reference = run_reference(program, record)
            try: actual = execute(record)
            except Exception as exc: actual = {'input_status': 'TARGET_ERROR', 'error_type': type(exc).__name__}
            if (projection(reference) != expected or projection(actual) != expected or actual != reference
                    or canonical(record) != original):
                divergence_count += 1
                if len(divergences) < 50:
                    divergences.append({'program_index': program_index, 'case_index': case_index,
                                        'scenario_sha256': scenario_hash, 'record': record,
                                        'expected': expected, 'reference': reference, 'actual': actual,
                                        'input_mutated': canonical(record) != original})
            for trace in reference.get('trace', []): outcomes[trace['rule_id']].add(trace['branch'])
            executed += 1; per_program += 1
            if expected['input_status'] == 'ACCEPT_INPUT': valid += 1; per_valid += 1
            else: invalid += 1; per_invalid += 1
            labels[label] += 1; families[spec['family']] += 1
            if limit is not None and executed >= limit: break
        programs.append({'program_index': program_index, 'family': spec['family'], 'variant': spec['variant'],
                         'specification': spec, 'source_and_copybooks_sha256': program_hash,
                         'generated_target_sha256': hashlib.sha256(code.encode()).hexdigest(),
                         'semantic_configuration_sha256': semantic_hash, 'executed': per_program,
                         'valid_inputs': per_valid, 'invalid_inputs': per_invalid})
        branch_coverage += [{'program_index': program_index, 'rule_id': rid,
                             'observed': sorted(values), 'missing': [v for v in (False,True) if v not in values]}
                            for rid, values in outcomes.items()]
        if limit is not None and executed >= limit: break
    after = implementation_fingerprint()
    stable = before == after
    full_programs, remainder = divmod(requested, cases_per_program)
    expected_valid = full_programs * (cases_per_program * 4 // 5) + min(remainder, cases_per_program * 4 // 5)
    expected_invalid = requested - expected_valid
    input_mix_verified = valid == expected_valid and invalid == expected_invalid
    expanded_args = ' --total-scenarios ' + str(total_scenarios) if total_scenarios != TOTAL_SCENARIOS else ''
    return {'schema_version': 1, 'kind': 'DETERMINISTIC_GENERATED_SCENARIO_CAMPAIGN',
            'method': '10 finite source families x 20 program variants x ' + str(cases_per_program) + ' unique program/input scenarios; ' + str(cases_per_program * 4 // 5) + ' valid and ' + str(cases_per_program // 5) + ' invalid inputs per program; compiled once per concrete program; three-way comparison to independent hand-coded family expectations',
            'seed': seed, 'requested': requested, 'executed': executed,
            'total_scenarios': total_scenarios, 'cases_per_program': cases_per_program,
            'python_version': sys.version,
            'unique_scenarios': len(scenario_hashes), 'duplicate_executions': duplicate_executions,
            'duplicate_candidates_rejected_before_execution': rejected_duplicates,
            'valid_inputs': valid, 'invalid_inputs': invalid,
            'expected_valid_inputs': expected_valid, 'expected_invalid_inputs': expected_invalid,
            'input_mix_verified': input_mix_verified,
            'compiled_programs': len(programs), 'unique_source_programs': len(program_hashes),
            'unique_semantic_configurations': len(semantic_hashes),
            'scenario_sequence_sha256': aggregate.hexdigest(),
            'family_counts': dict(families), 'input_family_counts': dict(labels),
            'programs': programs, 'branch_coverage': branch_coverage,
            'branch_targets': len(branch_coverage)*2,
            'branches_observed': sum(len(r['observed']) for r in branch_coverage),
            'divergence_count': divergence_count, 'divergences': divergences,
            'divergence_details_limit': 50, 'source_unchanged_during_campaign': stable,
            'implementation_before': before, 'implementation_after': after,
            'elapsed_seconds': round(time.perf_counter()-started, 6),
            'passed': divergence_count == 0 and duplicate_executions == 0 and len(scenario_hashes) == requested and stable and executed == requested and input_mix_verified,
            'replay': {'command': 'PYTHONPATH=. python tools/scenario_campaign.py --seed ' + str(seed)
                                 + expanded_args
                                 + (' --limit ' + str(limit) if limit is not None else ''),
                       'single_scenario': 'PYTHONPATH=. python tools/scenario_campaign.py --seed ' + str(seed) + expanded_args + ' --program-index N --case-index M',
                       'program_index_range': [0,199], 'case_index_range': [0,cases_per_program-1]},
            'limitations': ['Finite generated combinations, not ' + str(total_scenarios) + ' independent reviews or exhaustive proof.',
                            'Only flat caller-owned LINKAGE JSON semantics; no native storage, files, decimal encoding, collation ordering, CICS, SQL, scheduler or mainframe execution.',
                            'Independent expected behavior is hand-coded for these ten families; target and reference still share the production source parser.',
                            'Decision outcomes include provably unreachable boundaries; missing outcomes remain explicit.',
                            'This engineering campaign does not alter the separately configured per-process fixture budget, frozen historical version-1/version-2 evidence or any human SME gate.']}


def replay(program_index, case_index, seed=DEFAULT_SEED, total_scenarios=TOTAL_SCENARIOS):
    cases_per_program = _case_count(total_scenarios)
    if type(case_index) is not int or not 0 <= case_index < cases_per_program:
        raise ValueError('case_index must be an integer in 0..' + str(cases_per_program-1))
    spec = specification(program_index)
    source, files = source_program(spec)
    program = analyze_program(f'CAM{program_index:03d}.cbl', source, files)
    program['target_contract_version'] = 2
    record = next(row for index,row,_,_ in program_records(spec, seed, cases_per_program) if index == case_index)
    return {'seed': seed, 'program_index': program_index, 'case_index': case_index,
            'source': source, 'copybooks': files, 'record': record,
            'scenario_sha256': digest({'program_hash': digest({'source': source, 'copybooks': files}), 'record': record}),
            'independent_expected': independent_expected(spec, record),
            'reference': run_reference(program, record),
            'target': prepare_generated(emit_program(program))(record)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--seed', type=int, default=DEFAULT_SEED)
    parser.add_argument('--total-scenarios', type=int, choices=(TOTAL_SCENARIOS, EXPANDED_TOTAL_SCENARIOS), default=TOTAL_SCENARIOS,
                        help='Finite full campaign: default 200000 or explicit 600000 distinct program/input scenarios')
    parser.add_argument('--limit', type=int, help='Smoke run only; never counts as the selected full campaign')
    parser.add_argument('--output', type=Path, default=Path('.implementation/tmp/scenario-campaign.json'))
    parser.add_argument('--program-index', type=int)
    parser.add_argument('--case-index', type=int)
    args = parser.parse_args()
    if args.program_index is not None or args.case_index is not None:
        if args.program_index is None or args.case_index is None: parser.error('Both replay indices are required')
        print(json.dumps(replay(args.program_index, args.case_index, args.seed, args.total_scenarios), indent=2, sort_keys=True))
        return 0
    result = campaign(args.seed, args.limit, args.total_scenarios)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    temporary = args.output.with_name(args.output.name + '.new')
    temporary.write_text(json.dumps(result, indent=2, sort_keys=True)+'\n')
    temporary.replace(args.output)
    print(json.dumps({k: result[k] for k in ('passed','executed','unique_scenarios','duplicate_executions',
                     'compiled_programs','valid_inputs','invalid_inputs','divergence_count','elapsed_seconds',
                     'scenario_sequence_sha256','source_unchanged_during_campaign')}, indent=2))
    return 0 if result['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
