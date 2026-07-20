---
description: (herow) Resolve merge conflicts on a PR or branch by analyzing the commit history of both sides
argument-hint: [<PR-number-or-URL> | <branch-name>]
allowed-tools: Bash(git:*), Bash(gh:*), Bash(glab:*), Bash(grep:*), Read, Edit, Write, AskUserQuestion
effort: medium
---

# Resolve merge conflicts

Your task is to resolve merge conflicts **intelligently and with justification**, always grounding each decision in the commit history that produced each side of the conflict — never just the raw diff. Resolution happens in an **isolated git worktree** (see Step 2) and, once the pre-push validation gate is green, the branch is **committed and pushed automatically** — no manual confirmation before pushing.

> **For any GitHub operation (`gh`, PRs, reviews, comments, status checks): always consult the `github-ops` skill** before executing. It defines the conventions, authentication, argument shapes, and error handling for this project. Load it before any `gh` call in this flow.

> **Recommended subagents (when installed):** after resolution, delegate to `code-reviewer` to verify each merged hunk preserves intent on both sides; if a resolution introduces logic that fails at runtime, delegate the diagnosis to `debugger` (writes a regression test before fixing). Invoke via the `Agent` tool with the matching `subagent_type`. If the agent file is not present at `~/.claude/agents/<name>.md`, execute the steps below directly.

## Received argument

`$ARGUMENTS`

---

## Step 0 — Freshen remote refs

Run `git fetch origin --prune` in the **primary tree** before anything else. This updates all remote-tracking refs (`origin/<base>`, `origin/<head>`, …) without touching the primary tree's checked-out branch — do **not** run `git pull` or `git checkout` here. Every `$BASE`/`$HEAD_BRANCH` reference below is resolved against these fresh `origin/*` refs.

---

## Step 1 — Identify the target and the base branch

Inspect `$ARGUMENTS` and follow **one** of the three paths below. None of them touch the primary tree's checkout — they only determine which refs to use and, for 1a/1b, which branch the worktree in Step 2 will be built from.

### 1a. Argument is a PR (number, e.g. `123`, or URL `https://.../pull/123`)

> Before running any `gh`, load the **`github-ops`** skill and follow its conventions (authentication, default repo, required flags). The commands below are a skeleton — adapt them to whatever the skill prescribes.

1. Get the base and head branch from the PR itself (do not ask the user):
   `gh pr view <PR> --json baseRefName,headRefName -q '{base: .baseRefName, head: .headRefName}'`
2. Set `BASE=origin/<baseRefName>` and `HEAD_BRANCH=<headRefName>`.
3. Slug: `pr-<number>`.

### 1b. Argument is a branch name

1. **Ask for the base branch using the `AskUserQuestion` tool.**
   - To suggest relevant options, first run:
     `git for-each-ref --format='%(refname:short)' refs/remotes/origin | grep -E '/(main|master|develop|development|dev|staging|release)$' | sed 's|^origin/||' | sort -u`
   - Build the question with the discovered branches as options (mark the most likely one as `(Recommended)`) and always include an "Other (type)" option for free-form input.
2. Set `BASE=origin/<answer>` and `HEAD_BRANCH=<branch>`.
3. Slug: the branch name, kebab-cased (lowercase, `[a-z0-9-]` only, max 40 chars) — same sanitization style as the plan slug in `blueprint.md`.

### 1c. Empty argument

1. Use the current branch: `HEAD_BRANCH=$(git rev-parse --abbrev-ref HEAD)`.
2. Ask for the base branch with `AskUserQuestion` (same logic as 1b).
3. Set `BASE=origin/<answer>`.
4. This is the **in-place case** — see Step 2's special case. No slug needed.

---

## Step 2 — Worktree isolation

All resolution work (merge attempt, conflict mapping, per-file resolution, the pre-push gate) happens in a **dedicated git worktree** at `.claude/worktree/<slug>`, following the same convention as `execute.md`'s "Worktree isolation" section — never invent a new pattern.

