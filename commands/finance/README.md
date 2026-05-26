# finance

Personal finance slash commands. Nested under `commands/finance/`, so each is invoked as **`/finance:<name>`** (Claude Code's path-as-namespace convention).

## Contents

| Command | One-liner |
|---|---|
| [`/finance:organizze`](#financeorganizze) | Pull Organizze data via REST API, build a snapshot, delegate to the [`financial-analyst`](../../agents/financial-analyst/README.md) subagent for a prioritized action plan. |
| [`/finance:goal`](#financegoal) | CRUD de objetivos financeiros (`~/finance/plans.md`). Provider-agnóstico. |
| [`/finance:context`](#financecontext) | CRUD de restrições/contexto (`~/finance/memory.md`). Provider-agnóstico. |

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
    ├── _common.sh               # load_auth, curl_organizze, die
    ├── _paths.py                # HOME/AUTH/CONFIG/... + re-exports migrate_legacy
    ├── setup_auth.sh            # onboarding (stdin: email\ntoken)
    ├── pull.py                  # API client + snapshot consolidation
    ├── reconcile.py             # one-shot balance offset calibration
    ├── config.py                # ~/finance/organizze/.config helper
    ├── cashflow.py              # per-account daily balance projection
    ├── suggest_budgets.py       # budget suggestions for current + next month
    └── analyze.py               # snapshot + memory + plans + framework → subagent prompt
```

```
~/finance/                       # storage (chmod 700, never in git)
├── memory.md                    # global: restrições / contexto
├── plans.md                     # global: objetivos
└── organizze/                   # provider-specific
    ├── .auth                    # API credentials (chmod 600)
    ├── .config                  # CARD_PAYMENT_ACCOUNT_*, CASHFLOW_THRESHOLD_CENTS, ...
    ├── balances.json            # initial-balance offsets per account
    ├── snapshots/YYYY-MM-DD-HHMM.json
    ├── reports/YYYY-MM-DD-HHMM.md
    ├── budget-suggestions/YYYY-MM-DD-HHMM.json
    └── cache/categories.json
```

> **Legacy migration**: pre-refactor data in `~/finance-organizze/` is moved automatically on the first run of any script (Python or shell). `memory.md`/`plans.md` go to `~/finance/`; the rest goes to `~/finance/organizze/`. Idempotent.

## Conventions

- Local-only storage under `~/finance/` (chmod 600 on credentials, never committed).
- Python scripts use stdlib only — no `pip install`.
- Bash scripts follow the repo-wide pipe-delimited output (`ok|...`, `info|...`, `err|...`).
- Memory and plans are **provider-agnostic** — any future provider (Nubank scraper, manual CSV, etc.) consumes the same `~/finance/{memory,plans}.md`.

---

## /finance:organizze

Pulls personal financial data from **Organizze** via its official REST API, builds a consolidated snapshot, and delegates analysis to the [`financial-analyst`](../../agents/financial-analyst/README.md) subagent.

### What it does

1. Calls `https://api.organizze.com.br/rest/v2` to fetch accounts (with computed balances), categories, credit cards, invoices, past transactions (default 180d), future transactions (default 90d) and budgets (current + next 2 months).
2. Enriches locally: balance projections 7/30/90d, recurring detection (≥3 occurrences in 6m, <15% variation), top categories, MoM variation, overdue past transactions, parcelamento progress.
3. Renders a prompt that injects the snapshot + user memory + user plans + the system prompt extracted from `analista-financeiro-claude-code.md` (section 4.1).
4. Delegates to the `financial-analyst` subagent; falls back to `general-purpose` if not installed.
5. Suggests budget updates (median 3m × p75 6m, ≥ current realized) for current + next month.
6. Offers to register new memory/plan entries (or redirect to `/finance:context` / `/finance:goal`).

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
4. Validate via `GET /accounts` and store them in `~/finance/organizze/.auth` with `chmod 600`.
5. After the first pull, ask for the real balance of each principal account to seed the offset in `~/finance/organizze/balances.json` (Organizze's API doesn't return current balance — see [Balance reconciliation](#balance-reconciliation)).

From then on, plain `/finance:organizze` works — no browser, no re-login.

### Arguments

```
/finance:organizze [<texto livre> | --history-days N | --future-days N | --no-analyze]
```

Texto livre é classificado e roteado: objetivos → `/finance:goal`, restrições → `/finance:context`, perguntas analíticas → fluxo normal.

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

Wrapper conversacional sobre `scripts/plans.py`. Gerencia objetivos financeiros que qualquer provider consome.

```bash
# Inline via slash command — sem argumentos abre menu interativo:
/finance:goal
/finance:goal "guardar R$ 5000 para viagem em dezembro"
/finance:goal list
/finance:goal done "2026-05-24 13:56"
/finance:goal pause "2026-05-24 13:55"

# Ou direto no script:
python3 scripts/plans.py add "..." --target-cents 500000 --deadline 2026-12-31 --priority negociavel
python3 scripts/plans.py list --status active
python3 scripts/plans.py done "<ts>"
python3 scripts/plans.py status "<ts>" paused
python3 scripts/plans.py prune --older-than-done 365
```

Storage: `~/finance/plans.md` (editável à mão). Header inline: `## <ts> [target=… · deadline=… · account=… · priority=… · status=…]`.

`analyze.py` injeta a versão renderizada (`plans.py render`) em toda análise.

---

## /finance:context

Wrapper conversacional sobre `scripts/memory.py`. Restrições e contexto que análises devem respeitar.

```bash
/finance:context
/finance:context "remédio X é prescrição médica — não cortar"
/finance:context list

# Ou direto:
python3 scripts/memory.py add "..." [--tag <opcional>]
python3 scripts/memory.py list --recent 10
python3 scripts/memory.py prune --older-than 365
```

Storage: `~/finance/memory.md` (editável à mão).

`analyze.py` injeta a versão renderizada (`memory.py render`) e instrui o subagent a não contradizer nenhum item.

---

## Privacy

- Tudo local (`~/finance/`). Nada vai para git, nada vai para a nuvem.
- Organizze API é HTTPS-only.
- Credenciais em `.auth` e `balances.json` com `chmod 600`.
- Os comandos nunca logam o token; se for mostrado em mensagem, é mascarado.

## Design notes

- **API ao invés de scraping**: sem CAPTCHA, sem cookie expirado, sem seletor frágil. Playwright só roda no onboarding do token.
- O framework de análise (`analista-financeiro-claude-code.md` na raiz do repo) é **lido** por `analyze.py` — seção 4.1 vira system prompt do subagent. Atualizar o framework atualiza a análise sem mexer em código.
- Budgets não são escrevíveis via API REST do Organizze (só `GET`). `suggest_budgets.py` produz tabela + JSON; usuário aplica na UI.
- **Provider-agnóstico**: `scripts/{memory,plans}.py` não dependem do Organizze. Para adicionar Nubank/Banco do Brasil/CSV manual no futuro, crie `<provider>.md` + `<provider>-scripts/` consumindo os mesmos `~/finance/{memory,plans}.md`.
