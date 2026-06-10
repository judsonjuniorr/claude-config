# /graphify-install

End-to-end bootstrap for [graphify](https://github.com/safishamsi/graphify) inside any git repository.

See [`graphify-install.md`](./graphify-install.md) for the full agent-facing procedure.

## What it does

1. Confirms the working directory and verifies it's a git repo (offers `git init` if not).
2. Detects the project stack(s) — Node.js, Python, Go, Rust, Java/Kotlin, Ruby, PHP, .NET, Next.js, Nuxt — and tailors the output accordingly (cumulative for monorepos).
3. Generates a stack-tuned `.graphifyignore` with a generic base block plus stack-specific entries (e.g. `node_modules/`, `__pycache__/`, `target/`).
4. Appends the recommended graphify block to `.gitignore` (keeps `graph.json`, `GRAPH_REPORT.md`, `graph.html`, and `.graphify_labels.json` versioned; ignores caches and local metadata).
5. Runs the `graphify` skill to build (or update) the knowledge graph.
6. Optionally stages, commits, and pushes the resulting changes.
7. Prints a concise summary.

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
