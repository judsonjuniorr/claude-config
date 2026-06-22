#!/usr/bin/env python3
"""Render the financial-analyst prompt from a snapshot.

Usage:
  analyze.py --snapshot PATH [--framework PATH] [--out PATH]

Output: prints a single prompt to stdout (and optionally writes to --out)
that injects the snapshot summary + the system prompt extracted from the
framework markdown. The caller (slash command) delegates this prompt to
the financial-analyst subagent.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import pathlib
import re
import sys
from collections import defaultdict

sys.path.insert(0, str(pathlib.Path(__file__).parent))
from _paths import migrate_legacy  # noqa: E402

migrate_legacy()


def _plugin_root() -> pathlib.Path:
    """Walk up from this script to the plugin root (the dir holding .claude-plugin/).

    More robust than a hardcoded parents[N] count: it keeps resolving even if the
    script moves up or down a directory level. Falls back to parents[2]
    (scripts/organizze/ -> plugin root) if no marker is found.
    """
    here = pathlib.Path(__file__).resolve()
    for d in here.parents:
        if (d / ".claude-plugin").is_dir() or (d / "agents").is_dir():
            return d
    return here.parents[2]


PLUGIN_ROOT = _plugin_root()
DEFAULT_FRAMEWORK = PLUGIN_ROOT / "agents" / "financial-analyst.md"


def cents_to_brl(c: int | float | None) -> str:
    if c is None:
        return "R$ 0,00"
    v = int(c) / 100.0
    s = f"{abs(v):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return f"-R$ {s}" if v < 0 else f"R$ {s}"


def extract_system_prompt(framework_md: str) -> str:
    """Extract the system prompt from financial-analyst.md (body after YAML frontmatter)."""
    lines = framework_md.splitlines()
    # Strip YAML frontmatter (--- ... ---) if present
    if lines and lines[0].strip() == "---":
        end = 1
        while end < len(lines) and lines[end].strip() != "---":
            end += 1
        lines = lines[end + 1 :]
    return "\n".join(lines).strip() or "You are a senior personal financial analyst."


_INVOICE_NAME_RE = re.compile(
    r"(^\s*fatura\b|fatura\s+de\s+cart[aã]o|pagamento\s+de\s+fatura|^\s*invoice\b)",
    re.IGNORECASE,
)


def _is_invoice_category_name(name: str | None) -> bool:
    """True if the category name looks like a credit card invoice payment.

    Used to exclude these categories from the effective spending top list
    (they inflate artificially: the real spend was the card purchase, and
    the invoice is just the corresponding settlement).

    Conservative: only matches clear variations of "fatura" / "pagamento de
    fatura" / "fatura de cartão". Does NOT filter categories like "Cartão
    Refeição" or "Cartão Alimentação" (meal/food vouchers — real effective
    spending)."""
    if not name:
        return False
    return bool(_INVOICE_NAME_RE.search(name))


def top_categories(
    snapshot: dict, month: dt.date | None = None
) -> list[tuple[str, int]]:
    cats = {c.get("id"): c.get("name") for c in snapshot.get("categories") or []}
    totals: dict[str, int] = defaultdict(int)
    target_month = (month or dt.date.today()).strftime("%Y-%m")
    for t in snapshot.get("transactions_past") or []:
        if (t.get("date") or "")[:7] != target_month:
            continue
        amt = int(t.get("amount_cents") or 0)
        if amt >= 0:
            continue  # expenses only
        name = cats.get(t.get("category_id")) or "Uncategorized"
        totals[name] += -amt
    return sorted(totals.items(), key=lambda x: -x[1])[:10]


def top_categories_effective(
    snapshot: dict, month: dt.date | None = None, limit: int = 3
) -> list[tuple[str, int]]:
    """Top N effective spending categories for the month, EXCLUDING categories
    whose name contains 'fatura'/'cartão'/'invoice' (invoice payments, which
    are not new spending)."""
    cats = {c.get("id"): c.get("name") for c in snapshot.get("categories") or []}
    totals: dict[str, int] = defaultdict(int)
    target_month = (month or dt.date.today()).strftime("%Y-%m")
    for t in snapshot.get("transactions_past") or []:
        if (t.get("date") or "")[:7] != target_month:
            continue
        amt = int(t.get("amount_cents") or 0)
        if amt >= 0:
            continue
        name = cats.get(t.get("category_id")) or "Uncategorized"
        if _is_invoice_category_name(name):
            continue
        totals[name] += -amt
    return sorted(totals.items(), key=lambda x: -x[1])[:limit]


def top_transactions_of_category(
    snapshot: dict, cat_name: str, month: dt.date | None = None, limit: int = 5
) -> list[dict]:
    cats = {c.get("id"): c.get("name") for c in snapshot.get("categories") or []}
    target_month = (month or dt.date.today()).strftime("%Y-%m")
    rows: list[dict] = []
    for t in snapshot.get("transactions_past") or []:
        if (t.get("date") or "")[:7] != target_month:
            continue
        amt = int(t.get("amount_cents") or 0)
        if amt >= 0:
            continue
        name = cats.get(t.get("category_id")) or "Uncategorized"
        if name != cat_name:
            continue
        rows.append(t)
    rows.sort(key=lambda x: int(x.get("amount_cents") or 0))
    return rows[:limit]


def category_median_6m(snapshot: dict, cat_name: str) -> int:
    """Monthly median over the last 6 months for the category (in cents, expense)."""
    cats = {c.get("id"): c.get("name") for c in snapshot.get("categories") or []}
    today = dt.date.today()
    months: list[str] = []
    y, m = today.year, today.month
    for _ in range(6):
        m -= 1
        if m == 0:
            m = 12
            y -= 1
        months.append(f"{y:04d}-{m:02d}")
    totals: dict[str, int] = defaultdict(int)
    for t in snapshot.get("transactions_past") or []:
        key = (t.get("date") or "")[:7]
        if key not in months:
            continue
        amt = int(t.get("amount_cents") or 0)
        if amt >= 0:
            continue
        name = cats.get(t.get("category_id")) or "Uncategorized"
        if name != cat_name:
            continue
        totals[key] += -amt
    vals = sorted(totals.values())
    if not vals:
        return 0
    n = len(vals)
    return vals[n // 2] if n % 2 else (vals[n // 2 - 1] + vals[n // 2]) // 2


def top_transactions_of_month(
    snapshot: dict, month: dt.date | None = None, limit: int = 20
) -> list[dict]:
    """Top N expenses of the month ordered by absolute value, excluding invoice
    payment categories (which duplicate card spending)."""
    cats = {c.get("id"): c.get("name") for c in snapshot.get("categories") or []}
    target_month = (month or dt.date.today()).strftime("%Y-%m")
    rows: list[dict] = []
    for t in snapshot.get("transactions_past") or []:
        if (t.get("date") or "")[:7] != target_month:
            continue
        amt = int(t.get("amount_cents") or 0)
        if amt >= 0:
            continue
        name = cats.get(t.get("category_id")) or "Uncategorized"
        if _is_invoice_category_name(name):
            continue
        rows.append(t)
    rows.sort(key=lambda x: int(x.get("amount_cents") or 0))
    return rows[:limit]


def category_delta(snapshot: dict) -> list[tuple[str, int, int, float]]:
    """(category, current_month_cents, previous_month_cents, change_pct)"""
    cats = {c.get("id"): c.get("name") for c in snapshot.get("categories") or []}
    today = dt.date.today()
    prev = today.replace(day=1) - dt.timedelta(days=1)
    cur_key = today.strftime("%Y-%m")
    prev_key = prev.strftime("%Y-%m")
    cur: dict[str, int] = defaultdict(int)
    prv: dict[str, int] = defaultdict(int)
    for t in snapshot.get("transactions_past") or []:
        amt = int(t.get("amount_cents") or 0)
        if amt >= 0:
            continue
        name = cats.get(t.get("category_id")) or "Uncategorized"
        key = (t.get("date") or "")[:7]
        if key == cur_key:
            cur[name] += -amt
        elif key == prev_key:
            prv[name] += -amt
    rows = []
    for name in set(list(cur.keys()) + list(prv.keys())):
        c = cur.get(name, 0)
        p = prv.get(name, 0)
        delta = ((c - p) / p * 100.0) if p else (100.0 if c else 0.0)
        rows.append((name, c, p, delta))
    rows.sort(key=lambda x: -x[1])
    return rows[:10]


def summarize(snapshot: dict) -> str:
    m = snapshot.get("meta", {})
    t = m.get("totais", {})
    accounts = snapshot.get("accounts") or []
    invoices = snapshot.get("invoices") or []
    today = dt.date.today()

    out: list[str] = []
    out.append(f"# Organizze Snapshot — {m.get('pulled_at', '')}")
    out.append(
        f"Period: {m.get('periodo', {}).get('history_start')} → {m.get('periodo', {}).get('future_end')}"
    )
    out.append("")
    out.append("## Consolidated balance and projection")
    out.append(f"- Current balance: **{cents_to_brl(t.get('saldo_cents'))}**")
    out.append(f"- Projection +7d: {cents_to_brl(t.get('saldo_proj_7d_cents'))}")
    out.append(f"- Projection +30d: {cents_to_brl(t.get('saldo_proj_30d_cents'))}")
    out.append(f"- Projection +90d: {cents_to_brl(t.get('saldo_proj_90d_cents'))}")
    out.append("")

    def is_principal(a):
        return not a.get("archived") and a.get("type") in (
            "checking",
            "savings",
            "other",
        )

    out.append("## Balance by main account (included in consolidated)")
    for a in accounts:
        if not is_principal(a):
            continue
        bal = a.get("_balance_cents") or 0
        out.append(f"- {a.get('name')} ({a.get('type')}): {cents_to_brl(bal)}")

    out.append("")
    out.append(
        "## Other accounts (not included in consolidated: savings pots, auxiliary accounts)"
    )
    for a in accounts:
        if a.get("archived") or is_principal(a):
            continue
        bal = a.get("_balance_cents") or 0
        kind = a.get("institution_id") or a.get("type") or "?"
        out.append(f"- {a.get('name')} ({kind}): {cents_to_brl(bal)}")
    out.append("")

    # Card → paying account map (config) to show which account debits each invoice
    try:
        sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
        from config import card_to_account_map  # type: ignore

        _card_map = card_to_account_map()
    except Exception:
        _card_map = {}
    _acc_name_by_id = {a.get("id"): a.get("name") for a in accounts}

    def _inv_amount(inv: dict) -> int:
        return int(inv.get("amount_cents") or inv.get("total_cents") or 0)

    out.append("## Invoices due (next 7 days)")
    n = 0
    for inv in invoices:
        d = (inv.get("date") or "")[:10]
        try:
            due = dt.date.fromisoformat(d)
        except ValueError:
            continue
        amt = _inv_amount(inv)
        if amt == 0:
            continue
        if today <= due <= today + dt.timedelta(days=7):
            out.append(
                f"- {inv.get('_credit_card_name')} · due {d} · {cents_to_brl(amt)}"
            )
            n += 1
    if n == 0:
        out.append("- (none)")
    out.append("")

    # Invoices in the rest of the horizon (8-90d) — included in projected cashflow,
    # but only appear as a nominal driver when the day is critical. Listing them here
    # forces the analyst to size transfers accounting for them even when the
    # post-invoice balance remains positive.
    out.append("## Invoices due on the horizon (8–90 days)")
    out.append(
        "_Already embedded in the projected balance of the paying account. Do not duplicate as an extra debit when recommending transfers — but consider as the LARGEST debit of the month when sizing the paying account's cash._"
    )
    n = 0
    for inv in sorted(invoices, key=lambda x: x.get("date") or ""):
        d = (inv.get("date") or "")[:10]
        try:
            due = dt.date.fromisoformat(d)
        except ValueError:
            continue
        amt = _inv_amount(inv)
        if amt == 0:
            continue
        if today + dt.timedelta(days=8) <= due <= today + dt.timedelta(days=90):
            cid = inv.get("credit_card_id") or inv.get("_credit_card_id")
            pay_acc_id = _card_map.get(cid) if cid is not None else None
            pay_acc = (
                _acc_name_by_id.get(pay_acc_id, "⚠️ no paying account mapped")
                if pay_acc_id
                else "⚠️ no paying account mapped"
            )
            out.append(
                f"- {inv.get('_credit_card_name')} · due {d} · {cents_to_brl(amt)} · debits from **{pay_acc}**"
            )
            n += 1
    if n == 0:
        out.append("- (none)")
    out.append("")

    out.append("## Top 10 categories — current month")
    tops = top_categories(snapshot)
    if not tops:
        out.append("- (no expenses in the current month)")
    else:
        for name, amt in tops:
            out.append(f"- {name}: {cents_to_brl(amt)}")
    out.append("")

    out.append("## Category change — current vs. previous month")
    for name, c, p, delta in category_delta(snapshot):
        sign = "+" if delta >= 0 else ""
        out.append(
            f"- {name}: {cents_to_brl(c)} (previous {cents_to_brl(p)}, {sign}{delta:.1f}%)"
        )
    out.append("")

    out.append("## Detected recurring transactions")
    rec = [
        t for t in (snapshot.get("transactions_past") or []) if t.get("is_recurring")
    ]
    by_payee: dict[str, tuple[int, int]] = {}  # payee -> (count, sum)
    for t in rec:
        p = t.get("description") or "?"
        c, s = by_payee.get(p, (0, 0))
        by_payee[p] = (c + 1, s + int(t.get("amount_cents") or 0))
    for payee, (c, s) in sorted(by_payee.items(), key=lambda x: -x[1][0])[:15]:
        out.append(f"- {payee}: {c}x · total {cents_to_brl(s)}")
    if not by_payee:
        out.append("- (none identified)")
    out.append("")

    # === Past transactions NOT PAID (overdue) ===
    out.append("## ⚠️ Overdue transactions (past, NOT paid)")
    overdue = [
        t
        for t in (snapshot.get("transactions_past") or [])
        if not t.get("paid") and t.get("credit_card_id") is None
    ]
    overdue.sort(key=lambda x: x.get("date") or "")
    if not overdue:
        out.append("- (none)")
    else:
        for t in overdue[:40]:
            d = (t.get("date") or "")[:10]
            amt = int(t.get("amount_cents") or 0)
            tag = "OVERDUE INCOME" if amt > 0 else "OVERDUE EXPENSE"
            out.append(
                f"- {d} · {tag} · {t.get('description') or '?'} · {cents_to_brl(amt)}"
            )
        tot = snapshot.get("meta", {}).get("totais", {})
        out.append(
            f"\nSummary: {tot.get('n_atrasadas_despesa', 0)} expenses (total {cents_to_brl(-tot.get('soma_atrasadas_despesa_cents', 0))}), "
            f"{tot.get('n_atrasadas_receita', 0)} income (total {cents_to_brl(tot.get('soma_atrasadas_receita_cents', 0))}) — should be paid/collected as soon as possible."
        )
    out.append("")

    # === Active installments ===
    out.append("## Active installments")
    insts = snapshot.get("installments") or []
    if not insts:
        out.append("- (none)")
    else:
        out.append(
            "| Description | Progress | Avg installment | Remaining | Amount left | Expected end | Status |"
        )
        out.append("|---|:---:|---:|:---:|---:|:---:|:---|")
        for r in insts[:25]:
            status_parts = []
            if r.get("almost_done"):
                status_parts.append("**almost done**")
            if r.get("long_way"):
                status_parts.append("**long way to go**")
            status = ", ".join(status_parts) or "—"
            out.append(
                f"| {r['description'][:50]} "
                f"| {r['paid']}/{r['total_installments']} ({r['progress_pct']}%) "
                f"| {cents_to_brl(r['avg_amount_cents'])} "
                f"| {r['remaining']} "
                f"| {cents_to_brl(r['remaining_amount_cents'])} "
                f"| {r.get('expected_end_date') or '?'} "
                f"| {status} |"
            )
    out.append("")

    out.append("## Confirmed future entries (next 30 days)")
    n = 0
    for t in (snapshot.get("transactions_future") or [])[:50]:
        d = (t.get("date") or "")[:10]
        try:
            td = dt.date.fromisoformat(d)
        except ValueError:
            continue
        if today < td <= today + dt.timedelta(days=30):
            out.append(
                f"- {d}: {t.get('description') or '?'} · {cents_to_brl(t.get('amount_cents'))}"
            )
            n += 1
    if n == 0:
        out.append("- (none)")
    out.append("")

    # === Cash flow per account — daily projection + critical days ===
    cf_block = render_cashflow_block(snapshot)
    if cf_block:
        out.append(cf_block)
        out.append("")

    # === Top 20 transactions of the month (effective spending, ex-card invoices) ===
    out.append(
        "## Top 20 transactions of the current month (expenses, ex-invoice payments)"
    )
    out.append("")
    out.append(
        "Use this table to suggest merchant-level cuts/substitutions "
        "(non-negotiable rule `[CUT]`). Each line is a real expense of the month "
        "— card purchases appear here (categories labelled "
        "'Invoice/Card' have been filtered to avoid duplication)."
    )
    out.append("")
    cats = {c.get("id"): c.get("name") for c in snapshot.get("categories") or []}
    accounts_by_id = {
        a.get("id"): a.get("name") for a in snapshot.get("accounts") or []
    }
    cards_by_id = {
        c.get("id"): c.get("name") for c in snapshot.get("credit_cards") or []
    }
    top_tx = top_transactions_of_month(snapshot)
    if not top_tx:
        out.append("- (no expenses in the current month)")
    else:
        out.append(
            "| Date | Description | Category | Source | Amount | Paid? | Recurring? |"
        )
        out.append("|---|---|---|---|---:|:---:|:---:|")
        for t in top_tx:
            d = (t.get("date") or "")[:10]
            desc = (t.get("description") or "?").replace("|", "/")[:48]
            cat_name = cats.get(t.get("category_id")) or "Uncategorized"
            if t.get("credit_card_id"):
                origin = f"💳 {cards_by_id.get(t.get('credit_card_id')) or '?'}"
            else:
                origin = accounts_by_id.get(t.get("account_id")) or "?"
            amt = cents_to_brl(t.get("amount_cents"))
            paid = "✓" if t.get("paid") else "✗"
            rec = "✓" if t.get("is_recurring") else ""
            out.append(
                f"| {d} | {desc} | {cat_name} | {origin} | {amt} | {paid} | {rec} |"
            )
    out.append("")

    # === Target categories for market research (top 3 ex-invoices) ===
    out.append("## Target categories for market research (TARGET-WEBSEARCH)")
    out.append("")
    out.append(
        "Top 3 effective spending categories of the month (excluding invoice "
        "payments). **For each one, you MUST run 1 `WebSearch` "
        "looking for cheaper alternatives considering the `cidade` from "
        "the user profile** (non-negotiable rule 14). Present the result "
        "in the 'Market alternatives' section of the report with URL + price "
        "found. If no reasonable alternative exists, mark "
        "`(no alternative found)`."
    )
    out.append("")
    targets = top_categories_effective(snapshot, limit=3)
    if not targets:
        out.append("- (no effective spending categories in the current month)")
    else:
        for cat_name, total in targets:
            median = category_median_6m(snapshot, cat_name)
            out.append(f"### TARGET-WEBSEARCH: {cat_name}")
            out.append(
                f"- Month total: **{cents_to_brl(total)}** · "
                f"6m median: {cents_to_brl(median)}"
            )
            top5 = top_transactions_of_category(snapshot, cat_name, limit=5)
            if top5:
                out.append("- Top 5 transactions in this category this month:")
                for t in top5:
                    d = (t.get("date") or "")[:10]
                    desc = (t.get("description") or "?")[:60]
                    out.append(
                        f"  - {d} · {desc} · {cents_to_brl(t.get('amount_cents'))}"
                    )
            out.append("")
    out.append("")

    out.append("## Current month budget (targets vs. actuals)")
    cur_key_y = today.year
    cur_key_m = today.month
    cats = {c.get("id"): c.get("name") for c in snapshot.get("categories") or []}
    rows = []
    for b in snapshot.get("budgets") or []:
        if b.get("_year") != cur_key_y or b.get("_month") != cur_key_m:
            continue
        name = cats.get(b.get("category_id")) or b.get("name") or "?"
        budget = int(b.get("amount_in_cents") or b.get("amount_cents") or 0)
        spent = int(b.get("total_in_cents") or b.get("total_cents") or 0)
        if budget == 0 and spent == 0:
            continue
        pct = (spent / budget * 100.0) if budget else 0.0
        rows.append((name, spent, budget, pct))
    for name, spent, budget, pct in sorted(rows, key=lambda x: -x[3])[:15]:
        out.append(
            f"- {name}: {cents_to_brl(spent)} / {cents_to_brl(budget)} ({pct:.0f}%)"
        )
    if not rows:
        out.append("- (no budget targets defined)")

    return "\n".join(out)


_SHARED_SCRIPTS = pathlib.Path(__file__).resolve().parent.parent / "scripts"


def load_memory_block() -> str:
    """Read ~/finance/memory.md and return a rendered block for injection."""
    mem_path = pathlib.Path.home() / "finance" / "memory.md"
    if not mem_path.exists():
        return ""
    import subprocess

    script = _SHARED_SCRIPTS / "memory.py"
    try:
        r = subprocess.run(
            ["python3", str(script), "render"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        return r.stdout.strip()
    except Exception:
        return ""


def load_profile_block() -> str:
    """Read ~/finance/profile.md and return a rendered block for injection.

    Always renders something: if the profile does not exist, shows the block with
    all fields marked (no data) — this signals the subagent to emit [QUESTION]
    in the final report."""
    import subprocess

    script = _SHARED_SCRIPTS / "profile.py"
    try:
        r = subprocess.run(
            ["python3", str(script), "render"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        return r.stdout.strip()
    except Exception:
        return ""


def load_plans_block() -> str:
    """Read ~/finance/plans.md and return a rendered block for injection."""
    plans_path = pathlib.Path.home() / "finance" / "plans.md"
    if not plans_path.exists():
        return ""
    import subprocess

    script = _SHARED_SCRIPTS / "plans.py"
    try:
        r = subprocess.run(
            ["python3", str(script), "render"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        return r.stdout.strip()
    except Exception:
        return ""


def list_research_targets(snapshot: dict, limit: int = 3) -> list[dict]:
    """Return the N target categories for parallel market research.

    Each item: {name, total_cents, median_6m_cents, top_txs: [(date, desc, amount_cents), ...]}.
    Excludes invoice payment categories (filter `_is_invoice_category_name`)."""
    targets = top_categories_effective(snapshot, limit=limit)
    out: list[dict] = []
    for name, total in targets:
        top5 = top_transactions_of_category(snapshot, name, limit=5)
        out.append(
            {
                "name": name,
                "total_cents": total,
                "median_6m_cents": category_median_6m(snapshot, name),
                "top_txs": [
                    {
                        "date": (t.get("date") or "")[:10],
                        "description": t.get("description") or "?",
                        "amount_cents": int(t.get("amount_cents") or 0),
                    }
                    for t in top5
                ],
            }
        )
    return out


def _profile_city() -> str:
    """Read cidade from profile; '(no data)' if empty."""
    import subprocess

    script = _SHARED_SCRIPTS / "profile.py"
    try:
        r = subprocess.run(
            ["python3", str(script), "get", "cidade"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        v = (r.stdout or "").strip()
        return v if v else "(no data)"
    except Exception:
        return "(no data)"


def render_list_targets(snapshot: dict) -> str:
    """Pipe-delimited output for consumption by organizze.md (parallel dispatch)."""
    city = _profile_city()
    lines: list[str] = [f"profile|cidade|{city}"]
    for tgt in list_research_targets(snapshot):
        top_str = "; ".join(
            f"{t['description']} ({cents_to_brl(t['amount_cents'])})"
            for t in tgt["top_txs"]
        )
        lines.append(
            f"target|{tgt['name']}|{tgt['total_cents']}|"
            f"{tgt['median_6m_cents']}|{top_str}"
        )
    return "\n".join(lines)


def load_research_block(research_dir: pathlib.Path | None) -> str:
    """Read `<slug>.md` files in `research_dir/` (results pre-collected by
    parallel search-specialist agents) and return a markdown block ready to
    append to the analyst prompt.

    Each file is a research report for one category. Shows mtime (ISO) of
    each file so the subagent knows whether it is fresh or reused from cache.
    """
    if not research_dir or not research_dir.exists():
        return ""
    files = sorted(research_dir.glob("*.md"))
    if not files:
        return ""
    today = dt.date.today()
    out: list[str] = []
    out.append("# Market research (PRE-COLLECTED — DO NOT REDO WebSearch)")
    out.append("")
    out.append(
        "Each category below was researched by a dedicated "
        "`search-specialist` agent, BEFORE this analysis. Recent searches "
        "are reused from cache (TTL ~14 days) — the collection date "
        "is in the header of each block. **Consume these "
        "results** in the 'Market alternatives' section of the report."
    )
    out.append("")
    for f in files:
        try:
            mtime = dt.date.fromtimestamp(f.stat().st_mtime)
            age = (today - mtime).days
            age_str = f"today" if age == 0 else f"{age}d ago"
            out.append(f"## {f.stem} _(collected on {mtime.isoformat()} · {age_str})_")
        except OSError:
            out.append(f"## {f.stem}")
        out.append("")
        out.append(f.read_text().strip())
        out.append("")
    return "\n".join(out)


def find_cached_research(category: str, max_age_days: int = 14) -> pathlib.Path | None:
    """Search for the most recent `<category>.md` file across all historical
    research dirs (`~/finance/organizze/research/*/`). Returns path if mtime <=
    max_age_days, otherwise None.

    Comparison is by literal name — organizze.md writes each report with the
    exact category name (`Alimentação.md`, `Transporte.md`), so a hit here
    means fresh research for that specific category.
    """
    base = pathlib.Path.home() / "finance" / "organizze" / "research"
    if not base.exists():
        return None
    cutoff = dt.datetime.now().timestamp() - max_age_days * 86400
    candidates: list[tuple[float, pathlib.Path]] = []
    for snap_dir in base.iterdir():
        if not snap_dir.is_dir():
            continue
        f = snap_dir / f"{category}.md"
        if not f.exists():
            continue
        try:
            mt = f.stat().st_mtime
        except OSError:
            continue
        if mt >= cutoff:
            candidates.append((mt, f))
    if not candidates:
        return None
    candidates.sort(reverse=True)
    return candidates[0][1]


def render_cashflow_block(snapshot: dict) -> str:
    """Run cashflow.per_account_projection and return ready markdown."""
    try:
        sys.path.insert(0, str(pathlib.Path(__file__).parent))
        from cashflow import per_account_projection, render_markdown
        from config import threshold_cents

        proj = per_account_projection(
            snapshot, threshold_cents=threshold_cents(), horizon_days=90
        )
        return render_markdown(proj).strip()
    except Exception as e:
        return f"## Cash flow per account\n_(error computing projection: {e})_"


def render_prompt(
    snapshot: dict, framework_md: str, research_dir: pathlib.Path | None = None
) -> str:
    system = extract_system_prompt(framework_md)
    summary = summarize(snapshot)
    profile_block = load_profile_block()
    memory_block = load_memory_block()
    plans_block = load_plans_block()
    research_block = load_research_block(research_dir)
    profile_section = f"\n---\n\n{profile_block}\n" if profile_block else ""
    memory_section = f"\n---\n\n{memory_block}\n" if memory_block else ""
    plans_section = f"\n---\n\n{plans_block}\n" if plans_block else ""
    research_section = f"\n---\n\n{research_block}\n" if research_block else ""

    # List of existing account names (for transfer guardrail)
    existing_accounts = [
        a.get("name")
        for a in (snapshot.get("accounts") or [])
        if not a.get("archived") and a.get("type")
    ]
    accounts_hint = ", ".join(f"`{n}`" for n in existing_accounts if n) or "(none)"

    return f"""{system}
{profile_section}{memory_section}{plans_section}{research_section}
---

