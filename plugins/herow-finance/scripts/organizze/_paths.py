"""Path constants for Organizze provider, with legacy migration.

All Organizze data now lives under HEROW_HOME/finance/organizze/. The shared
BASE/{memory,plans}.md are provider-agnostic and live one level up.

This module is the single source of truth for organizze-scripts/*.py paths.
It also re-exports auto_migrate() from the shared scripts/_storage module,
so any organizze script's first run auto-migrates the pre-refactor layout.
"""

from __future__ import annotations

import os
import pathlib
import sys

# Make shared scripts/finance/_storage.py importable
_SHARED = pathlib.Path(__file__).resolve().parent.parent / "finance"
if str(_SHARED) not in sys.path:
    sys.path.insert(0, str(_SHARED))

from _storage import (  # noqa: E402
    BASE as FINANCE_BASE,
    LOGS as FINANCE_LOGS,
    auto_migrate,
    migrate_legacy,
)

# Allow override via env for tests, default to HEROW_HOME/finance/organizze/
HOME = pathlib.Path(os.environ.get("ORGANIZZE_HOME", str(FINANCE_BASE / "organizze")))
AUTH = HOME / ".auth"
CONFIG = HOME / ".config"
BALANCES = HOME / "balances.json"
SNAPSHOTS = HOME / "snapshots"
REPORTS = HOME / "reports"
BUDGET_SUGGESTIONS = HOME / "budget-suggestions"
CACHE = HOME / "cache"
RESEARCH = HOME / "research"
METRICS = HOME / "metrics.json"
ID_MAP = HOME / ".id-map.json"
LOGS = FINANCE_LOGS


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
    "RESEARCH",
    "METRICS",
    "ID_MAP",
    "LOGS",
    "chromium_executable_path",
    "auto_migrate",
    "migrate_legacy",
]
