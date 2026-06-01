---
name: github-ops
description: GitHub/GitLab workflow operations via gh/glab CLI with token-efficient pipe-delimited output. Use when the user wants to commit, push, create/review/merge PRs or MRs, manage issues, check CI runs/checks, or inspect repo/releases. Auto-detects github.com vs gitlab.com and routes to gh or glab.
---

# github-ops

> **Recommended subagent (when installed):** before crafting the commit message in `ship.sh`'s two-call flow — or before opening a PR — optionally delegate the staged diff to `code-reviewer` for a security/correctness/performance pass. Invoke via the `Agent` tool with `subagent_type: code-reviewer`. If `~/.claude/agents/code-reviewer.md` is not present, skip the delegation and continue with the standard flow below.

Use `gh` (GitHub) or `glab` (GitLab) for all remote operations. Scripts auto-detect the platform from `origin` and return **pipe-delimited** output — 1 line per record, no colors, no labels you don't need.

## NEVER add AI attribution

**Never, under any circumstance, add `Co-Authored-By: Claude`, `🤖 Generated with Claude Code`, or any similar AI-attribution line to a commit message or a PR/MR body.** Do not append it yourself when crafting `--message` or `--body`. The scripts strip these lines defensively and the `git-guard` hook hard-denies any raw `git`/`gh`/`glab` command that contains them — but the rule is yours to follow first: write clean commit subjects and PR bodies with no attribution footer.

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
| Create PR | `bash github-ops/scripts/pr.sh create [--draft] [--title T] [--body B\|--body-file F]` |
| Edit PR | `bash github-ops/scripts/pr.sh edit <num> [--title T] [--body B\|--body-file F] [--add-label L] [--remove-label L]` |
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
| Failed steps of a run | `bash github-ops/scripts/repo.sh runs --log <id>` |
| Dispatch workflow | `bash github-ops/scripts/repo.sh workflow-run <name> [--ref branch]` |

## Output format

All scripts emit pipe-delimited records, 1 per line.

- Data lines: `<type>|<field>|<field>|...` (e.g., `pr|42|open|fix bug|feature/x|2/3`).
- Errors (stderr, exit non-zero): `err|<code>|<detail>` (e.g., `err|missing-cli|gh`).

### Tee pattern — long output is compacted, never lost

Long output (`ship.sh` diff, `pr.sh view` body, `pr.sh diff`, `issue.sh view` comment thread, `repo.sh runs --log`) is shown inline up to a cap, but the **complete** content is always written to a file. When truncated, the script appends:

```
<label>|... +N more lines
full|/tmp/github-ops-tee/<context>.txt
saved|<orig>→<inline> tokens (~P%)
```

- `full|<path>` — the entire untruncated output. **Read this file only if the inline preview isn't enough** (e.g., you need a hunk past the cap, or a full PR body). Files use deterministic names, so a re-run overwrites rather than piling up.
- `saved|...` — rough token savings of inline vs. full (RTK `(chars+3)/4` estimate).

So nothing is discarded — the inline view stays cheap, and detail is one `Read` away.

### Failure-focus on CI

- `pr.sh checks <num>` emits `checks|<ok>/<total>` and then **only** the non-passing checks as `check|<name>|<result>|<url>`; the full check list goes to `full|`.
- `repo.sh runs` lists failures first.
- `repo.sh runs --log <id>` dumps **only the failed steps** of a run (`gh run view --log-failed` / `glab ci trace`), compacted via the tee pattern.

Example `pr.sh list`:
```
42|open|fix: cache invalidation|feature/cache|2/3
41|merged|feat: retry on 502|main|3/3
40|draft|wip: oauth|feature/oauth|-
```

