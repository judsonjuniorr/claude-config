#!/usr/bin/env bash
# Ensure OS dependencies for the stack. Idempotent: present deps are no-ops.
# macOS-first (brew). Installs only what's missing.
set -u
HERE="$(cd "$(dirname "$0")" && pwd)"
. "${HERE}/_common.sh"

# Homebrew is the base package manager on macOS — bootstrap it first if missing.
if ! have brew; then
  info "install-brew" "Homebrew missing — installing"
  /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)" \
    || { emit err brew-install "Homebrew install failed — install manually then re-run"; exit 1; }
  # make brew available this session (Apple Silicon path)
  [ -x /opt/homebrew/bin/brew ] && eval "$(/opt/homebrew/bin/brew shellenv)"
fi

brew_pkg() {  # brew_pkg <cmd> <formula>
  local cmd="$1" formula="$2"
  if have "$cmd"; then emit ok "dep-${cmd}" "present"; return 0; fi
  info "install-${cmd}" "brew install ${formula}"
  if brew install "$formula"; then emit ok "dep-${cmd}" "installed"
  else emit err "dep-${cmd}" "brew install ${formula} failed"; return 1; fi
}

brew_pkg git    git
brew_pkg python3 python    # python formula provides python3
brew_pkg node   node        # provides node + npm
brew_pkg bun    bun

# uv: official installer (not always in brew), used by graphify/headroom installs
if have uv; then emit ok dep-uv present
else
  info install-uv "curl -LsSf https://astral.sh/uv/install.sh | sh"
  curl -LsSf https://astral.sh/uv/install.sh | sh \
    && emit ok dep-uv installed \
    || emit err dep-uv "uv install failed"
fi

# python >= 3.10 guard (headroom requirement)
if have python3; then
  if python3 -c 'import sys; sys.exit(0 if sys.version_info >= (3,10) else 1)' 2>/dev/null; then
    emit ok python-version "$(python3 -c 'import sys;print("%d.%d"%sys.version_info[:2])')"
  else
    emit err python-version "python3 < 3.10 — upgrade (brew upgrade python)"
  fi
fi
exit 0
