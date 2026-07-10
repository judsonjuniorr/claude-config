---
description: (herow) Creates entries in Organizze (account, card, invoice, transfer) with dry-run + confirmation + verification.
allowed-tools: Bash, Read, AskUserQuestion
argument-hint: "[<free text: 'spent 50 at the market yesterday'> | --conta X --cartao Y --fatura Z --parcelas N --recorrente --transferencia]"
effort: medium
---

# /finance:organizze-create — create an entry in Organizze

> **GLOBAL RULE — questions to the user:** every question requiring a user response must be asked via `AskUserQuestion`, with 2-4 structured options (the free-text "Other" field is automatic). **Never** ask questions inline in the text.

> **Safety spine (writing real money):** DRY-RUN is the default. No POST happens without `--apply`, and `--apply` is only passed **after** an Apply/Cancel confirmation via `AskUserQuestion`. Every creation is verified via read-back.

This is the **first write path** of the Organizze integration (everything else is read-only). The command parses natural language + asks questions; the `create.py` script is non-interactive and handles resolution by id + payload + POST + verify.

`SCRIPT="${CLAUDE_PLUGIN_ROOT}/scripts/organizze/create.py"`

## Script protocol (how to read the output)
- **stderr:** `info|<state>|...` (auth/resolve/category/duplicate/dry-run/payload/apply/verify), `err|<code>|<detail>`.
- **stdout:** `ok|created|<id>` or `ok|transfer|<id>` — only on an `--apply` that actually wrote.
- The token **never** appears (masked as `org…xxx`).

## Steps (follow exactly, skip none)

### 1. First-run / auth
If `~/finance/organizze/.auth` does not exist, **do not** run the script: it's the same `.auth` as `/finance:organizze` (read+write scope — no new credential needed). **Read `${CLAUDE_PLUGIN_ROOT}/resources/organizze-onboarding.md` and follow §Step 2 (token setup)** to create `.auth`. Stop here until `.auth` exists.

### 2. Intent parse (natural language → flags)
From `$ARGUMENTS`, extract whatever you can: description, amount, sign (spent/paid → `--despesa`; received/earned → `--receita`), relative date (yesterday/today/"day X"), target (on card X → `--cartao`; transfer from A to B → `--transferencia --de A --para B`), installments ("3x" → `--parcelas 3`), recurrence ("every month"/"fixed" → `--recorrente`). Whatever **cannot** be confidently inferred becomes a question in step 3 — never guess the amount, account, or sign.

### 3. Fill gaps via AskUserQuestion
For each essential field that's missing or ambiguous (target account/card, amount, income/expense sign, date), ask via `AskUserQuestion` with 2-4 options. If the script returns `err|resolve|<hint>` (account/card name not found or ambiguous) or `err|invoice-unresolved|<card>`, **turn it into an AskUserQuestion** with the list — never a dead end.

**Paid vs. pending:** for an entry with a **past or today's** date, ask "is it already paid?" via `AskUserQuestion` (Yes → `--paga`, No → `--nao-paga`). For a **future** date, the default is pending (don't ask). Without a flag, the script infers from the date (past/today = paid, future = pending).

### 4. DRY-RUN (always first)

> **SECURITY — free text never goes to the command line.** Description and notes may contain `` ` ``, `$(...)`, `;`, quotes (e.g., text pasted from a receipt). **Never** interpolate these fields directly into Bash. Use the **Write** tool to create a temporary JSON file and pass `--input-file`:
> ```json
> // /tmp/org-create.json — written via the Write tool, not by the shell
> { "description": "<user's free text>", "notes": "<optional note>" }
> ```
> Only the **structured** fields (amount, account, date, sign) go as flags — argparse type-coerces them.

Run the script **without** `--apply` with the resolved flags + the `--input-file`:
```bash
python3 "$SCRIPT" --input-file /tmp/org-create.json --conta "<conta>" --despesa --valor <v> --data <YYYY-MM-DD> --categoria "<cat>"
```
Read `info|resolve|...`, `info|category|...`, `info|dry-run|...`, and `info|payload|...`. If `info|installments|...` appears (installment amount semantics not verified) or `[APROXIMADA]` shows up in invoice resolution, **highlight it to the user**. Render a **human-readable summary** of the resolved target in full (e.g., "Nubank → July invoice", not "card 3 invoice 189") + amount + category. **Do not** dump raw JSON by default (offer the masked payload only if asked).

> **Transfer:** `--de` is the **source** account (where money leaves from) and `--para` is the **destination** (where it arrives) — the script maps these to `credit_account_id`/`debit_account_id` in the correct API direction. Confirm both accounts in the summary before Apply.

### Step 4.5 — Invalidate compute cache

After a successful write, delete the cached metrics so the next `/finance:organizze` run recomputes fresh values:

```bash
rm -f ~/finance/organizze/metrics.json
```

This ensures the next analysis reflects the new transaction. Silent if the file doesn't exist.

### 5. Duplicate warning
If `info|duplicate|...` appears, show the existing matching entry (id/date/amount) **before** the confirmation, so the user can decide whether it's a repeat.

### 6. Apply / Cancel confirmation
Ask via `AskUserQuestion`: **Apply** (create) or **Cancel**. Only on **Apply** run with `--apply` (and `--force` if the user confirmed creating despite a duplicate):
```bash
python3 "$SCRIPT" --apply [--force] <same flags as the dry-run>
```

### 7. Verification + success line
- On success, the script prints `ok|created|<id>` (or `ok|transfer|<id>`) and an `info|verify|ok id <id>`.
- Render the rich line to the user:
  `✅ Created: <description> R$ <amount> in <account | card→month invoice> [category] — id <id>`
- If `err|verify|...` comes back (it wrote but the read-back didn't match), show a **loud warning** — don't silently declare "ok".

## Error map (render problem + cause + fix)
- `err|no-auth|...` → "No credential. Set up the token: `resources/organizze-onboarding.md` §Step 2."
- `err|bad-auth|missing <k>` → "`.auth` file incomplete (missing `<k>`). Redo the token: `resources/organizze-onboarding.md` §Step 2."
- `err|duplicate|...` → "A matching recent entry already exists (shown above). Confirm creating it anyway → re-run with `--force`, or cancel."
- `err|http-401|...` → "Token rejected. Re-authenticate (delete `~/finance/organizze/.auth` and redo the setup)."
- `err|http-422|<body>` → show the Organizze message + the field; offer to reopen the field via AskUserQuestion.
- `err|resolve|<hint>` → "Couldn't find account/card '<hint>'." + AskUserQuestion with the list.
- `err|invoice-unresolved|<card>` → "Couldn't map the invoice for that date." + AskUserQuestion with the invoices.
- `err|validation|amount` → "Amount cannot be 0."
- `err|validation|installments-recurrence` → "Installments and recurrence are mutually exclusive — choose one."
- `err|validation|transfer-card` → "Transfer is only between bank accounts, not cards."
- `err|validation|periodicity` → "Invalid periodicity. Use: monthly, yearly, weekly, biweekly, bimonthly, trimonthly."
- `err|input-file|...` → "Failed to read the free-text JSON; rewrite the file via the Write tool."
- `err|network|...` → network failure; try again, no blind retry.

## Rules
- DRY-RUN is the default and is **always** shown before any write.
- `--apply` is the only path that writes, and only after Apply is confirmed.
- Every question goes through `AskUserQuestion`. User-facing messages are in English; protocol lines (`info|`/`ok|`/`err|`) remain machine-readable English.
- Do not pre-inspect (no `git status`/listing directories) — the script is self-contained.