# Consolidated data (Organizze)

{summary}

---

# Mandatory guidelines

1. **Budget targets by category**: Organizze already defines a budget per category (section "Current month budget"). Your analysis MUST prioritize hitting those targets — highlight categories above 80% of budget as risk and categories well below as reallocation opportunities.

2. **User objectives** (section above, if any): evaluate ad-hoc whether there is room in the month for each objective from the **current balance + tx_future**, without assuming a fixed monthly contribution. For each `active` objective state clearly: "viable this month: YES/NO/PARTIAL — R$ X possible", with numerical justification.

3. **Objective vs. imminent debit conflict**: if any critical day appears in any main account (section "Cash flow per account"), **pause objectives with priority=negociavel this cycle** and name them explicitly in "Paused objectives". Objectives with priority=inegociavel must be maintained by cutting spending in other categories.

4. **Inter-account transfers (STRICT GUARDRAIL)**: accounts that EXIST in this snapshot: {accounts_hint}. Every transfer suggestion must name **two of these accounts** and cover a specific debit with a date. If the user's objective cites a target account NOT in the list above, do NOT invent: say "reserve R$ X for Y" without naming an account.

5. **Day-by-day source balance (CRITICAL RULE)**: when suggesting a transfer from account A to account B on date D, **account A must have balance ≥ suggested amount on D AND remain ≥ 0 until the end of the projected horizon** (not just D — needs to cover D, D+1, …, until the last confirmed debit of account A in the cycle). Use the "Cash flow per account" section to validate — if day D appears with `❌ no main account with sufficient slack`, or the `accounts with slack on that day` list does not include A with sufficient amount, or A has a confirmed future debit (financing, invoice, automatic debit) between D and the end of the horizon that overdraws the post-transfer balance, **DO NOT suggest that transfer**. Instead:
   (a) delay the transfer to the first date on which A has sustainable slack (e.g.: after a confirmed salary/income entry AND before the next large debit);
   (b) propose renegotiating/deferring the destination account's debit to after the next income entry;
   (c) suggest reordering the month's payments to fit the cash flow.
   Always cite **the source balance on the date AND the projected source balance at end of cycle** ("<source account> on DD/MM: R$ X · end of cycle: R$ Y") as evidence. Mentally redoing the day-by-day math is MANDATORY — do not just rely on "slack on that day" from the snapshot, because the `accounts with slack on that day` column shows the balance ON THE DATE, without subtracting confirmed future debits.

