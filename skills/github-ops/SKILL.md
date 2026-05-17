---
name: github-ops
description: GitHub/GitLab workflow operations via gh/glab CLI with token-efficient pipe-delimited output. Use when the user wants to commit, push, create/review/merge PRs or MRs, manage issues, check CI runs/checks, or inspect repo/releases. Auto-detects github.com vs gitlab.com and routes to gh or glab.
---

# github-ops

Use `gh` (GitHub) or `glab` (GitLab) for all remote operations. Use raw `git` only for local state (status, log, diff). Scripts auto-detect the platform from `origin` and return **pipe-delimited** output — 1 line per record, no colors, no labels you don't need.

## When to activate

User says: commit, push, create PR/MR, list PRs, merge, checks, CI status, open issue, close issue, comment, release, workflow run, repo info, "ship this", "is CI green?".

## Commands

| Intent | Command |
|---|---|
| Commit + push | `bash github-ops/scripts/ship.sh` |
| Same, custom msg | `bash github-ops/scripts/ship.sh --message "feat(x): y"` |
| Just suggest a message | `bash github-ops/scripts/commit-msg.sh` |
| Create PR | `bash github-ops/scripts/pr.sh create [--draft] [--title T]` |
| List PRs | `bash github-ops/scripts/pr.sh list [--state open\|closed\|all] [--mine]` |
| View PR | `bash github-ops/scripts/pr.sh view <num>` |
| PR checks | `bash github-ops/scripts/pr.sh checks <num>` |
| PR diff | `bash github-ops/scripts/pr.sh diff <num>` |
| Merge PR | `bash github-ops/scripts/pr.sh merge <num> [--squash\|--merge\|--rebase]` |
| Create issue | `bash github-ops/scripts/issue.sh create --title T [--body B\|--body-file F] [--label l1,l2]` |
| List issues | `bash github-ops/scripts/issue.sh list [--state open\|closed\|all] [--label L]` |
| View issue | `bash github-ops/scripts/issue.sh view <num>` |
| Close issue | `bash github-ops/scripts/issue.sh close <num>` |
| Comment issue | `bash github-ops/scripts/issue.sh comment <num> --body "..."` |
| Repo info | `bash github-ops/scripts/repo.sh info` |
| Releases | `bash github-ops/scripts/repo.sh releases [--limit N]` |
| CI runs | `bash github-ops/scripts/repo.sh runs [--limit N] [--workflow W]` |
| Dispatch workflow | `bash github-ops/scripts/repo.sh workflow-run <name> [--ref branch]` |

## Output format

All scripts emit pipe-delimited records, 1 per line.

- Data lines: `<type>|<field>|<field>|...` (e.g., `pr|42|open|fix bug|feature/x|2/3`).
- Errors (stderr, exit non-zero): `err|<code>|<detail>` (e.g., `err|missing-cli|gh`).
- Body content from `pr.sh view` and `issue.sh view` is truncated to 40 lines, with `...` appended if cut.

Example `pr.sh list`:
```
42|open|fix: cache invalidation|feature/cache|2/3
41|merged|feat: retry on 502|main|3/3
40|draft|wip: oauth|feature/oauth|-
```

Example `ship.sh` on a new branch:
```
branch|feature/x
staged|3
commit|abc1234|feat(api): add retry
push|origin/feature/x|new
pr-url|https://github.com/org/repo/pull/new/feature/x
```

## Rules

- **Never** call `git push`, `git commit`, `gh pr create`, etc. directly — use the scripts. They handle platform routing, secret detection, conventional-commit synthesis, and compact output.
- **Never** stage `.env`, `*.key`, `*.pem`, `*_rsa`, `*credentials*.json` — `ship.sh` blocks them; use `--force` only on explicit user request.
- Conventional Commits (auto-detected by `commit-msg.sh`): `feat`, `fix`, `refactor`, `docs`, `style`, `test`, `chore`, `perf`, `ci`. Subject ≤ 72 chars, imperative mood, no trailing period.
- For PRs: prefer `--squash` merges unless the user says otherwise.
- For destructive ops (force-push via `ship.sh --amend`, `pr.sh merge`, `issue.sh close`) — confirm with the user before running.
- If `detect_platform` returns `unknown` (e.g., self-hosted), the script exits with `err|unknown-platform|<url>`; ask the user which CLI to use.

## Platform support

- `github.com` → uses `gh`. Required: `gh auth login` done.
- `gitlab.com` / `gitlab.*` → uses `glab`. Required: `glab auth login` done.
- Anything else → manual fallback to `git` + curl, but flag it to the user first.
