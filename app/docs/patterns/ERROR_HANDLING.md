---
title: Error Handling Architecture
updated: 2026-01-25
category: patterns
related_skills:
- result-pattern
- ui-error-handling
related_docs: []
---

# Error Handling Architecture

**Status**: ✅ Migration Complete (September 24, 2025)
**Current Implementation**: `result_simplified.py` with boundary handlers

## Quick Start

**Skills:** [@result-pattern](../../.claude/skills/result-pattern/SKILL.md), [@ui-error-handling](../../.claude/skills/ui-error-handling/SKILL.md)

For hands-on implementation guidance:
1. Invoke `@result-pattern` for Result[T] patterns and error factories
2. See [QUICK_REFERENCE.md](../../.claude/skills/result-pattern/QUICK_REFERENCE.md) for decision trees
3. Continue reading below for architectural context and detailed patterns

**Related ADRs:** [ADR-022](../decisions/ADR-022-graph-native-authentication.md) - Graph-native auth with Result[T]

---

## Core Philosophy: Results Internally, Exceptions at Boundaries

SKUEL follows a clean, predictable error handling pattern:
- **Inside the system**: Use `Result[T]` for all operations
- **At system boundaries**: Convert Results to exceptions or HTTP responses
- **One way forward**: Consistent pattern across all layers
- **No defensive programming**: Never use `hasattr` - use Protocol-based interfaces

## The Result Pattern

### Basic Structure

```python
from core.utils.result_simplified import Result, Errors

# Success
result = Result.ok(value)

# Failure with rich context
result = Result.fail(Errors.validation(
    "Invalid email format",
    field="email",
    value=user_input,
    user_message="Please enter a valid email address"
))

# Check result
if result.is_ok:
    value = result.value
else:
    error = result.error
    print(f"Error: {error.message} (Category: {error.category})")
```

### Error Categories (6 Total)

| Category | Purpose | HTTP Status | Retry Strategy | Example |
|----------|---------|-------------|----------------|---------|
| `VALIDATION` | Invalid input data | 400 Bad Request | User must fix | Missing required field |
| `NOT_FOUND` | Resource doesn't exist | 404 Not Found | No retry | Entity not in database |
| `DATABASE` | Storage layer issues | 503 Service Unavailable | Exponential backoff | Connection timeout |
| `INTEGRATION` | External service issues | 502 Bad Gateway | Circuit breaker | API call failed |
| `BUSINESS` | Domain rule violations | 422 Unprocessable | User must fix | Insufficient balance |
| `SYSTEM` | Unexpected errors | 500 Internal Error | Log and alert | Null pointer exception |

### ErrorContext Structure

```python
@dataclass
class ErrorContext:
    # --- Sent to clients (via to_client_dict()) ---
    category: ErrorCategory              # How to handle
    code: str                           # Searchable (e.g., "DB_CONN_TIMEOUT")
    severity: ErrorSeverity             # Logging level (LOW, MEDIUM, HIGH, CRITICAL)
    user_message: Optional[str]        # Safe for UI (becomes "message" in response)
    timestamp: datetime                 # When it occurred

    # --- Internal only (to_dict() for logging, stripped from HTTP responses) ---
    message: str                         # Developer-facing detail
    details: dict[str, Any]            # Debugging data (field, value, etc.)
    source_location: Optional[str]     # file:function:line
    stack_trace: Optional[str]         # For critical errors
```

**Two serialization methods:**
- `to_dict()` — all fields, for internal logging (`log_if_error()`, structured logs)
- `to_client_dict()` — 5 safe fields only, used by `result_to_response()` at HTTP boundaries

## The Three-Layer Pattern

### Layer 1: Backends (Data Layer)
```python
# Backends ALWAYS return Result[T]
@safe_backend_operation("create_report")
async def create(self, report: Report) -> Result[Report]:
    try:
        node = to_neo4j_node(report)
        result = await self.execute_query(
            "CREATE (r:Report $props) RETURN r",
            props=node
        )
        created = from_neo4j_node(result['r'], Report)
        return Result.ok(created)
    except Neo4jError as e:
        # Automatically wrapped in Result.fail by decorator
        raise
```

