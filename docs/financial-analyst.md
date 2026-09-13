# financial-analyst

Subagent for personal financial analysis. Consumes a pre-built data snapshot (balances, transactions, overdue items, installments, budgets, user memory) and outputs an opinionated, prioritized action plan — never fetches data on its own.

## Where it lives

The agent ships with the `herow-finance` plugin at
`plugins/herow-finance/agents/financial-analyst.md` and is picked up automatically when the
plugin is installed — there is no symlink step. If it is unavailable,
`/herow-finance:organizze` falls back to `general-purpose`, which still works but loses the
domain rules below.

## Why it exists

A general-purpose agent given raw financial data wanders: invents averages, ignores user constraints, suggests cuts the user already said no to, and stays generic ("cut streaming") instead of personalized ("cancel Spotify Family R$ 27,90, switch to Individual R$ 21,90 — saves R$ 72/year"). This subagent enforces:

- **Profile-driven personalization** — every recommendation cites at least one field from the user profile (age, income, dependents, housing, city, risk tolerance). No generic advice.
- **Memory as law** — if the user said "don't touch the mortgage", the agent never proposes it again.
- **Overdue first** — unpaid past transactions surface before any optimization.
- **Merchant-level cuts** — uses the actual `description` from the snapshot, never invents merchant names.
- **Market research arrives pre-collected** — the caller dispatches `search-specialist` agents **in parallel** (one per target category) before invoking this agent; results are injected as a `# Market research (PRE-COLLECTED)` block. The analyst has no web-search tool of its own, so a category the block does not cover is reported as `(data unavailable)` rather than guessed at.
- **Installment semantics** — "almost done" (≤3 left → cash relief incoming, don't replace) vs "far from done" (≥12 total + half remaining → real future drag).
- **Payoff strategy by risk profile** — avalanche (highest interest first) for `agressivo`, snowball (smallest balance first) for `conservador`/`moderado`. Justified, never silent.
- **Numbers are sourced** — no invented metrics; everything traces to the snapshot or to a URL cited in the pre-collected research block.
- **Open questions loop** — emits `[QUESTION]` markers when critical context is missing; the calling command captures them and asks the user, feeding the answers into the next run.
- **Crisis protocol** — recurring negative balance / installment >30% of income triggers a different output shape.

## Prerequisites

- Claude Code with subagents support.
- Caller supplies the full prompt (data + profile + memory + plans + task). The agent doesn't pull data itself.
- **User profile** in `~/finance/profile.md` (managed via `/herow-finance:profile`) — without it, recommendations stay generic and the agent will emit `[QUESTION]` markers asking for the missing fields.
- **Pre-collected market research** — supplied by the caller. Without it the "Market alternatives" section reports `(data unavailable)`; the agent never searches on its own.

## Contract

The frontmatter, the report's section order, and the non-negotiable rules live in
`plugins/herow-finance/agents/financial-analyst.md` — read them there rather than mirroring
them here, so the two cannot drift. The snapshot-specific guidance and the exact output
templates the caller parses are rendered by
`plugins/herow-finance/scripts/organizze/analyze.py`; the report markers it captures
(`[QUESTION]`, `[CUT]`) are documented at
`plugins/herow-finance/commands/organizze.md`.

## Pairs naturally with

- [`/herow-finance:organizze`](../plugins/herow-finance/commands/organizze.md) — fetches Organizze data, builds the snapshot, renders the prompt, delegates here.

## When NOT to use this agent

- Generic Q&A about finance (use a regular Claude session).
- Data extraction tasks (use the `/herow-finance:organizze` command's `pull.py` first).
- Anything requiring write access to external systems (it has no `Write`/`Edit`).
