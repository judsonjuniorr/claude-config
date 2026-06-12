---
description: (herow) Comprehensive Python code review for PEP 8 compliance, type hints, security, and Pythonic idioms. Invokes the python-reviewer agent.
model: sonnet
effort: medium
---

# Python Code Review

This command invokes the **python-reviewer** agent for comprehensive Python-specific code review.

## What This Command Does

1. **Identify Python Changes**: Find modified `.py` files via `git diff`
2. **Run Static Analysis**: Execute the project's configured tools (prefer `ruff check` + `ruff format --check`; fall back to `black`/`isort`/`pylint` only if the project configures them)
3. **Type Safety**: Run `mypy` (or the project's configured type checker)
4. **Security Scan**: `bandit -r .` plus dependency audit (`pip-audit`) when available
5. **Dispatch**: Run the `python-reviewer` agent against the diff
6. **Generate Report**: Categorize issues by severity with file:line, issue, why, and a concrete fix

## When to Use

- After writing or modifying Python code, before committing
- Reviewing pull requests with Python code
- Onboarding to a new Python codebase

## Review Categories

### CRITICAL (Must Fix)
- SQL/Command injection vulnerabilities
- Unsafe eval/exec usage
- Pickle unsafe deserialization
- Hardcoded credentials
- YAML unsafe load
- Bare except clauses hiding errors

### HIGH (Should Fix)
- Missing type hints on public functions
- Mutable default arguments
- Swallowing exceptions silently
- Not using context managers for resources
- C-style looping instead of comprehensions
- Using type() instead of isinstance()
- Race conditions without locks

### MEDIUM (Consider)
- PEP 8 formatting violations
- Missing docstrings on public functions
- Print statements instead of logging
- Inefficient string operations
- Magic numbers without named constants
- Not using f-strings for formatting
- Unnecessary list creation

## Report Format

For each finding: `[SEVERITY] title`, `File: path:line`, one-sentence issue, why it
matters, and a concrete before/after fix snippet. End with a severity count summary
and the verdict.

## Approval Criteria

| Status | Condition |
|--------|-----------|
| PASS: Approve | No CRITICAL or HIGH issues |
| WARNING: Warning | Only MEDIUM issues (merge with caution) |
| FAIL: Block | CRITICAL or HIGH issues found |

## Framework-Specific Lanes

- **Django**: N+1 queries (`select_related`/`prefetch_related`), missing migrations, raw SQL where ORM works, missing `transaction.atomic()` for multi-step operations
- **FastAPI**: CORS misconfiguration, Pydantic request/response models, async/await correctness, dependency injection patterns (or use `/herow-dev:python:fastapi-review`)
- **Flask**: app/request context management, error handling, blueprint organization, configuration management

## Related

- Agent: `python-reviewer` (ships with this plugin)
- Idiom and pattern reference: herow-core's `rules/python/` (the session-start rules pointer prints its resolved path) — canonical fixes for mutable defaults, context managers, comprehensions, f-strings
- Use `/herow-dev:code:review` for non-Python-specific concerns on the same change
