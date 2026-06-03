---
description: Weekly technical-SEO ritual — export GSC, hunt what's broken, get a prioritized ~10-fix list to action in one sitting. Gated on human approval.
allowed-tools: Read, Write, Bash, WebFetch, Grep, Glob, Agent, AskUserQuestion
argument-hint: "[gsc-export-path | --since N | --site URL]"
---

# /seo:weekly-audit — the weekly technical-SEO habit

> **Requires:** a GSC export (Performance CSV / Bulk Export) **or** the `toprank` plugin's GSC integration. With no data, this command prints the 3-step export guide and stops.
> **Human gate:** never auto-applies fixes. Ends by presenting the ranked fix list for your approval.
> **No vanity metrics:** ranks problems by CTR / indexation / clicks-at-risk, never impressions alone.

Pillar 3 of the corrected Agensi playbook: a once-a-week ritual, not a one-off. Export GSC → feed the auditor → "what's broken" → a prioritized ~10-fix list the founder can action in one sitting. The point is the **cadence** — run it every week and let problems surface before they compound.

## GSC data contract (shared across the suite)

`$ARGUMENTS` accepts one of:
- `gsc-export-path` — path to a **GSC Performance export** (CSV/XLSX: `Queries`/`Pages`/`Dates` with `Clicks, Impressions, CTR, Position`) or a **Bulk Data Export** (`searchdata_url_impression` / `searchdata_site_impression` rows). This is the canonical contract; the full column spec lives in [`commands/seo/README.md`](./README.md).
- `--since N` — analyze the last N days (used with toprank's GSC integration, if present).
- `--site URL` — the property to analyze.

If no data source resolves, do **not** fabricate data. Detect toprank's GSC integration first; if absent, print the **3-step export guide**: (1) Search Console → Performance → Export, or set up Bulk Data Export to BigQuery; (2) include Queries + Pages + Dates with Clicks/Impressions/CTR/Position; (3) save the file and re-run with its path. Then stop.

## Flow

1. **Resolve data.** Detect `toprank` (look for its `seo-analysis` / `broken-link-checker` skills). If present, prefer delegating the GSC pull / crawl to it. Else read the export at `gsc-export-path`. If neither resolves → print the 3-step guide and stop. Error clearly on a missing/empty/malformed file — never silently pass.
2. **Audit.** Delegate to the **`technical-seo-auditor`** agent via the `Agent` tool (fall back to `general-purpose` if the agent file isn't installed — same precedent as finance/organizze). Have it hunt the classic failures: duplicate/conflicting schema across many URLs, hydration/render bugs causing high bounce on article pages, http→https→www redirect chains, titles truncated >60 chars, missing canonical, slow Core Web Vitals, orphan pages. Use `WebFetch` to confirm a live symptom when a URL is given.
3. **Rank.** The auditor returns a prioritized **~10 fixes**, highest-impact first — each with: what / where (URL or pattern + count) / why it matters / the concrete fix. On a large export it **summarizes** (top-N, aggregates) rather than dumping rows.
4. **HUMAN GATE.** Present the fix list and ask via `AskUserQuestion` which fixes to action this week (top recommendation first). **Never auto-apply** — fixes are actioned manually by the founder or routed onward.

## Output artifact

A prioritized `audit-YYYYWW.md` fix list (top-10, highest-impact first) with counts and concrete fixes, plus a one-line data-confidence note. Nothing is applied.

## Guardrails

- **Weekly cadence:** this is a habit, not a one-off. The value is running it every week so problems surface early — say so if the user treats it as a single audit.
- **No vanity metrics:** lead with CTR / indexation / clicks-at-risk, never impressions alone.
- **toprank optional:** detect-and-delegate (`seo-analysis` / `broken-link-checker`); degrade to native tools (Read/Bash/WebFetch); never hard-fail on a missing plugin.
- **Ends at the human gate:** the command stops at "approve this fix list." It never edits files or publishes.
