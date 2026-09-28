#!/usr/bin/env bash
# Tests for herow-project.sh: the herow-dev per-project store resolver.
# Every case runs with HOME and GIT_CONFIG_GLOBAL pointed at a sandbox under the REAL
# $HOME, GIT_CONFIG_NOSYSTEM=1, and HEROW_HOME pointed at that same sandbox — so this
# suite never touches the developer's real ~/.herow or ~/.gitconfig.
# Run: bash plugins/herow-dev/scripts/tests/test-herow-project.sh
set -u

SCRIPT="$(cd "$(dirname "$0")/.." && pwd)/herow-project.sh"
[ -f "$SCRIPT" ] || { echo "script not found: $SCRIPT" >&2; exit 1; }

REAL_HOME="$HOME"
SANDBOX="$REAL_HOME/.herow-project-test.$$"
mkdir -p "$SANDBOX/home"
trap 'rm -rf "$SANDBOX"' EXIT

export HOME="$SANDBOX/home"
export GIT_CONFIG_GLOBAL="$SANDBOX/home/.gitconfig"
export GIT_CONFIG_NOSYSTEM=1
unset GIT_CONFIG_SYSTEM
: > "$GIT_CONFIG_GLOBAL"
git config --global user.email test@example.com
git config --global user.name test
export HEROW_HOME="$SANDBOX/herow"

PASS=0
FAIL=0
ok()   { PASS=$((PASS + 1)); echo "ok   - $1"; }
fail() { FAIL=$((FAIL + 1)); echo "FAIL - $1"; }

run() { bash "$SCRIPT" "$@"; }

new_repo() { # $1 = path
  mkdir -p "$1" && git init -q "$1"
}

# --- 1. Plain lookup creates nothing --------------------------------------------------------
new_repo "$SANDBOX/plain-repo"
OUT="$(cd "$SANDBOX/plain-repo" && run plans)"
if [ -n "$OUT" ] && [ ! -e "$HEROW_HOME" ]; then
  ok "plain lookup: prints a path, HEROW_HOME left nonexistent"
else
  fail "plain lookup: HEROW_HOME was created or no path printed (out=$OUT)"
fi

