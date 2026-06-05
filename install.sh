#!/usr/bin/env bash
set -euo pipefail

REPO_DIR=$(cd "$(dirname "$0")" && pwd)
CLAUDE_DIR="$HOME/.claude"

# ── claude-config additions: paths ──────────────────────────────────────────────
MANIFEST="$REPO_DIR/manifests/profiles.json"
MCP_REGISTRY="$REPO_DIR/mcp-configs/registry.json"
RULES_COMMON_DIR="$REPO_DIR/rules/common"
GLOBAL_HOOKS_SRC="$REPO_DIR/hooks/hooks.json"
GLOBAL_HOOKS_LINK="$CLAUDE_DIR/claude-config-hooks"  # symlink → $REPO_DIR/hooks (stable path baked into settings.json)
GLOBAL_HOOKS_MARKER="claude-config-hooks/"           # identifies our hook entries in settings.json
POINTER_RULE="language-rules-pointer.md"             # templated real file, not a symlink

usage() {
  cat <<EOF
Usage: $(basename "$0") [OPTIONS] [COMMAND]

Commands:
  (none)            Interactive install — select assets to install
  uninstall         Interactive uninstall — select installed assets to remove

Options:
  --profile NAME    Install a named bundle from manifests/profiles.json
                    (also installs global hooks + common rules)
  --list-profiles   List available profiles and their assets
  --mcp             Print MCP server config guidance (env vars, opt-in; writes nothing)
  --doctor          Diagnose the installation (symlinks, hooks, rules, manifest)
  --all             Install all assets without prompting
  --replace         Overwrite existing files/symlinks (default: backup as .bak)
  --help            Show this help and exit

Profiles, global hooks (doc-file-warning, config-protection), and common rules
(auto-loaded from ~/.claude/rules/) are claude-config extensions. Language rules
under rules/<lang>/ are applied per-project by the Claude session, not installed.
EOF
  exit 0
}

# ── Argument parsing ──────────────────────────────────────────────────────────
MODE="install"
OPT_ALL=false
OPT_REPLACE=false
OPT_PROFILE=""

while [ "$#" -gt 0 ]; do
  case "$1" in
    uninstall)       MODE="uninstall" ;;
    --all)           OPT_ALL=true ;;
    --replace)       OPT_REPLACE=true ;;
    --profile)       shift; OPT_PROFILE="${1:-}"; [ -n "$OPT_PROFILE" ] || { echo "ERROR: --profile requires a name"; usage; } ;;
    --profile=*)     OPT_PROFILE="${1#*=}" ;;
    --list-profiles) MODE="list-profiles" ;;
    --mcp)           MODE="mcp" ;;
    --doctor)        MODE="doctor" ;;
    --help|-h)       usage ;;
    *) echo "Unknown option: $1"; usage ;;
  esac
  shift
done

# ── Capability detection ──────────────────────────────────────────────────────
BASH_MAJOR="${BASH_VERSINFO[0]:-3}"
HAS_FZF=false
USE_FZF=false
if command -v fzf >/dev/null 2>&1; then HAS_FZF=true; fi
if $HAS_FZF && [ "$BASH_MAJOR" -ge 4 ]; then USE_FZF=true; fi

# ── Ensure destination dirs exist ─────────────────────────────────────────────
mkdir -p "$CLAUDE_DIR/commands" "$CLAUDE_DIR/skills" "$CLAUDE_DIR/agents"

# ── Broken symlink check ──────────────────────────────────────────────────────
broken=()
while IFS= read -r link; do
  broken+=("$link")
done < <(find "$CLAUDE_DIR" -maxdepth 2 -type l ! -exec test -e {} \; -print 2>/dev/null || true)

if [ "${#broken[@]}" -gt 0 ]; then
  echo "WARNING: broken symlinks found in $CLAUDE_DIR:"
  for b in "${broken[@]}"; do echo "  $b"; done
  echo "  (repo may have moved — re-run install.sh to fix)"
  echo
fi

