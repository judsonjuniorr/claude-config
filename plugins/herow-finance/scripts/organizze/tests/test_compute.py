"""Tests for compute.py."""
import json
import sys
import pathlib
import tempfile
import datetime as dt

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))
from compute import compute_metrics, query_metrics, compute_alerts


# ---------------------------------------------------------------------------
# Minimal snapshot factory
# ---------------------------------------------------------------------------

def make_snapshot(expenses=None, income=None, accounts=None, categories=None):
    today = dt.date.today().isoformat()
    txs_past = []
    if expenses:
        for i, (cat_id, amt) in enumerate(expenses):
            txs_past.append({
                "id": i + 1,
                "amount_cents": -abs(amt),
                "date": today,
                "category_id": cat_id,
                "paid": True,
                "is_recurring": False,
            })
    if income:
        for i, (cat_id, amt) in enumerate(income):
            txs_past.append({
                "id": 100 + i,
                "amount_cents": abs(amt),
                "date": today,
                "category_id": cat_id,
                "paid": True,
                "is_recurring": False,
            })
    return {
        "transactions_past": txs_past,
        "transactions_future": [],
        "accounts": accounts or [{"id": 1, "_balance_cents": 500000, "type": "checking", "archived": False}],
        "categories": categories or [{"id": 1, "name": "Alimentação"}],
    }


# ---------------------------------------------------------------------------
# Burn / runway tests
# ---------------------------------------------------------------------------

def test_burn_positive_when_expenses_exceed_income():
    snap = make_snapshot(expenses=[(1, 300000)], income=[(1, 200000)])
    m = compute_metrics(snap)
    assert m["burn_cents"] > 0
    assert m["burn_cents"] == 100000


def test_runway_null_when_burn_zero_or_negative():
    snap = make_snapshot(expenses=[(1, 200000)], income=[(1, 300000)])
    m = compute_metrics(snap)
    assert m["runway_days"] is None


def test_runway_computed_when_positive_burn():
    snap = make_snapshot(expenses=[(1, 500000)], income=[(1, 100000)])
    m = compute_metrics(snap)
    assert m["runway_days"] is not None
    assert m["runway_days"] > 0


# ---------------------------------------------------------------------------
# Category totals
# ---------------------------------------------------------------------------

def test_category_totals_populated():
    snap = make_snapshot(expenses=[(1, 12000)])
    m = compute_metrics(snap)
    assert "Alimentação" in m["category_totals"]
    assert m["category_totals"]["Alimentação"] == 12000


# ---------------------------------------------------------------------------
# Query tests
# ---------------------------------------------------------------------------

def test_query_monthly_expenses():
    snap = make_snapshot(expenses=[(1, 30000)])
    m = compute_metrics(snap)
    result = query_metrics("quanto gastei", m)
    # Value 30000 must appear in some form
    assert "30000" in result or "300" in result


def test_query_category_explicit_empty():
    snap = make_snapshot(expenses=[(1, 10000)])
    m = compute_metrics(snap)
    result = query_metrics("em transporte", m, category_totals=m["category_totals"])
    assert "No transactions for category" in result


# ---------------------------------------------------------------------------
# CP1 alert tests
# ---------------------------------------------------------------------------

def test_cp1_alerts_empty_when_less_than_2_months_history(tmp_path):
    alerts = compute_alerts({"Alimentação": 50000}, logs_dir=tmp_path)
    assert alerts == []


def test_cp1_alert_fires_when_over_120pct(tmp_path):
    # Create 2 prior months of history
    log_file = tmp_path / "2026-05.jsonl"
    log_file.write_text(
        json.dumps({
            "month": "2026-05",
            "category_totals": {"Alimentação": 30000},
            "snapshot_hash": "abc123",
        }) + "\n"
    )
    log_file2 = tmp_path / "2026-04.jsonl"
    log_file2.write_text(
        json.dumps({
            "month": "2026-04",
            "category_totals": {"Alimentação": 30000},
            "snapshot_hash": "def456",
        }) + "\n"
    )
    # 40000 > 30000 * 1.2 = 36000 → alert fires
    alerts = compute_alerts({"Alimentação": 40000}, logs_dir=tmp_path, threshold_pct=120)
    assert len(alerts) == 1
    assert alerts[0]["category"] == "Alimentação"


def test_cp1_cold_start_when_only_1_month_history(tmp_path):
    log_file = tmp_path / "2026-05.jsonl"
    log_file.write_text(
        json.dumps({
            "month": "2026-05",
            "category_totals": {"Alimentação": 30000},
            "snapshot_hash": "abc123",
        }) + "\n"
    )
    # Only 1 prior month → cold start, no alerts
    alerts = compute_alerts({"Alimentação": 50000}, logs_dir=tmp_path, threshold_pct=120)
    assert alerts == []


def test_cp1_no_alert_when_under_threshold(tmp_path):
    for month, h in [("2026-04", "aaaa"), ("2026-05", "bbbb")]:
        (tmp_path / f"{month}.jsonl").write_text(
            json.dumps({
                "month": month,
                "category_totals": {"Alimentação": 30000},
                "snapshot_hash": h,
            }) + "\n"
        )
    # 31000 < 30000 * 1.2 = 36000 → no alert
    alerts = compute_alerts({"Alimentação": 31000}, logs_dir=tmp_path, threshold_pct=120)
    assert alerts == []
