# github-ops

A consolidated skill for GitHub/GitLab operations via `gh`/`glab` with **pipe-delimited** output — optimized for AI agent consumption (fewer tokens, less parsing).

## Making it used system-wide

Add the following on `~/.claude/CLAUDE.md`:

```markdown
# github-ops
Invoke the `github-ops` skill before any `git`/`gh`/`glab` operation: commit, push, status, diff, log, PR/MR ops, issue ops, repo/release/CI inspection.

Do not pre-inspect. Scripts are self-contained — never run `git status`/`diff`/`log` or `gh pr view` before them. Overrides the default "git status + diff + log before commit" workflow: go straight to `ship.sh`. If you truly need inspection, call `inspect.sh` (one tool call, not three).
```

## Why it exists

Agents that run `gh pr list` or `git push` directly get verbose output (ANSI colors, headers, prose) and burn tokens re-reading it. This skill:

- Detects the platform (`github.com` → `gh`, `gitlab.com` → `glab`) and routes automatically.
- Returns **1 line per record**, fields separated by `|`, no colors, no redundant labels.
- Blocks accidental commits of `.env`, `*.key`, `*.pem`, `*_rsa`, `*credentials*.json`.
- Synthesizes Conventional Commit messages from the diff.
- Runs pre-commit checks (lint, type-check, fast tests) before committing.
- Detects mixed concerns in a staged diff and suggests splitting into separate commits.
- Generates PR bodies from `git log` + `git diff --stat` when you don't pass one.


## Prerequisites

```bash
gh auth login           # for GitHub
glab auth login         # for GitLab
```

## Structure

```
github-ops/
├── SKILL.md
└── scripts/
    ├── _common.sh        # shared helpers (sourced)
    ├── inspect.sh        # status + diff + log in one compact call
    ├── ship.sh           # commit + push
    ├── commit-msg.sh     # suggest message only
    ├── pr.sh             # create | list | view | merge | checks | diff
    ├── issue.sh          # create | list | view | close | comment
    └── repo.sh           # info | releases | runs | workflow-run
```

## Output format

| Type | Pattern | Example |
|---|---|---|
| Data | `<type>\|<f1>\|<f2>...` | `pr\|42\|open\|fix: cache\|feature/x\|2/3` |
| Error (stderr) | `err\|<code>\|<detail>` | `err\|missing-cli\|gh` |
| Truncated marker | `<label>\|... +N more lines` | `diff\|... +312 more lines` |
| Full-output pointer | `full\|<path>` | `full\|/tmp/github-ops-tee/pr-3-diff.txt` |
| Token savings | `saved\|<orig>→<inline> tokens (~P%)` | `saved\|1840→210 tokens (~88%)` |

### Tee pattern — nothing is discarded

Long output (`ship.sh` diff, `pr.sh view` body, `pr.sh diff`, `issue.sh view` comments, `repo.sh runs --log`) is shown inline up to a cap. The **complete** content is always written to the `full|` file under `${TMPDIR:-/tmp}/github-ops-tee/` with a deterministic name (re-runs overwrite). Read that file only when the inline preview isn't enough. This mirrors RTK's compress-inline / preserve-on-disk approach, so token cost stays low without losing data.

### Failure-focus on CI

- `pr.sh checks <num>` → `checks|<ok>/<total>` summary, then only the non-passing checks; full list in `full|`.
- `repo.sh runs` → failures listed first.
- `repo.sh runs --log <id>` → only the failed steps of a run, compacted via the tee pattern.

---

## Examples

### `inspect.sh` — status + diff + log in one call

Use when you'd otherwise reach for `git status` + `git diff` + `git log`. Three tool calls collapse into one, with stable pipe-delimited fields.

