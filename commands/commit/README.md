# /commit

Stage changes, run pre-commit checks, craft an emoji-enhanced Conventional Commit message, and commit via `github-ops`.

See [`commit.md`](./commit.md) for the full agent-facing procedure.

## What it does

1. Inspects staged/unstaged changes via `github-ops/inspect.sh`.
2. Optionally auto-stages all modified files if nothing is staged.
3. Runs pre-commit checks: lint (Biome, ESLint), type-check (tsc, mypy), fast tests — stops on failure.
4. Maps the change type to an emoji using the Conventional Commits taxonomy.
5. Asks for the commit type if not already clear from the diff or argument.
6. Detects mixed concerns and offers to split into separate commits.
7. Commits via `github-ops/ship.sh` — never calls `git commit` directly.

## Frontmatter

- **description**: Stage changes, craft a conventional commit message with emoji, and commit via github-ops.
- **argument-hint**: `[message] [--no-verify]`
- **allowed-tools**: Bash(git:*), Read, Glob, Grep, AskUserQuestion

## Usage

```
/commit
/commit fix(auth): handle expired token on refresh
/commit --no-verify
```

## Emoji convention

| Emoji | Type | Meaning |
|-------|------|---------|
| ✨ | `feat` | New feature |
| 🐛 | `fix` | Bug fix |
| 🚑️ | `hotfix` | Critical production fix |
| 📝 | `docs` | Documentation |
| ♻️ | `refactor` | Refactor (no behavior change) |
| ⚡️ | `perf` | Performance improvement |
| ✅ | `test` | Tests only |
| 🔧 | `chore` | Tooling, deps, config |
| 👷 | `ci` | CI/CD |
| 🎨 | `style` | Formatting |
| ⏪️ | `revert` | Revert |

## Relationship to github-ops

This command is a higher-level UX layer over `github-ops`:
- It handles pre-commit validation and emoji message crafting.
- `github-ops/ship.sh` performs the actual staging, committing, and pushing.
- For automated or CI flows, use `github-ops/ship.sh` directly.
- For human-driven commits with message guidance, use `/commit`.

## Prerequisites

- The `github-ops` skill must be installed (`~/.claude/skills/github-ops/`).
- Inside a git repository with at least one modified file.
