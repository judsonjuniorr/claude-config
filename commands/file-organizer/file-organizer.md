---
description: Analyze a directory, find duplicates, propose a tidy structure, and reorganize files only after explicit approval.
argument-hint: "[target-directory] [conservative|comprehensive]"
allowed-tools: Bash, Read, Write, Edit, Glob, Grep, AskUserQuestion
---

# File Organizer

Reorganize the directory specified in `$ARGUMENTS` (or asked for at Step 1) by understanding its current state, surfacing duplicates and clutter, proposing a structure, and only then moving files — every destructive action gated by user approval.

**Core principle:** No file is moved, renamed, or deleted before the user sees the plan and confirms. Every change is logged so it can be reversed.

## Step 1 — Parse arguments and scope the job

- First token: target directory (absolute or relative). If missing, ask via `AskUserQuestion` with sensible candidates (`~/Downloads`, `~/Documents`, current directory).
- Second token (optional): aggressiveness — `conservative` (only obvious wins, never delete) or `comprehensive` (group by type/date, dedupe with confirmation, archive stale items). Default: `conservative`.
- Resolve `~` and verify the directory exists and is writable. Refuse to operate on `/`, `$HOME`, or any path containing a `.git/` at its root unless the user explicitly insists.

Then ask via `AskUserQuestion`:
1. **Main problem** — can't find things / duplicates / no structure / pre-archive cleanup / other.
2. **Protected paths** — folders or files to leave untouched (e.g. active projects, secrets, sync clients like `Dropbox/`, `iCloud Drive/`).
3. **Dedupe?** — whether to scan for duplicates this run.

## Step 2 — Analyze current state

Run the following and summarize results inline. Use `find -maxdepth` to keep large trees bounded (depth 3 by default; ask before going deeper than 5).

```bash
# Top-level overview
ls -la "$TARGET"

# File-type breakdown (extensions)
find "$TARGET" -maxdepth 3 -type f 2>/dev/null \
  | sed 's/.*\.//' | sort | uniq -c | sort -rn | head -20

# Largest items
du -sh "$TARGET"/* 2>/dev/null | sort -rh | head -20

# Date ranges (oldest / newest)
find "$TARGET" -maxdepth 3 -type f -printf '%T@ %p\n' 2>/dev/null \
  | sort -n | awk 'NR==1 || END' 
```

On macOS, substitute `stat -f` for `-printf` when needed. Report:
- Total files / folders / size.
- Type distribution (top 10 extensions).
- Largest offenders.
- Date span and obvious clutter (e.g. `*.dmg`, `*-final-v2 (1).pdf`, `Untitled*`).

## Step 3 — Find duplicates (only if user opted in)

```bash
# Exact duplicates by hash (md5 on macOS, md5sum on Linux)
find "$TARGET" -type f -size +0 2>/dev/null \
  | xargs -I{} sh -c 'md5 -r "{}" 2>/dev/null || md5sum "{}"' \
  | sort | awk '{print $1}' | uniq -d \
  | while read h; do
      echo "--- $h ---"
      find "$TARGET" -type f -exec sh -c 'h2=$(md5 -r "$1" 2>/dev/null | cut -d" " -f1 || md5sum "$1" | cut -d" " -f1); [ "$h2" = "'$h'" ] && echo "$1"' _ {} \;
    done

# Filename collisions across directories
find "$TARGET" -type f -printf '%f\n' 2>/dev/null | sort | uniq -d
```

For each duplicate set, list every path with size and `mtime`, recommend which to keep (newest, best-named, in the most "canonical" location), and stop. **Do not delete anything in this step.**

## Step 4 — Propose an organization plan

Present a plan in a single message before touching the filesystem:

```markdown
# Organization Plan for <TARGET>

## Current state
- N files across M folders, total size S
- Top types: …
- Issues: …

## Proposed structure
<TARGET>/
├── Documents/
├── Images/
├── Archives/
├── Projects/
└── Archive/

## Changes
1. Create folders: …
2. Move:
   - X PDFs → Documents/
   - Y images → Images/
   - Z stale files (mtime > 6 months) → Archive/
3. Rename (pattern: YYYY-MM-DD-<slug>.<ext>): …
4. Delete (duplicates, confirmed above): …

## Items needing your decision
- file-a.pdf — unclear which folder
- folder-b/ — looks active, leave it?
```

Then ask via `AskUserQuestion`: **Proceed / Modify plan / Cancel**.

## Step 5 — Execute (only after explicit approval)

Run a single dry-run pass first, writing planned actions to a log file alongside the target:

```bash
LOG="$TARGET/.file-organizer-$(date +%Y%m%d-%H%M%S).log"
mkdir -p "$TARGET/Documents" "$TARGET/Images" …   # create new structure
# For each move, log first then execute
echo "MOVE\t$src\t$dst" >> "$LOG"
mv -nv "$src" "$dst"                              # -n: never overwrite
```

Rules:
- `mv -n` (no clobber). On collision, append `-1`, `-2`, … and log the renaming.
- Preserve modification times — never `touch` after moving.
- Deletions: only files the user explicitly confirmed in Step 4. Prefer moving to a `_trash/` subfolder over `rm`. If `rm` is unavoidable, ask one more time per batch.
- If anything unexpected appears mid-run (permission denied, symlink loop, mountpoint, `.git/` directory), stop and report.

## Step 6 — Summarize and hand off

Report:
- Folders created.
- Files moved (count per destination).
- Bytes freed (only if dedupe deletions happened).
- Path to the log file (so the user can reverse changes manually if needed).
- Suggested maintenance cadence: weekly sort of new arrivals, monthly review, quarterly dedupe scan, yearly archive sweep.

If the user wants to repeat on another directory, restart at Step 1.

## Safety rules (apply at every step)

- Never operate on `/`, `$HOME` root, `~/Library`, `~/.config`, `~/.ssh`, or any path with a top-level `.git/` unless explicitly insisted on.
- Never delete without explicit per-batch confirmation.
- Never touch paths listed as "protected" in Step 1.
- Every move/rename/delete is appended to the log file with a tab-separated `ACTION\tSRC\tDST` line, so the user can `awk` it back into an undo script.