### Layer 2: Services (Business Logic)
```python
# Services use Result[T] throughout
class ReportService:
    async def create_report(self, data: dict) -> Result[Report]:
        # Validation returns Result
        validation_result = self._validate_create(data)
        if not validation_result.is_ok:
            return validation_result

        # Backend also returns Result
        report = Report(**data)
        create_result = await self.backend.create(report)

        # Chain operations without try/catch
        if create_result.is_ok:
            # Additional business logic
            await self._send_notification(create_result.value)

        return create_result  # Propagate Result
```

### Layer 3: Routes (System Boundary)
```python
# Routes use @boundary_handler to convert Results
@rt("/api/journals")
@boundary_handler(success_status=201)
async def create_journal_route(request):
    data = await request.json()

    # Service returns Result
    result = await journal_service.create_journal(data)

    # boundary_handler automatically converts:
    # - Result.ok() → (json_body, success_status)
    # - Result.fail() → (error_json, error_status)
    return result
```

### Layer 4: UI Routes (Activity Domains)

*Added: 2026-01-24*

**Pattern:** "Typed params, Result[T] propagation, visible error banners"

Activity domain UI routes (Tasks, Goals, Habits, Events, Choices, Principles) use a specialized error-handling pattern that renders errors as visible UI banners instead of returning empty lists.

```python
from dataclasses import dataclass
from core.utils.result_simplified import Errors, Result

# 1. Define typed query parameters
@dataclass
class Filters:
    status: str
    sort_by: str

def parse_filters(request) -> Filters:
    """Extract filter parameters from request query params."""
    return Filters(
        status=request.query_params.get("filter_status", "active"),
        sort_by=request.query_params.get("sort_by", "default"),
    )

# 2. Error banner component
def render_error_banner(message: str) -> Div:
    """Render error banner for UI failures."""
    return Div(
        Div(
            P("⚠️ Error", cls="font-bold text-error"),
            P(message, cls="text-sm"),
            cls="alert alert-error",
        ),
        cls="mb-4",
    )

# 3. Routes call service facades that return Result[T]
@rt("/tasks")
async def tasks_dashboard(request) -> Any:
    user_uid = require_authenticated_user(request)
    filters = parse_filters(request)

    # Single service call returns entities + stats (+ projects/assignees for Tasks)
    filtered_result = await tasks_service.get_filtered_context(
        user_uid, status_filter=filters.status_filter, sort_by=filters.sort_by,
    )

    # CHECK FOR ERRORS - show banner instead of empty list
    if filtered_result.is_error:
        error_content = Div(
            TasksViewComponents.render_view_tabs(active_view="list"),
            render_error_banner("Failed to load tasks"),
            cls=f"{Spacing.PAGE} {Container.WIDE}",
        )
        return create_tasks_page(error_content, request=request)

    # Extract values only after error check
    ctx = filtered_result.value
    tasks, stats = ctx["entities"], ctx["stats"]
    return TasksViewComponents.render_list_view(tasks, stats, ...)
```

**Benefits:**
- **User-visible errors** - No more silent failures with empty lists
- **Debuggability** - Full error context in structured logs
- **Consistency** - All Activity domains use same pattern
- **Type safety** - Dataclasses prevent parameter extraction bugs

**Implementation Status (January 2026):**
- ✅ Tasks, Goals, Habits, Events - Complete
- 🔄 Choices, Principles - In progress

**Reference:** See `/docs/patterns/UI_COMPONENT_PATTERNS.md` for full implementation details.

## Key Components

### 1. Result Type (`/core/utils/result_simplified.py`)
- Type-safe container for success or failure
- 59% code reduction from original implementation
- Rich error information with ErrorContext
- Prevents double-wrapping

### 2. Error Boundary Utilities (`/adapters/inbound/boundary.py` + `/adapters/inbound/boundary.py`)
```python
# Decorator for routes - converts Result to HTTP
@boundary_handler(success_status=200)
async def route_handler(request):
    return await service.operation()  # Returns Result

# Decorator for backends - catches exceptions
@safe_backend_operation("operation_name")
async def backend_method(self):
    # Exceptions automatically wrapped in Result.fail()

# Manual conversion when needed
response = result_to_response(result)  # → (body, status_code)
exception = result_to_exception(result)  # → Exception (rarely needed)
```

### 3. Error Factory Methods
```python
# Validation errors - 400
Errors.validation(message, field=None, value=None, user_message=None)

# Resource not found - 404
Errors.not_found(resource, identifier=None)

# Database errors - 503
Errors.database(operation, message, query=None, **details)

# External service errors - 502
Errors.integration(service, message, status_code=None, **details)

# Business rule violations - 422
Errors.business(rule, message, **details)

# System/unexpected errors - 500
Errors.system(message, exception=None, **details)
```

