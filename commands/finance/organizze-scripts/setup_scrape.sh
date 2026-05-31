#!/usr/bin/env bash
# Idempotent scraping setup: ensure playwright+chromium installed and the web
# password is in the macOS Keychain. Reads email from .auth. Password is read
# from stdin (optional — skip if already in Keychain). Safe to run repeatedly.
# Usage:
#   echo "$SENHA" | bash setup_scrape.sh   # set/update password + ensure playwright
#   bash setup_scrape.sh </dev/null        # ensure playwright; require existing password

HERE="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=_common.sh
. "$HERE/_common.sh"

ensure_home
load_auth  # populates ORGANIZZE_EMAIL

# Optional password from stdin (non-TTY only — never echo a prompt here)
SENHA=""
if [ ! -t 0 ]; then
  IFS= read -r SENHA || true
fi

if [ -n "$SENHA" ]; then
  security add-generic-password -a "$ORGANIZZE_EMAIL" -s "organizze-login" -w "$SENHA" -U \
    || die "keychain-error" "failed to save password to Keychain"
  unset SENHA
fi

# Fail fast before the slow playwright install if no password is available yet
has_web_password "$ORGANIZZE_EMAIL" || die "no-web-password" "web password not in Keychain — pipe it via stdin"

# Ensure playwright is importable (install to user site; Homebrew Python is
# externally managed — PEP 668 — so --break-system-packages is required)
if ! python3 -c "import playwright" 2>/dev/null; then
  echo "info|installing-playwright|pip install --user playwright" >&2
  pip3 install --quiet --user --break-system-packages playwright \
    || die "playwright-install-failed" "pip3 install playwright failed"
fi
if ! python3 -c "from playwright.sync_api import sync_playwright" 2>/dev/null; then
  die "playwright-missing" "playwright import failed after install"
fi

# Reuse the Chromium already installed by the Claude Code MCP playwright
# (~/Library/Caches/ms-playwright) instead of downloading our own.
python3 -c "
import sys, pathlib
sys.path.insert(0, '$HERE')
from _paths import chromium_executable_path
from playwright.sync_api import sync_playwright
exe = chromium_executable_path()
if not exe or not pathlib.Path(exe).exists():
    sys.exit('no-chromium')
with sync_playwright() as p:
    p.chromium.launch(headless=True, executable_path=exe).close()
" 2>/dev/null || die "chromium-missing" "no reusable Chromium in ms-playwright cache (run the MCP playwright once, or set ORGANIZZE_CHROMIUM_PATH)"

echo "ok|scrape-ready|$ORGANIZZE_EMAIL"
