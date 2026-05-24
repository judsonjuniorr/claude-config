#!/usr/bin/env python3
"""Objetivos financeiros (planos de poupança/economia).

Mesmo padrão da memory.py: markdown legível em ~/finance-organizze/plans.md,
editável à mão. Cada entrada tem metadados inline no header.

Header format:
  ## <ts> [target=<cents>][·deadline=<YYYY-MM-DD>][·account=<nome livre>][·category=<nome>][·priority=<negociavel|inegociavel>][·status=<active|done|paused|cancelled>]

Usage:
  plans.py add "<texto>" --target-cents N [--deadline YYYY-MM-DD] [--account "<nome>"] [--category "<nome>"] [--priority negociavel|inegociavel]
  plans.py list [--recent N] [--status active|done|paused|cancelled]
  plans.py render             # bloco markdown pronto pra injetar no prompt
  plans.py done <ts>          # marca status=done
  plans.py status <ts> <novo_status>
  plans.py prune --older-than-done 365
"""
from __future__ import annotations

import argparse
import datetime as dt
import pathlib
import re
import sys

PLANS = pathlib.Path.home() / "finance-organizze" / "plans.md"

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
    out = ["# Objetivos financeiros", "",
           "Planos de poupança/economia que a IA deve perseguir.",
           "Editável à mão. Entradas mais recentes no topo.",
           "Prioridade: `inegociavel` = não pausar mesmo com débito iminente.",
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
        print("(sem objetivos)", file=sys.stderr)
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
    print("# Objetivos do usuário (METAS DE POUPANÇA/ECONOMIA — PERSEGUIR)")
    print()
    print("Cada item é um objetivo financeiro registrado pelo usuário. "
          "**Avalie ad-hoc se há espaço no mês para cada um** olhando saldo atual + "
          "tx_future. NÃO assuma aporte mensal fixo. Se um dia crítico aparecer em "
          "qualquer conta principal, **pause objetivos com priority=negociavel** "
          "e priorize cobrir o débito; objetivos com priority=inegociavel devem "
          "ser mantidos cortando gastos em outras categorias.")
    print()
    print("Se o objetivo cita uma `account=` que NÃO existe em `accounts` do snapshot, "
          "NÃO sugira transferência: recomende em formato genérico "
          "('reserve R$ X para Y'). Toda sugestão de transferência deve nomear "
          "duas contas que existem no snapshot.")
    print()
    for e in sorted(entries, key=lambda x: x["ts"], reverse=True):
        bits = []
        if e.get("target_cents"):
            bits.append(f"alvo {_brl(e['target_cents'])}")
        if e.get("deadline"):
            try:
                d = dt.date.fromisoformat(e["deadline"])
                days = (d - today).days
                bits.append(f"prazo {e['deadline']} ({days}d)")
            except ValueError:
                bits.append(f"prazo {e['deadline']}")
        if e.get("account"):
            bits.append(f"conta-alvo: {e['account']}")
        if e.get("category"):
            bits.append(f"categoria: {e['category']}")
        bits.append(f"prioridade: {e.get('priority')}")
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
