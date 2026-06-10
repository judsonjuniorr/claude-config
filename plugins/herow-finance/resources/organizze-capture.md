# organizze — profile fill & post-analysis capture

On-demand resource for `/finance:organizze`. Three independent sub-flows, read from the
main command at their respective points: **§Step 2.8** before the pull (fill missing
profile fields), **§Step 6.5** after analysis (capture new memory/goal), **§Step 6.6**
after analysis (answer the subagent's open questions). The GLOBAL RULE (ask via
`AskUserQuestion`, never inline) and the main command's `**Absolute paths**` apply here.
The profile field list below is the shared copy — `/finance:profile` Mode 4 references it.

## Step 2.8 — Fill in missing personal profile fields

Recommendation personalization depends on the profile in `~/finance/profile.md` (age, profession, income, family, housing, city, risk tolerance). If a critical field is empty, the subagent will emit `[QUESTION]` at the end — better to fill it before analysis.

1. Check whether to ask now:
   ```bash
   python3 ${CLAUDE_PLUGIN_ROOT}/scripts/finance/profile.py should-ask
   ```
   - Exit code 1 → profile is complete OR silenced (`last_skip` < 7d). Skip to Step 3.
   - Exit code 0 → there are missing fields and it's not silenced. Continue.

2. List missing fields:
   ```bash
   MISSING=$(python3 ${CLAUDE_PLUGIN_ROOT}/scripts/finance/profile.py missing)
   ```

3. For each field in `$MISSING` (limit **6 questions per run** — the rest will be asked next time):
   - Use `AskUserQuestion` with the format appropriate for the field (single-select with enum + "Skip" for `estado_civil`, `moradia_tipo`, `tolerancia_risco`; open text for the rest).
   - Suggested questions per field (identical to Mode 4 of `/finance:profile`):
     - `idade`: "How old are you?"
     - `profissao`: "What is your profession / how do you earn money?"
     - `renda_liquida_mensal_cents`: "What is your average net monthly income in R$?" → convert to cents.
     - `estado_civil`: options `solteiro / relacionamento / casado / divorciado / viuvo` + Skip.
     - `dependentes`: "Do you have dependents? How many and their ages, or 'none'."
     - `moradia_tipo`: options `owned (paid off) / owned (mortgaged) / rented / provided / other` + Skip. Map option text to enum: "owned (paid off)" → `propria_quitada`, "owned (mortgaged)" → `propria_financiada`, "rented" → `alugada`, "provided" → `cedida`, "other" → `outra`.
     - `moradia_custo_cents`: "How much do you pay for housing per month (installment or rent) in R$? Use 0 if zero." → convert to cents.
     - `cidade`: "What city/state do you live in? E.g.: 'São Paulo, SP'." — used in market research.
     - `tolerancia_risco`: options `conservador / moderado / agressivo` + Skip. Include a short description of each.
   - For each valid answer (not "Skip"), save immediately:
     ```bash
     python3 ${CLAUDE_PLUGIN_ROOT}/scripts/finance/profile.py set <key> "<value>"
     ```

4. If the user skipped **all** the fields asked, save a 7-day silence:
   ```bash
   python3 ${CLAUDE_PLUGIN_ROOT}/scripts/finance/profile.py mark-skip
   ```

5. Proceed to Step 3 (Pull). The updated profile will be included in the Step 5 prompt.

## Step 6.5 — Capture new memory/goal (optional)

After analysis, offer to register new context/goals. Each block is independent; skip if the user has nothing.

**6.5a — Memory/restriction** — ask via `AskUserQuestion` (single-select with "Skip"):

> Do you want to register any restriction or context for future analyses? Examples: "I can't reduce the house installment", "medication X is a prescription", "tithe is non-negotiable".

If there is a response, save:

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/scripts/finance/memory.py add "<user text>" [--tag <optional>]
```

(Or tell the user they can run `/finance:context` later.)

**6.5b — Financial goal** — ask via `AskUserQuestion` (single-select with "Skip"):

> Do you want to register a financial goal? E.g.: "save R$ 5000 for a trip in December", "pay off debt X by June", "build an emergency fund of R$ 20000".

If there is a response, ask short follow-up questions in sequence (each with "Skip" when optional):

1. **Descriptive text**: already captured.
2. **Target amount (R$)**: ask and convert to cents (e.g.: `5000` → `500000`).
3. **Deadline (YYYY-MM-DD)**: optional. "December" → last day of the mentioned month.
4. **Destination account**: optional. Show list of main accounts + caixinhas from the snapshot.
5. **Priority**: `negociavel` (default) or `inegociavel`.

Save:

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/scripts/finance/plans.py add "<text>" \
  --target-cents <N> \
  [--deadline <YYYY-MM-DD>] \
  [--account "<name>"] \
  [--priority negociavel|inegociavel]
```

(Or tell the user they can run `/finance:goal` later.)

Memory and goals live in `~/finance/{memory,plans}.md` — provider-agnostic. `analyze.py` injects them automatically into future analyses. To manage outside the analysis flow: `/finance:context` and `/finance:goal`.

## Step 6.6 — Answer open questions from the subagent

The subagent emits up to 3 questions at the end of the report, in the exact format `[QUESTION] <text>` (one per line, no hyphen/bullet prefix). Capture them and bring them to the user.

1. Parse `$REPORT` saved in Step 6 — tolerate bullet/hyphen/indentation the subagent may add:
   ```bash
   QUESTIONS=$(grep -oE '\[QUESTION\][^[:cntrl:]]*' "$REPORT" | sed 's/^\[QUESTION\][[:space:]]*//')
   ```

2. If empty (or contains only `(no open questions)`), skip to Step 7.

3. For each question (max 3), use `AskUserQuestion` (single-select with "Skip"):
   - Question header: derive 1-2 words from the content (e.g.: "Emergency fund", "Phone plan", "External debt").
   - Options: 2-3 reasonable answers when inferable (e.g.: for "is this subscription essential?", offer "Yes — keep / No — can cut / Depends — explain"); otherwise, open format.
   - "Skip" always available.

4. For each valid response (not "Skip"), save to memory:
   ```bash
   python3 ${CLAUDE_PLUGIN_ROOT}/scripts/finance/memory.py add "<question + condensed answer>" --tag <derived tag>
   ```
   - Example tags: `subscription`, `debt`, `home`, `transport`, `goal`.

5. Confirm in 1 line: "N memories saved — next `/finance:organizze` will take them into account." **Do not re-invoke the subagent** in this turn.
