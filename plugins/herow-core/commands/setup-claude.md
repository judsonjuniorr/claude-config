---
description: (herow) Author personal, non-committed project instructions in CLAUDE.local.md (or shared CLAUDE.md) — an interview-driven friction log, not a codebase overview; optionally scaffolds skills + hooks.
argument-hint: "[local | project | both | <free text about yourself>]"
allowed-tools: Bash, Read, Edit, Write, AskUserQuestion, Glob, Grep, Agent, Skill
effort: xhigh
---

# /herow-core:setup-claude — personal project instructions

Author **personal user instructions** for *this* repo — the register of "who I am, how I work,
my sandbox URLs, my preferences, the traps I keep hitting here." This is the counterpart to the
built-in `/init`: `/init` writes a **codebase overview**; `setup-claude` writes a **friction
log** for you (or the team). It targets two files:

- **`CLAUDE.local.md`** — private, **globally** git-ignored (via `core.excludesfile`), never committed. Your personal notes for this repo.
- **`CLAUDE.md`** — team-shared, committed. Operational instructions everyone gets.

Both auto-load into every session at this directory level (`CLAUDE.local.md` loads *after*
`CLAUDE.md`). This command **never** touches the global `~/.claude/CLAUDE.md` — that's managed
separately.

> **GLOBAL RULE — questions to the user:** every question requiring a user response goes through
> the `AskUserQuestion` tool with 2–4 structured options (the free-text "Other" field is
> automatic). **Never** ask inline in prose. Save/accumulate answers incrementally; cap ~6
> questions per turn to avoid fatigue.

---

## The optimization policy (the whole point of this command)

Every line written to `CLAUDE.md`/`CLAUDE.local.md` costs context in **every** future session, so
it must earn its place. Before writing any line, it must pass **both** tests:

1. **Would removing this make Claude more likely to make a mistake here?** If no → cut it.
2. **Could Claude discover this by inspecting the repo, docs, manifests, CI, or config on
   demand?** If yes → cut it.

- **Include only:** non-discoverable personal facts (role, sandbox URLs, test accounts, local
  setup), operational landmines (tooling gotchas, unsafe legacy traps, commands Claude would
  guess wrong), non-obvious conventions, and always-on preferences (terse vs explain-tradeoffs,
  a tool/routing rule for this repo).
- **Never include:** directory trees, tech-stack summaries, architecture overviews, module
  catalogs, generic best-practice filler ("write clean code", "handle errors"), long API
  references (use an `@path/to/file` import instead), or anything that changes frequently when
  the source can just be referenced.
- **Prefer fixing the root cause.** If a repeated mistake can be prevented by a linter rule, a
  test, a hook, or automation, propose that instead of a permanent instruction line (Steps 6–7).
- **Editing an existing file = prune + add**, not append-only. Remove stale lines whose
  underlying issue is fixed; a `CLAUDE.md` that only grows is failing.
- **Never propose alternate instruction filenames** (no `AGENTS.md`, `.cursorrules`,
  `.windsurfrules`, `copilot-instructions.md`). Only `CLAUDE.md` / `CLAUDE.local.md`.

---

## Step 1 — Classify args, pick target & opt-ins

Read `$ARGUMENTS`:
- `local` → target is `CLAUDE.local.md`; `project` → `CLAUDE.md`; `both` → both.
- Free text (e.g. "I'm the backend lead, sandbox at localhost:8899") → treat as personal facts
  to extract now (fold into Step 3); still ask the target below.
- Empty → ask the target below.

Ask target via `AskUserQuestion` (unless `$ARGUMENTS` already fixed it):
- **Personal — CLAUDE.local.md** *(private, globally git-ignored — Recommended)*
- **Shared — CLAUDE.md** *(committed, team-visible)*
- **Both**

Then one `AskUserQuestion` — "Also set up skills and hooks?":
- **Skills + hooks** / **Skills only** / **Hooks only** / **Neither, just instructions**

This answer is a **hard filter**: Step 6 runs only if skills were chosen, Step 7 only if hooks
were chosen. Never scaffold an artifact type the user didn't opt into.

## Step 2 — Detect current state (read-only)

