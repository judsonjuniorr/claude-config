#!/usr/bin/env bash
# UserPromptSubmit hook for herow-dev (registered in herow-dev/hooks/hooks.json).
#
# Guarantees /herow-dev:{blueprint,quick,execute} start on the freshest code: it
# fast-forwards the current branch to its upstream BEFORE the command runs. At
# UserPromptSubmit time cwd is the repo root on the current branch and no worktree
# exists yet, so fast-forwarding here == freshening the base branch that quick/
# execute will branch off — the ordering lands for free.
#
# Contract (design-brief + DX review):
#   - Silent + zero cost on every non-matching prompt.
#   - Fail-open ALWAYS (exit 0): never blocks the command. UserPromptSubmit only
#     blocks on exit 2 — we never exit non-zero.
#   - `git pull --ff-only` only — never rewrites/auto-merges local commits.
#   - HEROW_SKIP_PULL is the deliberate escape hatch (offline/old-base/slow-link),
#     checked FIRST before any git call.
#   - Every skip/fail path prints reason + fix; noisy-but-fine paths stay silent.

set -u

# --- 1. Read the submitted prompt and match the three commands -----------------
RAW="$(cat)"

# Prefer jq for a clean .prompt extract; fall back to the raw payload for matching
# if jq is absent (do not hard-depend on jq). The slash-command text is present in
# either form, which is all the regex needs.
if command -v jq >/dev/null 2>&1; then
  PROMPT="$(printf '%s' "$RAW" | jq -r '.prompt // empty' 2>/dev/null)"
  [ -z "$PROMPT" ] && PROMPT="$RAW"
else
  PROMPT="$RAW"
fi

# Only act on blueprint / quick / execute. Anything else: silent, instant exit.
# Anchored so an incidental mention doesn't fire a pull: the command must be bounded
# by start/end, whitespace, or a JSON quote (the last covers the jq-absent path where
# we match against the raw `"...prompt..."` payload). Blocks e.g. `/herow-dev:executed`.
printf '%s' "$PROMPT" | grep -Eq '(^|[[:space:]"])/herow-dev:(blueprint|quick|execute)([[:space:]"]|$)' || exit 0

# --- 2. Escape hatch (checked before any git call) -----------------------------
if [ -n "${HEROW_SKIP_PULL:-}" ]; then
  echo "↻ freshness skip: HEROW_SKIP_PULL set"
  exit 0
fi

# --- 3. Fail-open guards -------------------------------------------------------
# Not a git repo → nothing to pull, stay silent.
git rev-parse --is-inside-work-tree >/dev/null 2>&1 || exit 0

# Detached HEAD → no branch to fast-forward.
BRANCH="$(git symbolic-ref -q --short HEAD 2>/dev/null)" || {
  echo "↻ freshness skip: detached HEAD — no branch to fast-forward"
  exit 0
}

# No upstream configured → nothing to pull from.
git rev-parse --abbrev-ref --symbolic-full-name '@{u}' >/dev/null 2>&1 || {
  echo "↻ freshness skip: '${BRANCH}' has no upstream — push/set upstream to enable"
  exit 0
}

# --- 4. Fast-forward the current branch ----------------------------------------
BEFORE="$(git rev-parse --short HEAD 2>/dev/null)"
# Non-interactive: a passphrase/credential prompt or unreachable remote must fail
# fast into the fail-open branch below, never hang waiting on a tty. The hook's
# hooks.json `timeout` bounds the remaining fetch latency.
if GIT_TERMINAL_PROMPT=0 GIT_SSH_COMMAND='ssh -oBatchMode=yes' git pull --ff-only >/dev/null 2>&1; then
  AFTER="$(git rev-parse --short HEAD 2>/dev/null)"
  # Only speak when something actually advanced; up-to-date stays silent.
  [ "$BEFORE" != "$AFTER" ] && echo "↻ pulled latest: ${BEFORE}..${AFTER}"
else
  echo "⚠ freshness: pull failed (offline or diverged) — continuing on local state"
fi

exit 0
