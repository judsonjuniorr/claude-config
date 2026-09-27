#!/usr/bin/env bash
# Tests for qa-setup/scripts/ensure-ignored.sh.
# Every case runs with HOME, XDG_CONFIG_HOME and GIT_CONFIG_GLOBAL pointed at a sandbox
# under the REAL $HOME, and GIT_CONFIG_NOSYSTEM=1 — so the suite never reads or writes the
# developer's actual global excludesfile. Asserted at the end: it is byte-identical after.
# Run: bash plugins/herow-dev/scripts/tests/test-qa-ensure-ignored.sh
set -u

SCRIPT="$(cd "$(dirname "$0")/../../skills/qa-setup/scripts" && pwd)/ensure-ignored.sh"
[ -f "$SCRIPT" ] || { echo "script not found: $SCRIPT" >&2; exit 1; }

REAL_HOME="$HOME"
REAL_EXCLUDES="$(git config --type=path --get core.excludesfile 2>/dev/null || true)"
REAL_SUM=""
if [ -n "$REAL_EXCLUDES" ] && [ -f "$REAL_EXCLUDES" ]; then
  REAL_SUM="$(shasum "$REAL_EXCLUDES" 2>/dev/null | awk '{print $1}')"
fi

SANDBOX="$REAL_HOME/.qa-ensure-ignored-test.$$"
mkdir -p "$SANDBOX"
cleanup() {
  # restore real env before exiting so trailing shell state is sane
  export HOME="$REAL_HOME"
  unset XDG_CONFIG_HOME GIT_CONFIG_GLOBAL GIT_CONFIG_SYSTEM GIT_CONFIG_NOSYSTEM
  rm -rf "$SANDBOX"
}
trap cleanup EXIT

PASS=0
FAIL=0
ok()   { PASS=$((PASS + 1)); echo "ok   - $1"; }
fail() { FAIL=$((FAIL + 1)); echo "FAIL - $1"; }

CASE=""
new_case() { # $1 = case name
  CASE="$SANDBOX/$1"
  mkdir -p "$CASE/home" "$CASE/xdg" "$CASE/proj"
  export HOME="$CASE/home"
  export XDG_CONFIG_HOME="$CASE/xdg"
  export GIT_CONFIG_GLOBAL="$CASE/home/.gitconfig"
  export GIT_CONFIG_NOSYSTEM=1
  unset GIT_CONFIG_SYSTEM
  : > "$GIT_CONFIG_GLOBAL"
}

run_script() { "$SCRIPT" "$@"; }

# --- 1. Literal ~ value ---------------------------------------------------------------------
new_case literal-tilde
printf '[core]\n\texcludesfile = ~/.gitignore\n' > "$GIT_CONFIG_GLOBAL"
if ! run_script --check "$CASE/proj" >/dev/null 2>&1; then
  ok "literal ~: --check reports not covered before apply"
else
  fail "literal ~: --check should not be covered yet"
fi
if run_script --apply "$CASE/proj" >/dev/null 2>&1 && grep -qxF '.qa/' "$HOME/.gitignore"; then
  ok "literal ~: --apply expands ~ and appends to \$HOME/.gitignore"
else
  fail "literal ~: expected \$HOME/.gitignore to contain '.qa/'"
fi

# --- 2. Value set through an include.path file ------------------------------------------------
new_case include-path
INCLUDED="$HOME/.gitconfig-included"
TARGET="$HOME/.git-ignore-included"
printf '[core]\n\texcludesfile = %s\n' "$TARGET" > "$INCLUDED"
printf '[include]\n\tpath = %s\n' "$INCLUDED" > "$GIT_CONFIG_GLOBAL"
if run_script --apply "$CASE/proj" >/dev/null 2>&1 && [ -f "$TARGET" ] && grep -qxF '.qa/' "$TARGET"; then
  ok "include.path: resolves the included excludesfile and appends there"
else
  fail "include.path: expected $TARGET to contain '.qa/'"
fi

# --- 3. System-scope value ---------------------------------------------------------------------
new_case system-scope
SYS_FILE="$SANDBOX/system-scope/gitconfig-system"
SYS_TARGET="$SANDBOX/system-scope/system-ignore"
mkdir -p "$(dirname "$SYS_FILE")"
printf '[core]\n\texcludesfile = %s\n' "$SYS_TARGET" > "$SYS_FILE"
: > "$GIT_CONFIG_GLOBAL"   # global has no excludesfile of its own
export GIT_CONFIG_SYSTEM="$SYS_FILE"
unset GIT_CONFIG_NOSYSTEM
if run_script --apply "$CASE/proj" >/dev/null 2>&1 && [ -f "$SYS_TARGET" ] && grep -qxF '.qa/' "$SYS_TARGET"; then
  ok "system scope: resolves core.excludesfile from GIT_CONFIG_SYSTEM"