### 4. Event Handler Decorator (`@safe_event_handler`)

For event handlers that should log errors but not propagate them (event-driven architecture):

```python
from core.utils.error_boundary import safe_event_handler

class KuService:
    @safe_event_handler("knowledge.applied_in_task")
    async def handle_knowledge_applied_in_task(self, event) -> None:
        """
        Handle KnowledgeAppliedInTask event.

        The decorator provides:
        - Structured logging with event context on failure
        - Error categorization for monitoring
        - Consistent error handling across all event handlers
        """
        await self.increment_substance_metric(
            ku_uid=event.knowledge_uid,
            metric="times_applied_in_tasks",
            timestamp_field="last_applied_date",
            timestamp=event.occurred_at,
        )
        self.logger.debug(
            f"Substance updated: {event.knowledge_uid} applied in task {event.task_uid}"
        )
```

**Why event handlers don't propagate errors:**
- Event handlers run asynchronously
- The event bus may have multiple handlers for the same event
- One handler failing shouldn't prevent other handlers from running

### 5. Structured Logging for Exception Blocks

When exception blocks must remain (graceful degradation, internal helpers), use structured logging:

```python
# ❌ WRONG - Unstructured logging
except Exception as e:
    logger.error(f"Failed to load data: {e}")
    return []

# ✅ CORRECT - Structured logging with context
except Exception as e:
    logger.error(
        "Failed to load data - returning empty",
        extra={
            "user_uid": user_uid,
            "error_type": type(e).__name__,
            "error_message": str(e),
        },
    )
    return []
```

**Standard fields for structured exception logging:**
| Field | Purpose |
|-------|---------|
| `error_type` | Exception class name (e.g., `"ValueError"`) |
| `error_message` | String representation of exception |
| `user_uid` | User context if available |
| `entity_uid` | Entity being operated on |
| `operation` | Operation that failed |
| Additional context | Domain-specific fields |

This enables:
- Log aggregation and filtering by error type
- Monitoring dashboards and alerting
- Easier debugging with full context

## Fail-Fast Philosophy for Required Dependencies
*Last updated: January 2026*

**Core Principle:** "All dependencies are REQUIRED - no graceful degradation"

SKUEL distinguishes between **bootstrap dependencies** (must exist) and **runtime operations** (may fail with `Result[T]`):

| Layer | Pattern | Handling |
|-------|---------|----------|
| **Bootstrap** | Factory/service exists | Fail-fast at startup if missing |
| **Runtime** | Methods return `Result[T]` | Propagate to HTTP boundary (500) |
| **UI** | Components expect data | No None handling, no fallbacks |

### Anti-Pattern: Graceful Degradation

```python
# ❌ WRONG - Graceful degradation violates fail-fast
async def _get_intelligence_data(context):
    if not services.context_intelligence:  # Silent failure
        logger.debug("Intelligence factory not available")
        return {"daily_plan": None, "alignment": None}  # Fallback

    try:
        plan = await intelligence.get_ready_to_work_on_today()
        return {"daily_plan": plan.value if plan.is_ok else None}
    except Exception as e:
        logger.debug(f"Failed: {e}")  # Silent failure
        return {"daily_plan": None}
```

**Problems:**
- Factory check enables "soft failures" - hides bootstrap problems
- try/except swallows errors - debugging nightmare
- None fallbacks propagate to UI - more defensive code needed

### Correct Pattern: Fail-Fast + Result Propagation

```python
# ✅ CORRECT - Fail-fast + Result[T] propagation
async def _get_intelligence_data(context: UserContext) -> Result[dict[str, Any]]:
    """Get intelligence data. Returns Result[T] for proper error propagation."""
    # Factory is REQUIRED (bootstrap dependency) - no graceful degradation
    intelligence = services.context_intelligence.create(context)

    # Methods return Result[T] - propagate errors via expect_error()
    plan_result = await intelligence.get_ready_to_work_on_today()
    if plan_result.is_error:
        return plan_result.expect_error()

    alignment_result = await intelligence.calculate_life_path_alignment()
    if alignment_result.is_error:
        return alignment_result.expect_error()

    return Result.ok({
        "daily_plan": plan_result.value,
        "alignment": alignment_result.value,
    })
```

