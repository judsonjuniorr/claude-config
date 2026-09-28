#!/usr/bin/env bash
# herow-project.sh dir|plans|qa [--ensure] [start-path]
#
# Sole resolver for the herow-dev per-project store under $HEROW_HOME/projects/<id>/.
# Prints the resolved absolute path on stdout and nothing else. All diagnostics
# (warnings, errors) go to stderr, pipe-delimited: "<level>|<code>|<path>|<message>".
#
# Only --ensure creates directories (0700) and writes .root / runs the legacy
# in-repo migration; a plain lookup never mkdirs, so a stray ancestor walk for
# `qa` never litters projects/<slug>-* entries.
#
# Root resolution (dir | plans): git-common-dir maps a worktree/subdir to the
# main checkout; ".git/modules/..." (submodule) falls back to --show-toplevel
# (its own root, not the superproject's); non-git -> physical cwd.
#
# `qa` additionally prefers an already-set-up ancestor workspace root over creating a new
# project for a child repo, unless the child already has its own qa/ -- see the dispatch
# right after walk_ancestors_for_qa_root below.
set -eu

HEROW_HOME="${HEROW_HOME:-$HOME/.herow}"
STORE="$HEROW_HOME/projects"

diag() { printf '%s\n' "$1" >&2; }

usage() {
  echo "usage: herow-project.sh dir|plans|qa|checkout-root [--ensure] [start-path]" >&2
  exit 3
}

KIND=""
ENSURE=0
START="."

while [ $# -gt 0 ]; do
  case "$1" in
    dir|plans|qa|checkout-root)
      [ -z "$KIND" ] || usage
      KIND="$1"; shift ;;
    --ensure) ENSURE=1; shift ;;
    -*) usage ;;
    *) START="$1"; shift ;;
  esac
done
[ -n "$KIND" ] || usage
[ "$KIND" = "checkout-root" ] && ENSURE=0

[ -d "$START" ] || { diag "error|bad-start|$START|not a directory"; exit 3; }
START_ABS="$(cd "$START" && pwd -P)"

HAVE_GIT=0
command -v git >/dev/null 2>&1 && HAVE_GIT=1

# --- root resolution ------------------------------------------------------------------------

resolve_root() {
  local start="$1" common base
  if [ "$HAVE_GIT" -eq 1 ]; then
    common="$(git -C "$start" rev-parse --git-common-dir 2>/dev/null)" || common=""
    if [ -n "$common" ]; then
      # git-common-dir can be relative to $start; resolve it physically from there.
      common="$(cd "$start" && cd "$common" && pwd -P)" || common=""
    fi
  else
    common=""
  fi
  if [ -n "$common" ]; then
    base="$(basename "$common")"
    if [ "$base" = ".git" ]; then
      (cd "$(dirname "$common")" && pwd -P)
    else
      # submodule (.git/modules/...): the submodule's own toplevel, not the superproject's.
      git -C "$start" rev-parse --show-toplevel 2>/dev/null
    fi
  else
    printf '%s' "$start"
  fi
}

ROOT="$(resolve_root "$START_ABS")"
[ -n "$ROOT" ] || { diag "error|no-root|$START_ABS|could not resolve a root"; exit 3; }

# --- id computation ---------------------------------------------------------------------------

sanitize_component() {
  printf '%s' "$1" | tr -c 'A-Za-z0-9._-' '-'
}

owner_repo_from_origin() {
  # $1 = origin URL (https or ssh form). Prints "<owner>-<repo>", sanitized. Empty on failure.
  python3 -c "
import re, sys
url = sys.argv[1].strip()
if not url:
    sys.exit(1)
url = re.sub(r'\.git/?\$', '', url)
m = re.match(r'^[^/@]+@[^:/]+:(.+)\$', url)
if m:
    path = m.group(1)
else:
    path = re.sub(r'^[a-zA-Z][a-zA-Z0-9+.-]*://(?:[^@/]+@)?[^/]+/', '', url)
parts = [p for p in path.split('/') if p]
def san(s):
    return re.sub(r'[^A-Za-z0-9._-]', '-', s)
if len(parts) >= 2:
    print(f'{san(parts[-2])}-{san(parts[-1])}')
elif parts:
    print(san(parts[-1]))
else:
    sys.exit(1)
" "$1" 2>/dev/null
}

compute_id() {
  local root="$1" origin="" slug hash
  if [ "$HAVE_GIT" -eq 1 ]; then
    origin="$(git -C "$root" remote get-url origin 2>/dev/null)" || origin=""
  fi
  slug=""
  if [ -n "$origin" ]; then
    slug="$(owner_repo_from_origin "$origin")" || slug=""
  fi
  [ -n "$slug" ] || slug="$(sanitize_component "$(basename "$root")")"
  hash="$(printf '%s' "$root" | shasum -a 256 | awk '{print $1}' | cut -c1-6)"
  printf '%s-%s' "$slug" "$hash"
}

