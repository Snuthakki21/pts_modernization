"""Read-only, bounded presentation of an accepted rule inventory.

This module never executes source/target code or awards verification credit.
Diagnostics are frozen at report creation; filters use that same snapshot.
"""
import html
import json
import re
from bisect import bisect_left
from .domain import encode, sha, require
from .rule_inventory import CATEGORIES, STATUSES, _counts

GAP_STATUSES = {'identified', 'implemented_unverified', 'blocked'}
FILTERS = {'all', 'gaps', 'verified', 'excluded'}
EXCERPT_LIMIT = 2400
LABELS = {'converted_verified':'Verified at report acceptance', 'implemented_unverified':'Python candidate · unverified',
          'identified':'No implementation evidence', 'blocked':'Verification blocked',
          'excluded_by_requirements':'Selected No · intentionally omitted'}
BASIS = ('Frozen at accepted report generation. Verification inherits whole-program source-derived checks; '
         'filtering does not rerun tests or establish observed mainframe parity.')


def evidence_basis(model):
    return ('Frozen accepted evidence. Record logic uses whole-program checks; BMS character layout uses separately replayed source, unit, randomized, mutation and FastAPI checks. Layout credit does not verify native controller or data behavior. Source-derived tests do not establish observed mainframe parity.' if model.get('cics_contract_version')==1 else BASIS)


def program_key(program):
    return 'PROGRAM_' + sha(encode([program['program'], program['source_path'], program['source_version']]))[:24]


def _sme_facts(doc, item_id):
    answers=doc.get('answers') or {}; answer=(answers.get('items') or {}).get(item_id, {})
    return {'item_id':item_id, **{k:answer.get(k) for k in ('answer','correction','reviewer','group_id','kind','question')},
            'packet_hash':answers.get('packet_hash'), 'return_hash':answers.get('return_hash'),
            'credit_scope':'whole_program', 'packet_consumed':bool(doc.get('packet_imported'))}


SME_RESOLUTION=('Preserve the consumed human return and its correction. This remains unresolved under the one-packet contract; '
                'use a new authorized intake for changed source/requirements, never replace the return or issue another checklist for this process.')


def freeze_process_gates(doc, coverage):
    gates=[]
    for reason in coverage['summary'].get('integrity_errors', []):
        gates.append({'id':'PROCESS_'+sha(reason)[:24], 'scope':'process','kind':'integrity_gate','program':None,'source_rule_id':None,
                      'reason':reason, 'resolution':'Recover or resolve the named original evidence through the Coordinator; preserve immutable artifacts and unresolved human obligations. A plan or changed flag cannot restore credit.',
                      'facts':{},'evidence':[]})
    rule_ids={r['id'] for p in (doc.get('analysis') or {}).get('programs',{}).values() for r in p.get('rules',[])+p.get('omitted_rules',[])}
    for blocker in doc.get('blockers', []):
        rid=blocker.get('item_id')
        if blocker.get('kind')!='sme_unresolved' or rid in rule_ids:continue
        facts=_sme_facts(doc,rid);facts['credit_scope']='recorded_process_or_job_obligation'
        gates.append({'id':'PROCESS_'+sha(encode(blocker))[:24], 'scope':'process','kind':'sme_unresolved','program':None,'source_rule_id':rid,
                      'reason':blocker['message'], 'resolution':SME_RESOLUTION, 'facts':facts,
                      'evidence':['review/packet.json',('input/sme-return.html' if (doc.get('answers') or {}).get('return_format')=='html' else 'input/sme-return.xlsx')]})
    return gates


