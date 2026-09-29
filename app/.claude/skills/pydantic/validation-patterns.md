# Pydantic Validation Patterns

Deep dive on field validators, model validators, and SKUEL's shared validator library.

## Field Validator Anatomy

```python
from pydantic import field_validator
from typing import Any

class ExampleRequest(BaseModel):
    field_name: str

    @field_validator("field_name")  # Field(s) to validate
    @classmethod                     # Always a classmethod
    def validate_field_name(        # Method name is arbitrary
        cls,                         # Class reference
        v: str                       # The field value
    ) -> str:                        # Must return the (possibly modified) value
        if not v.strip():
            raise ValueError("Cannot be empty")
        return v.strip()  # Can transform the value
```

### Key Rules

1. **Always `@classmethod`** - Required for Pydantic V2
2. **Return the value** - Even if unchanged
3. **Raise `ValueError`** - For validation failures
4. **Can transform** - Return modified value

## Multi-Field Validators

Apply same validation to multiple fields:

```python
class DateRangeRequest(BaseModel):
    start_date: date | None = None
    end_date: date | None = None
    due_date: date | None = None

    @field_validator("start_date", "end_date", "due_date")
    @classmethod
    def validate_not_past(cls, v: date | None) -> date | None:
        """Validate all date fields are not in the past"""
        if v is not None and v < today_in(current_zone()):
            raise ValueError("Date cannot be in the past")
        return v
```

## ValidationInfo for Cross-Field Access

Access fields declared earlier in the model during validation:

```python
# core/models/validation_rules.py — used by TaskCreateRequest and EventCreateRequest
def validate_recurrence_end_after_start(recurrence_end_field: str, start_field: str) -> Callable:
    @field_validator(recurrence_end_field)
    def _validate_recurrence_end(cls, v: date | None, info: ValidationInfo) -> date | None:
        if v is None:
            return v
        start_value = info.data.get(start_field)
        if start_value and v <= start_value:
            raise ValueError(f"Recurrence end must be after {start_field.replace('_', ' ')}")
        return v
    return _validate_recurrence_end
```

⚠ **A field validator does not run on a field the client omitted.** Pydantic validates a
default only when the field says `Field(validate_default=True)`. A rule of the shape
"*this* field is required — or gets a default — when *that* field has a value" written as
a `field_validator` therefore fires only when the client sends the field, which is exactly
when the rule is not needed. `validate_required_when` and `validate_url_when_online` in
`validation_rules.py` have this shape: `EventCreateRequest(is_online=True)` with no
`meeting_url` is accepted, while an explicit `meeting_url=""` is refused. Write a
conditional default or requirement as a model validator, which always runs:

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

### ValidationInfo Fields

| Field | Type | Description |
|-------|------|-------------|
| `info.data` | `dict[str, Any]` | All field values (may be incomplete) |
| `info.field_name` | `str` | Current field being validated |
| `info.mode` | `str` | Validation mode ("python" or "json") |

**Important:** `info.data` holds only the fields validated so far — those declared *before*
the current one, and only the ones that passed. A field declared after it is absent.

## Model Validators (Cross-Field)

For validation that needs all fields:

```python
from pydantic import model_validator

# core/models/goal/goal_request.py — GoalCreateRequest (abridged)
@model_validator(mode="after")
def validate_target_value(self) -> GoalCreateRequest:
    """Validate target value based on measurement type."""
    if self.measurement_type == MeasurementType.PERCENTAGE:
        if self.target_value and (self.target_value < 0 or self.target_value > 100):
            raise ValueError("Percentage target must be between 0 and 100")
    elif self.measurement_type == MeasurementType.NUMERIC and not self.target_value:
        raise ValueError("Numeric measurement requires a target value")

    return self  # Must return self
```

### mode="before" vs mode="after"

| Mode | Input | Use Case |
|------|-------|----------|
| `mode="before"` | Raw `dict` | Transform input before field validation |
| `mode="after"` | Validated model instance | Cross-field validation (preferred) |

```python
# mode="before" - for input transformation
@model_validator(mode="before")
@classmethod
def normalize_input(cls, data: dict) -> dict:
    """Normalize field names before validation"""
    if "due" in data:
        data["due_date"] = data.pop("due")
    return data

# mode="after" - for cross-field validation (PREFERRED)
@model_validator(mode="after")
def validate_business_rules(self):
    """Validate after all fields are typed and validated"""
    if self.priority == Priority.HIGH and not self.due_date:
        raise ValueError("High-priority tasks require due_date")
    return self
```

