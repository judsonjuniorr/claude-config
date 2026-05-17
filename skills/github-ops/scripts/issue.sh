#!/usr/bin/env bash
# Issue operations via gh/glab with pipe-delimited output.
# Subcommands: create | list | view | close | comment
set -eu
DIR="$(cd "$(dirname "$0")" && pwd)"
# shellcheck disable=SC1091
. "$DIR/_common.sh"

require_repo
CLI="$(pick_cli)"
SUB="${1:-}"
[ -n "$SUB" ] || die "usage" "issue.sh create|list|view|close|comment"
shift || true

cmd_create() {
  local title="" body="" body_file="" labels=""
  while [ $# -gt 0 ]; do
    case "$1" in
      --title) title="$2"; shift 2 ;;
      --body) body="$2"; shift 2 ;;
      --body-file) body_file="$2"; shift 2 ;;
      --label) labels="$2"; shift 2 ;;
      *) die "bad-arg" "$1" ;;
    esac
  done
  [ -n "$title" ] || die "usage" "--title required"
  if [ "$CLI" = "gh" ]; then
    local args=(--title "$title")
    if [ -n "$body_file" ]; then args+=(--body-file "$body_file")
    else args+=(--body "${body:-}"); fi
    [ -n "$labels" ] && args+=(--label "$labels")
    local url; url="$(gh issue create "${args[@]}")" || die "create-failed" "gh"
    local num; num="$(echo "$url" | grep -oE '[0-9]+$')"
    echo "issue|$num|$url"
  else
    local args=(--title "$title")
    if [ -n "$body_file" ]; then args+=(--description "$(cat "$body_file")")
    else args+=(--description "${body:-}"); fi
    [ -n "$labels" ] && args+=(--label "$labels")
    glab issue create "${args[@]}" >/tmp/.glab-out 2>&1 || { cat /tmp/.glab-out >&2; die "create-failed" "glab"; }
    local url; url="$(grep -oE 'https?://[^ ]+/issues/[0-9]+' /tmp/.glab-out | head -1)"
    local num; num="$(echo "$url" | grep -oE '[0-9]+$')"
    echo "issue|$num|$url"
  fi
}

cmd_list() {
  local state="open" label=""
  while [ $# -gt 0 ]; do
    case "$1" in
      --state) state="$2"; shift 2 ;;
      --label) label="$2"; shift 2 ;;
      *) die "bad-arg" "$1" ;;
    esac
  done
  if [ "$CLI" = "gh" ]; then
    local extra=()
    [ -n "$label" ] && extra+=(--label "$label")
    gh issue list --state "$state" "${extra[@]}" \
      --json number,state,labels,title \
      --jq '.[] | [
        .number,
        (.state|ascii_downcase),
        ((.labels|map(.name))|join(",") // "-"),
        .title
      ] | join("|")'
  else
    local extra=()
    [ -n "$label" ] && extra+=(--label "$label")
    glab issue list --state "$state" "${extra[@]}" 2>/dev/null \
      | awk 'NR>1 && NF { print $1 "|'"$state"'|-|" substr($0, index($0,$2)) }'
  fi
}

cmd_view() {
  local num="${1:-}"; [ -n "$num" ] || die "usage" "issue.sh view <num>"
  if [ "$CLI" = "gh" ]; then
    gh issue view "$num" --json number,state,title,author,labels,body --jq '
      "issue|" + (.number|tostring) + "|" + (.state|ascii_downcase) + "|" + .title,
      "author|" + (.author.login // "?"),
      "labels|" + ((.labels|map(.name))|join(",") // "-"),
      "body|" + (.body // "" | gsub("\r";""))
    ' | awk 'BEGIN{inbody=0; count=0}
            /^body\|/{inbody=1; print; next}
            inbody && count<40 {print; count++; next}
            inbody && count==40 {print "..."; inbody=0; next}
            !inbody {print}'
    # last 3 comments
    gh issue view "$num" --comments --json comments --jq '
      .comments[-3:][]? | "comment|" + (.author.login // "?") + "|" + (.body|gsub("\r";"")|gsub("\n";" ")|.[0:160])
    '
  else
    glab issue view "$num" 2>/dev/null \
      | awk -v n="$num" '
        /^title:/  { sub(/^title: */,""); print "issue|" n "|-|" $0 }
        /^state:/  { sub(/^state: */,""); print "state|" $0 }
        /^author:/ { sub(/^author: */,""); print "author|" $0 }
        /^labels:/ { sub(/^labels: */,""); print "labels|" $0 }
      '
  fi
}

cmd_close() {
  local num="${1:-}"; [ -n "$num" ] || die "usage" "issue.sh close <num>"
  if [ "$CLI" = "gh" ]; then
    gh issue close "$num" >/dev/null 2>&1 || die "close-failed" "$num"
  else
    glab issue close "$num" >/dev/null 2>&1 || die "close-failed" "$num"
  fi
  echo "closed|$num"
}

cmd_comment() {
  local num="${1:-}"; [ -n "$num" ] || die "usage" "issue.sh comment <num> --body ..."
  shift
  local body="" body_file=""
  while [ $# -gt 0 ]; do
    case "$1" in
      --body) body="$2"; shift 2 ;;
      --body-file) body_file="$2"; shift 2 ;;
      *) die "bad-arg" "$1" ;;
    esac
  done
  if [ "$CLI" = "gh" ]; then
    if [ -n "$body_file" ]; then gh issue comment "$num" --body-file "$body_file" >/dev/null
    else gh issue comment "$num" --body "$body" >/dev/null; fi
  else
    if [ -n "$body_file" ]; then glab issue note "$num" --message "$(cat "$body_file")" >/dev/null
    else glab issue note "$num" --message "$body" >/dev/null; fi
  fi
  echo "commented|$num"
}

case "$SUB" in
  create)  cmd_create "$@" ;;
  list)    cmd_list "$@" ;;
  view)    cmd_view "$@" ;;
  close)   cmd_close "$@" ;;
  comment) cmd_comment "$@" ;;
  *) die "bad-sub" "$SUB" ;;
esac
