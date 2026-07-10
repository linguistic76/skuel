# Result Pattern - Quick Reference

> **Fast lookup** for common syntax, methods, and operations

---

## Canonical Result Shapes

### Create + check (the everyday pattern)

```python
from core.utils.result_simplified import Result, Errors

result = Result.ok(task)                          # success (guards against double-wrap)
result = Result.fail(Errors.not_found("Task", uid))  # failure — ErrorContext via Errors factory

if result.is_error:        # NOT .is_err — SKUEL003
    return result
task = result.value        # raises ValueError if accessed on an error result
```

**When to use**: Every service/backend method — internal code returns `Result[T]`, never raises for expected failures.

### Cross-type error propagation

```python
inner = await self.backend.get_user(uid)   # Result[User]
if inner.is_error:
    return Result.fail(inner)              # Result[User] → Result[Task]; NOT Result.fail(inner.expect_error())
```

**When to use**: Whenever the failing `Result`'s type parameter differs from your return type. `Result.fail()` accepts `ErrorContext | str | Result[Any]` and extracts the error internally.

### Reading the error (logging, branching)

```python
if result.is_error:
    error = result.expect_error()          # ErrorContext, guaranteed non-None (MyPy-safe)
    logger.error(f"Failed: {error.message} [{error.code}]")
```

**When to use**: ONLY when you need to *read* the error (category branching, logging). For pure propagation, `Result.fail(result)` is the one path.

### Route fetch + not-found guard

```python
from adapters.inbound.result_helpers import require_found

found = require_found(await service.get(uid), "Task", uid)   # (result, resource, identifier)
if found.is_error:
    return found
task = found.value                         # guaranteed non-None
```

**When to use**: Routes fetching an entity where `Result[T | None]` success-with-None must become a 404. Combines the `is_error` check and the `value is None` check. For user-owned entities prefer `verify_entity_ownership` (fetch + 404 + ownership in one).

### Chaining (functional composition)

```python
result = Result.ok(uid).and_then(get_user).map(extract_prefs)   # and_then: f returns Result; map: f returns plain value
result = await Result.ok(uid).aflat_map(get_user_async)         # async and_then (accepts sync or async f)
result.log_if_error("Task creation failed")                     # logs by severity, returns self
```

**When to use**: Linear pipelines without intermediate branching. Also available: `map_error` (transform error in flight), `inspect`/`inspect_error` (side effects), `or_else(default)`, `expect(msg)`.

---

## Key Infrastructure

### `Errors` factory (SKUEL007 — never `Result.fail("string")`)

All factories live in `core/utils/result_simplified.py` (there is NO `errors_simplified.py`).

| Factory | Signature (key args) | Category → HTTP |
|---------|---------------------|-----------------|
| `Errors.validation` | `(message, field=None, value=None, user_message=None)` | VALIDATION → 400 |
| `Errors.forbidden` | `(action, reason=None, required_role=None)` | FORBIDDEN → 403 |
| `Errors.not_found` | `(resource, identifier=None)` | NOT_FOUND → 404 |
| `Errors.business` | `(rule, message, **details)` | BUSINESS → 422 |
| `Errors.integration` | `(service, message, status_code=None, **details)` | INTEGRATION → 502 |
| `Errors.database` | `(operation, message, query=None, **details)` | DATABASE → 503 |
| `Errors.system` | `(message, exception=None, user_message=None, **details)` | SYSTEM → 500 |
| `Errors.unavailable` | `(feature, reason, **details)` — optional feature not configured (soft) | SYSTEM → 500 |
| `Errors.ps_validation_report` | `(violations: list[Violation])` — wraps `business()` | BUSINESS → 422 |

Decision flow: database op? → `database` · single-field input? → `validation` · multi-entity/state rule? → `business` · missing resource? → `not_found` · external service? → `integration` · optional feature off? → `unavailable` · truly unexpected? → `system`.

### HTTP conversion at the boundary

`@boundary_handler(success_status=200)` (`adapters/inbound/boundary.py`) converts `Result[T]` → `JSONResponse`; `_get_status_for_error()` maps `ErrorCategory` to the status codes above (unknown → 500). Client bodies use `ErrorContext.to_client_dict()` — stack traces and `details` stripped, `message` = `user_message`.

```python
@rt("/api/tasks", methods=["POST"])
@boundary_handler(success_status=201)          # POST create → 201
async def create_task(request: Request) -> Result[Task]:
    return await task_service.create(...)      # auto-converted at the edge
```

### `ErrorContext` (the one error class)

Fields: `category`, `message` (developer), `code` (searchable, e.g. `NOT_FOUND_TASK`), `severity`, `details`, `source_location`, `user_message`, `timestamp`, `stack_trace`. UI rendering uses `.display_message` (`user_message` falling back to `message`). Severity drives `log_if_error()`: CRITICAL→critical, HIGH→error, MEDIUM→warning, LOW→info.

---

## Common Pitfalls

| Problem | Solution |
|---------|----------|
| `.is_err` | `.is_error` (SKUEL003) — the only failure predicate |
| `Result.fail("some message")` | `Result.fail(Errors.system(...))` etc. (SKUEL007); bare strings become generic SYSTEM errors |
| `Result.fail(result.expect_error())` | `Result.fail(result)` — pass the Result itself across type boundaries |
| `.value` without checking `.is_ok` | Raises `ValueError` on error results — check first or use `.or_else(default)` / `.expect(msg)` |
| Multi-field uniqueness as `Errors.validation` | It's a domain rule → `Errors.business(rule=..., ...)` (422, not 400) |
| Unconfigured embeddings/LLM as `Errors.system` | `Errors.unavailable(feature, reason)` — soft degradation, not a failure |
| Callback returning `Result` into a wrapping executor | Produces `Result[Result[T]]` — inner failure reads as success; return raw values from processors, gate in the caller |
| `lambda` inside `and_then`/`map` chains | Named functions (SKUEL012) |
| `from core.utils.errors_simplified import Errors` | Module doesn't exist — `Errors`, `ErrorContext`, `ErrorCategory` all live in `core.utils.result_simplified` |
| Custom exception classes for domain failures | One `ErrorContext` class + `Errors` factory; exceptions only at boundaries |
| Bare `except Exception` when converting to Results | Narrow via `core/utils/exception_types.py` tuples (`NEO4J_EXCEPTIONS` → `Errors.database`, `LLM_EXCEPTIONS` → `Errors.integration`) or annotate (SKUEL017) |

---

**See Also**: [SKILL.md](SKILL.md) for detailed explanations
**See Also**: [PATTERNS.md](PATTERNS.md) for design patterns
**See Also**: [patterns-reference.md](patterns-reference.md) for comprehensive code examples
**See Also**: `/docs/patterns/ERROR_HANDLING.md` for the full error handling architecture