# ── Asset discovery ───────────────────────────────────────────────────────────
# Returns lines of the form: "type|name|src_file"
# src_file is the principal file; for namespace dirs it's the dir path itself (ends with /)
discover_assets() {
  # commands: two patterns
  #   standard:  commands/{name}/{name}.md  → link file
  #   namespace: commands/{ns}/             → link directory (when no {ns}/{ns}.md exists)
  for dir in "$REPO_DIR"/commands/*/; do
    [ -d "$dir" ] || continue
    name=$(basename "$dir")
    principal="$dir${name}.md"
    if [ -f "$principal" ]; then
      # standard command
      echo "commands|$name|$principal"
    else
      # namespace dir: any non-README .md inside
      has_md=false
      for f in "$dir"*.md; do
        [ -f "$f" ] || continue
        [ "$(basename "$f")" = "README.md" ] && continue
        has_md=true
        break
      done
      $has_md && echo "commands-ns|$name|${dir%/}"
    fi
  done

  # skills/{name}/SKILL.md
  for f in "$REPO_DIR"/skills/*/SKILL.md; do
    [ -f "$f" ] || continue
    name=$(basename "$(dirname "$f")")
    echo "skills|$name|$f"
  done

  # agents/{name}/{name}.md
  for f in "$REPO_DIR"/agents/*/*.md; do
    [ -f "$f" ] || continue
    name=$(basename "$(dirname "$f")")
    file=$(basename "$f")
    [ "$file" = "README.md" ] && continue
    [ "$file" = "${name}.md" ] || continue
    echo "agents|$name|$f"
  done

  # agents/{name}.md (flat layout)
  for f in "$REPO_DIR"/agents/*.md; do
    [ -f "$f" ] || continue
    file=$(basename "$f")
    [ "$file" = "README.md" ] && continue
    name="${file%.md}"
    echo "agents|$name|$f"
  done
}

# Collect assets into parallel arrays (bash 3.x safe)
ASSET_TYPES=()
ASSET_NAMES=()
ASSET_SRCS=()

while IFS='|' read -r t n s; do
  ASSET_TYPES+=("$t")
  ASSET_NAMES+=("$n")
  ASSET_SRCS+=("$s")
done < <(discover_assets)

if [ "${#ASSET_NAMES[@]}" -eq 0 ]; then
  echo "No assets found in $REPO_DIR."
  exit 1
fi

# ── Status helper ─────────────────────────────────────────────────────────────
is_installed() {
  local type="$1" name="$2"
  local dest
  case "$type" in
    skills)      dest="$CLAUDE_DIR/skills/$name" ;;
    commands-ns) dest="$CLAUDE_DIR/commands/$name" ;;
    commands)    dest="$CLAUDE_DIR/commands/$name.md" ;;
    *)           dest="$CLAUDE_DIR/$type/$name.md" ;;
  esac
  [ -e "$dest" ] || [ -L "$dest" ]
}

# ── Selection ─────────────────────────────────────────────────────────────────
# selected_indices: space-separated indices into ASSET_NAMES
select_assets_fzf() {
  local items=()
  local i=0
  while [ "$i" -lt "${#ASSET_NAMES[@]}" ]; do
    local status="new" display_type="${ASSET_TYPES[$i]}"
    [ "$display_type" = "commands-ns" ] && display_type="commands"
    is_installed "${ASSET_TYPES[$i]}" "${ASSET_NAMES[$i]}" && status="installed"
    items+=("$(printf '%s | %-30s [%s]' "$display_type" "${ASSET_NAMES[$i]}" "$status")")
    i=$((i + 1))
  done

  local chosen
  chosen=$(printf '%s\n' "${items[@]}" | \
    fzf --multi \
        --header="SPACE to select, ENTER to confirm (Tab also works)" \
        --prompt="Install > " \
        --height=40% \
        --layout=reverse)

  local idx=0
  for line in "${items[@]}"; do
    if echo "$chosen" | grep -qF "$line"; then
      echo "$idx"
    fi
    idx=$((idx + 1))
  done
}

select_assets_menu() {
  local i=0
  echo "Available assets:" >&2
  while [ "$i" -lt "${#ASSET_NAMES[@]}" ]; do
    local status="new" display_type="${ASSET_TYPES[$i]}"
    [ "$display_type" = "commands-ns" ] && display_type="commands"
    is_installed "${ASSET_TYPES[$i]}" "${ASSET_NAMES[$i]}" && status="installed"
    printf '  %2d) [%-9s] %-30s [%s]\n' $((i+1)) "$display_type" "${ASSET_NAMES[$i]}" "$status" >&2
    i=$((i + 1))
  done
  echo >&2
  printf "Enter numbers separated by spaces (e.g. 1 3 4), or 'all': " >&2
  read -r selection </dev/tty
  if [ "$selection" = "all" ]; then
    i=0
    while [ "$i" -lt "${#ASSET_NAMES[@]}" ]; do
      echo "$i"
      i=$((i + 1))
    done
    return
  fi
  for n in $selection; do
    local idx=$((n - 1))
    if [ "$idx" -ge 0 ] && [ "$idx" -lt "${#ASSET_NAMES[@]}" ]; then
      echo "$idx"
    fi
  done
}

# ── Install/uninstall helpers ─────────────────────────────────────────────────
dest_for() {
  local type="$1" name="$2"
  if [ "$type" = "skills" ]; then
    echo "$CLAUDE_DIR/skills/$name"
  elif [ "$type" = "commands-ns" ]; then
    echo "$CLAUDE_DIR/commands/$name"
  elif [ "$type" = "commands" ]; then
    echo "$CLAUDE_DIR/commands/$name.md"
  else
    echo "$CLAUDE_DIR/$type/$name.md"
  fi
}

handle_conflict() {
  local dest="$1"
  if [ ! -e "$dest" ] && [ ! -L "$dest" ]; then return 0; fi
  if $OPT_REPLACE; then
    rm -rf "$dest"
    return 0
  fi
  # default: backup
  mv "$dest" "${dest}.bak"
  echo "  (backed up existing to $(basename "${dest}").bak)"
}

install_asset() {
  local type="$1" name="$2" src="$3"
  local src_dir
  src_dir=$(dirname "$src")

  if [ "$type" = "skills" ]; then
    # Install entire skill dir as a symlink
    local dest="$CLAUDE_DIR/skills/$name"
    if [ -e "$dest" ] || [ -L "$dest" ]; then
      if ! $OPT_REPLACE; then
        if [ -L "$dest" ] && [ "$(readlink "$dest")" = "$src_dir" ]; then
          echo "  $type/$name — already linked, skipping"
          return
        fi
        mv "$dest" "${dest}.bak"
        echo "  (backed up existing to $name.bak)"
      else
        rm -rf "$dest"
      fi
    fi
    ln -s "$src_dir" "$dest"
    echo "  ✓ $type/$name"
  elif [ "$type" = "commands-ns" ]; then
    # Namespace dir: create real dir, symlink each non-README file/dir inside
    # src = path to namespace directory (e.g. .../commands/finance)
    local dest="$CLAUDE_DIR/commands/$name"
    # If it's a symlink (from old install), replace with real dir
    if [ -L "$dest" ]; then
      $OPT_REPLACE && rm -f "$dest" || { mv "$dest" "${dest}.bak"; echo "  (backed up existing symlink to $name.bak)"; }
    fi
    if [ -e "$dest" ] && [ ! -d "$dest" ]; then
      $OPT_REPLACE && rm -f "$dest" || { echo "ERROR: $dest exists as a file. Run with --replace to overwrite."; return 1; }
    fi
    mkdir -p "$dest"
    local any_installed=false
    for item in "$src"/*/; do
      [ -d "$item" ] || continue
      local iname
      iname=$(basename "$item")
      [ "$iname" = "README.md" ] && continue
      local idest="$dest/$iname"
      if [ -e "$idest" ] || [ -L "$idest" ]; then
        $OPT_REPLACE && rm -rf "$idest" || { mv "$idest" "${idest}.bak"; }
      fi
      ln -s "${item%/}" "$idest"
      any_installed=true
    done
    for item in "$src"/*.md; do
      [ -f "$item" ] || continue
      [ "$(basename "$item")" = "README.md" ] && continue
      local idest="$dest/$(basename "$item")"
      if [ -e "$idest" ] || [ -L "$idest" ]; then
        if [ -L "$idest" ] && [ "$(readlink "$idest")" = "$item" ]; then continue; fi
        $OPT_REPLACE && rm -f "$idest" || { mv "$idest" "${idest}.bak"; }
      fi
      if $USE_SYMLINK; then
        ln -s "$item" "$idest"
      else
        cp "$item" "$idest"
      fi
      any_installed=true
    done
    $any_installed && echo "  ✓ commands/$name (namespace)" || echo "  commands/$name — nothing to install"
    return
  else
    local dest
    dest=$(dest_for "$type" "$name")

    # Check if dest already points to the same source
    if [ -L "$dest" ] && [ "$(readlink "$dest")" = "$src" ]; then
      echo "  $type/$name — already linked, skipping"
      return
    fi

    handle_conflict "$dest"

    if $USE_SYMLINK; then
      ln -s "$src" "$dest"
    else
      cp "$src" "$dest"
    fi
    echo "  ✓ $type/$name"

    # Dependencies: any non-README directory alongside the main file
    for dep in "$src_dir"/*/; do
      [ -d "$dep" ] || continue
      dep_name=$(basename "$dep")
      [ "$dep_name" = "README.md" ] && continue
      local dep_dest="$CLAUDE_DIR/$type/$dep_name"
      if [ -e "$dep_dest" ] || [ -L "$dep_dest" ]; then
        if ! $OPT_REPLACE; then
          if [ -L "$dep_dest" ] && [ "$(readlink "$dep_dest")" = "${dep%/}" ]; then
            continue
          fi
          mv "$dep_dest" "${dep_dest}.bak"
        else
          rm -rf "$dep_dest"
        fi
      fi
      ln -s "${dep%/}" "$dep_dest"
      echo "    ↳ $dep_name/ (dependency)"
    done
  fi
}

