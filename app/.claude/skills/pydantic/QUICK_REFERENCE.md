# Pydantic - Quick Reference

> **Fast lookup** for common syntax, methods, and operations

---

## Where Pydantic Lives (Three-Tier Type System)

Pydantic is **Tier 1 — the edges only**: request/response models validating external input.
Tier 2 is DTOs (mutable data movement), Tier 3 is frozen dataclasses (core domain logic).
Request models live in `core/models/{domain}/{domain}_request.py` (e.g. `core/models/task/task_request.py`);
never validate in domain models — a frozen dataclass with `__post_init__` validation is the wrong layer.

---

## Canonical Snippets

### Create request (real shape, `core/models/task/task_request.py`)

```python
from core.models.request_base import CreateRequestBase
from core.models.validation_rules import validate_future_date, validate_recurrence_end_after_start

class TaskCreateRequest(CreateRequestBase):
    title: str = Field(min_length=1, max_length=200, description="Task title")
    description: str | None = Field(default=None, description="Detailed description")
    due_date: date | None = Field(default=None, description="Due date")
    priority: Priority = Field(default=Priority.MEDIUM, description="Task priority")
    status: EntityStatus = Field(default=EntityStatus.DRAFT, description="Initial status")
    tags: list[str] = Field(default_factory=list, description="Task tags")

    # Shared validators (DRY — factories from validation_rules.py)
    _validate_dates = validate_future_date("due_date", "scheduled_date")
    _validate_recurrence_end = validate_recurrence_end_after_start("recurrence_end_date", "due_date")

    @model_validator(mode="after")
    def validate_due_after_scheduled(self) -> "TaskCreateRequest":
        if self.due_date and self.scheduled_date and self.due_date < self.scheduled_date:
            raise ValueError("Due date cannot be before scheduled date")
        return self
```

**When to use**: Every POST body. Inherit `CreateRequestBase` / `UpdateRequestBase` / `FilterRequestBase` / `ResponseBase` from `core/models/request_base.py` — never redeclare `model_config`.

### Field validator (V2 syntax — decorator + `@classmethod`)

```python
@field_validator("completion_date")
@classmethod
def validate_completion_date(cls, v, info: ValidationInfo) -> Any:
    if info.data.get("status") == EntityStatus.COMPLETED and not v:
        v = date.today()
    return v
```

**When to use**: Single-field logic `Field()` constraints can't express; `info.data` reads already-validated earlier fields, `info.context` carries validation context (e.g. `{"allow_past_dates": True}` skips `validate_future_date` for historical vault ingestion).

### Model validator (cross-field)

```python
@model_validator(mode="after")
def validate_date_ordering(self) -> "GoalCreateRequest":
    if self.target_date and self.start_date and self.target_date <= self.start_date:
        raise ValueError("Target date must be after start date")
    return self
```

**When to use**: Validation spanning multiple fields. Prefer `mode="after"` (typed `self`) over `mode="before"` (raw dict).

### Typed update intent — ADR-066 (`TaskUpdateRequest.to_intent()`)

```python
def to_intent(self) -> TaskUpdateIntent:
    set_fields = self.model_fields_set

    def when_set[T](name: str, value: T) -> T | Unset:
        return value if name in set_fields else UNSET

    return TaskUpdateIntent(
        title=when_set("title", self.title),
        priority=when_set("priority", self.priority.value if self.priority is not None else None),
        # ... one when_set per updatable field; enums lowered to .value
    )
```

**When to use**: Every Activity Domain `*UpdateRequest`. Absent field → `UNSET` (untouched); explicit `None` → clear. `CRUDRouteFactory` calls `.to_intent()` when the schema satisfies `SupportsToIntent` (`core/models/update_contracts.py`); non-activity schemas fall back to `RawChanges` from `model_dump(exclude_unset=True)`. Never resurrect `*UpdatePayload` (SKUEL025).

---

## Key Infrastructure

