---
description: (herow) Pulls data from Organizze via REST API and generates a consolidated financial analysis (balance, projection, recommendations).
allowed-tools: Bash, Read, Write, AskUserQuestion, Agent, mcp__playwright__browser_navigate, mcp__playwright__browser_close, mcp__playwright__browser_snapshot
argument-hint: "[<free text> | --history-days N | --future-days N | --no-analyze]"
---

# /finance:organizze — Organizze → consolidated analysis

> **GLOBAL RULE — questions to the user:** every question requiring a user response must be asked via the `AskUserQuestion` tool, with 2-4 structured options (the free-text "Other" field is automatic). **Never** ask questions inline in text. Applies to all steps below and to every on-demand resource.

> **Recommended subagent (when installed):** Step 6 delegates analysis to the `financial-analyst` subagent via the `Agent` tool. The agent ships with this plugin (herow-finance); if it is unavailable the step automatically falls back to `general-purpose` — the command continues to work.

When the user invokes `/finance:organizze`, follow these steps **exactly**. Skip none. Do not pre-inspect (do not run `git status`, do not list directories, do not check versions — go straight to the scripts; they are self-contained and handle legacy migration automatically).

Optional arguments (parse from `$ARGUMENTS`):
- `--history-days N` (default 180)
- `--future-days N` (default 90)
- `--no-analyze` → only pull and save the snapshot, do not call the subagent

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

**First run only:** after this pull, follow §Step 2.5 and §Step 2.7 of `organizze-onboarding.md` when their conditions hold (see Step 2 above).

## Step 3.5 — Web scraping (real values via raw Playwright per subagent)

Enrich the snapshot with real scraped values. **Read `${CLAUDE_PLUGIN_ROOT}/resources/organizze-scrape.md` and follow it** (Steps 3.5a–3.5d). If scraping fails at any point, it degrades silently to API-only (snapshot remains; a WARN line is added at the start of the Step 8 report) and you continue at Step 4.

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

## Steps 5.5 / 5.6 — Market research & per-account forecast

**Read `${CLAUDE_PLUGIN_ROOT}/resources/organizze-research.md` and follow it.** Step 5.5 fires `search-specialist` in parallel (with a 14-day cache) and renders the prompt with `--research-dir`; Step 5.6 appends the `balance_on.py` per-account forecast block to `$PROMPT_FILE`. Then continue to Step 6.

## Step 6 — Delegate to the `financial-analyst` subagent

Use the `Agent` tool:
- `subagent_type`: `financial-analyst` if it exists at `~/.claude/agents/financial-analyst.md`. If it does not exist, **warn the user** ("subagent not installed — use `general-purpose` this time? To install, run `ln -sf <claude-config-root>/agents/financial-analyst/financial-analyst.md ~/.claude/agents/`") and proceed with `general-purpose`.
- `description`: `Monthly Organizze financial analysis`
- `prompt`: the contents of `$PROMPT_FILE` (rendered in step 5.5 with pre-collected research).

Save the subagent's response to `$REPORT`.

## Steps 6.5 / 6.6 — Post-analysis capture

**Read `${CLAUDE_PLUGIN_ROOT}/resources/organizze-capture.md` and follow §Step 6.5 then §Step 6.6:**
- **§Step 6.5** (optional) — offer to register new memory/restriction and a financial goal.
- **§Step 6.6** — parse `$REPORT` for `[QUESTION]` lines and bring up to 3 to the user, saving answers to memory. If there are none, continue to Step 7.

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
