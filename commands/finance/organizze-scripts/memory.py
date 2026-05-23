#!/usr/bin/env python3
"""Memória financeira persistente.

Armazena restrições, contextos e preferências do usuário que a IA deve respeitar
nas análises futuras. Exemplo: "não consigo diminuir a parcela da casa" — daí
em diante o subagent não sugere isso.

Cada entrada vai com timestamp; entradas mais recentes pesam mais (mas nada é
descartado automaticamente — use `prune` para remover obsoletas).

Arquivo: ~/finance-organizze/memory.md (markdown legível, editável manualmente).

Usage:
  memory.py add "<texto>"           # adiciona entrada
  memory.py add --tag dívida "..."  # com tag opcional
  memory.py list [--recent N]       # lista (default: tudo)
  memory.py render                  # imprime formatado para injeção em prompt
  memory.py prune --older-than 365  # remove entradas mais velhas que N dias
"""
from __future__ import annotations

import argparse
import datetime as dt
import pathlib
import re
import sys

MEM = pathlib.Path.home() / "finance-organizze" / "memory.md"
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
    # normaliza body
    for e in entries:
        e["body"] = "\n".join(e["lines"]).strip()
        del e["lines"]
    return entries


def _save(entries: list[dict]) -> None:
    MEM.parent.mkdir(parents=True, exist_ok=True)
    out = ["# Memória financeira", "",
           "Restrições, contextos e preferências que a IA DEVE respeitar.",
           "Entradas mais recentes no topo; edição manual permitida.", ""]
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
        print("(memória vazia)", file=sys.stderr)
        return 0
    for e in entries:
        tag = f" [{e['tag']}]" if e.get("tag") else ""
        print(f"## {e['ts']}{tag}")
        print(e["body"])
        print()
    return 0


def cmd_render(args) -> int:
    """Imprime memória pronta para injeção em prompt do subagent."""
    entries = sorted(_load(), key=lambda x: x["ts"], reverse=True)
    if not entries:
        return 0
    today = dt.date.today()
    print("# Memória do usuário (RESTRIÇÕES E CONTEXTO — RESPEITAR)")
    print()
    print("Cada item abaixo é uma decisão/restrição registrada pelo usuário em ")
    print("conversas anteriores. **Não sugira ações que contradigam estes itens.** ")
    print("Itens com data mais recente têm maior peso.")
    print()
    for e in entries:
        try:
            d = dt.datetime.strptime(e["ts"], "%Y-%m-%d %H:%M").date()
            age = (today - d).days
            recency = "recente" if age <= 30 else ("vigente" if age <= 180 else "antiga")
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
