#!/usr/bin/env bash
# First-run onboarding: reads email + API token (+ web password) and persists
# credentials. API token → ~/finance/organizze/.auth; web password → macOS Keychain.
# Usage:
#   echo -e "$EMAIL\n$TOKEN\n$SENHA" | bash setup_auth.sh
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
  printf "Organizze web password (for scraping; stored in Keychain, not on disk): " >&2
  read -rs SENHA
  echo >&2
else
  read -r EMAIL
  read -r TOKEN
  read -r SENHA
fi

[ -n "${EMAIL:-}" ] || die "missing-email" "email required"
[ -n "${TOKEN:-}" ] || die "missing-token" "token required"
[ -n "${SENHA:-}" ] || die "missing-password" "web password required for scraping"

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
  200) ;;
  401) rm -f "$ORGANIZZE_AUTH"; die "bad-credentials" "401 from /accounts — token rejected" ;;
  400) rm -f "$ORGANIZZE_AUTH"; die "bad-user-agent" "400 from /accounts — User-Agent rejected" ;;
  *)   die "unexpected-status" "$RESP from /accounts" ;;
esac

# Store web password in Keychain + install playwright/chromium (idempotent)
printf '%s' "$SENHA" | bash "$HERE/setup_scrape.sh" >&2 \
  || die "scrape-setup-failed" "setup_scrape.sh failed"
unset SENHA

echo "ok|auth-saved|$ORGANIZZE_AUTH"
