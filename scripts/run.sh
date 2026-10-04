#!/bin/bash
set -e
cd "$(dirname "$0")/.."
PY=".venv/bin/python"
if [ ! -x "$PY" ]; then
  python3 -m venv .venv
  .venv/bin/pip install -q -r requirements.txt
fi
"$PY" -m app run "$@"
