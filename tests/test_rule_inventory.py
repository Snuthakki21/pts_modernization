"""Rule reporting preserves source evidence, counts and conservative credit."""
import copy
import unittest
from workbench.rule_inventory import build_rule_inventory


class RuleInventoryTests(unittest.TestCase):
    def model(self):
        rule={'id':'R1','plain':'Age must be at least 18','source_start':2,'source_end':3}
        doc={'id':'p','jobs':[{'name':'J1','steps':[{'name':'S1','program':'P'},{'name':'S2','program':'P'}]},
                            {'name':'J2','steps':[{'name':'S1','program':'P'}]}],
             'analysis':{'programs':{'P':{'path':'P.cbl','source_hash':'a','rules':[rule],'coverage':[{'line':4,'disposition':'data_layout'}]}},'assets':[]}}
        rows=[]
        for number,unit,disp in [(2,'r','mapped_verified'),(3,'r','mapped_verified'),(4,'layout','mapped_verified'),(5,'u','blocked'),(6,'v','blocked')]:
            rows.append({'source_path':'P.cbl','source_hash':'a','source_kind':'cobol_program','source_line':number,
                         'unit_id':unit,'source_text':'source '+str(number),'disposition':disp,
                         'target_mappings':[{'file':'shared/target/python/a.py','version':'a','start':1,'end':2}] if disp=='mapped_verified' else [],
                         'tests':['boundary'],'evidence':[{'file':'test.json'}],'reason':'verified' if disp=='mapped_verified' else 'unsupported','replacement':None})
        return doc,{'rows':rows,'summary':{'integrity_errors':[]}}

    def test_unique_rules_and_job_memberships_do_not_inflate_reuse(self):
        doc,cov=self.model(); result=build_rule_inventory(doc,cov)
        self.assertEqual(result['summary']['business_rule']['total'],1)
        self.assertEqual(result['summary']['business_rule']['converted_verified'],1)
        self.assertEqual(result['summary']['unclassified']['total'],1)
        self.assertEqual(len(result['jobs']),2)
        self.assertEqual(result['jobs'][0]['counts']['business_rule']['total'],1)
        rule=next(r for r in result['rules'] if r['category']=='business_rule')
        self.assertEqual(len(rule['memberships']),3)
        self.assertEqual(len(rule['source']),2)
        self.assertEqual(len(result['programs']),1)
        self.assertEqual([r['invocation_memberships'] for r in result['job_programs']],[6,3])

    def test_blocked_line_revokes_rule_credit_and_no_target_is_explicit(self):
        doc,cov=self.model();cov['rows'][1]['disposition']='blocked'
        result=build_rule_inventory(doc,cov)
        self.assertEqual(result['summary']['business_rule']['converted_verified'],0)
        self.assertEqual(result['summary']['business_rule']['blocked'],1)
        gap=next(r for r in result['rules'] if r['category']=='unclassified')
        self.assertEqual(gap['modernized_behavior'],'Not implemented')

    def test_unknown_and_zero_denominators_are_not_success(self):
        doc,cov=self.model();cov['rows']=cov['rows'][-2:]
        result=build_rule_inventory(doc,cov)
        self.assertIsNone(result['summary']['business_rule']['verification_percent'])
        self.assertEqual(result['summary']['unclassified']['blocked'],1)

    def test_inventory_is_pure_and_integrity_errors_revoke_credit(self):
        doc,cov=self.model();before=copy.deepcopy((doc,cov))
        build_rule_inventory(doc,cov);self.assertEqual((doc,cov),before)
        cov['summary']['integrity_errors']=['tampered']
        result=build_rule_inventory(doc,cov)
        self.assertEqual(result['summary']['business_rule']['converted_verified'],0)

    def test_historical_external_adapter_mapping_is_preserved(self):
        import tempfile
        from pathlib import Path
        from workbench import reference
        from workbench.domain import sha
        doc,cov=self.model();cov['rows']=[cov['rows'][2]]
        target=Path(reference.__file__).resolve()
        cov['rows'][0]['target_mappings']=[{'file':str(target),'version':sha(target.read_bytes()),'start':1,'end':2}]
        with tempfile.TemporaryDirectory() as folder:
            report=build_rule_inventory(doc,cov,Path(folder))
        self.assertIn('text',report['rules'][0]['targets'][0])
        self.assertEqual(report['summary']['technical_logic']['converted_verified'],1)

    def test_multi_job_member_assigns_cards_to_own_job_only(self):
        doc,cov=self.model()
        doc['lineage']={'nodes':[{'id':'a','name':'J1','kind':'job','path':'both.jcl'},
                                  {'id':'b','name':'J2','kind':'job','path':'both.jcl'}],'edges':[]}
        template=cov['rows'][2];cov['rows']=[]
        for n,(job,text) in enumerate([('J1','//J1 JOB'),('J1','//S1 EXEC PGM=P'),('J2','//J2 JOB'),('J2','//S1 EXEC PGM=P')],1):
            cov['rows'].append({**template,'source_path':'both.jcl','source_kind':'jcl_job','source_line':n,'source_text':text,'unit_id':str(n)})
        report=build_rule_inventory(doc,cov)
        self.assertEqual([j['counts']['technical_logic']['total'] for j in report['jobs']],[2,2])
        self.assertEqual(report['summary']['technical_logic']['total'],4)

    def test_dd_control_member_is_owned_by_job(self):
        doc,cov=self.model()
        doc['lineage']={'nodes':[{'id':'a','name':'J1','kind':'job','path':'job.jcl'},
            {'id':'step','name':'S1','kind':'jcl_step','path':'job.jcl'},
            {'id':'control','name':'SORTIN','kind':'control_member','path':'SORTIN.ctl'}],
            'edges':[{'source':'a','target':'step','kind':'contains_step','resolution':'resolved'},
                     {'source':'step','target':'control','kind':'dd_member','resolution':'resolved'}]}
        cov['rows']=[{**cov['rows'][-1],'source_path':'SORTIN.ctl','source_kind':'utility_control'}]
        report=build_rule_inventory(doc,cov)
        self.assertEqual(report['jobs'][0]['counts']['unclassified']['total'],1)
        self.assertEqual(report['jobs'][1]['counts']['unclassified']['total'],0)
        self.assertEqual(report['unassigned_rule_ids'],[])

    def shared_copybook_model(self, called=False):
        from workbench.source import analyze_sources
        from workbench.domain import sha
        source = ('IDENTIFICATION DIVISION.\nPROGRAM-ID. {name}.\nDATA DIVISION.\n'
                  'LINKAGE SECTION.\nCOPY COMMON.\nPROCEDURE DIVISION USING REC.\n'
                  'IF N > 5\nMOVE "Y" TO RESULT\nELSE\nMOVE "N" TO RESULT\nEND-IF.\nGOBACK.\n')
        files = {name+'.cbl':source.format(name=name) for name in ('P','Q')}
        files['COMMON.cpy']='01 REC.\n05 N PIC 9(2).\n05 RESULT PIC X.\n'
        jobs=[{'name':job,'steps':[{'name':'S1','program':name,'inputs':[],
               'outputs':[],'condition':'ALWAYS'}]} for job,name in [('J1','P'),('J2','Q')]]
        analysis=analyze_sources(files,{'jobs':jobs})
        self.assertFalse(analysis['blockers'])
        original={p['path']:{r['line']:r['disposition'] for r in p['coverage']}
                  for p in analysis['programs'].values()}
        rows=[]
        for path,text in files.items():
            for line,value in enumerate(text.splitlines(),1):
                nonexecuting=original.get(path,{}).get(line) in ('blank','comment','structure','paragraph')
                nonexecuting |= path=='COMMON.cpy' and line==1
                rows.append({'source_path':path,'source_hash':sha(text),
                    'source_kind':'copybook' if path.endswith('.cpy') else 'cobol_program',
                    'source_line':line,'source_text':value,'unit_id':path+':'+str(line),
                    'disposition':'non_executable' if nonexecuting else 'mapped_unverified',
                    'target_mappings':[],'tests':[],'evidence':[],
                    'reason':'Fictional unverified rule projection','replacement':None})
        doc={'id':'fixture','jobs':jobs,'analysis':analysis}
        if called:
            doc['lineage']={'nodes':[{'id':name,'name':name,'kind':'program','path':name+'.cbl'}
                                     for name in ('P','Q')],
                            'edges':[{'source':'P','target':'Q','kind':'calls','resolution':'resolved'}]}
        return doc,{'rows':rows,'summary':{'integrity_errors':[]}}

    def test_shared_copybook_does_not_assign_unreachable_program_to_job(self):
        doc,cov=self.shared_copybook_model();report=build_rule_inventory(doc,cov)
        self.assertEqual({(r['job'],r['program']) for r in report['job_programs']},
                         {('J1','P'),('J2','Q')})
        common=next(r for r in report['rules'] if r['source_path']=='COMMON.cpy')
        self.assertEqual({(m['job'],m['program']) for m in common['memberships']},
                         {('J1','P'),('J2','Q')})
        self.assertEqual([r['invocation_memberships'] for r in report['programs']],
                         [len(r['rule_ids']) for r in report['programs']])

    def test_shared_copybook_preserves_transitively_called_program_membership(self):
        doc,cov=self.shared_copybook_model(called=True);report=build_rule_inventory(doc,cov)
        self.assertEqual({(r['job'],r['program']) for r in report['job_programs']},
                         {('J1','P'),('J1','Q'),('J2','Q')})
        for row in report['job_programs']:
            self.assertEqual(row['invocation_memberships'],len(row['rule_ids']))

    def test_shared_copybook_invocations_within_one_job_remain_program_specific(self):
        doc,cov=self.shared_copybook_model()
        doc['jobs'][0]['steps'].append({**doc['jobs'][1]['steps'][0],'name':'S2'})
        doc['jobs']=doc['jobs'][:1]
        report=build_rule_inventory(doc,cov)
        self.assertEqual({(r['job'],r['program']) for r in report['job_programs']},
                         {('J1','P'),('J1','Q')})
        for row in report['job_programs']:
            self.assertEqual(row['invocation_memberships'],len(row['rule_ids']))

    def test_shared_copybook_rollup_agrees_in_json_csv_html_and_workbook(self):
        import csv,json,tempfile
        from pathlib import Path
        from openpyxl import Workbook
        from workbench.rule_inventory import write_inventory,render_rule_summary,add_workbook
        doc,cov=self.shared_copybook_model();report=build_rule_inventory(doc,cov)
        expected={('J1','P'),('J2','Q')}
        with tempfile.TemporaryDirectory() as folder:
            paths=write_inventory(report,Path(folder))
            frozen=json.loads(paths[0].read_text())
            self.assertEqual({(r['job'],r['program']) for r in frozen['job_programs']},expected)
            with paths[1].open(newline='') as source:
                rows=list(csv.DictReader(source))
            common=next(r for r in rows if r['source_path']=='COMMON.cpy')
            self.assertEqual({(m['job'],m['program']) for m in json.loads(common['memberships'])},expected)
        rendered=render_rule_summary(report)
        for job,program in expected:self.assertIn('<td>'+job+' / '+program+'</td>',rendered)
        for job,program in {('J1','Q'),('J2','P')}:self.assertNotIn('<td>'+job+' / '+program+'</td>',rendered)
        book=Workbook();add_workbook(book,report)
        self.assertEqual({tuple(row[:2]) for row in book['Job Program Summary'].iter_rows(min_row=2,values_only=True)},expected)
