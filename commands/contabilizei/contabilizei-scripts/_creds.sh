#!/usr/bin/env bash
# Shared helpers for contabilizei scripts. Sourced, not executed.
# Data → stdout. Diagnostics → stderr. Pipe-delimited.

set -u

CONTABILIZEI_HOME="${CONTABILIZEI_HOME:-$HOME/finance/contabilizei}"
CONTABILIZEI_CONFIG="$CONTABILIZEI_HOME/.config"
CONTABILIZEI_EXTRACTED="$CONTABILIZEI_HOME/extracted"

die() {
  echo "err|$1|$2" >&2
  exit 1
}

ensure_home() {
  mkdir -p "$CONTABILIZEI_HOME" "$CONTABILIZEI_EXTRACTED"
  chmod 700 "$CONTABILIZEI_HOME"
}

has_config() {
  [ -f "$CONTABILIZEI_CONFIG" ] && grep -q '^EMAIL=' "$CONTABILIZEI_CONFIG"
}

load_config() {
  has_config || die "no-config" "email not configured — run setup first"
  # shellcheck disable=SC1090
  set -a; . "$CONTABILIZEI_CONFIG"; set +a
  : "${EMAIL:?missing EMAIL in .config}"
}

has_password() {
  local email="$1"
  security find-generic-password -a "$email" -s "contabilizei-login" -w >/dev/null 2>&1
}

read_keychain_password() {
  local email="$1"
  security find-generic-password -a "$email" -s "contabilizei-login" -w 2>/dev/null
}

save_keychain_password() {
  local email="$1" password="$2"
  security add-generic-password -a "$email" -s "contabilizei-login" -w "$password" -U \
    || die "keychain-error" "failed to save password to Keychain"
}
