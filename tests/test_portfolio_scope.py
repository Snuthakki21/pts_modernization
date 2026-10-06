import tempfile
import unittest
from pathlib import Path

from workbench.intake import parse_manifest
from workbench.ledger import Ledger
from workbench.reports import portfolio
from workbench.source import analyze_sources


EXAMPLES=Path(__file__).resolve().parent.parent/'examples'


class PortfolioScopeTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.ledger=Ledger(self.tmp.name);self.addCleanup(self.ledger.close)
        self.manifest=(EXAMPLES/'process-input.md').read_text()
        self.files={p.name:p.read_text() for p in (EXAMPLES/'Endeavor').iterdir() if p.is_file()}
        self.files['UNUSED.cbl']=self.files['ELIGIBLE.cbl'].replace('PROGRAM-ID. ELIGIBLE.','PROGRAM-ID. UNUSED.')
        self.files['UNUSED.cpy']='01 UNUSED-LAYOUT.\n  05 UNUSED-FIELD PIC 9.\n'

    def add(self,pid,program='ELIGIBLE',demo=False):
        manifest=parse_manifest(self.manifest.replace('example-referral',pid).replace('| ELIGIBLE |','| '+program+' |'))
        doc=self.ledger.create(manifest,demo)
        doc['analysis']=analyze_sources(self.files,manifest)
        self.ledger.register_assets(pid,doc['analysis']['assets']);self.ledger.save(doc)
        return doc

    def test_exported_unused_programs_and_copybooks_do_not_inflate_scope(self):
        self.add('process-a')
        model=portfolio(self.ledger)
        self.assertEqual(model['unique_program_versions'],1)
        self.assertEqual(model['discovered_program_versions'],2)
        self.assertEqual(model['unique_copybook_versions'],1)
        self.assertEqual(model['discovered_copybook_versions'],2)
        self.assertEqual(model['program_memberships'],1)

    def test_selection_by_later_process_overrides_first_asset_membership_scope(self):
        self.add('process-a');self.add('process-b','UNUSED')
        # The global asset cache retains the first process's out-of-scope flag.
        cached=next(a for a in self.ledger.assets() if a['kind']=='cobol_program' and a['name']=='UNUSED')
        self.assertFalse(cached['selected'])
        model=portfolio(self.ledger)
        self.assertEqual(model['unique_program_versions'],2)
        self.assertEqual(model['discovered_program_versions'],2)
        self.assertEqual(model['program_memberships'],2)

    def test_selected_shared_versions_are_deduplicated_but_memberships_are_retained(self):
        self.add('process-a');self.add('process-b')
        model=portfolio(self.ledger)
        self.assertEqual(model['unique_program_versions'],1)
        self.assertEqual(model['unique_copybook_versions'],1)
        self.assertEqual(model['program_memberships'],2)

    def test_demo_selection_does_not_expand_production_scope(self):
        self.add('process-a');self.add('demo-b','UNUSED',True)
        model=portfolio(self.ledger)
        self.assertEqual(model['processes'],1)
        self.assertEqual(model['unique_program_versions'],1)
        self.assertEqual(model['program_memberships'],1)

    def test_unanalyzed_process_does_not_create_program_scope(self):
        self.ledger.create(parse_manifest(self.manifest))
        model=portfolio(self.ledger)
        self.assertEqual(model['unique_program_versions'],0)
        self.assertEqual(model['discovered_program_versions'],0)
        self.assertEqual(model['program_memberships'],0)


if __name__=='__main__':unittest.main()
