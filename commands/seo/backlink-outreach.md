---
description: The human-work command — finds relevant link targets, drafts personalized outreach, and tracks status. Cannot build links or manufacture DR; drafts only, you send.
allowed-tools: Read, Write, Edit, WebSearch, WebFetch, Grep, Glob, Agent, AskUserQuestion
argument-hint: "[gsc-export-path | --since N | --site URL]"
---

# /seo:backlink-outreach — draft + track link outreach (you build the links)

> **Requires:** a topic/niche to pursue authority for. Optionally a GSC export (Performance CSV / Bulk Export) **or** the `toprank` plugin's GSC integration, to find which pages most need authority. With no data, the topic alone is enough — GSC just sharpens targeting.
> **Human gate:** never sends anything, never auto-publishes. Ends by presenting targets + drafts + tracker for you to send manually.
> **No vanity metrics:** ranks targets by relevance and realistic reply odds, never by raw DR or list size.

**This command cannot build links.** It cannot manufacture DR or domain authority. Backlinks and DR gains are **human** outreach work — relationship-building done by the founder over **months**, never automatable. This command only *finds* relevant targets, *drafts* personalized messages, and *tracks* status. Sending the messages and building the relationships is your work. It will **never** claim a DR increase or guarantee a link.

## GSC data contract (shared across the suite)

`$ARGUMENTS` accepts one of:
- `gsc-export-path` — path to a **GSC Performance export** (CSV/XLSX: `Queries`/`Pages`/`Dates` with `Clicks, Impressions, CTR, Position`) or a **Bulk Data Export** (`searchdata_url_impression` / `searchdata_site_impression` rows). This is the canonical contract; the full column spec lives in [`commands/seo/README.md`](./README.md).
- `--since N` — analyze the last N days (used with toprank's GSC integration, if present).
- `--site URL` — the property to analyze.

If no data source resolves, do **not** fabricate data. Detect toprank's GSC integration first; if absent, print the **3-step export guide**: (1) Search Console → Performance → Export, or set up Bulk Data Export to BigQuery; (2) include Queries + Pages + Dates with Clicks/Impressions/CTR/Position; (3) save the file and re-run with its path. Then stop — *unless* a topic/niche was given, in which case proceed on the topic alone (GSC is optional here, only used to prioritize which pages need authority most).

## Flow

1. **Resolve topic + optional data.** Get the topic/niche from `$ARGUMENTS` or ask via `AskUserQuestion`. If a GSC source is given, detect `toprank` (its `seo-analysis` integration) and prefer delegating the pull to it; else read the export at `gsc-export-path`. Use GSC only to flag which pages most need authority — never required.
2. **Find realistic targets.** Delegate to the **`seo-strategist`** agent via the `Agent` tool (fall back to `general-purpose` if the agent file isn't installed — same precedent as the rest of the suite) to find relevant, *realistic* outreach targets via `WebSearch` (relevant blogs, resource pages, communities where the niche actually gathers). **Never** spammy mass lists — a short list of genuine fits beats a thousand cold domains.
3. **Draft personalized outreach.** Draft a few outreach messages, each personalized to the target with a genuine value angle (a resource they'd actually want, a correction, a contribution) — **not** link-begging. One message per target, in your voice.
4. **Maintain the tracker.** Append to (or create) an outreach tracking table: `target | contact | angle | status (drafted/sent/replied/linked) | date`. New runs append; never overwrite existing rows.
5. **HUMAN GATE.** Present the target list + drafts + tracker as artifacts. Ask via `AskUserQuestion`: approve / revise / discard. **You** send them manually. Never send, never auto-publish, never claim a DR gain.

## Output artifact

A target list (relevant blogs / resource pages / communities), a few personalized outreach drafts, and an outreach tracking table (`target | contact | angle | status | date`) — all written to the working tree for your review. Nothing is sent.

## Guardrails

- **Cannot build links:** this is the human-work command. Link-building is the founder's outreach over months; the command only drafts + tracks.
- **Never claim DR/authority gains:** no promised links, no projected DR. Outcomes depend on humans replying, which is outside any tool's control.
- **No spam / no mass-outreach:** relevance and a real value angle over volume. A bad fit is worse than no message.
- **toprank optional:** detect-and-delegate where relevant (GSC pull); degrade to native tools (WebSearch/WebFetch/Write); never hard-fail on a missing plugin.
- **Human gate:** every path ends with you sending manually. The command never sends, never publishes.
