# claude-config

Personal Claude Code configuration hub: slash commands, skills, agents, global guardrail
hooks, system-wide rules, and profile-based install — travels with me across machines and projects.

## (herow) tagging convention

Commands and skills in this repo are marked `(herow)` at the start of their `description:`
frontmatter value. This prefix identifies assets that originate from or are curated by this
repo, as opposed to external plugins. It is idempotent — the install scripts strip it before
displaying help text if needed.

## Structure

```
claude-config/
├── commands/                    # slash commands (namespaced)
│   ├── code/                    → /code:review, /code:refactor-code
│   ├── finance/                 → /finance:organizze (+ context/goal/profile helpers)
│   ├── file-organizer/          → /file-organizer
│   ├── generate-tests/          → /generate-tests
│   ├── git/                     → /git:fix-conflicts, /git:pr, /git:release-notes
│   ├── graphify-install/        → /graphify-install
│   ├── create-prd/              → /create-prd
│   ├── python/                  → /python:review, /python:fastapi-review
│   ├── react/                   → /react:review, /react:test, /react:validate-ui
│   └── seo/                     → 11 /seo:* commands
├── skills/                      # skills
│   ├── github-ops/              → token-efficient GitHub/GitLab ops
│   ├── error-handling/          → typed errors, Result pattern, retries (TS + Python)
│   ├── deep-research/           → multi-source deep research via firecrawl + exa
│   ├── exa-search/              → neural web search via Exa MCP
│   ├── prompt-optimizer/        → analyze and optimize prompts
│   ├── research-ops/            → evidence-first research workflow
│   └── jira-integration/        → Jira API patterns via MCP or REST
├── agents/                      # subagents
│   ├── backend-architect.md
│   ├── code-reviewer.md
│   ├── code-simplifier.md       → simplifies code while preserving behavior
│   ├── comment-analyzer.md      → analyzes comment accuracy and rot risk
│   ├── content-engineer.md
│   ├── debugger.md
│   ├── fastapi-reviewer.md      → FastAPI async/DI/Pydantic reviewer
│   ├── financial-analyst/
│   ├── fullstack-developer.md
│   ├── mobile-developer.md
│   ├── pr-test-analyzer.md      → test coverage quality for PRs
│   ├── python-pro.md
│   ├── python-reviewer.md       → Python PEP8/type hints/security reviewer
│   ├── react-reviewer.md        → React hooks/RSC/a11y/perf reviewer
│   ├── search-specialist.md
│   ├── security-reviewer.md     → OWASP Top 10, secrets, SSRF reviewer
│   ├── seo-strategist.md
│   ├── silent-failure-hunter.md
│   ├── tdd-guide.md             → TDD specialist enforcing test-first
│   ├── technical-seo-auditor.md
│   ├── type-design-analyzer.md  → type encapsulation and invariant analyzer
│   ├── typescript-reviewer.md   → TS/JS type safety/async/security reviewer
│   └── ui-ux-designer.md
├── rules/                       # auto-loaded global guidance + per-language library
│   ├── common/                  → symlinked into ~/.claude/rules/ (loaded everywhere)
│   │   ├── api-design.md        → REST API conventions
│   │   └── backend-patterns.md  → repository/service/caching patterns
│   ├── csharp/                  → C#/.NET coding style, patterns, security, dotnet-patterns
│   ├── python/                  → Python coding style, FastAPI, hooks, patterns, security, testing
│   ├── react/                   → React hooks, patterns, security, testing, motion, performance
│   ├── rust/                    → Rust coding style, hooks, patterns, security, testing
│   ├── swift/                   → Swift coding style, hooks, patterns, security, testing
│   ├── typescript/              → TypeScript coding style
│   └── web/                     → web design-quality, a11y, design-system, patterns, performance
├── hooks/                       # global guardrails (merged into settings.json)
│   ├── hooks.json
│   ├── doc-file-warning.sh      → warns on stray .md doc creation (PreToolUse)
│   ├── config-protection.sh     → warns on linter/formatter config edits (PreToolUse)
│   ├── stop-guard.sh            → Stop: nudges premature stop to finish the task
│   ├── quality-gate.js          → PostToolUse: format check after edits (Biome/Prettier/ruff/gofmt)
│   ├── post-edit-console-warn.js → PostToolUse: warns on console.log in edited TS/JS files
│   ├── stop-format-typecheck.js → Stop: batch format + tsc on all files edited this response
│   └── check-console-log.js     → Stop: scans git-modified TS/JS files for console.log
├── manifests/
│   └── profiles.json            → install bundles (minimal / dev / seo / finance)
└── mcp-configs/                 # opt-in MCP server templates + config guidance
    ├── registry.json            → context7, playwright, github, sequential-thinking, exa-web-search, omega-memory, shadcn
    └── mcp.template.json
```