else
  fail "system scope: expected $SYS_TARGET to contain '.qa/'"
fi
export GIT_CONFIG_NOSYSTEM=1
unset GIT_CONFIG_SYSTEM

# --- 4. Unset value, with XDG_CONFIG_HOME set ---------------------------------------------------
new_case unset-with-xdg
: > "$GIT_CONFIG_GLOBAL"
if run_script --apply "$CASE/proj" >/dev/null 2>&1 && [ -f "$XDG_CONFIG_HOME/git/ignore" ] && grep -qxF '.qa/' "$XDG_CONFIG_HOME/git/ignore"; then
  ok "unset + XDG_CONFIG_HOME: falls back to \$XDG_CONFIG_HOME/git/ignore (created)"
else
  fail "unset + XDG_CONFIG_HOME: expected \$XDG_CONFIG_HOME/git/ignore to exist and contain '.qa/'"
fi

# --- 5. Unset value, without XDG_CONFIG_HOME -----------------------------------------------------
new_case unset-without-xdg
: > "$GIT_CONFIG_GLOBAL"
unset XDG_CONFIG_HOME
if run_script --apply "$CASE/proj" >/dev/null 2>&1 && [ -f "$HOME/.config/git/ignore" ] && grep -qxF '.qa/' "$HOME/.config/git/ignore"; then
  ok "unset, no XDG_CONFIG_HOME: falls back to \$HOME/.config/git/ignore (created)"
else
  fail "unset, no XDG_CONFIG_HOME: expected \$HOME/.config/git/ignore to exist and contain '.qa/'"
fi
export XDG_CONFIG_HOME="$CASE/xdg"

# --- 6. File without trailing newline -------------------------------------------------------------
new_case no-trailing-newline
printf '[core]\n\texcludesfile = %s/.gitignore\n' "$HOME" > "$GIT_CONFIG_GLOBAL"
printf 'node_modules' > "$HOME/.gitignore"   # no trailing newline, no trailing pattern line
if run_script --apply "$CASE/proj" >/dev/null 2>&1; then
  CONTENT="$(cat "$HOME/.gitignore")"
  case "$CONTENT" in
    *$'node_modules\n.qa/'*) ok "no trailing newline: a newline is inserted before appending" ;;
    *) fail "no trailing newline: got unexpected content: $CONTENT" ;;
  esac
else
  fail "no trailing newline: --apply failed"
fi

# --- 7. Already covered by a glob → no append -----------------------------------------------------
new_case glob-covered
printf '[core]\n\texcludesfile = %s/.gitignore\n' "$HOME" > "$GIT_CONFIG_GLOBAL"
printf '**/.qa/\n' > "$HOME/.gitignore"
BEFORE="$(cat "$HOME/.gitignore")"
if run_script --apply "$CASE/proj" >/dev/null 2>&1; then
  AFTER="$(cat "$HOME/.gitignore")"
  if [ "$BEFORE" = "$AFTER" ]; then
    ok "glob covered: --apply is a no-op when a broader glob already matches"
  else
    fail "glob covered: file was modified even though already covered ($AFTER)"
  fi
else
  fail "glob covered: --apply should exit 0"
fi

# --- 8. Second --apply is a no-op -------------------------------------------------------------------
new_case idempotent-apply
: > "$GIT_CONFIG_GLOBAL"
printf '[core]\n\texcludesfile = %s/.gitignore\n' "$HOME" > "$GIT_CONFIG_GLOBAL"
run_script --apply "$CASE/proj" >/dev/null 2>&1
FIRST="$(cat "$HOME/.gitignore" 2>/dev/null || true)"
run_script --apply "$CASE/proj" >/dev/null 2>&1
SECOND="$(cat "$HOME/.gitignore" 2>/dev/null || true)"
if [ "$FIRST" = "$SECOND" ]; then
  ok "idempotent: second --apply does not duplicate the line"
else
  fail "idempotent: second --apply changed the file ($FIRST != $SECOND)"
fi

