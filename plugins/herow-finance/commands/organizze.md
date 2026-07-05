---
description: (herow) Pulls data from Organizze via REST API and generates a consolidated financial analysis (balance, projection, recommendations), then renders an interactive HTML dashboard artifact.
allowed-tools: Bash, Read, Write, AskUserQuestion, Agent, Artifact, mcp__playwright__browser_navigate, mcp__playwright__browser_close, mcp__playwright__browser_snapshot
argument-hint: "[<free text> | --history-days N | --future-days N | --no-analyze | --lang en|pt-br]"
effort: medium
---

# /finance:organizze — Organizze → consolidated analysis

> **GLOBAL RULE — questions to the user:** every question requiring a user response must be asked via the `AskUserQuestion` tool, with 2-4 structured options (the free-text "Other" field is automatic). **Never** ask questions inline in text. Applies to all steps below and to every on-demand resource.

> **Recommended subagent (when installed):** Step 6 delegates analysis to the `financial-analyst` subagent via the `Agent` tool. The agent ships with this plugin (herow-finance); if it is unavailable the step automatically falls back to `general-purpose` — the command continues to work.

When the user invokes `/finance:organizze`, follow these steps **exactly**. Skip none. Do not pre-inspect (do not run `git status`, do not list directories, do not check versions — go straight to the scripts; they are self-contained and handle legacy migration automatically).

Optional arguments (parse from `$ARGUMENTS`):
- `--history-days N` (default 180)
- `--future-days N` (default 90)
- `--no-analyze` → only pull and save the snapshot, do not call the subagent
- `--refresh` → force re-run of sanitize.py + compute.py even if recent outputs exist, then continue normally
- `--lang en|pt-br` → language of the Step 9 interactive artifact. Forgiving parse: accept `en`/`english` and `pt-br`/`ptbr`/`pt` (case-insensitive); an invalid value falls back to the prompt. Overrides **and** persists the remembered choice (`config.py set organizze_artifact_lang`)

**Absolute paths**:
- Global scripts (provider-agnostic): `${CLAUDE_PLUGIN_ROOT}/scripts/finance/`
- Organizze scripts: `${CLAUDE_PLUGIN_ROOT}/scripts/organizze/`
- Global storage: `~/finance/` (`memory.md`, `plans.md`, `profile.md`)
- Organizze storage: `~/finance/organizze/` (`snapshots/`, `reports/`, `budget-suggestions/`, `.auth`, `.config`, `balances.json`)
- System prompt (read by `analyze.py`): `${CLAUDE_PLUGIN_ROOT}/agents/financial-analyst.md`

> **On-demand resources** — detailed sub-flows live in `${CLAUDE_PLUGIN_ROOT}/resources/` and are loaded only when this command reaches them. When a step says *"read `<resource>` and follow it"*, open that file, execute its instructions inline (the GLOBAL RULE and the paths above still apply), then return here:
> - `organizze-onboarding.md` — first-run auth, balance calibration, card→account mapping (Steps 2 / 2.5 / 2.7)
> - `organizze-capture.md` — profile fill (Step 2.8) and post-analysis memory/goal capture + open questions (Steps 6.5 / 6.6)
> - `organizze-scrape.md` — web scraping subsystem (Step 3.5)
> - `organizze-research.md` — parallel market research + per-account forecast (Steps 5.5 / 5.6)

---

## Step 0 — Intent routing

If `$ARGUMENTS` is empty or contains only flags (`--history-days`, `--future-days`, `--no-analyze`, `--refresh`, `--lang`), go directly to Step 1 (normal analysis flow).

- **Longitudinal query** (`--compare-months N`): if `$ARGUMENTS` contains `--compare-months`, skip the full pipeline and run:
  ```bash
  python3 ${CLAUDE_PLUGIN_ROOT}/scripts/organizze/compute.py \
    --compare-months <N from argument, default 3>
  ```
  Print the output and stop. Do not run pull.py or analyze.py.

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
- **Does not exist** → first run: **read `${CLAUDE_PLUGIN_ROOT}/resources/organizze-onboarding.md` and follow §Step 2 (token setup)** to create `.auth`, then continue to Step 3.

## Steps 2 / 2.5 / 2.7 — Onboarding (first run)

All in `${CLAUDE_PLUGIN_ROOT}/resources/organizze-onboarding.md`:
- **§Step 2** (token setup) is triggered from Step 1 when `.auth` is missing.
- **§Step 2.5** (calibrate initial balance) and **§Step 2.7** (map paying account per card) run **after the first `pull.py` in Step 3** when their conditions hold (no `~/finance/organizze/balances.json`; `config.py cards-missing` returns rows). Read that file and follow those sections when you reach Step 3 on a first run.

