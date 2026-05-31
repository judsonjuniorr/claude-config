#!/usr/bin/env bash
set -euo pipefail

REPO_DIR=$(cd "$(dirname "$0")" && pwd)
CLAUDE_DIR="$HOME/.claude"

usage() {
  cat <<EOF
Usage: $(basename "$0") [OPTIONS] [COMMAND]

Commands:
  (none)      Interactive install — select assets to install
  uninstall   Interactive uninstall — select installed assets to remove

Options:
  --all       Install all assets without prompting
  --replace   Overwrite existing files/symlinks (default: backup as .bak)
  --help      Show this help and exit
EOF
  exit 0
}

# ── Argument parsing ──────────────────────────────────────────────────────────
MODE="install"
OPT_ALL=false
OPT_REPLACE=false

for arg in "$@"; do
  case "$arg" in
    uninstall) MODE="uninstall" ;;
    --all)     OPT_ALL=true ;;
    --replace) OPT_REPLACE=true ;;
    --help|-h) usage ;;
    *) echo "Unknown option: $arg"; usage ;;
  esac
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
  echo
  echo "Done."
}

# ── github-ops hooks (settings.json) ───────────────────────────────────────────
# The github-ops skill ships PreToolUse/PostToolUse hooks (git-guard, auto-stage).
# These are registered in ~/.claude/settings.json rather than symlinked, so they
# need an explicit merge/remove pass tagged by the "github-ops/hooks/" marker.
GHO_HOOKS_SRC="$REPO_DIR/skills/github-ops/hooks/hooks.json"

merge_github_ops_hooks() {
  local settings="$CLAUDE_DIR/settings.json"
  local hooks_dir="$CLAUDE_DIR/skills/github-ops/hooks"
  [ -f "$GHO_HOOKS_SRC" ] || return 0

  chmod +x "$REPO_DIR"/skills/github-ops/hooks/*.sh 2>/dev/null || true

  if ! command -v jq >/dev/null 2>&1; then
    echo "  ↳ hooks: jq not found — add these to $settings manually:"
    sed "s#{{HOOKS_DIR}}#$hooks_dir#g" "$GHO_HOOKS_SRC" | sed 's/^/      /'
    return 0
  fi

  [ -f "$settings" ] || echo '{}' > "$settings"
  cp "$settings" "$settings.bak"

  local tmp_hooks
  tmp_hooks="$(mktemp)"
  sed "s#{{HOOKS_DIR}}#$hooks_dir#g" "$GHO_HOOKS_SRC" > "$tmp_hooks"

  if jq --slurpfile add "$tmp_hooks" '
        .hooks //= {}
        | .hooks |= (to_entries
            | map(.value |= [ .[] | select(([..|strings] | any(test("github-ops/hooks/"))) | not) ])
            | from_entries)
        | reduce ($add[0]|to_entries[]) as $e (.;
            .hooks[$e.key] = ((.hooks[$e.key] // []) + $e.value))
      ' "$settings" > "$settings.tmp"; then
    mv "$settings.tmp" "$settings"
    echo "  ↳ hooks registered in settings.json (git-guard, auto-stage)"
  else
    rm -f "$settings.tmp"
    echo "  ↳ hooks: merge failed — settings.json left unchanged (backup at settings.json.bak)"
  fi
  rm -f "$tmp_hooks"
}

remove_github_ops_hooks() {
  local settings="$CLAUDE_DIR/settings.json"
  [ -f "$settings" ] || return 0
  command -v jq >/dev/null 2>&1 || { echo "  ↳ hooks: jq not found — remove github-ops entries from $settings manually."; return 0; }
  cp "$settings" "$settings.bak"
  if jq '
        if .hooks then
          .hooks |= (to_entries
            | map(.value |= [ .[] | select(([..|strings] | any(test("github-ops/hooks/"))) | not) ]
                  | select(.value | length > 0))
            | from_entries)
        else . end
      ' "$settings" > "$settings.tmp"; then
    mv "$settings.tmp" "$settings"
    echo "  ↳ hooks removed from settings.json"
  else
    rm -f "$settings.tmp"
  fi
}

# Returns 0 if "github-ops" is among the given asset name args.
contains_github_ops() {
  local n
  for n in "$@"; do [ "$n" = "github-ops" ] && return 0; done
  return 1
}

# ── Main ──────────────────────────────────────────────────────────────────────
if [ "$MODE" = "uninstall" ]; then
  uninstall_mode
  exit 0
fi

# Ask symlink vs copy (skip in --all mode, default to symlink)
USE_SYMLINK=true
if ! $OPT_ALL; then
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
if $OPT_ALL; then
  i=0
  while [ "$i" -lt "${#ASSET_NAMES[@]}" ]; do
    selected_indices+=("$i"); i=$((i+1))
  done
elif $USE_FZF; then
  while IFS= read -r idx; do
    selected_indices+=("$idx")
  done < <(select_assets_fzf)
else
  while IFS= read -r idx; do
    selected_indices+=("$idx")
  done < <(select_assets_menu)
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

# Summary
echo
echo "─────────────────────────────────────"
echo "Installed ${#installed[@]} asset(s):"
for item in "${installed[@]}"; do echo "  • $item"; done
echo
echo "Open Claude Code and type /fix-conflicts (or the command you installed) to test."
if $USE_SYMLINK; then
  echo "Note: symlinks point to $REPO_DIR — don't move the repo."
fi
echo "─────────────────────────────────────"
