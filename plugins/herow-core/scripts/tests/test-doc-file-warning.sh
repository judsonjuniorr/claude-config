#!/usr/bin/env bash
# Tests for doc-file-warning.sh: the output-hygiene guard for stray .md writes.
# Run: bash plugins/herow-core/scripts/tests/test-doc-file-warning.sh
set -eu

GUARD="$(cd "$(dirname "$0")/.." && pwd)/doc-file-warning.sh"
[ -f "$GUARD" ] || { echo "guard not found: $GUARD" >&2; exit 1; }

T="$(mktemp -d)"
trap 'rm -rf "$T"' EXIT
mkdir -p "$T/repo/.claude/plans/20260101-000000-demo"
cd "$T/repo"
git init -q .

PASS=0
FAIL=0
ok()   { PASS=$((PASS + 1)); echo "ok   - $1"; }
fail() { FAIL=$((FAIL + 1)); echo "FAIL - $1"; }

run() { printf '{"tool_input":{"file_path":"%s"}}' "$1" | bash "$GUARD"; }

# 1. Random doc in the repo -> prompts
run 'NOTES-SUMMARY.md' | grep -q permissionDecision \
  && ok "stray repo doc prompts" || fail "stray repo doc did not prompt"

# 2. Conventional doc -> silent
[ -z "$(run 'README.md')" ] \
  && ok "README.md allowed silently" || fail "README.md prompted"

# 3. Plan orchestration artifact -> silent (per-plan layout exemption)
[ -z "$(run '.claude/plans/20260101-000000-demo/plan.md')" ] \
  && ok "plan-dir write allowed silently" || fail "plan-dir write prompted"

# 4. Traversal through the exemption -> still prompts (path is canonicalized first)
run '.claude/plans/../../escape.md' | grep -q permissionDecision \
  && ok "dot-dot traversal via plans/ still prompts" || fail "traversal bypassed the guard"

# 5. Outside the repo -> silent
[ -z "$(run '/tmp/external-notes.md')" ] \
  && ok "outside-repo write allowed silently" || fail "outside-repo write prompted"

# 6. Non-markdown -> silent
[ -z "$(run 'script.sh')" ] \
  && ok "non-markdown ignored" || fail "non-markdown prompted"

echo "----"
echo "$PASS passed, $FAIL failed"
[ "$FAIL" -eq 0 ]
