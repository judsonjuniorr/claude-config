#!/usr/bin/env bash
# Tests for qa-run/scripts/change-surface.sh.
# Builds throwaway git repos under $HOME (never bare /tmp — see ensure-ignored's
# same convention) and asserts on the script's stdout/exit code.
# Run: bash plugins/herow-dev/scripts/tests/test-qa-change-surface.sh
set -u

SCRIPT="$(cd "$(dirname "$0")/../../skills/qa-run/scripts" && pwd)/change-surface.sh"
[ -f "$SCRIPT" ] || { echo "script not found: $SCRIPT" >&2; exit 1; }

SANDBOX="$HOME/.qa-change-surface-test.$$"
mkdir -p "$SANDBOX"
trap 'rm -rf "$SANDBOX"' EXIT

PASS=0
FAIL=0
ok()   { PASS=$((PASS + 1)); echo "ok   - $1"; }
fail() { FAIL=$((FAIL + 1)); echo "FAIL - $1"; }

git_repo() { # $1 = path, creates an initialized repo with one commit on main
  mkdir -p "$1"
  ( cd "$1" \
    && git init -q -b main . \
    && git config user.email test@example.com \
    && git config user.name test \
    && echo "one" > file.txt \
    && git add file.txt \
    && git commit -q -m "initial" )
}

# --- 1. Clean tree ---------------------------------------------------------------------------
REPO="$SANDBOX/clean"
git_repo "$REPO"
OUT="$("$SCRIPT" "$REPO" 2>&1)"; RC=$?
if [ "$RC" -eq 0 ] && printf '%s\n' "$OUT" | grep -q "^clean$"; then
  ok "clean tree: reports 'clean', exit 0"
else
  fail "clean tree: expected 'clean' and exit 0, got rc=$RC out=$OUT"
fi

# --- 2. Dirty tree -----------------------------------------------------------------------------
REPO="$SANDBOX/dirty"
git_repo "$REPO"
echo "uncommitted" >> "$REPO/file.txt"
OUT="$("$SCRIPT" "$REPO" 2>&1)"; RC=$?
if [ "$RC" -eq 0 ] && printf '%s' "$OUT" | grep -q "file.txt"; then
  ok "dirty tree: reports the modified file"
else
  fail "dirty tree: expected file.txt listed, got rc=$RC out=$OUT"
fi

# --- 3. Commits ahead of main --------------------------------------------------------------------
REPO="$SANDBOX/ahead"
git_repo "$REPO"
( cd "$REPO" && git checkout -q -b feature/x && echo "two" > new.txt && git add new.txt && git commit -q -m "feature commit" )
OUT="$("$SCRIPT" "$REPO" 2>&1)"; RC=$?
if [ "$RC" -eq 0 ] && printf '%s' "$OUT" | grep -q "^base: main$" && printf '%s' "$OUT" | grep -q "new.txt"; then
  ok "ahead of main: resolves base=main, reports new.txt vs base"
else
  fail "ahead of main: expected base=main and new.txt, got rc=$RC out=$OUT"
fi

# --- 4. No origin/HEAD (main/master local fallback) -----------------------------------------------
REPO="$SANDBOX/no-origin-head"
mkdir -p "$REPO"
( cd "$REPO" \
  && git init -q -b master . \
  && git config user.email test@example.com \
  && git config user.name test \
  && echo one > f.txt && git add f.txt && git commit -q -m init \
  && git checkout -q -b work && echo two > g.txt && git add g.txt && git commit -q -m work )
OUT="$("$SCRIPT" "$REPO" 2>&1)"; RC=$?
if [ "$RC" -eq 0 ] && printf '%s' "$OUT" | grep -q "^base: master$"; then
  ok "no origin/HEAD: falls back to local master"
else
  fail "no origin/HEAD: expected base=master, got rc=$RC out=$OUT"
fi

# --- 5. No resolvable base ------------------------------------------------------------------------
REPO="$SANDBOX/no-base"
mkdir -p "$REPO"
( cd "$REPO" \
  && git init -q -b oddball . \
  && git config user.email test@example.com \
  && git config user.name test \
  && echo one > f.txt && git add f.txt && git commit -q -m init )
OUT="$("$SCRIPT" "$REPO" 2>&1)"; RC=$?
if [ "$RC" -eq 0 ] && printf '%s' "$OUT" | grep -q "^base: unresolved$"; then
  ok "no resolvable base: prints 'base: unresolved', exit 0"
else
  fail "no resolvable base: expected 'base: unresolved' and exit 0, got rc=$RC out=$OUT"
fi

# --- 6. --diff cap truncation ------------------------------------------------------------------------
REPO="$SANDBOX/diff-cap"
git_repo "$REPO"
( cd "$REPO" && git checkout -q -b feature/big )
python3 -c "
lines = ''.join(f'line {i}\n' for i in range(600))
open('$REPO/file.txt', 'w').write(lines)
"
( cd "$REPO" && git add file.txt && git commit -q -m "big change" )
OUT="$("$SCRIPT" "$REPO" --diff --max-lines 50 2>&1)"; RC=$?
if [ "$RC" -eq 0 ] && printf '%s' "$OUT" | grep -qE "^truncated: 50/[0-9]+$"; then
  ok "--diff cap: truncates at --max-lines and reports shown/total"
else
  fail "--diff cap: expected a 'truncated: 50/N' line, got rc=$RC out=$OUT"
fi

# --- 7. --diff includes uncommitted changes, not just what's on HEAD --------------------------------
REPO="$SANDBOX/diff-uncommitted"
git_repo "$REPO"
( cd "$REPO" && git checkout -q -b feature/uncommitted && echo "committed change" > committed.txt && git add committed.txt && git commit -q -m "committed" )
echo "uncommitted change" >> "$REPO/committed.txt"
OUT="$("$SCRIPT" "$REPO" --diff 2>&1)"; RC=$?
if [ "$RC" -eq 0 ] && printf '%s' "$OUT" | grep -q "uncommitted change"; then
  ok "--diff: includes uncommitted changes vs the merge-base, not just HEAD"
else
  fail "--diff: expected the uncommitted hunk in the output, got rc=$RC out=$OUT"
fi

# --- 8. Unresolved base + --diff still reports the working-tree diff --------------------------------
REPO="$SANDBOX/no-base-diff"
mkdir -p "$REPO"
( cd "$REPO" \
  && git init -q -b oddball . \
  && git config user.email test@example.com \
  && git config user.name test \
  && echo one > f.txt && git add f.txt && git commit -q -m init )
echo "dirty line" >> "$REPO/f.txt"
OUT="$("$SCRIPT" "$REPO" --diff 2>&1)"; RC=$?
if [ "$RC" -eq 0 ] && printf '%s' "$OUT" | grep -q "^base: unresolved$" && printf '%s' "$OUT" | grep -q "dirty line"; then
  ok "unresolved base + --diff: still reports the working-tree-vs-HEAD diff"
else
  fail "unresolved base + --diff: expected 'base: unresolved' and the dirty hunk, got rc=$RC out=$OUT"
fi

# --- 9. Non-repo path → exit 2 ---------------------------------------------------------------------
REPO="$SANDBOX/not-a-repo"
mkdir -p "$REPO"
OUT="$("$SCRIPT" "$REPO" 2>&1)"; RC=$?
if [ "$RC" -eq 2 ]; then
  ok "non-repo path: exit 2"
else
  fail "non-repo path: expected exit 2, got rc=$RC out=$OUT"
fi

echo
echo "$PASS passed, $FAIL failed"
[ "$FAIL" -eq 0 ]