def freeze_program_gates(doc, programs):
    """Keep actual gate facts, scope and receipt locations; guidance is not proof."""
    analysis = (doc.get('analysis') or {}).get('programs', {})
    run = (doc.get('runs') or [{}])[-1]
    rows = []
    for entry in programs:
        name = entry['program']; program = analysis.get(name, {}); issues = []
        result = run.get('programs', {}).get(name)
        evidence = ([f"synthetic/{run['id']}/{name}/actual-and-comparison.json",
                     f"synthetic/{run['id']}/{name}/expected.json"] if result and run.get('id') else [])
        def issue(kind, reason, resolution, *, scope='program', rule=None, facts=None, refs=None):
            payload = {'kind':kind, 'scope':scope, 'program':name, 'source_rule_id':rule,
                       'reason':reason, 'facts':facts or {}, 'resolution':resolution, 'evidence':refs if refs is not None else evidence}
            payload['id'] = 'GATE_' + sha(encode([program_key(entry), payload]))[:24]
            if not any(prior['id']==payload['id'] for prior in issues): issues.append(payload)
        for blocker in program.get('blockers', []):
            if isinstance(blocker, dict):
                issue(blocker.get('kind', 'source_semantics'), blocker.get('message', str(blocker)),
                      'Implement and test a source-supported semantic replacement; refresh hash-bound analysis before requesting verification.',
                      facts={k:v for k,v in blocker.items() if k not in ('kind','message')}, refs=['analysis/source-analysis.json'])
        if result:
            coverage = result.get('coverage') or {}
            guidance = {
                'gaps':'Provide a source-derived witness for the named branch and compare the actual Python result; retain unreachable branches as explicit obligations.',
                'record_count_gaps':'Provide the required distinct valid randomized source states at rule execution and actual target comparisons. Duplicate padding cannot count. A source domain smaller than the requirement remains unverified under the current contract; a review flag cannot clear it.',
                'technical_record_count_gaps':'Provide the required distinct valid randomized complete records and target comparisons for this technical unit.',
                'correlation_gaps':'Provide both valid linked-file matching keys and intentional mismatches, with actual target comparisons.',
                'obligation_gaps':'Execute the named mandatory source boundary or negative-input witness against the actual target.'}
            for kind, resolution in guidance.items():
                for gap in coverage.get(kind, []):
                    rid = gap.get('rule_id')
                    issue(kind, gap.get('reason', gap.get('explanation', 'Recorded fixture obligation is unresolved')),
                          resolution, scope='rule' if rid else 'program', rule=rid,
                          facts={k:v for k,v in gap.items() if k not in ('reason','explanation','rule_id')})
            differences = result.get('differences') or []
            if differences:
                issue('target_difference', 'Actual target output differs from frozen source-derived expectations.',
                      'Inspect the named cases in the comparison receipt, correct the implementation or reviewed adapter, and rerun the immutable expectations.',
                      facts={'difference_count':len(differences), 'case_ids':[d.get('case_id') for d in differences[:20]],
                             'case_ids_complete':len(differences)<=20})
            adversarial = result.get('adversarial') or {}
            if adversarial.get('passed') is False:
                issue('adversarial_review', 'Recorded adversarial checks did not pass.',
                      'Resolve the surviving mutation or failed safety/accounting check named in the receipt and rerun adversarial verification.',
                      facts={'gaps':adversarial.get('gaps', [])[:20], 'gap_count':len(adversarial.get('gaps', [])),
                             'forbidden_import_rejected':adversarial.get('forbidden_import_rejected'),
                             'source_accounted':adversarial.get('source_accounted')})
            units = result.get('unit_tests') or {}
            if units.get('passed') is False:
                issue('unit_tests', 'Generated target comparison unit tests failed.',
                      'Correct the failures named in the generated unit-test receipt and rerun the actual target.',
                      facts={'tests_run':units.get('tests_run'), 'failures':units.get('failures'), 'errors':units.get('errors')},
                      refs=[v for v in (units.get('module'), units.get('receipt')) if v])
            if coverage.get('complete') is False:
                issue('program_coverage', 'Whole-program fixture coverage is incomplete; this prevents verification credit for the program.',
                      'Resolve every named fixture obligation in the expected/comparison receipts, then pass whole-program verification.',
                      facts={'branch_targets':coverage.get('branch_targets'), 'branches_observed':coverage.get('branches_observed'),
                             'minimum_distinct_records':coverage.get('min_records_per_logic')})
        # SME/stage/source gates retain the exact recorded message, without guessing a failing rule.
        owned_ids={r['id'] for r in program.get('rules',[])+program.get('omitted_rules',[])}
        for blocker in doc.get('blockers', []):
            rid = blocker.get('rule_id') or blocker.get('item_id')
            if blocker.get('program') != name and rid not in owned_ids: continue
            sme=blocker.get('kind')=='sme_unresolved'
            issue(blocker.get('kind', 'program_gate'), blocker.get('message', 'Recorded program gate remains unresolved'),
                  SME_RESOLUTION if sme else 'Resolve this recorded obligation using its source and receipt evidence, then refresh analysis and pass the Coordinator verification gates.',
                  scope='rule' if rid else 'program', rule=rid,
                  facts=_sme_facts(doc,rid) if sme else {k:v for k,v in blocker.items() if k not in ('kind','message','program','rule_id')},
                  refs=['review/packet.json',('input/sme-return.html' if (doc.get('answers') or {}).get('return_format')=='html' else 'input/sme-return.xlsx')] if sme else ['analysis/source-analysis.json'])
        rows.append({'key':program_key(entry), 'program':name, 'issues':issues})
    return rows


def _inventory(model):
    require(isinstance(model, dict) and type(model.get('schema_version')) is int and model['schema_version'] == 1, 'Unsupported accepted rule inventory schema')
    require(isinstance(model.get('process_id'), str) and isinstance(model.get('rules'), list), 'Accepted rule inventory identity or rules are missing')
    require('comparison_contract_version' not in model or type(model['comparison_contract_version']) is int and model['comparison_contract_version'] in (1,2), 'Unsupported comparison diagnostic contract')
    rules = model['rules']; ids = set()
    for rule in rules:
        require(isinstance(rule, dict), 'Malformed accepted rule')
        for field in ('id','source_rule_id','description','source_path','source_version','modernized_behavior'):
            require(isinstance(rule.get(field), str) and bool(rule[field]), 'Accepted rule is missing '+field)
        require(rule['id'] not in ids, 'Duplicate accepted rule identity'); ids.add(rule['id'])
        require(rule.get('status') in STATUSES and rule.get('category') in CATEGORIES, 'Unknown accepted rule status or category')
        require(isinstance(rule.get('source'), list) and bool(rule['source']), 'Accepted rule source span is missing')
        last = 0
        for line in rule['source']:
            require(isinstance(line,dict) and type(line.get('line')) is int and line['line'] > last and isinstance(line.get('text'),str), 'Malformed accepted source span')
            last = line['line']
        for field in ('targets','tests','evidence','reasons','memberships'):
            require(isinstance(rule.get(field), list), 'Accepted rule is missing '+field)
        require(all(isinstance(x,str) for x in rule['tests']+rule['reasons']), 'Malformed accepted rule tests or reasons')
        require(isinstance(rule.get('gap_reasons',[]),list) and all(isinstance(x,str) for x in rule.get('gap_reasons',[])), 'Malformed accepted gap reasons')
        require(all(isinstance(x,dict) for x in rule['evidence']+rule['memberships']), 'Malformed accepted evidence or memberships')
        for member in rule['memberships']:
            require(all(isinstance(member.get(k),str) for k in ('job','step','program')), 'Malformed accepted job membership')
        for target in rule['targets']:
            require(isinstance(target,dict) and all(isinstance(target.get(k),str) and target[k] for k in ('file','version'))
                    and type(target.get('start')) is int and type(target.get('end')) is int and 0 < target['start'] <= target['end']
                    and ('text' not in target or isinstance(target['text'],str)), 'Malformed accepted Python mapping')
        if rule['status'] == 'converted_verified':
            require(rule['category'] != 'unclassified' and rule['targets'] and rule['tests'] and rule['evidence'], 'Accepted verification credit lacks required evidence')
        require((rule['status']=='excluded_by_requirements') == bool(rule.get('requirements_excluded')), 'Accepted requirements exclusion is inconsistent')
    require(model.get('summary') == _counts(rules), 'Accepted rule totals differ from their evidence')
    require(isinstance(model.get('programs'),list), 'Accepted program ownership is missing')
    by_id = {r['id']:r for r in rules}; keys = set(); owned = set()
    for program in model['programs']:
        require(isinstance(program,dict) and all(isinstance(program.get(k),str) and program[k] for k in ('program','source_path','source_version')), 'Malformed accepted program identity')
        key=program_key(program); require(key not in keys, 'Duplicate accepted program identity'); keys.add(key)
        refs=program.get('rule_ids'); require(isinstance(refs,list) and all(isinstance(r,str) and r in ids for r in refs) and len(refs)==len(set(refs)), 'Accepted program rule ownership is invalid')
        require(program.get('counts')==_counts([by_id[r] for r in refs]), 'Accepted program totals differ from owned rules')
        owned.update(refs)
    diagnostic_owners={program_key(p):p['program'] for p in model['programs']}
    diagnostics=model.get('program_gates', [])
    require(isinstance(diagnostics,list), 'Malformed frozen program gates')
    seen=set()
    for entry in diagnostics:
        require(isinstance(entry,dict) and isinstance(entry.get('key'),str) and entry['key'] in keys and entry['key'] not in seen and entry.get('program')==diagnostic_owners[entry['key']] and isinstance(entry.get('issues'),list), 'Malformed frozen program gate ownership')
        seen.add(entry['key'])
        for issue in entry['issues']:
            require(isinstance(issue,dict) and issue.get('scope') in ('program','rule') and all(isinstance(issue.get(k),str) for k in ('id','kind','program','reason','resolution'))
                    and isinstance(issue.get('facts'),dict) and isinstance(issue.get('evidence'),list)
                    and all(isinstance(ref,str) for ref in issue['evidence']) and 'source_rule_id' in issue
                    and (issue['source_rule_id'] is None or isinstance(issue['source_rule_id'],str))
                    and issue['program']==entry.get('program')
                    and (issue['scope']!='rule' or bool(issue['source_rule_id'])), 'Malformed frozen program gate')
    require(isinstance(model.get('process_gates',[]),list), 'Malformed frozen process gates')
    for gate in model.get('process_gates',[]):
        require(isinstance(gate,dict) and gate.get('scope')=='process' and all(isinstance(gate.get(k),str) for k in ('id','kind','reason','resolution'))
                and isinstance(gate.get('facts'),dict) and isinstance(gate.get('evidence'),list) and all(isinstance(v,str) for v in gate['evidence'])
                and 'program' in gate and 'source_rule_id' in gate, 'Malformed frozen process gate')
    return rules, owned


