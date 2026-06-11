#!/usr/bin/env bash
# Wire headroom into Claude Code. Two modes:
#   mcp   (default, safe) — register headroom MCP tools (compress/retrieve/stats).
#                           Non-invasive: does NOT touch API auth.
#   wrap  (max savings)   — `headroom wrap claude` routes the API through the local
#                           proxy. Backs up Claude config first; under Pro/Max OAuth
#                           the proxy can break auth — rollback instructions printed.
# Usage: headroom-wrap.sh [mcp|wrap]
set -u
HERE="$(cd "$(dirname "$0")" && pwd)"
. "${HERE}/_common.sh"

MODE="${1:-mcp}"

have headroom || { emit err headroom-missing "install headroom first (install-stack.sh)"; exit 1; }

case "$MODE" in
  mcp)
    info headroom-mcp "headroom mcp install"
    if headroom mcp install 2>/dev/null; then
      emit ok headroom-mode "mcp (compress/retrieve/stats tools registered)"
    else
      emit err headroom-mcp "headroom mcp install failed — run 'headroom mcp install' manually"
    fi
    ;;
  wrap)
    # Back up anything the proxy wrap might rewrite, so rollback is always possible.
    backup_file "$CLAUDE_JSON" >/dev/null
    backup_file "$SETTINGS"    >/dev/null
    info headroom-wrap "headroom wrap claude --memory false --code-graph"
    if headroom wrap claude --memory false --code-graph 2>/dev/null \
       || headroom wrap claude 2>/dev/null; then
      emit ok headroom-mode "wrap (API proxied via headroom; memory OFF)"
      emit info headroom-rollback "if auth breaks next session: 'headroom unwrap claude' or restore the .bak files"
    else
      info headroom-wrap "wrap failed — falling back to safe MCP mode"
      headroom mcp install 2>/dev/null \
        && emit ok headroom-mode "mcp (wrap failed, fell back)" \
        || emit err headroom-wrap "wrap and mcp both failed"
    fi
    ;;
  *)
    emit err headroom-mode "unknown mode '$MODE' (use mcp|wrap)"; exit 1 ;;
esac
exit 0
