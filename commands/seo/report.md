---
description: Consolidated SEO/GEO dashboard — pulls the suite's real KPIs (CTR, indexation coverage, AI-referral, conversion) into one "where are we" snapshot, gated on human review.
allowed-tools: Read, Write, Bash, WebFetch, WebSearch, Grep, Glob, Agent, AskUserQuestion
argument-hint: "[gsc-export-path | --since N | --site URL]"
---

# /seo:report — the consolidated dashboard

> **Requires:** a GSC export (Performance CSV / Bulk Export) **or** the `toprank` plugin's GSC integration, plus optional AI-referral and conversion exports. With no data, this command prints the 3-step export guide and stops.
> **Human gate:** never auto-publishes. Ends by presenting the dashboard for your review — it is yours to send, not the command's.
> **No vanity metrics:** impressions appear only as context beside CTR / indexation / conversion, never as the headline number.

Closes the metrics loop for the corrected Agensi playbook: the single artifact the founder actually shows. Every other `/seo:*` command moves one number — this one tells you whether the loop is working. It reports; it does not chase a chart up and to the right.

## GSC data contract (shared across the suite)

`$ARGUMENTS` accepts one of:
- `gsc-export-path` — path to a **GSC Performance export** (CSV/XLSX: `Queries`/`Pages`/`Dates` with `Clicks, Impressions, CTR, Position`) or a **Bulk Data Export** (`searchdata_url_impression` / `searchdata_site_impression` rows). This is the canonical contract; the full column spec lives in [`commands/seo/README.md`](./README.md).
- `--since N` — analyze the last N days (used with toprank's GSC integration, if present).
- `--site URL` — the property to analyze.

If no data source resolves, do **not** fabricate data. Detect toprank's GSC integration first; if absent, print the **3-step export guide**: (1) Search Console → Performance → Export, or set up Bulk Data Export to BigQuery; (2) include Queries + Pages + Dates with Clicks/Impressions/CTR/Position; (3) save the file and re-run with its path. Then stop.

## Flow

1. **Resolve data sources.** Detect `toprank` (look for its `seo-analysis` skill); if present, prefer delegating the GSC pull to it. Else read the export at `gsc-export-path`, plus any provided AI-referral log and conversion export. If **nothing** resolves → print the 3-step guide and stop. Otherwise **degrade gracefully**: print which export feeds which section, build the sections you have data for, and mark the rest **"no data"**. Error clearly on a missing/malformed file you were handed — never silently pass.
2. **Traffic + indexation.** Delegate to the **`technical-seo-auditor`** agent via the `Agent` tool (fall back to `general-purpose` if the agent file isn't installed) for the CTR numbers (clicks-at-risk, truncated/low-CTR queries) and the indexation-coverage breakdown (indexed vs `Discovered`/`Crawled – not indexed`).
3. **AI-citation + conversion + next moves.** Delegate to the **`seo-strategist`** agent (fallback `general-purpose`) for the AI-referral read (sessions by engine from the referral log) and the conversion read, plus the **top-3 "what to do next"** ranked by leverage.
4. **Assemble.** Merge both agents' output into a single consolidated markdown dashboard (sections below), each metric tracing to a parsed row or marked "no data" — never invented.
5. **HUMAN GATE.** Present the dashboard as an artifact and stop. Ask via `AskUserQuestion` only whether to save/revise the file. **Never publish, send, post, or share it anywhere** — distribution is entirely the founder's call.

## Output artifact

A single `seo-report-YYYY-MM-DD.md` dashboard, written to the working tree (or a chosen `out/` dir), with sections:
- **Traffic** — CTR and clicks; impressions shown only as adjacent context.
- **Indexation coverage** — indexed vs not-indexed counts and the unblock.
- **AI-citation** — referral sessions by engine (ChatGPT/Perplexity/Gemini/Claude/Kagi), or "no data".
- **Conversion** — conversions / conversion rate from the conversion export, or "no data".
- **Next actions** — the top-3 highest-leverage moves, each with the metric it should move.

## Guardrails

- **Impressions are context, never the headline.** They appear only beside CTR / indexation / conversion. If a section can only show impressions, that's a gap to call out, not a win to report.
- **No data ≠ zero.** Any section without a feeding export is marked **"no data"** explicitly — never backfilled, estimated, or fabricated.
- **toprank optional:** detect-and-delegate to its `seo-analysis`; degrade to native parsing (Read/Bash/WebFetch); never hard-fail on a missing plugin.
- **Human gate:** the command presents the dashboard; it does not publish or send it. Distribution is manual.