def counts(rules):
    total=len(rules); verified=sum(r['status']=='converted_verified' for r in rules)
    excluded=sum(r['status']=='excluded_by_requirements' for r in rules)
    return {'total':total, 'selected':total-excluded, 'verified':verified, 'excluded':excluded,
            'gaps':sum(r['status'] in GAP_STATUSES for r in rules),
            'unclassified':sum(r['category']=='unclassified' for r in rules)}


def _clip(text, limit=EXCERPT_LIMIT):
    return text[:limit], len(text)<=limit


def _gate(issue):
    value={k:issue[k] for k in ('id','kind','scope','program','source_rule_id','reason','resolution','evidence','facts')}
    value['reason'], a = _clip(value['reason']); value['resolution'], b = _clip(value['resolution'])
    facts=json.dumps(value.pop('facts'), ensure_ascii=False, sort_keys=True)
    # Preserve numeric facts for UI/tests when small; an explicit bounded preview otherwise.
    if len(facts)>EXCERPT_LIMIT: value['facts']={'preview':facts[:EXCERPT_LIMIT], 'preview_complete':False}
    else: value['facts']=issue['facts']
    value['evidence']=value['evidence'][:12]; value['details_complete']=a and b and len(issue['evidence'])<=12 and len(facts)<=EXCERPT_LIMIT
    return value


def _source_gaps(rule, model, *, bounded=True, include_process=True):
    if rule['status'] not in GAP_STATUSES:return []
    # Successful line-level reasons are not a failure cause when a process gate withheld credit.
    reasons=rule.get('gap_reasons',rule['reasons'])
    process=model.get('process_gates',[])
    if 'gap_reasons' not in rule and process and rule['targets'] and rule['tests'] and rule['evidence']:
        reasons=[]
    resolution=('Identify and classify all retained behavior in this span and verify a source-supported replacement.' if rule['category']=='unclassified'
                else 'Resolve the recorded gate and supply version-bound Python mapping, target comparisons, required witnesses and review before a new accepted report.')
    if not reasons and not process:reasons=['The specific verification failure was not recorded for this span; inspect the frozen receipts.']
    output=[]
    for index, reason in enumerate(reasons[:8] if bounded else reasons):
        text,complete=_clip(reason) if bounded else (reason,True)
        output.append({'id':rule['id']+':'+str(index+1), 'scope':'affected_source_span',
                       'kind':'unclassified_source' if rule['category']=='unclassified' else 'coverage_gate',
                       'reason':text,'resolution':resolution,'details_complete':complete})
    if include_process:
        output.extend(_gate(g) for g in process[:4]) if bounded else output.extend(process)
    return output



# These are presentation qualifications, never an alternative verification oracle.
TRACEABILITY_BASIS = ('Source logic obligations and saved operator scope are distinct. '
                     'Links use the accepted source path, version and overlapping physical lines. '
                     'Target spans may satisfy multiple obligations; line counts are not complexity or equivalence. '
                     'Accepted source-derived verification does not establish observed mainframe parity.')


def _target_spans(rule):
    return {(t['file'],t['version'],t['start'],t['end']) for t in rule['targets']}