## Step 2.8 — Fill in missing personal profile fields

Before pulling, optionally fill missing profile fields (improves personalization). **Read `${CLAUDE_PLUGIN_ROOT}/resources/organizze-capture.md` and follow §Step 2.8** — it self-checks via `profile.py should-ask` and skips silently when the profile is complete or recently silenced. Then proceed to Step 3.

## Step 3 — Pull snapshot

```bash
SNAP=~/finance/organizze/snapshots/$(date +%F-%H%M).json
python3 ${CLAUDE_PLUGIN_ROOT}/scripts/organizze/pull.py \
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

After pull.py runs successfully, print:
```
📅 Snapshot pulled at <meta.pulled_at>. Use --refresh to force re-sanitize.
```

**First run only:** after this pull, follow §Step 2.5 and §Step 2.7 of `organizze-onboarding.md` when their conditions hold (see Step 2 above).

## Step 3.1 — Sanitize snapshot (PII removal)

```bash
SNAP=$(ls -t ~/finance/organizze/snapshots/*.json 2>/dev/null | grep -v '\.bak$' | head -1)
SNAP_SAN=~/finance/organizze/snapshot_sanitized.json
python3 ${CLAUDE_PLUGIN_ROOT}/scripts/organizze/sanitize.py \
  --snapshot "$SNAP" --out "$SNAP_SAN"
```

Reads `$SNAP`, tokenizes account IDs (replaces with `acct_<sha256[:8]>`), strips CPF/CNPJ patterns, masks medical descriptions as `[MEDICAL_EXPENSE]`. Saves to `$SNAP_SAN`. Map stored at `~/finance/organizze/.id-map.json`.

On error: print the error and continue with `$SNAP_SAN` absent (analyze.py degrades gracefully when `--snapshot-sanitized` is not provided).

If `--refresh` was passed in `$ARGUMENTS`, run sanitize.py unconditionally regardless of whether `$SNAP_SAN` already exists.

## Step 3.2 — Compute deterministic metrics

```bash
SNAP_SAN=~/finance/organizze/snapshot_sanitized.json
if [ -f "$SNAP_SAN" ]; then
  python3 ${CLAUDE_PLUGIN_ROOT}/scripts/organizze/compute.py \
    --snapshot "$SNAP_SAN" --out ~/finance/organizze/metrics.json
fi
```

Writes `~/finance/organizze/metrics.json` with pre-computed burn, runway, category totals, and spending velocity alerts. `analyze.py` loads this inside `render_prompt` — no arithmetic by the LLM.

If `--refresh` was passed in `$ARGUMENTS`, run compute.py unconditionally (pass `--out` to overwrite existing metrics.json).

## Step 3.5 — Web scraping (real values via raw Playwright per subagent)

Enrich the snapshot with real scraped values. **Read `${CLAUDE_PLUGIN_ROOT}/resources/organizze-scrape.md` and follow it** (Steps 3.5a–3.5e). If scraping fails at any point, it degrades silently to API-only (snapshot remains; a WARN line is added at the start of the Step 8 report) and you continue at Step 4. Step 3.5e re-runs sanitize.py + compute.py so the sanitized snapshot and metrics.json reflect the scraped values, not the pre-scrape ones from Steps 3.1/3.2.

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

`analyze.py` reads the snapshot + system prompt from `agents/financial-analyst.md` + injects `profile.md`, `memory.md`, `plans.md`, and the contents of `$RESEARCH_DIR` (pre-collected research) — returns a single prompt ready to deliver to the subagent. It now also accepts `--snapshot-sanitized PATH` to use the PII-sanitized snapshot for the LLM prompt body.

> **Pre-flight — personalization data.** Before rendering, check which global state files exist:
> ```bash
> for f in memory plans profile; do [ -f ~/finance/$f.md ] || echo "missing: ~/finance/$f.md"; done
> ```
> `analyze.py` injects these silently — a missing `memory.md` (restrictions/context) or `plans.md` (goals) is dropped with no warning, and a missing `profile.md` renders as `(no data)`. If any are missing, tell the user in 1 line: "No <memory/plans/profile> on file — this analysis will be less personalized; you can add context via `/finance:context`, goals via `/finance:goal`, profile via `/finance:profile`." Then continue (do not block).

## Steps 5.5 / 5.6 — Market research & per-account forecast

**Read `${CLAUDE_PLUGIN_ROOT}/resources/organizze-research.md` and follow it.** Step 5.5 fires `search-specialist` in parallel (with a 14-day cache) and renders the prompt with `--research-dir`; Step 5.6 appends the `balance_on.py` per-account forecast block to `$PROMPT_FILE`. Then continue to Step 6.

## Step 6 — Delegate to the `financial-analyst` subagent

Use the `Agent` tool:
- `subagent_type`: `financial-analyst` if it exists at `~/.claude/agents/financial-analyst.md`. If it does not exist, **warn the user** ("subagent not installed — use `general-purpose` this time? To install, run `ln -sf <claude-config-root>/agents/financial-analyst.md ~/.claude/agents/`") and proceed with `general-purpose`.
- `description`: `Monthly Organizze financial analysis`
- `prompt`: the contents of `$PROMPT_FILE` (rendered in step 5.5 with pre-collected research).

Save the subagent's response to `$REPORT`.

## Steps 6.5 / 6.6 — Post-analysis capture

**Read `${CLAUDE_PLUGIN_ROOT}/resources/organizze-capture.md` and follow §Step 6.5 then §Step 6.6:**
- **§Step 6.5** (optional) — offer to register new memory/restriction and a financial goal.
- **§Step 6.6** — parse `$REPORT` for `[QUESTION]` lines and bring up to 3 to the user, saving answers to memory. If there are none, continue to Step 7.

## Step 6.7 — Append to audit log

```bash
SNAP=$(ls -t ~/finance/organizze/snapshots/*.json 2>/dev/null | grep -v '\.bak$' | head -1)
METRICS=~/finance/organizze/metrics.json
if [ -f "$METRICS" ]; then
  python3 ${CLAUDE_PLUGIN_ROOT}/scripts/organizze/audit_log.py \
    --snapshot "$SNAP" --metrics "$METRICS"
fi
```

Appends a JSONL entry to `~/finance/logs/YYYY-MM.jsonl`. Skips silently if the snapshot hash matches the last entry (duplicate run). Never fails fatally.

## Step 7 — Suggest budget updates

After the subagent analysis, run:

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/scripts/organizze/suggest_budgets.py \
  --snapshot "$SNAP" --top 20
```

The script:
- Calculates, per category, `max(3m median, 6m p75)`, ensures ≥ current month's realized amount, rounds to R$ 10.
- Prints a markdown table: Current | Realized | 3m Median | 6m p75 | **Suggested** | Δ | Confidence.
- Saves JSON to `~/finance/organizze/budget-suggestions/YYYY-MM-DD-HHMM.json` with the payloads (current_month + next_month).

Show the table to the user.

### Step 7.5 — Apply the budgets (Playwright via the scraping `.session`)

The Organizze REST API can't write budgets ("limite de gastos"), but the web app can. `apply_budgets.py` reuses the same `.session` created for scraping (Step 3.5) to set each category's limit on `/<wsid>/limite-de-gastos`, matching by `category_id` (so duplicate category names are disambiguated). It defaults to **DRY-RUN**; `--apply` writes and verifies each value by reading it back. `Transferências` and `Pagamento de fatura` are skipped automatically (not real spending limits).

Only run this when the scraping `.session` exists (it does whenever Step 3.5 did not degrade). If `~/finance/organizze/.session` is missing, **skip to the manual fallback** below.

1. Dry-run and show the diff to the user:
   ```bash
   python3 ${CLAUDE_PLUGIN_ROOT}/scripts/organizze/apply_budgets.py \
     --suggestions "$(ls -t ~/finance/organizze/budget-suggestions/*.json | head -1)"
   ```
   Output: `dry|would-set|<cat>|R$ a -> R$ b` lines + `dry|summary|would-apply=N,already=M,unmatched=U,failed=0`.

2. If `would-apply` > 0, **ask the user to confirm via `AskUserQuestion`** (single question, options "Apply / Skip") before writing — show the would-set diff in the question. Only on explicit confirmation, apply live:
   ```bash
   python3 ${CLAUDE_PLUGIN_ROOT}/scripts/organizze/apply_budgets.py \
     --suggestions "$(ls -t ~/finance/organizze/budget-suggestions/*.json | head -1)" --apply
   ```
   Report the `ok|summary|applied=N,already=M,unmatched=U,failed=F` line. If `unmatched` > 0 or `failed` > 0, list those categories so the user can set them manually.

3. **Manual fallback** — if auto-apply was skipped (no `.session`), declined, or partially failed, tell the user:
   > Apply the remaining budgets manually at https://app.organizze.com.br/orcamento. JSON with the values is at `<path>` for reference.

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

## Step 9 — Interactive artifact

After the Step 8 chat output, render a **self-contained, interactive HTML dashboard** via the `Artifact` tool. This is **presentation-only** over data already produced in this run — no new API pulls, no new financial math. The chat output of Step 8 is the source of truth and stays unchanged; the artifact is an additive deliverable.

> **GLOBAL RULE still applies:** the language question in 9c is asked via `AskUserQuestion` (never inline).

### 9a — Resolve inputs (all read-only, all optional)

Every source below may be absent at runtime — resolve what exists and degrade per source, never crash:

```bash
SNAP=$(ls -t ~/finance/organizze/snapshots/*.json 2>/dev/null | grep -v '\.bak$' | head -1)
METRICS=~/finance/organizze/metrics.json                                   # may be absent
BUDGETS=$(ls -t ~/finance/organizze/budget-suggestions/*.json 2>/dev/null | head -1)  # may be absent
TRENDS=$(python3 ${CLAUDE_PLUGIN_ROOT}/scripts/organizze/compute.py --compare-months 6 2>/dev/null)  # "not enough months" when <2
```

`$REPORT` is the report path written in Step 5 / saved in Step 6. `$SNAP .meta.totais` holds the headline totals (fallback when `metrics.json` is absent). Read `$METRICS`, `$REPORT`, `$SNAP`, and `$BUDGETS` for the artifact content; parse `$TRENDS` for month-over-month deltas, sparklines, and the top-movers banner.

Log which sources were present vs. absent (so a degraded artifact is explainable), e.g. `info|artifact|metrics=yes report=yes budgets=no trends=1-month`.

### 9b — Skip when there is nothing to present

If `$REPORT` does not exist (i.e. `--no-analyze` was passed, so no analysis was produced), **skip Step 9 entirely and silently** — there is nothing to present. Do not prompt for language, do not call the `Artifact` tool.

### 9c — Resolve language (ask once, then remember)

Resolve in this precedence order:

1. **`--lang` flag** in `$ARGUMENTS` → normalize (`en`/`english` → `en`; `pt-br`/`ptbr`/`pt` → `pt-br`, case-insensitive). An **invalid** value is ignored (fall through to step 3, the prompt). A valid value is used **and persisted**:
   ```bash
   python3 ${CLAUDE_PLUGIN_ROOT}/scripts/organizze/config.py set organizze_artifact_lang <en|pt-br>
   ```
2. **Saved value** (no flag): `ARTIFACT_LANG=$(python3 ${CLAUDE_PLUGIN_ROOT}/scripts/organizze/config.py get organizze_artifact_lang 2>/dev/null)` (do **not** name it `LANG` — that is the reserved POSIX locale variable). If set, use it and print **one** override affordance line so the choice is never a dead-end:
   - pt-br: `🌐 Artifact em pt-BR — use \`--lang en\` para trocar.`
   - en: `🌐 Artifact in English — use \`--lang pt-br\` to switch.`
3. **Unset and no flag** (first run): ask **once** via `AskUserQuestion` — question "Language for the interactive artifact?", 2 options: **pt-BR (recommended)** / **English**. Persist the answer with `config.py set organizze_artifact_lang <choice>`.

Financial figures stay in **R$** in both languages. Everything else (labels + `aria-label`s) is localized. Number/date formatting follows the language: **pt-BR** `R$ 1.234,56` / `dd/mm` / Portuguese month names; **en** `R$ 1,234.56` / `mmm dd`.

### 9d — Build and render the artifact

1. Load the `artifact-design` **and** `dataviz` skills first (calibration + chart-form heuristics), then author the HTML per the **Artifact content spec** below.
2. Write the HTML to `~/finance/organizze/reports/<same TS as $REPORT>.artifact.html` (for archival; the `Artifact` tool renders from the file).
3. Call the `Artifact` tool: `favicon` 💰, a **stable** title (`Análise financeira` / `Financial analysis` + the month), a one-sentence `description`.
4. Print the artifact URL as part of the final output block (see below).

### 9e — Failure is never fatal

If **anything** in 9d fails (skill load, HTML write, `Artifact` tool error), degrade to the Step 8 chat output with **one** WARN line — never fail the whole `/finance:organizze` run because the artifact could not render:
- pt-br: `⚠️ Não consegui gerar o artifact (<motivo>). A análise acima continua válida.`
- en: `⚠️ Could not generate the artifact (<reason>). The analysis above still stands.`

---

### Artifact content spec (bake into the build)

**Self-contained (hard CSP):** the `Artifact` tool blocks every external host — inline **all** CSS/JS; charts are **inline SVG** (no CDN chart library); system fonts only; no remote images. Wide tables/charts live inside an `overflow-x:auto` container so the page body never scrolls sideways.

**Theme-aware:** style both light and dark via `@media (prefers-color-scheme: dark)` **and** `:root[data-theme="dark"]` / `:root[data-theme="light"]` overrides (the viewer's toggle stamps `data-theme`; it must win in both directions).

**Information hierarchy (top → bottom, the 3-second scan):**
1. **Header:** `Análise financeira — <month>` / `Financial analysis — <month>`, snapshot date, current language, and a **Print / PDF** button.
2. **Top-movers banner** directly under the header — one line, the biggest up/down category vs. last month ("what changed"). Degrades to a warm "first month recorded" note when there is no prior month.
3. **KPI tile row:** Saldo líquido / Liquid balance · Entradas / Income · Saídas / Expense · Burn/month · Runway (days). Big `tabular-nums` figures, each with a signed month-over-month delta arrow.
4. **Sectioned/tabbed body:** Categorias/Categories · Metas/Goals · Fluxo de caixa/Cashflow · Cortes/Cuts · Quitação/Payoff · **Relatório completo/Full report** (collapsible `<details>`, last — progressive disclosure).

**Dataviz choices (per the dataviz skill's form heuristic):**
- **Category breakdown = ranked horizontal bars** (primary), sorted desc by amount, with a sort toggle (amount / MoM delta / name). Ranked bars beat a donut for magnitude and line up with each row's trend badge + sparkline. A donut is optional/secondary for share-of-total only.
- **Trend badge:** ▲/▼ glyph + signed % vs. last month. Color is semantic **and** redundant with the glyph/sign (never color-only): rising spend = attention color, falling spend = good; invert for income. A category present this month but absent last month shows a **"novo"/"new"** badge, never `↑∞%`.
- **Sparkline:** ~80×20 inline SVG over up to 6 months, last point marked; a single non-zero month renders flat (no divide-by-zero); `<2` months degrades to `—`.
- **Cashflow:** line/area over the forecast horizon with a "hoje"/"today" marker and a visible zero baseline.
- **Runway:** number + a slim horizontal gauge bar (not a dial).

**Accessibility:** text contrast ≥ 4.5:1, chart marks ≥ 3:1, colorblind-safe (glyph/label carry meaning, not hue alone). Tabs and sort headers are real `<button>`s; the full report is `<details>`/`aria-expanded`; visible focus outlines; touch targets ≥ 44px; `tabular-nums` for figure alignment.

**Empty / degraded states (warm, never "No items found"):**
- `<2` months of history → "Primeiro mês registrado — tendências aparecem no próximo" / "First month recorded — trends appear next month" instead of empty badges/sparklines.
- `metrics.json` missing → KPI tiles render from `$SNAP .meta.totais` where possible, otherwise show `—` with a quiet "dados detalhados indisponíveis" / "detailed data unavailable" note; the grid stays intact.
- No budget suggestions → hide the budget panel (no empty table). No cuts/goals → warm per-panel empty state.
- Negative balance / negative burn → format with the sign, never `NaN`.
- Long category names → truncate with a `title=` tooltip, no layout break.

**Report markers:** parse `[CUT]` / `[QUESTION]` / `[MEDICAL_EXPENSE]` from `$REPORT` into their panels; never leak the raw marker text into the UI.

**Print / PDF (`@media print`):** the button calls `window.print()`; expand all collapsibles (full report visible), hide interactive controls (tabs become stacked sections), force light theme, `page-break-inside:avoid` on cards/tables, and print a header/footer with the snapshot date + "gerado em"/"generated on".

**Anti-slop:** no generic 3-column card grid, no decorative hero. Lead with numbers + story; cards earn their place (KPI tiles yes, not every paragraph). Minimal shadows.

**PII:** build from the sanitized values already used upstream. **Never** embed raw account IDs, CPF/CNPJ, or the API token in the HTML — the artifact is shareable.

### Final output block

At the very end, alongside the existing footer, print (localized labels; paths verbatim):

```
🎴 Artifact interativo: <url>
📄 Snapshot: <SNAP>
📊 Report: <REPORT>
```

If the artifact was degraded, add **one** line naming which sections were limited and why, e.g.:
- `⚠️ metrics.json ausente — artifact gerado só com os totais do snapshot; rode com --refresh para recalcular.` / `⚠️ metrics.json missing — artifact built from snapshot totals only; run with --refresh to recompute.`

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

- **`financial-analyst`** — personalized personal financial analysis (consumes Organizze snapshots, respects user memories, generates a prioritized action plan). Ships with this plugin (`agents/financial-analyst.md`).