```bash
$ bash github-ops/scripts/inspect.sh --diff --log 5
branch|feature/retry|dirty|ahead 2|behind 0
remote|origin/feature/retry
staged|1
unstaged|2
untracked|0
file|M.|src/api/retry.ts
file|.M|src/api/client.ts
file|.M|README.md
diff-stat|3 files changed, 47 insertions(+), 12 deletions(-)
log|abc1234|feat(api): retry on 502
log|de23a91|fix(auth): expired refresh token
log|...|...
```

Fields: `file|<porcelain-status>|<path>` (dots replace spaces in status so columns are stable). Capped at 50 files. Omit `--diff` to skip the shortstat; pass `--log N` to change recent-commit count (default 3).

---

### `ship.sh` — commit + push

**Auto-generated message (from the diff)**
```bash
$ bash github-ops/scripts/ship.sh
branch|feature/retry
staged|3
commit|abc1234|feat(api): update 3 files
push|origin/feature/retry|new
pr-url|https://github.com/org/repo/pull/new/feature/retry
```

**Custom message**
```bash
$ bash github-ops/scripts/ship.sh --message "fix(auth): handle expired refresh token"
branch|fix/auth
staged|2
commit|de23a91|fix(auth): handle expired refresh token
push|origin/fix/auth|existing
```

**Commit only, no push**
```bash
$ bash github-ops/scripts/ship.sh --no-push -m "wip: testing"
```

**Safe amend + force-push**
```bash
$ bash github-ops/scripts/ship.sh --amend -m "feat: corrected message"
```

**Error: secret detected**
```bash
$ echo "API_KEY=xxx" > .env && bash github-ops/scripts/ship.sh
err|secret-detected|use --force to override
```

---

### `commit-msg.sh` — suggest message only

```bash
$ git add src/api/retry.ts
$ bash github-ops/scripts/commit-msg.sh
feat|api|update retry.ts
```

Output is `type|scope|description`. Format it as `feat(api): update retry.ts` if you want.

---

### `pr.sh` — pull requests / merge requests

**Create PR (body generated from the diff)**
```bash
$ bash github-ops/scripts/pr.sh create
pr|142|https://github.com/org/repo/pull/142
```

**Create draft PR with custom title**
```bash
$ bash github-ops/scripts/pr.sh create --draft --title "WIP: oauth flow"
pr|143|https://github.com/org/repo/pull/143
```

**List open PRs**
```bash
$ bash github-ops/scripts/pr.sh list
42|open|fix: cache invalidation|feature/cache|2/3
41|open|feat: retry on 502|feature/retry|3/3
40|draft|wip: oauth|feature/oauth|-
```

Fields: `<num>|<state>|<title>|<branch>|<checks-ok>/<total>`.

**Only mine**
```bash
$ bash github-ops/scripts/pr.sh list --mine --state all
```

**View PR details**
```bash
$ bash github-ops/scripts/pr.sh view 42
pr|42|open|fix: cache invalidation
branch|feature/cache→main
author|judson
checks|2/3|test:success|lint:success|e2e:failure
body|## What
body|Fixes the cache invalidation race when two requests
body|hit the same key in <50ms window.
body|
body|## Testing
body|- [x] unit tests
body|- [x] reproduced manually
```

**Check CI status** (failure-focus — only non-passing checks inline)
```bash
$ bash github-ops/scripts/pr.sh checks 42
checks|2/3
check|e2e|failure|https://github.com/org/repo/actions/runs/125
full|/tmp/github-ops-tee/pr-42-checks.txt
```

**Raw PR diff**
```bash
$ bash github-ops/scripts/pr.sh diff 42
```

**Merge (squash by default)**
```bash
$ bash github-ops/scripts/pr.sh merge 42
merged|42|ef89b21

$ bash github-ops/scripts/pr.sh merge 42 --rebase
merged|42|ef89b21
```

---

### `issue.sh` — issues

**Create**
```bash
$ bash github-ops/scripts/issue.sh create \
    --title "Cache misses on cold start" \
    --body "Repro: restart pod, first 5 reqs miss." \
    --label bug,p1
issue|217|https://github.com/org/repo/issues/217
```

