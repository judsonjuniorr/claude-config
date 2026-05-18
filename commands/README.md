# commands

Slash commands for Claude Code. Each command lives in its own subdirectory containing:

- a `<command>.md` file with YAML frontmatter (`description`, `allowed-tools`, `argument-hint`) followed by the agent-facing instructions, and
- a `README.md` with the human-facing summary (what it does, when to use, prerequisites).

## Available

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
