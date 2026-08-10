#!/usr/bin/env bash
set -euo pipefail

PROFILE="default"
SOURCE="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --profile) [[ $# -ge 2 ]] || { echo "--profile requires a value" >&2; exit 2; }; PROFILE="$2"; shift 2 ;;
    *) echo "Unknown argument: $1" >&2; exit 2 ;;
  esac
done

if ! command -v hermes >/dev/null 2>&1; then
  echo "Hermes CLI not found on PATH." >&2
  exit 1
fi

PROFILE="$(printf '%s' "$PROFILE" | tr '[:upper:]' '[:lower:]')"
if [[ ! "$PROFILE" =~ ^[a-z0-9][a-z0-9_-]{0,63}$ ]]; then
  echo "Invalid Hermes profile slug: $PROFILE" >&2
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
if ! hermes profile show "$PROFILE" >/dev/null 2>&1; then
  echo "Hermes profile does not exist: $PROFILE" >&2
  exit 1
fi
if [[ "$PROFILE" == "default" ]]; then
  HROOT="$SHARED_HOME"
else
  HROOT="$SHARED_HOME/profiles/$PROFILE"
fi
HROOT="$(canonical_path "$HROOT")"
if [[ "$HROOT" != "$SHARED_HOME" && "$HROOT" != "$SHARED_HOME/"* ]]; then
  echo "Profile home resolves outside shared Hermes home: $HROOT" >&2
  exit 2
fi
HERMES_CMD=(hermes -p "$PROFILE")

PLUGIN_PARENT="$HROOT/plugins"
mkdir -p "$PLUGIN_PARENT"
PLUGIN_PARENT="$(canonical_path "$PLUGIN_PARENT")"
if [[ "$PLUGIN_PARENT" != "$HROOT/"* ]]; then
  echo "Plugin directory resolves outside profile home: $PLUGIN_PARENT" >&2
  exit 2
fi
TARGET="$PLUGIN_PARENT/thinktofinish-company"
RESOLVED_TARGET="$(canonical_path "$TARGET")"
if [[ "$RESOLVED_TARGET" != "$PLUGIN_PARENT/"* ]]; then
  echo "Plugin target resolves outside plugin directory: $RESOLVED_TARGET" >&2
  exit 2
fi
STAGE="$(mktemp -d "$PLUGIN_PARENT/.thinktofinish-company.XXXXXX")"
BACKUP=""
INSTALLED=0
rollback() {
  local status=$?
  local rollback_failed=0
  trap - EXIT HUP INT TERM
  set +e
  if [[ $status -ne 0 ]]; then
    [[ -z "$STAGE" || ! -e "$STAGE" ]] || rm -rf "$STAGE"
    if [[ -n "$BACKUP" && ( -e "$BACKUP" || -L "$BACKUP" ) ]]; then
      [[ ! -e "$TARGET" && ! -L "$TARGET" ]] || rm -rf "$TARGET" || rollback_failed=1
      mv "$BACKUP" "$TARGET" || rollback_failed=1
    elif [[ "$INSTALLED" -eq 1 && ( -e "$TARGET" || -L "$TARGET" ) ]]; then
      rm -rf "$TARGET" || rollback_failed=1
    fi
  fi
  [[ "$rollback_failed" -eq 0 ]] || status=1
  exit "$status"
}
trap rollback EXIT
trap 'exit 129' HUP
trap 'exit 130' INT
trap 'exit 143' TERM

# Copy the portable package without local build/cache state.
tar -C "$SOURCE" \
  --exclude='.git' --exclude='.venv' --exclude='.pytest_cache' \
  --exclude='__pycache__' --exclude='.local-data' \
  --exclude='.env' --exclude='.env.*' \
  -cf - . | tar -C "$STAGE" -xf -

for REQUIRED in plugin.json mcp.json server.py; do
  [[ -f "$STAGE/$REQUIRED" ]] || { echo "Staged plugin is missing $REQUIRED" >&2; exit 1; }
done
if [[ -e "$TARGET" || -L "$TARGET" ]]; then
  BACKUP="$PLUGIN_PARENT/.thinktofinish-company.backup.$$"
  [[ ! -e "$BACKUP" ]] || { echo "Backup path already exists: $BACKUP" >&2; exit 1; }
  mv "$TARGET" "$BACKUP"
fi
INSTALLED=1
mv "$STAGE" "$TARGET"
STAGE=""

chmod +x "$TARGET/scripts/"*.sh 2>/dev/null || true
"${HERMES_CMD[@]}" plugins enable thinktofinish-company --no-allow-tool-override >/dev/null
trap - EXIT HUP INT TERM
if [[ -n "$BACKUP" ]]; then
  rm -rf "$BACKUP"
  BACKUP=""
fi

echo "Installed and enabled thinktofinish-company for profile: $PROFILE"
echo "Location: $TARGET"
