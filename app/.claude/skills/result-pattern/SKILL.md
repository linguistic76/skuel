---
name: result-pattern
description: Expert guide for SKUEL's Result[T] error handling pattern. Use when handling errors, returning failures from services, converting errors to HTTP responses, or when the user mentions Result type, Errors factory, error handling, failure propagation, or exception handling.
allowed-tools: Read, Grep, Glob
---

# Result[T] Error Handling: SKUEL's Unified Pattern

> "Results Internally, Exceptions at Boundaries"

SKUEL uses a monadic `Result[T]` type for ALL internal error handling. Services return `Result[T]`, backends return `Result[T]`, and only at HTTP boundaries do we convert to responses via `@boundary_handler`.

## Quick Reference

### Result[T] Type

```python
from core.utils.result_simplified import Result

# Success
result = Result.ok(value)

# Failure
result = Result.fail(error)  # ErrorContext, str, or another Result

# Checking
if result.is_ok:
    data = result.value
if result.is_error:  # NOT .is_err (deprecated)
    error = result.expect_error()  # Type-safe: ErrorContext (guaranteed)
```

### Key Methods

| Method | Purpose | Returns |
|--------|---------|---------|
| `.is_ok` | Check success | `bool` |
| `.is_error` | Check failure (preferred) | `bool` |
| `.value` | Get success value | `T` (raises if error) |
| `.error` | Get error | `ErrorContext \| None` |
| `.expect_error()` | Type-safe error access | `ErrorContext` (guaranteed) |
| `.expect(msg)` | Get value with custom error | `T` (raises with msg if error) |
| `.or_else(default)` | Get value or default | `T` |

### Factory Methods

| Method | Purpose |
|--------|---------|
| `Result.ok(value)` | Create success (prevents double-wrapping) |
| `Result.fail(error)` | Create failure (accepts ErrorContext, str, Result) |

---

## ErrorContext & The Errors Factory

### Six Error Categories

SKUEL uses exactly 6 error categories (reduced from 37):

| Category | HTTP | When to Use | Example |
|----------|------|-------------|---------|
| `VALIDATION` | 400 | Bad input user can fix | Invalid email format |
| `NOT_FOUND` | 404 | Resource doesn't exist | User "abc123" not found |
| `BUSINESS` | 422 | Domain rule violated | Duplicate journal title |
| `DATABASE` | 503 | Storage operation failed | Neo4j connection timeout |
| `INTEGRATION` | 502 | External service failed | OpenAI rate limit |
| `SYSTEM` | 500 | Unexpected error | Null pointer, index error |

### ErrorSeverity Levels

| Severity | Log Level | Meaning |
|----------|-----------|---------|
| `LOW` | info | Degraded functionality |
| `MEDIUM` | warning | Feature unavailable |
| `HIGH` | error | Major functionality broken |
| `CRITICAL` | critical | System-wide failure |

### Errors Factory Methods

```python
from core.utils.errors_simplified import Errors

# Validation - single field issues
Errors.validation(
    message="Email format invalid",
    field="email",
    value="not-an-email",
    user_message="Please enter a valid email address"
)

# Not Found - resource lookup failed
Errors.not_found(
    resource="Task",
    identifier="task-123"
)

# Database - storage operations
Errors.database(
    operation="create_user",
    message="Connection timeout after 30s",
    query="CREATE (u:User ...)"
)

# Integration - external services
Errors.integration(
    service="OpenAI",
    message="Rate limit exceeded",
    status_code=429
)

# Business - domain rule violations
Errors.business(
    rule="journal_uniqueness",
    message="Journal with this title already exists on this date",
    title="Morning Reflection",
    date="2025-01-15"
)

# System - unexpected errors
Errors.system(
    message="Unexpected null reference",
    exception=exc  # Optional: captures stack trace
)
```

### Decision Tree: Which Error Category?

```
Is it bad user input (field-level)?
├── Yes → VALIDATION (400)
└── No
    ├── Does the resource not exist?
    │   ├── Yes → NOT_FOUND (404)
    │   └── No
    │       ├── Is it a business rule (multi-entity/state constraint)?
    │       │   ├── Yes → BUSINESS (422)
    │       │   └── No
    │       │       ├── Is it database/storage?
    │       │       │   ├── Yes → DATABASE (503)
    │       │       │   └── No
    │       │       │       ├── Is it an external service?
    │       │       │       │   ├── Yes → INTEGRATION (502)
    │       │       │       │   └── No → SYSTEM (500)
```

