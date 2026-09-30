---
name: pydantic
description: Expert guide for Pydantic V2 validation models. Use when creating API request/response models, validating user input, working with field validators, model validators, or when the user mentions Pydantic, BaseModel, validation, or serialization.
allowed-tools: Read, Grep, Glob
---

# Pydantic Validation Patterns for SKUEL

## Core Philosophy

> "Pydantic at the edges, pure Python at the core"

Pydantic models are the **gatekeepers** of SKUEL - they validate and sanitize all external input before it enters the domain layer. This is Tier 1 of the three-tier type system.

```
External World → [Pydantic] → [DTOs] → [Domain Models] → Core Logic
                  ↑ YOU ARE HERE
```

## Quick Reference

| Pattern | Location | Purpose |
|---------|----------|---------|
| **Base Classes** | `core/models/request_base.py` | DRY configuration |
| **Shared Validators** | `core/models/validation_rules.py` | Reusable validation functions |
| **Field Constraints** | `Field(min_length=1, ge=0)` | Declarative validation |
| **Field Validators** | `@field_validator("field")` | Custom single-field logic |
| **Model Validators** | `@model_validator(mode="after")` | Cross-field validation |
| **ConfigDict** | `model_config = ConfigDict(...)` | Serialization behavior |

## Three-Tier Type System

SKUEL separates types by responsibility:

| Tier | Type | Purpose | Mutability |
|------|------|---------|------------|
| **1. External** | Pydantic Models | Validation & serialization | N/A |
| **2. Transfer** | DTOs | Data movement between layers | Mutable |
| **3. Core** | Frozen Dataclasses | Immutable business logic | Frozen |

```python
# Tier 1: Pydantic (External) - Validation at the edge
class TaskCreateRequest(CreateRequestBase):
    title: str = Field(min_length=1, max_length=200)
    due_date: date | None = Field(default=None)
    priority: Priority = Field(default=Priority.MEDIUM)


# Tier 2: DTO (Transfer) - Mutable data movement
@dataclass
class TaskDTO(UserOwnedDTO):
    due_date: date | None = None


# Tier 3: Domain Model (Core) - Immutable business logic
@dataclass(frozen=True, kw_only=True)
class Task(UserOwnedEntity):
    due_date: date | None = None

    def is_overdue(self) -> bool:
        """Business logic lives in domain models"""
        if self.is_completed or not self.due_date:
            return False
        return self.due_date < today_in(current_zone())
```

## Base Class Hierarchy

SKUEL uses a base class hierarchy to eliminate repeated `model_config` declarations:

```python
# core/models/request_base.py
from pydantic import BaseModel, ConfigDict

class RequestBase(BaseModel):
    """Base for all request models"""
    model_config = ConfigDict()  # Pydantic V2 defaults — enums stay enum members


class CreateRequestBase(RequestBase):
    """Base for create requests"""
    pass


class UpdateRequestBase(RequestBase):
    """Base for update requests - all fields optional.

    Activity Domain *UpdateRequest models also expose `to_intent()`, which builds the
    frozen `*UpdateIntent` the service contract consumes (ADR-066) — never pass the raw
    request dict to `service.update`. See request-response-reference.md.
    """
    pass


class FilterRequestBase(RequestBase):
    """Base for GET filter/query requests"""
    pass


class ResponseBase(BaseModel):
    """Base for all response models"""
    model_config = ConfigDict(from_attributes=True)
```

**Usage:**

```python
# Inherits configuration from base
class TaskCreateRequest(CreateRequestBase):
    title: str = Field(min_length=1, max_length=200)
    due_date: date | None = None


class TaskUpdateRequest(UpdateRequestBase):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    actual_minutes: int | None = Field(default=None, ge=0)
```

## Binding a Request Model in a Route

A handler binds a request model through one of three helpers, inside the handler. A rejected body
is a **400** (`ErrorCategory.VALIDATION`) — 422 is `BUSINESS`, a well-formed request that
breaks a domain rule.

