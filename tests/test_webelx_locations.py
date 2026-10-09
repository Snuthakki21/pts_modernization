"""Canonical WEBELX bindings retain historical WEDLX without silent identity rewrites."""
import tempfile,unittest
from pathlib import Path
from workbench.domain import encode,ValidationError
from workbench.locations import input_locations
from workbench.lineage import map_lineage
from workbench.setup import save_workstation
class WebelxLocationTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name).resolve();(self.root/'knowledge').mkdir();(self.root/'share').mkdir()
 def write(self,names):
  raw=encode({'schema_version':1,'locations':[{'name':name,'path':str(self.root/'share'),'bindings':[]} for name in names]});p=self.root/'knowledge/input-locations.json';p.write_bytes(raw);return p,raw
 def test_canonical_binding_is_accepted_without_rewriting_evidence(self):
  p,raw=self.write(['WEBELX']);self.assertEqual(set(input_locations(self.root)),{'WEBELX'});self.assertEqual(p.read_bytes(),raw)
 def test_legacy_binding_is_still_exact(self):
  p,raw=self.write(['WEDLX']);self.assertEqual(set(input_locations(self.root)),{'WEDLX'});self.assertEqual(p.read_bytes(),raw)
 def test_aliases_cannot_claim_two_distinct_locations(self):
  self.write(['WEDLX','WEBELX'])
  with self.assertRaises(ValidationError):input_locations(self.root)
 def test_new_form_override_uses_canonical_name(self):
  save_workstation(self.root,{'source_mode':'upload','wedlx_folder':str(self.root/'share')})
  self.assertEqual(set(input_locations(self.root)),{'WEBELX'})
 def test_existing_override_preserves_old_binding_identity(self):
  p,raw=self.write(['WEDLX']);save_workstation(self.root,{'source_mode':'upload','wedlx_folder':str(self.root/'share')});self.assertEqual(set(input_locations(self.root)),{'WEDLX'});self.assertEqual(p.read_bytes(),raw)
 def test_job_led_webelx_location_metadata_is_selected_without_data_reads(self):
  manifest={'id':'Example','name':'Example','jobs':[{'name':'NIGHT','order':1,'steps':[{'name':'S1','order':1,'program':'MAIN','inputs':['WEBELX'],'outputs':[]}]}],'application_input_locations':{'WEBELX':{'path':'UNKNOWN_EXAMPLE_PATH','evidence':[]}}}
  files={'NIGHT.jcl':'//NIGHT JOB\n//S1 EXEC PGM=MAIN','MAIN.cbl':'PROGRAM-ID. MAIN.\nGOBACK.'}
  result=map_lineage(files,manifest);locations=[n for n in result['nodes'] if n['kind']=='input_location' and n['selected']]
  self.assertEqual({n['name'] for n in locations},{'WEBELX'});self.assertEqual(result['closure']['input_data_readiness'],'Unknown')

 def test_legacy_context_is_preserved_when_current_spelling_selects_location(self):
  manifest={'id':'Example','name':'Example','jobs':[{'name':'NIGHT','order':1,'steps':[{'name':'S1','order':1,'program':'MAIN','inputs':['WEBELX'],'outputs':[]}]}],'application_input_locations':{'WEDLX':{'path':'EXACT_LEGACY_FOLDER','evidence':[{'bindings':[{'logical_id':'EXAMPLE.INPUT','available':True,'basis':'READ_ONLY_FILE_METADATA_NO_BUSINESS_READINESS_CLAIM'}]}]}}}
  files={'NIGHT.jcl':'//NIGHT JOB\n//S1 EXEC PGM=MAIN\n//IN DD DSN=EXAMPLE.INPUT,DISP=SHR','MAIN.cbl':'PROGRAM-ID. MAIN.\nGOBACK.'}
  result=map_lineage(files,manifest);locations=[n for n in result['nodes'] if n['kind']=='input_location' and n['selected']]
  self.assertEqual({n['name'] for n in locations},{'WEDLX'});self.assertEqual(locations[0]['physical_path'],'EXACT_LEGACY_FOLDER')
  self.assertFalse(any(x.get('name')=='EXAMPLE.INPUT' for x in result['closure']['gaps']))
 def test_lowercase_current_input_is_location_even_without_context(self):
  manifest={'id':'Example','name':'Example','jobs':[{'name':'NIGHT','order':1,'steps':[{'name':'S1','order':1,'program':'MAIN','inputs':['webelx'],'outputs':[]}]}]}
  result=map_lineage({'NIGHT.jcl':'//NIGHT JOB\n//S1 EXEC PGM=MAIN','MAIN.cbl':'PROGRAM-ID. MAIN.\nGOBACK.'},manifest)
  self.assertEqual({n['name'] for n in result['nodes'] if n['kind']=='input_location' and n['selected']},{'WEBELX'})
