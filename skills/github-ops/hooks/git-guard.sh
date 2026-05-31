#!/usr/bin/env bash
# github-ops PreToolUse/Bash guard.
# Nudges raw mutation/PR commands (git commit|push, gh|glab pr/issue/release/ci)
# toward the github-ops scripts. Read-only git (status/diff/log) is left alone —
# RTK's own hook handles those, so this guard does not overlap.
#
# Severity: "ask" — surfaces the suggested script in a permission prompt; the
# user can approve the raw command or let Claude re-issue via the script.
# Never blocks hard, never errors.

CMD="$(python3 -c "import json,sys; d=json.load(sys.stdin); print(d.get('tool_input',d).get('command',''))" 2>/dev/null || true)"
[ -n "$CMD" ] || exit 0

# Strip a leading RTK proxy prefix so `rtk git commit` matches like `git commit`.
CMD="${CMD#rtk }"

# Allow the github-ops scripts themselves (they call git/gh internally).
case "$CMD" in
  *github-ops/scripts/*) exit 0 ;;
esac

suggest=""
case "$CMD" in
  git\ commit*|git\ push*)                       suggest="ship.sh" ;;
  gh\ pr\ *|glab\ mr\ *)                          suggest="pr.sh" ;;
  gh\ issue\ *|glab\ issue\ *)                    suggest="issue.sh" ;;
  gh\ release\ *|gh\ run\ *|gh\ workflow\ *|glab\ ci\ *|glab\ release\ *) suggest="repo.sh" ;;
esac

[ -n "$suggest" ] || exit 0

reason="github-ops: prefer \`bash github-ops/scripts/${suggest}\` over running raw \`${CMD}\` (pipe-delimited output, fewer tokens)."
python3 -c "import json,sys; print(json.dumps({'hookSpecificOutput':{'hookEventName':'PreToolUse','permissionDecision':'ask','permissionDecisionReason':sys.argv[1]}}))" "$reason"
exit 0
