---
description: (herow) Bootstraps graphify in a git repository (stack-tuned .graphifyignore, .gitignore, first graph build, optional commit)
allowed-tools: Bash, Read, Write, Edit, AskUserQuestion, Skill
argument-hint: ""
effort: low
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

## Step 6 — Install git freshness hooks (post-merge, post-checkout)

The graph goes stale after a `git pull` or branch switch. Install two small,
append-safe git hooks so the graph refreshes even when Claude Code isn't running.
These complement (not replace) graphify's own `graphify hook install` (post-commit) —
that one is offered separately by the `graphify` skill itself; this step only covers
post-merge/post-checkout.

Both hooks share one rule: **never clobber an existing hook.** Before writing, check
for the sentinel `# >>> graphify auto-refresh` in the target file (`grep -F` if it
exists). If present, skip that hook and print "git hook already installed — skipping."
If the target file doesn't exist, create it with a `#!/bin/sh` shebang. If it exists
without the sentinel, **append** the block to the end (preceded by a blank line) —
never overwrite.

Both blocks additionally require `graphify-out/manifest.json` to exist — not just
`graph.json` — before running. `manifest.json` is gitignored (Step 4), so a fresh
`git worktree add` checkout has `graph.json` (committed) but no `manifest.json`.
Worktrees **share** the main repo's `.git/hooks` (git resolves them to the common
dir), and `git worktree add` fires `post-checkout` with `$3 = 1` — so without this
guard, every `/herow-dev:quick`/`/herow-dev:execute` worktree creation would kick
off a `graphify update` inside a disposable tree. This mirrors the same guard in
the herow-core `graphify-freshen.sh` backstop (Part B1) — keep the two in agreement.

Both hooks must take the **same lock** `graphify-freshen.sh` uses
(`graphify-out/.graphify_update.lock`) — not a hook-local lock — so a git-triggered
refresh and a session-triggered refresh can never race on `graph.json`/`manifest.json`
concurrently. Reclaim is gated on **PID liveness**, not a fixed time window: a flat
TTL would risk stealing the lock from a `graphify update` that's simply still
running (large repo, LLM-backed semantic pass, slow API) and spawning a second
concurrent update with no coordination between them. The lock instead records the
backgrounded job's PID and is only reclaimed once `kill -0 <pid>` confirms that
process is actually dead (a 30s grace window covers the brief gap between `mkdir`
and the PID being written). A `graphify-out/.graphify_update.failcount` file tracks
consecutive failures and backs off (linear, capped at 30 min) instead of retrying a
persistently-broken `graphify update` on every single pull/checkout.

The guard-and-refresh body below is **identical in both hooks** (only the outer
condition differs — post-checkout adds the `$3 = 1` branch-checkout check) and
mirrors `graphify-freshen.sh` exactly, including its `|| true` guards after every
`read` — this block gets appended to an arbitrary pre-existing hook file that may
have `set -e`, and a `read` returning non-zero on a short/malformed file must not
abort the whole hook. Embed it verbatim in place of `<REFRESH_BLOCK>`:

```sh
LOCK=graphify-out/.graphify_update.lock
FAILFILE=graphify-out/.graphify_update.failcount
SKIP=0
if [ -f "$FAILFILE" ]; then
  FAILCOUNT=0; LAST_FAIL=0
  read FAILCOUNT LAST_FAIL < "$FAILFILE" 2>/dev/null || true
  case "$FAILCOUNT" in (*[!0-9]*|'') FAILCOUNT=0 ;; esac
  case "$LAST_FAIL" in (*[!0-9]*|'') LAST_FAIL=0 ;; esac
  if [ "$FAILCOUNT" -ge 3 ]; then
    BACKOFF=$((FAILCOUNT * 60)); [ "$BACKOFF" -gt 1800 ] && BACKOFF=1800
    NOW=$(date +%s)
    [ $((NOW - LAST_FAIL)) -ge "$BACKOFF" ] || SKIP=1
  fi
fi
if [ "$SKIP" = "0" ]; then
  if mkdir "$LOCK" 2>/dev/null; then
    :
  else
    OWNER_PID=""
    [ -f "$LOCK/pid" ] && OWNER_PID=$(cat "$LOCK/pid" 2>/dev/null || true)
    case "$OWNER_PID" in (*[!0-9]*|'') OWNER_PID="" ;; esac
    if [ -n "$OWNER_PID" ] && kill -0 "$OWNER_PID" 2>/dev/null; then
      SKIP=1
    else
      STARTED=0
      [ -f "$LOCK/started_at" ] && STARTED=$(cat "$LOCK/started_at" 2>/dev/null || echo 0)
      case "$STARTED" in (*[!0-9]*|'') STARTED=0 ;; esac
      NOW2=$(date +%s)
      if [ "$STARTED" -gt 0 ] && [ $((NOW2 - STARTED)) -gt 30 ]; then
        rm -rf "$LOCK" 2>/dev/null
        mkdir "$LOCK" 2>/dev/null || SKIP=1
      else
        SKIP=1
      fi
    fi
  fi
fi
if [ "$SKIP" = "0" ]; then
  date +%s > "$LOCK/started_at" 2>/dev/null
  nohup sh -c '
    if graphify update >graphify-out/.graphify_update.log 2>&1 </dev/null; then
      git rev-parse HEAD > graphify-out/.graphify_head 2>/dev/null
      rm -f graphify-out/.graphify_update.failcount
    else
      count=0
      [ -f graphify-out/.graphify_update.failcount ] && { read count _ < graphify-out/.graphify_update.failcount 2>/dev/null || true; }
      case "$count" in (*[!0-9]*|"") count=0 ;; esac
      count=$((count + 1))
      printf "%s %s\n" "$count" "$(date +%s)" > graphify-out/.graphify_update.failcount 2>/dev/null
    fi
    rm -rf graphify-out/.graphify_update.lock 2>/dev/null
  ' >/dev/null 2>&1 </dev/null &
  echo $! > "$LOCK/pid" 2>/dev/null
fi
```

