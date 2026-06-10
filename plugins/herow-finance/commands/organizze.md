---
description: (herow) Pulls data from Organizze via REST API and generates a consolidated financial analysis (balance, projection, recommendations).
allowed-tools: Bash, Read, Write, AskUserQuestion, Agent, mcp__playwright__browser_navigate, mcp__playwright__browser_close, mcp__playwright__browser_snapshot
argument-hint: "[<free text> | --history-days N | --future-days N | --no-analyze]"
---

# /finance:organizze — Organizze → consolidated analysis

> **GLOBAL RULE — questions to the user:** every question requiring a user response must be asked via the `AskUserQuestion` tool, with 2-4 structured options (the free-text "Other" field is automatic). **Never** ask questions inline in text. Applies to all steps below.

> **Recommended subagent (when installed):** Step 6 delegates analysis to the `financial-analyst` subagent via the `Agent` tool. If the file `~/.claude/agents/financial-analyst.md` does not exist, the step automatically falls back to `general-purpose` — the command continues to work. To install the dedicated subagent, run `install.sh` in this repo and select `financial-analyst`.

When the user invokes `/finance:organizze`, follow these steps **exactly**. Skip none. Do not pre-inspect (do not run `git status`, do not list directories, do not check versions — go straight to the scripts; they are self-contained and handle legacy migration automatically).

Optional arguments (parse from `$ARGUMENTS`):
- `--history-days N` (default 180)
- `--future-days N` (default 90)
- `--no-analyze` → only pull and save the snapshot, do not call the subagent

**Absolute paths**:
- Global scripts (provider-agnostic): `/Users/judson/sources/personal/claude-config/commands/finance/scripts/`
- Organizze scripts: `/Users/judson/sources/personal/claude-config/commands/finance/organizze-scripts/`
- Global storage: `~/finance/` (`memory.md`, `plans.md`, `profile.md`)
- Organizze storage: `~/finance/organizze/` (`snapshots/`, `reports/`, `budget-suggestions/`, `.auth`, `.config`, `balances.json`)
- System prompt (read by `analyze.py`): `/Users/judson/sources/personal/claude-config/agents/financial-analyst/financial-analyst.md`

---

## Step 0 — Intent routing

If `$ARGUMENTS` is empty or contains only flags (`--history-days`, `--future-days`, `--no-analyze`), go directly to Step 1 (normal analysis flow).

If `$ARGUMENTS` contains natural language text, **do not run pull/analyze just to "have context"** — they are expensive (minutes) and exist only for the analysis flow. Classify:

- **Financial goal/target** (amount + deadline + something to buy/contract/pay off/save — "trip", "pay off X", "save R$ Y by Z", "emergency fund"): **redirect to `/finance:goal`** telling the user in 1 line "This looks like a goal — opening `/finance:goal`" and follow that command's instructions passing `$ARGUMENTS` as text.

- **Restriction/context** (statements about what **not** to change, prescriptions, non-negotiables — "I can't reduce X", "Y is a medical prescription", "Z is non-negotiable"): **redirect to `/finance:context`** with the same logic.

- **Personal profile update** (statements about identity/life — "I'm 32", "I live in SP", "I earn R$ 12k", "I'm married", "I have 2 kids", "I work as a dev"): **redirect to `/finance:profile`** saying "This looks like a profile update — opening `/finance:profile`" and follow that command's instructions passing `$ARGUMENTS`.

- **Analysis request/question** (anything else: "how am I doing", "what should I cut", "will I miss anything?"): continue to Step 1.

When genuinely unsure between the 3 destinations, ask the user with `AskUserQuestion` which to open. When unsure between registering and analyzing, ask.

---

## Step 1 — Verify auth

```bash
ls ~/finance/organizze/.auth 2>/dev/null
```

- **File exists** → skip to Step 3.
- **Does not exist** → execute Step 2.

## Step 2 — Onboarding (first run)

1. Open the token page via headed Playwright (the MCP session is already authenticated):
   ```
   mcp__playwright__browser_navigate → https://app.organizze.com.br/configuracoes/api-keys
   ```

2. Show the user in chat:
   > I opened the Organizze API keys page. Create a new token (click "Gerar nova chave"), copy it, and paste it below.

