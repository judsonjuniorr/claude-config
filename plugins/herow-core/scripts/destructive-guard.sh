#!/usr/bin/env bash
# claude-config PreToolUse/(Bash|Write) guard.
# Always-on confirmation before an irreversible Bash command (file/git-history/
# SQL/datastore/cloud deletion) or a Write that overwrites an existing
# non-empty file. Surfaces a permission prompt ("ask") so destruction becomes
# a conscious choice instead of a silent `defaultMode: auto` pass-through.
#
# Boundary vs. gstack's /careful skill: /careful covers similar Bash patterns
# but is opt-in and session-scoped (its own SKILL.md: "To deactivate, end the
# conversation or start a new one"). This hook is always-on and has no
# invocation step. If /careful is also active in a session, an `rm -rf` can
# surface two prompts — accepted, not a bug; a doubled prompt is the safe
# direction, and narrowing this guard's coverage to dodge it would reopen the
# gap /careful leaves when it isn't invoked.
#
# Boundary vs. git-guard.sh (same PreToolUse/Bash matcher): git-guard denies
# Claude-attribution in commits/PRs and fast-allows read-only gh/glab; it has
# zero coverage of `rm`/SQL/cloud deletion, so there is no overlap with the
# families this guard checks.
#
# Write-side overlap (confirmed by piping identical payloads through all
# three scripts): an overwrite of an existing tsconfig.json also asks via
# config-protection.sh, and an overwrite of an existing *.md also asks via
# doc-file-warning.sh. Accepted, not fixed here — each hook is independently
# correct and narrowing this guard's file-clobber check to dodge those two
# would reopen it for every other file type. Whether Claude Code coalesces
# two simultaneous `ask` decisions into one prompt or shows both is outside
# this repo's control; a doubled prompt is still the safe direction.
#
# Deliberately NOT covered (decisions, not oversights): shell `>` redirect
# clobber (fires on ordinary `cmd > out.txt`, too noisy), `mv` over an
# existing file, `git rm`, `git restore`, MCP delete tools (Organizze/Gmail/
# Calendar — a different matcher shape, left for a future pass), Edit calls
# (no large-deletion heuristic here). Composition residual: the Write branch's
# "existing non-empty file" check is stateless, so a prior `: > file` shell
# truncation (itself excluded above) followed by a Write to the same path is
# silently allowed — the guard has no way to know the file held real content
# moments earlier.
#
# Accepted limitation, not a gap to chase: any command indirection — `sh -c`,
# `bash -c`, `xargs`, `env`, `command`, a leading `\`, variable or function
# indirection (`x=$(echo rm); $x -rf ~`) — defeats the `^command` anchors
# below. Closing this needs real shell parsing or execution-time
# interception, not a bigger regex; this is a heuristic UX guard, not a
# sandbox, same framing as git-guard.sh's own documented residuals. Command-
# name matching is also case-insensitive (`RM -rf` asks same as `rm -rf`) but
# `check_rm_segment`'s path/allowlist matching stays case-sensitive by
# design — a directory literally named `Node_Modules` should not silently
# inherit the `node_modules` allowlist entry.
#
# The build/dep-artifact allowlist matches by directory NAME anywhere in the
# resolved path, not by contents — a target that merely happens to be named
# `target`/`build`/`cache`/etc. for unrelated reasons gets the same pass as
# a real build directory. Accepted: tightening to "only when it's the
# target's own basename" trades a rare naming collision for prompting on
# routine nested cleanup (`rm -rf node_modules/.cache/x`), which is worse.
#
# TOCTOU: the realpath/size checks below are a snapshot at hook time: a
# symlink swap or file replacement between the "ask" decision and the tool
# actually executing could change what gets destroyed. Theoretical in a
# single-agent session (no concurrent writer) — not fixed here.
#
# Never blocks hard, never errors — always exit 0. Any parse failure or
# internal error fails OPEN (silent allow), so a bug in this script can never
# wedge a session.

PAYLOAD="$(cat)"
[ -n "$PAYLOAD" ] || exit 0

# Read the whole payload once, then extract each field with its OWN python3
# call re-reading that same payload — never a newline-joined multi-value
# blob split back apart with `read`/`mapfile`. An earlier version joined
# tool_name/command/file_path with print() into one string; a `command`
# value containing a real newline (any heredoc or multi-step script —
# routine, non-adversarial Claude output, not an edge case) silently
# truncated CMD to its first line and clobbered FILE with the second,
# defeating the guard for that command entirely. Each extraction below
# writes its field's raw bytes via sys.stdout.write with no added
# delimiter, so embedded newlines pass through CMD intact into the segment
# splitter below (which already handles them — IFS includes $'\n').
TOOL_NAME="$(printf '%s' "$PAYLOAD" | python3 -c "
import json, sys
try:
    d = json.load(sys.stdin)
