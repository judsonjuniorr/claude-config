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

# Strip ANSI/color escape codes from stdin.
strip_ansi() {
  sed $'s/\x1b\\[[0-9;]*m//g'
}

# Collapse consecutive identical lines into "<line> (xN)".
dedup_lines() {
  awk '
    NR==1 { prev=$0; c=1; next }
    $0==prev { c++; next }
    { if (c>1) print prev " (x" c ")"; else print prev; prev=$0; c=1 }
    END { if (NR>0) { if (c>1) print prev " (x" c ")"; else print prev } }
  '
}

# Group a flat list of paths (stdin) by directory:
#   dir/
#     base1
#     base2
group_by_dir() {
  sort | awk -F/ '
    { d = (NF>1) ? substr($0, 1, length($0)-length($NF)-1) : "."
      b = $NF
      if (d != last) { print d "/"; last = d }
      print "  " b }
  '
}

# Rough token estimate of stdin, RTK formula: (chars + 3) / 4.
estimate_tokens() {
  local chars
  chars="$(wc -c)"
  echo $(( (chars + 3) / 4 ))
}

# Ensure the tee dir exists and echo a deterministic file path for <name>.
# Re-runs overwrite the same file instead of accumulating orphans.
tee_file() {
  local dir="${TMPDIR:-/tmp}/github-ops-tee"
  mkdir -p "$dir"
  echo "$dir/$1"
}

# Core RTK tee pattern. Reads full content from stdin, dedups it, writes
# ALL of it to <tee_file>, then emits up to <limit> lines inline prefixed
# with "<label>|". If truncated, also emits the full-file pointer and a
# token-savings line so nothing is lost — the agent reads the file on demand.
#   emit_compact <limit> <label> <tee_file>
emit_compact() {
  local limit="$1" label="$2" tf="$3"
  dedup_lines > "$tf"
  local total comp_chars orig_chars orig comp pct
  total="$(wc -l < "$tf" | tr -d ' ')"
  sed -n "1,${limit}p" "$tf" | sed "s/^/$label|/"
  if [ "$total" -gt "$limit" ]; then
    echo "$label|... +$((total - limit)) more lines"
    echo "full|$tf"
    orig_chars="$(wc -c < "$tf")"
    comp_chars="$(sed -n "1,${limit}p" "$tf" | wc -c)"
    orig=$(( (orig_chars + 3) / 4 ))
    comp=$(( (comp_chars + 3) / 4 ))
    pct=0
    [ "$orig" -gt 0 ] && pct=$(( (orig - comp) * 100 / orig ))
    echo "saved|${orig}→${comp} tokens (~${pct}%)"
  fi
}

# Returns 0 if any staged path matches secret patterns.
has_secret_paths() {
  git diff --cached --name-only \
    | grep -Eq '(^|/)(\.env(\..+)?|.*\.(key|pem|p12|pfx)|.*_rsa|.*credentials.*\.json)$'
}
