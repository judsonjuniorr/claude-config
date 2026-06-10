---
description: (herow) Programmatic long-tail catalog pages — generate or validate unique per-item title/meta/schema with cannibalization + uniqueness checks, gated on human approval.
allowed-tools: Read, Write, Edit, Bash, WebFetch, WebSearch, Grep, Glob, Agent, AskUserQuestion
argument-hint: "[gsc-export-path | --since N | --site URL]"
---

# /seo:catalog-pages — programmatic long-tail catalog pages

> **Requires:** a catalog data source (CSV/JSON of items) + a page template. Optionally a GSC export (Performance CSV / Bulk Export) **or** the `toprank` plugin's GSC integration for the cannibalization/coverage read. With no GSC data, the uniqueness checks still run; the coverage read is skipped.
> **Human gate:** never auto-publishes. Ends by presenting the generated pages + the cannibalization/uniqueness report for your approval.
> **No vanity metrics:** ranks pages by uniqueness / indexability / clicks-at-risk, never raw page count.

Pillar 4 of the corrected Agensi playbook: **the catalog is the SEO engine.** 700+ unique indexable pages, each genuinely differentiated, is the long-tail moat — but only if every page earns its index slot. Thin duplicates do not add reach; they get flagged, suppressed, and drag the rest down. This command generates or validates the catalog and refuses to ship near-duplicates.

## GSC data contract (shared across the suite)

`$ARGUMENTS` accepts one of:
- `gsc-export-path` — path to a **GSC Performance export** (CSV/XLSX: `Queries`/`Pages`/`Dates` with `Clicks, Impressions, CTR, Position`) or a **Bulk Data Export** (`searchdata_url_impression` / `searchdata_site_impression` rows). This is the canonical contract; the full column spec lives in `${CLAUDE_PLUGIN_ROOT}/reference/gsc-data-contract.md`.
- `--since N` — analyze the last N days (used with toprank's GSC integration, if present).
- `--site URL` — the property to analyze.

If no data source resolves, do **not** fabricate data. Detect toprank's GSC integration first; if absent, print the **3-step export guide**: (1) Search Console → Performance → Export, or set up Bulk Data Export to BigQuery; (2) include Queries + Pages + Dates with Clicks/Impressions/CTR/Position; (3) save the file and re-run with its path. Then stop. (The catalog source + template are required; the GSC export is optional — without it, run uniqueness checks and skip the coverage/cannibalization-vs-live-queries read.)

## Flow

1. **Resolve sources.** Locate the **catalog data source** (a CSV/JSON of items) and the **page template** via args or by globbing the working tree; error clearly on a missing/empty/malformed source — never silently pass. Then resolve optional GSC data: detect `toprank` (look for its `seo-analysis` / `content-planner` skills) and prefer delegating the GSC pull to it; else read the export at `gsc-export-path`; else print the 3-step guide for the coverage read and continue with uniqueness-only.
2. **Generate per-item content.** Delegate to the **`content-engineer`** agent via the `Agent` tool (fall back to `general-purpose` if the agent file isn't installed — same precedent as finance/organizze) to produce, for every catalog item: a **unique title (≤60c)**, **unique meta (≤155c)**, and typed **JSON-LD** (`Product` / `Article` / `BreadcrumbList`) bound to the template. The **information-gain gate** applies per page: any item that would render thin/commodity (no differentiating substance beyond the templated fields) is flagged **BLOCKED** with the missing input, not silently shipped. If `toprank`'s `content-writer` / `schema-markup-generator` are installed, delegate to them and apply the gate to their output.
3. **Cannibalization + uniqueness check.** Delegate to the **`seo-strategist`** agent (fallback `general-purpose`) to detect: near-duplicate titles/meta, multiple pages competing for the same intent/query (cannibalization), and pages with no differentiating content (thin). When GSC data resolved, cross-read against live queries/coverage to flag pages already cannibalizing each other in the SERP. Output a ranked report of collisions and thin pages.
4. **HUMAN GATE.** Present the generated pages **and** the cannibalization/uniqueness report as artifacts (written to the working tree or a chosen `out/` dir). Ask via `AskUserQuestion`, per collision cluster, which to **keep / merge / drop** (top recommendation first), and what to do with BLOCKED/thin pages. **Never publish** — publishing is manual or via `toprank setup-cms`.

## Output artifact

A per-page set of **unique title + meta + typed JSON-LD** (one block/file per catalog item), plus a **cannibalization & uniqueness report** naming which pages collide (duplicate title/intent), which are thin/BLOCKED, and the merge/keep/drop recommendation for each — all for review. Nothing is published.

## Guardrails

- **Uniqueness is a gate, not a nice-to-have:** every page must be genuinely differentiated. Thin duplicates hurt indexation, they don't extend reach — BLOCKED pages stay BLOCKED.
- **Information gain applies per page:** a templated page with no proprietary substance is Core-Update-fragile; flag it, don't ship it.
- **toprank optional:** detect-and-delegate per skill; degrade to native tools (Read/Write/WebFetch/WebSearch); never hard-fail on a missing plugin.
- **No auto-publish:** every path ends at a human gate.
- **No vanity metrics:** 700 pages is not a result; 700 *indexed, unique, converting* pages is. Say so if the user equates page count with traffic.
