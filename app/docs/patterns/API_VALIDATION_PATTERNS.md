---
title: API Validation Patterns
updated: 2026-03-23
category: patterns
related_skills:
- pydantic
- skuel-ui
related_docs:
- /docs/patterns/three_tier_type_system.md
- /docs/patterns/ROUTE_FACTORIES.md
- /docs/patterns/ERROR_HANDLING.md
---

# API Validation Patterns

*Created: 2026-01-24 | Updated: 2026-03-23*

## Quick Start

**Skills:** [@pydantic](../../.claude/skills/pydantic/SKILL.md), [@skuel-ui](../../.claude/skills/skuel-ui/SKILL.md)

For hands-on implementation:
1. Invoke `@pydantic` for request model validation patterns
2. Invoke `@skuel-ui` for form handling and error display
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

**Query param helpers live in** `adapters/inbound/route_factories/route_helpers.py` (re-exported from `adapters.inbound.route_factories`). **Body parsing helpers** (`parse_json_body`, `parse_form_body`) live in `adapters/inbound/form_helpers.py`.

**Example:**
```python
from adapters.inbound.route_factories import (
    parse_bool_query_param,
    parse_date_query_param,
    parse_csv_query_param,
    parse_pagination_params,
    parse_date_param_strict,
)

@rt("/api/context/dashboard")
@boundary_handler()
async def get_dashboard(request: Request) -> Result[Any]:
    user_uid = require_authenticated_user(request)
    params = dict(request.query_params)

    # Boolean parsing (silent fallback)
    include_predictions = parse_bool_query_param(params, "include_predictions", default=True)

    # Enum validation (domain-specific)
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
# core/models/task/task_request.py (context-aware models live in domain request files)

from typing import Any
from pydantic import BaseModel, ConfigDict, Field

class ContextualTaskCompletionRequest(BaseModel):
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

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "context": {
                    "knowledge_applied": ["ku.python"],
                    "time_invested_minutes": 120
                },
                "reflection": "Great learning experience"
            }
        }
    )
```

**Usage in Routes:**
```python
from adapters.inbound.form_helpers import parse_json_body

@rt("/api/context/task/complete", methods=["POST"])
@boundary_handler(success_status=200)
async def complete_task(request: Request, task_uid: str) -> Result[Any]:
    """Complete task with context awareness."""
    result = await parse_json_body(request, ContextualTaskCompletionRequest)
    if result.is_error:
        return result  # type: ignore[return-value]
    req = result.value

    return await service.complete_task_with_context(
        task_uid=task_uid,
        completion_context=req.context,  # Type-safe access
        reflection_notes=req.reflection,
    )
```

**With extra fields** (e.g., entity UID from `@require_ownership_query`):
```python
result = await parse_json_body(request, TrackHabitRequest, extra={"habit_uid": entity.uid})
```

**Benefits:**
- ✅ Automatic structure + type validation via Pydantic
- ✅ Type-safe field access (`req.field` vs `body["field"]`)
- ✅ MyPy catches errors at dev time
- ✅ Self-documenting (model shows expected structure)
- ✅ Clear validation errors with field-level details
- ✅ Consistent error handling via `Result.fail()`
- ✅ No boilerplate — `parse_json_body()` handles JSON parsing + ValidationError → Result conversion

---

### HTML Form Parameters: Model-Level `from_form_params()` Classmethod

**Use Case:** Complex search/filter forms with many checkbox, enum, and optional string parameters that need coercion from raw HTML strings to typed values.

**Pattern:** A `@classmethod` on the Pydantic model that encapsulates all form-specific normalization (empty string → None, checkbox string → bool, string → enum). The regular constructor stays clean for API/JSON use.

**Example:**
```python
class SearchRequest(BaseModel):
    status: EntityStatus | None = None
    ready_to_learn: bool = False
    # ... 25+ fields

    @classmethod
    def from_form_params(cls, *, status: str | None = None, ready_to_learn: str | None = None, ...) -> "SearchRequest":
        """Build from raw HTML form strings."""
        def _none_if_empty(v: str | None) -> str | None:
            return None if not v or v.strip() == "" else v

        def _checkbox_to_bool(v: str | None) -> bool:
            return v == "true" if v else False

        status = _none_if_empty(status)
        return cls(
            status=EntityStatus(status) if status else None,
            ready_to_learn=_checkbox_to_bool(ready_to_learn),
            ...
        )
```