5b. **Existing recurring transfer is the default — DO NOT duplicate** (CRITICAL RULE). Before suggesting ANY inter-account transfer, check the "Confirmed future entries" and "Detected recurring transactions" sections to identify already-scheduled recurring transfers (e.g.: monthly allocation between salary account and operating account, or recurring contributions to savings pots). If the recurring transfer already covers the destination account balance in the cycle (destination projected ≥ 0 without additional contribution), **do not recommend extra transfers** — they are redundant and drain the source account which is counting on that cash for its own debits. Cite explicitly: "recurring transfer of R$ X on <date> already covers <destination account> — no additional contribution needed". Critical days on the destination account may be false positives when `cashflow_by_account` does not match the transfer credit with the debit on the other side — always validate by redoing the destination day-by-day WITH the internal transfer credits on the same day they leave the source.

6. **Due date renegotiation (use when cash flow does not close)**: if a recurring debit consistently falls on a date with no cash (e.g.: subscription on day 5 when salary arrives on day 6), recommend **changing the due date** or **changing the payment method** (bank debit → card, prepay bill, etc.). Include in format:
   `[RENEGOTIATE · <creditor>] Move due date from <current date> to <suggested date> — reason: cash on <current date> is R$ X, insufficient for debit of R$ Y`.

7. **Tone**: no fluff, no hedging. Numbers first, recommendation after.