**`.git/hooks/post-merge`** (fires after `git pull` / `git merge`):

```sh

# >>> graphify auto-refresh (installed by /graphify-install) >>>
if [ -f graphify-out/graph.json ] && [ -f graphify-out/manifest.json ] && command -v graphify >/dev/null 2>&1; then
<REFRESH_BLOCK>
fi
# <<< graphify auto-refresh <<<
```

**`.git/hooks/post-checkout`** (fires after `git checkout`/branch switch — git passes
`$3 = 1` for a branch checkout, `$3 = 0` for a plain file checkout; only act on the
former):

```sh

# >>> graphify auto-refresh (installed by /graphify-install) >>>
if [ "$3" = "1" ] && [ -f graphify-out/graph.json ] && [ -f graphify-out/manifest.json ] && command -v graphify >/dev/null 2>&1; then
<REFRESH_BLOCK>
fi
# <<< graphify auto-refresh <<<
```

After writing, `chmod +x` both files. Everything above uses only POSIX `sh` (no
bashisms) since an existing hook file may not have a bash shebang. `graphify update`
is incremental and AST-only for code changes (no LLM call), so this stays fast;
output is redirected to `graphify-out/.graphify_update.log` (already covered by the
`.graphify_*` gitignore glob from Step 4) so it never surfaces as noise. On success
it also stamps `graphify-out/.graphify_head`, which keeps the herow-core
`graphify-freshen.sh` UserPromptSubmit backstop quiet afterward (it only re-triggers
when its own stored HEAD is behind).

If `.git/hooks/` doesn't exist (unlikely, but possible in a bare or partial repo),
skip silently — don't fail the install.

---

## Step 7 — Offer commit & push

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
Do not run `git add`. Proceed to Step 8.

### If "No, just leave them staged"
Only do the selective stage (below), **without commit**. Proceed to Step 8.

### If committing (with or without push)

**Selective stage** — only add files that exist; never use `git add .`:

```bash
for f in .graphifyignore .gitignore graphify-out/graph.json graphify-out/GRAPH_REPORT.md graphify-out/graph.html graphify-out/.graphify_labels.json; do
  [ -e "$f" ] && git add "$f"
done
git status --short
```

**Commit** with a heredoc (no AI attribution — never add Co-Authored-By or any Claude reference):

```bash
git commit -m "$(cat <<'EOF'
chore: install graphify

- add .graphifyignore tuned for detected stack
- add graphify entries to .gitignore
- initial knowledge graph build
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

## Step 8 — Final summary

Print a short summary in English:

```
✓ graphify installed in <path>

Detected stacks: <list>
Files created/updated:
  - .graphifyignore
  - .gitignore (graphify block)
  - graphify-out/ (initial graph)
  - .git/hooks/post-merge, post-checkout (auto-refresh on pull/branch switch)

Commit: <SHA or "not created">
Push:   <done / no remote / skipped>

Next steps:
  /graphify query "<question about the repo>"
  /graphify .            # full rebuild
  /graphify --update     # incremental update
```

Keep the summary lean — don't repeat the whole pipeline. Only list a hook line if
it was actually installed (not skipped as already-present).
