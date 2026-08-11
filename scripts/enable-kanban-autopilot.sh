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
PINNED_DB="$(canonical_path "$PINNED_DB")"
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
HERMES_INSTALL_DIR="$(hermes --version 2>/dev/null | sed -n 's/^Install directory:[[:space:]]*//p' | head -1 || true)"
HERMES_RUNTIME_PYTHON="${HERMES_PYTHON:-}"
if [[ -z "$HERMES_RUNTIME_PYTHON" && -n "$HERMES_INSTALL_DIR" ]]; then
  HERMES_RUNTIME_PYTHON="$HERMES_INSTALL_DIR/venv/bin/python3"
fi
TARGET="$PROFILE_HOME/scripts"
ENGINE="ttf-${BOARD}-transition-engine.py"
ENGINE_CORE="ttf-${BOARD}-transition-engine-core.py"
JOB_NAME="ttf-${BOARD}-transition-engine"

# Read-only preflight: fail before changing profile files or cron state.
python3 "$ROOT/scripts/kanban-transition-engine.py" --board "$BOARD" --home "$KANBAN_HOME" --check-board >/dev/null

INSTALL_LOCK="${PINNED_DB}.ttf-install.lock"
exec 9>"$INSTALL_LOCK"
if ! python3 - 9 <<'PY'
import fcntl
import sys

try:
    fcntl.flock(int(sys.argv[1]), fcntl.LOCK_EX | fcntl.LOCK_NB)
except BlockingIOError:
    raise SystemExit(1)
PY
then
  echo "Another transition-engine install is already running for $PROFILE/$BOARD." >&2
  exit 1
fi

INSTALL_CHILD=""
PENDING_SIGNAL=""
PENDING_STATUS=""
forward_install_signal() {
  local signal="$1" status="$2"
  if [[ -z "$INSTALL_CHILD" ]]; then
    PENDING_SIGNAL="$signal"
    PENDING_STATUS="$status"
    return
  fi
  trap '' HUP INT TERM
  kill -s "$signal" "$INSTALL_CHILD" 2>/dev/null || true
  wait "$INSTALL_CHILD" 2>/dev/null || true
  exit "$status"
}
trap 'forward_install_signal HUP 129' HUP
trap 'forward_install_signal INT 130' INT
trap 'forward_install_signal TERM 143' TERM

