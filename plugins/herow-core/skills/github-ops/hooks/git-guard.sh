#!/usr/bin/env bash
# github-ops PreToolUse/Bash guard.
# Read-only gh/glab commands (view/list/diff/status/checks/...) — including via
# the skill's own read-only scripts (inspect.sh, commit-msg.sh, pr/issue/repo.sh
# view|list|checks|diff|info|releases|runs) — are ALLOWED outright, no
# permission prompt. Only write/mutating PR/issue/release/CI commands surface a
# confirmation ("ask") that nudges toward the github-ops scripts. Raw git
# commit/push are left alone (normal permission rules); read-only git
# (status/diff/log) is RTK's own hook — so no overlap.
# Never blocks hard, never errors.

CMD="$(python3 -c "import json,sys; d=json.load(sys.stdin); print(d.get('tool_input',d).get('command',''))" 2>/dev/null || true)"
[ -n "$CMD" ] || exit 0

# Strip a leading RTK proxy prefix so `rtk [proxy] git commit` matches like
# `git commit`. `rtk proxy ` must be stripped before the shorter `rtk ` prefix,
# or `rtk proxy gh pr view 42` is left as `proxy gh pr view 42` and matches
# nothing below.
CMD="${CMD#rtk proxy }"
CMD="${CMD#rtk }"

