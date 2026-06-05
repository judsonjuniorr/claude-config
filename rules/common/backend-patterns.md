# Backend Patterns

Architecture patterns for Node.js, TypeScript, and Next.js server-side code.

## Layered Architecture

```
HTTP layer    — request parsing, auth middleware, response serialization
Service layer — business logic, orchestration
Repository    — data access, queries (no business logic)
```

Never put business logic in route handlers. Never put queries in the service layer — delegate to a repository.

## Repository Pattern

```typescript
interface UserRepository {
  findById(id: string): Promise<User | null>
  findAll(filters?: UserFilters): Promise<User[]>
  create(data: CreateUserDto): Promise<User>
  update(id: string, data: UpdateUserDto): Promise<User>
  delete(id: string): Promise<void>
}
```

- One repository per aggregate root
- Repositories return domain objects, not raw DB rows
- Repositories hide the ORM — callers don't know about Prisma/Drizzle/etc.

## Authentication Middleware

- Validate session/JWT on every protected route inside the handler
- Never rely solely on middleware — always re-check authorization in the action/service
- Return 401 for missing auth, 403 for insufficient permissions

## Caching Strategy

```
L1: In-memory (process-local, LRU, tiny TTL) — hot path, sub-ms reads
L2: Redis (shared, typed keys, explicit TTL) — cross-instance
L3: HTTP cache headers — GET endpoints with stable data
```

- Cache at the read, invalidate at the write
- Use explicit `CACHE_KEY_VERSION` constants — never rely on key guessing for invalidation
- Default TTL for session data: 15 min. For reference data: 1 hour.

## Database Patterns

- Use parameterized queries / ORM — never string-concatenate SQL
- Prefer `select()` with explicit field lists over `select *`
- Avoid N+1 queries — use `include`/`with` or batch load
- Use transactions for multi-step mutations — roll back on any error
- Connection pool: max 10 per Lambda/container, use `pgBouncer` for serverless

## Async Patterns

- `Promise.all` for independent async work — never sequential `await` in a loop
- `Promise.allSettled` when partial failure is acceptable
- Always handle rejections — no fire-and-forget unless in a background job with its own error handling

## Error Handling

- Throw typed domain errors, not raw `Error('something went wrong')`
- Map domain errors to HTTP status codes in the HTTP layer, not the service layer
- Log full error with context at the service layer, return safe message to client
- Never expose stack traces or DB error details to the client

## Background Jobs

- Idempotent by design — safe to retry on failure
- Store job state in DB, not in-memory
- Dead letter queue for failed jobs
- Alert on queue depth / failure rate

## Validation

- Validate at API boundary (Zod schema on route input)
- Validate again at service layer for programmatic callers
- Domain invariants enforced in the model/entity constructor
