#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

INSTALL_OMH=1
OMH_SETUP=1
OMH_DOCTOR=1
OMH_SMOKE=0

usage() {
  cat <<'USAGE'
Usage: scripts/bootstrap-company.sh [options]

Bootstrap the recommended ThinkToFinish stack:
  ThinkToFinish Company Core → Oh My Hermes → Hermes Agent.

Options:
  --skip-omh          Do not install/update the pinned OMH baseline.
  --skip-omh-setup    Install OMH but skip interactive `omh setup`.
  --skip-omh-doctor   Skip `omh doctor`.
  --omh-smoke         Run `omh release hermes-smoke` after setup.
  -h, --help          Show this help.
USAGE
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --skip-omh) INSTALL_OMH=0 ;;
    --skip-omh-setup) OMH_SETUP=0 ;;
    --skip-omh-doctor) OMH_DOCTOR=0 ;;
    --omh-smoke) OMH_SMOKE=1 ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown option: $1" >&2; usage >&2; exit 2 ;;
  esac
  shift
done

if ! command -v hermes >/dev/null 2>&1; then
  echo "Hermes Agent is required and must be on PATH before bootstrapping ThinkToFinish." >&2
  exit 1
fi

if [[ "$INSTALL_OMH" -eq 1 ]]; then
  OMH_ARGS=()
  [[ "$OMH_SETUP" -eq 1 ]] || OMH_ARGS+=(--skip-setup)
  [[ "$OMH_DOCTOR" -eq 1 ]] || OMH_ARGS+=(--skip-doctor)
  [[ "$OMH_SMOKE" -eq 0 ]] || OMH_ARGS+=(--smoke)
  "$ROOT/scripts/install-omh.sh" "${OMH_ARGS[@]}"
else
  if ! command -v omh >/dev/null 2>&1; then
    echo "--skip-omh was requested but the `omh` command is not available." >&2
    exit 1
  fi
fi

echo
echo "Installing ThinkToFinish Company Core and role charters into Hermes..."
"$ROOT/scripts/bootstrap-hermes.sh"

echo
echo "Checking the layered runtime boundary..."
"$ROOT/scripts/compatibility-check.sh" --quick

echo
echo "ThinkToFinish stack is ready."
echo "Layer order: ThinkToFinish Company Core → Oh My Hermes Work Intelligence → Hermes Execution OS."
echo "Next: ./scripts/create-pilot.sh /absolute/path/to/project [board-slug]"
