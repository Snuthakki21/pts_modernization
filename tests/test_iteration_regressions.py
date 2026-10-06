"""Failures reproduced during the thirty-pass review, without live source writes."""
from io import BytesIO
from pathlib import Path
import unittest
from zipfile import ZipFile
import xml.etree.ElementTree as ET

from openpyxl import load_workbook
from workbench.domain import ValidationError
from workbench.domain import checked_zip
from workbench.intake import parse_intake_xlsx

EXAMPLES=Path(__file__).resolve().parents[1]/'examples'


class IterationRegressionTests(unittest.TestCase):
    def workbook(self):
        book=load_workbook(EXAMPLES/'intake-template.xlsx')
        sheet=book['Intake']
        sheet.append([2,'LOSTJOB',1,'S1','SECRET','INPUT','OUTPUT','Always'])
        out=BytesIO();book.save(out);book.close()
        return out.getvalue()

    def forge(self,data,mutate):
        out=BytesIO()
        with ZipFile(BytesIO(data)) as source,ZipFile(out,'w') as target:
            for member in source.infolist():
                raw=source.read(member.filename)
                if member.filename=='xl/worksheets/sheet1.xml':
                    node=ET.fromstring(raw);mutate(node);raw=ET.tostring(node)
                target.writestr(member,raw)
        return out.getvalue()

    def test_forged_intake_dimension_cannot_hide_job_rows(self):
        namespace='{http://schemas.openxmlformats.org/spreadsheetml/2006/main}'
        data=self.forge(self.workbook(),lambda node:node.find(namespace+'dimension').set('ref','A1:H5'))
        with self.assertRaisesRegex(ValidationError,'dimension'):
            parse_intake_xlsx(data)

    def test_actual_intake_row_outside_declared_bounds_is_rejected(self):
        namespace='{http://schemas.openxmlformats.org/spreadsheetml/2006/main}'
        def mutate(node):
            node.find(namespace+'dimension').set('ref','A1:H5')
            row=node.find(namespace+'sheetData')[-1];row.set('r','206')
            for cell in row:cell.set('r',cell.get('r').rstrip('0123456789')+'206')
        data=self.forge(self.workbook(),mutate)
        with self.assertRaises(ValidationError):parse_intake_xlsx(data)

    def test_normal_two_job_intake_preserves_both_jobs(self):
        self.assertEqual([job['name'] for job in parse_intake_xlsx(self.workbook())['jobs']],['REFJOB','LOSTJOB'])

    def test_source_accounting_does_not_resplit_the_program_per_line(self):
        from workbench.source import analyze_program
        from test_source import COBOL
        class CountedText(str):
            calls=0
            def splitlines(self,*args,**kwargs):
                self.calls+=1;return super().splitlines(*args,**kwargs)
        text=CountedText('*> preserved comment\n'*2000+COBOL)
        program=analyze_program('ELIGIBLE.cbl',text,{})
        self.assertEqual(len(program['coverage']),2020)
        self.assertLessEqual(text.calls,3,'Full source should be split a bounded number of times, independent of line count')
        self.assertEqual([row['original'] for row in program['coverage']],str(text).splitlines())

    def test_encoded_xml_declarations_are_rejected_before_parsing(self):
        xml='<?xml version="1.0"?><!DOCTYPE root [<!ENTITY item "expanded">]><root>&item;</root>'
        for encoding in ('utf-8','utf-16','utf-32'):
            out=BytesIO()
            with ZipFile(out,'w') as archive:archive.writestr('file.xml',xml.encode(encoding))
            with self.subTest(encoding=encoding),self.assertRaisesRegex(ValidationError,'declarations'):
                checked_zip(out.getvalue())

    def test_malformed_intake_xml_has_a_named_validation_error(self):
        out=BytesIO()
        with ZipFile(BytesIO(self.workbook())) as source,ZipFile(out,'w') as target:
            for member in source.infolist():
                target.writestr(member,b'<worksheet' if member.filename=='xl/worksheets/sheet1.xml' else source.read(member.filename))
        with self.assertRaisesRegex(ValidationError,'XLSX intake'):
            parse_intake_xlsx(out.getvalue())
