"""Synthetic adversarial witnesses for Endeavor-first discovery and source plans."""
import random
import tempfile
from pathlib import Path
import unittest
from unittest.mock import patch

from tests.test_lineage_connectors import FakeZowe
from workbench.connectors import ReadOnlyLineageResolver
from workbench.domain import sha
from workbench.lineage import map_lineage, derive_job_plan


def manifest(*jobs):
    return {'id':'LocalFirst','name':'Synthetic estate','process_intake_version':2,
            'jobs':[{'name':name,'order':i+1,'steps':[]} for i,name in enumerate(jobs or ('NIGHT',))]}


def basic():
    return {'NIGHT.jcl':'//NIGHT JOB\n//S1 EXEC PGM=MAIN',
            'MAIN.cbl':'PROGRAM-ID. MAIN.\nGOBACK.'}


class LocalFirstDiscoveryTests(unittest.TestCase):
    def test_complete_local_closure_does_not_load_env_or_initialize_clients(self):
        with patch.object(ReadOnlyLineageResolver,'from_environment',side_effect=AssertionError('must not inspect .env')) as prepare:
            resolver=ReadOnlyLineageResolver.deferred_from_environment({},workspace='/synthetic')
            lineage=map_lineage(basic(),manifest(),resolver=resolver)
        self.assertTrue(lineage['closure']['complete']);self.assertEqual(lineage['read_only_lookups'],[])
        prepare.assert_not_called()

    def test_deferred_native_setup_runs_once_only_after_missing_reference(self):
        requests=[]
        class Client:
            def resolve(self, request):
                requests.append(request['name'])
                return {'status':'UNAVAILABLE','reason':'synthetic missing'}
        sources=basic();sources['MAIN.cbl']+='\nCOPY LOST.\nCALL "OTHER".'
        with patch.object(ReadOnlyLineageResolver,'from_environment',return_value=Client()) as prepare:
            result=map_lineage(sources,manifest(),resolver=ReadOnlyLineageResolver.deferred_from_environment({}))
        self.assertEqual(prepare.call_count,1);self.assertEqual(set(requests),{'LOST','OTHER'})
        self.assertFalse(result['closure']['complete'])

    def test_setup_failure_stays_actionable_without_leaking_private_error(self):
        sources=basic();sources['MAIN.cbl']+='\nCOPY LOST.'
        with patch.object(ReadOnlyLineageResolver,'from_environment',side_effect=ValueError('private password=secret SSN=999999999')):
            result=map_lineage(sources,manifest(),resolver=ReadOnlyLineageResolver.deferred_from_environment({}))
        self.assertNotIn('999999999',str(result));self.assertNotIn('password=secret',str(result))
        self.assertIn('shared .env',result['closure']['gaps'][0]['reason'])
        self.assertIn('approved certificates',result['closure']['gaps'][0]['reason'])

    def test_shared_env_does_not_reactivate_an_inherited_legacy_http_db2_url(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);(root/'.env').write_text('# synthetic private env fixture\n')
            with patch('workbench.db2_env.read_workspace_env',return_value={'DB2_LOCATION_NAME':'SYNTHETIC'}), \
                 patch('workbench.connectors.Db2MCP') as db2, \
                 patch('workbench.connectors.ZoweReader') as zowe:
                resolver=ReadOnlyLineageResolver.from_environment({'WB_DB2_MCP_URL':'not-an-endpoint',
                    'WB_ZOWE_PROFILE':'synthetic'},workspace=root)
            db2.assert_not_called();self.assertIsNone(resolver.db2);zowe.assert_called_once()

    def test_absent_native_resolver_prompts_correct_evidence_channel(self):
        sources=basic();sources['MAIN.cbl']+='\nCOPY LOST.\nEXEC SQL SELECT ID FROM APP.T END-EXEC.'
        result=map_lineage(sources,manifest())
        reasons={gap['kind']:gap['reason'] for gap in result['closure']['gaps']}
        self.assertIn('Zowe CLI',reasons['copybook']);self.assertIn('Db2 MCP',reasons['db2_table'])
        self.assertNotIn('resolver is not configured',str(result))

    def test_complete_static_jcllib_scope_is_passed_to_proc_lookup(self):
        sources={'NIGHT.jcl':'//NIGHT JOB\n//LIB JCLLIB ORDER=(APP.PROC,\n// APP.INCLUDE)\n//S1 EXEC PROC=RUNPROC'}
        requests=[]
        map_lineage(sources,manifest(),resolver=lambda r:requests.append(r) or {})
        request=next(r for r in requests if r['kind']=='proc')
        self.assertEqual(request['source_library_hints'],['APP.PROC','APP.INCLUDE'])
        self.assertTrue(request['local_repository_checked'])

    def test_static_jcllib_scope_never_becomes_program_or_copy_scope(self):
        sources=basic();sources['NIGHT.jcl']='//NIGHT JOB\n//LIB JCLLIB ORDER=APP.PROC\n//S1 EXEC PGM=MAIN'
        sources['MAIN.cbl']+='\nCOPY LOST.\nCALL "OTHER".'
        requests=[]
        map_lineage(sources,manifest(),resolver=lambda r:requests.append(r) or {})
        self.assertTrue(requests);self.assertTrue(all('source_library_hints' not in r for r in requests))

    def test_dynamic_or_malformed_jcllib_is_a_named_obligation(self):
        for order in ('&PROCLIB','(APP.A,APP.A)','(APP.A,','APP.A EXTRA=BAD','JUNK:*',"'APP.A\"",''):
            with self.subTest(order=order):
                sources=basic();sources['NIGHT.jcl']='//NIGHT JOB\n//LIB JCLLIB ORDER='+order+'\n//S1 EXEC PGM=MAIN'
                result=map_lineage(sources,manifest())
                self.assertFalse(result['closure']['complete'])
                gap=next(g for g in result['closure']['gaps'] if g['name']=='JCLLIB_SOURCE_SCOPE')
                self.assertEqual(gap['status'],'dynamic_unknown')

    def test_jcllib_scope_resets_between_root_jobs(self):
        sources={'jobs.jcl':'//FIRST JOB\n//LIB JCLLIB ORDER=APP.FIRST\n//S EXEC PROC=PROC1\n//SECOND JOB\n//S EXEC PROC=PROC2'}
        requests=[]
        map_lineage(sources,manifest('FIRST','SECOND'),resolver=lambda r:requests.append(r) or {})
        refs={r['name']:r for r in requests}
        self.assertEqual(refs['PROC1']['source_library_hints'],['APP.FIRST'])
        self.assertNotIn('source_library_hints',refs['PROC2'])

    def test_identical_proc_names_in_different_remote_scopes_do_not_reuse_cache(self):
        sources={'a.jcl':'//FIRST JOB\n//LIB JCLLIB ORDER=APP.FIRST\n//S EXEC PROC=COMMON',
                 'b.jcl':'//SECOND JOB\n//LIB JCLLIB ORDER=APP.SECOND\n//S EXEC PROC=COMMON',
                 'MAIN.cbl':'PROGRAM-ID. MAIN.\nGOBACK.'}
        requests=[]
        def resolve(request):
            requests.append(request)
            scope=request['source_library_hints'][0]
            return {'status':'RESOLVED','coverage':'COMPLETE',
                    'filename':scope+'/COMMON.proc','content':'//COMMON PROC\n//M EXEC PGM=MAIN\n// PEND',
                    'provenance':{'origin':'zowe_cli','dataset_member':scope+'(COMMON)'}}
        result=map_lineage(sources,manifest('FIRST','SECOND'),resolver=resolve)
        self.assertTrue(result['closure']['complete'])
        self.assertEqual([r['source_library_hints'] for r in requests],[['APP.FIRST'],['APP.SECOND']])
        self.assertEqual(len(result['source_snapshots']),2)

    def test_qualified_remote_control_card_works_without_account_wide_hint(self):
        client=FakeZowe([{'dsname':'APP.CNTL','dsorg':'PO'}],{'APP.CNTL':[{'member':'CARD'}]},'SORT FIELDS=COPY')
        result=ReadOnlyLineageResolver(zowe=client).resolve({'kind':'control_member','name':'CARD','library':'APP.CNTL'})
        self.assertEqual(result['status'],'RESOLVED');self.assertEqual(client.calls[0][1],'APP.CNTL')
        self.assertEqual(result['filename'],'remote/APP.CNTL/CARD.cntl')
        self.assertEqual(result['provenance']['discovery_scope'],['APP.CNTL'])

    def test_qualified_dependency_cannot_fall_back_to_a_different_library(self):
        client=FakeZowe([{'dsname':'APP.EXACT','dsorg':'PO'}],{'APP.OTHER':[{'member':'CARD'}]},'SORT FIELDS=COPY')
        result=ReadOnlyLineageResolver(zowe=client,dataset_hints=['APP.*']).resolve({'kind':'control_member','name':'CARD','library':'APP.EXACT'})
        self.assertEqual(result['status'],'UNRESOLVED');self.assertEqual(client.calls[0][1],'APP.EXACT')
        self.assertFalse(any(call[0]=='read' for call in client.calls))

    def test_exact_library_response_cannot_substitute_an_unrequested_library(self):
        client=FakeZowe([{'dsname':'APP.OTHER','dsorg':'PO'}],{'APP.OTHER':[{'member':'CARD'}]},'SORT FIELDS=COPY')
        result=ReadOnlyLineageResolver(zowe=client).resolve({'kind':'control_member','name':'CARD','library':'APP.EXACT'})
        self.assertEqual(result['status'],'UNRESOLVED')
        self.assertEqual([call[0] for call in client.calls],['list'])
        self.assertNotIn('content',result)

    def test_untrusted_or_overbroad_exact_libraries_are_not_sent_to_cli(self):
        for library in ('APP.*','../APP','APP;echo','APP\nEVIL','APP(ANY)','A.'+'B'*45):
            with self.subTest(library=library):
                client=FakeZowe([])
                result=ReadOnlyLineageResolver(zowe=client).resolve({'kind':'proc','name':'RUNPROC','library':library})
                self.assertEqual(result['status'],'UNRESOLVED');self.assertEqual(client.calls,[])

    def test_jcllib_scope_rejected_for_cobol_retrieval(self):
        client=FakeZowe([])
        result=ReadOnlyLineageResolver(zowe=client).resolve({'kind':'program','name':'MAIN','source_library_hints':['APP.PROC']})
        self.assertEqual(result['status'],'UNRESOLVED');self.assertEqual(client.calls,[])

    def test_local_duplicate_definitions_stay_blocked_without_remote_guessing(self):
        sources=basic();sources['other/MAIN.cbl']=sources['MAIN.cbl']
        with patch.object(ReadOnlyLineageResolver,'from_environment',side_effect=AssertionError('no remote tie breaker')) as prepare:
            result=map_lineage(sources,manifest(),resolver=ReadOnlyLineageResolver.deferred_from_environment({}))
        self.assertEqual(result['closure']['status'],'BLOCKED');prepare.assert_not_called()

    def test_source_above_800000_bytes_preserves_every_dependency_span(self):
        sources=basic()
        sources['MAIN.cbl']='PROGRAM-ID. MAIN.\n'+('EXEC SQL SELECT ID FROM APP.T END-EXEC.\n'*22_000)
        sources['T.ddl']='CREATE TABLE APP.T (ID INTEGER);'
        self.assertGreater(len(sources['MAIN.cbl'].encode()),800_000)
        result=map_lineage(sources,manifest())
        self.assertTrue(result['closure']['complete'])
        links=[e for e in result['edges'] if e['kind']=='sql_table']
        self.assertEqual(len(links),22_000)
        self.assertEqual({e['evidence'][0]['line'] for e in links},set(range(2,22_002)))
        self.assertEqual(result['scope']['retained_files'],sorted(sources))
        self.assertEqual(result['read_only_lookups'],[])

    def test_64_distinct_randomized_scopes_compare_actual_fetched_source(self):
        rng=random.Random(20261012);witnesses=set()
        for index in range(64):
            token=''.join(rng.choice('ABCDEFGHIJKLMNOPQRSTUVWXYZ') for _ in range(6))
            member='P'+token;library='APP.'+token;body='//'+member+' PROC\n//S EXEC PGM=MAIN\n// PEND'
            sources={'NIGHT.jcl':'//NIGHT JOB\n//LIB JCLLIB ORDER='+library+'\n//S EXEC PROC='+member,
                     'MAIN.cbl':'PROGRAM-ID. MAIN.\nGOBACK.','unused/U'+str(index)+'.cbl':'PROGRAM-ID. U'+str(index)+'.\nCALL "NOTNEEDED".'}
            client=FakeZowe([{'dsname':library,'dsorg':'PO'}],{library:[{'member':member}]},body)
            result=map_lineage(sources,manifest(),resolver=ReadOnlyLineageResolver(zowe=client))
            self.assertTrue(result['closure']['complete'])
            self.assertEqual(result['source_snapshots'][0]['text'],body)
            self.assertEqual(result['source_snapshots'][0]['source_hash'],sha(body))
            self.assertEqual(result['scope']['retained_files'],sorted(sources))
            self.assertFalse(any('NOTNEEDED' in str(call) for call in client.calls))
            witnesses.add((library,member,sha(body)))
        self.assertEqual(len(witnesses),64)


