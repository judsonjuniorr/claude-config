#!/usr/bin/env bash
# claude-config PreToolUse/(Grep|Glob|Bash) nudge.
# Steers Claude toward the graphify knowledge graph (graphify-out/) instead of raw
# grep/glob/file search, in any repo where graphify is installed. Version-controlled
# replacement for a machine-local settings.json block that never actually fired:
# that one only matched tool "Bash" and grepped the command string, but native
# Grep/Glob tool calls (USE_BUILTIN_RIPGREP=1) never go through Bash at all.
# Never blocks hard, never errors.

set -u

# Resolve the git toplevel rather than trusting CLAUDE_PROJECT_DIR verbatim — if
# Claude Code was launched from a subdirectory of the repo, CLAUDE_PROJECT_DIR may
# not be the root, and graphify-freshen.sh already resolves via git toplevel. All
# three graphify hooks must agree on "the repo" or this one silently never fires
# while freshen.sh keeps refreshing a graph nobody gets nudged toward. Fail CLOSED
# on resolution failure (exit 0), matching freshen.sh — never act on an unverified
# path.
DIR="$(git -C "${CLAUDE_PROJECT_DIR:-.}" rev-parse --show-toplevel 2>/dev/null)" || exit 0

RAW="$(cat)"
TOOL="$(printf '%s' "$RAW" | python3 -c "import json,sys; print(json.load(sys.stdin).get('tool_name',''))" 2>/dev/null || true)"

GRAPH_DIR=""
[ -f "$DIR/graphify-out/graph.json" ] && GRAPH_DIR="$DIR"

case "$TOOL" in
  Grep|Glob)
    if [ -z "$GRAPH_DIR" ]; then
      # Session root has no graph — check the call's OWN target path too (covers
      # e.g. a frontend-rooted session whose Grep reaches into a sibling backend/
      # that IS graphified; the session root alone would otherwise miss it).
      TARGET_PATH="$(printf '%s' "$RAW" | python3 -c "import json,sys; d=json.load(sys.stdin); ti=d.get('tool_input') or {}; print(ti.get('path','') if isinstance(ti,dict) else '')" 2>/dev/null || true)"
      if [ -n "$TARGET_PATH" ]; then
        case "$TARGET_PATH" in
          /*) TARGET_ABS="$TARGET_PATH" ;;
          *)  TARGET_ABS="$DIR/$TARGET_PATH" ;;
        esac
        TARGET_ROOT="$(git -C "$TARGET_ABS" rev-parse --show-toplevel 2>/dev/null || true)"
        [ -n "$TARGET_ROOT" ] && [ -f "$TARGET_ROOT/graphify-out/graph.json" ] && GRAPH_DIR="$TARGET_ROOT"
      fi
    fi
    ;;
  Bash)
    CMD="$(printf '%s' "$RAW" | python3 -c "import json,sys; d=json.load(sys.stdin); print(d.get('tool_input',{}).get('command',''))" 2>/dev/null || true)"
    case "$CMD" in
      *grep\ *|*rg\ *|*find\ *|*fd\ *|*ack\ *|*ag\ *) ;;
      *) exit 0 ;;
    esac
    # A Bash command can target any arbitrary path via its own arguments — reliably
    # parsing a target directory out of an opaque shell string is out of scope, so
    # only the session root is checked for Bash (unlike Grep/Glob above).
    ;;
  *) exit 0 ;;
esac

[ -n "$GRAPH_DIR" ] || exit 0

MSG="$(printf 'graphify: knowledge graph at %s/graphify-out/graph.json. For codebase/architecture/file-relationship questions, prefer `graphify query "<question>"` (scoped subgraph, usually far smaller than raw search) over grepping/globbing files. Use `graphify path "A" "B"` / `graphify explain "Node"` for relationships. Read GRAPH_REPORT.md only for broad architecture context.' "$GRAPH_DIR")"

python3 -c "import json,sys; print(json.dumps({'hookSpecificOutput':{'hookEventName':'PreToolUse','additionalContext':sys.argv[1]}}))" "$MSG"
exit 0
