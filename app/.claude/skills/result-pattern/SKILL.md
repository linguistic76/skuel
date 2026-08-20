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
    return Result.fail(result)  # Propagate error (preferred)
    # Or access error details: error = result.expect_error()
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
from core.utils.result_simplified import Errors

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
                      user_uid: UserUID) -> Result[Task]:
    # Validation - return early
    if not user_uid:
        return Result.fail(
            Errors.validation(
                message="user_uid is required",
                field="user_uid"
            )
        )

    # Backend call — return directly, no re-wrapping needed
    return await self.backend.create(task)
```

### Pattern 2: Error Propagation

```python
async def get_user_tasks(self, user_uid: UserUID) -> Result[list[Task]]:
    result = await self.backend.get_user_tasks(user_uid)
    if result.is_error:
        return result  # Propagate - types align

    # Transform success value
    tasks = [self._to_domain_model(t) for t in result.value]
    return Result.ok(tasks)
```

### Pattern 3: Cross-Type Error Propagation

```python
async def complex_operation(self) -> Result[Output]:
    result = await some_operation()  # Returns Result[Input]
    if result.is_error:
        return Result.fail(result)  # Result[Input] → Result[Output]

    return Result.ok(transform(result.value))
```

Use `.expect_error()` only when you need to _read_ the error (logging, branching):
```python
if result.is_error:
    error = result.expect_error()  # Type: ErrorContext (guaranteed)
    logger.error(f"Failed: {error.message}")
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

**In route handlers**, use the `verify_entity_ownership` helper:

```python
from adapters.inbound.route_factories import verify_entity_ownership

@rt("/api/transcriptions/delete", methods=["DELETE"])
@boundary_handler()
async def delete_transcription(request, uid: str) -> Result[bool]:
    user_uid = require_authenticated_user(request)
    ownership_error = await verify_entity_ownership(
        transcription_service, uid, user_uid, "transcription"
    )
    if ownership_error:
        return ownership_error  # Returns 404 (security: don't reveal existence)
    return await transcription_service.delete(uid)
```

**In service internals**, use the service method directly:

```python
async def update_for_user(self, uid: str, updates: dict,
                          user_uid: UserUID) -> Result[Task]:
    ownership = await self.verify_ownership(uid, user_uid)
    if ownership.is_error:
        return ownership  # Returns 404
    return await self.update(uid, updates)
```

---

## Route Integration

### The @boundary_handler Decorator

Routes use `@boundary_handler` to convert `Result[T]` to HTTP responses:

```python
from adapters.inbound.boundary import boundary_handler

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

### require_found() — Fetch + Not-Found Guard

For detail routes that fetch a shared entity and need to 404 if missing:

```python
from adapters.inbound.result_helpers import require_found

@rt("/api/path-steps/get")
@boundary_handler()
async def get_path_step(request: Request, uid: str) -> Result[dict[str, Any]]:
    found = require_found(await service.get(uid), "PathStep", uid)
    if found.is_error:
        return found
    return Result.ok(entity_to_response(found.value))
```

Combines `is_error` check + `value is None` check into one call. Overloaded for both
shapes: a backend-style getter returning `Result[T | None]`, and a service-style one
returning `Result[T]` (`BaseService.get()` converts not-found into an error itself).
`Result` is invariant, so without the second overload a route fetching through a typed
service could not call this helper at all. Both arms narrow to `Result[T]`; keep the
guard on the non-nullable shape too — it is defense in depth, and dropping it turns a
contract violation into a 500 instead of a 404.

**Note:** For user-owned entities, prefer ownership verification over `require_found` — it combines the fetch + not-found + ownership check in one step. See OWNERSHIP_VERIFICATION.md.

### Request Body Parsing → Result[T]

Use `parse_json_body()` and `parse_form_body()` to convert Pydantic `ValidationError` into `Result.fail()` at the boundary — no manual try/except needed:

```python
from adapters.inbound.form_helpers import parse_json_body, parse_form_body

@rt("/api/goals/milestones", methods=["POST"])
@boundary_handler(success_status=201)
async def create_milestone(request: Request, entity: Any) -> Result[dict[str, Any]]:
    result = await parse_json_body(request, MilestoneCreateRequest)
    if result.is_error:
        return result  # type: ignore[return-value]  → 422 with validation details
    req = result.value
    return await goals_service.create_milestone(entity.uid, req.title, req.target_date)

# With extra fields (e.g., entity UID from ownership decorator)
result = await parse_json_body(request, TrackHabitRequest, extra={"habit_uid": entity.uid})

