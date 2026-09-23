#!/usr/bin/env bash
# Tests for destructive-guard.sh: the always-on confirmation hook for
# irreversible Bash commands and Write-overwrites of existing files.
# Run: bash plugins/herow-core/scripts/tests/test-destructive-guard.sh
set -eu

GUARD="$(cd "$(dirname "$0")/.." && pwd)/destructive-guard.sh"
[ -f "$GUARD" ] || { echo "guard not found: $GUARD" >&2; exit 1; }

# The sandbox must NOT live under a path the guard allowlists as scratch
# space, or every relative target inside it silently passes and the Write and
# compound-command cases assert nothing. `mktemp -d` defaults to $TMPDIR, which
# is /var/folders/... on macOS (harmless) but /tmp on Linux — and the guard
# hardcodes /tmp and /private/tmp alongside $TMPDIR. That difference hid three
# broken assertions until these suites started running in CI on ubuntu.
# $HOME is not allowlisted on either platform.
T="$(mktemp -d "${HOME}/.destructive-guard-test.XXXXXXXX")"
trap 'rm -rf "$T"' EXIT
mkdir -p "$T/repo/.claude/plans"
cd "$T/repo"
git init -q .

# Belt and braces with the sandbox relocation above: an inherited $TMPDIR would
# exempt targets inside it the same way. Unset it so the guard sees these as
# ordinary paths; the hardcoded /tmp and /private/tmp cases below pass literal
# paths and do not depend on $TMPDIR.
unset TMPDIR

PASS=0
FAIL=0
ok()   { PASS=$((PASS + 1)); echo "ok   - $1"; }
fail() { FAIL=$((FAIL + 1)); echo "FAIL - $1"; }

run_bash() {
  python3 -c "import json,sys; print(json.dumps({'tool_name':'Bash','tool_input':{'command':sys.argv[1]}}))" "$1" | bash "$GUARD"
}
run_write() {
  python3 -c "import json,sys; print(json.dumps({'tool_name':'Write','tool_input':{'file_path':sys.argv[1]}}))" "$1" | bash "$GUARD"
}

asks() { printf '%s' "$1" | grep -q permissionDecision; }

# --- Bash: rm/rmdir allowlist semantics ------------------------------------

out="$(run_bash 'rm -rf ~/data')"
asks "$out" && ok "rm -rf ~/data asks" || fail "rm -rf ~/data did not ask"

out="$(run_bash 'rm -rf ./node_modules')"
[ -z "$out" ] && ok "rm -rf ./node_modules silent" || fail "rm -rf ./node_modules asked"

out="$(run_bash 'rm -rf /tmp/scratch/x')"
[ -z "$out" ] && ok "rm -rf /tmp/scratch/x silent" || fail "rm -rf /tmp/scratch/x asked"

out="$(run_bash 'rm -rf dist build .next')"
[ -z "$out" ] && ok "rm -rf dist build .next silent (all allowlisted)" || fail "rm -rf dist build .next asked"

out="$(run_bash 'rm -rf node_modules ~/important')"
asks "$out" && ok "rm -rf node_modules ~/important asks (mixed list, ALL not ANY)" \
  || fail "rm -rf node_modules ~/important did NOT ask — mixed-target allowlist bug"

out="$(run_bash 'rm -r -f dist')"
[ -z "$out" ] && ok "rm -r -f dist silent (split flags)" || fail "rm -r -f dist asked"

out="$(run_bash 'rm --recursive --force dist')"
[ -z "$out" ] && ok "rm --recursive --force dist silent (long flags)" || fail "rm --recursive --force dist asked"

out="$(run_bash 'cd foo && rm -rf bar')"
asks "$out" && ok "compound 'cd foo && rm -rf bar' asks" || fail "compound command bypassed the guard"

out="$(run_bash 'rm -rf node_modules/../../important')"
asks "$out" && ok "traversal 'node_modules/../../important' asks" || fail "traversal defeated the allowlist"