def _scope_index(model):
    """Index optional saved scope without trusting prose or guessed rule-name matches."""
    comparison=model.get('requirements_comparison')
    if comparison is None:return {}, None, None
    require(isinstance(comparison,dict) and isinstance(comparison.get('items'),list),
            'Malformed accepted requirements comparison')
    markdown=comparison.get('markdown');revision=comparison.get('revision')
    require(markdown is None or isinstance(markdown,str), 'Malformed accepted requirements Markdown reference')
    require(revision is None or type(revision) is int and revision>0, 'Malformed accepted requirements revision')
    index={};seen=set()
    for row in comparison['items']:
        require(isinstance(row,dict) and all(isinstance(row.get(k),str) and row[k] for k in ('id','kind','source_path','source_hash'))
                and type(row.get('selected')) is bool and row.get('status') in ('converted_verified','no_runtime_replacement_required','unverified','excluded_by_requirements')
                and type(row.get('start_line')) is int and type(row.get('end_line')) is int
                and 0<row['start_line']<=row['end_line'], 'Malformed accepted scope requirement')
        require(row['id'] not in seen, 'Duplicate accepted scope requirement identity');seen.add(row['id'])
        index.setdefault((row['source_path'],row['source_hash']),[]).append(row)
    for key, rows in list(index.items()):
        rows.sort(key=lambda row:(row['start_line'],row['end_line'],row['id']))
        ends=[];maximum=0
        for row in rows:maximum=max(maximum,row['end_line']);ends.append(maximum)
        index[key]=(rows,[row['start_line'] for row in rows],ends)
    return index,markdown,revision


def _scope_links(rule, index):
    entry=index.get((rule['source_path'],rule['source_version']))
    if entry is None:return []
    rows,starts,ends=entry;first=rule['source'][0]['line'];last=rule['source'][-1]['line']
    # Prefix maximum handles overlapping historical scope units without a full scan.
    start=bisect_left(ends,first);stop=bisect_left(starts,last+1)
    lines=[row['line'] for row in rule['source']];linked=[]
    for row in rows[start:stop]:
        witness=bisect_left(lines,row['start_line'])
        if witness<len(lines) and lines[witness]<=row['end_line']:linked.append(row)
    return linked


def _traceability_summary(rules, links):
    spans=set();requirements=set()
    for rule in rules:
        spans.update(_target_spans(rule));requirements.update(r['id'] for r in links[rule['id']])
    base=counts(rules)
    return {'source_units':base['total'],'identified_logic_units':base['total']-base['unclassified'],
            'unclassified_obligations':base['unclassified'],'selected':base['selected'],
            'excluded':base['excluded'],'verified_source_derived':base['verified'],
            'unmet_selected':base['gaps'],'target_mapping_links':sum(len(r['targets']) for r in rules),
            'unique_target_spans':len(spans),'linked_scope_requirements':len(requirements),
            'requirements_linked_units':sum(bool(links[r['id']]) for r in rules),
            'requirements_unlinked_units':sum(not links[r['id']] for r in rules),
            'observed_mainframe_parity':'Unknown'}


def _gap_class(kind):
    if kind in ('integrity_gate','evidence_integrity'):return 'evidence_integrity'
    if kind=='target_difference':return 'behavioral_difference'
    if kind in ('record_count_gaps','technical_record_count_gaps','correlation_gaps','obligation_gaps','gaps','program_coverage'):
        return 'validation_coverage'
    if kind in ('adversarial_review','unit_tests'):return 'validation_failure'
    if kind=='sme_unresolved':return 'human_review'
    if kind=='requirements_dependency':return 'selection_dependency'
    if kind in ('unclassified_source','source_semantics'):return 'source_semantics'
    return 'recorded_obligation'


def _qualify_gap(gap):
    return {**gap,'classification':_gap_class(gap['kind']),'closure_evidence':[gap['resolution']],
            'owner':'Unknown','risk':'Unknown'}



def _span_is_covered(rule, linked):
    """Physical-line coverage is linear in source lines and sorted scope links."""
    index=0
    for source in rule['source']:
        line=source['line']
        while index<len(linked) and linked[index]['end_line']<line:index+=1
        if index==len(linked) or linked[index]['start_line']>line:return False
    return True


