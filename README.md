# claude-config

Personal Claude Code configuration hub: slash commands, skills, agents, global guardrail
hooks, system-wide rules, and profile-based install — travels with me across machines and projects.

## Structure

```
claude-config/
├── commands/                    # slash commands
│   ├── finance/                 → see commands/finance/README.md
│   │   ├── organizze.md         → /finance:organizze command file
│   │   └── organizze-scripts/   → scripts used by /finance:organizze
│   ├── file-organizer/          → see commands/file-organizer/README.md
│   ├── fix-conflicts/           → see commands/fix-conflicts/README.md
│   ├── generate-tests/          → see commands/generate-tests/README.md
│   ├── graphify-install/        → see commands/graphify-install/README.md
│   ├── refactor-code/           → see commands/refactor-code/README.md
│   ├── release-notes/           → see commands/release-notes/README.md
│   ├── seo/                     → see commands/seo/README.md (11 /seo:* commands)
│   └── validate-ui/             → see commands/validate-ui/README.md
├── skills/                      # skills
│   ├── github-ops/              → see skills/github-ops/README.md
│   └── error-handling/          → typed errors, Result pattern, retries (TS + Python)
├── agents/                      # subagents
│   ├── backend-architect.md     → /agent backend-architect
│   ├── code-reviewer.md         → /agent code-reviewer
│   ├── content-engineer.md      → /agent content-engineer
│   ├── debugger.md              → /agent debugger
│   ├── financial-analyst/       → see agents/financial-analyst/README.md
│   ├── fullstack-developer.md   → /agent fullstack-developer
│   ├── mobile-developer.md      → /agent mobile-developer
│   ├── python-pro.md            → /agent python-pro
│   ├── search-specialist.md     → /agent search-specialist
│   ├── seo-strategist.md        → /agent seo-strategist
│   ├── silent-failure-hunter.md → /agent silent-failure-hunter
│   ├── technical-seo-auditor.md → /agent technical-seo-auditor
│   └── ui-ux-designer.md        → /agent ui-ux-designer
├── rules/                       # auto-loaded global guidance + per-language library
│   ├── common/                  → symlinked into ~/.claude/rules/ (loaded everywhere)
│   ├── typescript/              → applied per-project by the Claude session
│   └── python/                  → applied per-project by the Claude session
├── hooks/                       # global guardrails (merged into settings.json)
│   ├── hooks.json
│   ├── doc-file-warning.sh      → warns on stray .md doc creation
│   ├── config-protection.sh     → warns on linter/formatter config edits
│   └── stop-guard.sh            → Stop hook: nudges a premature stop to finish the task
├── manifests/
│   └── profiles.json            → install bundles (minimal / dev / seo / finance)
└── mcp-configs/                 # opt-in MCP server templates + config guidance
    ├── registry.json
    └── mcp.template.json
```

## Rules (auto-loaded, replaces the old CLAUDE.md)

