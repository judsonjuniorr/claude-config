#!/usr/bin/env bash
# Read-only inventory for /herow-core:setup.
# Emits pipe-delimited records the command reads back:
#   dep|<name>|installed|<path>            OS dependency present
#   dep|<name>|missing|-                   OS dependency absent
#   tool|<name>|installed|<detail>         stack tool present
#   tool|<name>|missing|-                  stack tool absent (will install)
#   remove|omega|<surface>|<detail>        OMEGA surface found (removal candidate)
#   remove|loose|<surface>|<detail>        loose duplicate command/hook found
#   remove|stray|<name>|<detail>           other memory/token tool found
set -u
HERE="$(cd "$(dirname "$0")" && pwd)"
. "${HERE}/_common.sh"

## --- OS dependencies ---
for c in git brew python3 uv node npm bun; do
  if have "$c"; then echo "dep|${c}|installed|$(command -v "$c")"
  else echo "dep|${c}|missing|-"; fi
done

## --- stack tools ---
if have rtk;      then emit tool rtk      installed "$(rtk --version 2>/dev/null | head -1)";      else emit tool rtk      missing -; fi
if have graphify; then emit tool graphify installed "$(graphify --version 2>/dev/null | head -1)"; else emit tool graphify missing -; fi
if have headroom; then emit tool headroom installed "$(headroom --version 2>/dev/null | head -1)"; else emit tool headroom missing -; fi
if [ -d "${GSTACK_DIR}/.git" ]; then emit tool gstack installed "${GSTACK_DIR}"; else emit tool gstack missing -; fi

## --- OMEGA surfaces (all removal candidates) ---
have uv && uv tool list 2>/dev/null | grep -qi '^omega-memory' && emit remove omega uv-tool "uv tool: omega-memory"
[ -e "${HOME}/.local/bin/omega" ] && emit remove omega bin "${HOME}/.local/bin/omega"
[ -f "$SETTINGS" ] && grep -q 'omega' "$SETTINGS" 2>/dev/null && emit remove omega settings-hooks "$SETTINGS"
[ -f "$CLAUDE_MD" ] && grep -qi 'OMEGA' "$CLAUDE_MD" 2>/dev/null && emit remove omega claude-md "$CLAUDE_MD (## Memory section)"
if [ -f "$CLAUDE_JSON" ]; then
  python3 - "$CLAUDE_JSON" <<'PY' 2>/dev/null || true
import json,sys
try: d=json.load(open(sys.argv[1]))
except: sys.exit(0)
srv=d.get("mcpServers",{})
for k in srv:
    if "omega" in k.lower(): print("remove|omega|mcp-server|%s (~/.claude.json)"%k)
PY
fi

## --- loose duplicate commands/hooks (superseded by herow-dev plugin) ---
for n in blueprint quick execute; do
  [ -f "${LOOSE_CMD_DIR}/${n}.md" ] && emit remove loose "cmd-${n}" "${LOOSE_CMD_DIR}/${n}.md"
done
[ -f "$LOOSE_HOOK" ] && emit remove loose track-script "$LOOSE_HOOK"
[ -f "$SETTINGS" ] && grep -q 'blueprint-track.sh' "$SETTINGS" 2>/dev/null && emit remove loose settings-hook "$SETTINGS (blueprint-track.sh Skill hooks)"

## --- other stray memory/token MCP servers (excluding omega, already covered) ---
if [ -f "$CLAUDE_JSON" ]; then
  python3 - "$CLAUDE_JSON" <<'PY' 2>/dev/null || true
import json,sys
try: d=json.load(open(sys.argv[1]))
except: sys.exit(0)
for k in d.get("mcpServers",{}):
    kl=k.lower()
    if "omega" in kl: continue
    if "memory" in kl: print("remove|stray|%s|MCP server '%s' (~/.claude.json)"%(k,k))
PY
fi
exit 0
