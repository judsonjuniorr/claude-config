#!/usr/bin/env bash
# Harness-driven persistence for /herow-dev:blueprint.
# Fires on PreToolUse/PostToolUse for the Skill tool (registered in herow-dev/hooks/hooks.json).
# - PRE  : snapshot file mtimes into /tmp/blueprint-<id>.snap
# - POST : diff against snapshot, append artifacts + checkpoint to .plans/<id>.state.json
# Only acts when .plans/.active exists in the project dir.
set -eu

EVENT="${1:-post}"
PAYLOAD="$(cat || true)"
CWD="${CLAUDE_PROJECT_DIR:-$PWD}"
MARKER="$CWD/.plans/.active"

[ -f "$MARKER" ] || exit 0
ID="$(tr -d '[:space:]' < "$MARKER")"
[ -n "$ID" ] || exit 0

SKILL="$(printf '%s' "$PAYLOAD" | python3 -c "import json,sys
try:
  d=json.load(sys.stdin)
  ti=d.get('tool_input',{})
  print(ti.get('skill') or ti.get('args') or '')
except: pass" 2>/dev/null || true)"
[ -n "$SKILL" ] || exit 0

STATE="$CWD/.plans/$ID.state.json"
SNAP="/tmp/blueprint-$ID.snap"
NOW="$(date -u +%Y-%m-%dT%H:%M:%SZ)"

# BSD (macOS) vs GNU stat
if stat -f "%m" "$0" >/dev/null 2>&1; then
  STAT_FMT='-f' STAT_ARG='%m %N'
else
  STAT_FMT='-c' STAT_ARG='%Y %n'
fi

snapshot() {
  cd "$CWD" && find . -type f \
    -not -path './node_modules/*' \
    -not -path './.git/*' \
    -not -path './.plans/*' \
    -not -path './dist/*' -not -path './build/*' \
    -print0 2>/dev/null \
    | xargs -0 stat "$STAT_FMT" "$STAT_ARG" 2>/dev/null | sort
}

if [ "$EVENT" = "pre" ]; then
  snapshot > "$SNAP" || true
  exit 0
fi

# POST: compute diff and append to state
[ -f "$SNAP" ] || exit 0
NEW="$(mktemp)"
snapshot > "$NEW" || true

ARTIFACTS_JSON="$(comm -13 "$SNAP" "$NEW" 2>/dev/null \
  | awk '{print $2}' \
  | python3 -c "import json,sys; print(json.dumps([l.strip() for l in sys.stdin if l.strip()]))")"

python3 - "$STATE" "$SKILL" "$NOW" "$ARTIFACTS_JSON" <<'PY'
import json, sys, pathlib
state_path, skill, ts, artifacts_json = sys.argv[1:5]
artifacts = json.loads(artifacts_json)
p = pathlib.Path(state_path)
state = json.loads(p.read_text()) if p.exists() else {"id": p.stem.replace('.state',''), "skills": []}
state.setdefault("skills", []).append({
    "skill": skill,
    "finished_at": ts,
    "artifacts": artifacts,
})
state["last_update"] = ts
p.write_text(json.dumps(state, indent=2))
PY

rm -f "$SNAP" "$NEW"
exit 0
