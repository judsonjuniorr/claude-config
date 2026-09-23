# Changelog

All notable changes to this project will be documented in this file.

## [0.11.4.0] - 2026-09-23

### Changed
- **`/herow-core:doctor` pins Opus 5.5.** `token-guard.sh` now pins `claude-opus-5-5`, and
  `model-pin.py` lists it first. It needs Claude Code ≥ 2.1.280; older installs fall back to
  Opus 4.7, the same way the Opus 5 pin already did.
- **Prompt audit against Opus 5.5.** Prompt text across the plugins was trimmed where it
  prescribed method instead of outcome: the research skill and `search-specialist` state a
  stop rule instead of source counts, the builder agents keep their definition of done but
  drop the "analyze first" phase, and all-caps constraints now read at normal volume.
  `ui-ux-designer` names the current generic defaults to flag instead of prescribing new ones.
- The SEO suite states its rules without the Reddit-thread provenance, and
  `technical-seo-auditor` / `content-engineer` pin `model: sonnet`, so cost-guard's cheap tier
  is actually enforced.
- `github-ops`' hook section is down to the four facts the model acts on; the full `git-guard`
  behavior stays in its README.

### Fixed
- **`security-reviewer` findings survived no `/code:review` cutoff.** The agent had no
  `confidence=` findings contract, so the ranker scored every finding 0 and dropped it at
  every effort level. It now emits the same header line as the other review agents.
- **Agent delegation checked `~/.claude/agents/`, which plugin installs never populate.**
  `github-ops` always skipped its code-reviewer pass, and `/herow-finance:organizze` warned
  "not installed" on every run before falling back to `general-purpose`. Every delegation now
  names the namespaced agent (`herow-core:code-reviewer`, `herow-finance:financial-analyst`, …)
  and falls back only when it is missing from the session's agent list.
- Removed the "1M context needs usage credits" check from `/quick`, `/execute` and
  `/fix-cves`. Sonnet 5 and Opus 4.7+ run native 1M with no credits, and the probe read a
  settings key that is never set, so it could not fire.
