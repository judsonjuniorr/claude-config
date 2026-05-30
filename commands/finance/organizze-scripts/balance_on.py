#!/usr/bin/env python3
"""Saldo e previsto por conta numa data-alvo.

Para uma data-alvo, devolve por conta principal (checking/savings, não-arquivada,
não-cofrinho) e no total:
- saldo_cents:    saldo atual (_balance_cents, já reconciliado pelo pull.py —
                  soma das transações PAGAS).
- previsto_cents: saldo + todas as transações não pagas com data <= alvo:
                  - transações diretas (sem credit_card_id) não pagas, em past
                    (atrasadas) e future;
                  - débitos de faturas de cartão vencendo em (hoje, alvo] na conta
                    pagadora declarada em ~/finance/organizze/.config.

Faturas com vencimento <= hoje são presumidas pagas (já refletidas no saldo via a
transação de pagamento); o campo `paid` da invoice não é confiável na API.

Usage standalone:
  balance_on.py --snapshot PATH [--date YYYY-MM-DD] [--json]

Como módulo:
  from balance_on import balance_on
  result = balance_on(snapshot, target)   # target: datetime.date
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import pathlib
import sys

try:
    from cashflow import is_principal, _parse_date, _brl
    from config import card_to_account_map
except ImportError:
    sys.path.insert(0, str(pathlib.Path(__file__).parent))
    from cashflow import is_principal, _parse_date, _brl
    from config import card_to_account_map


def balance_on(snapshot: dict, target: dt.date) -> dict:
    """Saldo e previsto por conta na data-alvo.

    {
      "date": "YYYY-MM-DD",
      "accounts": [{
        "id": int, "name": str,
        "saldo_cents": int,        # saldo atual
        "previsto_cents": int,     # saldo + não pagas até a data
        "delta_cents": int,        # previsto - saldo
      }],
      "totals": {"saldo_cents": int, "previsto_cents": int, "delta_cents": int},
      "unmapped_cards": [{"id","name"}],  # faturas NÃO entram no previsto
    }
    """
    today = dt.date.today()
    card_map = card_to_account_map()

    principals = [a for a in (snapshot.get("accounts") or []) if is_principal(a)]
    accounts_by_id = {a["id"]: a for a in principals if "id" in a}

    # delta por conta: soma das não pagas até a data
    delta: dict[int, int] = {aid: 0 for aid in accounts_by_id}

    # 1) transações diretas (sem cartão) não pagas, past + future, data <= alvo
    for key in ("transactions_past", "transactions_future"):
        for t in snapshot.get(key) or []:
            if t.get("paid"):
                continue
            if t.get("credit_card_id") is not None:
                continue
            d = _parse_date(t.get("date"))
            if d is None or d > target:
                continue
            aid = t.get("account_id")
            if aid not in accounts_by_id:
                continue
            delta[aid] += int(t.get("amount_cents") or 0)

    # 2) débitos de faturas vencendo em (hoje, alvo] na conta pagadora mapeada
    unmapped_cards: list[dict] = []
    mapped_card_ids: set[int] = set()
    for cc in snapshot.get("credit_cards") or []:
        cid = cc.get("id")
        if cid is None:
            continue
        if cid in card_map:
            mapped_card_ids.add(cid)
        else:
            unmapped_cards.append({"id": cid, "name": cc.get("name") or "?"})

    for inv in snapshot.get("invoices") or []:
        cid = inv.get("credit_card_id") or inv.get("_credit_card_id")
        if cid is None or cid not in mapped_card_ids:
            continue
        d = _parse_date(inv.get("date"))
        if d is None or d <= today or d > target:
            continue
        aid = card_map.get(cid)
        if aid not in accounts_by_id:
            continue
        amt = int(inv.get("amount_cents") or inv.get("total_cents") or 0)
        if amt == 0:
            continue
        delta[aid] += -abs(amt)  # fatura é sempre débito

    accounts: list[dict] = []
    tot_saldo = tot_prev = 0
    for aid, acc in accounts_by_id.items():
        saldo = int(acc.get("_balance_cents") or 0)
        previsto = saldo + delta[aid]
        tot_saldo += saldo
        tot_prev += previsto
        accounts.append({
            "id": aid,
            "name": acc.get("name"),
            "saldo_cents": saldo,
            "previsto_cents": previsto,
            "delta_cents": delta[aid],
        })
    accounts.sort(key=lambda a: a["previsto_cents"])

    return {
        "date": target.isoformat(),
        "accounts": accounts,
        "totals": {
            "saldo_cents": tot_saldo,
            "previsto_cents": tot_prev,
            "delta_cents": tot_prev - tot_saldo,
        },
        "unmapped_cards": unmapped_cards,
    }


def render_markdown(res: dict) -> str:
    out: list[str] = []
    out.append(f"## Saldo e previsto por conta até {res['date']}")
    out.append("")
    if res.get("unmapped_cards"):
        out.append("⚠️ Cartões SEM conta pagadora (faturas NÃO entram no previsto):")
        for cc in res["unmapped_cards"]:
            out.append(f"- {cc['name']} (id={cc['id']}) — `config.py card-account {cc['id']} <account_id>`")
        out.append("")
    out.append("| Conta | Saldo atual | Previsto | Δ (não pagas) |")
    out.append("|---|--:|--:|--:|")
    for a in res["accounts"]:
        out.append(f"| {a['name']} | {_brl(a['saldo_cents'])} | {_brl(a['previsto_cents'])} | {_brl(a['delta_cents'])} |")
    t = res["totals"]
    out.append(f"| **Total** | **{_brl(t['saldo_cents'])}** | **{_brl(t['previsto_cents'])}** | **{_brl(t['delta_cents'])}** |")
    out.append("")
    return "\n".join(out)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--snapshot", required=True)
    ap.add_argument("--date", default=None, help="YYYY-MM-DD (default: hoje)")
    ap.add_argument("--json", action="store_true", help="emite JSON cru em vez de markdown")
    args = ap.parse_args()

    target = dt.date.fromisoformat(args.date) if args.date else dt.date.today()
    snap = json.loads(pathlib.Path(args.snapshot).read_text())
    res = balance_on(snap, target)
    if args.json:
        print(json.dumps(res, ensure_ascii=False, indent=2))
    else:
        print(render_markdown(res))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
