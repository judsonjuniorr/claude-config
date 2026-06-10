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

# Strip benign redirections from a check-copy: fd duplications (2>&1, >&2) and
# redirects to/from /dev/null (2>/dev/null, &>/dev/null). These don't introduce a
# second command, so they must not defeat the read-only fast-allow below. A
# redirect to a real file (> out.txt) is left intact — it can clobber, so it stays
# flagged.
CHK="$(printf '%s' "$CMD" | sed -E -e 's/[0-9]*>>?&[0-9]+//g' -e 's/(&|[0-9]*)>>?[[:space:]]*\/dev\/[a-z]+//g')"

# PERF GATE (DX #7): this hook runs on EVERY Bash tool call. Only gh/glab commands
# are ever gated below, so bail fast for everything else — ordinary commands
# (`npm test`, `cat a | grep b`) must never pay the per-segment parsing cost.
case "$CMD" in
  *gh\ *|*glab\ *) ;;
  *) exit 0 ;;
esac

# Read-only gh/glab verbs (single segment). Added: pr checkout/reviews, mr checkout.
ro_re='^(gh (pr (view|list|diff|checks|status|checkout|reviews)|issue (view|list|status)|release (view|list|download)|run (view|list|watch|download)|workflow (view|list)|repo view|auth status|search )|glab (mr (view|list|diff|checkout)|issue (view|list)|release (view|list)|ci (view|list|status|trace)|repo view|auth status))'
# Safe inspector/pipe-target helpers (read-only or temp-only).
# Deliberately EXCLUDES tee/sed/awk: they write files (`tee FILE`, `sed -i`, awk
# redirection) and would let a write smuggle into an auto-allowed chain.
# Residual (accepted, low-severity, documented): `sort -o FILE` / `uniq IN OUT`
# can still write via an unusual flag — worst case overwrites one file, not
# arbitrary execution.
safe_re='^(cat|head|tail|wc|less|more|jq|grep|egrep|fgrep|rg|sort|uniq|cut|tr|column|nl|echo|printf|true|git (branch|log|diff|status|show|rev-parse))( |$)'

all_safe=1; has_ro=0
# Bail on ALL substitution — `$(...)`, backticks, AND process substitution
# `<(...)` / `>(...)` — any of which hides an arbitrary command inside an
# otherwise read-only-looking chain (e.g. `gh pr diff 1 > /tmp/x; cat <(rm -rf y)`).
case "$CHK" in *'$('*|*'`'*|*'<('*|*'>('*) all_safe=0 ;; esac
if [ "$all_safe" = 1 ]; then
  oldIFS="$IFS"; IFS='|&;'$'\n'; set -f          # split on | & ; (covers || &&) and newlines; disable globbing
  for seg in $CHK; do
    s="$(printf '%s' "$seg" | sed -E 's/^[[:space:]]+//; s/[[:space:]]+$//')"
    [ -n "$s" ] || continue
    s="${s#rtk proxy }"; s="${s#rtk }"           # treat `rtk [proxy] <cmd>` like <cmd>
    s="$(printf '%s' "$s" | sed -E 's/[[:space:]]*>>?[[:space:]]*\/tmp\/[^[:space:]]+[[:space:]]*$//')"  # tolerate redirect to /tmp only
    # Any residual redirect after the /tmp-only strip is a non-/tmp real-file
    # redirect (`> /etc/passwd`) or an input redirect — ro_re/safe_re match a
    # PREFIX and would ignore the trailing `> file`, so guard it here. /dev/null
    # + fd-dups were already stripped at line 36; only real-file redirects remain.
    case "$s" in *'>'*|*'<'*) all_safe=0; break ;; esac
    if printf '%s' "$s" | grep -qE "$ro_re"; then has_ro=1; continue; fi
    if printf '%s' "$s" | grep -qE "$safe_re"; then continue; fi
    all_safe=0; break
  done
  IFS="$oldIFS"; set +f
fi
if [ "$all_safe" = 1 ] && [ "$has_ro" = 1 ]; then
  python3 -c "import json; print(json.dumps({'hookSpecificOutput':{'hookEventName':'PreToolUse','permissionDecision':'allow','permissionDecisionReason':'github-ops: read-only command — no confirmation needed.'}}))"
  exit 0
fi

# Write/mutating PR/issue/release/CI commands → ask, nudging toward the script.
suggest=""
case "$CMD" in
  gh\ pr\ *|glab\ mr\ *)                          suggest="pr.sh" ;;
  gh\ issue\ *|glab\ issue\ *)                    suggest="issue.sh" ;;
  gh\ release\ *|gh\ run\ *|gh\ workflow\ *|glab\ ci\ *|glab\ release\ *) suggest="repo.sh" ;;
esac

[ -n "$suggest" ] || exit 0

SCRIPTS_DIR="${CLAUDE_PLUGIN_ROOT:+$CLAUDE_PLUGIN_ROOT/skills/}github-ops/scripts"
reason="github-ops: prefer \`bash \"${SCRIPTS_DIR}/${suggest}\"\` over running raw \`${CMD}\` (pipe-delimited output, fewer tokens)."
python3 -c "import json,sys; print(json.dumps({'hookSpecificOutput':{'hookEventName':'PreToolUse','permissionDecision':'ask','permissionDecisionReason':sys.argv[1]}}))" "$reason"
exit 0
