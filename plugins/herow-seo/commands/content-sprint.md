---
description: (herow) Question-intent content pipeline — turn a GSC keyword gap into a drafted, schema-equipped article, gated on human approval.
allowed-tools: Read, Write, Edit, Bash, WebFetch, WebSearch, Grep, Glob, Agent, AskUserQuestion
argument-hint: "[gsc-export-path | --since N | --site URL]"
---

# /seo:content-sprint — question-intent content pipeline

> **Requires:** a GSC export (Performance CSV / Bulk Export) **or** the `toprank` plugin's GSC integration. With no data, this command prints the 3-step export guide and stops.
> **Human gate:** never auto-publishes. Ends by presenting the draft + schema for your approval.
> **No vanity metrics:** ranks opportunity by CTR / clicks-at-risk / indexability, never impressions alone.

Pillar 1 of the corrected Agensi playbook: answer exact developer/user queries at volume, one cluster at a time, with information gain that survives Core Updates. This is the 80% command — run it repeatedly, for months. Tooling gives you execution speed; **persistence is the actual lever.**

## GSC data contract (shared across the suite)

`$ARGUMENTS` accepts one of:
- `gsc-export-path` — path to a **GSC Performance export** (CSV/XLSX: `Queries`/`Pages`/`Dates` with `Clicks, Impressions, CTR, Position`) or a **Bulk Data Export** (`searchdata_url_impression` / `searchdata_site_impression` rows). This is the canonical contract; the full column spec lives in `${CLAUDE_PLUGIN_ROOT}/reference/gsc-data-contract.md`.
- `--since N` — analyze the last N days (used with toprank's GSC integration, if present).
- `--site URL` — the property to analyze.

If no data source resolves, do **not** fabricate data. Detect toprank's GSC integration first; if absent, print the **3-step export guide**: (1) Search Console → Performance → Export, or set up Bulk Data Export to BigQuery; (2) include Queries + Pages + Dates with Clicks/Impressions/CTR/Position; (3) save the file and re-run with its path. Then stop.

## Flow

1. **Resolve data.** Detect `toprank` (look for its `seo-analysis` / `content-planner` skills). If present, prefer delegating the GSC pull to it. Else read the export at `gsc-export-path`. If neither resolves → print the 3-step guide and stop. Error clearly on a missing/empty/malformed file — never silently pass.
2. **Strategize.** Delegate to the **`seo-strategist`** agent via the `Agent` tool (fall back to `general-purpose` if the agent file isn't installed — same precedent as finance/organizze) to find striking-distance question clusters: position 5–20 or weak CTR, filtered to question-intent and winnable difficulty (proxy KD ≤ 29, SV > 500, clear intent), deduped for cannibalization, with a content-gap read.
3. **Pick the cluster — HUMAN GATE.** Present the ranked clusters and ask via `AskUserQuestion` which one to draft (top recommendation first). Do not proceed without a choice.
4. **Draft.** Delegate to the **`content-engineer`** agent (fallback `general-purpose`) to produce: a quick-answer block at the top, the body, a concise FAQ, valid `FAQPage` + `Article` JSON-LD, 3–8 internal links with anchors, and a ≤60c title / ≤155c meta. If `toprank`'s `content-writer` / `schema-markup-generator` are installed, delegate to them and apply the gate to their output.
5. **Information-gain gate.** content-engineer returns **PASS** (with the proprietary element named) or **BLOCKED** (with the missing input — a real screenshot, benchmark, or take). A BLOCKED draft is returned to you with `[INSERT: …]` placeholders, never finalized.
6. **Final HUMAN GATE.** Present the draft + schema + link plan as artifacts (written to the working tree or a chosen `out/` dir). Ask via `AskUserQuestion`: approve / revise / discard. **Never publish** — publishing is manual or via `toprank setup-cms`.

## Output artifact

A `draft.md` (quick-answer + body + FAQ), a `schema.json` (FAQPage + Article JSON-LD), an internal-link plan, and title/meta — all for review, plus the gate verdict. Nothing is published.

## Guardrails

- **toprank optional:** detect-and-delegate per skill; degrade to native tools (WebFetch/WebSearch/Write); never hard-fail on a missing plugin.
- **No auto-publish:** every path ends at a human gate.
- **Information gain is a gate, not a nice-to-have:** commodity reworded-web drafts are BLOCKED.
- **Persistence reality:** one good cluster/day for months beats a burst. Say so if the user expects fast results.