**Benefits:**
- No factory check - if factory doesn't exist, we have a bootstrap bug
- No try/except - Result pattern handles errors explicitly
- Errors propagate to HTTP boundary where they become 500 responses

### UI Components: Expect Data

```python
# ❌ WRONG - Optional parameters with fallbacks
def OverviewView(
    context: UserContext,
    daily_plan: "DailyWorkPlan | None" = None,  # Optional
    alignment: "LifePathAlignment | None" = None,
) -> Div:
    if daily_plan is None:
        return Div(P("Loading..."))  # Fallback UI

# ✅ CORRECT - Required parameters
def OverviewView(
    context: UserContext,
    daily_plan: "DailyWorkPlan",  # Required
    alignment: "LifePathAlignment",  # Required
) -> Div:
    # Component expects data - if None reaches here, it's a bug
    return Div(
        _daily_work_plan_card(daily_plan),
        _alignment_breakdown(alignment),
    )
```

**Key Distinction:** Empty list `[]` is valid data (user has no synergies). The fix removes `| None`, NOT empty checks.

### Route Handler Pattern

```python
@rt("/profile")
async def profile_page(request: Request) -> Any:
    user_uid = require_authenticated_user(request)
    context = await _get_user_context(user_uid)

    # Result propagation at HTTP boundary
    intel_result = await _get_intelligence_data(context)
    if intel_result.is_error:
        return JSONResponse(
            {"error": str(intel_result.error)},
            status_code=500,  # Fail clearly at boundary
        )

    intel_data = intel_result.value
    content = OverviewView(
        context,
        daily_plan=intel_data["daily_plan"],
        alignment=intel_data["alignment"],
    )
    # ...
```

**See:**
- `/adapters/inbound/user_profile_ui.py` - Profile Hub implementation
- `/ui/profile/domain_views.py` - UI components with required parameters

---

## Common Patterns

### Pattern 1: Chain Operations
```python
async def complex_operation(self, data: dict) -> Result[Output]:
    # Validation
    validation = self._validate(data)
    if not validation.is_ok:
        return validation

    # Permission check
    permission = await self._check_permissions(data)
    if not permission.is_ok:
        return permission

    # Main operation
    result = await self._perform_operation(data)
    if not result.is_ok:
        return result

    # Format output
    return Result.ok(self._format_output(result.value))
```

### Pattern 2: Early Return
```python
async def get_entity(self, uid: str) -> Result[Entity]:
    # Check existence
    get_result = await self.backend.get(uid)
    if not get_result.is_ok:
        return get_result  # Propagate backend error

    if not get_result.value:
        return Result.fail(Errors.not_found("Entity", uid))

    # Process entity
    entity = get_result.value
    processed = self._process(entity)
    return Result.ok(processed)
```

### Pattern 3: Collect Multiple Results
```python
async def batch_operation(self, ids: List[str]) -> Result[List[Entity]]:
    results = []
    errors = []

    for id in ids:
        result = await self.get_entity(id)
        if result.is_ok:
            results.append(result.value)
        else:
            errors.append(f"{id}: {result.error.message}")

    if errors:
        return Result.fail(Errors.business(
            "Batch operation partially failed",
            failed_ids=errors,
            successful_count=len(results)
        ))

    return Result.ok(results)
```

### Pattern 4: Transaction Pattern
```python
async def transactional_operation(self) -> Result[bool]:
    tx = await self.begin_transaction()

    try:
        # Multiple operations in transaction
        step1 = await self.operation1(tx)
        if not step1.is_ok:
            await tx.rollback()
            return step1

        step2 = await self.operation2(tx, step1.value)
        if not step2.is_ok:
            await tx.rollback()
            return step2

        await tx.commit()
        return Result.ok(True)

    except Exception as e:
        await tx.rollback()
        return Result.fail(Errors.database(
            "transaction",
            f"Transaction failed: {e}"
        ))
```

## Debugging Features

### Searchable Error Codes
Every error has a unique, searchable code:
```bash
# Find all database connection errors
grep "DB_CONNECTION" logs/*.log

# Find validation errors for specific field
grep "VALIDATION_FIELD_EMAIL" logs/*.log

# Find all critical errors
grep "SEVERITY_CRITICAL" logs/*.log
```

