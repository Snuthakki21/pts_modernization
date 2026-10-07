"""Deterministic source-driven boundaries, interactions and linked record groups."""
import itertools
import ast
import copy
import random
from .domain import encode, sha, require
from .reference import run_reference, input_errors, predicate
from .target import run_generated, prepare_generated, rule_nodes, layout_nodes


def comparisons(node):
    if not isinstance(node,dict) or 'field' in node:return []
    return comparisons(node['left'])+comparisons(node['right']) if node['op'] in ('AND','OR') else [node]


def plan_cases(program, seed=21, budget=256, min_records_per_logic=0, fixture_contract_version=None):
    """Replay historical suites; new intake pins v4 and its runtime-generated seed."""
    require(fixture_contract_version is None or type(fixture_contract_version) is int and
            fixture_contract_version in (1,3,4), 'Unsupported fixture contract version')
    if fixture_contract_version == 4:
        require(type(min_records_per_logic) is int and min_records_per_logic == 20,
                'V4 requires at least 20 distinct randomized records per logic')
        require(type(seed) is int and 0 <= seed < 2**63, 'V4 seed must be an unsigned 63-bit integer')
        return _plan_cases_v3(program, seed, budget, min_records_per_logic, version=4)
    require(fixture_contract_version != 1 or not min_records_per_logic,
            'Historical V1 fixture contract has no multiplicity policy')
    require(fixture_contract_version != 3 or bool(min_records_per_logic),
            'V3 fixture contract requires a multiplicity policy')
    require(min_records_per_logic is None or type(min_records_per_logic) is int and
            (min_records_per_logic == 0 or 10 <= min_records_per_logic <= 20),
            'Minimum distinct records per logic must be zero (historical) or 10 to 20')
    if min_records_per_logic:
        return _plan_cases_v3(program, seed, budget, min_records_per_logic)
    return _plan_cases_legacy(program, seed, budget)


