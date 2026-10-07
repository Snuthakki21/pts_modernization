"""Generate auditable Python from a constrained source IR, not arbitrary LLM code."""
import ast
import re
from .domain import require, sha
from .reference import contract_version


def expression(node):
    if not isinstance(node,dict):return repr(node)
    if 'field' in node:return 'row['+repr(node['field'])+']'
    op={'=':'==','<>':'!=','AND':'and','OR':'or'}.get(node['op'],node['op'])
    return '('+expression(node['left'])+' '+op+' '+expression(node['right'])+')'


def emit_program(program):
    require(not program['blockers'], 'Unsupported program cannot receive a complete executable translation')
    contract_version(program)
    lines=['# Generated from source SHA256 '+program['source_hash'], '# Evidence class: SOURCE_DERIVED_EXPECTED', '# Semantic/dependency SHA256 '+program.get('semantic_hash',program['source_hash']), 'def run_program(record):']
    if program.get('requirements_hash'):
        lines.insert(3,'# Saved requirements SHA256 '+program['requirements_hash'])
        lines.append('    '+repr('Apply the selected source rules in order to an independent validated record; return the record, source trace and status.'))
    if program.get('target_contract_version') == 2:
        # Keep the exported function self-contained: callers cannot bypass a
        # fixture-only adapter and accidentally accept a non-COBOL input value.
        lines += ['    if type(record) is not dict:',
                  "        return {'input_status': 'REJECT_INPUT', 'errors': ['record must be an object'], 'return_code': None}",
                  '    errors = []']
        fields = dict(sorted(program['fields'].items()))
        shape = 'len(record) != '+str(len(fields))
        for name in fields:
            shape += ' or '+repr(name)+' not in record'
        lines += ['    if '+shape+':', "        errors.append('field set differs from source layout')"]
        for name, field in fields.items():
            value = 'record.get('+repr(name)+')'
            if field['type'] == 'integer':
                invalid = 'type('+value+') is not int or '+value+' < 0 or '+value+' > '+str(field['max'])
                error = name+': invalid unsigned integer'
            else:
                invalid = 'type('+value+') is not str or len('+value+') != '+str(field['width'])
                error = name+': invalid fixed-width string'
            lines += ['    if '+invalid+':', '        errors.append('+repr(error)+')']
        lines += ['    if errors:', "        return {'input_status': 'REJECT_INPUT', 'errors': errors, 'return_code': None}"]
    lines += ['    row = dict(record)', '    trace = []']
    for rule in program['rules']:
        if program.get('requirements_hash'):lines.append('    # Source rule '+rule['id']+'; selected Yes in saved requirements.')
        lines.append('    if '+expression(rule['predicate'])+':')
        for effect in rule['then']:lines.append('        row['+repr(effect['field'])+'] = '+repr(effect['value']))
        lines.append('        trace.append('+repr({'rule_id':rule['id'],'branch':True,'source_refs':rule['source_refs']})+')')
        lines.append('    else:')
        for effect in rule['else']:lines.append('        row['+repr(effect['field'])+'] = '+repr(effect['value']))
        lines.append('        trace.append('+repr({'rule_id':rule['id'],'branch':False,'source_refs':rule['source_refs']})+')')
    lines.append("    return {'input_status': 'ACCEPT_INPUT', 'record': row, 'trace': trace, 'return_code': 0}")
    return '\n'.join(lines)+'\n'


def layout_nodes(tree, program):
    """Return input guards separately from source business decisions."""
    guards = [n for n in tree.body[0].body if isinstance(n, ast.If)]
    return guards[:len(program['fields'])+3] if program.get('target_contract_version') == 2 else []


def rule_nodes(tree, program):
    branches = [n for n in tree.body[0].body if isinstance(n, ast.If)]
    return branches[len(layout_nodes(tree, program)):]