3. Use `AskUserQuestion` with three questions:
   - "What is your Organizze account email?" (header: "Email")
   - "Paste the generated token:" (header: "Token")
   - "What is your Organizze web login password? (used to scrape real values; stored in Keychain, never on disk)" (header: "Password")

4. Save the credentials by running the script (email+token → `.auth`; password → Keychain; installs Playwright):
   ```bash
   printf '%s\n%s\n%s\n' "$EMAIL" "$TOKEN" "$PASSWORD" | bash /Users/judson/sources/personal/claude-config/commands/finance/organizze-scripts/setup_auth.sh
   ```
   Replace `$EMAIL`, `$TOKEN` and `$PASSWORD` with the real values (do not expose token/password in history — pass via heredoc).

5. The script validates via `GET /accounts`, saves the password to Keychain, and installs Playwright+Chromium. If it returns `ok|auth-saved|...`, proceed. If `err|bad-credentials|...`, warn and redo Step 2. If `err|scrape-setup-failed|...`, the token was saved but scraping setup failed — Step 3.5a will retry.

6. Close the browser:
   ```
   mcp__playwright__browser_close
   ```

## Step 2.5 — Calibrate initial balance (first run only)

The Organizze `/accounts` API **does not return the current balance** — `pull.py` calculates it by summing paid transactions from the past 5 years. The initial balance the user entered when creating the account in the app **is not exposed** and creates a discrepancy.

After the first `pull.py`, if `~/finance/organizze/balances.json` does not yet exist:

1. Show the user, with `jq '.accounts | map(select(.archived==false and .institution_id != "cofrinho" and (.type == "checking" or .type == "savings"))) | map({id, name, calculated: (._balance_cents / 100)})' "$SNAP"`, the calculated balance for each main account.

2. Use `AskUserQuestion` to confirm: "Does the calculated balance match what appears in the Organizze app for each account?" If not, ask the real balance account by account (in reais, e.g.: `801.74`).

3. Call:
   ```bash
   python3 /Users/judson/sources/personal/claude-config/commands/finance/organizze-scripts/reconcile.py --snapshot "$SNAP" <id>=<cents> [<id>=<cents> ...]
   ```
   E.g.: `1234567=80174 7654321=194746` (R$ 801.74 and R$ 1,947.46 — illustrative IDs).

4. The script writes `~/finance/organizze/balances.json` with the per-account offset. Future pulls apply it automatically — no need to repeat.

5. Re-run `pull.py` (Step 3) to validate.

Skip this step if `balances.json` already exists.

## Step 2.7 — Map the paying account for each card (run when missing)

The per-account cash flow projection (Step 5+) needs to know **which account pays each card** to debit the invoice on the right date. Without this, invoices won't enter the projection and silent overdrafts may slip through.

After the first `pull.py` (Step 3), run:

```bash
python3 /Users/judson/sources/personal/claude-config/commands/finance/organizze-scripts/config.py cards-missing --snapshot "$SNAP"
```

Output: `<card_id>|<card_name>` line by line — only cards without a mapping. If empty, skip this step.

For each line:

1. Show the user the active main accounts:
   ```bash
   jq '[.accounts[] | select(.archived==false and .institution_id != "cofrinho" and (.type == "checking" or .type == "savings"))] | map({id, name})' "$SNAP"
   ```

2. `AskUserQuestion`: "Which account is the invoice for **<card_name>** debited from?" — dynamic options (one per main account).

3. Save:
   ```bash
   python3 /Users/judson/sources/personal/claude-config/commands/finance/organizze-scripts/config.py card-account <card_id> <account_id>
   ```

Optional — alert threshold for critical days (default R$ 0, no margin):
```bash
python3 /Users/judson/sources/personal/claude-config/commands/finance/organizze-scripts/config.py set CASHFLOW_THRESHOLD_CENTS 20000
```
(`20000` = R$ 200 margin; projected balance below this becomes a "critical day".)

Mappings live in `~/finance/organizze/.config` (format `KEY=VALUE`, 0600). Manual editing is allowed.

## Step 2.8 — Fill in missing personal profile fields

Recommendation personalization depends on the profile in `~/finance/profile.md` (age, profession, income, family, housing, city, risk tolerance). If a critical field is empty, the subagent will emit `[QUESTION]` at the end — better to fill it before analysis.