# ── Uninstall ─────────────────────────────────────────────────────────────────
uninstall_mode() {
  # Find installed assets (those that are symlinks pointing into REPO_DIR)
  local inst_types=()
  local inst_names=()
  local inst_dests=()

  local i=0
  while [ "$i" -lt "${#ASSET_NAMES[@]}" ]; do
    local type="${ASSET_TYPES[$i]}" name="${ASSET_NAMES[$i]}"
    is_installed "$type" "$name" || { i=$((i+1)); continue; }
    local dest
    dest=$(dest_for "$type" "$name")
    { [ -e "$dest" ] || [ -L "$dest" ]; } || { i=$((i+1)); continue; }
    inst_types+=("$type")
    inst_names+=("$name")
    inst_dests+=("$dest")
    i=$((i+1))
  done

  if [ "${#inst_names[@]}" -eq 0 ]; then
    echo "Nothing installed from this repo."
    exit 0
  fi

  local selected_indices=()

  if $OPT_ALL; then
    i=0
    while [ "$i" -lt "${#inst_names[@]}" ]; do
      selected_indices+=("$i"); i=$((i+1))
    done
  else
    echo "Installed assets:"
    i=0
    while [ "$i" -lt "${#inst_names[@]}" ]; do
      printf '  %2d) [%-9s] %s\n' $((i+1)) "${inst_types[$i]}" "${inst_names[$i]}"
      i=$((i+1))
    done
    echo
    echo "Enter numbers to uninstall (e.g. 1 3), or 'all':"
    read -r selection
    if [ "$selection" = "all" ]; then
      i=0
      while [ "$i" -lt "${#inst_names[@]}" ]; do selected_indices+=("$i"); i=$((i+1)); done
    else
      for n in $selection; do
        local idx=$((n - 1))
        if [ "$idx" -ge 0 ] && [ "$idx" -lt "${#inst_names[@]}" ]; then
          selected_indices+=("$idx")
        fi
      done
    fi
  fi

  if [ "${#selected_indices[@]}" -eq 0 ]; then
    echo "Nothing selected."
    exit 0
  fi

  echo
  echo "Removing:"
  local removed_names=()
  for i in "${selected_indices[@]}"; do
    local dest="${inst_dests[$i]}"
    rm -rf "$dest"
    removed_names+=("${inst_names[$i]}")
    echo "  ✓ ${inst_types[$i]}/${inst_names[$i]}"
    # Also remove dependency dirs
    local src_dir
    src_dir=$(dirname "${ASSET_SRCS[$i]}")
    for dep in "$src_dir"/*/; do
      [ -d "$dep" ] || continue
      local dep_name
      dep_name=$(basename "$dep")
      [ "$dep_name" = "README.md" ] && continue
      local dep_dest="$CLAUDE_DIR/${inst_types[$i]}/$dep_name"
      if [ -L "$dep_dest" ]; then
        rm -f "$dep_dest"
        echo "    ↳ $dep_name/ (dependency removed)"
      fi
    done
  done
  if contains_github_ops "${removed_names[@]}"; then
    remove_github_ops_hooks
  fi
  # Full uninstall (every installed asset selected): also clear the global footprint
  # (guardrail hooks + common rules) so nothing is left pointing at the repo.
  if [ "${#selected_indices[@]}" -eq "${#inst_names[@]}" ]; then
    remove_global_hooks
    remove_common_rules
  fi
  echo
  echo "Done."
}

# ── Hooks (settings.json) ───────────────────────────────────────────────────────
# Hooks are registered in ~/.claude/settings.json (not symlinked), tagged by a
# marker substring so each source's entries can be merged/removed idempotently
# without touching another source's. Two callers: github-ops (skill) and the
# global claude-config guardrails. The merge is replace-by-marker, so re-running
# never duplicates entries.
GHO_HOOKS_SRC="$REPO_DIR/skills/github-ops/hooks/hooks.json"
GHO_HOOKS_MARKER="github-ops/hooks/"

# merge_hooks <src_hooks_json> <hooks_dir> <marker> <label>
merge_hooks() {
  local src="$1" hooks_dir="$2" marker="$3" label="$4"
  local settings="$CLAUDE_DIR/settings.json"
  [ -f "$src" ] || return 0

  if ! command -v jq >/dev/null 2>&1; then
    echo "  ↳ hooks ($label): jq not found — add these to $settings manually:"
    sed "s#{{HOOKS_DIR}}#$hooks_dir#g" "$src" | sed 's/^/      /'
    return 0
  fi

  [ -f "$settings" ] || echo '{}' > "$settings"
  cp "$settings" "$settings.bak"

  local tmp_hooks
  tmp_hooks="$(mktemp)"
  sed "s#{{HOOKS_DIR}}#$hooks_dir#g" "$src" > "$tmp_hooks"

  if jq --arg m "$marker" --slurpfile add "$tmp_hooks" '
        .hooks //= {}
        | .hooks |= (to_entries
            | map(.value |= [ .[] | select(([..|strings] | any(contains($m))) | not) ])
            | from_entries)
        | reduce ($add[0]|to_entries[]) as $e (.;
            .hooks[$e.key] = ((.hooks[$e.key] // []) + $e.value))
      ' "$settings" > "$settings.tmp"; then
    mv "$settings.tmp" "$settings"
    echo "  ↳ hooks registered in settings.json ($label)"
  else
    rm -f "$settings.tmp"
    echo "  ↳ hooks ($label): merge failed — settings.json left unchanged (backup at settings.json.bak)"
  fi
  rm -f "$tmp_hooks"
}

# remove_hooks <marker> <label>
remove_hooks() {
  local marker="$1" label="$2"
  local settings="$CLAUDE_DIR/settings.json"
  [ -f "$settings" ] || return 0
  command -v jq >/dev/null 2>&1 || { echo "  ↳ hooks ($label): jq not found — remove entries from $settings manually."; return 0; }
  cp "$settings" "$settings.bak"
  if jq --arg m "$marker" '
        if .hooks then
          .hooks |= (to_entries
            | map(.value |= [ .[] | select(([..|strings] | any(contains($m))) | not) ]
                  | select(.value | length > 0))
            | from_entries)
        else . end
      ' "$settings" > "$settings.tmp"; then
    mv "$settings.tmp" "$settings"
    echo "  ↳ hooks removed from settings.json ($label)"
  else
    rm -f "$settings.tmp"
  fi
}

merge_github_ops_hooks() {
  [ -f "$GHO_HOOKS_SRC" ] || return 0
  chmod +x "$REPO_DIR"/skills/github-ops/hooks/*.sh 2>/dev/null || true
  merge_hooks "$GHO_HOOKS_SRC" "$CLAUDE_DIR/skills/github-ops/hooks" "$GHO_HOOKS_MARKER" "git-guard"
}
remove_github_ops_hooks() { remove_hooks "$GHO_HOOKS_MARKER" "git-guard"; }

# Global guardrails: symlink the repo hooks dir to a stable path so settings.json
# never bakes in the repo location, then merge under the claude-config marker.
merge_global_hooks() {
  [ -f "$GLOBAL_HOOKS_SRC" ] || return 0
  chmod +x "$REPO_DIR"/hooks/*.sh 2>/dev/null || true
  if [ ! -L "$GLOBAL_HOOKS_LINK" ] || [ "$(readlink "$GLOBAL_HOOKS_LINK")" != "$REPO_DIR/hooks" ]; then
    rm -rf "$GLOBAL_HOOKS_LINK"
    ln -s "$REPO_DIR/hooks" "$GLOBAL_HOOKS_LINK"
  fi
  merge_hooks "$GLOBAL_HOOKS_SRC" "$GLOBAL_HOOKS_LINK" "$GLOBAL_HOOKS_MARKER" "doc-file-warning, config-protection"
}
remove_global_hooks() {
  remove_hooks "$GLOBAL_HOOKS_MARKER" "claude-config guardrails"
  [ -L "$GLOBAL_HOOKS_LINK" ] && rm -f "$GLOBAL_HOOKS_LINK"
}

# Returns 0 if "github-ops" is among the given asset name args.
contains_github_ops() {
  local n
  for n in "$@"; do [ "$n" = "github-ops" ] && return 0; done
  return 1
}

# ── Common rules (auto-loaded from ~/.claude/rules/) ──────────────────────────────
# common/*.md are symlinked in (global, auto-loaded). The pointer rule is templated
# (real file, $REPO_DIR substituted). Foreign files in ~/.claude/rules/ are preserved.
install_common_rules() {
  [ -d "$RULES_COMMON_DIR" ] || return 0
  local dest_dir="$CLAUDE_DIR/rules"
  mkdir -p "$dest_dir"
  local f base dest
  for f in "$RULES_COMMON_DIR"/*.md; do
    [ -f "$f" ] || continue
    base="$(basename "$f")"
    dest="$dest_dir/$base"
    if [ "$base" = "$POINTER_RULE" ]; then
      # Templated real file (not a symlink): substitute the repo path.
      if [ -L "$dest" ]; then rm -f "$dest"; fi
      sed "s#{{REPO_DIR}}#$REPO_DIR#g" "$f" > "$dest"
      echo "  ✓ rules/$base (generated)"
      continue
    fi
    if [ -L "$dest" ] && [ "$(readlink "$dest")" = "$f" ]; then
      continue
    fi
    if [ -e "$dest" ] || [ -L "$dest" ]; then
      $OPT_REPLACE && rm -rf "$dest" || { mv "$dest" "${dest}.bak"; echo "  (backed up existing to rules/$base.bak)"; }
    fi
    ln -s "$f" "$dest"
    echo "  ✓ rules/$base"
  done
}
remove_common_rules() {
  [ -d "$RULES_COMMON_DIR" ] || return 0
  local dest_dir="$CLAUDE_DIR/rules"
  local f base dest
  for f in "$RULES_COMMON_DIR"/*.md; do
    [ -f "$f" ] || continue
    base="$(basename "$f")"
    dest="$dest_dir/$base"
    if [ "$base" = "$POINTER_RULE" ]; then
      # Only remove if it's our generated pointer (don't nuke a user file).
      [ -f "$dest" ] && grep -q "Language-specific rules" "$dest" 2>/dev/null && { rm -f "$dest"; echo "  ↳ rules/$base removed"; }
      continue
    fi
    if [ -L "$dest" ] && [ "$(readlink "$dest")" = "$f" ]; then
      rm -f "$dest"; echo "  ↳ rules/$base removed"
    fi
  done
}

# ── Profiles / manifest ───────────────────────────────────────────────────────
require_jq() {
  command -v jq >/dev/null 2>&1 || { echo "ERROR: jq is required for $1. Install jq or use interactive per-asset selection."; exit 1; }
}

# index_of <type> <name> → prints index into ASSET arrays, or empty if not found
index_of() {
  local want_type="$1" want_name="$2" i=0
  while [ "$i" -lt "${#ASSET_NAMES[@]}" ]; do
    if [ "${ASSET_TYPES[$i]}" = "$want_type" ] && [ "${ASSET_NAMES[$i]}" = "$want_name" ]; then
      echo "$i"; return 0
    fi
    i=$((i+1))
  done
  return 1
}

list_profiles() {
  require_jq "--list-profiles"
  [ -f "$MANIFEST" ] || { echo "No manifest at $MANIFEST"; exit 1; }
  local p
  for p in $(jq -r '.profiles | keys[]' "$MANIFEST"); do
    echo "Profile: $p"
    jq -r --arg p "$p" '.profiles[$p][]' "$MANIFEST" | sed 's/^/  - /'
    echo
  done
}

# Populate global `selected_indices` from a profile name. Aborts on unknown
# profile or any manifest↔disk inconsistency (preflight validation).
resolve_profile_indices() {
  local profile="$1"
  require_jq "--profile"
  [ -f "$MANIFEST" ] || { echo "ERROR: no manifest at $MANIFEST"; exit 1; }
  if ! jq -e --arg p "$profile" '.profiles | has($p)' "$MANIFEST" >/dev/null; then
    echo "ERROR: unknown profile '$profile'. Available:"
    jq -r '.profiles | keys[] | "  - " + .' "$MANIFEST"
    exit 1
  fi
  echo "Validating manifest…"
  if ! validate_manifest; then
    echo "ERROR: manifest references assets not on disk — aborting (fix manifests/profiles.json)."
    exit 1
  fi
  local entry type name idx
  while IFS= read -r entry; do
    [ -n "$entry" ] || continue
    type="${entry%%/*}"; name="${entry#*/}"
    idx=$(index_of "$type" "$name") || { echo "ERROR: profile asset not found: $entry"; exit 1; }
    selected_indices+=("$idx")
  done < <(jq -r --arg p "$profile" '.profiles[$p][]' "$MANIFEST")
}