Example `ship.sh` without `--message` (first call — stages, emits diff, bails). `diff-files` is a flat CSV for few files, grouped by directory once it exceeds ~8:
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
diff|... +312 more lines
full|/tmp/github-ops-tee/ship-diff-feature-x.txt
saved|1840→210 tokens (~88%)
err|need-message|re-run with --message "<conventional-commit subject>"
```

Example `ship.sh --message "feat(api): add retry"` on a new branch. On an existing branch the push line carries the pushed-commit count: `push|origin/x|existing|+2`:
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

Run only the checks relevant to the staged files. Use the `diff-files` list from the first `ship.sh` call to classify the change, then apply the table below. Stop on the first failure — do not commit broken code. Skip all checks if the user passes `--no-verify` or says "skip checks".

### File classification

Classify staged files into one or more categories:

| Category | File patterns |
|----------|--------------|
| **code** | `*.ts`, `*.tsx`, `*.js`, `*.jsx`, `*.py`, `*.go`, `*.rs`, `*.rb` |
| **config** | `*.json`, `*.yaml`, `*.yml`, `*.toml`, `*.ini`, `*.env.*` (non-secret) |
| **ci** | `.github/workflows/`, `.gitlab-ci.yml`, `.circleci/`, `Dockerfile*` |
| **docs** | `*.md`, `*.mdx`, `*.txt`, `*.rst`, `*.adoc` |
| **deps** | `package.json`, lockfiles, `Cargo.toml`, `go.mod`, `requirements*.txt`, `pyproject.toml` |
| **assets** | `*.png`, `*.svg`, `*.ico`, `*.jpg`, `*.css` (no logic) |

### Which checks to run

| Change type | Lint | Type-check | Tests |
|-------------|------|------------|-------|
| code only | ✅ staged files | ✅ staged files | ✅ targeted |
| code + config | ✅ staged files | ✅ staged files | ✅ targeted |
| config / ci only | ✅ staged files | ❌ skip | ❌ skip |
| deps only | ❌ skip | ❌ skip | ❌ skip |
| docs / assets only | ❌ skip | ❌ skip | ❌ skip |

### Running each check

Detect the package manager from the lock file in the repo root: `pnpm-lock.yaml` → pnpm, `yarn.lock` → yarn, `bun.lockb` → bun, `package-lock.json` → npm.

**Lint — staged files only, not the whole project:**
- JS/TS with Biome: `pnpm exec biome check <staged-files>` (or yarn/npm equivalent)
- JS/TS with ESLint: `pnpm exec eslint <staged-files>`
- Python: `ruff check <staged-files>`

**Type-check — always whole-project (incremental by the compiler):**
- TS: `pnpm exec tsc --noEmit` (skip if no `tsconfig.json`)
- Python: `mypy <changed-packages>` (skip if mypy not configured)

**Tests — targeted, not the full suite:**

Derive the test file(s) from the staged source files using the project's conventions (e.g., `src/foo.ts` → `src/foo.test.ts` or `tests/foo.test.ts`). Run only those files:

- Vitest: `pnpm vitest run <test-files>`
- Jest: `pnpm jest --testPathPattern "<test-files>" --passWithNoTests`
- pytest: `pytest <test-files> -x -q`
- Go: `go test ./path/to/package/...`

If no corresponding test file exists for a staged file, skip tests for that file — do not run the full suite as a fallback.

**Full suite** — run only when: the user explicitly asks, the change touches ≥ 10 source files, or the change modifies shared utilities / core modules that have broad downstream impact.

Skip check #3 entirely if the user says "skip tests".

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

## Installed hooks

Installing this skill via `install.sh` also registers two hooks in `~/.claude/settings.json` (idempotent; the uninstall flow removes them). Both are optional — the scripts work without them.

- **`git-guard`** (`PreToolUse` / `Bash`, severity `ask`) — when a raw **mutation/PR** command is about to run (`git commit`/`git push`, `gh|glab pr`/`issue`/`release`/`run`/`ci`), it surfaces a permission prompt suggesting the matching script (`ship.sh`/`pr.sh`/`issue.sh`/`repo.sh`). Read-only `git status`/`diff`/`log` are left untouched, so it does not overlap RTK's git proxy. Commands that already invoke `github-ops/scripts/` are allowed silently.
- **`auto-stage`** (`PostToolUse` / `Edit|Write`) — `git add`s the edited file so `ship.sh`/`inspect.sh` see a warm index. Skips secret-looking paths (`.env`, `*.key`, `*.pem`, `*_rsa`, `*credentials*.json`). Silent and reversible.

## Platform support

- `github.com` → uses `gh`. Required: `gh auth login` done.
- `gitlab.com` / `gitlab.*` → uses `glab`. Required: `glab auth login` done.
- Anything else → manual fallback to `git` + curl, but flag it to the user first.

## Recommended subagents

These subagents from this repo (`agents/`) sharpen the workflow when installed. The skill works without them — install selectively via `install.sh`.

- **[`code-reviewer`](../../agents/code-reviewer.md)** — between `ship.sh`'s staged-diff emit and the final `--message` call, or before `pr.sh create`. Reviews the staged diff for security vulnerabilities, correctness bugs, and performance regressions. Auto-detects the project's package manager. Skip when the diff is trivial (typo, docstring, formatting-only).
