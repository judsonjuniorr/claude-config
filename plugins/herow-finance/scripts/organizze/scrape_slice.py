#!/usr/bin/env python3
import calendar
import datetime as dt
import json
import os
import pathlib
import re
import sys

sys.path.insert(0, str(pathlib.Path(__file__).parent))
from _paths import HOME, chromium_executable_path

SESSION = HOME / ".session"
SCRAPE_DIR = HOME / "scrape"

ORGANIZZE_URL = "https://app.organizze.com.br"

# Organizze is an AngularJS SPA. All app routes are prefixed with the
# workspace id (e.g. /289189/a/lancamentos); the legacy invoice pages live
# under /<wid>/cartao-de-credito/<card_id>/faturas/<card_id>,<invoice_id>.
# resolve_workspace_id() reads the id from the post-login landing URL.
SELECTORS: dict[str, str] = {
    "dashboard_account_row": 'a[href*="accountUUID="]',
    "dashboard_account_name": ".naming strong",
    "dashboard_account_balance": "big.ng-binding:not(.hidden-placeholder)",
    # Transactions list (lancamentos) — rows are <zze-transaction-item>,
    # grouped under <div class="zze-transactions-day-header"> that carries the
    # date (DD/MM/YY). Amount sign comes from the .amt 'inflow' class.
    "tx_row": "zze-transaction-item",
    "tx_day_header": ".zze-transactions-day-header",
    "tx_description": ".desc name",
    "tx_account": ".acc name",
    "tx_amount": ".amt",
    # Invoice (fatura) — legacy template. Rows are <li id="transaction-...">,
    # date in <trx-date> (DD/MM), description in <trx-description> name,
    # amount in <trx-amount> ('inflow' class for credits). Total sits next to
    # the "VALOR DA FATURA" label.
    "invoice_tx_row": 'li[id^="transaction-"]',
    "invoice_tx_date": "trx-date",
    "invoice_tx_description": "trx-description name",
    "invoice_tx_amount": "trx-amount",
    "invoice_total_label": "VALOR DA FATURA",
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


def amount_with_sign(text: str, inflow: bool) -> int:
    """Magnitude from the text; sign from the rendered '-' first, then class.

    Organizze renders expenses with a leading '-' (red, no 'inflow' class) and
    credits with no sign (green, 'inflow' class). Trust an explicit '-' when
    present so a missing or renamed class can never flip a clearly-signed
    value; fall back to the 'inflow' class only for rows rendered without a
    sign (e.g. internal transfers).
    """
    cents = abs(parse_money(text))
    negative = ("-" in text) or (not inflow)
    return -cents if negative else cents


def is_login_redirect(url: str) -> bool:
    """True when the URL is a login/auth page (session expired)."""
    return bool(re.search(r"/(login|entrar)(?:[/?#]|$)", url))


def dom_id_from_row_id(row_id: str) -> str | None:
    """'tr-2046264594' / 'transaction-3067044748' -> 'tx-2046264594'."""
    num = re.sub(r"\D", "", row_id or "")
    return f"tx-{num}" if num else None


def list_date_to_iso(label: str) -> str:
    """Day-header label ('05/06/26', 'Hoje 05/06/26') -> 'YYYY-MM-DD'."""
    m = re.search(r"(\d{2})/(\d{2})/(\d{2,4})", label or "")
    if not m:
        if "hoje" in (label or "").lower():
            return dt.date.today().isoformat()
        return ""
    d, mo, y = m.groups()
    y = f"20{y}" if len(y) == 2 else y
    try:
        return dt.date(int(y), int(mo), int(d)).isoformat()
    except ValueError:
        return ""


def invoice_date_to_iso(label: str, month: str) -> str:
    """Invoice row date 'DD/MM' -> 'YYYY-MM-DD', inferring the year.

    Invoice transactions span the cycle preceding the invoice date, so the
    transaction month is <= the invoice month within the same year; a higher
    month number means it wrapped into the previous year (e.g. December
    purchases on a January invoice).
    """
    m = re.search(r"(\d{2})/(\d{2})", label or "")
    if not m:
        return ""
    d, mo = int(m.group(1)), int(m.group(2))
    inv_year, inv_month = int(month[:4]), int(month[5:7])
    year = inv_year if mo <= inv_month else inv_year - 1
    try:
        return dt.date(year, mo, d).isoformat()
    except ValueError:
        return ""


def dump_dom_excerpt(page) -> str:  # type: ignore[no-untyped-def]
    try:
        body = page.inner_html("body")
        return body[:5000]
    except Exception:
        return ""


def resolve_workspace_id(page) -> str:  # type: ignore[no-untyped-def]
    """Navigate to the app root and read the workspace id from the URL."""
    page.goto(f"{ORGANIZZE_URL}/")
    page.wait_for_load_state("networkidle")
    page.wait_for_timeout(800)
    if is_login_redirect(page.url):
        print("err|session-expired|workspace")
        sys.exit(1)
    # The workspace id is always the first path segment; anchor the fallback
    # there so a digit-run elsewhere in the URL can't be mistaken for it.
    m = re.search(r"/(\d+)/a/inicio", page.url) or re.search(
        r"^https?://[^/]+/(\d+)(?:/|$)", page.url
    )
    if not m:
        print(f"err|workspace-id-not-resolved|{page.url}")
        sys.exit(1)
    return m.group(1)


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
    wid = resolve_workspace_id(page)
    year_s, mon_s = month.split("-")
    last_day = calendar.monthrange(int(year_s), int(mon_s))[1]
    url = (
        f"{ORGANIZZE_URL}/{wid}/a/lancamentos"
        f"?start_date={month}-01&end_date={month}-{last_day:02d}"
    )
    page.goto(url)
    page.wait_for_load_state("networkidle")
    if is_login_redirect(page.url):
        print(f"err|session-expired|tx {month}")
        sys.exit(1)
    try:
        page.wait_for_selector(SELECTORS["tx_row"], timeout=10000)
    except Exception:
        pass
    page.wait_for_timeout(1500)

    rows = page.query_selector_all(SELECTORS["tx_row"])
    if not rows:
        # Genuinely-empty month: on the transactions view AND no day-headers.
        # A day-header only renders when that day has rows, so a header present
        # with zero rows means the row selector broke — error rather than
        # silently dropping a real month of spending.
        on_tx_view = page.query_selector("body.transactions")
        has_day_header = page.query_selector(SELECTORS["tx_day_header"])
        if on_tx_view and not has_day_header:
            return {
                "type": "tx",
                "month": month,
                "scraped_at": dt.datetime.now().isoformat(timespec="seconds"),
                "transactions": [],
            }
        excerpt = dump_dom_excerpt(page)
        print(f"err|selector-not-found|tx_row={SELECTORS['tx_row']}\n{excerpt}")
        sys.exit(1)

    # Walk headers and items in document order so each item inherits the date
    # from the most recent day-header above it.
    raw = page.evaluate(
        """(sel) => {
            const nodes = document.querySelectorAll(sel.tx_day_header + ', ' + sel.tx_row);
            const out = []; let cur = '';
            nodes.forEach((n) => {
                if (n.matches(sel.tx_day_header)) {
                    cur = (n.innerText || '').trim();
                } else {
                    const d = n.querySelector(sel.tx_description);
                    const a = n.querySelector(sel.tx_account);
                    const m = n.querySelector(sel.tx_amount);
                    out.push({
                        row_id: n.id || '',
                        date_label: cur,
                        description: d ? d.innerText.trim() : '',
                        account: a ? a.innerText.trim() : '',
                        amount_text: m ? m.innerText.trim() : '',
                        inflow: m ? m.classList.contains('inflow') : false,
                    });
                }
            });
            return out;
        }""",
        SELECTORS,
    )

    transactions = []
    for r in raw:
        transactions.append({
            "dom_id": dom_id_from_row_id(r["row_id"]),
            "date": list_date_to_iso(r["date_label"]),
            "description": r["description"],
            "amount_cents": amount_with_sign(r["amount_text"], r["inflow"]),
            "account": r["account"],
        })

    return {
        "type": "tx",
        "month": month,
        "scraped_at": dt.datetime.now().isoformat(timespec="seconds"),
        "transactions": transactions,
    }


def scrape_invoice(page, card_id: int, month: str, invoice_id: int) -> dict:  # type: ignore[no-untyped-def]
    wid = resolve_workspace_id(page)
    url = (
        f"{ORGANIZZE_URL}/{wid}/cartao-de-credito/{card_id}"
        f"/faturas/{card_id},{invoice_id}"
    )
    page.goto(url)
    page.wait_for_load_state("networkidle")
    if is_login_redirect(page.url):
        print(f"err|session-expired|invoice {card_id} {month}")
        sys.exit(1)
    try:
        page.wait_for_selector(SELECTORS["invoice_tx_row"], timeout=10000)
    except Exception:
        pass
    page.wait_for_timeout(1000)

    total_raw = page.evaluate(
        """(label) => {
            let node = null;
            document.querySelectorAll('*').forEach((e) => {
                if (e.children.length === 0 &&
                    (e.innerText || '').trim().toUpperCase() === label) node = e;
            });
            if (!node) return null;
            const cont = node.parentElement;
            if (!cont) return null;
            const cands = cont.querySelectorAll('big strong, big, strong');
            // Prefer the first money-shaped value so a sibling (due date,
            // minimum payment) can't be mistaken for the invoice total.
            for (const c of cands) {
                const t = (c.innerText || '').trim();
                if (/\\d[\\d.]*,\\d{2}/.test(t)) return t;
            }
            return cands.length ? cands[0].innerText.trim() : null;
        }""",
        SELECTORS["invoice_total_label"],
    )
    if total_raw is None:
        excerpt = dump_dom_excerpt(page)
        print(f"err|selector-not-found|invoice_total_label={SELECTORS['invoice_total_label']}\n{excerpt}")
        sys.exit(1)
    total_cents = parse_money(total_raw)

    raw = page.evaluate(
        """(sel) => {
            const out = [];
            document.querySelectorAll(sel.invoice_tx_row).forEach((n) => {
                const d = n.querySelector(sel.invoice_tx_date);
                const de = n.querySelector(sel.invoice_tx_description);
                const m = n.querySelector(sel.invoice_tx_amount);
                out.push({
                    row_id: n.id || '',
                    date_label: d ? d.innerText.trim() : '',
                    description: de ? de.innerText.trim() : '',
                    amount_text: m ? m.innerText.trim() : '',
                    inflow: m ? m.classList.contains('inflow') : false,
                });
            });
            return out;
        }""",
        SELECTORS,
    )

    transactions = []
    for r in raw:
        transactions.append({
            "dom_id": dom_id_from_row_id(r["row_id"]),
            "date": invoice_date_to_iso(r["date_label"], month),
            "description": r["description"],
            "amount_cents": amount_with_sign(r["amount_text"], r["inflow"]),
        })

    return {
        "type": "invoice",
        "card_id": card_id,
        "month": month,
        "invoice_id": invoice_id,
        "scraped_at": dt.datetime.now().isoformat(timespec="seconds"),
        "total_cents": total_cents,
        "transactions": transactions,
    }


def main() -> None:
    if len(sys.argv) < 2:
        print("err|usage|python3 scrape_slice.py <dashboard|tx YYYY-MM|invoice <card_id> YYYY-MM <invoice_id>>")
        sys.exit(1)

    if not SESSION.exists():
        print("err|no-session|run organizze_login.py first")
        sys.exit(1)

    SCRAPE_DIR.mkdir(parents=True, exist_ok=True)
    os.chmod(SCRAPE_DIR, 0o700)

    slice_type = sys.argv[1]
    month_re = re.compile(r"^\d{4}-\d{2}$")

    # Validate per-type args before importing playwright so malformed input
    # yields an err| line (the caller parses err|/ok|) instead of a traceback
    # from int()/month.split() further down.
    if slice_type == "tx":
        if len(sys.argv) < 3 or not month_re.match(sys.argv[2]):
            print("err|usage|python3 scrape_slice.py tx YYYY-MM")
            sys.exit(1)
    elif slice_type == "invoice":
        if (
            len(sys.argv) < 5
            or not sys.argv[2].isdigit()
            or not month_re.match(sys.argv[3])
            or not sys.argv[4].isdigit()
        ):
            print("err|usage|python3 scrape_slice.py invoice <card_id> YYYY-MM <invoice_id>")
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
        page.set_default_navigation_timeout(25000)

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
            invoice_id = int(sys.argv[4])
            data = scrape_invoice(page, card_id, month, invoice_id)
            slice_name = f"invoice_{card_id}_{month}"

        browser.close()

    out_path = SCRAPE_DIR / f"{slice_name}.json"
    out_path.write_text(json.dumps(data, ensure_ascii=False, indent=2))
    print(f"ok|scraped|{out_path}")


if __name__ == "__main__":
    main()
