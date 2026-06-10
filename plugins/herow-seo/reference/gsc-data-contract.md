# seo

SEO/GEO growth slash commands. Nested under `commands/seo/`, so each is invoked as **`/seo:<name>`** (Claude Code's path-as-namespace convention, same as `/finance:*`).

This suite encodes the validated Agensi/Reddit SEO+GEO playbook — **with the skeptic corrections built in as first-class commands**: optimize CTR + conversion (not vanity impressions), gate on indexation, weight GEO (AI citation) heavily, treat backlinks as human work, enforce an information-gain quality bar, and control token cost. Every command **runs standalone** (native tools) and **delegates to the `toprank` plugin when installed**. Every command ends at a **human gate** — nothing is ever auto-published.

> **The tool is not the lever — persistence is.** The founder in the source post shipped 100+ articles over months before results. These commands give you a small team's execution speed; you still have to run `/seo:content-sprint` (and friends) repeatedly, for months. Don't judge results at 10 articles.

## Commands

| Command | Pillar / correction | One-liner |
|---|---|---|
| [`/seo:content-sprint`](./content-sprint.md) | Pillar 1 (the 80%) | GSC keyword gap → cluster → draft + FAQ schema + internal links → human gate. |
| [`/seo:weekly-audit`](./weekly-audit.md) | Pillar 3 | Weekly habit: export GSC → "what's broken" → prioritized ~10 fixes. |
| [`/seo:indexation-check`](./indexation-check.md) | Correction (indexation) | Diagnose coverage; resolve "Discovered/Crawled – not indexed". |
| [`/seo:geo-optimize`](./geo-optimize.md) | Pillar 2 (GEO) | Typed JSON-LD + quick-answers + AI-referral tracking for AI citation. |
| [`/seo:catalog-pages`](./catalog-pages.md) | Pillar 4 | Programmatic long-tail pages; uniqueness + cannibalization checks. |
| [`/seo:ctr-tune`](./ctr-tune.md) | Correction (CTR) | High-impression/low-CTR queries → better titles/meta, ranked by clicks-at-risk. |
| [`/seo:conversion-track`](./conversion-track.md) | Correction (conversion) | Join traffic ↔ conversion; flag high-traffic/low-conversion pages. |
| [`/seo:backlink-outreach`](./backlink-outreach.md) | Correction (human work) | Finds targets, drafts outreach, tracks status. **Cannot build links** — that's human work. |
| [`/seo:cost-guard`](./cost-guard.md) | Correction (token cost) | Model-tiering policy the suite honors (cheap tier for parsing, Opus for decisions). |
| [`/seo:report`](./report.md) | Metrics loop | Consolidated dashboard: CTR, indexation, AI-citation, conversion. |
| [`/seo:launch`](./launch.md) | Orchestrator (heavy) | Runs the full playbook end-to-end for a new project; sequences the agents inline with cost + indexation gates. **Most expensive command.** |

## The three agents (the "team")

The commands delegate to three specialist agents in [`../../agents/`](../../agents/) (and fall back to `general-purpose` when an agent file isn't installed — same precedent as `finance/organizze`):

- [`seo-strategist`](../../agents/seo-strategist.md) (Opus, **no Write**) — analyzes GSC/data, finds patterns, makes the call. Decisions only.
- [`content-engineer`](../../agents/content-engineer.md) (Sonnet) — drafts content + FAQ schema + internal links, with a hard **information-gain gate** (refuses to finalize commodity reworded-web content).
- [`technical-seo-auditor`](../../agents/technical-seo-auditor.md) (Sonnet) — parses GSC exports → prioritized fix list + indexation coverage + CTR diagnostics.

## GSC data contract (canonical)

Every data command accepts the same `$ARGUMENTS`: **`[gsc-export-path | --since N | --site URL]`**.

- **`gsc-export-path`** — a path to a Google Search Console export, in one of two shapes:
  - **Performance export** (Search Console → Performance → Export, as CSV/XLSX). Sheets/files: `Queries` (Top queries, Clicks, Impressions, CTR, Position), `Pages`, `Countries`, `Devices`, `Dates`.
  - **Bulk Data Export** (Search Console → Settings → Bulk Data Export → BigQuery; CSV dump). Tables: `searchdata_url_impression`, `searchdata_site_impression`, `ExportLog` — per-URL/query rows with `impressions`, `clicks`, `sum_position`.
  - **Page Indexing / Coverage export** (for `/seo:indexation-check`) — read the `Reason` / `Coverage state` columns.
- **`--since N`** — analyze the last N days; used with toprank's GSC integration when present.
- **`--site URL`** — the property to analyze.

If no data source resolves, a command does **not** fabricate data. It detects toprank's GSC integration first; if absent, it prints a 3-step export guide and stops. Missing/empty/malformed files error clearly — never a silent pass. Large exports (10k+ rows) are summarized, never dumped.

`/seo:cost-guard` is policy-only — it doesn't read GSC itself; it sets the model tier the data commands use to parse the export.

## Layout

```
commands/seo/
├── README.md            # this file
├── content-sprint.md    # /seo:content-sprint
├── weekly-audit.md      # /seo:weekly-audit
├── indexation-check.md  # /seo:indexation-check
├── geo-optimize.md      # /seo:geo-optimize
├── catalog-pages.md     # /seo:catalog-pages
├── ctr-tune.md          # /seo:ctr-tune
├── conversion-track.md  # /seo:conversion-track
├── backlink-outreach.md # /seo:backlink-outreach
├── cost-guard.md        # /seo:cost-guard
├── report.md            # /seo:report
└── launch.md            # /seo:launch (heavy orchestrator)
```

## Install

Install via the herow plugin marketplace — no manual wiring:

```bash
/plugin marketplace add judsonjuniorr/claude-config
/plugin install herow-seo@herow
```

## Prerequisites

- A GSC export (Performance or Bulk) **or** the `toprank` plugin's GSC integration. No hard dependency on either — commands degrade to native tools.
- Optional: the `toprank` plugin (`seo-analysis`, `content-writer`, `content-planner`, `schema-markup-generator`, `meta-tags-optimizer`, `geo-optimizer`, `seo-page`, `broken-link-checker`) — detected and delegated to when present.
