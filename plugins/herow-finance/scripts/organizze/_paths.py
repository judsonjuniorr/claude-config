"""Path constants for Organizze provider, with legacy migration.

All Organizze data now lives under ~/finance/organizze/. The shared
~/finance/{memory,plans}.md are provider-agnostic and live one level up.

This module is the single source of truth for organizze-scripts/*.py paths.
It also re-exports migrate_legacy() from the shared scripts/_storage module,
so any organizze script's first run auto-migrates the pre-refactor layout.
"""

from __future__ import annotations

import os
import pathlib
import sys

# Make shared scripts/_storage.py importable
_SHARED = pathlib.Path(__file__).resolve().parent.parent / "scripts"
if str(_SHARED) not in sys.path:
    sys.path.insert(0, str(_SHARED))

from _storage import BASE as FINANCE_BASE, migrate_legacy  # noqa: E402

# Allow override via env for tests, default to ~/finance/organizze/
HOME = pathlib.Path(os.environ.get("ORGANIZZE_HOME", str(FINANCE_BASE / "organizze")))
AUTH = HOME / ".auth"
CONFIG = HOME / ".config"
BALANCES = HOME / "balances.json"
SNAPSHOTS = HOME / "snapshots"
REPORTS = HOME / "reports"
BUDGET_SUGGESTIONS = HOME / "budget-suggestions"
CACHE = HOME / "cache"


def chromium_executable_path() -> str | None:
    """Locate a Chromium already installed by the Claude Code MCP playwright.

    Lets us reuse the browser in ~/Library/Caches/ms-playwright/ instead of
    downloading our own. Override with ORGANIZZE_CHROMIUM_PATH. Returns None
    when nothing is found, so callers fall back to Playwright's own resolution.
    """
    override = os.environ.get("ORGANIZZE_CHROMIUM_PATH")
    if override:
        return override
    cache = pathlib.Path.home() / "Library/Caches/ms-playwright"
    if not cache.is_dir():
        return None
    candidates = []
    for d in cache.glob(
        "chromium-*/chrome-mac-arm64/Google Chrome for Testing.app/Contents/MacOS/Google Chrome for Testing"
    ):
        try:
            rev = int(d.parts[-6].split("-")[-1])  # chromium-<rev>
        except (ValueError, IndexError):
            rev = 0
        candidates.append((rev, str(d)))
    if not candidates:
        return None
    return max(candidates)[1]


__all__ = [
    "FINANCE_BASE",
    "HOME",
    "AUTH",
    "CONFIG",
    "BALANCES",
    "SNAPSHOTS",
    "REPORTS",
    "BUDGET_SUGGESTIONS",
    "CACHE",
    "chromium_executable_path",
    "migrate_legacy",
]
