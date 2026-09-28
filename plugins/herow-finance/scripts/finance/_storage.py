"""Finance storage paths under HEROW_HOME/finance, plus the one-shot ~/finance migration.

When drained, ~/finance becomes a symlink to BASE so outside skills that hardcode it keep working."""

from __future__ import annotations

import os
import pathlib
import shutil
import sys

HEROW_HOME = pathlib.Path(
    os.environ.get("HEROW_HOME") or pathlib.Path.home() / ".herow"
)
HOME = pathlib.Path.home()
BASE = HEROW_HOME / "finance"
MEM = BASE / "memory.md"
PLANS = BASE / "plans.md"
PROFILE = BASE / "profile.md"
LOGS = BASE / "logs"
CONTABILIZEI = BASE / "contabilizei"

# Provider-specific files migrated from the old finance-organizze/ layout,
# relative to legacy_home/finance/<provider>/.
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

# Top-level files migrated from finance-organizze/ to legacy_home/finance/.
_GLOBAL_MOVES = ["memory.md", "plans.md", "profile.md"]


def _is_effectively_empty(d: pathlib.Path) -> bool:
    """True once a stray .DS_Store (deleted here) is the only remaining entry."""
    ds_store = d / ".DS_Store"
    if ds_store.exists():
        try:
            ds_store.unlink()
        except OSError:
            pass
    return not any(d.iterdir())


def _rmdir_if_empty(d: pathlib.Path) -> None:
    try:
        if d.is_dir() and _is_effectively_empty(d):
            d.rmdir()
    except OSError:
        pass


def _merge_move(src: pathlib.Path, dst: pathlib.Path, conflicts: list[str]) -> None:
    """Move src into dst child by child; an existing target is never overwritten."""
    if not dst.exists():
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(src), str(dst))
        print(f"info|migrated|{src}|{dst}", file=sys.stderr)
        return
    if src.is_dir() and dst.is_dir():
        for child in list(src.iterdir()):
            _merge_move(child, dst / child.name, conflicts)
        _rmdir_if_empty(src)
        return
    conflicts.append(str(dst))
    print(f"warn|migrate-conflict|{src}|{dst}", file=sys.stderr)


def migrate_legacy(legacy_home: pathlib.Path, base: pathlib.Path) -> None:
    """Idempotent: once legacy_home/finance is the symlink left behind, it's a no-op."""
    legacy_finance = legacy_home / "finance"
    legacy_organizze = legacy_home / "finance-organizze"

    if legacy_finance.is_symlink():
        return  # already migrated

    had_finance = legacy_finance.exists()
    had_organizze = legacy_organizze.exists()
    if not had_finance and not had_organizze:
        return  # nothing to migrate

    conflicts: list[str] = []

    if had_organizze:
        for name in _GLOBAL_MOVES:
            src = legacy_organizze / name
            if src.exists():
                _merge_move(src, legacy_finance / name, conflicts)
        for provider, names in _PROVIDER_MOVES.items():
            for name in names:
                src = legacy_organizze / name
                if src.exists():
                    _merge_move(src, legacy_finance / provider / name, conflicts)
        _rmdir_if_empty(legacy_organizze)

    if legacy_finance.exists():
        _merge_move(legacy_finance, base, conflicts)

    base.mkdir(parents=True, exist_ok=True)
    for d in (base.parent, base):
        try:
            d.chmod(0o700)
        except OSError:
            pass

    if legacy_finance.exists():
        print(
            f"warn|migrate-conflicts-remain|{legacy_finance}|{len(conflicts)}",
            file=sys.stderr,
        )
    elif had_finance or had_organizze:
        try:
            legacy_finance.symlink_to(base)
            print(f"info|migrated|{legacy_finance}|symlink->{base}", file=sys.stderr)
        except OSError as e:
            print(f"warn|symlink-failed|{legacy_finance}|{e}", file=sys.stderr)


def auto_migrate() -> None:
    """Any path override means a test or custom setup — never touch the real ~/finance then."""
    if any(
        os.environ.get(var)
        for var in ("HEROW_HOME", "ORGANIZZE_HOME", "CONTABILIZEI_HOME")
    ):
        return
    migrate_legacy(HOME, BASE)


if __name__ == "__main__":
    auto_migrate()
