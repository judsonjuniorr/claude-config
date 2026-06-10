#!/usr/bin/env bash
# PR/MR operations via gh/glab with pipe-delimited output.
# Subcommands: create | edit | list | view | merge | checks | diff
set -eu
DIR="$(cd "$(dirname "$0")" && pwd)"
# shellcheck disable=SC1091
. "$DIR/_common.sh"

require_repo
CLI="$(pick_cli)"
SUB="${1:-}"
[ -n "$SUB" ] || die "usage" "pr.sh create [--base B]|edit|list|view|merge|checks|diff"
shift || true

cmd_create() {
  local draft=0 title="" body_file="" body="" base=""
  while [ $# -gt 0 ]; do
    case "$1" in
      --draft) draft=1; shift ;;
      --title) title="$2"; shift 2 ;;
      --body) body="$2"; shift 2 ;;
      --body-file) body_file="$2"; shift 2 ;;
      --base) base="$2"; shift 2 ;;
      *) die "bad-arg" "$1" ;;
    esac
  done
  [ -n "$base" ] || base="$(default_branch)"
  local head; head="$(current_branch)"
  [ "$head" != "$base" ] || die "same-branch" "on $base; switch first"

  # --body takes precedence over the generated template; --body-file over both.
  if [ -z "$body_file" ] && [ -n "$body" ]; then
    body_file="$(mktemp)"
    printf '%s\n' "$body" > "$body_file"
  fi
  # Build body if still not provided.
  if [ -z "$body_file" ]; then
    body_file="$(mktemp)"
    {
      echo "## What"
      git log --no-merges --pretty=format:'- %s' "$base..HEAD" | head -10
      echo
      echo "## Changes"
      git diff --stat "$base...HEAD" | head -15
      echo
      echo "## Testing"
      echo "- [ ] Manual"
      echo "- [ ] Tests"
    } > "$body_file"
  fi
  [ -n "$title" ] || title="$(git log -1 --pretty=%s)"
  # Never let AI-attribution footers reach the PR/MR body.
  scrub_body_file "$body_file"

  if [ "$CLI" = "gh" ]; then
    local args=(--title "$title" --body-file "$body_file" --base "$base" --head "$head")
    [ "$draft" = "1" ] && args+=(--draft)
    local url; url="$(gh pr create "${args[@]}")" || die "create-failed" "gh"
    local num; num="$(echo "$url" | grep -oE '[0-9]+$')"
    echo "pr|$num|$url"
  else
    local args=(--title "$title" --description "$(cat "$body_file")" --target-branch "$base" --source-branch "$head")
    [ "$draft" = "1" ] && args+=(--draft)
    glab mr create "${args[@]}" >/tmp/.glab-out 2>&1 || { cat /tmp/.glab-out >&2; die "create-failed" "glab"; }
    local url; url="$(grep -oE 'https?://[^ ]+/merge_requests/[0-9]+' /tmp/.glab-out | head -1)"
    local num; num="$(echo "$url" | grep -oE '[0-9]+$')"
    echo "pr|$num|$url"
  fi
}

cmd_edit() {
  local num="${1:-}"; [ -n "$num" ] || die "usage" "pr.sh edit <num> [--title T] [--body B|--body-file F] [--add-label L] [--remove-label L]"
  shift
  local title="" body="" body_file="" add_label="" rm_label=""
  while [ $# -gt 0 ]; do
    case "$1" in
      --title) title="$2"; shift 2 ;;
      --body) body="$2"; shift 2 ;;
      --body-file) body_file="$2"; shift 2 ;;
      --add-label) add_label="$2"; shift 2 ;;
      --remove-label) rm_label="$2"; shift 2 ;;
      *) die "bad-arg" "$1" ;;
    esac
  done
  [ -n "$title$body$body_file$add_label$rm_label" ] || die "usage" "pr.sh edit <num> needs at least one field to change"
  # Never let AI-attribution footers reach the PR/MR body.
  [ -n "$body_file" ] && scrub_body_file "$body_file"
  [ -n "$body" ] && body="$(printf '%s\n' "$body" | strip_attribution)"

  if [ "$CLI" = "gh" ]; then
    local args=("$num")
    [ -n "$title" ] && args+=(--title "$title")
    if [ -n "$body_file" ]; then args+=(--body-file "$body_file")
    elif [ -n "$body" ]; then args+=(--body "$body"); fi
    [ -n "$add_label" ] && args+=(--add-label "$add_label")
    [ -n "$rm_label" ] && args+=(--remove-label "$rm_label")
    gh pr edit "${args[@]}" >/dev/null 2>&1 || die "edit-failed" "$num"
  else
    local args=("$num")
    [ -n "$title" ] && args+=(--title "$title")
    if [ -n "$body_file" ]; then args+=(--description "$(cat "$body_file")")
    elif [ -n "$body" ]; then args+=(--description "$body"); fi
    [ -n "$add_label" ] && args+=(--label "$add_label")
    [ -n "$rm_label" ] && args+=(--unlabel "$rm_label")
    glab mr update "${args[@]}" >/dev/null 2>&1 || die "edit-failed" "$num"
  fi
  echo "pr|$num|edited"
}

