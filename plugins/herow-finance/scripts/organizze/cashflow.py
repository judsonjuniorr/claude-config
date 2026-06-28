#!/usr/bin/env python3
"""Daily balance projection per main account.

For each main account (checking/savings, not archived, not savings pot):
- initial balance = _balance_cents (already reconciled by pull.py)
- applies transactions_future with corresponding account_id, in chronological order
- applies credit card invoice debits on the due date, on the paying account
  declared in ~/finance/organizze/.config (CARD_PAYMENT_ACCOUNT_<card_id>)
- emits critical days: projected balance < threshold (default 0, configurable)
- for each critical day, lists accounts with slack (projected balance on the same day
  > shortfall) as transfer candidates

Standalone usage:
  cashflow.py --snapshot PATH [--horizon-days 90] [--threshold-cents 0]

As a module:
  from cashflow import per_account_projection
  result = per_account_projection(snapshot, threshold_cents=0, horizon_days=90)
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import pathlib
import sys

try:
    from config import card_to_account_map, threshold_cents as cfg_threshold
except ImportError:
    sys.path.insert(0, str(pathlib.Path(__file__).parent))
    from config import card_to_account_map, threshold_cents as cfg_threshold


def is_principal(a: dict) -> bool:
    if a.get("archived"):
        return False
    if a.get("institution_id") == "cofrinho":
        return False
    return a.get("type") in ("checking", "savings")


def _parse_date(s: str | None) -> dt.date | None:
    if not s:
        return None
    try:
        return dt.date.fromisoformat(s[:10])
    except ValueError:
        return None


def _brl(c: int) -> str:
    v = abs(int(c)) / 100.0
    s = f"{v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return f"-R$ {s}" if c < 0 else f"R$ {s}"


def per_account_projection(
    snapshot: dict,
    threshold_cents: int = 0,
    horizon_days: int = 90,
) -> dict:
    """Returns a serializable structure with projection and critical days per account.

    {
      "threshold_cents": int,
      "horizon_end": "YYYY-MM-DD",
      "accounts": [{
        "id": int, "name": str, "initial_cents": int, "final_cents": int,
        "critical_days": [{
          "date": "YYYY-MM-DD",
          "projected_cents": int,
          "shortfall_cents": int,   # how much is needed to reach threshold
          "drivers": [{"date","description","amount_cents","kind"}],
          "cover_candidates": [{"account_id","account_name","available_cents"}]
        }]
      }],
      "card_payment_map": {card_id: account_id},
      "unmapped_cards": [{"id","name"}],   # cards without CARD_PAYMENT_ACCOUNT_*
    }
    """
    today = dt.date.today()
    horizon = today + dt.timedelta(days=horizon_days)
    card_map = card_to_account_map()

    principals = [a for a in (snapshot.get("accounts") or []) if is_principal(a)]
    accounts_by_id = {a["id"]: a for a in principals if "id" in a}

    # events per account: [(date, amount_cents, description, kind)]
    events: dict[int, list[tuple[dt.date, int, str, str]]] = {aid: [] for aid in accounts_by_id}

    # 1) transactions_future filtered by main account_id
    for t in snapshot.get("transactions_future") or []:
        d = _parse_date(t.get("date"))
        # Boleto guard: use vencimento_date if present
        if t.get("vencimento_date"):
            try:
                venc_d = dt.date.fromisoformat(t["vencimento_date"][:10])
                d = venc_d
            except (ValueError, TypeError):
                pass  # keep original d
        if d is None or d <= today or d > horizon:
            continue
        if t.get("credit_card_id") is not None:
            # invoice spending enters via invoice debit below, not as tx
            continue
        aid = t.get("account_id")
        if aid not in accounts_by_id:
            continue
        amt = int(t.get("amount_cents") or 0)
        events[aid].append((d, amt, t.get("description") or "?", "tx"))

    # 2) credit card invoice debits on the paying account (only if mapped)
    unmapped_cards: list[dict] = []
    mapped_card_ids: set[int] = set()
    for cc in snapshot.get("credit_cards") or []:
        cid = cc.get("id")
        if cid is None:
            continue
        if cid not in card_map:
            unmapped_cards.append({"id": cid, "name": cc.get("name") or "?"})
        else:
            mapped_card_ids.add(cid)

    for inv in snapshot.get("invoices") or []:
        cid = inv.get("credit_card_id") or inv.get("_credit_card_id")
        if cid is None or cid not in mapped_card_ids:
            continue
        d = _parse_date(inv.get("date"))
        if d is None or d <= today or d > horizon:
            continue
        aid = card_map.get(cid)
        if aid not in accounts_by_id:
            continue
        amt = int(inv.get("amount_cents") or inv.get("total_cents") or 0)
        if amt == 0:
            continue
        amt = -abs(amt)  # invoice is always a debit
        name = inv.get("_credit_card_name") or "card"
        events[aid].append((d, amt, f"Invoice {name}", "invoice"))

    # 3) daily projection per account
    accounts_proj: dict[int, list[tuple[dt.date, int]]] = {}
    accounts_summary: list[dict] = []
    for aid, acc in accounts_by_id.items():
        evs = sorted(events.get(aid, []), key=lambda x: x[0])
        bal = int(acc.get("_balance_cents") or 0)
        daily: list[tuple[dt.date, int]] = []
        # aggregate by day: closing balance
        by_day: dict[dt.date, int] = {}
        for d, amt, _desc, _k in evs:
            by_day[d] = by_day.get(d, 0) + amt
        cur = bal
        d = today
        while d <= horizon:
            cur += by_day.get(d, 0)
            daily.append((d, cur))
            d += dt.timedelta(days=1)
        accounts_proj[aid] = daily
        accounts_summary.append({
            "id": aid,
            "name": acc.get("name"),
            "initial_cents": bal,
            "final_cents": daily[-1][1] if daily else bal,
            "events": evs,
        })

    # 4) detect critical days per account and coverage candidates
    result_accounts: list[dict] = []
    for s in accounts_summary:
        aid = s["id"]
        daily = accounts_proj[aid]
        evs = s.pop("events")
        critical: list[dict] = []
        for d, bal in daily:
            if bal >= threshold_cents:
                continue
            shortfall = threshold_cents - bal
            drivers = [
                {"date": dd.isoformat(), "description": desc, "amount_cents": amt, "kind": k}
                for (dd, amt, desc, k) in evs if dd == d and amt < 0
            ]
            # candidates: other main accounts with projected balance on that day >= shortfall
            covers: list[dict] = []
            for other in accounts_summary:
                if other["id"] == aid:
                    continue
                # find balance of other account on that day
                other_daily = accounts_proj[other["id"]]
                other_bal = next((b for (dx, b) in other_daily if dx == d), None)
                if other_bal is None or other_bal < shortfall:
                    continue
                covers.append({
                    "account_id": other["id"],
                    "account_name": other["name"],
                    "available_cents": other_bal,
                })
            covers.sort(key=lambda x: -x["available_cents"])
            critical.append({
                "date": d.isoformat(),
                "projected_cents": bal,
                "shortfall_cents": shortfall,
                "drivers": drivers,
                "cover_candidates": covers[:5],
            })
        s["critical_days"] = critical
        result_accounts.append(s)

    # Build upcoming_obligations: high-value debits within horizon
    upcoming_obligations: list[dict] = []
    for aid_u, acc_u in accounts_by_id.items():
        for ev in events.get(aid_u, []):
            d_ev, amt_ev, desc_ev, kind_ev = ev
            if amt_ev < -50000 and d_ev <= horizon:
                upcoming_obligations.append({
                    "date": d_ev.isoformat(),
                    "description": desc_ev,
                    "amount_cents": amt_ev,
                    "account_id": aid_u,
                    "account_name": acc_u.get("name"),
                    "kind": kind_ev,
                })
    upcoming_obligations.sort(key=lambda x: x["date"])

    return {
        "threshold_cents": threshold_cents,
        "horizon_end": horizon.isoformat(),
        "accounts": result_accounts,
        "card_payment_map": {str(k): v for k, v in card_map.items()},
        "unmapped_cards": unmapped_cards,
        "upcoming_obligations": upcoming_obligations,
    }


def render_markdown(proj: dict) -> str:
    """Markdown block ready to inject in analyze.py."""
    out: list[str] = []
    out.append("## Cash flow per account — critical days (next 90 days)")
    thr = proj.get("threshold_cents", 0)
    out.append(f"_Alert threshold: {_brl(thr)} · horizon: {proj.get('horizon_end')}_")
    out.append("")

    if proj.get("unmapped_cards"):
        out.append("⚠️ Cards WITHOUT a configured paying account (invoices NOT included in projection):")
        for cc in proj["unmapped_cards"]:
            out.append(f"- {cc['name']} (id={cc['id']}) — run `config.py card-account {cc['id']} <account_id>`")
        out.append("")

    any_critical = False
    for acc in proj.get("accounts", []):
        out.append(f"### {acc['name']}")
        out.append(f"- Initial balance: {_brl(acc['initial_cents'])} · projected final: {_brl(acc['final_cents'])}")
        critical = acc.get("critical_days") or []
        if not critical:
            out.append("- ✅ No critical days on the horizon.")
            out.append("")
            continue
        any_critical = True
        out.append(f"- ⚠️ {len(critical)} critical day(s):")
        for cd in critical[:10]:
            out.append(f"  - **{cd['date']}**: projected balance {_brl(cd['projected_cents'])} (shortfall {_brl(cd['shortfall_cents'])})")
            for drv in cd["drivers"][:5]:
                out.append(f"    - debit: {drv['description']} · {_brl(drv['amount_cents'])}")
            if cd["cover_candidates"]:
                covers_str = ", ".join(
                    f"{c['account_name']} ({_brl(c['available_cents'])})"
                    for c in cd["cover_candidates"]
                )
                out.append(f"    - accounts with slack on that day: {covers_str}")
            else:
                out.append("    - ❌ no main account with sufficient slack on that day.")
        if len(critical) > 10:
            out.append(f"  - … (+{len(critical) - 10} days)")
        out.append("")

    if not any_critical:
        out.append("✅ No main account has a critical day on the horizon.")
        out.append("")

    return "\n".join(out)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--snapshot", required=True)
    ap.add_argument("--horizon-days", type=int, default=90)
    ap.add_argument("--threshold-cents", type=int, default=None,
                    help="default: reads from ~/finance/organizze/.config CASHFLOW_THRESHOLD_CENTS")
    ap.add_argument("--json", action="store_true", help="emite JSON cru em vez de markdown")
    args = ap.parse_args()

    snap = json.loads(pathlib.Path(args.snapshot).read_text())
    thr = args.threshold_cents if args.threshold_cents is not None else cfg_threshold()
    proj = per_account_projection(snap, threshold_cents=thr, horizon_days=args.horizon_days)
    if args.json:
        print(json.dumps(proj, ensure_ascii=False, indent=2))
    else:
        print(render_markdown(proj))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
