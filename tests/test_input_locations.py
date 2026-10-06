from pathlib import Path
import tempfile
import unittest
from workbench.locations import input_locations
from workbench.domain import encode,ValidationError

class InputLocationTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name);(self.root/'knowledge').mkdir();(self.root/'share').mkdir()
    def save(self,bindings):
        (self.root/'knowledge/input-locations.json').write_bytes(encode({'schema_version':1,'locations':[{'name':'WEDLX','path':str(self.root/'share'),'bindings':bindings}]}))
    def test_missing_configuration_remains_unknown(self):self.assertEqual(input_locations(self.root),{})
    def test_exact_bindings_observe_missing_and_present_without_readiness_claim(self):
        (self.root/'share/referral.dat').write_bytes(b'not uploaded or executed')
        self.save([{'logical_id':'REFERRAL','file':'referral.dat'},{'logical_id':'LOOKUP','file':'missing.dat'}])
        facts=input_locations(self.root)['WEDLX'];self.assertEqual(facts['availability'],'AVAILABLE')
        self.assertEqual([r['available'] for r in facts['evidence'][0]['bindings']],[True,False]);self.assertEqual(facts['readiness'],'Unknown')
    def test_path_escape_is_rejected(self):
        self.save([{'logical_id':'REFERRAL','file':'../outside'}])
        with self.assertRaises(ValidationError):input_locations(self.root)
    def test_symlink_is_rejected(self):
        (self.root/'share/link').symlink_to(self.root/'knowledge');self.save([{'logical_id':'REFERRAL','file':'link'}])
        with self.assertRaises(ValidationError):input_locations(self.root)
    def test_duplicate_logical_binding_is_rejected(self):
        self.save([{'logical_id':'REFERRAL','file':'one'},{'logical_id':'REFERRAL','file':'two'}])
        with self.assertRaises(ValidationError):input_locations(self.root)
