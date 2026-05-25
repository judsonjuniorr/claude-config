#!/usr/bin/env python3
"""Sugere limites de gastos por categoria para o mês corrente e o próximo.

Estratégia default:
  - base = max(mediana dos últimos 3 meses, p75 dos últimos 6 meses)
  - mínimo = max(base, realizado_mes_atual)         # nunca sugerir abaixo do já gasto
  - arredonda para cima a múltiplo de R$ 10
  - se categoria não tem histórico suficiente (<2 meses com gasto), mantém atual
  - próximo mês = mesma sugestão (ajuste sazonal futuro)

A API REST do Organizze não expõe PUT/POST de /budgets — este script apenas
gera sugestões. Use --open para abrir a página de metas no Playwright e
aplicar manualmente (rápido); o JSON em ~/finance/organizze/budget-suggestions/
documenta o que aplicar.

Usage:
  suggest_budgets.py --snapshot PATH [--out PATH] [--top N]
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import math
import pathlib
import statistics
import sys
from collections import defaultdict

sys.path.insert(0, str(pathlib.Path(__file__).parent))
from _paths import HOME, BUDGET_SUGGESTIONS as OUT_DIR, migrate_legacy  # noqa: E402

migrate_legacy()


def cents_to_brl(c: int | float | None) -> str:
    if c is None:
        return "R$ 0,00"
    v = int(c) / 100.0
    s = f"{abs(v):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return f"-R$ {s}" if v < 0 else f"R$ {s}"


def round_up_cents(n: int, step_brl: int = 10) -> int:
    step = step_brl * 100
    if n <= 0:
        return 0
    return int(math.ceil(n / step) * step)


def p75(values: list[int]) -> int:
    if not values:
        return 0
    if len(values) == 1:
        return values[0]
    s = sorted(values)
    k = 0.75 * (len(s) - 1)
    lo, hi = int(math.floor(k)), int(math.ceil(k))
    return int(round(s[lo] + (s[hi] - s[lo]) * (k - lo)))


def month_key(d: dt.date) -> str:
    return d.strftime("%Y-%m")


def next_month(d: dt.date) -> tuple[int, int]:
    y, m = d.year, d.month + 1
    if m > 12:
        m, y = 1, y + 1
    return y, m


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--snapshot", required=True)
    ap.add_argument("--out", default=None, help="path do JSON com sugestões (default: ~/finance/organizze/budget-suggestions/YYYY-MM-DD-HHMM.json)")
    ap.add_argument("--top", type=int, default=30, help="máximo de categorias na tabela")
    args = ap.parse_args()

    snap = json.loads(pathlib.Path(args.snapshot).read_text())
    today = dt.date.today()
    cur_y, cur_m = today.year, today.month
    nxt_y, nxt_m = next_month(today)
    cur_key = today.strftime("%Y-%m")

    cats = {c.get("id"): c.get("name") for c in (snap.get("categories") or [])}

    # gastos por (mes, categoria) — só despesas pagas
    by_mc: dict[tuple[str, int], int] = defaultdict(int)
    for t in snap.get("transactions_past") or []:
        if not t.get("paid"):
            continue
        amt = int(t.get("amount_cents") or 0)
        if amt >= 0:  # só despesas
            continue
        d = (t.get("date") or "")[:10]
        try:
            td = dt.date.fromisoformat(d)
        except ValueError:
            continue
        cid = t.get("category_id")
        if cid is None:
            continue
        by_mc[(month_key(td), cid)] += -amt  # positivo

    # últimos 3 e 6 meses (excluindo mês corrente para não enviesar com mês incompleto)
    def months_back(n: int) -> list[str]:
        out = []
        for i in range(1, n + 1):
            y, m = cur_y, cur_m - i
            while m < 1:
                m += 12; y -= 1
            out.append(f"{y:04d}-{m:02d}")
        return out

    last_3 = months_back(3)
    last_6 = months_back(6)

    # orçamento atual do mês corrente (do snapshot — pull pega mês atual + 2)
    current_budget: dict[int, int] = {}
    for b in (snap.get("budgets") or []):
        if b.get("_year") == cur_y and b.get("_month") == cur_m:
            cid = b.get("category_id")
            if cid is not None:
                current_budget[cid] = int(b.get("amount_in_cents") or 0)

    # realizado mês corrente
    realized_cur: dict[int, int] = defaultdict(int)
    for (mk, cid), v in by_mc.items():
        if mk == cur_key:
            realized_cur[cid] = v

    rows = []
    all_cids = set(current_budget) | {cid for (_, cid) in by_mc}
    for cid in all_cids:
        h3 = [by_mc.get((mk, cid), 0) for mk in last_3]
        h6 = [by_mc.get((mk, cid), 0) for mk in last_6]
        nonzero_3 = [v for v in h3 if v > 0]
        nonzero_6 = [v for v in h6 if v > 0]
        if len(nonzero_6) < 2:
            base = current_budget.get(cid, 0)
            confidence = "baixa"
        else:
            med3 = int(statistics.median(nonzero_3)) if nonzero_3 else 0
            p75_6 = p75(nonzero_6)
            base = max(med3, p75_6)
            confidence = "alta" if len(nonzero_6) >= 4 else "média"
        suggested = round_up_cents(max(base, realized_cur.get(cid, 0)), step_brl=10)
        rows.append({
            "category_id": cid,
            "category_name": cats.get(cid) or f"#{cid}",
            "current_budget_cents": current_budget.get(cid, 0),
            "realized_current_month_cents": realized_cur.get(cid, 0),
            "median_3m_cents": int(statistics.median(nonzero_3)) if nonzero_3 else 0,
            "p75_6m_cents": p75(nonzero_6) if nonzero_6 else 0,
            "suggested_cents": suggested,
            "delta_cents": suggested - current_budget.get(cid, 0),
            "confidence": confidence,
            "months_with_spend": len(nonzero_6),
        })

    # ordena por delta absoluto (maiores mudanças primeiro)
    rows.sort(key=lambda r: -abs(r["delta_cents"]))

    # === output: tabela markdown + JSON ===
    md: list[str] = []
    md.append(f"# Sugestão de orçamento — {cur_y}-{cur_m:02d} e {nxt_y}-{nxt_m:02d}")
    md.append("")
    md.append(f"Estratégia: max(mediana 3m, p75 6m), nunca abaixo do realizado do mês atual, arredondado pra cima em R$ 10.")
    md.append("")
    md.append("| Categoria | Atual | Realizado (mês) | Mediana 3m | p75 6m | **Sugerido** | Δ | Confiança |")
    md.append("|---|---:|---:|---:|---:|---:|---:|:---:|")
    for r in rows[: args.top]:
        delta = r["delta_cents"]
        sign = "+" if delta > 0 else ""
        md.append(
            f"| {r['category_name']} "
            f"| {cents_to_brl(r['current_budget_cents'])} "
            f"| {cents_to_brl(r['realized_current_month_cents'])} "
            f"| {cents_to_brl(r['median_3m_cents'])} "
            f"| {cents_to_brl(r['p75_6m_cents'])} "
            f"| **{cents_to_brl(r['suggested_cents'])}** "
            f"| {sign}{cents_to_brl(delta)} "
            f"| {r['confidence']} |"
        )
    md.append("")
    md.append("> A API REST do Organizze não permite atualizar orçamentos via HTTP. ")
    md.append("> Aplique manualmente no app: https://app.organizze.com.br/orcamento")

    payload = {
        "generated_at": dt.datetime.now().isoformat(timespec="seconds"),
        "current_month": {"year": cur_y, "month": cur_m},
        "next_month": {"year": nxt_y, "month": nxt_m},
        "strategy": "max(median_3m, p75_6m) >= realized_current, round up R$10",
        "suggestions": rows,
    }

    out = pathlib.Path(args.out) if args.out else OUT_DIR / f"{dt.datetime.now().strftime('%Y-%m-%d-%H%M')}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2))

    sys.stdout.write("\n".join(md))
    sys.stdout.write("\n")
    print(f"\nok|suggestions|{out}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