| Binding | Where | A rejected body becomes |
|---------|-------|-------------------------|
| `parse_body(request, Model)` | a door both API clients (JSON) and HTMX forms reach — the CRUD factory's `/create` and `/update?uid=`, the admin account actions, the context integrations | `Result.fail(Errors.validation(...))` → 400 |
| `parse_json_body(request, Model)` | a JSON-only API route | same |
| `parse_form_body(request, Model)` | a form-only UI route (empty strings → `None`, `list[T]` split) | same; a UI route usually re-renders the form with a banner (200) |

The helpers live in `adapters/inbound/form_helpers.py`. `parse_body` picks its reader by
Content-Type — htmx url-encodes every body (multipart for a `Form`), whatever an
`hx-headers` Content-Type claims.

⚠ **Never declare the model as a handler parameter (`body: Model`).** FastHTML binds such a
parameter during parameter extraction, *before* the handler and `@boundary_handler` run,
and passes every *string* value through the field's annotation first — or, for `int`,
`date` and `bool`, its own `str2int` / `str2date` / `str2bool`. A `Literal` raises
`TypeError` on any value sent; an enum, `int`, `date` or `dict` raises on a value it cannot
convert; and a Pydantic rejection escapes the same way. Each answers 500. Through a helper,
Pydantic sees the raw value and every rejection is a 400 — so a `Literal` or an enum field
is fine there.

The helpers merge nothing into the body. When a route verifies ownership, it checks the
owner uid wherever it travels: a model field (`TrackHabitRequest.habit_uid`) is verified
after parsing; a query-string uid (`POST /api/principles/link?uid=`) before.

Secret-bearing auth fields (passwords, reset tokens) are `pydantic.SecretStr`, so neither
the model's `repr` nor `model_dump()` can disclose them — see
`/docs/patterns/AUTH_PATTERNS.md` § Secret-bearing fields are unprintable.

## Field Validation

### Field Constraints (Declarative)

Use `Field()` for simple constraints - no custom code needed:

```python
from pydantic import Field

class TaskCreateRequest(BaseModel):
    # String constraints
    title: str = Field(min_length=1, max_length=200)
    description: str | None = Field(None, max_length=2000)

    # Numeric constraints
    duration_minutes: int = Field(default=30, ge=5, le=480)
    progress: float = Field(default=0.0, ge=0.0, le=1.0)

    # List constraints
    tags: list[str] = Field(default_factory=list, max_length=20)

    # With descriptions (for schema docs)
    priority: Priority = Field(
        default=Priority.MEDIUM,
        description="Task priority level"
    )
```

### Field Validators (Custom Logic)

Use `@field_validator` when Field() constraints aren't enough:

```python
# core/models/habit/habit_request.py
CONTEXTUAL_QUALITY_VALUES: Final = ("poor", "fair", "good", "excellent")

class ContextualHabitCompletionRequest(BaseModel):
    quality: str = Field(default="good")

    @field_validator("quality")
    @classmethod
    def validate_quality(cls, value: str) -> str:
        """Reject a quality rating outside ``CONTEXTUAL_QUALITY_VALUES``."""
        if value not in CONTEXTUAL_QUALITY_VALUES:
            raise ValueError(f"quality must be one of: {', '.join(CONTEXTUAL_QUALITY_VALUES)}")
        return value
```

### Conditional Validation — a Field Validator Skips Omitted Fields

A `field_validator` runs only on a value the client sent; Pydantic validates a default
only under `Field(validate_default=True)`. So "default this field when that one has a
value" written as a field validator never fires for the client who omits it — which is
the whole case. Write it as a model validator, which always runs:

```python
# core/models/task/task_request.py — TaskCreateRequest
@model_validator(mode="after")
def default_completion_date_when_completed(self) -> TaskCreateRequest:
    """A task born COMPLETED carries a completion date — today unless supplied."""
    if self.status == EntityStatus.COMPLETED:
        if self.completion_date is None:
            self.completion_date = today_in(current_zone())
        else:
            _refuse_future_completion_date(self.completion_date)
    elif self.completion_date is not None:
        raise ValueError("completion_date requires status=completed")
    return self
```

