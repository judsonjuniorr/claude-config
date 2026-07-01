#!/usr/bin/env bash
# Apply recommended model + context settings to ~/.claude/settings.json.
# Idempotent — writes only when a value differs from target.
# Usage: token-guard.sh
set -u
HERE="$(cd "$(dirname "$0")" && pwd)"
. "${HERE}/_common.sh"

if [ ! -f "$SETTINGS" ]; then
  mkdir -p "$(dirname "$SETTINGS")"
  python3 -c "import json,sys; json.dump({}, open(sys.argv[1], 'w'), indent=2)" "$SETTINGS" \
    || { echo "err|token-guard|cannot create $SETTINGS"; exit 1; }
fi

backup_file "$SETTINGS" >/dev/null

python3 - "$SETTINGS" <<'PY'
import json, sys, os, tempfile

TARGETS = {
    "model": "opusplan",
    "advisorModel": "opus",
    "effortLevel": "high",
    "autoCompact": True,
}

p = sys.argv[1]
try:
    s = json.load(open(p))
    if not isinstance(s, dict):
        raise ValueError("not a JSON object")
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

# Subagents inherit the default input model — remove any legacy pin.
subagent_key = "CLAUDE_CODE_SUBAGENT_MODEL"
env = s.get("env")
if isinstance(env, dict) and subagent_key in env:
    del env[subagent_key]
    changes.append(("subagent-model", "removed"))
else:
    changes.append(("subagent-model", "absent"))

if any(v == "set" for _, v in changes):
    d = os.path.dirname(os.path.abspath(p))
    fd, tmp = tempfile.mkstemp(dir=d, prefix=".settings-tmp-")
    try:
        with os.fdopen(fd, "w") as f:
            json.dump(s, f, indent=2)
        os.replace(tmp, p)
    except Exception as e:
        try: os.unlink(tmp)
        except: pass
        print("err|token-guard|write failed: %s" % e)
        sys.exit(1)

for key, status in changes:
    print("ok|%s|%s" % (key, status))
PY

# Apply model pins (idempotent, safe defaults — doctor picker can override).
# model-pin.py version-gates claude-sonnet-5/claude-opus-4-8 itself and falls
# back when the installed Claude Code is too old.
python3 "${HERE}/model-pin.py" --apply \
  --opus claude-opus-4-8 \
  --sonnet claude-sonnet-5 \
  || { echo "err|token-guard|model-pin apply failed"; exit 1; }
