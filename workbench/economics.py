"""Evidence-bound pilot effort, provider units and conditional estate forecasts.

All quantities use decimal arithmetic. Framework effort, service duration, human
work and account billing are different measures, never interchangeable totals.
"""
from collections import defaultdict
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation, localcontext
import html
import re
from .domain import require, encode, sha, ValidationError
from .inventory import CATEGORY_KEYS

UNITS = ('process', *CATEGORY_KEYS)
STAGES = ('discovery', 'analysis', 'mainframe', 'conversion', 'sql', 'validation', 'review', 'reporting', 'rework', 'framework', 'pilot_total')
COUNTERS = ('input_tokens', 'output_tokens', 'cached_input_tokens', 'credits', 'premium_requests')
TERMINAL = {'COMPLETED', 'COMPLETED_WITH_BLOCKERS', 'CANCELLED'}


def decimal(value, label='quantity'):
    require(type(value) in (str, int, float) and len(str(value)) <= 64, 'Invalid '+label)
    try: result = Decimal(str(value))
    except InvalidOperation: result = Decimal('NaN')
    require(result.is_finite() and 0 <= result <= Decimal('1e15') and (result==0 or result>=Decimal('1e-30')), 'Invalid '+label)
    return result


def number(value):
    if value is None: return None
    with localcontext() as context:
        context.prec=100
        return format(value.quantize(Decimal('0.000001')), 'f').rstrip('0').rstrip('.') or '0'


def instant(value):
    require(isinstance(value, str) and len(value) <= 40, 'Timestamp must include timezone')
    try: dt = datetime.fromisoformat(value.replace('Z', '+00:00'))
    except ValueError: dt = None
    require(dt is not None and dt.tzinfo is not None and dt.utcoffset() is not None, 'Timestamp must include timezone')
    return dt.astimezone(timezone.utc)


def text(value, label):
    require(isinstance(value, str) and 0 < len(value.strip()) <= 500 and not any(ord(c) < 32 for c in value), 'Invalid '+label)
    return value


def fields(value, required, optional=()):
    require(isinstance(value, dict) and set(required) <= set(value) <= set(required)|set(optional), 'Missing or unsupported measurement fields')


def validate_plan(plan):
    fields(plan, ('cohorts',), ('capacity_hours_per_week', 'allocation_note'))
    require(isinstance(plan['cohorts'], list) and 1 <= len(plan['cohorts']) <= len(UNITS), 'Provide 1–9 forecast cohorts')
    ids=set(); units=set(); samples=set(); scopes=set()
    for row in plan['cohorts']:
        fields(row, ('id', 'unit', 'total'), ('hours_per_unit', 'sample_process_ids', 'process_ids', 'usage_per_unit'))
        text(row['id'], 'cohort ID'); require(row['id'] not in ids and isinstance(row['unit'],str) and row['unit'] in UNITS, 'Cohort ID must be distinct and unit must be recognized')
        if row['unit'] in units:require(row['unit']=='process' and all('process_ids' in c for c in plan['cohorts'] if c['unit']=='process'),'Repeated process cohorts require explicit disjoint process membership')
        ids.add(row['id']); units.add(row['unit'])
        require(type(row['total']) is int and 0 <= row['total'] <= 100000000, 'Cohort total must be a nonnegative integer')
        if 'hours_per_unit' in row:
            rates=row['hours_per_unit']; fields(rates, ('low', 'base', 'high'))
            values=[decimal(rates[k], k+' hours per unit') for k in ('low', 'base', 'high')]
            require(0 < values[0] <= values[1] <= values[2], 'Rate range must be positive and low <= base <= high')
        if 'usage_per_unit' in row:
            require(isinstance(row['usage_per_unit'],list) and len(row['usage_per_unit'])<=20,'Invalid AI rate list')
            keys=set()
            for rate in row['usage_per_unit']:
                fields(rate,('provider','account','unit','low','base','high'))
                for key in ('provider','account'):text(rate[key],key)
                require(isinstance(rate['unit'],str) and (rate['unit'] in COUNTERS or re.fullmatch(r'currency:[A-Z]{3}',rate['unit'])),'Invalid AI rate unit')
                identity=(rate['provider'],rate['account'],rate['unit']);require(identity not in keys,'Duplicate AI rate');keys.add(identity)
                require(decimal(rate['low'])<=decimal(rate['base'])<=decimal(rate['high']),'AI rate range must be ordered')
        if 'process_ids' in row:
            scope=row['process_ids']
            require(row['unit']=='process' and isinstance(scope,list) and len(scope)<=10000 and all(isinstance(p,str) for p in scope) and len(set(scope))==len(scope),'Scope must contain distinct process IDs')
            require(not scopes.intersection(scope),'Cohort process membership overlaps');scopes.update(scope)
            chosen=row.get('sample_process_ids',[])
            require(isinstance(chosen,list) and all(isinstance(p,str) for p in chosen),'Invalid calibration sample IDs')
            require(set(chosen)<=set(scope),'Calibration samples must belong to the declared cohort scope')
        if 'sample_process_ids' in row:
            pids=row['sample_process_ids']
            require(row['unit']=='process' and isinstance(pids,list) and 1<=len(pids)<=10000 and all(isinstance(p,str) for p in pids) and len(set(pids))==len(pids) and not samples.intersection(pids), 'Samples require distinct process IDs and process units')
            samples.update(pids)
    if len(plan['cohorts'])>1:
        require(not ('process' in units and len(units)>1), 'Do not add whole-process effort to asset effort')
        text(plan.get('allocation_note'), 'disjoint cohort-work allocation explanation')
    if 'capacity_hours_per_week' in plan: require(decimal(plan['capacity_hours_per_week']) > 0, 'Capacity must be positive')
    return plan


