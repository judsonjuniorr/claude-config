# /refactor-code

Safely refactor a file or function while preserving external behavior. Tests first, incremental changes, static analysis after.

See [`refactor-code.md`](./refactor-code.md) for the full agent-facing procedure.

## What it does

1. Reads the target and identifies code smells (duplication, complexity, naming, coupling).
2. Checks existing test coverage — stops and asks if coverage is insufficient for safe refactoring.
3. Writes characterization tests before making any change if needed.
4. Applies improvements incrementally: naming → extract → simplify → decouple → remove dead code.
5. Runs tests after each change; reverts and diagnoses on failure.
6. Runs static analysis (tsc, ruff, mypy, go vet, cargo clippy) on the result.
7. Reports what changed, why, and what was intentionally left out of scope.

## Frontmatter

- **description**: Safely refactor the specified file or function while preserving external behavior.
- **argument-hint**: `<file-or-function-path> [goal]`
- **allowed-tools**: Bash, Read, Write, Edit, Glob, Grep

## Usage

```
/refactor-code src/utils/payments.ts
/refactor-code src/api/users.ts:createUser extract validation layer
/refactor-code app/services/order_service.py reduce cyclomatic complexity
```

## When to use

- Code works but is hard to read or extend.
- A function grew too large and needs to be split.
- Duplication appeared across multiple files and needs a shared abstraction.
- Before adding a new feature to a messy area — clean up first.

## Notes

- Never changes external behavior. If a change is behavioral, it is a bug fix, not a refactor — stop and ask.
- Does not implement speculative abstractions. Only extracts patterns that exist at least twice.
- Performance-sensitive code gets a benchmark check before and after.
