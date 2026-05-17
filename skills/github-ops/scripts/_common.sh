#!/usr/bin/env bash
# Shared helpers for github-ops scripts. Sourced, not executed.
# Output convention: pipe-delimited, 1 line per record, no colors.
# Diagnostics → stderr. Data → stdout.

set -u

die() {
  echo "err|$1|$2" >&2
  exit 1
}

require_repo() {
  git rev-parse --is-inside-work-tree >/dev/null 2>&1 \
    || die "not-a-repo" "run inside a git repo"
}

remote_url() {
  git remote get-url origin 2>/dev/null || echo ""
}

detect_platform() {
  local url
  url="$(remote_url)"
  case "$url" in
    *github.com*) echo "github" ;;
    *gitlab.com*|*gitlab.*) echo "gitlab" ;;
    *) echo "unknown" ;;
  esac
}

pick_cli() {
  local platform
  platform="$(detect_platform)"
  case "$platform" in
    github)
      command -v gh >/dev/null 2>&1 || die "missing-cli" "gh"
      echo "gh" ;;
    gitlab)
      command -v glab >/dev/null 2>&1 || die "missing-cli" "glab"
      echo "glab" ;;
    *) die "unknown-platform" "$(remote_url)" ;;
  esac
}

current_branch() {
  git rev-parse --abbrev-ref HEAD
}

default_branch() {
  local cli
  cli="$(pick_cli)"
  if [ "$cli" = "gh" ]; then
    gh repo view --json defaultBranchRef --jq .defaultBranchRef.name 2>/dev/null \
      || echo "main"
  else
    glab repo view 2>/dev/null | awk -F': *' '/Default branch/ {print $2; exit}' \
      || echo "main"
  fi
}

repo_slug() {
  local url
  url="$(remote_url)"
  echo "$url" | sed -E 's#^(https?://|git@)([^/:]+)[:/]##; s/\.git$//'
}

# Truncate stdin to N lines, append `...` if cut.
truncate_lines() {
  local n="${1:-40}"
  awk -v n="$n" 'NR<=n {print} END {if (NR>n) print "..."}'
}

# Returns 0 if any staged path matches secret patterns.
has_secret_paths() {
  git diff --cached --name-only \
    | grep -Eq '(^|/)(\.env(\..+)?|.*\.(key|pem|p12|pfx)|.*_rsa|.*credentials.*\.json)$'
}
