#!/usr/bin/env python3
"""Pull Organizze data via REST v2 and save a consolidated snapshot.

Usage:
  pull.py --out PATH [--history-days N] [--future-days N]

Reads credentials from ~/finance-organizze/.auth (ORGANIZZE_EMAIL,
ORGANIZZE_TOKEN, ORGANIZZE_USER_AGENT). Stdlib only.
"""
from __future__ import annotations

import argparse
import base64
import datetime as dt
import json
import os
import pathlib
import statistics
import sys
import urllib.error
import urllib.parse
import urllib.request

API = "https://api.organizze.com.br/rest/v2"
HOME = pathlib.Path(os.environ.get("ORGANIZZE_HOME", str(pathlib.Path.home() / "finance-organizze")))
AUTH = HOME / ".auth"
CACHE = HOME / "cache"


# --- auth + http -----------------------------------------------------------

def load_auth() -> tuple[str, str, str]:
    if not AUTH.exists():
        sys.exit("err|no-auth|run setup_auth.sh first")
    env: dict[str, str] = {}
    for line in AUTH.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        env[k.strip()] = v.strip().strip('"').strip("'")
    try:
        return env["ORGANIZZE_EMAIL"], env["ORGANIZZE_TOKEN"], env["ORGANIZZE_USER_AGENT"]
    except KeyError as e:
        sys.exit(f"err|bad-auth|missing {e}")


