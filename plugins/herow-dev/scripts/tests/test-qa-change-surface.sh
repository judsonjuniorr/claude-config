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

git_repo() { # $1 = path, $2 = branch (default main); creates a repo with one commit
  mkdir -p "$1"
  ( cd "$1" \
    && git init -q -b "${2:-main}" . \
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
git_repo "$REPO" master
( cd "$REPO" \
  && git checkout -q -b work && echo two > g.txt && git add g.txt && git commit -q -m work )
OUT="$("$SCRIPT" "$REPO" 2>&1)"; RC=$?
if [ "$RC" -eq 0 ] && printf '%s' "$OUT" | grep -q "^base: master$"; then
  ok "no origin/HEAD: falls back to local master"
else
  fail "no origin/HEAD: expected base=master, got rc=$RC out=$OUT"
fi

# --- 5. No resolvable base ------------------------------------------------------------------------
REPO="$SANDBOX/no-base"
git_repo "$REPO" oddball
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
seq 0 599 | sed 's/^/line /' > "$REPO/file.txt"
( cd "$REPO" && git add file.txt && git commit -q -m "big change" )
OUT="$("$SCRIPT" "$REPO" --diff --max-lines 50 2>&1)"; RC=$?
if [ "$RC" -eq 0 ] && printf '%s' "$OUT" | grep -qE "^truncated: 50/[0-9]+$"; then
  ok "--diff cap: truncates at --max-lines and reports shown/total"
else
  fail "--diff cap: expected a 'truncated: 50/N' line, got rc=$RC out=$OUT"
fi

# --- 7. --diff = committed + uncommitted + untracked vs the merge-base, not main's tip ----------------
REPO="$SANDBOX/diff-uncommitted"
git_repo "$REPO"
( cd "$REPO" && git checkout -q -b feature/uncommitted && echo "committed change" > committed.txt && git add committed.txt && git commit -q -m "committed" )
( cd "$REPO" && git checkout -q main && echo "main moved on" > later.txt && git add later.txt && git commit -q -m "main later" && git checkout -q feature/uncommitted )
echo "uncommitted change" >> "$REPO/file.txt"
echo "untracked change" > "$REPO/untracked.txt"
OUT="$("$SCRIPT" "$REPO" --diff 2>&1)"; RC=$?
if [ "$RC" -eq 0 ] \
   && printf '%s\n' "$OUT" | grep -q "^+committed change$" \
   && printf '%s\n' "$OUT" | grep -q "^+uncommitted change$" \
   && printf '%s\n' "$OUT" | grep -q "^+untracked change$" \
   && ! printf '%s\n' "$OUT" | grep -q "main moved on"; then
  ok "--diff: committed + uncommitted + untracked hunks vs the merge-base, not main's tip"
else
  fail "--diff: expected committed/uncommitted/untracked hunks and no main-tip content, got rc=$RC out=$OUT"
fi

# --- 8. Unresolved base + --diff still reports the working-tree diff --------------------------------
REPO="$SANDBOX/no-base-diff"
git_repo "$REPO" oddball
echo "dirty line" >> "$REPO/file.txt"
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

# --- 10. origin/HEAD wins over local main ---------------------------------------------------------------
ORIGIN="$SANDBOX/origin"
git_repo "$ORIGIN"
( cd "$ORIGIN" && git checkout -q -b develop && echo d > d.txt && git add d.txt && git commit -q -m develop && git checkout -q main )
REPO="$SANDBOX/clone"
git clone -q "$ORIGIN" "$REPO"
( cd "$REPO" && git remote set-head origin develop && git checkout -q -b feat origin/develop )
OUT="$("$SCRIPT" "$REPO" 2>&1)"; RC=$?
if [ "$RC" -eq 0 ] && printf '%s\n' "$OUT" | grep -q "^base: origin/develop$"; then
  ok "origin/HEAD: preferred over local main"
else
  fail "origin/HEAD: expected base=origin/develop, got rc=$RC out=$OUT"
fi

# --- 11. --base overrides resolution -------------------------------------------------------------------
REPO="$SANDBOX/base-flag"
git_repo "$REPO"
( cd "$REPO" && git checkout -q -b topic && echo t > t.txt && git add t.txt && git commit -q -m topic && git checkout -q -b work )
OUT="$("$SCRIPT" "$REPO" --base topic 2>&1)"; RC=$?
if [ "$RC" -eq 0 ] && printf '%s\n' "$OUT" | grep -q "^base: topic$"; then
  ok "--base: overrides origin/HEAD/main resolution"
else
  fail "--base: expected base=topic, got rc=$RC out=$OUT"
fi

# --- 12. Invalid --base is reported, not silently 'unresolved' --------------------------------------------
OUT="$("$SCRIPT" "$REPO" --base nope 2>/dev/null)"; RC=$?
if [ "$RC" -eq 0 ] && printf '%s\n' "$OUT" | grep -q "^base: invalid (nope)$" && ! printf '%s\n' "$OUT" | grep -q "unresolved"; then
  ok "invalid --base: prints 'base: invalid (nope)', exit 0"
else
  fail "invalid --base: expected 'base: invalid (nope)', got rc=$RC out=$OUT"
fi

# --- 13. Non-numeric --max-lines → exit 2 -----------------------------------------------------------------
"$SCRIPT" "$REPO" --diff --max-lines abc >/dev/null 2>&1; RC=$?
if [ "$RC" -eq 2 ]; then
  ok "--max-lines abc: rejected with exit 2"
else
  fail "--max-lines abc: expected exit 2, got rc=$RC"
fi

echo
echo "$PASS passed, $FAIL failed"
[ "$FAIL" -eq 0 ]
