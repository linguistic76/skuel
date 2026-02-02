---
title: FastHTML Type Hints Pattern Guide
updated: 2025-11-18
category: patterns
related_skills:
- html-htmx
- fasthtml
related_docs: []
---

# FastHTML Type Hints Pattern Guide
**Date:** 2025-11-18
**Status:** Active Reference
**Version:** 1.0
## Related Skills

For implementation guidance, see:
- [@fasthtml](../../.claude/skills/fasthtml/SKILL.md)
- [@html-htmx](../../.claude/skills/html-htmx/SKILL.md)


## Core Principle

**"Type hints do the work, not manual extraction"**

FastHTML automatically extracts and validates parameters based on function type hints. This eliminates ~3-4 lines of boilerplate per route.

---

## The Pattern

### ❌ OLD WAY - Manual Extraction (Verbose)

```python
from fasthtml.common import Request
from core.utils.error_boundary import boundary_handler
from core.utils.result_simplified import Result

@rt("/api/tasks/{uid}/complete", methods=["POST"])
@boundary_handler()
async def complete_task_route(request: Request) -> Result[Any]:
    # Line 1: Extract path parameter
    uid = request.path_params["uid"]

    # Line 2: Parse JSON body
    body = await request.json()

    # Line 3-4: Extract fields from body
    actual_minutes = body.get("actual_minutes")
    quality_score = body.get("quality_score")

    # Line 5: Call service
    return await tasks_service.complete_task_with_cascade(
        uid,
        actual_minutes=actual_minutes,
        quality_score=quality_score
    )
```

**Issues:**
- 🔴 5 lines of boilerplate
- 🔴 No type validation
- 🔴 Manual error handling needed for invalid types
- 🔴 Not self-documenting
- 🔴 `methods=` parameter no longer needed

### ✅ NEW WAY - Type Hints (Clean)

```python
from core.utils.error_boundary import boundary_handler
from core.utils.result_simplified import Result

@rt("/tasks/complete")
@boundary_handler()
async def complete(
    uid: str,                              # Auto-extracted from ?uid=...
    actual_minutes: int | None = None,     # Auto-extracted & validated
    quality_score: float | None = None     # Auto-extracted & validated
) -> Result[Any]:
    return await tasks_service.complete_task_with_cascade(
        uid,
        actual_minutes=actual_minutes,
        quality_score=quality_score
    )
```

**Benefits:**
- ✅ **-4 lines** (60% reduction in boilerplate)
- ✅ **Type validation built-in** (FastHTML validates types)
- ✅ **Self-documenting** (signature shows all parameters)
- ✅ **No request object** (cleaner function signature)
- ✅ **No methods= needed** (FastHTML infers POST from body)

---

## Parameter Extraction Patterns

### 1. Query Parameters (Simple)

```python
# OLD
@rt("/api/tasks")
async def list_tasks_route(request: Request):
    params = dict(request.query_params)
    limit = int(params.get("limit", 100))
    offset = int(params.get("offset", 0))
    include_completed = params.get("include_completed", "false").lower() == "true"

# NEW
@rt("/tasks/list")
async def list_tasks(
    limit: int = 100,              # Auto-converts to int
    offset: int = 0,               # Auto-converts to int
    include_completed: bool = False  # Auto-converts "true"/"false"
):
    # Parameters already extracted and validated!
```

### 2. Path Parameters → Query Parameters

FastHTML prefers query parameters over path parameters for better type inference:

```python
# OLD (Path parameter - requires manual extraction)
@rt("/api/tasks/{uid}")
async def get_task_route(request: Request):
    uid = request.path_params["uid"]  # Manual extraction

# NEW (Query parameter - automatic extraction)
@rt("/tasks/get")
async def get(uid: str):  # Auto-extracted from ?uid=...
    # uid is already a string!
```

**When to use path vs query:**
- **Query parameters (preferred):** IDs, filters, pagination
- **Path parameters (rare):** Truly hierarchical resources only