def _traceability(rule, item, linked, markdown, revision):
    pinned=bool(isinstance(markdown,str) and re.fullmatch(r'analysis/requirements/[a-f0-9]{64}\.md',markdown) and revision)
    selected={row['selected'] for row in linked}
    expected=not rule.get('requirements_excluded')
    span_complete=_span_is_covered(rule,linked)
    selection=('Yes' if expected else 'No') if pinned and span_complete and selected=={expected} else 'Unknown'
    links=[{'id':row['id'],'kind':row['kind'],'selected':row['selected'],'status':row['status'],
            'source_start':row['start_line'],'source_end':row['end_line']} for row in linked[:20]]
    explanation={
        'converted_verified':'Accepted version-bound target mappings, tests and receipts satisfy the recorded source logic within the source-derived verification scope. The existing whole-program or separately replayed layout gates control this credit.',
        'implemented_unverified':'Target code is recorded, but the named accepted verification obligations remain unresolved. Implementation evidence alone does not establish satisfaction.',
        'identified':'This source obligation has no recorded target implementation; its behavior is not shown as satisfied.',
        'blocked':'The accepted report records unresolved source, verification or integrity obligations. A candidate replacement or plan cannot establish satisfaction.',
        'excluded_by_requirements':'Not converted because selected No in requirements. This is an explicit scope omission, not a successfully modernized requirement.'}[rule['status']]
    if rule['status']=='identified' and rule['targets']:
        explanation='The accepted report identifies this source obligation and retains candidate target mappings, but does not verify satisfaction.'
    elif rule['status']=='implemented_unverified' and not rule['targets']:
        explanation='The accepted report records an unverified candidate status, but no target mapping is available. Satisfaction remains unverified.'
    missing=[]
    def qualify(kind,reason,resolution):
        missing.append({'kind':kind,'reason':reason,'resolution':resolution,'owner':'Unknown','risk':'Unknown'})
    if not linked:qualify('scope_link_unknown','No saved scope unit is linked to this exact source version and span.',
                          'Inspect the accepted scope receipt; historical missing requirements remain Unknown, never infer approval from default selection.')
    elif not pinned:qualify('scope_snapshot_unknown','Linked scope units have no recorded Markdown/revision binding.',
                           'Inspect the accepted snapshot references. Preserve historical evidence; a current flag cannot manufacture the missing pin.')
    elif not span_complete:qualify('scope_span_incomplete','Saved scope links do not account for every recorded physical line in this source obligation.',
                                  'Inspect the exact frozen source span and saved scope receipt. Retain the unlinked lines as Unknown; do not infer a full selection from a partial overlap.')
    elif selected!={expected}:qualify('scope_selection_conflict','Linked saved scope selections disagree with this accepted source-unit disposition.',
                                     'Inspect the exact source/version spans and accepted scope receipt; do not infer Yes or alter frozen evidence.')
    if rule['status']=='implemented_unverified' and not rule['targets']:
        qualify('target_mapping_unknown','No version-bound target mapping is recorded for the accepted candidate status.',
                'Inspect the accepted target receipt and retain this missing mapping as unverified; a candidate label is not implementation evidence.')
    if rule['targets'] and any('text' not in target for target in rule['targets']):
        qualify('target_excerpt_unknown','Some target spans have version/location evidence but no recorded code excerpt.',
                'Inspect the exact registered target version. Do not display replacement guidance as actual target code.')
    if not rule['tests'] or not rule['evidence']:
        qualify('verification_receipt_unknown','Complete test identifiers and verification receipt references are not recorded for this source unit.',
                'Inspect the frozen comparison/test receipts; missing evidence cannot be replaced by prose or test counts.')
    item['requirement']={'id':rule['source_rule_id'],'inventory_id':rule['id'],
        'kind':'unclassified_source_obligation' if rule['category']=='unclassified' else 'source_logic_obligation',
        'selection':selection,'selection_basis':'Saved source-bound operator scope; it is not SME approval.' if selection!='Unknown' else 'Saved operator scope binding is Unknown.',
        'linked_requirements':links,'linked_requirement_count':len(linked),'links_complete':len(linked)<=20,
        'markdown':markdown,'revision':revision,'source_span_complete':span_complete,'sme_approval':'Unknown'}
    item['fulfillment']={'state':rule['status'],'explanation':explanation,'observed_mainframe_parity':'Unknown','owner':'Unknown','risk':'Unknown'}
    item['traceability_missing']=missing
    item['evidence_matrix']={
        'source':{'path':rule['source_path'],'version':rule['source_version'],'start':item['source_start'],'end':item['source_end'],'excerpt_complete':item['source_excerpt_complete']},
        'target':{'mapping_count':len(rule['targets']),'unique_span_count':len(_target_spans(rule)),
                  'preview_complete':item['targets_complete'],'excerpt_complete':all(t.get('excerpt_available') and t['excerpt_complete'] for t in item['targets']) and item['targets_complete']},
        'validation':{'test_count':len(rule['tests']),'evidence_count':len(rule['evidence']),
                      'preview_complete':item['tests_complete'] and item['evidence_complete'],'basis':'source_derived'},
        'diagnostics':{'recorded':item['diagnostics_recorded'],'gap_count':item['gap_count'],'program_gate_count':item['program_gate_count'],
                       'preview_complete':item['gaps_complete'] and item['program_gates_complete']},
        'requirements':{'linked_count':len(linked),'preview_complete':len(linked)<=20}}


