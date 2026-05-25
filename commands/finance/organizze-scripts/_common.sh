#!/usr/bin/env bash
# Shared helpers for organizze skill scripts. Sourced, not executed.
# Data → stdout. Diagnostics → stderr. Pipe-delimited.

set -u

ORGANIZZE_HOME="${ORGANIZZE_HOME:-$HOME/finance/organizze}"
ORGANIZZE_AUTH="$ORGANIZZE_HOME/.auth"
ORGANIZZE_API="https://api.organizze.com.br/rest/v2"

# Legacy migration: pre-refactor layout lived in ~/finance-organizze/. If any
# python script ran first it already handled the move. This guard catches the
# case where setup_auth.sh is the very first thing the user runs.
_LEGACY_ORG="$HOME/finance-organizze"
if [ -d "$_LEGACY_ORG" ]; then
  mkdir -p "$HOME/finance"
  for item in .auth .config balances.json snapshots reports budget-suggestions cache; do
    if [ -e "$_LEGACY_ORG/$item" ] && [ ! -e "$ORGANIZZE_HOME/$item" ]; then
      mkdir -p "$ORGANIZZE_HOME"
      mv "$_LEGACY_ORG/$item" "$ORGANIZZE_HOME/$item"
      echo "info|migrated|$_LEGACY_ORG/$item|$ORGANIZZE_HOME/$item" >&2
    fi
  done
  for item in memory.md plans.md; do
    if [ -e "$_LEGACY_ORG/$item" ] && [ ! -e "$HOME/finance/$item" ]; then
      mv "$_LEGACY_ORG/$item" "$HOME/finance/$item"
      echo "info|migrated|$_LEGACY_ORG/$item|$HOME/finance/$item" >&2
    fi
  done
  rmdir "$_LEGACY_ORG" 2>/dev/null || true
fi

die() {
  echo "err|$1|$2" >&2
  exit 1
}

ensure_home() {
  mkdir -p "$ORGANIZZE_HOME/snapshots" "$ORGANIZZE_HOME/reports" "$ORGANIZZE_HOME/cache"
  chmod 700 "$ORGANIZZE_HOME"
}

has_auth() {
  [ -f "$ORGANIZZE_AUTH" ] && grep -q '^ORGANIZZE_TOKEN=' "$ORGANIZZE_AUTH" && grep -q '^ORGANIZZE_EMAIL=' "$ORGANIZZE_AUTH"
}

load_auth() {
  has_auth || die "no-auth" "run setup_auth.sh first"
  # shellcheck disable=SC1090
  set -a; . "$ORGANIZZE_AUTH"; set +a
  : "${ORGANIZZE_EMAIL:?missing}"
  : "${ORGANIZZE_TOKEN:?missing}"
  : "${ORGANIZZE_USER_AGENT:?missing}"
}

curl_organizze() {
  # Usage: curl_organizze <path-with-leading-slash> [extra curl args...]
  local path="$1"; shift || true
  curl -sS -u "$ORGANIZZE_EMAIL:$ORGANIZZE_TOKEN" \
    -H "User-Agent: $ORGANIZZE_USER_AGENT" \
    -H "Accept: application/json" \
    "$@" \
    "$ORGANIZZE_API$path"
}