1. **Ensure `.claude/worktree/` is in the global `.gitignore`** (add the line if missing) — the worktree isn't versioned.
2. **Special case — 1c (empty argument, current branch):** git refuses to check out a branch that's already checked out in another worktree, including the primary tree the command is running from. Since `HEAD_BRANCH` here **is** the primary tree's current branch, **skip worktree creation** and resolve in place instead. Log this clearly: "resolving in place — no isolation needed, already on target branch." All subsequent steps run in the primary tree for this case, and Step 7's worktree-removal step is skipped.
3. **1a/1b (PR or explicit branch) — create the worktree from the fresh remote ref:**
   - If `HEAD_BRANCH` doesn't exist locally:
     `git worktree add .claude/worktree/<slug> -b <HEAD_BRANCH> origin/<HEAD_BRANCH>`
   - If it exists locally and is not checked out elsewhere:
     `git worktree add .claude/worktree/<slug> <HEAD_BRANCH>`
   - If the branch is checked out somewhere else unexpectedly, **stop** and warn — another execution may be in progress (same guard `execute.md` uses).
   - This never touches the primary tree's checkout.
4. **`cd` into `.claude/worktree/<slug>`** (or stay in the primary tree for the 1c in-place case) and do all remaining work there — merge attempt, conflict mapping, per-file resolution, gate.

---

## Step 3 — Pre-flight checks

1. Confirm a clean tree: `git status --porcelain`. If there are uncommitted changes, **stop** and ask the user what to do (stash, commit, or abort). In the worktree case this should already be clean since it was just created; this mainly matters for the 1c in-place case.
2. Make sure `$BASE` exists after the fetch: `git rev-parse --verify $BASE`.

---

## Step 4 — Attempt the merge

Run (inside the worktree, or in place for the 1c case):

```
git merge $BASE --no-commit --no-ff
```

- If it completes **without conflicts**: tell the user, **do not commit**, and finish by letting them know the merge is ready for review and finalization.
- If conflicts appear: proceed to Step 5.

If the merge fails for any other reason (dirty tree, missing base, etc.), run `git merge --abort` and report the error to the user.

---

## Step 5 — Map the conflicts

1. List all conflicting files: `git diff --name-only --diff-filter=U`
2. Identify the common ancestor: `MERGE_BASE=$(git merge-base HEAD MERGE_HEAD)`
3. Show the user the list of files before starting to resolve, as a short table with: file, number of hunks (`grep -c '^<<<<<<<' <file>`), and apparent type (code, config, lock, doc).

---

## Step 6 — Resolve each file, one at a time

For **each conflicting file**:

### 6.1 Study the intent of both sides

Do not look only at the conflicting lines — read the **purpose** of the commits that touched the file since the common ancestor:

```
# Commits on the HEAD side (your branch / PR)
git log --no-merges --pretty=format:'%h %s' $MERGE_BASE..HEAD -- <file>

# Commits on the base side
git log --no-merges --pretty=format:'%h %s' $MERGE_BASE..MERGE_HEAD -- <file>
```

For commits that look relevant to the conflicting lines (especially those mentioning refactor, fix, rename, revert, or touching the same functions), inspect the diff:

```
git show <hash> -- <file>
```

If one side has many commits, focus on the most recent ones and those that directly touch the conflicting lines (`git log -L`).

### 6.2 Read the file with the conflict markers

Use the `Read` tool on the whole file. Locate each block:

```
<<<<<<< HEAD
... PR / current-branch version ...
=======
... base-branch version ...
>>>>>>> <base>
```

### 6.3 Decide the resolution

Use the history from 6.1 to classify each hunk:

| Situation | Resolution |
|---|---|
| Both sides changed **different and complementary** things (e.g. refactor on one side, new feature on the other) | Combine both. |
| One side **explicitly supersedes or reverts** the other's work (commit message makes it clear) | Keep the intentional side, drop the other. |
| Purely **stylistic/formatting** change vs. **semantic** change | Keep the semantics and reapply the formatting on top if needed. |
| **Imports**, dependency lists, alphabetical enums | Union both sets, preserving order. |
| **Lockfiles** (`package-lock.json`, `yarn.lock`, `Gemfile.lock`, `poetry.lock`, `pnpm-lock.yaml`) | Don't resolve by hand. Drop the conflict and regenerate with the proper package manager (`npm install`, `yarn`, `pnpm install`, etc.) after the merge. |
| Genuine doubt about intent even after reading the commits | Use **`AskUserQuestion`** with two (or three) clearly described alternatives, citing the commit hashes that back each side. |

### 6.4 Apply and validate

