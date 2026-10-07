"""Issue and replay bounded BMS layout evidence through Coordinator gates."""
from .domain import encode, sha, write_new, require
from .cics import (selected_screens, emit_screen, plan_screen_cases, verify_screen,
                   adversarial_screen, screen_target_mappings)
from .unit_evidence import run_unit_tests


def unit_script(screen, suite, version):
    """Expectations are frozen before this standalone unit module executes."""
    return '''"""BMS layout comparisons; native controller remains unverified."""
import copy, hashlib, json, unittest
from pathlib import Path
HERE = Path(__file__).resolve()
BASE = HERE.parents[3]
RUN = HERE.parents[1].name
SCREEN = ''' + repr(screen['id']) + '''
EXPECTED_HASH = ''' + repr(sha(encode(suite))) + '''
TARGET_HASH = ''' + repr(version) + '''
SOURCE_HASH = ''' + repr(screen['source_hash']) + '''
raw = (BASE/'synthetic'/RUN/SCREEN/'expected.json').read_bytes()
if hashlib.sha256(raw).hexdigest() != EXPECTED_HASH: raise ValueError('Expected screen suite changed')
suite = json.loads(raw)
raw = (BASE/'target'/RUN/(SCREEN+'.py')).read_bytes()
if hashlib.sha256(raw).hexdigest() != TARGET_HASH: raise ValueError('Screen target changed')
namespace = {'__builtins__': {}, 'type': type, 'dict': dict, 'str': str, 'len': len, 'any': any, 'ord': ord}
exec(compile(raw.decode('utf-8'), '<pinned-screen-target>', 'exec'), namespace)
class SourceComparisonTests(unittest.TestCase): pass
def comparison(case):
    def test(self):
        values = copy.deepcopy(case['values'])
        actual = namespace['run_screen'](values)
        self.assertEqual(json.dumps(actual, sort_keys=True, allow_nan=False), json.dumps(case['expected'], sort_keys=True, allow_nan=False), case['id'])
        self.assertEqual(values, case['values'], 'Target mutated caller input')
    return test
for index, case in enumerate(suite['cases']):
    setattr(SourceComparisonTests, 'test_case_'+str(index+1).zfill(6), comparison(case))
if __name__ == '__main__': unittest.main()
'''


def suite_for(doc, screen, checkpoint=None):
    return plan_screen_cases(screen, doc['authorization']['seed'],
                             max(20, doc.get('logic_validation_min_records', 20)),
                             min(10000, doc['authorization']['max_cases_per_program']),checkpoint=checkpoint)


def controller_witness(doc, screen):
    return {'owners':screen['owners'], 'mapset':screen['mapset'], 'map':screen['map'],
            'lineage_hash':sha(encode(doc.get('lineage') or {})), 'native_controller_verified':False}


def verify_layouts(coordinator, doc, run):
    """Issue immutable artifacts after the actual human return, never another engine."""
    root = coordinator.process_root(doc['id']); run_id = run['id']
    run['screens'] = {}; doc['screen_versions'] = {}
    def issue(relative, data):
        path = root/relative; write_new(path, data); coordinator.register(doc, relative)
        return path
    for screen in selected_screens(doc['analysis']):
        coordinator.checkpoint(doc)
        if screen['support'] != 'layout_supported' or screen['gaps']: continue
        code = emit_screen(screen); version = sha(code); ident = screen['id']
        shared = coordinator.root/'shared/target/python'/(version+'.py')
        if not shared.exists(): write_new(shared, code.encode())
        require(shared.read_bytes() == code.encode(), 'Shared screen target integrity failed')
        doc['screen_versions'][ident] = version
        checkpoint=lambda:coordinator.checkpoint(doc,persist=False)
        suite = suite_for(doc, screen, checkpoint)
        issue(f'synthetic/{run_id}/{ident}/expected.json', encode(suite))
        issue(f'target/{run_id}/{ident}.py', code.encode())
        coordinator.checkpoint(doc)
        result = verify_screen(screen, code, suite, checkpoint=checkpoint)
        result['adversarial'] = adversarial_screen(screen, code, suite, checkpoint=checkpoint)
        script = unit_script(screen, suite, version)
        module = f'tests/{run_id}/{ident}/test_generated.py'
        path = issue(module, script.encode())
        unit = run_unit_tests(script, path, checkpoint=lambda:coordinator.checkpoint(doc, persist=False))
        receipt = f'tests/{run_id}/{ident}/unit-results.json'
        issue(receipt, encode(unit)); result['unit_tests'] = {**unit, 'module':module, 'receipt':receipt}
        result['linked_controller_witness'] = controller_witness(doc, screen)
        issue(f'synthetic/{run_id}/{ident}/actual-and-comparison.json', encode(result))
        run['screens'][ident] = result
        if not result['passed'] or not result['adversarial']['passed'] or not unit['passed']:
            doc['blockers'].append({'kind':'screen_verification_gap', 'screen':ident, 'source_path':screen['source_path'],
                                    'message':'BMS layout has a comparison, randomized-state, generated unit or adversarial witness gap',
                                    'gaps':suite['coverage']['gaps']})


