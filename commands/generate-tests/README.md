# /generate-tests

Generate a comprehensive test suite for a file, module, or specific function. Detects the project's existing testing framework and follows its conventions.

See [`generate-tests.md`](./generate-tests.md) for the full agent-facing procedure.

## What it does

1. Parses `$ARGUMENTS` to identify the target (file path, or `file:FunctionName` pattern).
2. Reads the target and identifies exported functions, classes, and method signatures.
3. Detects the testing ecosystem in use (Vitest, Jest, pytest, Go table tests, Rust `#[cfg(test)]`).
4. Designs mock strategies for external dependencies (network, database, filesystem, SDKs).
5. Writes unit tests following Arrange-Act-Assert, covering happy path, edge cases, and error paths.
6. Adds integration tests when the target crosses system boundaries.
7. Self-checks test isolation, naming clarity, and mock hygiene before finishing.

## Frontmatter

- **description**: Generate a comprehensive test suite for the specified file, module, or function.
- **argument-hint**: `<file-or-function-path>`
- **allowed-tools**: Bash, Read, Write, Edit, Glob, Grep

## Usage

```
/generate-tests src/utils/formatCurrency.ts
/generate-tests src/api/users.ts:createUser
/generate-tests app/services/payment_service.py
```

## Framework support

| Language | Framework |
|----------|-----------|
| TypeScript / JavaScript | Vitest (default), Jest |
| Python | pytest + pytest-mock |
| Go | table-driven `_test.go` |
| Rust | `#[cfg(test)]` inline modules |

## When to use

- Before refactoring: generate tests first to lock in the current behavior.
- After writing new logic: ensure coverage before the PR.
- On untested legacy code: bootstrap a test suite without reading every line manually.

## Notes

- Never hits real network, database, or filesystem from unit tests — always mocks external I/O.
- Targets 80%+ coverage on critical business logic.
- Reports gaps that require human judgment (e.g., complex stateful workflows).
