---
name: prompt-optimizer
description: >-
  (herow) Analyze raw prompts, identify intent and gaps, match claude-config components
  (skills/commands/agents/hooks), and output a ready-to-paste optimized
  prompt. Advisory role only — never executes the task itself.
  TRIGGER when: user says "optimize prompt", "improve my prompt",
  "how to write a prompt for", "help me prompt", "rewrite this prompt",
  or explicitly asks to enhance prompt quality.
  DO NOT TRIGGER when: user wants the task executed directly, or says
  "just do it". DO NOT TRIGGER when user says "optimize performance" or
  "optimize this code" — those are refactoring/performance tasks, not
  prompt optimization.
origin: community
metadata:
  author: YannJY02
  version: "1.0.0"
model: sonnet
effort: medium
---

# Prompt Optimizer

Analyze a draft prompt, critique it, match it to available components, and output a
complete optimized prompt the user can paste and run.

> Detection tables, component-matching tables, the full output-format spec, and worked
> examples live in `reference.md` **in this skill's directory** — read it before
> producing output. It lists herow components; the installed plugin set varies, so
> verify a component exists in the current session before recommending it.

## When to Use

- "Optimize this prompt" / "improve my prompt" / "rewrite this prompt"
- "Help me write a better prompt for…" / "what's the best way to ask Claude Code to…"
- User pastes a draft prompt and asks for feedback or enhancement

### Do Not Use When

- User wants the task done directly (just execute it) or says "just do it"
- "Optimize this code/performance" — refactoring, not prompt optimization
- User is asking about tooling setup rather than prompt content

## How It Works

**Advisory only — do not execute the user's task.** Do NOT write code, create files,
run commands, or take any implementation action. Your ONLY output is an analysis plus
an optimized prompt. If the user asks for execution, tell them to make a normal task
request instead.

Run this pipeline sequentially, then present results in the Output Format below.

1. **Phase 0 — Project detection.** Read `CLAUDE.md` if present; detect the tech
   stack from project files (signal table in `reference.md`). No project files →
   flag "tech stack unknown".
2. **Phase 1 — Intent detection.** Classify into: New Feature, Bug Fix, Refactor,
   Research, Testing, Review, Documentation, Infrastructure, Design (signals in
   `reference.md`).
3. **Phase 2 — Scope assessment.** TRIVIAL (single file, <50 lines) → direct
   execution · LOW (single module) → one command/skill · MEDIUM (multi-component,
   same domain) → command chain + verify · HIGH (cross-domain, 5+ files) → plan
   first, phased execution · EPIC (multi-session/PR) → blueprint skill.
4. **Phase 3 — Component matching.** Map intent + scope + stack to concrete
   commands/skills/agents using the tables in `reference.md`, validated against what
   actually exists in the session.
5. **Phase 4 — Missing-context detection.** Check: tech stack, target scope,
   acceptance criteria, error handling, security, testing expectations, performance
   constraints, UI/UX (if frontend), database changes (if data layer), existing
   patterns, scope boundaries. Classify each gap as:
   - **Material** — the answer would change the substance of the generated prompt
     (e.g. which auth strategy, which DB, target framework, deployment target).
   - **Non-material** — Phase 0 auto-detected the answer, or a sensible default
     applies (state the default in the output; do **not** ask).
   If any **material** gaps exist, call `AskUserQuestion` **before** proceeding to
   Phase 5 or generating any output:
   - Each question must include 2–4 **concrete** options derived from context
     (e.g. auth → JWT / OAuth2 / Session cookie) so the user gets clickable
     choices plus the auto-added "Other" open field — never a blank open question.
   - Batch up to 4 questions in a single `AskUserQuestion` call, most material
     first. If you'd need more than 4, prioritize by impact (which answer changes
     the most about the generated prompt) — do not spam multiple calls; remaining
     gaps are reclassified as non-material with the best available default stated in Section 1.
   - The ordering is strict: **ask → receive answers → fold answers in → Phase 5
     → generate output.** Never emit any output — including Section 1 (Prompt
     Diagnosis) — before all material questions are answered.
   Distinguish two kinds of questions:
   - Questions **this skill needs** to write the prompt → `AskUserQuestion`
     (blocking, answered now).
   - Questions **the executor should resolve during the task** → embed inside the
     generated prompt (as the EPIC example does), not asked here.
6. **Phase 5 — Workflow & model recommendation.** Place the prompt in
   Research → Plan → Implement (TDD) → Review → Verify → Commit; recommend a model
   tier and, for HIGH/EPIC, a multi-prompt split (tables in `reference.md`).

## Output Format

Respond in the same language as the user's input, with these sections (full spec and
examples in `reference.md`):

1. **Prompt Diagnosis** — strengths, issues table (issue/impact/fix), assumptions & resolved clarifications
2. **Recommended Components** — type/component/purpose table incl. model
3. **Optimized Prompt — Full Version** — one self-contained fenced block: task +
   context, tech stack, command invocations at the right stages, acceptance criteria,
   verification steps, scope boundaries (what NOT to do)
4. **Optimized Prompt — Quick Version** — compact one-liner pattern for the intent
5. **Enhancement Rationale** — what was added and why
6. **Footer** — "Not what you need? Tell me what to adjust, or make a normal task
   request if you want execution instead."
