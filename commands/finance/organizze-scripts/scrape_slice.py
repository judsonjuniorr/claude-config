#!/usr/bin/env python3
import calendar
import datetime as dt
import json
import os
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).parent))
from _paths import HOME, chromium_executable_path

SESSION = HOME / ".session"
SCRAPE_DIR = HOME / "scrape"

ORGANIZZE_URL = "https://app.organizze.com.br"

SELECTORS: dict[str, str] = {
    "dashboard_account_row": 'a[href*="accountUUID="]',
    "dashboard_account_name": ".naming strong",
    "dashboard_account_balance": "big.ng-binding:not(.hidden-placeholder)",
    "tx_row": ".transaction-row",
    "tx_date": ".transaction-date",
    "tx_description": ".transaction-description",
    "tx_amount": ".transaction-amount",
    "tx_dom_id": "[data-id]",
    "invoice_total": ".invoice-total",
    "invoice_tx_row": ".invoice-transaction",
}


def parse_money(raw: str) -> int:
    """Convert 'R$ 1.234,56' or '-R$ 1.234,56' to cents."""
    s = raw.strip()
    negative = s.startswith("-")
    # strip currency symbols and whitespace
    s = s.lstrip("-").replace("R$", "").replace("r$", "").strip()
    # remove thousand separators (dots) then convert comma decimal
    s = s.replace(".", "").replace(",", ".")
    try:
        cents = round(float(s) * 100)
    except ValueError:
        return 0
    return -cents if negative else cents


def dump_dom_excerpt(page) -> str:  # type: ignore[no-untyped-def]
    try:
        body = page.inner_html("body")
        return body[:2000]
    except Exception:
        return ""


def scrape_dashboard(page) -> dict:  # type: ignore[no-untyped-def]
    # Base URL redirects to /<workspace_id>/a/inicio (the dashboard). The
    # workspace id is account-specific, so let the app resolve it.
    page.goto(f"{ORGANIZZE_URL}/")
    page.wait_for_load_state("networkidle")
    try:
        page.wait_for_selector(SELECTORS["dashboard_account_row"], timeout=10000)
    except Exception:
        pass

    rows = page.query_selector_all(SELECTORS["dashboard_account_row"])
    if not rows:
        excerpt = dump_dom_excerpt(page)
        print(f"err|selector-not-found|dashboard_account_row={SELECTORS['dashboard_account_row']}\n{excerpt}")
        sys.exit(1)

    accounts = []
    for row in rows:
        name_el = row.query_selector(SELECTORS["dashboard_account_name"])
        balance_el = row.query_selector(SELECTORS["dashboard_account_balance"])
        if name_el is None or balance_el is None:
            continue
        name = (name_el.inner_text() or "").strip()
        balance_raw = (balance_el.inner_text() or "").strip()
        accounts.append({"name": name, "balance_cents": parse_money(balance_raw)})

    if not accounts:
        excerpt = dump_dom_excerpt(page)
        print(f"err|selector-not-found|no accounts parsed from dashboard\n{excerpt}")
        sys.exit(1)

    return {
        "type": "dashboard",
        "scraped_at": dt.datetime.now().isoformat(timespec="seconds"),
        "accounts": accounts,
    }


def scrape_tx(page, month: str) -> dict:  # type: ignore[no-untyped-def]
    year_s, mon_s = month.split("-")
    last_day = calendar.monthrange(int(year_s), int(mon_s))[1]
    url = (
        f"{ORGANIZZE_URL}/lancamentos"
        f"?start_date={month}-01&end_date={month}-{last_day:02d}"
    )
    page.goto(url)
    page.wait_for_load_state("networkidle")

    rows = page.query_selector_all(SELECTORS["tx_row"])
    if not rows:
        excerpt = dump_dom_excerpt(page)
        print(f"err|selector-not-found|tx_row={SELECTORS['tx_row']}\n{excerpt}")
        sys.exit(1)

    transactions = []
    for row in rows:
        date_el = row.query_selector(SELECTORS["tx_date"])
        desc_el = row.query_selector(SELECTORS["tx_description"])
        amount_el = row.query_selector(SELECTORS["tx_amount"])
        dom_id_el = row.query_selector(SELECTORS["tx_dom_id"])

        date_raw = (date_el.inner_text() if date_el else "").strip()
        desc = (desc_el.inner_text() if desc_el else "").strip()
        amount_raw = (amount_el.inner_text() if amount_el else "").strip()
        dom_id = dom_id_el.get_attribute("data-id") if dom_id_el else None

        # Try to normalize date to YYYY-MM-DD
        date_iso = ""
        for fmt in ("%d/%m/%Y", "%Y-%m-%d", "%d/%m/%y"):
            try:
                date_iso = dt.datetime.strptime(date_raw, fmt).date().isoformat()
                break
            except ValueError:
                pass

        account_el = row.query_selector(".account-name, .transaction-account")
        account = (account_el.inner_text() if account_el else "").strip()

        transactions.append({
            "dom_id": f"tx-{dom_id}" if dom_id else None,
            "date": date_iso,
            "description": desc,
            "amount_cents": parse_money(amount_raw),
            "account": account,
        })

    return {
        "type": "tx",
        "month": month,
        "scraped_at": dt.datetime.now().isoformat(timespec="seconds"),
        "transactions": transactions,
    }


