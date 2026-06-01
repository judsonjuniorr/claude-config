# commands

Slash commands for Claude Code. Each command lives in its own subdirectory containing:

- a `<command>.md` file with YAML frontmatter (`description`, `allowed-tools`, `argument-hint`) followed by the agent-facing instructions, and
- a `README.md` with the human-facing summary (what it does, when to use, prerequisites).

## Available

### [`/create-prd`](./create-prd/)

Brainstorm the inputs first, write second: extract every requirement a Product Requirements Document needs through structured questioning, then synthesize the PRD — lean one-pager or comprehensive.

**What it does**

1. Takes a feature name / one-line idea from `$ARGUMENTS` (asks if empty), derives a slug, then asks for **depth** (lean one-pager vs comprehensive) — which selects both the questions and the output template.
2. Runs structured `AskUserQuestion` discovery rounds: problem & evidence, who's affected, 5-Whys root cause, jobs-to-be-done & key flows, in/out-of-scope, success metrics (primary/secondary/guardrail), risks, and — for comprehensive — UX requirements plus an optional `backend-architect` handoff for high-level technical considerations. Skips anything already answered; never fabricates evidence or metrics — unknowns become open questions.
3. Synthesizes the PRD inline using the depth-appropriate sections — no time estimates, *what & why* never *how*, every requirement traceable to a user need. Comprehensive output includes personas, jobs-to-be-done, prioritized requirements, and user stories with `GIVEN/WHEN/THEN` acceptance criteria.
4. Offers to save. Chat-only by default; writes `docs/prd/<slug>.md` (or a chosen path) only if the user opts in — never unprompted.

**Allowed tools**: `AskUserQuestion`, `Read`, `Write`, `Glob`, `Grep`, `Agent`.

**Language**: English.

**When to use**: a vague idea needs a structured brief before engineering scopes it; you want a repeatable PRD with explicit problem, scope boundaries, and a primary/secondary/guardrail metric split rather than a free-form doc.

**Prerequisites**:
- None required — the PRD renders in chat; a file is written only on request.
- Optional: the [`backend-architect`](../agents/backend-architect.md) agent for the high-level technical-considerations section (fills inline if absent).

### [`/file-organizer`](./file-organizer/)

Analyze a directory, surface duplicates and clutter, propose a tidy structure, and only after explicit approval move/rename files — every destructive action is logged so it can be reversed.

**What it does**

1. Parses the target directory and aggressiveness (`conservative` default, `comprehensive` opt-in). Asks via `AskUserQuestion` for protected paths and whether to scan for duplicates.
2. Inventories the tree depth-limited (`find -maxdepth 3`): top-level layout, extension breakdown, largest items, date span, obvious clutter.
3. Optionally finds exact duplicates (`md5`/`md5sum`) and filename collisions — surfaces them with sizes/mtimes and a recommendation, never auto-deletes.
4. Presents a written plan (folders to create, moves, renames, deletions, items needing a decision) and asks **Proceed / Modify / Cancel**.
5. Executes with `mv -n` (no clobber), preserving mtimes, writing every action as `ACTION\tSRC\tDST` to `<target>/.file-organizer-YYYYMMDD-HHMMSS.log`.
6. Reports folders created, files moved per destination, bytes freed (if any), and the log path. Suggests a maintenance cadence (weekly sort, monthly review, quarterly dedupe, yearly archive).

**Allowed tools**: `Bash`, `Read`, `Write`, `Edit`, `Glob`, `Grep`, `AskUserQuestion`.

**Language**: English.

**When to use**: `Downloads/` has degenerated into chaos; a project tree needs structure before archiving; disk space is tight and you suspect duplicates; you're about to back up or sync a directory and want it clean first.

**Prerequisites**:
- POSIX shell with `find`, `du`, `sort`, `awk`, and `md5`/`md5sum`.
- Refuses to operate on `/`, `$HOME` root, `~/Library`, `~/.config`, `~/.ssh`, or paths with a top-level `.git/` unless the user explicitly insists.

### [`/fix-conflicts`](./fix-conflicts/)

