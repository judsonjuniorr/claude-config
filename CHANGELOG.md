# Changelog

All notable changes to this project will be documented in this file.

## [Unreleased]

## [0.1.1.0] - 2026-06-15

### Added
- Three new global operating-rule files in `herow-core/rules/common/`: `verify-before-claiming.md`, `scope-and-safety.md`, and `judgment-and-craft.md` — AI behavior rules from Fable5 covering confirmed-vs-inferred claim discipline, operational scope/safety (rollback protocol, blast-radius framing, prompt-injection guard), and judgment at decision forks (recommendation-first, evidence grounding, honest status close)

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
