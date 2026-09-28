"""Tests for _storage.py — migrate_legacy() recursive merge + auto_migrate() guard.

Every test drives migrate_legacy() directly against tmp_path fixtures — the real
~/finance is never touched (see the package-level conftest.py, which also keeps
auto_migrate() a no-op for this whole suite via HEROW_HOME/ORGANIZZE_HOME)."""

from __future__ import annotations

import pathlib
import sys
from unittest.mock import MagicMock

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
import _storage  # noqa: E402


def _write(path: pathlib.Path, text: str = "x") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)


def test_full_move_including_unknown_files(tmp_path: pathlib.Path) -> None:
    legacy_home = tmp_path / "home"
    base = tmp_path / "herow" / "finance"
    _write(legacy_home / "finance" / "memory.md", "mem")
    _write(legacy_home / "finance" / "ynab-map.md", "ynab")
    _write(legacy_home / "finance" / "ynab-sync-state.json", "{}")
    _write(legacy_home / "finance" / "conciliacao" / "map.md", "conc")

    _storage.migrate_legacy(legacy_home, base)

    assert (base / "memory.md").read_text() == "mem"
    assert (base / "ynab-map.md").read_text() == "ynab"
    assert (base / "ynab-sync-state.json").read_text() == "{}"
    assert (base / "conciliacao" / "map.md").read_text() == "conc"
    assert (legacy_home / "finance").is_symlink()
    assert (legacy_home / "finance").resolve() == base.resolve()
    assert base.stat().st_mode & 0o777 == 0o700


def test_merge_when_target_pre_exists_children_still_moved(
    tmp_path: pathlib.Path,
) -> None:
    legacy_home = tmp_path / "home"
    base = tmp_path / "herow" / "finance"
    _write(legacy_home / "finance" / "organizze" / "snapshots" / "a.json", "a")
    _write(base / "organizze" / "reports" / "r.md", "r")  # pre-existing, unrelated

    _storage.migrate_legacy(legacy_home, base)

    assert (base / "organizze" / "snapshots" / "a.json").read_text() == "a"
    assert (base / "organizze" / "reports" / "r.md").read_text() == "r"  # untouched
    assert (legacy_home / "finance").is_symlink()


def test_conflict_keeps_target_and_skips_symlink(
    tmp_path: pathlib.Path, capsys
) -> None:
    legacy_home = tmp_path / "home"
    base = tmp_path / "herow" / "finance"
    _write(legacy_home / "finance" / "memory.md", "legacy")
    _write(base / "memory.md", "existing")

    _storage.migrate_legacy(legacy_home, base)

    assert (
        base / "memory.md"
    ).read_text() == "existing"  # target wins, never overwritten
    assert (
        legacy_home / "finance" / "memory.md"
    ).read_text() == "legacy"  # left in place
    assert not (
        legacy_home / "finance"
    ).is_symlink()  # unresolved conflict -> no symlink
    err = capsys.readouterr().err
    assert "warn|migrate-conflict|" in err
    assert "warn|migrate-conflicts-remain|" in err


def test_idempotent_second_call_is_noop(tmp_path: pathlib.Path) -> None:
    legacy_home = tmp_path / "home"
    base = tmp_path / "herow" / "finance"
    _write(legacy_home / "finance" / "memory.md", "mem")

    _storage.migrate_legacy(legacy_home, base)
    resolved = (legacy_home / "finance").resolve()

    _storage.migrate_legacy(legacy_home, base)  # already a symlink -> early return

    assert (legacy_home / "finance").resolve() == resolved
    assert (base / "memory.md").read_text() == "mem"


def test_already_symlink_skipped_entirely(tmp_path: pathlib.Path) -> None:
    legacy_home = tmp_path / "home"
    legacy_home.mkdir()
    base = tmp_path / "herow" / "finance"
    other_target = tmp_path / "elsewhere"
    other_target.mkdir()
    (legacy_home / "finance").symlink_to(other_target)

    _storage.migrate_legacy(legacy_home, base)

    assert (legacy_home / "finance").resolve() == other_target.resolve()
    assert not base.exists()  # never even created


def test_finance_organizze_chain(tmp_path: pathlib.Path) -> None:
    legacy_home = tmp_path / "home"
    base = tmp_path / "herow" / "finance"
    _write(legacy_home / "finance-organizze" / "memory.md", "mem")
    _write(legacy_home / "finance-organizze" / "plans.md", "plans")
    _write(legacy_home / "finance-organizze" / ".auth", "auth")
    _write(legacy_home / "finance-organizze" / "snapshots" / "s.json", "s")

    _storage.migrate_legacy(legacy_home, base)

    assert (base / "memory.md").read_text() == "mem"
    assert (base / "plans.md").read_text() == "plans"
    assert (base / "organizze" / ".auth").read_text() == "auth"
    assert (base / "organizze" / "snapshots" / "s.json").read_text() == "s"
    assert not (legacy_home / "finance-organizze").exists()
    assert (legacy_home / "finance").is_symlink()


def test_nothing_to_migrate_is_a_true_noop(tmp_path: pathlib.Path) -> None:
    legacy_home = tmp_path / "home"
    legacy_home.mkdir()
    base = tmp_path / "herow" / "finance"

    _storage.migrate_legacy(legacy_home, base)

    assert not (legacy_home / "finance").exists()
    assert not base.exists()


def test_ds_store_deleted_and_dir_removed_when_otherwise_empty(
    tmp_path: pathlib.Path,
) -> None:
    d = tmp_path / "d"
    d.mkdir()
    (d / ".DS_Store").write_text("junk")

    _storage._rmdir_if_empty(d)

    assert not d.exists()


def test_ds_store_deleted_but_dir_kept_when_other_files_remain(
    tmp_path: pathlib.Path,
) -> None:
    d = tmp_path / "d"
    d.mkdir()
    (d / ".DS_Store").write_text("junk")
    (d / "keep.md").write_text("x")

    _storage._rmdir_if_empty(d)

    assert d.exists()
    assert not (d / ".DS_Store").exists()
    assert (d / "keep.md").exists()


def test_auto_migrate_noop_when_any_override_env_var_set(monkeypatch) -> None:
    spy = MagicMock()
    monkeypatch.setattr(_storage, "migrate_legacy", spy)
    for var in ("HEROW_HOME", "ORGANIZZE_HOME", "CONTABILIZEI_HOME"):
        for other in ("HEROW_HOME", "ORGANIZZE_HOME", "CONTABILIZEI_HOME"):
            monkeypatch.delenv(other, raising=False)
        monkeypatch.setenv(var, "/tmp/whatever-not-real-home")
        _storage.auto_migrate()
    spy.assert_not_called()


def test_auto_migrate_calls_migrate_legacy_when_no_override_set(
    monkeypatch, tmp_path: pathlib.Path
) -> None:
    fake_home = tmp_path / "home"
    spy = MagicMock()
    monkeypatch.setattr(_storage, "HOME", fake_home)
    monkeypatch.setattr(_storage, "migrate_legacy", spy)
    for var in ("HEROW_HOME", "ORGANIZZE_HOME", "CONTABILIZEI_HOME"):
        monkeypatch.delenv(var, raising=False)

    _storage.auto_migrate()

    spy.assert_called_once_with(fake_home, _storage.BASE)
