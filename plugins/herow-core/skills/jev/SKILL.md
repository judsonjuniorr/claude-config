---
name: jev
description: Classify, score, or triage texts with Jev (typesafe/jev-1.13 via OpenRouter), a decision model that answers only typed questions (choice from a list, score on a scale, probability yes/no) with calibrated confidence. Use when the user says "use Jev to classify", "Jev decides", "ask Jev", or wants to classify/score/triage/route/filter a set of texts (emails, tickets, leads, passages) with a cheap, fast, calibrated decision instead of free-text reasoning. Use proactively whenever a task applies the same judgment to many texts, even if Jev isn't mentioned. Jev never writes text; Claude does.
---

# Jev — typed decisions

Jev decides; you write. Use it for narrow, structured judgments over text. Never ask it to draft, summarize, or explain; it only returns numbers and labels.

## Setup (once per machine)

1. Run `/herow-core:doctor`. It installs the `~/.herow/bin/jev` and `~/.herow/bin/jev-route` shims and lists the key under Manual steps.
2. Create a key at https://openrouter.ai/keys (the account needs credits), then store it in your own terminal, never in the chat:
   - macOS: `security add-generic-password -a "$USER" -s openrouter-api-key -w`
   - elsewhere: `export OPENROUTER_API_KEY=...` in your shell profile.
3. Start a new session or run `/clear` so the routing block is injected.

The key is read at runtime: Keychain first, then `OPENROUTER_API_KEY`. Never print it, export it from a script, or write it to a file or `.env`. If it's missing, tell the user to run the command above themselves.

`HEROW_HOME` (default `~/.herow`) holds the shims and the optional local files: `jev/config.json`, `jev/consents.md`, `jev/cases.local.json`, `jev/cache/` and `jev/route.log`. The commands below use the default path; if `HEROW_HOME` is set, replace `~/.herow` with it.

## Privacy gate (before every call)

Everything in `state` leaves the machine for OpenRouter/TypeSafe.
- Invented or public data: send directly.
- Anything real from the user (their files, email, notes, finances, clients, work): first show a short summary of what will be sent (item count, fields, a redacted sample) and wait for explicit confirmation. Send only the fields each question needs.

**Standing consents.** A skill that calls Jev may declare its own standing consent inline (which fields it sends, which it never sends); follow that instead of asking per run. The user may also record consents in `~/.herow/jev/consents.md`; read it when it exists. Without either, ask.

**Routing exemption.** `jev-route` calls need no per-call confirmation, because a stored key is the opt-in. The terms:
- Send only a Claude-written English task summary, never the raw prompt or file contents.
- `--redact-br` is always on (`jev-route` passes it).
- Project and person names go in only when `~/.herow/jev/consents.md` contains the line `routing: project-names`. Otherwise keep summaries generic.

## Call

```bash
~/.herow/bin/jev input.json [--conf 0.7] [--noul-band 0.3 0.7] [--workers 8] [--redact-br] [--dry-run]
```

Input: one request per item, with all questions batched (cheaper than one call per question):

```json
{
  "items": [{"id": "t1", "state": "My checkout page shows a blank screen after I click Pay."}],
  "questions": {
    "is_bug":  {"type": "noul",   "instructions": "Is the customer reporting a software defect?",
                "criteria": {"true": "Broken or unexpected behavior.", "false": "A question or feature request."}},
    "team":    {"type": "choice", "instructions": "Which team should own this ticket?",
                "criteria": {"payments": "Checkout or billing.", "frontend": "Rendering or layout.", "account": null}},
    "urgency": {"type": "score",  "instructions": "How urgent is this ticket?",
                "criteria": ["Can wait for the next release", "Should be fixed this week", "Blocking revenue right now"]}
  }
}
```

`state` may also be an object or an array; point to fields by name in backticks inside `instructions`.

An item may carry its own `questions`, which replace the top-level ones for that item. Use this when each item has its own candidate list. Give the options opaque keys (`c1`..`cN`, `none`) and put the candidate text in the criteria description. For a pair comparison, put both records in `state` as `{"a": …, "b": …}` under one fixed question, rather than writing B into `instructions`.

Items run concurrently (`--workers`, default 8); results keep input order. `--redact-br` scrubs Brazilian CPF/CNPJ (full, masked or cut short), chave de acesso, agência/conta and digit runs of 9+ from `state` and from criteria descriptions (option keys are left as they are). `--dry-run` prints the outgoing bodies without reading the key or calling the API; use it to audit what leaves the machine.

Output: `{"results": [{id, answers, uncertain, ms, cost, cost_source, model, generation_id, usage}], "errors": [{item_id, status, body, request}], "totals": {n, failed, ms, wall_ms, cost}}`. A failed item, including an exception inside a worker, doesn't drop the others (they're already paid); any failure exits 1. The `request` has no auth header; `status` is `null` on a timeout. A missing key or shim problem exits non-zero with one `jev unavailable: <problem>. <fix>` line on stderr, not JSON, so callers treat any non-zero exit as "Jev unavailable". Report errors verbatim, and don't switch route or model to make it work.

