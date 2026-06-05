# finance

Personal finance slash commands. Nested under `commands/finance/`, so each is invoked as **`/finance:<name>`** (Claude Code's path-as-namespace convention).

## Contents

| Command | One-liner |
|---|---|
| [`/finance:organizze`](#financeorganizze) | Pull Organizze data via REST API, build a snapshot, delegate to the [`financial-analyst`](../../agents/financial-analyst/README.md) subagent for a prioritized action plan. |
| [`/finance:goal`](#financegoal) | CRUD of financial goals (`~/finance/plans.md`). Provider-agnostic. |
| [`/finance:context`](#financecontext) | CRUD of restrictions/context (`~/finance/memory.md`). Provider-agnostic. |

## Layout

```
commands/finance/
├── README.md
├── organizze.md                 # /finance:organizze
├── goal.md                      # /finance:goal
├── context.md                   # /finance:context
├── scripts/                     # provider-agnostic
│   ├── _storage.py              # paths + legacy migration
│   ├── memory.py                # add/list/render/prune financial memory
│   └── plans.py                 # add/list/render/done/status/prune objectives
└── organizze-scripts/           # Organizze provider
    ├── _common.sh               # load_auth, curl_organizze, die, read_keychain_password
    ├── _paths.py                # HOME/AUTH/CONFIG/... + re-exports migrate_legacy
    ├── setup_auth.sh            # onboarding (stdin: email\ntoken\npassword)
    ├── pull.py                  # API client + snapshot consolidation
    ├── reconcile.py             # one-shot balance offset calibration
    ├── config.py                # ~/finance/organizze/.config helper
    ├── cashflow.py              # per-account daily balance projection
    ├── suggest_budgets.py       # budget suggestions for current + next month
    ├── analyze.py               # snapshot + memory + plans + framework → subagent prompt
    ├── organizze_login.py       # Playwright headless login → .session (storageState)
    ├── scrape_slice.py          # scraper for 1 slice (dashboard|tx YYYY-MM|invoice card_id YYYY-MM invoice_id)
    ├── apply_scrape.py          # consolidates scrape/*.json into the snapshot (surgical override)
    └── tests/
        └── test_apply_scrape.py # 13 merge/match/idempotency tests
```

```
~/finance/                       # storage (chmod 700, never in git)
├── memory.md                    # global: restrictions / context
├── plans.md                     # global: goals
└── organizze/                   # provider-specific
    ├── .auth                    # API credentials (chmod 600) — no web password
    ├── .config                  # CARD_PAYMENT_ACCOUNT_*, CASHFLOW_THRESHOLD_CENTS, SCRAPE_MAX_AGENTS, ...
    ├── .session                 # Playwright storageState (chmod 600) — never in git
    ├── balances.json            # initial-balance offsets per account
    ├── snapshots/YYYY-MM-DD-HHMM.json
    ├── reports/YYYY-MM-DD-HHMM.md
    ├── budget-suggestions/YYYY-MM-DD-HHMM.json
    ├── scrape/                  # scraping JSONs per slice (dashboard, tx_*, invoice_*)
    └── cache/categories.json
```

> **Legacy migration**: pre-refactor data in `~/finance-organizze/` is moved automatically on the first run of any script (Python or shell). `memory.md`/`plans.md` go to `~/finance/`; the rest goes to `~/finance/organizze/`. Idempotent.

## Conventions

- Local-only storage under `~/finance/` (chmod 600 on credentials, never committed).
- Python scripts use stdlib only, **except** `playwright` (new dependency, authorized; installed automatically by `setup_auth.sh`).
- Bash scripts follow the repo-wide pipe-delimited output (`ok|...`, `info|...`, `err|...`).
- Memory and plans are **provider-agnostic** — any future provider (Nubank scraper, manual CSV, etc.) consumes the same `~/finance/{memory,plans}.md`.

## Design notes

### Web scraping (raw Playwright, exception to the MCP rule)

Step 3.5 of `/finance:organizze` uses **raw Playwright (Python lib + Chromium)** called via Bash in each subagent — **outside the MCP `mcp__playwright-headless__*`**. This is an **explicit and authorized exception** to the global rule "always use `mcp__playwright__*` for all web browsing". The scope of the exception is limited to this authenticated Organizze scraping flow.

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

## /finance:organizze

Pulls personal financial data from **Organizze** via its official REST API, builds a consolidated snapshot, and delegates analysis to the [`financial-analyst`](../../agents/financial-analyst/README.md) subagent.

### What it does

1. Calls `https://api.organizze.com.br/rest/v2` to fetch accounts (with computed balances), categories, credit cards, invoices, past transactions (default 180d), future transactions (default 90d) and budgets (current + next 2 months).
2. Enriches locally: balance projections 7/30/90d, recurring detection (≥3 occurrences in 6m, <15% variation), top categories, MoM variation, overdue past transactions, parcelamento progress.
3. Renders a prompt that injects the snapshot + user memory + user plans + the system prompt from `agents/financial-analyst/financial-analyst.md`.
4. Delegates to the `financial-analyst` subagent; falls back to `general-purpose` if not installed.
5. Suggests budget updates (median 3m × p75 6m, ≥ current realized) for current + next month.
6. Offers to register new memory/plan entries (or redirect to `/finance:context` / `/finance:goal`).

### Prerequisites

- An Organizze account.
- Python 3.9+ with `pip3` in PATH.
- `curl` in PATH.
- macOS Keychain (`security` CLI) — native on macOS.
- `mcp__playwright__*` available (used only during the one-time token onboarding).
- `playwright` Python library + Chromium — **installed automatically by `setup_auth.sh`** (`pip3 install playwright` + `python3 -m playwright install chromium`).
- `financial-analyst` subagent installed — see [`agents/financial-analyst/README.md`](../../agents/financial-analyst/README.md).

### First run

Run `/finance:organizze`. The command will:

1. Detect missing credentials.
2. Open `https://app.organizze.com.br/configuracoes/api-keys` in Playwright (existing MCP session is reused).
3. Ask for your email, the generated API token, **and your web login password** via `AskUserQuestion`.
4. Validate API token via `GET /accounts`; store in `~/finance/organizze/.auth` (chmod 600). Store password in macOS Keychain — **never on disk in plain text**.
5. Install `playwright` + Chromium if not already present.
6. After the first pull, ask for the real balance of each principal account to seed the offset in `~/finance/organizze/balances.json` (Organizze's API doesn't return current balance — see [Balance reconciliation](#balance-reconciliation)).

From then on, plain `/finance:organizze` works — no interaction needed. The web session (`.session`) is reused and auto-renewed.

### Arguments

```
/finance:organizze [<free text> | --history-days N | --future-days N | --no-analyze]
```

Free text is classified and routed: goals → `/finance:goal`, restrictions → `/finance:context`, analytical questions → normal flow.

| Flag | Default | Purpose |
|---|---|---|
| `--history-days N` | 180 | History window for the analysis snapshot. |
| `--future-days N` | 90 | Forward window (scheduled + recurring projection). |
| `--no-analyze` | off | Pull + save snapshot, skip subagent delegation. |

### Balance reconciliation

The Organizze REST API **does not return current balance** in `/accounts`. `pull.py` reconstructs it by summing 5 years of paid transactions per account, excluding credit-card transactions (`credit_card_id != null`). The initial balance the user typed into the app when creating each account is not exposed and creates a gap.

Fix: on the first run, calibrate with the real balance shown in the app's "Minhas contas" widget:

```bash
python3 organizze-scripts/reconcile.py --snapshot <latest-snapshot.json> \
  <account_id>=<balance_in_cents> [<account_id>=<balance_in_cents> ...]
# Example: 1234567=80174 7654321=194746  (R$ 801.74 and R$ 1,947.46 — sample IDs)
```

This writes `~/finance/organizze/balances.json` (per-`account_id` offset in cents). Future pulls apply it automatically.

The **consolidated balance** uses only `checking`/`savings` accounts that are **not archived** and **not caixinhas** (`institution_id != "cofrinho"`) — matches the app's "Saldo geral" widget. Caixinhas and auxiliary accounts are listed separately in the report, never summed into the total.

---

## /finance:goal

Conversational wrapper over `scripts/plans.py`. Manages financial goals consumed by any provider.

```bash
# Inline via slash command — no arguments opens interactive menu:
/finance:goal
/finance:goal "save R$ 5000 for a trip in December"
/finance:goal list
/finance:goal done "2026-05-24 13:56"
/finance:goal pause "2026-05-24 13:55"

# Or directly in the script:
python3 scripts/plans.py add "..." --target-cents 500000 --deadline 2026-12-31 --priority negociavel
python3 scripts/plans.py list --status active
python3 scripts/plans.py done "<ts>"
python3 scripts/plans.py status "<ts>" paused
python3 scripts/plans.py prune --older-than-done 365
```

Storage: `~/finance/plans.md` (hand-editable). Inline header: `## <ts> [target=… · deadline=… · account=… · priority=… · status=…]`.

`analyze.py` injects the rendered version (`plans.py render`) into every analysis.

---

## /finance:context

Conversational wrapper over `scripts/memory.py`. Restrictions and context that analyses must respect.

```bash
/finance:context
/finance:context "medication X is a prescription — do not cut"
/finance:context list

# Or directly:
python3 scripts/memory.py add "..." [--tag <optional>]
python3 scripts/memory.py list --recent 10
python3 scripts/memory.py prune --older-than 365
```

Storage: `~/finance/memory.md` (hand-editable).

`analyze.py` injects the rendered version (`memory.py render`) and instructs the subagent not to contradict any item.

---

## Privacy

- Everything local (`~/finance/`). Nothing goes to git, nothing goes to the cloud.
- Organizze API is HTTPS-only.
- Credentials in `.auth` and `balances.json` with `chmod 600`.
- Commands never log the token; if shown in a message, it is masked.

## Design notes

- **API instead of scraping**: no CAPTCHA, no expired cookie, no fragile selector. Playwright only runs during token onboarding.
- The system prompt is read from `agents/financial-analyst/financial-analyst.md` by `analyze.py` (YAML frontmatter is stripped). Updating `financial-analyst.md` updates the analysis without touching code.
- Budgets are not writable via Organizze REST API (GET only). `suggest_budgets.py` produces a table + JSON; the user applies it in the UI.
- **Provider-agnostic**: `scripts/{memory,plans}.py` do not depend on Organizze. To add Nubank/Banco do Brasil/manual CSV in the future, create `<provider>.md` + `<provider>-scripts/` consuming the same `~/finance/{memory,plans}.md`.
