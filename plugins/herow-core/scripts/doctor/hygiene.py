#!/usr/bin/env python3
"""Hygiene checks for /herow-core:doctor. Stdlib only; dry-run by default.

Checks:
  gstack_bak          — ~/.claude/skills/gstack.bak/ is a stale backup dir (WARN).
  claude_md_backups   — ~/.claude/CLAUDE.md.bak.* and CLAUDE.md.pre-omega leftovers (WARN).
  language_rules_paths— ~/.claude/rules/language-rules-pointer.md lacks YAML frontmatter
                        with a paths: scope (WARN).
  legacy_herow_dirs   — pre-~/.herow data left behind (~/finance real dir, ~/.claude/seo,
                        ~/.claude/herow-data) (WARN, informational only — each owning
                        plugin migrates its own data on next run).
  herow_permissions   — settings.json lacks prompt-free access to ~/.herow
                        (permissions.additionalDirectories + permissions.allow) (WARN).
"""

from __future__ import annotations

import os
import pathlib
import shutil
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from _doctor import (  # noqa: E402
    backup,
    claude_home,
    emit,
    fix_cmd_for,
    home,
    load_json,
    rules_dir,
    run_main,
    settings_path,
    skills_dir,
    write_json,
)


def _dir_size(path: pathlib.Path) -> int:
    total = 0
    for root, _dirs, files in os.walk(path):
        for f in files:
            try:
                total += (pathlib.Path(root) / f).stat().st_size
            except OSError:
                pass
    return total


def _human(n: int) -> str:
    size = float(n)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if size < 1024 or unit == "TB":
            return f"{size:.0f}{unit}" if unit == "B" else f"{size:.1f}{unit}"
        size /= 1024
    return f"{size:.1f}TB"


# --- gstack_bak -------------------------------------------------------------


def _gstack_bak() -> pathlib.Path:
    return skills_dir() / "gstack.bak"


def check_gstack_bak() -> None:
    p = _gstack_bak()
    if not p.exists():
        emit("gstack_bak", "pass", "no gstack.bak leftover")
        return
    size = _human(_dir_size(p))
    emit(
        "gstack_bak",
        "warn",
        f"stale gstack.bak backup dir present ({size})",
        diff=f"- rm -rf {p}  # reclaims {size}",
        fix_cmd=fix_cmd_for(__file__, "gstack_bak"),
    )


def apply_gstack_bak() -> bool:
    p = _gstack_bak()
    if not p.exists():
        return False
    shutil.rmtree(p)  # it is itself a stale backup — no further backup taken
    return True


# --- claude_md_backups ------------------------------------------------------


def _claude_md_backups() -> list[pathlib.Path]:
    base = claude_home()
    found = sorted(base.glob("CLAUDE.md.bak.*"))
    pre = base / "CLAUDE.md.pre-omega"
    if pre.exists():
        found.append(pre)
    return found


def check_claude_md_backups() -> None:
    targets = _claude_md_backups()
    if not targets:
        emit("claude_md_backups", "pass", "no stale CLAUDE.md backups")
        return
    emit(
        "claude_md_backups",
        "warn",
        f"{len(targets)} stale CLAUDE.md backup file(s)",
        diff="\n".join(f"- rm {p}" for p in targets),
        fix_cmd=fix_cmd_for(__file__, "claude_md_backups"),
    )


def apply_claude_md_backups() -> bool:
    removed = 0
    for p in _claude_md_backups():
        try:
            p.unlink()
            removed += 1
        except OSError:
            pass
    return removed > 0


# --- language_rules_paths ---------------------------------------------------

FRONTMATTER = """---
description: Pointer to language-specific coding rules (TypeScript, Python).
paths:
  - "**/*.ts"
  - "**/*.tsx"
  - "**/*.js"
  - "**/*.jsx"
  - "**/*.py"
---
"""


def _rules_pointer() -> pathlib.Path:
    return rules_dir() / "language-rules-pointer.md"


def check_language_rules_paths() -> None:
    p = _rules_pointer()
    if not p.exists():
        emit("language_rules_paths", "pass", "no language-rules-pointer.md")
        return
    try:
        text = p.read_text()
    except OSError:
        emit(
            "language_rules_paths",
            "pass",
            "language-rules-pointer.md unreadable — skipping",
        )
        return
    if text.lstrip().startswith("---"):
        emit(
            "language_rules_paths",
            "pass",
            "language-rules-pointer.md has YAML frontmatter",
        )
        return
    emit(
        "language_rules_paths",
        "warn",
        "language-rules-pointer.md has no YAML frontmatter (no paths: scoping)",
        diff="+ prepend frontmatter with description + paths: [ts, tsx, js, jsx, py]",
        fix_cmd=fix_cmd_for(__file__, "language_rules_paths"),
    )


