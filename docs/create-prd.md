# /create-prd

Brainstorm the inputs first, write second: an interactive command that extracts every requirement a Product Requirements Document needs through structured questioning, then synthesizes the PRD — lean one-pager or comprehensive.

See [`create-prd.md`](./create-prd.md) for the full agent-facing procedure.

## What it does

1. Takes a feature name / one-line idea from `$ARGUMENTS` (asks if empty) and derives a slug.
2. Asks for **depth** — lean one-pager vs comprehensive — which selects both the questions and the output template.
3. Runs structured `AskUserQuestion` discovery rounds: problem & evidence, who's affected, 5-Whys root cause, jobs-to-be-done & key flows, in/out-of-scope, success metrics (primary/secondary/guardrail), risks, and — for comprehensive — UX requirements and high-level technical considerations. Skips anything already answered; never fabricates evidence or metrics.
4. Synthesizes the PRD inline in chat using the depth-appropriate sections. No time estimates; *what & why*, never *how*; every requirement traces to a user need.
5. Offers to save the result. Chat-only by default; writes `docs/prd/<slug>.md` (or a path you choose) only if you opt in.

## Frontmatter

- **description**: Brainstorm and extract every requirement, then generate a Product Requirements Document.
- **argument-hint**: `[feature name or one-line idea]`
- **allowed-tools**: AskUserQuestion, Read, Write, Glob, Grep, Agent

## Usage

```
/create-prd checkout abandonment
/create-prd "self-serve seat management for admins"
/create-prd
```

## Language

English.

## When to use

- A stakeholder hands you a vague idea and you need a structured brief before engineering scopes it.
- You want a repeatable PRD with explicit problem, scope boundaries, and success metrics — not a free-form doc.
- You need acceptance criteria (`GIVEN/WHEN/THEN`) and a primary/secondary/guardrail metric split for a new feature.

## Prerequisites

- None required. The PRD is rendered in chat; a file is written only on request.
- Optional: the [`backend-architect`](../../agents/backend-architect.md) agent installed — the command offers to delegate the high-level technical-considerations section to it (fills inline if absent).
