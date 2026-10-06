"""Run the 500 additional scenarios R501–R1000 without duplicating the first set."""
import argparse
from pathlib import Path
import sys
import uuid

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from tools.review500 import run

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',default=str(ROOT/'.implementation/tmp'/('expanded-'+uuid.uuid4().hex)))
    args=parser.parse_args()
    raise SystemExit(run(args.output,501,1000,'test_expanded_*.py'))