# --- ancestor walk for `qa` (matches an already-registered workspace root) -------------------

walk_ancestors_for_qa_root() {
  # $1 = physical start path. Prints the matching, ACTUALLY-CONFIGURED projects/<id> dir
  # on stdout, or nothing. Matching on .root alone would let any ancestor that merely had
  # `dir`/`plans --ensure` run in it (creating .root, no qa/ involved at all) capture every
  # child repo's qa lookup — so a candidate only counts once qa-setup has actually written
  # its config.yml there.
  local dir="$1" rf recorded proj
  [ -d "$STORE" ] || return 0
  while :; do
    for rf in "$STORE"/*/.root; do
      [ -f "$rf" ] || continue
      recorded="$(cat "$rf" 2>/dev/null || true)"
      if [ "$recorded" = "$dir" ]; then
        proj="$(dirname "$rf")"
        [ -f "$proj/qa/config.yml" ] || continue
        printf '%s\n' "$proj"
        return 0
      fi
    done
    [ "$dir" = "/" ] && return 0
    dir="$(dirname "$dir")"
  done
}

MATCH_DIR=""
if [ "$KIND" = "qa" ] || [ "$KIND" = "checkout-root" ]; then
  ID="$(compute_id "$ROOT")"
  OWN_DIR="$STORE/$ID"
  if [ -f "$OWN_DIR/qa/config.yml" ]; then
    # Already configured for THIS repo — never let an enclosing workspace's store shadow
    # it, even if one exists (keying on config.yml, not just the qa/ dir, also means an
    # aborted qa-setup that created an empty qa/ before writing config.yml never wins here).
    PROJECT_DIR="$OWN_DIR"
  else
    MATCH_DIR="$(walk_ancestors_for_qa_root "$START_ABS")"
    if [ -n "$MATCH_DIR" ]; then
      PROJECT_DIR="$MATCH_DIR"
    else
      PROJECT_DIR="$OWN_DIR"
    fi
  fi
else
  ID="$(compute_id "$ROOT")"
  PROJECT_DIR="$STORE/$ID"
fi

# --- move detection (--ensure only, own-id path only): repo moved to a new abs path ----------

realpath_py() {
  python3 -c "import os,sys; print(os.path.realpath(sys.argv[1]))" "$1" 2>/dev/null
}

detect_move() {
  # $1 = id, $2 = current root. Renames a stale <slug>-<hash6> dir into place when exactly
  # one candidate's recorded .root no longer exists on disk.
  local id="$1" root="$2" slug cand hex n=0 found="" recorded
  hex='[0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f]'
  slug="${id%-??????}"
  [ -d "$STORE" ] || return 0
  for cand in "$STORE/$slug"-$hex; do
    [ -d "$cand" ] || continue
    [ "$(basename "$cand")" = "$id" ] && continue
    [ -f "$cand/.root" ] || continue
    recorded="$(cat "$cand/.root" 2>/dev/null || true)"
    [ -n "$recorded" ] || continue
    [ -d "$recorded" ] && continue   # old root still exists — not a move
    n=$((n + 1))
    found="$cand"
  done
  if [ "$n" -eq 1 ]; then
    mv "$found" "$STORE/$id"
    printf '%s\n' "$root" > "$STORE/$id/.root"
    diag "info|moved|$STORE/$id|renamed from $found"
  elif [ "$n" -gt 1 ]; then
    diag "warn|move-ambiguous|$STORE/$slug|$n candidates with a missing .root target — not guessing"
  fi
}

if [ "$ENSURE" -eq 1 ] && [ -z "$MATCH_DIR" ] && [ ! -d "$PROJECT_DIR" ]; then
  detect_move "$ID" "$ROOT"
fi

# --- legacy in-repo migration (--ensure only) --------------------------------------------------

migrate_legacy() {
  # $1 = the legacy root to scan (a real checkout — main repo or a registered workspace root)
  # $2 = the project's store dir (already created)
  local root="$1" project_dir="$2"
  [ -d "$root" ] || return 0

  local tracked="" tracked_qa=0 tracked_plans=0 line
  if [ "$HAVE_GIT" -eq 1 ]; then
    tracked="$(git -C "$root" ls-files -- .qa .claude/plans 2>/dev/null || true)"
  fi
  while IFS= read -r line; do
    case "$line" in
      .qa/*) tracked_qa=1 ;;
      .claude/plans/*) tracked_plans=1 ;;
    esac
  done <<EOF
$tracked
EOF

  # .claude/plans/* (skip .active-*) -> project_dir/plans/
  if [ "$tracked_plans" -eq 1 ]; then
    [ -d "$root/.claude/plans" ] && \
      diag "warn|tracked|$root/.claude/plans|migration skipped: files are git-tracked"
  elif [ -d "$root/.claude/plans" ]; then
    (umask 077; mkdir -p "$project_dir/plans")
    local entry base target
    for entry in "$root/.claude/plans"/*; do
      [ -e "$entry" ] || continue
      base="$(basename "$entry")"
      case "$base" in .active-*) continue ;; esac
      target="$project_dir/plans/$base"
      if [ -e "$target" ]; then
        diag "warn|target-exists|$target|migration skipped for $entry: target already exists"
      else
        mv "$entry" "$target"
      fi
    done
    rmdir "$root/.claude/plans" 2>/dev/null || true
  fi

  # .qa/{config.yml,knowledge,reports} -> project_dir/qa/
  if [ "$tracked_qa" -eq 1 ]; then
    [ -d "$root/.qa" ] && \
      diag "warn|tracked|$root/.qa|migration skipped: files are git-tracked"
  elif [ -d "$root/.qa" ]; then
    (umask 077; mkdir -p "$project_dir/qa")

    # Reverse-adoption symlinks (.claude/knowledge/*, .claude/skills/*/knowledge) that
    # resolve into the OLD .qa/knowledge must be re-pointed to the new location — record
    # them before the move, since they'd otherwise dangle the instant .qa/knowledge moves.
    local old_knowledge="$root/.qa/knowledge" old_knowledge_real="" repoint="" cand resolved
    if [ -e "$old_knowledge" ]; then
      old_knowledge_real="$(realpath_py "$old_knowledge")"
      for cand in "$root/.claude/knowledge"/* "$root/.claude/skills"/*/knowledge; do
        [ -L "$cand" ] || continue
        resolved="$(realpath_py "$cand")"
        if [ -n "$old_knowledge_real" ] && [ "$resolved" = "$old_knowledge_real" ]; then
          repoint="${repoint}${cand}
