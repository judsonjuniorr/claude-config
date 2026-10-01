#!/usr/bin/env bash
# Tests for jev-session.sh: atomic shim install, gated routing block, policy line, one-time hint.
# Run: bash plugins/herow-core/scripts/tests/test-jev-session.sh
set -eu

SCRIPTS="$(cd "$(dirname "$0")/.." && pwd)"
PLUGIN_ROOT="$(cd "$SCRIPTS/.." && pwd)"
HOOK="$SCRIPTS/jev-session.sh"

T="$(mktemp -d)"
trap 'chmod -R u+w "$T" 2>/dev/null; rm -rf "$T"' EXIT

PASS=0
FAIL=0
ok()   { PASS=$((PASS + 1)); echo "ok   - $1"; }
fail() { FAIL=$((FAIL + 1)); echo "FAIL - $1"; }

export HOME="$T/home"
export CLAUDE_CONFIG_DIR="$T/claude"
export JEV_SECURITY_BIN="$T/no-such-security"
unset OPENROUTER_API_KEY 2>/dev/null || true
mkdir -p "$HOME"

fresh() { export HEROW_HOME="$T/herow-$1"; }
run() { bash "$HOOK"; }

# Keyless: one-time hint, then silence.
fresh keyless
out="$(run)"
case "$out" in "Jev routing is off: no OpenRouter key. /herow-core:doctor"*) ok "keyless first run prints the hint";; *) fail "keyless hint: $out";; esac
case "$out" in *"jev-route"*) fail "keyless printed a routing block";; *) ok "keyless prints no routing block";; esac
[ -e "$HEROW_HOME/jev/.hinted" ] && ok "hint marker written" || fail "hint marker missing"
[ -z "$(run)" ] && ok "keyless second run is silent" || fail "hint repeated"

# Install is atomic and the helper copy matches the plugin's.
cmp -s "$HEROW_HOME/bin/jev_env.py" "$PLUGIN_ROOT/skills/jev/scripts/jev_env.py" \
  && ok "copied helper is byte-identical to the plugin copy" || fail "helper parity"
cmp -s "$HEROW_HOME/bin/jev" "$SCRIPTS/jev-shim.sh" && cmp -s "$HEROW_HOME/bin/jev-route" "$SCRIPTS/jev-shim.sh" \
  && ok "both shims match jev-shim.sh" || fail "shim parity"
[ -x "$HEROW_HOME/bin/jev" ] && [ -x "$HEROW_HOME/bin/jev-route" ] && ok "shims executable" || fail "shims not executable"
bin_list="$(find "$HEROW_HOME/bin" -mindepth 1 -exec basename {} \; | LC_ALL=C sort | tr '\n' ' ')"
[ "$bin_list" = "jev jev-route jev_env.py " ] && ok "no tmp leftovers in bin/" || fail "bin contents: $bin_list"
echo "# stale" >> "$HEROW_HOME/bin/jev"
run >/dev/null
cmp -s "$HEROW_HOME/bin/jev" "$SCRIPTS/jev-shim.sh" && ok "stale shim refreshed" || fail "stale shim kept"

# routing_assist:false silences even the hint.
fresh optout
mkdir -p "$HEROW_HOME/jev"
printf '{"routing_assist": false}' > "$HEROW_HOME/jev/config.json"
[ -z "$(run)" ] && ok "routing_assist:false keyless -> silent" || fail "opt-out keyless printed"
[ -z "$(OPENROUTER_API_KEY=sk-x run)" ] && ok "routing_assist:false with key -> no block" || fail "opt-out with key printed"

# Env key: block with a literal, existing jev-route path and the generic policy.
fresh envkey
out="$(OPENROUTER_API_KEY=sk-SECRET-ENV run)"
route_path="$(printf '%s\n' "$out" | sed -n 's/^`\([^`]*jev-route\) .*/\1/p' | head -1)"
[ "$route_path" = "$HEROW_HOME/bin/jev-route" ] && [ -x "$route_path" ] \
  && ok "block carries the literal existing jev-route path" || fail "block path: '$route_path'"
case "$out" in *"Routing policy: generic."*) ok "generic policy by default";; *) fail "policy line missing";; esac
case "$out" in *"supersedes any older"*) ok "block says it supersedes CLAUDE.md text";; *) fail "supersede line missing";; esac
case "$out" in *SECRET*) fail "key material in hook output";; *) ok "env key value never printed";; esac
[ ! -e "$HEROW_HOME/jev/.hinted" ] && ok "no hint marker when a key exists" || fail "hint marker with key"

# consents.md opt-in switches the policy line.
mkdir -p "$HEROW_HOME/jev"
printf 'routing: project-names\n' > "$HEROW_HOME/jev/consents.md"
case "$(OPENROUTER_API_KEY=sk-x run)" in *"Routing policy: project-names."*) ok "project-names policy from consents.md";; *) fail "project-names policy";; esac

# Malformed config: default behavior, warning never reaches stdout.
printf '{broken' > "$HEROW_HOME/jev/config.json"
out="$(OPENROUTER_API_KEY=sk-x run 2>/dev/null)"
case "$out" in *"jev-route"*) ok "malformed config -> default (block shown)";; *) fail "malformed config hid the block";; esac
case "$out" in *config.json*|*malformed*) fail "config warning leaked to stdout";; *) ok "config warning kept off stdout";; esac

# Keychain stub that prints a secret: presence is detected, the secret never printed.
fresh keychain
cat > "$T/security-leaky" <<'STUB'
#!/usr/bin/env bash
echo "sk-SECRET-STDOUT"; echo "sk-SECRET-STDERR" >&2; exit 0
STUB
chmod 755 "$T/security-leaky"
out="$(JEV_SECURITY_BIN="$T/security-leaky" run 2>&1)"
case "$out" in *"jev-route"*) ok "keychain key -> block";; *) fail "keychain block missing";; esac
case "$out" in *SECRET*) fail "stub secret leaked into hook output";; *) ok "stub secret never reaches hook output";; esac

# Read-only HEROW_HOME: install fails silently, no block.
fresh readonly
mkdir -p "$HEROW_HOME"
chmod 555 "$HEROW_HOME"
out="$(OPENROUTER_API_KEY=sk-x run 2>&1)"; rc=$?
[ -z "$out" ] && [ "$rc" -eq 0 ] && ok "read-only HEROW_HOME -> silent, exit 0" || fail "read-only: rc=$rc out=$out"
chmod 755 "$HEROW_HOME"

# HEROW_HOME unset -> ~/.herow.
(
  unset HEROW_HOME
  out="$(OPENROUTER_API_KEY=sk-x bash "$HOOK")"
  case "$out" in *"$HOME/.herow/bin/jev-route"*) exit 0;; *) exit 1;; esac
) && ok "HEROW_HOME unset -> block points at ~/.herow/bin/jev-route" || fail "default HEROW_HOME"

echo "----"
echo "$PASS passed, $FAIL failed"
[ "$FAIL" -eq 0 ]
