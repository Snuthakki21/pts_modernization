"""A report projection over replayed coverage, never a second conversion oracle."""
from collections import defaultdict
import csv
import html
import json
import re
from pathlib import Path
from .domain import encode, sha, safe_path, require

CATEGORIES = ('business_rule', 'technical_logic', 'unclassified')
STATUSES = ('identified', 'implemented_unverified', 'converted_verified', 'blocked', 'excluded_by_requirements')
VERIFIED = {'mapped_verified', 'platform_replaced_verified'}


def _counts(rules):
    result = {}
    for category in CATEGORIES:
        selected = [r for r in rules if r['category'] == category]
        counts = {status: sum(r['status'] == status for r in selected) for status in STATUSES}
        counts['total'] = len(selected)
        counts['selected']=len(selected)-counts['excluded_by_requirements']
        counts['verification_percent'] = round(100 * counts['converted_verified'] / counts['selected'], 2) if counts['selected'] else None
        result[category] = counts
    return result


def _memberships(doc, *, by_definition=False):
    """Traverse directed edges; optionally attribute only reached program definitions.

    File accounting remains the default. Definition keys prevent unrelated
    compilation units in the same retained file from inheriting an entrypoint.
    """
    result = defaultdict(set)
    lineage = doc.get('lineage') or {}
    nodes = {n['id']: n for n in lineage.get('nodes', [])}
    outgoing = defaultdict(list)
    for edge in lineage.get('edges', []):
        if edge.get('resolution', 'resolved') != 'resolved': continue
        if edge['kind'] in {'calls', 'executes', 'invokes_proc', 'includes', 'contains_step', 'selects_job', 'manifest_step', 'defined_in', 'copies', 'sql_includes', 'dd_member', 'dd_instream_data', 'dd_dataset'}:
            outgoing[edge['source']].append(edge['target'])
    programs = (doc.get('analysis') or {}).get('programs', {})
    for job in doc.get('jobs', []):
        for step in job['steps']:
            member = (job['name'], step['name'], step['program'])
            seeds = [n['id'] for n in nodes.values() if n.get('name', '').upper() == step['program'].upper() and n.get('kind') in {'program', 'proc', 'utility'}]
            seen = set(); pending = list(seeds)
            while pending:
                ident = pending.pop()
                if ident in seen: continue
                seen.add(ident); node = nodes.get(ident, {})
                if node.get('path') and (not by_definition or node.get('kind') == 'program'):
                    key = (node['path'], node['name']) if by_definition else node['path']
                    result[key].add(member)
                pending.extend(outgoing[ident])
            program = programs.get(step['program'])
            if program:
                key = (program['path'], step['program']) if by_definition else program['path']
                result[key].add(member)
                if not by_definition:
                    for dep in program.get('dependencies', []):
                        if dep.get('path'): result[dep['path']].add(member)
        if by_definition: continue
        # Job cards and utility/control dependencies belong to the job itself.
        seeds = [n['id'] for n in nodes.values() if n.get('kind') in {'job', 'manifest_job'} and n.get('name', '').upper() == job['name'].upper()]
        seen = set(); pending = list(seeds)
        while pending:
            ident = pending.pop()
            if ident in seen: continue
            seen.add(ident); node = nodes.get(ident, {})
            if node.get('path') and not any(m[0] == job['name'] for m in result[node['path']]):
                result[node['path']].add((job['name'], '', ''))
            pending.extend(outgoing[ident])
    return result