"
        fi
      done
    fi

    local name src dest link_target abs_target
    for name in config.yml knowledge reports; do
      src="$root/.qa/$name"
      dest="$project_dir/qa/$name"
      [ -e "$src" ] || [ -L "$src" ] || continue
      if [ -e "$dest" ]; then
        diag "warn|target-exists|$dest|migration skipped for $src: target already exists"
        continue
      fi
      if [ -L "$src" ]; then
        # .qa/knowledge itself was a symlink (rare) — recreate pointing at its own absolute
        # target, never chain through the old path.
        link_target="$(readlink "$src")"
        case "$link_target" in
          /*) abs_target="$link_target" ;;
          *) abs_target="$(cd "$(dirname "$src")" && cd "$(dirname "$link_target")" 2>/dev/null && pwd -P)/$(basename "$link_target")" ;;
        esac
        ln -s "$abs_target" "$dest"
        rm "$src"
      else
        mv "$src" "$dest"
      fi
    done
    rmdir "$root/.qa" 2>/dev/null || true

    if [ -n "$repoint" ]; then
      printf '%s' "$repoint" | while IFS= read -r p; do
        [ -n "$p" ] || continue
        [ -L "$p" ] || continue
        rm "$p"
        ln -sfn "$project_dir/qa/knowledge" "$p"
      done
    fi
  fi
}

if [ "$ENSURE" -eq 1 ]; then
  (umask 077; mkdir -p "$PROJECT_DIR")
  chmod 700 "$HEROW_HOME" "$STORE" "$PROJECT_DIR" 2>/dev/null || true

  if [ -z "$MATCH_DIR" ]; then
    RECORDED=""
    [ -f "$PROJECT_DIR/.root" ] && RECORDED="$(cat "$PROJECT_DIR/.root" 2>/dev/null || true)"
    if [ "$RECORDED" != "$ROOT" ]; then
      printf '%s\n' "$ROOT" > "$PROJECT_DIR/.root"
    fi
    LEGACY_ROOT="$ROOT"
  else
    LEGACY_ROOT="$(cat "$MATCH_DIR/.root" 2>/dev/null || printf '%s' "$ROOT")"
  fi

  migrate_legacy "$LEGACY_ROOT" "$PROJECT_DIR"
fi

case "$KIND" in
  dir) OUT="$PROJECT_DIR" ;;
  plans) OUT="$PROJECT_DIR/plans" ;;
  qa) OUT="$PROJECT_DIR/qa" ;;
  # repos[].path base: the workspace root when qa resolved to an enclosing workspace, else this checkout (worktree-aware).
  checkout-root)
    if [ -n "$MATCH_DIR" ]; then
      OUT="$(cat "$MATCH_DIR/.root")"
    else
      OUT="$(git -C "$START_ABS" rev-parse --show-toplevel 2>/dev/null || printf '%s' "$START_ABS")"
    fi ;;
esac

if [ "$ENSURE" -eq 1 ]; then
  (umask 077; mkdir -p "$OUT")
  chmod 700 "$OUT" 2>/dev/null || true
fi

printf '%s\n' "$OUT"
