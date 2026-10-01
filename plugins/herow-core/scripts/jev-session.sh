#!/usr/bin/env bash
# SessionStart hook: installs the Jev shims, then injects the routing block only when a key exists.
# Prints nothing on any failure: a Jev problem must never add noise to session context.
# `--install-only` installs the shims and exits 0/1 (used by setup/install-stack.sh).
set -u

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." 2>/dev/null && pwd)" || exit 0
HH="${HEROW_HOME:-$HOME/.herow}"
BIN="$HH/bin"
SHIM_SRC="$ROOT/scripts/jev-shim.sh"
HELPER_SRC="$ROOT/skills/jev/scripts/jev_env.py"

# tmp + mv -f in the same dir: a concurrently running shim never sees a partial file.
install_file() {
  local src="$1" dst="$2" tmp
  if [ -x "$dst" ] && cmp -s "$src" "$dst"; then return 0; fi
  tmp="$(mktemp "$BIN/.jev-tmp.XXXXXX" 2>/dev/null)" || return 1
  if cp "$src" "$tmp" 2>/dev/null && chmod 755 "$tmp" 2>/dev/null && mv -f "$tmp" "$dst" 2>/dev/null; then
    return 0
  fi
  rm -f "$tmp" 2>/dev/null
  return 1
}

install_all() {
  [ -f "$SHIM_SRC" ] && [ -f "$HELPER_SRC" ] || return 1
  mkdir -p "$BIN" 2>/dev/null || return 1
  install_file "$SHIM_SRC" "$BIN/jev" &&
    install_file "$SHIM_SRC" "$BIN/jev-route" &&
    install_file "$HELPER_SRC" "$BIN/jev_env.py"
}

if [ "${1:-}" = "--install-only" ]; then
  install_all
  exit $?
fi

command -v python3 >/dev/null 2>&1 || exit 0
install_all || exit 0

routing_assist=true
routing=generic
while IFS='=' read -r k v; do
  case "$k" in
    routing_assist) routing_assist="$v" ;;
    routing) routing="$v" ;;
  esac
done <<POLICY
$(python3 "$HELPER_SRC" policy 2>/dev/null)
POLICY
[ "$routing_assist" = "false" ] && exit 0

source_name="$(python3 "$HELPER_SRC" probe 2>/dev/null)"
if [ "$source_name" != "env" ] && [ "$source_name" != "keychain" ]; then
  marker="$HH/jev/.hinted"
  if [ ! -e "$marker" ] && mkdir -p "$HH/jev" 2>/dev/null && : >"$marker" 2>/dev/null; then
    echo "Jev routing is off: no OpenRouter key. /herow-core:doctor sets it up (this hint shows once)."
  fi
  exit 0
fi

[ -x "$BIN/jev-route" ] || exit 0

if [ "$routing" = "project-names" ]; then
  policy_line="Routing policy: project-names. Summaries may name the project or person (the user consented in $HH/jev/consents.md)."
else
  policy_line="Routing policy: generic. Keep summaries generic: no project, person or company names."
fi

cat <<BLOCK
## Jev routing assist (herow-core)

At the start of a multi-step task, or when choosing between subagents or skills is ambiguous, run
\`$BIN/jev-route "<summary 1>" ["<summary 2>" ...]\` with one short English summary per subtask.
Send only a summary you wrote, never the raw prompt or file contents (\`--redact-br\` is always on).
No per-call confirmation is needed: the stored key is the user's opt-in.
$policy_line

The answer is advisory. Skip anything listed under \`uncertain\`. On \`vault-first\` (only emitted when a
vault skill is installed), run the vault skill first. On \`jev unavailable\`, use the routing table in
CLAUDE.md if one exists; otherwise decide inline. This block supersedes any older "Jev routing assist"
text in CLAUDE.md.
BLOCK
exit 0