Resolves merge conflicts on a PR or branch with every decision justified by the commit history of both sides — not by the raw diff.

**What it does**

1. Identifies the target from `$ARGUMENTS`: PR number/URL (`gh pr checkout`, base read from the PR), branch name (checks out, asks for the base via `AskUserQuestion` with discovered candidates), or empty (current branch + ask for base).
2. Refuses to proceed on a dirty tree; verifies the base ref exists after `git fetch --prune`.
3. Runs `git merge $BASE --no-commit --no-ff`. If clean, hands off without committing.
4. On conflicts, lists every unmerged file with hunk count and type (code/config/lock/doc).
5. Per file, inspects the commit history on both sides (`git log $MERGE_BASE..HEAD`, `$MERGE_BASE..MERGE_HEAD`, `git show <hash>`) and resolves each hunk against a decision table — complementary changes combine, explicit supersede/revert keeps the intentional side, formatting yields to semantics, imports/enums union, lockfiles are dropped and regenerated by the package manager, genuine doubt is escalated via `AskUserQuestion` with commit-backed alternatives.
6. Validates no `<<<<<<<`/`=======`/`>>>>>>>` markers remain, stages each file, records a one-line rationale per hunk.
7. Presents a per-file summary (intent of each side, decision, commits) and suggests `git commit --no-edit` or `git merge --continue`. Never commits, pushes, or posts PR updates automatically.

**Allowed tools**: `Bash(git:*)`, `Bash(gh:*)`, `Bash(glab:*)`, `Bash(grep:*)`, `Read`, `Edit`, `Write`, `AskUserQuestion`.

**Language**: English.

**When to use**: a PR is blocked by conflicts and you want resolutions justified by intent; a long-lived branch needs a careful merge from `main`/`develop`; conflicts span multiple files and need a structured walkthrough.

**Prerequisites**:
- Inside a git repository (the command runs `git fetch origin --prune` itself).
- For the PR path: `gh` (or `glab`) authenticated against the host.
- The [`github-ops`](../skills/github-ops/README.md) skill installed — every `gh`/`glab` interaction defers to it.

### [`/graphify-install`](./graphify-install/)

