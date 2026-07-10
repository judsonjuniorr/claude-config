#!/usr/bin/env bash
# Harness-driven persistence for /herow-dev:blueprint.
# Fires on PreToolUse/PostToolUse for the Skill tool (registered in herow-dev/hooks/hooks.json).
#
# Layout: one directory per plan under .claude/plans/<slug>/ holding plan.md, state.json,
# optional source.md, and an artifacts/ subdir for everything the plan's orchestration produces.
#
# Concurrency model (parallel sessions in the same repo are the norm):
#   - The active plan is bound to the SESSION, not the repo: the marker file is
#     .claude/plans/.active-<session_id>, and this hook only acts on the plan owned by
#     the session_id in its OWN payload. A second session's Skill calls never land in
#     another session's plan.
#   - state.json is written atomically (temp file + os.replace) so a crash or the hook
#     timeout can never leave torn/half-written JSON that poisons every later run.
#   - The mtime snapshot is scoped to the plan's own artifacts/ dir and keyed per
#     invocation (LIFO stack), so nested/overlapping Skill calls never clobber each other.
set -eu

EVENT="${1:-post}"
PAYLOAD="$(cat || true)"
CWD="${CLAUDE_PROJECT_DIR:-$PWD}"

# --- Resolve the session that owns this hook invocation, and the skill name. ---
read_field() {
  # $1 = python expression against the parsed payload dict `d`; prints '' on any error.
  printf '%s' "$PAYLOAD" | python3 -c "import json,sys
try:
  d=json.load(sys.stdin)
except Exception:
  print(''); sys.exit(0)
try:
  print($1)
except Exception:
  print('')" 2>/dev/null || true
}

SID="$(read_field "d.get('session_id') or ''")"
[ -n "$SID" ] || exit 0

MARKER="$CWD/.claude/plans/.active-$SID"
[ -f "$MARKER" ] || exit 0                       # this session is not blueprinting — no-op
# Tolerate the marker being removed concurrently (consolidation's rm) — a benign teardown
# race must produce a clean no-op, not a set -e abort on the failed redirection.
SLUG="$(tr -d '[:space:]' < "$MARKER" 2>/dev/null || true)"
[ -n "$SLUG" ] || exit 0

PLAN_DIR="$CWD/.claude/plans/$SLUG"
[ -d "$PLAN_DIR" ] || exit 0

SKILL="$(read_field "(lambda ti: ti.get('skill') or ti.get('args') or '')(d.get('tool_input',{}))")"
[ -n "$SKILL" ] || exit 0
# Normalize: drop a leading plugin namespace (herow-core:github-ops -> github-ops) and any
# leading slash, so the canonical coverage checklist (unnamespaced) matches reliably.
SKILL="${SKILL##*/}"
SKILL="${SKILL##*:}"

STATE="$PLAN_DIR/state.json"
ART_DIR="$PLAN_DIR/artifacts"
SNAP_DIR="$PLAN_DIR/.snap"
STACK="$SNAP_DIR/stack"
NOW="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
mkdir -p "$ART_DIR" "$SNAP_DIR"

# Serialize the stack mutation + state.json read-modify-write per plan. The harness can run
# independent tool calls (hence Skill PRE/POST pairs) concurrently within one session, and
# atomic os.replace() alone would still lose an update in that race. macOS ships no flock(1),
# so use mkdir as a bounded spinlock, and FAIL OPEN after the bound so the hook can never hang
# toward its 15/20s timeout. lock_release only ever removes a lock this invocation owns.
LOCK="$SNAP_DIR/.lock"
lock_held=0
lock_acquire() {
  local i=0
  while [ "$i" -lt 50 ]; do
    if mkdir "$LOCK" 2>/dev/null; then lock_held=1; return 0; fi
    i=$((i + 1)); sleep 0.1
  done
  return 0                                        # ~5s elapsed — proceed unlocked (fail open)
}
lock_release() {
  [ "$lock_held" = 1 ] || return 0
  rmdir "$LOCK" 2>/dev/null || true
  lock_held=0
}
trap '[ "$lock_held" = 1 ] && rmdir "$LOCK" 2>/dev/null; true' EXIT

