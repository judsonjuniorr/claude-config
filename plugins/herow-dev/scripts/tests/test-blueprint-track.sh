#!/usr/bin/env bash
# Functional + concurrency tests for blueprint-track.sh.
# Self-contained: builds a throwaway HEROW_HOME + plan dir in a temp dir, drives the hook
# with synthetic PreToolUse/PostToolUse payloads on stdin, and asserts on the resulting
# state.json.
# Run: bash plugins/herow-dev/scripts/tests/test-blueprint-track.sh
set -eu

HOOK="$(cd "$(dirname "$0")/.." && pwd)/blueprint-track.sh"
[ -f "$HOOK" ] || { echo "hook not found: $HOOK" >&2; exit 1; }

T="$(mktemp -d)"
trap 'rm -rf "$T"' EXIT

export HEROW_HOME="$T/herow"
PROJECT_DIR="$HEROW_HOME/projects/demo-repo-abc123"
ACTIVE_DIR="$HEROW_HOME/projects/.active"
mkdir -p "$ACTIVE_DIR" "$PROJECT_DIR/plans"

PASS=0
FAIL=0
ok()   { PASS=$((PASS + 1)); echo "ok   - $1"; }
fail() { FAIL=$((FAIL + 1)); echo "FAIL - $1"; }

pre()  { printf '{"session_id":"%s","tool_input":{"skill":"%s"}}' "$1" "$2" | bash "$HOOK" pre; }
post() { printf '{"session_id":"%s","tool_input":{"skill":"%s"}}' "$1" "$2" | bash "$HOOK" post; }

new_plan() { # $1 = slug
  mkdir -p "$PROJECT_DIR/plans/$1/artifacts"
}
state() { # $1 = slug, $2 = python expr over parsed state `s`
  python3 -c "
import json, sys
s = json.load(open('$PROJECT_DIR/plans/$1/state.json'))
print($2)"
}
set_marker() { # $1 = session id, $2 = literal marker content (an absolute plan-dir path)
  printf '%s' "$2" > "$ACTIVE_DIR/$1"
}

# --- 1. Session gating: no marker for this session_id -> no-op ---------------------------
new_plan 20260101-000000-alpha
set_marker owner "$PROJECT_DIR/plans/20260101-000000-alpha"
pre other-session office-hours
post other-session office-hours
if [ ! -f "$PROJECT_DIR/plans/20260101-000000-alpha/state.json" ]; then
  ok "session gating: foreign session_id records nothing"
else
  fail "session gating: foreign session_id wrote state.json"
fi

# --- 2. Hostile session_id (path chars) -> clean no-op, exit 0 ---------------------------
if printf '{"session_id":"../x","tool_input":{"skill":"spec"}}' | bash "$HOOK" post; then
  ok "hostile session_id: no-op, exit 0"
else
  fail "hostile session_id: hook exited non-zero"
fi

# --- 3. Marker with a traversal path -> rejected, nothing written outside the store -------
# The target must actually exist as a directory, or the hook's earlier `[ -d ]` guard bails
# out before ever reaching the prefix check below — proving nothing about that check.
mkdir -p "$T/etc"
set_marker owner "$HEROW_HOME/projects/demo-repo-abc123/plans/../../../../etc"
pre owner office-hours
post owner office-hours
if [ ! -f "$T/etc/state.json" ]; then
  ok "traversal marker: rejected, no writes outside the store"
else
  fail "traversal marker: hook wrote outside the store"
fi

# --- 4. Marker pointing outside HEROW_HOME entirely -> rejected ---------------------------
OUTSIDE="$T/outside-plan"
mkdir -p "$OUTSIDE"
set_marker owner "$OUTSIDE"
pre owner spec
post owner spec
if [ ! -f "$OUTSIDE/state.json" ]; then
  ok "marker outside HEROW_HOME: rejected, no state.json written there"
else
  fail "marker outside HEROW_HOME: hook wrote state.json outside the store"
fi

# --- 5. Marker resolves via a symlinked slug dir pointing outside the store -> rejected ----
ESCAPE_TARGET="$T/escape-target"
mkdir -p "$ESCAPE_TARGET"
ln -s "$ESCAPE_TARGET" "$PROJECT_DIR/plans/escape-link"
set_marker owner "$PROJECT_DIR/plans/escape-link"
pre owner spec
post owner spec
if [ ! -f "$ESCAPE_TARGET/state.json" ]; then
  ok "symlinked slug dir escaping the store: rejected"