- **Anchor to the repo root first** — instruction files live at the repo root, not wherever
  Claude Code was launched. Resolve it once and use it for every path below (this doubles as the
  not-a-git-repo guard):
  ```bash
  ROOT="$(git rev-parse --show-toplevel)" || { echo "not a git repo — cannot set up project instructions"; exit 1; }
  ```
  Targets are `$ROOT/CLAUDE.md` and `$ROOT/CLAUDE.local.md`.
- **Existing target file:** if `$ROOT/CLAUDE.md` / `$ROOT/CLAUDE.local.md` already exists, `Read`
  it. You will propose precise diffs (prune + add), never clobber it.
- **Survey subagent (only if skills and/or hooks were opted in):** launch **one** read-only
  survey via the `Agent` tool (`subagent_type: Explore`). Ask it for *only* the facts needed to
  propose good skills/hooks: build/test/lint/format commands, existing `.claude/skills/`,
  formatter config (prettier/biome/ruff/black/gofmt/rustfmt or a `format` script), and CI config.
  This is **not** a codebase-overview pass for the instruction file — that stays a friction log.
- **Privacy coverage** (matters for a `local` target). `CLAUDE.local.md` must be **globally**
  git-ignored — a project `.gitignore` entry is a committed, team-shared rule, *not* the mechanism
  for a personal file. Resolve the global excludes at runtime — never hardcode a home path:
  ```bash
  GI="$(git config --global core.excludesfile)"; GI="${GI:-$HOME/.gitignore}"; GI="${GI/#\~/$HOME}"
  if grep -qxF 'CLAUDE.local.md' "$GI" 2>/dev/null; then echo "covered:global $GI"; else echo "uncovered:global"; fi
  ```
  If covered, the privacy guarantee already holds. Otherwise Step 5 adds it to the global excludes.
- **Worktrees:** run `git worktree list`. More than one entry means a git-ignored
  `CLAUDE.local.md` would exist only in the worktree that created it → Step 5 offers the import-
  stub pattern.

## Step 3 — Interview (AskUserQuestion, structured options, always a "Skip")

