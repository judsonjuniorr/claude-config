---
description: (herow) Join GSC search traffic to conversion data, flag high-traffic / low-conversion pages, and gate every action on human approval.
allowed-tools: Read, Bash, WebFetch, WebSearch, Grep, Glob, Agent, AskUserQuestion
argument-hint: "[gsc-export-path | --since N | --site URL]"
---

# /seo:conversion-track — does the traffic actually convert?

> **Requires:** a GSC export (Performance CSV / Bulk Export) **or** the `toprank` plugin's GSC integration, **plus** a conversion data source (an analytics/CSV export mapping pages → signups/sales). With no data, this command prints the export guide and stops.
> **Human gate:** never auto-publishes. Ends by presenting flagged pages + recommended actions for your approval.
> **No vanity metrics:** the KPI is **conversion**, never impressions or raw clicks.

The skeptic correction (szymon-slowik-seo): impressions and clicks are not the goal — conversion is. A page can win clicks and still convert nobody. This command closes the **"traffic ≠ value"** gap by joining search traffic to conversion per page and surfacing where the clicks are wasted.

## GSC data contract (shared across the suite)

`$ARGUMENTS` accepts one of:
- `gsc-export-path` — path to a **GSC Performance export** (CSV/XLSX: `Queries`/`Pages`/`Dates` with `Clicks, Impressions, CTR, Position`) or a **Bulk Data Export** (`searchdata_url_impression` / `searchdata_site_impression` rows). This is the canonical contract; the full column spec lives in [`commands/seo/README.md`](./README.md).
- `--since N` — analyze the last N days (used with toprank's GSC integration, if present).
- `--site URL` — the property to analyze.

If no data source resolves, do **not** fabricate data. Detect toprank's GSC integration first; if absent, print the **3-step export guide**: (1) Search Console → Performance → Export, or set up Bulk Data Export to BigQuery; (2) include Queries + Pages + Dates with Clicks/Impressions/CTR/Position; (3) save the file and re-run with its path. Then stop.

## Flow

1. **Resolve both data sources.** Detect `toprank` (look for its `seo-analysis` / `content-planner` skills); if present, prefer delegating the GSC pull to it, else read the export at `gsc-export-path`. If neither resolves → print the 3-step guide and stop. **Then resolve the conversion source** — an analytics export or CSV mapping pages/paths to conversions/signups/sales. If conversion data is absent, say so plainly and stop: do **not** invent conversion numbers. Error clearly on a missing/empty/malformed file — never silently pass.
2. **Join traffic ↔ conversion.** Delegate to the **`seo-strategist`** agent via the `Agent` tool (fall back to `general-purpose` if the agent file isn't installed — same precedent as finance/organizze) to join GSC pages to the conversion source by page/path (normalize trailing slashes, query strings, and protocol), compute conversion rate per page (conversions ÷ clicks), and rank pages by traffic.
3. **Flag the gaps.** Surface **high-traffic / low-conversion** pages (clicks coming in, nothing converting — the wasted-traffic pages) and **high-conversion winners** worth doubling down on. Every flag must trace to a real row in both exports.
4. **HUMAN GATE.** Present the ranked per-page table + flags + recommended actions (improve the CTA, match search intent to the page, or stop chasing a query that never converts) and ask via `AskUserQuestion` what to action — top recommendation first. **Never change anything automatically.**

## Output artifact

A per-page table — **traffic (clicks), conversion rate, flag (high-traffic/low-CVR vs winner)** — with a recommended action per flagged row, plus one line on data confidence. All for review; nothing is published or changed.

## Guardrails

- **Conversion is the KPI:** rank and headline on conversion, never on impressions or raw clicks.
- **No fake conversion data:** if no conversion source is provided, say so clearly and stop — don't estimate it into existence.
- **No vanity metrics:** a high-traffic page with zero conversions is a problem to flag, not a win.
- **toprank optional:** detect-and-delegate per skill; degrade to native tools (Read/Bash/WebFetch); never hard-fail on a missing plugin.
- **Human gate:** every path ends at a human decision — improve, re-target, or abandon. The command never publishes or edits.