def validate_receipt(record, observed=False, as_of=None):
    common={'id','kind','process_id','evidence','recorded_by'}
    optional={'supersedes'}
    require(isinstance(record,dict) and isinstance(record.get('kind'),str), 'Measurement must be an object with a kind')
    kind=record['kind']
    extras={'work':({'stage','hours','started_at','ended_at','actor'}, {'complete'}),
            'usage':({'provider','account','model','started_at','ended_at','quantities'}, {'coverage'}),
            'budget':({'provider','account','unit','allowance','consumed','period_start','period_end','snapshot_at'}, set()),
            'plan':({'plan'}, set())}
    if observed: extras['provider_call']=({'provider','account','model','started_at','ended_at','counters'}, set())
    require(kind in extras, 'Unknown measurement kind')
    required, more=extras[kind]; fields(record, common|required, optional|more)
    require(isinstance(record['id'],str) and re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,119}',record['id']), 'Invalid receipt ID')
    require(record['process_id'] is None or isinstance(record['process_id'],str), 'Invalid receipt process')
    for key in ('evidence','recorded_by'): text(record[key],key)
    if 'supersedes' in record: text(record['supersedes'],'superseded receipt ID')
    current=instant(as_of) if as_of else datetime.now(timezone.utc)
    if kind in ('work','usage','provider_call'):
        start=instant(record['started_at']); end=instant(record['ended_at'])
        require(start <= end <= current, 'Measurement interval must be ordered and in the past')
    if kind=='work':
        require(isinstance(record['stage'],str) and record['stage'] in STAGES, 'Unknown work stage'); text(record['actor'],'actor')
        require(type(record.get('complete',False)) is bool,'Complete must be a boolean')
        hours=decimal(record['hours'],'work hours')
        if record['stage']!='pilot_total': require(hours <= Decimal(str((end-start).total_seconds()))/3600, 'Actor work hours exceed the interval')
        if record['process_id'] is None: require(record['stage']=='framework' and not record.get('complete'), 'Global work records are one-time framework investment')
        else: require(record['stage']!='framework', 'Framework investment must be recorded once at workspace scope')
        if record.get('complete'): require(record['stage']=='pilot_total' and hours>0, 'Complete effort requires an explicit whole-pilot total')
    if kind in ('usage','budget','provider_call'):
        for key in ('provider','account'): text(record[key],key)
    if kind in ('usage','provider_call'): text(record['model'],'model')
    if kind=='usage':
        require(isinstance(record['quantities'],dict),'Usage quantities must be an object')
        require(record.get('coverage','partial') in ('partial','complete_process'),'Unknown usage coverage')
        if record.get('coverage')=='complete_process':require(record['process_id'] is not None and set(record['quantities'])=={'credits'},'Complete process billing requires a process and a whole-pilot credits total for this provider/account')
        q=record['quantities']; require(isinstance(q,dict) and 0<len(q)<=10,'Provide actual usage quantities')
        for unit,value in q.items():
            require(unit in COUNTERS or re.fullmatch(r'currency:[A-Z]{3}',unit), 'Unsupported usage unit')
            quantity=decimal(value,unit)
            if unit.endswith('tokens') or unit=='premium_requests':require(quantity==quantity.to_integral_value(),'Token and request counts must be integers')
    if kind=='budget':
        require(record['process_id'] is None,'Account budgets belong to workspace scope')
        require(record['unit']=='credits', 'AI budgets use credits; tokens are not credit balances')
        decimal(record['allowance']); decimal(record['consumed'])
        require(instant(record['period_start']) <= instant(record['snapshot_at']) < instant(record['period_end']) and instant(record['snapshot_at']) <= current, 'Budget snapshot must fall inside its period and in the past')
    if kind=='plan':
        require(record['process_id'] is None,'Estate plans belong to workspace scope'); validate_plan(record['plan'])
    return record


