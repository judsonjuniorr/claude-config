#!/usr/bin/env python3
"""Financial goals (savings/economy plans) — provider-agnostic.

Same pattern as memory.py: readable markdown in ~/finance/plans.md,
manually editable. Each entry has inline metadata in the header.

Header format:
  ## <ts> [target=<cents>][·deadline=<YYYY-MM-DD>][·account=<free name>][·category=<name>][·priority=<negociavel|inegociavel>][·status=<active|done|paused|cancelled>]

Usage:
  plans.py add "<text>" --target-cents N [--deadline YYYY-MM-DD] [--account "<name>"] [--category "<name>"] [--priority negociavel|inegociavel]
  plans.py list [--recent N] [--status active|done|paused|cancelled]
  plans.py render             # markdown block ready to inject into prompt
  plans.py done <ts>          # mark status=done
  plans.py status <ts> <new_status>
  plans.py prune --older-than-done 365
"""
from __future__ import annotations

import argparse
import datetime as dt
import pathlib
import re
import sys

sys.path.insert(0, str(pathlib.Path(__file__).parent))
from _storage import PLANS, migrate_legacy  # noqa: E402

HEADER_RE = re.compile(r"^## (\d{4}-\d{2}-\d{2} \d{2}:\d{2})(.*)$")
META_RE = re.compile(r"(\w+)=([^·\]]+?)(?=\s*[·\]]|$)")

ALLOWED_STATUS = {"active", "done", "paused", "cancelled"}
ALLOWED_PRIORITY = {"negociavel", "inegociavel"}


def _parse_header(line: str) -> dict | None:
    m = HEADER_RE.match(line)
    if not m:
        return None
    ts, rest = m.group(1), m.group(2)
    meta: dict[str, str] = {}
    inside = rest.strip()
    if inside.startswith("[") and inside.endswith("]"):
        inside = inside[1:-1]
    for k, v in META_RE.findall(inside):
        meta[k.strip()] = v.strip()
    out: dict = {"ts": ts}
    if "target" in meta:
        try:
            out["target_cents"] = int(meta["target"])
        except ValueError:
            out["target_cents"] = 0
    out["deadline"] = meta.get("deadline")
    out["account"] = meta.get("account")
    out["category"] = meta.get("category")
    out["priority"] = meta.get("priority") or "negociavel"
    out["status"] = meta.get("status") or "active"
    return out


def _load() -> list[dict]:
    if not PLANS.exists():
        return []
    entries: list[dict] = []
    current: dict | None = None
    body_lines: list[str] = []
    for line in PLANS.read_text().splitlines():
        h = _parse_header(line)
        if h is not None:
            if current is not None:
                current["body"] = "\n".join(body_lines).strip()
                entries.append(current)
            current = h
            body_lines = []
        elif current is not None:
            body_lines.append(line)
    if current is not None:
        current["body"] = "\n".join(body_lines).strip()
        entries.append(current)
    return entries


def _fmt_header(e: dict) -> str:
    parts: list[str] = []
    if e.get("target_cents"):
        parts.append(f"target={int(e['target_cents'])}")
    if e.get("deadline"):
        parts.append(f"deadline={e['deadline']}")
    if e.get("account"):
        parts.append(f"account={e['account']}")
    if e.get("category"):
        parts.append(f"category={e['category']}")
    parts.append(f"priority={e.get('priority', 'negociavel')}")
    parts.append(f"status={e.get('status', 'active')}")
    suffix = f" [{' · '.join(parts)}]" if parts else ""
    return f"## {e['ts']}{suffix}"


def _save(entries: list[dict]) -> None:
    PLANS.parent.mkdir(parents=True, exist_ok=True)
    out = ["# Financial goals", "",
           "Savings/economy plans the AI should pursue.",
           "Manually editable. Most recent entries at top.",
           "Priority: `inegociavel` = do not pause even with imminent debt.",
           ""]
    for e in sorted(entries, key=lambda x: x["ts"], reverse=True):
        out.append(_fmt_header(e))
        out.append("")
        out.append(e.get("body", ""))
        out.append("")
    PLANS.write_text("\n".join(out))
    PLANS.chmod(0o600)


def _brl(c: int) -> str:
    v = abs(int(c)) / 100.0
    s = f"{v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return f"R$ {s}"


def cmd_add(args) -> int:
    text = args.text.strip()
    if not text:
        print("err|empty|nothing to add", file=sys.stderr)
        return 1
    if args.priority and args.priority not in ALLOWED_PRIORITY:
        print(f"err|bad-priority|use {ALLOWED_PRIORITY}", file=sys.stderr)
        return 1
    if args.deadline:
        try:
            dt.date.fromisoformat(args.deadline)
        except ValueError:
            print("err|bad-deadline|use YYYY-MM-DD", file=sys.stderr)
            return 1
    ts = dt.datetime.now().strftime("%Y-%m-%d %H:%M")
    entries = _load()
    entries.append({
        "ts": ts,
        "target_cents": args.target_cents or 0,
        "deadline": args.deadline,
        "account": args.account,
        "category": args.category,
        "priority": args.priority or "negociavel",
        "status": "active",
        "body": text,
    })
    _save(entries)
    print(f"ok|added|{ts}|{PLANS}")
    return 0


