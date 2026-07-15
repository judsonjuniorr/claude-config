#!/usr/bin/env bash
# Install / verify the stack tools. Idempotent.
set -u
HERE="$(cd "$(dirname "$0")" && pwd)"
. "${HERE}/_common.sh"

## --- gstack (git clone + ./setup; needs bun) ---
if [ -d "${GSTACK_DIR}/.git" ]; then
  # Already installed — verify only; updates are handled by /gstack-upgrade (keeps setup idempotent/cheap).
  emit ok gstack "present ${GSTACK_DIR} (update via /gstack-upgrade)"
else
  if ! have bun; then emit err gstack "bun missing — run ensure-deps first"; else
    info gstack "cloning garrytan/gstack"
    if git clone --single-branch --depth 1 https://github.com/garrytan/gstack.git "$GSTACK_DIR" \
       && ( cd "$GSTACK_DIR" && ./setup ); then
      emit ok gstack "installed ${GSTACK_DIR}"
    else
      emit err gstack "clone/setup failed"
    fi
  fi
fi

## --- rtk (keep; install via brew only if absent) ---
if have rtk; then emit ok rtk "$(rtk --version 2>/dev/null | head -1)"
elif have brew; then
  info rtk "brew install rtk"
  brew install rtk && emit ok rtk installed || emit err rtk "brew install rtk failed"
else emit err rtk "missing and no brew"; fi

## --- graphify (keep; verify only) ---
if have graphify; then emit ok graphify "$(graphify --version 2>/dev/null | head -1)"
else emit err graphify "missing — install with: uv tool install graphifyy"; fi

## --- organizze CLI (herow-finance's Organizze read path; brew cask, curl fallback) ---
if have organizze; then emit ok organizze "$(organizze --version 2>/dev/null | head -1)"
elif have brew; then
  info organizze "brew install --cask organizze/tap/organizze"
  if brew install --cask organizze/tap/organizze; then emit ok organizze installed
  else
    info organizze "brew cask failed — falling back to curl installer"
    curl -fsSL https://raw.githubusercontent.com/organizze/agent-tools/main/scripts/install.sh | bash \
      && emit ok organizze "installed (curl)" \
      || emit err organizze "install failed"
  fi
else
  curl -fsSL https://raw.githubusercontent.com/organizze/agent-tools/main/scripts/install.sh | bash \
    && emit ok organizze "installed (curl)" \
    || emit err organizze "missing and no brew"
fi
exit 0
