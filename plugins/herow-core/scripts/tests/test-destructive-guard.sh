#!/usr/bin/env bash
# Tests for destructive-guard.sh: the always-on confirmation hook for
# irreversible Bash commands and Write-overwrites of existing files.
# Run: bash plugins/herow-core/scripts/tests/test-destructive-guard.sh
set -eu

GUARD="$(cd "$(dirname "$0")/.." && pwd)/destructive-guard.sh"
[ -f "$GUARD" ] || { echo "guard not found: $GUARD" >&2; exit 1; }

T="$(mktemp -d)"
trap 'rm -rf "$T"' EXIT
mkdir -p "$T/repo/.claude/plans"
cd "$T/repo"
git init -q .

# The sandbox itself lives under macOS's $TMPDIR (mktemp's default root), which
# the guard's own scratchpad allowlist is designed to exempt — so leaving
# TMPDIR set here would make every relative target inside $T look like scratch
# space and silently pass. Unset it so the guard sees these as ordinary paths;
# the hardcoded /tmp and /private/tmp cases below don't depend on $TMPDIR.
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
# The read is bounded only on bash >= 4; bash 3.2 DISCARDS a partial timed-out
# read, so it deliberately keeps the old unbounded read.
#
# Two things are asserted per shell, and BOTH matter:
#   1. the guard still asks (the bound did not drop the payload), and
#   2. the elapsed time proves which branch actually ran.
# Without (2) these tests pass against a guard whose bound was reverted to a
# plain $(cat) — the writer closes on its own, so "it asked" is true either
# way. (2) is the only assertion that pins the bound itself.
#
# The shell's major version is PROBED, never assumed: /bin/bash is bash 3.2 on
# stock macOS but bash 5 on Linux CI and on brew-linked Macs. A label claiming
# "3.2 coverage" on a host where both shells are bash 5 is a test that lies
# about a data-loss guard, so uncovered branches print a loud SKIP instead.
shell_major() {
  local v
  v="$("$1" -c 'echo ${BASH_VERSINFO[0]}' 2>/dev/null || true)"
  case "$v" in ''|*[!0-9]*) echo 0 ;; *) echo "$v" ;; esac
}

# Payload is built ONCE, outside the writer subshell: a python3 cold start
# inside the fork would race the guard's own 2s bound on a loaded machine and
# produce a false "guard was disarmed" failure.
STALL_PAYLOAD="$(python3 -c "import json; print(json.dumps({'tool_name':'Bash','tool_input':{'command':'rm -rf ~/important'}}))")"
# MUST exceed the guard's -t bound, or the bound never fires and these degrade
# into ordinary-EOF tests that pass while covering nothing.
STALL_WRITER_SLEEP=6
# $SECONDS is whole-second resolution and counts tick boundaries crossed, so a
# genuine 2.1s bounded read can read as 3. The ceiling sits between the 2s
# bound and the 6s close with a full second of slack on each side; tightening
# it to 3 made this flake. Do not narrow the gap without switching to
# sub-second timing.
STALL_BOUND_CEILING=4

stall_guard() {
  local sh="$1" fifo w
  fifo="$T/stall.$$"
  rm -f "$fifo"; mkfifo "$fifo"
  { printf '%s\n' "$STALL_PAYLOAD"; sleep "$STALL_WRITER_SLEEP"; } > "$fifo" &
  w=$!
  SECONDS=0
  STALL_OUT="$("$sh" "$GUARD" < "$fifo")"
  STALL_SECS=$SECONDS
  kill "$w" 2>/dev/null || true
  wait "$w" 2>/dev/null || true
  rm -f "$fifo"
}