# Interactive: offer profiles first, "custom" falls through to per-asset selection.
# Prints the chosen profile name, or "custom".
interactive_profile_pick() {
  command -v jq >/dev/null 2>&1 || { echo "custom"; return; }
  [ -f "$MANIFEST" ] || { echo "custom"; return; }
  local profs=() p
  while IFS= read -r p; do profs+=("$p"); done < <(jq -r '.profiles | keys[]' "$MANIFEST")
  [ "${#profs[@]}" -gt 0 ] || { echo "custom"; return; }
  echo "Install a profile, or pick assets manually?" >&2
  local i=0
  while [ "$i" -lt "${#profs[@]}" ]; do
    printf '  %d) %s\n' $((i+1)) "${profs[$i]}" >&2
    i=$((i+1))
  done
  printf '  %d) custom (choose individual assets)\n' $((i+1)) >&2
  printf "Choice [%d]: " $((i+1)) >&2
  local choice; read -r choice </dev/tty
  [ -z "$choice" ] && { echo "custom"; return; }
  if [ "$choice" -ge 1 ] 2>/dev/null && [ "$choice" -le "${#profs[@]}" ] 2>/dev/null; then
    echo "${profs[$((choice-1))]}"
  else
    echo "custom"
  fi
}

# Validate every profile asset exists on disk, and registry servers are well-formed.
# Prints problems; returns non-zero if any.
validate_manifest() {
  local problems=0 entry type name
  if [ -f "$MANIFEST" ] && command -v jq >/dev/null 2>&1; then
    while IFS= read -r entry; do
      [ -n "$entry" ] || continue
      type="${entry%%/*}"; name="${entry#*/}"
      if ! index_of "$type" "$name" >/dev/null; then
        echo "  ✗ profile asset not found on disk: $entry"
        problems=$((problems+1))
      fi
    done < <(jq -r '.profiles | to_entries[] | .value[]' "$MANIFEST")
  fi
  if [ -f "$MCP_REGISTRY" ] && command -v jq >/dev/null 2>&1; then
    local bad
    bad=$(jq -r '[.servers | to_entries[] | select((.value.command|type) != "string" or (.value.args|type) != "array") | .key] | join(", ")' "$MCP_REGISTRY")
    if [ -n "$bad" ]; then
      echo "  ✗ malformed MCP registry entries: $bad"
      problems=$((problems+1))
    fi
  fi
  [ "$problems" -eq 0 ]
}

