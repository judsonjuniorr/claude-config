#!/usr/bin/env bash
# Idempotent setup: create ~/finance/contabilizei/ dirs and install pdfplumber.
# Safe to run repeatedly; second run is a no-op.

HERE="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=_creds.sh
. "$HERE/_creds.sh"

ensure_home

if ! python3 -c "import pdfplumber" 2>/dev/null; then
  echo "info|installing-pdfplumber|pip install --user pdfplumber" >&2
  pip3 install --quiet --user --break-system-packages pdfplumber \
    || die "pdfplumber-install-failed" "pip3 install pdfplumber failed"
fi

echo "ok|setup-ready|$CONTABILIZEI_HOME"
