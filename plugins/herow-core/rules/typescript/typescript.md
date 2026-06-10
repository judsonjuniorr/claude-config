# TypeScript rules

Applies when the project's primary language is TypeScript/JavaScript (Next.js, React, tRPC,
Drizzle, Node). Read before writing code.

## Types
- `strict` is assumed on. Never use `any` — use `unknown` + narrowing, or a precise type.
- Prefer `type` aliases for unions/objects; `interface` only for declaration merging or public
  extension points.
- Derive, don't duplicate: `z.infer<typeof schema>`, `Awaited<ReturnType<typeof fn>>`,
  `(typeof obj)[keyof typeof obj]`. One source of truth for a shape.
- No non-null `!` to silence the compiler — handle the nullish branch.

## Style
- `const` by default; `let` only when reassigned; never `var`.
- Pure functions and early returns over deep nesting. Guard clauses first.
- Name async functions for what they return, not "doX". Await at the edge, pass data inward.
- Discriminated unions for state (`{ status: 'loading' } | { status: 'error', error } | ...`)
  instead of boolean soup.

## Errors
- Throw `Error` subclasses with a `name`; never throw strings. See the `error-handling` skill for
  the typed-error / `Result<T,E>` patterns.
- No empty `catch`. No `catch (e) { return [] }` that hides the failure — log or rethrow.

## React / Next.js
- Server Components by default; `'use client'` only when you need state/effects/browser APIs.
- Keep `useEffect` for synchronization with external systems, not for deriving state.
- Stable keys (never array index for dynamic lists). Co-locate state with the component that owns it.
- Validate all external input (forms, route params, API bodies) with a schema (zod) at the boundary.

## Testing
- Vitest/Jest. Test behavior and contracts, not implementation details.
- One assertion focus per test; name tests `it('returns X when Y')`.
- Cover the nullish/empty/error shadow paths, not just the happy path.