# ── MCP guidance (opt-in; writes nothing) ─────────────────────────────────────────
mcp_guidance() {
  [ -f "$MCP_REGISTRY" ] || { echo "No MCP registry at $MCP_REGISTRY"; return 0; }
  require_jq "--mcp"
  echo "MCP server config guidance (opt-in — nothing is written for you):"
  echo
  local name
  for name in $(jq -r '.servers | keys[]' "$MCP_REGISTRY"); do
    echo "  • $name"
    local cmd args note
    cmd=$(jq -r --arg n "$name" '.servers[$n].command' "$MCP_REGISTRY")
    args=$(jq -r --arg n "$name" '.servers[$n].args | join(" ")' "$MCP_REGISTRY")
    note=$(jq -r --arg n "$name" '.servers[$n].note // ""' "$MCP_REGISTRY")
    echo "      run: $cmd $args"
    [ -n "$note" ] && echo "      note: $note"
    # env vars + how-to
    jq -r --arg n "$name" '.servers[$n].env // {} | to_entries[] | "      env: \(.key) — \(.value)"' "$MCP_REGISTRY"
    local envcount
    envcount=$(jq -r --arg n "$name" '.servers[$n].env // {} | length' "$MCP_REGISTRY")
    [ "$envcount" = "0" ] && echo "      env: none required"
    echo
  done
  echo "Template to copy from: $REPO_DIR/mcp-configs/mcp.template.json"
  echo "Paste the servers you want into a project .mcp.json or ~/.claude.json (mcpServers)."
}

