#!/usr/bin/env bash
# ensure-ignored.sh --check|--apply <root> [--pattern P]
#
# Verifies (and optionally establishes) that git's GLOBAL excludesfile covers a
# pattern for a project root. Used by qa-setup (pattern ".qa/") and qa-run
# (--check only, same plugin); blueprint.md reuses it with --pattern
# ".claude/plans/". See plugins/herow-dev/skills/qa-setup/reference.md.
#
# Exit codes:
#   0  covered and untracked
#   1  not covered (after --apply: still not covered)
#   2  tracked files exist under <root>/<pattern> (prints the git rm --cached fix)
#   3  environment error (git missing, HOME unset, excludesfile unwritable, bad args)
set -u

usage() {
  echo "usage: ensure-ignored.sh --check|--apply <root> [--pattern P]" >&2
  exit 3
}

MODE=""
ROOT=""
PATTERN=".qa/"

while [ $# -gt 0 ]; do
  case "$1" in
    --check) MODE="check"; shift ;;
    --apply) MODE="apply"; shift ;;
    --pattern)
      [ $# -ge 2 ] || usage
      PATTERN="$2"; shift 2 ;;
    -*) usage ;;
    *)
      if [ -z "$ROOT" ]; then ROOT="$1"; else usage; fi
      shift ;;
  esac
done

[ -n "$MODE" ] || usage
[ -n "$ROOT" ] || usage

command -v git >/dev/null 2>&1 || { echo "ensure-ignored: git not found" >&2; exit 3; }
[ -n "${HOME:-}" ] || { echo "ensure-ignored: HOME is unset" >&2; exit 3; }
[ -d "$ROOT" ] || { echo "ensure-ignored: root not found: $ROOT" >&2; exit 3; }

ROOT="$(cd "$ROOT" && pwd)"
PATTERN_DIR="${PATTERN%/}"
[ -n "$PATTERN_DIR" ] || { echo "ensure-ignored: --pattern must not be empty" >&2; exit 3; }

# --- Probe repo: throwaway git repo under $HOME, independent of <root> --------------------
PROBE="$(mktemp -d "$HOME/.qa-ignore-probe.XXXXXX" 2>/dev/null)" || {
  echo "ensure-ignored: cannot create a probe dir under HOME ($HOME)" >&2
  exit 3
}
cleanup() { rm -rf "$PROBE"; }
trap cleanup EXIT

git init -q "$PROBE" >/dev/null 2>&1 || { echo "ensure-ignored: git init failed in probe repo" >&2; exit 3; }

mkdir -p "$PROBE/$PATTERN_DIR"
PROBE_REL="$PATTERN_DIR/probe-file"
: > "$PROBE/$PROBE_REL"

# --- Resolve the effective global excludesfile ---------------------------------------------
# `git config --type=path --get` (no scope flag) merges system/global/local config with
# includes honored, and expands a literal `~` — see reference.md "Excludesfile resolution".
resolve_excludesfile() {
  local resolved
  resolved="$(cd "$PROBE" && git config --type=path --get core.excludesfile 2>/dev/null)" || true
  if [ -n "$resolved" ]; then
    printf '%s' "$resolved"
    return 0
  fi
  if [ -n "${XDG_CONFIG_HOME:-}" ]; then
    printf '%s' "$XDG_CONFIG_HOME/git/ignore"
  else
    printf '%s' "$HOME/.config/git/ignore"
  fi
}

EXCLUDES="$(resolve_excludesfile)"
[ -n "$EXCLUDES" ] || { echo "ensure-ignored: could not resolve an excludesfile path" >&2; exit 3; }

is_covered() {
  ( cd "$PROBE" && git check-ignore -q "$PROBE_REL" ) 2>/dev/null
}

# --- Tracked check: <root>'s own repo (if any) + repos nested under <root> ------------------
ls_tracked() { # $1 = repo path, $2 = path relative to that repo to check
  ( cd "$1" 2>/dev/null && git ls-files -- "$2" 2>/dev/null )
}

TRACKED_LINES=""
add_tracked() { # $1 = repo, $2 = pattern path relative to repo
  TRACKED_LINES="${TRACKED_LINES}${1}|${2}
"
}

CONTAINING_REPO="$(cd "$ROOT" && git rev-parse --show-toplevel 2>/dev/null || true)"
if [ -n "$CONTAINING_REPO" ]; then
  REL_FROM_REPO="${ROOT#"$CONTAINING_REPO"}"
  REL_FROM_REPO="${REL_FROM_REPO#/}"
  if [ -n "$REL_FROM_REPO" ]; then
    REL_PATTERN="$REL_FROM_REPO/$PATTERN_DIR"
  else
    REL_PATTERN="$PATTERN_DIR"
  fi
  if [ -n "$(ls_tracked "$CONTAINING_REPO" "$REL_PATTERN")" ]; then
    add_tracked "$CONTAINING_REPO" "$REL_PATTERN"
  fi
fi

while IFS= read -r gitdir; do
  [ -n "$gitdir" ] || continue
  nested_repo="$(dirname "$gitdir")"
  [ "$nested_repo" = "$CONTAINING_REPO" ] && continue
  if [ -n "$(ls_tracked "$nested_repo" "$PATTERN_DIR")" ]; then
    add_tracked "$nested_repo" "$PATTERN_DIR"
  fi
done <<EOF
$(find "$ROOT" -mindepth 1 -maxdepth 4 -type d -name .git 2>/dev/null)
EOF

if [ -n "$TRACKED_LINES" ]; then
  echo "ensure-ignored: tracked files found under '$PATTERN':" >&2
  printf '%s' "$TRACKED_LINES" | while IFS='|' read -r repo relpath; do
    [ -n "$repo" ] || continue
    echo "  fix: git -C \"$repo\" rm -r --cached \"$relpath\"" >&2
  done
  exit 2
fi

if is_covered; then
  exit 0
fi

if [ "$MODE" = "check" ]; then
  echo "ensure-ignored: '$PATTERN' is not covered by the global excludesfile ($EXCLUDES)" >&2
  exit 1
fi

# --- --apply: create/append the excludesfile, writing THROUGH a symlink --------------------
EXCLUDES_DIR="$(dirname "$EXCLUDES")"
mkdir -p "$EXCLUDES_DIR" 2>/dev/null || { echo "ensure-ignored: cannot create $EXCLUDES_DIR" >&2; exit 3; }
if [ ! -e "$EXCLUDES" ]; then
  : > "$EXCLUDES" 2>/dev/null || { echo "ensure-ignored: cannot create $EXCLUDES" >&2; exit 3; }
fi
[ -w "$EXCLUDES" ] || { echo "ensure-ignored: $EXCLUDES is not writable" >&2; exit 3; }

if [ -s "$EXCLUDES" ]; then
  # Last byte is a newline iff piping it through `tail -c1` yields exactly one line.
  if [ "$(tail -c1 "$EXCLUDES" | wc -l | tr -d ' ')" = "0" ]; then
    printf '\n' >> "$EXCLUDES"
  fi
fi
printf '%s\n' "$PATTERN" >> "$EXCLUDES"

if is_covered; then
  echo "ensure-ignored: appended '$PATTERN' to $EXCLUDES"
  exit 0
fi

echo "ensure-ignored: appended '$PATTERN' to $EXCLUDES but coverage still fails — check the file manually" >&2
exit 1