def comparison_page(model, *, program='', status='all', after=0, limit=25):
    require(program=='' or isinstance(program,str), 'Invalid program filter')
    require(isinstance(status,str) and status in FILTERS, 'Unknown comparison status filter')
    require(type(after) is int and after>=0 and type(limit) is int and 1<=limit<=50, 'Comparison page bounds are invalid')
    rules, owned=_inventory(model)
    scope_index,markdown,revision=_scope_index(model)
    links={r['id']:_scope_links(r,scope_index) for r in rules}
    catalog=[]; by_id={r['id']:r for r in rules}; owners={r['id']:[] for r in rules}
    for entry in model['programs']:
        header={k:entry[k] for k in ('program','source_path','source_version')}
        header.update(key=program_key(entry), counts=counts([by_id[rid] for rid in entry['rule_ids']]),
                      traceability_summary=_traceability_summary([by_id[rid] for rid in entry['rule_ids']],links))
        catalog.append(header)
        for rid in entry['rule_ids']: owners[rid].append(header)
    selected=rules
    if program=='unassigned': selected=[r for r in rules if r['id'] not in owned]
    elif program:
        entry=next((p for p in model['programs'] if program_key(p)==program), None)
        require(entry is not None, 'Program is not in this accepted report')
        wanted=set(entry['rule_ids']); selected=[r for r in rules if r['id'] in wanted]
    scoped_counts=counts(selected)
    matching=[r for r in selected if status=='all' or status=='gaps' and r['status'] in GAP_STATUSES
              or status=='verified' and r['status']=='converted_verified'
              or status=='excluded' and r['status']=='excluded_by_requirements']
    require(after<=len(matching), 'Comparison page is beyond the matching evidence')
    gates={p['key']:p['issues'] for p in model.get('program_gates', [])}
    output=[]
    for rule in matching[after:after+limit]:
        item={k:rule[k] for k in ('id','source_rule_id','category','status','source_path','source_version')}
        item['description'], item['description_complete']=_clip(rule['description'])
        item['modernized_behavior'], item['behavior_complete']=_clip(rule['modernized_behavior'])
        item['source_start']=rule['source'][0]['line']; item['source_end']=rule['source'][-1]['line']
        item['source_excerpt'], item['source_excerpt_complete']=_clip('\n'.join(str(s['line'])+': '+s['text'] for s in rule['source']))
        item['targets']=[]
        for target in rule['targets'][:4]:
            text, complete=_clip(target.get('text',''))
            item['targets'].append({k:target[k] for k in ('file','version','start','end')} | {'text':text, 'excerpt_complete':complete, 'excerpt_available':'text' in target})
        item['target_count']=len(rule['targets']); item['targets_complete']=len(rule['targets'])<=4
        for field, cap in (('tests',20), ('evidence',12), ('reasons',8), ('memberships',12)):
            item[field]=rule[field][:cap]; item[field+'_count']=len(rule[field]); item[field+'_complete']=len(rule[field])<=cap
        item['programs']=[p['program'] for p in owners[rule['id']]]
        if 'cics_screens' in rule:item['cics_screens']=rule['cics_screens']
        item['gaps']=[]; item['gap_count']=0; item['gaps_complete']=True; item['program_gates']=[]
        if rule['status'] in GAP_STATUSES:
            item['gaps']=_source_gaps(rule,model)
            item['gap_count']=len(_source_gaps(rule,model,bounded=False))
            item['gaps_complete']=len(item['gaps'])==item['gap_count']
            issues=[g for p in owners[rule['id']] for g in gates.get(p['key'], [])]
            # The selected rule's actual deficits must survive a bounded preview.
            issues.sort(key=lambda g:0 if g.get('source_rule_id')==rule['source_rule_id'] and (rule.get('program') is None or g.get('program')==rule.get('program')) else 1 if g['scope']=='program' else 2)
            item['program_gates']=[_gate(g) for g in issues[:12]]
            item['program_gate_count']=len(issues); item['program_gates_complete']=len(issues)<=12
        else: item['program_gate_count']=0; item['program_gates_complete']=True
        item['diagnostics_recorded']=model.get('comparison_contract_version',0)>=2
        item['gaps']=[_qualify_gap(g) for g in item['gaps']]
        item['program_gates']=[_qualify_gap(g) for g in item['program_gates']]
        _traceability(rule,item,links[rule['id']],markdown,revision)
        output.append(item)
    return {'traceability_contract_version':1,'traceability_basis':TRACEABILITY_BASIS,
            'traceability_summary':_traceability_summary(selected,links),'inventory_traceability_summary':_traceability_summary(rules,links),
            'cics_contract_version':model.get('cics_contract_version'), 'process_id':model['process_id'], 'basis':evidence_basis(model), 'programs':catalog,
            'unassigned_count':sum(r['id'] not in owned for r in rules), 'inventory_counts':counts(rules),
            'counts':scoped_counts, 'process_gates':[_qualify_gap(_gate(g)) for g in model.get('process_gates',[])[:12]],
            'process_gate_count':len(model.get('process_gates',[])), 'process_gates_complete':len(model.get('process_gates',[]))<=12, 'filters':{'program':program, 'status':status}, 'matching_total':len(matching),
            'after':after, 'limit':limit, 'next_after':after+limit if after+limit<len(matching) else None, 'rules':output}