**Usage in Routes:**
```python
@rt("/search/results")
async def search_results(request: Request, query: str = "", status: str | None = None, ...):
    user_uid = require_authenticated_user(request)
    search_request = SearchRequest.from_form_params(query=query, user_uid=user_uid, status=status, ...)
    result = await search_router.faceted_search(search_request, user_uid)
```

**Benefits:**
- ✅ Route handler stays thin — no inline normalization logic
- ✅ Model owns its own coercion rules (single source of truth)
- ✅ Regular constructor unaffected (JSON/API callers use it directly)
- ✅ Testable independently of HTTP layer

**Real-world usage:** `SearchRequest.from_form_params()` in `core/models/search_request.py` — handles 25+ form parameters for the search page.

---

### Form Data Bodies: `parse_form_body()` Helper

**Use Case:** POST form data (not JSON) that should be validated as a structured Pydantic model. Replaces manual `(body.get("field") or "").strip()` + enum try/except + required-field checks.

**Helper:** `parse_form_body()` from `adapters/inbound/form_helpers.py` — converts form fields to a dict (stripping strings, converting empty strings to `None`), then validates via Pydantic.

**Example Request Model:**
```python
# core/models/teaching/teaching_request.py
class CreateTeachingExerciseRequest(BaseModel):
    name: str = Field(..., min_length=1)
    instructions: str = Field(..., min_length=1)
    scope: ExerciseScope = ExerciseScope.PERSONAL
    group_uid: str | None = None
    due_date: date | None = None
    processor_type: ReportSource = ReportSource.LLM

    @model_validator(mode="after")
    def assigned_scope_requires_group(self) -> "CreateTeachingExerciseRequest":
        if self.scope == ExerciseScope.ASSIGNED and not self.group_uid:
            raise ValueError("group_uid is required for assigned exercises")
        return self
```

**Usage in Routes:**
```python
from adapters.inbound.form_helpers import parse_form_body

@rt("/api/teaching/review/{uid}/revision", methods=["POST"])
@boundary_handler()
async def request_revision(request: Request, uid: str) -> Result[Any]:
    parsed = await parse_form_body(request, RequestRevisionRequest)
    if parsed.is_error:
        return parsed  # type: ignore[return-value]
    req = parsed.value

    return await service.request_revision(report_uid=uid, notes=req.notes)
```

**Benefits:**
- ✅ Replaces 20-30 lines of imperative form parsing with 3 lines
- ✅ Required fields, enum coercion, cross-field validation all in the model
- ✅ Empty strings → `None` for optional fields (HTML form quirk handled automatically)
- ✅ Same Result[T] error flow as `parse_json_body()`

**When to use `parse_form_body()` vs `safe_form_string()`:**
- `parse_form_body()` — structured form data with multiple fields, validation rules, enum parsing
- `safe_form_string()` — individual field extraction in UI routes where Pydantic is overkill

**Real-world usage:** `teaching_api.py` — `CreateTeachingExerciseRequest` and `UpdateTeachingExerciseRequest`.

---

### Date and Integer Query Parameters with `Result[T]` (Strict Helpers)

**Use Case:** Routes where invalid dates or out-of-range integers should return a 400 error, not fall back to a default.

**Helpers:** `parse_date_param_strict()` and `parse_int_param_strict()` from `route_helpers.py` — compose naturally with `@boundary_handler()`.

**Usage in Routes:**
```python
from adapters.inbound.route_factories import parse_date_param_strict, parse_int_param_strict

@rt("/api/analytics/quarterly-progress")
@boundary_handler()
async def get_quarterly(request: Request) -> Result[Any]:
    user_uid = require_authenticated_user(request)

    year_result = parse_int_param_strict(request.query_params.get("year"), "year", 2000, 2100)
    if year_result.is_error:
        return year_result
    quarter_result = parse_int_param_strict(request.query_params.get("quarter"), "quarter", 1, 4)
    if quarter_result.is_error:
        return quarter_result

    return await service.generate_quarterly_progress(user_uid, year_result.value, quarter_result.value)
```

