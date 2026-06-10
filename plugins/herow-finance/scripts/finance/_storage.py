"""Shared storage paths + legacy migration for finance commands.

Provider-agnostic data lives in ~/finance/. Provider-specific data lives in
~/finance/<provider>/. This module owns:

- BASE     : ~/finance/
- MEM      : ~/finance/memory.md
- PLANS    : ~/finance/plans.md
- PROFILE  : ~/finance/profile.md
- migrate_legacy(): one-shot move of pre-refactor layout
    ~/finance-organizze/memory.md   -> ~/finance/memory.md
    ~/finance-organizze/plans.md    -> ~/finance/plans.md
    ~/finance-organizze/{.auth,.config,balances.json,snapshots/,reports/,
                         budget-suggestions/,cache/} -> ~/finance/organizze/

Idempotent: only moves files that exist at the legacy path AND do not yet
exist at the new path. Logs each move to stderr as `info|migrated|<old>|<new>`.
"""
from __future__ import annotations

import pathlib
import shutil
import sys

HOME = pathlib.Path.home()
BASE = HOME / "finance"
MEM = BASE / "memory.md"
PLANS = BASE / "plans.md"
PROFILE = BASE / "profile.md"
LEGACY = HOME / "finance-organizze"

# Provider-specific files moved into BASE/<provider>/
_PROVIDER_MOVES = {
    "organizze": [
        ".auth",
        ".config",
        "balances.json",
        "snapshots",
        "reports",
        "budget-suggestions",
        "cache",
    ],
}

# Top-level files migrated to BASE (global)
_GLOBAL_MOVES = ["memory.md", "plans.md", "profile.md"]


def _move(src: pathlib.Path, dst: pathlib.Path) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(src), str(dst))
    print(f"info|migrated|{src}|{dst}", file=sys.stderr)


def migrate_legacy() -> None:
    """Move pre-refactor files to the new layout. Safe to call repeatedly."""
    if not LEGACY.exists():
        return
    BASE.mkdir(parents=True, exist_ok=True)
    try:
        BASE.chmod(0o700)
    except OSError:
        pass

    for name in _GLOBAL_MOVES:
        src = LEGACY / name
        dst = BASE / name
        if src.exists() and not dst.exists():
            _move(src, dst)

    for provider, names in _PROVIDER_MOVES.items():
        pbase = BASE / provider
        for name in names:
            src = LEGACY / name
            dst = pbase / name
            if src.exists() and not dst.exists():
                _move(src, dst)

    # Remove legacy dir if empty
    try:
        if not any(LEGACY.iterdir()):
            LEGACY.rmdir()
    except OSError:
        pass