## Rules (auto-loaded, replaces the old CLAUDE.md)

`rules/common/*.md` are symlinked into `~/.claude/rules/`, which Claude Code **auto-loads
globally** at the start of every session — communication style, output hygiene, the four
working principles (think before coding, simplicity first, surgical changes, goal-driven
execution), and "finish the task" (don't stop mid-task). This replaces the former monolithic
`CLAUDE.md`. The "finish the task" rule is paired with the `stop-guard.sh` Stop hook, which
bounces a premature stop back with a reminder to continue.

Per-language rules under `rules/typescript/`, `rules/python/`, `rules/react/`, etc. are **not**
installed globally (they would add noise to unrelated projects). A pointer rule in `common/`
tells the Claude session to read and apply them when you are working in a project of that language.

## Contents

| Type    | Name                                                         | One-liner                                                                   |
|---------|--------------------------------------------------------------|-----------------------------------------------------------------------------|
| Command | `/code:review`                                               | Multi-agent code review — dispatches 7 specialist reviewers, dedupes, ranks by severity. Local or PR mode. |
| Command | `/code:refactor-code`                                        | Safely refactor a file or function with tests-first, incremental changes, and static analysis verification. |
| Command | `/finance:organizze`                                         | Pull personal finance data from Organizze via REST API, build a snapshot, delegate to the `financial-analyst` subagent for a prioritized action plan. |
| Command | `/file-organizer`                                            | Analyze a directory, find duplicates, propose a tidy structure, and reorganize files only after explicit approval. |
| Command | `/git:fix-conflicts`                                         | Resolve merge conflicts on a PR or branch, grounding each decision in the commit history of both sides. |
| Command | `/git:pr`                                                    | Create a GitHub PR — discovers templates, analyzes commits, pushes, creates with CI status check. |
| Command | `/git:release-notes`                                         | Generate a user-friendly changelog (pt-br/en) from commits since the last tag, inline in the chat. |
| Command | `/generate-tests`                                            | Generate a comprehensive test suite for a file or function, auto-detecting the project's testing framework. |
| Command | `/graphify-install`                                          | Bootstrap [graphify](https://github.com/safishamsi/graphify) inside any git repo end-to-end. |
| Command | `/python:review`                                             | Comprehensive Python code review for PEP 8, type hints, security, and Pythonic idioms. |
| Command | `/python:fastapi-review`                                     | FastAPI architecture, async correctness, DI, Pydantic, security, and production readiness review. |
| Command | `/react:review`                                              | React/JSX code review for hook correctness, RSC boundaries, accessibility, and security. |
| Command | `/react:test`                                                | TDD workflow for React with React Testing Library, Vitest or Jest. |
| Command | `/react:validate-ui`                                         | Audit UI/UX against the Vercel Web Interface Guidelines. Read-only. |
| Command | `/seo:*`                                                     | SEO/GEO growth suite — 11 `/seo:*` commands encoding the Agensi playbook. |
| Skill   | `github-ops`                                                 | Token-efficient GitHub/GitLab ops via `gh`/`glab`. Conventional Commits, pre-commit checks, split detection, PR/issue/CI management. |
| Skill   | `error-handling`                                             | Typed error hierarchies, the `Result<T,E>` pattern, API error envelopes, React error boundaries, and retry-with-backoff for TypeScript and Python. |
| Skill   | `deep-research`                                              | Multi-source deep research using firecrawl and exa MCPs. Cited reports with source attribution. |
| Skill   | `exa-search`                                                 | Neural search via Exa MCP for web, code, company research, and people lookup. |
| Skill   | `prompt-optimizer`                                           | Analyze raw prompts, identify intent and gaps, output a ready-to-paste optimized prompt. |
| Skill   | `research-ops`                                               | Evidence-first current-state research workflow. Fresh facts, comparisons, and recommendations. |
| Skill   | `jira-integration`                                           | Jira API patterns for retrieving tickets, updating status, adding comments, transitioning issues. |
| Agent   | `backend-architect`                                          | Produces architecture documents: OpenAPI specs, database schemas, event schemas, diagrams, and trade-off analyses. Design only — not implementation. |
| Agent   | `code-reviewer`                                              | Senior code reviewer focused on security, correctness, and performance. Detects the project's package manager automatically. |
| Agent   | `code-simplifier`                                            | Simplifies and refines code for clarity, consistency, and maintainability while preserving behavior. |
| Agent   | `comment-analyzer`                                           | Analyzes code comments for accuracy, completeness, maintainability, and comment rot risk. |
| Agent   | `content-engineer`                                           | SEO/GEO content engineer — drafts articles, FAQ schema, quick-answers, internal links, with a hard information-gain gate. Part of the `/seo:*` suite. |
| Agent   | `debugger`                                                   | Systematic fault-localization debugger. No fix without root cause. Writes a regression test for every bug fixed. |
| Agent   | `fastapi-reviewer`                                           | Reviews FastAPI apps for async correctness, DI, Pydantic schemas, security, and production readiness. |
| Agent   | `financial-analyst`                                          | Personal finance analyst subagent — consumes pre-built snapshots, respects user memory, outputs prioritized action plans. |
| Agent   | `fullstack-developer`                                        | End-to-end TypeScript implementation: Next.js 16, React 19+, tRPC, Drizzle ORM, shadcn/ui. UI to database. |
| Agent   | `mobile-developer`                                           | Cross-platform mobile with React Native 0.82+, Expo SDK, iOS 18, and Android 15. Performance-first. |
| Agent   | `pr-test-analyzer`                                           | Reviews PR test coverage quality and completeness, emphasizing behavioral coverage and real bug prevention. |
| Agent   | `python-pro`                                                 | Expert Python 3.12+ developer: FastAPI, Polars, uv, ruff, mypy strict, full type coverage. |
| Agent   | `python-reviewer`                                            | Expert Python code reviewer for PEP 8, type hints, security, and Pythonic idioms. |
| Agent   | `react-reviewer`                                             | Expert React/JSX reviewer: hooks rules, RSC boundaries, accessibility, render performance, React security. |
| Agent   | `search-specialist`                                          | Web research with rigorous source evaluation, contradiction handling, and structured findings reports. |
| Agent   | `security-reviewer`                                          | Security vulnerability detection: OWASP Top 10, secrets, SSRF, injection, unsafe crypto. |
| Agent   | `silent-failure-hunter`                                      | Single-purpose reviewer for swallowed errors, dangerous fallbacks (`.catch(() => [])`), lost stack traces, and missing error propagation. |
| Agent   | `seo-strategist`                                             | Senior SEO/GEO strategist (Opus, no Write) — analyzes GSC exports, makes the call on what to build. Part of the `/seo:*` suite. |
| Agent   | `tdd-guide`                                                  | TDD specialist enforcing write-tests-first methodology. Ensures 80%+ test coverage. |
| Agent   | `technical-seo-auditor`                                      | Parses GSC exports → prioritized fix list + indexation coverage + CTR diagnostics. Part of the `/seo:*` suite. |
| Agent   | `type-design-analyzer`                                       | Analyzes type design for encapsulation, invariant expression, usefulness, and enforcement. |
| Agent   | `typescript-reviewer`                                        | Expert TypeScript/JavaScript reviewer: type safety, async correctness, Node/web security, idiomatic patterns. |
| Agent   | `ui-ux-designer`                                             | Research-driven senior UI/UX designer. Evidence-backed critique, WCAG 2.2 AA, anti-generic aesthetics. |

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
| `dev` | full dev toolkit — skills, engineering agents (incl. specialist reviewers), all git/react/python/code command namespaces |
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

`--mcp` reads `mcp-configs/registry.json` and prints, per curated server, the command and any
required env vars with where to get them. It never writes secrets and never auto-installs — copy
the servers you want from `mcp-configs/mcp.template.json` into a project `.mcp.json` or `~/.claude.json`.

Curated servers: `context7`, `playwright`, `github`, `sequential-thinking`, `exa-web-search`,
`omega-memory`, `shadcn` (project-conditional — only when `components.json` is present).

### What gets installed where

| Type | Installed to |
|------|-------------|
| Commands | `~/.claude/commands/{name}.md` |
| Namespaced commands (e.g. `/git:*`) | `~/.claude/commands/{namespace}/` (real dir, symlinked files inside) |
| Skills | `~/.claude/skills/{name}/` (directory symlink) |
| Agents | `~/.claude/agents/{name}.md` |
| Common rules | `~/.claude/rules/{name}.md` (symlink; pointer rule is a generated file) |
| Global hooks | merged into `~/.claude/settings.json`; scripts via `~/.claude/claude-config-hooks` → `hooks/` |

`README.md` files are never copied to `~/.claude/`. The language rules (`rules/typescript/`,
`rules/python/`, `rules/react/`, etc.) are intentionally **not** installed globally — the Claude
session applies them per-project.
