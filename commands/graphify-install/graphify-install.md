---
description: (herow) Bootstraps graphify in a git repository (stack-tuned .graphifyignore, .gitignore, first graph build, optional commit)
allowed-tools: Bash, Read, Write, Edit, AskUserQuestion, Skill
argument-hint: ""
---

# /graphify-install

End-to-end bootstrap of graphify in the current repository: detects the stack, creates an appropriate `.graphifyignore`, adjusts `.gitignore`, runs the first graph build, and offers to commit/push the changes. All messages in **English**.

Execute the steps below **in order**. Do not skip steps. Communicate with the user in English.

---

## Step 0 — Confirm working directory

```bash
pwd
```

Show the path to the user in a single sentence: "Installing graphify in `<path>`." All actions happen in this directory. Do not change directories without confirmation.

---

## Step 1 — Verify git repository

Run:

```bash
git rev-parse --is-inside-work-tree 2>/dev/null && git rev-parse --show-toplevel 2>/dev/null
```

Three cases:

### 1a. Inside a repo and cwd is the root
`--show-toplevel` output matches `pwd`. Proceed to Step 2.

### 1b. Inside a repo but cwd is NOT the root
`--show-toplevel` output differs from `pwd`. Use `AskUserQuestion`:

- **Question:** "The current directory is a subdirectory of the repo (root: `<toplevel>`). Where should graphify be installed?"
- **Options:**
  - "At the repository root" (recommended) — mentally `cd <toplevel>`: adjust all subsequent paths to the root.
  - "In the current subdirectory" — continue with cwd as the base.

### 1c. NOT inside a git repo
The command failed. Use `AskUserQuestion`:

- **Question:** "This directory is not a git repository. graphify-install needs a repo. Initialize one now with `git init`?"
- **Options:**
  - "Yes, run git init"
  - "No, cancel"

If "No" → print "Installation canceled. Run `git init` manually and call `/graphify-install` again." and **exit without creating any file**.

If "Yes" → run `git init` and proceed to Step 2.

---

## Step 2 — Detect repository stack(s)

List the root files and detect which stacks are present. Detection is **cumulative** (monorepos may have several). Use:

```bash
ls -1a
```

Mark each stack as present based on the existence of signal files in the root:

| Stack | Signals |
|---|---|
| Node.js | `package.json`, `pnpm-lock.yaml`, `yarn.lock`, `package-lock.json`, `bun.lockb` |
| Python | `pyproject.toml`, `requirements.txt`, `setup.py`, `Pipfile`, `poetry.lock` |
| Go | `go.mod`, `go.sum` |
| Rust | `Cargo.toml` |
| Java/Kotlin | `pom.xml`, `build.gradle`, `build.gradle.kts` |
| Ruby | `Gemfile` |
| PHP | `composer.json` |
| .NET | any `*.csproj` or `*.sln` |
| Next.js | `next.config.js`, `next.config.ts`, `next.config.mjs` |
| Nuxt | `nuxt.config.js`, `nuxt.config.ts` |

Print to the user: "Detected stacks: <list>" (or "No recognized stack — using the generic block only.").

---

## Step 3 — Create `.graphifyignore`

If `.graphifyignore` **already exists** at the root, use `AskUserQuestion`:

- **Question:** "`.graphifyignore` already exists. What should we do?"
- **Options:**
  - "Overwrite" — delete the current file and regenerate from scratch
  - "Skip" — keep the existing file, proceed to Step 4

If creating (new or overwriting), assemble the content dynamically:

**Base block (always):**

```
# .graphifyignore — file/directory patterns that graphify should ignore
# Same syntax as .gitignore

# Generic
.git/
.DS_Store
Thumbs.db
*.log
*.swp
*.swo
.vscode/
.idea/
tmp/
temp/
coverage/

# graphify's own outputs
graphify-out/
```

**Append** the blocks below according to the detected stacks (in the order they appeared):

Node.js:
```

# Node.js
node_modules/
dist/
build/
.next/
.nuxt/
.vercel/
.turbo/
*.tsbuildinfo
```

Python:
```

# Python
__pycache__/
*.pyc
.venv/
venv/
env/
.pytest_cache/
.tox/
*.egg-info/
htmlcov/
.mypy_cache/
.ruff_cache/
```