8. **Personalization via profile (CRITICAL)**: the "User profile" block at the top has age, income, dependents, housing, city, risk tolerance. **Every recommendation cites at least one profile field**. Ex.: "for someone with `2 small children` in `São Paulo, SP` financing a home (`R$ 2,500/month`), suggested minimum reserve = 6 months of expenses (~R$ X)". If any critical field is `(no data)`, emit a `[QUESTION]` in the final block.

9. **Merchant-level cuts (3-5 mandatory)**: using the "Top 20 transactions of the current month" table, identify 3-5 specific transactions to cut/substitute. Each item in format `[CUT] <merchant/description> · R$ X/month → alternative Y · savings R$ Z/month · R$ Z*12/year`. Use the real `description` from the snapshot, do not invent merchant names.

10. **Market research — CONSUME, DO NOT REDO.** The command that invoked you dispatched `search-specialist` agents in parallel (1 per target category) BEFORE this analysis; the results are in the "Market research (PRE-COLLECTED)" block above — if that block exists, **use it** in the 'Market alternatives' section (cite URLs and prices directly from it, do not invoke WebSearch). **Use WebSearch only as fallback** when that block is absent OR does not cover a specific target category — in that case run at most 1 extra search per discovered category. No useful source = `(no alternative found)`.

11. **Prioritized payoff**: list installments and debts detectable in the snapshot ordered by chosen strategy: **avalanche** (highest interest/payment first — rational, saves more) or **snowball** (lowest balance first — psychological, motivating). Choose by `tolerancia_risco` from profile (`conservador`/`moderado` → snowball; `agressivo` → avalanche). Respect user memory (do not propose paying off items marked "non-negotiable" or "essential").

