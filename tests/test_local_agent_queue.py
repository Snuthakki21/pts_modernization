"""Local command queue contracts, independent of Coordinator integration."""
import tempfile
import random
import secrets
import unittest
from pathlib import Path
from unittest.mock import patch

from workbench.domain import ValidationError, decode, encode, sha
from workbench.local_agent import COMMANDS, RESULTS, drain_commands, submit_command


class QueueCoordinator:
    def __init__(self, root):
        self.root = root
        self.calls = []
        self.fail = None

    def local_agent_action(self, process_id, action, payload):
        self.calls.append((process_id, action, payload))
        if self.fail:
            raise self.fail
        return {'process_id': process_id, 'action': action}


class LocalAgentQueueTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name).resolve()
        self.coordinator = QueueCoordinator(self.root)
        (self.root / COMMANDS).mkdir(parents=True)
        self.command_id = 'a' * 32

    def command(self, command_id=None, **changes):
        value = {'version': 1, 'command_id': command_id or self.command_id,
                 'process_id': 'PROCESS', 'action': 'inspect', 'payload': {}, **changes}
        value['command_hash'] = sha(encode(value))
        return value

    def pending(self, document=None, filename=None):
        document = document or self.command()
        path = self.root / COMMANDS / (filename or document['command_id'] + '.json')
        path.write_bytes(encode(document))
        return path

    def result(self, command_id=None):
        return decode((self.root / RESULTS / ((command_id or self.command_id) + '.json')).read_bytes())

    def test_unrelated_files_do_not_starve_valid_commands(self):
        for index in range(20):
            (self.root / COMMANDS / f'junk-{index}.txt').write_text('unrelated')
        pending = self.pending()
        folder = self.root / COMMANDS
        ordered = sorted((p for p in folder.iterdir() if p != pending), key=lambda p: p.name) + [pending]
        original = Path.iterdir
        with patch.object(Path, 'iterdir', lambda path: iter(ordered) if path == folder else original(path)):
            drain_commands(self.coordinator)
        self.assertEqual(len(self.coordinator.calls), 1)
        self.assertEqual(self.result()['status'], 'DONE')

    def test_unexpected_action_error_does_not_stop_following_command(self):
        self.pending(self.command(action='refresh'))
        second = self.command('b' * 32)
        self.pending(second)
        original = self.coordinator.local_agent_action
        def action(*args):
            if args[1] == 'refresh':
                self.coordinator.calls.append(args)
                raise RuntimeError('unexpected failure')
            return original(*args)
        self.coordinator.local_agent_action = action
        drain_commands(self.coordinator)
        self.assertEqual(len(self.coordinator.calls), 2)
        self.assertEqual(self.result()['status'], 'INDETERMINATE')
        self.assertEqual(self.result(second['command_id'])['status'], 'DONE')

    def test_completed_command_is_idempotent_and_conflicting_payload_is_preserved(self):
        original = self.command()
        self.pending(original)
        drain_commands(self.coordinator)
        saved = self.result()
        self.pending(original)
        drain_commands(self.coordinator)
        self.assertEqual(len(self.coordinator.calls), 1)
        self.assertEqual(self.result(), saved)
        conflicting = self.command(action='refresh')
        path = self.pending(conflicting)
        drain_commands(self.coordinator)
        self.assertFalse(path.exists())
        self.assertEqual(len(self.coordinator.calls), 1)
        self.assertEqual(self.result(), saved)
        preserved = list((self.root / '.migration/agent-rejected').glob('*'))
        self.assertTrue(any(p.read_bytes() == encode(conflicting) for p in preserved if p.is_file()))

    def test_filename_payload_mismatch_never_calls_action(self):
        self.pending(self.command('b' * 32), self.command_id + '.json')
        drain_commands(self.coordinator)
        self.assertFalse(self.coordinator.calls)
        self.assertEqual(self.result()['status'], 'REJECTED')

    def test_malformed_document_and_symlink_do_not_starve_later_command(self):
        path = self.root / COMMANDS / (self.command_id + '.json')
        path.write_text('{malformed')
        other_id = 'b' * 32
        outside = self.root / 'outside.json'
        outside.write_bytes(encode(self.command(other_id)))
        (self.root / COMMANDS / (other_id + '.json')).symlink_to(outside)
        third = self.command('c' * 32)
        self.pending(third)
        drain_commands(self.coordinator)
        self.assertEqual(len(self.coordinator.calls), 1)
        self.assertEqual(self.result(third['command_id'])['status'], 'DONE')
        self.assertTrue(outside.exists())
        drain_commands(self.coordinator)
        self.assertEqual(len(self.coordinator.calls), 1)

    def test_result_write_failure_never_reexecutes_a_started_mutation(self):
        self.pending(self.command(action='refresh'))
        from workbench import local_agent
        publish = getattr(local_agent, '_publish', None)
        self.assertIsNotNone(publish, 'Queue requires atomic publication')
        def fail_result(path, data):
            if Path(path).parent.name == 'agent-results' and Path(path).name == self.command_id + '.json':
                raise OSError('simulated disk failure')
            return publish(path, data)
        with patch('workbench.local_agent._publish', side_effect=fail_result):
            drain_commands(self.coordinator)
        self.assertEqual(len(self.coordinator.calls), 1)
        drain_commands(self.coordinator)
        self.assertEqual(len(self.coordinator.calls), 1)
        self.assertEqual(self.result()['status'], 'INDETERMINATE')

    def test_client_rejects_wrong_result_identity_and_malformed_result(self):
        destination = self.root / RESULTS / (self.command_id + '.json')
        destination.parent.mkdir(parents=True)
        for value in ([], {'command_hash': self.command()['command_hash'], 'command_id': 'b' * 32,
                           'status': 'DONE', 'result': {}},
                      {'command_hash': self.command()['command_hash'], 'command_id': self.command_id,
                       'status': 'APPROVED', 'result': {}}):
            destination.write_bytes(encode(value))
            with self.subTest(value=value), self.assertRaises(ValidationError):
                submit_command(self.root, 'PROCESS', 'inspect', {}, timeout=.001, command_id=self.command_id)

    def test_client_pending_retry_preserves_bytes_and_id(self):
        first = submit_command(self.root, 'PROCESS', 'inspect', {}, timeout=.001, command_id=self.command_id)
        raw = (self.root / COMMANDS / (self.command_id + '.json')).read_bytes()
        second = submit_command(self.root, 'PROCESS', 'inspect', {}, timeout=.001, command_id=self.command_id)
        self.assertEqual(first, second)
        self.assertEqual(raw, (self.root / COMMANDS / (self.command_id + '.json')).read_bytes())
        with self.assertRaises(ValidationError):
            submit_command(self.root, 'PROCESS', 'refresh', {}, timeout=.001, command_id=self.command_id)
        drain_commands(self.coordinator)
        result = submit_command(self.root, 'PROCESS', 'inspect', {}, timeout=.001, command_id=self.command_id)
        self.assertEqual(result['status'], 'DONE')
        self.assertEqual(len(self.coordinator.calls), 1)

    def test_atomic_publication_never_replaces_conflicting_existing_bytes(self):
        from workbench import local_agent
        publish = getattr(local_agent, '_publish', None)
        self.assertIsNotNone(publish, 'Queue requires atomic publication')
        path = self.root / COMMANDS / (self.command_id + '.json')
        first = encode(self.command())
        self.assertTrue(publish(path, first))
        self.assertFalse(publish(path, encode(self.command(action='refresh'))))
        self.assertEqual(path.read_bytes(), first)
        self.assertEqual(sorted(p.name for p in path.parent.iterdir()), [path.name])

    def test_oversized_command_does_not_block_valid_following_command(self):
        (self.root / COMMANDS / (self.command_id + '.json')).write_bytes(b'x' * 300000)
        self.pending(self.command('b' * 32))
        drain_commands(self.coordinator)
        self.assertEqual(self.result()['status'], 'REJECTED')
        self.assertEqual(len(self.coordinator.calls), 1)

    def test_atomic_command_is_not_visible_until_complete_publication(self):
        from workbench import local_agent
        original = local_agent.os.link
        observed = []
        def link(source, destination):
            if Path(destination).parent.name == 'agent-commands':
                observed.append(decode(Path(source).read_bytes()))
                drain_commands(self.coordinator)
                self.assertEqual(self.coordinator.calls, [])
                self.assertFalse(Path(destination).exists())
            return original(source, destination)
        with patch('workbench.local_agent.os.link', side_effect=link):
            response = submit_command(self.root, 'PROCESS', 'inspect', {}, timeout=.001, command_id=self.command_id)
        self.assertEqual(response['status'], 'PENDING')
        self.assertEqual(observed, [self.command()])
        drain_commands(self.coordinator)
        self.assertEqual(len(self.coordinator.calls), 1)

    def test_retired_request_race_returns_matching_completed_result(self):
        self.pending()
        from workbench import local_agent
        original = local_agent._publish
        def publish(path, data):
            if Path(path).parent.name == 'agent-commands':
                drain_commands(self.coordinator)
                return False
            return original(path, data)
        with patch('workbench.local_agent._publish', side_effect=publish):
            result = submit_command(self.root, 'PROCESS', 'inspect', {}, timeout=.001, command_id=self.command_id)
        self.assertEqual(result['status'], 'DONE')
        self.assertEqual(len(self.coordinator.calls), 1)

    def test_interrupted_marker_with_another_hash_never_executes(self):
        self.pending()
        marker = self.root / RESULTS / (self.command_id + '.started.json')
        marker.parent.mkdir(parents=True)
        marker.write_bytes(encode({'version': 1, 'command_id': self.command_id, 'command_hash': '0' * 64}))
        drain_commands(self.coordinator)
        self.assertEqual(self.coordinator.calls, [])
        self.assertEqual(self.result()['status'], 'REJECTED')

    def test_twenty_randomized_commands_have_one_result_each_across_bounded_batches(self):
        seed = secrets.randbits(63)
        rng = random.Random(seed)
        commands = []
        for index in range(20):
            command_id = format(rng.getrandbits(128), '032x')
            command = self.command(command_id, process_id=f'P{rng.randrange(100000)}',
                                   action=rng.choice(('inspect', 'continue', 'refresh')))
            self.pending(command)
            commands.append(command)
        drain_commands(self.coordinator)
        self.assertEqual(len(self.coordinator.calls), 16, f'seed={seed}')
        drain_commands(self.coordinator)
        self.assertEqual(len(self.coordinator.calls), 20, f'seed={seed}')
        for command in commands:
            with self.subTest(seed=seed, command=command['command_id']):
                result = self.result(command['command_id'])
                self.assertEqual(result['command_hash'], command['command_hash'])
                self.assertEqual(result['result'], {'process_id': command['process_id'], 'action': command['action']})
                self.pending(command)
        drain_commands(self.coordinator)
        drain_commands(self.coordinator)
        self.assertEqual(len(self.coordinator.calls), 20, f'seed={seed}')

    def test_result_symlink_cannot_read_external_result_or_stop_following_commands(self):
        first = self.command()
        self.pending(first)
        outside = self.root / 'outside-result.json'
        outside.write_bytes(encode({'command_id': self.command_id, 'command_hash': first['command_hash'],
                                    'status': 'DONE', 'result': {'private': 'untrusted'}}))
        folder = self.root / RESULTS
        folder.mkdir(parents=True)
        (folder / (self.command_id + '.json')).symlink_to(outside)
        self.pending(self.command('b' * 32))
        with self.assertRaises(ValidationError):
            submit_command(self.root, 'PROCESS', 'inspect', {}, timeout=.001, command_id=self.command_id)
        drain_commands(self.coordinator)
        self.assertEqual(len(self.coordinator.calls), 1)
        self.assertEqual(self.result('b' * 32)['status'], 'DONE')
        self.assertTrue(outside.exists())

    def test_post_publication_error_keeps_retry_identity(self):
        from workbench import local_agent
        original = local_agent._publish
        def publish_then_fail(path, data):
            original(path, data)
            raise OSError('directory sync failed after publication')
        with patch('workbench.local_agent._publish', side_effect=publish_then_fail):
            result = submit_command(self.root, 'PROCESS', 'inspect', {}, timeout=.001, command_id=self.command_id)
        self.assertEqual(result['status'], 'PENDING')
        self.assertEqual(result['command_id'], self.command_id)
        drain_commands(self.coordinator)
        self.assertEqual(len(self.coordinator.calls), 1)
        self.assertEqual(self.result()['status'], 'DONE')

    def test_unsafe_result_is_quarantined_out_of_the_active_queue(self):
        path = self.pending()
        destination = self.root / RESULTS / (self.command_id + '.json')
        destination.parent.mkdir(parents=True)
        destination.symlink_to(self.root / 'missing-external')
        drain_commands(self.coordinator)
        self.assertFalse(path.exists())
        self.assertEqual(self.coordinator.calls, [])
        self.assertEqual(len(list((self.root / '.migration/agent-rejected').iterdir())), 1)