cmd_list() {
  local state="open" mine=0
  while [ $# -gt 0 ]; do
    case "$1" in
      --state) state="$2"; shift 2 ;;
      --mine) mine=1; shift ;;
      *) die "bad-arg" "$1" ;;
    esac
  done
  if [ "$CLI" = "gh" ]; then
    local extra=()
    [ "$mine" = "1" ] && extra+=(--author "@me")
    gh pr list --state "$state" "${extra[@]}" \
      --json number,state,title,headRefName,statusCheckRollup \
      --jq '.[] | [
        .number,
        (.state|ascii_downcase),
        .title,
        .headRefName,
        ( if (.statusCheckRollup|length)==0 then "-"
          else
            ((.statusCheckRollup | map(select(.conclusion=="SUCCESS"))|length)|tostring)
            + "/"
            + ((.statusCheckRollup|length)|tostring)
          end )
      ] | join("|")'
  else
    local extra=()
    [ "$mine" = "1" ] && extra+=(--mine)
    glab mr list --state "$state" "${extra[@]}" --output json \
      | awk 'BEGIN{RS="},{"} 1' \
      | python3 -c '
import json,sys
data=json.loads(sys.stdin.read())
for m in data:
  print("|".join([str(m.get("iid","")),m.get("state",""),m.get("title",""),m.get("source_branch",""),"-"]))
' 2>/dev/null || glab mr list --state "$state" "${extra[@]}"
  fi
}

cmd_view() {
  local num="${1:-}"; [ -n "$num" ] || die "usage" "pr.sh view <num>"
  if [ "$CLI" = "gh" ]; then
    # Header (compact) and body (separately, so it can go through emit_compact).
    gh pr view "$num" --json number,state,title,headRefName,baseRefName,author,statusCheckRollup \
      --jq '
        "pr|" + (.number|tostring) + "|" + (.state|ascii_downcase) + "|" + .title,
        "branch|" + .headRefName + "→" + .baseRefName,
        "author|" + (.author.login // "?"),
        "checks|" + (
          if (.statusCheckRollup|length)==0 then "-"
          else
            ((.statusCheckRollup|map(select(.conclusion=="SUCCESS"))|length)|tostring) + "/" +
            ((.statusCheckRollup|length)|tostring) + "|" +
            ( [ .statusCheckRollup[] | (.name // .context // "?") + ":" + ((.conclusion // .status // "?")|ascii_downcase) ] | join("|") )
          end )
      '
    gh pr view "$num" --json body --jq '.body // "" | gsub("\r";"")' \
      | emit_compact 40 body "$(tee_file "pr-${num}-body.txt")"
  else
    glab mr view "$num" 2>/dev/null \
      | awk -v n="$num" '
        /^title:/   { sub(/^title: */,""); title=$0 }
        /^state:/   { sub(/^state: */,""); state=$0 }
        /^author:/  { sub(/^author: */,""); author=$0 }
        /^source:/  { sub(/^source: */,""); src=$0 }
        /^target:/  { sub(/^target: */,""); tgt=$0 }
        END {
          print "pr|" n "|" state "|" title
          print "branch|" src "→" tgt
          print "author|" author
        }'
  fi
}

cmd_merge() {
  local num="${1:-}"; [ -n "$num" ] || die "usage" "pr.sh merge <num> [--squash|--merge|--rebase]"
  shift
  local mode="squash"
  while [ $# -gt 0 ]; do
    case "$1" in
      --squash) mode="squash"; shift ;;
      --merge)  mode="merge"; shift ;;
      --rebase) mode="rebase"; shift ;;
      *) die "bad-arg" "$1" ;;
    esac
  done
  if [ "$CLI" = "gh" ]; then
    gh pr merge "$num" "--$mode" --delete-branch >/dev/null 2>&1 || die "merge-failed" "$num"
    local sha; sha="$(gh pr view "$num" --json mergeCommit --jq '.mergeCommit.oid // ""' | cut -c1-7)"
    echo "merged|$num|${sha:--}"
  else
    glab mr merge "$num" "--$mode" --remove-source-branch --yes >/dev/null 2>&1 || die "merge-failed" "$num"
    echo "merged|$num|-"
  fi
}

cmd_checks() {
  local num="${1:-}"; [ -n "$num" ] || die "usage" "pr.sh checks <num>"
  if [ "$CLI" = "gh" ]; then
    # Failure-focus: emit a pass/total summary, then ONLY the non-success
    # checks inline. The full check list is written to the tee file.
    local tf; tf="$(tee_file "pr-${num}-checks.txt")"
    gh pr view "$num" --json statusCheckRollup --jq \
      '.statusCheckRollup[]? | [(.name // .context // "?"), ((.conclusion // .status // "?")|ascii_downcase), (.detailsUrl // .targetUrl // "-")] | join("|")' \
      > "$tf"
    local total ok
    total="$(wc -l < "$tf" | tr -d ' ')"
    ok="$(awk -F'|' '$2=="success"' "$tf" | wc -l | tr -d ' ')"
    echo "checks|$ok/$total"
    awk -F'|' '$2!="success" && $2!="" {print "check|" $0}' "$tf"
    if [ "$ok" -lt "$total" ]; then echo "full|$tf"; fi
  else
    glab ci status --branch "$(glab mr view "$num" 2>/dev/null | awk '/^source:/{print $2}')" 2>/dev/null || true
  fi
}

cmd_diff() {
  local num="${1:-}"; [ -n "$num" ] || die "usage" "pr.sh diff <num>"
  if [ "$CLI" = "gh" ]; then
    gh pr diff "$num" | strip_ansi \
      | emit_compact 100 diff "$(tee_file "pr-${num}-diff.txt")"
  else
    glab mr diff "$num" | strip_ansi \
      | emit_compact 100 diff "$(tee_file "pr-${num}-diff.txt")"
  fi
}

case "$SUB" in
  create) cmd_create "$@" ;;
  edit)   cmd_edit "$@" ;;
  list)   cmd_list "$@" ;;
  view)   cmd_view "$@" ;;
  merge)  cmd_merge "$@" ;;
  checks) cmd_checks "$@" ;;
  diff)   cmd_diff "$@" ;;
  *) die "bad-sub" "$SUB" ;;
esac
