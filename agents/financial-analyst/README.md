# financial-analyst

Subagent for personal financial analysis. Consumes a pre-built data snapshot (saldos, transações, atrasadas, parcelamentos, orçamentos, memória do usuário) and outputs an opinionated, prioritized action plan — never fetches data on its own.

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

A general-purpose agent given raw financial data wanders: invents averages, ignores user constraints, suggests cuts the user already said no to. This subagent enforces:

- **Memory as law** — if the user said "don't touch the mortgage", the agent never proposes it again.
- **Overdue first** — unpaid past transactions surface before any optimization.
- **Parcela semantics** — "acabando" (≤3 left → cash relief incoming, don't replace) vs "longe do fim" (≥12 total + half remaining → real future drag).
- **Numbers are sourced** — no invented metrics; everything traces to the snapshot.
- **Crisis protocol** — recurring negative balance / parcela >30% renda triggers a different output shape.

## Prerequisites

- Claude Code with subagents support.
- Caller supplies the full prompt (data + memory + task). The agent doesn't pull data itself.

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
| `tools` | `Read, Bash, Grep, Glob` (no `Write`/`Edit` — analysis only) |
| `model` | `opus` |
| `description` | Triggers on requests for consolidated balance, projections, budget variance, debt strategy comparison, scenario simulation, parcelamento analysis, prioritized cuts. |

## Output contract

Every response follows this exact order:

1. **TL;DR** — 3 lines (state · nearest risk · biggest opportunity).
2. **Números-chave** — markdown table (balance, projections, % committed, parcelas, overdue, top category, next invoice).
3. **Atrasadas — ação imediata** — ≤3 bullets `pay/collect by <date> · <amount>`.
4. **Parcelamentos — visão acionável** — ≤5 bullets, highlight "acabando" and "longe do fim".
5. **3 recomendações priorizadas** — `[IMPACT · EFFORT] title / Economia / Evidência / Ação`.
6. **Próximos passos verificáveis** — ≤3 bullets, each with a measurable criterion.
7. Disclaimer: `Isto não é aconselhamento financeiro licenciado.`

## Inviolable rules

1. Never invent numbers — every metric comes from supplied data or is tagged `[estimado: <fonte>]`.
2. Commit to methodology before calculating.
3. Local only — no exfiltration; no external calls except authorized public quotes.
4. Strip PII when generating exports.
5. Disclaimer at the end of every response.
6. Crisis protocol first if applicable.
7. **User memory is law** — never propose anything that contradicts it; recency = weight.
8. Overdue requires immediate action — surface at top.
9. Distinguish parcelas "acabando" (≤3 left) from "longe do fim" (≥12 total, ≥half remaining).

## Pairs naturally with

- [`/finance:organizze`](../../commands/finance/README.md#financeorganizze) — fetches Organizze data, builds the snapshot, renders the prompt, delegates here.

## When NOT to use this agent

- Generic Q&A about finance (use a regular Claude session).
- Data extraction tasks (use the `/finance:organizze` command's `pull.py` first).
- Anything requiring write access to external systems (it has no `Write`/`Edit`).