def active_receipts(receipts):
    replaced={r['supersedes'] for r in receipts if r.get('supersedes')}
    return [r for r in receipts if r['id'] not in replaced]


def timing(doc, transitions, attempts, as_of):
    rows=[r for r in transitions if r['process_id']==doc['id']]
    current=instant(as_of); created=instant(doc['created'])
    # Without an initial READY transition, historical elapsed/status attribution
    # is incomplete. Do not use updated_at as a fabricated completion timestamp.
    complete=bool(rows and rows[0]['status']=='READY' and instant(rows[0]['created'])==created)
    end=current
    if doc['status'] in TERMINAL and rows and rows[-1]['status']==doc['status']: end=instant(rows[-1]['created'])
    elif doc['status'] in TERMINAL: complete=False
    buckets=defaultdict(Decimal); anomalies=[]
    for i,row in enumerate(rows):
        start=instant(row['created']); stop=instant(rows[i+1]['created']) if i+1<len(rows) else end
        if stop<start: anomalies.append('Wall clock moved backwards'); continue
        if row['status'] in TERMINAL and i+1==len(rows): continue
        status=row['status']
        group='terminal_idle' if status in TERMINAL else 'sme_wait' if status=='WAITING_SME' else 'agent_wait' if status=='WAITING_COPILOT' else 'discovery_wait' if status=='WAITING_DISCOVERY' else 'paused' if status=='PAUSED' else 'queue' if status.startswith('QUEUED_') or status=='READY' else 'stage_wall' if status in ('ANALYZING','VERIFYING','REPORTING') else 'other'
        buckets[group]+=Decimal(str((stop-start).total_seconds()))/3600
    stages=defaultdict(Decimal); failed=Decimal(0); unfinished=0; attempts_count=0
    for row in attempts:
        if row['process_id']!=doc['id']: continue
        attempts_count+=1
        if row['elapsed_seconds'] is None: unfinished+=1; continue
        value=decimal(row['elapsed_seconds'])/3600; stages[row['stage']]+=value
        if row['outcome']!='returned': failed+=value
    return {'elapsed_hours':number(Decimal(str(max(0,(end-created).total_seconds())))/3600) if complete and not anomalies else None,
            'status_hours':{k:number(v) for k,v in sorted(buckets.items())},'status_history_complete':complete and not anomalies,
            'service_hours':number(sum(stages.values(),Decimal(0))) if stages else None,
            'service_timings_complete':bool(complete and not anomalies and attempts_count and not unfinished),
            'service_by_stage':{k:number(v) for k,v in sorted(stages.items())}, 'nonreturning_attempt_hours':number(failed),
            'attempts':attempts_count,'unfinished_attempts':unfinished,'anomalies':anomalies,
            'boundary':'Service timings are monotonic observed execution, including I/O. Agent/SME waiting is wall time, not active work. Open attempts have unknown duration.'}


def work_summary(receipts, process_id):
    work=[r for r in receipts if r['kind']=='work' and r['process_id']==process_id]
    details=[r for r in work if r['stage']!='pilot_total']; totals=[r for r in work if r['stage']=='pilot_total']
    issues=[]; actors=defaultdict(list); stages=defaultdict(Decimal)
    for row in details:stages[row['stage']]+=decimal(row['hours'])
    for row in receipts:
        if row['kind']=='work' and row['stage']!='pilot_total':actors[row['actor']].append(row)
    for actor,rows in actors.items():
        ordered=sorted(rows,key=lambda r:instant(r['started_at']))
        active=[]
        for row in ordered:
            active=[r for r in active if instant(r['ended_at'])>instant(row['started_at'])]
            if active and (row['process_id']==process_id or any(r['process_id']==process_id for r in active)):issues.append('Overlapping work intervals for '+actor+' across recorded scopes')
            active.append(row)
    if len(totals)>1: issues.append('Multiple whole-pilot totals: supersede the previous receipt')
    total=totals[0] if len(totals)==1 else None
    detail_hours=sum(stages.values(),Decimal(0))
    if total and detail_hours>decimal(total['hours']): issues.append('Stage work exceeds whole-pilot total')
    return {'recorded_detail_hours':number(detail_hours) if details and not issues else None,
            'total_effort_hours':number(decimal(total['hours'])) if total else None,
            'complete':bool(total and total.get('complete') and not issues),
            'by_stage':{k:number(v) for k,v in sorted(stages.items())},'issues':issues,
            'basis':'Imported attributed work receipts; whole-pilot totals include stage work and must not be added to it.'}