def apply_language_rules_paths() -> bool:
    p = _rules_pointer()
    if not p.exists():
        return False
    text = p.read_text()
    if text.lstrip().startswith("---"):
        return False  # idempotent: frontmatter already present
    backup(p)
    p.write_text(FRONTMATTER + "\n" + text)
    return True


# --- legacy_herow_dirs -------------------------------------------------------


def _legacy_herow_dirs() -> list[pathlib.Path]:
    candidates = [
        home() / "finance",
        claude_home() / "seo",
        claude_home() / "herow-data",
    ]
    return [p for p in candidates if p.exists() and not p.is_symlink()]


def check_legacy_herow_dirs() -> None:
    found = _legacy_herow_dirs()
    if not found:
        emit("legacy_herow_dirs", "pass", "no legacy dirs left outside ~/.herow")
        return
    emit(
        "legacy_herow_dirs",
        "warn",
        f"{len(found)} legacy dir(s) left outside ~/.herow: "
        + ", ".join(str(p) for p in found),
        diff="\n".join(
            f"- {p}  # moves automatically next time its owning plugin runs"
            for p in found
        ),
    )


def apply_legacy_herow_dirs() -> bool:
    return False  # informational only — each plugin owns its own one-shot migration


# --- herow_permissions --------------------------------------------------------

_HEROW_DIR_ENTRY = "~/.herow"
_HEROW_ALLOW_ENTRY = "Edit(~/.herow/**)"


def _herow_access(s: dict) -> tuple[bool, bool]:
    perms = s.get("permissions")
    perms = perms if isinstance(perms, dict) else {}
    add_dirs = perms.get("additionalDirectories")
    add_dirs = add_dirs if isinstance(add_dirs, list) else []
    allow = perms.get("allow")
    allow = allow if isinstance(allow, list) else []
    return _HEROW_DIR_ENTRY in add_dirs, _HEROW_ALLOW_ENTRY in allow


def check_herow_permissions() -> None:
    s = load_json(settings_path())
    if not isinstance(s, dict):
        emit("herow_permissions", "pass", "settings.json missing/unreadable — skipping")
        return
    has_dir, has_allow = _herow_access(s)
    if has_dir and has_allow:
        emit(
            "herow_permissions",
            "pass",
            "settings.json grants prompt-free ~/.herow access",
        )
        return
    missing = []
    if not has_dir:
        missing.append(f'permissions.additionalDirectories += "{_HEROW_DIR_ENTRY}"')
    if not has_allow:
        missing.append(f'permissions.allow += "{_HEROW_ALLOW_ENTRY}"')
    emit(
        "herow_permissions",
        "warn",
        "settings.json is missing prompt-free access to ~/.herow",
        diff="\n".join(f"+ {m}" for m in missing),
        fix_cmd=fix_cmd_for(__file__, "herow_permissions"),
    )


def apply_herow_permissions() -> bool:
    s = load_json(settings_path())
    if not isinstance(s, dict):
        return False  # missing/unparseable — never fabricate or clobber settings.json
    perms = s.setdefault("permissions", {})
    if not isinstance(perms, dict):
        return False
    has_dir, has_allow = _herow_access(s)
    if has_dir and has_allow:
        return False  # idempotent noop
    add_dirs = perms.get("additionalDirectories")
    add_dirs = list(add_dirs) if isinstance(add_dirs, list) else []
    if _HEROW_DIR_ENTRY not in add_dirs:
        add_dirs.append(_HEROW_DIR_ENTRY)
    allow = perms.get("allow")
    allow = list(allow) if isinstance(allow, list) else []
    if _HEROW_ALLOW_ENTRY not in allow:
        allow.append(_HEROW_ALLOW_ENTRY)
    backup(settings_path())
    perms["additionalDirectories"] = add_dirs
    perms["allow"] = allow
    write_json(settings_path(), s)
    return True


CHECKS = {
    "gstack_bak": (check_gstack_bak, apply_gstack_bak),
    "claude_md_backups": (check_claude_md_backups, apply_claude_md_backups),
    "language_rules_paths": (check_language_rules_paths, apply_language_rules_paths),
    "legacy_herow_dirs": (check_legacy_herow_dirs, apply_legacy_herow_dirs),
    "herow_permissions": (check_herow_permissions, apply_herow_permissions),
}


def main(argv=None) -> int:
    return run_main(CHECKS, sys.argv[1:] if argv is None else argv, __file__)


if __name__ == "__main__":
    raise SystemExit(main())
