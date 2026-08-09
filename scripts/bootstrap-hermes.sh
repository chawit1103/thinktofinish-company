#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

if ! command -v hermes >/dev/null 2>&1; then
  echo "Hermes is not installed or not on PATH." >&2
  exit 1
fi

install_charter() {
  local name="$1"
  local charter="$ROOT/profiles/$name.md"
  local hroot="${HERMES_HOME:-$HOME/.hermes}/profiles/$name"
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
  "$ROOT/scripts/install-local.sh" --profile "$name"
  install_charter "$name"
}

create_profile orchestrator "Coordinates goals through Hermes Kanban; decomposes, routes, monitors, replans, and applies ThinkToFinish governance. Does not implement production code."
create_profile product "Researches users, market, requirements, and produces product specifications with stable requirement IDs and acceptance criteria."
create_profile architect "Creates implementation-ready architecture, ADRs, data/API contracts, security boundaries, and verification plans."
create_profile engineer "Implements scoped software tasks in worktrees, writes tests, runs quality gates, and produces PR-ready evidence."
create_profile qa-reviewer "Independently reviews changes, regression evidence, acceptance criteria, security posture, and release readiness."
create_profile release-manager "Assembles release evidence, checks CI and traceability, coordinates release candidates, and stops at production human gates."

# Enable the portable layer in the default profile too, useful for interactive control.
"$ROOT/scripts/install-local.sh" --profile default

echo
echo "Profiles created and Company Layer installed."
echo "Next: create a board with scripts/create-pilot.sh /absolute/path/to/project"
echo "Then start the gateway: hermes gateway start"
echo "No global Kanban settings were changed. The pilot uses a dispatcher-spawned orchestrator card, so Kanban task tools are injected automatically."
echo "Optional: enable the 'kanban' toolset on the orchestrator profile only if you want interactive orchestrator chats to route board work."
