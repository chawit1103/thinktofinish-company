#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
QUICK=0
STATIC_ONLY=0

usage() {
  cat <<'USAGE'
Usage: scripts/compatibility-check.sh [--quick|--static]

--quick   Check installed commands + TTF static/MCP smoke; skip OMH doctor.
--static  Run repository-only boundary checks; do not require Hermes/OMH.
USAGE
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --quick) QUICK=1 ;;
    --static) STATIC_ONLY=1 ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown option: $1" >&2; usage >&2; exit 2 ;;
  esac
  shift
done

python3 "$ROOT/scripts/runtime-boundary-check.py"

if [[ "$STATIC_ONLY" -eq 1 ]]; then
  exit 0
fi

for cmd in hermes omh python3; do
  command -v "$cmd" >/dev/null 2>&1 || { echo "Missing required command: $cmd" >&2; exit 1; }
done

echo "Hermes: $(hermes --version 2>/dev/null || echo installed)"
echo "OMH:    $(omh --version 2>/dev/null || echo installed)"

if [[ "$QUICK" -eq 0 ]]; then
  omh doctor
fi

python3 "$ROOT/scripts/mcp-smoke.py"

echo "TTF_COMPATIBILITY_OK"
