#!/usr/bin/env bash
# Repo info, releases, CI runs, workflow dispatch.
# Subcommands: info | releases | runs | workflow-run
set -eu
DIR="$(cd "$(dirname "$0")" && pwd)"
# shellcheck disable=SC1091
. "$DIR/_common.sh"

require_repo
CLI="$(pick_cli)"
SUB="${1:-}"
[ -n "$SUB" ] || die "usage" "repo.sh info|releases|runs|workflow-run"
shift || true

cmd_info() {
  if [ "$CLI" = "gh" ]; then
    gh repo view --json nameWithOwner,defaultBranchRef,visibility,mergeCommitAllowed,squashMergeAllowed,rebaseMergeAllowed \
      --jq '
        "name|" + .nameWithOwner,
        "default-branch|" + .defaultBranchRef.name,
        "visibility|" + (.visibility|ascii_downcase),
        "merge-allowed|" +
          ( (if .mergeCommitAllowed then "merge," else "" end)
          + (if .squashMergeAllowed then "squash," else "" end)
          + (if .rebaseMergeAllowed then "rebase" else "" end) )
      '
  else
    local slug; slug="$(repo_slug)"
    local def;  def="$(default_branch)"
    echo "name|$slug"
    echo "default-branch|$def"
    glab repo view 2>/dev/null \
      | awk -F': *' '/Visibility/ {print "visibility|" tolower($2)}'
  fi
}

cmd_releases() {
  local limit=10
  while [ $# -gt 0 ]; do
    case "$1" in
      --limit) limit="$2"; shift 2 ;;
      *) die "bad-arg" "$1" ;;
    esac
  done
  if [ "$CLI" = "gh" ]; then
    gh release list --limit "$limit" \
      --json tagName,name,publishedAt,isDraft,isPrerelease \
      --jq '.[] | [
        .tagName,
        (.name // .tagName),
        (.publishedAt // "-"),
        (if .isDraft then "draft" elif .isPrerelease then "prerelease" else "stable" end)
      ] | join("|")'
  else
    glab release list 2>/dev/null \
      | awk 'NR>1 && NF { print $1 "|" $2 "|" $3 "|stable" }' \
      | head -n "$limit"
  fi
}

cmd_runs() {
  local limit=10 workflow="" logid=""
  while [ $# -gt 0 ]; do
    case "$1" in
      --limit) limit="$2"; shift 2 ;;
      --workflow) workflow="$2"; shift 2 ;;
      --log) logid="$2"; shift 2 ;;
      *) die "bad-arg" "$1" ;;
    esac
  done

  # Failure-focus: dump only the failed steps of one run, full log to tee.
  if [ -n "$logid" ]; then
    if [ "$CLI" = "gh" ]; then
      gh run view "$logid" --log-failed 2>/dev/null | strip_ansi \
        | emit_compact 80 log "$(tee_file "run-${logid}-failed.txt")"
    else
      glab ci trace "$logid" 2>/dev/null | strip_ansi \
        | emit_compact 80 log "$(tee_file "run-${logid}-failed.txt")"
    fi
    return
  fi

  if [ "$CLI" = "gh" ]; then
    local extra=()
    [ -n "$workflow" ] && extra+=(--workflow "$workflow")
    # Failures first, then everything else (each group in original order).
    gh run list --limit "$limit" "${extra[@]}" \
      --json databaseId,status,conclusion,headBranch,workflowName \
      --jq '.[] | [
        (.databaseId|tostring),
        (.status|ascii_downcase),
        ((.conclusion // "-")|ascii_downcase),
        .headBranch,
        .workflowName
      ] | join("|")' \
      | awk -F'|' '$3=="failure"{print;next}{rest[n++]=$0} END{for(i=0;i<n;i++)print rest[i]}'
  else
    glab ci list 2>/dev/null \
      | awk 'NR>1 && NF { print $1 "|" tolower($2) "|-|" $3 "|-" }' \
      | head -n "$limit"
  fi
}

cmd_workflow_run() {
  local name="${1:-}"; [ -n "$name" ] || die "usage" "repo.sh workflow-run <name> [--ref branch]"
  shift
  local ref=""
  while [ $# -gt 0 ]; do
    case "$1" in
      --ref) ref="$2"; shift 2 ;;
      *) die "bad-arg" "$1" ;;
    esac
  done
  if [ "$CLI" = "gh" ]; then
    local args=("$name")
    [ -n "$ref" ] && args+=(--ref "$ref")
    gh workflow run "${args[@]}" >/dev/null 2>&1 || die "dispatch-failed" "$name"
    sleep 2
    gh run list --workflow "$name" --limit 1 --json databaseId,url \
      --jq '.[0] | "run|" + (.databaseId|tostring) + "|" + .url'
  else
    glab ci run --workflow "$name" ${ref:+--branch "$ref"} >/dev/null 2>&1 || die "dispatch-failed" "$name"
    echo "run|-|-"
  fi
}

case "$SUB" in
  info)         cmd_info "$@" ;;
  releases)     cmd_releases "$@" ;;
  runs)         cmd_runs "$@" ;;
  workflow-run) cmd_workflow_run "$@" ;;
  *) die "bad-sub" "$SUB" ;;
esac