**With body from a file**
```bash
$ bash github-ops/scripts/issue.sh create --title "Spec" --body-file /tmp/spec.md
issue|218|https://github.com/org/repo/issues/218
```

**List**
```bash
$ bash github-ops/scripts/issue.sh list
217|open|bug,p1|Cache misses on cold start
215|open|bug|Auth race condition
210|open|-|Improve docs
```

Fields: `<num>|<state>|<labels>|<title>`.

**Filter by label**
```bash
$ bash github-ops/scripts/issue.sh list --label bug
```

**View**
```bash
$ bash github-ops/scripts/issue.sh view 217
issue|217|open|Cache misses on cold start
author|judson
labels|bug,p1
body|Repro: restart pod, first 5 reqs miss.
body|
body|Suspect the warmup hook isn't priming the LRU.
comment|alice|tried locally, can confirm
comment|bob|PR #218 should fix this
comment|judson|closing once #218 lands
```

**Comment**
```bash
$ bash github-ops/scripts/issue.sh comment 217 --body "Fixed in #218"
commented|217
```

**Close**
```bash
$ bash github-ops/scripts/issue.sh close 217
closed|217
```

---

### `repo.sh` — repository information

**Basic info**
```bash
$ bash github-ops/scripts/repo.sh info
name|org/repo
default-branch|main
visibility|private
merge-allowed|squash,rebase
```

**Latest releases**
```bash
$ bash github-ops/scripts/repo.sh releases --limit 5
v2.4.0|Retry hardening|2026-05-12T18:22:00Z|stable
v2.3.1|Patch: cache fix|2026-05-08T10:01:00Z|stable
v2.3.0|OAuth flow|2026-05-01T09:00:00Z|stable
v2.3.0-rc1|RC|2026-04-28T15:00:00Z|prerelease
v2.2.0|—|2026-04-15T12:00:00Z|stable
```

Fields: `<tag>|<name>|<published-at>|<draft|prerelease|stable>`.

**Recent CI runs** (failures listed first)
```bash
$ bash github-ops/scripts/repo.sh runs --limit 5
9920|completed|failure|feature/x|test
9921|completed|success|main|test
9919|in_progress|-|feature/y|test
9918|completed|success|main|deploy
9917|completed|success|main|test
```

Fields: `<run-id>|<status>|<conclusion>|<branch>|<workflow>`.

**Filter by workflow**
```bash
$ bash github-ops/scripts/repo.sh runs --workflow deploy --limit 3
```

**Failed steps of a run** (failure-focus — only the failing steps, full log to `full|`)
```bash
$ bash github-ops/scripts/repo.sh runs --log 9920
log|FAIL src/api/retry.test.ts > retries on 502
log|  AssertionError: expected 3 attempts, got 1
log|... +120 more lines
full|/tmp/github-ops-tee/run-9920-failed.txt
saved|640→90 tokens (~86%)
```

**Dispatch a workflow**
```bash
$ bash github-ops/scripts/repo.sh workflow-run deploy --ref main
run|9930|https://github.com/org/repo/actions/runs/9930
```

---

## Composed workflows

### Ship + open PR + check CI

```bash
$ bash github-ops/scripts/ship.sh -m "feat(api): add retry"
branch|feature/retry
staged|3
commit|abc1234|feat(api): add retry
push|origin/feature/retry|new
pr-url|https://github.com/org/repo/pull/new/feature/retry

$ bash github-ops/scripts/pr.sh create
pr|144|https://github.com/org/repo/pull/144

$ bash github-ops/scripts/pr.sh checks 144
test|in_progress|...
lint|success|...
```

### Triage PRs with failing CI

