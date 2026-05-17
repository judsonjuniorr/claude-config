# claude-config

Personal Claude Code configuration hub: custom slash commands and skills that travel with me across machines and projects.

## Structure

```
claude-config/
├── CLAUDE.md                    # global instructions Claude Code loads at session start
├── commands/                    # slash commands
│   └── graphify-install.md      → see commands/README.md
└── skills/                      # skills
    └── github-ops/              → see skills/github-ops/README.md
```

## CLAUDE.md

[`CLAUDE.md`](./CLAUDE.md) holds the global instructions Claude Code reads at the start of every session — communication style, output hygiene, and the four working principles (think before coding, simplicity first, surgical changes, goal-driven execution).

## Contents

| Type    | Name                                                         | One-liner                                                                   |
|---------|--------------------------------------------------------------|-----------------------------------------------------------------------------|
| Command | [`/graphify-install`](./commands/README.md)                  | Bootstrap [graphify](https://github.com/) inside any git repo end-to-end.   |
| Skill   | [`github-ops`](./skills/github-ops/README.md)                | Token-efficient GitHub/GitLab ops via `gh`/`glab` with pipe-delimited output. |

Each command and skill has its own README with the full reference, examples, and rules.

## Installation

Clone somewhere stable (e.g. `~/sources/personal/claude-config`) and point Claude Code at it, or symlink individual items into `~/.claude/commands/` and `~/.claude/skills/` as needed.
