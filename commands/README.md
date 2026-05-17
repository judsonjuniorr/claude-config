# commands

Slash commands for Claude Code. Each command is a single `.md` file with YAML frontmatter (`description`, `allowed-tools`, `argument-hint`) followed by the agent-facing instructions.

## Available

### [`/graphify-install`](./graphify-install.md)

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

**When to use**: first time you want graphify on a repo, or to refresh `.graphifyignore`/`.gitignore` after the repo's stack has shifted.

**Prerequisites**:
- The `graphify` skill is installed and available to Claude Code.
- You're inside a git repo (or willing to let the command run `git init`).

## Adding a new command

1. Drop a new `.md` file in this directory.
2. Start with frontmatter:
   ```yaml
   ---
   description: One-line summary shown in the slash-command picker.
   allowed-tools: Bash, Read, Write
   argument-hint: "<arg description>"
   ---
   ```
3. Write the agent-facing body as a numbered procedure — be explicit about ordering, error handling, and when to ask the user.
4. Document it here with: what it does, allowed tools, language (if non-English UX), when to use, and prerequisites.
