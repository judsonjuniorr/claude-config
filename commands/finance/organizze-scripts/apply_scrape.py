#!/usr/bin/env python3
import argparse
import datetime as dt
import json
import pathlib
import re
import sys


def normalize_name(s: str) -> str:
    return re.sub(r"\s+", " ", s.strip().lower())


def load_scrapes(scrape_dir: pathlib.Path) -> list[dict]:
    scrapes = []
    for f in sorted(scrape_dir.glob("*.json")):
        try:
            data = json.loads(f.read_text())
            data["_source_file"] = f.name
            scrapes.append(data)
        except json.JSONDecodeError as e:
            print(f"err|malformed-scrape|{f.name}|{e}")
            sys.exit(1)
    return scrapes


def apply_dashboard(snapshot: dict, scrape: dict) -> tuple[int, list[str]]:
    matched = 0
    unreconciled: list[str] = []

    scrape_accounts = scrape.get("accounts") or []
    name_counts: dict[str, int] = {}
    for a in scrape_accounts:
        key = normalize_name(a.get("name") or "")
        name_counts[key] = name_counts.get(key, 0) + 1

    duplicates = {k for k, v in name_counts.items() if v > 1}
    warned_duplicates: set[str] = set()

    snap_accounts = snapshot.get("accounts") or []
    snap_by_name: dict[str, dict] = {}
    for a in snap_accounts:
        key = normalize_name(a.get("name") or "")
        snap_by_name[key] = a

    for sa in scrape_accounts:
        key = normalize_name(sa.get("name") or "")
        if key in duplicates:
            if key not in warned_duplicates:
                print(f"warn|duplicate-account-name|{sa.get('name')}", file=sys.stderr)
                warned_duplicates.add(key)
                unreconciled.append(sa.get("name") or key)
            continue
        if key in snap_by_name:
            snap_by_name[key]["_balance_cents"] = sa["balance_cents"]
            matched += 1
        else:
            unreconciled.append(sa.get("name") or key)

    return matched, unreconciled


def apply_transactions(snapshot: dict, scrape: dict) -> tuple[int, list[str]]:
    matched = 0
    unreconciled: list[str] = []

    scrape_txs = scrape.get("transactions") or []

    snap_txs = snapshot.get("transactions_past", []) + snapshot.get("transactions_future", [])

    # Index snap txs by dom_id
    snap_by_dom: dict[str, dict] = {}
    for t in snap_txs:
        dom_id = t.get("dom_id")
        if dom_id:
            snap_by_dom[dom_id] = t

    # Index snap txs by (date, desc_norm) for fallback — list to handle collisions by order
    snap_by_date_desc: dict[tuple[str, str], list[dict]] = {}
    for t in snap_txs:
        key = (t.get("date", "")[:10], normalize_name(t.get("description") or ""))
        snap_by_date_desc.setdefault(key, []).append(t)
    # track how many we've consumed per key
    snap_date_desc_cursor: dict[tuple[str, str], int] = {}

    for st in scrape_txs:
        dom_id = st.get("dom_id")
        matched_snap: dict | None = None

        if dom_id and dom_id in snap_by_dom:
            matched_snap = snap_by_dom[dom_id]
        else:
            key = (st.get("date", "")[:10], normalize_name(st.get("description") or ""))
            candidates = snap_by_date_desc.get(key)
            if candidates:
                idx = snap_date_desc_cursor.get(key, 0)
                if idx < len(candidates):
                    matched_snap = candidates[idx]
                    snap_date_desc_cursor[key] = idx + 1

        if matched_snap is not None:
            matched_snap["amount_cents"] = st["amount_cents"]
            matched += 1
        else:
            label = f"{st.get('date')}|{st.get('description')}"
            unreconciled.append(label)

    return matched, unreconciled


def apply_invoice(snapshot: dict, scrape: dict) -> tuple[int, list[str]]:
    matched = 0
    unreconciled: list[str] = []

    card_id = scrape.get("card_id")
    month = scrape.get("month") or ""

    snap_invoices = snapshot.get("invoices") or []
    for inv in snap_invoices:
        cid = inv.get("_credit_card_id") or inv.get("credit_card_id")
        inv_date = (inv.get("date") or "")[:7]  # YYYY-MM
        if cid == card_id and inv_date == month:
            inv["total_cents"] = scrape["total_cents"]
            matched += 1

    if matched == 0:
        unreconciled.append(f"card_id={card_id} month={month}")

    return matched, unreconciled


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--snapshot", required=True)
    args = ap.parse_args()

    snap_path = pathlib.Path(args.snapshot)
    if not snap_path.exists():
        print(f"err|snapshot-not-found|{snap_path}")
        sys.exit(1)

    try:
        snapshot = json.loads(snap_path.read_text())
    except json.JSONDecodeError as e:
        print(f"err|malformed-scrape|{snap_path.name}|{e}")
        sys.exit(1)

    scrape_dir = pathlib.Path(
        __import__("os").environ.get(
            "ORGANIZZE_HOME",
            str(pathlib.Path.home() / "finance" / "organizze"),
        )
    ) / "scrape"

    if not scrape_dir.exists():
        print("err|scrape-dir-not-found|scrape dir does not exist")
        sys.exit(1)

    scrapes = load_scrapes(scrape_dir)
    if not scrapes:
        print("warn|unreconciled|accounts=0,transactions=0,invoices=0")
        sys.exit(0)

    total_accounts = total_txs = total_invoices = 0
    unrec_accounts: list[str] = []
    unrec_txs: list[str] = []
    unrec_invoices: list[str] = []
    slice_names: list[str] = []

    for scrape in scrapes:
        source = scrape.get("_source_file", "unknown")
        stype = scrape.get("type")

        if not stype:
            print(f"err|malformed-scrape|{source}|missing 'type' field")
            sys.exit(1)

        slice_name = source.removesuffix(".json")
        slice_names.append(slice_name)

        if stype == "dashboard":
            n, unrec = apply_dashboard(snapshot, scrape)
            total_accounts += n
            unrec_accounts.extend(unrec)

        elif stype == "tx":
            n, unrec = apply_transactions(snapshot, scrape)
            total_txs += n
            unrec_txs.extend(unrec)

        elif stype == "invoice":
            n, unrec = apply_invoice(snapshot, scrape)
            total_invoices += n
            unrec_invoices.extend(unrec)

    has_warn = bool(unrec_accounts or unrec_txs or unrec_invoices)

    snapshot["_scrape_meta"] = {
        "applied_at": dt.datetime.now().isoformat(timespec="seconds"),
        "slices": slice_names,
        "warn": has_warn,
    }

    if has_warn:
        snapshot["_scrape_unreconciled"] = {
            "accounts": unrec_accounts,
            "transactions": unrec_txs,
            "invoices": unrec_invoices,
        }

    # Backup before writing
    bak_path = snap_path.with_suffix(".json.bak")
    bak_path.write_text(snap_path.read_text())

    snap_path.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2))

    summary = f"accounts={total_accounts},transactions={total_txs},invoices={total_invoices}"
    if has_warn:
        n_ua = len(unrec_accounts)
        n_ut = len(unrec_txs)
        n_ui = len(unrec_invoices)
        print(f"warn|unreconciled|accounts={n_ua},transactions={n_ut},invoices={n_ui}")
    else:
        print(f"ok|applied|{summary}")


if __name__ == "__main__":
    main()
