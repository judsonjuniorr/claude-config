# /file-organizer

Analyze a directory, surface duplicates and clutter, propose a tidy structure, and only after explicit approval move/rename files — every destructive action is logged so it can be reversed.

See [`file-organizer.md`](./file-organizer.md) for the full agent-facing procedure.

## What it does

1. Parses the target directory and aggressiveness (`conservative` default, `comprehensive` opt-in). Asks for protected paths and whether to scan for duplicates.
2. Inventories the tree (depth-limited): file types, sizes, date ranges, obvious clutter.
3. Optionally finds exact duplicates (md5/md5sum) and filename collisions — surfaces them, never auto-deletes.
4. Presents a written plan: folders to create, moves, renames, deletions, items needing a decision. Asks **Proceed / Modify / Cancel**.
5. Executes with `mv -n` (no clobber), preserving mtimes, writing every action to a timestamped log file inside the target.
6. Summarizes what changed, where the log lives, and suggested maintenance cadence.

## Frontmatter

- **description**: Analyze a directory, find duplicates, propose a tidy structure, and reorganize files only after explicit approval.
- **argument-hint**: `[target-directory] [conservative|comprehensive]`
- **allowed-tools**: Bash, Read, Write, Edit, Glob, Grep, AskUserQuestion

## Usage

```
/file-organizer ~/Downloads
/file-organizer ~/Documents/scans comprehensive
/file-organizer
```

## When to use

- The `Downloads/` folder has degenerated into chaos.
- A project directory needs a real structure before archiving.
- Disk space is tight and you suspect duplicates.
- You're about to back up or sync a tree and want to clean it first.

## Safety

- Never touches `/`, `$HOME` root, `~/Library`, `~/.config`, `~/.ssh`, or paths with a top-level `.git/` unless explicitly insisted on.
- Never deletes without per-batch confirmation. Prefers moving to a `_trash/` subfolder over `rm`.
- Every move/rename/delete is appended to `<target>/.file-organizer-YYYYMMDD-HHMMSS.log` as `ACTION\tSRC\tDST`, so the user can reverse changes with a one-liner.

## Prerequisites

- POSIX shell environment with `find`, `du`, `sort`, `awk`, and `md5`/`md5sum` available (any macOS or Linux setup qualifies).
