#!/usr/bin/env bash
# change-surface.sh <repo-path> [--base <branch>] [--diff [--max-lines N]]
#
# Read-only change-surface inspector for qa-run's Phase 1b. Prints working-tree status,
# name-status vs HEAD, and name-status vs the merge-base with a resolved base branch.
# github-ops' inspect.sh cannot serve here (cwd-only, shortstat only) — this is its
# per-repo, read-only counterpart for qa-run. See qa-run/reference.md.
#
# Base resolution order: --base flag > origin/HEAD > main > master. When none resolves
# (shallow clone, detached HEAD, unusual default branch), prints "base: unresolved" and
# reports working tree + HEAD only — this is not a failure (exit 0).
#
# Exit codes: 0 always, except 2 = <repo-path> is not inside a git work tree.
set -u

REPO=""
BASE=""
WANT_DIFF=0
MAX_LINES=400

while [ $# -gt 0 ]; do
  case "$1" in
    --base)
      [ $# -ge 2 ] || { echo "usage: change-surface.sh <repo-path> [--base <branch>] [--diff [--max-lines N]]" >&2; exit 2; }
      BASE="$2"; shift 2 ;;
    --diff) WANT_DIFF=1; shift ;;
    --max-lines)
      [ $# -ge 2 ] || { echo "usage: change-surface.sh <repo-path> [--base <branch>] [--diff [--max-lines N]]" >&2; exit 2; }
      MAX_LINES="$2"; shift 2 ;;
    -*) echo "unknown flag: $1" >&2; exit 2 ;;
    *)
      if [ -z "$REPO" ]; then REPO="$1"; else echo "unexpected argument: $1" >&2; exit 2; fi
      shift ;;
  esac
done

[ -n "$REPO" ] || { echo "usage: change-surface.sh <repo-path> [--base <branch>] [--diff [--max-lines N]]" >&2; exit 2; }
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

echo
echo "working tree:"
WT_STATUS="$(git -C "$REPO" status --porcelain 2>/dev/null)"
if [ -n "$WT_STATUS" ]; then
  printf '%s\n' "$WT_STATUS"
else
  echo "clean"
fi

echo
echo "changed vs HEAD:"
VS_HEAD="$(git -C "$REPO" diff --name-status HEAD 2>/dev/null)"
if [ -n "$VS_HEAD" ]; then
  printf '%s\n' "$VS_HEAD"
else
  echo "none"
fi

# --- Resolve the base branch ---------------------------------------------------------------
resolve_base() {
  if [ -n "$BASE" ]; then
    if git -C "$REPO" rev-parse --verify -q "$BASE" >/dev/null 2>&1; then
      printf '%s' "$BASE"
      return 0
    fi
    return 1
  fi
  local candidate origin_head
  origin_head="$(git -C "$REPO" symbolic-ref --short refs/remotes/origin/HEAD 2>/dev/null || true)"
  if [ -n "$origin_head" ] && git -C "$REPO" rev-parse --verify -q "$origin_head" >/dev/null 2>&1; then
    printf '%s' "$origin_head"
    return 0
  fi
  for candidate in origin/main main origin/master master; do
    if git -C "$REPO" rev-parse --verify -q "$candidate" >/dev/null 2>&1; then
      printf '%s' "$candidate"
      return 0
    fi
  done
  return 1
}

print_capped_diff() { # $1 = full unified diff text
  local full="$1" total=0
  echo
  echo "diff:"
  if [ -n "$full" ]; then
    total="$(printf '%s\n' "$full" | wc -l | tr -d ' ')"
  fi
  if [ "$total" -gt "$MAX_LINES" ]; then
    printf '%s\n' "$full" | head -n "$MAX_LINES"
    echo "truncated: $MAX_LINES/$total"
  else
    [ -n "$full" ] && printf '%s\n' "$full"
    echo "truncated: $total/$total"
  fi
}

RESOLVED_BASE=""
MERGE_BASE=""
if RESOLVED_BASE="$(resolve_base)" && [ -n "$RESOLVED_BASE" ]; then
  MERGE_BASE="$(git -C "$REPO" merge-base HEAD "$RESOLVED_BASE" 2>/dev/null || true)"
fi

if [ -n "$RESOLVED_BASE" ] && [ -n "$MERGE_BASE" ]; then
  echo
  echo "base: $RESOLVED_BASE"
  echo "changed vs base:"
  VS_BASE="$(git -C "$REPO" diff --name-status "$MERGE_BASE" HEAD 2>/dev/null)"
  if [ -n "$VS_BASE" ]; then
    printf '%s\n' "$VS_BASE"
  else
    echo "none"
  fi

  if [ "$WANT_DIFF" -eq 1 ]; then
    # Working tree vs merge-base — the change under test is usually still uncommitted
    # (qa-run's own note), so this must include it, not just what's on HEAD.
    print_capped_diff "$(git -C "$REPO" diff "$MERGE_BASE" 2>/dev/null)"
  fi
else
  echo
  echo "base: unresolved"
  if [ "$WANT_DIFF" -eq 1 ]; then
    # No merge-base to diff against — still report working tree vs HEAD, per R2-22.
    print_capped_diff "$(git -C "$REPO" diff HEAD 2>/dev/null)"
  fi
fi

exit 0