### Source Location Tracking (Internal Only)
Errors automatically capture origin for server-side debugging (stripped from client responses):
```python
error.source_location
# "services/submissions_core_service.py:create_report:45"
```

### Rich Context for Debugging
```python
Errors.database(
    operation="connection",
    message="Connection timeout after 3 retries",
    host="neo4j://localhost:7687",
    timeout=30,
    retry_count=3,
    last_error="Connection refused",
    connection_pool_size=10,
    active_connections=10
)
```

### Logging Integration
```python
result = await some_operation()

# Automatic logging with appropriate level
result.log_if_error("Failed to process user request")
# - CRITICAL → logger.critical()
# - HIGH → logger.error()
# - MEDIUM → logger.warning()
# - LOW → logger.info()
```

## Best Practices

### DO ✅
- Return `Result.ok(None)` for "not found" (not an error at backend level)
- Use `Result.fail()` for actual errors
- Propagate Results through service layers
- Convert to responses only at boundaries
- Use specific error factories (validation_error, database_error, etc.)
- Include debugging context in details dict
- Provide user_message for validation/business errors
- Handle errors by category, not specific types

### DON'T ❌
- Mix Result and exceptions in same layer
- Catch exceptions in services (use Result)
- Return Result from routes (convert at boundary)
- Lose error context when propagating
- Use generic errors when specific ones exist
- Create custom error classes
- Use hasattr to check for error attributes
- Expose internal error details to users

## Migration Impact & Metrics

### Code Reduction
- **Lines of code**: 891 → 369 (59% reduction)
- **Error categories**: 23 → 6 (74% reduction)
- **Error classes**: 11 → 1 (91% reduction)
- **Total migration**: ~8,000 lines updated

### Backends Migrated (✅ Complete)
- journals_neo4j_backend.py
- tasks_neo4j_backend.py
- events_neo4j_backend.py
- habits_neo4j_backend.py
- finance_neo4j_backend.py
- users_neo4j_backend.py

### Services Migrated (✅ Complete)
- journal_core_service.py
- tasks_service.py
- events_service.py
- habits_service.py
- finance_service.py
- unified_knowledge_service.py

### Routes Migrated (✅ Complete)
- submissions_routes.py (includes JOURNALS_CONFIG — journal routes merged here Feb 2026)
- tasks_routes.py
- events_routes.py
- habits_routes.py
- finance_routes.py
- knowledge_routes.py

## Performance Benefits

1. **No exception stack unwinding** inside system
2. **Faster error propagation** through Result chain
3. **Less memory overhead** from exception objects
4. **Better branch prediction** with consistent patterns
5. **Compile-time optimization** possible with Result type

## Testing Benefits

```python
# Easy to test error paths
async def test_validation_error():
    # Mock backend to return specific error
    mock_backend.get.return_value = Result.fail(
        Errors.not_found("Report", "123")
    )

    result = await service.get_report("123")

    assert not result.is_ok
    assert result.error.category == ErrorCategory.NOT_FOUND
    assert "123" in result.error.message
```

## Safe Form Parsing Pattern
*Added: January 25, 2026*

**Context:** HTML form submissions can send empty strings, missing values, or invalid text for numeric fields, causing `ValueError` or `TypeError` crashes.

**Problem:**
```python
# ❌ UNSAFE - Crashes on invalid input
preferences_update = {
    "available_minutes_daily": int(form_data.get("available_minutes_daily", 60)),
    "enable_reminders": bool(form_data.get("enable_reminders")),
    "weekly_task_goal": int(form_data.get("weekly_task_goal", 10)),
}
# ValueError if user submits empty field or non-numeric text
# TypeError if form_data.get() returns None
```

**Solution: Safe Parsing Helpers**

```python
def safe_int(value: Any, default: int) -> int:
    """
    Safely parse integer from form data.

    Args:
        value: Form field value (may be None, empty string, or invalid)
        default: Default value if parsing fails

    Returns:
        Parsed integer or default

    Examples:
        >>> safe_int("25", 10)
        25
        >>> safe_int("", 10)
        10
        >>> safe_int(None, 10)
        10
        >>> safe_int("invalid", 10)
        10
    """
    if not value:
        return default
    try:
        return int(value)
    except (ValueError, TypeError):
        return default


def safe_bool(value: Any, default: bool = False) -> bool:
    """
    Safely parse boolean from form data.

    HTML checkboxes send "on" when checked, nothing when unchecked.

    Args:
        value: Form field value
        default: Default value if parsing fails

    Returns:
        Parsed boolean or default

    Examples:
        >>> safe_bool("on", False)
        True
        >>> safe_bool(None, False)
        False
        >>> safe_bool("true", False)
        True
    """
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    # HTML checkbox values
    if value in ("on", "true", "True", "1"):
        return True
    if value in ("off", "false", "False", "0"):
        return False
    return default
```

