#!/usr/bin/env bash
# Suggest a conventional commit message from currently staged changes.
# Output: type|scope|description   (scope may be empty)
# Exit non-zero if nothing is staged.

set -eu
DIR="$(cd "$(dirname "$0")" && pwd)"
# shellcheck disable=SC1091
. "$DIR/_common.sh"

require_repo

if git diff --cached --quiet; then
  die "nothing-staged" "stage changes first"
fi

FILES="$(git diff --cached --name-only)"
DIFF="$(git diff --cached)"

# --- type ---
type=""
if echo "$FILES" | grep -qE '(^|/)(test|tests|__tests__|spec)(/|$)|\.test\.|\.spec\.'; then
  type="test"
elif echo "$FILES" | grep -qE '\.(md|mdx|txt|rst|adoc)$'; then
  if [ "$(echo "$FILES" | grep -cvE '\.(md|mdx|txt|rst|adoc)$')" = "0" ]; then
    type="docs"
  fi
fi
if [ -z "$type" ]; then
  if echo "$FILES" | grep -qE '(^|/)(package\.json|package-lock\.json|yarn\.lock|pnpm-lock\.yaml|requirements\.txt|Pipfile|poetry\.lock|Cargo\.toml|Cargo\.lock|go\.mod|go\.sum|Gemfile|Gemfile\.lock)$'; then
    type="chore"
  elif echo "$FILES" | grep -qE '(^|/)(\.github/workflows/|\.gitlab-ci\.yml|Dockerfile|\.circleci/)'; then
    type="ci"
  elif echo "$DIFF" | grep -qiE '^\+.*\b(fix|bug|hotfix|patch)\b'; then
    type="fix"
  elif echo "$DIFF" | grep -qiE '^\+.*\b(refactor|rename|extract|inline)\b'; then
    type="refactor"
  elif echo "$DIFF" | grep -qiE '^\+.*\b(perf|performance|optimi[sz]e)\b'; then
    type="perf"
  else
    type="feat"
  fi
fi

# --- scope ---
# Use the most common top-level dir among staged files, ignoring noise.
scope="$(echo "$FILES" \
  | awk -F/ 'NF>1 {print $1}' \
  | grep -vE '^(\.|node_modules|dist|build|vendor)$' \
  | sort | uniq -c | sort -rn | head -1 | awk '{print $2}')"
# If only one file, fall back to its basename without extension.
if [ -z "$scope" ]; then
  one="$(echo "$FILES" | head -1)"
  scope="$(basename "$one" | sed 's/\.[^.]*$//')"
fi
# Friendly aliases.
case "$scope" in
  src|lib|app) scope="" ;;
esac

# --- description ---
num="$(echo "$FILES" | sed '/^$/d' | wc -l | tr -d ' ')"
case "$type" in
  docs)     desc="update documentation" ;;
  test)     desc="update tests" ;;
  chore)    desc="update dependencies" ;;
  ci)       desc="update ci config" ;;
  *)
    if [ "$num" = "1" ]; then
      desc="update $(basename "$(echo "$FILES" | head -1)")"
    else
      desc="update $num files"
    fi
    ;;
esac

echo "${type}|${scope}|${desc}"