def _plan_cases_legacy(program, seed=21, budget=256, max_budget=256):
    require(type(budget) is int and 1<=budget<=max_budget,'Case budget must be between 1 and '+str(max_budget))
    if program.get('target_contract_version') == 2:
        # Ledger JSON canonicalization must not alter the frozen case order.
        program={**program,'fields':dict(sorted(program['fields'].items()))}
    rng=random.Random(seed)
    base={k:f['default'] for k,f in program['fields'].items()}
    values={};comparators=[c for r in program['rules'] for c in comparisons(r['predicate'])]
    for c in comparators:
        for side,other in [('left','right'),('right','left')]:
            field=c[side]
            if not isinstance(field,dict) or 'field' not in field:continue
            name=field['field'];f=program['fields'][name]
            values.setdefault(name,[f['default']])
            literal=c[other]
            if isinstance(literal,dict):
                if 'field' in literal:
                    peer=literal['field']
                    if f['type']=='string':
                        token=('SYN'+str(seed)).ljust(f['width'])[:f['width']];base[name]=token;base[peer]=token.ljust(program['fields'][peer]['width'])[:program['fields'][peer]['width']]
                        values[name]+=[base[name],'Z'*f['width']]
                    else:base[name]=base[peer]=1;values[name]+=[0,1,2]
                continue
            if f['type']=='integer' and type(literal)is int:values[name]+=[literal-1,literal,literal+1,0,f['max'],rng.randrange(f['max']+1)]
            if f['type']=='string' and type(literal)is str:values[name]+=[literal.ljust(f['width'])[:f['width']],' '*f['width'],'Z'*f['width']]
    candidates={};cases=[]
    def add(record,reason,mandatory=True):
        fingerprint=sha(encode(record))
        if fingerprint in candidates:
            candidates[fingerprint]['mandatory'] |= mandatory
            return
        expected=run_reference(program,record)
        groups={}
        if isinstance(record,dict):
            for k,v in record.items():
                if k in program['fields']:groups.setdefault(program['fields'][k]['group'],{})[k]=v
        candidates[fingerprint]={'mandatory':mandatory,'reason':reason,'record':record,'files':{group:[row] for group,row in groups.items()},'expected':expected,'intentional_invalid':expected['input_status']=='REJECT_INPUT'}
    add(base.copy(),'Source-layout baseline with synthetic identities')
    for name,options in values.items():
        unique=list(dict.fromkeys(options));values[name]=unique
        for v in unique:add({**base,name:v},f'Boundary/domain witness: {name}={v!r}')
    for name,f in program['fields'].items():
        for bad in ([-1,f['max']+1,'wrong-type'] if f['type']=='integer' else ['', 'X'*(f['width']+1),None]):add({**base,name:bad},f'Intentional input-layout violation: {name}')
    if program.get('target_contract_version') == 2:
        # These records test the exported function itself, including Python's
        # bool-is-an-int pitfall and callers that bypass the workbench UI.
        for bad in (None, [], list(base.items())):add(bad,'Intentional non-object input contract violation')
        add({**base,'__EXTRA_FIELD__':'unexpected'},'Intentional extra field input contract violation')
        for name,field in program['fields'].items():
            add({k:v for k,v in base.items() if k!=name},'Intentional missing field input contract violation: '+name)
            for bad in ([True,False,0.0,None] if field['type']=='integer' else [True,0,[]]):
                add({**base,name:bad},'Intentional strict type input contract violation: '+name)
    names=list(values)
    # Reserve layout violations before filling the remaining budget with interactions.
    for combination in itertools.islice(itertools.product(*(values[n] for n in names)),min(4096,budget*16)):add({**base,**dict(zip(names,combination))},'Source-predicate interaction witness',False)
    # Select decision witnesses first; every omitted mandatory boundary/invalid
    # record is still reported. A budget must never silently erase obligations.
    remaining={(r['id'],b) for r in program['rules'] for b in (True,False)}
    selected=set()
    def select(key):
        if key in selected or len(cases)>=budget:return
        case=dict(candidates[key]);case.pop('mandatory');case['id']=f'case_{len(cases):04d}';cases.append(case);selected.add(key)
        remaining.difference_update((t['rule_id'],t['branch']) for t in case['expected'].get('trace',[]))
    for key,case in candidates.items():
        if remaining.intersection((t['rule_id'],t['branch']) for t in case['expected'].get('trace',[])):select(key)
    for key,case in candidates.items():
        if case['mandatory']:select(key)
    for key in candidates:select(key)
    obligation_gaps=[{'record_hash':key,'reason':case['reason'],'status':'budget_exhausted','explanation':'Required boundary or intentional layout-negative witness omitted by the configured case budget; unverified.'} for key,case in candidates.items() if case['mandatory'] and key not in selected]
    branches={r['id']:{'true':[],'false':[]} for r in program['rules']}
    for case in cases:
        for t in case['expected'].get('trace',[]):branches[t['rule_id']]['true' if t['branch'] else 'false'].append(case['id'])
    gaps=[{'rule_id':rid,'branch':branch,'status':'unknown_or_unprovable','reason':'No witness in bounded source-derived candidates; branch may be unreachable or require additional interactions. No verification credit.'} for rid,record in branches.items() for branch,witnesses in record.items() if not witnesses]
    coverage={'rule_count':len(branches),'branch_targets':len(branches)*2,'branches_observed':sum(bool(w) for b in branches.values() for w in b.values()),'rules':branches,'gaps':gaps,'obligation_gaps':obligation_gaps,'budget':budget,'mandatory_candidates':sum(c['mandatory'] for c in candidates.values()),'complete':not gaps and not obligation_gaps and not program['blockers'],'exhaustive':False,'claim':'Decision outcomes for the supported source IR; not all input/path/condition coverage or observed legacy parity.'}
    contract={'source':program.get('semantic_hash',program['source_hash']),'seed':seed,'rules':program['rules'],'fields':program['fields']}
    if program.get('target_contract_version') == 2:contract['target_contract_version']=2
    return {'version':1,'program':program['name'],'source_hash':program['source_hash'],'seed':seed,'evidence_basis':'SOURCE_DERIVED_EXPECTED','generator_version':'source-subset-2' if program.get('target_contract_version') == 2 else 'source-subset-1','cases':cases,'coverage':coverage,'contract_hash':sha(encode(contract))}


