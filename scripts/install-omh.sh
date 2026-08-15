#!/usr/bin/env bash
set -euo pipefail

# ThinkToFinish-supported Oh My Hermes baseline.
OMH_VERSION="${TTF_OMH_VERSION:-1.0.6}"
OMH_COMMIT="${TTF_OMH_COMMIT:-0106a636d7c971408e9caf634b5e21a471fc5082}"
RUN_SETUP=1
RUN_DOCTOR=1
RUN_SMOKE=0

usage() {
  cat <<'USAGE'
Usage: scripts/install-omh.sh [options]

Install/configure the ThinkToFinish-supported Oh My Hermes stable baseline.

Options:
  --skip-setup    Install OMH but do not run `omh setup`.
  --skip-doctor   Do not run `omh doctor` after setup.
  --smoke         Also run `omh release hermes-smoke`.
  -h, --help      Show this help.

Environment overrides (for compatibility testing only):
  TTF_OMH_VERSION
  TTF_OMH_COMMIT
USAGE
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --skip-setup) RUN_SETUP=0 ;;
    --skip-doctor) RUN_DOCTOR=0 ;;
    --smoke) RUN_SMOKE=1 ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown option: $1" >&2; usage >&2; exit 2 ;;
  esac
  shift
done

for cmd in hermes curl python3; do
  if ! command -v "$cmd" >/dev/null 2>&1; then
    echo "Required command not found: $cmd" >&2
    exit 1
  fi
done

if [[ ! "$OMH_COMMIT" =~ ^[0-9a-f]{40}$ ]]; then
  echo "TTF_OMH_COMMIT must be a full 40-character Git commit SHA." >&2
  exit 2
fi
if [[ ! "$OMH_VERSION" =~ ^[0-9]+\.[0-9]+\.[0-9]+([.-][0-9A-Za-z.-]+)?$ ]]; then
  echo "TTF_OMH_VERSION is not a supported version string: $OMH_VERSION" >&2
  exit 2
fi

TMPDIR_OMH="$(mktemp -d "${TMPDIR:-/tmp}/ttf-omh.XXXXXX")"
cleanup() { rm -rf "$TMPDIR_OMH"; }
trap cleanup EXIT HUP INT TERM

INSTALLER="$TMPDIR_OMH/install.sh"
INSTALLER_URL="https://raw.githubusercontent.com/rlaope/oh-my-hermes/${OMH_COMMIT}/install.sh"

echo "ThinkToFinish OMH baseline: v$OMH_VERSION @ $OMH_COMMIT"
echo "Fetching pinned installer: $INSTALLER_URL"
curl --fail --silent --show-error --location \
  --proto '=https' --tlsv1.2 \
  "$INSTALLER_URL" -o "$INSTALLER"

# The installer itself is source-pinned above. These variables also force the
# requested stable package version so the install cannot silently follow main.
OMH_CHANNEL=stable OMH_VERSION="$OMH_VERSION" sh "$INSTALLER"

# Some installers add a user bin directory that was not present in the shell's
# original PATH. Probe common locations before reporting failure.
if ! command -v omh >/dev/null 2>&1; then
  for candidate in "$HOME/.local/bin/omh" "$HOME/bin/omh"; do
    if [[ -x "$candidate" ]]; then
      export PATH="$(dirname "$candidate"):$PATH"
      break
    fi
  done
fi

if ! command -v omh >/dev/null 2>&1; then
  echo "OMH installation completed but the `omh` command is not on PATH." >&2
  echo "Open a new shell or add the installer-reported bin directory to PATH, then run: omh setup && omh doctor" >&2
  exit 1
fi

echo "Installed command: $(command -v omh)"
omh --version || true

if [[ "$RUN_SETUP" -eq 1 ]]; then
  echo
  echo "Running OMH setup. Preserve existing Hermes configuration and review any model-alias changes before accepting them."
  omh setup
fi

if [[ "$RUN_DOCTOR" -eq 1 ]]; then
  echo
  echo "Running OMH doctor..."
  omh doctor
fi

if [[ "$RUN_SMOKE" -eq 1 ]]; then
  echo
  echo "Running OMH/Hermes compatibility smoke..."
  omh release hermes-smoke
fi

echo
echo "OMH is installed at the ThinkToFinish-supported stable baseline."
echo "Pinned baseline: v$OMH_VERSION @ $OMH_COMMIT"