out="$(run_bash 'rm -rf $(cat targets.txt)')"
asks "$out" && ok "unexpanded substitution asks" || fail "substitution target was silently allowed"

out="$(run_bash 'rm -rf')"
[ -z "$out" ] && ok "bare 'rm -rf' (no target) silent" || fail "bare 'rm -rf' behavior changed"

out="$(run_bash 'rm -rf $HOME')"
asks "$out" && ok "rm -rf \$HOME (literal) asks" || fail "rm -rf \$HOME did not ask"

out="$(run_bash 'rm -rf `cat targets.txt`')"
asks "$out" && ok "unexpanded backtick substitution asks" || fail "backtick substitution was silently allowed"

out="$(run_bash 'rm -rf <(cat targets.txt)')"
asks "$out" && ok "unexpanded process substitution <( ) asks" || fail "process substitution <( ) was silently allowed"

touch important.log
out="$(run_bash 'rm -rf important.log')"
[ -z "$out" ] && ok "rm -rf *.log (suffix allowlist) silent" || fail "rm -rf *.log asked"
rm -f important.log

mkdir -p "$T/scratch-tmpdir"
out="$(TMPDIR="$T/scratch-tmpdir" run_bash "rm -rf $T/scratch-tmpdir/leftover")"
[ -z "$out" ] && ok "rm -rf under \$TMPDIR silent" || fail "rm -rf under \$TMPDIR asked"

out="$(run_bash "rm -rf 'unterminated)")"
asks "$out" && ok "shlex parse error (unbalanced quote) asks" || fail "unbalanced quote did not ask"

# --- Regression: adversarial-review bypasses (fixed) -------------------

out="$(python3 -c "import json,sys; print(json.dumps({'tool_name':'Bash','tool_input':{'command':'echo start\nrm -rf ~/important-data\necho done'}}))" | bash "$GUARD")"
asks "$out" && ok "multi-line command (embedded newline) asks — was silently truncated to line 1" \
  || fail "multi-line command bypassed the guard"

out="$(run_bash 'RM -rf ~/important-data')"
asks "$out" && ok "uppercase RM -rf asks (case-insensitive command anchor)" || fail "uppercase RM -rf bypassed the guard"

out="$(run_bash 'Git Push --Force')"
asks "$out" && ok "mixed-case 'Git Push --Force' asks" || fail "mixed-case git push --force bypassed the guard"

out="$(run_bash 'unlink ~/important-file.txt')"
asks "$out" && ok "unlink asks" || fail "unlink did not ask"

out="$(run_bash 'git reflog expire --expire=now --all')"
asks "$out" && ok "git reflog expire asks" || fail "git reflog expire did not ask"

out="$(run_bash 'git gc --prune=now')"
asks "$out" && ok "git gc --prune=now asks" || fail "git gc --prune=now did not ask"

out="$(run_bash 'git filter-branch --force --index-filter foo')"
asks "$out" && ok "git filter-branch asks" || fail "git filter-branch did not ask"

out="$(run_bash 'rtk rm -rf ~/data')"
asks "$out" && ok "rtk-wrapped rm -rf ~/data asks" || fail "rtk wrapper bypassed the guard"

out="$(run_bash 'rtk proxy rm -rf ~/data')"
asks "$out" && ok "rtk proxy-wrapped rm -rf ~/data asks" || fail "rtk proxy wrapper bypassed the guard"

out="$(run_bash 'echo hi; rm -rf ~/data')"
asks "$out" && ok "semicolon-chained rm -rf asks" || fail "semicolon compound bypassed the guard"

# --- Bash: other file-deletion patterns (find/shred/dd) --------------------

out="$(run_bash "find . -name '*.bak' -delete")"
asks "$out" && ok "find -delete asks" || fail "find -delete did not ask"

out="$(run_bash 'shred -u secret.txt')"
asks "$out" && ok "shred asks" || fail "shred did not ask"