1. Check whether to ask now:
   ```bash
   python3 /Users/judson/sources/personal/claude-config/commands/finance/scripts/profile.py should-ask
   ```
   - Exit code 1 → profile is complete OR silenced (`last_skip` < 7d). Skip to Step 3.
   - Exit code 0 → there are missing fields and it's not silenced. Continue.

2. List missing fields:
   ```bash
   MISSING=$(python3 /Users/judson/sources/personal/claude-config/commands/finance/scripts/profile.py missing)
   ```

3. For each field in `$MISSING` (limit **6 questions per run** — the rest will be asked next time):
   - Use `AskUserQuestion` with the format appropriate for the field (single-select with enum + "Skip" for `estado_civil`, `moradia_tipo`, `tolerancia_risco`; open text for the rest).
   - Suggested questions per field (identical to Mode 4 of `/finance:profile`):
     - `idade`: "How old are you?"
     - `profissao`: "What is your profession / how do you earn money?"
     - `renda_liquida_mensal_cents`: "What is your average net monthly income in R$?" → convert to cents.
     - `estado_civil`: options `solteiro / relacionamento / casado / divorciado / viuvo` + Skip.
     - `dependentes`: "Do you have dependents? How many and their ages, or 'none'."
     - `moradia_tipo`: options `owned (paid off) / owned (mortgaged) / rented / provided / other` + Skip. Map option text to enum: "owned (paid off)" → `propria_quitada`, "owned (mortgaged)" → `propria_financiada`, "rented" → `alugada`, "provided" → `cedida`, "other" → `outra`.
     - `moradia_custo_cents`: "How much do you pay for housing per month (installment or rent) in R$? Use 0 if zero." → convert to cents.
     - `cidade`: "What city/state do you live in? E.g.: 'São Paulo, SP'." — used in market research.
     - `tolerancia_risco`: options `conservador / moderado / agressivo` + Skip. Include a short description of each.
   - For each valid answer (not "Skip"), save immediately:
     ```bash
     python3 /Users/judson/sources/personal/claude-config/commands/finance/scripts/profile.py set <key> "<value>"
     ```

4. If the user skipped **all** the fields asked, save a 7-day silence:
   ```bash
   python3 /Users/judson/sources/personal/claude-config/commands/finance/scripts/profile.py mark-skip
   ```

5. Proceed to Step 3 (Pull). The updated profile will be included in the Step 5 prompt.

## Step 3 — Pull snapshot

```bash
SNAP=~/finance/organizze/snapshots/$(date +%F-%H%M).json
python3 /Users/judson/sources/personal/claude-config/commands/finance/organizze-scripts/pull.py \
  --out "$SNAP" \
  --history-days <N or 180> \
  --future-days <N or 90>
```

The script prints `info|...` lines on stderr (counts per endpoint) and a final `ok|snapshot|<path>` line on stdout. On error: `err|<code>|<detail>`.

