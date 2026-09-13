---
description: (herow) Generate or upsert a CLAUDE.md — interviews you for the friction only you know, reconciles the subagent routing table against the agents actually installed, writes the Health Stack, and prunes dated prompt text against the current model. Targets the global, project, and local instruction files.
argument-hint: "[global | project | local | both | all | <free text about yourself>]"
allowed-tools: Bash, Read, Edit, Write, AskUserQuestion, Glob, Grep, Agent, Skill
effort: xhigh
---

# /herow-core:setup-claude — author and upsert CLAUDE.md

Author the instruction files Claude loads in every session — the register of "who I am, how I
work, my sandbox URLs, my preferences, the traps I keep hitting here," plus the two blocks worth
generating rather than hand-writing: the subagent routing table and the health stack. This is the
counterpart to the built-in `/init`: `/init` writes a **codebase overview**; `setup-claude` writes
a **friction log**. It targets three files:

- **`CLAUDE.local.md`** — private, **globally** git-ignored (via `core.excludesfile`), never committed. Your personal notes for this repo.
- **`CLAUDE.md`** — team-shared, committed. Operational instructions everyone gets.
- **`~/.claude/CLAUDE.md`** — your machine-wide file, loaded in every repo. Home for the rules that
  aren't about one codebase: subagent routing, tool preferences, output style.

These are **concatenated, not overridden** — user file, then project `CLAUDE.md`, then
`CLAUDE.local.md`, ordered from the filesystem root down to the working directory, so the file
closest to where Claude started is read last. A fact stated in two of them is a fact the model has
to reconcile mid-task. Keep each one in exactly one file, chosen by scope: machine-wide → global,
this-repo-and-everyone → project, this-repo-and-just-me → local.

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
  test, a hook, or automation, propose that instead of a permanent instruction line (Steps 9–10).
- **Editing an existing file = prune + add**, not append-only. Remove stale lines whose
  underlying issue is fixed; a `CLAUDE.md` that only grows is failing.
- **Never propose alternate instruction filenames** (no `AGENTS.md`, `.cursorrules`,
  `.windsurfrules`, `copilot-instructions.md`). Only `CLAUDE.md` / `CLAUDE.local.md`.

### The budget

Target **under 200 lines per file**. Past that, adherence drops — rules get lost in their own
noise, and the ones that get lost are not the ones you'd choose. Measure before writing:
`wc -l "$TARGET"`.

`@imports` buy no headroom: imported files load at launch like everything else. The two mechanisms
that genuinely defer are `.claude/rules/*.md` with `paths:` frontmatter (loads only when Claude
touches a matching file) and skills (only the `description` stays resident). So the test for a
section is not "is this useful" but **"is this useful in every session"** — if it is merely
sometimes-relevant, it belongs in a rule file or a skill, not here.

### Model fit — write for the current model, not the last one

`CLAUDE.md` is a prompt and it ages like one: pressure language, scaffolds the API has since
replaced, step-by-step choreography for judgment calls, mitigations for a retired model's quirks.

**Those pattern tables are deliberately not restated here.** They ship with Claude Code in the
`claude-api` skill and are rewritten with every version of it, so read them at request time instead
of from a snapshot in this file:

```
/claude-api prompt-audit          # Skill(claude-api, "prompt-audit")
```

Step 6 runs it over the files you are editing. Consult it while *drafting* too — a pattern that
would be flagged on the way out should not be written on the way in. **Where anything in this
command disagrees with that skill, the skill wins:** it ships alongside the model, this file does
not.

What it does not cover, because these are properties of instruction files rather than dated
patterns:

- **Prose cannot enforce.** `CLAUDE.md` arrives as a user message, not as configuration; compliance
  is likely, never guaranteed. Anything that *must* happen at a fixed point is a hook (Step 10).
- **Enumerate, don't imply.** The current model reads literally and will not generalize a rule from
  one item to its sibling. A routing table naming six agents does not route the seventh; a lint
  command written for one package does not cover the monorepo's others.
- **Length is an instruction, not a setting.** If you want terse sessions, write the conciseness
  rule into the file — lowering `effort` reduces thinking, not the visible response.

---

## Step 1 — Classify args, pick target & opt-ins

Read `$ARGUMENTS`:
- `local` → `CLAUDE.local.md`; `project` → the repo's `CLAUDE.md`; `global` → `~/.claude/CLAUDE.md`;
  `both` → project + local; `all` → all three.
- Free text (e.g. "I'm the backend lead, sandbox at localhost:8899") → treat as personal facts
  to extract now (fold into Step 5); still ask the target below.
- Empty → ask the target below.