12. **Open questions (final block)**: at the end of the report, list **up to 3 concrete questions** that would improve the next analysis, in the exact format `[QUESTION] <question text>` (one per line, no bullets or hyphens in front). Examples: "[QUESTION] Do you have any debt outside Organizze (financing, family loan)?", "[QUESTION] Is subscription X of R$ Y essential?". The command that invoked you will capture these questions and bring them to the user. No questions? Write only: `(no open questions)`.

---

# Task — produce EXACTLY this format

**TL;DR** (3 lines): current situation + nearest risk + biggest opportunity.

**Key numbers** (markdown table): current balance, 7/30/90d projection, % committed to recurring,
active installments (total remaining), overdue (expense/income), largest category this month, nearest invoice, number of critical days per account.

**Overdue — immediate action** (≤3 bullets): for each relevant overdue transaction, indicate
"pay/collect by <date>".

**Category targets — status** (≤5 bullets): categories at risk (>80% spent) and categories with relevant slack. Use numbers from the "Current month budget" section.

**User objectives — viability this month** (1 bullet per active objective): short name · viable YES/NO/PARTIAL · amount possible this month · justification in 1 line. If no active objectives, write "(no active objectives)".

**Transfer and savings plan** (≤5 bullets): for each relevant critical day OR viable objective, format:
```
[CRITICAL · on <date>] Transfer R$ X from "<source account>" to "<destination account>"
  Source balance on <date>: R$ Y  ← mandatory, must be ≥ X
  Reason: <specific debit on <date> leaves destination at <amount>>
```
or
```
[RENEGOTIATE · <creditor>] Move due date/payment method from <current date> to <suggested date>
  Cash on <current date>: R$ Y (insufficient for debit R$ Z)
  Target: fit debit on a date with slack ≥ R$ Z
```
or
```
[SAVINGS · this month] Reserve R$ X for "<destination account if it exists>" OR "<objective Y>" if account not registered
  Source: <account with slack or monthly surplus>
```
**Rules**: (a) only use accounts from the existing list; (b) never suggest transfer from account A on date D if the "Cash flow per account" section indicates A has no slack on D; (c) when no account has slack on the critical day, prefer `[RENEGOTIATE]` over `[CRITICAL]`. If no clear action, write "(no transfer actions needed)".

