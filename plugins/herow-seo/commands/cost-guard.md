---
description: (herow) Model-tiering & token-budget policy for the /seo:* suite — cheap tiers for parsing/diagnostics, Opus only for the final judgment call. Policy-only, gated on human approval.
allowed-tools: Read, Write, Edit, AskUserQuestion
argument-hint: "[gsc-export-path | --since N | --site URL]"
effort: low
---

# /seo:cost-guard — model-tiering & token-budget policy

> **Policy-only:** writes/updates a tiering policy the other /seo:* commands read; it never analyzes GSC and **never publishes site content.**
> **Human gate:** never silently changes behavior. Any policy edit is presented for your approval before it's written.
> **No runaway cost:** never run the whole suite on the most expensive tier — Opus is reserved for the final decision call.

Skeptic correction (Ok_Priority_5044): running *everything* through Claude makes token cost climb fast. This command defines and persists the **model-tiering policy** the rest of the suite honors — cheap tier for bulk work, Opus only where judgment actually matters — plus a per-run token budget the heavier commands check.

## Relationship to the data commands

The data commands (`/seo:content-sprint`, `/seo:launch`, etc.) accept a `gsc-export-path` — a GSC **Performance** export or **Bulk Export** — and cost-guard sets the model tier they use to *parse* it. The `argument-hint` is kept standard for suite consistency, but this command does not read GSC data itself; it only reads and writes the policy those commands consult.

## Tiering policy (work-type → tier)

- **Bulk GSC parsing & summarization** → Haiku / Sonnet (cheap tier).
- **Diagnostics** (cannibalization, indexability, gap reads) → Haiku / Sonnet.
- **Content drafting** → Sonnet.
- **Final strategic decisions** (which cluster, which fix list) → Opus only.
- **Per-run token budget** — a cap the heavier commands (e.g. `/seo:launch`) check before fanning out; over budget → stop and ask.

## Flow

1. **Read.** Load the current policy artifact if it exists (`~/.claude/seo/cost-policy.md`). If none exists, hold the defaults above in memory as the starting point.
2. **Show.** With `show` (or no args), print the current policy: each work-type → tier mapping and the token budget. With no args, also offer to edit it via `AskUserQuestion`.
3. **Propose — HUMAN GATE.** With `set` or free-text (e.g. "cap each run at 200k tokens", "force diagnostics to Sonnet"), translate the request into a concrete proposed policy and present the full proposed mapping + budget. Ask via `AskUserQuestion`: approve / revise / cancel. Do not write on anything but approve.
4. **Persist.** Only after approval, write/update the policy artifact. Confirm the path written.

## Output artifact

The persisted tiering + token-budget policy (`cost-policy.md`) that the other /seo:* commands read before choosing a model or fanning out work. Nothing else is produced.

## Guardrails

- **Never max-tier everything:** Opus is the final-judgment exception, not the default; bulk and diagnostic work stays on the cheap tier.
- **Advisory but checked:** the policy is advisory, but the heavier commands **must** consult it (and the budget cap) before running.
- **Human approves changes:** no policy is written without explicit approval at the gate.
- **Policy, not data:** this command never touches GSC data or publishes content — it only governs how the suite spends tokens.
