---
title: API Validation Patterns
updated: 2026-01-24
status: current
category: patterns
tags:
- patterns
- api
- validation
- pydantic
- routes
related:
- three_tier_type_system.md
- ROUTE_FACTORIES.md
- ERROR_HANDLING.md
related_skills:
- pydantic
---

# API Validation Patterns

*Created: 2026-01-24*

## Quick Start

**Skills:** [@pydantic](../../.claude/skills/pydantic/SKILL.md), [@skuel-form-patterns](../../.claude/skills/skuel-form-patterns/SKILL.md)

For hands-on implementation:
1. Invoke `@pydantic` for request model validation patterns
2. Invoke `@skuel-form-patterns` for form handling and error display
3. See [QUICK_REFERENCE.md](../../.claude/skills/pydantic/QUICK_REFERENCE.md) for validation examples
4. Continue below for complete validation strategy

**Related ADRs:** [ADR-035](../decisions/ADR-035-tier-selection-guidelines.md) - Pydantic's role in three-tier system

---

## Core Principle

> "Validate at boundaries, fail fast with clear errors"

SKUEL validates all external input at API boundaries to prevent 500 errors from malformed data. Use appropriate validation strategies based on input type:

- **Query Parameters (GET):** Helper functions with `Result[T]`
- **JSON Bodies (POST/PUT):** Pydantic request models

## Two-Tier Validation Strategy

### Query Parameters: Helper Functions

**Use Case:** Simple string inputs from URL query params

**Pattern:** Lightweight helper functions that return `Result[T]`

**Example:**
```python
def parse_bool_param(params: dict[str, str], key: str, default: bool = True) -> bool:
    """Parse boolean from query param (handles true/1/yes/on)."""
    value = params.get(key, str(default)).lower()
    return value in ("true", "1", "yes", "on")

def validate_enum(value: str, allowed: list[str]) -> Result[str]:
    """Validate enum value against whitelist."""
    if value not in allowed:
        return Result.fail(
            Errors.validation(
                message=f"Value must be one of: {allowed}",
                field="param_name",
                value=value,
            )
        )
    return Result.ok(value)
```

**Usage in Routes:**
```python
@rt("/api/context/dashboard")
@boundary_handler()
async def get_dashboard(request: Request, user_uid: str) -> Result[Any]:
    params = dict(request.query_params)

    # Boolean parsing
    include_predictions = parse_bool_param(params, "include_predictions", default=True)

    # Enum validation
    time_window_result = validate_time_window(params.get("time_window", "7d"))
    if time_window_result.is_error:
        return time_window_result  # 400 with clear error

    return await service.get_dashboard(
        user_uid=user_uid,
        include_predictions=include_predictions,
        time_window=time_window_result.value,
    )
```

**Benefits:**
- ✅ Flexible boolean parsing (true/1/yes/on)
- ✅ Clear 400 errors with field context
- ✅ Reusable across routes
- ✅ Minimal overhead

---

### JSON Bodies: Pydantic Request Models

**Use Case:** Complex structured data from POST/PUT request bodies

**Pattern:** Pydantic `BaseModel` classes with field validation

**File Pattern:** `core/models/{domain}/{domain}_request.py` (where {domain} is tasks, goals, habits, etc.)

**Example:**
```python
# core/models/context/context_request.py

from typing import Any, Literal
from pydantic import BaseModel, Field

class TaskCompletionRequest(BaseModel):
    """Request model for completing a task with context awareness."""

    context: dict[str, Any] = Field(
        default_factory=dict,
        description="Context data (knowledge_applied, time_invested_minutes, quality)"
    )
    reflection: str = Field(
        default="",
        max_length=2000,
        description="Reflection notes on task completion"
    )

    class Config:
        json_schema_extra = {
            "example": {
                "context": {
                    "knowledge_applied": ["ku.python"],
                    "time_invested_minutes": 120
                },
                "reflection": "Great learning experience"
            }
        }
```

