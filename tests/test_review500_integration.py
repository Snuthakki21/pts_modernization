"""Twenty integration reviews: filename preservation and OS-owned writer locks."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from workbench.domain import ValidationError
from workbench.instance import InstanceLock
from workbench.limits import MAX_SOURCE_FILES, MAX_SOURCE_FILE_BYTES, MAX_UI_SOURCE_BYTES

ROOT=Path(__file__).resolve().parents[1]


class IntegrationReviews(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.build=tempfile.TemporaryDirectory()
        cls.bundle=Path(cls.build.name)/'intake.cjs'
        script="require('./node_modules/esbuild').buildSync({entryPoints:['src/intakeFiles.ts'],bundle:true,platform:'node',format:'cjs',outfile:process.argv[1]})"
        subprocess.run(['node','-e',script,str(cls.bundle)],cwd=ROOT/'frontend',check=True,capture_output=True)

    @classmethod
    def tearDownClass(cls):cls.build.cleanup()

    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)

    def node(self,code):
        prefix='const {readSourceFiles,readUtf8Source}=require('+json.dumps(str(self.bundle))+');\n'
        prefix+='const file=(name,text)=>({name,size:Buffer.byteLength(text),arrayBuffer:async()=>Buffer.from(text)});\n'
        script=prefix+'(async()=>{'+code+'})().catch(e=>{console.error(e);process.exit(1)});'
        p=subprocess.run(['node','-e',script],capture_output=True,text=True,timeout=15)
        self.assertEqual(p.returncode,0,p.stderr)
        return json.loads(p.stdout)

    def lock(self,path):
        lock=InstanceLock(path);self.addCleanup(lock.close);return lock

    def test_r481_prototype_filename_is_retained(self):
        """A selected __proto__ file must survive upload serialization."""
        result=self.node("console.log(JSON.stringify(await readSourceFiles([file('__proto__','SOURCE')])));")
        self.assertEqual(result,{'__proto__':'SOURCE'})

    def test_r482_duplicate_filename_rejects_whole_selection(self):
        """Two same-named selected files must not overwrite one another."""
        result=self.node("try{await readSourceFiles([file('A','one'),file('A','two')]);throw Error('accepted')}catch(e){console.log(JSON.stringify(e.message))}")
        self.assertIn('Duplicate filenames',result)

    def test_r483_object_builtin_names_are_plain_source_keys(self):
        """Object built-in names must not collide with export bookkeeping."""
        result=self.node("console.log(JSON.stringify(await readSourceFiles([file('constructor','A'),file('toString','B')])));")
        self.assertEqual(result,{'constructor':'A','toString':'B'})

    def test_r484_invalid_utf8_is_rejected_without_replacement_characters(self):
        """Invalid UTF-8 must not silently change source bytes to replacement text."""
        result=self.node("try{await readUtf8Source({name:'BAD',size:2,arrayBuffer:async()=>new Uint8Array([0xc3,0x28])},10);throw Error('accepted')}catch(e){console.log(JSON.stringify(e.message))}")
        self.assertIn('UTF-8 text export',result)

    def test_r485_source_bom_columns_and_line_endings_are_preserved(self):
        """Text intake must preserve BOM, significant spaces and CRLF evidence."""
        original='\ufeff000100     MOVE X TO Y.  \r\n'
        result=self.node('console.log(JSON.stringify(await readUtf8Source(file("A",'+json.dumps(original)+'),512000)));')
        self.assertEqual(result,original)

    def test_r486_excess_file_count_rejects_before_reading(self):
        """More than 10,000 selections must be rejected before file reads begin."""
        result=self.node("let reads=0;try{await readSourceFiles(Array.from({length:"+str(MAX_SOURCE_FILES+1)+"},(_,i)=>({name:String(i),size:0,arrayBuffer:async()=>{reads++;return new ArrayBuffer(0)}})))}catch(e){console.log(JSON.stringify({error:e.message,reads}))}")
        self.assertEqual(result['reads'],0);self.assertIn('10,000',result['error'])

    def test_r487_aggregate_byte_limit_is_checked_before_reads(self):
        """An export above the 32 MiB browser budget must fail before member reads."""
        result=self.node("let reads=0;try{await readSourceFiles(Array.from({length:3},(_,i)=>({name:String(i),size:"+str(MAX_UI_SOURCE_BYTES//3+1)+",arrayBuffer:async()=>{reads++;return new ArrayBuffer(0)}})))}catch(e){console.log(JSON.stringify({error:e.message,reads}))}")
        self.assertEqual(result['reads'],0);self.assertIn('32 MiB',result['error'])

    def test_r488_oversized_member_is_not_materialized(self):
        """One member above 16 MiB must fail before allocating its byte buffer."""
        result=self.node("let reads=0;try{await readSourceFiles([{name:'BIG',size:"+str(MAX_SOURCE_FILE_BYTES+1)+",arrayBuffer:async()=>{reads++;return new ArrayBuffer(0)}}])}catch(e){console.log(JSON.stringify({error:e.message,reads}))}")
        self.assertEqual(result['reads'],0);self.assertIn(str(MAX_SOURCE_FILE_BYTES),result['error'])

    def test_r489_later_member_failure_does_not_return_partial_export(self):
        """A failure after a valid first member must reject the whole selection."""
        result=self.node("try{const data=await readSourceFiles([file('FIRST','OK'),{name:'SECOND',size:1,arrayBuffer:async()=>{throw Error('device failure')}}]);console.log(JSON.stringify(data))}catch(e){console.log(JSON.stringify({rejected:true,message:e.message}))}")
        self.assertTrue(result['rejected']);self.assertIn('SECOND',result['message'])

    def test_r490_empty_selection_remains_empty_for_local_export_fallback(self):
        """Clearing an upload must not invent a source file or keep stale content."""
        self.assertEqual(self.node("console.log(JSON.stringify(await readSourceFiles([])));"),{})

    def test_r491_file_read_failure_names_the_affected_source(self):
        """A file read error must surface a source-specific actionable message."""
        result=self.node("try{await readUtf8Source({name:'LOCKED.cbl',size:1,arrayBuffer:async()=>{throw Error('locked')}},10)}catch(e){console.log(JSON.stringify(e.message))}")
        self.assertIn('LOCKED.cbl',result);self.assertIn('text export',result)

    def test_r492_second_writer_is_rejected(self):
        """A second coordinator lock must not acquire the same workspace."""
        self.lock(self.root)
        with self.assertRaisesRegex(ValidationError,'Another workbench'):InstanceLock(self.root)

    def test_r493_os_releases_lock_after_process_termination(self):
        """An abruptly terminated writer must not leave a permanent stale lock."""
        code="from pathlib import Path;from workbench.instance import InstanceLock;import sys,time;lock=InstanceLock(Path(sys.argv[1]));print('ready',flush=True);time.sleep(30)"
        proc=subprocess.Popen([sys.executable,'-c',code,str(self.root)],cwd=ROOT,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
        try:
            self.assertEqual(proc.stdout.readline().strip(),'ready')
            with self.assertRaises(ValidationError):InstanceLock(self.root)
        finally:
            proc.kill();proc.communicate(timeout=5)
        self.lock(self.root)

    def test_r494_independent_workspaces_can_each_have_a_writer(self):
        """Workspace locking must not serialize unrelated process workspaces."""
        self.lock(self.root/'one');self.lock(self.root/'two')

    def test_r495_symlink_workspace_root_is_refused(self):
        """The lock boundary must reject a root that redirects through a symlink."""
        actual=self.root/'actual';actual.mkdir();alias=self.root/'alias';alias.symlink_to(actual,target_is_directory=True)
        with self.assertRaisesRegex(ValidationError,'Unsafe workspace'):InstanceLock(alias)
        self.assertFalse((actual/'.migration').exists())

    def test_r496_symlink_state_directory_is_refused(self):
        """A redirected state directory must not create locks outside the workspace."""
        elsewhere=self.root/'elsewhere';elsewhere.mkdir();(self.root/'.migration').symlink_to(elsewhere,target_is_directory=True)
        with self.assertRaisesRegex(ValidationError,'Unsafe state'):InstanceLock(self.root)
        self.assertFalse((elsewhere/'coordinator.lock').exists())

    def test_r497_symlink_lock_file_is_refused(self):
        """The lock file itself must not point to another file."""
        state=self.root/'.migration';state.mkdir();sentinel=self.root/'sentinel';sentinel.write_text('unchanged')
        (state/'coordinator.lock').symlink_to(sentinel)
        with self.assertRaisesRegex(ValidationError,'Unsafe lock'):InstanceLock(self.root)
        self.assertEqual(sentinel.read_text(),'unchanged')

    def test_r498_symlink_parent_is_refused(self):
        """A safe-looking child path must not hide a symlink in a parent."""
        actual=self.root/'actual';actual.mkdir();alias=self.root/'alias';alias.symlink_to(actual,target_is_directory=True)
        with self.assertRaisesRegex(ValidationError,'Unsafe workspace'):InstanceLock(alias/'child')
        self.assertFalse((actual/'child').exists())

    def test_r499_state_file_collision_does_not_overwrite_file(self):
        """A file named .migration must cause failure and retain its bytes."""
        state=self.root/'.migration';state.write_text('evidence')
        with self.assertRaises(OSError):InstanceLock(self.root)
        self.assertEqual(state.read_text(),'evidence')

    @unittest.skipIf(os.name=='nt','POSIX fault injection; native Windows remains separately unverified')
    def test_r500_failed_os_lock_closes_open_descriptor(self):
        """A rejected OS lock must close its descriptor before returning failure."""
        opened=[];original=Path.open
        def track(path,*args,**kwargs):
            handle=original(path,*args,**kwargs);opened.append(handle);return handle
        with patch.object(Path,'open',track),patch('fcntl.flock',side_effect=OSError('fixture lock failure')):
            with self.assertRaises(ValidationError):InstanceLock(self.root)
        self.assertEqual(len(opened),1);self.assertTrue(opened[0].closed)
