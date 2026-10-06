import tempfile
import unittest
from pathlib import Path

from workbench.domain import ValidationError, safe_path
from workbench.intake import parse_manifest
from workbench.ledger import Ledger

MANIFEST = '''# Referral process
- Process ID: poc-001
- Process name: Referral eligibility
| Job order | Job | Step order | Step | Program or utility | Input files/tables | Output files/tables | Condition or dependency |
|---|---|---|---|---|---|---|---|
| 2 | JOBB | 1 | S010 | RULES | INPUT | OUTPUT | Always |
| 1 | JOBA | 2 | S020 | RULES | INPUT | OUTPUT | RC <= 4 |
| 1 | JOBA | 1 | S010 | RULES | INPUT | OUTPUT | Always |
'''


class FoundationTests(unittest.TestCase):
    def test_portable_identity_and_paths_reject_device_names_and_control_characters(self):
        from workbench.domain import identity
        for name in ('CON','NUL','com1','LPT9'):
            with self.subTest(name=name),self.assertRaises(ValidationError):identity(name)
        with tempfile.TemporaryDirectory() as t:
            for path in ('source\x00.cbl','bad\nname.cbl','folder/NUL.cpy','file.cbl.','trailing '):
                with self.subTest(path=path),self.assertRaises(ValidationError):safe_path(t,path)
    def test_manifest_preserves_order_and_conditions(self):
        p = parse_manifest(MANIFEST)
        self.assertEqual(p['id'], 'poc-001')
        self.assertEqual([j['name'] for j in p['jobs']], ['JOBA', 'JOBB'])
        self.assertEqual([s['name'] for s in p['jobs'][0]['steps']], ['S010', 'S020'])
        self.assertEqual(p['jobs'][0]['steps'][1]['condition'], 'RC <= 4')

    def test_rejects_unsafe_identity_and_duplicate_step(self):
        with self.assertRaises(ValidationError):
            parse_manifest(MANIFEST.replace('poc-001', '../escape'))
        with self.assertRaises(ValidationError):
            parse_manifest(MANIFEST.replace('| 1 | JOBA | 2 | S020', '| 1 | JOBA | 1 | S010'))

    def test_path_escape_and_symlink_rejected(self):
        with tempfile.TemporaryDirectory() as t:
            root = Path(t)
            with self.assertRaises(ValidationError): safe_path(root, '../escape')
            (root/'link').symlink_to(root.parent, target_is_directory=True)
            with self.assertRaises(ValidationError): safe_path(root, 'link/file')

    def test_durable_events_and_single_packet_quota(self):
        with tempfile.TemporaryDirectory() as t:
            ledger = Ledger(Path(t))
            ledger.create(parse_manifest(MANIFEST))
            ledger.event('poc-001', 'analysis', 'Started analysis')
            ledger.issue_packet('poc-001', 'hash-one')
            with self.assertRaises(ValidationError): ledger.issue_packet('poc-001', 'hash-two')
            ledger.close()
            ledger = Ledger(Path(t))
            self.assertEqual(ledger.get('poc-001')['packet_hash'], 'hash-one')
            self.assertEqual(ledger.events('poc-001')[0]['message'], 'Started analysis')
            with self.assertRaises(ValidationError): ledger.create(parse_manifest(MANIFEST))
            ledger.close()


if __name__ == '__main__': unittest.main()
