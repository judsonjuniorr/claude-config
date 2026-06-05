#!/usr/bin/env bash
# claude-config PreToolUse/Write guard.
# Enforces the "output hygiene" rule: do NOT generate reference guides, summary docs,
# or any .md documentation files unless the user explicitly asked. Surfaces a
# permission prompt ("ask") so a stray doc write becomes a conscious choice.
# Conventional project files (README, CHANGELOG, ...) are allowed silently.
# Never blocks hard, never errors.

FILE="$(python3 -c "import json,sys; d=json.load(sys.stdin); print(d.get('tool_input',d).get('file_path',''))" 2>/dev/null || true)"
[ -n "$FILE" ] || exit 0

# Only care about markdown.
case "$FILE" in
  *.md|*.markdown|*.mdx) ;;
  *) exit 0 ;;
esac

# Allow conventional repo docs that are expected to exist.
base="$(basename "$FILE")"
shopt -s nocasematch 2>/dev/null || true
case "$base" in
  README.md|CHANGELOG.md|CONTRIBUTING.md|LICENSE.md|SECURITY.md|CODE_OF_CONDUCT.md) exit 0 ;;
esac

reason="output hygiene: creating a .md doc file ($base). Per the standing rule, don't generate reference guides / summary docs / .md files unless explicitly asked. Approve only if the user requested this document."
python3 -c "import json,sys; print(json.dumps({'hookSpecificOutput':{'hookEventName':'PreToolUse','permissionDecision':'ask','permissionDecisionReason':sys.argv[1]}}))" "$reason"
exit 0