| Piece | Location | Purpose |
|-------|----------|---------|
| Base classes | `core/models/request_base.py` | `RequestBase`, `CreateRequestBase`, `UpdateRequestBase`, `FilterRequestBase`, `AnalyticsRequestBase`, `ResponseBase` (`from_attributes=True`), `ListResponseBase` |
| Shared validator factories | `core/models/validation_rules.py` | `validate_future_date`, `validate_required_string`, `validate_percentage`, `validate_recurrence_end_after_start`, `validate_list_no_duplicates`, ~20 more |
| Update sentinels | `core/models/sentinels.py` | `UNSET` / `Unset` for partial-patch intents |
| Intent contracts | `core/models/update_contracts.py` | `SupportsToIntent`, `SupportsToChanges`, `RawChanges` |
| Body parsing → Result | `adapters/inbound/form_helpers.py` | `parse_json_body(request, Model)` / `parse_form_body(request, Model)` — catch `ValidationError`, return `Result.fail(Errors.validation(..., field="body"))` |
| Query-param parsing | `adapters/inbound/route_factories/route_helpers.py` | Silent-default: `parse_bool_query_param`, `parse_date_query_param`, `parse_csv_query_param`, `parse_pagination_params`; strict Result-based: `parse_date_param_strict`, `parse_int_param_strict` |

### Validation error → HTTP status

`_get_status_for_error` in `adapters/inbound/boundary.py` maps error categories: **VALIDATION → 400**, BUSINESS → 422, NOT_FOUND → 404. So:

- **Query params (GET)** → 400 (strict `route_helpers` parsers return `Errors.validation` Results).
- **JSON bodies via `parse_json_body`** → `Errors.validation` Result → 400 through `boundary_handler`.
- **JSON bodies auto-bound by FastHTML** (`body: SomeRequest` handler param) → also **400**, via `install_request_validation_guard`. Both binding styles agree. The guard is required, not decorative: FastHTML constructs the model during parameter extraction, *before* the handler and its `@boundary_handler` wrapper run, so the `ValidationError` escapes every route-level guard and was surfacing as a **500** until an app-level handler caught it (sibling of `install_malformed_json_guard` for malformed JSON; both wired in bootstrap's `_create_web_app`).

⚠ **Never annotate an auto-bound body field as a `Literal`.** FastHTML coerces each incoming value by *calling* the annotation, and `Literal(...)` raises `TypeError: Cannot instantiate typing.Literal` — not a `ValidationError`, so no guard converts it and the request 500s. Use an enum, a validated `str`, or bind via `parse_json_body`.

---

## Common Pitfalls

| Problem | Solution |
|---------|----------|
| `request.dict()` (V1) | `request.model_dump()`; PATCH uses `model_dump(exclude_unset=True)` |
| Validation in a frozen dataclass `__post_init__` | Move to the Pydantic request model — validation belongs at the edge |
| Re-checking what `Field(min_length=1)` already enforces | Let `Field()` handle declarative constraints; validators are for logic only |
| Inline validator duplicating a shared one | Use the `validation_rules.py` factory (`_validate_title = validate_required_string("title")`) |
| Passing `request.model_dump()` to `service.update` | Build the typed intent: `request.to_intent()` (ADR-066); dict patches are `RawChanges` only for non-activity domains |
| `None` vs absent confusion in updates | `model_fields_set` distinguishes them — absent → `UNSET`, explicit `None` → clear |
| Enum objects leaking to persistence | `to_intent()` lowers enums to `.value`; `RawChanges` path runs `get_enum_value` |
| `@model_validator(mode="before")` by default | Prefer `mode="after")` — fields are typed and validated |
| Declaring `model_config` per model | Inherit from `request_base.py`; only `ResponseBase` needs `from_attributes=True` |
| try/except `ValidationError` boilerplate in routes | `parse_json_body(request, Model)` returns `Result[Model]` |

---

**See Also**: [SKILL.md](SKILL.md) for the three-tier system and full validator catalog
**See Also**: [validation-patterns.md](validation-patterns.md) for the complete validator reference
**See Also**: [request-response-reference.md](request-response-reference.md) for Create/Update/Filter/Response patterns
**See Also**: `/docs/patterns/API_VALIDATION_PATTERNS.md`, `/docs/decisions/ADR-066-typed-update-intents.md`
