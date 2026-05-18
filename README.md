# claude-config

Personal Claude Code configuration hub: custom slash commands and skills that travel with me across machines and projects.

## Structure

```
claude-config/
├── CLAUDE.md                    # global instructions Claude Code loads at session start
├── commands/                    # slash commands
│   ├── fix-conflicts/           → see commands/fix-conflicts/README.md
│   ├── graphify-install/        → see commands/graphify-install/README.md
│   └── release-notes/           → see commands/release-notes/README.md
└── skills/                      # skills
    └── github-ops/              → see skills/github-ops/README.md
```

## CLAUDE.md

[`CLAUDE.md`](./CLAUDE.md) holds the global instructions Claude Code reads at the start of every session — communication style, output hygiene, and the four working principles (think before coding, simplicity first, surgical changes, goal-driven execution).

## Contents

| Type    | Name                                                         | One-liner                                                                   |
|---------|--------------------------------------------------------------|-----------------------------------------------------------------------------|
| Command | [`/fix-conflicts`](./commands/fix-conflicts/README.md)       | Resolve merge conflicts on a PR or branch, grounding each decision in the commit history of both sides. |
| Command | [`/graphify-install`](./commands/graphify-install/README.md) | Bootstrap [graphify](https://github.com/safishamsi/graphify) inside any git repo end-to-end. |
| Command | [`/release-notes`](./commands/release-notes/README.md)       | Generate a user-friendly changelog (pt-br/en) from commits since the last tag, inline in the chat. |
| Skill   | [`github-ops`](./skills/github-ops/README.md)                | Token-efficient GitHub/GitLab ops via `gh`/`glab` with pipe-delimited output. |

Each command and skill has its own README with the full reference, examples, and rules.

## Installation

Clone somewhere stable (e.g. `~/sources/personal/claude-config`) and point Claude Code at it, or symlink individual items into `~/.claude/commands/` and `~/.claude/skills/` as needed.