def _logic_fields(node):
    if not isinstance(node,dict):return set()
    if 'field' in node:return {node['field']}
    return _logic_fields(node['left']) | _logic_fields(node['right'])


def _logic_inputs(program,record):
    """Observe source predicate inputs after all preceding source MOVE effects."""
    if input_errors(program,record):return {}
    state=record.copy();inputs={}
    for rule in program['rules']:
        inputs[rule['id']]={name:state[name] for name in sorted(_logic_fields(rule['predicate']))}
        arm=rule['then'] if predicate(rule['predicate'],state) else rule['else']
        for effect in arm:state[effect['field']]=effect['value']
    return inputs


def _domain_options(spec,minimum,seed):
    values=[spec['default']]
    if spec['type']=='integer':
        values += [0,spec['max']] + list(range(min(spec['max']+1,minimum*2)))
        rng=random.Random(seed)
        values += [rng.randrange(spec['max']+1) for _ in range(minimum*2)]
    else:
        values += [' '*spec['width']]
        alphabet='0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz'
        values += [letter.ljust(spec['width']) for letter in alphabet[:minimum*2]]
    return list(dict.fromkeys(values))


def _random_domain_options(spec, count, rng):
    """Bounded seeded values with no duplicate padding and no global RNG mutation."""
    if spec['type']=='integer':
        size=spec['max']+1
        if size<=10000:return rng.sample(range(size),min(count,size))
        values=set();result=[]
        for _ in range(count*8):
            value=rng.randrange(size)
            if value not in values:values.add(value);result.append(value)
            if len(result)>=count:break
        return result
    alphabet=' 0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz'
    if spec['width']==1:return rng.sample(list(alphabet),min(count,len(alphabet)))
    values=set();result=[]
    for _ in range(count*8):
        value=''.join(rng.choice(alphabet) for _ in range(spec['width']))
        if value not in values:values.add(value);result.append(value)
        if len(result)>=count:break
    return result


def _select_source_mutation_witnesses(program, candidates, selected, select):
    """Keep meaningful interactions without executing every optional candidate.

    Selection uses source IR only. Frozen expected results remain untouched and
    the actual target mutation review still determines whether evidence passes.
    """
    boundaries={'=':'<>','<>':'=','>=':'>','>':'>=','<=':'<','<':'<='}
    valid={key:case for key,case in candidates.items() if not case['intentional_invalid']}
    def witness(differs):
        # Existing coverage is checked first; add only a differentiating record
        # when none of the already selected cases exposes this source mutation.
        if any(differs(valid[key]) for key in sorted(selected) if key in valid):return
        for key,case in valid.items():
            if key not in selected and differs(case):select(key);return
    for index,rule in enumerate(program['rules']):
        for offset,_ in enumerate(comparisons(rule['predicate'])):
            changed=copy.deepcopy(rule['predicate'])
            relation=comparisons(changed)[offset];relation['op']=boundaries[relation['op']]
            def differs(case,changed=changed,rule=rule):
                state=case['logic_inputs'][rule['id']]
                return predicate(changed,state)!=predicate(rule['predicate'],state)
            witness(differs)
        for arm in ('then','else'):
            for offset,effect in enumerate(rule[arm]):
                spec=program['fields'][effect['field']];old=effect['value']
                replacement=(old+1)%(spec['max']+1) if spec['type']=='integer' else ('Z' if old[:1]!='Z' else 'Y')+old[1:]
                rules=copy.deepcopy(program['rules']);rules[index][arm][offset]['value']=replacement
                changed={**program,'rules':rules}
                witness(lambda case,changed=changed:encode(run_reference(changed,case['record']))!=encode(case['expected']))