**Paused objectives this cycle** (≤3 bullets, omit if empty): objective name + reason (critical day on <date> or category target at risk).

**Installments — actionable view** (≤5 bullets): highlight those that are "almost done" and those "long way to go". Do not suggest renegotiating installments that user memory explicitly excludes.

**Specific cuts suggested** (3-5 items, format `[CUT]`): using the "Top 20 transactions of the current month" and "Detected recurring transactions" tables, identify cuttable or substitutable spending. Exact format:
```
[CUT] <description/merchant from snapshot> · R$ X/month
  Alternative: <concrete substitute>
  Savings: R$ Z/month · R$ Z*12/year
  Justification: <1 line citing profile or memory>
```
If nothing to cut (profile already lean), write `(no cuts recommended — spending already aligned with profile)` and explain why in 1 line.

**Prioritized payoff** (ordered list, 1 line per item): for each installment/debt detectable in the snapshot, order by chosen strategy (avalanche or snowball) and cite the first line justifying the choice by the `tolerancia_risco` from the profile. Format:
```
Strategy: avalanche|snowball — chosen by profile tolerance `<value>`.
1. <installment/debt description> · R$ X remaining · <N installments left> · priority <Y>
2. ...
```
If no eligible debts (zero active installments), write `(no eligible debts for accelerated payoff)`.

