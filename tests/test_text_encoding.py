"""Source text and persisted evidence use UTF-8 independently of host locale."""
import ast
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from workbench.domain import encode, sha
from workbench.fixtures import verify_program, adversarial_review
from workbench.source import analyze_program
from workbench.target import emit_program

ROOT = Path(__file__).resolve().parents[1]


class TextEncodingTests(unittest.TestCase):
    def test_cli_preserves_utf8_source_hash_and_target_comparisons_without_utf8_mode(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory).resolve()
            content = ('*> Fran\u00e7ais \u65e5\u672c\u8a9e source commentary\n' + (ROOT/'examples/Endeavor/ELIGIBLE.cbl').read_text(encoding='utf-8'))
            source = folder/'ELIGIBLE.cbl';source.write_bytes(content.encode('utf-8'))
            layout = (ROOT/'examples/Endeavor/LAYOUT.cpy').read_bytes()
            (folder/'LAYOUT.cpy').write_bytes(layout)
            output = folder/'expected.json'
            env = dict(os.environ, LC_ALL='C', PYTHONUTF8='0', PYTHONCOERCECLOCALE='0')
            env.pop('PYTHONPATH', None)
            result = subprocess.run([sys.executable, '-X', 'utf8=0', str(ROOT/'tools/synthetic_cases.py'),
                                     '--source', str(source), '--copybooks', str(folder), '--output', str(output)],
                                    env=env, cwd=folder, capture_output=True, timeout=30)
            self.assertEqual(result.returncode, 0, result.stderr.decode('ascii', 'backslashreplace'))
            suite = json.loads(output.read_bytes())
            self.assertEqual(suite['source_hash'], sha(source.read_bytes()))
            program = analyze_program(source.name, content, {'LAYOUT.cpy':layout.decode('utf-8')})
            self.assertFalse(program['blockers'])
            program['target_contract_version'] = 2
            code = emit_program(program)
            comparison = verify_program(program, code, suite)
            self.assertEqual(comparison['differences'], [])
            self.assertFalse(comparison['observed_legacy_parity'])
            self.assertTrue(adversarial_review(program, code, suite)['passed'])

    def test_new_cli_fixtures_use_current_randomized_twenty_state_contract(self):
        env = dict(os.environ);env.pop('PYTHONPATH', None)
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory).resolve()
            source = folder/'ELIGIBLE.cbl';source.write_bytes((ROOT/'examples/Endeavor/ELIGIBLE.cbl').read_bytes())
            (folder/'LAYOUT.cpy').write_bytes((ROOT/'examples/Endeavor/LAYOUT.cpy').read_bytes())
            suites = []
            for index in range(2):
                output = folder/(f'expected-{index}.json')
                result = subprocess.run([sys.executable, str(ROOT/'tools/synthetic_cases.py'),
                                         '--source', str(source), '--copybooks', str(folder), '--output', str(output)],
                                        env=env, cwd=folder, capture_output=True, timeout=30)
                self.assertEqual(result.returncode, 0, result.stderr.decode('utf-8', 'replace'))
                suite = json.loads(output.read_bytes());suites.append(suite)
                self.assertEqual(suite['version'], 4)
                self.assertEqual(suite['coverage']['logic_validation']['minimum_distinct_records_per_logic'], 20)
                self.assertTrue(all(count >= 20 for count in suite['coverage']['randomized_record_counts'].values()))
                self.assertTrue(suite['coverage']['complete'])
                program = analyze_program(source.name, source.read_bytes().decode('utf-8'),
                                          {'LAYOUT.cpy':(folder/'LAYOUT.cpy').read_bytes().decode('utf-8')})
                program['target_contract_version'] = 2
                code = emit_program(program)
                self.assertEqual(verify_program(program, code, suite)['differences'], [])
                self.assertTrue(adversarial_review(program, code, suite)['passed'])
            self.assertNotEqual(suites[0]['seed'], suites[1]['seed'])
            replay = folder/'replay.json'
            result = subprocess.run([sys.executable, str(ROOT/'tools/synthetic_cases.py'),
                                     '--source', str(source), '--copybooks', str(folder), '--output', str(replay),
                                     '--seed', str(suites[0]['seed'])],
                                    env=env, cwd=folder, capture_output=True, timeout=30)
            self.assertEqual(result.returncode, 0, result.stderr.decode('utf-8', 'replace'))
            self.assertEqual(json.loads(replay.read_bytes()), suites[0])


    def test_cli_low_budget_keeps_gaps_and_invalid_replay_seeds_cannot_publish(self):
        env = dict(os.environ);env.pop('PYTHONPATH', None)
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory).resolve()
            source = folder/'ELIGIBLE.cbl';source.write_bytes((ROOT/'examples/Endeavor/ELIGIBLE.cbl').read_bytes())
            (folder/'LAYOUT.cpy').write_bytes((ROOT/'examples/Endeavor/LAYOUT.cpy').read_bytes())
            for seed in (0, -1, 2**63):
                with self.subTest(seed=seed):
                    output = folder/(str(seed)+'.json')
                    result = subprocess.run([sys.executable, str(ROOT/'tools/synthetic_cases.py'),
                                             '--source', str(source), '--copybooks', str(folder), '--output', str(output),
                                             '--budget', '8', '--seed', str(seed)],
                                            env=env, cwd=folder, capture_output=True, timeout=30)
                    if seed == 0:
                        self.assertEqual(result.returncode, 0, result.stderr.decode('utf-8', 'replace'))
                        suite = json.loads(output.read_bytes())
                        self.assertEqual(suite['seed'], 0)
                        self.assertFalse(suite['coverage']['complete'])
                        self.assertGreater(suite['coverage']['logic_validation']['gaps'], 0)
                    else:
                        self.assertNotEqual(result.returncode, 0)
                        self.assertFalse(output.exists())
                        self.assertIn(b'unsigned 63-bit integer', result.stderr)

    def test_cli_copybook_case_preserves_original_names_on_each_platform(self):
        env = dict(os.environ);env.pop('PYTHONPATH', None)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            for index, suffix in enumerate(('.cpy', '.CPY', '.CpY')):
                with self.subTest(suffix=suffix):
                    folder = root/('case-'+str(index));folder.mkdir()
                    source = folder/'ELIGIBLE.cbl';source.write_bytes((ROOT/'examples/Endeavor/ELIGIBLE.cbl').read_bytes())
                    copy_name = 'LAYOUT'+suffix
                    copy_path = folder/copy_name;copy_path.write_bytes((ROOT/'examples/Endeavor/LAYOUT.cpy').read_bytes())
                    output = folder/'expected.json'
                    result = subprocess.run([sys.executable, str(ROOT/'tools/synthetic_cases.py'),
                                             '--source', str(source), '--copybooks', str(folder), '--output', str(output),
                                             '--seed', '12'],
                                            env=env, cwd=folder, capture_output=True, timeout=30)
                    self.assertEqual(result.returncode, 0, result.stderr.decode('utf-8', 'replace'))
                    suite = json.loads(output.read_bytes())
                    program = analyze_program(source.name, source.read_bytes().decode('utf-8'),
                                              {copy_name:copy_path.read_bytes().decode('utf-8')})
                    program['target_contract_version'] = 2
                    self.assertEqual(program['dependencies'][0]['path'], copy_name)
                    self.assertEqual(program['dependencies'][0]['source_hash'], sha(copy_path.read_bytes()))
                    code = emit_program(program)
                    self.assertEqual(verify_program(program, code, suite)['differences'], [])
                    self.assertTrue(adversarial_review(program, code, suite)['passed'])

    def test_standalone_tools_resolve_repository_without_pythonpath_or_repository_cwd(self):
        env = dict(os.environ);env.pop('PYTHONPATH', None)
        with tempfile.TemporaryDirectory() as directory:
            for tool in ('synthetic_cases', 'scenario_campaign', 'demo_e2e'):
                with self.subTest(tool=tool):
                    result = subprocess.run([sys.executable, str(ROOT/'tools'/(tool+'.py')), '--help'],
                                            cwd=directory, env=env, capture_output=True, timeout=30)
                    self.assertEqual(result.returncode, 0, result.stderr.decode('utf-8', 'replace'))
                    self.assertIn(b'usage:', result.stdout)

    def test_cli_preserves_lf_crlf_and_mixed_source_and_copybook_hashes(self):
        source_text = (ROOT/'examples/Endeavor/ELIGIBLE.cbl').read_bytes().decode('utf-8')
        copy_text = (ROOT/'examples/Endeavor/LAYOUT.cpy').read_bytes().decode('utf-8')
        def line_endings(text, mode):
            lines = text.splitlines()
            return ''.join(line + ('\r\n' if mode == 'CRLF' or mode == 'mixed' and i % 2 else '\n')
                           for i, line in enumerate(lines))
        env = dict(os.environ);env.pop('PYTHONPATH', None)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            for mode in ('LF', 'CRLF', 'mixed'):
                with self.subTest(mode=mode):
                    folder = root/mode;folder.mkdir()
                    content = line_endings(source_text, mode)
                    copybook = line_endings(copy_text, mode)
                    source = folder/'ELIGIBLE.cbl';source.write_bytes(content.encode('utf-8'))
                    copy_path = folder/'LAYOUT.cpy';copy_path.write_bytes(copybook.encode('utf-8'))
                    output = folder/'expected.json'
                    result = subprocess.run([sys.executable, str(ROOT/'tools/synthetic_cases.py'),
                                             '--source', str(source), '--copybooks', str(folder), '--output', str(output)],
                                            env=env, cwd=folder, capture_output=True, timeout=30)
                    self.assertEqual(result.returncode, 0, result.stderr.decode('utf-8', 'replace'))
                    suite = json.loads(output.read_bytes())
                    self.assertEqual(suite['source_hash'], sha(source.read_bytes()))
                    program = analyze_program(source.name, content, {'LAYOUT.cpy':copybook})
                    self.assertTrue(any(item['source_hash'] == sha(copy_path.read_bytes()) for item in program['dependencies']))
                    semantic_hash = sha(encode({'source_hash':sha(source.read_bytes()), 'dependencies':program['dependencies']}))
                    self.assertEqual(program['semantic_hash'], semantic_hash)
                    program['target_contract_version'] = 2
                    self.assertEqual(suite['contract_hash'], sha(encode({'source':semantic_hash, 'seed':suite['seed'],
                                                                       'rules':program['rules'], 'fields':program['fields'],
                                                                       'target_contract_version':2, 'fixture_contract_version':4,
                                                                       'min_records_per_logic':20, 'budget':256})))
                    code = emit_program(program)
                    self.assertEqual(verify_program(program, code, suite)['differences'], [])
                    self.assertTrue(adversarial_review(program, code, suite)['passed'])

    def test_repository_text_io_declares_encoding_instead_of_using_system_codepage(self):
        missing = []
        for folder in ('workbench', 'tools'):
            for path in (ROOT/folder).glob('*.py'):
                tree = ast.parse(path.read_text(encoding='utf-8'))
                for node in ast.walk(tree):
                    if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute): continue
                    method = node.func.attr
                    if method not in ('read_text', 'write_text'): continue
                    positional = len(node.args) >= (1 if method == 'read_text' else 2)
                    if not positional and not any(k.arg == 'encoding' for k in node.keywords):
                        missing.append(f'{path.relative_to(ROOT)}:{node.lineno}')
        self.assertEqual(missing, [], 'Implicit locale text I/O can corrupt source hashes and reports')


if __name__ == '__main__':
    unittest.main()
