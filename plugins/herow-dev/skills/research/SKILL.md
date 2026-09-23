---
name: research
description: (herow) Multi-source research with cited reports via Exa/web MCPs. Use when the user wants researched, sourced answers — deep dives, comparisons, current-state questions. Quick single-fact lookups don't need this skill.
---

# Research

> **Drift-prone skill.** Exa/web MCP tool names, quotas, and result shapes change.
> Verify the configured MCP tools and current API docs before promising coverage
> or quoting live source counts.

Produce thorough, cited research reports from multiple web sources, and route lighter
asks to the cheapest path that answers them. This is the single research entry point.

## When to Activate

- User asks to research a topic in depth, compare options, or evaluate a decision
- Competitive analysis, technology evaluation, market sizing, or due diligence
- Any question requiring synthesis from multiple current sources
- User says "research", "deep dive", "compare", or "what's the current state of"

Do **not** spin up a full pass when the answer is already in local code/docs, or when a
single quick lookup suffices — see Step 0.

## MCP Requirements

This repo's configured Exa server exposes:
- **`web_search_exa`** — web/news discovery
- **`web_fetch_exa`** — fetch a URL's full content (use on the best result URLs when snippets aren't enough, including code/docs pages)

Any configured search/fetch MCP works as a substitute — **verify the exposed tool names
first** (the `exa-search` skill documents the current Exa surface). Configure in
`~/.claude.json` or `~/.codex/config.toml`.

## Workflow

### Step 0: Classify the ask (take the lightest path first)

Before searching, pick the lane:

- **Quick factual answer** → one `web_search_exa` (or the `exa-search` skill); stop there.
- **Comparison / decision memo** → the full multi-source pass below.
- **Already in local repo/docs** → answer from there; don't run a heavy pass.
- **Recurring question** → answer now, then say so and recommend a monitor/workflow layer
  instead of repeating the same manual search forever.

Also normalize anything the user already supplied into: already-evidenced facts · needs
verification · open questions. Don't restart from zero if the user already built part of
the model.

### Step 1: Understand the Goal

Ask 1-2 quick clarifying questions:
- "What's your goal — learning, making a decision, or writing something?"
- "Any specific angle or depth you want?"

If the user says "just research it" — skip ahead with reasonable defaults.

### Steps 2–4: Plan, search, deep-read

Split the topic into the sub-questions a decision actually hinges on. Search each with varied
phrasings, mixing general and news-focused queries and favoring academic, official, and reputable
news sources over blogs and forums:

```
web_search_exa(query: "<sub-question keywords>", numResults: 8)
```

Fetch full text for the sources your conclusions rest on — don't rely on snippets alone:

```
web_fetch_exa(url: "<url>")   # for any URL, including GitHub/SO/docs pages for code & API detail
```

Stop when every sub-question has corroborated evidence or a stated gap.

### Step 5: Synthesize and Write Report

Structure the report:

```markdown
# [Topic]: Research Report
*Generated: [date] | Sources: [N] | Confidence: [High/Medium/Low]*

## Executive Summary
[3-5 sentence overview of key findings]

## 1. [First Major Theme]
[Findings with inline citations]
- Key point ([Source Name](url))
- Supporting data ([Source Name](url))

## 2. [Second Major Theme]
...

## Key Takeaways
- [Actionable insight 1]
- [Actionable insight 2]

## Sources
1. [Title](url) — [one-line summary]
2. ...

## Methodology
Searched [N] queries across web and news. Analyzed [M] sources.
Sub-questions investigated: [list]
```

Label every important claim by evidence type — **sourced fact** vs **user-supplied
context** vs **inference** vs **recommendation** — and give concrete dates on
freshness-sensitive answers.

### Step 6: Deliver

- **Short topics**: Post the full report in chat
- **Long reports**: Post the executive summary + key takeaways, save full report to a file

## Parallel Research with Subagents

For broad topics, use the Agent tool to split the sub-questions across parallel agents, with
cross-cutting themes assigned to one of them. Each agent searches, reads sources, and returns findings. The main session synthesizes
into the final report.

## Quality Rules

1. **Every claim needs a source.** No unsourced assertions.
2. **Cross-reference.** If only one source says it, flag it as unverified.
3. **Recency matters.** Prefer sources from the last 12 months; date freshness-sensitive claims.
4. **Label evidence type.** Separate sourced fact, user-supplied context, inference, and recommendation.
5. **Acknowledge gaps.** If you couldn't find good info on a sub-question, say so.
6. **No hallucination.** If you don't know, say "insufficient data found."

## Examples

```
"Research the current state of nuclear fusion energy"
"Deep dive into Rust vs Go for backend services in 2026"
"Research the best strategies for bootstrapping a SaaS business"
"What's happening with the US housing market right now?"
"Investigate the competitive landscape for AI code editors"
```