# ── Doctor ──────────────────────────────────────────────────────────────────────
doctor() {
  local problems=0
  echo "claude-config doctor"

  # 1. symlink health
  local broken_links
  broken_links=$(find "$CLAUDE_DIR" -maxdepth 3 -type l ! -exec test -e {} \; -print 2>/dev/null || true)
  if [ -z "$broken_links" ]; then
    echo "  ✓ symlinks healthy"
  else
    echo "  ✗ broken symlinks:"; echo "$broken_links" | sed 's/^/      /'; problems=$((problems+1))
  fi

  # 2. global hooks block present
  local settings="$CLAUDE_DIR/settings.json"
  if [ -f "$settings" ] && command -v jq >/dev/null 2>&1 && \
     jq -e --arg m "$GLOBAL_HOOKS_MARKER" '[(.hooks // {}) | .. | strings] | any(contains($m))' "$settings" >/dev/null 2>&1; then
    echo "  ✓ global hooks present in settings.json"
  else
    echo "  ✗ global hooks block missing (run install to register guardrails)"; problems=$((problems+1))
  fi

  # 3. language-rules pointer installed
  if [ -f "$CLAUDE_DIR/rules/$POINTER_RULE" ]; then
    echo "  ✓ language-rules pointer installed"
  else
    echo "  ✗ language-rules pointer missing in ~/.claude/rules/"; problems=$((problems+1))
  fi

  # 4. manifest ↔ disk consistency
  if validate_manifest >/tmp/.cc-doctor-validate 2>&1; then
    echo "  ✓ manifest ↔ disk consistent"
  else
    echo "  ✗ manifest inconsistencies:"; sed 's/^/    /' /tmp/.cc-doctor-validate; problems=$((problems+1))
  fi
  rm -f /tmp/.cc-doctor-validate 2>/dev/null || true

  echo
  if [ "$problems" -eq 0 ]; then
    echo "All checks passed."
    exit 0
  else
    echo "$problems problem(s) found."
    exit 1
  fi
}

