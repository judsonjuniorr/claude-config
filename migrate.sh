#!/usr/bin/env bash
# migrate.sh — one-time migration from the legacy symlink install (install.sh)
# to the herow plugin marketplace.
#
# What it does:
#   1. Removes symlinks in ~/.claude/{agents,commands,skills,rules} that point
#      into this repo (the old install.sh footprint).
#   2. Strips the hook entries install.sh merged into ~/.claude/settings.json
#      (markers: "claude-config-hooks/" and "github-ops/hooks/") — REQUIRED,
#      otherwise every hook fires twice once the plugin is enabled.
#   3. Removes the ~/.claude/claude-config-hooks symlink.
#   4. Prints the plugin install instructions.
#
# Idempotent: safe to run multiple times. Does not touch anything it did not create.
set -euo pipefail

CLAUDE_DIR="${CLAUDE_DIR:-$HOME/.claude}"
REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SETTINGS="$CLAUDE_DIR/settings.json"

echo "herow migrate: legacy symlink install → plugin marketplace"
echo

# ── 1. Remove symlinks pointing into this repo ─────────────────────────────
removed=0
for dir in agents commands skills rules; do
  base="$CLAUDE_DIR/$dir"
  [ -d "$base" ] || continue
  # depth 2 covers namespaced commands (~/.claude/commands/<ns>/<cmd>.md)
  while IFS= read -r link; do
    target=$(readlink "$link" || true)
    case "$target" in
      "$REPO_DIR"/*)
        rm -f "$link"
        removed=$((removed + 1))
        echo "  ↳ removed $link"
        ;;
    esac
  done < <(find "$base" -maxdepth 2 -type l 2>/dev/null)
  # prune now-empty namespace dirs
  find "$base" -mindepth 1 -maxdepth 1 -type d -empty -delete 2>/dev/null || true
done
# broken symlinks left behind by moved files (repo restructure) — prune those too
for dir in agents commands skills rules; do
  base="$CLAUDE_DIR/$dir"
  [ -d "$base" ] || continue
  while IFS= read -r link; do
    [ -e "$link" ] || { rm -f "$link"; removed=$((removed + 1)); echo "  ↳ removed broken $link"; }
  done < <(find "$base" -maxdepth 2 -type l 2>/dev/null)
done
echo "  symlinks removed: $removed"

# ── 2. Strip merged hook entries from settings.json ────────────────────────
strip_hooks() {
  local marker="$1" label="$2"
  [ -f "$SETTINGS" ] || return 0
  command -v jq >/dev/null 2>&1 || {
    echo "  ⚠ jq not found — remove hook entries containing '$marker' from $SETTINGS manually."
    return 0
  }
  cp "$SETTINGS" "$SETTINGS.bak"
  if jq --arg m "$marker" '
        if .hooks then
          .hooks |= (to_entries
            | map(.value |= [ .[] | select(([..|strings] | any(contains($m))) | not) ]
                  | select(.value | length > 0))
            | from_entries)
        else . end
      ' "$SETTINGS" > "$SETTINGS.tmp"; then
    mv "$SETTINGS.tmp" "$SETTINGS"
    echo "  ↳ hooks stripped from settings.json ($label)"
  else
    rm -f "$SETTINGS.tmp"
    echo "  ⚠ hook strip failed ($label) — settings.json unchanged (backup: settings.json.bak)"
  fi
}
strip_hooks "claude-config-hooks/" "claude-config guardrails"
strip_hooks "github-ops/hooks/" "git-guard"

# ── 3. Remove the stable hooks symlink ─────────────────────────────────────
if [ -L "$CLAUDE_DIR/claude-config-hooks" ]; then
  rm -f "$CLAUDE_DIR/claude-config-hooks"
  echo "  ↳ removed $CLAUDE_DIR/claude-config-hooks"
fi

# ── 4. Next steps ───────────────────────────────────────────────────────────
cat <<'EOF'

Done. Now install via the plugin marketplace (inside Claude Code):

  /plugin marketplace add judsonjuniorr/claude-config
  /plugin install herow-core@herow      # hooks, rules, github-ops, review agents
  /plugin install herow-dev@herow       # code/git/react/python commands + dev agents
  /plugin install herow-seo@herow       # SEO suite        (optional)
  /plugin install herow-finance@herow   # finance suite    (optional)
  /plugin install herow-extras@herow    # PRD, organizer   (optional)

Enable auto-update once (new versions then apply on every session start):

  /plugin  →  Marketplaces  →  herow  →  Enable auto-update

Command names changed with plugin namespacing, e.g.:
  /code:review        →  /herow-dev:code:review
  /git:pr             →  /herow-dev:git:pr
  /seo:weekly-audit   →  /herow-seo:weekly-audit
  /finance:organizze  →  /herow-finance:organizze
EOF
