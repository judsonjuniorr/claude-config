#!/usr/bin/env bash
# UserPromptSubmit hook for herow-core (registered in herow-core/hooks/hooks.json).
#
# Backstop freshness check for graphify: if HEAD has moved since the graph was last
# built (pull, branch switch, or any commit) and no git hook already caught it (see
# /graphify-install's post-merge/post-checkout hooks), kick off an incremental
# `graphify update` in the background so a stale graph doesn't silently answer
# queries. Style/contract mirrors herow-dev/scripts/pull-latest.sh:
#   - Silent + zero cost on every non-matching prompt.
#   - Fail-open ALWAYS (exit 0): UserPromptSubmit only blocks on exit 2 — never used here.
#   - HEROW_SKIP_GRAPHIFY is the escape hatch, checked FIRST.
#   - The actual `graphify update` runs detached so this hook returns instantly.
#
# Note: uses nohup, not setsid — setsid is a Linux/util-linux tool absent on macOS.
# nohup + explicit stdio redirection + disown gets the same "survives the hook
# process exiting, no attached pipes" result portably on both platforms.

set -u

# --- 1. Escape hatch ---------------------------------------------------------
[ -z "${HEROW_SKIP_GRAPHIFY:-}" ] || exit 0

# --- 2. Fail-open guards ------------------------------------------------------
DIR="${CLAUDE_PROJECT_DIR:-$PWD}"
DIR="$(git -C "$DIR" rev-parse --show-toplevel 2>/dev/null)" || exit 0
command -v graphify >/dev/null 2>&1 || exit 0

# Only act when a full graph + manifest baseline exist. A missing manifest.json
# (gitignored) means either the graph was never incrementally built here, or this
# is a throwaway worktree (e.g. /herow-dev:quick, /herow-dev:execute) — skip rather
# than trigger an accidental full LLM rebuild inside a disposable tree.
[ -f "$DIR/graphify-out/graph.json" ] && [ -f "$DIR/graphify-out/manifest.json" ] || exit 0

# --- 3. Staleness check --------------------------------------------------------
HEAD="$(git -C "$DIR" rev-parse HEAD 2>/dev/null)" || exit 0
STAMP_FILE="$DIR/graphify-out/.graphify_head"

# First time this script has ever seen this repo: baseline silently instead of
# firing a rebuild in every already-graphified repo the moment this feature ships.
# The graph may already be stale at that point, but it was already stale before
# this feature existed — `/graphify --update` still works manually. Only HEAD
# movement AFTER this baseline is treated as "went stale under our watch".
if [ ! -f "$STAMP_FILE" ]; then
  printf '%s' "$HEAD" > "$STAMP_FILE" 2>/dev/null || true
  exit 0
fi

STORED="$(cat "$STAMP_FILE" 2>/dev/null || true)"
[ "$HEAD" != "$STORED" ] || exit 0

# --- 4. Failure backoff ---------------------------------------------------------
# A persistently-failing `graphify update` (bad config, expired API key, quota)
# would otherwise get silently retried on every single prompt forever. After 3
# failures, back off with a linear delay (cap 30 min) between retries, so it stops
# hammering and eventually recovers on its own once the underlying issue clears.
FAILFILE="$DIR/graphify-out/.graphify_update.failcount"
if [ -f "$FAILFILE" ]; then
  FAILCOUNT=0; LAST_FAIL=0
  read -r FAILCOUNT LAST_FAIL < "$FAILFILE" 2>/dev/null || true
  case "$FAILCOUNT" in (*[!0-9]*|'') FAILCOUNT=0 ;; esac
  case "$LAST_FAIL" in (*[!0-9]*|'') LAST_FAIL=0 ;; esac
  if [ "$FAILCOUNT" -ge 3 ]; then
    BACKOFF=$((FAILCOUNT * 60)); [ "$BACKOFF" -gt 1800 ] && BACKOFF=1800
    NOW_CHECK=$(date +%s)
    [ $((NOW_CHECK - LAST_FAIL)) -ge "$BACKOFF" ] || exit 0
  fi
fi

# --- 5. Single-flight lock, gated on PID liveness (not a time heuristic) --------
# A flat TTL is wrong here: a legitimate incremental update can occasionally run
# longer than any fixed window (large repo, LLM-backed semantic pass, slow API) —
# reclaiming by age alone would steal the lock from a still-running job and spawn
# a second concurrent `graphify update` writing the same files with no coordination.
# Instead: record the backgrounded job's PID and only reclaim when that PID is
# actually dead (kill -0 fails). A short grace window (30s) covers the brief gap
# between mkdir and the pid file being written, and also recovers an orphaned lock
# whose job never started at all.
LOCK="$DIR/graphify-out/.graphify_update.lock"
if ! mkdir "$LOCK" 2>/dev/null; then
  OWNER_PID=""
  [ -f "$LOCK/pid" ] && OWNER_PID="$(cat "$LOCK/pid" 2>/dev/null || true)"
  case "$OWNER_PID" in (*[!0-9]*|'') OWNER_PID="" ;; esac
  if [ -n "$OWNER_PID" ] && kill -0 "$OWNER_PID" 2>/dev/null; then
    exit 0   # owning process is genuinely still alive — never steal a live lock
  fi
  STARTED=0
  [ -f "$LOCK/started_at" ] && STARTED="$(cat "$LOCK/started_at" 2>/dev/null || echo 0)"
  case "$STARTED" in (*[!0-9]*|'') STARTED=0 ;; esac
  NOW_LOCK=$(date +%s)
  if [ "$STARTED" -gt 0 ] && [ $((NOW_LOCK - STARTED)) -gt 30 ]; then
    rm -rf "$LOCK" 2>/dev/null
    mkdir "$LOCK" 2>/dev/null || exit 0   # lost the race to reclaim — another process got there first
  else
    exit 0   # lock just created, pid not written yet — give it the grace window
  fi
fi
date +%s > "$LOCK/started_at" 2>/dev/null || true

# --- 6. Refresh in the background, fully detached ------------------------------
# Explicit stdio redirection is mandatory: an un-redirected `&` here would keep
# this hook's pipe open and make it look hung to the harness.
nohup bash -c '
  dir="$1"
  failfile="$dir/graphify-out/.graphify_update.failcount"
  if graphify update >"$dir/graphify-out/.graphify_update.log" 2>&1 </dev/null; then
    git -C "$dir" rev-parse HEAD > "$dir/graphify-out/.graphify_head" 2>/dev/null
    rm -f "$failfile"
  else
    count=0
    [ -f "$failfile" ] && { read -r count _ < "$failfile" 2>/dev/null || true; }
    case "$count" in (*[!0-9]*|"") count=0 ;; esac
    count=$((count + 1))
    printf "%s %s\n" "$count" "$(date +%s)" > "$failfile" 2>/dev/null
  fi
  rm -rf "$dir/graphify-out/.graphify_update.lock" 2>/dev/null
' _ "$DIR" >/dev/null 2>&1 </dev/null &
echo $! > "$LOCK/pid" 2>/dev/null || true
disown 2>/dev/null || true

echo "↻ graphify: graph stale (HEAD changed) — refreshing in background"
exit 0