def _plan_cases_v3(program,seed,budget,minimum,version=3):
    require(type(budget) is int and 1<=budget<=10000,'Case budget must be between 1 and 10000')
    # Regenerate the historical source boundaries/strict negatives, then add
    # distinct source-relevant values. Nothing rewrites a frozen v1/v2 suite.
    baseline=_plan_cases_legacy(program,seed,min(10000,max(256,budget*4)),max_budget=10000)
    program={**program,'fields':dict(sorted(program['fields'].items()))}
    base={name:spec['default'] for name,spec in program['fields'].items()}
    candidates={};mandatory=set()
    def add(record,reason,required=False,randomized=False):
        key=sha(encode(record))
        if required:mandatory.add(key)
        if key in candidates:
            if randomized:candidates[key]['randomized']=True
            return
        if version==4 and len(candidates)>=10000:return
        expected=run_reference(program,record);groups={}
        if isinstance(record,dict):
            for name,value in record.items():
                if name in program['fields']:groups.setdefault(program['fields'][name]['group'],{})[name]=value
        logic_inputs=_logic_inputs(program,record)
        correlations=[]
        if not input_errors(program,record):
            for relationship in program.get('relationships',[]):
                left,right=relationship['left'],relationship['right']
                if program['fields'][left]['group']==program['fields'][right]['group']:continue
                correlations.append({'left':left,'right':right,
                                     'left_group':program['fields'][left]['group'],
                                     'right_group':program['fields'][right]['group'],
                                     'left_value':record[left],'right_value':record[right],
                                     'status':'MATCH' if record[left]==record[right] else 'INTENTIONAL_MISMATCH',
                                     'source_refs':list(relationship.get('source_refs',[]))})
        candidates[key]={'reason':reason,'record':record,'files':{group:[row] for group,row in groups.items()},
                         'expected':expected,'intentional_invalid':expected['input_status']=='REJECT_INPUT',
                         'logic_inputs':logic_inputs,
                         'logic_input_hashes':{rid:sha(encode(values)) for rid,values in logic_inputs.items()},
                         'correlations':correlations}
        if version==4:candidates[key]['randomized']=randomized
    for case in baseline['cases']:
        add(case['record'],case['reason'],case['reason']!='Source-predicate interaction witness')
    domains={name:_domain_options(spec,minimum,seed) for name,spec in program['fields'].items()}
    all_fields=sorted(set().union(*(_logic_fields(rule['predicate']) for rule in program['rules']))) if program['rules'] else []
    if version==4:
        rng=random.Random(seed)
        random_domains={name:_random_domain_options(program['fields'][name],minimum*4,rng)
                        for name in program['fields']}
        # Vary every layout input together so large rule inventories
        # share useful executions instead of allocating twenty rows per rule.
        for index in range(minimum*4):
            # Reshuffle each small domain on its next cycle; equal-sized fields
            # must not lock into the same ten pairs when their joint domain is 100.
            for values in random_domains.values():
                if index and index%len(values)==0:rng.shuffle(values)
            record={**base,**{name:values[index%len(values)] for name,values in random_domains.items()}}
            add(record,'Seeded randomized source-predicate state',randomized=True)
        # Linked layout groups receive deliberate matching and mismatching
        # randomized keys. These projections do not claim native dataset I/O.
        for relationship in program.get('relationships',[]):
            left,right=relationship['left'],relationship['right']
            a,b=program['fields'][left],program['fields'][right]
            if a['type']!=b['type']:continue
            if a['type']=='integer':shared={**a,'max':min(a['max'],b['max'])}
            elif a['width']==b['width']:shared=a
            else:continue
            values=_random_domain_options(shared,minimum*2,rng)
            for index,value in enumerate(values):
                record={**base,left:value,right:value}
                add(record,'Seeded randomized linked-key match',randomized=True)
                if len(values)>1:
                    add({**record,right:values[(index+1)%len(values)]},
                        'Seeded randomized intentional linked-key mismatch',randomized=True)
    for name in all_fields:
        for value in domains[name]:
            if len(candidates)>=10000:break
            add({**base,name:value},'Distinct source predicate input: '+name)
    for rule in program['rules']:
        for comparison in comparisons(rule['predicate']):
            left,right=comparison['left'],comparison['right']
            if not (isinstance(left,dict) and 'field' in left and isinstance(right,dict) and 'field' in right):continue
            a,b=left['field'],right['field']
            common=[value for value in domains[a] if value in domains[b]]
            for index,value in enumerate(common):
                if len(candidates)>=10000:break
                add({**base,a:value,b:value},'Correlated source key/value equality: '+a+' / '+b)
                alternatives=[other for other in domains[b] if other!=value]
                if alternatives:
                    add({**base,a:value,b:alternatives[index%len(alternatives)]},'Intentional source key/value mismatch: '+a+' / '+b)
    rules={rule['id']:{'true':[],'false':[]} for rule in program['rules']}
    counts={rid:set() for rid in rules};random_counts={rid:set() for rid in rules}
    observed=set();selected=set();cases=[];random_records=set()
    def select(key):
        if key in selected or len(cases)>=budget:return
        case=copy.deepcopy(candidates[key]);case['id']=f'case_{len(cases):04d}'
        cases.append(case);selected.add(key)
        if case.get('randomized') and not case['intentional_invalid']:random_records.add(key)
        for rid,fingerprint in case['logic_input_hashes'].items():
            counts[rid].add(fingerprint)
            if case.get('randomized'):random_counts[rid].add(fingerprint)
        for trace in case['expected'].get('trace',[]):
            observed.add((trace['rule_id'],trace['branch']))
            rules[trace['rule_id']]['true' if trace['branch'] else 'false'].append(case['id'])
    # Every branch and each distinct logic signature gets priority over bulk
    # interactions. Mandatory invalid/layout obligations remain explicit.
    for key,case in candidates.items():
        if any((trace['rule_id'],trace['branch']) not in observed for trace in case['expected'].get('trace',[])):select(key)
    if version==4:
        for key,case in candidates.items():
            if case.get('randomized') and (len(random_records)<minimum or any(
                    len(random_counts[rid])<minimum and fingerprint not in random_counts[rid]
                    for rid,fingerprint in case['logic_input_hashes'].items())):select(key)
    for key,case in candidates.items():
        if any(len(counts[rid])<minimum and fingerprint not in counts[rid]
               for rid,fingerprint in case['logic_input_hashes'].items()):select(key)
    for key in candidates:
        if key in mandatory:select(key)
    if version==4:_select_source_mutation_witnesses(program,candidates,selected,select)
    else:
        for key in candidates:select(key)
    gaps=[{'rule_id':rid,'branch':branch,'status':'unknown_or_unprovable',
           'reason':'No source-derived witness; the branch may be unreachable or need a reviewed semantic adapter. No verification credit.'}
          for rid,branches in rules.items() for branch,witnesses in branches.items() if not witnesses]
    record_gaps=[]
    for rid,fingerprints in (random_counts if version==4 else counts).items():
        if len(fingerprints)>=minimum:continue
        fields=sorted(_logic_fields(next(rule['predicate'] for rule in program['rules'] if rule['id']==rid)))
        finite_domain=1
        for name in fields:
            spec=program['fields'][name]
            if spec['type']!='integer':finite_domain=None;break
            finite_domain *= spec['max']+1
            if finite_domain>=minimum:break
        available={case['logic_input_hashes'][rid] for case in candidates.values() if rid in case['logic_input_hashes']
                   and (version==3 or case.get('randomized'))}
        limited=finite_domain is not None and finite_domain<minimum
        status='limited_input_domain' if limited else 'budget_exhausted' if len(available)>=minimum else 'bounded_generation_exhausted'
        record_gaps.append({'rule_id':rid,'required':minimum,'observed':len(fingerprints),
                            'status':status,'multiplicity_applicable':not limited,
                            'proven_input_domain_size':finite_domain if limited else None,
                            'reason':'The source predicate has fewer distinct valid input states than the requested minimum; duplicate or unused-field padding cannot count. Review the multiplicity exception explicitly.' if limited else 'The configured budget omitted available distinct source logic records.' if status=='budget_exhausted' else 'Bounded generation cannot prove the required distinct executed logic states; prior assignments or unreachable logic may constrain them. Retain the gap.'})
    obligation_gaps=list(baseline['coverage']['obligation_gaps'])
    obligation_gaps += [{'record_hash':key,'reason':case['reason'],'status':'budget_exhausted',
                         'explanation':'Required source boundary or intentional input-negative case omitted; no verification credit.'}
                        for key,case in candidates.items() if key in mandatory and key not in selected]
    correlation_validation=[];correlation_gaps=[]
    for relationship in program.get('relationships',[]):
        left,right=relationship['left'],relationship['right']
        if program['fields'][left]['group']==program['fields'][right]['group']:continue
        rows=[correlation for case in cases for correlation in case['correlations']
              if correlation['left']==left and correlation['right']==right]
        result={'left':left,'right':right,'matched_records':sum(row['status']=='MATCH' for row in rows),
                'mismatched_records':sum(row['status']=='INTENTIONAL_MISMATCH' for row in rows),
                'basis':'SOURCE_LAYOUT_GROUP_PROJECTIONS_NOT_DATASET_IO_PARITY'}
        correlation_validation.append(result)
        if not result['matched_records'] or not result['mismatched_records']:
            correlation_gaps.append({**result,'status':'linked_key_witness_missing',
                                     'reason':'Both valid matching keys and intentional mismatches are required before linked-record credit.'})
    coverage={'rule_count':len(rules),'branch_targets':len(rules)*2,
              'branches_observed':sum(bool(value) for branches in rules.values() for value in branches.values()),
              'rules':rules,'gaps':gaps,'obligation_gaps':obligation_gaps,'budget':budget,
              'mandatory_candidates':len(mandatory),'min_records_per_logic':minimum,
              'record_counts':{rid:len(values) for rid,values in counts.items()},
              'record_hashes':{rid:sorted(values) for rid,values in counts.items()},
              'logic_fields':{rule['id']:sorted(_logic_fields(rule['predicate'])) for rule in program['rules']},
              'record_count_gaps':record_gaps,'correlation_validation':correlation_validation,
              'correlation_gaps':correlation_gaps,
              'complete':not gaps and not obligation_gaps and not record_gaps and not correlation_gaps and not program['blockers'],
              'exhaustive':False,
              'claim':'At least the configured distinct valid source predicate input states per applicable supported logic, with source boundaries, input negatives and linked layout-group keys. Missing/duplicate/empty dataset I/O semantics require their own reviewed adapter; no observed legacy parity.'}
    coverage['logic_validation']={'contract_version':version,'minimum_distinct_records_per_logic':minimum,
                                  'applicable_logic_count':len(rules),'logic_meeting_minimum':sum(len(values)>=minimum for values in counts.values()),
                                  'distinct_logic_records':sum(len(values) for values in counts.values()),
                                  'gaps':len(record_gaps),'complete':not record_gaps and not program['blockers'],
                                  'distinctness_basis':'SOURCE_PREDICATE_INPUT_STATE_AT_EXECUTION; unused fields and duplicate records do not count',
                                  'records_per_logic':coverage['record_counts']}
    if version==4:
        valid_records={sha(encode(case['record'])) for case in cases if not case['intentional_invalid']}
        technical_complete=len(random_records)>=minimum and not program['blockers']
        technical_base={'required':minimum,'distinct_valid_records':len(valid_records),
                        'randomized_valid_records':len(random_records),
                        'basis':'SOURCE_VALID_COMPLETE_INPUT_RECORDS; TARGET_COMPARISON_REQUIRED',
                        'complete':technical_complete}
        technical={'input_layout':{**technical_base,
                                   'invalid_input_cases':sum(case['intentional_invalid'] for case in cases)},
                   'terminal':dict(technical_base)}
        technical_gaps=[]
        if not technical_complete:
            available=sum(case.get('randomized',False) and not case['intentional_invalid']
                          for case in candidates.values())
            domain_size=1
            for spec in program['fields'].values():
                if spec['type']!='integer':domain_size=None;break
                domain_size*=spec['max']+1
                if domain_size>=minimum:break
            limited=domain_size is not None and domain_size<minimum
            for name in technical:
                technical_gaps.append({'technical_unit':name,'required':minimum,
                    'observed':len(random_records),
                    'status':'source_blocked' if program['blockers'] else 'limited_input_domain' if limited else 'budget_exhausted' if available>=minimum else 'bounded_generation_exhausted',
                    'proven_input_domain_size':domain_size if limited else None,
                    'reason':'Twenty distinct valid randomized complete records are required for layout and terminal behavior; duplicate padding and unsupported source receive no credit.'})
        coverage['technical_record_count_gaps']=technical_gaps
        coverage['complete']=coverage['complete'] and technical_complete
        coverage['logic_validation']['complete']=coverage['complete']
        coverage['logic_validation']['gaps']+=len(technical_gaps)
        coverage['logic_validation']['technical']=technical
        coverage['randomized_record_counts']={rid:len(values) for rid,values in random_counts.items()}
        coverage['randomized_record_hashes']={rid:sorted(values) for rid,values in random_counts.items()}
        coverage['logic_validation'].update(
            randomized_records_per_logic=coverage['randomized_record_counts'],
            logic_meeting_randomized_minimum=sum(len(values)>=minimum for values in random_counts.values()),
            generation='RUNTIME_SEEDED_PSEUDORANDOM_WITH_MANDATORY_SOURCE_BOUNDARIES',
            replay_seed=seed)
        coverage['claim']='At least 20 distinct valid randomized source predicate states per supported logic, plus mandatory boundaries and invalid inputs. Limited, unreachable and undersampled states remain explicit gaps; no exhaustive or observed legacy parity claim.'
    contract={'source':program.get('semantic_hash',program['source_hash']),'seed':seed,
              'rules':program['rules'],'fields':program['fields'],'target_contract_version':program.get('target_contract_version',1),
              'fixture_contract_version':version,'min_records_per_logic':minimum,'budget':budget}
    return {'version':version,'program':program['name'],'source_hash':program['source_hash'],'seed':seed,
            'evidence_basis':'SOURCE_DERIVED_EXPECTED','generator_version':'source-subset-'+str(version),
            'cases':cases,'coverage':coverage,'contract_hash':sha(encode(contract))}