# ── Main ──────────────────────────────────────────────────────────────────────
if [ "$MODE" = "uninstall" ]; then
  uninstall_mode
  exit 0
elif [ "$MODE" = "list-profiles" ]; then
  list_profiles
  exit 0
elif [ "$MODE" = "mcp" ]; then
  mcp_guidance
  exit 0
elif [ "$MODE" = "doctor" ]; then
  doctor   # exits with status
fi

# Ask symlink vs copy (skip in --all/--profile mode, default to symlink)
USE_SYMLINK=true
if ! $OPT_ALL && [ -z "$OPT_PROFILE" ]; then
  echo "Install mode:"
  echo "  1) Symlink (recommended — changes in repo reflect immediately)"
  echo "  2) Copy (robust, but requires re-running install after changes)"
  printf "Choice [1]: "
  read -r choice
  [ "$choice" = "2" ] && USE_SYMLINK=false
  echo
fi

# Select assets
selected_indices=()
USED_PROFILE=""
if [ -n "$OPT_PROFILE" ]; then
  resolve_profile_indices "$OPT_PROFILE"
  USED_PROFILE="$OPT_PROFILE"
elif $OPT_ALL; then
  i=0
  while [ "$i" -lt "${#ASSET_NAMES[@]}" ]; do
    selected_indices+=("$i"); i=$((i+1))
  done