Ask about **the user and their relationship to this repo**, not about the codebase (that's
`/init`'s job). For each, offer options plus an explicit **Skip**. Suggested topics — pick the
ones that fit, don't ask all of them:

- **Role on this project** (e.g. backend lead / reviewer-only / occasional contributor / solo owner).
- **Familiarity** with this stack/codebase (deep / moderate / new-here — calibrates how much
  Claude should explain).
- **Communication preference** (terse / explain trade-offs / show-diffs-only).
- **Personal sandbox / test accounts / local setup** — URLs, ports, seeded logins, env-file
  locations (open question; these are the highest-value non-discoverable facts).
- **Workflow quirks** for this repo — anything you always do or always avoid here.
- **An always-on tool/routing rule** for this repo (e.g. "always run the app via `make dev`, not
  `npm start`").

For a **shared** `CLAUDE.md` target, steer toward team-relevant landmines and conventions rather
than personal facts (sandbox URLs belong in `CLAUDE.local.md`). If the user picked **Both**,
route each answer to the right file: personal/private → local, team-operational → shared.

If the user skips everything and gave no free-text facts, say so and stop — don't write an empty file.

## Step 4 — Synthesize + preview (optimization-policy gate)

Draft the file content applying the optimization policy above. Structure it like the user's own
instruction style: short topic-segmented `##`/`#` sections of imperative, always-on rules
(directive tone — "Always…", "Never…"), not prose paragraphs. Keep it minimal and high-signal.

For a **project `CLAUDE.md`** that's newly created, prefix it with:

```
# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.
```

(A `CLAUDE.local.md` needs no such preamble — start straight with the sections.)

Show the proposed content as a preview (use `AskUserQuestion`'s `preview` field where it fits;
for a longer file, show the full text then a plain **Confirm write?** question). If editing an
existing file, present it as a **diff** — additions *and* the stale lines you propose to remove.
**Nothing is written before an explicit Yes.**

## Step 5 — Write + privacy guard

On confirmation:

- **Write:** if the file exists, use `Edit` to apply the precise additions/removals; use `Write`
  only for a brand-new file.
- **No repo-side `.bak`.** `CLAUDE.md` is git-tracked (git is your backup). `CLAUDE.local.md` is
  unversioned — if you're overwriting an existing one, first copy the prior version into the
  session scratchpad and tell the user its path. A `CLAUDE.local.md.bak` in the repo would trip
  `/herow-core:doctor`'s `claude_md_backups` hygiene check, so never leave one.
- **Privacy guard (local target, if Step 2 found it uncovered):** `CLAUDE.local.md` must be
  **globally** git-ignored — **never** add it to the project `.gitignore` (a committed, team-shared
  rule defeats a *personal* file). Confirm via `AskUserQuestion`, then add it to the resolved
  global excludes (idempotent):
  ```bash
  GI="$(git config --global core.excludesfile)"; GI="${GI:-$HOME/.gitignore}"; GI="${GI/#\~/$HOME}"
  [ -f "$GI" ] || : > "$GI"
  grep -qxF 'CLAUDE.local.md' "$GI" || printf '%s\n' 'CLAUDE.local.md' >> "$GI"
  ```
- **Worktree stub (only if Step 2 detected multiple worktrees and target is `local`):** offer to
  write the real content to `~/.claude/<project>-instructions.md` (derive `<project>` from
  `basename "$ROOT"`) and make `$ROOT/CLAUDE.local.md` a one-line import:
  ```
  @~/.claude/<project>-instructions.md
  ```
  This survives across worktrees (each worktree's `CLAUDE.local.md` stub imports the same shared
  file). The stub path is home-scope, so it loads without the external-import approval dialog.

## Step 6 — Skills (only if opted in)

Propose skills that capture **repeatable workflows** the Step-2 survey surfaced, plus anything
the interview flagged as "I always do X here." If `.claude/skills/` already exists, review it
first and propose only complementary skills. Show each proposal via `AskUserQuestion`'s `preview`;
create only the accepted ones.

Create each at `.claude/skills/<skill-name>/SKILL.md`:

```yaml
---
name: <skill-name>
description: <what the skill does and when Claude should invoke it>
---

<Instructions for Claude.>
```

For a workflow with side effects, add `disable-model-invocation: true` and read input via
`$ARGUMENTS`.

> **Frontmatter caveat:** a `SKILL.md`'s frontmatter schema is **different** from this repo's
> command frontmatter. Skills use `name:` + `description:` (+ optional `disable-model-invocation`);
> commands use `description` / `argument-hint` / `allowed-tools` / `effort` and **never** `name`
> or `disable-model-invocation`. Don't copy one into the other.

## Step 7 — Hooks (only if opted in)

Propose a hook only where a repeated mistake is better prevented **mechanically** (e.g.
format-on-edit, a pre-commit guard) than by a persistent instruction line. A hook is a config
write to `.claude/settings.json` — **gate it** (show the JSON diff + an explicit **Confirm?**).

Prefer routing the actual settings edit through the built-in **`update-config`** skill rather
than hand-editing JSON; this command's job is to *identify* the hook and hand off, not to
reimplement settings plumbing. **Fallback** (since `update-config` is a built-in skill, not a
herow one — a soft dependency): if it isn't available, present the `settings.json` diff and let
the user apply it.

## Step 8 — Summary & follow-ups

- Recap what was written and why each file exists (which facts went to which file).
- Remind the user: `CLAUDE.md`/`CLAUDE.local.md` is a **friction log, not a dumping ground** —
  keep it small and prune lines as the underlying friction gets fixed. Re-running this command
  later should usually *remove* as much as it adds.
- Present any follow-ups as a short, impact-ordered to-do list (e.g. missing `gh` CLI, no lint
  config to enforce a convention you had to write as prose, a proposal-sourced hook the user
  deferred). Prefer mechanical fixes over more instruction lines.

---

## Self-check before finishing

Before declaring done, re-read what you wrote and confirm it did **not** regress into a codebase
overview: no directory tree, no stack summary, no generic best-practice filler. If editing an
existing file, confirm you proposed removals of stale lines, not only additions. If any of that
slipped in, fix it — that's the exact failure this command exists to prevent.
