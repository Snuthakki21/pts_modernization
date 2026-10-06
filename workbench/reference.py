"""Independent source-IR reference evaluation, never generated target outputs."""
from .domain import require


def contract_version(program):
    version=program.get('target_contract_version',1)
    require(type(version) is int and version in (1,2), 'Unsupported target contract version')
    return version


def input_errors(program, record):
    contract_version(program)
    errors=[]
    if (type(record) is not dict if program.get('target_contract_version') == 2 else not isinstance(record,dict)):return ['record must be an object']
    if set(record)!=set(program['fields']):errors.append('field set differs from source layout')
    fields = sorted(program['fields'].items()) if program.get('target_contract_version') == 2 else program['fields'].items()
    for name,f in fields:
        value=record.get(name)
        if f['type']=='integer':
            if type(value) is not int or not 0<=value<=f['max']:errors.append(name+': invalid unsigned integer')
        elif type(value) is not str or len(value)!=f['width']:errors.append(name+': invalid fixed-width string')
    return errors


def predicate(node, record):
    if not isinstance(node,dict):return node
    if 'field' in node:return record[node['field']]
    a=predicate(node['left'],record);b=predicate(node['right'],record);op=node['op']
    if op=='AND':return bool(a) and bool(b)
    if op=='OR':return bool(a) or bool(b)
    if op=='=':return type(a) is type(b) and a==b
    if op=='<>':return type(a) is not type(b) or a!=b
    if type(a) is not type(b):raise ValueError('Source operands have differing types')
    if op=='>=':return a>=b
    if op=='<=':return a<=b
    if op=='>':return a>b
    if op=='<':return a<b
    raise ValueError('Unsupported source predicate')


def run_reference(program, record):
    errors=input_errors(program,record)
    if errors:return {'input_status':'REJECT_INPUT','errors':errors,'return_code':None}
    state=record.copy();trace=[]
    for rule in program['rules']:
        branch=predicate(rule['predicate'],state)
        for effect in rule['then'] if branch else rule['else']:state[effect['field']]=effect['value']
        # Returned evidence must not expose the source IR's mutable provenance
        # list. Each call and fixture case owns its own trace, like the target.
        trace.append({'rule_id':rule['id'],'branch':branch,'source_refs':list(rule['source_refs'])})
    return {'input_status':'ACCEPT_INPUT','record':state,'trace':trace,'return_code':0}
