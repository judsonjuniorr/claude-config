#!/usr/bin/env python3
"""Shared helpers for the /herow-core:doctor audit scripts. Stdlib only.

Output contract — every check prints ONE JSON line to stdout in dry-run:
  {"check","status":"pass|warn|fail","detail","diff":<str|null>,"fix_cmd":<str|null>}
Fatal/diagnostic errors go to stderr as `err|code|detail`. Exit code stays 0 even
when checks report "fail" — the calling agent decides what to do.

Paths derive from DOCTOR_HOME (falling back to the real home dir) and are exposed
as *functions* so a test can retarget HOME between cases without reimporting. No
hardcoded home paths live in this file (CI rejects absolute user paths under plugins/).
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import pathlib
import shutil
import sys

# --- paths (DOCTOR_HOME override keeps tests hermetic) ----------------------


def home() -> pathlib.Path:
    return pathlib.Path(os.environ.get("DOCTOR_HOME") or pathlib.Path.home())


def claude_home() -> pathlib.Path:
    return home() / ".claude"


def settings_path() -> pathlib.Path:
    return claude_home() / "settings.json"


def claude_json_path() -> pathlib.Path:
    return home() / ".claude.json"


def mcp_stash_path() -> pathlib.Path:
    return claude_home() / "mcp-stash.json"


def mcp_restore_path() -> pathlib.Path:
    return claude_home() / "mcp-restore.sh"


def skills_dir() -> pathlib.Path:
    return claude_home() / "skills"


def rules_dir() -> pathlib.Path:
    return claude_home() / "rules"


# --- output -----------------------------------------------------------------


def emit(
    check: str,
    status: str,
    detail: str,
    diff: str | None = None,
    fix_cmd: str | None = None,
) -> None:
    """Print one dry-run JSON line to stdout."""
    print(
        json.dumps(
            {
                "check": check,
                "status": status,
                "detail": detail,
                "diff": diff,
                "fix_cmd": fix_cmd,
            }
        )
    )


def fatal(code: str, detail: str) -> None:
    """Diagnostic to stderr only — never pollutes the JSONL stdout stream."""
    print(f"err|{code}|{detail}", file=sys.stderr)


def fix_cmd_for(script_path: str, check_id: str) -> str:
    """Build the exact apply invocation for a check, from the owning script path.

    Resolved at runtime, so the rendered absolute path never lives in source.
    """
    return f'python3 "{pathlib.Path(script_path).resolve()}" --apply {check_id}'


# --- file io ----------------------------------------------------------------


def load_json(path: pathlib.Path):
    """Parsed JSON dict, or None on missing/unreadable/unparseable. Never raises."""
    try:
        return json.loads(pathlib.Path(path).read_text())
    except FileNotFoundError:
        return None
    except (json.JSONDecodeError, OSError, ValueError):
        return None


def backup(path: pathlib.Path) -> pathlib.Path | None:
    """Timestamped `.bak.<UTC>` copy (matches setup/_common.sh), chmod 0600.

    Returns the backup path, or None if the source does not exist. A same-second
    collision gets a numeric suffix so an existing backup is never clobbered.
    """
    path = pathlib.Path(path)
    if not path.exists():
        return None
    ts = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%d-%H%M%S")
    bak = path.with_name(path.name + f".bak.{ts}")
    i = 1
    while bak.exists():
        bak = path.with_name(path.name + f".bak.{ts}-{i}")
        i += 1
    shutil.copy2(path, bak)
    try:
        bak.chmod(0o600)  # backups may hold secrets
    except OSError:
        pass
    return bak


def write_json(path: pathlib.Path, obj) -> None:
    """Atomically write `obj` as 2-space-indented JSON (tmp file + os.replace)."""
    path = pathlib.Path(path)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(obj, indent=2) + "\n")
    os.replace(tmp, path)


# --- shared CLI -------------------------------------------------------------


def run_main(checks: dict, argv: list[str], script_path: str) -> int:
    """Drive a sub-script's CLI.

    `checks` maps id -> (check_fn, apply_fn). check_fn emits one JSON line;
    apply_fn performs the idempotent fix and returns True if it changed state.
      no args        -> run every check_fn (dry-run JSONL), exit 0
      --apply <id>   -> run that apply_fn, print ok|applied|<id> or ok|noop|<id>
                        unknown id -> err|bad-check, exit 2
                        apply raised -> err|apply-failed, exit 1
    """
    parser = argparse.ArgumentParser(add_help=True)
    parser.add_argument("--apply", metavar="CHECK_ID", default=None)
    args = parser.parse_args(argv)

    if args.apply is not None:
        entry = checks.get(args.apply)
        if entry is None:
            fatal("bad-check", args.apply)
            return 2
        _check_fn, apply_fn = entry
        try:
            changed = apply_fn()
        except Exception as exc:  # noqa: BLE401 — surface, never crash mid-write
            fatal("apply-failed", f"{args.apply}: {exc}")
            return 1
        print(f"ok|{'applied' if changed else 'noop'}|{args.apply}")
        return 0

    for _cid, (check_fn, _apply_fn) in checks.items():
        check_fn()
    return 0