def cmd_list(args) -> int:
    entries = sorted(_load(), key=lambda x: x["ts"], reverse=True)
    if args.status:
        entries = [e for e in entries if e.get("status") == args.status]
    if args.recent:
        entries = entries[: args.recent]
    if not entries:
        print("(no goals)", file=sys.stderr)
        return 0
    for e in entries:
        print(_fmt_header(e))
        print(e.get("body", ""))
        print()
    return 0


def cmd_render(args) -> int:
    entries = [e for e in _load() if e.get("status") == "active"]
    if not entries:
        return 0
    today = dt.date.today()
    print("# User goals (SAVINGS/ECONOMY TARGETS — PURSUE)")
    print()
    print("Each item is a financial goal recorded by the user. "
          "**Evaluate ad-hoc whether there is room in the month for each one** by looking at current balance + "
          "tx_future. Do NOT assume a fixed monthly contribution. If a critical day appears in "
          "any main account, **pause goals with priority=negociavel** "
          "and prioritize covering the debt; goals with priority=inegociavel must "
          "be maintained by cutting spending in other categories.")
    print()
    print("If the goal references an `account=` that does NOT exist in the snapshot `accounts`, "
          "do NOT suggest a transfer: recommend in generic format "
          "('set aside R$ X for Y'). Every transfer suggestion must name "
          "two accounts that exist in the snapshot.")
    print()
    for e in sorted(entries, key=lambda x: x["ts"], reverse=True):
        bits = []
        if e.get("target_cents"):
            bits.append(f"target {_brl(e['target_cents'])}")
        if e.get("deadline"):
            try:
                d = dt.date.fromisoformat(e["deadline"])
                days = (d - today).days
                bits.append(f"deadline {e['deadline']} ({days}d)")
            except ValueError:
                bits.append(f"deadline {e['deadline']}")
        if e.get("account"):
            bits.append(f"target-account: {e['account']}")
        if e.get("category"):
            bits.append(f"category: {e['category']}")
        bits.append(f"priority: {e.get('priority')}")
        meta = " · ".join(bits)
        print(f"- ({e['ts']}) [{meta}] {e.get('body', '')}")
    print()
    return 0


def cmd_status(args) -> int:
    if args.new_status not in ALLOWED_STATUS:
        print(f"err|bad-status|use {ALLOWED_STATUS}", file=sys.stderr)
        return 1
    entries = _load()
    hit = False
    for e in entries:
        if e["ts"] == args.ts:
            e["status"] = args.new_status
            hit = True
    if not hit:
        print(f"err|not-found|{args.ts}", file=sys.stderr)
        return 1
    _save(entries)
    print(f"ok|status|{args.ts}={args.new_status}")
    return 0


def cmd_done(args) -> int:
    args.new_status = "done"
    return cmd_status(args)


def cmd_prune(args) -> int:
    cutoff = dt.datetime.now() - dt.timedelta(days=args.older_than_done)
    entries = _load()
    kept: list[dict] = []
    dropped = 0
    for e in entries:
        if e.get("status") == "done":
            try:
                d = dt.datetime.strptime(e["ts"], "%Y-%m-%d %H:%M")
                if d < cutoff:
                    dropped += 1
                    continue
            except ValueError:
                pass
        kept.append(e)
    _save(kept)
    print(f"ok|pruned|{dropped} done plans older than {args.older_than_done}d")
    return 0


def main() -> int:
    migrate_legacy()

    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)

    a = sub.add_parser("add")
    a.add_argument("text")
    a.add_argument("--target-cents", type=int, default=0)
    a.add_argument("--deadline", default=None)
    a.add_argument("--account", default=None)
    a.add_argument("--category", default=None)
    a.add_argument("--priority", default="negociavel")
    a.set_defaults(func=cmd_add)

    l = sub.add_parser("list")
    l.add_argument("--recent", type=int, default=None)
    l.add_argument("--status", default=None)
    l.set_defaults(func=cmd_list)

    r = sub.add_parser("render")
    r.set_defaults(func=cmd_render)

    d = sub.add_parser("done")
    d.add_argument("ts")
    d.set_defaults(func=cmd_done)

    s = sub.add_parser("status")
    s.add_argument("ts")
    s.add_argument("new_status")
    s.set_defaults(func=cmd_status)

    p = sub.add_parser("prune")
    p.add_argument("--older-than-done", type=int, default=365)
    p.set_defaults(func=cmd_prune)

    args = ap.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
