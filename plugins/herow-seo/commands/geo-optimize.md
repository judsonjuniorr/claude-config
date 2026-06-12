---
description: (herow) Make pages AI-citable — emit typed JSON-LD + lead-with-the-answer quick-answers per page, track AI-referral sessions, gated on human approval.
allowed-tools: Read, Write, Edit, Bash, WebFetch, WebSearch, Grep, Glob, Agent, AskUserQuestion
argument-hint: "[gsc-export-path | --since N | --site URL]"
model: sonnet
effort: medium
---

# /seo:geo-optimize — generative-engine optimization (AI citability)

> **Requires:** target page URLs/paths (and optionally a GSC export — Performance CSV / Bulk Export — plus an AI-referral log). With no pages, this command prints what to provide and stops.
> **Human gate:** never injects into the live site. Ends by presenting the JSON-LD + quick-answers for your approval.
> **No vanity metrics:** prioritizes pages by AI-citation potential and conversion, never impressions alone.

Pillar 2 of the corrected Agensi playbook: make content **citable by AI search engines** (ChatGPT, Perplexity, Gemini, Claude, Kagi). The skeptics' correction is load-bearing here — dev-tutorial Google SEO is decaying because devs ask Claude/Codex, not Google. **Weight GEO heavily: this is growth, not hygiene.** Schema coverage + quick-answer formatting is what gets you cited.

## GSC data contract (shared across the suite)

`$ARGUMENTS` accepts one of:
- `gsc-export-path` — path to a **GSC Performance export** (CSV/XLSX: `Queries`/`Pages`/`Dates` with `Clicks, Impressions, CTR, Position`) or a **Bulk Data Export** (`searchdata_url_impression` / `searchdata_site_impression` rows). This is the canonical contract; the full column spec lives in `${CLAUDE_PLUGIN_ROOT}/reference/gsc-data-contract.md`.
- `--since N` — analyze the last N days (used with toprank's GSC integration, if present).
- `--site URL` — the property to analyze.

If no data source resolves, do **not** fabricate data. Detect toprank's GSC integration first; if absent, print the **3-step export guide**: (1) Search Console → Performance → Export, or set up Bulk Data Export to BigQuery; (2) include Queries + Pages + Dates with Clicks/Impressions/CTR/Position; (3) save the file and re-run with its path. Then stop.

## Flow

1. **Resolve targets + optional data.** Take the page URL/path or set of pages from `$ARGUMENTS`. Detect `toprank` (look for its `geo-optimizer` / `schema-markup-generator` skills). If present, prefer delegating the GEO audit and schema generation to it. Else read the live pages (WebFetch) and any `gsc-export-path` / AI-referral log directly. If no pages resolve → print what to provide (a URL/path, optional GSC export, optional AI-referral log) and stop. Error clearly on a missing/empty/malformed file — never silently pass.
2. **Generate schema + quick-answers.** Delegate to the **`content-engineer`** agent via the `Agent` tool (fall back to `general-purpose` if the agent file isn't installed — same precedent as finance/organizze) to emit, **per page**: valid JSON-LD for the right type(s) — `Article`, `Product`, `FAQPage`, `BreadcrumbList`, `Organization` — and a **quick-answer block** (2–4 sentences, lead-with-the-answer, snippet-eligible and AI-citable). Keep schema valid and minimal. If `toprank`'s `schema-markup-generator` / `geo-optimizer` are installed, delegate to them and apply the gate to their output.
3. **Prioritize from AI referrals.** Delegate to the **`seo-strategist`** agent (fallback `general-purpose`) to read the AI-referral sessions — which pages get cited, by which engine (ChatGPT/Perplexity/Gemini/Claude/Kagi) — and recommend which pages to prioritize for GEO work. No referral log → reason from page type + indexation + GSC, and say the confidence is thin.
4. **HUMAN GATE.** Present the per-page JSON-LD + quick-answers + the AI-referral prioritization as named artifacts (written to the working tree or a chosen `out/` dir) for review. Ask via `AskUserQuestion`: approve / revise / discard. On approve, the human applies the schema manually or via `toprank setup-cms` — this command **never injects markup into the live site** and never publishes.

## Output artifact

Per page: a `schema.json` (typed JSON-LD — `Article` / `Product` / `FAQPage` / `BreadcrumbList` / `Organization` as the page type requires) + a quick-answer block, plus an **AI-referral tracking note** (which pages are cited, by which engine, and the prioritization rationale). All for review — nothing is applied or published.

## Guardrails

- **GEO is growth, not hygiene:** weight it heavily — dev-tutorial Google SEO is decaying; AI citation is the rising channel.
- **Valid + minimal schema:** emit only the fields the page truly supports; never fabricate ratings, prices, or authorship.
- **toprank optional:** detect-and-delegate per skill (`geo-optimizer`, `schema-markup-generator`); degrade to native tools (WebFetch/WebSearch/Write); never hard-fail on a missing plugin.
- **No vanity metrics:** prioritize by AI-citation potential and conversion, never impressions alone.
- **No auto-inject:** every path ends at a human gate; schema is applied manually or via `toprank setup-cms`.