(
exec 9>&-

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

JOB_INFO="$(cron_jobs "$JOB_NAME")"
CURRENT_WAS_ACTIVE=0
JOB_ID=""
JOB_STATE=""
ORIGINAL_ACTIVE_JOB_IDS=()
if [[ -n "$JOB_INFO" ]]; then
  CANONICAL_JOB="$(printf '%s\n' "$JOB_INFO" | awk '
    NR == 1 { fallback=$0 }
    $2 == "active" { print; found=1; exit }
    END { if (!found) print fallback }
  ')"
  JOB_ID="${CANONICAL_JOB%% *}"
  JOB_STATE="${CANONICAL_JOB#* }"
  [[ "$JOB_STATE" != "active" ]] || CURRENT_WAS_ACTIVE=1
  while read -r CURRENT_ID CURRENT_STATE; do
    [[ "$CURRENT_STATE" != "active" ]] || ORIGINAL_ACTIVE_JOB_IDS+=("$CURRENT_ID")
  done <<< "$JOB_INFO"
fi

mkdir -p "$TARGET"
TARGET="$(canonical_path "$TARGET")"
if [[ "$TARGET" != "$PROFILE_HOME/"* ]]; then
  echo "Profile scripts directory resolves outside profile home: $TARGET" >&2
  exit 2
fi
ENGINE_PATH="$TARGET/$ENGINE"
ENGINE_CORE_PATH="$TARGET/$ENGINE_CORE"
ROLLBACK_DIR="$(mktemp -d "$TARGET/.ttf-${BOARD}-engine-rollback.XXXXXX")"
CREATE_NAME="${JOB_NAME}-install-${ROLLBACK_DIR##*.}"
ENGINE_FILES_COMMITTED=0
CRON_MUTATION_STARTED=0
CRON_SNAPSHOT="$ROLLBACK_DIR/cron-definition.json"
CRON_MUTATION_MARKER="$ROLLBACK_DIR/cron-mutated"
CRON_ACTIVATION="$ROLLBACK_DIR/cron-activation.json"
CRON_RUNTIME="$ROLLBACK_DIR/cron-runtime.json"
PAUSED_JOB_PROFILES=()
PAUSED_JOB_IDS=()
PAUSED_JOB_NAMES=()
PAUSED_JOB_HOMES=()

run_cron_transaction() {
  python3 - "$@" <<'PY'
import copy
import contextlib
import fcntl
import json
import os
import stat
import sys
import tempfile
import time
from datetime import datetime, timedelta
from pathlib import Path

mode = sys.argv[1]
jobs_path = Path(sys.argv[2])
job_id = sys.argv[3]
snapshot_path = Path(sys.argv[4])
mutation_marker = Path(sys.argv[5])
activation_path = Path(sys.argv[6])
runtime_path = Path(sys.argv[7])
lock_path = jobs_path.parent / ".jobs.lock"
lock_path.parent.mkdir(parents=True, exist_ok=True)

def load_store():
    raw = jobs_path.read_text(encoding="utf-8-sig")
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        payload = json.loads(raw, strict=False)
    jobs = payload.get("jobs", []) if isinstance(payload, dict) else payload
    if not isinstance(jobs, list):
        raise SystemExit("cron jobs store has an invalid shape")
    matches = [i for i, job in enumerate(jobs) if isinstance(job, dict) and job.get("id") == job_id]
    if len(matches) != 1:
        raise SystemExit(f"expected one cron job {job_id}, found {len(matches)}")
    return payload, jobs, matches[0]

def atomic_json(path, payload, mode_bits=None, owner=None):
    fd, temporary = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.restore.")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2, ensure_ascii=False)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temporary, 0o600 if mode_bits is None else mode_bits)
        if owner is not None:
            with contextlib.suppress(PermissionError, OSError):
                os.chown(temporary, *owner)
        os.replace(temporary, path)
        temporary = None
        directory = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        if temporary is not None:
            Path(temporary).unlink(missing_ok=True)

def restore_field(target, source, field):
    if field in source:
        target[field] = copy.deepcopy(source[field])
    else:
        target.pop(field, None)

definition_fields = {
    "name", "schedule", "schedule_display", "script", "no_agent",
    "monitor_script", "monitor_url", "provider_snapshot",
    "model_snapshot", "skill", "skills",
}
lifecycle_fields = {"enabled", "state", "paused_at", "paused_reason", "next_run_at"}
controlled = definition_fields | lifecycle_fields | {"repeat"}

def runtime_view(record):
    view = {key: value for key, value in record.items() if key not in controlled}
    repeat = copy.deepcopy(record.get("repeat"))
    if isinstance(repeat, dict):
        repeat.pop("times", None)
    view["repeat_runtime"] = repeat
    return view

def activation_point(record):
    return {
        "present": "next_run_at" in record,
        "value": copy.deepcopy(record.get("next_run_at")),
        "runtime": runtime_view(record),
    }

with lock_path.open("a+") as lock:
    deadline = time.monotonic() + 30
    while True:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            break
        except BlockingIOError:
            if time.monotonic() >= deadline:
                raise SystemExit("timed out waiting for the cron jobs lock")
            time.sleep(0.1)
    try:
        payload, jobs, index = load_store()
        current = jobs_path.stat()
        job = jobs[index]
        if mode == "snapshot":
            atomic_json(snapshot_path, job)
            if job.get("state") != "paused" or not job.get("paused_at"):
                mutation_marker.write_text("parked\n", encoding="utf-8")
                with mutation_marker.open("r+") as marker:
                    marker.flush()
                    os.fsync(marker.fileno())
                job["enabled"] = False
                job["state"] = "paused"
                job["paused_at"] = datetime.now().astimezone().isoformat()
                job["paused_reason"] = "thinktofinish transition-engine upgrade"
                atomic_json(
                    jobs_path,
                    payload,
                    stat.S_IMODE(current.st_mode),
                    (current.st_uid, current.st_gid),
                )
        elif mode == "activate":
            before = activation_point(job)
            job["enabled"] = True
            job["state"] = "scheduled"
            job["paused_at"] = None
            job["paused_reason"] = None
            job["next_run_at"] = (datetime.now().astimezone() + timedelta(minutes=1)).isoformat()
            # Write-ahead provenance makes a later scheduler-only next_run update
            # distinguishable from the activation value even if this process dies.
            atomic_json(
                activation_path,
                {"before": before, "after": activation_point(job)},
            )
            atomic_json(
                jobs_path,
                payload,
                stat.S_IMODE(current.st_mode),
                (current.st_uid, current.st_gid),
            )
        elif mode == "rollback-park":
            if not runtime_path.exists():
                atomic_json(runtime_path, job)
            if activation_path.exists():
                activation = json.loads(activation_path.read_text(encoding="utf-8"))
                if "after" not in activation:
                    activation["after"] = activation_point(job)
                    atomic_json(activation_path, activation)
            job["enabled"] = False
            job["state"] = "paused"
            job["paused_at"] = datetime.now().astimezone().isoformat()
            job["paused_reason"] = "thinktofinish transition-engine rollback"
            atomic_json(
                jobs_path,
                payload,
                stat.S_IMODE(current.st_mode),
                (current.st_uid, current.st_gid),
            )
        elif mode == "restore":
            snapshot = json.loads(snapshot_path.read_text(encoding="utf-8"))
            captured = (
                json.loads(runtime_path.read_text(encoding="utf-8"))
                if runtime_path.exists()
                else job
            )
            runtime_changed = runtime_view(job) != runtime_view(snapshot)
            for field in definition_fields:
                restore_field(job, snapshot, field)

            current_repeat = copy.deepcopy(job.get("repeat"))
            snapshot_repeat = copy.deepcopy(snapshot.get("repeat"))
            if isinstance(current_repeat, dict):
                if isinstance(snapshot_repeat, dict) and "times" in snapshot_repeat:
                    current_repeat["times"] = snapshot_repeat["times"]
                else:
                    current_repeat.pop("times", None)
                if current_repeat:
                    job["repeat"] = current_repeat
                elif "repeat" in snapshot:
                    job["repeat"] = snapshot_repeat
                else:
                    job.pop("repeat", None)
            else:
                restore_field(job, snapshot, "repeat")

            repeat = job.get("repeat")
            snapshot_completed = (
                snapshot_repeat.get("completed", 0)
                if isinstance(snapshot_repeat, dict)
                else 0
            )
            exhausted = (
                isinstance(repeat, dict)
                and isinstance(repeat.get("times"), int)
                and repeat["times"] > 0
                and isinstance(repeat.get("completed"), int)
                and repeat["completed"] > snapshot_completed
                and repeat["completed"] >= repeat["times"]
            )
            terminal_source = job if job.get("state") in {"completed", "error"} else captured
            terminal_progress = exhausted or (
                runtime_changed and terminal_source.get("state") in {"completed", "error"}
            )
            for field in {"paused_at", "paused_reason"}:
                restore_field(job, snapshot, field)
            if not terminal_progress:
                for field in {"enabled", "state"}:
                    restore_field(job, snapshot, field)
            elif not exhausted:
                restore_field(job, terminal_source, "state")
                restore_field(
                    job,
                    snapshot if terminal_source.get("state") == "error" else terminal_source,
                    "enabled",
                )
            if activation_path.exists():
                activation = json.loads(activation_path.read_text(encoding="utf-8"))
                before = activation.get("before")
                after = activation.get("after")
                current_next = {
                    "present": "next_run_at" in job,
                    "value": copy.deepcopy(job.get("next_run_at")),
                }
                after_next = (
                    {"present": after["present"], "value": after["value"]}
                    if after is not None
                    else None
                )
                restore_before = (
                    before
                    and (
                        (
                            after is not None
                            and current_next == after_next
                            and before.get("runtime") == after.get("runtime")
                        )
                        or (after is None and not runtime_changed)
                    )
                )
                if restore_before:
                    if before["present"]:
                        job["next_run_at"] = before["value"]
                    else:
                        job.pop("next_run_at", None)
            if exhausted:
                job["enabled"] = False
                job["state"] = "completed"
                job["next_run_at"] = None

            atomic_json(
                jobs_path,
                payload,
                stat.S_IMODE(current.st_mode),
                (current.st_uid, current.st_gid),
            )
        else:
            raise SystemExit(f"unknown cron transaction mode: {mode}")
    finally:
        fcntl.flock(lock, fcntl.LOCK_UN)
PY
}

cron_job_transaction() {
  run_cron_transaction "$1" "$PROFILE_HOME/cron/jobs.json" "$JOB_ID" \
    "$CRON_SNAPSHOT" "$CRON_MUTATION_MARKER" "$CRON_ACTIVATION" "$CRON_RUNTIME"
}

snapshot_cron_definition() { cron_job_transaction snapshot; }
restore_cron_definition() { cron_job_transaction restore; }
activate_cron() { cron_job_transaction activate; }
park_cron_for_rollback() { cron_job_transaction rollback-park; }

pause_managed_job() {
  local profile="$1" id="$2" name="$3" home index base
  if [[ "$profile" == "default" ]]; then home="$SHARED_HOME"; else home="$SHARED_HOME/profiles/$profile"; fi
  index="${#PAUSED_JOB_IDS[@]}"
  base="$ROLLBACK_DIR/paused-$index"
  PAUSED_JOB_PROFILES+=("$profile")
  PAUSED_JOB_IDS+=("$id")
  PAUSED_JOB_NAMES+=("$name")
  PAUSED_JOB_HOMES+=("$home")
  run_cron_transaction snapshot "$home/cron/jobs.json" "$id" \
    "$base-definition.json" "$base-mutated" "$base-activation.json" "$base-runtime.json" || return 1
  notify_cron_provider "$profile" || return 1
}

notify_cron_provider() {
  local profile="$1" home status
  if [[ "$profile" == "default" ]]; then home="$SHARED_HOME"; else home="$SHARED_HOME/profiles/$profile"; fi
  if [[ -n "$HERMES_RUNTIME_PYTHON" && -x "$HERMES_RUNTIME_PYTHON" ]]; then
    (
      unset PYTHONHOME PYTHONPATH
      export HERMES_HOME="$home" HERMES_PROFILE="$profile" HERMES_PROFILE_NAME="$profile"
      "$HERMES_RUNTIME_PYTHON" -c \
        'from cron.scheduler import _notify_provider_jobs_changed; _notify_provider_jobs_changed()'
    )
    return
  fi
  status="$(hermes -p "$profile" cron status 2>/dev/null)" || return 1
  if printf '%s\n' "$status" | grep -q 'Cron provider:'; then
    echo "Cannot notify the external cron provider: Hermes runtime Python was not found." >&2
    return 1
  fi
}

finish_engine_files() {
  local status=$?
  local rollback_failed=0
  local cron_cleanup_needed=0
  [[ "$CRON_MUTATION_STARTED" -eq 0 && ! -f "$CRON_MUTATION_MARKER" ]] || cron_cleanup_needed=1
  trap - EXIT
  trap '' HUP INT TERM
  set +e
  if [[ "$ENGINE_FILES_COMMITTED" -ne 1 && "$cron_cleanup_needed" -eq 1 ]]; then
    if [[ -n "$JOB_ID" && -f "$CRON_SNAPSHOT" ]]; then
      if ! park_cron_for_rollback; then
        rollback_failed=1
        "${HERMES_CMD[@]}" cron pause "$JOB_ID" >/dev/null 2>&1 || rollback_failed=1
      elif ! notify_cron_provider "$PROFILE" >/dev/null 2>&1; then
        rollback_failed=1
      fi
    elif [[ -n "$JOB_ID" ]]; then
      "${HERMES_CMD[@]}" cron pause "$JOB_ID" >/dev/null 2>&1 || rollback_failed=1
    fi
    if [[ -z "$JOB_INFO" ]]; then
      if ROLLBACK_CRON_LIST="$("${HERMES_CMD[@]}" cron list --all)"; then
        while read -r CURRENT_ID CURRENT_STATE; do
          [[ "$CURRENT_STATE" == "active" ]] || continue
          "${HERMES_CMD[@]}" cron pause "$CURRENT_ID" >/dev/null 2>&1 || rollback_failed=1
        done < <(cron_jobs_in "$ROLLBACK_CRON_LIST" "$CREATE_NAME")
      else
        rollback_failed=1
      fi
    fi
  fi
  if ! python3 - "$ENGINE_PATH" "$ENGINE_CORE_PATH" "$ROLLBACK_DIR" "$ENGINE_FILES_COMMITTED" <<'PY'
import os
import shutil
import sys
from pathlib import Path

wrapper, core, rollback = map(Path, sys.argv[1:4])
committed = sys.argv[4] == "1"
if rollback.exists():
    if not committed and (rollback / "ready").exists():
        for path, name in ((core, "core"), (wrapper, "wrapper")):
            backup = rollback / name
            if (rollback / f"{name}.existed").exists():
                os.replace(backup, path)
            else:
                path.unlink(missing_ok=True)
PY
  then
    echo "Failed to restore the previous transition engine files." >&2
    rollback_failed=1
  fi
  if [[ "$ENGINE_FILES_COMMITTED" -ne 1 && "$cron_cleanup_needed" -eq 1 && -f "$CRON_SNAPSHOT" ]]; then
    restore_failed=0
    restore_cron_definition || restore_failed=1
    notify_cron_provider "$PROFILE" >/dev/null 2>&1 || restore_failed=1
    if [[ "$restore_failed" -ne 0 ]]; then
      echo "Failed to restore the previous transition cron definition; inspect the retained snapshot." >&2
      rollback_failed=1
    fi
  fi
  if [[ "$ENGINE_FILES_COMMITTED" -ne 1 && "$cron_cleanup_needed" -eq 1 ]]; then
    for ((PAUSED_INDEX=0; PAUSED_INDEX<${#PAUSED_JOB_IDS[@]}; PAUSED_INDEX++)); do
      PAUSED_BASE="$ROLLBACK_DIR/paused-$PAUSED_INDEX"
      [[ -f "$PAUSED_BASE-definition.json" ]] || continue
      PAUSED_RESTORE_FAILED=0
      run_cron_transaction rollback-park \
        "${PAUSED_JOB_HOMES[$PAUSED_INDEX]}/cron/jobs.json" \
        "${PAUSED_JOB_IDS[$PAUSED_INDEX]}" \
        "$PAUSED_BASE-definition.json" "$PAUSED_BASE-mutated" \
        "$PAUSED_BASE-activation.json" "$PAUSED_BASE-runtime.json" \
        || PAUSED_RESTORE_FAILED=1
      notify_cron_provider "${PAUSED_JOB_PROFILES[$PAUSED_INDEX]}" \
        >/dev/null 2>&1 || PAUSED_RESTORE_FAILED=1
      run_cron_transaction restore \
        "${PAUSED_JOB_HOMES[$PAUSED_INDEX]}/cron/jobs.json" \
        "${PAUSED_JOB_IDS[$PAUSED_INDEX]}" \
        "$PAUSED_BASE-definition.json" "$PAUSED_BASE-mutated" \
        "$PAUSED_BASE-activation.json" "$PAUSED_BASE-runtime.json" \
        || PAUSED_RESTORE_FAILED=1
      notify_cron_provider "${PAUSED_JOB_PROFILES[$PAUSED_INDEX]}" \
        >/dev/null 2>&1 || PAUSED_RESTORE_FAILED=1
      [[ "$PAUSED_RESTORE_FAILED" -eq 0 ]] || rollback_failed=1
    done
  fi
  if [[ "$rollback_failed" -eq 0 || "$ENGINE_FILES_COMMITTED" -eq 1 ]]; then
    if ! python3 -c 'import shutil,sys; shutil.rmtree(sys.argv[1])' "$ROLLBACK_DIR"; then
      echo "Failed to remove cron rollback data: $ROLLBACK_DIR" >&2
      rollback_failed=1
    fi
  else
    echo "Rollback evidence retained at: $ROLLBACK_DIR" >&2
  fi
  [[ "$rollback_failed" -eq 0 ]] || status=1
  exit "$status"
}
trap finish_engine_files EXIT
trap 'exit 129' HUP
trap 'exit 130' INT
trap 'exit 143' TERM

if [[ -n "$JOB_INFO" ]] && ! snapshot_cron_definition; then
  echo "Could not snapshot the existing transition cron; no changes were made." >&2
  exit 1
fi
if [[ -f "$CRON_MUTATION_MARKER" ]]; then
  CRON_MUTATION_STARTED=1
  if ! notify_cron_provider "$PROFILE" >/dev/null; then
    echo "Could not park the active transition cron before staging its engine." >&2
    exit 1
  fi
fi

if (( ${#ORIGINAL_ACTIVE_JOB_IDS[@]} )); then
  for CURRENT_ID in "${ORIGINAL_ACTIVE_JOB_IDS[@]}"; do
    [[ "$CURRENT_ID" == "$JOB_ID" ]] && continue
    CRON_MUTATION_STARTED=1
    if ! pause_managed_job "$PROFILE" "$CURRENT_ID" "$JOB_NAME"; then
      echo "Could not pause the active transition job before staging its engine." >&2
      exit 1
    fi
  done
fi

if ! python3 - "$ENGINE_PATH" "$ENGINE_CORE_PATH" "$ROOT/scripts/kanban-transition-engine.py" \
  "$BOARD" "$KANBAN_HOME" "$PINNED_DB" "$PROFILE" "$ROLLBACK_DIR" <<'PY'
import os
import shutil
import sys
import tempfile
from pathlib import Path

wrapper, core, source = map(Path, sys.argv[1:4])
board, kanban_home, kanban_db, owner_profile = sys.argv[4:8]
rollback = Path(sys.argv[8])

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

targets = ((core, "core"), (wrapper, "wrapper"))
existed = {name: os.path.lexists(path) for path, name in targets}
for path, name in targets:
    if existed[name]:
        shutil.copy2(path, rollback / name, follow_symlinks=False)
        (rollback / f"{name}.existed").touch()
(rollback / "ready").touch()
wrapper_source = (
    "#!/usr/bin/env python3\nimport os, subprocess, sys\n"
    "for key in ('HERMES_KANBAN_TASK', 'HERMES_KANBAN_RUN_ID', 'HERMES_KANBAN_CLAIM_LOCK', 'HERMES_KANBAN_WORKSPACE'):\n    os.environ.pop(key, None)\n"
    f"os.environ['HERMES_KANBAN_HOME'] = {kanban_home!r}\n"
    f"os.environ['HERMES_KANBAN_DB'] = {kanban_db!r}\n"
    f"raise SystemExit(subprocess.run([sys.executable, {str(core)!r}, '--board', {board!r}, '--home', {kanban_home!r}, '--owner-profile', {owner_profile!r}]).returncode)\n"
)
atomic_write(core, source.read_bytes())
atomic_write(wrapper, wrapper_source.encode())
PY
then
  echo "Could not stage the board-specific transition engine; previous files were preserved." >&2
  exit 1
fi
if [[ -n "$JOB_INFO" ]]; then
  CRON_MUTATION_STARTED=1
  "${HERMES_CMD[@]}" cron edit "$JOB_ID" --schedule 'every 1m' --script "$ENGINE" \
    --no-agent --repeat 0 --monitor-script '' --monitor-url ''
fi

# Stop every legacy graph owner before the replacement activation boundary.
for ((i=0; i<${#LEGACY_IDS[@]}; i++)); do
  CRON_MUTATION_STARTED=1
  if pause_managed_job "${LEGACY_PROFILES[$i]}" "${LEGACY_IDS[$i]}" "${LEGACY_NAMES[$i]}"; then
    echo "Paused legacy job: ${LEGACY_PROFILES[$i]}:${LEGACY_NAMES[$i]}"
    continue
  fi
  echo "Failed to pause legacy job; restoring the previous active-job state." >&2
  exit 1
done

if [[ -n "$JOB_INFO" ]]; then
  CRON_MUTATION_STARTED=1
  activate_cron
  if ! notify_cron_provider "$PROFILE" >/dev/null; then
    echo "Could not activate the transition cron provider." >&2
    exit 1
  fi
else
  CRON_MUTATION_STARTED=1
  CREATE_OUTPUT="$(NO_COLOR=1 "${HERMES_CMD[@]}" cron create --name "$CREATE_NAME" --script "$ENGINE" --no-agent --repeat 0 'every 1m')"
  printf '%s\n' "$CREATE_OUTPUT"
  JOB_ID="$(printf '%s\n' "$CREATE_OUTPUT" | sed -n 's/.*Created job:[[:space:]]*//p' | tail -1)"
  if [[ ! "$JOB_ID" =~ ^[0-9a-f]+$ ]]; then
    echo "Hermes cron create did not return a valid job ID." >&2
    exit 1
  fi
  "${HERMES_CMD[@]}" cron edit "$JOB_ID" --name "$JOB_NAME"
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
if ! printf '%s\n' "$ACTIVE_CURRENT" | awk -v id="$JOB_ID" '$1 == id { found=1 } END { exit !found }'; then
  rollback_replacement_activation
  echo "Transition cron was not active after installation; legacy jobs were left unchanged." >&2
  exit 1
fi
CURRENT_KEEP_ID="$JOB_ID"
CURRENT_EXTRA_IDS=()
while read -r EXTRA_ID EXTRA_STATE; do
  [[ "$EXTRA_STATE" != "active" || "$EXTRA_ID" == "$CURRENT_KEEP_ID" ]] || CURRENT_EXTRA_IDS+=("$EXTRA_ID")
done <<< "$ACTIVE_CURRENT"
if (( ${#CURRENT_EXTRA_IDS[@]} )); then
  for EXTRA_ID in "${CURRENT_EXTRA_IDS[@]}"; do
    if ! pause_managed_job "$PROFILE" "$EXTRA_ID" "$JOB_NAME"; then
      echo "Failed to converge duplicate transition jobs; legacy jobs were left unchanged." >&2
      exit 1
    fi
  done
fi

ENGINE_FILES_COMMITTED=1
echo "Transition engine enabled for board: $BOARD (profile: $PROFILE)"
) &
INSTALL_CHILD=$!
[[ -z "$PENDING_SIGNAL" ]] || forward_install_signal "$PENDING_SIGNAL" "$PENDING_STATUS"
if wait "$INSTALL_CHILD"; then INSTALL_STATUS=0; else INSTALL_STATUS=$?; fi
trap - HUP INT TERM
exit "$INSTALL_STATUS"