out="$(run_bash 'dd if=/dev/zero of=/dev/sda')"
asks "$out" && ok "dd of= asks" || fail "dd of= did not ask"

# --- Bash: other destructive families ---------------------------------------

out="$(run_bash 'psql -c "DELETE FROM users"')"
asks "$out" && ok "psql DELETE FROM asks" || fail "psql DELETE FROM did not ask"

out="$(run_bash 'psql -c "DROP TABLE users"')"
asks "$out" && ok "psql DROP TABLE asks" || fail "psql DROP TABLE did not ask"

out="$(run_bash 'psql -c "TRUNCATE users"')"
asks "$out" && ok "psql TRUNCATE asks" || fail "psql TRUNCATE did not ask"

out="$(run_bash 'psql -c "SELECT * FROM users"')"
[ -z "$out" ] && ok "psql SELECT silent" || fail "psql SELECT asked"

out="$(run_bash 'git push --force')"
asks "$out" && ok "git push --force asks" || fail "git push --force did not ask"

out="$(run_bash 'git push --force-with-lease')"
[ -z "$out" ] && ok "git push --force-with-lease silent" || fail "git push --force-with-lease asked"

out="$(run_bash 'git clean -fd')"
asks "$out" && ok "git clean -fd asks" || fail "git clean -fd did not ask"

out="$(run_bash 'git reset --hard HEAD~1')"
asks "$out" && ok "git reset --hard asks" || fail "git reset --hard did not ask"

out="$(run_bash 'git checkout -- .')"
asks "$out" && ok "git checkout -- . asks" || fail "git checkout -- . did not ask"

out="$(run_bash 'git branch -D feature-x')"
asks "$out" && ok "git branch -D asks" || fail "git branch -D did not ask"

out="$(run_bash 'git stash drop')"
asks "$out" && ok "git stash drop asks" || fail "git stash drop did not ask"

out="$(run_bash 'git stash clear')"
asks "$out" && ok "git stash clear asks" || fail "git stash clear did not ask"

out="$(run_bash 'git worktree remove foo --force')"
asks "$out" && ok "git worktree remove --force asks" || fail "git worktree remove --force did not ask"

out="$(run_bash 'redis-cli flushall')"
asks "$out" && ok "redis-cli flushall asks" || fail "redis-cli flushall did not ask"

out="$(run_bash 'prisma migrate reset')"
asks "$out" && ok "prisma migrate reset asks" || fail "prisma migrate reset did not ask"

out="$(run_bash 'supabase db reset')"
asks "$out" && ok "supabase db reset asks" || fail "supabase db reset did not ask"

out="$(run_bash 'bin/rails db:drop')"
asks "$out" && ok "rails db:drop asks" || fail "rails db:drop did not ask"

out="$(run_bash 'alembic downgrade base')"
asks "$out" && ok "alembic downgrade base asks" || fail "alembic downgrade base did not ask"

out="$(run_bash 'terraform destroy')"
asks "$out" && ok "terraform destroy asks" || fail "terraform destroy did not ask"

out="$(run_bash 'kubectl delete pod foo')"
asks "$out" && ok "kubectl delete asks" || fail "kubectl delete did not ask"

out="$(run_bash 'aws s3 rm s3://bucket --recursive')"
asks "$out" && ok "aws s3 rm --recursive asks" || fail "aws s3 rm --recursive did not ask"

out="$(run_bash 'docker system prune -a')"
asks "$out" && ok "docker system prune asks" || fail "docker system prune did not ask"

out="$(run_bash 'gh repo delete owner/repo')"
asks "$out" && ok "gh repo delete asks" || fail "gh repo delete did not ask"

out="$(run_bash 'gh secret delete FOO')"
asks "$out" && ok "gh secret delete asks" || fail "gh secret delete did not ask"

out="$(run_bash 'npm test')"
[ -z "$out" ] && ok "npm test silent (perf gate)" || fail "npm test asked"

