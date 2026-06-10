# .NET Patterns

Idiomatic C# and .NET patterns for ASP.NET Core applications.

## Core Principles

### Prefer Immutability

```csharp
// Good: immutable record
public sealed record Money(decimal Amount, string Currency);

// Good: init-only DTO
public sealed class CreateOrderRequest
{
    public required string CustomerId { get; init; }
    public required IReadOnlyList<OrderItem> Items { get; init; }
}
```

### Explicit Over Implicit

- Always specify access modifiers (`public`, `private`, `internal`)
- Enable nullable reference types — annotate all nullable parameters explicitly
- Throw `ArgumentNullException` in constructors for required dependencies
- Use `required` keyword for mandatory properties (C# 11+)

### Depend on Abstractions

```csharp
// Always inject interfaces, not concrete types
public interface IOrderRepository
{
    Task<Order?> FindByIdAsync(Guid id, CancellationToken ct);
    Task AddAsync(Order order, CancellationToken ct);
}

// Registration
builder.Services.AddScoped<IOrderRepository, SqlOrderRepository>();
```

## Async/Await

- Every I/O method is `async Task<T>` — never `async void` except event handlers
- Always pass `CancellationToken` through — do not ignore it
- Never `.Result` or `.Wait()` — deadlocks in ASP.NET contexts
- Use `ConfigureAwait(false)` in library code, not application code

```csharp
// Good
public async Task<Order?> GetOrderAsync(Guid id, CancellationToken ct)
    => await _repository.FindByIdAsync(id, ct);

// Bad
public Order GetOrder(Guid id)
    => _repository.FindByIdAsync(id, CancellationToken.None).Result; // deadlock risk
```

## DI and Service Registration

- `AddScoped` for per-request services (DB contexts, unit-of-work)
- `AddSingleton` for thread-safe, stateless services
- `AddTransient` for cheap, stateless utilities
- Never inject `IServiceProvider` directly — use typed injection or factory pattern
- Use `Options<T>` pattern for configuration — never inject `IConfiguration` into business services

## Error Handling

- Define typed domain exceptions (`OrderNotFoundException`, `InsufficientFundsException`)
- Use global exception middleware to map to HTTP responses — not try/catch in every controller
- Log with structured properties: `_logger.LogError(ex, "Failed to process order {OrderId}", orderId)`
- Never swallow exceptions silently

## Entity Framework / Queries

- Always use parameterized queries or EF — never string-concatenated SQL
- Avoid lazy loading in web apps — use `Include()` explicitly
- Use `AsNoTracking()` for read-only queries
- Batch writes in transactions: `await using var tx = await _db.Database.BeginTransactionAsync(ct)`

## Controller Patterns

- Keep controllers thin — delegate to services
- Use `[ApiController]` attribute — enables automatic model validation
- Return `IActionResult` or `ActionResult<T>` — never `object`
- Use `ProblemDetails` for error responses (RFC 7807)

## Naming Conventions

- Async methods suffixed `Async`
- Interfaces prefixed `I`
- Private fields prefixed `_`
- Use PascalCase for public members, camelCase for locals