**Real-world usage:** `analytics_summary_api.py` — 4 routes using `parse_date_param_strict()` and `parse_int_param_strict()` for date/period validation.

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

**HTTP Response (client-safe — internal details stripped):**
```json
{
  "category": "validation",
  "code": "VALIDATION_FIELD_TIME_WINDOW",
  "message": "time_window must be one of: ['7d', '30d', '90d']",
  "severity": "low",
  "timestamp": "2026-01-15T10:30:00+00:00"
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

**⚠️ HTML Form Gotcha:** HTML `<select>` elements send empty strings (`""`) when no option is selected. `dict.get("field", "default")` does NOT catch this — the key exists, so the default is ignored. Always use `safe_form_string()` before passing to Pydantic:

```python
from adapters.inbound.form_helpers import safe_form_string

# ❌ WRONG - empty string passes through, fails enum validation
domain = form_data.get("domain", "personal")

# ✅ CORRECT - safe_form_string handles str|UploadFile|None, then `or` provides fallback
domain = safe_form_string(form_data.get("domain")) or "personal"
```

See `/docs/patterns/ERROR_HANDLING.md` → "Safe Enum Parsing for HTML Forms" for the full pattern.

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

### Cross-Field Validators

Use `@model_validator(mode="after")` when a rule spans multiple fields. The validator runs after all field validators succeed, so fields are already their final types.

```python
from pydantic import model_validator

class TaskCreateRequest(BaseModel):
    scheduled_date: date | None = None
    due_date: date | None = None

    @model_validator(mode="after")
    def validate_due_after_scheduled(self) -> "TaskCreateRequest":
        """Due date must not be before scheduled date."""
        if self.due_date and self.scheduled_date:
            if self.due_date < self.scheduled_date:
                raise ValueError("Due date cannot be before scheduled date")
        return self
```

The error surfaces as a 422 field error on `__root__` (model level), caught by route handlers and rendered as a user-friendly banner.

---

## When to Use Each Pattern

| Input Type | Pattern | Error Code | Use Case |
|------------|---------|------------|----------|
| **Query Params (GET)** | Silent helpers (`parse_*_query_param`) | 200 (default) | Booleans, dates, CSV lists, pagination |
| **Required Params (GET)** | Strict helpers (`parse_*_param_strict`) | 400 | Required dates, bounded integers |
| **HTML Form Params (GET)** | `Model.from_form_params()` classmethod | 400 | Many checkbox/enum/optional string params needing coercion |
| **JSON Bodies (POST/PUT)** | `parse_json_body(request, Model)` | 422 | Structured data, complex validation |
| **Form Data Bodies (POST)** | `parse_form_body(request, Model)` | 422 | Structured form data with validation |
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
    context: dict[str, Any] = Field(default_factory=dict)
    reflection: str = Field(default="")

# Route parses JSON → constructs model → calls service
@rt("/api/context/task/complete", methods=["POST"])
async def complete_task(request: Request) -> Result[Any]:
    result = await parse_json_body(request, TaskCompletionRequest)
    if result.is_error:
        return result
    req = result.value
    return await service.complete_task_with_context(
        completion_context=req.context,  # Type-safe access
        reflection_notes=req.reflection,
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

**Example (context-aware models dissolved into domain request files):**
```
core/models/task/task_request.py      # ContextualTaskCompletionRequest
core/models/goal/goal_request.py      # ContextualGoalTaskGenerationRequest
core/models/habit/habit_request.py    # ContextualHabitCompletionRequest
core/models/auth/auth_request.py      # RegistrationRequest, LoginRequest, ResetPasswordRequest
```

**Standalone request files** (domains without a directory):
```
core/models/lifepath_request.py       # CaptureVisionRequest, DesignateLifePathRequest
core/models/insight_request.py        # BulkInsightUidsRequest, SnoozeInsightRequest
core/models/user_pins_request.py      # PinEntityRequest, ReorderPinsRequest
core/models/entity_requests.py        # SmartDismissRequest, bulk ops, cross-domain models
```

**Note:** Auth request models validate HTML form data (not JSON bodies), but follow the same Pydantic pattern. Form data is extracted with `safe_form_string()` then passed to the model constructor.

### Route Files

```
adapters/inbound/
├── {domain}_routes.py     # Route registration
├── {domain}_api.py        # API routes (uses request models)
└── {domain}_ui.py         # UI routes
```

---

## Common Patterns

### Integer Query Parameters

**Use Case:** Pagination (`limit`, `offset`), time windows (`days`, `days_back`), depth controls

**Pattern:** `parse_int_query_param()` — safe parsing with fallback and bounds clamping

```python
from adapters.inbound.route_factories import parse_int_query_param

