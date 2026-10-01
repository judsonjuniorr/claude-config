#!/usr/bin/env bash
# Regression snapshot for setup/detect.sh and setup/verify.sh: every pre-existing record line must stay
# byte-identical (only Jev lines may differ), plus the new Jev records.
# Run: bash plugins/herow-core/scripts/tests/test-setup-records.sh
set -eu

SCRIPTS="$(cd "$(dirname "$0")/.." && pwd)"
PLUGIN_ROOT="$(cd "$SCRIPTS/.." && pwd)"
SETUP="$SCRIPTS/setup"

PASS=0
FAIL=0
ok()   { PASS=$((PASS + 1)); echo "ok   - $1"; }
fail() { FAIL=$((FAIL + 1)); echo "FAIL - $1"; }

TMPS=""
trap 'for d in $TMPS; do rm -rf "$d"; done' EXIT

# Fixture: a fresh HOME and a PATH holding only basic utilities plus git and python3, so dep lines are stable.
new_fixture() {
  local t c p
  t="$(mktemp -d)"
  TMPS="$TMPS $t"
  mkdir -p "$t/home" "$t/bin"
  for c in bash dirname head grep find date cat sed tr sort basename mktemp cp chmod mv rm mkdir cmp ls env uname python3 git; do
    p="$(command -v "$c")" && ln -sf "$p" "$t/bin/$c"
  done
  echo "$t"
}

populate() {
  local h="$1/home"
  mkdir -p "$h/.claude/commands" "$h/.claude/hooks" "$h/.local/bin" "$h/.claude/skills/gstack/.git"
  printf '{"model":"opusplan","advisorModel":"opus","effortLevel":"high","autoCompact":true,"env":{"ANTHROPIC_DEFAULT_OPUS_MODEL":"claude-opus-5-5","ANTHROPIC_DEFAULT_SONNET_MODEL":"claude-sonnet-5-5"},"hooks":{"x":"omega run; blueprint-track.sh"}}' > "$h/.claude/settings.json"
  printf '## Memory\nOMEGA here\n' > "$h/.claude/CLAUDE.md"
  printf '{"mcpServers":{"omega-mem":{},"my-memory":{},"other":{}}}' > "$h/.claude.json"
  : > "$h/.claude/commands/blueprint.md"
  : > "$h/.claude/hooks/blueprint-track.sh"
  : > "$h/.local/bin/omega"
}

# run <fixture> <detect|verify> [VAR=value ...]
run() {
  local t="$1" s="$2"
  shift 2
  env -i HOME="$t/home" PATH="$t/bin" JEV_SECURITY_BIN="$t/no-security" "$@" \
    "$t/bin/bash" "$SETUP/$s.sh" 2>/dev/null | sed "s|$t|@T@|g"
}

non_jev() { grep -v '^[a-z]*|jev-' || true; }

EMPTY_DETECT='dep|git|installed|@T@/bin/git
dep|brew|missing|-
dep|python3|installed|@T@/bin/python3
dep|uv|missing|-
dep|node|missing|-
dep|npm|missing|-
dep|bun|missing|-
tool|rtk|missing|-
tool|graphify|missing|-
tool|gstack|missing|-
tool|organizze|missing|-
opt|model|not-opusplan|settings.json: model not set to opusplan
opt|advisor-model|not-opus|settings.json: advisorModel not set to opus
opt|effort|not-high|settings.json: effortLevel not set to high
opt|autocompact|disabled|settings.json: autoCompact not enabled'

EMPTY_VERIFY='fail|rtk|rtk gain failed
fail|graphify|graphify missing
fail|gstack|gstack not installed
fail|organizze|organizze missing
fail|cmds-vendored|vendored herow-dev commands not found in plugin cache
pass|omega-bin|omega bin gone
pass|omega-settings|no omega in settings
pass|omega-md|no OMEGA in CLAUDE.md
pass|loose-cmds|loose blueprint removed
fail|model|model not set to opusplan in settings.json
fail|effort|effortLevel not set to high in settings.json
fail|advisor-model|advisorModel not set to opus in settings.json
fail|autocompact|autoCompact not set in settings.json
fail|subagent-model|CLAUDE_CODE_SUBAGENT_MODEL still pinned
fail|default-opus-model|ANTHROPIC_DEFAULT_OPUS_MODEL not set to a claude-opus-* id in settings.json env
fail|default-sonnet-model|ANTHROPIC_DEFAULT_SONNET_MODEL not set to a claude-sonnet-* id in settings.json env
summary|4 passed / 12 failed|review-fails'

