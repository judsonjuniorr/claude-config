---
description: Manages financial goals (savings/economy targets) consumed by any analysis provider.
allowed-tools: Bash, AskUserQuestion
argument-hint: "[<free text> | list | done <ts> | pause <ts> | cancel <ts> | activate <ts> | prune]"
---

# /finance:goal — Financial goals (provider-agnostic)

> **GLOBAL RULE — questions to the user:** every question requiring a user response must be asked via the `AskUserQuestion` tool, with 2-4 structured options (the free-text "Other" field is automatic). **Never** ask questions inline in text.

Conversational wrapper over `commands/finance/scripts/plans.py`. Data lives in `~/finance/plans.md` and is consumed by `/finance:organizze` (and future providers) automatically.

Absolute path of the script:
`/Users/judson/sources/personal/claude-config/commands/finance/scripts/plans.py`

When the user invokes `/finance:goal`, **classify `$ARGUMENTS`** and follow the corresponding flow. Do not pre-inspect the filesystem.

---

## Mode 1 — No args (manage)

1. List active goals:
   ```bash
   python3 /Users/judson/sources/personal/claude-config/commands/finance/scripts/plans.py list --status active
   ```
2. Show the output to the user (brief, 1 line per goal) and ask via `AskUserQuestion` what to do:
   - **A) Add new goal** — go to Mode 2 asking for the text.
   - **B) Mark one as done** — ask for the `ts` (full header) and run `plans.py done "<ts>"`.
   - **C) Pause / cancel / reactivate** — ask for `ts` and new status, run `plans.py status "<ts>" paused|cancelled|active`.
   - **D) View full history (including done/cancelled)** — run `plans.py list` without filter.
   - **E) Prune old completed goals** — run `plans.py prune --older-than-done 365`.
   - **F) Exit**.

## Mode 2 — Free text (register)

`$ARGUMENTS` contains the description of a new goal (e.g.: "save R$ 5000 for a trip in December").

1. **Pre-fill what can be inferred from the text** (amount, deadline, account). Ask only what's missing via `AskUserQuestion` (each with "Skip" when optional):
   - **Target amount (R$)** — required. Range ("9~12k") → propose the average. Convert to cents.
   - **Deadline (YYYY-MM-DD)** — optional. "December" → last day of the mentioned month. "June/July this year" → last mentioned month.
   - **Destination account** — optional. Free text.
   - **Priority** — `negociavel` (default — pauses on a critical day) or `inegociavel` (holds by cutting other categories).

2. Save:
   ```bash
   python3 /Users/judson/sources/personal/claude-config/commands/finance/scripts/plans.py add "<text>" \
     --target-cents <N> \
     [--deadline <YYYY-MM-DD>] \
     [--account "<text>"] \
     [--priority negociavel|inegociavel]
   ```

3. Confirm in 1-2 lines: what was registered and where (`~/finance/plans.md`). Say: "Next `/finance:organizze` will take this into account."

## Mode 3 — Direct sub-commands

If `$ARGUMENTS` starts with one of the words below, pass directly to the script:

| Argument                 | Command                                                            |
|--------------------------|--------------------------------------------------------------------|
| `list`                   | `plans.py list` (accepts `--status` / `--recent` extras)          |
| `done <ts>`              | `plans.py done "<ts>"`                                             |
| `pause <ts>`             | `plans.py status "<ts>" paused`                                    |
| `cancel <ts>`            | `plans.py status "<ts>" cancelled`                                 |
| `activate <ts>`          | `plans.py status "<ts>" active`                                    |
| `prune`                  | `plans.py prune --older-than-done 365` (or uses provided `--older-than-done`) |

Show the script output to the user.

---

## Rules

- **Do not call `/finance:organizze`** automatically. This command is CRUD; analysis is separate.
- The script runs legacy migration automatically (`~/finance-organizze/` → `~/finance/`) on the first run. No manual action needed.
- Storage is hand-editable (`~/finance/plans.md`).
