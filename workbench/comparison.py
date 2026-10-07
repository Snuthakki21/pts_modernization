"""Read-only, bounded presentation of an accepted rule inventory.

This module never executes source/target code or awards verification credit.
Diagnostics are frozen at report creation; filters use that same snapshot.
"""
import html
import json
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
                      'evidence':['review/packet.json','input/sme-return.xlsx']})
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
                  refs=['review/packet.json','input/sme-return.xlsx'] if sme else ['analysis/source-analysis.json'])
        rows.append({'key':program_key(entry), 'program':name, 'issues':issues})
    return rows


def _inventory(model):
    require(isinstance(model, dict) and model.get('schema_version') == 1, 'Unsupported accepted rule inventory schema')
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
    diagnostics=model.get('program_gates', [])
    require(isinstance(diagnostics,list), 'Malformed frozen program gates')
    seen=set()
    for entry in diagnostics:
        require(isinstance(entry,dict) and entry.get('key') in keys and entry['key'] not in seen and isinstance(entry.get('issues'),list), 'Malformed frozen program gate ownership')
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


def comparison_page(model, *, program='', status='all', after=0, limit=25):
    require(program=='' or isinstance(program,str), 'Invalid program filter')
    require(status in FILTERS, 'Unknown comparison status filter')
    require(type(after) is int and after>=0 and type(limit) is int and 1<=limit<=50, 'Comparison page bounds are invalid')
    rules, owned=_inventory(model)
    catalog=[]; by_id={r['id']:r for r in rules}; owners={r['id']:[] for r in rules}
    for entry in model['programs']:
        header={k:entry[k] for k in ('program','source_path','source_version')}
        header.update(key=program_key(entry), counts=counts([by_id[rid] for rid in entry['rule_ids']]))
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
        output.append(item)
    return {'process_id':model['process_id'], 'basis':BASIS, 'programs':catalog,
            'unassigned_count':sum(r['id'] not in owned for r in rules), 'inventory_counts':counts(rules),
            'counts':scoped_counts, 'process_gates':[_gate(g) for g in model.get('process_gates',[])[:12]],
            'process_gate_count':len(model.get('process_gates',[])), 'process_gates_complete':len(model.get('process_gates',[]))<=12, 'filters':{'program':program, 'status':status}, 'matching_total':len(matching),
            'after':after, 'limit':limit, 'next_after':after+limit if after+limit<len(matching) else None, 'rules':output}