**Market alternatives** (1 block per `TARGET-WEBSEARCH` category): for each of the top 3 categories, show the WebSearch result. Format:
```
### <Category>: <cheapest option found> · ~R$ X/month
  Source: <URL>
  Potential savings vs. current: R$ Z/month
  Note: <caveat if applicable, e.g.: 'price varies by neighborhood'>
```
If WebSearch returned nothing useful, write `(no alternative found for <category>)`.

**3 prioritized recommendations** in format:
```
[HIGH/MEDIUM IMPACT · LOW/MEDIUM EFFORT] <short title>
  Savings/gain: <monthly · annual amount>
  Evidence: <specific transactions/categories from the data above>
  Action: <concrete step>
  Why for you: <reference to profile — age, income, dependents, housing, etc.>
```
Never propose something that contradicts user memory or creates a new account.

**Next verifiable steps** (≤3 bullets).

**Open questions** (up to 3, exact format `[QUESTION] <text>` — one per line, no hyphen/bullet): if any critical personal data is missing from the profile OR if there is ambiguity about a specific expense/debt, ask here. The command that invoked you will bring these questions to the user and record the answers for the next analysis. No questions → write `(no open questions)`.

End with the disclaimer: "This is not licensed financial advice."
"""


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--snapshot",
        required=False,
        help="required except when using --research-cache-lookup",
    )
    ap.add_argument("--framework", default=str(DEFAULT_FRAMEWORK))
    ap.add_argument("--out", default=None)
    ap.add_argument(
        "--research-dir",
        default=None,
        help="dir with pre-collected research reports (1 .md per category)",
    )
    ap.add_argument(
        "--list-targets",
        action="store_true",
        help="only prints the 3 target categories (pipe-delimited) and exits — "
        "consumed by organizze.md to dispatch agents in parallel",
    )
    ap.add_argument(
        "--research-cache-lookup",
        metavar="CATEGORY",
        help="searches for a recent report for the category in historical research dirs; "
        "prints path if hit, empty if miss. Does not need --snapshot.",
    )
    ap.add_argument(
        "--max-age-days", type=int, default=14, help="research cache TTL (default 14)"
    )
    ap.add_argument("--dry-run", action="store_true", help="only prints the prompt")
    args = ap.parse_args()

    if args.research_cache_lookup:
        hit = find_cached_research(args.research_cache_lookup, args.max_age_days)
        if hit:
            sys.stdout.write(str(hit) + "\n")
        return 0

    if not args.snapshot:
        print(
            "err|missing-arg|--snapshot is required (except --research-cache-lookup)",
            file=sys.stderr,
        )
        return 2

    snap = json.loads(pathlib.Path(args.snapshot).read_text())

    if args.list_targets:
        sys.stdout.write(render_list_targets(snap) + "\n")
        return 0

    fw_path = pathlib.Path(args.framework)
    if fw_path.exists():
        fw = fw_path.read_text()
    else:
        # Never silently drop the framework: a missing file here means an explicit
        # bad --framework (the default always resolves). Warn loudly, then degrade
        # to the generic system prompt rather than aborting the whole analysis.
        print(
            f"warn|framework-missing|{fw_path} — using generic system prompt",
            file=sys.stderr,
        )
        fw = ""
    research_dir = pathlib.Path(args.research_dir) if args.research_dir else None
    prompt = render_prompt(snap, fw, research_dir=research_dir)

    if args.out:
        pathlib.Path(args.out).write_text(prompt)
        print(f"ok|prompt|{args.out}")
    else:
        sys.stdout.write(prompt)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