**Usage in Routes:**
```python
@rt("/api/context/task/complete", methods=["POST"])
@boundary_handler(success_status=200)
async def complete_task(
    request: Request,
    task_uid: str,
    body: TaskCompletionRequest  # FastHTML auto-parses & validates
) -> Result[Any]:
    """
    Complete task with context awareness.

    Pydantic automatically validates:
    - JSON structure (dict vs string)
    - Field types (str, int, etc.)
    - Field constraints (max_length, etc.)
    - Returns 422 on validation failure
    """
    return await service.complete_task_with_context(
        task_uid=task_uid,
        completion_context=body.context,  # Type-safe access
        reflection_notes=body.reflection,
    )
```

**Benefits:**
- ✅ Automatic structure validation
- ✅ Type-safe field access (`body.field` vs `body["field"]`)
- ✅ MyPy catches errors at dev time
- ✅ Self-documenting (model shows expected structure)
- ✅ Clear 422 errors with field-level details
- ✅ No manual JSON parsing boilerplate

---

## Validation Error Responses

### Query Parameter Errors (400 Bad Request)

```python
# Helper function returns Result.fail()
return Result.fail(
    Errors.validation(
        message="time_window must be one of: ['7d', '30d', '90d']",
        field="time_window",
        value="invalid",
    )
)
```

**HTTP Response:**
```json
{
  "error": {
    "type": "validation",
    "message": "time_window must be one of: ['7d', '30d', '90d']",
    "field": "time_window",
    "value": "invalid"
  }
}
```

---

### JSON Body Errors (422 Unprocessable Entity)

Pydantic automatically generates validation errors:

**Request:**
```json
{
  "context": "string",  // Should be dict
  "reflection": "x" * 2001  // Exceeds max_length
}
```

**HTTP Response (422):**
```json
{
  "detail": [
    {
      "type": "dict_type",
      "loc": ["body", "context"],
      "msg": "Input should be a valid dictionary",
      "input": "string"
    },
    {
      "type": "string_too_long",
      "loc": ["body", "reflection"],
      "msg": "String should have at most 2000 characters",
      "input": "xxx..."
    }
  ]
}
```

---

## Pydantic Request Model Patterns

### Basic Fields

```python
class MyRequest(BaseModel):
    # Required field
    title: str

    # Optional field with default
    description: str = ""

    # Optional field (None allowed)
    due_date: date | None = None

    # Field with validation
    priority: int = Field(ge=1, le=5, description="Priority 1-5")
```

### Enum Fields (Literal Types)

```python
from typing import Literal

QualityLiteral = Literal["poor", "fair", "good", "excellent"]

class HabitCompletionRequest(BaseModel):
    quality: QualityLiteral = Field(
        default="good",
        description="Quality rating of the habit completion"
    )
```

**Benefits:**
- Type-safe at dev time (MyPy validates)
- Clear error messages ("Input should be 'poor', 'fair', 'good' or 'excellent'")
- No manual validation needed

### Complex Fields

```python
class GoalTaskGenerationRequest(BaseModel):
    # Any dict (flexible)
    context_preferences: dict[str, Any] = Field(
        default_factory=dict,
        description="Preferences for task generation"
    )

    # Structured dict (typed)
    metadata: dict[str, str] = Field(
        default_factory=dict,
        description="String metadata only"
    )

    # List of items
    tags: list[str] = Field(
        default_factory=list,
        description="Tags for categorization"
    )
```

### Field Validators

```python
from pydantic import field_validator

class TaskCreateRequest(BaseModel):
    title: str
    due_date: date | None = None

    @field_validator('title')
    @classmethod
    def title_not_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError('Title cannot be empty or whitespace')
        return v.strip()

    @field_validator('due_date')
    @classmethod
    def due_date_not_past(cls, v: date | None) -> date | None:
        if v and v < date.today():
            raise ValueError('Due date cannot be in the past')
        return v
```

---

## When to Use Each Pattern

