#!/usr/bin/env python3
"""Reconcile calculated balances vs real balances shown in the Organizze app.

The /accounts API does not return the current balance. pull.py sums paid
transactions (long window) to estimate — but the initial balance configured by
the user when creating the account does not appear in /transactions. This script
captures the difference as an offset in ~/finance/organizze/balances.json, which
pull.py adds on the next run.

Mode 1 — account_id=value_in_cents pairs via CLI:
  reconcile.py --snapshot PATH <account_id_1>=<cents> <account_id_2>=<cents>
  e.g.: reconcile.py --snapshot PATH 1234567=80174 7654321=194746

Mode 2 — JSON via stdin:
  echo '{"1234567": 80174, "7654321": 194746}' | reconcile.py --snapshot PATH -

Mode 3 — interactive (default without args):
  reconcile.py --snapshot PATH
"""
from __future__ import annotations

import argparse
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).parent))
from _paths import HOME, BALANCES, migrate_legacy  # noqa: E402

migrate_legacy()


def cents_to_brl(c: int) -> str:
    v = c / 100.0
    s = f"{abs(v):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return f"-R$ {s}" if v < 0 else f"R$ {s}"


def brl_to_cents(s: str) -> int:
    s = s.strip().replace("R$", "").replace(" ", "")
    if "," in s:
        s = s.replace(".", "").replace(",", ".")
    return int(round(float(s) * 100))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--snapshot", required=True)
    ap.add_argument("pairs", nargs="*", help="account_id=value_in_cents (or '-' to read JSON from stdin)")
    args = ap.parse_args()

    snap = json.loads(pathlib.Path(args.snapshot).read_text())
    active = [a for a in snap.get("accounts") or [] if not a.get("archived")]
    by_id = {a["id"]: a for a in active}

    desired: dict[int, int] = {}

    if args.pairs == ["-"]:
        desired = {int(k): int(v) for k, v in json.load(sys.stdin).items()}
    elif args.pairs:
        for p in args.pairs:
            k, v = p.split("=", 1)
            desired[int(k)] = int(v)
    else:
        print("Active accounts — enter the REAL balance shown in the app (ENTER to skip):", file=sys.stderr)
        for a in active:
            calc = a.get("_balance_cents") or 0
            prompt = f"  {a['name']} ({a['id']}) — calculated {cents_to_brl(calc)} · real: "
            print(prompt, end="", file=sys.stderr, flush=True)
            line = sys.stdin.readline().strip()
            if not line:
                continue
            desired[a["id"]] = brl_to_cents(line)

    if not desired:
        print("err|nothing-to-reconcile|no input provided", file=sys.stderr)
        return 1

    HOME.mkdir(parents=True, exist_ok=True)
    existing: dict[str, int] = {}
    if BALANCES.exists():
        try:
            existing = {str(k): int(v) for k, v in json.loads(BALANCES.read_text()).items()}
        except Exception:
            existing = {}

    for acc_id, real in desired.items():
        a = by_id.get(acc_id)
        if not a:
            print(f"warn|unknown-account|{acc_id}", file=sys.stderr)
            continue
        calc = (a.get("_balance_cents") or 0) - int(existing.get(str(acc_id), 0))
        offset = real - calc
        existing[str(acc_id)] = offset
        print(f"ok|offset|{acc_id}|{a['name']}|calc={cents_to_brl(calc)}|real={cents_to_brl(real)}|offset={cents_to_brl(offset)}")

    BALANCES.write_text(json.dumps(existing, indent=2))
    BALANCES.chmod(0o600)
    print(f"ok|saved|{BALANCES}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
