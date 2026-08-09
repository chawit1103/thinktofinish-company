#!/usr/bin/env bash
set -euo pipefail

PROFILE="default"
SOURCE="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --profile) PROFILE="$2"; shift 2 ;;
    *) echo "Unknown argument: $1" >&2; exit 2 ;;
  esac
done

if ! command -v hermes >/dev/null 2>&1; then
  echo "Hermes CLI not found on PATH." >&2
  exit 1
fi

if [[ "$PROFILE" == "default" ]]; then
  HROOT="${HERMES_HOME:-$HOME/.hermes}"
  HERMES_CMD=(hermes)
else
  HROOT="${HERMES_HOME:-$HOME/.hermes}/profiles/$PROFILE"
  HERMES_CMD=(hermes -p "$PROFILE")
fi

TARGET="$HROOT/plugins/thinktofinish-company"
mkdir -p "$HROOT/plugins"
rm -rf "$TARGET"
mkdir -p "$TARGET"

# Copy the portable package without local build/cache state.
tar -C "$SOURCE" \
  --exclude='.git' --exclude='.venv' --exclude='.pytest_cache' \
  --exclude='__pycache__' --exclude='.local-data' \
  -cf - . | tar -C "$TARGET" -xf -

chmod +x "$TARGET/scripts/"*.sh 2>/dev/null || true
"${HERMES_CMD[@]}" plugins enable thinktofinish-company >/dev/null

echo "Installed and enabled thinktofinish-company for profile: $PROFILE"
echo "Location: $TARGET"