`rules/common/*.md` are symlinked into `~/.claude/rules/`, which Claude Code **auto-loads
globally** at the start of every session — communication style, output hygiene, the four
working principles (think before coding, simplicity first, surgical changes, goal-driven
execution), and "finish the task" (don't stop mid-task). This replaces the former monolithic
`CLAUDE.md`. The "finish the task" rule is paired with the `stop-guard.sh` Stop hook, which
bounces a premature stop back with a reminder to continue.

Per-language rules under `rules/typescript/` and `rules/python/` are **not** installed globally
(they would add noise to unrelated projects). A pointer rule in `common/` tells the Claude
session to read and apply them when you are working in a project of that language.

## Contents

| Type    | Name                                                         | One-liner                                                                   |
|---------|--------------------------------------------------------------|-----------------------------------------------------------------------------|
| Command | [`/finance:organizze`](./commands/finance/README.md#financeorganizze) | Pull personal finance data from Organizze via REST API, build a snapshot, delegate to the `financial-analyst` subagent for a prioritized action plan. |
| Command | [`/file-organizer`](./commands/file-organizer/README.md)     | Analyze a directory, find duplicates, propose a tidy structure, and reorganize files only after explicit approval. |
| Command | [`/fix-conflicts`](./commands/fix-conflicts/README.md)       | Resolve merge conflicts on a PR or branch, grounding each decision in the commit history of both sides. |
| Command | [`/generate-tests`](./commands/generate-tests/README.md)     | Generate a comprehensive test suite for a file or function, auto-detecting the project's testing framework. |
| Command | [`/graphify-install`](./commands/graphify-install/README.md) | Bootstrap [graphify](https://github.com/safishamsi/graphify) inside any git repo end-to-end. |
| Command | [`/refactor-code`](./commands/refactor-code/README.md)       | Safely refactor a file or function with tests-first, incremental changes, and static analysis verification. |
| Command | [`/release-notes`](./commands/release-notes/README.md)       | Generate a user-friendly changelog (pt-br/en) from commits since the last tag, inline in the chat. |
| Command | [`/seo:*`](./commands/seo/README.md)                         | SEO/GEO growth suite — 11 `/seo:*` commands encoding the Agensi playbook with skeptic corrections (CTR & conversion over impressions, indexation gate, GEO weighting, backlinks-are-human, information-gain bar, cost tiering). Standalone + optional `toprank`; every command ends at a human gate. |
| Command | [`/validate-ui`](./commands/validate-ui/README.md)           | Audit UI/UX against a consolidated ruleset (Vercel Web Interface Guidelines + 3 design skills + Context7 lib docs), static plus opportunistic live validation. Read-only. |
| Skill   | [`github-ops`](./skills/github-ops/README.md)                | Token-efficient GitHub/GitLab ops via `gh`/`glab`. Conventional Commits, pre-commit checks, split detection, PR/issue/CI management. |
| Skill   | [`error-handling`](./skills/error-handling/SKILL.md)         | Typed error hierarchies, the `Result<T,E>` pattern, API error envelopes, React error boundaries, and retry-with-backoff for TypeScript and Python. |
| Agent   | [`backend-architect`](./agents/backend-architect.md)         | Produces architecture documents: OpenAPI specs, database schemas, event schemas, diagrams, and trade-off analyses. Design only — not implementation. |
| Agent   | [`code-reviewer`](./agents/code-reviewer.md)                 | Senior code reviewer focused on security, correctness, and performance. Detects the project's package manager automatically. |
| Agent   | [`content-engineer`](./agents/content-engineer.md)           | SEO/GEO content engineer — drafts articles, FAQ schema, quick-answers, internal links, with a hard information-gain gate. Part of the `/seo:*` suite. |
| Agent   | [`debugger`](./agents/debugger.md)                           | Systematic fault-localization debugger. No fix without root cause. Writes a regression test for every bug fixed. |
| Agent   | [`financial-analyst`](./agents/financial-analyst/README.md)  | Personal finance analyst subagent — consumes pre-built snapshots, respects user memory, outputs prioritized action plans. |
| Agent   | [`fullstack-developer`](./agents/fullstack-developer.md)     | End-to-end TypeScript implementation: Next.js 16, React 19+, tRPC, Drizzle ORM, shadcn/ui. UI to database. |
| Agent   | [`mobile-developer`](./agents/mobile-developer.md)           | Cross-platform mobile with React Native 0.82+, Expo SDK, iOS 18, and Android 15. Performance-first. |
| Agent   | [`python-pro`](./agents/python-pro.md)                       | Expert Python 3.12+ developer: FastAPI, Polars, uv, ruff, mypy strict, full type coverage. |
| Agent   | [`search-specialist`](./agents/search-specialist.md)         | Web research with rigorous source evaluation, contradiction handling, and structured findings reports. |
| Agent   | [`silent-failure-hunter`](./agents/silent-failure-hunter.md) | Single-purpose reviewer for swallowed errors, dangerous fallbacks (`.catch(() => [])`), lost stack traces, and missing error propagation. |
| Agent   | [`seo-strategist`](./agents/seo-strategist.md)               | Senior SEO/GEO strategist (Opus, no Write) — analyzes GSC exports, makes the call on what to build. Part of the `/seo:*` suite. |
| Agent   | [`technical-seo-auditor`](./agents/technical-seo-auditor.md) | Parses GSC exports → prioritized fix list + indexation coverage + CTR diagnostics. Part of the `/seo:*` suite. |
| Agent   | [`ui-ux-designer`](./agents/ui-ux-designer.md)               | Research-driven senior UI/UX designer. Evidence-backed critique, WCAG 2.2 AA, anti-generic aesthetics. |

Each command, skill and agent has its own README with the full reference, examples, and rules.

## Installation

```bash
git clone https://github.com/judsonjuniorr/claude-config ~/sources/personal/claude-config
cd ~/sources/personal/claude-config

./install.sh --profile dev   # install a coherent bundle
./install.sh --doctor        # verify everything is wired
```

Every install also registers the global guardrail hooks and symlinks the common rules into
`~/.claude/rules/` (auto-loaded). Symlinks are the default — edits in the repo reflect
immediately without reinstalling.

Run with no flags for the interactive flow: it offers a **profile** first, or `custom` to pick
individual assets (fzf multi-select, or a numbered menu without fzf).

### Profiles

`--profile <name>` installs a bundle declared in `manifests/profiles.json`:

| Profile | Contents |
|---------|----------|
| `minimal` | `github-ops`, `code-reviewer`, `debugger` |
| `dev` | full dev toolkit — `github-ops`, `error-handling`, the engineering agents (incl. `silent-failure-hunter`), and the standalone dev commands |
| `seo` | `/seo:*` commands + `content-engineer`, `seo-strategist`, `technical-seo-auditor` |
| `finance` | `/finance:*` commands + `financial-analyst` |

`--list-profiles` prints each profile's assets. A profile referencing a missing asset fails the
preflight validation (also enforced in CI) rather than half-installing.

### Options

| Flag | Description |
|------|-------------|
| `--profile NAME` | Install a named bundle (+ global hooks + common rules) |
| `--list-profiles` | List profiles and their assets |
| `--mcp` | Print MCP server config guidance (env vars; opt-in, writes nothing) |
| `--doctor` | Diagnose the install (symlinks, hooks, rules pointer, manifest ↔ disk) |
| `--all` | Install everything without prompting |
| `--replace` | Overwrite existing files instead of creating `.bak` backups |
| `--help` | Show usage |
| `uninstall` | Interactively remove installed assets (a full uninstall also clears the global hooks + common rules) |

### MCP servers

`--mcp` reads `mcp-configs/registry.json` and prints, per curated server (context7, playwright,
github), the command and any required env vars with where to get them. It never writes secrets
and never auto-installs — copy the servers you want from `mcp-configs/mcp.template.json` into a
project `.mcp.json` or `~/.claude.json`.

### What gets installed where

| Type | Installed to |
|------|-------------|
| Commands | `~/.claude/commands/{name}.md` |
| Namespaced commands (e.g. `/finance:*`) | `~/.claude/commands/{namespace}/` (real dir, symlinked files inside) |
| Skills | `~/.claude/skills/{name}/` (directory symlink) |
| Agents | `~/.claude/agents/{name}.md` |
| Common rules | `~/.claude/rules/{name}.md` (symlink; pointer rule is a generated file) |
| Global hooks | merged into `~/.claude/settings.json`; scripts via `~/.claude/claude-config-hooks` → `hooks/` |

`README.md` files are never copied to `~/.claude/`. The language rules (`rules/typescript/`,
`rules/python/`) are intentionally **not** installed globally — the Claude session applies them
per-project.