**Usage in Routes:**

```python
@rt("/profile/settings/save")
async def save_user_settings(request: Request) -> Any:
    user_uid = require_authenticated_user(request)
    form_data = await request.form()

    # ✅ SAFE - Uses defaults on invalid input
    preferences_update = {
        "available_minutes_daily": safe_int(form_data.get("available_minutes_daily"), 60),
        "enable_reminders": safe_bool(form_data.get("enable_reminders"), False),
        "reminder_minutes_before": safe_int(form_data.get("reminder_minutes_before"), 15),
        "weekly_task_goal": safe_int(form_data.get("weekly_task_goal"), 10),
        "daily_habit_goal": safe_int(form_data.get("daily_habit_goal"), 3),
        "monthly_learning_hours": safe_int(form_data.get("monthly_learning_hours"), 20),
    }

    # Service call with validated data
    result = await user_service.update_preferences(user_uid, preferences_update)
    if result.is_error:
        # Log detailed error (don't leak to user)
        logger.error(
            "Failed to save user preferences",
            extra={"user_uid": user_uid, "error": str(result.error)},
        )
        # Return user-safe error message
        return Div(
            P("Failed to save preferences. Please try again.", cls="text-error"),
            P("If this problem persists, contact support.", cls="text-sm text-base-content/50 mt-2"),
            cls="p-4",
        )

    return render_success_message()
```

**Benefits:**
- ✅ No more 500 errors from invalid form submissions
- ✅ Graceful fallback to sensible defaults
- ✅ Clear separation: parsing vs business logic
- ✅ Easy to test edge cases

**Implementation:** `/adapters/inbound/user_profile_ui.py` (lines 58-117)

**See Also:** `/docs/patterns/API_VALIDATION_PATTERNS.md` for Pydantic request model validation (JSON bodies)

---

## Configuration vs Runtime Error Handling
*Added: January 25, 2026*

**Context:** Services with optional features (like intelligence services) need clear distinction between configuration errors (setup issues) and runtime errors (computation failures).

**Problem:**

```python
# ❌ TOO NARROW - Only catches AttributeError
try:
    intelligence = services.context_intelligence.create(context)
    plan_result = await intelligence.get_ready_to_work_on_today()
    return Result.ok({"daily_plan": plan_result.value})
except AttributeError as e:
    # Config error → basic mode
    return Result.ok(None)
# TypeError, KeyError would propagate as failures instead of gracefully degrading
```

**Solution: Layered Exception Handling**

```python
async def _get_intelligence_data(
    context: UserContext,
) -> "Result[dict[str, Any] | None]":
    """
    Get intelligence data for OverviewView if available.

    Error Handling Strategy:
    - Configuration errors (AttributeError, TypeError, KeyError) → basic mode
    - Runtime computation errors → Result.fail() (propagates to HTTP boundary)
    - Service not available → basic mode

    Returns:
        - Result.ok(dict) - Intelligence data when fully configured
        - Result.ok(None) - Intelligence not available (use basic mode UI)
        - Result.fail() - Actual error during intelligence computation
    """
    # Check if factory is available
    if not services.context_intelligence:
        logger.info("Intelligence factory not configured - using basic mode")
        return Result.ok(None)

    try:
        intelligence = services.context_intelligence.create(context)

        # Methods return Result[T] - check for runtime errors
        plan_result = await intelligence.get_ready_to_work_on_today()
        if plan_result.is_error:
            return Result.fail(plan_result.expect_error())

        alignment_result = await intelligence.calculate_life_path_alignment()
        if alignment_result.is_error:
            return Result.fail(alignment_result.expect_error())

        return Result.ok({
            "daily_plan": plan_result.value,
            "alignment": alignment_result.value,
        })

    except (AttributeError, TypeError, KeyError) as e:
        # Configuration errors - intelligence services not properly configured
        # These are setup issues, not runtime errors - degrade gracefully to basic mode
        logger.warning(
            "Intelligence services not properly configured - using basic mode",
            extra={
                "error_type": type(e).__name__,
                "error_message": str(e),
            },
        )
        return Result.ok(None)
    except Exception as e:
        # Unexpected error during intelligence computation
        # This is a true runtime error - propagate as failure
        logger.error(
            "Unexpected error in intelligence computation",
            extra={
                "error_type": type(e).__name__,
                "error_message": str(e),
            },
        )
        from core.utils.result_simplified import Errors
        return Result.fail(Errors.system(f"Intelligence computation failed: {e}"))
```

