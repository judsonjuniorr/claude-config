#!/usr/bin/env python3
"""Saldo e previsto por conta numa data-alvo.

Para uma data-alvo, devolve por conta principal (checking/savings, não-arquivada,
não-cofrinho) e por cofrinho (institution_id=="cofrinho"), separadamente:
- saldo_cents:           saldo atual (_balance_cents, já reconciliado pelo pull.py —
                         soma das transações PAGAS).
- previsto_cents:        saldo + não pagas FUTURAS (data em (hoje, alvo]) + faturas
                         de cartão vencendo em (hoje, alvo] na conta pagadora. Esta
                         é a coluna que bate com o "previsto" do app Organizze.
- previsto_atrasadas_cents: previsto + transações atrasadas (não pagas com data <= hoje).
                         Mais conservador — atrasada é obrigação real ainda não baixada.
- atrasadas_cents:       só as atrasadas (previsto_atrasadas - previsto).

Faturas com vencimento <= hoje são presumidas pagas (já refletidas no saldo via a
transação de pagamento); o campo `paid` da invoice não é confiável na API.

Cofrinhos entram numa lista separada e NÃO somam no total das contas principais
(espelha o tratamento do Organizze para reservas).

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
    from cashflow import _parse_date, _brl
    from config import card_to_account_map
except ImportError:
    sys.path.insert(0, str(pathlib.Path(__file__).parent))
    from cashflow import _parse_date, _brl
    from config import card_to_account_map


def _kind(a: dict) -> str | None:
    """principal | cofrinho | None (ignorada)."""
    if a.get("archived"):
        return None
    if a.get("institution_id") == "cofrinho":
        return "cofrinho"
    if a.get("type") in ("checking", "savings"):
        return "principal"
    return None


def balance_on(snapshot: dict, target: dt.date) -> dict:
    """Saldo, previsto (Organizze) e previsto c/ atrasadas por conta na data-alvo.

    {
      "date": "YYYY-MM-DD", "today": "YYYY-MM-DD",
      "accounts": [{id,name,saldo_cents,previsto_cents,
                    previsto_atrasadas_cents,atrasadas_cents,delta_cents}],
      "cofrinhos": [ ...mesma estrutura... ],
      "totals": {...},            # só contas principais
      "cofrinhos_totals": {...},
      "unmapped_cards": [{"id","name"}],
    }
    """
    today = dt.date.today()
    card_map = card_to_account_map()

    by_id: dict[int, dict] = {}
    kind_of: dict[int, str] = {}
    for a in snapshot.get("accounts") or []:
        k = _kind(a)
        if k is None or "id" not in a:
            continue
        by_id[a["id"]] = a
        kind_of[a["id"]] = k

    # delta futuro (hoje, alvo] e delta atrasadas (<= hoje), por conta
    delta_fut: dict[int, int] = {aid: 0 for aid in by_id}
    delta_late: dict[int, int] = {aid: 0 for aid in by_id}

    # 1) transações diretas (sem cartão) não pagas, data <= alvo
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
            if aid not in by_id:
                continue
            amt = int(t.get("amount_cents") or 0)
            if d > today:
                delta_fut[aid] += amt
            else:
                delta_late[aid] += amt

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
        if aid not in by_id:
            continue
        amt = int(inv.get("amount_cents") or inv.get("total_cents") or 0)
        if amt == 0:
            continue
        delta_fut[aid] += -abs(amt)  # fatura é sempre débito

    def row(aid: int) -> dict:
        saldo = int(by_id[aid].get("_balance_cents") or 0)
        previsto = saldo + delta_fut[aid]
        previsto_late = previsto + delta_late[aid]
        return {
            "id": aid,
            "name": by_id[aid].get("name"),
            "saldo_cents": saldo,
            "previsto_cents": previsto,
            "previsto_atrasadas_cents": previsto_late,
            "atrasadas_cents": delta_late[aid],
            "delta_cents": delta_fut[aid],
        }

    accounts = sorted((row(a) for a in by_id if kind_of[a] == "principal"),
                      key=lambda r: r["previsto_cents"])
    cofrinhos = sorted((row(a) for a in by_id if kind_of[a] == "cofrinho"),
                       key=lambda r: r["previsto_cents"])

    def totals(rows: list[dict]) -> dict:
        return {
            "saldo_cents": sum(r["saldo_cents"] for r in rows),
            "previsto_cents": sum(r["previsto_cents"] for r in rows),
            "previsto_atrasadas_cents": sum(r["previsto_atrasadas_cents"] for r in rows),
            "atrasadas_cents": sum(r["atrasadas_cents"] for r in rows),
            "delta_cents": sum(r["delta_cents"] for r in rows),
        }

    return {
        "date": target.isoformat(),
        "today": today.isoformat(),
        "accounts": accounts,
        "cofrinhos": cofrinhos,
        "totals": totals(accounts),
        "cofrinhos_totals": totals(cofrinhos),
        "unmapped_cards": unmapped_cards,
    }


def _table(rows: list[dict], total: dict, total_label: str) -> list[str]:
    out = ["| Conta | Saldo atual | Previsto (Organizze) | Previsto c/ atrasadas |",
           "|---|--:|--:|--:|"]
    for r in rows:
        out.append(
            f"| {r['name']} | {_brl(r['saldo_cents'])} | {_brl(r['previsto_cents'])} "
            f"| {_brl(r['previsto_atrasadas_cents'])} |"
        )
    out.append(
        f"| **{total_label}** | **{_brl(total['saldo_cents'])}** "
        f"| **{_brl(total['previsto_cents'])}** "
        f"| **{_brl(total['previsto_atrasadas_cents'])}** |"
    )
    return out


def render_markdown(res: dict) -> str:
    out: list[str] = [f"## Saldo e previsto por conta até {res['date']}", ""]
    if res.get("unmapped_cards"):
        out.append("⚠️ Cartões SEM conta pagadora (faturas NÃO entram no previsto):")
        for cc in res["unmapped_cards"]:
            out.append(f"- {cc['name']} (id={cc['id']}) — `config.py card-account {cc['id']} <account_id>`")
        out.append("")
    out.append("_Previsto (Organizze) = saldo + não pagas futuras + faturas até a data._")
    out.append("_Previsto c/ atrasadas soma também transações vencidas e não pagas._")
    out.append("")
    out += _table(res["accounts"], res["totals"], "Total (contas principais)")
    if res.get("cofrinhos"):
        out.append("")
        out.append("### Cofrinhos / reservas (não somam no total das contas principais)")
        out += _table(res["cofrinhos"], res["cofrinhos_totals"], "Total cofrinhos")
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