class SourceJobPlanTests(unittest.TestCase):
    def plan(self,sources=None,declared=None):
        sources=basic() if sources is None else sources;declared=manifest() if declared is None else declared
        return derive_job_plan(sources,declared,map_lineage(sources,declared))

    def test_empty_root_steps_derive_program_order_from_source_not_user_estimates(self):
        sources=basic();sources['NIGHT.jcl']+='\n//S2 EXEC PGM=SECOND';sources['SECOND.cbl']='PROGRAM-ID. SECOND.\nGOBACK.'
        declared=manifest();before=repr(declared);plan=self.plan(sources,declared)
        self.assertTrue(plan['complete']);self.assertEqual(repr(declared),before)
        self.assertEqual([s['program'] for s in plan['jobs'][0]['steps']],['MAIN','SECOND'])
        self.assertEqual([s['condition'] for s in plan['jobs'][0]['steps']],['ALWAYS','ALWAYS'])
        self.assertEqual(plan['step_evidence'][1]['source_ref']['line'],3)
        self.assertEqual(plan['source_files']['NIGHT.jcl'],sha(sources['NIGHT.jcl']))

    def test_declared_job_order_wins_over_file_name_and_physical_export_order(self):
        sources={'Z.jcl':'//SECOND JOB\n//S EXEC PGM=MAIN','A.jcl':'//FIRST JOB\n//S EXEC PGM=MAIN','MAIN.cbl':'PROGRAM-ID. MAIN.\nGOBACK.'}
        plan=self.plan(sources,manifest('SECOND','FIRST'))
        self.assertTrue(plan['complete']);self.assertEqual([j['name'] for j in plan['jobs']],['SECOND','FIRST'])

    def test_duplicate_job_and_step_declarations_do_not_become_success(self):
        for suffix in ('\n//NIGHT JOB\n//S EXEC PGM=MAIN','\n//S1 EXEC PGM=MAIN'):
            sources=basic();sources['NIGHT.jcl']+=suffix
            plan=self.plan(sources)
            self.assertFalse(plan['complete']);self.assertTrue(any('ambiguous' in g['kind'] for g in plan['gaps']))

    def test_conditional_proc_and_parameterized_exec_stay_exact_obligations(self):
        for card in ('//S1 EXEC PROC=RUNPROC','//S1 EXEC PGM=MAIN,COND=(0,NE)','//S1 EXEC PGM=&PROGRAM',"//S1 EXEC PGM=MAIN,PARM='X'"):
            sources=basic();sources['NIGHT.jcl']='//NIGHT JOB\n'+card
            plan=self.plan(sources);self.assertFalse(plan['complete']);self.assertEqual(plan['jobs'][0]['steps'],[])
            self.assertTrue(any(g['line']==2 for g in plan['gaps']))

    def test_disp_is_not_misclassified_as_input_output_business_direction(self):
        for disposition in ('SHR','OLD','(NEW,CATLG)','(MOD,KEEP)'):
            sources=basic();sources['NIGHT.jcl']+='\n//DATA DD DSN=APP.DATA,DISP='+disposition
            plan=self.plan(sources);self.assertFalse(plan['complete'])
            binding=plan['dd_bindings'][0];self.assertEqual(binding['role'],'Unknown');self.assertEqual(binding['dataset'],'APP.DATA')
            self.assertEqual(plan['jobs'][0]['steps'][0]['inputs'],[]);self.assertEqual(plan['jobs'][0]['steps'][0]['outputs'],[])
            self.assertEqual(plan['gaps'][0]['kind'],'unverified_dd_role')

    def test_if_program_does_not_get_an_invented_always_condition(self):
        sources=basic();sources['NIGHT.jcl']='//NIGHT JOB\n// IF RC = 0 THEN\n//S1 EXEC PGM=MAIN\n// ENDIF'
        plan=self.plan(sources);self.assertFalse(plan['complete']);self.assertEqual(plan['jobs'][0]['steps'],[])

    def test_other_job_and_comments_or_instream_facts_are_not_plan_steps(self):
        sources=basic();sources['NIGHT.jcl']='//NIGHT JOB\n//* //EVIL EXEC PGM=EVIL\n//S1 EXEC PGM=MAIN\n//SYSIN DD DATA\n//EVIL EXEC PGM=EVIL\n/*\n//OTHER JOB\n//S2 EXEC PGM=MAIN'
        plan=self.plan(sources);self.assertEqual([s['name'] for s in plan['jobs'][0]['steps']],['S1'])
        self.assertFalse(plan['complete'])

    def test_missing_program_or_ambiguous_mapping_never_gets_complete_plan(self):
        sources=basic();del sources['MAIN.cbl'];plan=self.plan(sources)
        self.assertFalse(plan['complete']);self.assertFalse(plan['lineage_closure_complete'])
        self.assertGreater(plan['lineage_gap_count'],0)

    def test_plan_binding_changes_when_source_changes_even_same_program_order(self):
        sources=basic();first=self.plan(sources);sources['NIGHT.jcl']='//NIGHT JOB\n//* revised source\n//S1 EXEC PGM=MAIN'
        second=self.plan(sources);self.assertNotEqual(first['source_binding_hash'],second['source_binding_hash'])

    def test_existing_manifest_contract_is_unchanged(self):
        declared=manifest();del declared['process_intake_version']
        plan=self.plan(basic(),declared);self.assertFalse(plan['applicable']);self.assertEqual(plan['jobs'],declared['jobs'])

    def test_64_random_unique_source_plans_compare_exact_jcl_dispatch_order(self):
        rng=random.Random(20261013);witnesses=set()
        for count in range(64):
            names=['P'+''.join(rng.choice('ABCDEFGHIJKLMNOPQRSTUVWXYZ') for _ in range(6)) for _ in range(rng.randrange(1,7))]
            sources={'NIGHT.jcl':'//NIGHT JOB\n'+'\n'.join('//S'+str(i)+' EXEC PGM='+n for i,n in enumerate(names))}
            sources.update({n+'.cbl':'PROGRAM-ID. '+n+'.\nGOBACK.' for n in names})
            plan=self.plan(sources);self.assertTrue(plan['complete'])
            actual=[(s['name'],s['program']) for s in plan['jobs'][0]['steps']]
            self.assertEqual(actual,[('S'+str(i),n) for i,n in enumerate(names)])
            witnesses.add(plan['source_binding_hash'])
        self.assertEqual(len(witnesses),64)


