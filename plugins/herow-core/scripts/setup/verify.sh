#!/usr/bin/env bash
# Post-setup assertions. Emits pass|<check>|<detail> or fail|<check>|<detail>,
# then a final summary line. Read-only.
set -u
HERE="$(cd "$(dirname "$0")" && pwd)"
. "${HERE}/_common.sh"

PASS=0; FAIL=0
ck()  { if eval "$2" >/dev/null 2>&1; then echo "pass|$1|$3"; PASS=$((PASS+1)); else echo "fail|$1|$4"; FAIL=$((FAIL+1)); fi; }

# stack tools work
ck rtk        'have rtk && rtk gain'                 "rtk gain ok"          "rtk gain failed"
ck graphify   'have graphify && graphify --version'  "graphify ok"          "graphify missing"
ck headroom   'have headroom'                         "headroom present"     "headroom missing"
ck gstack     '[ -d "${GSTACK_DIR}/.git" ]'          "gstack cloned"        "gstack not installed"

# vendored commands present in a herow-dev plugin dir (discoverable as /herow-dev:*)
VENDORED="$(find "${CLAUDE_HOME}/plugins" -path '*herow-dev*/commands/blueprint.md' -print -quit 2>/dev/null)"
ck cmds-vendored '[ -n "$VENDORED" ]' \
  "blueprint/quick/execute vendored ($VENDORED)" "vendored herow-dev commands not found in plugin cache"

# OMEGA fully gone
ck omega-bin      '! [ -e "${HOME}/.local/bin/omega" ]'                 "omega bin gone"        "omega bin still present"
ck omega-settings '! { [ -f "$SETTINGS" ] && grep -q omega "$SETTINGS"; }' "no omega in settings" "omega still in settings.json"
ck omega-md       '! { [ -f "$CLAUDE_MD" ] && grep -qi OMEGA "$CLAUDE_MD"; }' "no OMEGA in CLAUDE.md" "OMEGA still in CLAUDE.md"

# loose duplicates gone
ck loose-cmds '! [ -f "${LOOSE_CMD_DIR}/blueprint.md" ]' "loose blueprint removed" "loose blueprint.md still present"

# token optimizations
ck model \
  'python3 -c "import json,sys; s=json.load(open(\"${SETTINGS}\")); sys.exit(0 if \"sonnet\" in s.get(\"model\",\"\") else 1)" 2>/dev/null' \
  "model=sonnet" "model not set to sonnet in settings.json"
ck effort \
  'python3 -c "import json,sys; s=json.load(open(\"${SETTINGS}\")); sys.exit(0 if s.get(\"effortLevel\")==\"high\" else 1)" 2>/dev/null' \
  "effortLevel=high" "effortLevel not set to high in settings.json"
ck advisor-model \
  'python3 -c "import json,sys; s=json.load(open(\"${SETTINGS}\")); sys.exit(0 if s.get(\"advisorModel\")==\"opus\" else 1)" 2>/dev/null' \
  "advisorModel=opus" "advisorModel not set to opus in settings.json"
ck autocompact \
  'python3 -c "import json,sys; s=json.load(open(\"${SETTINGS}\")); sys.exit(0 if s.get(\"autoCompact\") is True else 1)" 2>/dev/null' \
  "autoCompact enabled" "autoCompact not set in settings.json"
ck subagent-model \
  'python3 -c "import json,sys; s=json.load(open(\"${SETTINGS}\")); sys.exit(0 if \"sonnet\" in s.get(\"env\",{}).get(\"CLAUDE_CODE_SUBAGENT_MODEL\",\"\") else 1)" 2>/dev/null' \
  "CLAUDE_CODE_SUBAGENT_MODEL=sonnet" "CLAUDE_CODE_SUBAGENT_MODEL not pinned to sonnet"

emit summary "${PASS} passed / ${FAIL} failed" "$([ "$FAIL" -eq 0 ] && echo all-green || echo review-fails)"
exit 0
