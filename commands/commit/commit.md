---
description: Stage changes, craft a conventional commit message with emoji, and commit via github-ops.
argument-hint: "[message] [--no-verify]"
allowed-tools: Bash(git:*), Read, Glob, Grep, AskUserQuestion
---

# Commit

Stage, validate, and commit the current changes using emoji-enhanced Conventional Commits. All git operations go through the `github-ops` skill.

> **Always load the `github-ops` skill before running any git command.** It defines the conventions, authentication, and error handling for this project.

## Step 1 — Detect staged changes

Invoke `github-ops`:

```bash
bash github-ops/scripts/inspect.sh --diff
```

Parse the output:
- `staged|<n>` — number of staged files.
- `unstaged|<n>` — number of unstaged tracked files.
- `untracked|<n>` — untracked files.

If `staged` is 0:
- Ask via `AskUserQuestion` whether to stage all modified files or let the user stage manually.
- If the user approves auto-staging: the `ship.sh` first call handles it.

## Step 2 — Run pre-commit checks (unless `--no-verify` in `$ARGUMENTS`)

Detect available scripts and run in order, stopping on first failure:

1. **Lint**: check `package.json` for `lint` script → `pnpm lint` / `yarn lint` / `npm run lint`. Or `biome check .` if Biome is configured.
2. **Type-check**: `pnpm exec tsc --noEmit` / `yarn tsc --noEmit` if `tsconfig.json` exists. Or `mypy .` for Python.
3. **Tests (fast only)**: `pnpm test --run` / `pytest -x -q` — skip if there is no `test` script.

If any check fails, report the failure and **stop**. Do not commit broken code.

## Step 3 — Determine the commit type

If `$ARGUMENTS` contains a message, parse it for a Conventional Commits prefix and map to an emoji:

| Type | Emoji | When to use |
|------|-------|-------------|
| `feat` | ✨ | New feature |
| `fix` | 🐛 | Bug fix |
| `hotfix` | 🚑️ | Critical production fix |
| `docs` | 📝 | Documentation only |
| `refactor` | ♻️ | Code change, no behavior change |
| `perf` | ⚡️ | Performance improvement |
| `test` | ✅ | Tests only |
| `chore` | 🔧 | Tooling, deps, config |
| `ci` | 👷 | CI/CD changes |
| `style` | 🎨 | Formatting, whitespace |
| `revert` | ⏪️ | Revert a prior commit |

If no prefix is detected, ask via `AskUserQuestion` which type best describes the change.

## Step 4 — Check for logical unit split

If `inspect.sh` shows changes across unrelated concerns (e.g., a bug fix mixed with a refactor), ask:

> "These changes seem to cover multiple concerns. Should I split into separate commits?"

Options: A) Yes, guide me through splitting; B) No, commit everything together.

## Step 5 — Craft the commit message

Build the final message:
```
<emoji> <type>(<scope>): <imperative subject>
```

Rules:
- Subject ≤ 72 characters, imperative mood, no trailing period.
- Scope: the primary package, module, or directory (optional but preferred).
- If `$ARGUMENTS` already contains a full message, use it as-is (after adding emoji if missing).

## Step 6 — Commit via github-ops

Call `ship.sh` with the crafted message:

```bash
bash github-ops/scripts/ship.sh --message "<emoji> <type>(<scope>): <subject>"
```

Parse the output:
- `commit|<hash>|<message>` → success, show hash and message.
- `push|origin/<branch>|new` → new branch pushed, show PR URL if present.
- `err|*` → report error, do not retry without user confirmation.

## Step 7 — Report

Show the user:
- Commit hash and message.
- Files committed.
- Whether a push happened and the branch status.
- Next suggested action (open PR, push if not pushed, etc.).
