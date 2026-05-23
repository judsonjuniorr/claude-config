---
description: Safely refactor the specified file or function while preserving external behavior.
argument-hint: <file-or-function-path> [goal]
allowed-tools: Bash, Read, Write, Edit, Glob, Grep
---

# Refactor Code

Refactor the target specified in `$ARGUMENTS` while preserving all external behavior. Safety over speed — no behavior change without a test to prove it.

**Core principle:** Every change must be traceable to a concrete improvement goal. If no goal is given, infer one from the code smell (duplication, complexity, naming, coupling).

## Step 1 — Parse arguments

- First token: file path (or `file:FunctionName` to scope to a single export).
- Remaining tokens: optional goal description (e.g., "extract service layer", "reduce cyclomatic complexity", "rename for clarity").
- If `$ARGUMENTS` is empty, ask the user for a target.

## Step 2 — Assess current state

1. Read the target with `Read`.
2. Identify code smells: duplication, long functions, deep nesting, poor naming, hidden coupling, magic numbers.
3. Check test coverage:
   - Look for existing tests in `__tests__/`, `tests/`, `*.test.*`, `*.spec.*`, or inline (`#[cfg(test)]`).
   - Run the test suite if a script is available: `npm test`, `pytest`, `go test ./...`, `cargo test`.
4. Report to the user: current state, identified smells, coverage level, and proposed refactoring goal.

**Stop here** if there are no tests and the function has side effects. Ask the user whether to write tests first.

## Step 3 — Write tests before touching code

If coverage is insufficient for the functions being changed:
1. Write minimal characterization tests that capture current behavior.
2. Run them to confirm they pass on the original code.
3. These tests become the safety net for the refactor.

## Step 4 — Refactor incrementally

Work in small, verifiable steps. After each change:
1. Run the test suite.
2. If tests fail, revert the last change and diagnose before continuing.

Apply improvements in this priority order:
1. **Naming** — rename variables, functions, and types to express intent clearly.
2. **Extract** — pull repeated code into named functions or classes.
3. **Simplify** — flatten nested conditionals, remove redundant branching.
4. **Decouple** — extract I/O, side effects, and external calls behind interfaces.
5. **Remove dead code** — delete unreachable branches and unused exports (confirm with Grep first).

Do not mix concerns — one improvement type per logical commit.

## Step 5 — Static analysis

After refactoring, run available linters and type-checkers:
- TypeScript: `tsc --noEmit` (or `pnpm exec tsc --noEmit`, `yarn tsc --noEmit`)
- Python: `ruff check` and `mypy`
- Go: `go vet ./...`
- Rust: `cargo clippy`

Fix any new warnings introduced by the refactor.

## Step 6 — Performance check (if applicable)

If the original code had performance-sensitive paths (tight loops, large data, hot render paths), verify the refactored version does not regress:
- Add a benchmark if one does not exist.
- Do not sacrifice measurable performance for aesthetics.

## Step 7 — Summarize

Report:
- What changed and why (one line per logical change).
- Test results before and after.
- Any remaining issues that were explicitly left out of scope.
- Suggestions for follow-up refactoring (do not implement unless asked).
