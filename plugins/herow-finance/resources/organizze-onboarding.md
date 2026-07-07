# organizze — onboarding (first run)

On-demand resource for `/finance:organizze`. Read and follow when triggered from the main
command (Step 1 detects `.auth` missing; Steps 2.5/2.7 run after the first pull when their
conditions hold). The same `**Absolute paths**` and GLOBAL RULE (ask via `AskUserQuestion`)
from the main command apply here.

> **Resolve `$SNAP` at the start of every bash block in Steps 2.5 and 2.7** (each block is a new shell, so `$SNAP` does not persist; never re-derive via `$(date ...)`):
>
> ```bash
> SNAP=$(ls -t ~/finance/organizze/snapshots/*.json 2>/dev/null | grep -v '\.bak$' | head -1)
> ```

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
   printf '%s\n%s\n%s\n' "$EMAIL" "$TOKEN" "$PASSWORD" | bash ${CLAUDE_PLUGIN_ROOT}/scripts/organizze/setup_auth.sh
   ```
   Replace `$EMAIL`, `$TOKEN` and `$PASSWORD` with the real values (do not expose token/password in history — pass via heredoc).

5. The script installs the official `organizze` CLI if missing (reads go through it — see `_cli.py`), validates via `organizze status`, saves the password to Keychain, and installs Playwright+Chromium. If it returns `ok|auth-saved|...`, proceed. If `err|bad-credentials|...`, warn and redo Step 2. If `err|cli-install-failed|...`, the token was saved but the CLI install failed — retry manually (`brew install --cask organizze/tap/organizze` or the curl installer in the script) then re-run `organizze status`. If `err|scrape-setup-failed|...`, the token was saved but scraping setup failed — Step 3.5a will retry.

6. Close the browser:
   ```
   mcp__playwright__browser_close
   ```

## Step 2.5 — Balance check (optional, first run only)

`pull.py` now fetches the **real balance** per account via `organizze accounts get <id>` (the official CLI), so no reconstruction/calibration is needed anymore. This step is only a sanity check.

After the first `pull.py`:

1. Show the user, with `jq '.accounts | map(select(.archived==false and .institution_id != "cofrinho" and (.type == "checking" or .type == "savings"))) | map({id, name, balance: (._balance_cents / 100)})' "$SNAP"`, the real balance for each main account.

2. Use `AskUserQuestion` to confirm it matches the Organizze app. It should — these are the account's true balances, not a computed estimate. If it doesn't, that's a data issue (e.g. an archived/orphan account) worth investigating, not something to patch with an offset.

3. If a permanent adjustment is still needed for some reason (e.g. an external account not tracked in Organizze), an optional manual override is supported:
   ```bash
   python3 ${CLAUDE_PLUGIN_ROOT}/scripts/organizze/reconcile.py --snapshot "$SNAP" <id>=<cents> [<id>=<cents> ...]
   ```
   This writes `~/finance/organizze/balances.json`, added on top of the real balance on every future pull. Skip this step entirely in the common case.

## Step 2.7 — Map the paying account for each card (run when missing)

The per-account cash flow projection (Step 5+) needs to know **which account pays each card** to debit the invoice on the right date. Without this, invoices won't enter the projection and silent overdrafts may slip through.

After the first `pull.py` (Step 3), run:

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/scripts/organizze/config.py cards-missing --snapshot "$SNAP"
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
   python3 ${CLAUDE_PLUGIN_ROOT}/scripts/organizze/config.py card-account <card_id> <account_id>
   ```

Optional — alert threshold for critical days (default R$ 0, no margin):
```bash
python3 ${CLAUDE_PLUGIN_ROOT}/scripts/organizze/config.py set CASHFLOW_THRESHOLD_CENTS 20000
```
(`20000` = R$ 200 margin; projected balance below this becomes a "critical day".)

Mappings live in `~/finance/organizze/.config` (format `KEY=VALUE`, 0600). Manual editing is allowed.