# Form data (empty strings → None, then validated by Pydantic)
result = await parse_form_body(request, RequestRevisionRequest)
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

Client responses use `ErrorContext.to_client_dict()` — internal fields (`details`, `source_location`, `stack_trace`) are stripped. The `message` field shows `user_message` (not the developer message):

```json
{
  "category": "not_found",
  "code": "NOT_FOUND_TASK",
  "message": "The requested Task could not be found",
  "severity": "low",
  "timestamp": "2026-01-15T10:30:00+00:00"
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

### Don't Return `Result` From a Callback a Result-Wrapping Boundary Calls (double-wrap)

When a boundary already wraps your callback's return in `Result.ok(...)` — e.g.
`Neo4jQueryExecutor.execute(...)` runs `Result.ok(processor(records))` — a
callback that itself returns a `Result` produces `Result[Result[T]]`. The inner
failure hides inside an outer `ok`, so callers checking `.is_error` never see it
(a `not_found` reads as success). Return a **raw value** from the callback and
keep the `Result.fail(...)` guard in the calling method.

```python
# WRONG - processor returns Result -> execute() wraps it -> Result[Result[bool]]
def _process_unpin(records: list) -> Result[bool]:
    return Result.ok(True) if records else Result.fail(Errors.not_found("Pin not found"))

return await executor.execute(query=..., processor=_process_unpin)  # double-wrapped

# CORRECT - processor returns raw bool; gate emptiness in the method
result = await executor.execute(query=..., processor=check_exists)  # -> Result[bool]
if result.is_error:
    return result
if not result.value:
    return Result.fail(Errors.not_found("Pin not found"))
return Result.ok(True)
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
| `/core/utils/result_simplified.py` | Result[T] type, ErrorContext, Errors factory |
| `/adapters/inbound/boundary.py` | @boundary_handler decorator |
| `/adapters/inbound/result_helpers.py` | `require_found()` — fetch + not-found in one call |
| `/docs/patterns/ERROR_HANDLING.md` | Full documentation |

## Related Skills

- **[python](../python/SKILL.md)** - Core Python patterns that Result[T] implements
- **[pytest](../pytest/SKILL.md)** - Testing patterns using Result[T] mocks
- **[pydantic](../pydantic/SKILL.md)** - Validation at edges before Result[T] in services

## Deep Dive Resources

**Patterns:**
- [ERROR_HANDLING.md](/docs/patterns/ERROR_HANDLING.md) - Complete error handling architecture (1015 lines)
- [linter_rules.md](/docs/patterns/linter_rules.md) - SKUEL003 (use .is_error), SKUEL007 (use Errors factory)

**ADRs:**
- [ADR-022](/docs/decisions/ADR-022-graph-native-authentication.md) - Graph-native auth with Result[T]

**Migration:**
- [result_migration_guide.md](/core/utils/result_migration_guide.md) - Migration from old Result to Result[T]

---

## Foundation

This skill has no prerequisites. It is a foundational pattern.

## Exception Narrowing

When writing manual try-except (not using `@with_error_handling`), narrow to specific types:

```python
from core.utils.exception_types import NEO4J_EXCEPTIONS, LLM_EXCEPTIONS

except NEO4J_EXCEPTIONS as e:       # → Errors.database()
except LLM_EXCEPTIONS as e:         # → Errors.integration()
except DATA_CONVERSION_EXCEPTIONS:  # → Errors.validation() or Errors.system()
```

**Available tuples:** `NEO4J_EXCEPTIONS`, `LLM_EXCEPTIONS`, `OPENAI_EXCEPTIONS`, `ANTHROPIC_EXCEPTIONS`, `FILE_IO_EXCEPTIONS`, `PARSING_EXCEPTIONS`, `DATA_CONVERSION_EXCEPTIONS`, `CONFIG_EXCEPTIONS`

Bare `except Exception` requires `# intentional-broad:`, `# safety-net:`, or `# skuel-lint: disable=SKUEL017` comment (SKUEL017). ✅ Zero violations — persistence uses `NEO4J_EXCEPTIONS`, boundaries use `# safety-net:`.

**See:** `/core/utils/exception_types.py`, `/docs/patterns/linter_rules.md` (SKUEL017)

## See Also

- [patterns-reference.md](patterns-reference.md) - Comprehensive code examples
- `/docs/patterns/ERROR_HANDLING.md` - Full error handling documentation
- `/core/utils/exception_types.py` - Centralized exception type groups
- `/docs/patterns/linter_rules.md` - SKUEL003/SKUEL007/SKUEL017 linter rules for Result[T]
