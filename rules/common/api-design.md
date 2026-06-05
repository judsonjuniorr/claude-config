# API Design Rules

Conventions for designing consistent, developer-friendly REST APIs.

## URL Structure

- Resources are nouns, plural, kebab-case: `/api/v1/team-members`
- Sub-resources for ownership: `/api/v1/users/:id/orders`
- Verbs only for non-CRUD actions: `POST /api/v1/orders/:id/cancel`
- Query params for filtering/sorting/pagination: `?status=active&sort=created&limit=20&cursor=<token>`
- Never put verbs in resource URLs: `/getUsers` is wrong

## HTTP Methods

| Method | Idempotent | Use For |
|--------|------------|---------|
| GET | Yes | Retrieve (never mutates) |
| POST | No | Create, trigger action |
| PUT | Yes | Full replacement |
| PATCH | No | Partial update |
| DELETE | Yes | Remove |

## Status Codes

```
200 OK            — GET, PUT, PATCH (with body)
201 Created       — POST (include Location header)
204 No Content    — DELETE, no-body responses
400 Bad Request   — Validation failure, malformed input
401 Unauthorized  — Missing/invalid auth
403 Forbidden     — Authenticated but not authorized
404 Not Found     — Resource missing
409 Conflict      — Duplicate, state conflict
422 Unprocessable — Semantic validation failure
429 Too Many Requests — Rate limited
500 Internal Error — Server fault
```

Never return `200` with an error body. Status code is the contract.

## Error Response Format

Always return structured errors:

```json
{
  "error": {
    "code": "VALIDATION_ERROR",
    "message": "Human-readable description",
    "details": [{ "field": "email", "message": "Invalid format" }]
  }
}
```

## Pagination

Prefer cursor-based for large/real-time datasets:

```
GET /api/v1/items?limit=20&cursor=<opaque-token>

Response:
{
  "data": [...],
  "pagination": {
    "next_cursor": "<token>",
    "has_more": true
  }
}
```

Offset-based acceptable for small, static datasets only.

## Versioning

- URL versioning: `/api/v1/`, `/api/v2/` — simple, cacheable
- Maintain at least one previous version when breaking changes ship
- Breaking changes: removing fields, changing types, changing semantics
- Additive changes (new optional fields) are not breaking

## Validation

- Validate at the API boundary with Zod (TypeScript) or Pydantic (Python)
- Never trust client input — validate shape, type, and domain rules
- Return field-level errors, not just a generic 400

## Security

- Rate limit all public endpoints
- Never expose internal IDs in error messages
- Sanitize errors before returning — no stack traces in production
- Auth on every protected route — never assume middleware ran
