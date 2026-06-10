---
description: (herow) Heavy end-to-end orchestrator — bootstrap a NEW project through the whole corrected playbook (strategy → indexation gate → draft → GEO schema → audit) with cost + human gates between every stage. Most expensive command; prefer the individual /seo:* commands unless you are starting from scratch.
allowed-tools: Read, Write, Edit, Bash, WebFetch, WebSearch, Grep, Glob, Agent, AskUserQuestion
argument-hint: "[gsc-export-path | --since N | --site URL]"
---

# /seo:launch — full-playbook bootstrap orchestrator

> **Requires:** a GSC export (Performance CSV / Bulk Export) **or** the `toprank` plugin's GSC integration. With no data, this command prints the 3-step export guide and stops.
> **Human gate:** never auto-publishes. Stops at a gate between every major stage and ends by presenting all stage artifacts for your approval.
> **No vanity metrics:** ranks opportunity by CTR / clicks-at-risk / indexability, never impressions alone.

The heavy global orchestrator for **bootstrapping a brand-new project** through the corrected Agensi playbook in one sequenced run: find clusters, check the site is even indexable before pouring on content, draft the top approved cluster with information gain, emit GEO schema, and produce a weekly audit baseline — with a cost gate and a human gate between stages.

> [!WARNING]
> **This is the heaviest, most token-expensive command in the suite.** It runs three agents back-to-back over your full GSC export and produces multiple artifacts in one pass. For day-to-day work, **run the individual commands instead** — the content-sprint stage to write one cluster, the indexation-check / weekly-audit stages to diagnose, the GEO stage for schema. Reach for `/seo:launch` **only** when bootstrapping a new project end-to-end and you accept the cost. It opens by asking you to confirm.

**This command does NOT invoke any other slash-command.** It is a single orchestrator that drives the **three agents inline, in sequence**, via the `Agent` tool. References below to "the content-sprint stage", "the indexation-check stage", "the GEO stage", and "the weekly-audit stage" are **descriptive labels for the conceptual `/seo:*` steps only** — the actual work is done by calling `seo-strategist`, `content-engineer`, and `technical-seo-auditor` directly here. A slash-command must never call another slash-command.

## GSC data contract (shared across the suite)

