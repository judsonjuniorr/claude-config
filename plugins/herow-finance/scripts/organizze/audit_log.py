#!/usr/bin/env python3
"""Append-only audit log for herow-finance analysis runs.

Usage:
  audit_log.py --snapshot PATH --metrics PATH

Appends one JSONL entry to ~/finance/logs/YYYY-MM.jsonl (current month file).
Skips if the snapshot_hash matches the most recent entry (duplicate run).
Never fails fatally — errors are warnings.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import pathlib
import sys
from typing import Optional

_DEFAULT_LOGS_DIR = pathlib.Path.home() / "finance" / "logs"


def _snapshot_hash(snap_path: str) -> str:
    """Compute SHA-256 of the raw snapshot file bytes.

    Args:
        snap_path: Path to the snapshot file.

    Returns:
        Hex digest string.
    """
    return hashlib.sha256(pathlib.Path(snap_path).read_bytes()).hexdigest()


def _last_entry_hash(log_path: pathlib.Path) -> Optional[str]:
    """Read the last JSONL line and return its snapshot_hash, or None."""
    if not log_path.exists():
        return None
    try:
        lines = [
            line.strip()
            for line in log_path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        if not lines:
            return None
        last = json.loads(lines[-1])
        return last.get("snapshot_hash")
    except Exception:
        return None


def append_log_entry(
    snap_path: str,
    metrics: Optional[dict],
    logs_dir: Optional[pathlib.Path] = None,
) -> str:
    """Append one JSONL entry to the monthly audit log.

    Args:
        snap_path: Path to the snapshot file (used for hash computation).
        metrics: Pre-computed metrics dict (from compute.py). May be None.
        logs_dir: Directory for JSONL files (default: ~/finance/logs/).

    Returns:
        "ok|audit-log|<path>" on success, "info|duplicate-skip|<hash[:8]>" on dup.

    Raises:
        Never — all errors are caught and returned as warning strings.
    """
    if logs_dir is None:
        logs_dir = _DEFAULT_LOGS_DIR

    logs_dir = pathlib.Path(logs_dir)

    today = dt.date.today()
    month_str = today.strftime("%Y-%m")
    log_path = logs_dir / f"{month_str}.jsonl"

    # Compute snapshot hash
    try:
        snap_hash = _snapshot_hash(snap_path)
    except Exception as e:
        return f"warn|hash-error|{e}"

    # Check for duplicate
    last_hash = _last_entry_hash(log_path)
    if last_hash == snap_hash:
        msg = f"info|duplicate-skip|{snap_hash[:8]}"
        print(msg)
        return msg

    # Build entry
    entry: dict = {
        "run_at": dt.datetime.now().isoformat(timespec="seconds"),
        "month": month_str,
        "snapshot_hash": snap_hash,
    }

    if metrics is None:
        entry["data_quality_flags"] = ["METRICS_MISSING"]
    else:
        entry["monthly_expenses_cents"] = int(metrics.get("monthly_expenses_cents") or 0)
        entry["monthly_income_cents"] = int(metrics.get("monthly_income_cents") or 0)
        entry["runway_days"] = metrics.get("runway_days")
        entry["category_totals"] = metrics.get("category_totals") or {}
        top5 = metrics.get("top_5_recurring") or []
        entry["top_5_recurring"] = [
            {"description": r.get("description", "?"), "amount_cents": r.get("amount_cents", 0)}
            for r in top5
        ]

    # Write
    try:
        logs_dir.mkdir(parents=True, exist_ok=True)
        with log_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except Exception as e:
        msg = f"warn|log-write|{e}"
        print(msg, file=sys.stderr)
        return msg

    msg = f"ok|audit-log|{log_path}"
    print(msg)
    return msg


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Append-only audit log for herow-finance analysis runs."
    )
    ap.add_argument("--snapshot", required=True, help="Path to snapshot file")
    ap.add_argument("--metrics", required=True, help="Path to metrics.json")
    args = ap.parse_args()

    snap_path = pathlib.Path(args.snapshot)
    if not snap_path.exists():
        print(f"warn|snapshot-missing|{snap_path}", file=sys.stderr)
        # Still try to log with minimal entry
        append_log_entry(str(snap_path), None)
        return 0

    metrics_path = pathlib.Path(args.metrics)
    metrics: Optional[dict] = None
    if metrics_path.exists():
        try:
            metrics = json.loads(metrics_path.read_text())
        except Exception as e:
            print(f"warn|metrics-parse|{e}", file=sys.stderr)

    append_log_entry(str(snap_path), metrics)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
