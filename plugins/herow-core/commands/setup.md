---
description: (herow) One-command stack installer/integrator — gstack, blueprint/quick/execute, rtk, graphify, headroom; removes OMEGA & conflicts (prompted)
allowed-tools: Bash, Read, Edit, AskUserQuestion
---

Bootstrap (or re-sync) this machine to the herow stack. **Idempotent** — re-running no-ops what's already done. Drive the steps below in order. The scripts live next to this command at `${CLAUDE_PLUGIN_ROOT}/scripts/setup/` and speak pipe-delimited records: `ok|code|detail`, `err|code|reason`, `info|...` (stderr), plus detect/verify use `dep|… tool|… remove|… pass|… fail|…`.

**Never remove anything without an explicit Yes from the user** (step 2). Every destructive edit writes a `.bak` first.

## Step 1 — Detect (read-only)

Run `bash "${CLAUDE_PLUGIN_ROOT}/scripts/setup/detect.sh"`. Parse the records and show the user a compact inventory in three groups:
- **Deps**: which of git/brew/python3/uv/node/npm/bun are `installed` vs `missing`.
- **Stack**: rtk / graphify / headroom / gstack — `installed` or `missing` (missing → will install).
- **Removal candidates**: every `remove|…` line — OMEGA surfaces, loose duplicate commands, stray memory/token MCP servers.

If there are zero missing items and zero removal candidates, say "already set up" and skip to Step 7 (verify).

## Step 2 — Confirm removals (AskUserQuestion, one Yes per group)

For each removal group that detect found, ask with `AskUserQuestion` (allow/deny). Nothing is removed without approval.
- **OMEGA** (if any `remove|omega|…`): one question covering all its surfaces (uv tool, `~/.local/bin/omega`, settings.json hooks, `~/.claude.json` MCP server, the `## Memory (OMEGA)` block in `~/.claude/CLAUDE.md`). Note: OMEGA's stored memories are dropped — the file-based `MEMORY.md` auto-memory remains. Default recommended: **remove** (this stack replaces it).
- **Loose duplicates** (if any `remove|loose|…`): one question to delete `~/.claude/commands/{blueprint,quick,execute}.md`, `~/.claude/hooks/blueprint-track.sh`, and the blueprint-track Skill hooks in settings.json — superseded by the herow-dev plugin versions. Default recommended: **remove**.
- **Stray memory/token tools** (each `remove|stray|<key>|…`): one question per server. Default: keep unless the user confirms it conflicts.

Collect the approved target tokens for Step 5: `omega`, `loose`, and `stray:<key>` for each approved stray.

## Step 3 — Ensure deps

Run `bash "${CLAUDE_PLUGIN_ROOT}/scripts/setup/ensure-deps.sh"`. Installs only what's missing (brew bootstrap if needed; uv via official installer). Surface any `err|…`. If python3 < 3.10 is reported, stop and tell the user to upgrade before headroom.

## Step 4 — Install stack

Run `bash "${CLAUDE_PLUGIN_ROOT}/scripts/setup/install-stack.sh"` (gstack clone+setup, rtk/graphify verify, headroom install). Report each `ok|…`/`err|…`.

Then wire headroom — **ask the user the mode** with `AskUserQuestion`:
- **MCP tools (Recommended, safe)**: registers headroom compress/retrieve/stats tools; does not touch API auth. → `bash "${CLAUDE_PLUGIN_ROOT}/scripts/setup/headroom-wrap.sh" mcp`
- **Proxy wrap (max savings)**: routes the API through the local proxy; can break Pro/Max OAuth auth (config is backed up; rollback = `headroom unwrap claude`). → `bash "${CLAUDE_PLUGIN_ROOT}/scripts/setup/headroom-wrap.sh" wrap`

Report the active mode the script prints.

## Step 5 — Apply approved removals

Only if Step 2 approved anything: run `bash "${CLAUDE_PLUGIN_ROOT}/scripts/setup/remove.sh" <tokens…>` with the approved tokens (e.g. `remove.sh omega loose`). Report each `ok|…`. Mention that `.bak` files were written.

## Step 6 — Integrate (verify wiring, no new settings.json hooks)

- The 3 commands ship from the **herow-dev** plugin (`/herow-dev:blueprint|quick|execute`) and its `hooks/hooks.json` registers the blueprint-track Skill hook — nothing to add to settings.json.
- Confirm `herow-core` and `herow-dev` are enabled (check `enabledPlugins` in `~/.claude/settings.json`); if not, tell the user to run `/plugin` → enable, or `claude plugin marketplace update herow`.
- The grep→graphify nudge hook stays in settings.json (kept). `/herow-dev:quick` and `/herow-dev:execute` now drive graphify directly.

## Step 7 — Verify

Run `bash "${CLAUDE_PLUGIN_ROOT}/scripts/setup/verify.sh"`. Show the `pass|…`/`fail|…` records and the final `summary|…` line.

## Final report

Summarize in a short block:
- Installed / already-present: gstack, rtk, graphify, headroom (+ mode).
- Removed (with Yes): OMEGA / loose dups / strays.
- 3 commands now at `/herow-dev:blueprint|quick|execute`; output is **compressed by default** (`/herow-core:uncompress` for full prose).
- **Manual follow-up:** restart the Claude session (or `/reload-plugins`) so the herow-dev hook and any removed OMEGA hooks take effect; if proxy-wrap was chosen, confirm the next API call works and `headroom unwrap claude` if auth fails.
