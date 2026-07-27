#!/usr/bin/env bash
# SessionStart hook: proactively point Claude at the graphify knowledge graph when
# one exists for this repo (SessionStart stdout becomes session context, same
# mechanism as rules-inject.sh). Complements graphify-nudge.sh (PreToolUse), which
# only fires once Claude has already reached for Grep/Glob/Bash-grep.
# Silent (no output) when no graph is present — zero cost in non-graphify repos.
set -u

# Resolve the git toplevel rather than trusting CLAUDE_PROJECT_DIR verbatim — see
# graphify-nudge.sh for why all three graphify hooks must agree on "the repo". Fail
# CLOSED on resolution failure (exit 0) — never act on an unverified path.
DIR="$(git -C "${CLAUDE_PROJECT_DIR:-.}" rev-parse --show-toplevel 2>/dev/null)" || exit 0
[ -f "$DIR/graphify-out/graph.json" ] || exit 0

cat <<'EOF'
## graphify

This repo has a graphify knowledge graph at `graphify-out/`. For codebase,
architecture, or file-relationship questions, prefer `graphify query "<question>"`,
`graphify path "A" "B"`, or `graphify explain "Node"` over grepping/reading files —
they return a scoped subgraph instead of raw text. Rebuild after significant code
changes with `graphify update` (incremental) or `/graphify --update`.
EOF

exit 0
