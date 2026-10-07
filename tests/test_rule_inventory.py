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
