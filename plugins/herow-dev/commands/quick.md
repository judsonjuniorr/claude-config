---
description: (herow) End-to-end gstack pipeline for a simple change (worktree → autoplan → implement → review → qa → ship)
argument-hint: <short description of the change>
effort: medium
---

## Model check (1M context)

The real blocker isn't the *tier* (Sonnet vs Opus) but **1M context**: the 1M toggle is session-global and inherited by commands/subagents. This command **does not pin a model** — it inherits the session's default model; in a 1M session it runs as `<model>[1m]` and fails with `API Error: Usage credits required for 1M context` if there are no credits. Detect this by the `[1m]` suffix:

```bash
python3 -c "
import json, os
model = os.environ.get('CLAUDE_MODEL', '')
if not model:
    try:
        s = json.load(open(os.path.expanduser('~/.claude/settings.json')))
        model = s.get('model') or ''
    except: model = ''
print(model)
" 2>/dev/null
```

- If the output **ends in `[1m]`** (e.g. `claude-sonnet-4-6[1m]`): the session is in 1M context (billed). Warn in 1 line that this invocation inherits 1M and will fail for lack of credits, and offer the two paths:
  - **Switch to standard context** (recommended for this command — runs without credits): `/model` → pick a **non-`[1m]`** model, or restart already running the task (replace `<description>` with the actual argument resolved above):

    ```
    claude --model claude-sonnet-4-6 "/herow-dev:quick <description>"
    ```
  - **Keep 1M** (only if the work genuinely needs Opus + 1M): run `/usage-credits` to turn on credits.
- If the output is **empty/indeterminate**: **don't warn** (fail open — the check is advisory only; most correct sessions land here).
- Otherwise (standard-context model): proceed without warning.

> Don't block in any case. This command does not pin a model in the frontmatter — it inherits the session's default model; in standard context it runs normally. The warning above only matters when the session is in 1M.

---

You are going to execute a small/medium change end-to-end using the gstack pipeline. The change description is:

**$ARGUMENTS**

## Execution rules

1. **Don't stop to ask** unless the request is genuinely ambiguous (multiple incompatible interpretations). For minor doubts, make the reasonable call and proceed.
2. **Auto-fix on failures:** if `/review` or `/qa` find issues, fix them automatically and re-run the step until it passes (max 3 attempts per step; if exceeded, stop and report).
3. **Don't skip steps.** Order matters to avoid rework.
4. **All development happens in an isolated worktree** (see below) — never edit the main working tree.

## Language of generated artifacts

All generated code, comments, commit messages, and documentation must be in English, even when the blueprint, questions, or user input are in Portuguese — unless the user explicitly requests otherwise.

## graphify integration (search/exploration)

gstack skills don't use graphify on their own — you're responsible for that:

- **Exploration:** when you need to understand the code before changing it, if `graphify-out/graph.json` exists, **prefer `graphify query "<question>"`** (scoped subgraph) over broad grep/reading. If it doesn't exist and the repo is large, offer to bootstrap it with `/herow-extras:graphify-install` (once per repo).
- **After implementing:** run `graphify update .` (AST-only, no API cost) in the worktree to keep the graph in sync with the new code.

## Worktree isolation (mandatory)

Implementation, `/review`, `/qa`, and `/ship` all run in a **dedicated git worktree** at `.claude/worktree/<slug>`, never in the main working tree.

1. **Base branch = the repository's current branch.** Capture it before anything else: `git rev-parse --abbrev-ref HEAD`. The PR will be opened against it. **If the base is ambiguous** (detached HEAD, or `git rev-parse` doesn't return a named branch), use `AskUserQuestion` to confirm the base branch — offer the detected branch/`main` as the recommended option.
2. **Slug + type (Conventional Commits).** Kebab-case slug from the description (max 40 chars). `<type>` inferred from the description: `feat` (new feature), `fix` (fix), `refactor`, `chore`, `docs`.
3. **Ensure `.claude/worktree/` is in the repo's `.gitignore`** (add the line if missing) — the worktree isn't versioned.
4. **Create the worktree:** `git worktree add .claude/worktree/<slug> -b <type>/<slug> <base-branch>`. If the worktree or branch already exist, **stop** and warn — another execution may be in progress.
5. **`cd` into `.claude/worktree/<slug>`** and do all the implementation there.

## Mandatory sequence

1. **Quick planning** — invoke `/autoplan` with the description above (can run on the main tree). Surface only critical decisions (don't ask about obvious things).
2. **Worktree** — carry out the "Worktree isolation" section above and enter the worktree.
3. **Implementation** — execute the plan. Use graphify to explore (see above) and the appropriate subagent (`fullstack-developer`, `python-pro`, `mobile-developer`, etc.) depending on the stack touched. When done, run `graphify update .`.
4. **Review** — run `/review`. Apply auto-fixes. Re-run until zero critical findings.
5. **QA** — run `/qa` pointing at the detected local/staging environment. Fix bugs found. Re-run until it passes.
6. **Pre-push validation gate** — before shipping, the project must be **100% green**. The canonical steps, anti-cheat forbidden list, and pre-existing-failure policy live in **`${CLAUDE_PLUGIN_ROOT}/reference/pre-push-gate.md`** — read it; the terse checklist is inlined here so you can act without chasing the link. In the worktree, detecting the commands from the stack (`package.json`/`Makefile`/`pyproject.toml`/`pom.xml`/`go.mod`/etc.), run in order:
   - **Lint with auto-fix** (`eslint --fix`, `biome check --write`, `ruff --fix`) — commit the auto-fixes → **Type-check** if present (`tsc --noEmit`, `mypy`) → **Tests** (`vitest run`, `pytest`, …) → **Build** (`next build`, `vite build`, …).
   - Each step that **exists must pass 100%**; skip + log any absent step — **never fake one green** (no `--passWithNoTests`). Fix and re-run failures (max 3 cycles per step).
   - **Anti-cheat (load-bearing):** fix the real problem — **never** skip/delete/disable tests, append `|| true`, add blanket `eslint-disable`/`# type: ignore`/`@ts-nocheck`, or push with `--no-verify`. Pre-existing (untouched-file) failures must also be fixed to reach 100%, in a **separate labeled commit** `chore: fix pre-existing gate failures`; if large/unrelated, **stop and report** instead.
   - If the gate can't be made honestly green in ≤3 cycles per step, **stop — do not run `/ship`**.
   - > `/ship` is an external gstack skill this repo can't gate directly; running this gate **before** `/ship` is the enforceable seam.
7. **Ship** — run `/ship` to open the PR **against the base branch** captured in step 1 of the isolation section. Only proceed if the pre-push validation gate (step 6) is fully green.
8. **Worktree cleanup** — only after the PR is opened: return to the repo root (`cd`) and `git worktree remove .claude/worktree/<slug>` (the branch stays on the PR). If removal fails, report it and leave the worktree intact — don't force it blindly.

## Final output

Report in up to 6 lines: what was done, branch (`<type>/<slug>`, base), PR link, any known pending items, and the status of the gstack steps in 1 line — `autoplan / review / qa / gate / ship`, each marked ✅ executed, ⬜ skipped (with reason), or ❌ failed. For `gate`, surface the per-step result (lint / type-check / test / build: ✅ pass · ➖ absent · ❌ stuck).