def forecast(processes, receipts, plan, inventory):
    validate_plan(plan); receipts=active_receipts(receipts); rows=[]; totals={k:Decimal(0) for k in ('low','base','high')}; unknown=0
    eligible={p['id']:p for p in processes if p.get('status')=='COMPLETED' and p.get('report_verified') and p.get('measurement_report_intact',False)
              and not (p.get('requirements') or {}).get('excluded_ids') and not p.get('demo') and not p.get('fixture_only') and not p.get('blockers') and p.get('coverage_summary',{}).get('completion_eligible')}
    for cohort in plan['cohorts']:
        unit=cohort['unit']; selected=cohort.get('sample_process_ids',cohort.get('process_ids',list(eligible)))
        samples=[]; rejected=[]
        if unit=='process':
            for pid in selected:
                effort=work_summary(receipts,pid)
                if pid in eligible and effort['complete']: samples.append({'process_id':pid,'hours':effort['total_effort_hours']})
                else: rejected.append(pid)
        # Asset completion remains the existing verified, deduplicated ledger projection.
        completed=len([pid for pid in cohort.get('process_ids',list(eligible)) if pid in eligible]) if unit=='process' else next((r['cumulative_converted_count'] for r in inventory.get('rows',[]) if r.get('key')==unit),0)
        require(completed<=cohort['total'],'Forecast scope is smaller than recorded completed scope')
        remaining=cohort['total']-completed; rates=None; basis='UNESTIMATED'
        if 'hours_per_unit' in cohort: rates={k:decimal(v) for k,v in cohort['hours_per_unit'].items()}; basis='ASSUMPTION'
        elif samples:
            values=[decimal(s['hours']) for s in samples]; rates={'low':min(values),'base':sum(values)/len(values),'high':max(values)}; basis='OBSERVED_PILOT' if len(values)==1 else 'OBSERVED_SAMPLE_RANGE'
        effort={k:number(rates[k]*remaining) if rates else ('0' if remaining==0 else None) for k in totals}
        for key in totals:
            if effort[key] is not None: totals[key]+=Decimal(effort[key])
        if rates is None: unknown+=remaining
        ai=[{**{k:r[k] for k in ('provider','account','unit')},'basis':'ASSUMPTION','remaining':{k:number(decimal(r[k])*remaining) for k in totals}} for r in cohort.get('usage_per_unit',[])]
        if not ai and unit=='process':
            credit_groups=defaultdict(list)
            credit_totals,credit_issues=credit_coverage(receipts)
            for key,receipt in credit_totals.items():
                provider,account,pid=key
                if pid in eligible and pid in selected and key not in credit_issues:
                    credit_groups[(provider,account)].append((pid,decimal(receipt['quantities']['credits'])))
            for (provider,account),observations in sorted(credit_groups.items()):
                values=[v for _,v in observations]
                rates_ai={'low':min(values),'base':sum(values)/len(values),'high':max(values)}
                ai.append({'provider':provider,'account':account,'unit':'credits','basis':'ATTRIBUTED_COMPLETE_PILOT_CREDITS',
                           'sample_size':len(values),'pilot_ids':[pid for pid,_ in observations],
                           'remaining':{k:number(v*remaining) for k,v in rates_ai.items()},
                           'boundary':'Imported whole-pilot credit receipts for this provider/account only. Other accounts and missing billing coverage remain unknown; rates and future model mix can change.'})
        rows.append({**cohort,'completed_units':completed,'remaining_units':remaining,'sample_size':len(samples),'samples':samples,'excluded_samples':rejected,
                     'remaining_ai_usage':ai or None,'basis':basis,'provisional':True,'hours_per_unit':{k:number(v) for k,v in rates.items()} if rates else None,'remaining_effort_hours':effort})
    capacity=decimal(plan['capacity_hours_per_week']) if plan.get('capacity_hours_per_week') is not None else None
    return {'cohorts':rows,'unestimated_units':unknown,'estimated_subset_effort_hours':{k:number(v) for k,v in totals.items()},
            'remaining_effort_hours':{k:None if unknown else number(v) for k,v in totals.items()},
            'capacity_weeks':{k:number(v/capacity) if capacity and not unknown else None for k,v in totals.items()},
            'capacity_hours_per_week':number(capacity),'full_completion_commitment':False,
            'boundary':'Conditional capacity estimate, not a delivery date or parity commitment. Observed min/mean/max are sample descriptions, not confidence intervals. Scope mix, reuse, dependency bottlenecks, missing skills, waiting and future framework work can change delivery. Existing framework hours are excluded from repeatable rates.'}