def scrape_invoice(page, card_id: int, month: str) -> dict:  # type: ignore[no-untyped-def]
    url = f"{ORGANIZZE_URL}/faturas/{card_id}?date={month}-01"
    page.goto(url)
    page.wait_for_load_state("networkidle")

    total_el = page.query_selector(SELECTORS["invoice_total"])
    if total_el is None:
        excerpt = dump_dom_excerpt(page)
        print(f"err|selector-not-found|invoice_total={SELECTORS['invoice_total']}\n{excerpt}")
        sys.exit(1)

    total_cents = parse_money((total_el.inner_text() or "").strip())

    rows = page.query_selector_all(SELECTORS["invoice_tx_row"])
    transactions = []
    for row in rows:
        date_el = row.query_selector(SELECTORS["tx_date"])
        desc_el = row.query_selector(SELECTORS["tx_description"])
        amount_el = row.query_selector(SELECTORS["tx_amount"])
        dom_id_el = row.query_selector(SELECTORS["tx_dom_id"])

        date_raw = (date_el.inner_text() if date_el else "").strip()
        desc = (desc_el.inner_text() if desc_el else "").strip()
        amount_raw = (amount_el.inner_text() if amount_el else "").strip()
        dom_id = dom_id_el.get_attribute("data-id") if dom_id_el else None

        date_iso = ""
        for fmt in ("%d/%m/%Y", "%Y-%m-%d", "%d/%m/%y"):
            try:
                date_iso = dt.datetime.strptime(date_raw, fmt).date().isoformat()
                break
            except ValueError:
                pass

        transactions.append({
            "dom_id": f"tx-{dom_id}" if dom_id else None,
            "date": date_iso,
            "description": desc,
            "amount_cents": parse_money(amount_raw),
        })

    return {
        "type": "invoice",
        "card_id": card_id,
        "month": month,
        "scraped_at": dt.datetime.now().isoformat(timespec="seconds"),
        "total_cents": total_cents,
        "transactions": transactions,
    }


def main() -> None:
    if len(sys.argv) < 2:
        print("err|usage|python3 scrape_slice.py <dashboard|tx YYYY-MM|invoice <card_id> YYYY-MM>")
        sys.exit(1)

    if not SESSION.exists():
        print("err|no-session|run organizze_login.py first")
        sys.exit(1)

    SCRAPE_DIR.mkdir(parents=True, exist_ok=True)
    os.chmod(SCRAPE_DIR, 0o700)

    slice_type = sys.argv[1]

    # Validate per-type args before importing playwright
    if slice_type == "tx":
        if len(sys.argv) < 3:
            print("err|usage|python3 scrape_slice.py tx YYYY-MM")
            sys.exit(1)
    elif slice_type == "invoice":
        if len(sys.argv) < 4:
            print("err|usage|python3 scrape_slice.py invoice <card_id> YYYY-MM")
            sys.exit(1)
    elif slice_type != "dashboard":
        print(f"err|usage|unknown slice type: {slice_type}")
        sys.exit(1)

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("err|playwright-not-installed|run: pip3 install playwright && python3 -m playwright install chromium")
        sys.exit(1)

    with sync_playwright() as p:
        exe = chromium_executable_path()
        browser = p.chromium.launch(headless=True, **({"executable_path": exe} if exe else {}))
        ctx = browser.new_context(storage_state=str(SESSION))
        page = ctx.new_page()
        page.set_default_navigation_timeout(15000)

        if slice_type == "dashboard":
            data = scrape_dashboard(page)
            slice_name = "dashboard"

        elif slice_type == "tx":
            month = sys.argv[2]
            data = scrape_tx(page, month)
            slice_name = f"tx_{month}"

        elif slice_type == "invoice":
            card_id = int(sys.argv[2])
            month = sys.argv[3]
            data = scrape_invoice(page, card_id, month)
            slice_name = f"invoice_{card_id}_{month}"

        browser.close()

    out_path = SCRAPE_DIR / f"{slice_name}.json"
    out_path.write_text(json.dumps(data, ensure_ascii=False, indent=2))
    print(f"ok|scraped|{out_path}")


if __name__ == "__main__":
    main()