else
  fail "symlinked slug dir escaping the store: hook wrote state.json into the escape target"
fi
rm -f "$PROJECT_DIR/plans/escape-link"

# --- 6. Normal PRE/POST: record appended, namespace stripped, artifact detected ----------
set_marker owner "$PROJECT_DIR/plans/20260101-000000-alpha"
pre owner 'herow-dev:code:review'
echo note > "$PROJECT_DIR/plans/20260101-000000-alpha/artifacts/note.txt"
post owner 'herow-dev:code:review'
if [ "$(state 20260101-000000-alpha "s['skills'][0]['skill']")" = "code:review" ] \
   && [ "$(state 20260101-000000-alpha "any('note.txt' in a for a in s['skills'][0]['artifacts'])")" = "True" ]; then
  ok "record: namespace stripped once (code:review), artifact detected"
else
  fail "record: wrong skill name or missing artifact"
fi

# --- 7. Nested LIFO pairing: inner POST pops inner PRE ------------------------------------
pre owner outer-skill
echo a > "$PROJECT_DIR/plans/20260101-000000-alpha/artifacts/outer-early.txt"
pre owner inner-skill
echo b > "$PROJECT_DIR/plans/20260101-000000-alpha/artifacts/inner.txt"
post owner inner-skill
echo c > "$PROJECT_DIR/plans/20260101-000000-alpha/artifacts/outer-late.txt"
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

# --- 8. Corruption: preserved aside (twice), tracking continues ---------------------------
echo 'GARBAGE{' > "$PROJECT_DIR/plans/20260101-000000-alpha/state.json"
pre owner spec; post owner spec
echo 'GARBAGE2{' > "$PROJECT_DIR/plans/20260101-000000-alpha/state.json"
pre owner qa; post owner qa
n_corrupt="$(ls "$PROJECT_DIR/plans/20260101-000000-alpha/" | grep -c corrupt || true)"
if [ "$n_corrupt" -ge 2 ] \
   && python3 -c "import json; json.load(open('$PROJECT_DIR/plans/20260101-000000-alpha/state.json'))" 2>/dev/null; then
  ok "corruption: both corrupt copies preserved, state valid again"
else
  fail "corruption: expected >=2 preserved copies and valid state (got $n_corrupt)"
fi

# --- 9. Stale lock: broken by TTL, record still lands, no 5s spin -------------------------
mkdir -p "$PROJECT_DIR/plans/20260101-000000-alpha/.snap/.lock"
old="$(date -v-1M +%Y%m%d%H%M 2>/dev/null || date -d '1 minute ago' +%Y%m%d%H%M)"
touch -t "$old" "$PROJECT_DIR/plans/20260101-000000-alpha/.snap/.lock"
start="$(date +%s)"
pre owner learn; post owner learn
elapsed=$(( $(date +%s) - start ))
if [ "$(state 20260101-000000-alpha "s['skills'][-1]['skill']")" = "learn" ] && [ "$elapsed" -lt 5 ]; then
  ok "stale lock: broken by TTL in ${elapsed}s, record landed"
else
  fail "stale lock: took ${elapsed}s or record missing"
fi

# --- 10. Concurrent same-plan POSTs: both records survive under the lock -------------------
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

# --- 11. Plan dir as a FILE (not dir) -> fail-safe no-op -----------------------------------
BOGUS_PROJECT="$HEROW_HOME/projects/bogus-repo-def456"
mkdir -p "$BOGUS_PROJECT/plans"
echo x > "$BOGUS_PROJECT/plans/notadir"
set_marker filerepo-session "$BOGUS_PROJECT/plans/notadir"
if printf '{"session_id":"filerepo-session","tool_input":{"skill":"spec"}}' | bash "$HOOK" post; then
  ok "plan-dir-as-file: clean no-op"
else
  fail "plan-dir-as-file: hook exited non-zero"
fi

echo "----"
echo "$PASS passed, $FAIL failed"
[ "$FAIL" -eq 0 ]
