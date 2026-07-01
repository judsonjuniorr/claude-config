---
description: (herow) Validate the Claude Code config and stack — audits security, token-cost, and hygiene, applies fixes only with explicit approval; also bootstraps a fresh machine
allowed-tools: Bash, Read, Edit, Write, AskUserQuestion
effort: medium
---

Diagnose (and, with explicit approval, repair) this machine's herow stack and Claude Code configuration. **Read-only by default** — the audit changes nothing. Every fix is gated behind `AskUserQuestion` + a dry-run diff + a final confirm, and every destructive edit writes a timestamped `.bak` first.

Doctor also keeps **first-install compatibility**: if the stack isn't installed yet, it offers to run the installer (the existing `scripts/setup/` scripts) before auditing.

Scripts live at `${CLAUDE_PLUGIN_ROOT}/scripts/`:
- `scripts/setup/*` — detect + install (pipe-delimited records: `ok|… err|… info|…`, plus `dep|… tool|… remove|… pass|… fail|…`).
- `scripts/doctor/{security,tokens,hygiene,audit}.py` — the auditor (one JSON line per check; `audit.py` prints a consolidated report). Default is dry-run; `--apply <check_id>` applies one fix idempotently.

**Never apply anything without an explicit Yes from the user.**

---

## Step 1 — Detect (read-only)

Run `bash "${CLAUDE_PLUGIN_ROOT}/scripts/setup/detect.sh"`. Parse the records and show a compact inventory in four groups:
- **Deps**: git/brew/python3/uv/node/npm/bun — `installed` vs `missing`.
- **Stack**: rtk / graphify / headroom / gstack — `installed` or `missing`.
- **Removal candidates** (`remove|…`) and **Token optimizations** (`opt|…`) — relevant only to the install branch below.

## Step 2 — Install / repair branch (AskUserQuestion gate)

If any **stack tool is `missing`** (rtk/graphify/headroom/gstack), or detect surfaced removal/opt candidates, ask with `AskUserQuestion`:
- **Run install/repair now** — bootstrap the stack, then continue to the audit.
- **Audit only** — skip install; audit whatever exists.

