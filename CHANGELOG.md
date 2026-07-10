# Changelog

All notable changes to this project will be documented in this file.

## [Unreleased]

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
