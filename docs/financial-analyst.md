# financial-analyst

Subagent for personal financial analysis. Consumes a pre-built data snapshot (balances, transactions, overdue items, installments, budgets, user memory) and outputs an opinionated, prioritized action plan — never fetches data on its own.

## Making it used system-wide

Symlink (recommended — picks up repo updates automatically):

```bash
mkdir -p ~/.claude/agents
ln -sf "$PWD/agents/financial-analyst/financial-analyst.md" \
       ~/.claude/agents/financial-analyst.md
```

Or copy:

```bash
mkdir -p ~/.claude/agents
cp agents/financial-analyst/financial-analyst.md ~/.claude/agents/
```

Verify:

```bash
ls -la ~/.claude/agents/financial-analyst.md
```

Without it installed, callers (like `/finance:organizze`) fall back to `general-purpose` — works, but loses the domain rules (respect user memory, prioritize overdue, distinguish parcelas "acabando" vs "longe do fim").

## Why it exists

A general-purpose agent given raw financial data wanders: invents averages, ignores user constraints, suggests cuts the user already said no to, and stays generic ("cut streaming") instead of personalized ("cancel Spotify Family R$ 27,90, switch to Individual R$ 21,90 — saves R$ 72/year"). This subagent enforces:

- **Profile-driven personalization** — every recommendation cites at least one field from the user profile (age, income, dependents, housing, city, risk tolerance). No generic advice.
- **Memory as law** — if the user said "don't touch the mortgage", the agent never proposes it again.
- **Overdue first** — unpaid past transactions surface before any optimization.
- **Merchant-level cuts** — uses the actual `description` from the snapshot, never invents merchant names. 3-5 specific cuts per analysis.
- **Market research arrives pre-collected** — the caller (`/finance:organizze`) dispatches `search-specialist` agents **in parallel** (one per target category) before invoking this agent; results are injected as a `# Market research (PRE-COLLECTED — DO NOT REDO WebSearch)` block. The analyst consumes the block instead of running WebSearch itself (~3x faster, saves the analyst's tokens). Falls back to its own WebSearch only when the block is missing or incomplete.
- **Installment semantics** — "almost done" (≤3 left → cash relief incoming, don't replace) vs "far from done" (≥12 total + half remaining → real future drag).
- **Payoff strategy by risk profile** — avalanche (highest interest first) for `agressivo`, snowball (smallest balance first) for `conservador`/`moderado`. Justified, never silent.
- **Numbers are sourced** — no invented metrics; everything traces to the snapshot or to a cited WebSearch URL.
- **Open questions loop** — emits `[QUESTION]` markers when critical context is missing; the calling command captures them and asks the user, feeding the answers into the next run.
- **Crisis protocol** — recurring negative balance / installment >30% of income triggers a different output shape.

## Prerequisites

- Claude Code with subagents support.
- Caller supplies the full prompt (data + profile + memory + plans + task). The agent doesn't pull data itself.
- **User profile** in `~/finance/profile.md` (managed via `/finance:profile`) — without it, recommendations stay generic and the agent will emit `[QUESTION]` markers asking for the missing fields.
- **WebSearch access** — required for the market-research section (otherwise that block will show `(sem alternativa encontrada)`).

## Structure

```
financial-analyst/
├── financial-analyst.md   # frontmatter + system prompt
└── README.md
```

## Frontmatter

| Field | Value |
|---|---|
| `name` | `financial-analyst` |
| `tools` | `Read, Bash, Grep, Glob, WebSearch, WebFetch` (no `Write`/`Edit` — analysis only; WebSearch is used only for the 3 target categories, capped cost) |
| `model` | `opus` |
| `description` | Triggers on requests for consolidated balance, projections, budget variance, debt strategy comparison, scenario simulation, parcelamento analysis, prioritized cuts, merchant-level cut suggestions, market research for alternatives, payoff strategy (avalanche/snowball). Calibrates by user profile. |

## Output contract

Every response follows this exact order (15 sections):

1. **TL;DR** — 3 lines (state · nearest risk · biggest opportunity), citing ≥1 profile field.
2. **Key numbers** — markdown table (balance, projections, % committed, installments, overdue, top category, next invoice).
3. **Overdue — immediate action** — ≤3 bullets `pay/collect by <date> · <amount>`.
4. **Category goals — status** — ≤5 bullets (risk + opportunity).
5. **User goals — feasibility this month** — 1 bullet per active goal.
6. **Transfer and savings plan** — ≤5 bullets `[CRITICAL]`/`[RENEGOTIATE]`/`[SAVINGS]`.
7. **Goals paused this cycle** — omit if empty.
8. **Installments — actionable view** — ≤5 bullets, highlight "almost done" and "long way to go".
9. **Suggested specific cuts** — 3-5 `[CUT] merchant · R$ X/month → alternative · savings · justification`.
10. **Prioritized payoff** — strategy (avalanche/snowball) chosen by `tolerancia_risco` + ordered list of eligible debts.
11. **Market alternatives** — 1 block per `TARGET-WEBSEARCH` category (URL + price + potential savings).
12. **3 prioritized recommendations** — `[IMPACT · EFFORT] title / Savings / Evidence / Action / Why for you (profile)`.
13. **Verifiable next steps** — ≤3 bullets, each with a measurable criterion.
14. **Open questions** — up to 3 lines `[QUESTION] <text>` (no leading hyphen/bullet) — captured by the calling command.
15. Disclaimer: `This is not licensed financial advice.`

## Inviolable rules

1. Never invent numbers — every metric comes from supplied data or is tagged `[estimated: <source>]`.
2. Commit to methodology before calculating.
3. Local only — no exfiltration; no external calls except `WebSearch` on the 3 target categories for market alternatives.
4. Strip PII when generating exports.
5. Disclaimer at the end of every response.
6. Crisis protocol first if applicable.
7. **User memory is law** — never propose anything that contradicts it; recency = weight.
8. Overdue requires immediate action — surface at top.
9. Distinguish installments "almost done" (≤3 left) from "far from done" (≥12 total, ≥half remaining).
10. Day-of source balance for transfer suggestions (validate via cashflow per account).
11. Proactive renegotiation when recurring debit consistently lands on a no-cash day.
12. **Profile personalization is mandatory** — every recommendation cites ≥1 field from the user profile.
13. **3-5 merchant-level cuts** — using the actual snapshot description, never inventing.
14. **Consume the pre-collected market research block** — `search-specialist` agents already searched in parallel; only use WebSearch as fallback when block is missing/incomplete.
15. **Payoff strategy chosen by risk tolerance** — avalanche for `agressivo`, snowball for `conservador`/`moderado`.
16. **Up to 3 `[QUESTION]` markers** at the end when critical context is missing; the calling command captures them.

## Pairs naturally with

- [`/finance:organizze`](../../commands/finance/README.md#financeorganizze) — fetches Organizze data, builds the snapshot, renders the prompt, delegates here.

## When NOT to use this agent

- Generic Q&A about finance (use a regular Claude session).
- Data extraction tasks (use the `/finance:organizze` command's `pull.py` first).
- Anything requiring write access to external systems (it has no `Write`/`Edit`).
