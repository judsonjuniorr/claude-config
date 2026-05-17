# claude-config

Personal Claude Code configuration hub: custom slash commands and skills that travel with me across machines and projects.

## Structure

```
claude-config/
├── commands/                    # slash commands
│   └── graphify-install.md      → see commands/README.md
└── skills/                      # skills
    └── github-ops/              → see skills/github-ops/README.md
```

## Contents

| Type    | Name                                                         | One-liner                                                                   |
|---------|--------------------------------------------------------------|-----------------------------------------------------------------------------|
| Command | [`/graphify-install`](./commands/README.md)                  | Bootstrap [graphify](https://github.com/) inside any git repo end-to-end.   |
| Skill   | [`github-ops`](./skills/github-ops/README.md)                | Token-efficient GitHub/GitLab ops via `gh`/`glab` with pipe-delimited output. |

Each command and skill has its own README with the full reference, examples, and rules.

## Installation

Clone somewhere stable (e.g. `~/sources/personal/claude-config`) and point Claude Code at it, or symlink individual items into `~/.claude/commands/` and `~/.claude/skills/` as needed.
