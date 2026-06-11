#!/usr/bin/env bash
# Shared helpers for /herow-core:setup scripts. Sourced, not executed.
# Output convention: pipe-delimited, 1 record per line. Data → stdout, diagnostics → stderr.
#   ok|<code>|<details>     success / state
#   err|<code>|<reason>     failure
#   info|<code>|<message>   progress (stderr)
set -u

CLAUDE_HOME="${HOME}/.claude"
SETTINGS="${CLAUDE_HOME}/settings.json"
CLAUDE_JSON="${HOME}/.claude.json"
CLAUDE_MD="${CLAUDE_HOME}/CLAUDE.md"
GSTACK_DIR="${CLAUDE_HOME}/skills/gstack"
LOOSE_CMD_DIR="${CLAUDE_HOME}/commands"
LOOSE_HOOK="${CLAUDE_HOME}/hooks/blueprint-track.sh"

emit()  { local IFS='|'; echo "$*"; }
info()  { echo "info|$1|$2" >&2; }
have()  { command -v "$1" >/dev/null 2>&1; }

# Timestamped .bak before any destructive edit. Echoes the backup path.
backup_file() {
  local f="$1"
  [ -f "$f" ] || return 0
  local bak="${f}.bak.$(date -u +%Y%m%d-%H%M%S)"
  cp "$f" "$bak"
  info "backup" "$f -> $bak"
  echo "$bak"
}
