#!/usr/bin/env bash
set -euo pipefail

PROFILE="orchestrator"
if [[ "${1:-}" == "--profile" ]]; then
  PROFILE="${2:-}"
  shift 2
fi
BOARD="${1:-}"
test -n "$BOARD" || { echo "Usage: $0 [--profile orchestrator] BOARD_SLUG"; exit 2; }
case "$BOARD" in *[!a-zA-Z0-9_-]*|"") echo "Invalid board slug: $BOARD"; exit 2 ;; esac

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SHARED_HOME="${HERMES_HOME:-$HOME/.hermes}"
if [[ "$PROFILE" == "default" ]]; then
  PROFILE_HOME="$SHARED_HOME"
  HERMES_CMD=(hermes)
else
  PROFILE_HOME="$SHARED_HOME/profiles/$PROFILE"
  HERMES_CMD=(hermes -p "$PROFILE")
fi
TARGET="$PROFILE_HOME/scripts"
HANDOFF="ttf-${BOARD}-handoff-autopilot.py"
SNAPSHOT="ttf-${BOARD}-kanban-snapshot.py"

mkdir -p "$TARGET"
cp "$ROOT/scripts/kanban-handoff-autopilot.py" "$TARGET/kanban-handoff-autopilot.py"
cp "$ROOT/scripts/kanban-state-snapshot.py" "$TARGET/kanban-state-snapshot.py"
"${HERMES_CMD[@]}" tools enable kanban >/dev/null
python3 - "$TARGET/$HANDOFF" "$TARGET/kanban-handoff-autopilot.py" "$TARGET/$SNAPSHOT" "$TARGET/kanban-state-snapshot.py" "$BOARD" "$SHARED_HOME" <<'PY'
import sys
from pathlib import Path

handoff, handoff_source, snapshot, snapshot_source = map(Path, sys.argv[1:5])
board, shared_home = sys.argv[5:7]
for wrapper, source in ((handoff, handoff_source), (snapshot, snapshot_source)):
    wrapper.write_text(
        "#!/usr/bin/env python3\nimport subprocess\n"
        f"raise SystemExit(subprocess.run(['python3', {str(source)!r}, '--board', {board!r}, '--home', {shared_home!r}]).returncode)\n",
        encoding="utf-8",
    )
    wrapper.chmod(0o755)
PY

if ! "${HERMES_CMD[@]}" cron list | grep -q "ttf-${BOARD}-handoff-autopilot"; then
  "${HERMES_CMD[@]}" cron create --name "ttf-${BOARD}-handoff-autopilot" --script "$HANDOFF" --no-agent 'every 1m'
fi
if ! "${HERMES_CMD[@]}" cron list | grep -q "ttf-${BOARD}-graph-governor"; then
  "${HERMES_CMD[@]}" cron create --name "ttf-${BOARD}-graph-governor" --monitor-script "$SNAPSHOT" 'every 1m' "Act as the autonomous governor for Hermes Kanban board $BOARD. Inspect the board only when its monitor changes. Before every mutating action call ttf_policy_check and honor every human_approval or forbidden result; never narrow or override Company Policy. Advance ordinary delivery without asking the operator: verified producer review-required handoffs go to their pre-created independent reviewer; reviewer REQUEST_CHANGES creates one bounded remediation plus reviewer pair; preserve historical failures as archived evidence. Do not bypass independent review. Never deploy, push main, use real data, or expose credentials. Stop at UAT-ready Release Candidate with release evidence."
fi

echo "Autopilot enabled for board: $BOARD (profile: $PROFILE)"
