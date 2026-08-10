#!/usr/bin/env bash
set -euo pipefail

usage() {
  echo "Usage: $0 [--profile orchestrator] [--replace-legacy] BOARD_SLUG" >&2
  exit 2
}

PROFILE="orchestrator"
REPLACE_LEGACY=0
BOARD=""
while [[ $# -gt 0 ]]; do
  case "$1" in
    --profile) [[ $# -ge 2 ]] || usage; PROFILE="$2"; shift 2 ;;
    --replace-legacy) REPLACE_LEGACY=1; shift ;;
    -*) usage ;;
    *) [[ -z "$BOARD" ]] || usage; BOARD="$1"; shift ;;
  esac
done
[[ -n "$BOARD" ]] || usage
PROFILE="$(printf '%s' "$PROFILE" | tr '[:upper:]' '[:lower:]')"
BOARD="$(printf '%s' "$BOARD" | tr '[:upper:]' '[:lower:]')"
if [[ ! "$PROFILE" =~ ^[a-z0-9][a-z0-9_-]{0,63}$ ]]; then
  echo "Invalid Hermes profile slug: $PROFILE" >&2
  exit 2
fi
if [[ ! "$BOARD" =~ ^[a-z0-9][a-z0-9_-]{0,63}$ ]]; then
  echo "Invalid Hermes board slug: $BOARD" >&2
  exit 2
fi

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

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ACTIVE_HOME="$(strip_trailing_slashes "${HERMES_HOME:-$HOME/.hermes}")"
require_safe_root "$ACTIVE_HOME" HERMES_HOME
ACTIVE_PARENT="${ACTIVE_HOME%/*}"
if [[ "${ACTIVE_PARENT##*/}" == "profiles" ]]; then
  SHARED_HOME="${ACTIVE_PARENT%/*}"
else
  SHARED_HOME="$ACTIVE_HOME"
fi
SHARED_HOME="$(canonical_path "$SHARED_HOME")"
require_safe_root "$SHARED_HOME" "shared Hermes home"
KANBAN_HOME="$(canonical_path "$(strip_trailing_slashes "${HERMES_KANBAN_HOME:-$SHARED_HOME}")")"
require_safe_root "$KANBAN_HOME" HERMES_KANBAN_HOME
KANBAN_DB_OVERRIDE="${HERMES_KANBAN_DB:-}"
if [[ -n "${HERMES_KANBAN_TASK:-}" ]]; then
  # A dispatched worker receives a task-specific DB pin; it must not leak into a board installer.
  KANBAN_DB_OVERRIDE=""
  unset HERMES_KANBAN_DB
fi
if [[ -n "$KANBAN_DB_OVERRIDE" && ( "$KANBAN_DB_OVERRIDE" != /* || "$KANBAN_DB_OVERRIDE" == "/" ) ]]; then
  echo "HERMES_KANBAN_DB must be an absolute file path: $KANBAN_DB_OVERRIDE" >&2
  exit 2
fi
if [[ -n "$KANBAN_DB_OVERRIDE" ]]; then
  KANBAN_DB_OVERRIDE="$(canonical_path "$KANBAN_DB_OVERRIDE")"
fi
if [[ -n "$KANBAN_DB_OVERRIDE" ]]; then
  PINNED_DB="$KANBAN_DB_OVERRIDE"
elif [[ "$BOARD" == "default" ]]; then
  PINNED_DB="$KANBAN_HOME/kanban.db"
else
  PINNED_DB="$KANBAN_HOME/kanban/boards/$BOARD/kanban.db"
fi
export HERMES_HOME="$SHARED_HOME"
if ! hermes profile show "$PROFILE" >/dev/null 2>&1; then
  echo "Hermes profile does not exist: $PROFILE" >&2
  exit 1
fi
if [[ "$PROFILE" == "default" ]]; then
  PROFILE_HOME="$SHARED_HOME"
else
  PROFILE_HOME="$SHARED_HOME/profiles/$PROFILE"
fi
PROFILE_HOME="$(canonical_path "$PROFILE_HOME")"
if [[ "$PROFILE_HOME" != "$SHARED_HOME" && "$PROFILE_HOME" != "$SHARED_HOME/"* ]]; then
  echo "Profile home resolves outside shared Hermes home: $PROFILE_HOME" >&2
  exit 2
fi
HERMES_CMD=(hermes -p "$PROFILE")
TARGET="$PROFILE_HOME/scripts"
ENGINE="ttf-${BOARD}-transition-engine.py"
ENGINE_CORE="ttf-${BOARD}-transition-engine-core.py"
JOB_NAME="ttf-${BOARD}-transition-engine"

# Read-only preflight: fail before changing profile files or cron state.
python3 "$ROOT/scripts/kanban-transition-engine.py" --board "$BOARD" --home "$KANBAN_HOME" --check-board >/dev/null

CRON_LIST="$("${HERMES_CMD[@]}" cron list --all)"
cron_jobs_in() {
  printf '%s\n' "$1" | awk -v wanted="$2" '
    /^[[:space:]]*[0-9a-f]+ \[[a-z]+\]$/ {
      id=$1; state=$2; gsub(/\[|\]/, "", state); next
    }
    /^[[:space:]]*Name:/ {
      name=$0; sub(/^[[:space:]]*Name:[[:space:]]*/, "", name)
      if (name == wanted) print id " " state
    }
  '
}

