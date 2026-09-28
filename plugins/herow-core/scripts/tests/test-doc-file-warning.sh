#!/usr/bin/env bash
# Tests for doc-file-warning.sh: the output-hygiene guard for stray .md writes.
# Run: bash plugins/herow-core/scripts/tests/test-doc-file-warning.sh
set -eu

GUARD="$(cd "$(dirname "$0")/.." && pwd)/doc-file-warning.sh"
[ -f "$GUARD" ] || { echo "guard not found: $GUARD" >&2; exit 1; }

T="$(mktemp -d)"
trap 'rm -rf "$T"' EXIT
mkdir -p "$T/repo"
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

# 3. Plan artifact under the herow project store -> still prompts (no in-repo exemption
#    left now that herow-dev writes plans under $HEROW_HOME, outside the repo entirely —
#    an in-repo .claude/plans/*.md write is just an ordinary stray doc).
mkdir -p .claude/plans/20260101-000000-demo
run '.claude/plans/20260101-000000-demo/plan.md' | grep -q permissionDecision \
  && ok "in-repo .claude/plans/*.md prompts (no exemption left)" || fail "in-repo plan write did not prompt"

# 4. Outside the repo -> silent (covers both /tmp and the herow store, e.g. ~/.herow)
[ -z "$(run '/tmp/external-notes.md')" ] \
  && ok "outside-repo write allowed silently" || fail "outside-repo write prompted"

# 5. Non-markdown -> silent
[ -z "$(run 'script.sh')" ] \
  && ok "non-markdown ignored" || fail "non-markdown prompted"

echo "----"
echo "$PASS passed, $FAIL failed"
[ "$FAIL" -eq 0 ]