Go:
```

# Go
vendor/
bin/
```

Rust:
```

# Rust
target/
```

Java/Kotlin:
```

# Java/Kotlin
target/
build/
.gradle/
*.class
```

Ruby:
```

# Ruby
.bundle/
vendor/bundle/
```

PHP:
```

# PHP
vendor/
```

.NET:
```

# .NET
bin/
obj/
```

Write the final file to `<root>/.graphifyignore` using the `Write` tool.

---

## Step 4 — Update `.gitignore`

Block recommended by graphify (keeps `graph.json`, `GRAPH_REPORT.md`, `graph.html`, and `.graphify_labels.json` **versioned** — only ignores local metadata and large caches):

```
# graphify
graphify-out/manifest.json
graphify-out/cost.json
graphify-out/.graphify_*
graphify-out/cache/
graphify-out/obsidian/
```

Behavior:

1. If `.gitignore` **does not exist**: create it with the block above (preceded by a blank line).
2. If `.gitignore` **exists**:
   - Check if it already contains the `# graphify` marker (use `grep -F '# graphify' .gitignore`).
   - If it does: print "graphify block already present in `.gitignore` — skipping." and continue.
   - If it doesn't: **append** the block to the end of the file (preceded by a blank line). Use Read + Write, or `cat >> .gitignore <<'EOF'` via Bash.

---

## Step 5 — Run `/graphify .`

Check whether a graph already exists:

```bash
test -f graphify-out/graph.json && echo "exists" || echo "new"
```

- If **exists**: run the graphify skill to update incrementally. Invoke the `Skill` tool with `skill: "graphify"` and `args: ". --update"`.
- If **new**: run the graphify skill for a full build. Invoke the `Skill` tool with `skill: "graphify"` and `args: "."`.

The skill handles the entire pipeline (detection, AST, semantic extraction via subagents, clustering, report). Wait for it to finish.

Afterwards, confirm that `graphify-out/graph.json` exists. If it doesn't, warn the user that the build failed and stop before Step 6.

---

## Step 6 — Offer commit & push

Show the current status:

```bash
git status --short
```

Use `AskUserQuestion`:

- **Question:** "Commit and push the changes?"
- **Options:**
  - "Yes, commit and push" (recommended if a remote exists)
  - "Yes, commit only (no push)"
  - "No, just leave them staged"
  - "Do nothing"

### If "Do nothing"
Do not run `git add`. Proceed to Step 7.

### If "No, just leave them staged"
Only do the selective stage (below), **without commit**. Proceed to Step 7.

### If committing (with or without push)

**Selective stage** — only add files that exist; never use `git add .`:

```bash
for f in .graphifyignore .gitignore graphify-out/graph.json graphify-out/GRAPH_REPORT.md graphify-out/graph.html graphify-out/.graphify_labels.json; do
  [ -e "$f" ] && git add "$f"
done
git status --short
```

**Commit** with a heredoc (follow the Co-Authored-By pattern from the system prompt):

```bash
git commit -m "$(cat <<'EOF'
chore: install graphify

- add .graphifyignore tuned for detected stack
- add graphify entries to .gitignore
- initial knowledge graph build

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>
EOF
)"
```

Show the resulting SHA (`git log -1 --oneline`).

### If also pushing

```bash
git remote -v
git branch --show-current
```

- **No remote configured:** print "Commit created, but no remote is configured. Skipped push. Configure with `git remote add origin <url>` and run `git push -u origin <branch>` manually."
- **With remote:** check whether the branch already has an upstream:

```bash
git rev-parse --abbrev-ref --symbolic-full-name @{u} 2>/dev/null
```

  - If upstream exists: `git push`
  - If not: `git push -u origin <branch>` (use the branch name obtained above)

**Never** use `--force` or `--no-verify`.

---

## Step 7 — Final summary

Print a short summary in English:

```
✓ graphify installed in <path>

Detected stacks: <list>
Files created/updated:
  - .graphifyignore
  - .gitignore (graphify block)
  - graphify-out/ (initial graph)

Commit: <SHA or "not created">
Push:   <done / no remote / skipped>

Next steps:
  /graphify query "<question about the repo>"
  /graphify .            # full rebuild
  /graphify --update     # incremental update
```

Keep the summary lean — don't repeat the whole pipeline.
