---
description: (herow) Brainstorm and extract every requirement, then generate a Product Requirements Document.
argument-hint: "[feature name or one-line idea]"
allowed-tools: AskUserQuestion, Read, Write, Glob, Grep, Agent
---

# Create PRD

> **Recommended subagent (when installed):** for the high-level **Technical considerations** section — architecture notes, dependencies, build/buy and stack trade-offs — offer to delegate to `backend-architect` via the `Agent` tool (`subagent_type: backend-architect`). The command works without it; if the agent file is not present at `~/.claude/agents/backend-architect.md`, fill the section inline and keep it high-level.

Turn a rough idea into a Product Requirements Document by **brainstorming the inputs first, writing second**. Treat `$ARGUMENTS` as the feature name or one-line idea seed.

**Core principle:** A PRD answers *what* and *why*, never *how*. Capture user problems, scope, and success measures — leave implementation to engineering. **Never include time estimates or timelines.** Never invent evidence, metrics, or personas — if it's unknown after asking, it's an open question, not a fact.

## Step 1 — Seed

- Read `$ARGUMENTS` as the working title / one-line idea. If empty, ask the user for it with `AskUserQuestion` (one short round) before continuing.
- Derive a kebab-case `<slug>` from the title (e.g. `checkout abandonment` → `checkout-abandonment`) for the optional file name later.

## Step 2 — Choose depth

Ask with `AskUserQuestion`:

- **Lean one-pager** — fast, single-page brief. Fewer questions, lighter output.
- **Comprehensive** — full PRD with personas, jobs-to-be-done, user stories, and acceptance criteria.

The choice selects which discovery rounds run (Step 3) and which output template you synthesize (Step 4).

## Step 3 — Discovery (brainstorming)

Run the rounds below as `AskUserQuestion` calls. Rules for every round:

- Offer concrete, opinionated options drawn from the idea — the user can always pick **Other** and type their own.
- **Skip any question already answered** by the seed or an earlier answer. Never re-ask what you know.
- Batch related questions into a single `AskUserQuestion` call (up to 4 questions) where it reads naturally.
- State assumptions out loud as you go. When the user is unsure, record it as an open question rather than guessing.
- **Never fabricate** metrics, evidence, persona sizes, or quotes. Unknowns flow into the **Open questions / Assumptions** section verbatim.

Rounds (run all for *comprehensive*; run the ★ subset for *lean*):

1. ★ **Problem & evidence** — What hurts, and how do we know? Evidence type: user quotes · usage data · support tickets · sales/loss reasons · hypothesis (unvalidated).
2. ★ **Who's affected** — Primary persona(s) and rough size/segment; the cost of *not* solving it (impact of inaction).
3. **Root cause (5 Whys)** — Starting from the stated problem, ask "why is that?" up to five times to separate symptom from root cause. Keep it short; stop once it bottoms out.
4. ★ **Solution shape & jobs-to-be-done** — The job the user is trying to get done, and the key user flow(s) expressed as `Step → Step → Outcome`.
5. ★ **Scope** — What's explicitly **in scope** for this version vs **out of scope / non-goals**. Force at least one explicit exclusion.
6. ★ **Success metrics** — Capture the split:
   - **Primary** — one metric with target + timeframe.
   - **Secondary** — supporting metrics.
   - **Guardrail** — a metric that must **not** regress.
7. ★ **Risks** — Top risks, each with likelihood (low/med/high) and a mitigation.
8. **UX requirements** *(comprehensive)* — Key states, empty/error/loading behavior, accessibility or responsive expectations, and the acceptance-criteria style the user wants.
9. **Technical considerations** *(comprehensive)* — Offer to delegate to `backend-architect` for high-level architecture notes, dependencies, and trade-offs. If declined or unavailable, capture them inline and keep them high-level (no implementation detail).

Stop the discovery loop once every required field for the chosen depth is filled or explicitly deferred to open questions.

## Step 4 — Synthesize the PRD (inline)

Render the document directly in chat (Markdown). Use the section set for the chosen depth. Omit empty sections only if the user explicitly deferred them — otherwise list what's missing under open questions.

**Lean one-pager:**

1. **Title & status** (`draft | review | approved`)
2. **Problem** — statement · evidence · who's affected · cost of inaction
3. **Solution** — summary (1–2 sentences) · key user flow(s)
4. **Out of scope** — explicit exclusions
5. **Success metrics** — primary · secondary · guardrail
6. **Risks & mitigations** — risk · likelihood · mitigation
7. **Open questions / Assumptions**

**Comprehensive:**

1. **Title / author / date / status**
2. **Problem** — statement · evidence · who's affected · impact of not solving
3. **Personas** — who they are, context, goals
4. **Jobs-to-be-done** — the job(s) the feature serves
5. **Goals & non-goals**
6. **Requirements** — functional requirements, prioritized (e.g. Must / Should / Could); each traceable to a stated user need
7. **In scope / Out of scope**
8. **User stories** — each as `As a [persona], when [trigger], I want [capability], so that [outcome]`, followed by:
   - **Acceptance criteria** in `GIVEN … WHEN … THEN …` form, plus edge cases.
   - **Definition of Done** checklist (AC pass, analytics fire, error states handled, responsive verified, accessibility standard met, performance threshold).
9. **Success metrics** — primary · secondary · guardrail
10. **UX requirements** — key states, accessibility, responsive notes
11. **Technical considerations** — high-level only (from `backend-architect` if used)
12. **Risks & mitigations**
13. **Dependencies** — teams, services, prerequisites
14. **Open questions / Assumptions**

**Constraints for both templates:**

- No time estimates, no timelines, no milestone dates.
- Product sections describe *what & why* — never *how*.
- Every requirement traces back to a user need surfaced in discovery.

## Step 5 — Offer to save

Ask with `AskUserQuestion` whether to write the PRD to a file or keep it chat-only.

- Default to **chat-only**. Only `Write` if the user opts in.
- If saving, default the path to `docs/prd/<slug>.md` (confirm or let them override). Create the directory if needed.
- Never write a file unprompted.

## Recommended subagents

This subagent from this repo (`agents/`) sharpens the output when installed. The command works without it — install selectively via `install.sh`.

- **[`backend-architect`](../../agents/backend-architect.md)** — for the **Technical considerations** section: surfaces dependencies, integration points, and build/buy or stack trade-offs at PRD altitude (no implementation). Optional; if absent, the command fills the section inline.