# BSD (macOS) vs GNU stat
if stat -f "%m" "$0" >/dev/null 2>&1; then
  STAT_ARGS=(-f '%m %N')
else
  STAT_ARGS=(-c '%Y %n')
fi

# Snapshot only the plan's own artifacts/ dir — fast, and immune to unrelated repo churn
# (worktrees, builds) or the plan's own bookkeeping (state.json / plan.md rewrites).
snapshot() {
  find "$ART_DIR" -type f -print0 2>/dev/null \
    | xargs -0 stat "${STAT_ARGS[@]}" 2>/dev/null | sort
}

if [ "$EVENT" = "pre" ]; then
  SNAP="$(mktemp "$SNAP_DIR/pre.XXXXXX")"
  snapshot > "$SNAP" || true
  lock_acquire
  printf '%s\n' "$SNAP" >> "$STACK"           # LIFO: paired by the matching POST
  lock_release
  exit 0
fi

# POST: pop the most recent PRE snapshot for this session's plan (LIFO pairs nested calls).
# The pop and the state.json update below run under the lock so a concurrent PRE append or a
# second POST cannot double-pop the stack or lose a skill record.
[ -f "$STACK" ] || exit 0
lock_acquire
SNAP="$(tail -n 1 "$STACK" 2>/dev/null || true)"
if [ -z "$SNAP" ]; then lock_release; exit 0; fi
# Drop the popped entry from the stack.
TMP_STACK="$(mktemp "$SNAP_DIR/stack.XXXXXX")"
sed '$d' "$STACK" > "$TMP_STACK" 2>/dev/null || true
mv "$TMP_STACK" "$STACK"
if [ ! -f "$SNAP" ]; then lock_release; exit 0; fi   # snapshot gone (teardown race) — drop record, fail open

NEW="$(mktemp "$SNAP_DIR/post.XXXXXX")"
snapshot > "$NEW" || true

# comm/sed/python can fail on odd filenames (e.g. invalid UTF-8); never let that abort the
# hook under set -e — an unrecorded artifact list is degraded, not fatal.
ARTIFACTS_JSON="$(comm -13 "$SNAP" "$NEW" 2>/dev/null \
  | sed 's/^[0-9]* //' \
  | python3 -c "import json,sys; print(json.dumps([l.strip() for l in sys.stdin if l.strip()]))" 2>/dev/null || true)"
[ -n "$ARTIFACTS_JSON" ] || ARTIFACTS_JSON='[]'

# Append the skill record via an atomic read-modify-write: write a sibling temp file in the
# same directory, then os.replace() over state.json so readers only ever see a whole file.
python3 - "$STATE" "$SLUG" "$SKILL" "$NOW" "$ARTIFACTS_JSON" <<'PY'
import json, os, sys, tempfile, pathlib
state_path, slug, skill, ts, artifacts_json = sys.argv[1:6]
artifacts = json.loads(artifacts_json)
p = pathlib.Path(state_path)
recovered = None
try:
    state = json.loads(p.read_text()) if p.exists() else {}
except Exception:
    # A corrupt file here means external damage (atomic writes can't produce it). Preserve it
    # aside instead of silently discarding recorded history, and leave a visible marker.
    aside = p.with_name(p.name + ".corrupt")
    if not aside.exists():
        try: p.replace(aside)
        except OSError: pass
    state = {}
    recovered = ts
state.setdefault("schema", 1)
if recovered:
    state["recovered_from_corruption"] = recovered
state.setdefault("id", slug)
state.setdefault("skills", [])
state["skills"].append({"skill": skill, "finished_at": ts, "artifacts": artifacts})
state["last_update"] = ts
fd, tmp = tempfile.mkstemp(dir=str(p.parent), prefix=".state.", suffix=".json")
try:
    with os.fdopen(fd, "w") as f:
        json.dump(state, f, indent=2)
    os.replace(tmp, str(p))         # atomic on the same filesystem
except Exception:
    try: os.unlink(tmp)
    except OSError: pass
    raise
PY

lock_release
rm -f "$SNAP" "$NEW"
exit 0
