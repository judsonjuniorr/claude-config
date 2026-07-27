# /graphify-install

End-to-end bootstrap for [graphify](https://github.com/safishamsi/graphify) inside any git repository.

See [`graphify-install.md`](./graphify-install.md) for the full agent-facing procedure.

## What it does

1. Confirms the working directory and verifies it's a git repo (offers `git init` if not).
2. Detects the project stack(s) — Node.js, Python, Go, Rust, Java/Kotlin, Ruby, PHP, .NET, Next.js, Nuxt — and tailors the output accordingly (cumulative for monorepos).
3. Generates a stack-tuned `.graphifyignore` with a generic base block plus stack-specific entries (e.g. `node_modules/`, `__pycache__/`, `target/`).
4. Appends the recommended graphify block to `.gitignore` (keeps `graph.json`, `GRAPH_REPORT.md`, `graph.html`, and `.graphify_labels.json` versioned; ignores caches and local metadata).
5. Runs the `graphify` skill to build (or update) the knowledge graph.
6. Installs append-safe `post-merge`/`post-checkout` git hooks so the graph auto-refreshes on `git pull` and branch switches, even when Claude Code isn't running.
7. Optionally stages, commits, and pushes the resulting changes.
8. Prints a concise summary.

## Keeping the graph fresh

Two complementary mechanisms keep `graphify-out/` from going stale:

- **Git hooks** (installed by this command, step 6 above): `post-merge` and `post-checkout` run `graphify update` in the background after a pull or branch switch, and stamp `graphify-out/.graphify_head` on success. Works even when Claude Code isn't open.
- **`herow-core`'s `graphify-freshen.sh`** (a `UserPromptSubmit` hook, ships separately with the `herow-core` plugin): a backstop that checks the current HEAD against `.graphify_head` on every prompt and triggers the same background refresh if the git hooks didn't already catch it (e.g. mid-session terminal pulls). Skips silently on worktrees without a `manifest.json`, single-flights via a lock dir, and can be disabled per-invocation with `HEROW_SKIP_GRAPHIFY=1`.

Also see `herow-core`'s `graphify-nudge.sh` (`PreToolUse`, matcher `Grep|Glob|Bash`) and `graphify-inject.sh` (`SessionStart`) — these steer Claude toward `graphify query`/`path`/`explain` instead of raw grep/glob whenever `graphify-out/graph.json` exists, without needing a per-repo `CLAUDE.md` edit.

## Frontmatter

- **description**: Bootstraps graphify in a git repository (stack-tuned `.graphifyignore`, `.gitignore`, first graph build, optional commit).
- **allowed-tools**: `Bash`, `Read`, `Write`, `Edit`, `AskUserQuestion`, `Skill`.
- **argument-hint**: none.

## Language

UX in **English**.

## When to use

- First time you want graphify on a repo.
- To refresh `.graphifyignore`/`.gitignore` after the repo's stack has shifted.

## Prerequisites

- The `graphify` skill is installed and available to Claude Code.
- You're inside a git repo (or willing to let the command run `git init`).