cron_jobs() {
  cron_jobs_in "$CRON_LIST" "$1"
}

LEGACY_IDS=()
LEGACY_NAMES=()
LEGACY_PROFILES=()
PROFILE_NAMES=(default)
[[ "$PROFILE" == "default" ]] || PROFILE_NAMES+=("$PROFILE")
for PROFILE_DIR in "$SHARED_HOME"/profiles/*; do
  [[ -d "$PROFILE_DIR" ]] || continue
  PROFILE_NAME="${PROFILE_DIR##*/}"
  [[ "$PROFILE_NAME" =~ ^[a-z0-9][a-z0-9_-]{0,63}$ ]] || continue
  hermes profile show "$PROFILE_NAME" >/dev/null 2>&1 || continue
  SEEN=0
  for KNOWN_PROFILE in "${PROFILE_NAMES[@]}"; do
    [[ "$KNOWN_PROFILE" == "$PROFILE_NAME" ]] && SEEN=1
  done
  [[ "$SEEN" -eq 1 ]] || PROFILE_NAMES+=("$PROFILE_NAME")
done
for SCAN_PROFILE in "${PROFILE_NAMES[@]}"; do
  if [[ "$SCAN_PROFILE" == "$PROFILE" ]]; then
    SCAN_CRON_LIST="$CRON_LIST"
  else
    SCAN_CRON_LIST="$(hermes -p "$SCAN_PROFILE" cron list --all)"
  fi
  for LEGACY_NAME in \
    "ttf-${BOARD}-handoff-autopilot" \
    "ttf-${BOARD}-graph-governor" \
    "product-factory-${BOARD}-handoff-autopilot" \
    "product-factory-${BOARD}-graph-governor" \
    "${BOARD}-graph-governor" \
    "$JOB_NAME"
  do
    [[ "$LEGACY_NAME" != "$JOB_NAME" || "$SCAN_PROFILE" != "$PROFILE" ]] || continue
    while read -r LEGACY_ID LEGACY_STATE; do
      [[ "$LEGACY_STATE" == "active" ]] || continue
      LEGACY_IDS+=("$LEGACY_ID")
      LEGACY_NAMES+=("$LEGACY_NAME")
      LEGACY_PROFILES+=("$SCAN_PROFILE")
    done < <(cron_jobs_in "$SCAN_CRON_LIST" "$LEGACY_NAME")
  done
