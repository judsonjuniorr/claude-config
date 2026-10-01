#!/usr/bin/env bash
# Tests for jev-shim.sh: basename dispatch and exec-time resolution of herow-core.
# Run: bash plugins/herow-core/scripts/tests/test-jev-shim.sh
set -eu

SCRIPTS="$(cd "$(dirname "$0")/.." && pwd)"
PLUGIN_ROOT="$(cd "$SCRIPTS/.." && pwd)"
SESSION="$SCRIPTS/jev-session.sh"

T="$(mktemp -d)"
trap 'rm -rf "$T"' EXIT

PASS=0
FAIL=0
ok()   { PASS=$((PASS + 1)); echo "ok   - $1"; }
fail() { FAIL=$((FAIL + 1)); echo "FAIL - $1"; }

export HOME="$T/home"
export CLAUDE_CONFIG_DIR="$T/claude"
export HEROW_HOME="$T/herow"
export JEV_SECURITY_BIN="$T/no-such-security"
unset OPENROUTER_API_KEY JEV_PLUGIN_REGISTRY 2>/dev/null || true
mkdir -p "$HOME" "$CLAUDE_CONFIG_DIR/plugins" "$T/project/sub"

# A fake herow-core install whose scripts just announce themselves.
fake_install() {
  local dir="$T/cache/$1"
  mkdir -p "$dir/skills/jev/scripts"
  printf 'import sys\nprint("%s-jev", *sys.argv[1:])\n' "$1" > "$dir/skills/jev/scripts/jev.py"
  printf 'import sys\nprint("%s-route", *sys.argv[1:])\n' "$1" > "$dir/skills/jev/scripts/route.py"
  echo "$dir"
}

registry() { printf '%s' "$1" > "$CLAUDE_CONFIG_DIR/plugins/installed_plugins.json"; }

USER_DIR="$(fake_install user)"
PROJ_DIR="$(fake_install proj)"
USER_ONLY='{"version":2,"plugins":{"herow-core@herow":[{"scope":"user","installPath":"'"$USER_DIR"'"}]}}'
BOTH='{"version":2,"plugins":{"herow-core@herow":[{"scope":"user","installPath":"'"$USER_DIR"'"},{"scope":"project","installPath":"'"$PROJ_DIR"'","projectPath":"'"$T/project"'"}]}}'

bash "$SESSION" --install-only && ok "install-only exits 0" || fail "install-only failed"
[ -x "$HEROW_HOME/bin/jev" ] && [ -x "$HEROW_HOME/bin/jev-route" ] && [ -f "$HEROW_HOME/bin/jev_env.py" ] \
  && ok "shims + helper installed under overridden HEROW_HOME" || fail "shims not installed"

registry "$USER_ONLY"
[ "$("$HEROW_HOME/bin/jev" --x 2>&1)" = "user-jev --x" ] && ok "jev dispatches to user jev.py" || fail "jev user dispatch"
[ "$("$HEROW_HOME/bin/jev-route" a b 2>&1)" = "user-route a b" ] && ok "jev-route dispatches to route.py" || fail "jev-route dispatch"

registry "$BOTH"
out="$(cd "$T/project/sub" && "$HEROW_HOME/bin/jev" 2>&1)"
[ "$out" = "proj-jev" ] && ok "project scope beats user inside the project" || fail "project precedence: $out"
out="$(cd "$T" && "$HEROW_HOME/bin/jev" 2>&1)"
[ "$out" = "user-jev" ] && ok "user scope outside the project" || fail "outside project: $out"

registry "$USER_ONLY"
printf '{"enabledPlugins":{"herow-core@herow":false}}' > "$CLAUDE_CONFIG_DIR/settings.json"
if out="$("$HEROW_HOME/bin/jev" 2>&1)"; then fail "disabled should exit 1"; else
  case "$out" in "jev unavailable: herow-core is disabled"*) ok "disabled -> unavailable with fix";; *) fail "disabled msg: $out";; esac
fi
rm -f "$CLAUDE_CONFIG_DIR/settings.json"