def usage_conflicts(receipts):
    """Imported interval totals cannot be silently summed over the same scope."""
    groups=defaultdict(list);conflicts=set()
    for r in receipts:
        if r['kind']!='usage' or r.get('coverage')=='complete_process':continue
        for unit in r['quantities']:groups[(r['provider'],r['account'],r['model'],unit)].append(r)
    for key,rows in groups.items():
        active=[]
        for row in sorted(rows,key=lambda r:instant(r['started_at'])):
            active=[r for r in active if instant(r['ended_at'])>=instant(row['started_at'])]
            # Identical zero-length charge timestamps are duplicates too; touching
            # positive intervals are adjacent and can safely coexist.
            if any(instant(r['ended_at'])>instant(row['started_at']) or r['started_at']==row['started_at'] and r['ended_at']==row['ended_at'] for r in active):conflicts.add(key)
            active.append(row)
    return conflicts


def credit_coverage(receipts):
    groups=defaultdict(list); issues={}; totals={}
    for row in receipts:
        if row['kind']=='usage' and 'credits' in row['quantities']:
            groups[(row['provider'],row['account'],row['process_id'])].append(row)
    conflicts=usage_conflicts(receipts)
    for key,rows in groups.items():
        if any((r['provider'],r['account'],r['model'],'credits') in conflicts for r in rows):issues[key]='Overlapping imported credit intervals require reconciliation'
        complete=[r for r in rows if r.get('coverage')=='complete_process']
        if len(complete)>1:issues[key]='Conflicting complete pilot credit receipts';continue
        if complete:
            total=complete[0];partials=[r for r in rows if r is not total]
            if sum((decimal(r['quantities']['credits']) for r in partials),Decimal(0))>decimal(total['quantities']['credits']):issues[key]='Partial credits exceed whole-pilot total'
            if any(instant(r['started_at'])<instant(total['started_at']) or instant(r['ended_at'])>instant(total['ended_at']) for r in partials):issues[key]='Credit detail interval falls outside pilot total'
            totals[key]=total
    return totals,issues


def usage_summary(receipts, as_of, process_id=None):
    totals=defaultdict(Decimal); calls=defaultdict(int)
    complete_credits,credit_issues=credit_coverage(receipts);conflicts=usage_conflicts(receipts)
    for row in receipts:
        if process_id is not None and row['process_id']!=process_id: continue
        if row['kind']=='usage':
            for unit,value in row['quantities'].items():
                key=(row['provider'],row['account'],row['process_id'])
                if (row['provider'],row['account'],row['model'],unit) in conflicts:continue
                if unit=='credits' and (key in credit_issues or key in complete_credits and complete_credits[key]['id']!=row['id']):continue
                totals[(row['provider'],row['account'],row['model'],unit,'imported')]+=decimal(value)
        elif row['kind']=='provider_call':
            c=row['counters']
            for key in ('requests','responses','cache_hits','responses_with_usage','responses_without_usage'): calls[key]+=c.get(key,0)
            if c.get('responses_with_usage'):
                for key in ('input_tokens','output_tokens'):totals[(row['provider'],row['account'],row['model'],key,'observed')]+=decimal(c.get(key,0))
    budgets=[]
    groups=defaultdict(list)
    for r in receipts:
        if r['kind']=='budget':groups[(r['provider'],r['account'],r['unit'])].append(r)
    for key,records in groups.items():
        record=max(records,key=lambda r:instant(r['snapshot_at'])); snap=instant(record['snapshot_at']); end=instant(record['period_end'])
        since=Decimal(0); overlaps=0
        for r in receipts:
            if r['kind']!='usage' or (r['provider'],r['account'])!=key[:2] or key[2] not in r['quantities']:continue
            credit_key=(r['provider'],r['account'],r['process_id'])
            if key[2]=='credits':
                if credit_key in credit_issues:overlaps+=1;continue
                if credit_key in complete_credits and complete_credits[credit_key]['id']!=r['id']:continue
            start=instant(r['started_at']); stop=instant(r['ended_at'])
            if snap<=start and stop<end: since+=decimal(r['quantities'][key[2]])
            elif start < snap < stop or start < end <= stop:overlaps+=1
        remaining=decimal(record['allowance'])-decimal(record['consumed']); valid=instant(record['period_start'])<=instant(as_of)<end
        budgets.append({'receipt_id':record['id'],'provider':key[0],'account':key[1],'unit':key[2],'snapshot_at':record['snapshot_at'],
                        'allowance':number(decimal(record['allowance'])),'consumed_at_snapshot':number(decimal(record['consumed'])),
                        'remaining_at_snapshot':number(max(Decimal(0),remaining)),'overage_at_snapshot':number(max(Decimal(0),-remaining)),
                        'tracked_since_snapshot':number(since),'conditional_remaining':number(max(Decimal(0),remaining-since)) if valid and not overlaps else None,
                        'period_end':record['period_end'],'expired':not valid,'straddling_receipts':overlaps,
                        'basis':'Account-wide imported snapshot. Conditional remaining assumes no untracked usage; it is not a live balance.'})
    copilot=defaultdict(Decimal)
    for (provider,account,model,unit,provenance),value in totals.items():
        if provider.casefold().replace(' ','').replace('-','') in ('copilot','githubcopilot') and unit=='credits':copilot[(provider,account)]+=value
    credit_counts=[{'provider':provider,'account':account,'credits_used':number(value)} for (provider,account),value in sorted(copilot.items())]
    return {'quantities':[dict(zip(('provider','account','model','unit','provenance'),key),quantity=number(value)) for key,value in sorted(totals.items())],
            'copilot_credits':{'accounts':credit_counts,'status':'RECORDED' if credit_counts else 'UNKNOWN','basis':'Actual attributed credits receipts only. Count is recorded usage for this scope; no token-to-credit estimate or live account total is inferred.'},
            'provider_calls':dict(calls),'budgets':budgets,'issues':[{'provider':k[0],'account':k[1],'process_id':k[2],'message':v} for k,v in credit_issues.items()]+[{'provider':k[0],'account':k[1],'model':k[2],'unit':k[3],'message':'Overlapping imported usage is ambiguous; affected totals withheld'} for k in sorted(conflicts)], 'primary_budget_unit':'credits','billing_state':'IMPORTED_SNAPSHOTS' if budgets else 'UNKNOWN',
            'boundary':'Distinct providers, accounts and units are never converted or summed together. Host Claude/Copilot usage and allowance are unknown without receipts. Imported totals must exclude calls already observed by this workbench; cached calls incur no repeated token credit.'}