A conditional *requirement* shared by several models is a model-validator helper —
`validate_url_when_online` on `EventCreateRequest` and `EventTemplateCreateRequest`; an
update request leaves the merged-state check to the service's `_validate_update` hook.
Both in [validation-patterns.md](validation-patterns.md).

`info.data` (`ValidationInfo`) still has its place: a check on a value that *was* sent,
against a field declared earlier — `validate_recurrence_end_after_start` in
[validation-patterns.md](validation-patterns.md).

### Client Datetime Fields

A `datetime` a client supplies is typed `ClientDateTime` (`core/models/request_base.py`), never a bare `datetime`: an offset-less value (a `datetime-local` field, a JSON string without an offset) is the user's wall clock, read in the current zone and held in the stored form of its instant; an aware value keeps its instant. `tests/unit/models/test_client_datetime_fields.py` fails on a request-model `datetime` field that is neither `ClientDateTime` nor a named response field.

```python
from core.models.request_base import ClientDateTime, UpdateRequestBase

class ChoiceUpdateRequest(UpdateRequestBase):
    decision_deadline: ClientDateTime | None = Field(default=None, description="Decision deadline")
```

## Model Validation (Cross-Field)

Use `@model_validator(mode="after")` for validation that spans multiple fields:

```python
# core/models/goal/goal_request.py — GoalCreateRequest (abridged)
from pydantic import model_validator

class GoalCreateRequest(BaseModel):
    # "Today" is today in a zone. A default factory takes the zero-argument form —
    # an uncalled `date.today` is refused in core/, adapters/ and ui/
    # (tests/unit/test_uncalled_clock_references.py).
    start_date: date | None = Field(default_factory=today_in_current_zone)
    target_date: date | None = Field(default=None, description="Target completion date")
    measurement_type: MeasurementType = Field(MeasurementType.PERCENTAGE)
    target_value: float | None = None

    @model_validator(mode="after")
    def validate_target_date(self, info: ValidationInfo) -> GoalCreateRequest:
        """Target date is in the future and on or after the start date."""
        allow_past = bool(info.context and info.context.get("allow_past_dates"))
        if not allow_past and self.target_date and self.target_date < today_in(current_zone()):
            raise ValueError("Target date must be in the future")
        return validate_date_after("target_date", "start_date", allow_equal=True)(self)

    @model_validator(mode="after")
    def validate_target_value(self) -> GoalCreateRequest:
        """Validate target value based on measurement type."""
        if self.measurement_type == MeasurementType.PERCENTAGE:
            if self.target_value and (self.target_value < 0 or self.target_value > 100):
                raise ValueError("Percentage target must be between 0 and 100")
        elif self.measurement_type == MeasurementType.NUMERIC and not self.target_value:
            raise ValueError("Numeric measurement requires a target value")
        return self
```

`today_in_current_zone` lives in `core/utils/zone_context.py`.

### Complex Cross-Field Example

```python
class HabitSystemUpdateRequest(BaseModel):
    """Validate habits don't appear in multiple essentiality levels"""
    essential_habit_uids: list[str] | None = None
    critical_habit_uids: list[str] | None = None
    supporting_habit_uids: list[str] | None = None
    optional_habit_uids: list[str] | None = None

    @model_validator(mode="after")
    def validate_no_duplicates(self):
        """Ensure no habit UID appears in multiple levels"""
        all_levels = {
            "essential": self.essential_habit_uids or [],
            "critical": self.critical_habit_uids or [],
            "supporting": self.supporting_habit_uids or [],
            "optional": self.optional_habit_uids or [],
        }

        seen = set()
        duplicates = set()
        for habits in all_levels.values():
            for habit in habits:
                if habit in seen:
                    duplicates.add(habit)
                seen.add(habit)

        if duplicates:
            raise ValueError(f"Habits in multiple levels: {duplicates}")
        return self
```

