#!/usr/bin/env bash
# First-run onboarding: opens Organizze API tokens page via Playwright MCP (caller),
# then reads email + token from stdin (one per line) and persists to ~/finance/organizze/.auth
# Usage:
#   echo -e "$EMAIL\n$TOKEN" | bash setup_auth.sh
# Or interactively if you have a TTY.

HERE="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=_common.sh
. "$HERE/_common.sh"

ensure_home

if [ -t 0 ]; then
  printf "Organizze email: " >&2
  read -r EMAIL
  printf "Organizze API token (https://app.organizze.com.br/configuracoes/api-keys): " >&2
  read -r TOKEN
else
  read -r EMAIL
  read -r TOKEN
fi

[ -n "${EMAIL:-}" ] || die "missing-email" "email required"
[ -n "${TOKEN:-}" ] || die "missing-token" "token required"

UA="claude-code-financeiro/1.0 ($EMAIL)"

umask 077
cat > "$ORGANIZZE_AUTH" <<EOF
# Organizze API credentials. chmod 600. Do not commit.
ORGANIZZE_EMAIL="$EMAIL"
ORGANIZZE_TOKEN="$TOKEN"
ORGANIZZE_USER_AGENT="$UA"
EOF
chmod 600 "$ORGANIZZE_AUTH"

# Validate
RESP="$(curl -sS -o /dev/null -w '%{http_code}' \
  -u "$EMAIL:$TOKEN" \
  -H "User-Agent: $UA" \
  -H "Accept: application/json" \
  "$ORGANIZZE_API/accounts")"

case "$RESP" in
  200) echo "ok|auth-saved|$ORGANIZZE_AUTH" ;;
  401) rm -f "$ORGANIZZE_AUTH"; die "bad-credentials" "401 from /accounts — token rejected" ;;
  400) rm -f "$ORGANIZZE_AUTH"; die "bad-user-agent" "400 from /accounts — User-Agent rejected" ;;
  *)   die "unexpected-status" "$RESP from /accounts" ;;
esac