def verify_program(program,code,suite,checkpoint=None):
    require(encode(suite)==encode(plan_cases(program,suite['seed'],suite['coverage']['budget'],suite['coverage'].get('min_records_per_logic',0),fixture_contract_version=suite.get('version',1))), 'Frozen suite or coverage differs from the deterministic source-derived contract')
    return _verify_cases(program,code,suite,checkpoint)


def _verify_cases(program,code,suite,checkpoint=None):
    require(suite['source_hash']==program['source_hash'],'Fixture source version differs')
    actual=[];diffs=[];execute=None
    for case in suite['cases']:
        if checkpoint:checkpoint()
        require(encode(case['expected'])==encode(run_reference(program,case['record'])),'Frozen expected result differs from independent source interpretation')
        if program.get('target_contract_version') == 2:
            if execute is None:execute=prepare_generated(code)
            try:got=execute(case['record'])
            except (TypeError,KeyError,ValueError,AttributeError,OverflowError) as exc:
                # A malformed target must produce failed evidence, including
                # when a guard mutation exposes an exception on invalid data.
                got={'input_status':'TARGET_ERROR','error_type':type(exc).__name__,'return_code':None}
        else:
            # Historical receipts used this adapter. Preserve replay exactly;
            # new contracts validate inside the generated target above.
            errors=input_errors(program,case['record'])
            if errors:got={'input_status':'REJECT_INPUT','errors':errors,'return_code':None}
            else:
                if execute is None:execute=prepare_generated(code)
                got=execute(case['record'])
        actual.append({'case_id':case['id'],'result':got})
        if encode(got)!=encode(case['expected']):diffs.append({'case_id':case['id'],'expected':case['expected'],'actual':got,'triage':'Target, oracle or adapter discrepancy; inspect source evidence before changing expectations.'})
    result={'status':'MISMATCH' if diffs else 'MATCHED_SOURCE_DERIVED_EXPECTATIONS' if suite['coverage']['complete'] else 'MATCHED_WITH_COVERAGE_GAPS','source_hash':program['source_hash'],'target_hash':sha(code),'contract_hash':suite['contract_hash'],'expected_count':len(suite['cases']),'matched_count':len(suite['cases'])-len(diffs),'differences':diffs,'actual':actual,'coverage':suite['coverage'],'observed_legacy_parity':False}
    if program.get('target_contract_version') == 2:
        result['input_validation_basis']='GENERATED_TARGET_FUNCTION'
        result['invalid_inputs_executed']=sum(c['intentional_invalid'] for c in suite['cases'])
    return result


