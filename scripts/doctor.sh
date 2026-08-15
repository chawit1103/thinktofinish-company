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

if command -v omh >/dev/null 2>&1; then
  echo "PASS  Oh My Hermes Work Intelligence ($(omh --version 2>/dev/null || echo installed))"
else
  echo "INFO  OMH not installed; Hermes-native fallback remains possible, recommended install: scripts/install-omh.sh"
fi

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
"$PYTHON_BIN" - <<PY || FAIL=1
import json, pathlib
root=pathlib.Path(r'''$ROOT''')
plugin=json.loads((root/'plugin.json').read_text())
mcp=json.loads((root/'mcp.json').read_text())
runtime=json.loads((root/'policies/runtime-boundary.json').read_text())
assert plugin['$schema']=='https://agent-plugins.org/schemas/1.0.0/plugin.schema.json'
assert plugin['name']=='thinktofinish-company'
assert mcp['$schema']=='https://agent-plugins.org/schemas/1.0.0/mcp.schema.json'
assert 'company' in mcp['mcpServers']
assert runtime['schema']=='ttf_runtime_boundary/v1'
assert runtime['legacy']['kanban_transition_engine']['enabled_by_default'] is False
print('PASS  Portable Company Core manifests')
PY

if "$PYTHON_BIN" "$ROOT/scripts/runtime-boundary-check.py" >/dev/null; then
  echo "PASS  Company Core runtime boundary"
else
  echo "FAIL  Company Core runtime boundary"
  FAIL=1
fi

if "$PYTHON_BIN" "$ROOT/scripts/mcp-smoke.py" --server "$ROOT/server.py" >/dev/null; then
  echo "PASS  MCP protocol smoke test"
else
  echo "FAIL  MCP protocol smoke test"
  FAIL=1
fi

if command -v hermes >/dev/null 2>&1; then
  hermes plugins list 2>/dev/null | grep -q 'thinktofinish-company' \
    && echo "PASS  Hermes discovers ThinkToFinish plugin" \
    || echo "INFO  TTF plugin not installed in active profile yet (run scripts/bootstrap-company.sh or scripts/install-local.sh)"
  hermes kanban boards list >/dev/null 2>&1 \
    && echo "PASS  Hermes Kanban board surface" \
    || echo "INFO  Kanban has not been initialized yet"
fi

exit "$FAIL"
