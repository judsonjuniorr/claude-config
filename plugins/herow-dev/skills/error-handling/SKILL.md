---
name: error-handling
description: (herow) Patterns for robust error handling in TypeScript and Python. Covers typed error hierarchies, the Result pattern, API error envelopes, React error boundaries, retries with backoff, and user-facing error messages.
model: sonnet
effort: medium
---

# Error Handling Patterns

Consistent, robust error handling patterns for production applications.

## When to Activate

- Designing error types or exception hierarchies for a new module or service
- Adding retry logic for unreliable external dependencies
- Reviewing API endpoints for missing error handling
- Implementing user-facing error messages and feedback
- Debugging cascading failures or silent error swallowing

## Core Principles

1. **Fail fast and loudly** — surface errors at the boundary where they occur; don't bury them
2. **Typed errors over string messages** — errors are first-class values with structure
3. **User messages ≠ developer messages** — show friendly text to users, log full context server-side
4. **Never swallow errors silently** — every `catch` block must either handle, re-throw, or log
5. **Errors are part of your API contract** — document every error code a client may receive

## Pattern Index

Full implementations live in `reference.md` **in this skill's directory** — read it
when you need the code, then adapt to the project's conventions:

| Pattern | Use for |
|---|---|
| Typed error classes (TS) | Domain error hierarchy: `AppError` base with `code` + `statusCode`, subclasses per failure kind |
| Result pattern (TS) | Expected, common failures (parsing, external calls) without throw/catch flow |
| API error handler (Next.js/Express) | One `handleApiError` mapping AppError/ZodError/unknown → standard envelope `{ error: { code, message, details? } }` |
| React Error Boundary | Catching render errors with a fallback UI + onError reporting |
| Python exception hierarchy | `AppError` base mirroring the TS shape (`code`, `status_code`) |
| FastAPI global handlers | `@app.exception_handler` for AppError + generic Exception (log full, return generic) |
| Retry with exponential backoff (TS) | Transient failures only — `retryIf` must exclude 4xx client errors; jittered, capped delay |
| User-facing messages | Code → friendly-text map; never expose stack traces or internals |

## Error Handling Checklist

Before merging any code that touches error handling:

- [ ] Every `catch` block handles, re-throws, or logs — no silent swallowing
- [ ] API errors follow the standard envelope `{ error: { code, message } }`
- [ ] User-facing messages contain no stack traces or internal details
- [ ] Full error context is logged server-side
- [ ] Custom error classes extend a base `AppError` with a `code` field
- [ ] Async functions surface errors to callers — no fire-and-forget without fallback
- [ ] Retry logic only retries retriable errors (not 4xx client errors)
- [ ] React components are wrapped in `ErrorBoundary` for rendering errors
