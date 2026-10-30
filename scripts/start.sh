#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
[[ -x .venv/bin/python ]] || { echo 'Run ./scripts/setup.sh first.'; exit 1; }
export PYTHONUTF8=1
exec .venv/bin/python scripts/run_server.py "$@"