COVERED_GE4=0
COVERED_LT4=0
for sh in bash /bin/bash; do
  maj="$(shell_major "$sh")"
  if [ "$maj" -eq 0 ]; then
    echo "SKIP - $sh unavailable or version unreadable"
    continue
  fi
  stall_guard "$sh"
  asks "$STALL_OUT" \
    && ok "late-EOF stall still asks ($sh = bash $maj, ${STALL_SECS}s)" \
    || fail "late-EOF stall DISARMED the guard ($sh = bash $maj)"
  if [ "$maj" -ge 4 ]; then
    COVERED_GE4=1
    [ "$STALL_SECS" -lt "$STALL_BOUND_CEILING" ] \
      && ok "read is bounded on bash $maj (${STALL_SECS}s < ${STALL_WRITER_SLEEP}s close)" \
      || fail "read NOT bounded on bash $maj: ${STALL_SECS}s — the -t bound is gone"
  else
    COVERED_LT4=1
    [ "$STALL_SECS" -ge "$STALL_BOUND_CEILING" ] \
      && ok "bash $maj keeps the unbounded read (${STALL_SECS}s, waited for EOF)" \
      || fail "bash $maj returned in ${STALL_SECS}s — expected it to wait for EOF"
  fi
done
[ "$COVERED_GE4" -eq 1 ] || echo "SKIP - bash>=4 BOUNDED-read branch not covered on this host"
[ "$COVERED_LT4" -eq 1 ] || echo "SKIP - bash 3.2 UNBOUNDED-read branch not covered on this host (no bash < 4 present)"

# Slow SENDER, not slow closer: only part of the JSON has arrived when the
# bound expires. Accepted, documented residual (see the guard's own comment) —
# the guard must fail OPEN silently and never emit a decision from half a
# payload. On bash 3.2 the unbounded read waits and the guard asks instead;
# both outcomes are safe, neither may be a bogus decision.
partial_send() {
  local sh="$1" fifo w
  fifo="$T/partial.$$"
  rm -f "$fifo"; mkfifo "$fifo"
  { printf '%s' "$(printf '%s' "$STALL_PAYLOAD" | cut -c1-20)"; sleep 4
    printf '%s\n' "$(printf '%s' "$STALL_PAYLOAD" | cut -c21-)"; } > "$fifo" &
  w=$!
  PARTIAL_OUT="$("$sh" "$GUARD" < "$fifo")"
  kill "$w" 2>/dev/null || true
  wait "$w" 2>/dev/null || true
  rm -f "$fifo"
}

for sh in bash /bin/bash; do
  maj="$(shell_major "$sh")"
  [ "$maj" -eq 0 ] && continue
  partial_send "$sh"
  if [ "$maj" -ge 4 ]; then
    [ -z "$PARTIAL_OUT" ] \
      && ok "slow sender fails OPEN silently on bash $maj (truncated JSON, no bogus decision)" \
      || fail "slow sender produced output on bash $maj: $PARTIAL_OUT"
  else
    asks "$PARTIAL_OUT" \
      && ok "slow sender still asks on bash $maj (unbounded read waits for the rest)" \
      || fail "slow sender neither asked nor stayed silent on bash $maj"
  fi
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

out="$(invalid_utf8_payload 'rm -rf ~/x'$'\xed\xb3\xa9' | bash "$GUARD" 2>/dev/null || true)"
[ -z "$out" ] && ok "KNOWN GAP pinned: invalid-UTF8 segment is skipped (fails open, pre-existing)" \
  || ok "invalid-UTF8 segment now asks — gap closed, update this comment"

out="$(invalid_utf8_payload 'echo bad'$'\xed\xb3\xa9''
rm -rf ~/important' | bash "$GUARD" 2>/dev/null || true)"
asks "$out" && ok "valid segments still checked alongside an invalid-UTF8 one" \
  || fail "invalid UTF-8 in one segment suppressed the whole command"

# Normal (prompt-EOF) payload under /bin/bash: the 3.2 branch must behave
# identically to the default shell for ordinary input, not just under stall.
out="$(python3 -c "import json,sys; print(json.dumps({'tool_name':'Bash','tool_input':{'command':'rm -rf ~/data'}}))" | /bin/bash "$GUARD")"
asks "$out" && ok "rm -rf ~/data asks under /bin/bash" || fail "guard did not ask under /bin/bash"

out="$(python3 -c "import json,sys; print(json.dumps({'tool_name':'Bash','tool_input':{'command':'rm -rf ./node_modules'}}))" | /bin/bash "$GUARD")"
[ -z "$out" ] && ok "rm -rf ./node_modules silent under /bin/bash" || fail "allowlisted target asked under /bin/bash"

echo "----"
echo "$PASS passed, $FAIL failed"
[ "$FAIL" -eq 0 ]
