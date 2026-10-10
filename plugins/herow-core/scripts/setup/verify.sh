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
ck gstack     '[ -d "${GSTACK_DIR}/.git" ]'          "gstack cloned"        "gstack not installed"
ck organizze  'have organizze && organizze --version' "organizze ok"        "organizze missing"

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
  'python3 -c "import json,sys; s=json.load(open(\"${SETTINGS}\")); sys.exit(0 if s.get(\"model\")==\"opusplan\" else 1)" 2>/dev/null' \
  "model=opusplan" "model not set to opusplan in settings.json"
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
  'python3 -c "import json,sys; s=json.load(open(\"${SETTINGS}\")); sys.exit(0 if not (s.get(\"env\",{}) or {}).get(\"CLAUDE_CODE_SUBAGENT_MODEL\") else 1)" 2>/dev/null' \
  "no subagent-model pin (inherits default)" "CLAUDE_CODE_SUBAGENT_MODEL still pinned"
ck default-opus-model \
  'python3 -c "import json,sys; s=json.load(open(\"${SETTINGS}\")); v=(s.get(\"env\",{}) or {}).get(\"ANTHROPIC_DEFAULT_OPUS_MODEL\",\"\"); sys.exit(0 if v.startswith(\"claude-opus-\") else 1)" 2>/dev/null' \
  "ANTHROPIC_DEFAULT_OPUS_MODEL pinned" "ANTHROPIC_DEFAULT_OPUS_MODEL not set to a claude-opus-* id in settings.json env"
ck default-sonnet-model \
  'python3 -c "import json,sys; s=json.load(open(\"${SETTINGS}\")); v=(s.get(\"env\",{}) or {}).get(\"ANTHROPIC_DEFAULT_SONNET_MODEL\",\"\"); sys.exit(0 if v.startswith(\"claude-sonnet-\") else 1)" 2>/dev/null' \
  "ANTHROPIC_DEFAULT_SONNET_MODEL pinned" "ANTHROPIC_DEFAULT_SONNET_MODEL not set to a claude-sonnet-* id in settings.json env"
ck default-haiku-model \
  'python3 -c "import json,sys; s=json.load(open(\"${SETTINGS}\")); v=(s.get(\"env\",{}) or {}).get(\"ANTHROPIC_DEFAULT_HAIKU_MODEL\",\"\"); sys.exit(0 if v.startswith(\"claude-haiku-\") else 1)" 2>/dev/null' \
  "ANTHROPIC_DEFAULT_HAIKU_MODEL pinned" "ANTHROPIC_DEFAULT_HAIKU_MODEL not set to a claude-haiku-* id in settings.json env"

# Jev is optional: a keyless machine is info, not a failure.
jev_dry_run() {
  printf '%s' '{"items":[{"id":"t","state":"ok"}],"questions":{"q":{"type":"noul","instructions":"x","criteria":{"true":"a","false":"b"}}}}' \
    | "${JEV_BIN}/jev" --dry-run | grep -q '"dry_run"'
}
JEV_SRC="$(jev_key_source)"
if [ "$JEV_SRC" = none ]; then
  echo "info|jev-key|absent"
else
  echo "pass|jev-key|key found (${JEV_SRC})"; PASS=$((PASS+1))
  ck jev-shim 'jev_dry_run' "jev shim resolves herow-core (dry-run ok)" \
    "jev shim missing or not resolving: run the doctor install step, then /herow-core:upgrade"
fi

emit summary "${PASS} passed / ${FAIL} failed" "$([ "$FAIL" -eq 0 ] && echo all-green || echo review-fails)"
exit 0
