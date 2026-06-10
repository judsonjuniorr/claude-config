# Python rules

Applies when the project's primary language is Python 3.12+ (FastAPI, Polars, uv, ruff, mypy).
Read before writing code.

## Types
- Full type coverage. `mypy --strict` is the target — no untyped defs, no implicit `Any`.
- Use modern syntax: `list[str]`, `dict[str, int]`, `X | None` (not `Optional[X]`/`List[...]`).
- `@dataclass(slots=True)` or pydantic models for structured data; never bare dicts as smuggled structs.
- Prefer `Protocol` for duck-typed interfaces over ABCs when no shared implementation.

## Style
- Pure functions and early returns. Guard clauses over nested `if`.
- f-strings only; never `%`/`.format()`. Pathlib over `os.path`.
- Comprehensions when they stay readable; a plain loop when they don't.
- Use `uv` for env/deps, `ruff` for lint+format, `mypy` for types. No black/flake8/isort separately.
- No mutable default args. Context managers (`with`) for every resource.

## Errors
- Raise specific exception types; never bare `raise Exception(...)`.
- No bare `except:` and no `except Exception:` that swallows — catch the narrowest type, log or reraise.
- See the `error-handling` skill for retry / circuit-breaker / Result patterns.

## Security
- Secrets from the environment: `os.environ["KEY"]` (raises on missing — fail loud); `python-dotenv` to load a local `.env`, never commit it. No hardcoded secrets.
- Static security analysis with **bandit**: `bandit -r src/`; treat findings as blockers.

## FastAPI / data
- Pydantic models for request/response; validate at the boundary, pass typed objects inward.
- Async endpoints for I/O-bound work; don't block the event loop with sync calls.
- Polars over pandas for dataframes; lazy frames for pipelines.

## Testing
- pytest. Arrange-Act-Assert; one behavior per test; parametrize over copy-paste.
- Fixtures for setup, not module-level globals. Cover the None/empty/error shadow paths.
- `pytest -q` clean before done.
