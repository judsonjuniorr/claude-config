#!/usr/bin/env bash
# claude-config Stop guard.
# Catches premature stops — when the model ends its turn mid-task — and asks it to
# continue, so you don't have to type "continue" yourself.
#
# Safe by construction:
#   - respects stop_hook_active (never re-fires inside a continuation it caused)
#   - hard per-session cap (MAX) so it can never loop forever
#   - conservative: only fires on clear incompleteness signals (unbalanced code
#     fence, or a trailing "I'll now…"-style lead-in with nothing after it)
# Never errors; defaults to allowing the stop.

INPUT="$(cat)"

CC_STOP_INPUT="$INPUT" python3 - <<'PY'
import json, os, sys, tempfile

try:
    d = json.loads(os.environ.get("CC_STOP_INPUT", "") or "{}")
except Exception:
    sys.exit(0)

# Already continuing because of a stop hook → let this stop through.
if d.get("stop_hook_active"):
    sys.exit(0)

session = str(d.get("session_id", "default"))
path = d.get("transcript_path", "")

MAX = 3
safe = "".join(c for c in session if c.isalnum() or c in "-_") or "default"
cnt_file = os.path.join(tempfile.gettempdir(), ".claude-config-stop-guard-" + safe)

cnt = 0
try:
    with open(cnt_file) as f:
        cnt = int((f.read().strip() or "0"))
except Exception:
    cnt = 0

if cnt >= MAX:
    try:
        os.remove(cnt_file)
    except Exception:
        pass
    sys.exit(0)

# Last assistant text block from the transcript.
last = ""
if path:
    try:
        with open(path) as f:
            for line in f:
                try:
                    obj = json.loads(line)
                except Exception:
                    continue
                msg = obj.get("message", obj)
                role = msg.get("role") or obj.get("type")
                if role == "assistant":
                    c = msg.get("content")
                    if isinstance(c, list):
                        txt = "".join(
                            p.get("text", "")
                            for p in c
                            if isinstance(p, dict) and p.get("type") == "text"
                        )
                    elif isinstance(c, str):
                        txt = c
                    else:
                        txt = ""
                    if txt.strip():
                        last = txt.strip()
    except Exception:
        last = ""

if not last:
    sys.exit(0)

incomplete = False
if last.count("```") % 2 == 1:
    incomplete = True
else:
    tail = last[-80:].lower()
    signals = [
        "i will now", "next, i", "continuing", "one moment", "stand by",
        "hold on", "proceeding to", "let me continue", "let me now",
    ]
    if any(s in tail for s in signals) or last.rstrip().endswith((":", "…")):
        incomplete = True

if not incomplete:
    try:
        os.remove(cnt_file)
    except Exception:
        pass
    sys.exit(0)

try:
    with open(cnt_file, "w") as f:
        f.write(str(cnt + 1))
except Exception:
    pass

reason = (
    "You appear to have stopped mid-task (incomplete output, an unbalanced code "
    "fence, or a trailing lead-in with nothing after it). Continue and finish the "
    "task you were asked to do: complete the remaining reasoning and steps before "
    "ending your turn. If you are genuinely blocked, say so explicitly and state "
    "what you need instead of stopping silently."
)
print(json.dumps({"decision": "block", "reason": reason}))
sys.exit(0)
PY
exit 0
