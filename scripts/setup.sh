#!/usr/bin/env bash
set -euo pipefail
cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.."
fail() { printf '%s\n' "$*" >&2; exit 1; }

if [[ ! -x .venv/bin/python ]]; then
    setup_python=''
    for candidate in python3.12 python3; do
        if command -v "$candidate" >/dev/null 2>&1; then
            setup_python="$candidate"
            break
        fi
    done
    [[ -n "$setup_python" ]] || fail 'CPython 3.12 is required. Install CPython 3.12 with venv and pip, then rerun this script.'
    "$setup_python" -c 'import platform, sys; sys.exit(0 if sys.version_info[:2] == (3, 12) and platform.python_implementation() == "CPython" else 1)' || fail 'CPython 3.12 is required. Put python3.12 on PATH, then rerun this script.'
    "$setup_python" -m venv .venv || fail 'Could not create .venv. Install the Python 3.12 venv/ensurepip package and check folder permissions.'
fi
.venv/bin/python -c 'import platform, sys; sys.exit(0 if sys.version_info[:2] == (3, 12) and platform.python_implementation() == "CPython" else 1)' || fail 'Existing .venv must use CPython 3.12. Rename it, then rerun setup to create a compatible environment.'
.venv/bin/python -m pip --disable-pip-version-check --no-input install --require-hashes --only-binary=:all: -r requirements.lock || fail 'Dependency installation failed. Check access to pypi.org/files.pythonhosted.org and wheel availability for CPython 3.12; no unverified source build was attempted.'
.venv/bin/python -m workbench.preflight --workspace "$PWD" --initialize-knowledge || fail 'Setup checks found blockers. Follow the diagnostic actions above, then rerun setup; existing application knowledge was preserved.'
mkdir -p Endeavor knowledge/inbox
printf '%s\n' 'Environment ready. Run bash scripts/start.sh to open the setup screen.'