| Input Type | Pattern | Error Code | Use Case |
|------------|---------|------------|----------|
| **Query Params (GET)** | Helper functions | 400 | Simple string inputs, enums, booleans |
| **JSON Bodies (POST/PUT)** | Pydantic models | 422 | Structured data, complex validation |
| **Path Params** | Avoid (SKUEL uses query params) | N/A | Not used in SKUEL API routes |

**SKUEL Preference:** Query parameters over path parameters for all routes. See [ROUTE_NAMING_CONVENTION.md](ROUTE_NAMING_CONVENTION.md).

---

## Integration with Three-Tier Type System

Pydantic request models are **Tier 1 (External)** in SKUEL's three-tier architecture:

```
API Request → Pydantic Model → DTO → Domain Model → Core Logic
  (Tier 1)      (Validation)   (Tier 2)  (Tier 3)
```

**Flow Example:**
```python
# Tier 1: External (API boundary)
class TaskCompletionRequest(BaseModel):  # Validates structure
    context: dict[str, Any]
    reflection: str

# Route converts to service call
@rt("/api/context/task/complete", methods=["POST"])
async def complete_task(body: TaskCompletionRequest) -> Result[Any]:
    return await service.complete_task_with_context(
        completion_context=body.context,  # Extract data
        reflection_notes=body.reflection,
    )

# Service layer uses DTOs (Tier 2)
async def complete_task_with_context(
    self,
    completion_context: dict[str, Any],
    reflection_notes: str,
) -> Result[Task]:  # Returns domain model (Tier 3)
    # Business logic...
```

See [three_tier_type_system.md](three_tier_type_system.md) for details.

---

## File Organization

### Request Models Location

```
core/models/{domain}/
├── {domain}_domain.py     # Domain models (Tier 3)
├── {domain}_dto.py        # DTOs (Tier 2)
└── {domain}_request.py    # Pydantic request models (Tier 1)
```

**Example:**
```
core/models/context/
├── __init__.py
└── context_request.py     # TaskCompletionRequest, etc.
```

### Route Files

```
adapters/inbound/
├── {domain}_routes.py     # Route registration
├── {domain}_api.py        # API routes (uses request models)
└── {domain}_ui.py         # UI routes
```

---

## Common Patterns

### Boolean Query Parameters

```python
# Helper function (reusable)
def parse_bool_param(params: dict[str, str], key: str, default: bool = True) -> bool:
    """Parse boolean from query param."""
    value = params.get(key, str(default)).lower()
    return value in ("true", "1", "yes", "on")

# Usage in route
include_insights = parse_bool_param(params, "include_insights", default=True)
```

**Handles:**
- `?flag=true` → `True`
- `?flag=1` → `True`
- `?flag=yes` → `True`
- `?flag=on` → `True`
- `?flag=false` → `False`
- `?flag=0` → `False`
- Missing → Uses default

---

### Enum Query Parameters

```python
# Helper function
def validate_time_window(time_window: str) -> Result[str]:
    """Validate time_window against whitelist."""
    allowed_windows = ["7d", "30d", "90d"]

    if time_window not in allowed_windows:
        return Result.fail(
            Errors.validation(
                message=f"time_window must be one of: {allowed_windows}",
                field="time_window",
                value=time_window,
            )
        )

    return Result.ok(time_window)

# Usage in route
time_window_result = validate_time_window(params.get("time_window", "7d"))
if time_window_result.is_error:
    return time_window_result  # Early return with 400 error
```

---

### Optional JSON Fields with Defaults

```python
class TaskCompletionRequest(BaseModel):
    # Optional dict (defaults to empty)
    context: dict[str, Any] = Field(default_factory=dict)

    # Optional string (defaults to empty string)
    reflection: str = Field(default="")

    # Optional with None (explicitly nullable)
    notes: str | None = Field(default=None)
```

**Request Handling:**
```json
// All valid:
{}                           // Uses all defaults
{"context": {...}}           // Partial
{"context": {...}, "reflection": "..."} // Full
```

---

## Migration Guide

### From Manual Parsing to Pydantic