out="$(run_bash 'ls -la')"
[ -z "$out" ] && ok "ls -la silent (perf gate)" || fail "ls -la asked"

out="$(python3 -c "import json,sys; print(json.dumps({'tool_name':'Bash','tool_input':{}}))" | bash "$GUARD")"
[ -z "$out" ] && ok "Bash with no command field silent" || fail "Bash with no command field produced output"

out="$(python3 -c "import json,sys; print(json.dumps({'tool_name':'Edit','tool_input':{'file_path':'foo.txt'}}))" | bash "$GUARD")"
[ -z "$out" ] && ok "Edit tool_name silent (not Bash/Write)" || fail "Edit tool_name produced output"

# --- Write: existing-file-overwrite semantics -------------------------------

echo "hello" > "$T/repo/existing.txt"
out="$(run_write "$T/repo/existing.txt")"
asks "$out" && ok "Write over existing non-empty file asks" || fail "Write overwrite did not ask"

out="$(run_write "$T/repo/brand-new.txt")"
[ -z "$out" ] && ok "Write to nonexistent path silent" || fail "Write to nonexistent path asked"

: > "$T/repo/empty.txt"
out="$(run_write "$T/repo/empty.txt")"
[ -z "$out" ] && ok "Write over empty file silent" || fail "Write over empty file asked"

echo "plan content" > "$T/repo/.claude/plans/x.md"
out="$(run_write "$T/repo/.claude/plans/x.md")"
[ -z "$out" ] && ok "Write over .claude/plans/x.md silent" || fail "Write over plan file asked"

mkdir -p "$T/repo/dist"
echo "bundled" > "$T/repo/dist/bundle.js"
out="$(run_write "$T/repo/dist/bundle.js")"
[ -z "$out" ] && ok "Write over dist/bundle.js (allowlisted dir) silent" || fail "Write over allowlisted dir file asked"

echo "old log" > "$T/repo/app.log"
out="$(run_write "$T/repo/app.log")"
[ -z "$out" ] && ok "Write over app.log (allowlisted suffix) silent" || fail "Write over allowlisted suffix file asked"

echo "placeholder" > "$T/repo/relative-existing.txt"
out="$(run_write "relative-existing.txt")"
asks "$out" && ok "Write over relative existing file asks (PWD-join)" || fail "relative Write path did not ask"

out="$(python3 -c "import json,sys; print(json.dumps({'tool_name':'Write','tool_input':{'file_path':''}}))" | bash "$GUARD")"
[ -z "$out" ] && ok "Write with empty file_path silent" || fail "Write with empty file_path produced output"

# --- Fail-open on malformed input -------------------------------------------

out="$(printf '' | bash "$GUARD")"
[ -z "$out" ] && ok "empty stdin silent, exit 0" || fail "empty stdin produced output"

out="$(printf 'not json' | bash "$GUARD")"
[ -z "$out" ] && ok "malformed stdin silent, exit 0" || fail "malformed stdin produced output"

# --- Bounded stdin read: bound must EXIST and must not disarm the guard -----
# The guard bounds its stdin read so a harness slow to CLOSE stdin costs ~2s
# instead of the full 10s hook timeout. That stall shape is a LATE EOF: the
# payload has already arrived and only the close is pending, so the guard must
# still evaluate the real command and ask. "Returns fast but silently
# unguarded" is the one outcome that must never happen in a data-loss guard.
#
# The bound lives INSIDE the guard's python3 call, which reads in blocks
# against a wall-clock deadline and keeps what arrived. That behaves the same
# on bash 3.2 and bash 5, so there is no version branch to cover any more --
# but the shell is still probed and printed, because the guard must keep
# working under stock macOS /bin/bash as well as a brew bash.
#
# Two things are asserted per shell, and BOTH matter:
#   1. the guard still asks (the bound did not drop the payload), and
#   2. the elapsed time proves the bound actually fired.
# Without (2) these tests pass against a guard whose bound was removed — the
# writer closes on its own, so "it asked" is true either way. (2) is the only
# assertion that pins the bound itself.
shell_major() {
  local v
  v="$("$1" -c 'echo ${BASH_VERSINFO[0]}' 2>/dev/null || true)"
  case "$v" in ''|*[!0-9]*) echo 0 ;; *) echo "$v" ;; esac
}

