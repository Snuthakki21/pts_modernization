"""Bounded source-derived documentation over the Coordinator's frozen analysis.

Recognition is not conversion support. This projection never writes source,
changes requirements, invents business purpose or runs a second analysis engine.
"""
from collections import defaultdict
from html import escape
import re

from .domain import encode, require, sha
from .mainframe import _lines
from .lineage import _mask_literals
from .requirements import NO_REASON

PAGE_SIZE = 20
DETAIL_LIMIT = 30
CATEGORIES = {
    'cobol_program': 'COBOL programs', 'copybook': 'Copybooks', 'dclgen': 'DCL / DCLGEN descriptors',
    'jcl_job': 'JCL job streams', 'jcl_proc': 'JCL procedures', 'jcl_fragment': 'JCL includes / fragments',
    'bms_map': 'CICS BMS screen sources', 'cics_definition': 'CICS resource definitions',
    'sql': 'SQL / Db2 sources', 'utility_control': 'Control cards', 'scheduler_definition': 'Scheduler definitions',
    'rexx': 'REXX', 'clist': 'CLIST', 'pli': 'PL/I', 'assembler': 'Assembler',
    'unknown': 'Unknown source types', 'ambiguous': 'Conflicting source types',
}
BOUNDARY = ('Recognition describes the retained export, not installed resources or the whole estate. '
            'Source-derived observations require validation; they do not establish business intent, '
            'conversion support or observed mainframe parity.')
NAME = r'[A-Z@$#][A-Z0-9@$#_-]*'


def _reference(asset, start=1, end=None):
    lines = len(asset.get('source_text', '').splitlines())
    return {'path': asset['path'], 'source_hash': asset['source_hash'],
            'start_line': start if lines else None, 'end_line': min(end or lines, lines) if lines else None}


def _definitions(asset):
    """Conservative observations, independent of the frozen type classification."""
    rows = _lines(asset.get('source_text', ''))
    by_line = dict(rows)
    # Preserve physical line positions while masking quoted SQL/COBOL strings.
    masked = _mask_literals('\n'.join(by_line.get(n, '') for n in range(1, len(asset.get('source_text', '').splitlines()) + 1)))
    patterns = {
        'cobol_program': rf'^\s*PROGRAM-ID\s*\.\s*({NAME})\s*\.',
        'jcl_job': rf'^//({NAME})\s+JOB\b',
        'jcl_proc': rf'^//({NAME})\s+PROC\b',
        'bms_map': rf'^\s*({NAME})\s+DFHMDI\b',
        'db2_procedure': rf'^\s*CREATE\s+(?:OR\s+REPLACE\s+)?PROCEDURE\s+({NAME}(?:\.{NAME})*)\s*(?:\(|LANGUAGE\b)',
    }
    result = defaultdict(list)
    for kind, pattern in patterns.items():
        for match in re.finditer(pattern, masked, re.I | re.M):
            # Leading whitespace may cross empty lines; evidence starts at the keyword.
            offset = match.start() + len(match[0]) - len(match[0].lstrip())
            start = masked.count('\n', 0, offset) + 1
            end = masked.count('\n', 0, match.end()) + 1
            result[kind].append({'name': match[1].upper(), **_reference(asset, start, end)})
    return result


