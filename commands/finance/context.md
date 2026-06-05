---
description: (herow) Manages financial restrictions/context that future analyses must respect.
allowed-tools: Bash, AskUserQuestion
argument-hint: "[<free text> | list | prune]"
---

# /finance:context — Restrictions and context (provider-agnostic)

> **GLOBAL RULE — questions to the user:** every question requiring a user response must be asked via the `AskUserQuestion` tool, with 2-4 structured options (the free-text "Other" field is automatic). **Never** ask questions inline in text.

Conversational wrapper over `commands/finance/scripts/memory.py`. Data lives in `~/finance/memory.md` and is injected into any analysis (Organizze and future providers) as directives that **the AI cannot contradict**.

Absolute path of the script:
`/Users/judson/sources/personal/claude-config/commands/finance/scripts/memory.py`

When the user invokes `/finance:context`, classify `$ARGUMENTS` and follow the flow. Do not pre-inspect the filesystem.

---

## Mode 1 — No args (manage)

1. List the 20 most recent:
   ```bash
   python3 /Users/judson/sources/personal/claude-config/commands/finance/scripts/memory.py list --recent 20
   ```

2. Show to the user and ask via `AskUserQuestion`:
   - **A) Add new restriction** — go to Mode 2 asking for the text.
   - **B) View all** — run `memory.py list`.
   - **C) Prune old entries (> 365d)** — run `memory.py prune --older-than 365`.
   - **D) Exit**.

## Mode 2 — Free text (register)

`$ARGUMENTS` contains a restriction or context (e.g.: "medication X is a prescription", "tithe is non-negotiable", "I can't reduce the house installment").

1. (Optional) Suggest an inferred `--tag` from the text (`health`, `home`, `tithe`, `subscription`, `debt`, `methodology`, ...) via `AskUserQuestion` with a "Skip" option.

2. Save:
   ```bash
   python3 /Users/judson/sources/personal/claude-config/commands/finance/scripts/memory.py add "<text>" [--tag <optional>]
   ```

3. Confirm in 1 line: what was saved and where (`~/finance/memory.md`). Say: "Next `/finance:organizze` will take this into account."

## Mode 3 — Direct sub-commands

| Argument               | Command                                          |
|------------------------|--------------------------------------------------|
| `list`                 | `memory.py list` (accepts `--recent N` extra)    |
| `prune`                | `memory.py prune --older-than 365` (or provided value) |

Show the output to the user.

---

## Rules

- **Do not call `/finance:organizze`** automatically. CRUD only.
- The script runs legacy migration automatically on the first run (`~/finance-organizze/memory.md` → `~/finance/memory.md`).
- Storage is hand-editable (`~/finance/memory.md`).