## Shared Validators Library

SKUEL's `/core/models/validation_rules.py` provides reusable validator factories.

### Available Validators

Field-validator factories (apply as class attributes):

| Factory | Checks |
|---------|--------|
| `validate_future_date(*fields)` | date/datetime not in the past (skipped under context `{"allow_past_dates": True}`) |
| `validate_past_date(*fields)` | date/datetime not in the future |
| `validate_required_string(*fields, min_length=1)` | not empty after strip; returns the stripped value |
| `validate_identity_format(*fields)` | identity-string format |
| `validate_email(*fields)` | email format |
| `validate_list_max_length(*fields, max_length)` | list length ≤ `max_length` |
| `validate_list_no_duplicates(*fields)` | no repeated items |
| `validate_time_after(later, earlier)` | time ordering |
| `validate_recurrence_end_after_start(end, start)` | recurrence end after the start date |
| `validate_required_when(field, condition_field, condition_value, default_value)` | default a field when a condition holds — ⚠ only when the field is sent (see above) |
| `validate_url_when_online(url_field, online_field)` | URL required for online events — ⚠ only when the URL is sent |
| `validate_percentage(*fields)` | 0–100 |
| `validate_score_0_to_1(*fields)` | 0–1 |
| `validate_habit_duration_by_difficulty(...)`, `validate_habit_target_days_by_pattern(...)` | habit-specific rules |
| `validate_weights_sum_to_one(field, required_keys=None, tolerance=0.05)` | each weight in 0–1, sum within tolerance of 1.0 |

Model-validator helpers (call inside a `@model_validator(mode="after")`):
`validate_date_after(later, earlier, allow_equal=False)`, `validate_timeframe_date_alignment()`.

#### A Factory's Shape

```python
# core/models/validation_rules.py
def validate_future_date(*field_names: str) -> Callable:
    """Validate date/datetime is not in the past.

    Honors validation context {"allow_past_dates": True} — the
    EXTRACT_ACTIVITIES converters pass it via model_validate() because
    historical vault notes legitimately carry past dates (Arc E, G10).
    Constructor / FastHTML auto-validation pass no context → guard stands.
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


def validate_list_no_duplicates(*field_names: str) -> Callable:
    @field_validator(*field_names)
    def _validate_no_duplicates(cls, v: list | None) -> list | None:
        if v is not None:
            seen = set()
            duplicates = set()
            for item in v:
                if item in seen:
                    duplicates.add(item)
                seen.add(item)
            if duplicates:
                raise ValueError(f"Duplicate items not allowed: {duplicates}")
        return v
    return _validate_no_duplicates
```

### Usage Pattern

Apply shared validators as class attributes:

```python
# core/models/task/task_request.py — TaskCreateRequest
_validate_dates = validate_future_date("due_date", "scheduled_date")
_validate_recurrence_end = validate_recurrence_end_after_start(
    "recurrence_end_date", "due_date"
)

# core/models/event/event_request.py — EventCreateRequest
_validate_end_time = validate_time_after("end_time", "start_time")
_validate_recurrence_end = validate_recurrence_end_after_start(
    "recurrence_end_date", "event_date"
)
```

## Model Validator Factories

For reusable cross-field validation — the factory returns a plain function you call from
your own `@model_validator(mode="after")`:

```python
# core/models/validation_rules.py
def validate_date_after(
    later_field: str,
    earlier_field: str,
    allow_equal: bool = False,
) -> Callable:
    def validator_impl(instance: Any) -> Any:
        later_value = getattr(instance, later_field, None)
        earlier_value = getattr(instance, earlier_field, None)

        if later_value is not None and earlier_value is not None:
            if allow_equal:
                if later_value < earlier_value:
                    raise ValueError(f"{later_field} must be on or after {earlier_field}")
            else:
                if later_value <= earlier_value:
                    raise ValueError(f"{later_field} must be after {earlier_field}")

        return instance

    return validator_impl
```

`validate_timeframe_date_alignment()` has the same shape: it caps the span from
`start_date` (today when unset) to `target_date` per `GoalTimeframe` — DAILY 1 day,
WEEKLY 7, MONTHLY 31, QUARTERLY 92, YEARLY 365.