# In a route handler:
params = dict(request.query_params)
limit = parse_int_query_param(params, "limit", 50, minimum=1, maximum=500)
offset = parse_int_query_param(params, "offset", 0, minimum=0)
days = parse_int_query_param(params, "days", 30, minimum=1, maximum=365)

# Also works directly with request.query_params (Starlette QueryParams):
limit = parse_int_query_param(request.query_params, "limit", 50, minimum=1, maximum=500)
```

**Behavior:**
- Missing key → returns `default`
- Empty string → returns `default`
- Non-numeric (e.g. `"abc"`) → returns `default`
- Below `minimum` → clamped to `minimum`
- Above `maximum` → clamped to `maximum`
- Valid integer → returned as-is

**Standard Bounds:**

| Parameter | Default | Min | Max | Used By |
|-----------|---------|-----|-----|---------|
| `limit` (general) | 50-100 | 1 | 500 | All list/query endpoints |
| `limit` (search) | 50 | 1 | 100 | Search endpoints |
| `offset` | 0 | 0 | — | Pagination |
| `days` / `days_back` / `period_days` | 30 | 1 | 365 | Analytics, time-windowed queries |
| `depth` | 2 | 1 | 5 | Graph traversal |
| `min_usage` | 1 | 0 | — | Tag usage filters |
| `max_steps` / `max_recommendations` | 5 | 1 | 20 | Askesis intelligence |
| `time_horizon_hours` | 8 | 1 | 168 | Schedule-aware recommendations |

### Float Query Parameters

**Pattern:** `parse_float_query_param()` — same contract as the int helper (default on missing/blank/invalid, optional `minimum`/`maximum` clamping) for ratio-style params.

```python
from adapters.inbound.route_factories import parse_float_query_param

min_progress = parse_float_query_param(request.query_params, "min_progress", 0.7)
```

**Anti-Pattern:**
```python
# BAD: Crashes with ValueError on non-numeric input → 500 error
limit = int(params.get("limit", 50))
limit = int(request.query_params.get("days_back", 30))

# GOOD: Safe fallback + bounds clamping
limit = parse_int_query_param(params, "limit", 50, minimum=1, maximum=500)
days_back = parse_int_query_param(request.query_params, "days_back", 30, minimum=1, maximum=365)
```

**Location:** `adapters/inbound/route_factories/route_helpers.py`
**Tests:** `tests/unit/adapters/test_route_helpers.py`

---

### Boolean Query Parameters

```python
from adapters.inbound.route_factories import parse_bool_query_param

include_insights = parse_bool_query_param(params, "include_insights", default=True)
```

**Handles:** `true/1/yes/on` → `True`, everything else → `False`, missing → default.

---

### Date Query Parameters

```python
from adapters.inbound.route_factories import parse_date_query_param

# Silent fallback (optional dates)
start_date = parse_date_query_param(params, "start_date", today - timedelta(days=7))

# Strict validation (required dates)
from adapters.inbound.route_factories import parse_date_param_strict
result = parse_date_param_strict(params.get("start_date"), "start_date")
if result.is_error:
    return result  # 400 with field-level error
```

---

### Comma-Separated List Parameters

```python
from adapters.inbound.route_factories import parse_csv_query_param, split_csv

# From query params dict
tags = parse_csv_query_param(params, "tags")  # ["python", "ml"]

# From a string variable
status_filter = split_csv(status)  # strips whitespace, filters empties
```

---

### Pagination Parameters

```python
from adapters.inbound.route_factories import parse_pagination_params

pagination = parse_pagination_params(params, default_limit=100, max_limit=500)
# pagination.limit  — clamped to [1, max_limit]
# pagination.offset — clamped to [0, ∞)
```

---

### Date Range Parameters

```python
from adapters.inbound.route_factories import parse_date_range_params

