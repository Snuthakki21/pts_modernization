"""Protected-local manual exports after synthetic bound Zowe absence receipts.

No test connects to a mainframe, uses real customer/source data or approves an
SME return. Mocked structural provenance is not evidence of live connectivity.
"""
import copy
from pathlib import Path
import random
import tempfile
import unittest
from unittest.mock import patch

from workbench.domain import ValidationError, encode, sha, write_new
from workbench.mainframe import load_knowledge
from workbench.retrieval import build_request, inspect_response, write_request, _source_generation
from workbench.supplemental import find_entries


def need_key(need):
    fields={k:need.get(k) for k in ('kind','name','source','relationship')}
    fields.update({k:need[k] for k in ('library','source_library_hints') if k in need})
    return sha(encode(fields))


class SupplementalTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name).resolve()
        self.doc={'id':'ManualTest','name':'Synthetic manual source test','jobs':[],
                  'source_files':{},'accelerator_contract_version':1,
                  'guided_contract_version':1,'guided_workspace':str(self.root),
                  'mainframe_knowledge':load_knowledge(self.root),'copilot_iteration':0}

    def receipt(self, needs=None, reason='Member not found in approved library', provenance=None, status='NOT_FOUND'):
        request=build_request(self.doc,needs or [{'kind':'job','name':'SYNJOB','reason':'Synthetic missing job','status':'missing'}])
        relative=write_request(self.root,request)
        response={'request_id':request['request_id'],'items':[{'need_id':n['need_id'],
            'status':status,'reason':reason,'provenance':provenance or {
                'origin':'zowe_cli','tool':'zowe files view ds',
                'locator':(n.get('library') or (n.get('source_library_hints') or ['SYNTH.EXPORT'])[0])+'('+n['name']+')',
                'retrieved_at':'2000-01-01T00:00:00Z'}} for n in request['needs']]}
        (self.root/request['return_folder']/'response.json').write_bytes(encode(response))
        accepted=inspect_response(self.root,request,self.doc['source_files'])
        accepted_relative='analysis/retrieval/'+request['request_id']+'/accepted-'+accepted['response_hash']+'.json'
        write_new(self.root/'processes'/self.doc['id']/accepted_relative,encode(accepted))
        self.doc['artifacts']=[relative,accepted_relative]
        self.doc['artifact_hashes']={rel:sha((self.root/'processes'/self.doc['id']/rel).read_bytes()) for rel in self.doc['artifacts']}
        self.doc['retrieval_request']={'id':request['request_id'],'artifact':relative,'status':'CONSUMED',
            'response_artifact':accepted_relative,'missing_items':accepted['missing_items'],
            'manual_request_source_generation':request['source_generation'],
            'manual_failure_source_generation':_source_generation(self.doc)}
        self.doc['retrieval_unresolved']={need_key(n):{'need':{k:v for k,v in n.items() if k!='need_id'},
            'request_id':request['request_id'],'status':status,'reason':reason} for n in request['needs']}
        return accepted['missing_items'],request['needs']

    def source(self, relative='supplemental/JCL/SYNJOB.jcl', text='//SYNJOB JOB\n//S1 EXEC PGM=SYNPROG\n'):
        path=self.root/relative;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(text.encode('utf-8'))
        return path

    def test_original_bytes_and_truthful_manual_provenance(self):
        failed,needs=self.receipt();path=self.source();original=path.read_bytes()
        result=find_entries(self.root,self.doc,failed,needs)
        self.assertEqual(result['gaps'],[]);self.assertEqual(len(result['entries']),1)
        entry=result['entries'][0];self.assertEqual(entry['path'],'supplemental/JCL/SYNJOB.jcl')
        self.assertEqual(entry['text'].encode(),original);self.assertEqual(entry['source_hash'],sha(original))
        self.assertEqual(entry['provenance']['origin'],'operator_export')
        self.assertEqual(entry['provenance']['tool'],'local_manual_export')
        self.assertEqual(entry['provenance']['retrieval_need_ids'],[needs[0]['need_id']])
        self.assertEqual(entry['provenance']['conversion_support'],'not_established')
        self.assertEqual(path.read_bytes(),original)

    def test_denied_and_config_failures_never_scan(self):
        for reason in ('Member not found: permission denied','Member not found due to TLS certificate failure',
                       'Member not found: authentication failed','Member not found: auth failed',
                       'Member not found with untrusted certificate','Connection unavailable',
                       'Profile not configured','Security policy forbids retrieval','Unknown failure'):
            with self.subTest(reason=reason):
                self.setUp();failed,needs=self.receipt(reason=reason);self.source()
                with patch('workbench.supplemental._index',side_effect=AssertionError('must not scan')):
                    result=find_entries(self.root,self.doc,failed,needs)
                self.assertFalse(result['entries']);self.assertTrue(result['gaps'])

    def test_exact_current_unresolved_binding_required_before_scan(self):
        for change in ('missing','request','status','name','kind','library','source_library_hints'):
            with self.subTest(change=change):
                self.setUp();failed,needs=self.receipt();self.source()
                record=next(iter(self.doc['retrieval_unresolved'].values()))
                if change=='missing':self.doc['retrieval_unresolved']={}
                elif change=='request':record['request_id']=sha('other request')
                elif change=='status':record['status']='RECEIVED'
                else:record['need'][change]=['OTHER.LIB'] if change=='source_library_hints' else 'OTHER'
                with patch('workbench.supplemental._index',side_effect=AssertionError('must not scan')):
                    with self.assertRaises(ValidationError):find_entries(self.root,self.doc,failed,needs)

    def test_source_generation_at_failure_is_current_and_request_bound(self):
        for change in ('missing_failure','missing_request','request','current'):
            with self.subTest(change=change):
                self.setUp();failed,needs=self.receipt();self.source();record=self.doc['retrieval_request']
                if change=='missing_failure':record.pop('manual_failure_source_generation')
                elif change=='missing_request':record.pop('manual_request_source_generation')
                elif change=='request':record['manual_request_source_generation']=sha('different')
                else:self.doc['source_files']['other.cbl']=sha('changed')
                with patch('workbench.supplemental._index',side_effect=AssertionError('must not scan')):
                    with self.assertRaises(ValidationError):find_entries(self.root,self.doc,failed,needs)

    def test_64_randomized_exact_manual_sources(self):
        rng=random.Random(20261009);states=set()
        for index in range(64):
            self.setUp();name='J'+''.join(rng.choice('ABCDEFGHJKLMNPQRSTUVWXYZ0123456789') for _ in range(7))
            step='S'+''.join(rng.choice('ABCDEFGHJKLMNPQRSTUVWXYZ0123456789') for _ in range(7))
            text='//'+name+" JOB (TEST),'SYNTHETIC'\n//"+step+' EXEC PGM=SYNPROG\n'
            failed,needs=self.receipt([{'kind':'job','name':name,'status':'missing','reason':'Synthetic missing job'}])
            path=self.source('supplemental/JCL/'+name+'.jcl',text);states.add(sha(text))
            result=find_entries(self.root,self.doc,failed,needs)
            self.assertEqual(result['gaps'],[]);self.assertEqual(len(result['entries']),1)
            self.assertEqual(result['entries'][0]['text'],text)
            self.assertEqual(result['entries'][0]['source_hash'],sha(path.read_bytes()))
        self.assertEqual(len(states),64)

    def test_no_scan_without_new_accelerator_contract(self):
        for version in (None,False,True,0,2,'1',1.0):
            with self.subTest(version=version):
                self.doc['accelerator_contract_version']=version
                with patch('workbench.supplemental._binding',side_effect=AssertionError('no binding')), \
                     patch('workbench.supplemental._index',side_effect=AssertionError('no scan')):
                    self.assertEqual(find_entries(self.root,self.doc,[],[]),{'entries':[],'gaps':[],'attempts':[]})

    def test_unapproved_provenance_and_non_read_commands_never_scan(self):
        values=[('operator_export','local_manual_export'),('configured_mcp','db2_describe_table'),
                ('config_only','zowe files view ds'),('zowe_cli','zowe jobs submit ds'),
                ('zowe_cli','zowe files upload ds'),('zowe_cli','zowe files list ds'),
                ('zowe_cli','zowe files view ds && echo ignored'),
                ('zowe_cli','zowe files view ds $(ignored)')]
        for origin,tool in values:
            with self.subTest(origin=origin,tool=tool):
                self.setUp();failed,needs=self.receipt(provenance={'origin':origin,'tool':tool,
                    'locator':'SYNTH.EXPORT(SYNJOB)','retrieved_at':'2000-01-01T00:00:00Z'})
                with patch('workbench.supplemental._index',side_effect=AssertionError('no scan')):
                    result=find_entries(self.root,self.doc,failed,needs)
                self.assertEqual(result['entries'],[])
                self.assertEqual(result['gaps'][0]['kind'],'manual_remote_route_unverified')

    def test_wrong_member_scope_and_command_target_never_scan(self):
        for locator,tool in [('SYNTH.EXPORT(OTHER)','zowe files view ds'),
                             ('OTHER.LIB(SYNJOB)','zowe files view ds'),
                             ('TPXSESSION','zowe files view ds'),
                             ('/tmp/SYNJOB.jcl','zowe files view uss'),
                             ('SYNTH.EXPORT(SYNJOB)','zowe files view ds OTHER.LIB(OTHER)'),
                             ('SYNTH.EXPORT(SYNJOB)','zowe files view ds SYNTH.EXPORT(SYNJOB) --reject-unauthorized false'),
                             ('SYNTH.EXPORT(SYNJOB)','zowe files view ds SYNTH.EXPORT(SYNJOB) --insecure')]:
            with self.subTest(locator=locator,tool=tool):
                self.setUp();failed,needs=self.receipt([{'kind':'job','name':'SYNJOB','library':'SYNTH.EXPORT','reason':'Synthetic'}],
                    provenance={'origin':'zowe_cli','tool':tool,'locator':locator,'retrieved_at':'2000-01-01T00:00:00Z'})
                with patch('workbench.supplemental._index',side_effect=AssertionError('no scan')):
                    result=find_entries(self.root,self.doc,failed,needs)
                self.assertEqual(result['entries'],[]);self.assertEqual(result['gaps'][0]['kind'],'manual_remote_identity_unverified')

    def test_ambiguous_dynamic_and_db2_needs_never_scan(self):
        cases=[({'kind':'job','name':'SYNJOB','reason':'Synthetic'},'AMBIGUOUS'),
               ({'kind':'job','name':'SYNJOB','reason':'Synthetic','status':'dynamic_unknown'},'NOT_FOUND'),
               ({'kind':'program','name':'SYNPROG','reason':'Synthetic'},'NOT_FOUND'),
               ({'kind':'db2_table','name':'APP.TABLE','reason':'Synthetic'},'NOT_FOUND')]
        for need,status in cases:
            with self.subTest(need=need,status=status):
                self.setUp();failed,needs=self.receipt([need],status=status)
                with patch('workbench.supplemental._index',side_effect=AssertionError('no scan')):
                    self.assertEqual(find_entries(self.root,self.doc,failed,needs),{'entries':[],'gaps':[],'attempts':[]})

    def test_missing_member_does_not_select_nearby_file(self):
        failed,needs=self.receipt();self.source('supplemental/JCL/SYNJOB2.jcl','//SYNJOB2 JOB\n//S1 EXEC PGM=SYNPROG\n')
        result=find_entries(self.root,self.doc,failed,needs)
        self.assertFalse(result['entries']);self.assertEqual(result['gaps'][0]['kind'],'manual_source_not_found')
        self.assertEqual(result['attempts'][0]['candidate_count'],0)

    def test_multiple_exact_members_remain_ambiguous(self):
        failed,needs=self.receipt();self.source();self.source('supplemental/JCLPlus/SYNJOB.jcl')
        result=find_entries(self.root,self.doc,failed,needs)
        self.assertFalse(result['entries']);self.assertEqual(result['gaps'][0]['kind'],'manual_source_ambiguous')
        self.assertEqual(result['attempts'][0]['candidate_count'],2)

    def test_scope_requires_exact_library_folder_and_failed_library(self):
        for relative in ('supplemental/JCL/SYNJOB.jcl','supplemental/JCL/OTHER.LIB/SYNJOB.jcl',
                         'supplemental/JCL/DEV.SECOND/SYNJOB.jcl'):
            with self.subTest(relative=relative):
                self.setUp();failed,needs=self.receipt([{'kind':'job','name':'SYNJOB','reason':'Synthetic',
                    'source_library_hints':['DEV.FIRST','DEV.SECOND']}]);self.source(relative)
                result=find_entries(self.root,self.doc,failed,needs)
                self.assertFalse(result['entries']);self.assertEqual(result['gaps'][0]['kind'],'manual_library_scope')
        self.setUp();failed,needs=self.receipt([{'kind':'job','name':'SYNJOB','reason':'Synthetic','library':'DEV.FIRST'}])
        self.source('supplemental/JCL/DEV/FIRST/SYNJOB.jcl')
        entry=find_entries(self.root,self.doc,failed,needs)['entries'][0]
        self.assertEqual(entry['provenance']['dataset_member'],'DEV.FIRST(SYNJOB)')
        self.assertEqual(entry['provenance']['library_binding'],'OPERATOR_EXPORT_DIRECTORY_NOT_MAINFRAME_OBSERVATION')

    def test_qualified_proc_cannot_resolve_a_different_jobs_library(self):
        from workbench.lineage import map_lineage

        needs=[{'kind':'proc','name':'COMMON','source':'job:J1','relationship':'invokes_proc',
                'source_library_hints':['DEV.FIRST'],'reason':'Synthetic'}]
        failed,bound=self.receipt(needs)
        self.source('supplemental/PROCConverted/DEV.FIRST/COMMON.proc','//COMMON PROC\n//S1 EXEC PGM=SYNPROG\n// PEND\n')
        entry=find_entries(self.root,self.doc,failed,bound)['entries'][0]
        files={'J1.jcl':'//J1 JOB\n//LIB JCLLIB ORDER=DEV.FIRST\n//S1 EXEC PROC=COMMON\n',
               'J2.jcl':'//J2 JOB\n//LIB JCLLIB ORDER=DEV.SECOND\n//S1 EXEC PROC=COMMON\n',
               'SYNPROG.cbl':'PROGRAM-ID. SYNPROG.\nGOBACK.\n',entry['path']:entry['text']}
        manifest={'id':'ManualTest','jobs':[{'name':'J1','order':1,'steps':[]},{'name':'J2','order':2,'steps':[]}],
                  'discovery_provenance':{entry['path']:entry['provenance']}}
        lineage=map_lineage(files,manifest)
        self.assertFalse(lineage['closure']['complete'])
        gaps=[g for g in lineage['closure']['gaps'] if g['kind']=='proc' and g['name']=='COMMON']
        self.assertEqual(len(gaps),1);self.assertEqual(gaps[0]['source_library_hints'],['DEV.SECOND'])

    def test_content_suffix_and_declared_identity_must_agree(self):
        samples=[('supplemental/JCL/SYNJOB.jcl','plain unknown source\n'),
                 ('supplemental/JCL/SYNJOB.cbl','//SYNJOB JOB\n//S1 EXEC PGM=SYNPROG\n'),
                 ('supplemental/JCL/SYNJOB.jcl','//OTHER JOB\n//S1 EXEC PGM=SYNPROG\n'),
                 ('supplemental/JCL/SYNJOB.jcl','//SYNJOB JOB\n//OTHER JOB\n//S1 EXEC PGM=SYNPROG\n')]
        for relative,text in samples:
            with self.subTest(relative=relative,text=text):
                self.setUp();failed,needs=self.receipt();self.source(relative,text)
                result=find_entries(self.root,self.doc,failed,needs)
                self.assertFalse(result['entries']);self.assertEqual(result['gaps'][0]['kind'],'manual_source_classification')
                self.assertNotIn(text,encode(result['gaps']).decode())

    def test_large_original_and_safe_read_ceiling(self):
        failed,needs=self.receipt();text='//SYNJOB JOB\n//S1 EXEC PGM=SYNPROG\n'+('//* synthetic comment\n'*50000)
        path=self.source(text=text);self.assertGreater(len(text),800000)
        self.assertEqual(find_entries(self.root,self.doc,failed,needs)['entries'][0]['text'],text)
        with patch('workbench.supplemental.MAX_SOURCE_FILE_BYTES',len(text.encode())-1):
            with self.assertRaises(ValidationError):find_entries(self.root,self.doc,failed,needs)
        self.assertEqual(path.read_bytes(),text.encode())

    def test_non_text_and_encoding_are_named_gaps(self):
        for raw,kind in ((b'\xff\xff','manual_source_encoding'),(b'//SYNJOB JOB\n\x00','manual_source_binary')):
            with self.subTest(raw=raw):
                self.setUp();failed,needs=self.receipt();path=self.source();path.write_bytes(raw)
                result=find_entries(self.root,self.doc,failed,needs)
                self.assertFalse(result['entries']);self.assertEqual(result['gaps'][0]['kind'],kind)

    def test_duplicate_needs_share_original_and_preserve_both_bindings(self):
        failed,needs=self.receipt([{'kind':'job','name':'SYNJOB','source':'first','reason':'Synthetic'},
                                  {'kind':'job','name':'SYNJOB','source':'second','reason':'Synthetic'}]);self.source()
        result=find_entries(self.root,self.doc,failed,needs)
        self.assertEqual(len(result['entries']),1)
        self.assertEqual(result['entries'][0]['provenance']['retrieval_need_ids'],[n['need_id'] for n in needs])
        self.assertTrue(all(a['status']=='FOUND' for a in result['attempts']))

    def test_unsafe_redirect_and_portable_case_collision_are_rejected(self):
        failed,needs=self.receipt();path=self.source()
        from workbench.domain import path_is_link
        with patch('workbench.supplemental.path_is_link',side_effect=lambda p:p==path or path_is_link(p)):
            with self.assertRaises(ValidationError):find_entries(self.root,self.doc,failed,needs)
        # Model both spellings independently of the host filesystem's case rules.
        from workbench.supplemental import validate_source_paths
        for paths in (['supplemental/JCL/A/SYNJOB.jcl','supplemental/JCL/a/OTHER.jcl'],
                      ['supplemental/JCL/SYNJOB.jcl','supplemental/JCL/synjob.jcl']):
            with self.assertRaises(ValidationError):validate_source_paths(paths)

    def test_bound_request_accepted_hash_and_failure_identity_cannot_change(self):
        for change in ('request_hash','accepted_hash','status','need','failure','workspace'):
            with self.subTest(change=change):
                self.setUp();failed,needs=self.receipt();self.source();record=self.doc['retrieval_request']
                if change=='request_hash':self.doc['artifact_hashes'][record['artifact']]=sha('changed')
                elif change=='accepted_hash':self.doc['artifact_hashes'][record['response_artifact']]=sha('changed')
                elif change=='status':record['status']='WAITING'
                elif change=='need':needs=copy.deepcopy(needs);needs[0]['name']='OTHER'
                elif change=='failure':failed=copy.deepcopy(failed);failed[0]['reason']='Different member not found'
                else:self.doc['guided_workspace']='/wrong-workspace'
                with patch('workbench.supplemental._index',side_effect=AssertionError('no scan')):
                    with self.assertRaises(ValidationError):find_entries(self.root,self.doc,failed,needs)

    def test_partial_manual_batch_skips_only_a_registered_original_journal(self):
        failed,needs=self.receipt();self.source();entry=find_entries(self.root,self.doc,failed,needs)['entries'][0]
        relative='analysis/discovery-'+sha(encode([entry]))+'.json';raw=encode({'files':[entry]})
        write_new(self.root/'processes'/self.doc['id']/relative,raw)
        self.doc['artifacts'].append(relative);self.doc['artifact_hashes'][relative]=sha(raw)
        self.source('processes/'+self.doc['id']+'/input/sources/'+entry['path'],entry['text'])
        self.doc['source_files'][entry['path']]=entry['source_hash']
        self.doc['discovery_provenance']={entry['path']:entry['provenance']}
        self.doc['retrieval_request']['manual_failure_source_generation']=_source_generation(self.doc)
        current=self.doc['retrieval_unresolved'][need_key(needs[0])]
        current.update(status='RECEIVED',path=entry['path'],source_hash=entry['source_hash'],reason='Accepted original source')
        for remove_current in (False,True):
            if remove_current:self.doc['retrieval_unresolved']={}
            with patch('workbench.supplemental._index',side_effect=AssertionError('no re-scan')):
                self.assertEqual(find_entries(self.root,self.doc,failed,needs),{'entries':[],'gaps':[],'attempts':[]})
        self.doc['artifact_hashes'][relative]=sha('tampered')
        with self.assertRaises(ValidationError):find_entries(self.root,self.doc,failed,needs)

    def test_fixed_categories_accept_only_the_requested_structural_kind(self):
        cases=[('proc','PROCONE','PROCConverted','proc','//PROCONE PROC\n//S1 EXEC PGM=SYNPROG\n// PEND\n'),
               ('jcl_include','INCONE','JCLPlus','jcl','//S1 EXEC PGM=SYNPROG\n'),
               ('copybook','COPYONE','Copybooks','cpy','       01 SOME-FIELD PIC X(8).\n'),
               ('dclgen','DCLONE','Copybooks','dcl','EXEC SQL DECLARE APP.T TABLE (ID CHAR(8)) END-EXEC.\n'),
               ('control','CTLONE','ControlCards','ctl',' SORT FIELDS=(1,5,CH,A)\n')]
        for kind,name,bucket,suffix,text in cases:
            with self.subTest(kind=kind):
                self.setUp();failed,needs=self.receipt([{'kind':kind,'name':name,'reason':'Synthetic'}])
                self.source('supplemental/'+bucket+'/'+name+'.'+suffix,text)
                result=find_entries(self.root,self.doc,failed,needs)
                self.assertEqual(len(result['entries']),1);self.assertEqual(result['gaps'],[])
                self.assertEqual(result['entries'][0]['provenance']['manual_category'],bucket)
                self.assertEqual(result['entries'][0]['provenance']['conversion_support'],'not_established')

    def test_traversal_file_batch_byte_and_line_bounds_stay_enforced(self):
        failed,needs=self.receipt();self.source()
        for ceiling in ('MAX_SOURCE_ENTRIES','MAX_SOURCE_FILES','MAX_SOURCE_BYTES','MAX_SOURCE_LINES'):
            with self.subTest(ceiling=ceiling),patch('workbench.supplemental.'+ceiling,0):
                with self.assertRaises(ValidationError):find_entries(self.root,self.doc,failed,needs)

    def test_previously_frozen_original_cannot_be_replaced(self):
        failed,needs=self.receipt();path=self.source();relative=path.relative_to(self.root).as_posix()
        self.doc['source_files'][relative]=sha('a different preserved original')
        self.doc['retrieval_request']['manual_failure_source_generation']=_source_generation(self.doc)
        with self.assertRaises(ValidationError):find_entries(self.root,self.doc,failed,needs)

    def test_returned_original_and_failure_artifacts_are_never_mutated(self):
        failed,needs=self.receipt();self.source()
        paths=[self.root/'processes'/self.doc['id']/relative for relative in self.doc['artifacts']]
        before={str(path):path.read_bytes() for path in paths}
        doc_before=copy.deepcopy(self.doc)
        find_entries(self.root,self.doc,failed,needs)
        self.assertEqual(self.doc,doc_before)
        self.assertEqual({str(path):path.read_bytes() for path in paths},before)

    def test_positive_absence_wording_does_not_require_magic_phrase(self):
        for reason in ('Member not found in authorized library','Member not found in authoritative source library',
                       'Zowe error: member not found','Dataset member does not exist'):
            with self.subTest(reason=reason):
                self.setUp();failed,needs=self.receipt(reason=reason);self.source()
                self.assertEqual(len(find_entries(self.root,self.doc,failed,needs)['entries']),1)
