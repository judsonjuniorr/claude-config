---
description: Indexation gate — diagnose GSC coverage and resolve the "Discovered/Crawled – currently not indexed" wall, with an inferred cause and concrete unblock per page, gated on human approval.
allowed-tools: Read, Bash, WebFetch, Grep, Glob, Agent, AskUserQuestion
argument-hint: "[gsc-export-path | --since N | --site URL]"
---

# /seo:indexation-check — the indexation gate the skeptics demanded

> **Requires:** a GSC export (Performance / Bulk Export, **or** a Page Indexing / Coverage CSV) **or** the `toprank` plugin's GSC integration. With no data, this command prints the 3-step export guide and stops.
> **Human gate:** never auto-applies. Ends by presenting the not-indexed list + cause + unblock actions for your approval.
> **No vanity metrics:** ranks by coverage state and clicks-at-risk, never impressions alone.

Indexation is the wall every volume play hits around 100 pages. "Discovered – currently not indexed" / "Crawled – currently not indexed" is not a bug to panic over — it's a quality / internal-link / crawl-budget problem to solve. This command surfaces coverage health and the per-page unblock before you write one more article.

## GSC data contract (shared across the suite)

`$ARGUMENTS` accepts one of:
- `gsc-export-path` — path to a **GSC Performance export** (CSV/XLSX: `Queries`/`Pages`/`Dates` with `Clicks, Impressions, CTR, Position`) or a **Bulk Data Export** (`searchdata_url_impression` / `searchdata_site_impression` rows). This is the canonical contract; the full column spec lives in [`commands/seo/README.md`](./README.md).
- `--since N` — analyze the last N days (used with toprank's GSC integration, if present).
- `--site URL` — the property to analyze.

If no data source resolves, do **not** fabricate data. Detect toprank's GSC integration first; if absent, print the **3-step export guide**: (1) Search Console → Performance → Export, or set up Bulk Data Export to BigQuery; (2) include Queries + Pages + Dates with Clicks/Impressions/CTR/Position; (3) save the file and re-run with its path. Then stop.

## Indexing-export note (this command also reads coverage)

Beyond the Performance / Bulk Export, this command also accepts a **GSC Page Indexing export** / Coverage CSV. When given one, read the `Reason` / `Coverage state` columns to classify each URL. To export it: Search Console → **Indexing → Pages** → click a status (e.g. *Discovered – currently not indexed*) → **Export**.

## Flow

1. **Resolve data.** Detect `toprank` (look for its `seo-analysis` skill). If present, prefer delegating the GSC/coverage pull to it. Else read the export at `gsc-export-path` (Page Indexing / Coverage CSV preferred for this command, Performance / Bulk Export as fallback). If neither resolves → print the 3-step guide (including the Page Indexing export steps above) and stop. Error clearly on a missing/empty/malformed file — never silently pass.
2. **Coverage breakdown.** Delegate to the **`technical-seo-auditor`** agent via the `Agent` tool (fall back to `general-purpose` if the agent file isn't installed — same precedent as finance/organizze) to break down indexed vs `Discovered – currently not indexed` vs `Crawled – currently not indexed` vs excluded, with counts by state and the full not-indexed page list. Summarize large exports — never dump raw rows.
3. **Infer cause + unblock.** Delegate to the **`seo-strategist`** agent (fallback `general-purpose`) to infer the likely cause per not-indexed page — thin/commodity content, orphan = no internal links, crawl budget, or duplicate — and the concrete unblock for each (add internal links, improve info-gain, submit in sitemap, consolidate duplicates).
4. **HUMAN GATE.** Present the ranked not-indexed list — each row: URL, coverage state, inferred cause, concrete unblock — plus counts by state. Ask via `AskUserQuestion` what to action (e.g. add internal links to orphans / improve info-gain on thin pages / consolidate duplicates / submit in sitemap). **Never auto-apply** any fix — the founder chooses, you hand the brief to the right agent or human.

## Output artifact

A coverage report: counts by state (indexed / `Discovered – currently not indexed` / `Crawled – currently not indexed` / excluded) plus a ranked not-indexed list, each row with its inferred cause and a concrete unblock — all for review. Nothing is applied.

## Guardrails

- **Indexation realism:** past ~100 pages, "not indexed" is *expected* — a quality / internal-link / crawl-budget problem to solve, not a panic. Frame it that way.
- **No vanity metrics:** lead with coverage state and clicks-at-risk, never impressions alone.
- **toprank optional:** detect-and-delegate to its `seo-analysis`; degrade to native parsing (Read/Bash/WebFetch); never hard-fail on a missing plugin.
- **No auto-apply:** every path ends at a human gate. You diagnose and recommend; the founder approves and executes.