# Payload is built ONCE, outside the writer subshell: a python3 cold start
# inside the fork would race the guard's own 2s bound on a loaded machine and
# produce a false "guard was disarmed" failure.
STALL_PAYLOAD="$(python3 -c "import json; print(json.dumps({'tool_name':'Bash','tool_input':{'command':'rm -rf ~/important'}}))")"
# MUST exceed the guard's bound, or the bound never fires and these degrade
# into ordinary-EOF tests that pass while covering nothing.
STALL_WRITER_SLEEP=6
# $SECONDS is whole-second resolution and counts tick boundaries crossed, so a
# genuine 2.1s bounded read can read as 3. The ceiling sits between the 2s
# bound and the 6s close with two seconds of slack on each side; at 3 (one
# second of slack below) this flaked. Do not narrow the gap without switching
# to sub-second timing.
STALL_BOUND_CEILING=4

# One FIFO harness for both stall shapes. `writer` is the name of a function
# that writes the payload into the pipe; it runs in the background and is
# reaped here, so each case only has to describe its own write pattern.
feed_guard() {
  local sh="$1" writer="$2" fifo w
  fifo="$T/feed.$$"
  rm -f "$fifo"; mkfifo "$fifo"
  "$writer" > "$fifo" &
  w=$!
  SECONDS=0
  FEED_OUT="$("$sh" "$GUARD" < "$fifo")"
  FEED_SECS=$SECONDS
  kill "$w" 2>/dev/null || true
  wait "$w" 2>/dev/null || true
  rm -f "$fifo"
}

# LATE EOF: the whole payload arrives at once, only the close is pending.
write_late_eof() { printf '%s\n' "$STALL_PAYLOAD"; sleep "$STALL_WRITER_SLEEP"; }

# Slow SENDER, not slow closer: only part of the JSON has arrived when the
# bound expires. Accepted, documented residual (see the guard's own comment) —
# the guard must fail OPEN silently and never emit a decision from half a
# payload.
write_slow_sender() {
  printf '%s' "$(printf '%s' "$STALL_PAYLOAD" | cut -c1-20)"
  sleep 4
  printf '%s\n' "$(printf '%s' "$STALL_PAYLOAD" | cut -c21-)"
}

COVERED_SHELLS=0
for sh in bash /bin/bash; do
  maj="$(shell_major "$sh")"
  if [ "$maj" -eq 0 ]; then
    echo "SKIP - $sh unavailable or version unreadable"
    continue
  fi
  COVERED_SHELLS=$((COVERED_SHELLS + 1))

  feed_guard "$sh" write_late_eof
  asks "$FEED_OUT" \
    && ok "late-EOF stall still asks ($sh = bash $maj, ${FEED_SECS}s)" \
    || fail "late-EOF stall DISARMED the guard ($sh = bash $maj)"
  [ "$FEED_SECS" -lt "$STALL_BOUND_CEILING" ] \
    && ok "read is bounded on bash $maj (${FEED_SECS}s < ${STALL_WRITER_SLEEP}s close)" \
    || fail "read NOT bounded on bash $maj: ${FEED_SECS}s — the bound is gone"

  feed_guard "$sh" write_slow_sender
  [ -z "$FEED_OUT" ] \
    && ok "slow sender fails OPEN silently on bash $maj (truncated JSON, no bogus decision)" \
    || fail "slow sender produced output on bash $maj: $FEED_OUT"
done
[ "$COVERED_SHELLS" -gt 0 ] || fail "no usable bash found; the read bound was never exercised"