done
if [[ ${#LEGACY_IDS[@]} -gt 0 && "$REPLACE_LEGACY" -ne 1 ]]; then
  echo "Active legacy graph automation exists for board '$BOARD'." >&2
  for ((i=0; i<${#LEGACY_IDS[@]}; i++)); do
    echo "  ${LEGACY_PROFILES[$i]}: ${LEGACY_NAMES[$i]} (${LEGACY_IDS[$i]})" >&2
  done
  echo "Migrate every reviewer to structured ttf_review verdicts, then rerun with --replace-legacy." >&2
  exit 1
fi

mkdir -p "$TARGET"
TARGET="$(canonical_path "$TARGET")"
if [[ "$TARGET" != "$PROFILE_HOME/"* ]]; then
  echo "Profile scripts directory resolves outside profile home: $TARGET" >&2
  exit 2
fi
python3 - "$TARGET/$ENGINE" "$TARGET/$ENGINE_CORE" "$ROOT/scripts/kanban-transition-engine.py" \
  "$BOARD" "$KANBAN_HOME" "$PINNED_DB" "$PROFILE" <<'PY'
import os
import sys
import tempfile
from pathlib import Path

wrapper, core, source = map(Path, sys.argv[1:4])
board, kanban_home, kanban_db, owner_profile = sys.argv[4:8]

def atomic_write(path: Path, data: bytes) -> None:
    fd, temporary = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.")
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temporary, 0o755)
        os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)

atomic_write(core, source.read_bytes())
wrapper_source = (
    "#!/usr/bin/env python3\nimport os, subprocess, sys\n"
    "for key in ('HERMES_KANBAN_TASK', 'HERMES_KANBAN_RUN_ID', 'HERMES_KANBAN_CLAIM_LOCK', 'HERMES_KANBAN_WORKSPACE'):\n    os.environ.pop(key, None)\n"
    f"os.environ['HERMES_KANBAN_HOME'] = {kanban_home!r}\n"
    f"os.environ['HERMES_KANBAN_DB'] = {kanban_db!r}\n"
    f"raise SystemExit(subprocess.run([sys.executable, {str(core)!r}, '--board', {board!r}, '--home', {kanban_home!r}, '--owner-profile', {owner_profile!r}]).returncode)\n"
)
atomic_write(wrapper, wrapper_source.encode())
PY

JOB_INFO="$(cron_jobs "$JOB_NAME")"
CURRENT_WAS_ACTIVE=0
JOB_ID=""
if [[ -n "$JOB_INFO" ]]; then
  CANONICAL_JOB="$(printf '%s\n' "$JOB_INFO" | awk '
    NR == 1 { fallback=$0 }
    $2 == "active" { print; found=1; exit }
    END { if (!found) print fallback }
  ')"
  JOB_ID="${CANONICAL_JOB%% *}"
  JOB_STATE="${CANONICAL_JOB#* }"
  [[ "$JOB_STATE" != "active" ]] || CURRENT_WAS_ACTIVE=1
  "${HERMES_CMD[@]}" cron edit "$JOB_ID" --schedule 'every 1m' --script "$ENGINE" \
    --no-agent --repeat 0 --monitor-script '' --monitor-url ''
  if [[ "$JOB_STATE" != "active" ]]; then
    "${HERMES_CMD[@]}" cron resume "$JOB_ID"
  fi
else
  CREATE_OUTPUT="$(NO_COLOR=1 "${HERMES_CMD[@]}" cron create --name "$JOB_NAME" --script "$ENGINE" --no-agent --repeat 0 'every 1m')"
  printf '%s\n' "$CREATE_OUTPUT"
  JOB_ID="$(printf '%s\n' "$CREATE_OUTPUT" | sed -n 's/.*Created job:[[:space:]]*//p' | tail -1)"
fi

rollback_replacement_activation() {
  if [[ "$CURRENT_WAS_ACTIVE" -ne 1 && -n "$JOB_ID" ]]; then
    "${HERMES_CMD[@]}" cron pause "$JOB_ID" >/dev/null 2>&1 || true
  fi
}
if ! UPDATED_CRON_LIST="$("${HERMES_CMD[@]}" cron list --all)"; then
  rollback_replacement_activation
  echo "Could not verify the transition cron; legacy jobs were left unchanged." >&2
  exit 1
fi
ACTIVE_CURRENT="$(cron_jobs_in "$UPDATED_CRON_LIST" "$JOB_NAME" | awk '$2 == "active"')"
if [[ -z "$ACTIVE_CURRENT" ]]; then
  rollback_replacement_activation
  echo "Transition cron was not active after installation; legacy jobs were left unchanged." >&2
  exit 1
fi
CURRENT_KEEP_ID="${ACTIVE_CURRENT%% *}"
CURRENT_EXTRA_IDS=()
while read -r EXTRA_ID EXTRA_STATE; do
  [[ "$EXTRA_STATE" != "active" || "$EXTRA_ID" == "$CURRENT_KEEP_ID" ]] || CURRENT_EXTRA_IDS+=("$EXTRA_ID")
done <<< "$ACTIVE_CURRENT"
PAUSED_LEGACY_INDEXES=()
restore_previous_jobs() {
  if (( ${#PAUSED_LEGACY_INDEXES[@]} )); then
    for PAUSED_INDEX in "${PAUSED_LEGACY_INDEXES[@]}"; do
      hermes -p "${LEGACY_PROFILES[$PAUSED_INDEX]}" cron resume "${LEGACY_IDS[$PAUSED_INDEX]}" >/dev/null 2>&1 || true
    done
  fi
  if (( ${#CURRENT_EXTRA_IDS[@]} )); then
    for EXTRA_ID in "${CURRENT_EXTRA_IDS[@]}"; do
      "${HERMES_CMD[@]}" cron resume "$EXTRA_ID" >/dev/null 2>&1 || true
    done
  fi
  if [[ "$CURRENT_WAS_ACTIVE" -ne 1 ]]; then
    "${HERMES_CMD[@]}" cron pause "$CURRENT_KEEP_ID" >/dev/null 2>&1 || true
  fi
}
if (( ${#CURRENT_EXTRA_IDS[@]} )); then
  for EXTRA_ID in "${CURRENT_EXTRA_IDS[@]}"; do
    if ! "${HERMES_CMD[@]}" cron pause "$EXTRA_ID"; then
      restore_previous_jobs
      echo "Failed to converge duplicate transition jobs; legacy jobs were left unchanged." >&2
      exit 1
    fi
  done
fi

# The replacement is active; now remove every other graph owner without risking an automation outage.
for ((i=0; i<${#LEGACY_IDS[@]}; i++)); do
  if hermes -p "${LEGACY_PROFILES[$i]}" cron pause "${LEGACY_IDS[$i]}"; then
    PAUSED_LEGACY_INDEXES+=("$i")
    echo "Paused legacy job: ${LEGACY_PROFILES[$i]}:${LEGACY_NAMES[$i]}"
    continue
  fi
  echo "Failed to pause legacy job; restoring the previous active-job state." >&2
  hermes -p "${LEGACY_PROFILES[$i]}" cron resume "${LEGACY_IDS[$i]}" >/dev/null 2>&1 || true
  restore_previous_jobs
  exit 1
done

echo "Transition engine enabled for board: $BOARD (profile: $PROFILE)"
