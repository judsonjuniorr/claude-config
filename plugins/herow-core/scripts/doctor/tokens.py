#!/usr/bin/env python3
"""Token-cost checks for /herow-core:doctor. Stdlib only; dry-run by default.

Checks:
  playwright_headed_active — the headed playwright MCP should be stashed on-demand,
                             not active (WARN; use playwright-headless instead).
  grafana_active           — grafana MCP loads ~30k tokens of tools; stash it (WARN).

MCP servers live in ~/.claude.json (active) + ~/.claude/mcp-stash.json (on-demand),
NOT in settings.json. The "move to stash" apply edits both JSON files atomically
(backing up each first); undo later with `~/.claude/mcp-restore.sh <name>`.
"""

from __future__ import annotations

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from _doctor import (  # noqa: E402
    backup,
    claude_json_path,
    emit,
    fix_cmd_for,
    load_json,
    mcp_stash_path,
    run_main,
    write_json,
)

# --- playwright_headed_active / grafana_active -----------------------------


def _active_servers():
    aj = load_json(claude_json_path())
    if not isinstance(aj, dict):
        return None
    srv = aj.get("mcpServers")
    return srv if isinstance(srv, dict) else {}


def _move_server_to_stash(name: str) -> bool:
    """Move an active MCP server from ~/.claude.json into the stash, atomically.

    Idempotent: noop when the server is not in the active mcpServers. Backs up both
    files before writing (the doctor's destructive-edit invariant). The direct JSON
    edit is equivalent to `claude mcp remove -s user` but with a guaranteed .bak and
    no dependency on the claude/jq CLIs. Undo with `~/.claude/mcp-restore.sh <name>`.
    """
    aj = load_json(claude_json_path())
    if not isinstance(aj, dict):
        return False
    active = aj.get("mcpServers")
    if not isinstance(active, dict) or name not in active:
        return False  # not active → nothing to do
    cfg = active[name]
    stash = load_json(mcp_stash_path())
    stash = stash if isinstance(stash, dict) else {}
    if stash.get(name) != cfg:
        backup(mcp_stash_path())
        stash[name] = cfg
        write_json(mcp_stash_path(), stash)
    backup(claude_json_path())
    del aj["mcpServers"][name]
    write_json(claude_json_path(), aj)
    print(f"info|stashed|{name} -> mcp-stash.json (restore via mcp-restore.sh {name})")
    return True


def check_playwright_headed_active() -> None:
    active = _active_servers()
    if active is None:
        emit(
            "playwright_headed_active",
            "pass",
            "~/.claude.json missing/unreadable — skipping",
        )
        return
    if "playwright" not in active:
        emit(
            "playwright_headed_active",
            "pass",
            "headed playwright not active (stash-only)",
        )
        return
    emit(
        "playwright_headed_active",
        "warn",
        "headed playwright MCP active — prefer playwright-headless; stash the headed one",
        diff="- ~/.claude.json mcpServers.playwright -> mcp-stash.json "
        "(restore later via mcp-restore.sh playwright)",
        fix_cmd=fix_cmd_for(__file__, "playwright_headed_active"),
    )


def apply_playwright_headed_active() -> bool:
    return _move_server_to_stash("playwright")


def check_grafana_active() -> None:
    active = _active_servers()
    if active is None:
        emit("grafana_active", "pass", "~/.claude.json missing/unreadable — skipping")
        return
    if "grafana" not in active:
        emit("grafana_active", "pass", "grafana MCP not active (stash-only)")
        return
    emit(
        "grafana_active",
        "warn",
        "grafana MCP active — loads ~30k tokens of tools; stash it on-demand",
        diff="- ~/.claude.json mcpServers.grafana -> mcp-stash.json "
        "(restore later via mcp-restore.sh grafana)",
        fix_cmd=fix_cmd_for(__file__, "grafana_active"),
    )


def apply_grafana_active() -> bool:
    return _move_server_to_stash("grafana")


CHECKS = {
    "playwright_headed_active": (
        check_playwright_headed_active,
        apply_playwright_headed_active,
    ),
    "grafana_active": (check_grafana_active, apply_grafana_active),
}


def main(argv=None) -> int:
    return run_main(CHECKS, sys.argv[1:] if argv is None else argv, __file__)


if __name__ == "__main__":
    raise SystemExit(main())
