#!/usr/bin/env bash
# Stage + conventional commit + push.
# Usage: ship.sh [--message "msg"] [--no-push] [--amend] [--force]
# Output (pipe-delimited):
#   branch|<name>
#   staged|<count>
#   commit|<sha>|<subject>
#   push|<remote/branch>|<new|existing>
#   pr-url|<url>          (only if new branch and platform known)

set -eu
DIR="$(cd "$(dirname "$0")" && pwd)"
# shellcheck disable=SC1091
. "$DIR/_common.sh"

require_repo

MSG=""
DO_PUSH=1
AMEND=0
FORCE=0
while [ $# -gt 0 ]; do
  case "$1" in
    --message|-m) MSG="${2:-}"; shift 2 ;;
    --no-push) DO_PUSH=0; shift ;;
    --amend) AMEND=1; shift ;;
    --force) FORCE=1; shift ;;
    *) die "bad-arg" "$1" ;;
  esac
done

BRANCH="$(current_branch)"
echo "branch|$BRANCH"

if git diff --quiet && git diff --cached --quiet && [ "$AMEND" = "0" ]; then
  die "nothing-to-commit" "no changes"
fi

# Stage everything if nothing is staged yet.
if git diff --cached --quiet; then
  if git status --porcelain | awk '{print $2}' | grep -Eq '(^|/)(\.env(\..+)?|.*\.(key|pem|p12|pfx)|.*_rsa|.*credentials.*\.json)$'; then
    [ "$FORCE" = "1" ] || die "secret-detected" "use --force to override"
  fi
  git add -A
fi

STAGED="$(git diff --cached --name-only | sed '/^$/d' | wc -l | tr -d ' ')"
echo "staged|$STAGED"

# Build commit message if not given.
if [ -z "$MSG" ]; then
  PARTS="$(bash "$DIR/commit-msg.sh")"
  T="$(echo "$PARTS" | cut -d'|' -f1)"
  S="$(echo "$PARTS" | cut -d'|' -f2)"
  D="$(echo "$PARTS" | cut -d'|' -f3)"
  if [ -n "$S" ]; then
    MSG="${T}(${S}): ${D}"
  else
    MSG="${T}: ${D}"
  fi
fi

FOOTER="$(printf '\n\n🤖 Generated with Claude Code\n\nCo-Authored-By: Claude <noreply@anthropic.com>')"
if [ "$AMEND" = "1" ]; then
  git commit --amend -m "${MSG}${FOOTER}" >/dev/null
else
  git commit -m "${MSG}${FOOTER}" >/dev/null
fi
SHA="$(git rev-parse --short HEAD)"
SUBJ="$(git log -1 --pretty=%s)"
echo "commit|$SHA|$SUBJ"

[ "$DO_PUSH" = "1" ] || exit 0

# Push (with -u if branch doesn't exist on remote).
if git ls-remote --exit-code --heads origin "$BRANCH" >/dev/null 2>&1; then
  if [ "$AMEND" = "1" ]; then
    git push --force-with-lease >/dev/null 2>&1 || die "push-failed" "$BRANCH"
  else
    git push >/dev/null 2>&1 || die "push-failed" "$BRANCH"
  fi
  echo "push|origin/$BRANCH|existing"
else
  git push -u origin "$BRANCH" >/dev/null 2>&1 || die "push-failed" "$BRANCH"
  echo "push|origin/$BRANCH|new"
  SLUG="$(repo_slug)"
  case "$(detect_platform)" in
    github) echo "pr-url|https://github.com/$SLUG/pull/new/$BRANCH" ;;
    gitlab) echo "pr-url|https://gitlab.com/$SLUG/-/merge_requests/new?merge_request[source_branch]=$BRANCH" ;;
  esac
fi
