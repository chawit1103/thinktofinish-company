#!/usr/bin/env bash
set -euo pipefail
FAIL=0

check() {
  local label="$1"; shift
  if "$@" >/dev/null 2>&1; then
    printf 'PASS  %s\n' "$label"
  else
    printf 'FAIL  %s\n' "$label"
    FAIL=1
  fi
}

if command -v python3 >/dev/null 2>&1; then
  PYTHON_BIN="$(command -v python3)"
elif command -v python >/dev/null 2>&1; then
  PYTHON_BIN="$(command -v python)"
else
  echo "FAIL  Python 3.11+"
  exit 1
fi

check "Hermes CLI" command -v hermes
check "Git" command -v git
check "Python 3.11+" "$PYTHON_BIN" -c 'import sys; raise SystemExit(0 if sys.version_info >= (3,11) else 1)'

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
"$PYTHON_BIN" - <<PY || FAIL=1
import json, pathlib
root=pathlib.Path(r'''$ROOT''')
plugin=json.loads((root/'plugin.json').read_text())
mcp=json.loads((root/'mcp.json').read_text())
assert plugin['$schema']=='https://agent-plugins.org/schemas/1.0.0/plugin.schema.json'
assert plugin['name']=='thinktofinish-company'
assert mcp['$schema']=='https://agent-plugins.org/schemas/1.0.0/mcp.schema.json'
assert 'company' in mcp['mcpServers']
print('PASS  Portable Agent Plugin manifest')
PY

if "$PYTHON_BIN" "$ROOT/scripts/mcp-smoke.py" --server "$ROOT/server.py" >/dev/null; then
  echo "PASS  MCP protocol smoke test"
else
  echo "FAIL  MCP protocol smoke test"
  FAIL=1
fi

if command -v hermes >/dev/null 2>&1; then
  hermes plugins list 2>/dev/null | grep -q 'thinktofinish-company' \
    && echo "PASS  Hermes discovers plugin" \
    || echo "INFO  Plugin not installed in the active profile yet (run scripts/install-local.sh)"
  hermes kanban boards list >/dev/null 2>&1 \
    && echo "PASS  Hermes Kanban board surface" \
    || echo "INFO  Kanban has not been initialized yet"
fi

exit "$FAIL"
