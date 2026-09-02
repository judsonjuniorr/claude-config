#!/usr/bin/env bash
# github-ops PreToolUse/Bash guard.
# Three tiers on gh/glab:
#   1. Read-only (view/list/diff/status/checks/...) — ALLOWED outright, no
#      prompt. Covers the skill's own scripts too when called with a
#      read-only verb (inspect.sh, commit-msg.sh, pr.sh view|list|checks|diff,
#      issue.sh view|list, repo.sh info|releases|runs) — see script_allow_re.
#   2. Non-destructive writes (pr ready/comment/review/reopen/lock/unlock/
#      update-branch, issue comment/reopen/pin/unpin/transfer/lock/unlock/
#      develop, release upload, run rerun, workflow run/enable/disable, and the
#      glab equivalents) — also ALLOWED outright, no prompt. See write_allow_re
#      for the exact verb list. The skill's own scripts get the same tier for
#      the equivalent verb (pr.sh ready, issue.sh comment, repo.sh
#      workflow-run) — see script_allow_re.
#   3. Destructive/identity-shaping writes on gh pr/issue/release/run/workflow
#      and glab mr/issue/ci/release (create, edit, close, delete, delete-asset,
#      cancel, merge, and glab's update) — surface a confirmation ("ask") that
#      nudges toward the matching github-ops script. Gated on the VERB, not
#      just the family: a read-only or non-destructive-write command that
#      merely fails the tier-1/2 fast-allow (piped to an unrecognized helper,
#      a `;`/`|` inside a quoted arg) gets NO decision here — it falls through
#      to normal Bash permission rules instead of an unhelpful "prefer the
#      script" nudge on a command the script tier has nothing to do with. A
#      destructive verb on a gh/glab command family this hook doesn't classify
#      (secret, cache, label, gist, repo, api, …) also gets no decision from
#      this hook at all — normal Bash permission rules apply, un-gated. See
#      destructive_re and the `suggest` case at the bottom for the exact verb/
#      family list this tier covers.
# Raw git commit/push are left alone (normal permission rules); read-only git
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
# Non-destructive gh/glab writes (single segment) — allowed outright, same tier
# as ro_re. Deliberately EXCLUDES create/edit/close/delete/cancel/merge/update:
# those stay behind the `ask` at the bottom. Boundary group at the end
# (`([[:space:]]|$)`) is required so e.g. `pr review` doesn't prefix-match
# `pr reviews` (already read-only, in ro_re) or vice versa.
write_allow_re='^(gh ((pr (ready|comment|review|reopen|lock|unlock|update-branch))|(issue (comment|reopen|pin|unpin|transfer|lock|unlock|develop))|(release (upload))|(run (rerun))|(workflow (run|enable|disable)))|glab ((mr (note|approve|revoke|rebase|todo|subscribe|unsubscribe))|(issue (note|reopen|subscribe|unsubscribe))|(release (upload))|(ci (retry|run|trigger))))([[:space:]]|$)'
# Read-only/non-destructive invocations of the skill's own scripts — treated
# the same as ro_re/write_allow_re, so a compound command mixing an allowed
# script call with a mutating one (`pr.sh view 42; ship.sh --message x`) is
# NOT allowed: every segment must independently qualify. Verb list is
# per-script (not a shared alternation) so e.g. `repo.sh comment` — not a real
# repo.sh subcommand — never accidentally qualifies via issue.sh's list.
script_allow_re='github-ops/scripts/(inspect|commit-msg)\.sh"?([[:space:]]|$)|github-ops/scripts/pr\.sh"?[[:space:]]+(view|list|checks|diff|ready)([[:space:]]|$)|github-ops/scripts/issue\.sh"?[[:space:]]+(view|list|comment)([[:space:]]|$)|github-ops/scripts/repo\.sh"?[[:space:]]+(info|releases|runs|workflow-run)([[:space:]]|$)'
# Safe inspector/pipe-target helpers (read-only or temp-only).
# Deliberately EXCLUDES tee/sed/awk: they write files (`tee FILE`, `sed -i`, awk
# redirection) and would let a write smuggle into an auto-allowed chain.
# Residual (accepted, low-severity, documented): `sort -o FILE` / `uniq IN OUT`
# can still write via an unusual flag — worst case overwrites one file, not
# arbitrary execution.
safe_re='^(cat|head|tail|wc|less|more|jq|grep|egrep|fgrep|rg|sort|uniq|cut|tr|column|nl|echo|printf|true|git (branch|log|diff|status|show|rev-parse))( |$)'