def http_get(path: str, params: dict | None, email: str, token: str, ua: str) -> object:
    qs = ("?" + urllib.parse.urlencode(params)) if params else ""
    url = f"{API}{path}{qs}"
    creds = base64.b64encode(f"{email}:{token}".encode()).decode()
    req = urllib.request.Request(
        url,
        headers={
            "Authorization": f"Basic {creds}",
            "User-Agent": ua,
            "Accept": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read().decode("utf-8") or "null")
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")[:200]
        sys.exit(f"err|http-{e.code}|{path} {body}")
    except urllib.error.URLError as e:
        sys.exit(f"err|network|{e.reason}")


# --- helpers ---------------------------------------------------------------

def iso(d: dt.date) -> str:
    return d.isoformat()


def month_ranges(start: dt.date, end: dt.date) -> list[tuple[dt.date, dt.date]]:
    """Yield (first_day, last_day) for each month touching [start, end]."""
    out = []
    cur = start.replace(day=1)
    while cur <= end:
        if cur.month == 12:
            nxt = cur.replace(year=cur.year + 1, month=1, day=1)
        else:
            nxt = cur.replace(month=cur.month + 1, day=1)
        last = nxt - dt.timedelta(days=1)
        out.append((max(cur, start), min(last, end)))
        cur = nxt
    return out


def cache_get(name: str, max_age_days: int) -> object | None:
    p = CACHE / name
    if not p.exists():
        return None
    age = dt.datetime.now().timestamp() - p.stat().st_mtime
    if age > max_age_days * 86400:
        return None
    try:
        return json.loads(p.read_text())
    except Exception:
        return None


def cache_set(name: str, data: object) -> None:
    CACHE.mkdir(parents=True, exist_ok=True)
    (CACHE / name).write_text(json.dumps(data, ensure_ascii=False))


# --- domain ----------------------------------------------------------------

def fetch_transactions(start: dt.date, end: dt.date, email: str, token: str, ua: str) -> list[dict]:
    """API agrupa por mês cheio; iteramos mês a mês e deduplicamos por id."""
    seen: dict[int, dict] = {}
    for (a, b) in month_ranges(start, end):
        rows = http_get("/transactions", {"start_date": iso(a), "end_date": iso(b)}, email, token, ua)
        if isinstance(rows, list):
            for t in rows:
                if isinstance(t, dict) and "id" in t:
                    seen[t["id"]] = t
    return list(seen.values())


def compute_account_balances(
    accounts: list[dict],
    credit_card_ids: set[int],
    email: str, token: str, ua: str,
    lookback_years: int = 5,
) -> dict[int, int]:
    """Saldo por conta = soma(transactions pagas, account_id da conta, NÃO de cartão), em cents.

    A API /accounts não devolve saldo. Reconstruímos somando o histórico longo,
    excluindo gastos de fatura de cartão (credit_card_id != null) e contas que
    são na verdade cartões (account_id ∈ credit_card_ids).
    Suporta offset manual em ~/finance-organizze/balances.json:
        {"<account_id>": <offset_cents>}  # somado ao calculado
    """
    today = dt.date.today()
    start = today.replace(year=today.year - lookback_years)
    sums: dict[int, int] = {a["id"]: 0 for a in accounts if "id" in a}
    for (a, b) in month_ranges(start, today):
        rows = http_get("/transactions", {"start_date": iso(a), "end_date": iso(b)}, email, token, ua)
        if not isinstance(rows, list):
            continue
        for t in rows:
            if not isinstance(t, dict):
                continue
            if not t.get("paid"):
                continue
            if t.get("credit_card_id") is not None:
                continue
            acc = t.get("account_id")
            if acc in credit_card_ids:
                continue
            if acc in sums:
                sums[acc] += int(t.get("amount_cents") or 0)
    offsets_path = HOME / "balances.json"
    if offsets_path.exists():
        try:
            offsets = json.loads(offsets_path.read_text())
            for k, v in offsets.items():
                try:
                    sums[int(k)] = sums.get(int(k), 0) + int(v)
                except (TypeError, ValueError):
                    pass
        except Exception as e:
            print(f"warn|balances-offset|{e}", file=sys.stderr)
    return sums


def detect_recurring(transactions: list[dict], months_window: int = 6) -> set[int]:
    """Marca tx como recorrente: mesmo payee normalizado, ≥3 ocorrências em janela, variação <15%."""
    today = dt.date.today()
    cutoff = today - dt.timedelta(days=months_window * 31)
    buckets: dict[str, list[dict]] = {}
    for t in transactions:
        d = t.get("date")
        if not d:
            continue
        try:
            td = dt.date.fromisoformat(d[:10])
        except ValueError:
            continue
        if td < cutoff:
            continue
        payee = (t.get("description") or "").strip().lower()
        if not payee:
            continue
        # normaliza dígitos e espaços múltiplos
        key = " ".join(c for c in payee if not c.isdigit()).strip()
        buckets.setdefault(key, []).append(t)
    recurring: set[int] = set()
    for key, txs in buckets.items():
        if len(txs) < 3:
            continue
        amounts = [abs(float(t.get("amount_cents", 0))) for t in txs if t.get("amount_cents") is not None]
        if not amounts:
            continue
        m = statistics.median(amounts)
        if m == 0:
            continue
        variation = (max(amounts) - min(amounts)) / m
        if variation < 0.15:
            for t in txs:
                if "id" in t:
                    recurring.add(t["id"])
    return recurring


def is_principal_account(a: dict) -> bool:
    """Todas as contas ativas (checking, savings, other) — inclui cofrinhos para bater com o total do Organizze."""
    if a.get("archived"):
        return False
    return a.get("type") in ("checking", "savings", "other")


def _load_card_account_map() -> dict[int, int]:
    cfg = HOME / ".config"
    mapping: dict[int, int] = {}
    if not cfg.exists():
        return mapping
    for line in cfg.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        k, v = k.strip(), v.strip()
        if k.startswith("CARD_PAYMENT_ACCOUNT_"):
            try:
                mapping[int(k[len("CARD_PAYMENT_ACCOUNT_"):])] = int(v)
            except ValueError:
                pass
    return mapping


def compute_totals(snapshot: dict) -> dict:
    accounts = snapshot.get("accounts") or []
    saldo = sum(int(a.get("_balance_cents") or 0) for a in accounts if is_principal_account(a))

    card_acct_map = _load_card_account_map()
    today = dt.date.today()

    def sum_future(days: int) -> int:
        end = today + dt.timedelta(days=days)
        total = 0
        for t in snapshot.get("transactions_future") or []:
            if t.get("credit_card_id") is not None:
                continue  # gasto de cartão entra via fatura, não como débito bancário direto
            d = t.get("date", "")[:10]
            try:
                td = dt.date.fromisoformat(d)
            except ValueError:
                continue
            if today < td <= end:
                total += int(t.get("amount_cents") or 0)
        return total

    def sum_invoices(days: int) -> int:
        end = today + dt.timedelta(days=days)
        total = 0
        for inv in snapshot.get("invoices") or []:
            d = (inv.get("date") or "")[:10]
            try:
                due = dt.date.fromisoformat(d)
            except ValueError:
                continue
            if today < due <= end:
                cid = inv.get("_credit_card_id") or inv.get("credit_card_id")
                if cid not in card_acct_map:
                    continue
                amt = int(inv.get("amount_cents") or 0)
                if amt != 0:
                    total += amt  # amount_cents já é negativo para faturas a pagar
        return total

    proj_7 = saldo + sum_future(7) + sum_invoices(7)
    proj_30 = saldo + sum_future(30) + sum_invoices(30)
    proj_90 = saldo + sum_future(90) + sum_invoices(90)

    # faturas a vencer em 7 dias
    invoices_due_7 = []
    for inv in snapshot.get("invoices") or []:
        d = (inv.get("date") or "")[:10]
        try:
            due = dt.date.fromisoformat(d)
        except ValueError:
            continue
        if today <= due <= today + dt.timedelta(days=7):
            invoices_due_7.append(inv)

    # Transações passadas NÃO pagas (atrasadas) — separadas por receita/despesa
    overdue_exp = 0
    overdue_inc = 0
    n_over_exp = n_over_inc = 0
    for t in snapshot.get("transactions_past") or []:
        if t.get("paid"):
            continue
        if t.get("credit_card_id") is not None:
            continue  # gasto no cartão entra via fatura, não como atrasado
        amt = int(t.get("amount_cents") or 0)
        if amt < 0:
            overdue_exp += -amt
            n_over_exp += 1
        elif amt > 0:
            overdue_inc += amt
            n_over_inc += 1

    return {
        "saldo_cents": saldo,
        "saldo_proj_7d_cents": proj_7,
        "saldo_proj_30d_cents": proj_30,
        "saldo_proj_90d_cents": proj_90,
        "n_transacoes_past": len(snapshot.get("transactions_past") or []),
        "n_transacoes_future": len(snapshot.get("transactions_future") or []),
        "n_recorrentes": sum(1 for t in (snapshot.get("transactions_past") or []) if t.get("is_recurring")),
        "n_faturas_vence_7d": len(invoices_due_7),
        "soma_faturas_vence_7d_cents": sum(int(i.get("total_cents") or 0) for i in invoices_due_7),
        "n_atrasadas_despesa": n_over_exp,
        "soma_atrasadas_despesa_cents": overdue_exp,
        "n_atrasadas_receita": n_over_inc,
        "soma_atrasadas_receita_cents": overdue_inc,
    }


def build_installments(snapshot: dict) -> list[dict]:
    """Agrupa parcelamentos em curso (total_installments > 1) de past + future.

    Chave: (descrição normalizada, total_installments). Mostra progresso, valor médio
    da parcela, quanto falta e data prevista de término.
    """
    today = dt.date.today()
    bag: dict[tuple[str, int], list[dict]] = {}
    for t in (snapshot.get("transactions_past") or []) + (snapshot.get("transactions_future") or []):
        total = int(t.get("total_installments") or 1)
        if total <= 1:
            continue
        desc = (t.get("description") or "").strip()
        # tira "(x/y)" típico do final
        norm = desc
        for tail in (f"({t.get('installment')}/{total})", f" {t.get('installment')}/{total}"):
            if tail in norm:
                norm = norm.replace(tail, "").strip()
        # remove sufixos numéricos finais para agrupar
        norm = norm.rstrip("0123456789/() -").strip().lower()
        bag.setdefault((norm, total), []).append(t)

    out = []
    for (norm, total), txs in bag.items():
        txs_sorted = sorted(txs, key=lambda x: int(x.get("installment") or 0))
        paid_count = sum(1 for x in txs_sorted if x.get("paid"))
        max_installment = max((int(x.get("installment") or 0) for x in txs_sorted), default=0)
        # Se a parcela de número mais alto que vemos é a última E está paga, o parcelamento acabou.
        if max_installment == total and all(x.get("paid") for x in txs_sorted):
            continue
        last_paid = next((x for x in reversed(txs_sorted) if x.get("paid")), None)
        next_unpaid = next((x for x in txs_sorted if not x.get("paid")), None)
        amounts = [abs(int(x.get("amount_cents") or 0)) for x in txs_sorted if x.get("amount_cents") is not None]
        avg = int(sum(amounts) / len(amounts)) if amounts else 0
        remaining = total - paid_count
        if remaining <= 0:
            continue
        # Fim previsto = data da próxima não-paga + (remaining - 1) meses; fallback: última conhecida + meses faltantes
        end_date = None
        anchor = next_unpaid or last_paid or (txs_sorted[0] if txs_sorted else None)
        if anchor and anchor.get("date"):
            try:
                anchor_d = dt.date.fromisoformat(anchor["date"][:10])
                if next_unpaid:
                    months_to_add = max(remaining - 1, 0)
                else:
                    months_to_add = remaining
                y = anchor_d.year + (anchor_d.month + months_to_add - 1) // 12
                m = (anchor_d.month + months_to_add - 1) % 12 + 1
                end_date = dt.date(y, m, min(anchor_d.day, 28)).isoformat()
            except ValueError:
                pass
        out.append({
            "description": (txs_sorted[0].get("description") if txs_sorted else norm).strip(),
            "total_installments": total,
            "paid": paid_count,
            "remaining": remaining,
            "avg_amount_cents": avg,
            "remaining_amount_cents": avg * remaining,
            "next_due_date": (next_unpaid or {}).get("date"),
            "expected_end_date": end_date,
            "progress_pct": round(paid_count / total * 100.0, 1) if total else 0.0,
            "almost_done": (remaining <= 3),
            "long_way": (remaining >= total // 2 and total >= 12),
        })
    out.sort(key=lambda r: -(r["remaining_amount_cents"]))
    return out


# --- main ------------------------------------------------------------------

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--history-days", type=int, default=180)
    ap.add_argument("--future-days", type=int, default=90)
    args = ap.parse_args()

    email, token, ua = load_auth()
    CACHE.mkdir(parents=True, exist_ok=True)

    today = dt.date.today()
    past_start = today - dt.timedelta(days=args.history_days)
    future_end = today + dt.timedelta(days=args.future_days)

    print(f"info|pulling|history={args.history_days}d future={args.future_days}d", file=sys.stderr)

    accounts_all = http_get("/accounts", None, email, token, ua) or []
    # ativas = não-arquivadas E com type definido (type=null indica conta zumbi/órfã)
    accounts = [a for a in accounts_all if not a.get("archived") and a.get("type")]
    print(f"info|accounts|{len(accounts)} ativas (ignoradas {len(accounts_all) - len(accounts)} arquivadas/órfãs)", file=sys.stderr)

    categories = cache_get("categories.json", max_age_days=7)
    if categories is None:
        categories = http_get("/categories", None, email, token, ua) or []
        cache_set("categories.json", categories)
    print(f"info|categories|{len(categories)} (cached={categories is not None})", file=sys.stderr)

    credit_cards_all = http_get("/credit_cards", None, email, token, ua) or []
    credit_cards = [cc for cc in credit_cards_all if not cc.get("archived")]
    credit_card_ids = {cc["id"] for cc in credit_cards if "id" in cc}
    print(f"info|credit_cards|{len(credit_cards)} ativos (ignorados {len(credit_cards_all) - len(credit_cards)} arquivados)", file=sys.stderr)

    # Saldos por conta — calculados via histórico longo (API não devolve saldo)
    balances = compute_account_balances(accounts, credit_card_ids, email, token, ua)
    for a in accounts:
        a["_balance_cents"] = balances.get(a.get("id"), 0)
    print(f"info|balances|computed for {len(balances)} accounts", file=sys.stderr)

    invoices: list[dict] = []
    for cc in credit_cards:
        cid = cc.get("id")
        if not cid:
            continue
        invs = http_get(
            f"/credit_cards/{cid}/invoices",
            {"start_date": iso(past_start), "end_date": iso(future_end)},
            email, token, ua,
        ) or []
        for inv in invs:
            inv["_credit_card_id"] = cid
            inv["_credit_card_name"] = cc.get("name")
        invoices.extend(invs)
    print(f"info|invoices|{len(invoices)}", file=sys.stderr)

    tx_past = fetch_transactions(past_start, today, email, token, ua)
    print(f"info|transactions_past|{len(tx_past)}", file=sys.stderr)

    tx_future = fetch_transactions(today + dt.timedelta(days=1), future_end, email, token, ua)
    print(f"info|transactions_future|{len(tx_future)}", file=sys.stderr)

    recurring_ids = detect_recurring(tx_past)
    for t in tx_past:
        t["is_recurring"] = t.get("id") in recurring_ids

    # Orçamentos: mês corrente + próximos 2
    budgets: list[dict] = []
    for offset in range(3):
        y = today.year
        m = today.month + offset
        while m > 12:
            m -= 12
            y += 1
        b = http_get(f"/budgets/{y}/{m}", None, email, token, ua)
        if isinstance(b, list):
            for item in b:
                item["_year"] = y
                item["_month"] = m
            budgets.extend(b)
        elif isinstance(b, dict):
            b["_year"] = y
            b["_month"] = m
            budgets.append(b)
    print(f"info|budgets|{len(budgets)}", file=sys.stderr)

    snapshot = {
        "meta": {
            "pulled_at": dt.datetime.now().isoformat(timespec="seconds"),
            "periodo": {"history_start": iso(past_start), "today": iso(today), "future_end": iso(future_end)},
        },
        "accounts": accounts,
        "categories": categories,
        "credit_cards": credit_cards,
        "invoices": invoices,
        "transactions_past": tx_past,
        "transactions_future": tx_future,
        "budgets": budgets,
    }
    snapshot["installments"] = build_installments(snapshot)
    print(f"info|installments|{len(snapshot['installments'])} parcelamentos ativos", file=sys.stderr)
    snapshot["meta"]["totais"] = compute_totals(snapshot)

    out = pathlib.Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2))
    print(f"ok|snapshot|{out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