def adversarial_review(program, code, suite, checkpoint=None):
    """Mutate target syntax only, preserving the frozen independent source oracle.

    Every rule gets a decision reversal, each atomic relation a boundary mutation,
    and every literal assignment a different valid field value. A surviving
    mutation is an explicit gap (including effects overwritten downstream).
    """
    require(encode(suite)==encode(plan_cases(program,suite['seed'],suite['coverage']['budget'],suite['coverage'].get('min_records_per_logic',0),fixture_contract_version=suite.get('version',1))), 'Adversarial suite differs from frozen source contract')
    tree=ast.parse(code);rules=rule_nodes(tree,program)
    require(len(rules)==len(program['rules']),'Target rule structure differs')
    mutations=[]
    boundaries={ast.Eq:ast.NotEq,ast.NotEq:ast.Eq,ast.GtE:ast.Gt,ast.Gt:ast.GtE,ast.LtE:ast.Lt,ast.Lt:ast.LtE}
    def record(mutant,rid,kind,label):
        if checkpoint:checkpoint()
        result=_verify_cases(program,ast.unparse(mutant),suite,checkpoint)
        detected=bool(result['differences'])
        mutations.append({'rule_id':rid,'kind':kind,'mutation':label,'detected':detected,'witnesses':[d['case_id'] for d in result['differences']], 'reason':'Frozen source expectations detected changed target behavior' if detected else 'No differentiating output/trace witness; effect may be masked or unreachable. Unproved, no adversarial credit.'})
    for index,rule in enumerate(program['rules']):
        mutant=copy.deepcopy(tree);branch=rule_nodes(mutant,program)[index]
        # Swap the whole decision, including its trace, without changing oracle IR.
        branch.body,branch.orelse=branch.orelse,branch.body
        record(mutant,rule['id'],'predicate','reverse whole decision')
        relations=[n for n in ast.walk(rules[index].test) if isinstance(n,ast.Compare)]
        for offset,relation in enumerate(relations):
            mutant=copy.deepcopy(tree);branch=rule_nodes(mutant,program)[index]
            comparison=[n for n in ast.walk(branch.test) if isinstance(n,ast.Compare)][offset]
            comparison.ops[0]=boundaries[type(comparison.ops[0])]()
            record(mutant,rule['id'],'comparison',f'boundary relation {offset+1}')
        for arm in ('then','else'):
            for offset,effect in enumerate(rule[arm]):
                spec=program['fields'][effect['field']];old=effect['value']
                value=(old+1)%(spec['max']+1) if spec['type']=='integer' else ('Z' if old[:1]!='Z' else 'Y')+old[1:]
                mutant=copy.deepcopy(tree);branch=rule_nodes(mutant,program)[index]
                assignments=[n for n in (branch.body if arm=='then' else branch.orelse) if isinstance(n,ast.Assign)]
                require(offset<len(assignments),'Target effect structure differs')
                assignments[offset].value=ast.Constant(value=value)
                record(mutant,rule['id'],'effect',f'{arm} assignment {offset+1}: {effect["field"]}')
    for index,guard in enumerate(layout_nodes(tree,program)):
        mutant=copy.deepcopy(tree)
        layout_nodes(mutant,program)[index].test=ast.Constant(value=False)
        record(mutant,'INPUT_CONTRACT','input_contract',f'disable input guard {index+1}')
    denied=False
    if checkpoint:checkpoint()
    try:run_generated('import os\ndef run_program(record):\n    return record\n',{})
    except ValueError:denied=True
    gaps=[m for m in mutations if not m['detected']]
    accounted=all(x['disposition']!='unaccounted' for x in program['coverage'])
    method='deterministic per-rule, per-comparison and per-effect target mutations against frozen source expectations; not independent human/model review'
    if program.get('target_contract_version') == 2:method+='; each generated input guard is also disabled and tested against rejecting witnesses'
    return {'method':method, 'mutations':mutations,'gaps':gaps,'mutation_detected':bool(mutations) and not gaps,'forbidden_import_rejected':denied,'source_accounted':accounted,'passed':not gaps and denied and accounted}