class LateLineageSafetyRegressionTests(unittest.TestCase):
    def source_plan(self,cards):
        sources=basic();sources['NIGHT.jcl']='//NIGHT JOB\n'+cards
        return sources,derive_job_plan(sources,manifest(),map_lineage(sources,manifest()))

    def qualified_copy(self,path,provenance=None):
        sources=basic();sources['MAIN.cbl']+='\nCOPY SAME IN ORG.LIB.';sources[path]='01 SAME PIC X.\n'
        declared=manifest()
        if provenance is not None:declared['discovery_provenance']={path:provenance}
        return map_lineage(sources,declared)

    def test_orphan_control_terminators_are_exact_unverified_obligations(self):
        for closer in ('ENDIF','PEND'):
            with self.subTest(closer=closer):
                sources,plan=self.source_plan('// '+closer+'\n//S1 EXEC PGM=MAIN')
                self.assertFalse(plan['complete'])
                gap=next(g for g in plan['gaps'] if g['kind']=='unmatched_jcl_terminator')
                self.assertEqual(gap['status'],'UNVERIFIED')
                self.assertEqual(gap['source_ref'],{'path':'NIGHT.jcl','line':2,'end_line':2,'source_hash':sha(sources['NIGHT.jcl'])})

    def test_malformed_terminator_does_not_restore_unconditional_execution(self):
        for opener,closer,unclosed in (('// IF RC = 0 THEN','ENDIF EXTRA','unclosed_jcl_if'),('//LOCAL PROC','PEND EXTRA','unclosed_jcl_proc')):
            with self.subTest(closer=closer):
                sources,plan=self.source_plan(opener+'\n// '+closer+'\n//S1 EXEC PGM=MAIN')
                self.assertFalse(plan['complete']);self.assertEqual(plan['jobs'][0]['steps'],[])
                self.assertTrue(any(g['kind']=='malformed_jcl_terminator' and g['line']==3 for g in plan['gaps']))
                gap=next(g for g in plan['gaps'] if g['kind']==unclosed)
                self.assertEqual(gap['source_ref'],{'path':'NIGHT.jcl','line':2,'end_line':4,'source_hash':sha(sources['NIGHT.jcl'])})

    def test_unclosed_control_scopes_stop_at_current_job_boundary(self):
        for opener,kind in (('// IF RC = 0 THEN','unclosed_jcl_if'),('//LOCAL PROC','unclosed_jcl_proc')):
            with self.subTest(opener=opener):
                sources,plan=self.source_plan('//S1 EXEC PGM=MAIN\n'+opener+'\n//OTHER JOB\n//S2 EXEC PGM=MAIN')
                gap=next(g for g in plan['gaps'] if g['kind']==kind)
                self.assertEqual(gap['source_ref'],{'path':'NIGHT.jcl','line':3,'end_line':3,'source_hash':sha(sources['NIGHT.jcl'])})
                self.assertFalse(plan['complete']);self.assertEqual([s['name'] for s in plan['jobs'][0]['steps']],['S1'])

    def test_valid_nested_scopes_keep_syntax_balanced_without_claiming_execution(self):
        _,plan=self.source_plan('//LOCAL PROC\n// IF RC = 0 THEN\n// ELSE\n// ENDIF\n// PEND\n// IF RC = 0 THEN\n// IF RC = 4 THEN\n// ELSE\n// ENDIF\n// ELSE\n// ENDIF\n//S1 EXEC PGM=MAIN')
        self.assertFalse(plan['complete']);self.assertEqual([s['name'] for s in plan['jobs'][0]['steps']],['S1'])
        self.assertFalse(any(g['kind'].startswith(('unclosed_','unmatched_','malformed_')) for g in plan['gaps']))

    def test_crossed_scopes_and_duplicate_else_never_become_balanced(self):
        _,plan=self.source_plan('//LOCAL PROC\n// IF RC = 0 THEN\n// PEND\n// ENDIF\n// ELSE\n//S1 EXEC PGM=MAIN')
        self.assertTrue(any(g['kind']=='unmatched_jcl_terminator' and g['line']==4 for g in plan['gaps']))
        self.assertTrue(any(g['kind']=='unclosed_jcl_proc' for g in plan['gaps']))
        _,plan=self.source_plan('// IF RC = 0 THEN\n// ELSE\n// ELSE\n// ENDIF\n//S1 EXEC PGM=MAIN')
        self.assertTrue(any(g['kind']=='unmatched_jcl_terminator' and g['line']==4 for g in plan['gaps']))

    def test_qualified_local_path_requires_ordered_exact_library_suffix(self):
        for path in ('LIB/ORG/SAME.cpy','ORG/OTHER/LIB/SAME.cpy','ORG/LIB/OTHER/SAME.cpy'):
            with self.subTest(path=path):
                result=self.qualified_copy(path);self.assertFalse(result['closure']['complete'])
                gap=next(g for g in result['closure']['gaps'] if g['kind']=='copybook');self.assertEqual((gap['name'],gap['library']),('SAME','ORG.LIB'))
        for path in ('ORG/LIB/SAME.cpy','export/ORG.LIB/SAME.cpy'):
            with self.subTest(path=path):self.assertTrue(self.qualified_copy(path)['closure']['complete'])

    def test_observed_library_identity_cannot_be_overridden_by_local_path(self):
        for provenance in ({'dataset_member':'OTHER.LIB(SAME)','origin':'zowe_cli'},{'dataset':'OTHER.LIB','dataset_member':'ORG.LIB(SAME)'},{'dataset':'ORG.LIB','dataset_member':'OTHER.LIB(SAME)'},{'dataset_member':17}):
            with self.subTest(provenance=provenance):self.assertFalse(self.qualified_copy('ORG/LIB/SAME.cpy',provenance)['closure']['complete'])
        self.assertTrue(self.qualified_copy('neutral/SAME.cpy',{'dataset':'ORG.LIB','dataset_member':'ORG.LIB(SAME)'})['closure']['complete'])

    def test_jcllib_conflicting_observed_identity_is_not_a_local_fallback(self):
        sources=basic();sources['NIGHT.jcl']='//NIGHT JOB\n//LIB JCLLIB ORDER=ORG.LIB\n//S1 EXEC PROC=LOCAL';sources['LOCAL.proc']='//LOCAL PROC\n//S EXEC PGM=MAIN\n// PEND'
        declared=manifest();declared['discovery_provenance']={'LOCAL.proc':{'dataset':'ORG.LIB','dataset_member':'OTHER.LIB(LOCAL)'}}
        self.assertFalse(map_lineage(sources,declared)['closure']['complete'])
        del declared['discovery_provenance'];self.assertTrue(map_lineage(sources,declared)['closure']['complete'])


if __name__=='__main__':unittest.main()
