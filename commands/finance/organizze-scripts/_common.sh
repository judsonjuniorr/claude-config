#!/usr/bin/env bash
# Shared helpers for organizze skill scripts. Sourced, not executed.
# Data → stdout. Diagnostics → stderr. Pipe-delimited.

set -u

ORGANIZZE_HOME="${ORGANIZZE_HOME:-$HOME/finance-organizze}"
ORGANIZZE_AUTH="$ORGANIZZE_HOME/.auth"
ORGANIZZE_API="https://api.organizze.com.br/rest/v2"

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