```bash
$ bash github-ops/scripts/pr.sh list --state open \
    | awk -F'|' '$5 ~ /^[0-9]+\/[0-9]+$/ && $5 != gensub(/\//,"\\&","g",$5) { split($5,a,"/"); if (a[1]<a[2]) print $1 }'
# prints numbers of PRs with failing checks
```

### How many open issues with the `bug` label

```bash
$ bash github-ops/scripts/issue.sh list --label bug | wc -l
```

---

## Common error codes

| Code | Meaning | How to resolve |
|---|---|---|
| `not-a-repo` | Directory is not a git repo | `cd` into a repo |
| `missing-cli` | `gh`/`glab` not installed | install and `auth login` |
| `unknown-platform` | Remote isn't GitHub or GitLab | use `git` manually |
| `nothing-to-commit` | No changes | do some work first |
| `nothing-staged` | Nothing in `git diff --cached` | `git add` something |
| `secret-detected` | `.env`/key in the list | review; `--force` if intentional |
| `same-branch` | Tried to create a PR from `main` into `main` | switch branches |
| `push-failed` | `git push` failed | check stderr |
| `create-failed` | `gh pr create` failed | check stderr |
| `merge-failed` | merge rejected | check branch protections |
| `dispatch-failed` | workflow doesn't exist | verify `--workflow` |
| `bad-arg` / `bad-sub` | unknown flag | check usage |

---

## Commit conventions

Commits follow Conventional Commits format without emoji:

`<type>(<scope>): <imperative subject>` — subject ≤ 72 chars, no trailing period.

### Type auto-detection (`commit-msg.sh`)

| Type | Trigger |
|------|---------|
| `docs` | Only `.md/.mdx/.txt/.rst/.adoc` files |
| `test` | Paths containing `test/`, `tests/`, `__tests__/`, `spec/`, `.test.`, `.spec.` |
| `chore` | `package.json`, lockfiles, `Cargo.toml`, `go.mod`, `Gemfile` |
| `ci` | `.github/workflows/`, `.gitlab-ci.yml`, `Dockerfile`, `.circleci/` |
| `fix` | Diff contains `+…fix\|bug\|hotfix\|patch` |
| `refactor` | Diff contains `+…refactor\|rename\|extract\|inline` |
| `perf` | Diff contains `+…perf\|performance\|optimize` |
| `feat` | Fallback |

Scope = the top-level directory most common among staged files (ignoring `node_modules`, `dist`, `build`, `vendor`).

### Pre-commit checks

Checks are scoped to what actually changed — no full test battery on small commits.

The staged file list is classified into: `code`, `config`, `ci`, `docs`, `deps`, `assets`. Then:

| Change type | Lint | Type-check | Tests |
|-------------|------|------------|-------|
| code | ✅ staged files only | ✅ whole project (incremental) | ✅ targeted test files |
| code + config | ✅ staged files only | ✅ whole project (incremental) | ✅ targeted test files |
| config / ci only | ✅ staged files only | ❌ | ❌ |
| deps / docs / assets | ❌ | ❌ | ❌ |

**Targeted tests**: derives the test file from the staged source file (`src/foo.ts` → `src/foo.test.ts`), runs only that file. Falls back to the full suite only when ≥ 10 source files changed or a shared core module is touched. Pass `--no-verify` to skip all checks, or `--skip-tests` to skip #3.

### Split detection

After staging, if the diff spans unrelated concerns (e.g., a bug fix + a new feature), the skill surfaces the groups and asks the user whether to split into separate commits before proceeding.

---

## When NOT to use this skill

- `git blame`, bisect, interactive rebase, conflict resolution — flows that require human decisions.
- Self-hosted repos (Gitea, Forgejo, Bitbucket) — `detect_platform` returns `unknown` and the skill bails; use the native CLI.

For pre-commit/working-tree inspection (`git status` / `git diff` / `git log`), **do** use this skill — call `inspect.sh` instead of the three raw git commands. One tool call, stable output, no ANSI noise.
