# Pre-push validation gate (shared spec)

> **Not a command.** This is a shared reference included by the herow-dev commands that push
> or finalize a branch (`execute`, `quick`, `git/pr`, `git/fix-conflicts`). It is the single
> source of truth for the gate steps and the anti-cheat rules — edit it here, not in four
> places.

**Rule in one line:** before any push (or before declaring a branch ready to finalize), the
project must be **100% green** — lint, type-check, test, and build must all pass for every step
that exists in the stack. Reaching green by weakening the checks is forbidden (see anti-cheat).

## The gate — four ordered steps

Run **in the worktree**, in this order. Detect the actual commands from the stack rather than
assuming a tool: read `package.json` scripts (npm/pnpm/yarn), `Makefile`, `pyproject.toml` /
`tox.ini`, `pom.xml` / `build.gradle`, `go.mod`, `Cargo.toml`, `composer.json`, etc. Prefer the
repo's own script (`npm run lint`, `make test`) over a raw tool invocation when one exists.

1. **Lint — with auto-fix.** e.g. `eslint --fix`, `biome check --write`, `ruff --fix`,
   `prettier --write`. Commit the auto-fixes (see "where the commits go").
2. **Type-check — if the stack has one.** e.g. `tsc --noEmit`, `vue-tsc --noEmit`, `mypy`,
   `pyright`.
3. **Tests.** The project's real suite: `vitest run`, `jest`, `pytest`, `go test ./...`,
   `mvn test`, `cargo test`, etc.
4. **Build.** e.g. `next build`, `vite build`, `tsc -b`, `mvn package`, `cargo build --release`.

**Each step that EXISTS must pass 100%.** A step the project genuinely lacks is **skipped and
logged** (`➖ absent`) — an absent step is not a failure. But an absent step must never be
**faked** into looking green (see anti-cheat).

### Monorepo / multiple packages
Run the gate for the package(s) actually touched. If a root orchestrator exists (turbo, nx,
lerna, a root `Makefile`), prefer it and run once at the root. **Log which scope you chose.**

## Anti-cheat clause (load-bearing — do not weaken)

To reach green you must **fix the real problem**. You must **NEVER**:

- skip or disable tests (`it.skip` / `xit` / `test.skip` / `describe.skip` / `@Disabled` /
  `@pytest.mark.skip` / `t.Skip()`);
- delete or comment out failing tests or their assertions;
- use `--passWithNoTests` (or any flag that makes an empty/absent suite report green), or
  narrow the test selection (single file, `-k`, `.only`) to dodge a failing test;
- append `|| true`, `; exit 0`, or otherwise swallow a non-zero exit code;
- add blanket `eslint-disable`, `// @ts-nocheck`, `// @ts-ignore`, `# type: ignore`,
  `# noqa`, or `#[allow(...)]` to silence errors instead of fixing them;
- push with `--no-verify` (never bypass hooks);
- lower thresholds, mock away the failing behavior, or edit config to stop a check from running.

Targeted, justified suppressions that already exist in the codebase's style are not the target
here — **manufacturing** a suppression to get past this gate is.

**If the project cannot be made honestly green within 3 cycles per step: STOP and report** which
step is stuck, the failing output, and why. **Never hack the gate to open the PR / finalize the
branch.** A red gate that is honestly reported is a success; a green gate reached by cheating is
a failure.

## Pre-existing failures (files the AI didn't touch)

The project must be at 100%, including failures that were already on the base branch. But:

- Fix pre-existing (untouched-file) failures in a **separate, clearly labeled commit**:
  `chore: fix pre-existing gate failures` — so the feature PR stays reviewable and the
  unrelated fixes are isolated.
- If the pre-existing breakage is **large or unrelated** (a rabbit hole), **default to STOP +
  report**: "base branch was already red: `<step>` — `<summary>`", and let the user decide,
  rather than absorbing an unbounded diff into this branch.

## Where the auto-fix / build commits go

- Fixes to files this change already touches → the **feature commit**.
- Fixes to previously-untouched files → the **separate labeled commit** above.
- Never leave the gate's own auto-fixes uncommitted before the push.

## Per-command tool posture

- **`execute`, `quick`, `git/fix-conflicts`** have `Edit`/`Write` → run the **full fix-loop**:
  run each step, fix failures (≤3 cycles/step), commit, re-run, until green — or STOP + report.
- **`git/pr`** is **verify-only** (`allowed-tools: Bash, Read` — no `Edit`/`Write`): run the
  gate to **detect** red, and if any step fails, **STOP** and tell the user to run
  `/herow-dev:execute` or `/herow-dev:quick` (which can fix). `git/pr` does not fix and does not
  push over a red gate.

## Surfacing the result

Report per-step status so a failure is legible: `✅ pass` / `➖ absent` / `❌ stuck`
(lint / type-check / test / build).