def economics_view(ledger, process_id=None, plan_override=None, as_of=None):
    from .ledger import now
    from .inventory import report_inventory, snapshot_inventory
    from .layout import output_path
    as_of=as_of or now(); records=ledger.measurements(); valid=[]; errors=[]
    for row in records:
        raw=encode(row['document'])
        if sha(raw)!=row['fingerprint']:errors.append(row['id']);continue
        if row['path']:
            path=output_path(ledger.root,row['process_id'],row['path'])
            if not path.is_file() or path.read_bytes()!=raw:errors.append(row['id']);continue
        valid.append(row['document'])
    receipts=active_receipts(valid); processes=ledger.list(True)
    selected=next((p for p in processes if p['id']==process_id),None)
    require(process_id is None or selected is not None,'Process not found')
    # The report fingerprints, not a status label alone, qualify calibration.
    for p in processes:
        hashes=p.get('report_hashes',{})
        p['measurement_report_intact']=bool(hashes) and all((path:=output_path(ledger.root,p['id'],name)).is_file() and sha(path.read_bytes())==digest for name,digest in hashes.items())
    inventory=report_inventory(selected or {'id':'portfolio','demo':True,'inventory_baseline':snapshot_inventory(ledger.root)},
                               [p for p in processes if p['measurement_report_intact'] and not p.get('fixture_only')])
    transitions,attempts=ledger.measurement_timing()
    plans=[r for r in receipts if r['kind']=='plan']
    plan=plan_override or (plans[-1]['plan'] if plans else None)
    learning=[]
    for p in processes:
        if p.get('demo') or p.get('fixture_only'):continue
        history=timing(p,transitions,attempts,as_of); work=work_summary(receipts,p['id'])
        accepted=not (p.get('requirements') or {}).get('excluded_ids') and p['status']=='COMPLETED' and p.get('report_verified') and p['measurement_report_intact'] and not p.get('blockers') and p.get('coverage_summary',{}).get('completion_eligible')
        analysis=p.get('analysis') or {}; coverage=p.get('coverage_summary') or {}
        learning.append({'process_id':p['id'],'status':p['status'],'eligible_completed_pilot':bool(accepted),
            'effort_calibration_eligible':bool(accepted and work['complete']),
            'source_snapshot':analysis.get('source_snapshot'),'source_files':len(p.get('source_files',{})),
            'capability_kinds':sorted({r.get('kind','unknown') for r in analysis.get('classifications',{}).values()}),
            'dependency_nodes':len(p.get('lineage',{}).get('nodes',[])),
            'requirements_excluded_units':len((p.get('requirements') or {}).get('excluded_ids',[])),
            'jobs':len(p.get('jobs',[])),'programs':len(analysis.get('programs',{})),
            'rules':len(analysis.get('rules',[])),'applicable_lines':coverage.get('applicable_lines'),
            'verified_lines':coverage.get('verified_applicable_lines'), 'artifact_count':len(p.get('artifacts',[])),
            'artifact_types':dict(sorted(__import__('collections').Counter(__import__('pathlib').PurePosixPath(path).suffix for path in p.get('artifacts',[])).items())),
            'verification_runs':len(p.get('runs',[])),'open_gaps':len(p.get('blockers',[])),
            'service_hours':history['service_hours'],'elapsed_hours':history['elapsed_hours'],
            'pilot_effort_hours':work['total_effort_hours'],'by_stage':history['service_by_stage'],
            'unfinished_attempts':history['unfinished_attempts'],'service_timings_complete':history['service_timings_complete'],
            'calibration_boundary':'Evidence is learned automatically; incomplete effort, unsupported scope, fixtures and changed reports cannot establish a completed-pilot conversion rate.'})
    measured=[]
    for p in processes:
        if process_id and p['id']!=process_id:continue
        measured.append({'process_id':p['id'],'status':p['status'],'demo':bool(p.get('demo') or p.get('fixture_only')),
                         'work':work_summary(receipts,p['id']),'timing':timing(p,transitions,attempts,as_of)})
    projection=None;forecast_errors=[]
    if plan and not errors:
        try:projection=forecast(processes,receipts,plan,inventory)
        except ValidationError as exc:
            if plan_override is not None:raise
            forecast_errors.append(str(exc))
    result={'schema_version':1,'as_of':as_of,'process_id':process_id,'processes':measured,'framework':work_summary(receipts,None),
            'usage':usage_summary(receipts,as_of,process_id),'forecast':projection,'forecast_errors':forecast_errors,
            'work_sessions':[{k:v for k,v in r.items() if k!='document'}|{'process_id':r['document']['process_id'],'actor':r['document']['actor'],'stage':r['document']['stage']} for r in ledger.work_sessions() if not r['receipt_id'] or r['receipt_id']=='UNMEASURED'],
            'learning':learning[-50:],'learning_count':len(learning),'learning_truncated':len(learning)>50,'plan':plan,'receipt_count':len(records),'receipt_ids':[r['id'] for r in receipts], 'integrity_errors':errors,
            'inventory_baseline':{k:inventory.get(k) for k in ('declared_total','category_total','unreconciled_count','baseline_status')},
            'boundary':'Measured service durations and imported work effort are separate. Unknown historical work is not zero. Forecasts never change conversion credit or bypass review, verification or source coverage gates.'}
    if errors:
        for budget in result['usage']['budgets']:budget['conditional_remaining']=None
        result['usage']['issues'].append({'provider':'measurement ledger','account':'workspace','message':'Corrupt or missing measurement evidence; conditional balance withheld'})
    if result['forecast']:
        for cohort in result['forecast']['cohorts']:
            if cohort['unit']!='process':continue
            candidates=[p for p in learning if p['eligible_completed_pilot'] and p['process_id'] in cohort.get('sample_process_ids',cohort.get('process_ids',[x['process_id'] for x in learning]))]
            projections={}
            for field in ('service_hours','elapsed_hours'):
                values=[decimal(p[field]) for p in candidates if p[field] is not None and (field!='service_hours' or p['service_timings_complete'])]
                projections[field]={'sample_size':len(values),'pilot_ids':[p['process_id'] for p in candidates if p[field] is not None and (field!='service_hours' or p['service_timings_complete'])],
                    'remaining_sequential_hours':{k:number(rate*cohort['remaining_units']) for k,rate in {'low':min(values),'base':sum(values)/len(values),'high':max(values)}.items()} if values else None}
            cohort['observed_component_projections']=projections
            cohort['component_boundary']='Automatic service and elapsed projections are separate from complete work effort. Elapsed includes waiting; sequential projections assume comparable processes and no parallelism. They must not be added together.'
    return result


