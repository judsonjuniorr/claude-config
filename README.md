# claude-config

Personal Claude Code configuration hub: custom slash commands and skills that travel with me across machines and projects.

## Structure

```
claude-config/
├── CLAUDE.md                    # global instructions Claude Code loads at session start
├── commands/                    # slash commands
│   ├── finance/                 → see commands/finance/README.md
│   │   ├── organizze.md         → /finance:organizze command file
│   │   └── organizze-scripts/   → scripts used by /finance:organizze
│   ├── file-organizer/          → see commands/file-organizer/README.md
│   ├── fix-conflicts/           → see commands/fix-conflicts/README.md
│   ├── generate-tests/          → see commands/generate-tests/README.md
│   ├── graphify-install/        → see commands/graphify-install/README.md
│   ├── refactor-code/           → see commands/refactor-code/README.md
│   └── release-notes/           → see commands/release-notes/README.md
├── skills/                      # skills
│   └── github-ops/              → see skills/github-ops/README.md
└── agents/                      # subagents
    ├── backend-architect.md     → /agent backend-architect
    ├── code-reviewer.md         → /agent code-reviewer
    ├── debugger.md              → /agent debugger
    ├── financial-analyst/       → see agents/financial-analyst/README.md
    ├── fullstack-developer.md   → /agent fullstack-developer
    ├── mobile-developer.md      → /agent mobile-developer
    ├── python-pro.md            → /agent python-pro
    ├── search-specialist.md     → /agent search-specialist
    └── ui-ux-designer.md        → /agent ui-ux-designer
```

## CLAUDE.md

[`CLAUDE.md`](./CLAUDE.md) holds the global instructions Claude Code reads at the start of every session — communication style, output hygiene, and the four working principles (think before coding, simplicity first, surgical changes, goal-driven execution).

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
| Skill   | [`github-ops`](./skills/github-ops/README.md)                | Token-efficient GitHub/GitLab ops via `gh`/`glab`. Conventional Commits, pre-commit checks, split detection, PR/issue/CI management. |
| Agent   | [`backend-architect`](./agents/backend-architect.md)         | Produces architecture documents: OpenAPI specs, database schemas, event schemas, diagrams, and trade-off analyses. Design only — not implementation. |
| Agent   | [`code-reviewer`](./agents/code-reviewer.md)                 | Senior code reviewer focused on security, correctness, and performance. Detects the project's package manager automatically. |
| Agent   | [`debugger`](./agents/debugger.md)                           | Systematic fault-localization debugger. No fix without root cause. Writes a regression test for every bug fixed. |
| Agent   | [`financial-analyst`](./agents/financial-analyst/README.md)  | Personal finance analyst subagent — consumes pre-built snapshots, respects user memory, outputs prioritized action plans. |
| Agent   | [`fullstack-developer`](./agents/fullstack-developer.md)     | End-to-end TypeScript implementation: Next.js 16, React 19+, tRPC, Drizzle ORM, shadcn/ui. UI to database. |
| Agent   | [`mobile-developer`](./agents/mobile-developer.md)           | Cross-platform mobile with React Native 0.82+, Expo SDK, iOS 18, and Android 15. Performance-first. |
| Agent   | [`python-pro`](./agents/python-pro.md)                       | Expert Python 3.12+ developer: FastAPI, Polars, uv, ruff, mypy strict, full type coverage. |
| Agent   | [`search-specialist`](./agents/search-specialist.md)         | Web research with rigorous source evaluation, contradiction handling, and structured findings reports. |
| Agent   | [`ui-ux-designer`](./agents/ui-ux-designer.md)               | Research-driven senior UI/UX designer. Evidence-backed critique, WCAG 2.2 AA, anti-generic aesthetics. |

Each command, skill and agent has its own README with the full reference, examples, and rules.

## Installation

```bash
git clone https://github.com/judsonjuniorr/claude-config ~/sources/personal/claude-config
~/sources/personal/claude-config/install.sh
```

`install.sh` discovers all commands, skills, and agents and lets you pick what to install. Symlinks are the default — edits in the repo reflect immediately in Claude Code without reinstalling.

### Options

| Flag | Description |
|------|-------------|
| `--all` | Install everything without prompting (useful on a new machine) |
| `--replace` | Overwrite existing files instead of creating `.bak` backups |
| `--help` | Show usage |
| `uninstall` | Interactively remove installed assets |

### Selection UI

- **With [fzf](https://github.com/junegunn/fzf):** multi-select list (Space to mark, Enter to confirm)
- **Without fzf / bash < 4:** numbered menu, enter space-separated numbers or `all`

Assets already installed are shown as `[installed]`. Symlinks point to the cloned repo — don't move it after installing.

### What gets installed where

| Type | Installed to |
|------|-------------|
| Commands | `~/.claude/commands/{name}.md` |
| Namespaced commands (e.g. `/finance:*`) | `~/.claude/commands/{namespace}/` (real dir, symlinked files inside) |
| Skills | `~/.claude/skills/{name}/` (directory symlink) |
| Agents | `~/.claude/agents/{name}.md` |

`README.md` files are never copied to `~/.claude/`.
