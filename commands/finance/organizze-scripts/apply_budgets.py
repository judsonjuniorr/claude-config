#!/usr/bin/env python3
"""Apply budget limits to the Organizze web app via Playwright.

The Organizze REST API can't write budgets ("limite de gastos"), but the web
app can. This reads a suggestions JSON (from suggest_budgets.py) and sets each
category's limit on /<wsid>/limite-de-gastos, reusing the scraping .session.

Default is DRY-RUN — it prints what would change. Pass --apply to write.

Matching is by category id (suggestion.category_id == budget item id), so
duplicate category names (e.g. two "Nádia") are disambiguated correctly.
"""
from __future__ import annotations

import argparse
import glob
import json
import pathlib
import re
import sys

sys.path.insert(0, str(pathlib.Path(__file__).parent))
from _paths import HOME, chromium_executable_path

SESSION = HOME / ".session"
ORGANIZZE_URL = "https://app.organizze.com.br"

# Categories that are not real spending budgets — never write a limit for these.
DEFAULT_SKIP = {"transferências", "pagamento de fatura"}

# JS read of every rendered budget item's category id / name / current limit.
READ_ITEMS_JS = """() => {
  const out = [];
  document.querySelectorAll('zze-budgets-item').forEach(el => {
    try {
      const s = window.angular && angular.element(el).scope();
      const d = s && s.budgetsItem && s.budgetsItem.data;
      if (d) out.push({id: d.id, name: d.name, value: d.budget ? d.budget.value : 0, isParent: !!d.isParent});
    } catch (e) {}
  });
  return out;
}"""


def normalize(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").strip().lower())


def latest_suggestions() -> pathlib.Path | None:
    files = sorted(glob.glob(str(HOME / "budget-suggestions" / "*.json")))
    return pathlib.Path(files[-1]) if files else None


def value_to_cents(value) -> int:
    """Budget item .value is reais (e.g. '150' or 150). Convert to cents."""
    if value in (None, "", 0, "0"):
        return 0
    try:
        return round(float(str(value).replace(",", ".")) * 100)
    except ValueError:
        return 0


def workspace_id(page) -> str:
    page.goto(f"{ORGANIZZE_URL}/")
    page.wait_for_load_state("networkidle")
    page.wait_for_timeout(1500)
    m = re.search(r"/(\d+)/a/", page.url)
    if not m:
        print("err|no-workspace|could not resolve workspace id from", page.url)
        sys.exit(1)
    return m.group(1)


def find_item_handle(page, category_id: int):
    """Re-query the DOM (list re-renders after each save) and return the
    zze-budgets-item element handle whose scope category id matches."""
    for el in page.query_selector_all("zze-budgets-item"):
        data = el.evaluate(
            "el => { try { const s = angular.element(el).scope();"
            " const d = s && s.budgetsItem && s.budgetsItem.data;"
            " return d ? d.id : null; } catch (e) { return null; } }"
        )
        if data == category_id:
            return el
    return None


def set_one(page, el, cents: int) -> bool:
    """Open the popover for this item and write `cents`. Returns success."""
    trigger = el.query_selector("a.zze-bar-button-edit") or el.query_selector("a.zze-button-plus")
    if trigger is None:
        return False
    trigger.click()
    # The ng-model is shared by income+expense popovers — target the visible one.
    inp = page.locator('input[ng-model="budgets.data.amount"]:visible').first
    try:
        inp.wait_for(state="visible", timeout=8000)
    except Exception:
        page.keyboard.press("Escape")
        return False
    inp.fill("")
    inp.type(str(cents), delay=25)  # mask reads digits right-to-left as cents
    ok = page.locator('button[ng-click="budgets.newBudget()"]:visible').first
    if ok.count() == 0:
        page.keyboard.press("Escape")
        return False
    ok.click()
    page.wait_for_timeout(1800)  # let the save round-trip + re-render
    return True


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--suggestions", help="path to budget-suggestions JSON (default: latest)")
    ap.add_argument("--apply", action="store_true", help="actually write (default: dry-run)")
    ap.add_argument("--skip", default=",".join(sorted(DEFAULT_SKIP)),
                    help="comma-separated category names to skip")
    ap.add_argument("--include-parents", action="store_true",
                    help="also set budgets on parent categories (default: leaf only)")
    args = ap.parse_args()

    if not SESSION.exists():
        print("err|no-session|run organizze_login.py first")
        return 1

    sug_path = pathlib.Path(args.suggestions) if args.suggestions else latest_suggestions()
    if not sug_path or not sug_path.exists():
        print("err|no-suggestions|no budget-suggestions JSON found")
        return 1

    skip = {normalize(s) for s in args.skip.split(",") if s.strip()}
    data = json.loads(sug_path.read_text())
    targets = []
    for s in data.get("suggestions", []):
        if normalize(s.get("category_name")) in skip:
            continue
        targets.append({
            "id": s["category_id"],
            "name": s["category_name"],
            "cents": s["suggested_cents"],
        })

    print(f"info|suggestions|{sug_path.name}|targets={len(targets)} skip={sorted(skip)}", file=sys.stderr)

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("err|playwright-not-installed|run setup_scrape.sh")
        return 1

    applied, already, unmatched, failed = [], [], [], []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, executable_path=chromium_executable_path())
        ctx = browser.new_context(storage_state=str(SESSION))
        page = ctx.new_page()
        page.set_default_navigation_timeout(25000)

        wsid = workspace_id(page)
        page.goto(f"{ORGANIZZE_URL}/{wsid}/limite-de-gastos")
        page.wait_for_load_state("networkidle")
        page.wait_for_selector("zze-budgets-item", timeout=15000)
        page.wait_for_timeout(2500)

        items = page.evaluate(READ_ITEMS_JS)
        by_id = {it["id"]: it for it in items}

        for t in targets:
            item = by_id.get(t["id"])
            if item is None:
                unmatched.append(t)
                continue
            if item["isParent"] and not args.include_parents:
                print(f"info|skip-parent|{t['name']}", file=sys.stderr)
                continue
            cur_cents = value_to_cents(item["value"])
            if cur_cents == t["cents"]:
                already.append(t)
                continue

            label = f"{t['name']}|R$ {cur_cents/100:.2f} -> R$ {t['cents']/100:.2f}"
            if not args.apply:
                applied.append(t)  # would-apply
                print(f"dry|would-set|{label}", file=sys.stderr)
                continue

            el = find_item_handle(page, t["id"])
            if el is None or not set_one(page, el, t["cents"]):
                failed.append(t)
                print(f"err|set-failed|{label}", file=sys.stderr)
                continue

            # verify
            after = next((x for x in page.evaluate(READ_ITEMS_JS) if x["id"] == t["id"]), None)
            if after and value_to_cents(after["value"]) == t["cents"]:
                applied.append(t)
                print(f"ok|set|{label}", file=sys.stderr)
            else:
                got = value_to_cents(after["value"]) if after else "?"
                failed.append(t)
                print(f"err|verify-failed|{t['name']}|got {got}", file=sys.stderr)

        browser.close()

    verb = "would-apply" if not args.apply else "applied"
    print(f"{'dry' if not args.apply else 'ok'}|summary|{verb}={len(applied)},already={len(already)},"
          f"unmatched={len(unmatched)},failed={len(failed)}")
    if unmatched:
        print("info|unmatched|" + "; ".join(f"{t['name']}({t['id']})" for t in unmatched), file=sys.stderr)
    return 0 if not failed else 2


if __name__ == "__main__":
    raise SystemExit(main())