def render_comparison_report(model):
    """New HTML generations only; historical executive rendering stays unchanged."""
    from .rule_inventory import render_rule_summary
    rules, owned=_inventory(model)
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
        proofs=esc(json.dumps({'tests':rule['tests'],'evidence':rule['evidence'],'memberships':rule['memberships']},ensure_ascii=False,sort_keys=True))
        cards.append('<article class="comparison" data-status="'+rule['status']+'" data-owners="'+','.join(owners[rule['id']])+'"><header><h2>'+esc(rule['description'])+'</h2><p>'+esc(rule['category'].replace('_',' '))+' · <strong>'+LABELS[rule['status']]+'</strong></p></header><div class="columns"><section><h3>COBOL / source logic</h3><p>'+esc(location)+'</p><pre>'+esc(source)+'</pre><small>Source version '+esc(rule['source_version'])+'</small></section><section aria-label="Modernized implementation"><h3>Python replacement</h3>'+targets+'</section></div>'+gaps+'<details><summary>Versions, tests and evidence</summary><p>Rule '+esc(rule['source_rule_id'])+' · '+esc(rule['id'])+'</p><pre>'+proofs+'</pre></details></article>')
    style='body{font:16px Arial,Helvetica,sans-serif;line-height:1.5;color:#292724;background:#faf9f7;margin:0;overflow-wrap:anywhere}main{max-width:1160px;margin:auto;padding:32px}h1{font-size:30px;margin-bottom:8px}h2{font-size:20px}h3{font-size:16px}p{overflow-wrap:anywhere}small{overflow-wrap:anywhere;color:#57534e}.filters{display:flex;gap:12px;flex-wrap:wrap;align-items:end;margin:24px 0}label{display:grid;gap:6px;min-width:0;max-width:100%}select{min-width:0;width:100%;box-sizing:border-box}select,button{font:inherit;padding:10px;border:1px solid #c9c4bc;border-radius:6px;background:white;max-width:100%}button[aria-pressed=true]{background:#ad1625;color:white;border-color:#ad1625}.comparison{background:white;border:1px solid #ddd8d0;border-radius:8px;padding:24px;margin:20px 0}.columns{display:grid;grid-template-columns:1fr 1fr;gap:24px}.columns section{min-width:0}pre{white-space:pre-wrap;overflow-wrap:anywhere;background:#f5f3ef;padding:16px;border-radius:4px;font-size:13px}details{margin-top:16px}summary{cursor:pointer}table{width:100%;table-layout:fixed;border-collapse:collapse}td,th{overflow-wrap:anywhere;padding:8px;text-align:left}.gap{border-left:3px solid #ad1625;padding:4px 16px;margin-top:20px;background:#fff8f7}[hidden]{display:none!important}@media(max-width:640px){main{padding:16px}.comparison{padding:16px}.columns{grid-template-columns:1fr}.filters{display:block}.filters>*{margin:8px 0;width:100%}}'
    script='''(()=>{const cards=[...document.querySelectorAll('.comparison')],program=document.getElementById('program'),buttons=[...document.querySelectorAll('[data-filter]')];let status='all';function update(){let selected=0,shown=0,verified=0,gaps=0,excluded=0;for(const card of cards){const owner=card.dataset.owners.split(',').filter(Boolean),inScope=!program.value||(program.value==='unassigned'?!owner.length:owner.includes(program.value)),s=card.dataset.status,isGap=['identified','implemented_unverified','blocked'].includes(s);if(inScope){selected++;verified+=s==='converted_verified';gaps+=isGap;excluded+=s==='excluded_by_requirements';}const visible=inScope&&(status==='all'||status==='gaps'&&isGap||status==='verified'&&s==='converted_verified'||status==='excluded'&&s==='excluded_by_requirements');card.hidden=!visible;shown+=visible;}for(const b of buttons)b.setAttribute('aria-pressed',String(b.dataset.filter===status));document.getElementById('count').textContent=shown+' shown / '+selected+' source units in this scope · '+verified+' verified · '+gaps+' gaps · '+excluded+' selected No';document.getElementById('empty').hidden=shown!==0;}program.addEventListener('change',update);for(const button of buttons)button.addEventListener('click',()=>{status=button.dataset.filter;update();});update();})();'''
    process_details=''
    if model.get('process_gates'):
        process_details='<details class="gap" id="process-gates"><summary>Process-wide gates ('+str(len(model['process_gates']))+')</summary><p>These obligations remain visible even when individual source units are verified.</p>'
        for gate in model['process_gates']:
            process_details+='<p><strong>Whole-process gate'+(' · '+esc(gate['source_rule_id']) if gate.get('source_rule_id') else '')+':</strong> '+esc(gate['reason'])+'</p><p><strong>Evidence needed:</strong> '+esc(gate['resolution'])+'</p><pre>'+esc(json.dumps({'facts':gate['facts'],'evidence':gate['evidence']},ensure_ascii=False,sort_keys=True))+'</pre>'
        process_details+='</details>'
    rollup=render_rule_summary({**model,'rules':[]})
    return '<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>COBOL and Python comparison</title><style>'+style+'</style></head><body><main><h1>COBOL and Python comparison</h1><p>'+esc(BASIS)+'</p><p>Counts are unique source units; unclassified spans have unknown semantic rule counts. Shared copybooks can appear in more than one program.</p>'+process_details+'<div class="filters"><label for="program">Program<select id="program"><option value="">All programs and source</option>'+options+'<option value="unassigned">Source outside parsed program ownership</option></select></label><div role="group" aria-label="Comparison status"><button type="button" data-filter="all" aria-pressed="true">All</button> <button type="button" data-filter="gaps" aria-pressed="false">Gaps only</button> <button type="button" data-filter="verified" aria-pressed="false">Verified</button> <button type="button" data-filter="excluded" aria-pressed="false">Selected No</button></div></div><p id="count" role="status">'+str(len(rules))+' source units in the accepted inventory.</p><noscript>All evidence is shown. Enable JavaScript to use filters.</noscript><p id="empty" hidden>No source units match these filters.</p>'+''.join(cards)+''.join(program_details)+'<details><summary>Full counts and requirements accounting</summary>'+rollup+'</details></main><script>'+script+'</script></body></html>'
