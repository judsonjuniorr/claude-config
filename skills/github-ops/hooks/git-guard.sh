#!/usr/bin/env bash
# github-ops PreToolUse/Bash guard.
# Read-only gh/glab commands (view/list/diff/status/checks/...) are ALLOWED
# outright — no permission prompt. Only write/mutating PR/issue/release/CI
# commands surface a confirmation ("ask") that nudges toward the github-ops
# scripts. Raw git commit/push are left alone (normal permission rules);
# read-only git (status/diff/log) is RTK's own hook — so no overlap.
# Never blocks hard, never errors.

CMD="$(python3 -c "import json,sys; d=json.load(sys.stdin); print(d.get('tool_input',d).get('command',''))" 2>/dev/null || true)"
[ -n "$CMD" ] || exit 0

# Strip a leading RTK proxy prefix so `rtk git commit` matches like `git commit`.
CMD="${CMD#rtk }"

# Hard block: NEVER allow AI-attribution trailers into a commit or PR/MR body,
# under any circumstance — even via the github-ops scripts (they strip it too,
# this is the belt-and-suspenders deny). Catches Co-Authored-By: Claude and the
# "Generated with Claude Code" footer in any git/gh/glab mutation command.
if printf '%s' "$CMD" | grep -qiE 'co-authored-by:[[:space:]]*claude|noreply@anthropic\.com|generated with \[?claude code|🤖[[:space:]]*generated with'; then
  reason="github-ops: refusing — never add Co-Authored-By: Claude or 'Generated with Claude Code' attribution to commits or PRs. Remove the attribution and retry."
  python3 -c "import json,sys; print(json.dumps({'hookSpecificOutput':{'hookEventName':'PreToolUse','permissionDecision':'deny','permissionDecisionReason':sys.argv[1]}}))" "$reason"
  exit 0
fi

# Allow the github-ops scripts themselves (they call git/gh internally).
case "$CMD" in
  *github-ops/scripts/*) exit 0 ;;
esac

# Strip benign trailing redirects (stderr/stdout merges and /dev/null discards)
# so a read-only command like `gh pr diff 21 2>&1` still fast-allows. These tokens
# never write to a real file, so removing them is safe for classification — while
# pipes, chains, substitutions and real file redirects still fall through below.
# Loops to peel stacked forms like `>/dev/null 2>&1`.
while :; do
  trimmed="$(printf '%s' "$CMD" | sed -E 's/[[:space:]]*(2>&1|>&2|&>\/dev\/null|2>\/dev\/null|1?>\/dev\/null)[[:space:]]*$//')"
  [ "$trimmed" = "$CMD" ] && break
  CMD="$trimmed"
done

# Read-only gh/glab commands → allow without a prompt. Listed before the broad
# write patterns below so e.g. `gh pr view` resolves here, not to the pr.sh nudge.
case "$CMD" in
  # Never fast-allow a command that chains, redirects, pipes, or substitutes —
  # even if it starts with a read-only verb (e.g. `gh pr view 1 && rm -rf x` or
  # `gh pr view$(...)`). Let those fall through to the write-nudge / normal flow.
  *'&'*|*';'*|*'|'*|*'<'*|*'>'*|*'$('*|*'`'*|*$'\n'*) : ;;
  gh\ pr\ view*|gh\ pr\ list*|gh\ pr\ diff*|gh\ pr\ checks*|gh\ pr\ status*|\
  glab\ mr\ view*|glab\ mr\ list*|glab\ mr\ diff*|\
  gh\ issue\ view*|gh\ issue\ list*|gh\ issue\ status*|\
  glab\ issue\ view*|glab\ issue\ list*|\
  gh\ release\ view*|gh\ release\ list*|gh\ release\ download*|\
  glab\ release\ view*|glab\ release\ list*|\
  gh\ run\ view*|gh\ run\ list*|gh\ run\ watch*|gh\ run\ download*|\
  gh\ workflow\ view*|gh\ workflow\ list*|\
  glab\ ci\ view*|glab\ ci\ list*|glab\ ci\ status*|glab\ ci\ trace*|\
  gh\ repo\ view*|glab\ repo\ view*|\
  gh\ auth\ status*|glab\ auth\ status*|\
  gh\ search\ *)
    python3 -c "import json; print(json.dumps({'hookSpecificOutput':{'hookEventName':'PreToolUse','permissionDecision':'allow','permissionDecisionReason':'github-ops: read-only command — no confirmation needed.'}}))"
    exit 0
    ;;
esac

# Write/mutating PR/issue/release/CI commands → ask, nudging toward the script.
suggest=""
case "$CMD" in
  gh\ pr\ *|glab\ mr\ *)                          suggest="pr.sh" ;;
  gh\ issue\ *|glab\ issue\ *)                    suggest="issue.sh" ;;
  gh\ release\ *|gh\ run\ *|gh\ workflow\ *|glab\ ci\ *|glab\ release\ *) suggest="repo.sh" ;;
esac

[ -n "$suggest" ] || exit 0

reason="github-ops: prefer \`bash github-ops/scripts/${suggest}\` over running raw \`${CMD}\` (pipe-delimited output, fewer tokens)."
python3 -c "import json,sys; print(json.dumps({'hookSpecificOutput':{'hookEventName':'PreToolUse','permissionDecision':'ask','permissionDecisionReason':sys.argv[1]}}))" "$reason"
exit 0
