---
name: github-ops
description: GitHub/GitLab workflow operations via gh/glab CLI with token-efficient pipe-delimited output. Use when the user wants to commit, push, create/review/merge PRs or MRs, manage issues, check CI runs/checks, or inspect repo/releases. Auto-detects github.com vs gitlab.com and routes to gh or glab.
---

# github-ops

Use `gh` (GitHub) or `glab` (GitLab) for all remote operations. Scripts auto-detect the platform from `origin` and return **pipe-delimited** output — 1 line per record, no colors, no labels you don't need.

## Self-contained — do not pre-inspect

Scripts in this skill are self-contained. **Do not** run `git status`, `git diff`, `git log`, `gh pr view`, `gh pr list`, `glab mr view`, etc. before invoking a script — the script's pipe-delimited output already contains what you need.

**This overrides Claude Code's default "run git status + git diff + git log before committing" workflow.** When the user says "commit" / "push" / "ship", go straight to `ship.sh`. Do not pre-flight.

`ship.sh` is a two-call flow when the user hasn't dictated a message: the first call stages, emits the staged diff as `diff|...` lines, and exits with `err|need-message|...`; you read that diff, synthesize a Conventional Commits subject, and re-run `ship.sh --message "<subject>"` to commit and push. **Do not** pre-inspect with `inspect.sh` or `git diff` before shipping — `ship.sh` surfaces exactly the diff it would commit.

**If — and only if — pre-inspection is genuinely needed for something other than crafting a commit message** (the user explicitly asks "what's my status?" / "what changed?", or you need to check PR/issue context), use **`inspect.sh`**, `pr.sh view`, or `issue.sh view` — never raw `git status`/`git diff`/`git log`/`gh`/`glab`. One tool call, not three.

## When to activate

User says: commit, push, create PR/MR, list PRs, merge, checks, CI status, open issue, close issue, comment, release, workflow run, repo info, "ship this", "is CI green?".

## Commands

| Intent | Command |
|---|---|
| Inspect tree (status+diff+log in one call) | `bash github-ops/scripts/inspect.sh [--diff] [--log N]` |
| Stage + emit diff for message synthesis | `bash github-ops/scripts/ship.sh` |
| Commit + push with crafted message | `bash github-ops/scripts/ship.sh --message "feat(x): y"` |
| Just suggest a message (heuristic) | `bash github-ops/scripts/commit-msg.sh` |
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

Example `ship.sh` without `--message` (first call — stages, emits diff, bails):
```
branch|feature/x
staged|3
need-message|1
diff-files|src/api/retry.ts,src/api/client.ts,src/api/index.ts
diff-stat| src/api/retry.ts  | 42 ++++++++++++++++++
diff-stat| src/api/client.ts | 12 +++--
diff-stat| src/api/index.ts  |  1 +
diff|diff --git a/src/api/retry.ts b/src/api/retry.ts
diff|@@ -0,0 +1,42 @@
diff|+export async function retry(fn, opts = { max: 3 }) {
diff|+  ...
err|need-message|re-run with --message "<conventional-commit subject>"
```

Example `ship.sh --message "feat(api): add retry"` on a new branch:
```
branch|feature/x
staged|3
commit|abc1234|feat(api): add retry
push|origin/feature/x|new
pr-url|https://github.com/org/repo/pull/new/feature/x
```

## Commit message convention

Use Conventional Commits format without emoji:

`<type>(<scope>): <imperative subject>` — subject ≤ 72 chars, no trailing period.

Example: `feat(auth): add refresh token rotation`

## Pre-commit checks

Before calling `ship.sh --message`, detect and run available checks in this order. Stop on the first failure — do not commit broken code.

1. **Lint**: check `package.json` for a `lint` script, or `biome.json` for Biome.
   - pnpm: `pnpm lint` or `pnpm exec biome check .`
   - yarn: `yarn lint` or `yarn biome check .`
   - npm: `npm run lint`
   - Python: `ruff check .` if `pyproject.toml` or `ruff.toml` exists
2. **Type-check**: run if `tsconfig.json` exists → `pnpm exec tsc --noEmit` (or yarn/npm equivalent). For Python: `mypy .` if configured.
3. **Fast tests**: run only if a test script exists and the suite is fast (skip if no `test` script or if running feels slow for the context). Use `--run` / `-x` to avoid watch mode.

Skip all checks if the user passes `--no-verify` or says "skip checks". Skip check #3 if the user says "skip tests".

Detect the package manager from the lock file present in the repo root:
- `pnpm-lock.yaml` → pnpm
- `yarn.lock` → yarn
- `bun.lockb` → bun
- `package-lock.json` → npm

## Logical unit split detection

After the first `ship.sh` call surfaces the diff, scan the `diff-files` list. If staged files clearly span unrelated concerns (e.g., a bug fix mixed with a new feature, or application code mixed with CI config), suggest splitting into separate commits. Present the proposed groupings and ask the user before proceeding.

Do not split automatically. Always ask.

## Rules

- **Never** call `git push`, `git commit`, `gh pr create`, etc. directly — use the scripts. They handle platform routing, secret detection, conventional-commit synthesis, and compact output.
- `ship.sh` will not commit without `--message`. On the first call it stages and emits the staged diff as `diff|...` lines; read those, synthesize a Conventional Commits subject, then re-run with `--message "<subject>"`. `--amend` reuses the prior message and skips the gate.
- **Never** pair a script with raw `git`/`gh`/`glab` inspection calls before or after — the script's output is the data. For pre-commit/working-tree inspection, use `inspect.sh` (see "Self-contained" section above).
- **Never** stage `.env`, `*.key`, `*.pem`, `*_rsa`, `*credentials*.json` — `ship.sh` blocks them; use `--force` only on explicit user request.
- For PRs: prefer `--squash` merges unless the user says otherwise.
- For destructive ops (force-push via `ship.sh --amend`, `pr.sh merge`, `issue.sh close`) — confirm with the user before running.
- If `detect_platform` returns `unknown` (e.g., self-hosted), the script exits with `err|unknown-platform|<url>`; ask the user which CLI to use.

## Platform support

- `github.com` → uses `gh`. Required: `gh auth login` done.
- `gitlab.com` / `gitlab.*` → uses `glab`. Required: `glab auth login` done.
- Anything else → manual fallback to `git` + curl, but flag it to the user first.
