---
description: (herow) Brainstorm any topic — not just code — into a concrete result through adaptive questioning, then deliver it your way (create-prd, blueprint, quick, research, an inline brief, or a Claude artifact).
argument-hint: "[topic, idea, question, or decision to think through]"
allowed-tools: AskUserQuestion, Read, Grep, Glob, Skill, Artifact, Write, Agent
effort: medium
---

# Brainstorm

> **Think first, deliver second.** Don't produce the final result — or hand off to another skill — until the idea has converged *and* you've asked the user how they want it delivered. Applies to every topic, however simple.

Turn any input — an idea, a question, a decision, a plan, a creative brief — into a concrete result by thinking it through **first** and choosing how to deliver **second**. Treat `$ARGUMENTS` as the seed topic. This is **not** limited to software: a trip, a business call, a name, a talk outline, and a product feature are all in scope.

**Core principle:** Diverge to explore, converge to decide, then deliver exactly the result the user wants. Never jump to the deliverable before the idea *and* the desired outcome are clear. **YAGNI** — cut anything that doesn't serve the goal. **Never fabricate** facts, metrics, or quotes; unknowns become open questions.

## Step 1 — Seed & desired result

- Read `$ARGUMENTS` as the topic. If empty, ask for it with one short `AskUserQuestion` round before continuing.
- Derive a kebab-case `<slug>` from the topic (e.g. `lisbon weekend trip` → `lisbon-weekend-trip`) for later use.
- **Pin the desired result early.** Ask what the user wants to walk away with — a *decision* · a *plan* · a *written piece* · a *design/brief* · a *shortlist* · a *validated idea* · a *PRD* · a *spec*. This one answer steers every later question and pre-selects the Step 7 delivery route.
- Anti-pattern guard — *"this is too simple to need a brainstorm."* Every topic gets at least a 30-second scope check; "simple" asks are where unexamined assumptions cost the most. The brainstorm can be short, but don't skip it.

## Step 2 — Context (lightweight)

- If the topic touches this repo or local files/docs, skim them first (`Read` / `Grep` / `Glob`) so you build on what exists.
- For a personal, business, or creative topic with no local context, skip this step.
- For a large topic that needs real digging, optionally delegate context-gathering to a subagent via the `Agent` tool and fold its findings back in.

## Step 3 — Scope triage

- Before detailed questions, check whether the ask is really **several independent topics** (e.g. "launch a brand" = name + positioning + pricing + channels). If so, say it plainly, decompose into pieces, and brainstorm the **first** piece now — note the rest so each can get its own run.

## Step 4 — Discovery (adaptive dialogue)

Ask with `AskUserQuestion`, **adaptive cadence:**

- **Batch** tightly-related, concrete questions into a single card (≤4) when they read naturally together.
- **Drop to one focused question** for open-ended or deep threads where a batch would flatten the thinking.

Rules for every round:

- Offer concrete, opinionated options drawn from the topic — the user can always pick **Other** and type their own.
- **Skip anything already known** from the seed or an earlier answer. Never re-ask.
- State assumptions out loud. When the user is unsure, record it as an open question rather than guessing.
- **Never fabricate** — no invented numbers, evidence, or quotes.

Draw questions from the dimensions that fit the desired result (use the relevant ones, not all):

- **Purpose / why** — what's the real goal behind this?
- **Audience / stakeholders** — who is it for, who decides, who's affected?
- **Constraints** — budget, time, tools, non-negotiables, hard limits.
- **Success criteria** — how will we know it worked?
- **Options / approaches** — the candidate directions.
- **Risks** — what could go wrong, and how likely.
- **Scope** — what's explicitly **in** vs **out** for this pass.

## Step 5 — Explore approaches

- Propose **2–3 approaches** with trade-offs, not one.
- **Lead with your recommendation** and the reasoning, then the alternatives.

## Step 6 — Converge (sectioned)

- Present the refined result in **sections scaled to complexity** — a couple of sentences when straightforward, more when nuanced.
- Confirm each section before moving on (incremental validation, not one big reveal). Go back and clarify if something doesn't hold up.
- Apply **YAGNI**, then self-review before delivery: **placeholder scan** (no "TBD"/gaps) · **internal consistency** · **scope focus** · **ambiguity** (could a line be read two ways?). Fix inline.

## Step 7 — Deliver (direct the desired result)

First, synthesize a tight **brief** (internally): *problem · desired result · key decisions · scope in/out · open questions*. Then ask with `AskUserQuestion`: **"How do you want to take this forward?"**

- Surface only the routes that **fit** what was brainstormed, **recommended route first** (matched to the Step 1 desired result), and always include at least one *deliver-here* option.
- `AskUserQuestion` shows **max 4 options**. Usually the two deliver-here routes plus 1–2 fitting handoffs cover it in one question. If **more than four** routes genuinely fit, use a two-step: first ask *"deliver here or hand off to a build/research skill?"*, then present the specific skills. **Other** reaches any route not surfaced.
- Keep it general: for a trip or a life decision, surface only **On screen / Claude artifact / research** — the dev routes appear only when the topic is actually software.

The six routes:

| Route | Surface when | How to execute |
|---|---|---|
| **create-prd** | a software/product feature that needs a PRD | `Skill` tool → `herow-extras:create-prd`, seeding it with the one-line idea |
| **blueprint** | a dev implementation that needs a full plan | `Skill` tool → `herow-dev:blueprint`, seeding it with the brief |
| **quick** | a small, well-scoped code change to build **and** ship | `Skill` tool → `herow-dev:quick`, seeding it with the brief |
| **research** | open questions that need multi-source, cited research | `Skill` tool → `herow-dev:research`, seeding it with the refined question(s) |
| **On screen** | any topic — the default | render the consolidated brief inline in chat (Markdown). No file |
| **Claude artifact** | a shareable brief, comparison table, decision matrix, or roadmap | load the `artifact-design` skill (via the `Skill` tool) first, then render with the `Artifact` tool |

**Handoff mechanics:** the handed-off skill shares this live conversation, so it already sees the whole brainstorm — pass the concise seed so it opens on the right foot and doesn't re-ask. **Confirm before handing off.** Never hand off or write a file unprompted.

## Quality rules

1. **Understand before delivering.** No result — and no handoff — until the idea and the desired outcome are clear.
2. **Adaptive questioning.** `AskUserQuestion` with concrete options + **Other**; never guess inline.
3. **Skip what you know.** Never re-ask an answered question.
4. **Never fabricate.** Unknowns are open questions, not facts.
5. **YAGNI.** Cut non-essentials; always weigh 2–3 approaches before settling.
6. **Deliver the chosen result.** Match the route to the desired outcome; pass a brief on handoff; confirm first.

## Examples

```
/herow-extras:brainstorm plan a 3-day Lisbon trip for 2 on a €1500 budget
/herow-extras:brainstorm should we switch our pricing to usage-based?
/herow-extras:brainstorm a name and positioning for my new coffee brand
/herow-extras:brainstorm outline a conference talk on burnout in eng teams
/herow-extras:brainstorm a feature that lets users schedule weekly reports   # → likely create-prd / blueprint
```