`$ARGUMENTS` accepts one of:
- `gsc-export-path` — path to a **GSC Performance export** (CSV/XLSX: `Queries`/`Pages`/`Dates` with `Clicks, Impressions, CTR, Position`) or a **Bulk Data Export** (`searchdata_url_impression` / `searchdata_site_impression` rows). This is the canonical contract; the full column spec lives in `${CLAUDE_PLUGIN_ROOT}/reference/gsc-data-contract.md`.
- `--since N` — analyze the last N days (used with toprank's GSC integration, if present).
- `--site URL` — the property to analyze.

If no data source resolves, do **not** fabricate data. Detect toprank's GSC integration first; if absent, print the **3-step export guide**: (1) Search Console → Performance → Export, or set up Bulk Data Export to BigQuery; (2) include Queries + Pages + Dates with Clicks/Impressions/CTR/Position; (3) save the file and re-run with its path. Then stop.

## Flow

0. **Cost confirmation — HUMAN GATE.** Open by stating this is the heaviest command and ask via `AskUserQuestion` to confirm running the full pipeline vs. running a single stage instead. If they decline, point them at the individual command for the stage they actually want and stop.

1. **Cost-guard gate.** Read/confirm the model-tiering policy before doing heavy work: **bulk parsing/summarization of the GSC export runs on the cheap tier; only the decision/judgment calls run on Opus.** State the tiering you'll use up front. Don't route every step through the most expensive path.

2. **Resolve data.** Detect `toprank` (look for its `seo-analysis` / `content-planner` skills). If present, prefer delegating the GSC pull to it. Else read the export at `gsc-export-path`. If neither resolves → print the 3-step guide and stop. Error clearly on a missing/empty/malformed file — never silently pass.

3. **Strategize** (the content-sprint stage). Delegate to the **`seo-strategist`** agent via the `Agent` tool (fall back to `general-purpose` if the agent file isn't installed) to find striking-distance question clusters: position 5–20 or weak CTR, filtered to question-intent and winnable difficulty (proxy KD ≤ 29, SV > 500, clear intent), deduped for cannibalization, with a content-gap read. Output: a ranked cluster list.

4. **Indexation gate** (the indexation-check stage) **— HUMAN GATE.** Delegate to the **`technical-seo-auditor`** agent (fallback `general-purpose`) to break down coverage: indexed vs `Discovered – currently not indexed` vs `Crawled – currently not indexed` vs excluded. **If a large share of pages are not indexed, STOP and surface the fix list first — do not pour more content onto an unindexable site.** Present the coverage status and, via `AskUserQuestion`, ask whether to fix indexability now or proceed to drafting anyway. Past ~100 pages, "not indexed" is expected — frame it as a quality/internal-link/crawl-budget problem, not a panic.

5. **Pick the cluster — HUMAN GATE.** Present the ranked clusters from stage 3 and ask via `AskUserQuestion` which one to draft (top recommendation first). Do not proceed without a choice.

6. **Draft.** Delegate to the **`content-engineer`** agent (fallback `general-purpose`) to produce the approved cluster: a quick-answer block at the top, the body, a concise FAQ, valid `FAQPage` + `Article` JSON-LD, 3–8 internal links with anchors, and a ≤60c title / ≤155c meta. Enforce the **information-gain gate**: content-engineer returns **PASS** (proprietary element named) or **BLOCKED** (missing input). A BLOCKED draft is returned with `[INSERT: …]` placeholders, never finalized.

7. **GEO schema** (the GEO stage). Still via **`content-engineer`**, emit the typed JSON-LD (`FAQPage` / `Article` / `BreadcrumbList` / `Organization` as fits the page) plus AI-citable quick-answers, formatted for citation by ChatGPT/Perplexity/Gemini/Claude.

8. **Audit** (the weekly-audit stage). Delegate to the **`technical-seo-auditor`** agent again to produce the weekly "what's broken" baseline: prioritized ~10 fixes (duplicate/conflicting schema, render/hydration bugs, redirect chains, titles >60c, missing canonical, slow CWV, orphan pages), plus CTR diagnostics ranked by clicks-at-risk. This is the recurring baseline the founder runs from week 2 on.

9. **Final HUMAN GATE.** Present the full ordered set of stage artifacts (cluster pick, draft + schema, indexation status, audit baseline) written to the working tree or a chosen `out/` dir. Ask via `AskUserQuestion`: approve / revise / discard. **Never publish** — publishing is manual or via `toprank setup-cms`.

## Output artifact

The ordered set of stage artifacts, all for review and nothing published: the strategist's ranked clusters + the picked cluster, a `draft.md` (quick-answer + body + FAQ), a `schema.json` (typed JSON-LD + quick-answers), the indexation-coverage status, and the weekly audit baseline (broken list + CTR diagnostics), each with its gate verdict.

## Guardrails

- **Heaviest / most expensive:** warn up front and confirm via `AskUserQuestion` before running. Recommend the individual commands for everything except a fresh bootstrap.
- **Cost-guard tiering:** bulk parsing on the cheap tier; only decisions on Opus. Honor it across every stage.
- **Indexation gate between stages:** if the site can't be indexed, fix that before producing more content — don't pour content onto an unindexable site.
- **No slash-command-calls-slash-command:** this orchestrator drives the three agents inline via the `Agent` tool; it never invokes another `/seo:*` command. The stage labels are descriptive only.
- **toprank optional:** detect-and-delegate per skill; degrade to native tools (WebFetch/WebSearch/Write); never hard-fail on a missing plugin.
- **No auto-publish & human gates throughout:** every stage boundary and the end is a human gate. Nothing ships without approval.
- **No vanity metrics:** lead with CTR, indexation coverage, and clicks-at-risk — never impressions alone.