all_safe=1; has_gh=0
# Bail on ALL substitution — `$(...)`, backticks, AND process substitution
# `<(...)` / `>(...)` — any of which hides an arbitrary command inside an
# otherwise read-only-looking chain (e.g. `gh pr diff 1 > /tmp/x; cat <(rm -rf y)`).
case "$CHK" in *'$('*|*'`'*|*'<('*|*'>('*) all_safe=0 ;; esac
if [ "$all_safe" = 1 ]; then
  # NOTE: a quoted `--body`/`--message` containing `;`/`|`/`&` or an embedded
  # newline (e.g. `gh pr comment 42 --body "a; b"`) still fragments into
  # segments here and sinks an otherwise write-tier-eligible command to
  # `ask` — a real UX gap, deliberately left unfixed. Four straight
  # cycles of adversarial review each broke a successively "smarter"
  # quote-aware pre-split transform meant to close it (raw quote-count
  # parity; per-type count + backslash-adjacency; a full linear quote-state
  # scanner; the same scanner narrowed to bail on any backslash or `$'`) —
  # the last of those four was defeated via bash's unquoted `#`
  # end-of-line comments, which the scanner had no concept of and which
  # contain neither a backslash nor `$'`, so it passed the narrowed
  # precondition and still let a `#'` ... real-newline ... `#'` construct
  # mask a live command separator as "inside quotes". Every fix closed one
  # bash-grammar hole and opened a smaller one; reimplementing enough of
  # bash's tokenizer to be safe is the wrong bar for a heuristic UX guard.
  # Reimplementing correctly would mean handling comments, brace expansion,
  # arithmetic expansion, and whatever construct review cycle five would
  # find — an open-ended commitment for a cosmetic classification nicety.
  # So this hook does not attempt it: segments are split directly on raw
  # `$CHK`, matching every other read-only/write-tier check in this file,
  # and a delimiter-bearing quoted argument correctly falls through to
  # `ask` (safe direction) rather than risk a wrongful `allow`.
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
      has_gh=1; continue
    fi
    if printf '%s' "$s" | grep -qE "$ro_re"; then has_gh=1; continue; fi
    if printf '%s' "$s" | grep -qE "$write_allow_re"; then has_gh=1; continue; fi
    if printf '%s' "$s" | grep -qE "$safe_re"; then continue; fi
    if printf '%s' "$s" | grep -qE "$script_allow_re"; then has_gh=1; continue; fi
    all_safe=0; break
  done
  IFS="$oldIFS"; set +f
fi
if [ "$all_safe" = 1 ] && [ "$has_gh" = 1 ]; then
  python3 -c "import json; print(json.dumps({'hookSpecificOutput':{'hookEventName':'PreToolUse','permissionDecision':'allow','permissionDecisionReason':'github-ops: gh/glab command allowed without confirmation.'}}))"
  exit 0
fi

# Write/mutating PR/issue/release/CI commands → ask, nudging toward the script.
#
# Gate by VERB, not just family: the read-only verbs (ro_re) and non-
# destructive writes (write_allow_re) were already auto-allowed above when the
# whole chain qualified. When it does NOT qualify — a pipe into an
# unrecognized helper, a `;`/`|` inside a quoted arg (the documented gap
# above) — the command used to land here and get an `ask` suggesting a script
# unrelated to it (`gh pr list` → "prefer pr.sh"). That nudge only makes sense
# for destructive verbs; for everything else this hook stays silent and
# normal Bash permission rules decide. NOT anchored at `^`: the destructive
# verb can be in any segment of a chain (`gh pr list && gh pr merge 42`) —
# same `(^|[[:space:]])` shape already used for the attribution-verb check
# above. End boundary keeps `delete` from prefix-matching `delete-asset`
# (listed explicitly).
#
# Conscious side effect: `gh pr view 42; rm -rf /tmp/x` no longer gets this
# hook's `ask` either (no destructive gh/glab verb in it) — not a real loss of
# protection, since `rm -rf` still answers to normal Bash permission rules and
# to destructive-guard.sh, which matches the same PreToolUse/Bash event.
destructive_re='(^|[[:space:]])(gh (pr|issue|release|run|workflow)|glab (mr|issue|ci|release))[[:space:]]+(create|edit|close|delete|delete-asset|cancel|merge|update)([[:space:]]|$)'
printf '%s' "$CMD" | grep -qE "$destructive_re" || exit 0

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
