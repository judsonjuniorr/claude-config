#!/usr/bin/env bash
# Install / verify the stack tools. Idempotent. headroom proxy/MCP wiring is
# handled separately by headroom-wrap.sh (this only installs the binary).
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

## --- headroom (install via uv tool: isolated, sidesteps PEP-668) ---
if have headroom; then
  emit ok headroom "$(headroom --version 2>/dev/null | head -1)"
elif have uv; then
  info headroom "uv tool install headroom-ai[all]"
  if uv tool install "headroom-ai[all]"; then emit ok headroom installed
  else
    info headroom "uv failed — falling back to pip --user --break-system-packages"
    python3 -m pip install --user --break-system-packages "headroom-ai[all]" \
      && emit ok headroom "installed (pip --user)" \
      || emit err headroom "install failed"
  fi
else
  emit err headroom "uv missing — run ensure-deps first"
fi
exit 0
