---
description: (herow) Generate a comprehensive test suite for the specified file, module, or function.
argument-hint: <file-or-function-path>
allowed-tools: Bash, Read, Write, Edit, Glob, Grep
---

# Generate Tests

> **Recommended subagents (when installed):** for **TypeScript/JavaScript** targets, delegate the implementation to `fullstack-developer`; for **Python** targets, delegate to `python-pro`. After tests are written, optionally hand off to `code-reviewer` to validate coverage and quality. Invoke via the `Agent` tool with the matching `subagent_type`. If the agent file is not present at `~/.claude/agents/<name>.md`, execute the steps below directly.

Your task is to create a comprehensive test suite for the target specified in `$ARGUMENTS`.

## Step 1 — Identify the target

Parse `$ARGUMENTS`:
- If it is a file path, analyze the entire file.
- If it is a `file:FunctionName` or `file::ClassName` pattern, scope the analysis to that export.
- If `$ARGUMENTS` is empty, ask the user to specify a target.

## Step 2 — Analyze the target

1. Read the target file with `Read`.
2. Identify all exported functions, classes, and their method signatures.
3. Detect the language and testing ecosystem already in use:
   - Look for `package.json` (Jest, Vitest, Testing Library), `pytest.ini` / `pyproject.toml` (pytest), `Cargo.toml` (`#[cfg(test)]`), `go.mod` (table-driven tests), etc.
   - Run `ls` on the nearest `__tests__`, `tests`, or `spec` directory if it exists.
4. Identify external dependencies that must be mocked (network, filesystem, database, third-party SDKs).

## Step 3 — Determine test strategy

- **Unit tests** — for pure functions and isolated methods.
- **Integration tests** — for functions that cross boundaries (HTTP, DB, filesystem).
- Follow the project's existing test patterns. If none exist, default to:
  - TypeScript/JS: Vitest with `@testing-library` for UI, plain Vitest for logic.
  - Python: `pytest` with `pytest-mock`.
  - Go: table-driven tests in `_test.go` files.
  - Rust: inline `#[cfg(test)]` modules.

## Step 4 — Design mocks and test data

1. List every external dependency found in Step 2.
2. Create minimal, realistic test data factories inline (no large fixtures unless necessary).
3. Mock external I/O — never hit real network, database, or filesystem from unit tests.

## Step 5 — Write unit tests

For each exported function/method:
- Follow **Arrange → Act → Assert**.
- Cover: happy path, edge cases (null, empty, boundaries), and error paths.
- Name tests descriptively: `it("returns empty array when input is empty")`.
- Target 80%+ coverage on critical business logic.

## Step 6 — Write integration tests (if applicable)

- Test component interactions and realistic end-to-end workflows.
- Keep these separate from unit tests (different file or `describe` block).

## Step 7 — Verify quality

Before finishing, self-check:
- No test depends on another test's side effects.
- Each test has a single assertion focus.
- Mocks are reset between tests.
- Test names describe behavior, not implementation.
- No hardcoded secrets or production credentials.

Report to the user: file written, framework used, number of tests generated, estimated coverage, and any gaps that require human judgment.

## Recommended subagents

These subagents ship with the herow-dev plugin and sharpen the output when installed. The command works without them.

- **[`fullstack-developer`](../../agents/fullstack-developer.md)** — when the target is TypeScript/JavaScript (Vitest, Jest, Testing Library). Best for React/Next.js components, tRPC procedures, or Drizzle queries.
- **[`python-pro`](../../agents/python-pro.md)** — when the target is Python (pytest, pytest-mock). Brings ruff/mypy strict discipline to the generated suite.
- **[`code-reviewer`](../../agents/code-reviewer.md)** — after tests are written, to audit coverage, mock hygiene, and flag anti-patterns before commit.

Each is optional. If none are installed, run the steps above inline.
