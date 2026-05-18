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

# Require an explicit --message. Emit the staged diff so the agent can
# craft a descriptive Conventional Commits subject, then re-run with
# --message "...". --amend keeps the prior message and skips this gate.
if [ -z "$MSG" ] && [ "$AMEND" = "0" ]; then
  echo "need-message|1"
  FILES_CSV="$(git diff --cached --name-only | paste -sd, -)"
  echo "diff-files|$FILES_CSV"
  git diff --cached --stat | sed 's/^/diff-stat|/'
  TOTAL="$(git diff --cached | wc -l | tr -d ' ')"
  git diff --cached | head -200 | sed 's/^/diff|/'
  if [ "$TOTAL" -gt 200 ]; then
    echo "diff|...(truncated, $TOTAL total lines)"
  fi
  die "need-message" "re-run with --message \"<conventional-commit subject>\""
fi

FOOTER="$(printf '\n\n🤖 Generated with Claude Code\n\nCo-Authored-By: Claude <noreply@anthropic.com>')"
if [ "$AMEND" = "1" ]; then
  if [ -z "$MSG" ]; then
    git commit --amend --no-edit >/dev/null
  else
    git commit --amend -m "${MSG}${FOOTER}" >/dev/null
  fi
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
