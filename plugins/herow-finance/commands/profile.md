---
description: (herow) Manages the personal profile (age, profession, income, family, housing, city, risk) that analyses use to personalize recommendations.
allowed-tools: Bash, AskUserQuestion
argument-hint: "[<free text> | init | list | get <key> | set <key> <value> | skip]"
model: haiku
effort: low
---

# /finance:profile — Personal profile (provider-agnostic)

> **GLOBAL RULE — questions to the user:** every question requiring a user response must be asked via the `AskUserQuestion` tool, with 2-4 structured options (the free-text "Other" field is automatic). **Never** ask questions inline in text.

Conversational wrapper over `${CLAUDE_PLUGIN_ROOT}/scripts/finance/profile.py`. Data lives in `~/finance/profile.md` (format `key: value`, hand-editable) and is injected into **every analysis** (`/finance:organizze` and future providers) as personal context — to calibrate recommendations by age, income, dependents, housing, city, risk tolerance.

Absolute path of the script:
`${CLAUDE_PLUGIN_ROOT}/scripts/finance/profile.py`

When the user invokes `/finance:profile`, classify `$ARGUMENTS` and follow the flow. Do not pre-inspect the filesystem.

---

## Profile fields

| Key                              | Type                                                                                  | Required |
|----------------------------------|---------------------------------------------------------------------------------------|:--------:|
| `idade`                          | integer                                                                               |   ✓      |
| `profissao`                      | free text                                                                             |   ✓      |
| `renda_liquida_mensal_cents`     | integer in cents (R$ 12,000.00 = `1200000`)                                           |   ✓      |
| `estado_civil`                   | `solteiro` \| `relacionamento` \| `casado` \| `divorciado` \| `viuvo`                 |   ✓      |
| `dependentes`                    | free text (e.g.: "none", "2 children (5 and 8 years old)", "spouse + dog")            |   ✓      |
| `moradia_tipo`                   | `propria_quitada` \| `propria_financiada` \| `alugada` \| `cedida` \| `outra`         |   ✓      |
| `moradia_custo_cents`            | integer in cents (mortgage installment or rent; `0` if gifted/paid off)               |   ✓      |
| `cidade`                         | free text (e.g.: "São Paulo, SP") — used in market research                           |   ✓      |
| `tolerancia_risco`               | `conservador` \| `moderado` \| `agressivo`                                            |   ✓      |
| `habitos`                        | free text, 1 line (e.g.: "works out 4x/week, home office")                           |          |
| `objetivo_principal`             | free text, 1 line (current financial focus)                                           |          |

---

## Mode 1 — No args (manage)

1. Show the current profile:
   ```bash
   python3 ${CLAUDE_PLUGIN_ROOT}/scripts/finance/profile.py get
   ```

2. List missing fields:
   ```bash
   python3 ${CLAUDE_PLUGIN_ROOT}/scripts/finance/profile.py missing
   ```

3. Ask via `AskUserQuestion` what to do:
   - **A) Fill in missing fields now** — go to Mode 4 (interview).
   - **B) Update a specific field** — ask which one + new value, run `profile.py set <key> <value>`.
   - **C) Start a full interview from scratch** — go to Mode 4.
   - **D) Silence questions for 7 days** — run `profile.py mark-skip`.
   - **E) Exit**.

## Mode 2 — Free text (register)

`$ARGUMENTS` contains a phrase like "I'm 32, a developer, earn 12k". Extract what you can and save field by field with `profile.py set`. For anything that can't be inferred with certainty, **don't guess** — ask via `AskUserQuestion` or leave it for next time.

For monetary values in phrases ("12k", "R$ 12,000", "12 thousand") convert to cents before saving.

## Mode 3 — Direct sub-commands

| Argument                        | Command                                                |
|---------------------------------|--------------------------------------------------------|
| `list` or `get`                 | `profile.py get` (lists everything)                    |
| `get <key>`                     | `profile.py get <key>`                                 |
| `set <key> <value>`             | `profile.py set <key> <value>`                         |
| `missing`                       | `profile.py missing`                                   |
| `skip`                          | `profile.py mark-skip` (silences for 7d)               |
| `init`                          | go to Mode 4                                           |

## Mode 4 — Interview (init or missing fields)

For each key to ask (all in `init`; only the ones from `missing` when called by `/finance:organizze`), use `AskUserQuestion` with the appropriate format and **always include a "Skip" option**.

**Format suggestions by field:**

- `idade`: open question ("How old are you?"), accept numeric answer.
- `profissao`: open question ("What is your profession / how do you earn money?").
- `renda_liquida_mensal_cents`: open question ("What is your average net monthly income in R$?"). Convert to cents.
- `estado_civil`: options `solteiro / relacionamento / casado / divorciado / viuvo` + Skip.
- `dependentes`: open question ("Do you have dependents? How many and their ages, or 'none'").
- `moradia_tipo`: options `owned (paid off) / owned (mortgaged) / rented / provided / other` + Skip. (Map option text to enum: "owned (paid off)" → `propria_quitada`, "owned (mortgaged)" → `propria_financiada`, "rented" → `alugada`, "provided" → `cedida`, "other" → `outra`.)
- `moradia_custo_cents`: open question ("How much do you pay for housing per month (installment or rent) in R$? Use 0 if zero"). Convert to cents.
- `cidade`: open question ("What city/state do you live in? E.g.: 'São Paulo, SP'").
- `tolerancia_risco`: options `conservador / moderado / agressivo` + Skip. Include a short description of each.
- `habitos` (optional): open question ("Any relevant habits/context? E.g.: 'work out 4x/week, home office, travel a lot'").
- `objetivo_principal` (optional): open question ("What is your main financial focus right now? E.g.: 'pay off credit card', 'build emergency fund', 'buy a car'").

For each valid answer, save immediately:
```bash
python3 ${CLAUDE_PLUGIN_ROOT}/scripts/finance/profile.py set <key> "<value>"
```

If the user skips **all** fields, run `profile.py mark-skip` (silences for 7 days).

At the end, show the updated state with `profile.py get` and say: "Next `/finance:organizze` will take this into account."

---

## Rules

- **Do not call `/finance:organizze`** automatically. This command is CRUD; analysis is separate.
- The script runs legacy migration automatically on the first run.
- Storage is hand-editable (`~/finance/profile.md`).
- **Per-session limit**: if called by `/finance:organizze` during the interview flow, ask at most **6 fields** per turn to avoid fatigue. The rest will be asked on the next run.
- **Monetary conversion**: user says "12k" → save `1200000`. User says "R$ 1,200.50" → save `120050`. Confirm in 1 line before saving when the value is ambiguous.
