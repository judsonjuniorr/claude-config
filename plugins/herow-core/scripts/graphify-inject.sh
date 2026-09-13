#!/usr/bin/env bash
# SessionStart hook: proactively point Claude at the graphify knowledge graph when
# one exists for this repo (SessionStart stdout becomes session context, same
# mechanism as rules-inject.sh). Stating it once per session is enough — a
# per-tool-call nudge used to repeat it on every Grep/Glob/Bash-grep, which cost
# tokens on every search and second-guessed a tool choice already made.
# Silent (no output) when no graph is present — zero cost in non-graphify repos.
set -u

# Resolve the git toplevel rather than trusting CLAUDE_PROJECT_DIR verbatim: if
# Claude Code was launched from a subdirectory, CLAUDE_PROJECT_DIR may not be the
# root. Both graphify hooks must agree on "the repo" or this one announces a graph
# that graphify-freshen.sh is refreshing under a different path. Fail CLOSED on
# resolution failure (exit 0) — never act on an unverified path.
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