date_range = parse_date_range_params(params, default_start=today - timedelta(days=7))
# date_range.start_date, date_range.end_date — both date | None
```

---

### Timeframe String Parameters

```python
from core.utils.validation_helpers import parse_timeframe_days

# Parse "90d" → 90, with fallback default
lookback_days = parse_timeframe_days(timeframe, default=90)
```

**Handles:**
- `"30d"` → `30`
- `"7d"` → `7`
- `"invalid"` → Uses default
- `""` → Uses default

**Location:** `core/utils/validation_helpers.py`

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
    # Wrong types → silent data loss
```

**After (parse_json_body helper):**
```python
from adapters.inbound.form_helpers import parse_json_body

@rt("/api/context/task/complete", methods=["POST"])
async def complete_task(request: Request, task_uid: str) -> Result[Any]:
    result = await parse_json_body(request, TaskCompletionRequest)
    if result.is_error:
        return result  # type: ignore[return-value]
    req = result.value

    return await service.complete_task_with_context(
        task_uid=task_uid,
        completion_context=req.context,
        reflection_notes=req.reflection,
    )
```

**For ownership-verified routes** (entity UID comes from `@require_ownership_query`):
```python
async def track_habit_route(request: Request, entity: Any, ...) -> Result[Any]:
    result = await parse_json_body(request, TrackHabitRequest, extra={"habit_uid": entity.uid})
    if result.is_error:
        return result  # type: ignore[return-value]
    return await habits_service.track_habit(result.value)
```

**For form data** (replace manual `(body.get("field") or "").strip()` patterns):
```python
from adapters.inbound.form_helpers import parse_form_body

async def create_exercise(request: Request) -> Result[Any]:
    parsed = await parse_form_body(request, CreateTeachingExerciseRequest)
    if parsed.is_error:
        return parsed  # type: ignore[return-value]
    req = parsed.value
    return await service.create_exercise(name=req.name, ...)
```

**Steps:**
1. Create Pydantic model in `core/models/{domain}/{domain}_request.py`
2. Use `parse_json_body()` or `parse_form_body()` — handles parsing + ValidationError → Result
3. Access fields via `req.field` instead of `body["field"]`
4. Remove manual validation code (required checks, type coercion, enum try/except)

---

## Testing Validation

### Unit Tests for Helpers

Tests in `tests/unit/adapters/test_route_helpers.py` cover all shared helpers (59 tests):

```python
def test_parse_bool_query_param():
    assert parse_bool_query_param({"flag": "true"}, "flag") is True
    assert parse_bool_query_param({"flag": "1"}, "flag") is True
    assert parse_bool_query_param({"flag": "false"}, "flag") is False
    assert parse_bool_query_param({}, "flag", default=True) is True

def test_parse_date_param_strict():
    result = parse_date_param_strict("2026-03-18", "start_date")
    assert result.is_ok
    result = parse_date_param_strict("bad", "start_date")
    assert result.is_error

def test_parse_csv_query_param():
    assert parse_csv_query_param({"tags": "a, b, c"}, "tags") == ["a", "b", "c"]
    assert parse_csv_query_param({}, "tags") == []
```

### Unit Tests for Pydantic Models

```python
from pydantic import ValidationError
from core.models.task.task_request import ContextualTaskCompletionRequest

def test_task_completion_request_valid():
    req = ContextualTaskCompletionRequest(
        context={"knowledge_applied": ["ku.python"]},
        reflection="Great experience"
    )
    assert req.context["knowledge_applied"] == ["ku.python"]

def test_task_completion_request_invalid():
    try:
        ContextualTaskCompletionRequest(context="string")  # Should be dict
        assert False, "Should raise ValidationError"
    except ValidationError as e:
        assert "context" in str(e)

def test_task_completion_request_defaults():
    req = ContextualTaskCompletionRequest()
    assert req.context == {}
    assert req.reflection == ""
```

---

## Shared Helpers

### Request Body Helpers

**Location:** `adapters/inbound/form_helpers.py`

| Helper | Returns | Use Case |
|--------|---------|----------|
| `parse_json_body(request, schema, extra=None)` | `Result[T]` | JSON body → Pydantic model with Result[T] wrapping |
| `parse_form_body(request, schema)` | `Result[T]` | Form data → Pydantic model (empty strings → None) |

### Query Param Helpers