# --- 2. Output is exactly one absolute line --------------------------------------------------
OUT="$(cd "$SANDBOX/plain-repo" && run plans --ensure)"
LINES="$(printf '%s' "$OUT" | wc -l | tr -d ' ')"
case "$OUT" in
  /*) is_abs=1 ;;
  *) is_abs=0 ;;
esac
if [ "$is_abs" -eq 1 ] && [ "$(printf '%s\n' "$OUT" | wc -l | tr -d ' ')" = "1" ]; then
  ok "stdout is exactly one absolute path line"
else
  fail "stdout was not a single absolute line: $OUT"
fi
[ -d "$OUT" ] || fail "ensured plans dir does not exist: $OUT"

# --- 3. Same id from a subdir and from a git worktree ----------------------------------------
new_repo "$SANDBOX/repo-a"
( cd "$SANDBOX/repo-a" && echo x > f.txt && git add f.txt && git commit -q -m init )
ID_ROOT="$(cd "$SANDBOX/repo-a" && run dir --ensure)"
mkdir -p "$SANDBOX/repo-a/nested/deep"
ID_SUBDIR="$(cd "$SANDBOX/repo-a/nested/deep" && run dir --ensure)"
git -C "$SANDBOX/repo-a" worktree add -q -b wt-branch "$SANDBOX/repo-a-wt" >/dev/null 2>&1
ID_WORKTREE="$(cd "$SANDBOX/repo-a-wt" && run dir --ensure)"
if [ "$ID_ROOT" = "$ID_SUBDIR" ] && [ "$ID_ROOT" = "$ID_WORKTREE" ]; then
  ok "same id from repo root, a subdir, and a worktree"
else
  fail "id mismatch: root=$ID_ROOT subdir=$ID_SUBDIR worktree=$ID_WORKTREE"
fi

# --- 4. Two clones of the SAME origin at different paths -> different ids (path drives the
#        hash suffix even when the owner-repo slug is identical) ------------------------------
new_repo "$SANDBOX/clone-1"
( cd "$SANDBOX/clone-1" && git remote add origin https://github.com/acme/widget.git )
new_repo "$SANDBOX/clone-2"
( cd "$SANDBOX/clone-2" && git remote add origin https://github.com/acme/widget.git )
IDA="$(cd "$SANDBOX/clone-1" && run dir --ensure)"
IDB="$(cd "$SANDBOX/clone-2" && run dir --ensure)"
if [ "$IDA" != "$IDB" ]; then
  ok "two clones of the same origin at different paths get different ids"
else
  fail "two clones of the same origin collided on id: $IDA"
fi
[ -d "$IDA" ] || fail "clone-1's store dir disappeared after ensuring clone-2 ($IDA)"

# --- 4b. Second --ensure on an already-registered repo does not trigger move detection, and
#         does not disturb a DIFFERENT repo's store dir -----------------------------------------
BEFORE="$(cd "$SANDBOX/clone-1" && run dir --ensure)"
AFTER="$(cd "$SANDBOX/clone-1" && run dir --ensure 2>"$SANDBOX/hpt-move-err")"
MOVE_WARN="$(grep -c '|moved|' "$SANDBOX/hpt-move-err" 2>/dev/null || true)"
rm -f "$SANDBOX/hpt-move-err"
if [ "$BEFORE" = "$AFTER" ] && [ "${MOVE_WARN:-0}" = "0" ] && [ -d "$IDB" ]; then
  ok "re-ensuring an unmoved repo does not trigger move detection or disturb clone-2's store"
else
  fail "unexpected move detection or cross-clone disturbance (before=$BEFORE after=$AFTER idb=$IDB)"
fi

# --- 5. No remote -> basename-derived id ------------------------------------------------------
new_repo "$SANDBOX/lonely-repo"
OUT="$(cd "$SANDBOX/lonely-repo" && run dir --ensure)"
case "$(basename "$OUT")" in
  lonely-repo-*) ok "no remote: basename-derived id ($OUT)" ;;
  *) fail "no remote: expected a lonely-repo-* id, got $OUT" ;;
esac

# --- 6. Submodule gets its own id, distinct from the superproject -----------------------------
new_repo "$SANDBOX/sub-target"
( cd "$SANDBOX/sub-target" && echo s > s.txt && git add s.txt && git commit -q -m init )
new_repo "$SANDBOX/super-proj"
SUPER_ID="$(cd "$SANDBOX/super-proj" && run dir --ensure)"
( cd "$SANDBOX/super-proj" && git -c protocol.file.allow=always submodule add -q "$SANDBOX/sub-target" subm >/dev/null 2>&1 )
if [ -d "$SANDBOX/super-proj/subm/.git" ] || [ -f "$SANDBOX/super-proj/subm/.git" ]; then
  SUB_ID="$(cd "$SANDBOX/super-proj/subm" && run dir --ensure)"
  if [ -n "$SUB_ID" ] && [ "$SUB_ID" != "$SUPER_ID" ]; then
    ok "submodule resolves to its own id, distinct from the superproject"
  else
    fail "submodule id ($SUB_ID) matched or was empty vs superproject ($SUPER_ID)"
  fi
else
  echo "skip - submodule: 'git submodule add' unavailable in this environment"
fi

# --- 7. Moved repo -> store dir renamed, .root rewritten ---------------------------------------
new_repo "$SANDBOX/movable"
( cd "$SANDBOX/movable" && git remote add origin https://github.com/acme/movable.git )
OLD_DIR="$(cd "$SANDBOX/movable" && run dir --ensure)"
mv "$SANDBOX/movable" "$SANDBOX/movable-renamed"
NEW_DIR="$(cd "$SANDBOX/movable-renamed" && run dir --ensure)"
if [ "$OLD_DIR" != "$NEW_DIR" ] && [ ! -d "$OLD_DIR" ] && [ -d "$NEW_DIR" ] \
   && [ "$(cat "$NEW_DIR/.root" 2>/dev/null)" = "$SANDBOX/movable-renamed" ]; then
  ok "moved repo: store dir renamed and .root rewritten"
else
  fail "move detection failed: old=$OLD_DIR new=$NEW_DIR root=$(cat "$NEW_DIR/.root" 2>/dev/null)"
fi

# --- 8. Legacy .claude/plans + .qa migrated, including symlink re-pointing --------------------
new_repo "$SANDBOX/legacy"
mkdir -p "$SANDBOX/legacy/.claude/plans/20260101-000000-demo" "$SANDBOX/legacy/.claude/knowledge/mystore"
echo "plan" > "$SANDBOX/legacy/.claude/plans/20260101-000000-demo/plan.md"
echo "marker" > "$SANDBOX/legacy/.claude/plans/.active-somesession"
mkdir -p "$SANDBOX/legacy/.qa/knowledge" "$SANDBOX/legacy/.qa/reports"
echo "cfg" > "$SANDBOX/legacy/.qa/config.yml"
echo "nav" > "$SANDBOX/legacy/.qa/knowledge/navigation.md"
echo "report" > "$SANDBOX/legacy/.qa/reports/r.md"
rm -rf "$SANDBOX/legacy/.claude/knowledge/mystore"
ln -s "$(cd "$SANDBOX/legacy/.qa" && pwd -P)/knowledge" "$SANDBOX/legacy/.claude/knowledge/mystore"

QA_DIR="$(cd "$SANDBOX/legacy" && run qa --ensure)"
PLANS_DIR="$(cd "$SANDBOX/legacy" && run plans)"

pass8=1
# .claude/plans itself may legitimately survive containing only the skipped .active-*
# marker (rmdir refuses a non-empty dir) — assert the marker stayed behind, not that the
# whole legacy tree vanished.
[ -f "$SANDBOX/legacy/.claude/plans/.active-somesession" ] || pass8=0
[ -d "$SANDBOX/legacy/.qa" ] && pass8=0
[ -f "$PLANS_DIR/20260101-000000-demo/plan.md" ] || pass8=0
[ -f "$QA_DIR/config.yml" ] || pass8=0
[ -f "$QA_DIR/knowledge/navigation.md" ] || pass8=0
[ -f "$QA_DIR/reports/r.md" ] || pass8=0
[ "$(readlink "$SANDBOX/legacy/.claude/knowledge/mystore")" = "$QA_DIR/knowledge" ] || pass8=0
[ ! -e "$PLANS_DIR/.active-somesession" ] || pass8=0
if [ "$pass8" = 1 ]; then
  ok "legacy .claude/plans + .qa migrated, reverse-adoption symlink re-pointed"
else
  fail "legacy migration incomplete or symlink not re-pointed"
fi

# --- 9. Tracked .qa file -> nothing moved, warning printed --------------------------------------
new_repo "$SANDBOX/tracked"
mkdir -p "$SANDBOX/tracked/.qa"
echo "schema_version: 1" > "$SANDBOX/tracked/.qa/config.yml"
( cd "$SANDBOX/tracked" && git add -f .qa/config.yml && git commit -q -m tracked )
ERR="$(cd "$SANDBOX/tracked" && run qa --ensure 2>&1 >/dev/null)"
if [ -d "$SANDBOX/tracked/.qa" ] && [ -f "$SANDBOX/tracked/.qa/config.yml" ] \
   && printf '%s' "$ERR" | grep -q '^warn|tracked|'; then
  ok "tracked .qa/ file: nothing moved, warning printed"
else
  fail "tracked .qa/: expected untouched tree + warning, got: $ERR"
fi

# --- 9b. qa ancestor walk only matches an ANCESTOR that is actually qa-configured -------------
# An unconfigured ancestor's .root (from a plain `dir`/`plans --ensure`, unrelated to qa) must
# never capture a child repo's independent qa lookup.
mkdir -p "$SANDBOX/unconfigured-parent/child-repo"
( cd "$SANDBOX/unconfigured-parent" && run dir --ensure >/dev/null )
new_repo "$SANDBOX/unconfigured-parent/child-repo"
CHILD_QA="$(cd "$SANDBOX/unconfigured-parent/child-repo" && run qa --ensure)"
case "$(dirname "$(dirname "$CHILD_QA")")" in
  "$SANDBOX/unconfigured-parent"*) fail "unconfigured ancestor incorrectly captured the child's qa lookup ($CHILD_QA)" ;;
  *) ok "unconfigured ancestor (.root only, no config.yml) does not capture a child's qa lookup" ;;
esac

# --- 9c. A CONFIGURED ancestor workspace IS shared with a child repo lacking its own qa/ -------
mkdir -p "$SANDBOX/configured-ws/svc"
WS_QA="$(cd "$SANDBOX/configured-ws" && run qa --ensure)"
echo "schema_version: 1" > "$WS_QA/config.yml"
new_repo "$SANDBOX/configured-ws/svc"
SVC_QA="$(cd "$SANDBOX/configured-ws/svc" && run qa)"
if [ "$SVC_QA" = "$WS_QA" ]; then
  ok "configured ancestor workspace is reused by a child repo without its own qa/"
else
  fail "configured ancestor workspace was not reused: svc got $SVC_QA, workspace is $WS_QA"
fi

# --- 9d. checkout-root: workspace root via a configured ancestor, worktree toplevel otherwise --
SANDBOX_REAL="$(cd "$SANDBOX" && pwd -P)"
CR_SVC="$(cd "$SANDBOX/configured-ws/svc" && run checkout-root)"
[ "$CR_SVC" = "$SANDBOX_REAL/configured-ws" ] && ok "checkout-root from a workspace child is the workspace root" \
  || fail "checkout-root from workspace child: got $CR_SVC"
CR_WT="$(cd "$SANDBOX/repo-a-wt" && run checkout-root)"
[ "$CR_WT" = "$SANDBOX_REAL/repo-a-wt" ] && ok "checkout-root from a worktree is the worktree, not the main checkout" \
  || fail "checkout-root from worktree: got $CR_WT"
mkdir -p "$SANDBOX/cr-nogit"
BEFORE_CR="$(find "$HEROW_HOME" | sort)"
CR_NOGIT="$(cd "$SANDBOX/cr-nogit" && run checkout-root --ensure)"
[ "$CR_NOGIT" = "$SANDBOX_REAL/cr-nogit" ] && [ "$BEFORE_CR" = "$(find "$HEROW_HOME" | sort)" ] \
  && ok "checkout-root in a non-git dir is the cwd and never creates store dirs (even with --ensure)" \
  || fail "checkout-root non-git: got $CR_NOGIT or the store changed"

# --- 10. Nothing written outside HEROW_HOME (and outside the repo being migrated) ---------------
new_repo "$SANDBOX/isolation-check"
BEFORE_SANDBOX="$(find "$SANDBOX" -mindepth 1 -not -path "$HEROW_HOME*" 2>/dev/null | sort)"
BEFORE_REPO="$(find "$SANDBOX/isolation-check" 2>/dev/null | sort)"
( cd "$SANDBOX/isolation-check" && run qa --ensure >/dev/null )
AFTER_SANDBOX="$(find "$SANDBOX" -mindepth 1 -not -path "$HEROW_HOME*" 2>/dev/null | sort)"
AFTER_REPO="$(find "$SANDBOX/isolation-check" 2>/dev/null | sort)"
if [ "$BEFORE_SANDBOX" = "$AFTER_SANDBOX" ] && [ "$BEFORE_REPO" = "$AFTER_REPO" ]; then
  ok "no filesystem changes outside HEROW_HOME (repo tree untouched, no stray sandbox writes)"
else
  fail "unexpected filesystem changes outside HEROW_HOME"
fi

echo "----"
echo "$PASS passed, $FAIL failed"
[ "$FAIL" -eq 0 ]
