# finance

Personal finance slash commands. Nested under `commands/finance/`, so each is invoked as **`/finance:<name>`** (Claude Code's path-as-namespace convention for nested command folders).

## Contents

| Command | One-liner |
|---|---|
| [`/finance:organizze`](#financeorganizze) | Pull Organizze data via REST API, build a snapshot, delegate to the [`financial-analyst`](../../agents/financial-analyst/README.md) subagent for a prioritized action plan. |

## Conventions

- Local-only storage under `~/finance-<name>/` (chmod 600 on credentials, never committed).
- Python scripts use stdlib only — no `pip install`.
- Bash scripts follow the repo-wide pipe-delimited output (`ok|...`, `info|...`, `err|...`).
- Scripts for each command live next to it as `<name>-scripts/` (no nested folder named like the command, to keep the `/finance:<name>` URL clean).

---

## /finance:organizze

Pulls personal financial data from **Organizze** via its official REST API, builds a consolidated snapshot, and delegates analysis to the [`financial-analyst`](../../agents/financial-analyst/README.md) subagent.

### What it does

1. Calls `https://api.organizze.com.br/rest/v2` to fetch accounts (with computed balances), categories, credit cards, invoices, past transactions (default 180d), future transactions (default 90d) and budgets (current + next 2 months).
2. Enriches locally: balance projections 7/30/90d, recurring detection (≥3 occurrences in 6m, <15% variation), top categories, MoM variation, overdue past transactions, parcelamento progress.
3. Renders a prompt that injects the snapshot + user memory + the system prompt extracted from `analista-financeiro-claude-code.md` (section 4.1).
4. Delegates to the `financial-analyst` subagent; falls back to `general-purpose` if not installed.
5. Suggests budget updates (median 3m × p75 6m, ≥ current realized) for current + next month.
6. Asks if the user wants to add a memory entry (constraints / context that future analyses must respect).

### Prerequisites

- An Organizze account.
- Python 3 (stdlib only — no `pip install`).
- `curl` in PATH.
- `mcp__playwright__*` available (only used during the one-time token onboarding).
- `financial-analyst` subagent installed — see [`agents/financial-analyst/README.md`](../../agents/financial-analyst/README.md).

### First run

Run `/finance:organizze`. The command will:

1. Detect missing credentials.
2. Open `https://app.organizze.com.br/configuracoes/api-keys` in Playwright (existing MCP session is reused).
3. Ask for your email and the generated token via `AskUserQuestion`.
4. Validate via `GET /accounts` and store them in `~/finance-organizze/.auth` with `chmod 600`.
5. After the first pull, ask for the real balance of each principal account to seed the offset in `~/finance-organizze/balances.json` (Organizze's API doesn't return current balance — see [Balance reconciliation](#balance-reconciliation)).

From then on, plain `/finance:organizze` works — no browser, no re-login.

### Arguments

```
/finance:organizze [--history-days N] [--future-days N] [--no-analyze]
```

| Flag | Default | Purpose |
|---|---|---|
| `--history-days N` | 180 | History window for the analysis snapshot. |
| `--future-days N` | 90 | Forward window (scheduled + recurring projection). |
| `--no-analyze` | off | Pull + save snapshot, skip subagent delegation. Useful for cron-style runs. |

### Generated files

```
~/finance-organizze/
├── .auth                              # API credentials (chmod 600, never in git)
├── balances.json                      # per-account initial-balance offsets (chmod 600)
├── memory.md                          # user constraints/context (markdown, editable)
├── snapshots/YYYY-MM-DD-HHMM.json     # consolidated snapshot per run
├── reports/YYYY-MM-DD-HHMM.md         # subagent output per run
├── budget-suggestions/YYYY-MM-DD-HHMM.json
└── cache/categories.json              # 7-day cache of category IDs → names
```

### Structure

```
commands/finance/
├── README.md
├── organizze.md                  # frontmatter + numbered procedure (agent-facing)
└── organizze-scripts/
    ├── _common.sh                # load_auth, curl_organizze, die
    ├── setup_auth.sh             # onboarding (stdin: email\ntoken)
    ├── pull.py                   # API client + snapshot consolidation
    ├── reconcile.py              # one-shot balance offset calibration
    ├── suggest_budgets.py        # budget suggestions for current + next month
    ├── memory.py                 # add/list/render/prune financial memory
    └── analyze.py                # snapshot + memory + framework → subagent prompt
```

All Python is stdlib-only. Bash uses `set -u`. Script output follows the repo's pipe-delimited convention (`ok|...`, `info|...`, `err|...`).

### Balance reconciliation

The Organizze REST API **does not return current balance** in `/accounts`. `pull.py` reconstructs it by summing 5 years of paid transactions per account, excluding credit-card transactions (`credit_card_id != null`). The initial balance the user typed into the app when creating each account is not exposed and creates a gap.

Fix: on the first run, calibrate with the real balance shown in the app's "Minhas contas" widget:

```bash
python3 organizze-scripts/reconcile.py --snapshot <latest-snapshot.json> \
  <account_id>=<balance_in_cents> [<account_id>=<balance_in_cents> ...]
# Example: 1575443=80174 5044376=194746  (R$ 801,74 and R$ 1.947,46)
```

This writes `~/finance-organizze/balances.json` (per-`account_id` offset in cents). Future pulls apply it automatically.

The **consolidated balance** uses only `checking`/`savings` accounts that are **not archived** and **not caixinhas** (`institution_id != "cofrinho"`) — matches the app's "Saldo geral" widget. Caixinhas and auxiliary accounts are listed separately in the report, never summed into the total.

### Financial memory

Constraints/context the AI must respect across analyses live in `~/finance-organizze/memory.md` (editable markdown, one `## YYYY-MM-DD HH:MM` section per entry).

```bash
# add
python3 organizze-scripts/memory.py add "Não posso reduzir parcela do financiamento da casa (taxa fixa contrato 2023)"
python3 organizze-scripts/memory.py add --tag prescrição "Mounjaro é orientação médica — não cortar sem consulta"

# inspect / prune
python3 organizze-scripts/memory.py list --recent 10
python3 organizze-scripts/memory.py prune --older-than 365
```

`analyze.py` loads everything automatically and instructs the subagent: "respect these constraints, never propose anything that contradicts them". Recent entries weigh more; the rendered block tags each entry as `recente` / `vigente` / `antiga`.

### Privacy

- Everything local (`~/finance-organizze/`). Nothing reaches git, nothing reaches cloud.
- Organizze API is HTTPS-only.
- Credentials live in `.auth` and `balances.json` with `chmod 600`.
- The command never logs the token; if shown in a message, it's masked.

### Design notes

- **API instead of scraping**: no CAPTCHA, no expired cookie, no fragile selector. Playwright only runs during token onboarding.
- The analysis framework (`analista-financeiro-claude-code.md` at the repo root) is **read** by `analyze.py` — section 4.1 is injected as the subagent's system prompt. Update the framework, the analysis updates with it. No code change.
- Budgets aren't writeable via Organizze's REST API (only `GET`). `suggest_budgets.py` outputs a table + JSON; user applies in the app UI.