except Exception:
    sys.exit(0)
sys.stdout.write(d.get('tool_name', '') or '')
" 2>/dev/null || true)"
[ -n "$TOOL_NAME" ] || exit 0

CMD="$(printf '%s' "$PAYLOAD" | python3 -c "
import json, sys
try:
    d = json.load(sys.stdin)
except Exception:
    sys.exit(0)
ti = d.get('tool_input', d) or {}
sys.stdout.write(ti.get('command', '') or '')
" 2>/dev/null || true)"

FILE="$(printf '%s' "$PAYLOAD" | python3 -c "
import json, sys
try:
    d = json.load(sys.stdin)
except Exception:
    sys.exit(0)
ti = d.get('tool_input', d) or {}
sys.stdout.write(ti.get('file_path', '') or '')
" 2>/dev/null || true)"

ask() {
  # $1 = reason
  python3 -c "import json,sys; print(json.dumps({'hookSpecificOutput':{'hookEventName':'PreToolUse','permissionDecision':'ask','permissionDecisionReason':sys.argv[1]}}))" "$1"
  exit 0
}

# ---------------------------------------------------------------------------
# rm/rmdir target check: every target must be allowlisted (build/dep
# artifacts, *.pyc/*.log/*.tmp, /tmp or /private/tmp or $TMPDIR) or this asks.
# "All", never "any" — a mixed list like `rm -rf node_modules ~/important`
# must still ask, or the allowlist becomes a data-loss bug in a data-loss
# guard. Hard exclusions (/, ~, ., *, literal $HOME) and any target
# containing `..` or an unexpanded substitution ($(...), backticks, <(/>()
# always ask, since the real target can't be resolved from text alone.
# ---------------------------------------------------------------------------
check_rm_segment() {
  python3 -c "
import shlex, os, sys
seg = sys.argv[1]
try:
    tokens = shlex.split(seg)
except ValueError:
    print('ASK')
    sys.exit(0)
rest = tokens[1:]
targets = []
after_dashdash = False
for t in rest:
    if after_dashdash:
        targets.append(t); continue
    if t == '--':
        after_dashdash = True; continue
    if t.startswith('-') and len(t) > 1:
        continue
    targets.append(t)

if not targets:
    print('ALLOW'); sys.exit(0)

HARD = {'/', '~', '.', '*', '\$HOME', '\${HOME}'}
allow_dirs = {'node_modules', 'dist', 'build', '.next', 'target', '__pycache__',
              '.venv', 'venv', '.pytest_cache', '.ruff_cache', '.turbo',
              '.cache', 'coverage', '.gradle'}
allow_suffixes = ('.pyc', '.log', '.tmp')

def is_allowlisted(t):
    if t in HARD or '..' in t:
        return False
    for marker in ('\$(', '\`', '<(', '>('):
        if marker in t:
            return False
    p = os.path.expanduser(t)
    if not os.path.isabs(p):
        p = os.path.join(os.getcwd(), p)
    p = os.path.realpath(p)
    if any(part in allow_dirs for part in p.split(os.sep)):
        return True
    if t.endswith(allow_suffixes):
        return True
    if p.startswith('/tmp/') or p.startswith('/private/tmp/'):
        return True
    tmpdir = os.environ.get('TMPDIR')
    if tmpdir:
        real_tmp = os.path.realpath(tmpdir)
        if p.startswith(real_tmp + os.sep) or p == real_tmp:
            return True
    return False

for t in targets:
    if not is_allowlisted(t):
        print('ASK'); sys.exit(0)
print('ALLOW')
" "$1"
}

