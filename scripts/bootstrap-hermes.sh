#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

strip_trailing_slashes() {
  local value="$1"
  while [[ "$value" != "/" && "$value" == */ ]]; do value="${value%/}"; done
  printf '%s' "$value"
}

require_safe_root() {
  [[ -n "$1" && "$1" == /* && "$1" != "/" ]] || {
    echo "$2 must be a non-root absolute path: ${1:-<empty>}" >&2
    exit 2
  }
}

canonical_path() {
  python3 -c 'from pathlib import Path; import sys; print(Path(sys.argv[1]).expanduser().resolve())' "$1"
}

ACTIVE_HOME="$(strip_trailing_slashes "${HERMES_HOME:-$HOME/.hermes}")"
require_safe_root "$ACTIVE_HOME" HERMES_HOME
ACTIVE_PARENT="${ACTIVE_HOME%/*}"
RESOLVED_ACTIVE_HOME="$(canonical_path "$ACTIVE_HOME")"
RESOLVED_ACTIVE_PARENT="${RESOLVED_ACTIVE_HOME%/*}"
ACTIVE_PROFILE_HINT="${HERMES_PROFILE_NAME:-${HERMES_PROFILE:-}}"
if [[ "${ACTIVE_PARENT##*/}" == "profiles" && (
  -f "$ACTIVE_HOME/profile.yaml" || "$ACTIVE_PROFILE_HINT" == "${ACTIVE_HOME##*/}"
) ]]; then
  SHARED_HOME="${ACTIVE_PARENT%/*}"
elif [[ "${RESOLVED_ACTIVE_PARENT##*/}" == "profiles" && (
  -f "$RESOLVED_ACTIVE_HOME/profile.yaml" || "$ACTIVE_PROFILE_HINT" == "${RESOLVED_ACTIVE_HOME##*/}"
) ]]; then
  SHARED_HOME="${RESOLVED_ACTIVE_PARENT%/*}"
else
  SHARED_HOME="$RESOLVED_ACTIVE_HOME"
fi
SHARED_HOME="$(canonical_path "$SHARED_HOME")"
require_safe_root "$SHARED_HOME" "shared Hermes home"
export HERMES_HOME="$SHARED_HOME"

if ! command -v hermes >/dev/null 2>&1; then
  echo "Hermes is not installed or not on PATH." >&2
  exit 1
fi

install_charter() {
  local name="$1"
  local charter="$ROOT/profiles/$name.md"
  local hroot="$SHARED_HOME/profiles/$name"
  hroot="$(canonical_path "$hroot")"
  if [[ "$hroot" != "$SHARED_HOME/"* ]]; then
    echo "Profile home resolves outside shared Hermes home: $hroot" >&2
    exit 2
  fi
  local soul="$hroot/SOUL.md"
  [[ -f "$charter" ]] || return 0
  mkdir -p "$hroot"
  python3 - "$soul" "$charter" <<'PYCHARTER'
from pathlib import Path
import sys
soul = Path(sys.argv[1])
charter = Path(sys.argv[2]).read_text(encoding="utf-8").strip()
start = "<!-- BEGIN THINKTOFINISH ROLE CHARTER -->"
end = "<!-- END THINKTOFINISH ROLE CHARTER -->"
old = soul.read_text(encoding="utf-8") if soul.exists() else ""
block = f"{start}\n{charter}\n{end}"
if start in old and end in old:
    before = old.split(start, 1)[0].rstrip()
    after = old.split(end, 1)[1].lstrip()
    new = "\n\n".join(part for part in (before, block, after) if part).rstrip() + "\n"
else:
    new = (old.rstrip() + "\n\n" if old.strip() else "") + block + "\n"
soul.write_text(new, encoding="utf-8")
PYCHARTER
  echo "Role charter installed: $name"
}

create_profile() {
  local name="$1" desc="$2"
  if hermes profile show "$name" >/dev/null 2>&1; then
    echo "Profile exists: $name"
  else
    hermes profile create "$name" --description "$desc"
  fi
  HERMES_HOME="$SHARED_HOME" "$ROOT/scripts/install-local.sh" --profile "$name"
  install_charter "$name"
}

create_profile orchestrator "Owns ThinkToFinish company governance and macro delivery phases; coordinates through OMH/Hermes but does not implement production code."
create_profile product "Owns the authoritative Product Spec, stable requirement IDs, scope, risks, and acceptance criteria; may use OMH interview/research as supporting capabilities."
create_profile architect "Owns authoritative ADRs, architecture contracts, shared decisions, security boundaries, and verification plans; may use OMH research/planning as support."
create_profile engineer "Owns a governed Company Task Contract; uses OMH/coding owners for execution where appropriate and Hermes native same-card review."
create_profile qa-reviewer "Independent implementation reviewer and integrated QA/security judge; uses Hermes native review lifecycle and may consume OMH QA evidence."
create_profile release-manager "Assembles company release evidence, checks CI/security/traceability/residual risk, and stops at production human gates."

# Enable the portable Company Core in the default profile for interactive governance.
HERMES_HOME="$SHARED_HOME" "$ROOT/scripts/install-local.sh" --profile default

echo
echo "ThinkToFinish Company Core profiles installed."
if command -v omh >/dev/null 2>&1; then
  echo "OMH Work Intelligence detected: $(omh --version 2>/dev/null || echo installed)"
else
  echo "OMH is not on PATH. Recommended: $ROOT/scripts/install-omh.sh"
fi
echo "Next: create a board with scripts/create-pilot.sh /absolute/path/to/project"
echo "Then start/keep the gateway: hermes -p orchestrator gateway start"
echo "New projects use Hermes native review/rework. The legacy TTF transition engine is not enabled by default."