End-to-end bootstrap for [graphify](https://github.com/safishamsi/graphify) inside any git repository.

**What it does**

1. Confirms the working directory and verifies it's a git repo (offers `git init` if not).
2. Detects the project stack(s) — Node.js, Python, Go, Rust, Java/Kotlin, Ruby, PHP, .NET, Next.js, Nuxt — and tailors the output accordingly (cumulative for monorepos).
3. Generates a stack-tuned `.graphifyignore` with a generic base block plus stack-specific entries (e.g. `node_modules/`, `__pycache__/`, `target/`).
4. Appends the recommended graphify block to `.gitignore` (keeps `graph.json`, `GRAPH_REPORT.md`, `graph.html`, and `.graphify_labels.json` versioned; ignores caches and local metadata).
5. Runs the `graphify` skill to build (or update) the knowledge graph.
6. Optionally stages, commits, and pushes the resulting changes.
7. Prints a concise summary.

**Allowed tools**: `Bash`, `Read`, `Write`, `Edit`, `AskUserQuestion`, `Skill`.

**Language**: English.

**When to use**: first time you want graphify on a repo, or to refresh `.graphifyignore`/`.gitignore` after the repo's stack has shifted.

**Prerequisites**:
- The `graphify` skill is installed and available to Claude Code.
- You're inside a git repo (or willing to let the command run `git init`).

### [`/release-notes`](./release-notes/)

Generates a user-friendly changelog from the commits since the last tag (or the last 50 commits if no tag exists), rendered inline in the chat.

**What it does**

1. Detects the last language used in this repo (`customCommands.releaseNotes.lang` in `<repo-root>/.claude/settings.local.json`, default `pt-br`).
2. Asks for the language (`pt-br` or `en`) with the last choice pre-selected as `(Recommended)` and persists the answer (atomic write via `jq`, Python fallback), preserving every other key in the file.
3. Collects commits since the most recent tag by date — or the last 50 commits if no tag exists — dropping merge commits and cancelling out revert↔original pairs.
4. Classifies each commit into ✨ New Features, 🛠️ Improvements, 🐛 Bug Fixes, or 🔧 Internal Changes, using Conventional Commit prefixes and explicit decision rules. Marks breaking changes with `⚠️ Breaking:`.
5. Rewrites bullets in past tense, user-facing language — no jargon, no hashes, no PR/issue IDs, no author names — and groups related commits.
6. Suggests the next SemVer version (major/minor/patch) based on the change mix.
7. Renders the changelog inline in the chat using the localized template, omitting empty sections, and runs a final validation checklist.

**Allowed tools**: inherits Claude Code defaults (no explicit allow-list).

**Language**: bilingual — `pt-br` (default) or `en`, persisted per-repo.

**When to use**: preparing release notes before tagging a new version, or sharing a human-readable summary with non-engineering stakeholders.

**Prerequisites**:
- Inside a git repository.
- `jq` available (Python fallback if not).

### [`/validate-ui`](./validate-ui/)

Audits UI/UX against a **consolidated** ruleset — Vercel's Web Interface Guidelines as the base, plus three `davila7/claude-code-templates` skills (`frontend-design`, `ui-ux-pro-max`, `ui-design-system`) and Context7 docs for the detected lib/framework. **Read-only — never edits files.**

**What it does**

1. Fetches all four guideline sources fresh via `WebFetch` (raw URLs, never cache): Vercel `web-interface-guidelines` (mandatory base — stops if it fails) + `frontend-design`, `ui-ux-pro-max`, `ui-design-system` (warns and continues if a secondary one fails).
2. Consolidates them into one ruleset: Vercel as the a11y/focus/forms base; Pro Max for concrete thresholds (contrast 4.5:1, touch 44×44px, transitions 150–300ms, breakpoints 375/768/1024) and pre-delivery checklist; Design System for token consistency (8pt grid); Frontend Design for anti-generic aesthetics.
3. Resolves the files to audit from `$ARGUMENTS` (path/glob/URL) or, when empty, `Glob`s common UI files and lists them first.
4. Detects the stack (`package.json`/imports) and fetches the lib/framework's official best practices via **Context7** (`resolve-library-id` → `query-docs`), folding them into the ruleset. Skips gracefully if undetectable.
5. Static audit across every dimension: accessibility/ARIA, semantic HTML, visible focus, keyboard nav, forms, heading hierarchy, touch & interaction, reduced-motion, light/dark contrast, responsive layout, performance, token consistency, anti-generic aesthetics, and UX.
6. Opportunistic live validation: when given a URL or a detectable dev server, starts/uses it and drives `playwright-headless` to check focus rings, contrast, touch targets, and reduced-motion on screen — then shuts the server down.
7. Reports `file:line — [SEVERITY] rule: problem → fix`, grouped by file, with a SUMMARY (counts per severity) and the top-5 priorities. Never edits files.

**Allowed tools**: `WebFetch`, `Read`, `Glob`, `Grep`, `Bash`, `mcp__playwright-headless`, `mcp__context7`. No `Write`/`Edit` — read-only by construction.

**Language**: English.

**When to use**: before opening a UI PR; to audit a specific component/page against the Vercel standard; to check focus, contrast, and touch targets on screen, not just in code.

**Prerequisites**:
- Network access for the four guideline sources (Vercel base is mandatory).
- `playwright-headless` MCP server for live validation (optional — falls back to static-only).
- `context7` MCP server for lib/framework best practices (optional — skips if absent).

## Adding a new command

1. Create a subdirectory `commands/<name>/`.
2. Add `<name>.md` starting with frontmatter:
   ```yaml
   ---
   description: One-line summary shown in the slash-command picker.
   allowed-tools: Bash, Read, Write
   argument-hint: "<arg description>"
   ---
   ```
3. Write the agent-facing body as a numbered procedure — be explicit about ordering, error handling, and when to ask the user.
4. Add a `README.md` in the same subdirectory with the human-facing summary (what it does, allowed tools, language, when to use, prerequisites).
5. Document the new command here with: what it does, allowed tools, language (if non-English UX), when to use, and prerequisites.
