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
ENGINE="ttf-${BOARD}-transition-engine.py"

mkdir -p "$TARGET"
cp "$ROOT/scripts/kanban-transition-engine.py" "$TARGET/kanban-transition-engine.py"
"${HERMES_CMD[@]}" tools enable kanban >/dev/null
python3 - "$TARGET/$ENGINE" "$TARGET/kanban-transition-engine.py" "$BOARD" "$SHARED_HOME" <<'PY'
import sys
from pathlib import Path

wrapper, source = map(Path, sys.argv[1:3])
board, shared_home = sys.argv[3:5]
wrapper.write_text(
    "#!/usr/bin/env python3\nimport subprocess\n"
    f"raise SystemExit(subprocess.run(['python3', {str(source)!r}, '--board', {board!r}, '--home', {shared_home!r}]).returncode)\n",
    encoding="utf-8",
)
wrapper.chmod(0o755)
PY

if ! "${HERMES_CMD[@]}" cron list | grep -q "ttf-${BOARD}-transition-engine"; then
  "${HERMES_CMD[@]}" cron create --name "ttf-${BOARD}-transition-engine" --script "$ENGINE" --no-agent 'every 1m'
fi

echo "Transition engine enabled for board: $BOARD (profile: $PROFILE)"