def replay_layouts(doc, root, base, errors, checkpoint=None):
    """Reproduce gates before crediting source lines with layout-only verification."""
    from .coverage import _read, _target
    states = {}
    for screen in selected_screens(doc.get('analysis') or {}):
        ident = screen['id']; state = {'verified':False, 'mappings':{}, 'tests':[], 'evidence':[], 'reason':'Screen layout verification is unavailable.'}
        states[ident] = state
        if screen['support'] != 'layout_supported' or screen['gaps']:
            state['reason'] = '; '.join(g['message'] for g in screen['gaps']) or 'Unsupported BMS layout'; continue
        try:
            if checkpoint: checkpoint()
            require(not errors and not doc.get('cancel_requested'), 'Screen replay denied by integrity or cancellation gate')
            require(doc.get('verification_finished') and doc.get('runs'), 'Screen verification did not finish')
            require(doc.get('packet_imported') and (doc.get('answers') or {}).get('items'), 'Actual human review is required')
            require(all(a['answer']=='Yes' and not a['correction'] for a in doc['answers']['items'].values()), 'Human review contains unresolved answers or corrections')
            run = doc['runs'][-1]; result = run.get('screens', {}).get(ident)
            require(result is not None, 'Screen is absent from the latest run')
            version = doc.get('screen_versions', {}).get(ident); code = emit_screen(screen)
            require(version == sha(code), 'Screen target differs from its source/requirements contract')
            target = root/'shared/target/python'/(version+'.py'); raw = _read(target)
            require(raw == code.encode(), 'Shared screen target changed')
            folder = base/'synthetic'/run['id']/ident
            suite = suite_for(doc, screen, checkpoint); require(_read(folder/'expected.json')==encode(suite), 'Frozen screen expectations do not reproduce')
            replay = verify_screen(screen, code, suite, checkpoint=checkpoint); adversarial = adversarial_screen(screen, code, suite, checkpoint=checkpoint)
            require(all(encode(result.get(k))==encode(v) for k,v in replay.items()) and replay['passed'], 'Screen comparisons do not reproduce or have uncovered states')
            require(result.get('adversarial')==adversarial and adversarial['passed'], 'Screen adversarial evidence does not reproduce')
            copy_path = base/'target'/run['id']/(ident+'.py'); require(_read(copy_path)==raw, 'Run screen target changed')
            script = unit_script(screen, suite, version); module = base/f'tests/{run["id"]}/{ident}/test_generated.py'
            require(_read(module)==script.encode(), 'Screen unit module changed')
            unit = run_unit_tests(script, module, checkpoint)
            receipt = base/f'tests/{run["id"]}/{ident}/unit-results.json'
            require(_read(receipt)==encode(unit) and unit['passed'], 'Screen unit receipt changed or failed')
            require(result['unit_tests']=={**unit, 'module':module.relative_to(base).as_posix(), 'receipt':receipt.relative_to(base).as_posix()}, 'Screen unit run differs')
            require(result.get('linked_controller_witness')==controller_witness(doc,screen), 'Linked screen/controller witness changed')
            require(_read(folder/'actual-and-comparison.json')==encode(result), 'Stored screen result differs from run')
            from .online import replay_screen_http
            http_files = replay_screen_http(doc, root, base, screen, suite, checkpoint=checkpoint)
            state['evidence'] = [{'file':p.relative_to(root).as_posix(), 'sha256':sha(_read(p)), 'kind':kind}
                for p,kind in [(folder/'expected.json','frozen_source_expectations'), (folder/'actual-and-comparison.json','reproduced_screen_comparison'),
                               (copy_path,'executed_target_version'), (module,'executable_unit_tests'), (receipt,'reproduced_unit_test_results'), *http_files]]
            state['mappings'] = {key:_target(target,root,span['start'],span['end']) for key,span in screen_target_mappings(code,screen).items()}
            state['tests'] = [case['id'] for case in suite['cases']]; state['verified'] = True
            state['reason'] = 'Human-reviewed BMS character layout; frozen independent expectations, actual Python/FastAPI comparisons, generated units and adversarial witnesses reproduce. Native controller, terminal encoding and persistence remain unverified.'
        except Exception as exc:
            state['reason'] = str(exc) or type(exc).__name__
            state['error'] = ident+': '+state['reason']
    return states