**Error Categories:**

| Error Type | Meaning | Action | Example |
|------------|---------|--------|---------|
| Service missing | Factory not configured | Basic mode | `if not services.intelligence` |
| `AttributeError` | Interface mismatch | Basic mode | Method doesn't exist |
| `TypeError` | Wrong data type | Basic mode | Method returns int instead of dict |
| `KeyError` | Missing config key | Basic mode | Config dict missing required field |
| `Exception` | Runtime computation error | Fail (500) | Division by zero, graph query error |

**Route Handling:**

```python
@rt("/profile")
async def profile_page(request: Request) -> Any:
    user_uid = require_authenticated_user(request)
    context = await _get_user_context(user_uid)

    # Get intelligence data - may return None for basic mode
    intel_result = await _get_intelligence_data(context)
    if intel_result.is_error:
        # Actual error - propagate to HTTP boundary
        return JSONResponse(
            {"error": str(intel_result.error)},
            status_code=500,
        )

    intel_data = intel_result.value  # May be None (basic mode) or dict (full mode)

    # Create view - passes None for intelligence data in basic mode
    if intel_data is not None:
        content = OverviewView(
            context,
            daily_plan=intel_data["daily_plan"],
            alignment=intel_data["alignment"],
        )
    else:
        # Basic mode - show profile without intelligence features
        content = OverviewView(context)

    return create_profile_page(content, ...)
```

**Benefits:**
- ✅ Clear separation: config issues → graceful degradation, runtime errors → fail fast
- ✅ Better structured logging distinguishes error categories
- ✅ Easier debugging (config vs computation problems)
- ✅ Documented error handling strategy in docstring

**Implementation:** `/adapters/inbound/user_profile_ui.py` (lines 633-716)

**Anti-Pattern:** Don't use broad `except Exception` for configuration errors - it would catch runtime errors too.

---

## Integration with Other Patterns

### Works with Generic Programming
```python
class BaseService[T]:
    async def get(self, uid: str) -> Result[T]:
        # Generic Result handling
```

### Works with Repository Pattern
```python
class Repository[T]:
    async def find(self, spec: QuerySpec) -> Result[List[T]]:
        # Repository returns Results
```

### Works with Relationship-Centric Architecture
```python
async def add_relationship(
    self, from_uid: str, rel_type: str, to_uid: str
) -> Result[Relationship]:
    # Graph operations return Results
```

## File Locations

- **Current Implementation**: `/core/utils/result_simplified.py`
- **Boundary Utilities**: `/adapters/inbound/boundary.py` + `/adapters/inbound/boundary.py`
- **Migration Guide**: `/core/utils/result_migration_guide.md`
- **Old Implementation**: `/core/utils/result.py` (deprecated)
- **Tests**: `/tests/test_result_simplified.py`

## Future Enhancements

1. **Telemetry Integration**: Send error metrics to monitoring
2. **Automatic Retry**: Implement retry strategies by category
3. **Circuit Breakers**: For integration errors
4. **Error Aggregation**: Collect multiple validation errors
5. **GraphQL Integration**: Map Results to GraphQL errors

## Conclusion

The "Results internally, exceptions at boundaries" pattern with simplified Result[T] provides:

- **Clean architecture**: Clear separation of concerns
- **Predictable behavior**: No surprise exceptions
- **Rich error context**: Excellent debugging capabilities
- **Type safety**: Explicit error handling
- **Performance**: No exception overhead internally
- **Testability**: Easy to test error paths
- **One way forward**: Consistent pattern everywhere

This error handling architecture aligns perfectly with SKUEL's principles of clean, maintainable code with a single clear path forward, while providing enterprise-grade debugging and monitoring capabilities.

---

*Last Updated: After completing migration to Result pattern across all services and adding relationship-centric architecture support*