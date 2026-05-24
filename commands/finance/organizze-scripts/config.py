#!/usr/bin/env python3
"""Config helper para ~/finance-organizze/.config (KEY=VALUE).

Chaves conhecidas:
  CASHFLOW_THRESHOLD_CENTS=0
  CARD_PAYMENT_ACCOUNT_<card_id>=<account_id>

Usage:
  config.py get KEY [--default V]
  config.py set KEY VALUE
  config.py list
  config.py card-account <card_id>            # get
  config.py card-account <card_id> <acc_id>   # set
  config.py cards-missing --snapshot PATH     # imprime "<card_id>|<card_name>" para cartões sem pagadora
"""
from __future__ import annotations

import argparse
import json
import os
import pathlib
import sys

HOME = pathlib.Path(os.environ.get("ORGANIZZE_HOME", str(pathlib.Path.home() / "finance-organizze")))
CONF = HOME / ".config"


def load() -> dict[str, str]:
    if not CONF.exists():
        return {}
    out: dict[str, str] = {}
    for line in CONF.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        out[k.strip()] = v.strip().strip('"').strip("'")
    return out


def save(cfg: dict[str, str]) -> None:
    HOME.mkdir(parents=True, exist_ok=True)
    lines = ["# Config gerada por config.py — KEY=VALUE"]
    for k in sorted(cfg):
        lines.append(f"{k}={cfg[k]}")
    CONF.write_text("\n".join(lines) + "\n")
    CONF.chmod(0o600)


def get(key: str, default: str | None = None) -> str | None:
    return load().get(key, default)


def set_(key: str, value: str) -> None:
    cfg = load()
    cfg[key] = value
    save(cfg)


def card_account_key(card_id: int | str) -> str:
    return f"CARD_PAYMENT_ACCOUNT_{card_id}"


def threshold_cents() -> int:
    raw = get("CASHFLOW_THRESHOLD_CENTS", "0") or "0"
    try:
        return int(raw)
    except ValueError:
        return 0


def card_to_account_map() -> dict[int, int]:
    cfg = load()
    out: dict[int, int] = {}
    prefix = "CARD_PAYMENT_ACCOUNT_"
    for k, v in cfg.items():
        if not k.startswith(prefix):
            continue
        try:
            out[int(k[len(prefix):])] = int(v)
        except ValueError:
            continue
    return out


def cmd_get(args) -> int:
    v = get(args.key, args.default)
    if v is None:
        print(f"err|missing|{args.key}", file=sys.stderr)
        return 1
    print(v)
    return 0


def cmd_set(args) -> int:
    set_(args.key, args.value)
    print(f"ok|set|{args.key}={args.value}")
    return 0


def cmd_list(args) -> int:
    cfg = load()
    if not cfg:
        print("(vazio)", file=sys.stderr)
        return 0
    for k in sorted(cfg):
        print(f"{k}={cfg[k]}")
    return 0


def cmd_card_account(args) -> int:
    key = card_account_key(args.card_id)
    if args.account_id is None:
        v = get(key)
        if v is None:
            print(f"err|missing|{key}", file=sys.stderr)
            return 1
        print(v)
        return 0
    set_(key, str(args.account_id))
    print(f"ok|set|{key}={args.account_id}")
    return 0


def cmd_cards_missing(args) -> int:
    snap = json.loads(pathlib.Path(args.snapshot).read_text())
    mapping = card_to_account_map()
    for cc in snap.get("credit_cards") or []:
        cid = cc.get("id")
        if cid is None:
            continue
        if cid in mapping:
            continue
        print(f"{cid}|{cc.get('name') or '?'}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)

    g = sub.add_parser("get")
    g.add_argument("key")
    g.add_argument("--default", default=None)
    g.set_defaults(func=cmd_get)

    s = sub.add_parser("set")
    s.add_argument("key")
    s.add_argument("value")
    s.set_defaults(func=cmd_set)

    l = sub.add_parser("list")
    l.set_defaults(func=cmd_list)

    c = sub.add_parser("card-account")
    c.add_argument("card_id", type=int)
    c.add_argument("account_id", nargs="?", type=int, default=None)
    c.set_defaults(func=cmd_card_account)

    cm = sub.add_parser("cards-missing")
    cm.add_argument("--snapshot", required=True)
    cm.set_defaults(func=cmd_cards_missing)

    args = ap.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
