#!/usr/bin/env bash
set -euo pipefail
cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.."
fail() { printf '%s\n' "$*" >&2; exit 1; }
port=8765
browser_args=()
while [[ $# -gt 0 ]]; do
    case "$1" in
        --no-browser) browser_args=(--no-browser); shift ;;
        --port)
            [[ $# -ge 2 ]] || fail 'Provide a port from 1 to 65535 after --port.'
            [[ "$2" =~ ^[0-9]{1,5}$ ]] || fail 'Port must be an integer from 1 to 65535.'
            port=$((10#$2))
            ((port >= 1 && port <= 65535)) || fail 'Port must be an integer from 1 to 65535.'
            shift 2 ;;
        --help|-h)
            printf '%s\n' 'Usage: bash scripts/start.sh [--port 8765] [--no-browser]'
            exit 0 ;;
        *) fail "Unknown option: $1. Use --port PORT or --no-browser." ;;
    esac
done

if [[ ! -x .venv/bin/python ]] || ! .venv/bin/python -m workbench.launch --check-environment; then
    printf '%s\n' 'Preparing the locked Python environment. This is only needed on first launch or when dependencies change.'
    bash scripts/setup.sh
fi
exec .venv/bin/python -m workbench.launch --port "$port" "${browser_args[@]}"
