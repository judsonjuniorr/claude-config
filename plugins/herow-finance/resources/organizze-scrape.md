# organizze — web scraping subsystem (Step 3.5)

On-demand resource for `/finance:organizze`. Read and follow after the Step 3 pull, before
Step 4. Scrapes real values to enrich the API snapshot. **If anything fails, degrade
silently to API-only** (snapshot remains; add the WARN line below at the start of the
final report) and continue at Step 4. The main command's `**Absolute paths**` apply.

> **Authorized exception to the global rule**: this step uses raw Playwright (Bash) in each subagent, outside the MCP — because 1 MCP = 1 browser/1 active tab globally + serialized stdio → no real parallelism. Per-agent browser gives real parallelism + isolation. If scraping fails for any reason, degrade silently to API-only (snapshot remains; add WARN at the start of the report).

## 3.5a — Ensure scraping setup (Playwright + password) and web session

**IMPORTANT**: scraping setup is independent of the API `.auth`. Users who already had `.auth` (created before this feature) do NOT have Playwright installed nor the web password in Keychain — this step covers that case. Do not skip assuming "it's already configured".

```bash
SCRIPTS=${CLAUDE_PLUGIN_ROOT}/scripts/organizze
bash "$SCRIPTS/setup_scrape.sh" </dev/null
```

Output:
- `ok|scrape-ready|...` → setup complete, proceed to login below.
- `err|no-web-password|...` → web password missing from Keychain. Use `AskUserQuestion` (header "Password", one question) asking for the Organizze web login password. Then save + finish setup:
  ```bash
  printf '%s' "$PASSWORD" | bash "$SCRIPTS/setup_scrape.sh"
  ```
  Replace `$PASSWORD` with the real value (pass via heredoc/printf, never expose in history). Wait for `ok|scrape-ready|...`.
- `err|playwright-install-failed|...` / `err|chromium-install-failed|...` → **degrade to API-only** with WARN (environment without pip/network).
- `err|no-auth|...` → should not happen (Step 1 ensures `.auth`). **Degrade to API-only**.

With `ok|scrape-ready|...`, log in (creates/validates `.session`):

```bash
python3 "$SCRIPTS/organizze_login.py"
```

Expected output:
- `ok|session-valid|...` or `ok|session-saved|...` → proceed to 3.5b.
- `err|credentials-missing|...` → password disappeared from Keychain between steps (rare). Repeat `setup_scrape.sh` with the password.
- `err|2fa-detected|...` → 2FA active. **Degrade to API-only** with WARN: "scraping unavailable — 2FA detected; run with headed mode manually to create .session".
- `err|bad-credentials|...` → incorrect password in Keychain. Use `AskUserQuestion` asking for the password again and re-save via `setup_scrape.sh`; if it persists, **degrade to API-only**.
- `err|playwright-not-installed|...` → setup did not complete. **Degrade to API-only** with WARN.
- Any other `err|...` → **degrade to API-only** with WARN.

If degrading, **skip all of Step 3.5** and continue at Step 4.

## 3.5b — Enumerate slices to scrape

From the snapshot generated in Step 3, extract the slices (resolve `SNAP` in the same block — see critical note in Step 3):

```bash
SNAP=$(ls -t ~/finance/organizze/snapshots/*.json 2>/dev/null | grep -v '\.bak$' | head -1)
SNAP_JSON=$(python3 - "$SNAP" <<'PY'
import json, sys, calendar, datetime as dt

snap = json.load(open(sys.argv[1]))

slices = ["dashboard"]

# months with transactions (history + future months present in snapshot)
months = set()
for tx in snap.get("transactions_past", []) + snap.get("transactions_future", []):
    d = (tx.get("date") or "")[:7]
    if d:
        months.add(d)
for m in sorted(months):
    slices.append(f"tx {m}")

# invoices: one per (card_id, month) pair. The invoice id (the seq in the
# fatura URL /faturas/<card_id>,<invoice_id>) is required to open the page.
for inv in snap.get("invoices", []):
    cid = inv.get("_credit_card_id") or inv.get("credit_card_id")
    month = (inv.get("date") or "")[:7]
    inv_id = inv.get("id")
    if cid and month and inv_id:
        slices.append(f"invoice {cid} {month} {inv_id}")

print("\n".join(slices))
PY
)
```