def check_generated(code):
    require(isinstance(code,str) and len(code)<=512000,'Target code exceeds limit')
    try:tree=ast.parse(code)
    except SyntaxError as exc:raise ValueError('Invalid target syntax') from exc
    require(len(tree.body)==1 and isinstance(tree.body[0],ast.FunctionDef) and tree.body[0].name=='run_program','Only one generated program function is accepted')
    function = tree.body[0]
    require(len(function.args.args) == 1 and function.args.args[0].arg == 'record'
            and not function.args.posonlyargs and not function.args.kwonlyargs
            and not function.args.defaults and function.args.vararg is None
            and function.args.kwarg is None and not function.decorator_list
            and function.args.args[0].annotation is None and function.returns is None,
            'Generated target must accept exactly one record argument')
    allowed=(ast.Module,ast.FunctionDef,ast.arguments,ast.arg,ast.Assign,ast.Name,ast.Load,ast.Store,ast.Call,ast.Dict,ast.Constant,ast.List,ast.If,ast.Compare,ast.BoolOp,ast.And,ast.Or,ast.Eq,ast.NotEq,ast.Gt,ast.GtE,ast.Lt,ast.LtE,ast.IsNot,ast.NotIn,ast.Subscript,ast.Expr,ast.Attribute,ast.Return,ast.UnaryOp,ast.USub)
    for node in ast.walk(tree):
        require(isinstance(node,allowed),'Target includes an unsupported executable capability')
        if isinstance(node,ast.FunctionDef):require(node is function,'Nested target functions are not allowed')
        if isinstance(node,ast.Name):require(node.id in {'run_program','record','row','trace','errors','dict','type','int','str','len'},'Unknown target identifier')
        if isinstance(node,ast.Attribute):require(isinstance(node.value,ast.Name) and ((node.value.id in {'trace','errors'} and node.attr=='append') or (node.value.id=='record' and node.attr=='get')),'Target attribute access is not allowed')
        if isinstance(node,ast.Call):require(len(node.args)==1 and not node.keywords and ((isinstance(node.func,ast.Name) and node.func.id in {'dict','type','len'}) or (isinstance(node.func,ast.Attribute) and node.func.attr in {'append','get'})),'Target call is not allowed')
        if isinstance(node,ast.Assign):
            require(len(node.targets)==1 and all((isinstance(t,ast.Name) and t.id in {'row','trace','errors'}) or (isinstance(t,ast.Subscript) and isinstance(t.value,ast.Name) and t.value.id=='row' and isinstance(t.slice,ast.Constant) and isinstance(t.slice.value,str)) for t in node.targets),'Unsafe assignment target')
            destination=node.targets[0]
            if isinstance(destination,ast.Name):
                if destination.id=='row':
                    require(isinstance(node.value,ast.Call) and isinstance(node.value.func,ast.Name)
                            and node.value.func.id=='dict' and len(node.value.args)==1
                            and isinstance(node.value.args[0],ast.Name) and node.value.args[0].id=='record',
                            'Target row must be an independent record copy')
                else:require(isinstance(node.value,ast.List) and not node.value.elts,'Target trace/errors must start as fresh lists')
    return tree


def prepare_generated(code):
    """Validate one immutable code value and prepare its bounded entry point.

    A verification suite keeps this function only for that suite; every record
    still enters the generated input guards. No code or records are cached
    across runs, programs, or mutation candidates.
    """
    # This is a restricted generator/template boundary, not an OS sandbox for user-supplied Python.
    tree=check_generated(code)
    namespace={'__builtins__':{},'dict':dict,'type':type,'int':int,'str':str,'len':len}
    exec(compile(tree,'<source-generated-target>','exec'),namespace)
    return namespace['run_program']


def run_generated(code, record):
    return prepare_generated(code)(record)


def emit_jobs(manifest, program_versions):
    lines=['# Generated ordered orchestration. Program implementations are shared and version-pinned.']
    programs=manifest.get('analysis',{}).get('programs',{})
    validates_inputs=bool(programs) and all(p.get('target_contract_version')==2 for p in programs.values())
    method_names=set()
    for job in manifest['jobs']:
        require(isinstance(job['name'],str) and re.fullmatch(r'[A-Za-z][A-Za-z0-9_-]{0,79}',job['name']), 'Invalid job identifier')
        name=job['name'].lower().replace('-','_')
        require(name not in method_names,'Job names collide after Python normalization')
        method_names.add(name)
        lines += ['def run_job_'+name+'(context, programs):','    results = []','    previous_rc = 0']
        for step in job['steps']:
            condition=step['condition'].strip().upper()
            match=re.fullmatch(r'RC\s*(<=|>=|=|<|>)\s*(\d{1,5})',condition)
            require(condition in ('ALWAYS','') or match is not None,'Unsupported job return-code condition')
            require(step['program'].upper() in program_versions,'Missing version-pinned program')
            cond='True' if condition in ('ALWAYS','') else 'previous_rc '+('==' if match[1]=='=' else match[1])+' '+str(int(match[2]))
            lines+=['    if '+cond+':',"        result = programs["+repr(step['program'].upper())+"](context['record'])",'        results.append('+repr({'step':step['name'],'version':program_versions[step['program'].upper()]})+" | result)"]
            if validates_inputs:
                lines += ["        if result['input_status'] == 'REJECT_INPUT':",'            return results']
            lines += ['        previous_rc = result[\'return_code\']',"        context['record'] = result['record']",'    else:',"        results.append({'step': "+repr(step['name'])+", 'status': 'SKIPPED'})"]
        lines.append('    return results')
    lines+=['def run_process(context, programs):','    results = {}']
    for job in manifest['jobs']:
        results = 'results['+repr(job['name'])+']'
        lines.append('    '+results+' = run_job_'+job['name'].lower().replace('-','_')+'(context, programs)')
        if validates_inputs:
            lines += ['    if '+results+' and '+results+"[-1].get('input_status') == 'REJECT_INPUT':", '        return results']
    lines.append('    return results')
    return '\n'.join(lines)+'\n'