if [ "$TOOL_NAME" = "Bash" ]; then
  [ -n "$CMD" ] || exit 0

  # PERF GATE: this hook runs on every Bash call. Bail fast for anything that
  # can't possibly match a family below — deliberately coarse (no word
  # boundaries), so it over-triggers on things like "confirm" or "format"
  # rather than under-triggering; the precise per-family checks below still
  # filter those out correctly, this just saves the segment-split work.
  # MUST stay a superset of every per-family regex below: a new destructive
  # keyword added only to a family check and not here gets discarded by the
  # `exit 0` on the next line before it's ever evaluated — silently disabling
  # the new protection instead of the documented fail-open (parse failure).
  trigger_re='rm|rmdir|unlink|find|shred|truncate|dd |git[[:space:]]+(clean|reset|checkout|branch|push|stash|worktree|reflog|gc|filter-branch|filter-repo)|drop|delete|flushall|flushdb|deletemany|migrate|accept-data-loss|db[[:space:]]+reset|db:drop|db:reset|downgrade|terraform|kubectl|aws[[:space:]]+s3|dynamodb|docker[[:space:]]+(volume|system)|gcloud|pg:reset|repo[[:space:]]+delete|-x[[:space:]]+delete|secret[[:space:]]+delete|cache[[:space:]]+delete'
  printf '%s' "$CMD" | grep -qiE "$trigger_re" || exit 0

  CMD="${CMD#rtk proxy }"
  CMD="${CMD#rtk }"

  ASK_REASON=""
  oldIFS="$IFS"; IFS='|&;'$'\n'; set -f
  for seg in $CMD; do
    s="$(printf '%s' "$seg" | sed -E 's/^[[:space:]]+//; s/[[:space:]]+$//')"
    [ -n "$s" ] || continue
    s="${s#rtk proxy }"; s="${s#rtk }"
    # Command-name anchors below match case-insensitively (`RM -rf` asks same
    # as `rm -rf`) via this lowercased copy. check_rm_segment and the reason
    # string both still use the original-case $s — path/allowlist matching
    # and the human-readable reason must stay case-sensitive.
    s_lc="$(printf '%s' "$s" | tr 'A-Z' 'a-z')"

    if printf '%s' "$s_lc" | grep -qE '^(rm|rmdir|unlink)([[:space:]]|$)'; then
      if [ "$(check_rm_segment "$s")" = "ASK" ]; then
        ASK_REASON="file deletion: \`$s\`"; break
      fi
      continue
    fi

    if printf '%s' "$s_lc" | grep -qE '^find[[:space:]].*(-delete|-exec[[:space:]]+rm)' \
      || printf '%s' "$s_lc" | grep -qE '^shred([[:space:]]|$)' \
      || printf '%s' "$s_lc" | grep -qE '^truncate[[:space:]].*-s[[:space:]]*0' \
      || printf '%s' "$s_lc" | grep -qE '^dd[[:space:]].*of='; then
      ASK_REASON="file deletion: \`$s\`"; break
    fi

    if printf '%s' "$s_lc" | grep -qE '^git[[:space:]]+clean[[:space:]].*-[a-zA-Z]*f' \
      || printf '%s' "$s_lc" | grep -qE '^git[[:space:]]+reset[[:space:]]+--hard([[:space:]]|$)' \
      || printf '%s' "$s_lc" | grep -qE '^git[[:space:]]+checkout[[:space:]]+--[[:space:]]+\.([[:space:]]|$)' \
      || printf '%s' "$s_lc" | grep -qE '^git[[:space:]]+branch[[:space:]]+-d([[:space:]]|$)' \
      || { printf '%s' "$s_lc" | grep -qE '^git[[:space:]]+push' && printf '%s' "$s_lc" | grep -qE '(^|[[:space:]])(--force|-f)([[:space:]]|$)'; } \
      || printf '%s' "$s_lc" | grep -qE '^git[[:space:]]+stash[[:space:]]+(drop|clear)([[:space:]]|$)' \
      || printf '%s' "$s_lc" | grep -qE '^git[[:space:]]+worktree[[:space:]]+remove.*--force' \
      || printf '%s' "$s_lc" | grep -qE '^git[[:space:]]+reflog[[:space:]]+expire' \
      || printf '%s' "$s_lc" | grep -qE '^git[[:space:]]+gc[[:space:]].*--prune' \
      || printf '%s' "$s_lc" | grep -qE '^git[[:space:]]+(filter-branch|filter-repo)([[:space:]]|$)'; then
      ASK_REASON="irreversible git op: \`$s\`"; break
    fi

    if printf '%s' "$s_lc" | grep -qE 'drop[[:space:]]+(table|database|schema)[[:space:]]' \
      || printf '%s' "$s_lc" | grep -qE 'truncate([[:space:]]+table)?[[:space:]]' \
      || printf '%s' "$s_lc" | grep -qE 'delete[[:space:]]+from[[:space:]]'; then
      ASK_REASON="destructive SQL: \`$s\`"; break
    fi

    if printf '%s' "$s_lc" | grep -qE 'redis-cli.*(flushall|flushdb)' \
      || printf '%s' "$s_lc" | grep -qE 'mongosh.*(\.drop\(\)|deletemany)' \
      || printf '%s' "$s_lc" | grep -qE '^prisma[[:space:]]+migrate[[:space:]]+reset' \
      || printf '%s' "$s_lc" | grep -qE '^prisma[[:space:]].*--accept-data-loss' \
      || printf '%s' "$s_lc" | grep -qE '^supabase[[:space:]]+db[[:space:]]+reset' \
      || printf '%s' "$s_lc" | grep -qE '^(bin/)?rails[[:space:]]+db:(drop|reset)' \
      || printf '%s' "$s_lc" | grep -qE '^alembic[[:space:]]+downgrade[[:space:]]+base'; then
      ASK_REASON="datastore reset: \`$s\`"; break
    fi

    if printf '%s' "$s_lc" | grep -qE '^terraform[[:space:]]+destroy' \
      || printf '%s' "$s_lc" | grep -qE '^kubectl[[:space:]]+delete' \
      || printf '%s' "$s_lc" | grep -qE '^aws[[:space:]]+s3[[:space:]]+rm.*--recursive' \
      || printf '%s' "$s_lc" | grep -qE '^aws[[:space:]]+s3[[:space:]]+rb' \
      || printf '%s' "$s_lc" | grep -qE '^aws[[:space:]]+dynamodb[[:space:]]+delete-table' \
      || printf '%s' "$s_lc" | grep -qE '^docker[[:space:]]+volume[[:space:]]+rm' \
      || printf '%s' "$s_lc" | grep -qE '^docker[[:space:]]+system[[:space:]]+prune' \
      || printf '%s' "$s_lc" | grep -qE '^gcloud[[:space:]].*delete' \
      || printf '%s' "$s_lc" | grep -qE '^heroku[[:space:]]+pg:reset'; then
      ASK_REASON="cloud/infra destroy: \`$s\`"; break
    fi

    if printf '%s' "$s_lc" | grep -qE '^(gh|glab)[[:space:]]+repo[[:space:]]+delete' \
      || printf '%s' "$s_lc" | grep -qE '^gh[[:space:]]+api.*(-x|--method)[[:space:]]+delete' \
      || printf '%s' "$s_lc" | grep -qE '^gh[[:space:]]+secret[[:space:]]+delete' \
      || printf '%s' "$s_lc" | grep -qE '^gh[[:space:]]+cache[[:space:]]+delete'; then
      ASK_REASON="remote repo deletion: \`$s\`"; break
    fi
  done
  IFS="$oldIFS"; set +f

  [ -n "$ASK_REASON" ] || exit 0
  ask "destructive-guard: $ASK_REASON — confirm this is intended before it runs."