Ask target via `AskUserQuestion` (unless `$ARGUMENTS` already fixed it):
- **Personal — CLAUDE.local.md** *(private, globally git-ignored — Recommended)*
- **Shared — CLAUDE.md** *(committed, team-visible)*
- **Machine-wide — ~/.claude/CLAUDE.md** *(every repo on this machine; where subagent routing belongs)*
- **Project + personal** / **All three**

`global` is the one target that does not require a git repo — skip the repo-root guard below for
it, and never write repo-specific facts (paths, ports, this codebase's conventions) into it.

Then one `AskUserQuestion` — "Also set up skills and hooks?":
- **Skills + hooks** / **Skills only** / **Hooks only** / **Neither, just instructions**

This answer is a **hard filter**: Step 9 runs only if skills were chosen, Step 10 only if hooks
were chosen. Never scaffold an artifact type the user didn't opt into.

## Step 2 — Detect current state (read-only)

- **Anchor to the repo root first** — instruction files live at the repo root, not wherever
  Claude Code was launched. Resolve it once and use it for every path below (this doubles as the
  not-a-git-repo guard):
  ```bash
  ROOT="$(git rev-parse --show-toplevel)" || { echo "not a git repo — cannot set up project instructions"; exit 1; }
  ```
  Targets are `$ROOT/CLAUDE.md` and `$ROOT/CLAUDE.local.md`.
- **Existing target files:** `Read` every target that exists — `$ROOT/CLAUDE.md`,
  `$ROOT/CLAUDE.local.md`, `~/.claude/CLAUDE.md`. You will propose precise diffs (prune + add),
  never clobber them. Note the line count of each against the 200-line budget, and note which
  generated sections are already present: a routing table (and whether it is fenced by
  `setup-claude:` markers), and `## Health Stack` — including whether there is more than one of
  them, which means `/health` has written its own copy alongside ours (Step 8).
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
  If covered, the privacy guarantee already holds. Otherwise Step 8 adds it to the global excludes.
- **Worktrees:** run `git worktree list`. More than one entry means a git-ignored
  `CLAUDE.local.md` would exist only in the worktree that created it → Step 8 offers the import-
  stub pattern.

## Step 3 — Inventory the agents (whenever a routing table is in play)

The subagent routing table is the highest-value block in a machine-wide `CLAUDE.md` and the fastest
to rot: agents get renamed, plugins get namespaced, marketplaces get reinstalled, and the table goes
on pointing at names that no longer resolve. Never hand-write it. Generate it from what is installed:

```bash
python3 - <<'PY'
import json, pathlib, re
def fm(f, key):
    m = re.search(rf"^{key}: *(.+)$", f.read_text(errors="replace"), re.M)
    return m.group(1).strip() if m else ""
seen = []
for d in (pathlib.Path(".claude/agents"), pathlib.Path.home()/".claude/agents"):
    for f in sorted(d.glob("*.md")) if d.is_dir() else []:
        seen.append((fm(f, "name") or f.stem, fm(f, "description"), str(f)))
reg = pathlib.Path.home()/".claude/plugins/installed_plugins.json"
if reg.is_file():
    for full, entries in json.loads(reg.read_text()).get("plugins", {}).items():
        plug = full.split("@")[0]
        # a plugin can be installed at more than one scope; the project-scoped
        # copy is the one this repo actually gets, so let it win the dedupe below
        for e in sorted(entries, key=lambda e: e.get("scope") != "project"):
            for f in sorted(pathlib.Path(e["installPath"]).glob("agents/*.md")):
                n = fm(f, "name") or f.stem
                seen.append((f"{plug}:{n}", fm(f, "description"), str(f)))
out = dict()
for name, desc, src in seen:
    out.setdefault(name, (desc, src))
for name, (desc, src) in sorted(out.items()):
    print(f"{name}\t{desc[:160]}\t{src}")
print(f"\n{len(out)} agent(s)")
PY
```

Run it from the repo root so project-level `.claude/agents/` is included. If this repo *defines*
agents (`plugins/*/agents/`, `.claude/agents/`), those count too — read them from source rather
than from an installed copy, which may be a stale version.

**The table itself goes in the global file, and only there.** Routing is a machine-wide concern:
the same agents are available in every repo, and a copy in a project `CLAUDE.md` is a second
source of truth that will drift from the first. So enumerate from every source, but write the
table only when the run's target includes `global`. If the target excludes it and you find drift
anyway — rows naming agents that no longer resolve, or newly installed agents with no row — report
that as a gap in Step 11 with the command to fix it (`/herow-core:setup-claude global`) rather than
writing a routing table into the wrong file.

Two rules decide what you write:

- **Plugin agents are addressed `<plugin>:<name>`.** A bare `code-reviewer` does not name
  `herow-core:code-reviewer`. Every row carries the fully-qualified type exactly as the `Agent`
  tool accepts it — the model reads the table literally and will not repair a name that doesn't
  resolve. Verify each existing row against the inventory; this is the single most common defect
  in an inherited routing table.
- **Reconcile, don't append.** Diff the inventory against the rows already in the file and report
  three buckets before writing anything: rows naming an agent that no longer exists (**delete**),
  installed agents with no row (**add, or omit on purpose**), and rows whose trigger no longer
  matches the agent's own `description` (**rewrite**).

Then build the table — one trigger phrase, one fully-qualified type per row. Derive the trigger
from the agent's own `description`: that is the text its author wrote to be routed on, and keeping
the table in sync with it is what stops the two from drifting. Compress to the distinguishing
intent; a synonym list costs tokens in every session and generalizes worse than a category.

**Every routing table needs a brake.** The current model delegates *more* readily than its
predecessors, so a table with no upper bound over-routes: one-file edits get a subagent, context is
lost across the boundary, and the work costs several times what it should. The non-routing
conditions are not optional garnish — they are the half that makes the table safe:

```
## When NOT to route
- A single read or edit of one already-identified file.
- A question answerable from context already loaded.
- Continuation of work already running in this conversation.
- More than N subagents for one request.
```

Ask the user (`AskUserQuestion`) which agents are worth routing and whether they want the cap. An
agent they never reach for is a row that costs tokens in every session and buys nothing; an agent
whose `description` is too vague to derive a trigger from is a finding to report (Step 11), not a
row to invent.

## Step 4 — Detect the health stack

`CLAUDE.md` should answer "how do I check this repo" without the model guessing — guessing runs
`npm test` in a Bun repo and `pytest` where the real entry point is a `Makefile` target. Detect the
commands; read the manifests rather than assuming:

```bash
[ -f tsconfig.json ] && echo "typecheck: tsc --noEmit"
[ -f package.json ] && node -e 'const s=require("./package.json").scripts||{};for(const k of ["typecheck","lint","test","build"])if(s[k])console.log(k+": npm run "+k)' 2>/dev/null
ls biome.json biome.jsonc eslint.config.* .eslintrc* 2>/dev/null | head -1
[ -f pyproject.toml ] && grep -Eq 'ruff|pytest' pyproject.toml && echo "python: ruff check . / pytest"
[ -f Cargo.toml ] && echo "rust: cargo clippy -- -D warnings / cargo test"
[ -f go.mod ] && echo "go: go vet ./... / go test ./..."
[ -f Makefile ] && grep -E '^(lint|test|check|build|typecheck):' Makefile
command -v shellcheck >/dev/null && ls *.sh scripts/*.sh 2>/dev/null | head -1
```

Prefer the repo's own entry point over the underlying tool: if `package.json` defines a `lint`
script, write `npm run lint`, not `eslint .` — the script carries flags you would otherwise drop.
Confirm the detected set with the user (`AskUserQuestion`) before writing it.

Write it as a `## Health Stack` section, one `key: command` per line:

```
## Health Stack

- typecheck: tsc --noEmit
- lint: biome check .
- test: bun test
- deadcode: knip
- shell: shellcheck *.sh scripts/*.sh
```

Keep that heading and that shape exactly. It is a published contract, not a formatting choice: the
third-party `/health` skill reads `## Health Stack` from `CLAUDE.md` and skips its own detection
when it finds one, so writing the section makes the repo work with that skill **without this
command depending on it** — and the section earns its place on its own if the skill was never
installed. Do not call `/health`, and do not make the section conditional on it being present.

Omit a key you could not detect rather than writing a plausible guess. A wrong command here is
worse than a missing one: the model will run it.

## Step 5 — Interview (AskUserQuestion, structured options, always a "Skip")

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

## Step 6 — Audit what is already there (editing an existing file)

A `CLAUDE.md` that only grows is failing. Before proposing a single addition, audit the current
contents against the current model:

```
/claude-api prompt-audit          # Skill(claude-api, "prompt-audit")
```

Invoke it — never work from a remembered version of its rules. It is a bundled skill, re-shipped
with each Claude Code release, so the procedure and its pattern tables are current for the model
running right now in a way a copy in this file could never be.

Scope it to the instruction surface in play — `CLAUDE.md`, `CLAUDE.local.md`,
`~/.claude/CLAUDE.md`, `.claude/rules/*.md` — not the whole repo. It returns findings with
`file:line`, the dated pattern each one matches, and a concrete edit; fold the high- and
medium-confidence removals into the Step 7 diff alongside your additions. If the skill is
unavailable, apply the "Model fit" rules above by hand and say in the summary that the audit was
manual.

**An audit that finds nothing changes nothing.** A clean file is a valid outcome. Never manufacture
cuts to look productive, and never justify a removal by length alone — the harm comes from specific
dated instructions, not from volume. Environment facts, the reasons behind constraints, and the
quality bar are load-bearing context at any length.

## Step 7 — Synthesize + preview (optimization-policy gate)

Draft the file content applying the optimization policy above. Structure it like the user's own
instruction style: short topic-segmented `##`/`#` sections of imperative, always-on rules
(directive tone — "Always…", "Never…"), not prose paragraphs. Keep it minimal and high-signal.

For a **project `CLAUDE.md`** that's newly created, prefix it with:

```
# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.
```

(A `CLAUDE.local.md` needs no such preamble — start straight with the sections.)

Before previewing, check the result against the budget: count the lines the file will have after
the diff. If it lands over 200, do not just proceed — say so, and propose what moves out. The usual
answers are a path-scoped `.claude/rules/*.md` for anything that only matters when Claude touches
certain files, or a skill for a workflow that is occasionally relevant. Splitting into `@imports`
is not an answer; those load at launch too.

Show the proposed content as a preview (use `AskUserQuestion`'s `preview` field where it fits;
for a longer file, show the full text then a plain **Confirm write?** question). If editing an
existing file, present it as a **diff** — additions *and* the stale lines you propose to remove,
including everything Step 6's audit turned up. **Nothing is written before an explicit Yes.**

## Step 8 — Write + privacy guard

On confirmation:

- **Write:** if the file exists, use `Edit` to apply the precise additions/removals; use `Write`
  only for a brand-new file.
- **The routing table is replaced, not appended.** It is regenerated on every run, so fence it and
  rewrite only what is between the fences:

  ```
  <!-- setup-claude:agents:begin -->
  ## Subagent routing
  ...
  <!-- setup-claude:agents:end -->
  ```

  The fences are HTML comments, so the `##` heading inside is still an ordinary heading. Re-running
  replaces the block in place rather than leaving a second copy — two routing tables that disagree
  is worse than none. If an *unfenced* routing table is already in the file, show the replacement
  and ask before adopting it: hand edits may be living there.
- **`## Health Stack` is never fenced.** It is a shared section, not ours: `/health` appends or
  updates it in `CLAUDE.md` on its own, knows nothing about fences, and would write a second copy
  below ours or edit inside a fence we would then discard. Regenerate it positionally instead —
  find the `## Health Stack` heading and replace through to the next `##` (or end of file), leaving
  the heading itself in place. If two `## Health Stack` sections already exist, that is this
  collision having already happened: show both and ask which survives.
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

## Step 9 — Skills (only if opted in)

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

## Step 10 — Hooks (only if opted in)

Propose a hook only where a repeated mistake is better prevented **mechanically** (e.g.
format-on-edit, a pre-commit guard) than by a persistent instruction line. A hook is a config
write to `.claude/settings.json` — **gate it** (show the JSON diff + an explicit **Confirm?**).

Prefer routing the actual settings edit through the built-in **`update-config`** skill rather
than hand-editing JSON; this command's job is to *identify* the hook and hand off, not to
reimplement settings plumbing. **Fallback** (since `update-config` is a built-in skill, not a
herow one — a soft dependency): if it isn't available, present the `settings.json` diff and let
the user apply it.

## Step 11 — Summary & follow-ups

- Recap what was written and why each file exists (which facts went to which file).
- Remind the user: `CLAUDE.md`/`CLAUDE.local.md` is a **friction log, not a dumping ground** —
  keep it small and prune lines as the underlying friction gets fixed. Re-running this command
  later should usually *remove* as much as it adds.
- **Name what you could not resolve.** Every gap goes in the recap with the question attached,
  never silently dropped: a health-stack key you could not detect, a routing decision the user
  skipped, an agent whose `description` was too vague to derive a trigger from, a sandbox URL or
  test account nobody supplied, a convention you had to guess. The user can fill a gap they can
  see — ask for exactly the fact you need, not for "more context".
- Present any follow-ups as a short, impact-ordered to-do list (e.g. missing `gh` CLI, no lint
  config to enforce a convention you had to write as prose, a proposal-sourced hook the user
  deferred). Prefer mechanical fixes over more instruction lines.

---

## Self-check before finishing

Before declaring done, re-read what you wrote and confirm all of it:

- It did **not** regress into a codebase overview — no directory tree, no stack summary, no generic
  best-practice filler. That is the exact failure this command exists to prevent.
- Every agent type in the routing table is fully qualified and appears in the Step 3 inventory.
  Re-check them by name; a table that names agents which do not resolve is worse than no table.
- Every command in `## Health Stack` came from detection, not assumption.
- If you edited an existing file, you proposed removals, not only additions.
- Every Step 6 audit finding was either applied or explicitly declined with a reason — none
  silently dropped. (Don't re-derive its rules from memory here; it already ran.)
- The file is under 200 lines, or you told the user why it isn't and what you proposed moving out.

If any of that slipped, fix it before reporting done.
