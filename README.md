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
│   ├── fix-conflicts/           → see commands/fix-conflicts/README.md
│   ├── graphify-install/        → see commands/graphify-install/README.md
│   └── release-notes/           → see commands/release-notes/README.md
├── skills/                      # skills
│   └── github-ops/              → see skills/github-ops/README.md
└── agents/                      # subagents
    └── financial-analyst/       → see agents/financial-analyst/README.md
```

## CLAUDE.md

[`CLAUDE.md`](./CLAUDE.md) holds the global instructions Claude Code reads at the start of every session — communication style, output hygiene, and the four working principles (think before coding, simplicity first, surgical changes, goal-driven execution).

## Contents

| Type    | Name                                                         | One-liner                                                                   |
|---------|--------------------------------------------------------------|-----------------------------------------------------------------------------|
| Command | [`/finance:organizze`](./commands/finance/README.md#financeorganizze) | Pull personal finance data from Organizze via REST API, build a snapshot, delegate to the `financial-analyst` subagent for a prioritized action plan. |
| Command | [`/fix-conflicts`](./commands/fix-conflicts/README.md)       | Resolve merge conflicts on a PR or branch, grounding each decision in the commit history of both sides. |
| Command | [`/graphify-install`](./commands/graphify-install/README.md) | Bootstrap [graphify](https://github.com/safishamsi/graphify) inside any git repo end-to-end. |
| Command | [`/release-notes`](./commands/release-notes/README.md)       | Generate a user-friendly changelog (pt-br/en) from commits since the last tag, inline in the chat. |
| Skill   | [`github-ops`](./skills/github-ops/README.md)                | Token-efficient GitHub/GitLab ops via `gh`/`glab` with pipe-delimited output. |
| Agent   | [`financial-analyst`](./agents/financial-analyst/README.md)  | Personal finance analyst subagent — consumes pre-built snapshots, respects user memory, outputs prioritized action plans. |

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