fi

if [ "$TOOL_NAME" = "Write" ]; then
  [ -n "$FILE" ] || exit 0

  case "$FILE" in
    /*) abs="$FILE" ;;
    *)  abs="$PWD/$FILE" ;;
  esac
  abs="$(python3 -c "import os,sys; print(os.path.realpath(sys.argv[1]))" "$abs" 2>/dev/null || printf '%s' "$abs")"

  # Only an existing, non-empty regular file is an unrecoverable overwrite.
  size="$(python3 -c "
import os, sys
p = sys.argv[1]
try:
    st = os.stat(p)
except OSError:
    sys.exit(1)
if not os.path.isfile(p) or st.st_size == 0:
    sys.exit(1)
print(st.st_size)
" "$abs" 2>/dev/null)"
  [ -n "$size" ] || exit 0

  case "$abs" in
    */node_modules/*|*/dist/*|*/build/*|*/.next/*|*/target/*|*/__pycache__/*|\
    */.venv/*|*/venv/*|*/.pytest_cache/*|*/.ruff_cache/*|*/.turbo/*|*/.cache/*|\
    */coverage/*|*/.gradle/*|*.pyc|*.log|*.tmp|/tmp/*|/private/tmp/*) exit 0 ;;
  esac

  repo_root="$(git -C "$PWD" rev-parse --show-toplevel 2>/dev/null || true)"
  if [ -n "$repo_root" ]; then
    case "$abs" in
      "$repo_root"/.claude/plans/*) exit 0 ;;
    esac
  fi

  if [ -n "${TMPDIR:-}" ]; then
    tmpdir_real="$(python3 -c "import os,sys; print(os.path.realpath(sys.argv[1]))" "$TMPDIR" 2>/dev/null || true)"
    if [ -n "$tmpdir_real" ]; then
      case "$abs" in "$tmpdir_real"/*|"$tmpdir_real") exit 0 ;; esac
    fi
  fi

  base="$(basename "$FILE")"
  ask "destructive-guard: overwriting existing file ($base, ${size} bytes) — this discards its current contents. Confirm this is intended."
fi

exit 0
