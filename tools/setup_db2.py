#!/usr/bin/env python3
"""Prepare local nonsecret Db2 settings and the required CA placeholder."""
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from workbench.db2_setup import main

if __name__=='__main__':raise SystemExit(main())