# --- 9. Tracked file under the pattern → exit 2 -----------------------------------------------------
new_case tracked
printf '[core]\n\texcludesfile = %s/.gitignore\n' "$HOME" > "$GIT_CONFIG_GLOBAL"
( cd "$CASE/proj" \
  && git init -q . \
  && git config user.email test@example.com \
  && git config user.name test \
  && mkdir -p .qa \
  && echo "schema_version: 1" > .qa/config.yml \
  && git add .qa/config.yml \
  && git commit -q -m "tracked qa config" )
run_script --apply "$CASE/proj" >/dev/null 2>&1  # covers the global side first
OUT="$(run_script --check "$CASE/proj" 2>&1)"
RC=$?
if [ "$RC" -eq 2 ] && printf '%s' "$OUT" | grep -q "rm -r --cached"; then
  ok "tracked: exit 2 with a git rm --cached fix"
else
  fail "tracked: expected exit 2 with a fix line, got rc=$RC out=$OUT"
fi

# --- 10. Unwritable excludesfile → exit 3 -----------------------------------------------------------
if [ "$(id -u)" != "0" ]; then
  new_case unwritable
  printf '[core]\n\texcludesfile = %s/.gitignore\n' "$HOME" > "$GIT_CONFIG_GLOBAL"
  : > "$HOME/.gitignore"
  chmod 400 "$HOME/.gitignore"
  OUT="$(run_script --apply "$CASE/proj" 2>&1)"
  RC=$?
  chmod 600 "$HOME/.gitignore"
  if [ "$RC" -eq 3 ]; then
    ok "unwritable: exit 3 with a clear cause"
  else
    fail "unwritable: expected exit 3, got rc=$RC out=$OUT"
  fi
else
  echo "skip - unwritable: running as root, permission bits are meaningless"
fi

# --- 11. --check never writes -----------------------------------------------------------------------
new_case check-never-writes
: > "$GIT_CONFIG_GLOBAL"
unset XDG_CONFIG_HOME
run_script --check "$CASE/proj" >/dev/null 2>&1
if [ ! -e "$HOME/.config/git/ignore" ]; then
  ok "--check never writes: no fallback file created"
else
  fail "--check never writes: fallback file was created by --check"
fi
export XDG_CONFIG_HOME="$CASE/xdg"

# --- 12. Symlinked excludesfile → appended through the link, link intact -----------------------------
new_case symlinked
mkdir -p "$HOME/.dotfiles"
: > "$HOME/.dotfiles/gitignore"
ln -s "$HOME/.dotfiles/gitignore" "$HOME/.gitignore"
printf '[core]\n\texcludesfile = ~/.gitignore\n' > "$GIT_CONFIG_GLOBAL"
if run_script --apply "$CASE/proj" >/dev/null 2>&1 \
   && [ -L "$HOME/.gitignore" ] \
   && grep -qxF '.qa/' "$HOME/.dotfiles/gitignore"; then
  ok "symlinked excludesfile: appended through the link, link left intact"
else
  fail "symlinked excludesfile: expected the link intact and the real target updated"
fi

# --- 13. Custom --pattern (e.g. blueprint's .claude/plans/) -------------------------------------------
new_case custom-pattern
: > "$GIT_CONFIG_GLOBAL"
printf '[core]\n\texcludesfile = %s/.gitignore\n' "$HOME" > "$GIT_CONFIG_GLOBAL"
if run_script --apply "$CASE/proj" --pattern .claude/plans/ >/dev/null 2>&1 \
   && grep -qxF '.claude/plans/' "$HOME/.gitignore" \
   && ! grep -qxF '.qa/' "$HOME/.gitignore"; then
  ok "custom pattern: appends the given pattern, not the default"
else
  fail "custom pattern: expected only '.claude/plans/' in the excludesfile"
fi

echo
echo "$PASS passed, $FAIL failed"

# --- Real excludesfile must be untouched by the whole suite -------------------------------------------
export HOME="$REAL_HOME"
unset XDG_CONFIG_HOME GIT_CONFIG_GLOBAL GIT_CONFIG_SYSTEM GIT_CONFIG_NOSYSTEM
POST_EXCLUDES="$(git config --type=path --get core.excludesfile 2>/dev/null || true)"
if [ -n "$REAL_SUM" ]; then
  POST_SUM="$(shasum "$POST_EXCLUDES" 2>/dev/null | awk '{print $1}')"
  if [ "$POST_SUM" = "$REAL_SUM" ]; then
    echo "ok   - real excludesfile byte-identical after the suite"
  else
    echo "FAIL - real excludesfile CHANGED by the suite ($REAL_EXCLUDES)"
    FAIL=$((FAIL + 1))
  fi
fi

[ "$FAIL" -eq 0 ]