### 3. Request Body (JSON)

```python
# OLD
@rt("/api/goals/{uid}/progress", methods=["POST"])
async def update_progress_route(request: Request):
    uid = request.path_params["uid"]
    body = await request.json()
    progress_value = body.get("progress", 0)
    notes = body.get("notes", "")
    update_date = body.get("date")

# NEW
@rt("/goals/update-progress")
async def update_progress(
    uid: str,
    progress: float = 0.0,
    notes: str = "",
    date: str | None = None
):
    # FastHTML extracts from JSON body or query params automatically
```

### 4. Optional Parameters

```python
# OLD
@rt("/api/habits/{uid}/track", methods=["POST"])
async def track_habit_route(request: Request):
    uid = request.path_params["uid"]
    body = await request.json()

    # Manual None handling
    completion_date = body.get("date")
    notes = body.get("notes", "")
    value = body.get("value", 1)

# NEW
@rt("/habits/track")
async def track(
    uid: str,
    date: str | None = None,  # Optional parameter
    notes: str = "",          # Default value
    value: int = 1            # Default value
):
    # All parameters automatically extracted with defaults!
```

### 5. Complex Types (Dates, Lists)

```python
# OLD
@rt("/api/tasks/user/{user_uid}")
async def get_user_tasks_route(request: Request):
    user_uid = request.path_params["user_uid"]
    params = dict(request.query_params)

    # Manual date parsing
    start_date = params.get("start_date")
    if start_date:
        start_date = date.fromisoformat(start_date)

    # Manual list parsing
    tags = params.get("tags", "").split(",") if params.get("tags") else []

# NEW
from datetime import date

@rt("/tasks/user")
async def user_tasks(
    user_uid: str,
    start_date: date | None = None,  # Auto-converts ISO date string
    tags: list[str] | None = None    # Auto-converts comma-separated list
):
    # FastHTML handles conversion automatically!
```

---

## Migration Checklist

When converting a route from old to new pattern:

1. ✅ **Remove `methods=` parameter** - FastHTML infers method
2. ✅ **Change URL from `/api/{domain}/{uid}` to `/{domain}/action?uid=...`**
3. ✅ **Remove `Request` parameter** - Use type hints instead
4. ✅ **Add typed parameters** - One parameter per line with type hints
5. ✅ **Remove manual extraction** - Delete path_params, json(), query_params
6. ✅ **Add defaults** - For optional parameters
7. ✅ **Test** - Verify type conversion works as expected

---

## Type Conversion Reference

FastHTML automatically converts query/body parameters to typed values:

| Type Hint | Conversion | Example Input | Converted Value |
|-----------|------------|---------------|-----------------|
| `str` | No conversion | `"hello"` | `"hello"` |
| `int` | String → int | `"42"` | `42` |
| `float` | String → float | `"3.14"` | `3.14` |
| `bool` | String → bool | `"true"`, `"false"` | `True`, `False` |
| `date` | ISO string → date | `"2025-11-18"` | `date(2025, 11, 18)` |
| `datetime` | ISO string → datetime | `"2025-11-18T10:30:00"` | `datetime(...)` |
| `list[str]` | CSV → list | `"a,b,c"` | `["a", "b", "c"]` |
| `T \| None` | Optional | Missing param | `None` |

---

## Common Patterns

### Create Route

```python
@rt("/tasks/create")
@boundary_handler(success_status=201)
async def create(
    title: str,
    priority: str = "medium",
    due_date: date | None = None,
    tags: list[str] | None = None
) -> Result[Task]:
    return await tasks_service.create({
        "title": title,
        "priority": priority,
        "due_date": due_date,
        "tags": tags or []
    })
```

### Get Route

```python
@rt("/tasks/get")
@boundary_handler()
async def get(uid: str) -> Result[Task]:
    return await tasks_service.get(uid)
```

### Update Route