**Location:** `adapters/inbound/route_factories/route_helpers.py`
**Tests:** `tests/unit/adapters/test_route_helpers.py`

| Helper | Returns | Use Case |
|--------|---------|----------|
| `parse_int_query_param(params, key, default, *, minimum, maximum)` | `int` | Integer with bounds clamping, silent fallback |
| `parse_bool_query_param(params, key, default)` | `bool` | Boolean (`true/1/yes/on` → True), silent fallback |
| `parse_date_query_param(params, key, default)` | `date \| None` | ISO date, silent fallback |
| `parse_csv_query_param(params, key)` | `list[str]` | Comma-separated list from params dict |
| `split_csv(value)` | `list[str]` | Comma-separated list from a string variable |
| `parse_date_range_params(params, ...)` | `DateRangeParams` | Start/end date pair, silent fallback |
| `parse_pagination_params(params, ...)` | `PaginationParams` | Limit+offset pair with bounds |
| `parse_date_param_strict(value, field)` | `Result[date]` | ISO date with validation error on failure |
| `parse_int_param_strict(value, field, min, max)` | `Result[int]` | Integer in range with validation error on failure |

**Silent vs strict:** Use silent helpers (`parse_*_query_param`) when invalid input should fall back to a default. Use strict helpers (`parse_*_param_strict`) when invalid input should surface as a 400/422 error.

## Reference Implementations

**Teaching API** (`adapters/inbound/teaching_api.py`):
- Uses `parse_json_body()` for JSON POST routes (submit feedback, request revision)
- Uses `parse_form_body()` for form POST routes (create/update exercise)
- `CreateTeachingExerciseRequest` — demonstrates enum coercion, cross-field validation, date parsing in a single Pydantic model

**Activity Domain APIs** (habits, events, goals, choices):
- Use `parse_json_body()` with `extra=` param for ownership-verified routes
- Example: `parse_json_body(request, TrackHabitRequest, extra={"habit_uid": entity.uid})`

**Groups API** (`adapters/inbound/groups_api.py`):
- Uses `parse_json_body()` for create, update, add_member, remove_member routes

**Finance API** (`adapters/inbound/finance_api.py`):
- Uses `parse_json_body()` for receipt attachment, invoice creation, bulk categorize
- Request models: `AttachReceiptRequest`, `BulkCategorizeExpensesRequest` in `core/models/finance/finance_request.py`

**Insights API** (`adapters/inbound/insights_api.py`):
- Uses `parse_json_body()` for bulk dismiss/action, smart dismiss, snooze
- Request models: `BulkInsightUidsRequest`, `SnoozeInsightRequest` in `core/models/insight_request.py`

**LifePath API** (`adapters/inbound/lifepath_api.py`):
- Uses `parse_json_body()` for vision capture, life path designation
- Request models: `CaptureVisionRequest`, `DesignateLifePathRequest` in `core/models/lifepath_request.py`

**User Entry API** (`adapters/inbound/user_entry_api.py`):
- Uses `parse_json_body()` for create, form submit, and process
- Request models: `UserEntryCreateRequest`, `UserEntryProcessRequest` in `core/models/user_entry/user_entry_request.py`; `FormSubmitRequest` in `core/models/forms/form_submission_request.py`

**User Pins API** (`adapters/inbound/user_pins_api.py`):
- Uses `parse_json_body()` for pin and reorder operations
- Request models: `PinEntityRequest`, `ReorderPinsRequest` in `core/models/user_pins_request.py`

**Search Routes** (`adapters/inbound/search_routes.py`):
- Uses `split_csv()` for entity_types and tags parsing
- Uses `SearchRequest.from_form_params()` — model-level classmethod handles 25+ form params

**Analytics Summary API** (`adapters/inbound/analytics_summary_api.py`):
- Uses `parse_date_param_strict()` and `parse_int_param_strict()` from shared helpers
- 4 routes using these for date/period validation

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
- ❌ Manual `try: req = Model(**body) except ValidationError` — use `parse_json_body()` instead
- ❌ Manual `(body.get("field") or "").strip()` + `if not field:` chains — use `parse_form_body()` instead
- ❌ Manual `validate_*_form_data()` functions that duplicate constraints already on the Pydantic model (two sources of truth — and they diverge)