def build_rule_inventory(doc, coverage, root=None):
    programs = (doc.get('analysis') or {}).get('programs', {})
    by_path = {p['path']: (name, p) for name, p in programs.items()}
    memberships = _memberships(doc)
    program_memberships = _memberships(doc, by_definition=True)
    from .review import rule_classifications
    classifications = rule_classifications(doc)
    identified = {}; modeled = {}; original = {}
    for name, program in programs.items():
        original[program['path']] = {r['line']: r['disposition'] for r in program.get('coverage', [])}
        for rule in program['rules']+program.get('omitted_rules',[]):
            key = (program['path'], rule['id']); identified[key] = rule
            for number in range(rule['source_start'], rule['source_end'] + 1): modeled[program['path'], number] = key
    cics_units={}
    for descriptor in (doc.get('analysis') or {}).get('cics',{}).get('units',[]):
        for number in range(descriptor['start_line'],descriptor['end_line']+1):cics_units[descriptor['source_path'],number]=descriptor
    groups = {}; last_unknown = {}; target_cache = {}; jcl_context = {}
    for row in coverage['rows']:
        path=row['source_path']
        if row['source_kind']=='jcl_job':
            declaration=re.match(r'//([A-Z][A-Z0-9]{0,7})\s+JOB\b',row['source_text'].strip(),re.I)
            if declaration:jcl_context[path]=declaration[1].upper()
        if row['disposition'] in {'non_executable', 'out_of_scope'} and (not row.get('requirements_excluded') or row.get('requirement_kind') in ('blank','comment','structure','paragraph')): continue
        path = row['source_path']; number = row['source_line']; key = modeled.get((path, number))
        if key:
            rule = identified[key]
            # Historical packets called these business rules. New intake requires
            # an explicit, source-bound category, surfaced in the human packet.
            default = 'unclassified' if doc.get('sme_packet_version', 1) >= 4 else 'business_rule'
            category = classifications.get(rule['id'], {}).get('category', default)
            description = rule['plain']; identity = rule['id']
            basis = classifications.get(rule['id'], {}).get('reason', 'Historical business-rule designation' if default == 'business_rule' else 'Classification not yet evidenced')
        elif (path,number) in cics_units:
            descriptor=cics_units[path,number];identity='cics:'+str(descriptor['start_line'])+':'+descriptor['kind'];key=(path,identity)
            category='technical_logic';description=descriptor['description'];basis='Source-bound BMS field/layout or native controller obligation; controller behavior is never inferred from layout verification'
        elif row.get('requirements_excluded'):
            key=(path,row['requirement_id']);category='technical_logic' if row.get('requirement_kind') in ('data_layout','copybook','terminal') else 'unclassified';identity=row['requirement_id']
            description='Excluded source unit';basis='Explicit operator scope in saved requirements Markdown'
        elif original.get(path, {}).get(number) in {'data_layout', 'copybook', 'terminal'} or row['source_kind'] in {'copybook', 'jcl_job', 'jcl_proc'} and row['target_mappings']:
            key = (path, row['unit_id']); category = 'technical_logic'; identity = row['unit_id']
            description = row.get('replacement') or row['reason']; basis = 'Replayed layout, return or job adapter mapping'
        else:
            # A contiguous unknown span is an obligation, not an invented rule
            # for every unsupported physical line.
            scope=(path,jcl_context.get(path))
            previous = last_unknown.get(scope)
            key = previous[1] if previous and previous[0] == number - 1 else (path, 'unclassified:' + str(number))
            last_unknown[scope] = (number, key)
            category = 'unclassified'; identity = key[1]
            description = 'Unclassified source behavior; semantic rule count is unknown'
            basis = 'Unparsed span retained without inventing rule granularity'
        require(category in CATEGORIES, 'Unknown rule category')
        item = groups.setdefault(key, {'id': 'RULE_' + sha(encode([path, row['source_hash'], identity]))[:24],
            'source_rule_id': identity, 'category': category, 'description': description, 'classification_basis': basis,
            'program': by_path.get(path, (None,))[0], 'source_path': path, 'source_version': row['source_hash'],
            'requirements_excluded':row.get('requirements_excluded',False), 'source': [], 'targets': [], 'tests': set(), 'evidence': [], 'reasons': set(), '_gap_reasons':set(), '_dispositions': [],
            'memberships': [{'job': j, 'step': s, 'program': p} for j, s, p in sorted(memberships[path]) if path not in jcl_context or j.upper()==jcl_context[path]]})
        descriptor=cics_units.get((path,number))
        if descriptor:
            if descriptor['kind']=='screen_action':
                bindings=descriptor.get('bindings',[descriptor])
                screens=[screen for screen in doc['analysis']['cics']['screens'] if descriptor.get('program') in screen['owners'] and any(binding.get('mapset')==screen['mapset'] and binding.get('map')==screen['map'] for binding in bindings)]
            else:
                screens=[screen for screen in doc['analysis']['cics']['screens'] if screen['source_path']==path and (not descriptor.get('map') or screen['map']==descriptor['map'])]
            item['cics_screens']=sorted({screen['mapset']+'/'+screen['map'] for screen in screens})
            item['cics_programs']=([descriptor['program']] if descriptor.get('program') else sorted({owner for screen in screens for owner in screen['owners']}))
            if descriptor.get('program'):item['program']=descriptor['program']
        item['source'].append({'line': number, 'text': row['source_text']})
        item['_dispositions'].append(row['disposition']); item['tests'].update(row['tests']); item['reasons'].add(row['reason'])
        if row['disposition'] not in VERIFIED:item['_gap_reasons'].add(row['reason'])
        for value in row.get('evidence', []):
            if value not in item['evidence']: item['evidence'].append(value)
        for target in row['target_mappings']:
            value = dict(target)
            if root is not None:
                filename = target['file']
                if filename not in target_cache:
                    target_path=Path(filename)
                    if target_path.is_absolute():
                        from . import reference
                        require(target_path==Path(reference.__file__).resolve(),'Unrecognized external adapter mapping')
                    else:target_path=safe_path(Path(root),filename)
                    raw = target_path.read_bytes()
                    require(sha(raw) == target['version'], 'Rule target differs from coverage version')
                    target_cache[filename] = raw.decode('utf-8').splitlines()
                value['text'] = '\n'.join(target_cache[filename][target['start']-1:target['end']])
            if value not in item['targets']: item['targets'].append(value)
    rules = []
    for item in groups.values():
        dispositions = item.pop('_dispositions')
        verified = item['category'] != 'unclassified' and item['targets'] and item['tests'] and item['evidence'] and all(d in VERIFIED for d in dispositions) and not coverage['summary']['integrity_errors']
        item['status'] = 'excluded_by_requirements' if item['requirements_excluded'] else 'converted_verified' if verified else 'blocked' if 'blocked' in dispositions or coverage['summary']['integrity_errors'] or item['category'] == 'unclassified' else 'implemented_unverified' if item['targets'] else 'identified'
        from .requirements import NO_REASON
        item['modernized_behavior'] = NO_REASON if item['requirements_excluded'] else item['description'] if item['targets'] else 'Not implemented'
        item['gap_reasons']=sorted(item.pop('_gap_reasons'))
        item['tests'] = sorted(item['tests']); item['reasons'] = sorted(item['reasons']); rules.append(item)
    def rollup(key, selected):
        return {**key, 'counts': _counts(selected), 'rule_ids': [r['id'] for r in selected],
                'invocation_memberships': sum(len(r['memberships']) for r in selected)}
    job_rows = []
    for job in doc.get('jobs', []):
        selected = [r for r in rules if any(m['job'] == job['name'] for m in r['memberships'])]
        row = rollup({'job': job['name']}, selected)
        row['invocation_memberships'] = sum(sum(m['job'] == job['name'] for m in r['memberships']) for r in selected)
        job_rows.append(row)
    rules_by_path=defaultdict(list)
    for rule in rules:rules_by_path[rule['source_path']].append(rule)
    program_rows=[]
    for name,p in programs.items():
        owned={p['path']} | {d['path'] for d in p.get('dependencies',[]) if d.get('path')}
        for field in p.get('fields',{}).values():
            if field.get('source_ref'):owned.add(field['source_ref'].rsplit(':',1)[0])
        if (doc.get('analysis') or {}).get('cics_contract_version')==1:
            owned.update(screen['source_path'] for screen in doc['analysis']['cics']['screens'] if name in screen['owners'])
        selected=[r for path in sorted(owned) for r in rules_by_path[path] if (doc.get('analysis') or {}).get('cics_contract_version')!=1 or (name in r['cics_programs'] if 'cics_programs' in r else r.get('program') in (None,name))]
        row=rollup({'program':name,'source_path':p['path'],'source_version':p['source_hash']},selected)
        reached=program_memberships[p['path'],name]
        row['invocation_memberships']=sum(sum((m['job'],m['step'],m['program']) in reached for m in r['memberships']) for r in selected)
        program_rows.append(row)
    rules_by_id={r['id']:r for r in rules}
    job_programs=[]
    for job in job_rows:
        for program in program_rows:
            reached={member for member in program_memberships[program['source_path'],program['program']] if member[0]==job['job']}
            selected=[rules_by_id[rid] for rid in program['rule_ids'] if any((m['job'],m['step'],m['program']) in reached for m in rules_by_id[rid]['memberships'])]
            if selected:
                row=rollup({'job':job['job'],'program':program['program']},selected)
                row['invocation_memberships']=sum(sum((m['job'],m['step'],m['program']) in reached for m in r['memberships']) for r in selected)
                job_programs.append(row)
    from .requirements import comparison
    from .comparison import freeze_program_gates, freeze_process_gates
    result = {'comparison_contract_version':2, 'process_gates':freeze_process_gates(doc,coverage), 'program_gates':freeze_program_gates(doc,program_rows), 'requirements_comparison':comparison(doc,coverage), 'schema_version': 1, 'process_id': doc['id'], 'rules': rules, 'job_programs':job_programs, 'summary': _counts(rules),
            'jobs': job_rows, 'programs': program_rows,
            'unassigned_rule_ids': [r['id'] for r in rules if not r['memberships']],
            'basis': 'Unique source-version rule occurrences; job totals deduplicate repeated invocations. Unclassified spans are obligations, not a known count of semantic rules. Selected No units remain in original totals and are excluded from requested-scope conversion percentages. Verification inherits replayed whole-program coverage. Source-derived evidence is not observed mainframe parity.'}
    if (doc.get('analysis') or {}).get('cics_contract_version')==1:
        result['cics_contract_version']=1
        result['basis']=result['basis'].replace('Verification inherits replayed whole-program coverage.', 'Record logic inherits replayed whole-program coverage; BMS character layouts have separately replayed unit, randomized, mutation and FastAPI gates. Layout credit does not verify native controller or data behavior.')
    return result


