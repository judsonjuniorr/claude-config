#!/usr/bin/env bash
# Compact working-tree + recent-log inspection. One call replaces
# `git status` + `git diff` + `git log`.
# Usage: inspect.sh [--diff] [--log N]
# Output (pipe-delimited):
#   branch|<name>|<clean|dirty>|ahead N|behind N
#   remote|<remote/branch>            (omitted if no upstream)
#   staged|<count>
#   unstaged|<count>
#   untracked|<count>
#   file|<porcelain-status>|<path>    (capped at 50)
#   diff-stat|<shortstat>             (only if --diff)
#   log|<sha>|<subject>               (default 3)

set -eu
DIR="$(cd "$(dirname "$0")" && pwd)"
# shellcheck disable=SC1091
. "$DIR/_common.sh"

require_repo

SHOW_DIFF=0
LOG_N=3
while [ $# -gt 0 ]; do
  case "$1" in
    --diff) SHOW_DIFF=1; shift ;;
    --log) LOG_N="${2:-3}"; shift 2 ;;
    *) die "bad-arg" "$1" ;;
  esac
done

BRANCH="$(current_branch)"
DIRTY="clean"
if ! git diff --quiet || ! git diff --cached --quiet; then
  DIRTY="dirty"
fi
if [ -n "$(git ls-files --others --exclude-standard)" ]; then
  DIRTY="dirty"
fi

if UPSTREAM="$(git rev-parse --abbrev-ref --symbolic-full-name @{u} 2>/dev/null)"; then
  AHEAD="$(git rev-list --count "${UPSTREAM}..HEAD" 2>/dev/null || echo 0)"
  BEHIND="$(git rev-list --count "HEAD..${UPSTREAM}" 2>/dev/null || echo 0)"
  echo "branch|$BRANCH|$DIRTY|ahead $AHEAD|behind $BEHIND"
  echo "remote|$UPSTREAM"
else
  echo "branch|$BRANCH|$DIRTY|ahead 0|behind 0"
fi

STAGED="$(git diff --cached --name-only | sed '/^$/d' | wc -l | tr -d ' ')"
UNSTAGED="$(git diff --name-only | sed '/^$/d' | wc -l | tr -d ' ')"
UNTRACKED="$(git ls-files --others --exclude-standard | sed '/^$/d' | wc -l | tr -d ' ')"
echo "staged|$STAGED"
echo "unstaged|$UNSTAGED"
echo "untracked|$UNTRACKED"

git status --porcelain | head -50 | while IFS= read -r line; do
  S="$(printf '%s' "$line" | cut -c1-2 | sed 's/ /./g')"
  P="$(printf '%s' "$line" | cut -c4-)"
  echo "file|$S|$P"
done

if [ "$SHOW_DIFF" = "1" ]; then
  STAT="$(git diff --shortstat HEAD 2>/dev/null | sed 's/^ *//')"
  [ -n "$STAT" ] && echo "diff-stat|$STAT"
fi

git log --pretty=format:'log|%h|%s' -n "$LOG_N" 2>/dev/null
echo