# Hard block: NEVER allow any Claude Code / Anthropic reference into a commit or
# PR/MR body, under any circumstance — even via the github-ops scripts (they
# strip it too, this is the belt-and-suspenders deny). Catches Co-Authored-By:
# Claude, the "Generated with Claude Code" footer, the "Claude-Session:" footer,
# any "claude.ai/code" session link, and any "Claude Code" mention. Keep this
# pattern in sync with strip_attribution() in scripts/_common.sh.
#
# Scoped to commands that could actually carry a commit/PR/MR message — a
# message/body flag, or a git/gh/glab verb that always takes one — not every
# Bash call. Un-scoped, this used to deny any command merely containing the
# words "anthropic" or "claude code", e.g. `gh pr view 42 --repo
# anthropics/claude-code` or `rg "claude code" CHANGELOG.md`.
#
# Three boundary bugs, fixed: (1) a bare substring match on `-m`/verb names
# collided with unrelated flags/verbs sharing the same text — `rg -m 1
# "claude code" x`, `find . -mtime -1`, and `gh pr reviews` (vs `gh pr
# review`) all tripped the old glob and got wrongly denied. Flags and verbs
# are now matched with real word boundaries via grep -E. (2) the flag/verb
# check must only run at all when the command actually touches
# git/gh/glab/a github-ops script — a message-shaped flag on an unrelated
# tool must never reach this far. (3) "a github-ops script" must be
# recognized by BASENAME, not only by the literal `github-ops/scripts/`
# path substring — `bash scripts/ship.sh -m "...Co-Authored-By: Claude"` or
# a bare `issue.sh comment ...` (relative path, symlink, PATH resolution)
# used to skip this check entirely, and issue.sh has no scrub_body_file
# call of its own, so that gap was the ONLY defense for issue bodies/
# comments, not belt-and-suspenders. Deliberately broad: any repo's own
# unrelated same-named script now also gets extra scrutiny here — an
# over-denial false positive is the safe direction for a hard-deny gate.
attr_relevant=0
case "$CMD" in
  *git\ *|*gh\ *|*glab\ *|*github-ops/scripts/*) attr_candidate=1 ;;
  *) attr_candidate=0 ;;
esac
if [ "$attr_candidate" = 0 ] && printf '%s' "$CMD" | grep -qE '(^|[[:space:]/])(ship|pr|issue|repo|commit-msg)\.sh("|'"'"')?([[:space:]]|$)'; then
  attr_candidate=1
fi
if [ "$attr_candidate" = 1 ]; then
    if printf '%s' "$CMD" | grep -qE '(^|[[:space:]])(-m|--message|--body|--body-file|--description)([[:space:]=]|$)'; then
      attr_relevant=1
    fi
    if printf '%s' "$CMD" | grep -qE '(^|[[:space:]])(git commit|gh pr (create|edit|comment|review)|gh issue (create|comment)|gh release (create|edit)|glab mr (create|update|note)|glab issue (create|note))([[:space:]]|$)'; then
      attr_relevant=1
    fi
fi
if [ "$attr_relevant" = 1 ] && printf '%s' "$CMD" | grep -qiE 'co-authored-by:[[:space:]]*claude|anthropic|generated with \[?claude code|🤖[[:space:]]*generated with|claude-session:|claude\.ai/code|claude code'; then
  reason="github-ops: refusing — never add a Claude Code / Anthropic reference (Co-Authored-By: Claude, 'Generated with Claude Code', a Claude-Session: footer, or a claude.ai/code link) to commits or PRs. Remove it and retry."
  python3 -c "import json,sys; print(json.dumps({'hookSpecificOutput':{'hookEventName':'PreToolUse','permissionDecision':'deny','permissionDecisionReason':sys.argv[1]}}))" "$reason"
  exit 0
fi

# Strip benign redirections from a check-copy: fd duplications (2>&1, >&2) and
# redirects to/from /dev/null (2>/dev/null, &>/dev/null). These don't introduce a
# second command, so they must not defeat the read-only fast-allow below. A
# redirect to a real file (> out.txt) is left intact — it can clobber, so it stays
# flagged.
CHK="$(printf '%s' "$CMD" | sed -E -e 's/[0-9]*>>?&[0-9]+//g' -e 's/(&|[0-9]*)>>?[[:space:]]*\/dev\/[a-z]+//g')"

# PERF GATE (DX #7): this hook runs on EVERY Bash tool call. Only gh/glab
# commands and the skill's own scripts are ever gated below, so bail fast for
# everything else — ordinary commands (`npm test`, `cat a | grep b`) must never
# pay the per-segment parsing cost.
case "$CMD" in
  *gh\ *|*glab\ *|*github-ops/scripts/*) ;;
  *) exit 0 ;;
esac

# Read-only gh/glab verbs (single segment) — see the alternation below for the full set.
ro_re='^(gh ((pr (view|list|diff|checks|status|checkout|reviews))|(issue (view|list|status))|(release (view|list|download))|(run (view|list|watch|download))|(workflow (view|list))|(repo (view|list))|(label list)|(cache list)|(variable list)|(secret list)|(gist list)|(extension list)|(browse)|(status)|(auth status)|(--version)|(search ))|glab ((mr (view|list|diff|checkout|checks))|(issue (view|list))|(release (view|list))|(ci (view|list|status|trace))|(pipeline list)|(repo view)|(auth status)))'
# Read-only `gh api`/`glab api`: allowed only when nothing indicates a write —
# no non-GET -X/--method, no -f/--field/--raw-field/--input write payload. A
# prefix permission rule can't express this distinction; the hook can. Known
# false-negative, accepted: `gh api graphql -f query=...` is a read that uses
# `-f` for the query body — it falls through to the normal ask/prompt instead
# of an auto-allow. Conservative direction, not a bug.
api_re='^(gh|glab) api([[:space:]]|$)'
api_write_re='(^|[[:space:]])(-X|--method)[[:space:]=]*(POST|PUT|PATCH|DELETE)([[:space:]]|$)|(^|[[:space:]])(-f|--field|--raw-field|--input)([[:space:]=]|$)'
# Read-only invocations of the skill's own scripts — treated as a read-only
# segment just like ro_re, so a compound command mixing a read-only script call
# with a mutating one (`pr.sh view 42; ship.sh --message x`) is NOT allowed:
# every segment must independently qualify.
script_ro_re='github-ops/scripts/(inspect|commit-msg)\.sh"?([[:space:]]|$)|github-ops/scripts/(pr|issue|repo)\.sh"?[[:space:]]+(view|list|checks|diff|info|releases|runs)([[:space:]]|$)'
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
    # Tolerate a redirect to /tmp only — restricted to a FLAT filename (no `/`
    # allowed in the character class), not `[^[:space:]]+`. The looser form
    # let `/tmp/../../../etc/passwd` match as a "tolerated /tmp target" and
    # get auto-allowed: `..` and `/` were never excluded, so the trailing-`$`
    # match still covered the whole traversal string. A flat filename can
    # still be a pre-planted symlink to somewhere sensitive — that residual
    # is accepted (this hook is a heuristic UX guard, not a sandbox) — but it
    # closes the demonstrated traversal and any symlinked-subdirectory path.
    s="$(printf '%s' "$s" | sed -E 's/[[:space:]]*>>?[[:space:]]*\/tmp\/[A-Za-z0-9._-]+[[:space:]]*$//')"
    # Any residual `>`/`<` is checked on a de-quoted copy: a real shell redirect
    # never sits inside quotes, but a GitHub search qualifier does (`--search
    # "created:>2024-01-01"`). ro_re/safe_re match a PREFIX and would ignore a
    # trailing real redirect (`> /etc/passwd`), so it's guarded here explicitly.
    # /dev/null + fd-dups were already stripped when CHK was built above.
    s_noquotes="$(printf '%s' "$s" | sed -E 's/"[^"]*"//g; s/'"'"'[^'"'"']*'"'"'//g')"
    case "$s_noquotes" in *'>'*|*'<'*) all_safe=0; break ;; esac
    if printf '%s' "$s" | grep -qE "$api_re"; then
      # -i: HTTP method tokens are conventionally uppercase but gh/glab don't
      # enforce that on the CLI arg — `-X delete` must be caught too.
      if printf '%s' "$s" | grep -qEi "$api_write_re"; then all_safe=0; break; fi
      has_ro=1; continue
    fi
    if printf '%s' "$s" | grep -qE "$ro_re"; then has_ro=1; continue; fi
    if printf '%s' "$s" | grep -qE "$safe_re"; then continue; fi
    if printf '%s' "$s" | grep -qE "$script_ro_re"; then has_ro=1; continue; fi
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
