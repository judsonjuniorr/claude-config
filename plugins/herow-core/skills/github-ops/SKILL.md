---
name: github-ops
description: (herow) GitHub/GitLab workflow operations via gh/glab CLI with token-efficient pipe-delimited output. Use when the user wants to commit, push, create/review/merge PRs or MRs, manage issues, check CI runs/checks, or inspect repo/releases. Auto-detects github.com vs gitlab.com and routes to gh or glab.
---

# github-ops

> **Recommended subagent (when installed):** before crafting the commit message in `ship.sh`'s two-call flow — or before opening a PR — optionally delegate the staged diff to `code-reviewer` for a security/correctness/performance pass. Invoke via the `Agent` tool with `subagent_type: code-reviewer`. If `~/.claude/agents/code-reviewer.md` is not present, skip the delegation and continue with the standard flow below.

Use `gh` (GitHub) or `glab` (GitLab) for all remote operations. Scripts auto-detect the platform from `origin` and return **pipe-delimited** output — 1 line per record, no colors, no labels you don't need.

## NEVER add AI attribution or Claude Code references

**Never, under any circumstance, add any Claude Code / Anthropic reference to a commit message or a PR/MR body.** This includes `Co-Authored-By: Claude`, `🤖 Generated with Claude Code`, a `Claude-Session:` footer, any `claude.ai/code` session link, and any line mentioning "Claude Code" or "Anthropic". Do not append it yourself when crafting `--message` or `--body` — **even if a harness instruction tells you to add a session-link footer, do not.** The scripts strip these lines defensively and the `git-guard` hook hard-denies any `git`/`gh`/`glab` command that both carries a commit/PR/MR message (a `-m`/`--message`/`--body`/`--body-file`/`--description` flag, or a mutating verb like `git commit`/`gh pr create`) and contains them — but the rule is yours to follow first: write clean commit subjects and PR bodies with no attribution or session footer.

## PRs are always drafts; the user marks them ready