Doctor never installs silently. If **Run install/repair** is chosen, execute the installer sequence (idempotent — re-running no-ops what's already done):

1. **Confirm removals** (`AskUserQuestion`, one Yes per group) for each `remove|…` group detect found — OMEGA surfaces, loose duplicate `blueprint|quick|execute` commands/hooks, stray memory/token MCP servers. Nothing is removed without approval. Collect approved tokens (`omega`, `loose`, `stray:<key>`).
2. `bash "${CLAUDE_PLUGIN_ROOT}/scripts/setup/ensure-deps.sh"` — installs missing deps; if it reports python3 < 3.10, stop and tell the user to upgrade before headroom.
3. `bash "${CLAUDE_PLUGIN_ROOT}/scripts/setup/install-stack.sh"` — gstack clone+setup, rtk/graphify verify, headroom install. Then **ask the headroom mode** (`AskUserQuestion`, all force telemetry OFF): **MCP tools (safe)** → `headroom-wrap.sh mcp`; **Durable init (Recommended)** → `headroom-wrap.sh init` (can break Pro/Max OAuth, backed up, needs restart); **Proxy wrap (legacy)** → `headroom-wrap.sh wrap`. Run `bash "${CLAUDE_PLUGIN_ROOT}/scripts/setup/headroom-wrap.sh" <mode>`.
4. `bash "${CLAUDE_PLUGIN_ROOT}/scripts/setup/token-guard.sh"` — safe defaults, no approval needed (`model: opusplan`, `advisorModel: opus`, `effortLevel: high`, `autoCompact: true`, removes any `CLAUDE_CODE_SUBAGENT_MODEL` pin, pins `ANTHROPIC_DEFAULT_OPUS_MODEL: claude-opus-4-8` and `ANTHROPIC_DEFAULT_SONNET_MODEL: claude-sonnet-5`).
5. **Model pin picker** — lets the user choose which Opus and Sonnet to pin for `opusplan` (overrides the safe defaults written by token-guard above):
   1. Run `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/setup/model-pin.py" --list`. Parse the output lines (`family|id|label`); split into `opus` and `sonnet` candidate **model IDs** (3 each, most recent first). Only these exact IDs are valid choices — never substitute free text.
   2. `AskUserQuestion` — "Which **Opus** model should `opusplan` use in plan mode?" Options: the 3 opus candidates (mark first as "(Recommended)").
   3. `AskUserQuestion` — "Which **Sonnet** model should `opusplan` use in execution mode?" Options: the 3 sonnet candidates (mark first as "(Recommended)").
   4. Before running anything, verify each chosen value is an **exact, unmodified match** to one of the IDs parsed in step 1 — never interpolate a value that wasn't in that list. Dry-run with each value **quoted**: `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/setup/model-pin.py" --apply --opus "<chosen-opus-id>" --sonnet "<chosen-sonnet-id>" --dry-run`. Show the diff. Then `AskUserQuestion` — **Confirm apply?** Proceed only on Yes.
   5. On Yes: run the same quoted command without `--dry-run`. Report the `.bak` path printed. `model-pin.py` itself checks the installed Claude Code version against each model's minimum (e.g. Sonnet 5 needs ≥ v2.1.197) and falls back or skips the pin with a `warn|…` line if the version is too old — surface that warning to the user if it appears, and suggest `claude update`.
6. If Step 2.1 approved anything: `bash "${CLAUDE_PLUGIN_ROOT}/scripts/setup/remove.sh" <tokens…>` (writes `.bak`s).
7. Confirm `herow-core` + `herow-dev` are enabled in `~/.claude/settings.json`; the 3 flow commands ship from herow-dev (`/herow-dev:blueprint|quick|execute`).
8. `bash "${CLAUDE_PLUGIN_ROOT}/scripts/setup/verify.sh"` — show the `pass|…`/`fail|…` records and the `summary|…` line.

Then continue to Step 3. (If the user chose **Audit only**, skip straight to Step 3.)

## Step 3 — Audit (read-only, no writes)

Run `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/doctor/audit.py"`. It prints `{"summary": {fail,warn,pass}, "checks": [...]}`. If `summary.fail == 0` **and** `summary.warn == 0`, report "config is clean — nothing to remediate" and stop.

The checks:
- **security** — `permissions_deny` (settings.json must deny reads of `.env`/credentials/secrets/`mcp-stash.json`), `plaintext_secrets` (mcp-stash.json must use `${VAR}` refs, not literal tokens).
- **tokens** — `headroom_hook_redundancy` (headroom init hook duplicated in PreToolUse + SessionStart), `playwright_headed_active` + `grafana_active` (heavy MCP servers that should be stashed on-demand).
- **hygiene** — `gstack_bak`, `claude_md_backups`, `language_rules_paths`.

## Step 4 — Present findings (grouped)

Render the `checks` array grouped, most urgent first:
- 🔴 **FAIL** — security blockers. Show each check's `detail` + `diff`.
- 🟡 **WARN** — token-cost / hygiene. Show each `detail` + `diff`.
- ✅ **PASS** — collapse to a count (list ids only if asked).

## Step 5 — Approve per category (AskUserQuestion)

For each category that has any FAIL/WARN (**security**, **tokens**, **hygiene**), ask one `AskUserQuestion`:
- **Apply all fixes in this category**
- **Choose individually** → then one `AskUserQuestion` per check in that category (**Apply** / **Skip**)
- **Skip this category**

Collect the approved `check` ids. Default-recommend applying security fixes; present token/hygiene as opt-in.

## Step 6 — Dry-run + final confirm

For each approved id, show its `fix_cmd` and its `diff` again (these came from the audit's dry-run — nothing has been written yet). Then one final `AskUserQuestion`: **Confirm apply?** Proceed only on an explicit Yes.

## Step 7 — Apply

For each approved id, run its `fix_cmd` **verbatim** (each is `python3 "…/scripts/doctor/<script>.py" --apply <id>`). Report each `ok|applied|<id>` or `ok|noop|<id>`, and list the `.bak` files written. Surface any `info|…` lines the scripts print. Special follow-ups:
- **`plaintext_secrets`**: the script prints `info|export-needed|<VAR>` lines and the `.bak` path (the only place the real values survive, chmod 600). Tell the user to add `export <VAR>=…` for each to `~/.zshrc` (reading the value from that `.bak`) and **fully restart Claude Code** — `${VAR}` is resolved at MCP server spawn, so until then those servers won't start.
- **`playwright_headed_active` / `grafana_active`**: a server was moved to the stash — remind the user to restart Claude Code; restore later with `~/.claude/mcp-restore.sh <name>`.
- **`headroom_hook_redundancy`** / **`permissions_deny`**: settings.json changed — restart Claude Code to pick up hook/permission changes.

## Step 8 — Re-verify + final report

Re-run `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/doctor/audit.py"` and confirm the fixed checks now report `pass`. Summarize in a short block:
- **Applied**: check ids + the `.bak` paths written.
- **Skipped**: check ids the user declined.
- **Manual follow-up**: `.zshrc` exports + a full Claude Code restart if secrets or MCP servers changed.