1. Apply the resolution with `Edit`, removing **all** `<<<<<<<`, `=======`, `>>>>>>>` markers.
2. Verify no marker is left: `grep -nE '^(<{7}|={7}|>{7})' <file>` should return empty.
3. Mark as resolved: `git add <file>`.
4. Record a **one-line** internal summary per hunk explaining the decision and the commits that backed it — you'll surface this in Step 7.

---

## Step 7 — Wrap-up

Once every file is `add`ed:

1. Run `git status` and confirm there are no more `Unmerged paths`.
2. **Regenerate any lockfiles first** (per the 6.3 rule) — run the package manager
   (`npm install`, `pnpm install`, `yarn`, `poetry lock`, …) so the tree is consistent before
   the gate runs.
3. **Pre-push validation gate (mandatory).** Run the pre-push validation gate before pushing —
   the merged tree must be **100% green**. Canonical steps + anti-cheat rules:
   `${CLAUDE_PLUGIN_ROOT}/reference/pre-push-gate.md`. This command has `Edit`/`Write`, so run
   the **full fix-loop** — detect the stack's commands and run, in order, the steps that exist:
   - **Lint with auto-fix** (`eslint --fix`, `biome check --write`, `ruff --fix`) → **Type-check**
     if present (`tsc --noEmit`, `mypy`) → **Tests** (`vitest run`, `pytest`, …) → **Build**
     (`next build`, `vite build`, …).
   - Each existing step must pass 100% (skip + log absent ones — never fake green with
     `--passWithNoTests`). Fix failures — including ones the merge surfaced in untouched files —
     and re-run (max 3 cycles per step).
   - **Anti-cheat (load-bearing):** fix the real problem — **never** skip/delete/disable tests,
     append `|| true`, add blanket `eslint-disable`/`# type: ignore`/`@ts-nocheck`, or push with
     `--no-verify`. If the gate can't be made honestly green in ≤3 cycles per step, **STOP** and
     report which step is stuck — do not commit or push.
4. **Stage the gate's changes into the merge.** The regenerated lockfiles (7.2) and the gate's
   auto-fixes (7.3) are edited *after* the last `git add`, so they sit in the working tree
   **unstaged** — a plain `git commit --no-edit` would commit the merged index without them and
   silently discard the green you just achieved. Stage them first: `git add -A` (then re-confirm
   `git status` is clean of unstaged changes).
5. **Commit and push automatically** — no confirmation prompt, once the gate is green:
   ```
   git commit --no-edit     # keeps the default merge message
   git push                 # add -u if the branch has no upstream yet
   ```
   If `git push` is rejected because the remote advanced, `git fetch` + retry the push once;
   if it still fails, **stop and report** — never force-push.
6. **After a successful push, clean up the worktree** (skip this for the 1c in-place case,
   which never created one): return to the primary tree (`cd` back to the repo root) and
   `git worktree remove .claude/worktree/<slug>` — matching `execute.md`'s "only remove after
   success" rule. Never remove on failure; leave it for inspection.
7. Present the user with a per-file list:
   - What each side was trying to do (with commit hashes).
   - Which decision was made and why.

---

## Important rules

- **Always fetch** (Step 0) before any comparison or merge — never rely on a stale local checkout.
- **Never discard code without reading** the commits that introduced it.
- **Commit and push automatically once the pre-push validation gate is green** — no manual confirmation step. Never push a red gate; if the gate can't be made green within the retry budget, stop and report instead of pushing.
- If the merge state becomes inconsistent at any point, run `git merge --abort` and report.
- For genuinely ambiguous conflicts, **ask** with `AskUserQuestion` instead of guessing.
- **Any additional GitHub interaction** (posting a PR comment, updating status, marking ready for review, re-requesting review, etc.) must go through the **`github-ops`** skill — don't improvise `gh` flags by hand.

## Recommended subagents

These subagents ship with the herow-dev plugin and sharpen the output when installed. The command works without them.

- **[`code-reviewer`](../../agents/code-reviewer.md)** — after every conflict file is resolved, before commit. Audits whether the union/picked-side preserved each side's intent, flags accidental semantic loss, and verifies no marker leaked.
- **[`debugger`](../../agents/debugger.md)** — if tests fail after merge or the resolved code misbehaves at runtime. Runs root-cause analysis grounded in the merge history (not a fix-first reflex).

Each is optional. If none are installed, run the steps above inline.