def _cell(value):
    text = json.dumps(value, ensure_ascii=False, sort_keys=True) if isinstance(value, (dict, list)) else str(value)
    if re.search(r'[\x00-\x08\x0b\x0c\x0e-\x1f]',text):text=json.dumps(text,ensure_ascii=True)
    return "'" + text if text.lstrip().startswith(('=', '+', '-', '@')) else text


def add_workbook(book, model):
    """Use chunk rows to preserve large source/target excerpts without cell loss."""
    from .coverage import _utf16_chunks
    for title, rows, identity in [('Job Summary', model['jobs'], 'job'), ('Program Summary', model['programs'], 'program')]:
        sheet = book.create_sheet(title); sheet.append([identity, 'Category', 'Total', *STATUSES, 'Verified percent'])
        for row in rows:
            for category, counts in row['counts'].items():
                sheet.append([_cell(row[identity]), category, counts['total'], *[counts[s] for s in STATUSES], counts['verification_percent']])
        sheet.freeze_panes = 'C2'
    sheet=book.create_sheet('Job Program Summary');sheet.append(['Job','Program','Category','Total',*STATUSES])
    for row in model.get('job_programs',[]):
        for category,counts in row['counts'].items():sheet.append([_cell(row['job']),_cell(row['program']),category,counts['total'],*[counts[s] for s in STATUSES]])
    headers = ['Rule ID', 'Source rule', 'Program', 'Category', 'Status', 'Description', 'Jobs / steps', 'Source file', 'Source version', 'Chunk', 'Original source', 'Modernized implementation', 'Tests', 'Reasons']
    sheets = {c: book.create_sheet(t) for c, t in zip(CATEGORIES, ['Business Rules', 'Technical Logic', 'Unclassified'])}
    mapping = book.create_sheet('Rule Mapping'); mapping.append(['Rule ID', 'Chunk', 'Source', 'Targets', 'Verification evidence'])
    for sheet in sheets.values(): sheet.append(headers); sheet.freeze_panes = 'F2'
    for rule in model['rules']:
        fields = [rule['source'], rule['targets'] or rule['modernized_behavior'], rule['tests'], rule['reasons'], rule['memberships'], rule['description'], rule['evidence']]
        chunks = [list(_utf16_chunks(_cell(v), 28000)) for v in fields]
        for n in range(max(map(len, chunks))):
            parts = [_cell(c[n]) if n < len(c) else '' for c in chunks]
            sheets[rule['category']].append([rule['id'], rule['source_rule_id'], _cell(rule['program'] or ''), rule['category'], rule['status'], parts[5], parts[4], _cell(rule['source_path']), rule['source_version'], n+1, parts[0], parts[1], parts[2], parts[3]])
            mapping.append([rule['id'], n+1, parts[0], parts[1], parts[6]])


