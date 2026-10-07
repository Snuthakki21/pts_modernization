"""Native Windows junction checks, with deterministic junction witnesses elsewhere."""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from workbench.domain import ValidationError, atomic_bytes, encode, safe_path, sha, write_new
from workbench.instance import InstanceLock
from workbench.layout import validate_workspace
from workbench.preflight import _read_sources, initialize_knowledge


class PlatformPathTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='platform paths ')
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name).absolute()
        self.root = self.base / 'workspace with spaces'
        self.root.mkdir()
        self.external = self.base / 'outside workspace'
        self.external.mkdir()
        self.junctions = set()
        if os.name != 'nt':
            # A marked directory exercises the decision without claiming NTFS.
            self.junction_patch = patch.object(Path, 'is_junction',
                                               lambda path: path.absolute() in self.junctions)
            self.junction_patch.start()
            self.addCleanup(self.junction_patch.stop)

    def junction(self, path, destination):
        path.parent.mkdir(parents=True, exist_ok=True)
        if os.name == 'nt':
            result = subprocess.run([os.environ['COMSPEC'], '/d', '/c', 'mklink', '/J',
                                     str(path), str(destination)], capture_output=True,
                                    text=True, errors='replace', timeout=10)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertTrue(path.is_junction())
            self.assertFalse(path.is_symlink())
            self.addCleanup(lambda: path.rmdir() if path.is_junction() else None)
        else:
            path.mkdir()
            self.junctions.add(path.absolute())
        return path

    def test_junction_root_and_parent_block_before_writer_or_knowledge_creation(self):
        alias = self.junction(self.base / 'junction root', self.external)
        for root in (alias, alias / 'not yet created'):
            with self.subTest(root=root):
                with self.assertRaises(ValidationError): safe_path(root, 'analysis/evidence.json')
                with self.assertRaises(ValidationError): InstanceLock(root)
                self.assertTrue(validate_workspace(root))
        with self.assertRaises(ValidationError): initialize_knowledge(alias)
        self.assertEqual(list(self.external.iterdir()), [])
        self.assertFalse((alias / 'not yet created').exists())

    def test_nested_junction_blocks_immutable_and_mutable_output_before_write(self):
        alias = self.junction(self.root / 'processes/process-a/analysis', self.external)
        marker = self.external / 'existing.json'
        marker.write_bytes(b'original bytes')
        with self.assertRaises(ValidationError):
            safe_path(self.root, 'processes/process-a/analysis/new.json')
        with self.assertRaises(ValidationError): write_new(alias / 'new.json', b'new')
        with self.assertRaises(ValidationError): atomic_bytes(alias / 'existing.json', b'replaced')
        self.assertEqual(marker.read_bytes(), b'original bytes')
        self.assertEqual([path.name for path in self.external.iterdir()], ['existing.json'])

    def test_layout_prunes_junction_without_enumerating_its_destination(self):
        alias = self.junction(self.root / 'knowledge/inbox', self.external)
        (self.external / 'private.md').write_bytes(b'private destination')
        original_scan = os.scandir
        def scan(path):
            self.assertNotEqual(Path(path).absolute(), alias.absolute(),
                                'Layout must not enumerate a junction destination')
            return original_scan(path)
        with patch('os.scandir', scan):
            issues = validate_workspace(self.root)
        self.assertTrue(any('knowledge/inbox' in issue for issue in issues), issues)

    def test_source_folder_junction_is_rejected_before_export_read(self):
        alias = self.junction(self.base / 'source junction', self.external)
        (self.external / 'PROGRAM.cbl').write_bytes(b'IDENTIFICATION DIVISION.')
        with patch('workbench.preflight.os.scandir', side_effect=AssertionError('Do not read the linked export')):
            with self.assertRaises(ValidationError): _read_sources(self.root, alias)

    def test_redirected_queue_entries_retire_and_allow_bounded_command_progress(self):
        from workbench.local_agent import COMMANDS, MAX_BATCH, RESULTS, drain_commands
        from types import SimpleNamespace
        inbox = self.root/COMMANDS;inbox.mkdir(parents=True)
        marker = self.external/'preserved.txt';marker.write_bytes(b'outside target stays intact')
        redirects = []
        for index in range(MAX_BATCH):
            path = inbox/(f'{index:032x}' + '.json')
            if os.name == 'nt':
                self.junction(path, self.external)
            else:
                # Real POSIX directory symlinks exercise retirement; no fake
                # directory deletion is presented as native junction behavior.
                path.symlink_to(self.external, target_is_directory=True)
            redirects.append(path)
        command_id = f'{MAX_BATCH:032x}'
        document = {'version':1, 'command_id':command_id, 'process_id':'process-a',
                    'action':'inspect', 'payload':{}}
        document['command_hash'] = sha(encode(document))
        (inbox/(command_id+'.json')).write_bytes(encode(document))
        calls = []
        coordinator = SimpleNamespace(root=self.root,
                                      local_agent_action=lambda *args: calls.append(args) or {'intact':True})
        drain_commands(coordinator);drain_commands(coordinator)
        self.assertEqual(calls, [('process-a', 'inspect', {})])
        self.assertEqual(list(inbox.iterdir()), [])
        self.assertEqual(marker.read_bytes(), b'outside target stays intact')
        self.assertEqual([p.name for p in self.external.iterdir()], ['preserved.txt'])
        import json
        result = json.loads((self.root/RESULTS/(command_id+'.json')).read_bytes())
        self.assertEqual(result['status'], 'DONE')
        for path in redirects:
            result = json.loads((self.root/RESULTS/path.name).read_bytes())
            self.assertEqual(result['status'], 'REJECTED')

    def test_sibling_prefix_and_cwd_do_not_expand_relative_output_scope(self):
        sibling = self.base / (self.root.name + ' extra')
        sibling.mkdir()
        previous = Path.cwd()
        try:
            os.chdir(self.base)
            for relative in ('../' + sibling.name + '/state.json', '/state.json',
                             'analysis/../../' + sibling.name + '/state.json'):
                with self.subTest(relative=relative):
                    with self.assertRaises(ValidationError): safe_path(Path(self.root.name), relative)
            self.assertEqual(safe_path(Path(self.root.name), 'analysis/state.json'),
                             self.root / 'analysis/state.json')
        finally:
            os.chdir(previous)
        self.assertEqual(list(sibling.iterdir()), [])


if __name__ == '__main__': unittest.main()
