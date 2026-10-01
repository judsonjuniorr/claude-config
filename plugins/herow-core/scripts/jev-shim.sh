#!/usr/bin/env bash
# Constant entry point installed as ${HEROW_HOME:-$HOME/.herow}/bin/{jev,jev-route}.
# Resolves the active herow-core install at exec time, so plugin upgrades never leave it stale.
set -u

name="$(basename "$0")"
case "$name" in
  jev) target="jev.py" ;;
  jev-route) target="route.py" ;;
  *)
    echo "jev unavailable: unknown shim name '$name'. Reinstall the shims with /herow-core:doctor." >&2
    exit 1
    ;;
esac

if ! command -v python3 >/dev/null 2>&1; then
  echo "jev unavailable: python3 not found. Install python3 (3.9+) and retry." >&2
  exit 1
fi

helper="${HEROW_HOME:-$HOME/.herow}/bin/jev_env.py"
if [ ! -f "$helper" ]; then
  echo "jev unavailable: helper $helper is missing. Start a new Claude Code session or run /herow-core:doctor." >&2
  exit 1
fi

root="$(python3 "$helper" resolve herow-core)" || exit 1
script="$root/skills/jev/scripts/$target"
if [ ! -f "$script" ]; then
  echo "jev unavailable: herow-core at $root has no skills/jev (version too old). Run /herow-core:upgrade." >&2
  exit 1
fi

exec python3 "$script" "$@"