**Key distinction:** Single-field validation → `VALIDATION`. Multi-entity constraints or state rules → `BUSINESS`.

---

## Service Patterns

### Pattern 1: Early Return with Validation

```python
async def create_task(self, request: TaskCreateRequest,
                      user_uid: str) -> Result[Task]:
    # Validation - return early
    if not user_uid:
        return Result.fail(
            Errors.validation(
                message="user_uid is required",
                field="user_uid"
            )
        )

    # Backend call
    result = await self.backend.create(task)
    if result.is_error:
        return result  # Propagate error as-is

    # Success
    return Result.ok(result.value)
```

### Pattern 2: Error Propagation

```python
async def get_user_tasks(self, user_uid: str) -> Result[list[Task]]:
    result = await self.backend.get_user_tasks(user_uid)
    if result.is_error:
        return result  # Propagate - types align

    # Transform success value
    tasks = [self._to_domain_model(t) for t in result.value]
    return Result.ok(tasks)
```

### Pattern 3: Type-Safe Error Access

```python
async def complex_operation(self) -> Result[Output]:
    result = await some_operation()
    if result.is_error:
        # .expect_error() guarantees ErrorContext (not Optional)
        error = result.expect_error()
        # MyPy knows error is ErrorContext - no assertion needed
        return Result.fail(error)

    return Result.ok(transform(result.value))
```

### Pattern 4: Batch Operations

```python
async def batch_delete(self, uids: list[str]) -> Result[int]:
    errors = []
    deleted = 0

    for uid in uids:
        result = await self.delete(uid)
        if result.is_ok:
            deleted += 1
        else:
            errors.append(f"{uid}: {result.error.message}")

    if errors:
        return Result.fail(Errors.business(
            rule="batch_partial_failure",
            message=f"Deleted {deleted}/{len(uids)} items",
            errors=errors
        ))

    return Result.ok(deleted)
```

### Pattern 5: Ownership Verification

```python
async def update_for_user(self, uid: str, updates: dict,
                          user_uid: str) -> Result[Task]:
    # verify_ownership returns entity or NotFound error
    ownership = await self.verify_ownership(uid, user_uid)
    if ownership.is_error:
        return ownership  # Returns 404 (security: don't reveal existence)

    # Safe to update - user owns this entity
    return await self.update(uid, updates)
```

---

## Route Integration

### The @boundary_handler Decorator

Routes use `@boundary_handler` to convert `Result[T]` to HTTP responses:

```python
from core.utils.error_boundary import boundary_handler

@rt("/api/tasks")
@boundary_handler(success_status=201)  # POST creates → 201
async def create_task(request):
    result = await task_service.create(...)
    return result  # Automatically converted to JSON response

@rt("/api/tasks/{uid}")
@boundary_handler()  # Default: 200
async def get_task(request, uid: str):
    return await task_service.get(uid)  # Result[Task] → response
```

### HTTP Status Code Mapping

| ErrorCategory | HTTP Status | Response Type |
|---------------|-------------|---------------|
| Success | `success_status` (default 200) | JSON body |
| `VALIDATION` | 400 Bad Request | Error JSON |
| `NOT_FOUND` | 404 Not Found | Error JSON |
| `BUSINESS` | 422 Unprocessable Entity | Error JSON |
| `DATABASE` | 503 Service Unavailable | Error JSON |
| `INTEGRATION` | 502 Bad Gateway | Error JSON |
| `SYSTEM` | 500 Internal Server Error | Error JSON |

### Error Response Format

```json
{
  "category": "not_found",
  "code": "RESOURCE_NOT_FOUND",
  "message": "Task 'task-123' not found",
  "user_message": "The requested task could not be found",
  "severity": "medium",
  "timestamp": "2025-01-15T10:30:00Z"
}
```

---

## Functional Composition

### .map() - Transform Success Value

Use when the transformation returns a plain value (not Result):

```python
result = await get_user(uid)
# .map() transforms value if Ok, passes through error if not
prefs = result.map(lambda user: user.preferences)
```

### .and_then() - Chain Result-Returning Operations

Use when chaining operations that each return Result:

```python
result = (
    Result.ok(user_id)
    .and_then(get_user)           # Returns Result[User]
    .and_then(validate_active)    # Returns Result[User]
    .map(extract_preferences)     # Returns plain Prefs
)
```

### .aflat_map() - Async Chaining

Async version of `.and_then()`:

```python
result = await (
    Result.ok(uid)
    .aflat_map(get_user_async)
    .aflat_map(validate_async)
)
```

### .map_error() - Add Error Context

Transform error as it propagates:

```python
result = await backend.create(entity)
result = result.map_error(lambda e: e.with_context(
    operation="create_task",
    user_uid=user_uid
))
```

### .log_if_error() - Automatic Severity Logging

```python
result = await some_operation()
result.log_if_error("Task creation failed")
# Automatically logs by severity:
# - CRITICAL → logger.critical()
# - HIGH → logger.error()
# - MEDIUM → logger.warning()
# - LOW → logger.info()
```

---

## Anti-Patterns

### Use .is_error, NOT .is_err

```python
# WRONG (deprecated)
if result.is_err:  # SKUEL003 linter violation

# CORRECT
if result.is_error:
```

### Use Errors Factory, NOT String Failures

```python
# WRONG (SKUEL007 linter violation)
return Result.fail("Something went wrong")

# CORRECT
return Result.fail(Errors.system("Something went wrong"))
```

### Don't Mix Result and Exceptions

```python
# WRONG - inconsistent error handling
try:
    result = await service.get(uid)
    return result.value  # Raises if error
except ValueError:
    pass  # Unpredictable

# CORRECT
result = await service.get(uid)
if result.is_error:
    return result
return Result.ok(transform(result.value))
```

### Don't Create Custom Error Classes

```python
# WRONG (old pattern)
class TaskNotFoundError(Exception):
    pass

# CORRECT - use Errors factory
Result.fail(Errors.not_found("Task", task_uid))
```

### Don't Use Wrong Error Category

```python
# WRONG - uniqueness constraint is business rule, not validation
return Result.fail(Errors.validation(
    "Journal with this title already exists"
))

# CORRECT - multi-entity constraints are business rules
return Result.fail(Errors.business(
    rule="journal_uniqueness",
    message="Journal with this title already exists on this date"
))
```

### Don't Access .value Without Checking

```python
# WRONG - crashes if error
result = await service.get(uid)
task = result.value  # Raises ValueError if error!

# CORRECT
result = await service.get(uid)
if result.is_ok:
    task = result.value
else:
    return result  # Propagate error
```

---

## Testing Patterns

### Mocking Result Returns

```python
async def test_not_found_handling():
    mock_backend.get.return_value = Result.fail(
        Errors.not_found("Journal", "123")
    )

    result = await service.get_journal("123")

    assert result.is_error
    assert result.error.category == ErrorCategory.NOT_FOUND
    assert "123" in result.error.message
```

### Testing Error Propagation

```python
async def test_error_propagation():
    mock_backend.create.return_value = Result.fail(
        Errors.database("create", "Connection timeout")
    )

    result = await service.create_task(request, user_uid)

    assert result.is_error
    assert result.error.category == ErrorCategory.DATABASE
```

### Testing Success Cases

```python
async def test_success_case():
    expected = Task(uid="task-1", title="Test")
    mock_backend.get.return_value = Result.ok(expected)

    result = await service.get_task("task-1")

    assert result.is_ok
    assert result.value == expected
```

---

## Key Source Files

| File | Purpose |
|------|---------|
| `/core/utils/result_simplified.py` | Result[T] type definition |
| `/core/utils/errors_simplified.py` | ErrorContext, Errors factory |
| `/core/utils/error_boundary.py` | @boundary_handler decorator |
| `/docs/patterns/ERROR_HANDLING.md` | Full documentation |

## Related Skills

- **[python](../python/SKILL.md)** - Core Python patterns that Result[T] implements
- **[pytest](../pytest/SKILL.md)** - Testing patterns using Result[T] mocks
- **[pydantic](../pydantic/SKILL.md)** - Validation at edges before Result[T] in services

## Foundation

This skill has no prerequisites. It is a foundational pattern.

## See Also

- [patterns-reference.md](patterns-reference.md) - Comprehensive code examples
- `/docs/patterns/ERROR_HANDLING.md` - Full error handling documentation
- `/docs/patterns/linter_rules.md` - SKUEL003/SKUEL007 linter rules for Result[T]
