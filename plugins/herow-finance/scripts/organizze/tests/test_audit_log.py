"""Tests for audit_log.py."""
import json
import sys
import pathlib
import tempfile
import hashlib

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))
from audit_log import append_log_entry


def make_mock_snapshot(tmp_path):
    snap = {
        "meta": {"pulled_at": "2026-06-28T00:00:00"},
        "accounts": [],
        "transactions_past": [],
    }
    p = tmp_path / "snapshot.json"
    p.write_text(json.dumps(snap))
    return p


def make_mock_metrics():
    return {
        "monthly_expenses_cents": 300000,
        "monthly_income_cents": 800000,
        "runway_days": None,
        "category_totals": {"Alimentação": 100000},
        "top_5_recurring": [],
        "meta": {
            "alerts": [],
            "computed_at": "2026-06-28T00:00:00",
            "month": "2026-06",
        },
    }


def test_creates_log_file(tmp_path):
    snap_path = make_mock_snapshot(tmp_path)
    metrics = make_mock_metrics()
    logs_dir = tmp_path / "logs"
    append_log_entry(str(snap_path), metrics, logs_dir=logs_dir)
    files = list(logs_dir.glob("*.jsonl"))
    assert len(files) == 1
    line = json.loads(files[0].read_text().strip())
    assert "snapshot_hash" in line
    assert "monthly_expenses_cents" in line
    assert line["monthly_expenses_cents"] == 300000


def test_idempotent_same_hash(tmp_path):
    snap_path = make_mock_snapshot(tmp_path)
    metrics = make_mock_metrics()
    logs_dir = tmp_path / "logs"
    append_log_entry(str(snap_path), metrics, logs_dir=logs_dir)
    append_log_entry(str(snap_path), metrics, logs_dir=logs_dir)
    files = list(logs_dir.glob("*.jsonl"))
    lines = [l for l in files[0].read_text().splitlines() if l.strip()]
    assert len(lines) == 1  # only 1 entry despite 2 calls


def test_snapshot_hash_is_sha256_of_bytes(tmp_path):
    snap_path = make_mock_snapshot(tmp_path)
    metrics = make_mock_metrics()
    logs_dir = tmp_path / "logs"
    append_log_entry(str(snap_path), metrics, logs_dir=logs_dir)
    files = list(logs_dir.glob("*.jsonl"))
    line = json.loads(files[0].read_text().strip())
    expected_hash = hashlib.sha256(snap_path.read_bytes()).hexdigest()
    assert line["snapshot_hash"] == expected_hash


def test_schema_fields_present(tmp_path):
    snap_path = make_mock_snapshot(tmp_path)
    metrics = make_mock_metrics()
    logs_dir = tmp_path / "logs"
    append_log_entry(str(snap_path), metrics, logs_dir=logs_dir)
    files = list(logs_dir.glob("*.jsonl"))
    line = json.loads(files[0].read_text().strip())
    for field in [
        "run_at",
        "month",
        "monthly_expenses_cents",
        "monthly_income_cents",
        "runway_days",
        "category_totals",
        "top_5_recurring",
        "snapshot_hash",
    ]:
        assert field in line, f"Missing field: {field}"


def test_different_snapshots_append_two_entries(tmp_path):
    """Two runs with different snapshot content should produce 2 log entries."""
    snap1 = tmp_path / "snap1.json"
    snap2 = tmp_path / "snap2.json"
    snap1.write_text(json.dumps({"meta": {}, "v": 1}))
    snap2.write_text(json.dumps({"meta": {}, "v": 2}))
    metrics = make_mock_metrics()
    logs_dir = tmp_path / "logs"
    append_log_entry(str(snap1), metrics, logs_dir=logs_dir)
    append_log_entry(str(snap2), metrics, logs_dir=logs_dir)
    files = list(logs_dir.glob("*.jsonl"))
    lines = [l for l in files[0].read_text().splitlines() if l.strip()]
    assert len(lines) == 2