registry '{"version":2,"plugins":{"herow-core@herow":[{"scope":"user","installPath":"'"$T/cache/gone"'"}]}}'
if out="$("$HEROW_HOME/bin/jev" 2>&1)"; then fail "gone path should exit 1"; else
  case "$out" in "jev unavailable: herow-core install path is gone"*"/herow-core:upgrade"*) ok "missing installPath -> unavailable";; *) fail "gone msg: $out";; esac
fi

registry '{not json'
if out="$("$HEROW_HOME/bin/jev" 2>&1)"; then fail "malformed registry should exit 1"; else
  case "$out" in "jev unavailable: installed_plugins.json is not valid JSON"*) ok "malformed registry -> unavailable, no traceback";; *) fail "malformed msg: $out";; esac
fi

OLD_DIR="$T/cache/old"; mkdir -p "$OLD_DIR"
registry '{"version":2,"plugins":{"herow-core@herow":[{"scope":"user","installPath":"'"$OLD_DIR"'"}]}}'
if out="$("$HEROW_HOME/bin/jev" 2>&1)"; then fail "old version should exit 1"; else
  case "$out" in *"has no skills/jev"*) ok "old herow-core -> unavailable";; *) fail "old msg: $out";; esac
fi

registry "$USER_ONLY"
cp "$HEROW_HOME/bin/jev" "$T/jevx"
if out="$(bash "$T/jevx" 2>&1)"; then fail "unknown name should exit 1"; else
  case "$out" in "jev unavailable: unknown shim name 'jevx'"*) ok "unknown basename -> unavailable";; *) fail "unknown msg: $out";; esac
fi

mkdir -p "$T/nopy"
for c in bash basename dirname; do ln -sf "$(command -v "$c")" "$T/nopy/$c"; done
if out="$(PATH="$T/nopy" "$T/nopy/bash" "$HEROW_HOME/bin/jev" 2>&1)"; then fail "no python3 should exit 1"; else
  case "$out" in "jev unavailable: python3 not found"*) ok "missing python3 -> unavailable";; *) fail "no python3 msg: $out";; esac
fi

mv "$HEROW_HOME/bin/jev_env.py" "$T/helper.bak"
if out="$("$HEROW_HOME/bin/jev" 2>&1)"; then fail "missing helper should exit 1"; else
  case "$out" in "jev unavailable: helper"*) ok "missing helper -> unavailable";; *) fail "helper msg: $out";; esac
fi
mv "$T/helper.bak" "$HEROW_HOME/bin/jev_env.py"

# HEROW_HOME unset: everything lands in ~/.herow, and the real jev.py dry-run needs no key.
registry '{"version":2,"plugins":{"herow-core@herow":[{"scope":"user","installPath":"'"$PLUGIN_ROOT"'"}]}}'
(
  unset HEROW_HOME
  bash "$SESSION" --install-only || exit 1
  [ -x "$HOME/.herow/bin/jev" ] || exit 1
  echo '{"items":[{"id":"t1","state":"hello"}],"questions":{"q":{"type":"noul","instructions":"x","criteria":{"true":"a","false":"b"}}}}' \
    | "$HOME/.herow/bin/jev" --dry-run | python3 -c 'import json,sys; assert json.load(sys.stdin)["dry_run"][0]["state"]=="hello"'
) && ok "HEROW_HOME unset -> ~/.herow shims; real --dry-run works without a key" || fail "default HEROW_HOME / dry-run"

# No key at all: the real jev.py exits 1 with a one-line problem + fix.
out="$(echo '{"items":[{"id":"t1","state":"x"}],"questions":{}}' | "$HEROW_HOME/bin/jev" 2>&1 >/dev/null)" && fail "keyless call should exit 1" || {
  case "$out" in "jev unavailable: no OpenRouter key found. Fix:"*) ok "keyless real call -> unavailable + fix";; *) fail "keyless msg: $out";; esac
}

echo "----"
echo "$PASS passed, $FAIL failed"
[ "$FAIL" -eq 0 ]