## Shared Validators Library

SKUEL centralizes reusable validators as factory functions:

```python
# core/models/validation_rules.py

def validate_future_date(*field_names: str) -> Callable:
    """Factory: Validate date/datetime is not in the past.

    Skipped under validation context {"allow_past_dates": True} — the
    ingestion converters pass it (historical vault notes); interactive
    paths pass no context, so the guard stands there (Arc E, G10).
    """
    @field_validator(*field_names)
    def _validate_future_date(
        cls, v: date | datetime | None, info: ValidationInfo
    ) -> date | datetime | None:
        if v is None:
            return v
        if info.context and info.context.get("allow_past_dates"):
            return v
        if isinstance(v, datetime):
            # an instant: a ClientDateTime value is on the stored clock by now
            if as_utc(v) <= now_utc():
                raise ValueError("Date/time cannot be in the past")
        elif isinstance(v, date) and v < today_in(current_zone()):
            raise ValueError("Date cannot be in the past")
        return v
    return _validate_future_date


def validate_required_string(*field_names: str, min_length: int = 1) -> Callable:
    """Factory: Validate string is not empty after strip; returns the stripped value"""
    @field_validator(*field_names)
    def _validate_required_string(cls, v: str | None) -> str | None:
        if v is None:
            return v
        stripped = v.strip()
        if len(stripped) < min_length:
            raise ValueError("Field cannot be empty")
        return stripped
    return _validate_required_string


def validate_percentage(*field_names: str) -> Callable:
    """Factory: Validate value is 0-100"""
    @field_validator(*field_names)
    def _validate_percentage(cls, v: float | None) -> float | None:
        if v is not None and (v < 0 or v > 100):
            raise ValueError("Percentage must be between 0 and 100")
        return v
    return _validate_percentage
```

The full list is in [validation-patterns.md](validation-patterns.md).

**Usage in request models:**

```python
# core/models/task/task_request.py — TaskCreateRequest
_validate_dates = validate_future_date("due_date", "scheduled_date")
_validate_recurrence_end = validate_recurrence_end_after_start(
    "recurrence_end_date", "due_date"
)

# core/models/goal/goal_request.py — GoalCreateRequest
_validate_title = validate_required_string("title")
```

## Serialization Configuration

### ConfigDict Options

```python
from pydantic import ConfigDict

# The bases hold the shared config (core/models/request_base.py):
# RequestBase → ConfigDict() — Pydantic V2 defaults, so enums stay enum members
# ResponseBase → ConfigDict(from_attributes=True)

# A model that rejects unknown fields — core/models/transcription/transcription.py
class TranscriptionCreateRequest(BaseModel):
    audio_file_path: str = Field(..., description="Path to audio file")
    language: str = Field(default="en", description="Language code for transcription")

    model_config = {"extra": "forbid"}
```

### When to Use Each Option

| Option | Use Case |
|--------|----------|
| `extra="forbid"` | Reject unknown fields instead of dropping them |
| `from_attributes=True` | Create from DTO/domain model attributes |
| `use_enum_values=True` | Store `.value` strings instead of enum members (default False) |
| `json_schema_extra` | OpenAPI/Swagger examples |

## Literal Types for Strict Validation