# --- Payload SIZE must not bound the read ----------------------------------
# Regression pin. A previous bound used bash `read -r -d '' -t 2`, which drains
# a NON-SEEKABLE fd one byte per read(2) syscall (~1MB/s). That turned the
# wall-clock bound into a payload-size cap: past roughly 2MB the JSON arrived
# truncated, the parse failed, and the guard exited with NO decision — a large
# Write silently clobbering an existing file. `tool_input.content` carries the
# whole file body, so this is ordinary input, not an adversarial one.
#
# It reproduces ONLY over a pipe: with `< file` the fd is seekable and bash
# reads in bulk, which is why it has to be piped here.
SIZE_TARGET="$T/repo/size-victim.txt"
echo "existing content" > "$SIZE_TARGET"
for mb in 3 6; do
  for sh in bash /bin/bash; do
    [ "$(shell_major "$sh")" -eq 0 ] && continue
    out="$(python3 -c "
import json, sys
n = int(sys.argv[1]) * 1000000
print(json.dumps({'tool_name':'Write','tool_input':{'file_path':sys.argv[2],'content':'x'*n}}))" "$mb" "$SIZE_TARGET" | "$sh" "$GUARD")"
    asks "$out" \
      && ok "${mb}MB Write over a pipe still asks ($sh)" \
      || fail "${mb}MB Write over a pipe produced no decision ($sh) — the read is size-bounded again"
  done
done

# --- Normal path must not pay the bound ------------------------------------
# The common case is ~100% of calls. A read that stopped seeing EOF would pass
# every assertion above while making every Bash call wait the full bound —
# strictly worse than the 10s stall this bound exists to fix.
for sh in bash /bin/bash; do
  [ "$(shell_major "$sh")" -eq 0 ] && continue
  SECONDS=0
  out="$(printf '%s\n' "$STALL_PAYLOAD" | "$sh" "$GUARD")"
  el=$SECONDS
  asks "$out" && [ "$el" -lt 2 ] \
    && ok "ordinary payload returns immediately on $sh (${el}s, no bound paid)" \
    || fail "ordinary payload took ${el}s on $sh (decision: ${out:-none})"
done

# KNOWN GAP, pre-existing and deliberately pinned: a command carrying invalid
# UTF-8 (a lone surrogate) makes the segment loop's `sed`/`grep` abort with
# "illegal byte sequence" under a UTF-8 locale, so that segment is skipped and
# a destructive command in it is MISSED. Verified present before this change
# too (the old three-python3 extraction crashed on the text-mode write and
# dropped the whole command instead), so this is not a regression -- and the
# base64 framing is strictly better here, because segments WITHOUT invalid
# bytes still get checked. Not fixed in this pass: the obvious fix, forcing
# LC_ALL=C, cannot be applied globally because it would make python3 read
# stdin as ASCII and break every legitimately non-ASCII payload (verified: an
# emoji command currently guards correctly). Fixing it means scoping the
# locale to the matching calls only. These two cases pin both halves so the
# behavior cannot silently change.
invalid_utf8_payload() {
  python3 -c "
import json, sys
s = json.dumps({'tool_name':'Bash','tool_input':{'command':sys.argv[1]}})
sys.stdout.buffer.write(s.encode('utf-8','surrogatepass') + b'\n')" "$1"
}

out="$(invalid_utf8_payload 'rm -rf ~/x'$'\xed\xb3\xa9' | bash "$GUARD" 2>"$T/utf8.err")"
rc=$?
[ "$rc" -eq 0 ] || fail "guard exited $rc on invalid UTF-8: $(cat "$T/utf8.err")"
# Both outcomes below are acceptable, but they are NOT the same outcome, so
# each gets its own assertion and anything else FAILS. The earlier version
# called ok() on both arms, which meant a malformed or truncated decision also
# counted as a pass — the case pinned nothing while inflating the count.
if [ -z "$out" ]; then
  ok "KNOWN GAP pinned: invalid-UTF8 segment is skipped (fails open, pre-existing)"