def _inventory(analysis, assets, definitions):
    assessed = bool(analysis)
    classifications = analysis.get('classifications', {})
    categories = []
    unresolved = []
    for kind, label in CATEGORIES.items():
        selected = [a for a in assets if classifications.get(a['path'], {}).get('kind', 'unknown') == kind]
        refs = [{'path': a['path'], 'source_hash': a['source_hash'], 'selected': a.get('selected', True),
                 'evidence': classifications.get(a['path'], {}).get('evidence', [])[:5]} for a in selected]
        count = sum(len(definitions[a['path']].get(kind, [])) for a in selected) if kind in {'cobol_program', 'jcl_job', 'jcl_proc', 'bms_map'} else None
        categories.append({'kind': kind, 'label': label, 'file_count': len(selected) if assessed else None,
                           'selected_file_count': sum(a.get('selected', True) for a in selected) if assessed else None,
                           'definition_count': count if assessed else None, 'evidence': refs[:DETAIL_LIMIT],
                           'evidence_complete': len(refs) <= DETAIL_LIMIT})
        if kind in {'unknown', 'ambiguous'}: unresolved.extend(refs)
    procedures = [r for a in assets for r in definitions[a['path']].get('db2_procedure', [])]
    return {'retained_files': len(assets) if assessed else None,
            'selected_files': sum(a.get('selected', True) for a in assets) if assessed else None,
            'estate_total': None, 'categories': categories,
            'sql_procedures': {'observed_definitions': len(procedures) if assessed else None,
                               'estate_total': None, 'evidence': procedures[:DETAIL_LIMIT],
                               'evidence_complete': len(procedures) <= DETAIL_LIMIT,
                               'basis': 'Conservative unquoted CREATE PROCEDURE definitions; CALL references and literals are not definitions. These may remain unknown or conflicting in frozen classification.'},
            'unresolved_classifications': unresolved[:DETAIL_LIMIT], 'unresolved_count': len(unresolved),
            'unresolved_complete': len(unresolved) <= DETAIL_LIMIT,
            'basis': 'Mutually exclusive frozen file classifications. Definition counts are separate observed declarations; a file may contain multiple definitions. Missing classification stays Unknown.'}


def _entrypoints(doc, path, name, memberships):
    manifest = {'path': 'input/process-input.md', 'source_hash': doc.get('manifest_hash'), 'start_line': None, 'end_line': None}
    result = [{'kind': 'job_step', 'job': j, 'step': s, 'entry_program': p,
               'label': j + ('.' + s if s else ''), 'basis': 'Declared job/step or resolved directed dependency',
               'evidence': manifest} for j, s, p in sorted(memberships.get((path, name), set()))]
    for tx in doc.get('transactions', []):
        if tx['program'] == name:
            result.append({'kind': 'transaction', 'label': tx['id'], 'entry_program': tx['program'],
                           'mapset': tx.get('mapset'), 'map': tx.get('map'), 'basis': 'Declared transaction entry binding', 'evidence': manifest})
    return result


