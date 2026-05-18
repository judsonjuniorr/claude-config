# /release-notes

Generates a user-friendly changelog from the commits made since the last tag (or the last 50 commits if no tag exists), rendered inline in the chat.

See [`release-notes.md`](./release-notes.md) for the full agent-facing procedure.

## What it does

1. Detects the last language used for this command in the current repo by reading `<repo-root>/.claude/settings.local.json` → `customCommands.releaseNotes.lang` (defaults to `pt-br`).
2. Asks the user which language to use (`pt-br` or `en`) with the previously-used language pre-selected as `(Recommended)`.
3. Persists the chosen language to `<repo-root>/.claude/settings.local.json` under `customCommands.releaseNotes.lang`, preserving every other key (atomic write via `jq`, with a Python fallback).
4. Collects commits since the most recent tag by date (or the last 50 commits if none), skipping merge commits and cancelling out revert↔original pairs.
5. Classifies each commit into one of four categories — ✨ New Features, 🛠️ Improvements, 🐛 Bug Fixes, 🔧 Internal Changes — using Conventional Commit prefixes and explicit decision rules. Flags breaking changes with `⚠️ Breaking:`.
6. Rewrites every bullet as a short, past-tense, user-facing sentence (no jargon, no hashes, no PR/issue IDs, no author names) and groups related commits.
7. Suggests the next SemVer version based on the change mix (major / minor / patch).
8. Renders the changelog inline in the chat using the localized template, omitting empty sections.
9. Runs a final validation checklist before sending.

## Frontmatter

- **description**: Generate a user-friendly changelog from commits since the last tag/release.
- **allowed-tools**: inherits Claude Code defaults (no explicit allow-list).
- **argument-hint**: none.

## Language

UX is bilingual — `pt-br` (default) or `en`, persisted per-repo.

## When to use

- Preparing release notes before tagging a new version.
- Sharing a human-readable summary of recent work with non-engineering stakeholders.

## Prerequisites

- Inside a git repository.
- `jq` available (falls back to Python if not).
- Write access to `<repo-root>/.claude/settings.local.json` (the command only touches the `customCommands.releaseNotes.lang` key).

## Side effects

The **only** file written to disk is `<repo-root>/.claude/settings.local.json`, and only its `customCommands.releaseNotes.lang` key. The changelog itself is rendered in the chat — no file is created.
