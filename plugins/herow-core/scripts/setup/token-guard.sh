#!/usr/bin/env bash
# Apply recommended model + context settings to ~/.claude/settings.json.
# Idempotent — writes only when a value differs from target.
# Usage: token-guard.sh
set -u
HERE="$(cd "$(dirname "$0")" && pwd)"
. "${HERE}/_common.sh"

[ -f "$SETTINGS" ] || python3 -c "import json,sys; json.dump({}, open(sys.argv[1], 'w'), indent=2)" "$SETTINGS"

backup_file "$SETTINGS" >/dev/null

python3 - "$SETTINGS" <<'PY'
import json, sys

TARGETS = {
    "model": "opusplan",
    "advisorModel": "opus",
    "effortLevel": "high",
    "autoCompact": True,
}
SUBAGENT_MODEL = "claude-sonnet-4-6"

p = sys.argv[1]
try:
    s = json.load(open(p))
except Exception as e:
    print("err|token-guard|cannot parse %s: %s" % (p, e))
    sys.exit(1)

changes = []
for key, val in TARGETS.items():
    if s.get(key) != val:
        s[key] = val
        changes.append((key, "set"))
    else:
        changes.append((key, "already-set"))

env = s.setdefault("env", {})
subagent_key = "CLAUDE_CODE_SUBAGENT_MODEL"
if env.get(subagent_key) != SUBAGENT_MODEL:
    env[subagent_key] = SUBAGENT_MODEL
    changes.append(("subagent-model", "set"))
else:
    changes.append(("subagent-model", "already-set"))

if any(v == "set" for _, v in changes):
    json.dump(s, open(p, "w"), indent=2)

for key, status in changes:
    print("ok|%s|%s" % (key, status))
PY