def write_inventory(model, root):
    root = Path(root)
    from .domain import write_new
    write_new(root/'rules.json', encode(model))
    with (root/'rules.csv').open('x', encoding='utf-8', newline='') as output:
        writer = csv.writer(output); columns = ['id', 'category', 'program', 'description', 'status', 'memberships', 'source_path', 'source_version', 'source', 'targets', 'tests', 'reasons', 'modernized_behavior', 'evidence']
        writer.writerow(columns)
        for row in model['rules']: writer.writerow([_cell(row[c]) for c in columns])
    return [root/'rules.json', root/'rules.csv']


def render_rule_summary(model):
    esc = lambda v: html.escape(str(v), quote=True)
    columns = ['Job / Program', 'Business total / verified', 'Technical total / verified', 'Unverified', 'Blocked', 'Selected No', 'Unclassified spans']
    body = []
    for label, counts in [('Process unique total', model['summary'])] + [(r['job'], r['counts']) for r in model['jobs']] + [(r['job']+' / '+r['program'],r['counts']) for r in model.get('job_programs',[])] + [(r['program'], r['counts']) for r in model['programs']]:
        values = [label, str(counts['business_rule']['total'])+' / '+str(counts['business_rule']['converted_verified']), str(counts['technical_logic']['total'])+' / '+str(counts['technical_logic']['converted_verified']), sum(c['implemented_unverified'] for c in counts.values()), sum(c['blocked'] for c in counts.values()), sum(c['excluded_by_requirements'] for c in counts.values()), counts['unclassified']['total']]
        body.append('<tr>'+''.join('<td>'+esc(v)+'</td>' for v in values)+'</tr>')
    details = []
    for r in model['rules']:
        source = '\n'.join(str(s['line'])+': '+s['text'] for s in r['source'])
        targets = '\n\n'.join(t['file']+':'+str(t['start'])+'-'+str(t['end'])+'\n'+t.get('text','') for t in r['targets']) or r['modernized_behavior']
        details.append('<details><summary>'+esc(r['id']+' · '+r['category']+' · '+r['status'])+'</summary><p>'+esc(r['description'])+'</p><p>'+esc(r['source_path']+' · '+json.dumps(r['memberships']))+'</p><h3>Original source</h3><pre>'+esc(source)+'</pre><h3>Modernized implementation</h3><pre>'+esc(targets)+'</pre><p>Evidence: '+esc(json.dumps(r['evidence']))+'</p><p>Tests: '+esc(', '.join(r['tests']))+'</p><p>'+esc('; '.join(r['reasons']))+'</p></details>')
    comparison=model.get('requirements_comparison',{});units=[]
    for r in comparison.get('items',[]):
        units.append('<details><summary>'+esc(r['source_path']+':'+str(r['start_line'])+'–'+str(r['end_line'])+' · '+r['status'])+'</summary><p>'+esc(r['description'])+'</p><pre>'+esc(r['source_excerpt'])+'</pre><p>Source SHA256: '+esc(r['source_hash'])+'</p><p>'+esc(r['commentary'])+'</p><p>Replacement ('+esc(r['replacement_status'])+'): '+esc(r['replacement'])+'</p><p>Targets: '+esc(json.dumps(r['targets']))+'</p><p>Evidence: '+esc(json.dumps(r['evidence']))+'</p><p>Tests: '+esc(', '.join(r['tests']))+'</p></details>')
    unit_report='<h2>Complete source breakdown and replacements</h2><p>'+esc(comparison.get('basis',''))+'</p><p>Saved requirements: '+esc(comparison.get('markdown') or 'Historical full scope')+'</p>'+''.join(units)
    return '<section><h2>Rules by job and program</h2><p>'+esc(model['basis'])+'</p><table><thead><tr>'+''.join('<th scope="col">'+esc(c)+'</th>' for c in columns)+'</tr></thead><tbody>'+''.join(body)+'</tbody></table><h2>Original versus modernized rules</h2>'+''.join(details)+(unit_report if comparison.get('items') else '')+'</section>'