**Usage:**

```python
# core/models/goal/goal_request.py — GoalCreateRequest (abridged)
@model_validator(mode="after")
def validate_target_date(self, info: ValidationInfo) -> GoalCreateRequest:
    allow_past = bool(info.context and info.context.get("allow_past_dates"))
    if not allow_past and self.target_date and self.target_date < today_in(current_zone()):
        raise ValueError("Target date must be in the future")
    # allow_equal=True: same-day goals are valid (e.g., daily goals)
    return validate_date_after("target_date", "start_date", allow_equal=True)(self)

@model_validator(mode="after")
def validate_timeframe_alignment(self) -> GoalCreateRequest:
    return validate_timeframe_date_alignment()(self)
```

## Error Messages

### Custom Error Messages

```python
@field_validator("email")
@classmethod
def validate_email(cls, v: str) -> str:
    if "@" not in v:
        raise ValueError("Invalid email format - missing @")
    if not v.endswith((".com", ".org", ".edu", ".io")):
        raise ValueError("Email must use .com, .org, .edu, or .io domain")
    return v.lower()
```

### Structured Errors

Pydantic provides structured error output:

```python
from pydantic import ValidationError

try:
    request = TaskCreateRequest(title="", priority="invalid")
except ValidationError as e:
    errors = e.errors()
    # [
    #   {'type': 'string_too_short', 'loc': ('title',), 'msg': 'String should have at least 1 character', ...},
    #   {'type': 'enum', 'loc': ('priority',), 'msg': "Input should be 'low', 'medium' or 'high'", ...}
    # ]
```

### Route-Level Parsing (Result[T] Integration)

In routes, use the `adapters/inbound/form_helpers.py` readers to convert Pydantic `ValidationError` into `Result.fail(Errors.validation(...))` automatically — no manual try/except needed. `parse_body()` reads JSON or form by Content-Type and is the reader at a door both API clients and HTMX forms reach (the CRUD factory's create/update, the admin account actions); `parse_json_body()` / `parse_form_body()` serve a route with one caller kind. A failure is a **400** through `@boundary_handler`.

```python
from adapters.inbound.form_helpers import parse_body, parse_form_body, parse_json_body

# JSON or form, by Content-Type → Result[T]
result = await parse_body(request, TaskUpdateRequest)

# JSON body → Pydantic model → Result[T]
result = await parse_json_body(request, TaskCreateRequest)
if result.is_error:
    return Result.fail(result)  # SKUEL028: propagate across the type boundary
req = result.value

# Form data → Pydantic model → Result[T] (empty strings → None)
result = await parse_form_body(request, RequestRevisionRequest)

# When the owner uid is a model field (TrackHabitRequest.habit_uid): parse first, then
# verify_entity_ownership(service, req.habit_uid, user_uid, ...). When it is in the query string
# (POST /api/principles/link?uid=): verify first, then parse — that model's `uid` is the target.
# Nothing is merged into the body before validation.
```

See: `/docs/patterns/API_VALIDATION_PATTERNS.md`

## Testing Validators

```python
import pytest
from pydantic import ValidationError

def test_task_title_required():
    """Title cannot be empty"""
    with pytest.raises(ValidationError) as exc:
        TaskCreateRequest(title="")

    errors = exc.value.errors()
    assert any(e["loc"] == ("title",) for e in errors)


def test_task_date_not_past():
    """Due date cannot be in the past"""
    yesterday = today_in(current_zone()) - timedelta(days=1)

    with pytest.raises(ValidationError) as exc:
        TaskCreateRequest(title="Test", due_date=yesterday)

    errors = exc.value.errors()
    assert "past" in str(errors).lower()


def test_goal_date_ordering():
    """Target date must be on or after start date"""
    today = today_in(current_zone())
    with pytest.raises(ValidationError, match="must be on or after start_date"):
        GoalCreateRequest(
            title="Test",
            start_date=today + timedelta(days=30),
            target_date=today + timedelta(days=10),  # Before start (both future,
        )                                            # so the past-date rule stays quiet)
```

## Performance Tips

1. **Use Field() constraints first** - Faster than custom validators
2. **Avoid mode="before"** - Adds overhead, use only when necessary
3. **Reuse shared validators** - Factory functions are cached
4. **Validate early** - Fail fast on invalid input