> **CRITICAL — snapshot path between steps:** each bash block runs in a new shell, so the variable `SNAP` **does not persist**. NEVER re-derive `SNAP=...$(date +%F-%H%M).json` in a later step (the timestamp changes and the file won't exist → `FileNotFoundError`). In **all** subsequent steps (3.5, 4, 5, 5.6, 7), resolve the most recent snapshot at the start of the block:
> ```bash
> SNAP=$(ls -t ~/finance/organizze/snapshots/*.json 2>/dev/null | grep -v '\.bak$' | head -1)
> ```
> This is the canonical path. Always use it whenever you need `$SNAP` in a new block.

Error handling:
- `err|http-401|...` → token rejected. Delete `~/finance/organizze/.auth` and return to Step 2.
- `err|http-400|...` → User-Agent rejected. Check `~/finance/organizze/.auth` (field `ORGANIZZE_USER_AGENT`).
- `err|network|...` → fail fast, report to the user.

## Step 3.5 — Web scraping (real values via raw Playwright per subagent)

> **Authorized exception to the global rule**: this step uses raw Playwright (Bash) in each subagent, outside the MCP — because 1 MCP = 1 browser/1 active tab globally + serialized stdio → no real parallelism. Per-agent browser gives real parallelism + isolation. If scraping fails for any reason, degrade silently to API-only (snapshot remains; add WARN at the start of the report).

### 3.5a — Ensure scraping setup (Playwright + password) and web session

**IMPORTANT**: scraping setup is independent of the API `.auth`. Users who already had `.auth` (created before this feature) do NOT have Playwright installed nor the web password in Keychain — this step covers that case. Do not skip assuming "it's already configured".

```bash
SCRIPTS=/Users/judson/sources/personal/claude-config/commands/finance/organizze-scripts
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

### 3.5b — Enumerate slices to scrape

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

### 3.5c — Fan-out of Haiku subagents (parallel, limited by SCRAPE_MAX_AGENTS)

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
  python3 /Users/judson/sources/personal/claude-config/commands/finance/organizze-scripts/scrape_slice.py <SLICE ARGS>
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

### 3.5d — Consolidate scrapes into the snapshot

After **all** subagents return, check the results:

- Subagents with `err|session-expired|...` → re-login once: `python3 "$SCRIPTS/organizze_login.py"`. Re-fire the subagents with expired sessions.
- If re-login fails or critical slices (`dashboard`) don't return `ok|...` → **degrade to API-only** with WARN.

If at least `dashboard` returned `ok|scraped|...`, consolidate (resolve `SNAP` in the same block):

```bash
SCRIPTS=/Users/judson/sources/personal/claude-config/commands/finance/organizze-scripts
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

---

## Step 4 — If `--no-analyze`, stop here

Print the snapshot path and totals (use `jq '.meta.totais' "$SNAP"`). Do not call the subagent.

## Step 5 — Render the base analysis prompt

```bash
TS=$(date +%F-%H%M)
REPORT=~/finance/organizze/reports/$TS.md
RESEARCH_DIR=~/finance/organizze/research/$TS
mkdir -p "$RESEARCH_DIR"
PROMPT_FILE=~/finance/organizze/reports/$TS.prompt.md
```

Do not invoke `analyze.py` yet — first we need to fire the research (Step 5.5) and then render the prompt with `--research-dir` pointing to it.

`analyze.py` reads the snapshot + system prompt from `agents/financial-analyst/financial-analyst.md` + injects `profile.md`, `memory.md`, `plans.md`, and the contents of `$RESEARCH_DIR` (pre-collected research) — returns a single prompt ready to deliver to the subagent.

## Step 5.5 — Parallel market research (with cache)

Instead of `financial-analyst` running 3 `WebSearch` calls sequentially within its own context (slow and consumes its tokens), **fire `search-specialist` in parallel now** and save the reports to `$RESEARCH_DIR/<category>.md` — `analyze.py` injects them as a "Market research (PRE-COLLECTED)" block.

Before firing a new agent, **check the cache** (default TTL 14 days): if a recent report for that category already exists in any `~/finance/organizze/research/<TS>/<category>.md`, reuse it by copying to the current `$RESEARCH_DIR`.

1. List the target categories + city from the profile (pipe-delimited output):
   ```bash
   TARGETS=$(python3 /Users/judson/sources/personal/claude-config/commands/finance/organizze-scripts/analyze.py --snapshot "$SNAP" --list-targets)
   echo "$TARGETS"
   ```
   Expected format, 1 record per line:
   - `profile|cidade|<city or "(no data)">`
   - `target|<category name>|<total_cents>|<median_6m_cents>|<top5 transactions separated by ';'>`

2. Parse:
   - `CITY` = value from the `profile|cidade|...` line (use the literal `"the user's city"` if it's `(no data)`).
   - Each `target|...` line becomes an entry with `name`, `total_cents`, `top_txs`.

3. **For each target, check the cache first** (TTL 14d configurable). Split into two groups: `CACHED` and `MISSING`:
   ```bash
   for cat in <list of names>; do
     CACHED_PATH=$(python3 /Users/judson/sources/personal/claude-config/commands/finance/organizze-scripts/analyze.py \
       --research-cache-lookup "$cat" --max-age-days 14)
     if [ -n "$CACHED_PATH" ]; then
       cp "$CACHED_PATH" "$RESEARCH_DIR/$cat.md"
       echo "info|cache-hit|$cat|$CACHED_PATH" >&2
     else
       echo "info|cache-miss|$cat" >&2
       # add $cat to the MISSING list
     fi
   done
   ```
   Expected output: each category becomes `cache-hit` (report copied, no agent fired) or `cache-miss` (needs research).

   To force re-research of everything (ignore cache), use `--max-age-days 0`. For a longer TTL (e.g.: 30 days), `--max-age-days 30`.

4. If ALL are cache-hits, skip to Step 6 (render prompt and invoke analyst — no agents). Otherwise, **fire ALL pending agents IN A SINGLE MESSAGE with multiple parallel `Agent` tool calls** (1 per cache-miss category). DO NOT run in series. Configuration per call:
   - `subagent_type`: `search-specialist`
   - `description`: `Market research: <category>`
   - `prompt`:
     ```
     Research cheaper alternatives for spending in the category "<CATEGORY NAME>" considering the user lives in "<CITY>".
     
     Current monthly spending in this category: R$ <formatted total>.
     6-month median: R$ <median>.
     Top 5 transactions this month in this category:
       - <transaction 1>
       - <transaction 2>
       - ... (up to 5)
     
     Goal: find 3-5 legitimate and cheaper alternatives, viable for the user. Focus on comparable quality (don't compare a car to a bicycle). For each:
       - Name of the option
       - Current price (R$/month or R$/unit, as applicable)
       - Source URL (prioritize official sites — comparison sites like Buscapé/Zoom OK if official site has no price)
       - Differentiator / catch / restriction the user should know (e.g.: limited coverage, loyalty requirement, perceived quality)
     
     Required output:
       1. 1-paragraph summary (most recommended alternative + why).
       2. List of 3-5 alternatives in the format above.
       3. Table of consulted sources (URL, date, authority H/M/L).
     
     If nothing useful is found (category too specific or no public alternative), respond only "(no alternative found)" and justify in 1 line.
     ```

5. After each agent returns, save the report (raw text returned) in a separate file:
   ```bash
   # For each category with cache-miss, write the report returned by the agent to:
   # $RESEARCH_DIR/<category_name>.md
   # (keep the exact category name — analyze.py uses the file stem as header
   # and also for future cache lookups)
   ```

6. If ALL pending categories fail (rare), the files are missing from `$RESEARCH_DIR` — `analyze.py` injects only the ones that exist, and the analyst's rule 14 directs using WebSearch as fallback for the rest.

7. Now render the prompt **with** the `--research-dir`:
   ```bash
   python3 /Users/judson/sources/personal/claude-config/commands/finance/organizze-scripts/analyze.py \
     --snapshot "$SNAP" --research-dir "$RESEARCH_DIR" --out "$PROMPT_FILE"
   ```

## Step 5.6 — Balance and forecast per account (base for the transfer plan)

`balance_on.py` is the factual source for transfer recommendations: for a given date, it returns per main account (and per caixinha, in a separate section) the **current balance**, the **forecast (Organizze)** = balance + unpaid future transactions + invoices due by that date in the paying account (matches the app's "previsto" widget), and the **forecast with overdue items** = also sums past-due unpaid transactions. Generate the block for key dates and **append to `$PROMPT_FILE`** before delegating.

1. Define target dates: end of current month, +30d, +60d and end of the horizon (use the same `--future-days` as Step 3 — so no date exceeds the snapshot range). E.g.:
   ```bash
   FUTURE_DAYS=<N or 90>   # identical to --future-days in Step 3
   DATES="$(FUTURE_DAYS="$FUTURE_DAYS" python3 - <<'PY'
import datetime as dt, calendar, os
t = dt.date.today()
horizon = int(os.environ.get("FUTURE_DAYS", "90"))
def eom(d):
    return d.replace(day=calendar.monthrange(d.year, d.month)[1])
cands = {eom(t), t + dt.timedelta(days=30), t + dt.timedelta(days=60),
         t + dt.timedelta(days=horizon)}
ds = sorted(d.isoformat() for d in cands if d <= t + dt.timedelta(days=horizon))
print(" ".join(ds))
PY
)"
   ```

2. Append the tables (one per date) to the prompt:
   ```bash
   {
     echo
     echo "# Balance and forecast per account (generated by balance_on.py — DO NOT invent numbers)"
     echo "Use as the basis for the **Transfer and savings plan**: for each date, compare the **Forecast (Organizze)** column across main accounts. Where an account has a negative forecast (or below CASHFLOW_THRESHOLD_CENTS), propose moving the slack from another MAIN account with a positive forecast on the same date — stating origin → destination, amount and date. Caixinhas/reserves are the LAST resort: only suggest using them when NO main account has enough slack to cover the shortfall; when doing so, explicitly label it 'emergency use of reserve' and quantify how much of the reserve would be consumed. Use **Forecast with overdue** to see the real impact of past-due transactions. If not even reserves can cover it, flag the shortfall and suggest adjustments (defer/cut an unpaid expense, accelerate income)."
     for D in $DATES; do
       echo
       python3 /Users/judson/sources/personal/claude-config/commands/finance/organizze-scripts/balance_on.py \
         --snapshot "$SNAP" --date "$D"
     done
   } >> "$PROMPT_FILE"
   ```

3. If the warning `⚠️ Cards WITHOUT paying account` appears, run Step 2.7 (`config.py card-account ...`) and re-run — without the mapping, invoices won't enter the forecast and the transfer plan will be underestimated.

## Step 6 — Delegate to the `financial-analyst` subagent

Use the `Agent` tool:
- `subagent_type`: `financial-analyst` if it exists at `~/.claude/agents/financial-analyst.md`. If it does not exist, **warn the user** ("subagent not installed — use `general-purpose` this time? To install, run `ln -sf <claude-config-root>/agents/financial-analyst/financial-analyst.md ~/.claude/agents/`") and proceed with `general-purpose`.
- `description`: `Monthly Organizze financial analysis`
- `prompt`: the contents of `$PROMPT_FILE` (rendered in step 5.5 with pre-collected research).

Save the subagent's response to `$REPORT`.

## Step 6.5 — Capture new memory/goal (optional)

After analysis, offer to register new context/goals. Each block is independent; skip if the user has nothing.

**6.5a — Memory/restriction** — ask via `AskUserQuestion` (single-select with "Skip"):

> Do you want to register any restriction or context for future analyses? Examples: "I can't reduce the house installment", "medication X is a prescription", "tithe is non-negotiable".

If there is a response, save:

```bash
python3 /Users/judson/sources/personal/claude-config/commands/finance/scripts/memory.py add "<user text>" [--tag <optional>]
```

(Or tell the user they can run `/finance:context` later.)

**6.5b — Financial goal** — ask via `AskUserQuestion` (single-select with "Skip"):

> Do you want to register a financial goal? E.g.: "save R$ 5000 for a trip in December", "pay off debt X by June", "build an emergency fund of R$ 20000".

If there is a response, ask short follow-up questions in sequence (each with "Skip" when optional):

1. **Descriptive text**: already captured.
2. **Target amount (R$)**: ask and convert to cents (e.g.: `5000` → `500000`).
3. **Deadline (YYYY-MM-DD)**: optional. "December" → last day of the mentioned month.
4. **Destination account**: optional. Show list of main accounts + caixinhas from the snapshot.
5. **Priority**: `negociavel` (default) or `inegociavel`.

Save:

```bash
python3 /Users/judson/sources/personal/claude-config/commands/finance/scripts/plans.py add "<text>" \
  --target-cents <N> \
  [--deadline <YYYY-MM-DD>] \
  [--account "<name>"] \
  [--priority negociavel|inegociavel]
```

(Or tell the user they can run `/finance:goal` later.)

Memory and goals live in `~/finance/{memory,plans}.md` — provider-agnostic. `analyze.py` injects them automatically into future analyses. To manage outside the analysis flow: `/finance:context` and `/finance:goal`.

## Step 6.6 — Answer open questions from the subagent

The subagent emits up to 3 questions at the end of the report, in the exact format `[QUESTION] <text>` (one per line, no hyphen/bullet prefix). Capture them and bring them to the user.

1. Parse `$REPORT` saved in Step 6 — tolerate bullet/hyphen/indentation the subagent may add:
   ```bash
   QUESTIONS=$(grep -oE '\[QUESTION\][^[:cntrl:]]*' "$REPORT" | sed 's/^\[QUESTION\][[:space:]]*//')
   ```

2. If empty (or contains only `(no open questions)`), skip to Step 7.

3. For each question (max 3), use `AskUserQuestion` (single-select with "Skip"):
   - Question header: derive 1-2 words from the content (e.g.: "Emergency fund", "Phone plan", "External debt").
   - Options: 2-3 reasonable answers when inferable (e.g.: for "is this subscription essential?", offer "Yes — keep / No — can cut / Depends — explain"); otherwise, open format.
   - "Skip" always available.

4. For each valid response (not "Skip"), save to memory:
   ```bash
   python3 /Users/judson/sources/personal/claude-config/commands/finance/scripts/memory.py add "<question + condensed answer>" --tag <derived tag>
   ```
   - Example tags: `subscription`, `debt`, `home`, `transport`, `goal`.

5. Confirm in 1 line: "N memories saved — next `/finance:organizze` will take them into account." **Do not re-invoke the subagent** in this turn.

## Step 7 — Suggest budget updates

After the subagent analysis, run:

```bash
python3 /Users/judson/sources/personal/claude-config/commands/finance/organizze-scripts/suggest_budgets.py \
  --snapshot "$SNAP" --top 20
```

The script:
- Calculates, per category, `max(3m median, 6m p75)`, ensures ≥ current month's realized amount, rounds to R$ 10.
- Prints a markdown table: Current | Realized | 3m Median | 6m p75 | **Suggested** | Δ | Confidence.
- Saves JSON to `~/finance/organizze/budget-suggestions/YYYY-MM-DD-HHMM.json` with the payloads (current_month + next_month).

Show the table to the user and say:

> The Organizze REST API does not allow updating budgets via HTTP — apply manually at https://app.organizze.com.br/orcamento. JSON with the values is at `<path>` for reference.

If `--history-days` in Step 3 was less than 180, warn: "short history, low confidence — I suggest re-running `/finance:organizze` with `--history-days 180` for more robust suggestions".

## Step 8 — Present to the user

Print in chat, in this order:

1. The subagent report content. Expected structure (15 sections):
   - TL;DR (cites ≥1 profile field)
   - Key numbers
   - Overdue items — immediate action
   - **Category goals — status**
   - **User goals — viability this month**
   - **Transfer and savings plan** (highlight visually — this is the heart of the analysis)
   - **Goals paused this cycle** (if any)
   - Installment plans — actionable view
   - **Specific cuts suggested** (3-5 `[CUT]` merchant-level)
   - **Prioritized payoff** (avalanche/snowball + ordered list)
   - **Market alternatives** (3 blocks with URL+price from WebSearch research)
   - 3 prioritized recommendations (each with "Why for you" referencing the profile)
   - Verifiable next steps
   - **Open questions** (lines `[QUESTION]` captured in Step 6.6)
   - Disclaimer
2. Final line:
   ```
   📄 Snapshot: <SNAP path>
   📊 Report: <REPORT path>
   ```

Do not invent numbers. If the subagent does not cover any field in "Key numbers", mark `(no data)` instead of guessing.

---

## General rules

- **Do not pre-inspect** the filesystem before Step 1. Go straight.
- **Never commit** `~/finance/`. It is outside the repo.
- **Never expose** the token in logs or messages. If it must be shown, mask it as `org_xxx…xxx`.
- If the user runs twice in a row, each run generates files with a distinct timestamp — no corruption.
- Legacy migration from `~/finance-organizze/` → `~/finance/{,organizze/}` is automatic on the first run of any script. Do not run anything manually.

## Related commands

- **`/finance:goal`** — CRUD of financial goals (`~/finance/plans.md`).
- **`/finance:context`** — CRUD of restrictions/context (`~/finance/memory.md`).
- **`/finance:profile`** — CRUD of the personal profile (`~/finance/profile.md`) — used to personalize recommendations.

All three are provider-agnostic: any future provider consumes the same storage.

## Recommended subagents

Subagent from this repo (`agents/`) that improves results when installed. The command works without it — Step 6 automatically falls back to `general-purpose`.

- **[`financial-analyst`](../../../agents/financial-analyst/)** — personalized personal financial analysis (consumes Organizze snapshots, respects user memories, generates a prioritized action plan). Install via `install.sh` selecting `financial-analyst`.
