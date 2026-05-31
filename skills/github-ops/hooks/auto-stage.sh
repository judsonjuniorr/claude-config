#!/usr/bin/env bash
# github-ops PostToolUse/Edit|Write hook.
# Auto-stages the edited file so ship.sh / inspect.sh see a warm index.
# Skips secret-looking paths (matching _common.sh:has_secret_paths). Silent,
# reversible, never errors.

FILE="$(python3 -c "import json,sys; d=json.load(sys.stdin); print(d.get('tool_input',d).get('file_path',''))" 2>/dev/null || true)"
[ -n "$FILE" ] || exit 0

# Don't auto-stage secrets.
case "$FILE" in
  *.env|*.env.*|*.key|*.pem|*.p12|*.pfx|*_rsa|*credentials*.json) exit 0 ;;
esac

DIR="$(dirname "$FILE")"
git -C "$DIR" rev-parse --is-inside-work-tree >/dev/null 2>&1 || exit 0
git -C "$DIR" add -- "$FILE" 2>/dev/null || true
exit 0
