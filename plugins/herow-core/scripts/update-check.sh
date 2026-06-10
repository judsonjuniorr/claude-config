#!/usr/bin/env bash
# SessionStart hook: herow auto-update check (gstack pattern).
# Throttled to once/hour, network-failure-safe, silent unless behind.
# Complements the native marketplace auto-update toggle (which is opt-in).
set -u

REPO="judsonjuniorr/claude-config"

DATA_DIR="${CLAUDE_PLUGIN_DATA:-$HOME/.claude/herow-data}"
mkdir -p "$DATA_DIR" 2>/dev/null || exit 0
STAMP="$DATA_DIR/last-update-check"

now=$(date +%s)
if [ -f "$STAMP" ]; then
  last=$(cat "$STAMP" 2>/dev/null || echo 0)
  case "$last" in (*[!0-9]*|'') last=0 ;; esac
  [ $((now - last)) -lt 3600 ] && exit 0
fi
echo "$now" > "$STAMP" 2>/dev/null || true

# Installed SHA: the plugin cache is a git checkout of the marketplace repo.
ROOT="${CLAUDE_PLUGIN_ROOT:-}"
[ -n "$ROOT" ] || exit 0
dir="$ROOT"
while [ "$dir" != "/" ] && [ ! -e "$dir/.git" ]; do dir=$(dirname "$dir"); done
[ -e "$dir/.git" ] || exit 0
local_sha=$(git -C "$dir" rev-parse HEAD 2>/dev/null) || exit 0
[ -n "$local_sha" ] || exit 0

# Latest SHA on GitHub (curl -m is portable on macOS; `timeout` is not).
remote_sha=$(curl -m 5 -fsSL -H "Accept: application/vnd.github.sha" \
  "https://api.github.com/repos/$REPO/commits/HEAD" 2>/dev/null) || exit 0
case "$remote_sha" in ([0-9a-f]??????????????????????????????????????*) ;; (*) exit 0 ;; esac

if [ "$remote_sha" != "$local_sha" ]; then
  echo "herow: plugin updates available (installed $(printf '%.7s' "$local_sha"), latest $(printf '%.7s' "$remote_sha")). Run /herow-core:upgrade, or enable auto-update once via /plugin → Marketplaces → herow."
fi

exit 0
