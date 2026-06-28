#!/usr/bin/env python3
"""Deterministic metrics engine for herow-finance.

Usage:
  compute.py --snapshot PATH [--out PATH]
  compute.py --snapshot PATH --query "quanto gastei em alimentação"
  compute.py --compare-months N

Reads a SANITIZED snapshot (output of sanitize.py). Computes all metrics
deterministically — the LLM interprets pre-computed facts, never recalculates.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import pathlib
import re
import sys
import unicodedata
from typing import Optional, TypedDict

SCRIPTS_DIR = pathlib.Path(__file__).parent
_DEFAULT_LOGS_DIR = pathlib.Path.home() / "finance" / "logs"
_DEFAULT_OUT = pathlib.Path.home() / "finance" / "organizze" / "metrics.json"


# ---------------------------------------------------------------------------
# TypedDict schema
# ---------------------------------------------------------------------------

class MetricsAlert(TypedDict):
    category: str
    mtd_cents: int
    historical_avg_cents: int
    pct_over: float


class MetricsOutput(TypedDict):
    monthly_expenses_cents: int
    monthly_income_cents: int
    liquid_balance_cents: int
    burn_cents: int           # monthly_expenses - monthly_income; positive = overspending
    runway_days: Optional[int]  # None when burn <= 0
    category_totals: dict     # {category_name: total_cents} for current month expenses
    top_5_recurring: list     # [{description, amount_cents, occurrences}]
    meta: dict                # {alerts: list[MetricsAlert], computed_at: str, month: str}


# ---------------------------------------------------------------------------
# YAML parser (stdlib only, same as sanitize.py)
# ---------------------------------------------------------------------------

def _load_yaml_simple(path: pathlib.Path) -> dict:
    """Minimal YAML parser for simple key: value, list, and nested dict structures."""
    if not path.exists():
        return {}

    result: dict = {}
    current_key: Optional[str] = None

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        stripped = raw_line.strip()
        if not stripped or stripped.startswith("#"):
            continue

        indent = len(raw_line) - len(raw_line.lstrip())

        if indent == 0:
            if ":" not in stripped:
                continue
            idx = stripped.index(":")
            key = stripped[:idx].strip().strip('"').strip("'")
            rest = stripped[idx + 1 :].strip()
            if "#" in rest:
                rest = rest[: rest.index("#")].strip()

            if rest == "" or rest == "{}":
                current_key = key
                result.setdefault(key, {})
            elif rest == "[]":
                current_key = key
                result[key] = []
            else:
                current_key = key
                val_raw = rest.strip('"').strip("'")
                try:
                    if "." in val_raw:
                        result[key] = float(val_raw)
                    else:
                        result[key] = int(val_raw)
                except ValueError:
                    result[key] = val_raw
        else:
            if current_key is None:
                continue
            if stripped.startswith("- "):
                val = stripped[2:].strip().strip('"').strip("'")
                if not isinstance(result.get(current_key), list):
                    result[current_key] = []
                result[current_key].append(val)
            elif ":" in stripped:
                idx = stripped.index(":")
                k = stripped[:idx].strip().strip('"').strip("'")
                v = stripped[idx + 1 :].strip().strip('"').strip("'")
                if not isinstance(result.get(current_key), dict):
                    result[current_key] = {}
                result[current_key][k] = v

    return result


def _load_enrichment_rules() -> dict:
    return _load_yaml_simple(SCRIPTS_DIR / "enrichment_rules.yaml")


# ---------------------------------------------------------------------------
# Normalization
# ---------------------------------------------------------------------------

def _normalize(text: str) -> str:
    """NFKD normalization: strip accents, lowercase."""
    return (
        unicodedata.normalize("NFKD", text)
        .encode("ascii", "ignore")
        .decode()
        .lower()
        .strip()
    )


# ---------------------------------------------------------------------------
# QUERY_MAP
# ---------------------------------------------------------------------------

QUERY_MAP: list[tuple[re.Pattern, str]] = [
    (re.compile(r"gastei|gasto|despesa"), "monthly_expenses_cents"),
    (re.compile(r"receita|renda|ganh"), "monthly_income_cents"),
    (re.compile(r"saldo"), "liquid_balance_cents"),
    (re.compile(r"runway|meses"), "runway_days"),
    (re.compile(r"(?:em|de)\s+(\w+)"), "category"),  # special: extract category name
]


# ---------------------------------------------------------------------------
# Helper: account is principal
# ---------------------------------------------------------------------------

def _is_principal(acc: dict) -> bool:
    if acc.get("archived"):
        return False
    return acc.get("type") in ("checking", "savings", "other")


# ---------------------------------------------------------------------------
# Core computation
# ---------------------------------------------------------------------------

def compute_metrics(
    snapshot: dict,
    logs_dir: Optional[pathlib.Path] = None,
    alert_threshold_pct: Optional[int] = None,
) -> MetricsOutput:
    """Compute all deterministic metrics from a sanitized snapshot.

    Args:
        snapshot: Sanitized Organizze snapshot dict.
        logs_dir: Directory for historical JSONL files (default: ~/finance/logs/).
        alert_threshold_pct: Override CP1 alert threshold (default: from enrichment_rules.yaml).

    Returns:
        MetricsOutput with all pre-computed metrics.
    """
    rules = _load_enrichment_rules()
    if alert_threshold_pct is None:
        alert_threshold_pct = int(rules.get("alert_threshold_pct") or 120)

    today = dt.date.today()
    current_month = today.strftime("%Y-%m")

    cats = {c.get("id"): c.get("name") for c in snapshot.get("categories") or []}

    # Monthly expenses and income (current month, paid transactions)
    monthly_expenses_cents = 0
    monthly_income_cents = 0
    category_totals: dict[str, int] = {}

    for t in snapshot.get("transactions_past") or []:
        date_str = (t.get("date") or "")[:7]
        if date_str != current_month:
            continue
        amt = int(t.get("amount_cents") or 0)
        if amt < 0:
            monthly_expenses_cents += -amt
            cat_name = cats.get(t.get("category_id")) or "Uncategorized"
            category_totals[cat_name] = category_totals.get(cat_name, 0) + (-amt)
        elif amt > 0:
            monthly_income_cents += amt

    # Liquid balance: sum of principal accounts
    liquid_balance_cents = sum(
        int(a.get("_balance_cents") or 0)
        for a in (snapshot.get("accounts") or [])
        if _is_principal(a)
    )

    # Burn and runway
    burn_cents = monthly_expenses_cents - monthly_income_cents
    runway_days: Optional[int]
    if burn_cents <= 0:
        runway_days = None
    else:
        runway_days = round(liquid_balance_cents / burn_cents * 30)

    # Top 5 recurring transactions
    recurring_txs = [
        t for t in (snapshot.get("transactions_past") or []) if t.get("is_recurring")
    ]
    # Group by description, sum amounts
    rec_by_desc: dict[str, dict] = {}
    for t in recurring_txs:
        desc = (t.get("description") or "?").strip()
        amt = abs(int(t.get("amount_cents") or 0))
        if desc not in rec_by_desc:
            rec_by_desc[desc] = {"description": desc, "amount_cents": amt, "occurrences": 0}
        rec_by_desc[desc]["occurrences"] += 1
        rec_by_desc[desc]["amount_cents"] = max(rec_by_desc[desc]["amount_cents"], amt)

    top_5_recurring = sorted(
        rec_by_desc.values(), key=lambda x: -x["amount_cents"]
    )[:5]

    # CP1 alerts
    if logs_dir is None:
        logs_dir = _DEFAULT_LOGS_DIR
    alerts = compute_alerts(category_totals, logs_dir=logs_dir, threshold_pct=alert_threshold_pct)

    return MetricsOutput(
        monthly_expenses_cents=monthly_expenses_cents,
        monthly_income_cents=monthly_income_cents,
        liquid_balance_cents=liquid_balance_cents,
        burn_cents=burn_cents,
        runway_days=runway_days,
        category_totals=category_totals,
        top_5_recurring=list(top_5_recurring),
        meta={
            "alerts": alerts,
            "computed_at": dt.datetime.now().isoformat(timespec="seconds"),
            "month": current_month,
        },
    )


def validate_metrics(metrics: dict) -> list[str]:
    """Validate a metrics dict, returning a list of error strings.

    Args:
        metrics: Dict to validate.

    Returns:
        List of validation error strings. Empty list if valid.
    """
    errors: list[str] = []
    required_int = ["monthly_expenses_cents", "monthly_income_cents", "liquid_balance_cents", "burn_cents"]
    for field in required_int:
        if field not in metrics:
            errors.append(f"missing field: {field}")
        elif not isinstance(metrics[field], int):
            errors.append(f"field {field} must be int, got {type(metrics[field]).__name__}")
    if "runway_days" not in metrics:
        errors.append("missing field: runway_days")
    elif metrics["runway_days"] is not None and not isinstance(metrics["runway_days"], int):
        errors.append(f"runway_days must be int or None, got {type(metrics['runway_days']).__name__}")
    if "category_totals" not in metrics:
        errors.append("missing field: category_totals")
    elif not isinstance(metrics["category_totals"], dict):
        errors.append("category_totals must be dict")
    if "top_5_recurring" not in metrics:
        errors.append("missing field: top_5_recurring")
    elif not isinstance(metrics["top_5_recurring"], list):
        errors.append("top_5_recurring must be list")
    if "meta" not in metrics:
        errors.append("missing field: meta")
    elif not isinstance(metrics["meta"], dict):
        errors.append("meta must be dict")
    return errors


# ---------------------------------------------------------------------------
# CP1: Spending velocity alerts
# ---------------------------------------------------------------------------

def compute_alerts(
    category_totals: dict[str, int],
    logs_dir: Optional[pathlib.Path] = None,
    threshold_pct: int = 120,
) -> list[MetricsAlert]:
    """Compute CP1 spending velocity alerts.

    Requires at least 2 prior months of history. With fewer months, returns [].

    Args:
        category_totals: Current month MTD totals per category (in cents).
        logs_dir: Directory containing YYYY-MM.jsonl files.
        threshold_pct: Alert fires when MTD > historical_avg * threshold_pct/100.

    Returns:
        List of MetricsAlert dicts for categories over threshold.
    """
    if logs_dir is None:
        logs_dir = _DEFAULT_LOGS_DIR

    if not pathlib.Path(logs_dir).exists():
        return []

    today = dt.date.today()
    current_month = today.strftime("%Y-%m")

    # Read all JSONL files, exclude current month
    historical: list[dict] = []  # each entry: {month: str, category_totals: dict}
    for p in sorted(pathlib.Path(logs_dir).glob("*.jsonl")):
        if p.stem == current_month:
            continue
        for line in p.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
                if isinstance(entry.get("category_totals"), dict):
                    historical.append(entry)
            except Exception:
                continue

    # Need at least 2 prior months
    months_seen = {e.get("month") for e in historical if e.get("month")}
    if len(months_seen) < 2:
        return []

    # Compute historical average per category
    alerts: list[MetricsAlert] = []
    for cat, mtd in category_totals.items():
        prior_values = [
            int(e["category_totals"].get(cat) or 0)
            for e in historical
            if cat in e.get("category_totals", {})
        ]
        if len(prior_values) < 2:
            continue
        avg = sum(prior_values) / len(prior_values)
        if avg <= 0:
            continue
        threshold_value = avg * (threshold_pct / 100.0)
        if mtd > threshold_value:
            pct_over = (mtd / avg - 1.0) * 100.0
            alerts.append(
                MetricsAlert(
                    category=cat,
                    mtd_cents=mtd,
                    historical_avg_cents=round(avg),
                    pct_over=round(pct_over, 1),
                )
            )

    return alerts


# ---------------------------------------------------------------------------
# Query mode
# ---------------------------------------------------------------------------

def query_metrics(
    text: str,
    metrics: dict,
    category_totals: Optional[dict] = None,
) -> str:
    """Answer a natural-language query against pre-computed metrics.

    Args:
        text: Query text in Portuguese or English.
        metrics: Pre-computed MetricsOutput dict.
        category_totals: Override category_totals (defaults to metrics['category_totals']).

    Returns:
        String answer.
    """
    if category_totals is None:
        category_totals = metrics.get("category_totals") or {}

    rules = _load_enrichment_rules()
    alias_map: dict[str, str] = {}
    cats_yaml = rules.get("categories") or {}
    if isinstance(cats_yaml, dict):
        for display, canonical in cats_yaml.items():
            alias_map[_normalize(str(display))] = str(canonical)

    normalized = _normalize(text)

    # Check category query first (special handling)
    cat_pattern = re.compile(r"(?:em|de)\s+(\w+)")
    cat_match = cat_pattern.search(normalized)
    if cat_match:
        cat_query = cat_match.group(1)
        # Try to find in category_totals using normalized comparison
        for cat_name, total in (category_totals or {}).items():
            norm_name = _normalize(cat_name)
            canonical = alias_map.get(norm_name, norm_name)
            if canonical == cat_query or norm_name == cat_query:
                return f"{cat_name}: {total} cents"
        # Try alias reverse lookup
        for display_norm, canonical in alias_map.items():
            if canonical == cat_query:
                for cat_name, total in (category_totals or {}).items():
                    if _normalize(cat_name) == display_norm:
                        return f"{cat_name}: {total} cents"
        return f"No transactions for category {cat_query} found this month"

    # Check other patterns
    for pattern, metric_key in QUERY_MAP:
        if metric_key == "category":
            continue
        if pattern.search(normalized):
            value = metrics.get(metric_key)
            return f"{metric_key}: {value}"

    return f"(no match for query: {text})"


# ---------------------------------------------------------------------------
# CP4: compare-months mode
# ---------------------------------------------------------------------------

def compare_months(n: int, logs_dir: Optional[pathlib.Path] = None) -> str:
    """Generate a month-over-month comparison table for the last N months.

    Args:
        n: Number of months to compare.
        logs_dir: Directory containing YYYY-MM.jsonl files.

    Returns:
        Markdown table string.
    """
    if logs_dir is None:
        logs_dir = _DEFAULT_LOGS_DIR

    if not pathlib.Path(logs_dir).exists():
        return "No historical data found."

    # Collect unique months (use last entry per month)
    month_data: dict[str, dict] = {}
    for p in sorted(pathlib.Path(logs_dir).glob("*.jsonl")):
        for line in p.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
                month = entry.get("month") or p.stem
                if month:
                    month_data[month] = entry
            except Exception:
                continue

    # Sort by month (YYYY-MM)
    sorted_months = sorted(month_data.keys())
    if not sorted_months:
        return "No historical data found."

    available = len(sorted_months)
    out_lines: list[str] = []
    if available < n:
        out_lines.append(f"Warning: only {available} of {n} months available")
        out_lines.append("")

    selected = sorted_months[-n:] if available >= n else sorted_months

    rows: list[dict] = [month_data[m] for m in selected]

    # Header
    out_lines.append(
        "Month      | Expenses  | Income    | Burn     | Δ Expenses | Δ Income"
    )
    out_lines.append(
        "-----------|-----------|-----------|----------|------------|----------"
    )

    def _brl(c: int) -> str:
        v = abs(int(c)) / 100.0
        s = f"{v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
        return f"-R$ {s}" if c < 0 else f"R$ {s}"

    prev_exp = None
    prev_inc = None

    for row in rows:
        month = row.get("month", "?")
        exp = int(row.get("monthly_expenses_cents") or 0)
        inc = int(row.get("monthly_income_cents") or 0)
        burn = exp - inc

        exp_delta = "—"
        inc_delta = "—"
        if prev_exp is not None and prev_exp > 0:
            pct = (exp - prev_exp) / prev_exp * 100
            exp_delta = f"{pct:+.1f}%"
        if prev_inc is not None and prev_inc > 0:
            pct = (inc - prev_inc) / prev_inc * 100
            inc_delta = f"{pct:+.1f}%"

        out_lines.append(
            f"{month:<10} | {_brl(exp):<9} | {_brl(inc):<9} | {_brl(burn):<8} | {exp_delta:<10} | {inc_delta}"
        )
        prev_exp = exp
        prev_inc = inc

    # Biggest category shifts (top 3)
    if len(rows) >= 2:
        out_lines.append("")
        out_lines.append("## Top 3 category shifts (last 2 months)")
        prev_cats = rows[-2].get("category_totals") or {}
        curr_cats = rows[-1].get("category_totals") or {}
        shifts: list[tuple[str, float]] = []
        for cat in set(list(prev_cats.keys()) + list(curr_cats.keys())):
            p = int(prev_cats.get(cat) or 0)
            c = int(curr_cats.get(cat) or 0)
            if p > 0:
                pct = (c - p) / p * 100
                shifts.append((cat, pct))
        shifts.sort(key=lambda x: -abs(x[1]))
        for cat, pct in shifts[:3]:
            out_lines.append(f"- {cat}: {pct:+.1f}%")

    return "\n".join(out_lines)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> int:
    ap = argparse.ArgumentParser(description="Deterministic metrics engine for herow-finance.")
    ap.add_argument("--snapshot", default=None, help="Path to sanitized snapshot JSON")
    ap.add_argument(
        "--out",
        default=None,
        help="Output path for metrics.json (default: ~/finance/organizze/metrics.json)",
    )
    ap.add_argument("--query", default=None, help="Natural-language query against metrics")
    ap.add_argument(
        "--compare-months",
        type=int,
        default=None,
        metavar="N",
        help="Compare last N months (longitudinal mode)",
    )
    args = ap.parse_args()

    # Longitudinal mode
    if args.compare_months is not None:
        print(compare_months(args.compare_months))
        return 0

    # Need snapshot for other modes
    if not args.snapshot:
        print("err|missing-arg|--snapshot is required", file=sys.stderr)
        return 2

    snap_path = pathlib.Path(args.snapshot)
    if not snap_path.exists():
        print(f"err|snapshot-missing|{snap_path}", file=sys.stderr)
        return 1

    try:
        snapshot = json.loads(snap_path.read_text())
    except Exception as e:
        print(f"err|snapshot-parse|{e}", file=sys.stderr)
        return 1

    metrics = compute_metrics(snapshot)

    # Query mode
    if args.query:
        result = query_metrics(args.query, metrics)
        print(result)
        return 0

    # Default mode: write metrics.json
    out_path = pathlib.Path(args.out) if args.out else _DEFAULT_OUT
    try:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(metrics, ensure_ascii=False, indent=2))
    except Exception as e:
        print(f"err|metrics-write|{e}", file=sys.stderr)
        return 1

    print(f"ok|metrics|{out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