Enums are the default for a fixed vocabulary — they carry behavior and are reused across
models. A `Literal` suits a one-off constraint on a model built by a `parse_*` helper or
`from_form_params()` (see
[Binding a Request Model in a Route](#binding-a-request-model-in-a-route)):

```python
# core/models/search_request.py — SearchRequest, built by from_form_params()
connected_direction: Literal["outgoing", "incoming", "both"] = Field(default="outgoing")
```

## Response Models

An API route returns the frozen domain model — `Result[Task]` — and `@boundary_handler`
serializes it (`jsonable_content` in `adapters/inbound/boundary.py`, via Pydantic's
`to_jsonable_python`). There is no per-entity Pydantic response layer: `TaskResponse` and
`TaskListResponse` exist in `task_request.py`, but no route builds them.

A Pydantic response model is for a payload that is not an entity — the search envelope:

```python
# core/models/search_request.py (abridged) — built by SearchRouter
class SearchResponse(BaseModel):
    results: list[dict[str, Any]] = Field(default_factory=list)
    # Rows in THIS page — search is top-N: one page-only query, no match-set
    # count. Never read `total` as "how many matched".
    total: int = Field(..., ge=0)
    limit: int = Field(..., ge=1)
    offset: int = Field(..., ge=0)
    facet_counts: dict[str, list[FacetCount]] = Field(default_factory=dict)
    search_time_ms: float | None = None

    def has_results(self) -> bool:
        return len(self.results) > 0
```

## Anti-Patterns

### 1. Don't Validate Input in Domain Models

Input validation belongs at the edge. (A domain model's `__post_init__` does enforce its
own invariants — a leaf model rejects a mismatched `entity_type` (G6) — but it never
re-checks what the request model already checked.)

```python
# BAD - input validation in the domain model
@dataclass(frozen=True, kw_only=True)
class Task(UserOwnedEntity):
    def __post_init__(self) -> None:
        if len(self.title) < 1:
            raise ValueError("Title required")  # Wrong layer!

# GOOD - Validation in Pydantic (edge)
class TaskCreateRequest(BaseModel):
    title: str = Field(min_length=1)
```

### 2. Don't Use dict() - Use model_dump()

```python
# BAD - Pydantic V1 pattern
data = request.dict()

# GOOD - Pydantic V2 pattern
data = request.model_dump()
data = request.model_dump(exclude_unset=True)  # Only set fields
```

### 3. Don't Validate Same Thing Twice

```python
# BAD - Redundant validation
class TaskRequest(BaseModel):
    title: str = Field(min_length=1)

    @field_validator("title")
    @classmethod
    def validate_title(cls, v):
        if len(v) < 1:  # Already checked by Field!
            raise ValueError("Title required")
        return v

# GOOD - Let Field() handle simple constraints
class TaskRequest(BaseModel):
    title: str = Field(min_length=1)  # That's it!
```

### 4. Don't Use mode="before" Unless Necessary

```python
# AVOID - mode="before" runs before type coercion
@model_validator(mode="before")
@classmethod
def validate_early(cls, data: dict[str, object]) -> dict[str, object]:
    # data is the raw input, types not yet converted
    return data

# PREFER - mode="after" has typed, validated fields
@model_validator(mode="after")
def validate_complete(self) -> Self:
    # self has properly typed fields
    return self
```

### 5. Don't Mix Validation Styles

```python
# BAD - Inconsistent patterns
class TaskRequest(BaseModel):
    title: str
    due_date: date | None = None

    # Uses shared validator
    _validate_title = validate_required_string("title")

    # Uses inline validator for same purpose
    @field_validator("due_date")
    @classmethod
    def check_date(cls, v): ...

# GOOD - Consistent use of shared validators
class TaskRequest(BaseModel):
    title: str
    due_date: date | None = None

    _validate_title = validate_required_string("title")
    _validate_dates = validate_future_date("due_date")
```

## Additional Resources

- [validation-patterns.md](validation-patterns.md) - Complete validator reference
- [request-response-reference.md](request-response-reference.md) - Request/response patterns

## Related Skills

- **[python](../python/SKILL.md)** - Core Python patterns Pydantic models use
- **[result-pattern](../result-pattern/SKILL.md)** - Services return Result[T] after Pydantic validation
- **[fasthtml](../fasthtml/SKILL.md)** - Request/response handling with Pydantic

## Foundation

- **[python](../python/SKILL.md)** - Requires understanding of dataclasses, type hints

## See Also

- `/docs/patterns/three_tier_type_system.md` - Full type system (Pydantic is Tier 1)
- `/core/models/validation_rules.py` - Shared validators source
- `/core/models/request_base.py` - Base classes source