FULL_DETECT='dep|git|installed|@T@/bin/git
dep|brew|missing|-
dep|python3|installed|@T@/bin/python3
dep|uv|missing|-
dep|node|missing|-
dep|npm|missing|-
dep|bun|missing|-
tool|rtk|missing|-
tool|graphify|missing|-
tool|gstack|installed|@T@/home/.claude/skills/gstack
tool|organizze|missing|-
remove|omega|bin|@T@/home/.local/bin/omega
remove|omega|settings-hooks|@T@/home/.claude/settings.json
remove|omega|claude-md|@T@/home/.claude/CLAUDE.md (## Memory section)
remove|omega|mcp-server|omega-mem (~/.claude.json)
remove|loose|cmd-blueprint|@T@/home/.claude/commands/blueprint.md
remove|loose|track-script|@T@/home/.claude/hooks/blueprint-track.sh
remove|loose|settings-hook|@T@/home/.claude/settings.json (blueprint-track.sh Skill hooks)
remove|stray|my-memory|MCP server '"'"'my-memory'"'"' (~/.claude.json)'

FULL_VERIFY='fail|rtk|rtk gain failed
fail|graphify|graphify missing
pass|gstack|gstack cloned
fail|organizze|organizze missing
fail|cmds-vendored|vendored herow-dev commands not found in plugin cache
fail|omega-bin|omega bin still present
fail|omega-settings|omega still in settings.json
fail|omega-md|OMEGA still in CLAUDE.md
fail|loose-cmds|loose blueprint.md still present
pass|model|model=opusplan
pass|effort|effortLevel=high
pass|advisor-model|advisorModel=opus
pass|autocompact|autoCompact enabled
pass|subagent-model|no subagent-model pin (inherits default)
pass|default-opus-model|ANTHROPIC_DEFAULT_OPUS_MODEL pinned
pass|default-sonnet-model|ANTHROPIC_DEFAULT_SONNET_MODEL pinned
summary|8 passed / 8 failed|review-fails'

same() {
  if [ "$2" = "$3" ]; then ok "$1"; else
    fail "$1"
    diff <(printf '%s\n' "$3") <(printf '%s\n' "$2") | sed 's/^/    /' || true
  fi
}

# 1. Pre-existing records unchanged (keyless fixture, so the verify summary is unchanged too).
E="$(new_fixture)"
D="$(run "$E" detect)"; V="$(run "$E" verify)"
same "empty HOME: detect non-Jev lines byte-identical" "$(printf '%s\n' "$D" | non_jev)" "$EMPTY_DETECT"
same "empty HOME: verify non-Jev lines byte-identical" "$(printf '%s\n' "$V" | non_jev)" "$EMPTY_VERIFY"
F="$(new_fixture)"; populate "$F"
same "populated HOME: detect non-Jev lines byte-identical" "$(run "$F" detect | non_jev)" "$FULL_DETECT"
same "populated HOME: verify non-Jev lines byte-identical" "$(run "$F" verify | non_jev)" "$FULL_VERIFY"

# 2. Keyless Jev records: manual step + info, never a fail.
printf '%s\n' "$D" | grep -qx 'tool|jev-shim|missing|-' && ok "keyless: tool|jev-shim|missing|-" || fail "jev-shim missing record"
printf '%s\n' "$D" | grep -qx 'manual|jev-key|missing|-' && ok "keyless: manual|jev-key|missing|-" || fail "manual jev-key missing record"
printf '%s\n' "$V" | grep -qx 'info|jev-key|absent' && ok "keyless verify: info|jev-key|absent" || fail "info record"
printf '%s\n' "$V" | grep -q '^fail|jev' && fail "keyless verify emitted a jev fail" || ok "keyless verify has no jev fail"

# 3. Key in env, shims not installed: present + a real failure.
D="$(run "$E" detect OPENROUTER_API_KEY=sk-SECRET)"; V="$(run "$E" verify OPENROUTER_API_KEY=sk-SECRET)"
printf '%s\n' "$D" | grep -qx 'manual|jev-key|present|env' && ok "env key: manual|jev-key|present|env" || fail "env present record"
printf '%s\n' "$V" | grep -q '^fail|jev-shim|' && ok "key without shim: fail|jev-shim" || fail "missing shim not failed"
printf '%s\n' "$D$V" | grep -q SECRET && fail "key value leaked into records" || ok "key value never in records"

# 4. Keychain stub that prints a secret: source is keychain, secret never printed.
printf '#!/bin/sh\necho sk-SECRET-KC\nexit 0\n' > "$E/security-ok"; chmod 755 "$E/security-ok"
D="$(run "$E" detect JEV_SECURITY_BIN="$E/security-ok")"
printf '%s\n' "$D" | grep -qx 'manual|jev-key|present|keychain' && ok "keychain: manual|jev-key|present|keychain" || fail "keychain record"
printf '%s\n' "$D" | grep -q SECRET && fail "keychain stub output leaked" || ok "keychain stub output never in records"

# 5. Shims installed (the install-stack step) + registry: detect installed, verify passes.
env -i HOME="$E/home" PATH="$E/bin" "$E/bin/bash" "$SCRIPTS/jev-session.sh" --install-only && ok "install step writes shims" || fail "install step failed"
grep -q 'jev-session.sh" --install-only' "$SETUP/install-stack.sh" && ok "install-stack.sh uses the shared install routine" || fail "install-stack not wired"
mkdir -p "$E/home/.claude/plugins"
printf '{"version":2,"plugins":{"herow-core@herow":[{"scope":"user","installPath":"%s"}]}}' "$PLUGIN_ROOT" > "$E/home/.claude/plugins/installed_plugins.json"
D="$(run "$E" detect OPENROUTER_API_KEY=sk-x)"; V="$(run "$E" verify OPENROUTER_API_KEY=sk-x)"
printf '%s\n' "$D" | grep -qx 'tool|jev-shim|installed|@T@/home/.herow/bin/jev' && ok "detect: tool|jev-shim|installed" || fail "installed record"
printf '%s\n' "$V" | grep -qx 'pass|jev-key|key found (env)' && ok "verify: pass|jev-key" || fail "verify key pass"
printf '%s\n' "$V" | grep -q '^pass|jev-shim|' && ok "verify: shim dry-run passes" || fail "verify shim: $(printf '%s\n' "$V" | grep jev)"
same "verify summary counts the Jev checks" "$(printf '%s\n' "$V" | tail -1)" "summary|6 passed / 12 failed|review-fails"

echo "----"
echo "$PASS passed, $FAIL failed"
[ "$FAIL" -eq 0 ]
