"""Portable unittest exports that replay frozen source expectations on target code."""
from pathlib import Path
import unittest
from .domain import encode, sha, require


def generate_unit_tests(program, suite, target_hash):
    """No oracle is recomputed in the exported tests: expectations precede execution."""
    require(program.get('target_contract_version') == 2, 'Unit exports require generated input guards')
    return '''"""Generated source-derived comparison tests. Run this file with Python 3.

This bounded suite does not establish observed mainframe parity.
"""
import copy
import hashlib
import json
from pathlib import Path
import unittest

HERE = Path(__file__).resolve()
BASE = HERE.parents[3]
RUN = HERE.parents[1].name
PROGRAM = '''+repr(program['name'])+'''
EXPECTED_HASH = '''+repr(sha(encode(suite)))+'''
TARGET_HASH = '''+repr(target_hash)+'''
SOURCE_HASH = '''+repr(program['source_hash'])+'''
raw = (BASE / 'synthetic' / RUN / PROGRAM / 'expected.json').read_bytes()
if hashlib.sha256(raw).hexdigest() != EXPECTED_HASH:
    raise ValueError('Expected suite hash mismatch')
suite = json.loads(raw)
raw = (BASE / 'target' / RUN / (PROGRAM + '.py')).read_bytes()
if hashlib.sha256(raw).hexdigest() != TARGET_HASH:
    raise ValueError('Target hash mismatch')
namespace = {'__builtins__': {}, 'dict': dict, 'type': type, 'int': int, 'str': str, 'len': len}
exec(compile(raw.decode('utf-8'), '<pinned-generated-target>', 'exec'), namespace)

class SourceComparisonTests(unittest.TestCase):
    pass

def comparison(case):
    def test(self):
        record = copy.deepcopy(case['record'])
        actual = namespace['run_program'](record)
        self.assertEqual(json.dumps(actual, sort_keys=True, allow_nan=False), json.dumps(case['expected'], sort_keys=True, allow_nan=False), case['id'])
        self.assertEqual(json.dumps(record, sort_keys=True, allow_nan=False), json.dumps(case['record'], sort_keys=True, allow_nan=False), 'Target mutated caller input: ' + case['id'])
    return test

for index, case in enumerate(suite['cases']):
    setattr(SourceComparisonTests, 'test_case_' + str(index + 1).zfill(6), comparison(case))

if __name__ == '__main__':
    unittest.main()
'''


def run_unit_tests(script, path, checkpoint=None):
    """Execute the canonical export in-process; cancellation and failures propagate."""
    namespace={'__file__':str(Path(path).resolve()),'__name__':'frozen_source_comparison'}
    exec(compile(script,'<generated-unit-tests>','exec'),namespace)
    class Receipt(unittest.TestResult):
        def __init__(self):
            super().__init__();self.issues=[]
        def startTest(self,test):
            if checkpoint:checkpoint()
            super().startTest(test)
        def addFailure(self,test,err):
            super().addFailure(test,err);self.issue(test,err)
        def addError(self,test,err):
            super().addError(test,err);self.issue(test,err)
        def issue(self,test,err):
            self.issues.append({'test':test._testMethodName,'type':type(err[1]).__name__,'message':str(err[1])[:1000]})
    tests=unittest.defaultTestLoader.loadTestsFromTestCase(namespace['SourceComparisonTests'])
    result=Receipt();tests.run(result)
    return {'schema_version':1,'source_hash':namespace['SOURCE_HASH'],
            'suite_hash':namespace['EXPECTED_HASH'],'target_hash':namespace['TARGET_HASH'],
            'test_module_hash':sha(script),'tests_run':result.testsRun,
            'failures':len(result.failures),'errors':len(result.errors),'skipped':len(result.skipped),
            'expected_failures':len(result.expectedFailures),'unexpected_successes':len(result.unexpectedSuccesses),
            'passed':result.wasSuccessful() and not result.skipped and not result.expectedFailures and not result.unexpectedSuccesses and result.testsRun==len(namespace['suite']['cases']) and result.testsRun>0,
            'issues':result.issues,'basis':'FROZEN_SOURCE_EXPECTATIONS','observed_mainframe_parity':False}