- Subagents no longer "ask the user" (they can't): `code-reviewer` and `search-specialist`
  state their assumption and proceed. `code-reviewer`, `python-reviewer` and `react-reviewer`
  use the emoji severity levels their own output contract requires.
- `tdd-guide` triggers on test-first requests instead of on every feature, fix, or refactor,
  and its upstream "v1.8" addendum is gone. `/code:review` and the research skill name the
  `Agent` tool instead of `Task`.

## [0.11.3.0] - 2026-09-23

### Fixed
- **Bash commands no longer stall for 10 seconds when a hook is slow to receive its input.**
  The `destructive-guard` and `git-guard` PreToolUse hooks waited for the harness to close
  their input stream before doing anything. When that close was slow, each hook burned its
  full 10-second timeout and was then cancelled — which means it made no decision at all, so
  the wait bought nothing and the command ran unguarded anyway. Measured over one week:
  120 such cancellations for `destructive-guard` and 14 for `git-guard`, every one pinned at
  the timeout. The hooks now cap that wait at ~2 seconds and still make their decision from
  the input that already arrived, so a slow close costs 2 seconds instead of 10.
  The wait is bounded inside the same `python3` call that parses the payload, which reads in
  blocks against a wall-clock deadline and keeps whatever already arrived. That behaves the
  same under stock macOS `/bin/bash` (3.2) and bash 5, so no shell-version branch is needed —
  and, unlike a bash `read -t`, it bounds *time* rather than *size*: bash drains a pipe one
  byte per syscall, so a timed `read` silently truncated payloads past roughly 2MB and let a
  large Write through unguarded.
- **`destructive-guard` starts one interpreter per command instead of three.** It runs on
  every single Bash command, so the two extra startups were pure overhead on a path that
  exits early most of the time. Measured end-to-end: 126ms → 76ms per command.

### Changed
- Both guards now document their accepted failure modes in place: a harness slow to *send*
  (rather than slow to close) leaves the guard failing open, and a command containing invalid
  UTF-8 can skip a segment. Both are pinned by tests so they cannot change unnoticed.

### Added
- Hook guard test suites now run in CI. Previously `plugin-ci` only checked that these files
  parsed, so none of their assertions ever ran on a pull request.
- Tests for both guards now assert *elapsed time*, not just the decision — the only way to
  catch the wait cap being removed — pin a multi-MB payload so the cap can never regress into
  a size limit, and probe each shell's bash version instead of assuming it, failing loudly if
  no usable shell is found rather than passing with zero coverage.
- `destructive-guard` now checks that its `base64` decoder actually round-trips, and says so on
  stderr if none works, instead of silently decoding every field to empty and disarming itself.

## [0.11.2.0] - 2026-09-13

### Added
- **`/herow-dev:code:review` now has a real findings contract, and the bookkeeping runs in code
  instead of by hand.** Every dispatched reviewer leads each finding with
  `<emoji> <Level> confidence=<NN> <path>:<line> — <title>`, using the same four levels the command
  already ranks on. A new `rank-findings.py` then does the deduping, cutoff filtering, ESCALATE
  re-ranking and count-line rendering — all of it deterministic, so identical input gives identical
  output. Before this, the command specified a confidence cutoff that no reviewer supplied a number
  for, and reviewers answered in `CRITICAL`/`HIGH`/`MEDIUM` while the command ranked in
  🔴/🟠/🟡/🟢 with nothing mapping between them. Picking a finding's severity is still a judgment
  call and stays with the model.
- **CI now catches a hook that points at a deleted script.** `hooks.json` was only ever
  syntax-checked, so removing a hook script while leaving it registered passed CI green and then
  failed on every matching tool call. Python files under `plugins/` are syntax-checked too, and the
  shell check now covers `herow-core/scripts/setup/` and `herow-dev/scripts/`.

### Changed
- **The always-on rules no longer contradict each other or repeat what the harness already does.**
  "If something is unclear, stop. Ask." was overridden by the newer *Judgment and craft* rule
  ("decide, ship it, offer a swap menu") but never removed, which produced clarifying questions on
  exactly the low-blast work the other rule says to just get on with. The finish-the-task rule is
  now the one fact you can't infer — that a `Stop` hook bounces unfinished turns — and the
  plan-announcement template is gone. Terse "caveman" output is untouched.
- **Progress updates on long work are allowed again.** The style rules told Claude to skip
  narration and never explain a tool call. That was tuned against models that over-narrated;
  current ones under-narrate, and the rule read as "stay silent through a long tool-heavy stretch".
- **The `financial-analyst` prompt now lives in one place.** Its rules and report structure existed
  in four copies — the agent file, `analyze.py`'s guidelines, a second full output spec inside
  `analyze.py`, and `docs/financial-analyst.md` — which had drifted apart. The agent file is now the
  single source; `analyze.py` contributes only what depends on the snapshot plus the exact templates
  the command parses, and the docs page points at the agent file instead of mirroring it.
- **Report sections are as long as the data warrants.** Fixed caps (`≤3 bullets`, `≤5 bullets`,
  `max 3` questions, `3-5` cuts) were tuned against an older model's verbosity and truncated real
  findings — a month with six overdue items lost three of them. Every `[MARKER]` format stays, since
  the command parses them.
- **`security-reviewer` audits the stack you actually have.** Its scan step was hardcoded to
  `npm audit` even though the review command dispatches it on every language; it now detects the
  manifest and picks the matching audit and linter. Its OWASP checklist was the 2017 list, two
  editions stale, and is now the 2025 one with a verification date.
- **`typescript-reviewer` no longer double-reports React issues at a lower severity.** It carried a
  React block it described as a fallback, rating at MEDIUM what `react-reviewer` rates CRITICAL or
  HIGH — and both agents are dispatched together, so which severity survived depended on which
  agent answered first.
- **Five specialist agents describe themselves properly.** `comment-analyzer`,
  `type-design-analyzer`, `silent-failure-hunter`, `pr-test-analyzer` and `fastapi-reviewer` had
  one-sentence descriptions with no when-to-use and no boundary, leaving the router nothing to pick
  them on. Each now says when to use it, what it returns, and what it deliberately does not cover.
- **`/herow-core:setup-claude` generates the two blocks nobody should hand-write, and can target the
  global file.** It wrote an interview-driven friction log and explicitly never touched
  `~/.claude/CLAUDE.md` — which is exactly where the subagent routing table lives and rots: on this
  machine 9 of its 11 rows named agents that do not resolve (`code-reviewer`, not
  `herow-core:code-reviewer`), and 15 of the 26 installed agents had no row at all. The command now
  enumerates agents from `.claude/agents/`, `~/.claude/agents/` and every `installPath` in
  `installed_plugins.json`, reconciles the existing table against that inventory, and pairs it with
  explicit non-routing conditions — Opus 5 delegates more readily than its predecessors, so a table
  with no brake over-routes. It also writes a `## Health Stack` section in the shape `/health`
  already reads, without depending on that skill being installed, and prunes dated prompt text by
  invoking `/claude-api prompt-audit` at run time rather than from a copy of its rules, which ship
  with Claude Code and are rewritten per release.

### Fixed
- **`/herow-core:doctor` pins Opus 5.** It pinned Opus 4.8. Separately, `model-pin.py` had no opus
  entry in its version-fallback table, so on any machine below the required Claude Code version the
  opus pin was silently dropped and `verify.sh` then reported a bare `fail|default-opus-model` with
  no explanation.
- **Around 90 command references named commands that no longer exist.** Docs and prompts still said
  `/finance:organizze`, `/seo:weekly-audit` and similar from before the plugin rename — including
  places that told Claude to tell you to run one. Ten broken doc links from the same migration are
  fixed too.
- **The `financial-analyst` agent no longer carries instructions that cannot run.** It forbade a
  `WebSearch` tool it was never granted while `analyze.py` granted the same tool "as fallback"; it
  looked for a user-memory heading, a cash-flow section and a future-entries section under names
  nothing emits; and three different "no alternative found" strings were in circulation, one of them
  untranslated.
- **The Organizze dashboard no longer tries to surface redacted medical descriptions.** It was told
  to parse `[MEDICAL_EXPENSE]` out of the report into a panel — but that is the sanitizer's
  redaction token for data going *in*, so rendering it would have undone the redaction.
- **The graphify hint is stated once per session, not on every search.** A `PreToolUse` hook
  re-injected roughly 70 words of tool-preference steering on every Grep, Glob and search-style Bash
  call in a graphified repo, after Claude had already chosen the tool. The session-start
  announcement does the job.
- **The config doctor's own test suite passes again.** It asserted 8 registered checks when 7 are
  registered, and had been red since 2026-07-15 — unnoticed because CI runs no tests.

## [0.11.1.1] - 2026-09-02

### Fixed
- **`github-ops`'s `git-guard` hook no longer asks about read-only/non-destructive `gh`/`glab`
  commands that merely fail its fast-allow check.** The `ask` tier used to trigger on command
  *family* alone (`gh pr *`, `gh issue *`, ...), so any read-only or non-destructive-write
  command that failed the fast-allow for an unrelated reason — piped into an unrecognized
  helper like `python3` (only `jq` etc. are in the safe-helper list), or a `;`/`|`/`&` inside a
  quoted argument (a documented gap) — got an `ask` nudging toward a script the command had
  nothing to do with (e.g. `gh pr list | python3 -c "..."` → "prefer pr.sh"). The `ask` tier now
  additionally requires a destructive verb (`create`/`edit`/`close`/`delete`/`delete-asset`/
  `cancel`/`merge`/glab's `update`) to be present anywhere in the command; everything else that
  isn't fast-allowed now falls through with no decision from this hook, and normal Bash
  permission rules decide instead.

## [0.11.1.0] - 2026-08-28

### Fixed
- **`github-ops`'s `git-guard` hook no longer prompts for non-destructive `gh`/`glab` writes.**
  `gh pr ready/comment/review/reopen/lock/unlock/update-branch`, `gh issue
  comment/reopen/pin/unpin/transfer/lock/unlock/develop`, `gh release upload`, `gh run rerun`,
  `gh workflow run/enable/disable`, the `glab` equivalents, and the matching `github-ops`
  script verbs (`pr.sh ready`, `issue.sh comment`, `repo.sh workflow-run`) are now auto-allowed,
  same tier as the existing read-only fast-allow. The destructive/identity-shaping verbs the
  user chose to keep confirmation on — `create`, `edit`, `close`, `delete`, `cancel`, `merge`,
  and `glab`'s `update` — still surface an `ask`.
- **Adversarial review of a quote-fragmentation fix for the above surfaced, and fixed, a real
  permission-bypass regression** before it shipped: an earlier attempt at also letting a quoted
  `--body`/`--message` containing `;`/`|`/`&`/newline auto-allow (instead of fragmenting into
  segments that fall to `ask`) went through 4 review cycles, each of which found a live bypass
  in a smarter version of the transform — raw quote-count parity, then per-type count with
  backslash-adjacency, then a full linear quote-state scanner, then that scanner narrowed to
  bail on backslash/`$'` (defeated via bash's `#` end-of-line comments). Rather than a 5th
  scanner, the feature was removed: `git-guard.sh` now splits directly on the raw command like
  every other check in the file. A quoted body with an embedded delimiter still falls to `ask`
  (known, documented, deliberately accepted gap) rather than risk a wrongful `allow`.

## [0.11.0.0] - 2026-08-27

### Added
- **`/herow-dev:fix-cves`** — new command that finds and fixes dependency CVEs end-to-end.
  Detects the repo's ecosystem(s) (Node/TS: npm/pnpm/yarn/bun; Python: uv/poetry/pip) — cumulative,
  so a monorepo with both is handled in one run — then collects advisories via each ecosystem's
  native audit tool (falling back to `osv-scanner` when unavailable), triages by severity and
  direct-vs-transitive, and resolves each group's *minimum* patched version plus whether reaching
  it crosses a breaking change (Context7 → GitHub releases → the dependency's own CHANGELOG).
  Applies fixes one group at a time behind a human confirmation gate — direct bumps to the owning
  manifest, transitive-only advisories via the ecosystem's override mechanism (`overrides` /
  `pnpm.overrides` / `resolutions` / uv `constraint-dependencies` / a poetry pin / a pip
  `constraints.txt` entry), which is where most real advisories live and where a naive
  implementation would incorrectly report "no fix available". Runs a **baseline** validation pass
  before any change (so pre-existing red is never blamed on the upgrade) and the full
  lint/type-check/test/build gate after each group, explicitly overriding `github-ops`'s
  deps-only-changes-skip-checks rule since a CVE fix is precisely the case that needs regression
  proof. A stuck regression reverts (lockfile **and** reinstall, not just the file) and lands in a
  "needs human" bucket rather than blocking the rest of the run. Reports Fixed / No patch
  available / Needs human, then gates push + draft PR behind a final confirmation. New shared
  reference `plugins/herow-dev/reference/cve-ecosystems.md` holds the per-ecosystem command
  matrix. Scope is third-party dependencies only — first-party code security stays with
  `/security-review` and the `security-reviewer` agent.

## [0.10.0.0] - 2026-08-24

### Changed
- **PRs/MRs are now created as drafts by default** across the marketplace's one real PR-creation
  chokepoint, `github-ops`'s `pr.sh create` — the user marks a PR ready manually, never the agent.
  `--draft` is kept as a back-compat no-op; `--no-draft` (alias `--ready`) is the explicit opt-out.
  A new `pr.sh ready <num>` subcommand (`gh pr ready` / `glab mr update --ready`) exists for the
  user to invoke, but `github-ops`/`SKILL.md` now hard-rules that the agent never calls it on its
  own initiative, and never ready-then-merges a draft without asking first.
- **Draft rejection no longer fails the create.** If a repo doesn't support `--draft` (GitHub) or
  the installed `glab` doesn't support the flag (GitLab, retried once via a `Draft: ` title
  prefix), `pr.sh create` retries once as a ready PR and emits `warn|draft-unsupported` instead of
  erroring out.
- **The full PR URL is always returned**, never just a number: `pr.sh create` now also emits
  `draft|<true|false>` and an explicit `pr-url|<url>` line (in addition to the existing
  `pr|<num>|<url>`), and every consumer (`/herow-dev:git:pr`, `/herow-dev:execute`,
  `/herow-dev:quick`) was updated to surface that full URL in its final output.
- `/herow-dev:git:pr` now routes PR creation through `github-ops`'s `pr.sh` (preserving its
  template-composed body via `--body-file`) instead of hand-rolling `gh pr create` directly.
- `/herow-dev:quick` — which ends by delegating to gstack's `/ship` (a third-party skill this repo
  doesn't own or gate) — now converts the ready PR `/ship` opens into a draft immediately after,
  since `/ship` itself always creates one ready-for-review.

## [0.9.0.0] - 2026-08-18

### Added
- **Always-on destructive-operation confirmation hook** (`herow-core`) — a new PreToolUse guard
  (`destructive-guard.sh`, `Bash|Write` matcher) surfaces a permission prompt before an irreversible
  Bash command or a `Write` that overwrites an existing non-empty file, closing a real gap:
  `~/.claude/settings.json` runs `defaultMode: auto` with no `ask` rules at all, so `rm -rf` and
  friends previously ran without confirmation, and gstack's own `/careful` skill only covers this
  when explicitly invoked in a session (its own docs: "To deactivate, end the conversation or start
  a new one") — it's off by default, which is exactly when a mistake happens. The new hook is
  always-on, no invocation step. Covers six Bash families — file deletion (`rm`/`rmdir`/`unlink`/
  `find -delete`/`shred`/`truncate`/`dd of=`), irreversible git ops (`clean -f`, `reset --hard`,
  `checkout -- .`, `branch -D`, `push --force`, `stash drop/clear`, `worktree remove --force`,
  `reflog expire`, `gc --prune`, `filter-branch`/`filter-repo`), destructive SQL (`DROP`/`TRUNCATE`/
  `DELETE FROM`), datastore/ORM resets (Redis `FLUSHALL`, Mongo `.drop()`/`deleteMany`, Prisma
  `migrate reset`, Supabase `db reset`, Rails `db:drop`, Alembic `downgrade base`), cloud/infra
  destroy (`terraform destroy`, `kubectl delete`, `aws s3 rm --recursive`, `docker system prune`,
  …), and remote-repo deletion (`gh repo delete`, `gh api -X DELETE`, `gh secret delete`) — plus the
  `Write`-overwrite case. Command-name matching is case-insensitive; an `rm`-target allowlist (build/
  dep artifacts, `*.pyc`/`*.log`/`*.tmp`, `/tmp`/`$TMPDIR`) requires *every* target in a multi-target
  command to qualify before staying silent, never just one. 68 test cases (run under both Homebrew
  bash 5 and macOS's stock `/bin/bash` 3.2) pin the behavior.
- Adversarial review before merge caught and fixed four real bypasses that would otherwise have
  shipped silently: a `command` value containing an embedded newline (any heredoc or multi-step
  script — routine, non-adversarial Claude output) truncated the parsed command to its first line and
  corrupted the file-path field, defeating the guard entirely for that call; command-name matching
  was case-sensitive against a case-insensitive trigger gate, so `RM -rf` slipped through where
  `rm -rf` was caught; `unlink` and the git-history-erasure trio (`reflog expire`, `gc --prune`,
  `filter-branch`/`filter-repo`) had no coverage at all. Accepted, documented limitations (not fixed,
  by design — this is a heuristic UX guard, not a sandbox): command indirection (`sh -c`, `xargs`,
  a leading `\`, variable/function wrapping) defeats the `^command` anchors; the build/dep allowlist
  matches by directory name anywhere in the resolved path, so a coincidentally-named directory gets
  the same pass as a real build artifact; and a shell `: > file` truncation followed by a `Write` to
  the same path is invisible to the stateless overwrite check.

## [0.8.2.0] - 2026-08-17

### Fixed
- **github-ops read-only commands no longer trigger permission prompts** (`herow-core`) — `gh`/`glab`
  read-only calls made through the skill's own scripts (`pr.sh view`, `inspect.sh`, `repo.sh runs`,
  etc.) were falling through to a confirmation prompt instead of the intended silent allow; `gh api`/
  `glab api` GET requests, several read-only verbs (`gh status`, `repo list`, `label/cache/variable/
  secret/gist/extension list`, `browse`, `--version`, `glab mr checks`, `glab pipeline list`), an `rtk
  proxy` prefix, and a quoted `>`/`<` inside a GitHub search qualifier (`created:>2024-01-01`) all hit
  the same gap. All now auto-allow as designed.
- **Fixed an over-eager permission denial** — the attribution guard (which blocks any Claude Code/
  Anthropic reference from landing in a commit or PR/MR body) ran unscoped on every Bash command, not
  just git/gh/glab ones, so it could be tripped by any command that merely contained a matching
  substring, denying things like `rg -m 1 "claude code" CHANGELOG.md`, `find . -mtime -1 | grep
  anthropic`, and `gh pr reviews 42 --repo anthropics/claude-code`. The check is now scoped to
  commands that actually touch git/gh/glab and carry a message/body flag or mutating verb, matched
  with real word boundaries.
- **Fixed an under-eager permission allow** — `gh api -X delete ...` (lowercase HTTP method) was
  silently auto-approved as read-only instead of being caught as a write.
- **Fixed a path-traversal gap in the `/tmp` redirect tolerance** — `gh pr view 42 >
  /tmp/../../../etc/passwd` matched the "tolerated redirect to /tmp" pattern (which never excluded
  `..` or `/`) and was silently auto-allowed. The tolerated form is now restricted to a flat filename
  under `/tmp` — a legitimate `> /tmp/out.txt` still auto-allows, a traversal target no longer does.
- **Fixed the attribution guard skipping relative-path/bare wrapper-script invocations** — the new
  scoping only recognized a github-ops script by the literal `github-ops/scripts/` path substring, so
  `bash scripts/ship.sh -m "...Co-Authored-By: Claude"` or a bare `issue.sh comment ...` (relative
  path, symlink, PATH resolution) skipped the check entirely. For `issue.sh`, which has no
  attribution-scrubbing of its own, this hook was the *only* defense against an attribution string
  landing in a real GitHub issue/comment. Wrapper scripts are now also recognized by basename.

### Added
- Regression test suite for the github-ops permission guard (110 cases, expanded from 105 after
  adversarial review) committed alongside the fix.

## [0.8.1.0] - 2026-08-05

### Added
- **Memory-management review lane** (`herow-dev`) — `python-reviewer` and `react-reviewer` each gain a
  dedicated `HIGH` lane covering leaks, retention, and unbounded growth, since the only prior coverage
  anywhere in the config was a single generic bullet in `herow-core`'s `code-reviewer`. Python:
  unbounded materialization (`.read()`/`.readlines()`/`list(cursor)` without generators/`chunksize=`/lazy
  frames), unbounded `@lru_cache`/module-global caches (including `@lru_cache` on a method pinning
  `self`), retention via long-lived `global`s, unregistered callbacks, or stored `except ... as e`
  tracebacks, unreleased file/socket/DB/subprocess resources, missing `__slots__` at high object
  cardinality, unbounded `asyncio.Queue`/task sets, and long-lived server state (module globals,
  unclosed SQLAlchemy sessions, unpaginated cursors) — plus `tracemalloc`/`memray`/`objgraph` diagnostics
  and FastAPI/Django-specific checks. React: effect cleanup reframed as retention across
  listeners/observers/timers/sockets/subscriptions (flagging StrictMode's double-mount as the fast way
  to catch a missing one), fetches without `AbortController`, undisposed third-party instances
  (map/chart/editor/player), `createObjectURL` without `revokeObjectURL`, detached-DOM refs, unbounded
  client state (append-only lists/buffers), caches that never evict (module `Map`s, `gcTime: Infinity`),
  and per-request module state in RSC/Node — plus a heap-snapshot/DevTools/`jest --detect-leaks`
  diagnostics addition and a new scope-table row so the lane is unambiguously owned by `react-reviewer`
  rather than falling to `typescript-reviewer`. `/herow-dev:code:review` now documents this as a
  required lane for any `.py`/`.tsx`/`.jsx` diff, tags surviving memory findings with a 🧠 marker in the
  report and count line, and warns (`⚠️ memory lane skipped — <agent> unavailable`) instead of silently
  dropping the check when the availability guard fires.

### Changed
- **`/herow-dev:code:review` second opinion now prefers the `advisor` tool** over Codex/Agy/a Claude
  subagent when the session has it available (it's availability-gated, not shell-probed, and falls
  through silently to `which codex` otherwise) — `advisor` forwards the review's entire transcript
  (diff, every dispatched agent's findings, the DEDUPE & RANK reasoning) to a stronger reviewer model
  rather than a summary, and is already pinned to `advisorModel: opus` by `token-guard.sh`. Because
  `advisor` takes no parameters, the sanitized findings JSON and CONFIRM/DISPUTE/ESCALATE prompt are now
  emitted as the turn immediately before calling it, and its prose reply is mapped onto finding IDs
  rather than parsed as guaranteed JSON. Documented honestly: since `advisor` forwards the whole
  transcript, the Step 3 sanitization doesn't fully cover this channel — the original diff and every
  agent's raw findings are already in what gets forwarded, unlike the Codex/Agy/subagent channels
  which only ever see the sanitized copy.
- **`--fix` no longer dead-ends the working tree.** FIX now runs before FINISH (Local Mode: REPORT →
  FIX → FINISH; PR Mode: REPORT → FIX → FINISH & ACT) so the *Finish — choose an action* prompt can
  offer a third option — commit + push the applied fixes via the `github-ops` skill's `ship.sh` —
  alongside the existing "keep on screen" and "submit a review" options. `ship.sh` has no
  default-branch guard of its own (it pushes to whatever's checked out, and `github-ops`'s own hook
  pre-allows its invocations with no prompt), so the option's own instructions now check the current
  branch first and create a feature branch before delegating whenever the working tree is sitting on
  the repo's default branch. A non-interactive `--fix` run that skips the prompt now always prints a
  commit/push suggestion instead of leaving the tree dirty with no next step.

## [0.8.0.0] - 2026-07-31

### Added
- **`/herow-core:setup-claude`** — new command that authors **personal, non-committed project instructions** (`CLAUDE.local.md`) or team-shared ones (`CLAUDE.md`), the counterpart to the built-in `/init`: `/init` writes a codebase overview, this writes a **friction log** for the user (role, sandbox URLs/test accounts, workflow quirks, always-on preferences, repo landmines). Modeled on `doctor.md`'s gated safety envelope + `profile.md`'s AskUserQuestion interview. Key properties: an embedded **optimization policy** (every line must be non-discoverable *and* change how Claude operates — no directory trees / stack summaries / generic filler; prune stale lines on re-run rather than append-only); a runtime opt-in that hard-filters the optional **skills** (`.claude/skills/*/SKILL.md`) and **hooks** (`.claude/settings.json`, handed to the built-in `update-config` skill) phases; and a privacy guard that **resolves `git config --global core.excludesfile` at runtime** (never a hardcoded home path — CI forbids `/Users/` under `plugins/`) to confirm/add the `CLAUDE.local.md` ignore entry to the **global** excludes — never the committed project `.gitignore`, which would defeat a personal file. Detects git worktrees and offers the documented `@~/.claude/<project>-instructions.md` import-stub pattern so personal notes survive across worktrees. Writes **no repo-side `.bak`** (git covers `CLAUDE.md`; a `.bak` would trip doctor's `claude_md_backups` hygiene check) — diff-preview + explicit confirm is the safety mechanism. Scoped to the two project-root files; never touches the global `~/.claude/CLAUDE.md`.

## [0.7.0.0] - 2026-07-27

### Added
- **graphify auto-engage + auto-freshen hooks** (`herow-core`) — version-controlled replacement for a machine-local nudge that never actually fired: the old `~/.claude/settings.json` block matched tool `Bash` and grepped the command string, but native `Grep`/`Glob` tool calls (the default, via `USE_BUILTIN_RIPGREP=1`) never go through Bash. Three new `herow-core` hooks propagate through the marketplace to every repo instead of requiring a per-repo `CLAUDE.md` edit:
  - `graphify-nudge.sh` (`PreToolUse`, matcher `Grep|Glob|Bash`) — injects `additionalContext` steering Claude toward `graphify query`/`path`/`explain` whenever `graphify-out/graph.json` exists, whether the search is a native `Grep`/`Glob` call or a Bash `grep`/`rg`/`find`/etc. Also checks the call's own target path for `Grep`/`Glob` (not just the session root) so a session rooted in a non-graphified directory (e.g. `frontend/`) still gets nudged when a search explicitly reaches into a sibling directory (e.g. `../backend/`) that has its own graph — Bash commands stay session-root-only since reliably parsing a target path out of an arbitrary shell string is out of scope.
  - `graphify-inject.sh` (`SessionStart`) — a short proactive block alongside `rules-inject.sh`, silent when no graph exists.
  - `graphify-freshen.sh` (`UserPromptSubmit`) — detects when the current HEAD has moved past the graph's last-known commit (`graphify-out/.graphify_head`) and kicks off an incremental `graphify update` (AST-only, no LLM for code-only changes) fully detached in the background, so the hook returns instantly. Guards: skips repos without a `graphify-out/manifest.json` baseline (covers fresh `/herow-dev:quick`/`execute` worktrees, where an absent gitignored manifest would otherwise trigger a full rebuild), silently baselines `.graphify_head` on the very first prompt it ever sees in a repo instead of firing a fleet-wide rebuild the instant this feature ships (only HEAD movement *after* that baseline counts as stale), backs off (linear, capped at 30 min, tracked in `.graphify_update.failcount`) instead of retrying a persistently-failing update on every single prompt, and is disabled per-invocation with `HEROW_SKIP_GRAPHIFY=1`. Single-flights via a `mkdir` lock gated on **PID liveness** (`kill -0`), not a fixed time window — a flat TTL would risk stealing the lock from an update that's simply still running (large repo, LLM-backed semantic pass) and spawning a second concurrent writer against the same graph files; a 30s grace window covers the gap between acquiring the lock and its PID being recorded. Uses `nohup`, not `setsid` — the latter is Linux/util-linux-only and absent on macOS. All three hooks resolve their target repo via `git rev-parse --show-toplevel` (never trusting `CLAUDE_PROJECT_DIR` verbatim, and failing closed on resolution failure) so they agree on "the repo" regardless of which subdirectory Claude Code was launched from.
- **`/graphify-install` git-hook step** (`herow-extras`) — installs append-safe `post-merge`/`post-checkout` git hooks (POSIX `sh`, never clobber an existing hook file) so the graph refreshes even when Claude Code isn't running (e.g. a terminal `git pull`). `post-checkout` only acts on branch checkouts (`$3 = 1`), not file-level checkouts, and — like the `UserPromptSubmit` backstop — both hooks additionally require `graphify-out/manifest.json` to exist, since worktrees share the main repo's `.git/hooks` and `git worktree add` fires `post-checkout` with `$3 = 1` against a tree that has committed `graph.json` but no gitignored `manifest.json`. Both hooks share the exact same lock/failcount/PID-liveness semantics as `graphify-freshen.sh` (embedded identically in both hook templates, since standalone git hooks in an arbitrary target repo can't reliably call back into a `$CLAUDE_PLUGIN_ROOT` script) — a git-triggered and a session-triggered refresh can never race on `graph.json` concurrently. Both stamp `graphify-out/.graphify_head` on success so the `UserPromptSubmit` backstop stays quiet afterward.

### Changed
- README's plugin table, `docs/commands.md`, and `herow-core`'s marketplace `plugin.json` now mention the new graphify hooks, kept in sync with the feature above.

## [0.6.0.0] - 2026-07-17

### Added
- **herow-dev pull-latest hook** — a new `UserPromptSubmit` hook (`plugins/herow-dev/scripts/pull-latest.sh`, registered in `plugins/herow-dev/hooks/hooks.json`) fast-forwards the current branch to its upstream (`git pull --ff-only`) on the main tree **before** `/herow-dev:blueprint`, `/herow-dev:quick`, or `/herow-dev:execute` runs, so planning and implementation always start on the freshest code. It fires only on those three commands (silent and zero-cost otherwise) and is entirely fail-open: `HEROW_SKIP_PULL=1` opt-out (checked first), plus not-a-repo/detached-HEAD/no-upstream/offline/diverged paths each print an actionable one-line reason and continue — it never blocks a command (always exits 0) and never rewrites local commits (`--ff-only`). Bounded by a 20s hook `timeout`. Each of the three command files carries a prose note tying the invisible behavior back to the docs.
- **Mandatory pre-push validation gate** across the herow-dev push/finalize commands. New shared spec `plugins/herow-dev/reference/pre-push-gate.md` is the single source of truth for the gate — lint (auto-fix) → type-check (if present) → tests → build, each existing step must pass 100% (absent steps skipped + logged, never faked) — plus a load-bearing anti-cheat clause (no skip/delete/disable tests, `--passWithNoTests`, `|| true`, blanket `eslint-disable`/`# type: ignore`/`@ts-nocheck`, or `--no-verify`; stop + report over hacking the gate) and a pre-existing-failure policy (fix untouched-file failures too, isolated in a `chore: fix pre-existing gate failures` commit; stop + report if large/unrelated). Wired into `execute.md` (reconciles the old step-7 gate and the "don't touch files outside scope" rule with an explicit gate carve-out), `quick.md` (gate before the external `/ship`), `git/pr.md` (**verify-only** — detects red and directs the user to `execute`/`quick`, since it has no `Edit`/`Write`), and `git/fix-conflicts.md` (replaces the weak "suggest tests" line with a real fix-loop gate; still never auto-commits/pushes).

## [0.4.1.0] - 2026-07-15

### Removed
- **headroom integration** — the `headroom-ai` third-party CLI is no longer bundled: `scripts/setup/headroom-wrap.sh` deleted, `install-stack.sh`/`detect.sh`/`verify.sh` no longer install/detect/verify it, the `headroom_hook_redundancy` doctor check removed from `tokens.py`, and all install-flow prose in `commands/doctor.md`/`README.md` updated accordingly.

## [0.5.0.0] - 2026-07-15

### Added
- **`/herow-dev:ux-audit`** — new command that walks a live user flow with Playwright MCP as a real user (typed input, triggered actions, observed results — not a static code read), gates on console/network/axe-core a11y/perf hard thresholds, and produces a ranked findings report with reproduction steps, evidence, and a suspected `file:line` per finding. Adapted from [jezweb/claude-skills](https://github.com/jezweb/claude-skills)' `ux-audit` skill: retargeted to Playwright MCP only (this repo forbids the gstack `browse` skill and `mcp__claude-in-chrome__*` tools globally), condensed from its ~15 cross-referenced reference files into one self-contained command, and given a `--quick`/`--deep` depth control the source skill didn't have. Includes an interaction-manifest requirement (no logged real interaction = verdict `Incomplete`, never rounded up to Pass) and an optional `--fix` loop that patches Critical/High findings and re-verifies just the affected step.

## [0.4.0.0] - 2026-07-10

### Added
- **One-directory-per-plan layout** for `herow-dev` plan persistence. Each plan now lives in `.claude/plans/<slug>/` holding `plan.md`, `state.json`, optional `source.md`, and an `artifacts/` subdir for everything that plan's orchestration produces — replacing the flat `.plans/<name>.md` + `.plans/<name>.state.json` files that lived side by side at the `.plans/` root. Anticipates Claude Code's own community-requested project-scoped `.claude/plans/` convention (anthropics/claude-code#14866) and mirrors GitHub Spec Kit's per-feature `specs/<feature>/` directories.
- **Session-scoped tracking marker.** `blueprint-track.sh` now binds the active plan to the session via `.claude/plans/.active-<session_id>` (read from the hook payload's `session_id`, claimed by the blueprint command via `$CLAUDE_SESSION_ID`). Concurrent Claude Code sessions in the same repo — the normal workflow — can now each run a blueprint without colliding, and the hook never records one session's skill calls into another session's plan.
- **Idempotent gitignore guard** in `blueprint.md`: appends `.claude/plans/` to the global `core.excludesfile` and the repo `.gitignore` only if missing, keeping the legacy `.plans/` entry. `.claude/plans/` exemption added to `doc-file-warning.sh` so orchestration `.md` writes under a plan dir don't raise a permission prompt.
- **Committed test suites** for the hardened scripts: `plugins/herow-dev/scripts/tests/test-blueprint-track.sh` (9 cases — session gating, hostile session ids, traversal slugs, namespace normalization, LIFO pairing, double corruption, stale-lock recovery, concurrent POSTs, `.claude/plans`-as-file) and `plugins/herow-core/scripts/tests/test-doc-file-warning.sh` (6 cases for the output-hygiene guard).

### Changed
- `blueprint.md` / `execute.md` rewritten for the new layout: `mkdir` (without `-p`) claims the plan directory as an atomic uniqueness guard; `plan.md` is written once at consolidation (its absence marks an in-flight plan); the shared `latest.txt` pointer is gone — `execute` resolves an explicit slug/path or the newest plan directory containing `plan.md`, with a read-only fallback to the legacy flat `.plans/` layout (other repos migrate on demand; new plans are always written in the new layout).
- `blueprint-track.sh` scopes artifact detection to the plan's own `artifacts/` dir (fast, immune to unrelated repo/worktree churn, and no longer self-pollutes), writes `state.json` atomically (temp file + `os.replace`), and normalizes recorded skill names by stripping the plugin namespace so the coverage checklist matches reliably.
- Added the language rule to `blueprint`, `execute`, `quick`, and `create-prd`: all generated code, comments, commit messages, and documentation must be in English even when the input is in Portuguese, unless the user explicitly requests otherwise.
- Migrated this repo's existing 7 plans into the new layout and removed the empty `.plans/` directory.

### Fixed
- **Cross-session state contamination** — the previous hook keyed only on a repo-global `.plans/.active` with no session identity, so any concurrent session's skill calls (proven: `github-ops` entries leaked into planning-only state files) appended into whatever plan was active. The session-scoped marker eliminates this.
- **`state.json` corruption and lost updates** — the old in-place truncating read-modify-write could leave torn/half-written JSON that poisoned every later run under `set -eu`; writes are now atomic, a corrupt file is preserved as `state.json.corrupt` (not silently discarded) with tracking continuing, and a bounded `mkdir` lock serializes the stack pop + state update so concurrent PRE/POST pairs within a session can't lose a record.
- **`.plans/*.md` mtime fallback hazards** — a `<name>.source.md` sibling could shadow the real plan, and an in-flight empty plan file could be executed as garbage. Resolution now targets a fixed `plan.md` name and skips directories without it.
- **Review hardening (pre-merge adversarial review of this release):**
  - Path traversal via the marker slug — the model-generated slug crossed a trust boundary unvalidated, so a marker containing `../../..` made the hook create dirs and write `state.json` outside the repo. The hook now rejects any slug outside `[A-Za-z0-9._-]` or starting with a dot, and applies the same charset guard to the payload `session_id`.
  - The `state.json` write is wrapped in `|| true` so a disk-full/permission failure degrades to a lost record instead of a non-zero hook exit, honoring the fail-open contract.
  - Stale spinlock recovery — a lock directory older than 10s (owner killed without its EXIT trap) is broken instead of forcing every later invocation to spin ~5s and run unlocked.
  - Repeat `state.json` corruption now preserves each damaged copy under a timestamped `.corrupt.*` name instead of silently discarding the second one.
  - `doc-file-warning.sh` canonicalizes the path before matching, so `.claude/plans/../../x.md` can no longer slip through the plans exemption.
  - Skill-name normalization strips only one namespace segment (`herow-dev:code:review` → `code:review`, previously `review`).
  - `execute.md` branch-slug doc updated for the new layout (slug from the plan directory name, timestamp prefix stripped); blueprint setup sweeps `.active-*` markers older than 7 days.

## [0.3.0.0] - 2026-07-06

### Added
- `herow-finance`'s Organizze integration now reads through the official [`organizze` CLI](https://github.com/organizze/agent-tools) (`_cli.py`) instead of a hand-rolled `urllib` client — same API token, same data, officially maintained transport with built-in pagination.
- `/herow-core:doctor` detects, installs (brew cask / curl fallback), and verifies the `organizze` CLI alongside `rtk`/`graphify`/`headroom`.

### Changed
- Account balances now come from the CLI's real per-account `balance` (parsed from Organizze's formatted `"R$ 1.234,56"` string) instead of being reconstructed by summing 5 years of transactions — more accurate, and the old balance-calibration onboarding step is now an optional sanity check rather than a required workaround.
- `create.py`'s account/card/category/invoice/recent-transaction lookups also go through the CLI; the actual writes (transactions, transfers, installments, recurrences, invoice-targeted card entries) stay on the existing REST POST path, since the CLI's write surface doesn't cover all of them.
- `setup_auth.sh` installs the `organizze` CLI during onboarding and validates credentials with `organizze status`.

### Fixed
- Two issues caught by pre-merge review before they shipped: the CLI's `accounts get` balance field is a formatted string, not integer cents like every other money field in the API — parsing it directly would have crashed on any non-zero balance; and a narrow TOCTOU where the CLI binary disappears between the presence check and execution now surfaces as a normal `err|network|` failure instead of a raw traceback.

## [0.2.2.0] - 2026-07-05

### Fixed
- `herow-finance` per-account forecast (`balance_on.py`, `cashflow.py`) — Organizze occasionally emits an occurrence of a *recurring transfer* whose two linked legs (`oposite_transaction_id`) carry the **same sign**, so the pair no longer nets to zero and the destination account's forecast is thrown off by 2× the amount (an incoming R$ 5.500 transfer showing as a R$ 5.500 debit made one account project ~R$ 11k too low — 90 phantom "critical days"). New `cashflow.normalize_transfers()` repairs corrupt pairs in place by taking the correct per-account direction from the healthy sibling occurrences of the same `recurrence_id` (falling back to leaving undeterminable one-offs untouched with a `warn|transfer-unrepaired|…` line). It runs at ingestion in `pull.py` (so new snapshots are clean at the source) and defensively on read in `balance_on.py` / `cashflow.py` (so existing snapshots are repaired at compute time); healthy pairs are never touched, so the pass is idempotent. Regression tests in `tests/test_normalize_transfers.py`.

## [0.2.1.0] - 2026-07-02

### Fixed
- `herow-finance` `/herow-finance:organizze` — the balance-scraping reconciliation step (`apply_scrape.py`) mutated the raw Organizze snapshot in place, but the PII-sanitized snapshot and `metrics.json` that the analysis prompt and deterministic metrics actually read were generated *before* scraping ran. A run that corrected a balance via scraping could show two different numbers for the same account in the same report — the per-account breakdown fresh from scraping, the analysis narrative stale from before it. New `organizze-scrape.md` Step 3.5e re-runs `sanitize.py` + `compute.py` after any successful (or partially successful) scrape reconciliation, so every downstream step reads the same reconciled numbers.
- `apply_scrape.py` — the headline "Current balance" and +7/30/90-day projections (`meta.totais`) were computed once by `pull.py` at pull time and never recomputed afterward, so they stayed frozen at pre-scrape values even after Step 3.5e's refresh. `apply_scrape.py` now recomputes `meta.totais` from the reconciled accounts/transactions/invoices before writing the snapshot back.
- `sanitize.py` — the scrape reconciliation debug fields (`_scrape_meta`, `_scrape_unreconciled`) carried raw, untokenized account names and transaction descriptions that bypassed every PII-removal path (CPF/CNPJ stripping, medical masking, account tokenization). Nothing downstream reads these fields, so `sanitize_snapshot()` now drops them instead of letting raw text leak into the file meant to be safe for LLM consumption.

## [0.2.0.0] - 2026-06-30

### Added
- `model-pin.py` — new `scripts/setup/` CLI that lists and pins `ANTHROPIC_DEFAULT_OPUS_MODEL` / `ANTHROPIC_DEFAULT_SONNET_MODEL` in `~/.claude/settings.json`. `--list` queries the Anthropic Models API live (top 3 per family, sorted by release date; falls back to a static list when `ANTHROPIC_API_KEY` is absent, the API is unreachable, or a live response only covers one family). `--apply [--opus <id>] [--sonnet <id>]` writes idempotently with an atomic tmp+`os.replace` and a timestamped `.bak` (skipped gracefully when no prior settings.json exists), preserving the original file's permissions; `--dry-run` shows the diff without writing. Rejects a value that doesn't match its family (e.g. a Sonnet ID passed to `--opus`), and checks the installed Claude Code version against each model's minimum before pinning it — falling back (or skipping the pin) with a `warn|…` line when the version is too old, since Sonnet 5 requires Claude Code ≥ v2.1.197 and Opus 4.8 requires ≥ v2.1.154.
- `/herow-core:doctor` Step 2.5 — **interactive model pin picker**: after `token-guard.sh` applies safe defaults, doctor presents two `AskUserQuestion` prompts (one for Opus, one for Sonnet) showing the 3 most recent models from each family, exact-matched against `--list` output and passed through quoted to `model-pin.py --apply` behind a dry-run diff + confirm gate.
- `verify.sh` — two new assertions: `ANTHROPIC_DEFAULT_OPUS_MODEL` / `ANTHROPIC_DEFAULT_SONNET_MODEL` must be set to a `claude-opus-*` / `claude-sonnet-*` id in `settings.json` env.

### Changed
- `token-guard.sh` — after applying top-level defaults (`model: opusplan`, `advisorModel: opus`, `effortLevel: high`, `autoCompact: true`), now calls `model-pin.py --apply --opus claude-opus-4-8 --sonnet claude-sonnet-5` (with an exit-code check) so that reinstalling the plugin always guarantees Sonnet 5 / Opus 4.8 pins exist, or falls back cleanly on an older Claude Code. The doctor picker can override these after the fact.
- `~/.claude/settings.json` (live config) — added `ANTHROPIC_DEFAULT_OPUS_MODEL: claude-opus-4-8` and `ANTHROPIC_DEFAULT_SONNET_MODEL: claude-sonnet-5` to the `env` block, guaranteeing the `opusplan` alias's model halves regardless of future alias drift.

### Known risks (accepted)
- `model-pin.py` has no automated test suite yet (0% coverage on ship review) — a future change to the version-gate, family-validation, or atomic-write logic could regress silently. Accepted for this release; a `scripts/setup/tests/test_model_pin.py` following the existing `doctor/tests/` pattern is a good follow-up.
- No file locking around the settings.json read-modify-write in `model-pin.py` — concurrent `--apply` invocations could last-writer-wins clobber each other. Low risk for a single-user CLI tool.

## [0.1.4.0] - 2026-06-22

### Added
- `/herow-dev:code:review` — **interactive finish**: after the report, when a PR/MR is in play, the command asks (via `AskUserQuestion`) whether to keep the report on screen or **submit a review**. Submitting always uses the **Request changes** verdict whenever there is at least one finding (any severity), so it **blocks the merge** until the review is resolved — not a passive comment. The review carries inline GitHub/GitLab **suggestion blocks** wherever a fix maps to diff lines, so the author can apply them in one click; off-diff or non-literal fixes fall back to plain comments folded into the summary. All review comment text is written in the **repository's language** (detected from PR template → PR/MR body → README; defaults to English; code/paths/emoji/suggestions never translated). The `--comment` flag is the non-interactive shortcut for the same submission.

### Changed
- README, `.claude-plugin/marketplace.json`, and the `herow-dev:prompt-optimizer` reference tables now present `code:review` as the single **language-aware** review door (reframed for discoverability — "auto-detects `.tsx`/`.ts`/`.py` → specialist reviewers" — instead of listing per-language commands).
- `react-reviewer` agent: `## Related` footer repointed to the React authoring rules that exist (dropped the dangling `rules/react/hooks.md` reference) and reframed as the canonical authoring source the review lanes map onto.

### Removed
- `/herow-dev:python:review`, `/herow-dev:react:review`, `/herow-dev:python:fastapi-review` — the three standalone review commands are **consolidated into `/herow-dev:code:review`**, which already dispatches the matching specialist reviewers by changed-file language (`.tsx`/`.jsx` → `react-reviewer` + `typescript-reviewer`; `.ts`/`.js` → `typescript-reviewer`; `.py`, FastAPI-aware → `fastapi-reviewer` + `python-reviewer`). The per-language reviewer **agents are unchanged** — only the redundant command entry points are gone, making `code:review` the single review door with one consistent output format (its REPORT phase owns formatting).

## [0.1.3.0] - 2026-06-22

### Added
- `/herow-core:doctor` config auditor scripts under `plugins/herow-core/scripts/doctor/`: `security.py` (`permissions_deny` deny-block + `plaintext_secrets` mcp-stash scan), `tokens.py` (`headroom_hook_redundancy`, `playwright_headed_active`, `grafana_active`), `hygiene.py` (`gstack_bak`, `claude_md_backups`, `language_rules_paths`), and a read-only `audit.py` orchestrator. Each check emits a JSON line (`check/status/diff/fix_cmd`), is dry-run by default, and applies idempotently with `--apply <id>` writing a timestamped `.bak`. Includes a hermetic `unittest` suite.

### Changed
- Renamed `/herow-core:setup` → `/herow-core:doctor`. The command now leads with a read-only audit (security / token-cost / hygiene) and applies fixes only after explicit per-category `AskUserQuestion` approval + a dry-run diff + a final confirm. First-install compatibility is preserved: when the stack is missing, doctor offers to run the existing installer flow (the unchanged `scripts/setup/` scripts) before auditing.

## [0.1.2.0] - 2026-06-18

### Changed
- `herow-dev:prompt-optimizer` now **blocks on `AskUserQuestion` before generating any output** when material context gaps are detected. Phase 4 classifies each gap as material (answer would change the generated prompt) or non-material (sensible default applies); material gaps trigger a batched `AskUserQuestion` call with 2–4 concrete options per question, and the optimized prompt is only produced after all answers are received. The old escape hatch (listing open questions alongside the prompt) is removed.
- `herow-dev:prompt-optimizer` Section 1 renamed from "Needs Clarification" to "Assumptions & resolved clarifications" — it now records answers collected via `AskUserQuestion` and non-material defaults applied, never unanswered questions.

## [0.1.1.0] - 2026-06-15

### Added
- Three new global operating-rule files in `herow-core/rules/common/`: `verify-before-claiming.md`, `scope-and-safety.md`, and `judgment-and-craft.md` — AI behavior rules from Fable5 covering confirmed-vs-inferred claim discipline, operational scope/safety (rollback protocol, blast-radius framing, prompt-injection guard), and judgment at decision forks (recommendation-first, evidence grounding, honest status close)
- `/herow-dev:code:review` — **language-aware dispatch** (Phase 2.5): automatically detects changed file extensions and runs the matching specialist agents in parallel with the generic review agents. `.tsx`/`.jsx` → `react-reviewer` + `typescript-reviewer`; `.ts`/`.js` → `typescript-reviewer`; `.py` (with FastAPI detected via project files or diff) → `fastapi-reviewer` + `python-reviewer`; no match → no language agents. All rows are additive for multi-language diffs.
- `/herow-dev:code:review` — **second-opinion pass** (Phase 3.5 / Phase 4.5): serializes surviving findings to a compact JSON array, probes for `codex` → `agy` → Claude subagent, invokes with a CONFIRM/DISPUTE/ESCALATE reviewer prompt, and applies verdicts: `ESCALATE` raises severity one level (feeding the PR DECIDE table); `DISPUTE` keeps the finding but flags it and excludes it from `--fix`. Includes parse-failure recovery and a sanitization step to prevent hostile diffs from injecting instructions into the second-opinion prompt.
- `/herow-dev:code:review` — **unified report format**: every finding now carries an inline verdict badge (`🔴 Critical · ✅ CONFIRM — title`); `DISPUTE`/`ESCALATE` findings get a trailing `2nd opinion: <note>` line; the count line gains a second-opinion summary suffix (`🔴 1  🟠 2  🟡 3  🟢 0   (2nd opinion: ✅2 ⚠️1 ⏫1)`). Badge is omitted when the second-opinion pass produced no verdicts.

### Changed
- Commands and agents no longer pin a `model:` in frontmatter — every execution and subagent now inherits the **default input model** (the model selected for the session). Skills keep their `model:` pins.
- `token-guard.sh` no longer sets `CLAUDE_CODE_SUBAGENT_MODEL`; it now **removes** any existing pin so subagents inherit the session model. The session default (`model: opusplan`, `advisorModel: opus`, `effortLevel: high`, `autoCompact: true`) is unchanged.
- `detect.sh`/`verify.sh`: the subagent-model check now flags/asserts that no `CLAUDE_CODE_SUBAGENT_MODEL` pin is present.

### Fixed
- `/herow-dev:execute` and `/herow-dev:quick` model guardrail now detects the `[1m]` (1M-context) suffix — the real cause of "Usage credits required for 1M context" — instead of checking tier, and fails open when the model is unknown (no false positives).

## [0.1.0.0] - 2026-06-12

### Added
- `token-guard.sh` — new setup step that automatically applies token-saving defaults to `~/.claude/settings.json`: `model: opusplan` (Sonnet for all normal work, Opus with 1M context only when plan mode is active), `advisorModel: opus`, `effortLevel: high`, `autoCompact: true`, and `CLAUDE_CODE_SUBAGENT_MODEL: claude-sonnet-4-6` to pin all subagents to Sonnet regardless of parent model
- `/herow-core:setup` Step 4.5 wires token-guard automatically — runs on every setup with no user approval needed
- `detect.sh` reports missing token optimizations as `opt|` records in the Step 1 inventory, now even on fresh machines (before `settings.json` exists)
- `verify.sh` checks all five token settings post-install (`model`, `effortLevel`, `advisorModel`, `autoCompact`, `CLAUDE_CODE_SUBAGENT_MODEL`)
- `/herow-dev:execute` frontmatter now enforces `model: sonnet` — was documented in a comment but not enforced
- `/herow-dev:quick` frontmatter now enforces `model: sonnet`
- Model guardrail added to `/herow-dev:execute` and `/herow-dev:quick` — detects if the active session is not Sonnet and shows `claude --model claude-sonnet-4-6` as a copy-paste one-liner

### Fixed
- `token-guard.sh`: atomic write via `tempfile + os.replace` prevents settings corruption on disk-full or interrupted runs
- `token-guard.sh`: `"env": null` and non-dict roots in `settings.json` no longer crash silently — guarded with type checks
- `token-guard.sh`: bootstrap safely creates `~/.claude/` directory if it doesn't exist yet
- `detect.sh`: `opt|` block no longer gated on `[ -f "$SETTINGS" ]` — fresh machines without a settings file now correctly surface all missing token optimizations
