# finance

Personal finance slash commands, shipped by the **herow-finance** plugin
(`plugins/herow-finance/`). Each is invoked as **`/herow-finance:<name>`** (Claude
Code namespaces plugin commands by plugin name). Two providers: **Organizze**
(reads via the official `organizze` CLI, writes via REST API) and **Contabilizei**
(NF registration).

## Contents

| Command | One-liner |
|---|---|
| [`/herow-finance:organizze`](#herow-financeorganizze) | Pull Organizze data via the official `organizze` CLI, build a snapshot, delegate to the [`financial-analyst`](../plugins/herow-finance/agents/financial-analyst.md) subagent for a prioritized action plan. |
| [`/herow-finance:organizze-create`](#herow-financeorganizze-create) | **Write path.** Create a transaction in Organizze (account / card / specific invoice / transfer) via REST API. DRY-RUN by default, single Apply confirm, read-back verify. |
| [`/herow-finance:goal`](#herow-financegoal) | CRUD of financial goals (`~/finance/plans.md`). Provider-agnostic. |
| [`/herow-finance:context`](#herow-financecontext) | CRUD of restrictions/context (`~/finance/memory.md`). Provider-agnostic. |
| [`/herow-finance:profile`](#herow-financeprofile) | CRUD of the personal profile (age, profession, income, family, housing, city, risk) used to personalize analyses. Provider-agnostic. |
| [`/herow-finance:nf-tomada`](#herow-financenf-tomada) | Register a received NF (nota fiscal) in Contabilizei from a PDF/XML — headless login with the email code via Gmail, duplicate check, confirm before sending. |

## Layout

```
plugins/herow-finance/
├── commands/
│   ├── organizze.md             # /herow-finance:organizze
│   ├── organizze-create.md      # /herow-finance:organizze-create
│   ├── goal.md                  # /herow-finance:goal
│   ├── context.md               # /herow-finance:context
│   ├── profile.md               # /herow-finance:profile
│   └── nf-tomada.md             # /herow-finance:nf-tomada
├── agents/
│   └── financial-analyst.md     # subagent delegated by /herow-finance:organizze
├── resources/                   # on-demand sub-flows loaded by /herow-finance:organizze
│   ├── organizze-onboarding.md  # first-run token + CLI setup, balance sanity check, card mapping
│   ├── organizze-capture.md     # profile-capture prompt
│   ├── organizze-research.md    # research sub-flow
│   └── organizze-scrape.md      # Playwright scrape sub-flow
└── scripts/
    ├── finance/                 # provider-agnostic
    │   ├── _storage.py          # BASE=~/finance paths + legacy migration (migrate_legacy)
    │   ├── memory.py            # add/list/render/prune financial memory
    │   ├── plans.py             # add/list/render/done/status/prune goals
    │   └── profile.py           # personal profile CRUD
    ├── organizze/               # Organizze provider
    │   ├── _common.sh           # load_auth, curl_organizze, die, read_keychain_password
    │   ├── _cli.py              # read path: wraps the official `organizze` CLI (accounts/categories/cards/invoices/transactions/budgets)
    │   ├── _http.py             # write path only: http_post against REST v2 (reads moved to _cli.py)
    │   ├── _paths.py            # HOME/AUTH/CONFIG/... + re-exports migrate_legacy
    │   ├── setup_auth.sh        # onboarding (stdin: email\ntoken\npassword) — installs the `organizze` CLI, validates via `organizze status`
    │   ├── setup_scrape.sh      # idempotent playwright+chromium scrape setup
    │   ├── pull.py              # CLI-backed read path + snapshot consolidation
    │   ├── create.py            # write path: lookups via _cli.py, create transaction/transfer via REST (dry-run/apply/verify)
    │   ├── reconcile.py         # one-shot balance offset calibration
    │   ├── balance_on.py        # balance + forecast per account on a target date
    │   ├── config.py            # ~/finance/organizze/.config helper
    │   ├── cashflow.py          # per-account daily balance projection
    │   ├── suggest_budgets.py   # budget suggestions for current + next month
    │   ├── apply_budgets.py     # write budget limits to the web app via Playwright
    │   ├── analyze.py           # snapshot + memory + plans + framework → subagent prompt
    │   ├── sanitize.py          # PII removal (CPF/CNPJ, medical, account tokenization) → LLM-safe snapshot
    │   ├── compute.py           # deterministic metrics engine, reads sanitized snapshot
    │   ├── audit_log.py         # append-only JSONL log of analysis runs (~/finance/logs/)
    │   ├── enrichment_rules.yaml # category alias map + medical-keyword list (used by sanitize.py/compute.py)
    │   ├── organizze_login.py   # Playwright headless login → .session (storageState)
    │   ├── scrape_slice.py      # scraper for 1 slice (dashboard | tx | invoice)
    │   ├── apply_scrape.py      # consolidates scrape/*.json into the snapshot, recomputes meta.totais (surgical override)
    │   └── tests/
    │       ├── test_apply_scrape.py  # 15 merge/match/idempotency/meta.totais-recompute tests
    │       ├── test_sanitize.py      # PII-removal + scrape-debug-field-stripping tests
    │       ├── test_compute.py       # deterministic metrics tests
    │       ├── test_audit_log.py     # audit log append/dedup tests
    │       ├── test_enrichment.py    # category/medical enrichment rule tests
    │       ├── test_cli.py           # 32 _cli.py wrapper tests (subprocess mocked, balance parsing, exit-code mapping)
    │       ├── test_pull.py          # 10 pull.py CLI-backed read-path tests
    │       └── test_create.py        # 57 write-path tests (no network)
    └── contabilizei/            # Contabilizei provider (NF registration)
        ├── _creds.sh            # shared helpers (sourced)
        ├── setup.sh             # idempotent setup + pdfplumber install
        ├── extract_nf.py        # extract NF data from PDF/XML → JSON + TXT
        └── tests/
            └── test_extract_nf.py
```

```
~/finance/                       # storage (chmod 700, never in git)
├── memory.md                    # global: restrictions / context
├── plans.md                     # global: goals
├── profile.md                   # global: personal profile
├── organizze/                   # Organizze provider
│   ├── .auth                    # API credentials (chmod 600) — no web password
│   ├── .config                  # CARD_PAYMENT_ACCOUNT_*, CASHFLOW_THRESHOLD_CENTS, SCRAPE_MAX_AGENTS, ...
│   ├── .session                 # Playwright storageState (chmod 600) — never in git
│   ├── balances.json            # initial-balance offsets per account
│   ├── snapshots/YYYY-MM-DD-HHMM.json
│   ├── reports/YYYY-MM-DD-HHMM.md
│   ├── budget-suggestions/YYYY-MM-DD-HHMM.json
│   ├── scrape/                  # scraping JSONs per slice (dashboard, tx_*, invoice_*)
│   └── cache/categories.json
└── contabilizei/                # Contabilizei provider
    └── extracted/               # extracted NF JSON + TXT
```

> **Legacy migration**: pre-refactor data in `~/finance-organizze/` is moved automatically on the first run of any script (Python or shell). `memory.md`/`plans.md` go to `~/finance/`; the rest goes to `~/finance/organizze/`. Idempotent.

## Conventions

- Local-only storage under `~/finance/` (chmod 600 on credentials, never committed).
- Python scripts use stdlib only, **except** `playwright` (new dependency, authorized; installed automatically by `setup_auth.sh`).
- Bash scripts follow the repo-wide pipe-delimited output (`ok|...`, `info|...`, `err|...`).
- Memory and plans are **provider-agnostic** — any future provider (Nubank scraper, manual CSV, etc.) consumes the same `~/finance/{memory,plans}.md`.

## Design notes

### Web scraping (raw Playwright, exception to the MCP rule)

Step 3.5 of `/herow-finance:organizze` uses **raw Playwright (Python lib + Chromium)** called via Bash in each subagent — **outside the MCP `mcp__playwright-headless__*`**. This is an **explicit and authorized exception** to the global rule "always use `mcp__playwright__*` for all web browsing". The scope of the exception is limited to this authenticated Organizze scraping flow.

**Reason**: 1 MCP Playwright server = 1 browser + 1 active tab globally + serialized stdio. Subagents sharing the same MCP fight over the active tab and cannot run in true parallel. Per-agent browser gives true parallelism + session isolation + self-healing selectors (the Haiku subagent sees the DOM and fixes the selector).

### SCRAPE_MAX_AGENTS

Controls the maximum number of simultaneous Chromium browsers (each consumes ~150-200 MB). Default: 4. Configure in `~/finance/organizze/.config`:

```
SCRAPE_MAX_AGENTS=4
```

Reduce to 2 on low-RAM machines; increase to 6-8 on machines with 16+ GB.

### Credentials

- **API token** → `~/finance/organizze/.auth` (plain text, chmod 600, outside git).
- **Web password** → macOS Keychain (`security add-generic-password -s organizze-login`). **Never on disk in plain text.**
- **Playwright session** → `~/finance/organizze/.session` (storageState JSON, chmod 600). Reused across runs; automatic re-login on expiration detection.

### API-only degradation

Any failure in Step 3.5 (login, 2FA, scraping, consolidation) degrades silently to the API snapshot + WARN in the report. The analysis **never blocks**.

---

## /herow-finance:organizze

Pulls personal financial data from **Organizze** via the official [`organizze` CLI](https://github.com/organizze/agent-tools) (wrapping the REST v2 API), builds a consolidated snapshot, and delegates analysis to the [`financial-analyst`](../plugins/herow-finance/agents/financial-analyst.md) subagent.

### What it does

1. Calls the official `organizze` CLI (wrapping `https://api.organizze.com.br/rest/v2`) to fetch accounts (with real per-account balances), categories, credit cards, invoices, past transactions (default 180d), future transactions (default 90d) and budgets (current + next 2 months).
2. Enriches locally: balance projections 7/30/90d, recurring detection (≥3 occurrences in 6m, <15% variation), top categories, MoM variation, overdue past transactions, parcelamento progress.
3. Renders a prompt that injects the snapshot + user memory + user plans + the system prompt from `agents/financial-analyst.md`.
4. Delegates to the `financial-analyst` subagent; falls back to `general-purpose` if not installed.
5. Suggests budget updates (median 3m × p75 6m, ≥ current realized) for current + next month.
6. Offers to register new memory/plan entries (or redirect to `/herow-finance:context` / `/herow-finance:goal`).

### Prerequisites

- An Organizze account.
- Python 3.9+ with `pip3` in PATH.
- `curl` in PATH.
- The official [`organizze` CLI](https://github.com/organizze/agent-tools) — installed automatically by `setup_auth.sh` (brew cask, curl fallback) or via `/herow-core:doctor`.
- macOS Keychain (`security` CLI) — native on macOS.
- `mcp__playwright__*` available (used only during the one-time token onboarding).
- `playwright` Python library + Chromium — **installed automatically by `setup_auth.sh`** (`pip3 install playwright` + `python3 -m playwright install chromium`).
- `financial-analyst` subagent installed — see [`agents/financial-analyst.md`](../plugins/herow-finance/agents/financial-analyst.md).

### First run

Run `/herow-finance:organizze`. The command will:

1. Detect missing credentials.
2. Open `https://app.organizze.com.br/configuracoes/api-keys` in Playwright (existing MCP session is reused).
3. Ask for your email, the generated API token, **and your web login password** via `AskUserQuestion`.
4. Install the official `organizze` CLI if missing (brew cask, curl fallback), then validate credentials via `organizze status`; store the token in `~/finance/organizze/.auth` (chmod 600). Store password in macOS Keychain — **never on disk in plain text**.
5. Install `playwright` + Chromium if not already present.
6. After the first pull, show the real per-account balance from the CLI's `accounts get` and confirm it matches the app — no offset to seed anymore (see [Balance reconciliation](#balance-reconciliation)).

From then on, plain `/herow-finance:organizze` works — no interaction needed. The web session (`.session`) is reused and auto-renewed.

### Arguments

```
/herow-finance:organizze [<free text> | --history-days N | --future-days N | --no-analyze]
```

Free text is classified and routed: goals → `/herow-finance:goal`, restrictions → `/herow-finance:context`, analytical questions → normal flow.

| Flag | Default | Purpose |
|---|---|---|
| `--history-days N` | 180 | History window for the analysis snapshot. |
| `--future-days N` | 90 | Forward window (scheduled + recurring projection). |
| `--no-analyze` | off | Pull + save snapshot, skip subagent delegation. |

### Balance reconciliation

`pull.py` now fetches the **real per-account balance** via `organizze accounts get <id>` (the official CLI) — no reconstruction needed. The API returns it as a formatted string (`"R$ 1.234,56"`, unlike every other money field which is integer cents); `_cli.py`'s `_parse_brl_cents` parses it to cents.

The old approach — summing 5 years of paid transactions per account to estimate a balance the REST API didn't expose — is gone. What's left is an optional sanity check: on the first pull, confirm the CLI's real balance matches what the app shows.

If a permanent manual offset is still needed for some reason (e.g. an external account not tracked in Organizze), it's supported on top of the real balance:

```bash
python3 scripts/organizze/reconcile.py --snapshot <latest-snapshot.json> \
  <account_id>=<balance_in_cents> [<account_id>=<balance_in_cents> ...]
# Example: 1234567=80174 7654321=194746  (R$ 801.74 and R$ 1,947.46 — sample IDs)
```

This writes `~/finance/organizze/balances.json` (per-`account_id` offset in cents, added on top of the real balance). Future pulls apply it automatically. Skip this entirely in the common case.

The **consolidated balance** uses only `checking`/`savings` accounts that are **not archived** and **not caixinhas** (`institution_id != "cofrinho"`) — matches the app's "Saldo geral" widget. Caixinhas and auxiliary accounts are listed separately in the report, never summed into the total.

---

## /herow-finance:organizze-create

The first **write** path to Organizze (everything else is read-only). Creates a transaction via the REST API — on an account, on a credit card (invoice auto-resolved by date), on a specific invoice, or a transfer between bank accounts — with installments, recurrence, and income/expense by the sign of the amount.

### Safety spine (real money)

Mirrors `apply_budgets.py`: **DRY-RUN is the default**. No `POST` happens without `--apply`, and the command only passes `--apply` after a single Apply/Cancel confirmation via `AskUserQuestion`. Every write is **read-back verified** (mismatch → loud warning, never a silent ok). A recent-duplicate guard (same amount+description+date) warns and requires `--force`. The token is never logged.

### Split command/script

The command (`organizze-create.md`) parses natural language, fills gaps via `AskUserQuestion`, and renders the human confirmation line. The script (`create.py`) is non-interactive: it resolves names → ids via the official `organizze` CLI (`_cli.py`'s `accounts_list`/`credit_cards_list`/`categories_list` cached 7d, `invoices_list` on demand — never the full `pull.py`), builds the payload, and POSTs via `_http.py`. Free text (description/notes) is passed via `--input-file` (a JSON file written by the Write tool) so it never enters a shell-parsed command line. Protocol: `info|`/`err|` on stderr, `ok|created|<id>` / `ok|transfer|<id>` on stdout.

```bash
# dry-run (no write):
python3 scripts/organizze/create.py --input-file /tmp/tx.json \
  --conta "NuConta" --despesa --valor 50 --data 2026-06-14
# apply (writes), passed by the command only after the Apply confirm:
python3 scripts/organizze/create.py --apply [--force] <same flags>
```

> **API write surface (verified vs. api-doc):** transaction `amount_cents` negative = expense; `account_id` XOR (`credit_card_id` + `credit_card_invoice_id`); `installments_attributes{periodicity,total}` XOR `recurrence_attributes{periodicity}`. Transfer (`POST /transfers`): `credit_account_id` = **origem** (saída), `debit_account_id` = **destino** (entrada), positive amount, bank accounts only.

---

## /herow-finance:goal

Conversational wrapper over `scripts/finance/plans.py`. Manages financial goals consumed by any provider.

```bash
# Inline via slash command — no arguments opens interactive menu:
/herow-finance:goal
/herow-finance:goal "save R$ 5000 for a trip in December"
/herow-finance:goal list
/herow-finance:goal done "2026-05-24 13:56"
/herow-finance:goal pause "2026-05-24 13:55"

# Or directly in the script:
python3 scripts/finance/plans.py add "..." --target-cents 500000 --deadline 2026-12-31 --priority negociavel
python3 scripts/finance/plans.py list --status active
python3 scripts/finance/plans.py done "<ts>"
python3 scripts/finance/plans.py status "<ts>" paused
python3 scripts/finance/plans.py prune --older-than-done 365
```

Storage: `~/finance/plans.md` (hand-editable). Inline header: `## <ts> [target=… · deadline=… · account=… · priority=… · status=…]`.

`analyze.py` injects the rendered version (`plans.py render`) into every analysis.

---

## /herow-finance:context

Conversational wrapper over `scripts/finance/memory.py`. Restrictions and context that analyses must respect.

```bash
/herow-finance:context
/herow-finance:context "medication X is a prescription — do not cut"
/herow-finance:context list

# Or directly:
python3 scripts/finance/memory.py add "..." [--tag <optional>]
python3 scripts/finance/memory.py list --recent 10
python3 scripts/finance/memory.py prune --older-than 365
```

Storage: `~/finance/memory.md` (hand-editable).

`analyze.py` injects the rendered version (`memory.py render`) and instructs the subagent not to contradict any item.

---

## /herow-finance:profile

Conversational wrapper over `scripts/finance/profile.py`. Manages the personal profile (age, profession, income, family, housing, city, risk tolerance) that the `financial-analyst` subagent uses to personalize recommendations.

```bash
/herow-finance:profile               # interactive menu (init when empty)
/herow-finance:profile set income 12000
/herow-finance:profile get income
/herow-finance:profile list

# Or directly:
python3 scripts/finance/profile.py set <key> <value>
python3 scripts/finance/profile.py list
```

Storage: `~/finance/profile.md` (hand-editable, provider-agnostic). `analyze.py` injects the rendered profile into every analysis.

---

## /herow-finance:nf-tomada

The **Contabilizei** provider — registers a received NF (nota fiscal de serviço tomado) in the Contabilizei web app from a PDF or XML. Headless Playwright login with the email verification code read via Gmail, duplicate check against already-registered NFs, and an explicit confirmation before submitting.

```bash
/herow-finance:nf-tomada ~/Downloads/nota-fiscal.pdf
```

- `extract_nf.py` parses the PDF/XML → JSON + TXT under `~/finance/contabilizei/extracted/`.
- `setup.sh` is idempotent (creates dirs, installs `pdfplumber`).
- The flow asks for confirmation before any write to Contabilizei.

---

## Privacy

- Everything local (`~/finance/`). Nothing goes to git, nothing goes to the cloud.
- Organizze API is HTTPS-only.
- Credentials in `.auth` and `balances.json` with `chmod 600`.
- Commands never log the token; if shown in a message, it is masked.

## Design rationale

- **API-first**: reads go through the official `organizze` CLI, transaction writes go through the REST API directly (no CAPTCHA, no expired cookie, no fragile selector). Playwright is used only for token onboarding, optional dashboard scraping enrichment, and the two web-only writes below.
- The system prompt is read from `agents/financial-analyst.md` by `analyze.py` (YAML frontmatter is stripped). Updating `financial-analyst.md` updates the analysis without touching code.
- **Write paths**: transactions/transfers are writable via REST (`create.py`, dry-run + verify). **Budgets** ("limite de gastos") are *not* in the REST API, so `apply_budgets.py` writes them through the web app via Playwright; `suggest_budgets.py` produces the table + JSON it consumes.
- **Provider-agnostic**: `scripts/finance/{memory,plans,profile}.py` do not depend on Organizze. To add Nubank/Banco do Brasil/manual CSV in the future, create a `<provider>.md` command + `scripts/<provider>/` consuming the same `~/finance/{memory,plans,profile}.md`.