else
  pick=$(interactive_profile_pick)
  if [ -n "$pick" ] && [ "$pick" != "custom" ]; then
    resolve_profile_indices "$pick"
    USED_PROFILE="$pick"
  elif $USE_FZF; then
    while IFS= read -r idx; do
      selected_indices+=("$idx")
    done < <(select_assets_fzf)
  else
    while IFS= read -r idx; do
      selected_indices+=("$idx")
    done < <(select_assets_menu)
  fi
fi

if [ "${#selected_indices[@]}" -eq 0 ]; then
  echo "Nothing selected."
  exit 0
fi

echo
echo "Installing:"
installed=()
installed_names=()
for i in "${selected_indices[@]}"; do
  install_asset "${ASSET_TYPES[$i]}" "${ASSET_NAMES[$i]}" "${ASSET_SRCS[$i]}"
  display_t="${ASSET_TYPES[$i]}"
  [ "$display_t" = "commands-ns" ] && display_t="commands"
  installed+=("$display_t/${ASSET_NAMES[$i]}")
  installed_names+=("${ASSET_NAMES[$i]}")
done

if contains_github_ops "${installed_names[@]}"; then
  merge_github_ops_hooks
fi

# Global baseline: guardrail hooks + common (auto-loaded) rules.
echo
echo "Global guardrails + common rules:"
install_common_rules
merge_global_hooks

# Summary
echo
echo "─────────────────────────────────────"
echo "Installed ${#installed[@]} asset(s)${USED_PROFILE:+ from profile '$USED_PROFILE'}:"
for item in "${installed[@]}"; do echo "  • $item"; done
echo
echo "Open Claude Code and type /fix-conflicts (or the command you installed) to test."
echo "Verify wiring anytime with: $(basename "$0") --doctor"
if $USE_SYMLINK; then
  echo "Note: symlinks point to $REPO_DIR — don't move the repo."
fi
echo "─────────────────────────────────────"

# MCP guidance: offer interactively, hint otherwise.
if [ -f "$MCP_REGISTRY" ]; then
  if ! $OPT_ALL && [ -z "$OPT_PROFILE" ]; then
    printf "Show MCP server config guidance? [y/N]: "
    read -r mcp_ans </dev/tty 2>/dev/null || mcp_ans=""
    case "$mcp_ans" in [yY]*) echo; mcp_guidance ;; esac
  else
    echo "MCP setup guidance: $(basename "$0") --mcp"
  fi
fi
