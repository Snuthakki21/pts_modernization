"""Native Windows test launcher: run real CPython without installing packages."""
import json
import os
from pathlib import Path
import subprocess
import sys


name, *arguments = sys.argv[1:]
with Path(os.environ['FAKE_LOG']).open('a', encoding='utf-8') as stream:
    stream.write(json.dumps({'kind': 'candidate', 'name': name, 'args': arguments}) + '\n')
if arguments[:1] == ['-3.12']:
    arguments = arguments[1:]
if arguments[:1] == ['-c']:
    code = json.loads(os.environ['FAKE_CANDIDATE_CODES'])[name]
    if code == 'wrong-version':
        arguments[1] = 'import sys; sys.version_info = (3, 11, 14); ' + arguments[1]
    elif code == 'wrong-implementation':
        arguments[1] = "import platform; platform.python_implementation = lambda: 'PyPy'; " + arguments[1]
    elif code:
        raise SystemExit(code)
if arguments[:2] == ['-m', 'venv']:
    arguments.insert(2, '--without-pip')
raise SystemExit(subprocess.run([os.environ['FAKE_REAL_PYTHON'], *arguments], check=False, timeout=20).returncode)