elif asks "$out"; then
  ok "invalid-UTF8 segment now asks — gap closed, update this comment"
else
  fail "invalid-UTF8 segment produced a malformed decision: $out"
fi

out="$(invalid_utf8_payload 'echo bad'$'\xed\xb3\xa9''
rm -rf ~/important' | bash "$GUARD" 2>"$T/utf8.err")"
rc=$?
[ "$rc" -eq 0 ] || fail "guard exited $rc on invalid UTF-8 (mixed segments): $(cat "$T/utf8.err")"
asks "$out" && ok "valid segments still checked alongside an invalid-UTF8 one" \
  || fail "invalid UTF-8 in one segment suppressed the whole command"

# Normal (prompt-EOF) payload under /bin/bash: the 3.2 branch must behave
# identically to the default shell for ordinary input, not just under stall.
out="$(python3 -c "import json,sys; print(json.dumps({'tool_name':'Bash','tool_input':{'command':'rm -rf ~/data'}}))" | /bin/bash "$GUARD")"
asks "$out" && ok "rm -rf ~/data asks under /bin/bash" || fail "guard did not ask under /bin/bash"

out="$(python3 -c "import json,sys; print(json.dumps({'tool_name':'Bash','tool_input':{'command':'rm -rf ./node_modules'}}))" | /bin/bash "$GUARD")"
[ -z "$out" ] && ok "rm -rf ./node_modules silent under /bin/bash" || fail "allowlisted target asked under /bin/bash"

# --- base64 decode path: the -D fallback and the no-decoder case -----------
# `-d` is the GNU/newer-macOS decode flag; older macOS base64 only has `-D`.
# On every host where `-d` works — all of CI, every modern Mac — a typo in the
# `-D` fallback is invisible. These shim a fake `base64` onto PATH to force
# each branch.
B64_SHIM="$T/b64shim"
mkdir -p "$B64_SHIM"

# A base64 that rejects -d and only understands -D, like older macOS. It
# translates -D to the real binary's -d rather than passing it through: GNU
# base64 (every Linux runner) has no -D, so a pass-through shim would test
# nothing there.
REAL_B64="$(command -v base64)"
cat > "$B64_SHIM/base64" <<SHIM
#!/bin/sh
args=""
for a in "\$@"; do
  [ "\$a" = "-d" ] && exit 1
  [ "\$a" = "-D" ] && a="-d"
  args="\$args \$a"
done
exec "$REAL_B64" \$args
SHIM
chmod +x "$B64_SHIM/base64"
out="$(PATH="$B64_SHIM:$PATH" run_bash 'rm -rf ~/data')"
asks "$out" && ok "base64 -D fallback still guards (no -d support)" \
  || fail "guard went silent when base64 lacked -d — the -D fallback is broken"

# No usable base64 at all: the guard must fail OPEN (exit 0, no decision) and
# say why on stderr, rather than disarming itself invisibly on every call.
cat > "$B64_SHIM/base64" <<'SHIM'
#!/bin/sh
exit 127
SHIM
chmod +x "$B64_SHIM/base64"
out="$(PATH="$B64_SHIM:$PATH" run_bash 'rm -rf ~/data' 2>"$T/b64.err")"
rc=$?
[ "$rc" -eq 0 ] && [ -z "$out" ] \
  && ok "missing base64 fails OPEN (documented), exit 0" \
  || fail "missing base64: expected silent exit 0, got rc=$rc out=$out"
grep -q base64 "$T/b64.err" \
  && ok "missing base64 leaves a stderr breadcrumb instead of disarming silently" \
  || fail "missing base64 produced no diagnostic: $(cat "$T/b64.err")"
rm -rf "$B64_SHIM"

echo "----"
echo "$PASS passed, $FAIL failed"
[ "$FAIL" -eq 0 ]
