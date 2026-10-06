"""Execute the 500 numbered adversarial scenarios and record each outcome.

Run from the repository using the locked Python environment, with frontend
development dependencies installed for the UI boundary checks. Evidence stays
private under .implementation until the consolidated review is inspected.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import sys
import time
import unittest
import uuid

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
sys.path.insert(0,str(ROOT/'tests'))
from workbench.domain import require, safe_path
from tools.review_iterations import fingerprint


def flatten(suite):
    for item in suite:
        if isinstance(item,unittest.TestSuite):yield from flatten(item)
        else:yield item


class ReviewResult(unittest.TextTestResult):
    def __init__(self,*args,**kwargs):
        super().__init__(*args,**kwargs);self.rows=[];self.active={}

    def startTest(self,test):
        super().startTest(test)
        self.active[test.id()]={'test':test.id(),'status':'ERROR','started':time.monotonic()}

    def addSuccess(self,test):
        super().addSuccess(test);self.active[test.id()]['status']='PASS'

    def addFailure(self,test,err):
        super().addFailure(test,err);self.active[test.id()]['status']='FAIL'

    def addError(self,test,err):
        super().addError(test,err)
        if test.id() in self.active:self.active[test.id()]['status']='ERROR'

    def addSkip(self,test,reason):
        super().addSkip(test,reason);self.active[test.id()].update(status='UNVERIFIED',reason=reason)

    def addExpectedFailure(self,test,err):
        super().addExpectedFailure(test,err);self.active[test.id()]['status']='KNOWN_FAILURE'

    def addUnexpectedSuccess(self,test):
        super().addUnexpectedSuccess(test);self.active[test.id()]['status']='UNEXPECTED_SUCCESS'

    def addSubTest(self,test,subtest,err):
        super().addSubTest(test,subtest,err)
        if err is not None:self.active[test.id()]['status']='FAIL'

    def stopTest(self,test):
        row=self.active.pop(test.id())
        row['seconds']=round(time.monotonic()-row.pop('started'),6)
        row['id']='R'+re.search(r'\.test_r(\d{3,4})_',test.id())[1]
        self.rows.append(row);super().stopTest(test)
        if len(self.rows)%25==0:print(f'{len(self.rows)}/500 scenarios executed',flush=True)


def run(output,first=1,last=500,pattern='test_review500_*.py'):
    output=Path(output).absolute()
    require(output.is_relative_to(ROOT/'.implementation'),'Review logs belong under .implementation')
    safe_path(ROOT,output.relative_to(ROOT).as_posix())
    require(not output.exists(),'Use a fresh output directory; previous review evidence is immutable')
    output.mkdir(parents=True)
    for key in list(os.environ):
        if key.startswith('WB_'):del os.environ[key]
    # Keep test workspaces out of the repository's allowlisted root.
    temp=ROOT/'.implementation/tmp';temp.mkdir(parents=True,exist_ok=True)
    os.environ['TMPDIR']=str(temp)
    import tempfile
    tempfile.tempdir=None
    suite=unittest.defaultTestLoader.discover(str(ROOT/'tests'),pattern=pattern)
    cases=list(flatten(suite));ids=[]
    for case in cases:
        match=re.search(r'\.test_r(\d{3,4})_',case.id())
        require(match is not None,'Every review needs a numbered, distinct test: '+case.id())
        ids.append(int(match[1]))
    require(last-first+1==500 and sorted(ids)==list(range(first,last+1)),
            f'Reviews must contain each ID R{first:03d} through R{last:03d} exactly once')
    before=fingerprint()
    with (output/'execution.log').open('w',encoding='utf-8') as log:
        result=unittest.TextTestRunner(stream=log,verbosity=2,resultclass=ReviewResult).run(suite)
    after=fingerprint()
    report={'schema_version':1,'created':datetime.now(timezone.utc).isoformat(),
            'method':'500 individually named executable review scenarios; not 500 complete-suite runs, independent reviewers, or exhaustive proof',
            'source_fingerprint':before,'source_unchanged':before==after,
            'planned':500,'executed':len(result.rows),'passed':sum(r['status']=='PASS' for r in result.rows),
            'unverified':sum(r['status']=='UNVERIFIED' for r in result.rows),
            'rows':sorted(result.rows,key=lambda r:int(r['id'][1:])),
            'execution_log_sha256':hashlib.sha256((output/'execution.log').read_bytes()).hexdigest(),
            'limitations':['Local fictional fixtures only; live connections and native platform behavior remain separately unverified',
                           'Passing tests do not add unsupported conversion semantics or establish observed mainframe parity']}
    report['accepted']=result.wasSuccessful() and before==after and len(result.rows)==500 and report['passed']==500
    (output/'receipt.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({k:report[k] for k in ('planned','executed','passed','unverified','source_unchanged','accepted')}),flush=True)
    return 0 if report['accepted'] else 2


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',default=str(ROOT/'.implementation/tmp'/('review500-'+uuid.uuid4().hex)))
    raise SystemExit(run(parser.parse_args().output))
