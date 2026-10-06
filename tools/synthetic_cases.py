"""Source-grounded synthetic generator CLI; no source-system writes."""
import argparse
from pathlib import Path
from workbench.source import analyze_program
from workbench.fixtures import plan_cases
from workbench.domain import encode, require, write_new

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--source',required=True);p.add_argument('--copybooks');p.add_argument('--output',required=True);p.add_argument('--seed',type=int,default=21);p.add_argument('--budget',type=int,default=256);args=p.parse_args()
    require(8<=args.budget<=256,'Budget must be 8..256')
    source=Path(args.source);require(source.stat().st_size<=512000,'Source exceeds bound');files={}
    if args.copybooks:
        for f in Path(args.copybooks).glob('*.cpy'):
            require(f.stat().st_size<=512000 and len(files)<200,'Copybook export exceeds bounds');files[f.name]=f.read_text()
    analysis=analyze_program(source.name,source.read_text(),files);require(not analysis['blockers'],'Unsupported source; inspect its analysis in the UI before generating expected cases')
    write_new(Path(args.output),encode(plan_cases(analysis,args.seed,args.budget)))