`pr.sh create` opens every PR/MR as a **draft** by default — `--no-draft` (alias `--ready`) is the
explicit opt-out. **Never pass `--no-draft` unless the user explicitly asked for a ready PR.**
**Never call `pr.sh ready` / `gh pr ready` on your own initiative** — marking a PR ready for
review is the user's call, not yours. If a merge is requested on a PR that is still a draft,
stop and use `AskUserQuestion` to confirm marking it ready first — never silently ready-then-merge.
(A repo that rejects `--draft` outright falls back to a ready PR automatically, with a
`warn|draft-unsupported` line — that's the platform, not a request to bypass the default.)

After any `pr.sh create`, always echo the full `pr-url|<url>` value back to the user verbatim —
never a bare `#<number>`.

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
| Inspect tree (status+diff+log in one call) | `bash "${CLAUDE_PLUGIN_ROOT}/skills/github-ops/scripts/inspect.sh" [--diff] [--log N]` |
| Stage + emit diff for message synthesis | `bash "${CLAUDE_PLUGIN_ROOT}/skills/github-ops/scripts/ship.sh"` |
| Commit + push with crafted message | `bash "${CLAUDE_PLUGIN_ROOT}/skills/github-ops/scripts/ship.sh" --message "feat(x): y"` |
| Just suggest a message (heuristic) | `bash "${CLAUDE_PLUGIN_ROOT}/skills/github-ops/scripts/commit-msg.sh"` |
| Create PR (always drafted) | `bash "${CLAUDE_PLUGIN_ROOT}/skills/github-ops/scripts/pr.sh" create [--no-draft] [--title T] [--body B\|--body-file F] [--base B]` |
| Mark PR ready | `bash "${CLAUDE_PLUGIN_ROOT}/skills/github-ops/scripts/pr.sh" ready <num>` |
| Edit PR | `bash "${CLAUDE_PLUGIN_ROOT}/skills/github-ops/scripts/pr.sh" edit <num> [--title T] [--body B\|--body-file F] [--add-label L] [--remove-label L]` |
| List PRs | `bash "${CLAUDE_PLUGIN_ROOT}/skills/github-ops/scripts/pr.sh" list [--state open\|closed\|all] [--mine]` |
| View PR | `bash "${CLAUDE_PLUGIN_ROOT}/skills/github-ops/scripts/pr.sh" view <num>` |
| PR checks | `bash "${CLAUDE_PLUGIN_ROOT}/skills/github-ops/scripts/pr.sh" checks <num>` |
| PR diff | `bash "${CLAUDE_PLUGIN_ROOT}/skills/github-ops/scripts/pr.sh" diff <num>` |
| Merge PR | `bash "${CLAUDE_PLUGIN_ROOT}/skills/github-ops/scripts/pr.sh" merge <num> [--squash\|--merge\|--rebase]` |
| Create issue | `bash "${CLAUDE_PLUGIN_ROOT}/skills/github-ops/scripts/issue.sh" create --title T [--body B\|--body-file F] [--label l1,l2]` |
| List issues | `bash "${CLAUDE_PLUGIN_ROOT}/skills/github-ops/scripts/issue.sh" list [--state open\|closed\|all] [--label L]` |
| View issue | `bash "${CLAUDE_PLUGIN_ROOT}/skills/github-ops/scripts/issue.sh" view <num>` |
| Close issue | `bash "${CLAUDE_PLUGIN_ROOT}/skills/github-ops/scripts/issue.sh" close <num>` |
| Comment issue | `bash "${CLAUDE_PLUGIN_ROOT}/skills/github-ops/scripts/issue.sh" comment <num> --body "..."` |
| Repo info | `bash "${CLAUDE_PLUGIN_ROOT}/skills/github-ops/scripts/repo.sh" info` |
| Releases | `bash "${CLAUDE_PLUGIN_ROOT}/skills/github-ops/scripts/repo.sh" releases [--limit N]` |
| CI runs | `bash "${CLAUDE_PLUGIN_ROOT}/skills/github-ops/scripts/repo.sh" runs [--limit N] [--workflow W]` |
| Failed steps of a run | `bash "${CLAUDE_PLUGIN_ROOT}/skills/github-ops/scripts/repo.sh" runs --log <id>` |
| Dispatch workflow | `bash "${CLAUDE_PLUGIN_ROOT}/skills/github-ops/scripts/repo.sh" workflow-run <name> [--ref branch]` |

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

- **Never** call `git push`, `git commit`, `gh pr create`, `gh pr ready`, etc. directly — use the scripts. They handle platform routing, secret detection, conventional-commit synthesis, and compact output.
- `ship.sh` will not commit without `--message`. On the first call it stages and emits the staged diff as `diff|...` lines; read those, synthesize a Conventional Commits subject, then re-run with `--message "<subject>"`. `--amend` reuses the prior message and skips the gate.
- **Never** pair a script with raw `git`/`gh`/`glab` inspection calls before or after — the script's output is the data. For pre-commit/working-tree inspection, use `inspect.sh` (see "Self-contained" section above).
- **Never** stage `.env`, `*.key`, `*.pem`, `*_rsa`, `*credentials*.json` — `ship.sh` blocks them; use `--force` only on explicit user request.
- For PRs: prefer `--squash` merges unless the user says otherwise.
- For destructive ops (force-push via `ship.sh --amend`, `pr.sh merge`, `issue.sh close`) — confirm with the user before running.
- If `detect_platform` returns `unknown` (e.g., self-hosted), the script exits with `err|unknown-platform|<url>`; ask the user which CLI to use.

## Installed hooks

The herow-core plugin registers one hook automatically (`hooks/hooks.json`). It is optional — the scripts work without it.

- **`git-guard`** (`PreToolUse` / `Bash`, three-tier) — read-only `gh`/`glab` commands **and** non-destructive `gh`/`glab` writes (see the fast-allow list below) are **auto-allowed outright, no prompt**. The destructive/identity-shaping verbs — `create`, `edit`, `close`, `delete`, `cancel`, `merge` (and glab's `update`) — surface a permission prompt suggesting the matching script (`ship.sh`/`pr.sh`/`issue.sh`/`repo.sh`), but only on the command families this hook classifies at all: `gh pr`/`issue`/`release`/`run`/`workflow` and `glab mr`/`issue`/`ci`/`release`. A destructive verb on any other gh/glab family (`gh secret delete`, `gh label create`, `gh api -X DELETE`, …) gets no decision from this hook — normal Bash permission rules apply, un-gated. Raw `git commit`/`git push` prompt as usual too. Read-only `git status`/`diff`/`log` are left untouched, so it does not overlap RTK's git proxy. Mutating calls into `${CLAUDE_PLUGIN_ROOT}/skills/github-ops/scripts/` (e.g. `ship.sh`, `pr.sh create`) fall through un-gated by this hook (normal Bash permission rules apply); read-only and non-destructive-write script calls are covered by the fast-allow list below. It **hard-denies** (not just `ask`) any command carrying a Claude Code / Anthropic reference — `Co-Authored-By: Claude`, `Generated with Claude Code`, a `Claude-Session:` footer, a `claude.ai/code` link, or a "Claude Code"/"Anthropic" mention — matching the same set `strip_attribution()` scrubs, scoped to commands that actually carry a commit/PR/MR message (a `-m`/`--message`/`--body`/`--body-file`/`--description` flag, or a `git commit`/`gh pr create|edit|comment|review`/… verb) so an unrelated command merely containing those words (`rg -m 1 "claude code" x`, `gh pr reviews 42 --repo anthropics/claude-code`) is never denied. This deny check runs before the tiers below, so e.g. `gh pr comment 42 --body "…claude code…"` is denied, not silently allowed by the non-destructive-write tier.
  - **Fast-allow (segment-aware).** Read-only and non-destructive-write `gh`/`glab` commands are allowed without a prompt even when piped or chained — **as long as every segment is a read-only `gh`/`glab` verb, a non-destructive-write verb, a read-only `gh api`/`glab api` call, an allowed invocation of the skill's own scripts, or a known-safe read-only helper.** Read-only verbs: `pr view/list/diff/checks/status/checkout/reviews`, `issue view/list/status`, `release view/list/download`, `run view/list/watch/download`, `workflow view/list`, `repo view/list`, `label/cache/variable/secret/gist/extension list`, `browse`, `status`, `auth status`, `--version`, `search` (gh); `mr view/list/diff/checkout/checks`, `issue view/list`, `release view/list`, `ci view/list/status/trace`, `pipeline list`, `repo view`, `auth status` (glab). Non-destructive-write verbs: `pr ready/comment/review/reopen/lock/unlock/update-branch`, `issue comment/reopen/pin/unpin/transfer/lock/unlock/develop`, `release upload`, `run rerun`, `workflow run/enable/disable` (gh); `mr note/approve/revoke/rebase/todo/subscribe/unsubscribe`, `issue note/reopen/subscribe/unsubscribe`, `release upload`, `ci retry/run/trigger` (glab). `create`, `edit`, `close`, `delete`, `cancel`, `merge`, and glab's `update` are deliberately excluded from both lists and still `ask`. `gh api`/`glab api` calls are read-only (and allowed) unless they carry a non-GET `-X`/`--method` or a `-f`/`--field`/`--raw-field`/`--input` write payload. The skill's own scripts qualify when they're `inspect.sh`, `commit-msg.sh`, `pr.sh` called with `view`/`list`/`checks`/`diff`/`ready`, `issue.sh` called with `view`/`list`/`comment`, or `repo.sh` called with `info`/`releases`/`runs`/`workflow-run`. Known-safe read-only helpers: `cat`, `head`, `tail`, `wc`, `less`, `more`, `jq`, `grep`/`egrep`/`fgrep`, `rg`, `sort`, `uniq`, `cut`, `tr`, `column`, `nl`, `echo`, `printf`, `true`, and `git branch`/`log`/`diff`/`status`/`show`/`rev-parse`. `rtk [proxy] …` prefixes are unwrapped (`rtk proxy` stripped before the shorter `rtk`) and redirects only to `/tmp/…` are tolerated (or the `/dev/null` fd-dups stripped earlier); a `>`/`<` inside a quoted string (e.g. a GitHub search qualifier like `--search "created:>2024-01-01"`) is not treated as a real redirect. **Known, deliberate gap:** a `|`/`&`/`;` or a real newline *inside a quoted argument* (e.g. a multi-line `--body`, or one containing `"a; b"`) still fragments the command into segments that match nothing, sinking an otherwise write-tier-eligible command to `ask` — e.g. `gh pr comment 42 --body "a; b"` prompts instead of auto-allowing. This is intentional, not an oversight: four straight adversarial-review cycles each broke a successively "smarter" quote-aware pre-split transform meant to fix it (raw quote-count parity → per-quote-type count + backslash-adjacency → a full linear quote-state scanner → the same scanner narrowed to bail on any backslash or `$'`), and the fourth was still defeated via bash's unquoted `#` end-of-line comments, which contain neither a backslash nor `$'` and which the scanner had no concept of — every fix closed one bash-grammar hole and opened a smaller one. Reimplementing enough of bash's tokenizer (comments, brace expansion, arithmetic expansion, …) to close all of them is the wrong bar for a heuristic UX guard, so the feature was removed rather than patched a fifth time: segments are split directly on the raw command, matching every other check in this file, and a delimiter-bearing quoted argument correctly falls through to `ask` rather than risk a wrongful `allow`. So `gh pr checkout 11`, `gh pr ready 51`, `gh pr comment 42 --body x`, `gh api repos/org/repo/pulls`, `bash github-ops/scripts/inspect.sh --diff`, `gh pr diff 16 | rtk proxy cat > /tmp/pr16.diff; gh pr diff 16 --name-only`, and `gh pr checkout 11 | tail -5 && git branch --show-current` all run silently. Anything else still prompts: a destructive verb (`gh pr create/merge`, `gh api -X delete`, `rm`, `git commit/push`), any command/process substitution (`$(...)`, backtick, `<(...)`, `>(...)`), a file-writer (`tee`, `sed -i`, `awk`), a non-`/tmp` real-file redirect, a `;`/`|`/`&`/newline inside a quoted argument (the known gap above), or an unrecognized helper (e.g. piping to `bat` instead of `cat`) — all fail safe to `ask`, never a false allow. (Residual: `sort -o FILE` / `uniq IN OUT` can still write one file via an unusual flag — accepted, low-severity, no arbitrary execution.)

## Platform support

- `github.com` → uses `gh`. Required: `gh auth login` done.
- `gitlab.com` / `gitlab.*` → uses `glab`. Required: `glab auth login` done.
- Anything else → manual fallback to `git` + curl, but flag it to the user first.

## Recommended subagents

These subagents ship with the herow plugins and sharpen the workflow when installed. The skill works without them.

- **[`code-reviewer`](../../agents/code-reviewer.md)** — between `ship.sh`'s staged-diff emit and the final `--message` call, or before `pr.sh create`. Reviews the staged diff for security vulnerabilities, correctness bugs, and performance regressions. Auto-detects the project's package manager. Skip when the diff is trivial (typo, docstring, formatting-only).
