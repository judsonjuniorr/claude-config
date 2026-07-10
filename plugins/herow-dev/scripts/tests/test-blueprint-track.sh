#!/usr/bin/env bash
# Functional + concurrency tests for blueprint-track.sh.
# Self-contained: builds a throwaway git repo in a temp dir, drives the hook with synthetic
# PreToolUse/PostToolUse payloads on stdin, and asserts on the resulting state.json.
# Run: bash plugins/herow-dev/scripts/tests/test-blueprint-track.sh
set -eu

HOOK="$(cd "$(dirname "$0")/.." && pwd)/blueprint-track.sh"
[ -f "$HOOK" ] || { echo "hook not found: $HOOK" >&2; exit 1; }

T="$(mktemp -d)"
trap 'rm -rf "$T"' EXIT
mkdir -p "$T/outer/repo/.claude/plans"
cd "$T/outer/repo"
git init -q .

PASS=0
FAIL=0
ok()   { PASS=$((PASS + 1)); echo "ok   - $1"; }
fail() { FAIL=$((FAIL + 1)); echo "FAIL - $1"; }

pre()  { printf '{"session_id":"%s","tool_input":{"skill":"%s"}}' "$1" "$2" | CLAUDE_PROJECT_DIR="$PWD" bash "$HOOK" pre; }
post() { printf '{"session_id":"%s","tool_input":{"skill":"%s"}}' "$1" "$2" | CLAUDE_PROJECT_DIR="$PWD" bash "$HOOK" post; }

new_plan() { # $1 = slug
  mkdir -p ".claude/plans/$1/artifacts"
}
state() { # $1 = slug, $2 = python expr over parsed state `s`
  python3 -c "
import json, sys
s = json.load(open('.claude/plans/$1/state.json'))
print($2)"
}

# --- 1. Session gating: no marker for this session_id -> no-op ---------------------------
new_plan 20260101-000000-alpha
echo '20260101-000000-alpha' > .claude/plans/.active-owner
pre other-session office-hours
post other-session office-hours
if [ ! -f .claude/plans/20260101-000000-alpha/state.json ]; then
  ok "session gating: foreign session_id records nothing"
else
  fail "session gating: foreign session_id wrote state.json"
fi

# --- 2. Hostile session_id (path chars) -> clean no-op, exit 0 ---------------------------
if printf '{"session_id":"../x","tool_input":{"skill":"spec"}}' | CLAUDE_PROJECT_DIR="$PWD" bash "$HOOK" post; then
  ok "hostile session_id: no-op, exit 0"
else
  fail "hostile session_id: hook exited non-zero"
fi

# --- 3. Traversal slug in the marker -> rejected, nothing written outside the repo -------
echo '../../..' > .claude/plans/.active-owner
pre owner office-hours
post owner office-hours
if [ ! -e "$T/outer/state.json" ] && [ ! -d "$T/outer/artifacts" ] && [ ! -d "$T/outer/.snap" ]; then
  ok "traversal slug: rejected, no writes outside the repo"
else
  fail "traversal slug: hook wrote outside the repo"
fi

# --- 4. Normal PRE/POST: record appended, namespace stripped, artifact detected ----------
echo '20260101-000000-alpha' > .claude/plans/.active-owner
pre owner 'herow-dev:code:review'
echo note > .claude/plans/20260101-000000-alpha/artifacts/note.txt
post owner 'herow-dev:code:review'
if [ "$(state 20260101-000000-alpha "s['skills'][0]['skill']")" = "code:review" ] \
   && [ "$(state 20260101-000000-alpha "any('note.txt' in a for a in s['skills'][0]['artifacts'])")" = "True" ]; then
  ok "record: namespace stripped once (code:review), artifact detected"
else
  fail "record: wrong skill name or missing artifact"
fi

# --- 5. Nested LIFO pairing: inner POST pops inner PRE ------------------------------------
pre owner outer-skill
echo a > .claude/plans/20260101-000000-alpha/artifacts/outer-early.txt
pre owner inner-skill
echo b > .claude/plans/20260101-000000-alpha/artifacts/inner.txt
post owner inner-skill
echo c > .claude/plans/20260101-000000-alpha/artifacts/outer-late.txt
post owner outer-skill
inner_arts="$(state 20260101-000000-alpha "','.join(s['skills'][-2]['artifacts'])")"
outer_arts="$(state 20260101-000000-alpha "','.join(s['skills'][-1]['artifacts'])")"
case "$inner_arts" in
  *inner.txt*) case "$outer_arts" in
    *outer-early.txt*|*outer-late.txt*) ok "LIFO: nested calls paired correctly" ;;
    *) fail "LIFO: outer record missing its artifacts ($outer_arts)" ;;
  esac ;;
  *) fail "LIFO: inner record missing inner.txt ($inner_arts)" ;;
esac

# --- 6. Corruption: preserved aside (twice), tracking continues ---------------------------
echo 'GARBAGE{' > .claude/plans/20260101-000000-alpha/state.json
pre owner spec; post owner spec
echo 'GARBAGE2{' > .claude/plans/20260101-000000-alpha/state.json
pre owner qa; post owner qa
n_corrupt="$(ls .claude/plans/20260101-000000-alpha/ | grep -c corrupt || true)"
if [ "$n_corrupt" -ge 2 ] \
   && python3 -c "import json; json.load(open('.claude/plans/20260101-000000-alpha/state.json'))" 2>/dev/null; then
  ok "corruption: both corrupt copies preserved, state valid again"
else
  fail "corruption: expected >=2 preserved copies and valid state (got $n_corrupt)"
fi

# --- 7. Stale lock: broken by TTL, record still lands, no 5s spin -------------------------
mkdir -p .claude/plans/20260101-000000-alpha/.snap/.lock
old="$(date -v-1M +%Y%m%d%H%M 2>/dev/null || date -d '1 minute ago' +%Y%m%d%H%M)"
touch -t "$old" .claude/plans/20260101-000000-alpha/.snap/.lock
start="$(date +%s)"
pre owner learn; post owner learn
elapsed=$(( $(date +%s) - start ))
if [ "$(state 20260101-000000-alpha "s['skills'][-1]['skill']")" = "learn" ] && [ "$elapsed" -lt 5 ]; then
  ok "stale lock: broken by TTL in ${elapsed}s, record landed"
else
  fail "stale lock: took ${elapsed}s or record missing"
fi

# --- 8. Concurrent same-plan POSTs: both records survive under the lock -------------------
pre owner par-a
pre owner par-b
post owner par-a & post owner par-b &
wait
n="$(state 20260101-000000-alpha "sum(1 for k in s['skills'] if k['skill'] in ('par-a','par-b'))")"
if [ "$n" = "2" ]; then
  ok "concurrency: both concurrent POST records survived"
else
  fail "concurrency: lost update — only $n of 2 records"
fi

# --- 9. .claude/plans as a FILE (not dir) -> fail-safe no-op ------------------------------
mkdir -p "$T/outer/filerepo" && cd "$T/outer/filerepo" && git init -q .
mkdir .claude && echo x > .claude/plans
if printf '{"session_id":"s","tool_input":{"skill":"spec"}}' | CLAUDE_PROJECT_DIR="$PWD" bash "$HOOK" post; then
  ok "plans-as-file: clean no-op"
else
  fail "plans-as-file: hook exited non-zero"
fi

echo "----"
echo "$PASS passed, $FAIL failed"
[ "$FAIL" -eq 0 ]
