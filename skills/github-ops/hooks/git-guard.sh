#!/usr/bin/env bash
# github-ops PreToolUse/Bash guard.
# Nudges raw PR/issue/release commands (gh|glab pr/issue/release/ci) toward the
# github-ops scripts. Raw git commit/push are left alone (handled by normal
# permission rules); read-only git (status/diff/log) is RTK's own hook — so this
# guard does not overlap.
#
# Severity: "ask" — surfaces the suggested script in a permission prompt; the
# user can approve the raw command or let Claude re-issue via the script.
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
