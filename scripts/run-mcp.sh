#!/usr/bin/env bash
set -euo pipefail
ROOT="${PLUGIN_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"

if command -v python3 >/dev/null 2>&1; then
  PYTHON_BIN="$(command -v python3)"
elif command -v python >/dev/null 2>&1; then
  PYTHON_BIN="$(command -v python)"
else
  echo "thinktofinish-company: Python 3.11+ is required." >&2
  exit 127
fi

exec "$PYTHON_BIN" "$ROOT/server.py"
