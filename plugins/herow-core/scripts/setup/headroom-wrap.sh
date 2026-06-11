#!/usr/bin/env bash
# Wire headroom into Claude Code. Three modes:
#   mcp   (default, safe) — register headroom MCP tools (compress/retrieve/stats).
#                           Non-invasive: does NOT touch API auth.
#   init  (max savings)   — `headroom init --global --memory claude` installs durable
#                           hooks + provider routing (ANTHROPIC_BASE_URL → local proxy)
#                           with persistent memory. Backs up Claude config first; under
#                           Pro/Max OAuth the proxy can break auth — rollback printed.
#   wrap  (legacy)        — older `headroom wrap claude` path; kept for back-compat.
# Telemetry is forced OFF in init/wrap (HEADROOM_TELEMETRY=off, persisted to settings.json
# env so the hook-spawned proxy inherits it).
# Usage: headroom-wrap.sh [mcp|init|wrap]
set -u
HERE="$(cd "$(dirname "$0")" && pwd)"
. "${HERE}/_common.sh"

MODE="${1:-mcp}"

have headroom || { emit err headroom-missing "install headroom first (install-stack.sh)"; exit 1; }

# Persist HEADROOM_TELEMETRY=off into ~/.claude/settings.json env (idempotent), so the
# proxy launched by headroom's SessionStart/PreToolUse hook starts with telemetry off.
# Also flips any already-installed deploy manifest to telemetry-off for the next relaunch.
disable_telemetry_persist() {
  [ -f "$SETTINGS" ] || return 0
  python3 - "$SETTINGS" <<'PY' 2>/dev/null || true
import json,sys,glob,os
p=sys.argv[1]
try: s=json.load(open(p))
except Exception: sys.exit(0)
env=s.setdefault("env",{}); changed=False
for k in ("HEADROOM_TELEMETRY","HEADROOM_TELEMETRY_WARN"):
    if env.get(k)!="off": env[k]="off"; changed=True
if changed: json.dump(s,open(p,"w"),indent=2)
for m in glob.glob(os.path.expanduser("~/.headroom/deploy/*/manifest.json")):
    try: d=json.load(open(m))
    except Exception: continue
    d["telemetry_enabled"]=False
    be=d.setdefault("base_env",{}); be["HEADROOM_TELEMETRY"]="off"; be["HEADROOM_TELEMETRY_WARN"]="off"
    json.dump(d,open(m,"w"),indent=2)
PY
}

case "$MODE" in
  mcp)
    info headroom-mcp "headroom mcp install"
    if headroom mcp install 2>/dev/null; then
      emit ok headroom-mode "mcp (compress/retrieve/stats tools registered)"
    else
      emit err headroom-mcp "headroom mcp install failed — run 'headroom mcp install' manually"
    fi
    ;;
  init)
    # Durable hooks + provider routing + persistent memory, telemetry OFF.
    backup_file "$CLAUDE_JSON" >/dev/null
    backup_file "$SETTINGS"    >/dev/null
    info headroom-init "HEADROOM_TELEMETRY=off headroom init --global --memory claude"
    if HEADROOM_TELEMETRY=off HEADROOM_TELEMETRY_WARN=off \
         headroom init --global --memory claude 2>/dev/null; then
      disable_telemetry_persist
      emit ok headroom-mode "init (durable proxy + memory ON, telemetry OFF)"
      emit info headroom-restart "restart Claude Code to activate hooks + ANTHROPIC_BASE_URL routing"
      emit info headroom-rollback "if auth breaks: 'headroom unwrap claude' or restore the .bak files"
    else
      info headroom-init "init failed — falling back to safe MCP mode"
      headroom mcp install 2>/dev/null \
        && emit ok headroom-mode "mcp (init failed, fell back)" \
        || emit err headroom-init "init and mcp both failed"
    fi
    ;;
  wrap)
    # Back up anything the proxy wrap might rewrite, so rollback is always possible.
    backup_file "$CLAUDE_JSON" >/dev/null
    backup_file "$SETTINGS"    >/dev/null
    info headroom-wrap "headroom wrap claude --memory false --code-graph"
    if HEADROOM_TELEMETRY=off HEADROOM_TELEMETRY_WARN=off headroom wrap claude --memory false --code-graph 2>/dev/null \
       || HEADROOM_TELEMETRY=off HEADROOM_TELEMETRY_WARN=off headroom wrap claude 2>/dev/null; then
      disable_telemetry_persist
      emit ok headroom-mode "wrap (API proxied via headroom; memory OFF, telemetry OFF)"
      emit info headroom-rollback "if auth breaks next session: 'headroom unwrap claude' or restore the .bak files"
    else
      info headroom-wrap "wrap failed — falling back to safe MCP mode"
      headroom mcp install 2>/dev/null \
        && emit ok headroom-mode "mcp (wrap failed, fell back)" \
        || emit err headroom-wrap "wrap and mcp both failed"
    fi
    ;;
  *)
    emit err headroom-mode "unknown mode '$MODE' (use mcp|init|wrap)"; exit 1 ;;
esac
exit 0
