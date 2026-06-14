---
description: (herow) CTR-first SERP tuning — find high-impression/low-CTR queries, rewrite titles + meta to win the click, gated on human approval.
allowed-tools: Read, Bash, WebFetch, WebSearch, Grep, Glob, Agent, AskUserQuestion
argument-hint: "[gsc-export-path | --since N | --site URL]"
effort: medium
---

# /seo:ctr-tune — CTR-first SERP tuning

> **Requires:** a GSC export (Performance CSV / Bulk Export) **or** the `toprank` plugin's GSC integration. With no data, this command prints the 3-step export guide and stops.
> **Human gate:** never auto-publishes. Ends by presenting title/meta variants for your approval.
> **No vanity metrics:** ranks opportunity by CTR / clicks-at-risk, never impressions alone.

The skeptic correction: a 0.84% CTR is unsustainable. **CTR beats vanity impressions** — if the clicks don't rise, Google decays the impressions. This is the command that operationalizes "CTR > impressions": it finds queries where you already rank but nobody clicks, then rewrites the title + meta to earn the click.

## GSC data contract (shared across the suite)

`$ARGUMENTS` accepts one of:
- `gsc-export-path` — path to a **GSC Performance export** (CSV/XLSX: `Queries`/`Pages`/`Dates` with `Clicks, Impressions, CTR, Position`) or a **Bulk Data Export** (`searchdata_url_impression` / `searchdata_site_impression` rows). This is the canonical contract; the full column spec lives in `${CLAUDE_PLUGIN_ROOT}/reference/gsc-data-contract.md`.
- `--since N` — analyze the last N days (used with toprank's GSC integration, if present).
- `--site URL` — the property to analyze.

If no data source resolves, do **not** fabricate data. Detect toprank's GSC integration first; if absent, print the **3-step export guide**: (1) Search Console → Performance → Export, or set up Bulk Data Export to BigQuery; (2) include Queries + Pages + Dates with Clicks/Impressions/CTR/Position; (3) save the file and re-run with its path. Then stop.

## Flow

1. **Resolve data.** Detect `toprank` (look for its `seo-analysis` / `meta-tags-optimizer` skills). If present, prefer delegating the GSC pull to it. Else read the export at `gsc-export-path`. If neither resolves → print the 3-step guide and stop. Error clearly on a missing/empty/malformed file — never silently pass.
2. **Diagnose CTR.** Delegate to the **`technical-seo-auditor`** agent via the `Agent` tool (fall back to `general-purpose` if the agent file isn't installed — same precedent as the rest of the suite) to find queries whose **actual CTR is well below the SERP-position average**, ranked by **clicks-at-risk = impressions × (expected-CTR − actual-CTR)**. Flag titles truncated >60c, duplicate/vague titles, and missing meta.
3. **Draft variants.** Delegate to the **`content-engineer`** agent (fallback `general-purpose`) to write new **≤60c titles** and **≤155c metas** for the top offenders — specificity, a number/year, a concrete reason to click, no keyword stuffing. If `toprank`'s `meta-tags-optimizer` is installed, delegate to it and apply the gate to its output.
4. **HUMAN GATE.** Present the title/meta variants with the SERP rationale and clicks-at-risk per query. Ask via `AskUserQuestion` which variants to adopt (top clicks-at-risk first). Do not proceed without a choice. **Never apply automatically** — the human ships the change to the CMS/site.

## Output artifact

A ranked table of high-impression/low-CTR queries with **clicks-at-risk**, the current title/meta, the **proposed ≤60c title / ≤155c meta** variants, and the SERP rationale for each. Nothing is published — every row is a proposal for your approval.

## Guardrails

- **CTR + clicks-at-risk lead:** rank and present by CTR and clicks-at-risk, never impressions alone. Impressions without clicks decay.
- **Hard limits:** titles ≤60c, metas ≤155c. No keyword stuffing — earn the click with specificity and a reason, not repetition.
- **toprank optional:** detect-and-delegate to `meta-tags-optimizer`; degrade to native tools (WebFetch/WebSearch); never hard-fail on a missing plugin.
- **No auto-apply:** every path ends at the human gate. Adopting a variant is the human's call (manual or via `toprank setup-cms`).
