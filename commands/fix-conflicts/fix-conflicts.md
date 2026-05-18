---
description: Resolve merge conflicts on a PR or branch by analyzing the commit history of both sides
argument-hint: [<PR-number-or-URL> | <branch-name>]
allowed-tools: Bash(git:*), Bash(gh:*), Bash(glab:*), Bash(grep:*), Read, Edit, Write, AskUserQuestion
---

# Resolve merge conflicts

Your task is to resolve merge conflicts **intelligently and with justification**, always grounding each decision in the commit history that produced each side of the conflict — never just the raw diff.

> **For any GitHub operation (`gh`, PRs, reviews, comments, status checks): always consult the `github-ops` skill** before executing. It defines the conventions, authentication, argument shapes, and error handling for this project. Load it before any `gh` call in this flow.

## Received argument

`$ARGUMENTS`

---

## Step 1 — Identify the target and the base branch

Inspect `$ARGUMENTS` and follow **one** of the three paths below.

### 1a. Argument is a PR (number, e.g. `123`, or URL `https://.../pull/123`)

> Before running any `gh`, load the **`github-ops`** skill and follow its conventions (authentication, default repo, required flags). The commands below are a skeleton — adapt them to whatever the skill prescribes.

1. `git fetch origin --prune`
2. `gh pr checkout <PR>` — switches to the PR branch.
3. Get the base branch from the PR itself (do not ask the user):
   `gh pr view <PR> --json baseRefName,headRefName -q '{base: .baseRefName, head: .headRefName}'`
4. Set `BASE=origin/<baseRefName>` and `HEAD_BRANCH=<headRefName>`.

### 1b. Argument is a branch name

1. `git fetch origin --prune`
2. `git checkout <branch>` (create tracking if needed).
3. **Ask for the base branch using the `AskUserQuestion` tool.**
   - To suggest relevant options, first run:
     `git for-each-ref --format='%(refname:short)' refs/remotes/origin | grep -E '/(main|master|develop|development|dev|staging|release)$' | sed 's|^origin/||' | sort -u`
   - Build the question with the discovered branches as options (mark the most likely one as `(Recommended)`) and always include an "Other (type)" option for free-form input.
4. Set `BASE=origin/<answer>`.

### 1c. Empty argument

1. Use the current branch: `HEAD_BRANCH=$(git rev-parse --abbrev-ref HEAD)`.
2. Ask for the base branch with `AskUserQuestion` (same logic as 1b).

---

## Step 2 — Pre-flight checks

1. Confirm a clean tree: `git status --porcelain`. If there are uncommitted changes, **stop** and ask the user what to do (stash, commit, or abort).
2. Make sure `$BASE` exists locally after the fetch: `git rev-parse --verify $BASE`.

---

## Step 3 — Attempt the merge

Run:

```
git merge $BASE --no-commit --no-ff
```

- If it completes **without conflicts**: tell the user, **do not commit**, and finish by letting them know the merge is ready for review and finalization.
- If conflicts appear: proceed to Step 4.

If the merge fails for any other reason (dirty tree, missing base, etc.), run `git merge --abort` and report the error to the user.

---

## Step 4 — Map the conflicts

1. List all conflicting files: `git diff --name-only --diff-filter=U`
2. Identify the common ancestor: `MERGE_BASE=$(git merge-base HEAD MERGE_HEAD)`
3. Show the user the list of files before starting to resolve, as a short table with: file, number of hunks (`grep -c '^<<<<<<<' <file>`), and apparent type (code, config, lock, doc).

---

## Step 5 — Resolve each file, one at a time

For **each conflicting file**:

### 5.1 Study the intent of both sides

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

### 5.2 Read the file with the conflict markers

Use the `Read` tool on the whole file. Locate each block:

```
<<<<<<< HEAD
... PR / current-branch version ...
=======
... base-branch version ...
>>>>>>> <base>
```

### 5.3 Decide the resolution

Use the history from 5.1 to classify each hunk:

| Situation | Resolution |
|---|---|
| Both sides changed **different and complementary** things (e.g. refactor on one side, new feature on the other) | Combine both. |
| One side **explicitly supersedes or reverts** the other's work (commit message makes it clear) | Keep the intentional side, drop the other. |
| Purely **stylistic/formatting** change vs. **semantic** change | Keep the semantics and reapply the formatting on top if needed. |
| **Imports**, dependency lists, alphabetical enums | Union both sets, preserving order. |
| **Lockfiles** (`package-lock.json`, `yarn.lock`, `Gemfile.lock`, `poetry.lock`, `pnpm-lock.yaml`) | Don't resolve by hand. Drop the conflict and regenerate with the proper package manager (`npm install`, `yarn`, `pnpm install`, etc.) after the merge. |
| Genuine doubt about intent even after reading the commits | Use **`AskUserQuestion`** with two (or three) clearly described alternatives, citing the commit hashes that back each side. |

### 5.4 Apply and validate

1. Apply the resolution with `Edit`, removing **all** `<<<<<<<`, `=======`, `>>>>>>>` markers.
2. Verify no marker is left: `grep -nE '^(<{7}|={7}|>{7})' <file>` should return empty.
3. Mark as resolved: `git add <file>`.
4. Record a **one-line** internal summary per hunk explaining the decision and the commits that backed it — you'll surface this in Step 6.

---

## Step 6 — Wrap-up

Once every file is `add`ed:

1. Run `git status` and confirm there are no more `Unmerged paths`.
2. Present the user with a per-file list:
   - What each side was trying to do (with commit hashes).
   - Which decision was made and why.
3. Suggest the user run the project's test/lint suite before finalizing.
4. **Do not commit or push automatically.** Show the final command they can run:
   ```
   git commit --no-edit     # keeps the default merge message
   ```
   or, if they want to edit the message:
   ```
   git merge --continue
   ```

---

## Important rules

- **Always fetch** before any comparison or merge.
- **Never discard code without reading** the commits that introduced it.
- **Never commit or push** without explicit user confirmation.
- If the merge state becomes inconsistent at any point, run `git merge --abort` and report.
- For genuinely ambiguous conflicts, **ask** with `AskUserQuestion` instead of guessing.
- **Any additional GitHub interaction** (posting a PR comment, updating status, marking ready for review, re-requesting review, etc.) must go through the **`github-ops`** skill — don't improvise `gh` flags by hand.