def render_comparison_report(model):
    """New HTML generations only; historical executive rendering stays unchanged."""
    from .rule_inventory import render_rule_summary
    rules, owned=_inventory(model)
    scope_index,markdown,revision=_scope_index(model)
    scope_links={r['id']:_scope_links(r,scope_index) for r in rules}
    esc=lambda value:html.escape(str(value), quote=True)
    options=''.join('<option value="'+program_key(p)+'">'+esc(p['program']+' · '+p['source_path'])+'</option>' for p in model['programs'])
    owners={r['id']:[] for r in rules}
    for program in model['programs']:
        for rid in program['rule_ids']:owners[rid].append(program_key(program))
    diagnostics={p['key']:p['issues'] for p in model.get('program_gates',[])}
    program_names={program_key(p):p['program'] for p in model['programs']}
    by_rule={}
    def issue_html(issue):
        return '<p><strong>'+esc(issue['program'])+' · '+esc(issue['scope'])+' gate'+(' · '+esc(issue['source_rule_id']) if issue['source_rule_id'] else '')+':</strong> '+esc(issue['reason'])+'</p><pre>'+esc(json.dumps(issue['facts'],ensure_ascii=False,sort_keys=True))+'</pre><p><strong>Evidence needed:</strong> '+esc(issue['resolution'])+'</p><p>Receipts: '+esc(', '.join(issue['evidence']))+'</p>'
    program_details=[]
    for key, issues in diagnostics.items():
        if not issues:continue
        for issue in issues:
            if issue['source_rule_id']:by_rule.setdefault((key,issue['source_rule_id']),[]).append(issue)
        program_details.append('<section id="gates-'+key+'"><details><summary>'+esc(program_names[key])+' · complete program and rule gates ('+str(len(issues))+')</summary><p>Complete accepted program evidence. Rule cards repeat only their own specific deficits; shared program failures remain here.</p>'+''.join(issue_html(issue) for issue in issues)+'</details></section>')
    cards=[]
    for rule in rules:
        location=rule['source_path']+':'+str(rule['source'][0]['line'])+'–'+str(rule['source'][-1]['line'])
        source='\n'.join(str(s['line'])+': '+s['text'] for s in rule['source'])
        targets=''
        for target in rule['targets']:
            targets+='<p>'+esc(target['file'])+':'+str(target['start'])+'–'+str(target['end'])+'</p><pre>'+esc(target.get('text','Target excerpt was not recorded in this historical report.'))+'</pre><small>Version '+esc(target['version'])+'</small>'
        if rule['status']=='excluded_by_requirements': targets='<p>'+esc(rule['modernized_behavior'])+'</p>'
        elif not targets:targets='<p>No Python implementation evidence is recorded for this span.</p>'
        gaps=''
        if rule['status'] in GAP_STATUSES:
            resolution=('Identify and classify all behavior in this span and verify its replacement.' if rule['category']=='unclassified'
                        else 'Resolve the recorded gate and pass version-bound target comparison and review before generating a new accepted report.')
            gaps='<div class="gap"><h3>Specific gap · '+esc(rule['id'])+'</h3><p><strong>Affected source:</strong> '+esc(location)+'</p>'
            gaps+=''.join('<p><strong>'+('Process-wide gate' if gap['scope']=='process' else 'Recorded reason')+':</strong> '+esc(gap['reason'])+'</p><p><strong>Evidence needed:</strong> '+esc(gap['resolution'])+'</p>' for gap in _source_gaps(rule,model,bounded=False,include_process=False))
            gaps+='<p><strong>Evidence needed:</strong> '+resolution+'</p>'
            issues=[issue for key in owners[rule['id']] for issue in by_rule.get((key,rule['source_rule_id']), [])]
            if issues:
                gaps+='<details><summary>Specific rule verification gates ('+str(len(issues))+')</summary>'+''.join(issue_html(issue) for issue in issues)+'</details>'
            for key in owners[rule['id']]:
                if diagnostics.get(key):gaps+='<p><a href="#gates-'+key+'">'+esc(program_names[key])+' · complete program and rule gates ('+str(len(diagnostics[key]))+')</a></p>'
            if model.get('process_gates'):gaps+='<p><a href="#process-gates">Process-wide gates ('+str(len(model['process_gates']))+')</a> also affect verification credit.</p>'
            if model.get('comparison_contract_version',0)<2:gaps+='<p>Additional fixture diagnostics were not recorded in this historical inventory. Inspect the referenced receipts.</p>'
            gaps+='</div>'
        proof_item={'source_start':rule['source'][0]['line'],'source_end':rule['source'][-1]['line'],'source_excerpt_complete':True,
                    'targets':[{'excerpt_available':'text' in t,'excerpt_complete':True} for t in rule['targets']],
                    'targets_complete':True,'tests_complete':True,'evidence_complete':True,
                    'diagnostics_recorded':model.get('comparison_contract_version',0)>=2,
                    'gap_count':len(_source_gaps(rule,model,bounded=False)),
                    'program_gate_count':sum(len(diagnostics.get(key,[])) for key in owners[rule['id']]) if rule['status'] in GAP_STATUSES else 0,
                    'gaps_complete':True,'program_gates_complete':True}
        _traceability(rule,proof_item,scope_links[rule['id']],markdown,revision)
        requirement=proof_item['requirement']
        scope_text=('; '.join(row['id']+' · '+('Yes' if row['selected'] else 'No') for row in scope_links[rule['id']]) or 'Unknown: no matching saved scope requirement')
        satisfaction='<section class="satisfaction"><h3>How the requirement is satisfied</h3><p>'+esc(proof_item['fulfillment']['explanation'])+'</p><p><strong>Source logic obligation:</strong> '+esc(rule['source_rule_id'])+' · '+esc(rule['id'])+'</p><p><strong>Saved scope requirement links:</strong> '+esc(scope_text)+'</p><p><strong>Saved selection:</strong> '+esc(requirement['selection'])+' · '+esc(requirement['selection_basis'])+'</p><p><strong>Observed mainframe parity:</strong> Unknown · <strong>Risk / accountable owner:</strong> Unknown</p>'
        if proof_item['traceability_missing']:
            satisfaction+='<details><summary>Traceability qualifications ('+str(len(proof_item['traceability_missing']))+')</summary>'+''.join('<p><strong>'+esc(g['kind'].replace('_',' '))+':</strong> '+esc(g['reason'])+'</p><p><strong>Evidence needed:</strong> '+esc(g['resolution'])+'</p>' for g in proof_item['traceability_missing'])+'</details>'
        satisfaction+='</section>'
        proofs=esc(json.dumps({'tests':rule['tests'],'evidence':rule['evidence'],'memberships':rule['memberships'],'evidence_matrix':proof_item['evidence_matrix']},ensure_ascii=False,sort_keys=True))
        cards.append('<article class="comparison" id="unit-'+esc(rule['id'])+'" data-status="'+rule['status']+'" data-owners="'+','.join(owners[rule['id']])+'"><details><summary><strong>'+esc(rule['description'])+'</strong> · '+LABELS[rule['status']]+'</summary><p>'+esc(rule['category'].replace('_',' '))+'</p><div class="columns"><section><h3>COBOL / source logic</h3><p>'+esc(location)+'</p><pre>'+esc(source)+'</pre><small>Source version '+esc(rule['source_version'])+'</small></section><section aria-label="Modernized implementation"><h3>Python / database replacement</h3>'+targets+'</section></div>'+satisfaction+gaps+'<details><summary>Versions, tests and evidence</summary><pre>'+proofs+'</pre></details></details></article>')
    unique=_traceability_summary(rules,scope_links)
    aggregate_rows=[];rules_by_id={rule['id']:rule for rule in rules}
    for program in model['programs']:
        selected=[rules_by_id[rid] for rid in program['rule_ids']]
        summary=_traceability_summary(selected,scope_links)
        aggregate_rows.append('<tr><th scope="row"><button type="button" data-program-key="'+program_key(program)+'">'+esc(program['program'])+'</button></th>'+''.join('<td>'+str(summary[key])+'</td>' for key in ('source_units','verified_source_derived','unmet_selected','excluded','unique_target_spans'))+'</tr>')
    aggregate='<section aria-labelledby="aggregate-title"><h2 id="aggregate-title">Gap analysis at a glance</h2><p>'+str(unique['source_units'])+' unique source units · '+str(unique['verified_source_derived'])+' verified in the source-derived scope · '+str(unique['unmet_selected'])+' selected units with gaps · '+str(unique['excluded'])+' selected No · '+str(unique['unique_target_spans'])+' unique target spans.</p><p>'+esc(TRACEABILITY_BASIS)+'</p><p>Select a program below, then expand an obligation for its exact source, target and evidence. Shared source units may appear under several programs; program totals must not be added as a process total.</p><div class="table-scroll"><table><caption>Accepted evidence by program</caption><thead><tr><th scope="col">Program</th><th scope="col">Source units</th><th scope="col">Verified</th><th scope="col">With gaps</th><th scope="col">Selected No</th><th scope="col">Target spans</th></tr></thead><tbody>'+''.join(aggregate_rows)+'</tbody></table></div></section>'
    style='body{font:16px Arial,Helvetica,sans-serif;line-height:1.5;color:#292724;background:#faf9f7;margin:0;overflow-wrap:anywhere}main{max-width:1160px;margin:auto;padding:32px}h1{font-size:30px;margin-bottom:8px}h2{font-size:20px}h3{font-size:16px}p{overflow-wrap:anywhere}small{overflow-wrap:anywhere;color:#57534e}.filters{display:flex;gap:12px;flex-wrap:wrap;align-items:end;margin:24px 0}label{display:grid;gap:6px;min-width:0;max-width:100%}select{min-width:0;width:100%;box-sizing:border-box}select,button{font:inherit;padding:10px;border:1px solid #c9c4bc;border-radius:6px;background:white;max-width:100%}button[aria-pressed=true]{background:#ad1625;color:white;border-color:#ad1625}.table-scroll{overflow-x:auto}button:focus-visible,select:focus-visible,summary:focus-visible{outline:3px solid #1d5a94;outline-offset:3px}.satisfaction{border-top:1px solid #ddd8d0;margin-top:20px}.comparison{background:white;border:1px solid #ddd8d0;border-radius:8px;padding:24px;margin:20px 0}.columns{display:grid;grid-template-columns:1fr 1fr;gap:24px}.columns section{min-width:0}pre{white-space:pre-wrap;overflow-wrap:anywhere;background:#f5f3ef;padding:16px;border-radius:4px;font-size:13px}details{margin-top:16px}summary{cursor:pointer;padding:6px 0}table{width:100%;table-layout:fixed;border-collapse:collapse}td,th{overflow-wrap:anywhere;padding:8px;text-align:left}.gap{border-left:3px solid #ad1625;padding:4px 16px;margin-top:20px;background:#fff8f7}[hidden]{display:none!important}@media(max-width:640px){main{padding:16px}.comparison{padding:16px}.columns{grid-template-columns:1fr}.filters{display:block}.filters>*{margin:8px 0;width:100%}}'
    script='''(()=>{const cards=[...document.querySelectorAll('.comparison')],program=document.getElementById('program'),buttons=[...document.querySelectorAll('[data-filter]')];let status='all';function update(){let selected=0,shown=0,verified=0,gaps=0,excluded=0;for(const card of cards){const owner=card.dataset.owners.split(',').filter(Boolean),inScope=!program.value||(program.value==='unassigned'?!owner.length:owner.includes(program.value)),s=card.dataset.status,isGap=['identified','implemented_unverified','blocked'].includes(s);if(inScope){selected++;verified+=s==='converted_verified';gaps+=isGap;excluded+=s==='excluded_by_requirements';}const visible=inScope&&(status==='all'||status==='gaps'&&isGap||status==='verified'&&s==='converted_verified'||status==='excluded'&&s==='excluded_by_requirements');card.hidden=!visible;shown+=visible;}for(const b of buttons)b.setAttribute('aria-pressed',String(b.dataset.filter===status));document.getElementById('count').textContent=shown+' shown / '+selected+' source units in this scope · '+verified+' verified · '+gaps+' gaps · '+excluded+' selected No';document.getElementById('empty').hidden=shown!==0;}for(const button of document.querySelectorAll('[data-program-key]'))button.addEventListener('click',()=>{program.value=button.dataset.programKey;status='all';update();program.focus();});program.addEventListener('change',update);for(const button of buttons)button.addEventListener('click',()=>{status=button.dataset.filter;update();});update();})();'''
    process_details=''
    if model.get('process_gates'):
        process_details='<details class="gap" id="process-gates"><summary>Process-wide gates ('+str(len(model['process_gates']))+')</summary><p>These obligations remain visible even when individual source units are verified.</p>'
        for gate in model['process_gates']:
            process_details+='<p><strong>Whole-process gate'+(' · '+esc(gate['source_rule_id']) if gate.get('source_rule_id') else '')+':</strong> '+esc(gate['reason'])+'</p><p><strong>Evidence needed:</strong> '+esc(gate['resolution'])+'</p><pre>'+esc(json.dumps({'facts':gate['facts'],'evidence':gate['evidence']},ensure_ascii=False,sort_keys=True))+'</pre>'
        process_details+='</details>'
    rollup=render_rule_summary({**model,'rules':[]})
    output = '<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>COBOL and Python comparison</title><style>'+style+'</style></head><body><main><h1>COBOL and Python comparison</h1><p>'+esc(evidence_basis(model))+'</p><p>Counts are unique source units; unclassified spans have unknown semantic rule counts. Shared copybooks can appear in more than one program.</p>'+aggregate+process_details+'<div class="filters"><label for="program">Program<select id="program"><option value="">All programs and source</option>'+options+'<option value="unassigned">Source outside parsed program ownership</option></select></label><div role="group" aria-label="Comparison status"><button type="button" data-filter="all" aria-pressed="true">All</button> <button type="button" data-filter="gaps" aria-pressed="false">Gaps only</button> <button type="button" data-filter="verified" aria-pressed="false">Verified</button> <button type="button" data-filter="excluded" aria-pressed="false">Selected No</button></div></div><p id="count" role="status">'+str(len(rules))+' source units in the accepted inventory.</p><noscript>All evidence is shown. Enable JavaScript to use filters.</noscript><p id="empty" hidden>No source units match these filters.</p>'+''.join(cards)+''.join(program_details)+'<details><summary>Full counts and requirements accounting</summary>'+rollup+'</details></main><script>'+script+'</script></body></html>'

    if model.get('cics_contract_version')==1:
        output=output.replace('COBOL and Python comparison','Mainframe and Python / FastAPI comparison').replace('COBOL / source logic','Mainframe / CICS source logic').replace('Python / database replacement','Python / FastAPI / database replacement')
    return output
