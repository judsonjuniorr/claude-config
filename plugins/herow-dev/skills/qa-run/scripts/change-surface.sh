#!/usr/bin/env bash
# change-surface.sh <repo-path> [--base <branch>] [--diff [--max-lines N]]
# Read-only per-repo change surface for qa-run Phase 1b (see qa-run/reference.md).
# Base: --base (no fallback; "base: invalid (<x>)" if it doesn't resolve) > origin/HEAD >
# origin/main > main > origin/master > master; none → "base: unresolved" (not a failure).
# Exit: 0 always; 2 = bad args, not a directory, or not a git work tree.
set -u

usage() {
  echo "usage: change-surface.sh <repo-path> [--base <branch>] [--diff [--max-lines N]]" >&2
  exit 2
}

REPO=""
BASE=""
WANT_DIFF=0
MAX_LINES=400

while [ $# -gt 0 ]; do
  case "$1" in
    --base)
      [ $# -ge 2 ] || usage
      BASE="$2"; shift 2 ;;
    --diff) WANT_DIFF=1; shift ;;
    --max-lines)
      [ $# -ge 2 ] || usage
      case "$2" in
        ''|*[!0-9]*) echo "change-surface: --max-lines must be a non-negative integer" >&2; exit 2 ;;
      esac
      MAX_LINES="$2"; shift 2 ;;
    -*) echo "unknown flag: $1" >&2; exit 2 ;;
    *)
      if [ -z "$REPO" ]; then REPO="$1"; else echo "unexpected argument: $1" >&2; exit 2; fi
      shift ;;
  esac
done

[ -n "$REPO" ] || usage
[ -d "$REPO" ] || { echo "change-surface: not a directory: $REPO" >&2; exit 2; }

git -C "$REPO" rev-parse --is-inside-work-tree >/dev/null 2>&1 || {
  echo "change-surface: not a git repository: $REPO" >&2
  exit 2
}

REPO="$(cd "$REPO" && pwd)"
echo "repo: $REPO"

HEAD_SHA="$(git -C "$REPO" rev-parse --short HEAD 2>/dev/null || echo "unknown")"
HEAD_BRANCH="$(git -C "$REPO" symbolic-ref --short HEAD 2>/dev/null || echo "detached")"
echo "head: $HEAD_SHA ($HEAD_BRANCH)"

print_or() { # $1 = text, $2 = word to print when empty
  if [ -n "$1" ]; then printf '%s\n' "$1"; else echo "$2"; fi
}

echo
echo "working tree:"
print_or "$(git -C "$REPO" status --porcelain 2>/dev/null)" clean

echo
echo "changed vs HEAD:"
print_or "$(git -C "$REPO" diff --name-status HEAD 2>/dev/null)" none

resolve_base() {
  local candidate origin_head
  origin_head="$(git -C "$REPO" symbolic-ref --short refs/remotes/origin/HEAD 2>/dev/null || true)"
  for candidate in "$origin_head" origin/main main origin/master master; do
    [ -n "$candidate" ] || continue
    if git -C "$REPO" rev-parse --verify -q "$candidate^{commit}" >/dev/null 2>&1; then
      printf '%s' "$candidate"
      return 0
    fi
  done
  return 1
}

print_capped_diff() { # $1 = full unified diff text
  local full="$1" total=0 shown
  echo
  echo "diff:"
  [ -n "$full" ] && total="$(printf '%s\n' "$full" | wc -l | tr -d ' ')"
  shown=$total
  [ "$total" -gt "$MAX_LINES" ] && shown=$MAX_LINES
  [ -n "$full" ] && printf '%s\n' "$full" | head -n "$shown"
  echo "truncated: $shown/$total"
}

# Tracked changes vs $1 plus untracked new files — the change under test is often uncommitted.
full_diff() {
  local f
  git -C "$REPO" diff --no-color --no-ext-diff --no-textconv "$1" 2>/dev/null
  git -C "$REPO" ls-files --others --exclude-standard -z 2>/dev/null | while IFS= read -r -d '' f; do
    git -C "$REPO" diff --no-color --no-ext-diff --no-index -- /dev/null "$f" 2>/dev/null
  done
}

MERGE_BASE=""
DIFF_REF=HEAD
echo
if [ -n "$BASE" ]; then
  if git -C "$REPO" rev-parse --verify -q "$BASE^{commit}" >/dev/null 2>&1; then
    RESOLVED_BASE="$BASE"
  else
    RESOLVED_BASE=""
    echo "change-surface: --base '$BASE' does not resolve to a commit" >&2
    echo "base: invalid ($BASE)"
  fi
else
  RESOLVED_BASE="$(resolve_base)" || RESOLVED_BASE=""
fi
[ -n "$RESOLVED_BASE" ] && MERGE_BASE="$(git -C "$REPO" merge-base HEAD "$RESOLVED_BASE" 2>/dev/null || true)"

if [ -n "$MERGE_BASE" ]; then
  DIFF_REF="$MERGE_BASE"
  echo "base: $RESOLVED_BASE"
  echo "changed vs base:"
  print_or "$(git -C "$REPO" diff --name-status "$MERGE_BASE" HEAD 2>/dev/null)" none
elif [ -z "$BASE" ] || [ -n "$RESOLVED_BASE" ]; then
  echo "base: unresolved"
fi

[ "$WANT_DIFF" -eq 1 ] && print_capped_diff "$(full_diff "$DIFF_REF")"

exit 0
