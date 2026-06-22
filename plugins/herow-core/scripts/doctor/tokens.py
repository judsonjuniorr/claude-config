#!/usr/bin/env python3
"""Token-cost checks for /herow-core:doctor. Stdlib only; dry-run by default.

Checks:
  headroom_hook_redundancy — the headroom init hook should run once (SessionStart),
                             not also on every PreToolUse (WARN when duplicated).
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
    settings_path,
    write_json,
)

# --- headroom_hook_redundancy ----------------------------------------------


def _hook_is_headroom(matcher) -> bool:
    if not isinstance(matcher, dict):
        return False
    for h in matcher.get("hooks") or []:
        if isinstance(h, dict) and "headroom init hook ensure" in (
            h.get("command") or ""
        ):
            return True
    return False


def _pre_session(s: dict) -> tuple[list, list]:
    """PreToolUse + SessionStart matcher lists, tolerating malformed (non-dict/list) values."""
    hooks = s.get("hooks")
    hooks = hooks if isinstance(hooks, dict) else {}
    pre = hooks.get("PreToolUse")
    session = hooks.get("SessionStart")
    return (
        pre if isinstance(pre, list) else [],
        session if isinstance(session, list) else [],
    )


def check_headroom_hook_redundancy() -> None:
    s = load_json(settings_path())
    if not isinstance(s, dict):
        emit(
            "headroom_hook_redundancy",
            "pass",
            "settings.json missing/unreadable — skipping",
        )
        return
    pre, session = _pre_session(s)
    in_pre = [i for i, m in enumerate(pre) if _hook_is_headroom(m)]
    in_session = any(_hook_is_headroom(m) for m in session)
    if not in_pre:
        emit("headroom_hook_redundancy", "pass", "headroom init hook not in PreToolUse")
        return
    if not in_session:
        # Sole copy lives in PreToolUse — not redundant; removing it would lose the hook.
        emit(
            "headroom_hook_redundancy",
            "pass",
            "headroom init hook only in PreToolUse (sole copy — keeping)",
        )
        return
    emit(
        "headroom_hook_redundancy",
        "warn",
        "headroom init hook runs on every PreToolUse and at SessionStart — redundant",
        diff=(
            f"- remove PreToolUse matcher(s) at index {in_pre} (headroom init hook); "
            "keep the other PreToolUse matchers and the SessionStart copy"
        ),
        fix_cmd=fix_cmd_for(__file__, "headroom_hook_redundancy"),
    )


def apply_headroom_hook_redundancy() -> bool:
    s = load_json(settings_path())
    if not isinstance(s, dict):
        return False
    pre, session = _pre_session(s)
    if not any(_hook_is_headroom(m) for m in session):
        return False  # refuse to delete the only copy of the hook
    kept = [m for m in pre if not _hook_is_headroom(m)]
    if len(kept) == len(pre):
        return False  # idempotent: already absent from PreToolUse
    hooks_obj = s.get("hooks")
    if not isinstance(hooks_obj, dict):
        return False
    backup(settings_path())
    hooks_obj["PreToolUse"] = kept
    write_json(settings_path(), s)
    return True


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
    "headroom_hook_redundancy": (
        check_headroom_hook_redundancy,
        apply_headroom_hook_redundancy,
    ),
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