## Routing: which skill or subagent fits a task

```bash
~/.herow/bin/jev-route "task summary 1" ["task summary 2" ...]
```

One English summary per subtask, batched into one call, under the routing exemption above. Before calling Jev, a local BM25 pass picks the 8 most relevant agents (plus `general-purpose` and `Explore`) and the 15 most relevant skills (plus `vault` when that skill is installed), so each task costs ~1.6k input tokens, about $0.00007. A small pt-BR→English synonym map lets Portuguese descriptions match English summaries. When `--eval` reports `[not shortlisted]`, fix the synonyms or the `ALWAYS_*` lists, not Jev's instructions. Each line comes back as `agent=<id> (conf) | skill=<id> (conf) | alt=… | vault-first | uncertain=… | rule: …`. The options come from a catalog of the agents and skills actually installed, cached per working directory in `~/.herow/jev/cache/`. It rebuilds when `route.py`, plugins, settings, skills or command dirs change; `--rebuild` forces it.

`vault-first` appears only when a skill named `vault` is installed, and means P ≥ 0.6 that the task has history there: run that skill first. After Jev answers, rules apply on top: `general-purpose` is never used for finance or market tasks (when the better agent is installed), a `/command` is skipped, and any `rewrites` from `~/.herow/jev/config.json` apply. Without a `vault` skill Jev can't judge history, so there is no `vault-first`.

Optional `~/.herow/jev/config.json`:

```json
{
  "extra_command_dirs": ["~/my-commands"],
  "rewrites": [{"when_skill": "old-skill", "task_regex": "(?i)company", "to_skill": "new-skill"}],
  "routing_assist": true
}
```

`JEV_EXTRA_COMMAND_DIRS` (a `:`-separated list) replaces `extra_command_dirs`. `routing_assist: false` stops the session hook from injecting the routing block.

The output is advisory. Ignore any answer listed under `uncertain`, and fall back to your own judgment or a routing table in CLAUDE.md. `jev unavailable` (exit 1) means the same. `--eval` runs the bundled portable cases (herow components and built-ins only), then `~/.herow/jev/cases.local.json` against the full catalog when it exists; add `--gate 0.9` to exit 1 unless confident accuracy is at least 90% with confident answers on at least 75% of scored cases. Run it after editing the catalog text or instructions. Log: `~/.herow/jev/route.log`.

## The three formats

| type | criteria | answer | confidence |
|---|---|---|---|
| `choice` | `{option: description or null}`, up to 255 | `choice`, `probabilities` | `confidence` 0–1 |
| `score` | ordered list of 2–10 descriptive levels | `score` (float, can land between levels), `probabilities`, `legend` | `confidence` 0–1 |
| `noul` | `{"true": ..., "false": ...}` | `noul` = P(yes) | none |

## Uncertainty threshold

An answer is uncertain when choice/score `confidence < 0.7`, or when a noul falls in `0.3 ≤ P ≤ 0.7`. The script lists these under `uncertain`. The docs suggest a 0.5 floor and thresholds that scale with risk; 0.7 is the conservative default. Tighten it for destructive actions.

For uncertain rows, decide yourself from the text and mark the row **"decided by Claude"** in whatever you report. Keep Jev's raw answer alongside it.

## Reporting

For a batch, end with totals: item count, wall-clock time (`totals.wall_ms`), and total cost in USD from `totals`. If cost is `null`, say "not reported"; never estimate it.

## Pitfalls

- The route is `POST https://openrouter.ai/api/alpha/decisions`, **not** under `/api/v1` and not `/chat/completions`. The OpenRouter spec's global server is `/api/v1`, but the operation overrides it. Cost fallback: `GET /api/v1/generation?id=<id>`.
- Noul has no `confidence`; use distance from 0.5. `P(noul)` and `1 − P(negated noul)` are not comparable, so don't ask the negation to double-check.
- Score is a float. Threshold it; don't interpolate exact magnitudes from it.
- The model is literal. Put the exact condition in `instructions` and boundary cases in `criteria`. Avoid double negatives, multi-hop questions, and criteria that contradict the instruction. Split fuzzy judgments into two literal questions and combine them in code.
- English gives the best accuracy. Other languages work but worse, so watch confidence more closely.
- Limits: 64k tokens per request (state + all questions); 32k for state + the longest question. Pre-filter in code and send only needed fields.
- Pricing: billed per input token only (`usage.cost` = input_tokens × $0.042/Mtok); output is free. Fixed per-request overhead dominates short items, so putting all of an item's questions in one request costs about half as much as one call per question. 
- The same question can come back a few hundredths different on a repeat call, so don't treat a gap of about 0.03 as signal.
- Probabilities come back rounded to two decimals, so clear-cut cases show a hard `1`/`0` and `confidence: 1`. That's normal, not a bug.
- Choice option keys can contain spaces (`"quote request"`); the answer echoes the key verbatim.
- The response `model` field gives the dated version behind the alias. Log it, because the alias can move to a new version without warning.
- Docs: https://docs.typesafe.ai/llms.txt