```python
@rt("/tasks/update")
@boundary_handler()
async def update(
    uid: str,
    title: str | None = None,
    priority: str | None = None,
    status: str | None = None
) -> Result[Task]:
    updates = {k: v for k, v in {
        "title": title,
        "priority": priority,
        "status": status
    }.items() if v is not None}

    return await tasks_service.update(uid, updates)
```

### Delete Route

```python
@rt("/tasks/delete")
@boundary_handler()
async def delete(uid: str) -> Result[bool]:
    return await tasks_service.delete(uid)
```

### List Route

```python
@rt("/tasks/list")
@boundary_handler()
async def list_tasks(
    limit: int = 100,
    offset: int = 0,
    status: str | None = None,
    priority: str | None = None
) -> Result[list[Task]]:
    return await tasks_service.list(
        limit=limit,
        offset=offset,
        status=status,
        priority=priority
    )
```

### Domain-Specific Action

```python
@rt("/tasks/complete")
@boundary_handler()
async def complete(
    uid: str,
    actual_minutes: int | None = None,
    quality_score: float | None = None
) -> Result[Task]:
    return await tasks_service.complete_task_with_cascade(
        uid,
        actual_minutes=actual_minutes,
        quality_score=quality_score
    )
```

---

## Benefits Summary

| Metric | Old Pattern | New Pattern | Improvement |
|--------|-------------|-------------|-------------|
| **Lines per route** | ~8-12 | ~4-6 | **40-50% reduction** |
| **Type validation** | Manual | Automatic | **Built-in** |
| **Error handling** | Manual try/catch | FastHTML handles | **Simplified** |
| **Self-documenting** | No | Yes (signature) | **Better DX** |
| **Testability** | Requires Request mock | Direct function call | **Easier testing** |

---

## Testing Type Hints

Type hints make testing easier - no need to mock Request objects:

```python
# OLD - Requires Request mock
async def test_complete_task_old():
    request = Mock()
    request.path_params = {"uid": "task:123"}
    request.json = AsyncMock(return_value={
        "actual_minutes": 30,
        "quality_score": 0.9
    })

    result = await complete_task_route(request)

# NEW - Direct function call
async def test_complete_task_new():
    result = await complete(
        uid="task:123",
        actual_minutes=30,
        quality_score=0.9
    )

    assert result.is_ok
```

---

## Migration Strategy

### Phase 1: New Routes (Immediate)
All **new routes** written from today forward MUST use type hints pattern.

### Phase 2: High-Traffic Routes (Next Sprint)
Migrate routes that get called most frequently:
- CRUD operations (create, get, update, delete, list)
- Authentication routes
- Dashboard/profile routes

### Phase 3: Domain-Specific Routes (Incremental)
Migrate domain-specific routes by domain:
- Tasks → Events → Habits → Goals → etc.

### Phase 4: Legacy Routes (As Needed)
Migrate remaining routes when touching them for other reasons.

---

## Quick Reference Card

```python
# ✅ FastHTML Type Hints Pattern

@rt("/{domain}/{action}")           # Simplified URL
@boundary_handler()                 # Error handling
async def action_name(              # Descriptive function name
    uid: str,                       # Required parameter
    param: int = 0,                 # Optional with default
    optional: str | None = None     # Truly optional
) -> Result[T]:                     # Typed return
    return await service.method(...)
```

**Remember:**
1. No `methods=` parameter
2. No `Request` object
3. No manual extraction
4. Type hints do everything!

---

## References

- FastHTML Best Practices: `/docs/FastHTML Best Practices – fasthtml.html`
- Migration Guide: `/docs/API_MIGRATION_FASTHTML.md`
- Route Factory: `/core/infrastructure/routes/crud_route_factory.py`
- Cleanup Analysis: `/docs/analysis/ROUTE_CLEANUP_OPPORTUNITIES.md`

---

**Last Updated:** 2025-11-18
**Status:** Active - use this pattern for all new routes
