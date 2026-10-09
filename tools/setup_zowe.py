#!/usr/bin/env python3
"""Prepare clean project Zowe profiles from one private .env; secure Explorer locally."""
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from workbench.zowe_setup import main

if __name__ == '__main__': raise SystemExit(main())
