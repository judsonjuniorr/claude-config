#!/usr/bin/env python3
"""Persistent financial memory (provider-agnostic).

Stores user constraints, contexts, and preferences that the AI must respect
in future analyses. Example: "I can't reduce my mortgage payment" — from
that point on the subagent does not suggest it.

Each entry is timestamped; more recent entries carry more weight (but nothing
is discarded automatically — use `prune` to remove obsolete ones).

File: ~/finance/memory.md (readable markdown, manually editable).

Usage:
  memory.py add "<text>"           # add entry
  memory.py add --tag debt "..."   # with optional tag
  memory.py list [--recent N]      # list (default: all)
  memory.py render                 # print formatted for prompt injection
  memory.py prune --older-than 365 # remove entries older than N days
"""
from __future__ import annotations

import argparse
import datetime as dt
import pathlib
import re
import sys

sys.path.insert(0, str(pathlib.Path(__file__).parent))
from _storage import MEM, migrate_legacy  # noqa: E402

ENTRY_RE = re.compile(r"^## (\d{4}-\d{2}-\d{2} \d{2}:\d{2})(?: \[(?P<tag>[^\]]+)\])?\s*$")


def _load() -> list[dict]:
    if not MEM.exists():
        return []
    entries: list[dict] = []
    current: dict | None = None
    for line in MEM.read_text().splitlines():
        m = ENTRY_RE.match(line)
        if m:
            if current:
                entries.append(current)
            current = {"ts": m.group(1), "tag": m.group("tag"), "lines": []}
        elif current is not None:
            current["lines"].append(line)
    if current:
        entries.append(current)
    for e in entries:
        e["body"] = "\n".join(e["lines"]).strip()
        del e["lines"]
    return entries


def _save(entries: list[dict]) -> None:
    MEM.parent.mkdir(parents=True, exist_ok=True)
    out = ["# Financial memory", "",
           "Constraints, contexts, and preferences the AI MUST respect.",
           "Most recent entries at top; manual editing allowed.", ""]
    for e in sorted(entries, key=lambda x: x["ts"], reverse=True):
        tag = f" [{e['tag']}]" if e.get("tag") else ""
        out.append(f"## {e['ts']}{tag}")
        out.append("")
        out.append(e["body"])
        out.append("")
    MEM.write_text("\n".join(out))
    MEM.chmod(0o600)


def cmd_add(args) -> int:
    text = args.text.strip()
    if not text:
        print("err|empty|nothing to add", file=sys.stderr)
        return 1
    ts = dt.datetime.now().strftime("%Y-%m-%d %H:%M")
    entries = _load()
    entries.append({"ts": ts, "tag": args.tag, "body": text})
    _save(entries)
    print(f"ok|added|{ts}|{MEM}")
    return 0


def cmd_list(args) -> int:
    entries = sorted(_load(), key=lambda x: x["ts"], reverse=True)
    if args.recent:
        entries = entries[: args.recent]
    if not entries:
        print("(memory is empty)", file=sys.stderr)
        return 0
    for e in entries:
        tag = f" [{e['tag']}]" if e.get("tag") else ""
        print(f"## {e['ts']}{tag}")
        print(e["body"])
        print()
    return 0


def cmd_render(args) -> int:
    """Print memory ready for injection into the subagent prompt."""
    entries = sorted(_load(), key=lambda x: x["ts"], reverse=True)
    if not entries:
        return 0
    today = dt.date.today()
    print("# User memory (CONSTRAINTS AND CONTEXT — MUST RESPECT)")
    print()
    print("Each item below is a decision/constraint recorded by the user in ")
    print("previous conversations. **Do not suggest actions that contradict these items.** ")
    print("More recent items carry greater weight.")
    print()
    for e in entries:
        try:
            d = dt.datetime.strptime(e["ts"], "%Y-%m-%d %H:%M").date()
            age = (today - d).days
            recency = "recent" if age <= 30 else ("current" if age <= 180 else "old")
        except Exception:
            recency = "?"
        tag = f" `{e['tag']}`" if e.get("tag") else ""
        print(f"- ({e['ts']} · {recency}){tag} {e['body']}")
    print()
    return 0


def cmd_prune(args) -> int:
    cutoff = dt.datetime.now() - dt.timedelta(days=args.older_than)
    entries = _load()
    kept = []
    dropped = 0
    for e in entries:
        try:
            d = dt.datetime.strptime(e["ts"], "%Y-%m-%d %H:%M")
            if d < cutoff:
                dropped += 1
                continue
        except Exception:
            pass
        kept.append(e)
    _save(kept)
    print(f"ok|pruned|{dropped} entries older than {args.older_than}d")
    return 0


def main() -> int:
    migrate_legacy()

    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)

    a = sub.add_parser("add")
    a.add_argument("text")
    a.add_argument("--tag", default=None)
    a.set_defaults(func=cmd_add)

    l = sub.add_parser("list")
    l.add_argument("--recent", type=int, default=None)
    l.set_defaults(func=cmd_list)

    r = sub.add_parser("render")
    r.set_defaults(func=cmd_render)

    p = sub.add_parser("prune")
    p.add_argument("--older-than", type=int, default=365)
    p.set_defaults(func=cmd_prune)

    args = ap.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