## 3.5c — Fan-out of Haiku subagents (parallel, limited by SCRAPE_MAX_AGENTS)

`SCRAPE_MAX_AGENTS` controls how many browsers run simultaneously (default 4). Read from `~/finance/organizze/.config` if it exists; otherwise use 4.

```bash
SCRAPE_MAX_AGENTS=$(python3 -c "
import pathlib, re
cfg = pathlib.Path.home() / 'finance/organizze/.config'
if cfg.exists():
    for line in cfg.read_text().splitlines():
        m = re.match(r'^SCRAPE_MAX_AGENTS=(.+)$', line.strip())
        if m:
            print(m.group(1).strip('\"').strip(\"'\")); exit()
print('4')
")
```

Fire **all** subagents at once in a single message with multiple parallel `Agent` tool calls (up to `SCRAPE_MAX_AGENTS` simultaneous; if there are more slices, fire in batches of `SCRAPE_MAX_AGENTS`).

For each slice, call `Agent` with:
- `subagent_type`: `claude` (Haiku model — cheaper)
- `model`: `haiku`
- `description`: `Scrape Organizze: <slice>`
- `prompt`:
  ```
  Scrape the slice "<SLICE>" from Organizze using raw Playwright.
  
  Run:
  ```bash
  python3 ${CLAUDE_PLUGIN_ROOT}/scripts/organizze/scrape_slice.py <SLICE ARGS>
  ```
  
  Where <SLICE ARGS> is:
  - For "dashboard": `dashboard`
  - For "tx YYYY-MM": `tx YYYY-MM`
  - For "invoice <card_id> YYYY-MM <invoice_id>": `invoice <card_id> YYYY-MM <invoice_id>` (pass all 3 args verbatim)
  
  If the command returns `ok|scraped|...`, respond only with the output line.
  
  If it returns `err|selector-not-found|...` followed by a DOM excerpt:
  1. Read the DOM excerpt carefully.
  2. Identify the correct CSS selectors for the elements (account name, balance, transaction row, etc.) based on the real HTML.
  3. Update the `scrape_slice.py` file with the corrected selectors (edit only the `SELECTORS` dictionary at the top of the file — do not change the logic).
  4. Re-run the command. Max 2 selector correction attempts.
  5. If it still fails, respond `err|gave-up|<slice>|<detail>`.
  
  If `.session` has expired (redirect to /login), respond `err|session-expired|<slice>`.
  Any other error: respond with the exact error line.
  ```

## 3.5d — Consolidate scrapes into the snapshot

After **all** subagents return, check the results:

- Subagents with `err|session-expired|...` → re-login once: `python3 "$SCRIPTS/organizze_login.py"`. Re-fire the subagents with expired sessions.
- If re-login fails or critical slices (`dashboard`) don't return `ok|...` → **degrade to API-only** with WARN.

If at least `dashboard` returned `ok|scraped|...`, consolidate (resolve `SNAP` in the same block):

```bash
SCRIPTS=${CLAUDE_PLUGIN_ROOT}/scripts/organizze
SNAP=$(ls -t ~/finance/organizze/snapshots/*.json 2>/dev/null | grep -v '\.bak$' | head -1)
python3 "$SCRIPTS/apply_scrape.py" --snapshot "$SNAP"
```

Output:
- `ok|applied|...` → snapshot updated with web values. Continue.
- `warn|unreconciled|...` → partially applied. Continue but note in the report: "Some items not reconciled — see `_scrape_unreconciled` in the snapshot."
- `err|...` → **degrade to API-only** with WARN.

**Degradation WARN** (any failure in this step 3.5): add this line at the start of the final report (Step 8):

```
⚠️ WEB SCRAPING: [reason] — analysis based on estimated API values.
```
