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
        facts=input_locations(self.root)['WEDELX'];self.assertEqual(facts['availability'],'AVAILABLE')
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

    def test_canonical_and_legacy_location_names_share_one_identity(self):
        from workbench.domain import decode
        self.save([]);config=self.root/'knowledge/input-locations.json'
        legacy=input_locations(self.root)
        document=decode(config.read_bytes());document['locations'][0]['name']='WEDELX'
        config.write_bytes(encode(document));canonical=input_locations(self.root)
        self.assertEqual(set(legacy), {'WEDELX'});self.assertEqual(set(canonical), {'WEDELX'})
        self.assertEqual(legacy['WEDELX']['path'],canonical['WEDELX']['path'])
        self.assertNotEqual(legacy['WEDELX']['evidence'][0]['config_hash'],canonical['WEDELX']['evidence'][0]['config_hash'])

    def test_duplicate_aliases_fail_instead_of_overwriting_evidence(self):
        self.save([]);from workbench.domain import decode
        config=self.root/'knowledge/input-locations.json';document=decode(config.read_bytes())
        document['locations'].append(dict(document['locations'][0],name='WEDELX'))
        config.write_bytes(encode(document))
        with self.assertRaisesRegex(ValidationError,'duplicate input location'):input_locations(self.root)

    def test_tran_repository_spelling_is_normalized_and_unknown_name_is_rejected(self):
        self.save([]);from workbench.domain import decode
        config=self.root/'knowledge/input-locations.json';document=decode(config.read_bytes())
        document['locations'][0]['name']='Tran Repository';config.write_bytes(encode(document))
        self.assertEqual(set(input_locations(self.root)),{'TranRepository'})
        document['locations'][0]['name']='Another share';config.write_bytes(encode(document))
        with self.assertRaisesRegex(ValidationError,'Unknown'):input_locations(self.root)