def render_economics(model):
    esc=lambda x:html.escape(str(x if x is not None else 'Unknown'),quote=True)
    def table(headers,rows):
        return '<table><thead><tr>'+''.join('<th>'+esc(x)+'</th>' for x in headers)+'</tr></thead><tbody>'+''.join('<tr>'+''.join('<td>'+esc(x)+'</td>' for x in row)+'</tr>' for row in rows)+'</tbody></table>'
    pilot_rows=[(p['process_id'],p['status'],p['timing']['elapsed_hours'],p['timing']['service_hours'],p['work']['total_effort_hours'],p['work']['complete'],p['demo']) for p in model['processes']]
    usage=model['usage'];forecast=model.get('forecast');warnings=model['integrity_errors']+model.get('forecast_errors',[])
    warnings.extend(row['message'] for row in usage['issues'])
    for process in model['processes']:warnings.extend(process['work']['issues'])
    contents='<h1>Pilot effort and estate forecast</h1><p>As of '+esc(model['as_of'])+'</p><p>'+esc(model['boundary'])+'</p>'
    contents+=''.join('<p class="boundary">Unresolved measurement: '+esc(w)+'</p>' for w in warnings)
    contents+=table(('Process','Status','Elapsed hours','Service hours','Pilot effort hours','Effort complete','Demonstration'),pilot_rows)
    contents+='<h2>One-time framework investment</h2><p>Recorded hours: '+esc(model['framework']['recorded_detail_hours'])+'. Service duration, work effort and elapsed waiting must not be added together.</p>'
    credits=usage.get('copilot_credits',{}).get('accounts',[])
    contents+='<h2>GitHub Copilot credits used</h2>'+ (table(('Account','Recorded credits used'),[(r['account'],r['credits_used']) for r in credits]) if credits else '<p>Unknown: no actual credits receipt for this scope.</p>')
    contents+='<h2>AI credits and observed usage</h2><p>Credits are the budget unit. Tokens do not establish credit charges.</p>'
    contents+=table(('Provider','Account','Model','Unit','Recorded amount','Provenance'),[(r['provider'],r['account'],r['model'],r['unit'],r['quantity'],r['provenance']) for r in usage['quantities']]) if usage['quantities'] else '<p>Recorded usage: Unknown.</p>'
    contents+=table(('Provider / account','Snapshot','Allowance (credits)','Consumed','Remaining at snapshot','Conditional remaining','Period ends'),[(r['provider']+' / '+r['account'],r['snapshot_at'],r['allowance'],r['consumed_at_snapshot'],r['remaining_at_snapshot'],r['conditional_remaining'],r['period_end']) for r in usage['budgets']]) if usage['budgets'] else '<p>Credit allowance and remaining balance: Unknown.</p>'
    contents+='<p>'+esc(usage['boundary'])+' Account snapshots are dated; conditional remaining assumes no untracked charges.</p><h2>Remaining estate</h2>'
    if forecast:
        contents+=table(('Cohort / unit','Completed','Remaining','Pilot sample','Basis','Low hours','Base hours','High hours'),[(r['id']+' / '+r['unit'],r['completed_units'],r['remaining_units'],r['sample_size'],r['basis'],*[r['remaining_effort_hours'][k] for k in ('low','base','high')]) for r in forecast['cohorts']])
        contents+='<p>Remaining effort range: '+esc(forecast['remaining_effort_hours']['low'])+'–'+esc(forecast['remaining_effort_hours']['high'])+' hours; base '+esc(forecast['remaining_effort_hours']['base'])+'. Base capacity weeks: '+esc(forecast['capacity_weeks']['base'])+'. Unestimated units: '+esc(forecast['unestimated_units'])+'.</p><p>'+esc(forecast['boundary'])+'</p>'
        credits=[(c['id'],r['provider'],r['account'],r['unit'],r['basis'],r.get('sample_size'),*[r['remaining'][k] for k in ('low','base','high')]) for c in forecast['cohorts'] for r in c.get('remaining_ai_usage') or []]
        contents+=table(('Cohort','Provider','Account','Unit','Basis','Sample','Low','Base','High'),credits) if credits else '<p>Remaining AI credits: Unknown until complete pilot billing or an explicit credit rate is available.</p>'
    else:contents+='<p>Unknown: provide estate quantities, comparable pilot evidence or explicit rates, and available capacity.</p>'
    contents+='<h2>Migration evidence used for learning</h2><p>Completed, intact, non-demo pilots qualify by measure. Blocked processes and incomplete measurements remain visible. Sample sizes are descriptive; representative scope still needs to be established.</p>'
    contents+=table(('Process','Status','Jobs','Programs','Rules','Artifacts','Verification runs','Open gaps','Effort eligible'),[(r['process_id'],r['status'],r['jobs'],r['programs'],r['rules'],r['artifact_count'],r['verification_runs'],r['open_gaps'],r['effort_calibration_eligible']) for r in model['learning']])
    contents+='<details><summary>Measurement provenance, work stages and assumptions</summary><pre>'+esc(__import__('json').dumps(model,indent=2))+'</pre></details>'
    return '<!doctype html><meta charset="utf-8"><title>Pilot effort and estate forecast</title><style>body{font:16px system-ui;margin:2rem;max-width:1150px}td,th{padding:.5rem;text-align:left;border-bottom:1px solid #ddd}table{border-collapse:collapse;max-width:100%}pre{white-space:pre-wrap;overflow-wrap:anywhere}.boundary{background:#fff2db;padding:.7rem}</style>'+contents