def _document(doc, asset, definition, memberships, classifications, replayed):
    analysis = doc.get('analysis') or {}
    name = definition['name']; path = asset['path']
    candidate = analysis.get('programs', {}).get(name)
    program = candidate if candidate and candidate['path'] == path else {}
    omitted = {r['id'] for r in program.get('omitted_rules', [])}
    rules = sorted(program.get('rules', []) + program.get('omitted_rules', []), key=lambda r: (r['source_start'], r['id']))
    saved = bool(doc.get('requirements'))
    items = []
    for rule in rules[:DETAIL_LIMIT]:
        returned = (replayed or {}).get((path, rule['id']))
        classification = classifications.get(rule['id'], {})
        no = rule['id'] in omitted
        items.append({'id': rule['id'], 'description': rule['plain'],
                      'category': classification.get('category', 'unclassified'),
                      'classification_basis': classification.get('reason', 'Business versus technical classification needs source-grounded validation.'),
                      'selection': 'No' if no else 'Yes' if saved else 'Yes (default, not saved)',
                      'status': 'excluded_by_requirements' if no else returned['status'] if returned else 'identified_unverified',
                      'reason': NO_REASON if no else 'Selected conversion requires actual target comparisons and review evidence.',
                      'evidence': _reference(asset, rule['source_start'], rule['source_end'])})
    fields = [{'name': key, **{k: field[k] for k in ('type', 'width', 'length', 'digits', 'scale', 'group', 'storage_section', 'source_ref') if k in field}}
              for key, field in sorted(program.get('fields', {}).items())]
    dependencies = [{k: dep[k] for k in ('path', 'kind', 'name', 'source_hash', 'lines') if k in dep}
                    for dep in program.get('dependencies', [])]
    lineage = doc.get('lineage') or {}
    nodes = {n['id']: n for n in lineage.get('nodes', [])}
    own = {n['id'] for n in nodes.values() if n.get('path') == path and n.get('kind') == 'program' and n.get('name') == name}
    links = [{'kind': edge['kind'], 'target': nodes.get(edge['target'], {}).get('name', edge['target']),
              'resolution': edge.get('resolution'), 'evidence': edge.get('evidence', [])[:3]}
             for edge in lineage.get('edges', []) if edge['source'] in own and edge['kind'] != 'defined_in']
    risks = [{k: item[k] for k in ('kind', 'message', 'path', 'lines') if k in item} for item in program.get('blockers', [])]
    selected = asset.get('selected', True)
    count_verified = sum(replayed.get((path, r['id']), {}).get('status') == 'converted_verified' for r in rules) if replayed is not None else None
    mapping = _entrypoints(doc, path, name, memberships)
    return {'id': 'program-' + sha(encode([path, name]))[:20], 'name': name,
            'kind': 'cobol_program', 'scope': 'SELECTED_PROCESS' if selected else 'OUTSIDE_SELECTED_PROCESS',
            'source': _reference(asset), 'definition': definition,
            'analysis_state': 'SOURCE_DERIVED' if program else 'NOT_SEMANTICALLY_ANALYZED',
            'functional_summary': (f'{len(rules)} modeled decisions, {len(fields)} parsed fields and {len(links)} observed dependency links. '
                                   'Business purpose and complete functionality require validated source interpretation.') if program else 'Business purpose and behavior remain unanalysed; source is retained in the inventory.',
            'entrypoints': mapping[:DETAIL_LIMIT], 'entrypoint_count': len(mapping), 'entrypoints_complete': len(mapping) <= DETAIL_LIMIT,
            'technical_spec': {'fields': fields[:DETAIL_LIMIT], 'field_count': len(fields), 'fields_complete': len(fields) <= DETAIL_LIMIT,
                               'dependencies': dependencies[:DETAIL_LIMIT], 'dependency_count': len(dependencies), 'dependencies_complete': len(dependencies) <= DETAIL_LIMIT,
                               'links': links[:DETAIL_LIMIT], 'link_count': len(links), 'links_complete': len(links) <= DETAIL_LIMIT,
                               'io_status': 'Parsed record layout and observed dependency links; physical I/O, encoding and transaction behavior need separate verified adapters.'},
            'rules': items, 'rules_complete': len(rules) <= DETAIL_LIMIT,
            'rule_counts': {'identified': len(rules) if program else None, 'selected': len(rules) - len(omitted) if program else None,
                            'excluded': len(omitted) if program else None, 'converted_verified': count_verified if program else None},
            'validation_requirements': ['Validate business purpose and business/technical rule classifications with source evidence and the one human review.',
                                        'Save default-Yes scope explicitly; excluded items retain their exact No reason.',
                                        'Execute at least 20 distinct randomized valid states per supported logic item, unit tests and adversarial checks.',
                                        'Compare actual target output against frozen source-derived expectations; preserve unsupported and unreachable obligations.'],
            'risks': risks[:DETAIL_LIMIT], 'risk_count': len(risks), 'risks_complete': len(risks) <= DETAIL_LIMIT,
            'personas': {'business': 'Review rule descriptions and selected scope; business intent is not inferred from syntax.',
                         'engineer': 'Inspect source hashes, record fields and dependency links before target changes.',
                         'assurance': 'Use replayed rule/coverage reports for verified conversion counts; this summary alone grants no conversion credit.'}}


def program_insights(doc, coverage=None, after=0, *, complete=False):
    """Read-only page; report generation may request the complete program index."""
    require(type(after) is int and after >= 0, 'Invalid program insights cursor')
    analysis = doc.get('analysis') or {}
    assets = sorted(analysis.get('assets', []), key=lambda a: a['path'])
    definitions = {a['path']: _definitions(a) for a in assets}
    from .rule_inventory import _memberships
    from .review import rule_classifications
    memberships = _memberships(doc, by_definition=True); classifications = rule_classifications(doc) if analysis else {}
    replayed = None
    if coverage is not None:
        from .rule_inventory import build_rule_inventory
        replayed = {(r['source_path'], r['source_rule_id']): r for r in build_rule_inventory(doc, coverage)['rules']}
    entries = [(a, item) for a in assets for item in definitions[a['path']].get('cobol_program', [])]
    require(after <= len(entries), 'Invalid program insights cursor')
    page = entries[after:] if complete else entries[after:after + PAGE_SIZE]
    # None distinguishes no replay from replayed zero verified rules.
    programs = [_document(doc, a, item, memberships, classifications, replayed) for a, item in page]
    return {'schema_version': 1, 'process_id': doc['id'], 'source_snapshot': analysis.get('source_snapshot'),
            'basis': 'SOURCE_DERIVED' if analysis else 'NOT_ANALYZED', 'boundary': BOUNDARY,
            'inventory': _inventory(analysis, assets, definitions), 'programs': programs,
            'program_total': len(entries) if analysis else None, 'after': after, 'next_after': after + len(programs),
            'has_more': after + len(programs) < len(entries), 'page_size': PAGE_SIZE,
            'verification_basis': 'REPLAYED_COVERAGE' if coverage is not None else 'NOT_REPLAYED',
            'related_reports': ['rules.html', 'coverage.html', 'factory.html']}


