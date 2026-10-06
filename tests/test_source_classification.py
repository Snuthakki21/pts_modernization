"""Classification guides parsing but never grants executable conversion credit."""
import copy
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from workbench.domain import ValidationError, encode
from workbench.intake import parse_manifest
from workbench.source import analyze_sources, sql_table_references
from test_source import COBOL
from test_workflow import MANIFEST


class ClassifiedSourceTests(unittest.TestCase):
    def setUp(self):
        from workbench.mainframe import load_knowledge
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.manifest = parse_manifest(MANIFEST)
        self.manifest['mainframe_knowledge'] = load_knowledge(Path(self.tmp.name))

    def test_extensionless_program_copybook_and_job_keep_source_accountability(self):
        source = COBOL.replace('  05 AGE PIC 9(3).', 'COPY AGECOPY.')
        files = {'ELIGIBLE':source, 'AGECOPY':'05 AGE PIC 9(3).\n',
                 'JOBA':'//JOBA JOB\n//S010 EXEC PGM=ELIGIBLE\n'}
        analysis = analyze_sources(files, self.manifest)
        self.assertFalse(analysis['blockers'])
        self.assertEqual(set(analysis['programs']), {'ELIGIBLE'})
        self.assertEqual(analysis['programs']['ELIGIBLE']['dependencies'][0]['path'], 'AGECOPY')
        kinds = {a['path']:a['kind'] for a in analysis['assets']}
        self.assertEqual(kinds, {'ELIGIBLE':'cobol_program', 'AGECOPY':'copybook', 'JOBA':'jcl_job'})
        self.assertEqual(len(analysis['source_accounting']['ELIGIBLE']), len(source.splitlines()))
        self.assertTrue(all(c['conversion_support']=='not_established' for c in analysis['classifications'].values()))

    def test_content_extension_conflict_never_selects_executable_parser(self):
        analysis = analyze_sources({'ELIGIBLE.cpy':COBOL}, self.manifest)
        self.assertEqual(analysis['classifications']['ELIGIBLE.cpy']['kind'], 'ambiguous')
        self.assertFalse(analysis['programs'])
        self.assertEqual(analysis['assets'][0]['kind'], 'other_source')
        self.assertEqual(analysis['assets'][0]['source_text'], COBOL)
        self.assertTrue(any(b['kind']=='source_classification' for b in analysis['blockers']))

    def test_unknown_file_has_no_borrowed_sql_comment_exclusion(self):
        source = '-- UNKNOWN APPLICATION CONTROL RECORD\nXZY=42\n'
        analysis = analyze_sources({'ELIGIBLE.cbl':COBOL, 'UNRECOGNIZED':source}, self.manifest)
        asset = next(a for a in analysis['assets'] if a['path']=='UNRECOGNIZED')
        self.assertEqual(asset['kind'], 'other_source')
        self.assertEqual(asset['loc'], {'physical':2, 'code':2})
        self.assertTrue(asset['selected'])
        self.assertTrue(any(b.get('path')=='UNRECOGNIZED' for b in analysis['blockers']))

    def test_sql_comments_and_literals_do_not_inflate_table_reference_counts(self):
        sql = '''-- SELECT * FROM FALSE_COMMENT
/* INSERT INTO FALSE_BLOCK VALUES (1); /* FROM FALSE_NESTED */ */
SELECT 'FROM FALSE_LITERAL', 'escaped '' FROM FALSE_ESCAPED'
FROM actual.table_a JOIN actual.table_b ON table_a.id = table_b.id;
CREATE TABLE actual.table_c (id INTEGER);
SELECT * FROM FINAL TABLE (INSERT INTO actual.table_d VALUES (1));
SELECT * FROM "DELIMITED_TABLE";
'''
        analysis = analyze_sources({'ELIGIBLE':COBOL, 'QUERY.sql':sql}, self.manifest)
        asset = next(a for a in analysis['assets'] if a['path']=='QUERY.sql')
        self.assertEqual(asset['tables'], ['ACTUAL.TABLE_A','ACTUAL.TABLE_B','ACTUAL.TABLE_C','ACTUAL.TABLE_D'])
        self.assertEqual(asset['table_evidence_basis'], 'STATIC_UNQUOTED_REFERENCES_NOT_CATALOG_INVENTORY')
        self.assertTrue(any(b.get('path')=='QUERY.sql' for b in analysis['blockers']))

    def test_unclosed_sql_literal_or_comment_cannot_expose_fake_references(self):
        self.assertEqual(sql_table_references("SELECT * FROM REAL_TABLE; ' FROM FAKE_TABLE"), ['REAL_TABLE'])
        self.assertEqual(sql_table_references('SELECT * FROM REAL_TABLE; /* FROM FAKE_TABLE'), ['REAL_TABLE'])
        self.assertEqual(sql_table_references('SELECT * FROM "QUOTED" JOIN REAL_TABLE ON 1=1'), ['REAL_TABLE'])
        self.assertEqual(sql_table_references('SELECT * FROM APP."QUOTED" JOIN REAL_TABLE ON 1=1'), ['REAL_TABLE'])

    def test_empty_unknown_file_is_visible_and_blocked(self):
        analysis = analyze_sources({'ELIGIBLE':COBOL, 'EMPTY':''}, self.manifest)
        self.assertEqual(analysis['classifications']['EMPTY']['kind'], 'unknown')
        asset = next(a for a in analysis['assets'] if a['path']=='EMPTY')
        self.assertEqual(asset['loc'], {'physical':0,'code':0})
        self.assertTrue(any(b.get('path')=='EMPTY' for b in analysis['blockers']))

    def test_jcl_special_names_are_recognized_but_unsupported_cards_block(self):
        files = {'ELIGIBLE':COBOL, 'JOBA':'//JOBA JOB\n//S@01 EXEC PGM=ELIGIBLE\n'}
        analysis = analyze_sources(files, self.manifest)
        self.assertEqual(analysis['classifications']['JOBA']['kind'], 'jcl_job')
        self.assertTrue(any(b['kind']=='unsupported_jcl' for b in analysis['blockers']))

    def test_recognized_utility_requires_adapter_and_evidence(self):
        manifest = copy.deepcopy(self.manifest)
        manifest['jobs'][0]['steps'][0]['program'] = 'IDCAMS'
        analysis = analyze_sources({'JOBA':'//JOBA JOB\n//S010 EXEC PGM=IDCAMS\n'}, manifest)
        self.assertFalse(analysis['programs'])
        finding = next(f for f in analysis['utility_findings'] if f['program']=='IDCAMS')
        self.assertEqual(finding['conversion_support'], 'adapter_required')
        blocker = next(b for b in analysis['blockers'] if b['kind']=='unsupported_utility')
        self.assertIn('no verified executable adapter', blocker['message'])
        self.assertIn('Required evidence:', blocker['message'])
        self.assertEqual(blocker['job'], 'JOBA')
        self.assertEqual(blocker['step'], 'S010')

    def test_utility_in_export_but_missing_from_manifest_is_visible(self):
        files = {'ELIGIBLE':COBOL, 'JOBA':'//JOBA JOB\n//S010 EXEC PGM=ELIGIBLE\n//S020 EXEC PGM=IDCAMS\n'}
        analysis = analyze_sources(files, self.manifest)
        finding = next(f for f in analysis['utility_findings'] if f['program']=='IDCAMS')
        self.assertEqual(finding['conversion_support'], 'adapter_required')
        self.assertTrue(any(b['kind']=='unsupported_utility' and b.get('path')=='JOBA' for b in analysis['blockers']))
        self.assertTrue(any(b['kind']=='scope_mismatch' for b in analysis['blockers']))

    def test_jcl_procedure_is_preserved_without_job_or_conversion_credit(self):
        source = '//UTIL PROC\n//S1 EXEC PGM=IEFBR14\n// PEND\n'
        analysis = analyze_sources({'ELIGIBLE':COBOL, 'UTIL':source}, self.manifest)
        self.assertEqual(analysis['classifications']['UTIL']['kind'], 'jcl_proc')
        asset = next(a for a in analysis['assets'] if a['path']=='UTIL')
        self.assertEqual(asset['kind'], 'other_source')
        self.assertEqual(asset['source_text'], source)
        self.assertTrue(any(b.get('path')=='UTIL' and b['kind']=='unsupported_source' for b in analysis['blockers']))

    def test_duplicate_extensionless_copybooks_do_not_choose_first_match(self):
        source = COBOL.replace('  05 AGE PIC 9(3).', 'COPY AGECOPY.')
        files = {'ELIGIBLE':source, 'one/AGECOPY':'05 AGE PIC 9(3).\n',
                 'two/AGECOPY':'05 AGE PIC 9(3).\n'}
        analysis = analyze_sources(files, self.manifest)
        self.assertTrue(any('Copybook missing or ambiguous' in b['message'] for b in analysis['blockers']))
        self.assertEqual(len(analysis['programs']['ELIGIBLE']['dependencies']), 2)
        self.assertTrue(all(d['resolution']=='ambiguous' for d in analysis['programs']['ELIGIBLE']['dependencies']))

    def test_invalid_frozen_knowledge_fails_before_source_analysis(self):
        manifest = copy.deepcopy(self.manifest)
        manifest['mainframe_knowledge']['content_hash'] = '0'*64
        with self.assertRaises(ValidationError):
            analyze_sources({'ELIGIBLE':COBOL}, manifest)

    def test_frozen_snapshot_is_not_replaced_by_current_catalog(self):
        files = {'ELIGIBLE':COBOL}
        first = encode(analyze_sources(files, self.manifest))
        with patch('workbench.mainframe.load_knowledge', side_effect=AssertionError('Mutable knowledge must not be reloaded')):
            self.assertEqual(encode(analyze_sources(files, self.manifest)), first)

    def test_legacy_analysis_does_not_reclassify_or_add_new_keys(self):
        manifest = parse_manifest(MANIFEST)
        with patch('workbench.mainframe.classify_files', side_effect=AssertionError('Historical replay must preserve its parser')):
            analysis = analyze_sources({'ELIGIBLE':COBOL}, manifest)
        self.assertNotIn('classifications', analysis)
        self.assertNotIn('utility_findings', analysis)
        self.assertFalse(analysis['programs'])
        self.assertEqual(analysis['assets'][0]['kind'], 'other_source')


if __name__ == '__main__':
    unittest.main()
