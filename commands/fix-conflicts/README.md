# /fix-conflicts

Resolve merge conflicts on a PR or branch by grounding every decision in the commit history of both sides — never in the raw diff alone.

## What it does

1. Identifies the target from `$ARGUMENTS`:
   - **PR number/URL** → `gh pr checkout`, reads base branch from the PR itself.
   - **Branch name** → checks it out and asks for the base branch via `AskUserQuestion` (suggesting `main`/`master`/`develop`/`staging`/`release` discovered from `origin`).
   - **Empty** → uses the current branch and asks for the base branch.
2. Pre-flight: refuses to proceed on a dirty tree; verifies the base ref exists locally after `git fetch --prune`.
3. Runs `git merge $BASE --no-commit --no-ff`. If it merges cleanly, stops and hands off to the user without committing.
4. On conflicts, lists every unmerged file with hunk count and type (code, config, lock, doc).
5. For each file, inspects the relevant commit history on both sides (`git log $MERGE_BASE..HEAD` and `$MERGE_BASE..MERGE_HEAD`), reads suspicious diffs with `git show`, then resolves each hunk using a decision table (complementary changes → combine; explicit supersede/revert → keep the intentional side; formatting vs. semantics → keep semantics; imports/enums → union; lockfiles → drop conflict and regenerate via the package manager; genuine doubt → `AskUserQuestion` with commit-backed alternatives).
6. Validates that no `<<<<<<<`/`=======`/`>>>>>>>` markers remain, stages each file, and records a one-line rationale per hunk.
7. Wraps up with a per-file summary (what each side wanted, decision made, commits cited) and suggests `git commit --no-edit` or `git merge --continue` — **never commits or pushes automatically**.

## Allowed tools

`Bash(git:*)`, `Bash(gh:*)`, `Bash(glab:*)`, `Bash(grep:*)`, `Read`, `Edit`, `Write`, `AskUserQuestion`.

## Language

English.

## When to use

- A PR is blocked by conflicts and you want resolutions justified by intent, not by guessing.
- Long-lived feature branch needs a careful merge from `main`/`develop`.
- Conflicts span multiple files and you need a structured, file-by-file walkthrough.

## Prerequisites

- Inside a git repository with the remote fetched (the command runs `git fetch origin --prune` itself).
- For the PR path: `gh` (or `glab`) authenticated against the host.
- The [`github-ops`](../../skills/github-ops/README.md) skill installed — every `gh`/`glab` interaction in this flow defers to it.

## Notes

- Never discards code without reading the commits that introduced it.
- Never commits, pushes, or posts PR updates without explicit user confirmation.
- On any inconsistent merge state, runs `git merge --abort` and reports back.