def render_program_insights(view):
    e = lambda value: escape('Unknown' if value is None else str(value))
    rows = ''.join('<tr><th>' + e(c['label']) + '</th><td>' + e(c['file_count']) + '</td><td>' + e(c['selected_file_count']) + '</td><td>' + e(c['definition_count']) + '</td></tr>' for c in view['inventory']['categories'])
    nav = ''.join('<li><a href="#' + e(p['id']) + '">' + e(p['name']) + ' · ' + e(p['source']['path']) + '</a></li>' for p in view['programs'])
    sections = []
    for p in view['programs']:
        src = p['source']
        rules = ''.join('<tr><td>' + e(r['description']) + '</td><td>' + e(r['category']) + '</td><td>' + e(r['selection']) + '</td><td>' + e(r['status']) + '<p>' + e(r['reason']) + '</p></td><td>' + e(r['evidence']['start_line']) + '–' + e(r['evidence']['end_line']) + '</td></tr>' for r in p['rules'])
        sections.append('<section id="' + e(p['id']) + '"><h2>' + e(p['name']) + '</h2><p>' + e(p['scope']) + ' · ' + e(src['path']) + ':' + e(src['start_line']) + '–' + e(src['end_line']) + '</p><p><code>SHA256 ' + e(src['source_hash']) + '</code></p><p>' + e(p['functional_summary']) + '</p><h3>Use-case entry mappings</h3><p>Entry mappings identify technical triggers; they do not invent business use cases.</p><ul>' + ''.join('<li>' + e(m['kind']) + ': ' + e(m['label']) + ' → ' + e(m['entry_program']) + '</li>' for m in p['entrypoints']) + '</ul><details><summary>Technical specification, validation and persona guidance</summary><pre>' + e(encode({k: p[k] for k in ('technical_spec', 'validation_requirements', 'risks', 'personas')}).decode()) + '</pre></details><h3>Business and technical rule observations</h3><p>' + e(p['rule_counts']['identified']) + ' identified · ' + e(p['rule_counts']['converted_verified']) + ' verified by replayed coverage.</p><table><tr><th>Source behavior</th><th>Classification</th><th>Selection</th><th>Conversion</th><th>Lines</th></tr>' + rules + '</table><p>Detail lists are bounded. Full source and rule accounting remain in the linked coverage and rules reports.</p></section>')
    return '<!doctype html><html lang="en"><meta charset="utf-8"><title>Program knowledge</title><style>body{font:16px system-ui;max-width:1100px;margin:2rem auto;padding:1rem}table{border-collapse:collapse;width:100%}td,th{border-bottom:1px solid #ccc;padding:.5rem;text-align:left}pre,code{white-space:pre-wrap;overflow-wrap:anywhere}section{margin-top:3rem}</style><h1>Program knowledge</h1><p>' + e(view['boundary']) + '</p><nav><a href="rules.html">Rule evidence</a> · <a href="coverage.html">Source coverage</a> · <a href="factory.html">Factory evidence</a></nav><h2>Retained application inventory</h2><p>' + e(view['inventory']['basis']) + '</p><table><tr><th>Type</th><th>Files</th><th>Selected files</th><th>Observed definitions</th></tr>' + rows + '</table><p>Observed unquoted Db2 procedure definitions: ' + e(view['inventory']['sql_procedures']['observed_definitions']) + '. Entire-estate total: Unknown. Recognition grants no adapter support.</p><nav aria-label="Program index"><ul>' + nav + '</ul></nav>' + ''.join(sections) + '</html>'