**Before (Manual):**
```python
@rt("/api/context/task/complete", methods=["POST"])
async def complete_task(request: Request, task_uid: str) -> Result[Any]:
    body = await request.json()  # Manual parsing

    completion_context = body.get("context", {})
    reflection_notes = body.get("reflection", "")

    # No validation!
    # Malformed JSON → 500
    # Wrong types → 500
```

**After (Pydantic):**
```python
@rt("/api/context/task/complete", methods=["POST"])
async def complete_task(
    request: Request,
    task_uid: str,
    body: TaskCompletionRequest  # Auto-validates
) -> Result[Any]:
    # Validation automatic!
    # Malformed JSON → 422
    # Wrong types → 422 with field details

    return await service.complete_task_with_context(
        task_uid=task_uid,
        completion_context=body.context,
        reflection_notes=body.reflection,
    )
```

**Steps:**
1. Create Pydantic model in `core/models/{domain}/{domain}_request.py`
2. Add model to route signature
3. Remove manual `await request.json()`
4. Access fields via `body.field` instead of `body["field"]`
5. Remove manual validation code

---

## Testing Validation

### Unit Tests for Helpers

```python
def test_parse_bool_param():
    assert parse_bool_param({"flag": "true"}, "flag") == True
    assert parse_bool_param({"flag": "1"}, "flag") == True
    assert parse_bool_param({"flag": "false"}, "flag") == False
    assert parse_bool_param({}, "flag", default=True) == True

def test_validate_enum():
    result = validate_time_window("7d")
    assert not result.is_error

    result = validate_time_window("invalid")
    assert result.is_error
    assert "7d" in result.expect_error().message
```

### Unit Tests for Pydantic Models

```python
from pydantic import ValidationError
from core.models.context import TaskCompletionRequest

def test_task_completion_request_valid():
    req = TaskCompletionRequest(
        context={"knowledge_applied": ["ku.python"]},
        reflection="Great experience"
    )
    assert req.context["knowledge_applied"] == ["ku.python"]

def test_task_completion_request_invalid():
    try:
        TaskCompletionRequest(context="string")  # Should be dict
        assert False, "Should raise ValidationError"
    except ValidationError as e:
        assert "context" in str(e)

def test_task_completion_request_defaults():
    req = TaskCompletionRequest()
    assert req.context == {}
    assert req.reflection == ""
```

---

## Reference Implementation

**Complete Example:** Context-Aware API (`adapters/inbound/context_aware_api.py`)

**Helper Functions:**
- `parse_bool_param()` - Boolean query param parsing
- `validate_time_window()` - Enum validation

**Pydantic Models:**
- `TaskCompletionRequest` - Task completion body
- `GoalTaskGenerationRequest` - Goal task generation body
- `HabitCompletionRequest` - Habit completion body

**Routes:**
- 2 GET routes using helpers
- 3 POST routes using Pydantic models

---

## Related Documentation

- [three_tier_type_system.md](three_tier_type_system.md) - Pydantic's role in architecture
- [ROUTE_FACTORIES.md](ROUTE_FACTORIES.md) - CRUDRouteFactory uses Pydantic
- [ERROR_HANDLING.md](ERROR_HANDLING.md) - Result[T] pattern for errors
- [FASTHTML_ROUTE_REGISTRATION.md](FASTHTML_ROUTE_REGISTRATION.md) - Route patterns

---

## Key Takeaways

1. **Validate Early:** Catch errors at API boundaries, not deep in service logic
2. **Fail Fast:** Return clear 400/422 errors immediately
3. **Use Right Tool:**
   - Simple inputs → Helper functions
   - Complex data → Pydantic models
4. **Type Safety:** Let MyPy catch errors at dev time
5. **Self-Document:** Models and helpers clarify expected inputs
6. **DRY:** Reuse validation logic across routes

**Anti-Patterns:**
- ❌ Manual JSON parsing without validation
- ❌ Accepting invalid data and handling downstream
- ❌ Silent failures (accepting bad data without error)
- ❌ Returning 500 for validation errors
- ❌ Repeated validation logic in every route
