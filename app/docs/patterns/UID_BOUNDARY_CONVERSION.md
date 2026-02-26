---
title: UID Boundary Conversion Pattern
updated: '2026-02-02'
category: patterns
related_skills: []
related_docs: []
---
# UID Boundary Conversion Pattern
*Last updated: 2025-12-05*

## Core Principle: "Type-safe at the edges"

Convert raw strings to typed `EntityUID` at HTTP boundaries using `TypeConverter.to_entity_uid_safe()`. This ensures invalid UIDs are rejected early with proper error responses.

## The Problem

```python
# Route receives raw string from HTTP
@rt("/api/tasks/{uid}")
async def get_task(request, uid: str):
    # This uid could be anything - no validation!
    return await service.get_task(uid)
```

MyPy can't catch invalid UIDs because everything is `str`. Invalid formats slip through to the database layer.

## The Solution

```python
from core.models.type_hints import TypeConverter, EntityUID

@rt("/api/tasks/{uid}")
@boundary_handler()
async def get_task(request, uid: str):
    # Convert at boundary with Result-based error handling
    uid_result = TypeConverter.to_entity_uid_safe(uid)
    if uid_result.is_error:
        return uid_result  # Returns 400 via @boundary_handler

    # Now we have typed EntityUID - MyPy knows it's validated
    entity_uid: EntityUID = uid_result.value
    return await service.get_task(entity_uid)
```

## How It Works

### 1. `is_valid_uid()` - Type Guard

Validates both SKUEL UID formats:

```python
# Dot notation (curriculum domains)
is_valid_uid("ku.yoga.meditation")  # True
is_valid_uid("path.beginner.python")  # True

# Underscore notation (activity domains)
is_valid_uid("task_abc123")  # True
is_valid_uid("event_implement-auth_a1b2")  # True

# Invalid
is_valid_uid("invalid")  # False - no separator
is_valid_uid("123.numeric")  # False - numeric prefix
```

### 2. `TypeConverter.to_entity_uid_safe()` - Boundary Conversion

Returns `Result[EntityUID]` instead of raising exceptions:

```python
# Valid UID
result = TypeConverter.to_entity_uid_safe("ku.yoga")
assert result.is_ok
assert result.value == "ku.yoga"  # EntityUID type

# Invalid UID
result = TypeConverter.to_entity_uid_safe("invalid")
assert result.is_error
# Error category: VALIDATION
# Error message: "Invalid UID format: invalid"
```

### 3. Service Layer - Accepts EntityUID

Services can declare `EntityUID` in signatures (though `str` works due to `NewType`):

```python
# Services accept EntityUID (or str - NewType is erased at runtime)
async def get_task(self, task_uid: EntityUID) -> Result[Task]:
    # Implementation unchanged - EntityUID is str at runtime
    return await self.backend.get(task_uid)
```

## UID Formats

### Dot Notation (Curriculum Domains)
- Pattern: `prefix.parts...`
- Examples: `ku.yoga.meditation`, `path.beginner.python`, `moc.tech.overview`
- Used by: KU, LS, LP, MOC

### Underscore Notation (Activity Domains)
- Pattern: `prefix_slug_random` or `prefix_random`
- Examples: `task_abc123`, `event_meeting_12ab34cd`
- Used by: Task, Event, Habit, Goal, Choice, Principle, Finance

## When to Use

| Layer | Use |
|-------|-----|
| **HTTP Routes** | `TypeConverter.to_entity_uid_safe()` - validates and converts |
| **Services** | Accept `EntityUID` (or `str` for compatibility) |
| **Backends** | Work with raw strings (database doesn't care about types) |

## Migration Path

1. **New code**: Use `to_entity_uid_safe()` in routes
2. **Existing services**: Keep `str` parameters (works with `EntityUID`)
3. **Gradual update**: Update service signatures to `EntityUID` as time permits

## Example: Full Route Implementation

```python
from core.models.type_hints import TypeConverter, EntityUID
from adapters.inbound.boundary import boundary_handler

@rt("/api/tasks/{uid}")
@boundary_handler()
async def get_task(request, uid: str):
    """Get a task by UID with validation."""
    # Step 1: Validate and convert UID
    uid_result = TypeConverter.to_entity_uid_safe(uid)
    if uid_result.is_error:
        return uid_result  # 400 Bad Request

    # Step 2: Get authenticated user
    user_uid = require_authenticated_user(request)

    # Step 3: Verify ownership
    ownership = await tasks_service.verify_ownership(uid_result.value, user_uid)
    if ownership.is_error:
        return ownership  # 404 Not Found

    # Step 4: Get task with validated UID
    return await tasks_service.get_task(uid_result.value)
```

## Related

- `/core/models/type_hints.py` - EntityUID definition, TypeConverter class
- `/core/utils/uid_generator.py` - UID generation utilities
- `/docs/patterns/OWNERSHIP_VERIFICATION.md` - Multi-tenant security
- `/docs/patterns/ERROR_HANDLING.md` - Result[T] pattern
