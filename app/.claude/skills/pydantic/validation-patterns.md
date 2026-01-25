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
        if v is not None and v < date.today():
            raise ValueError("Date cannot be in the past")
        return v
```

## ValidationInfo for Cross-Field Access

Access other fields during validation:

```python
from pydantic import field_validator, ValidationInfo

class TaskRequest(BaseModel):
    status: ActivityStatus
    completion_date: date | None = None
    cancelled_reason: str | None = None

    @field_validator("completion_date")
    @classmethod
    def auto_set_completion(cls, v: date | None, info: ValidationInfo) -> date | None:
        """Auto-set completion date when status is COMPLETED"""
        status = info.data.get("status")
        if status == ActivityStatus.COMPLETED and v is None:
            return date.today()
        return v

    @field_validator("cancelled_reason")
    @classmethod
    def require_reason_if_cancelled(cls, v: str | None, info: ValidationInfo) -> str | None:
        """Require reason when status is CANCELLED"""
        status = info.data.get("status")
        if status == ActivityStatus.CANCELLED and not v:
            raise ValueError("Cancellation reason required")
        return v
```

### ValidationInfo Fields

| Field | Type | Description |
|-------|------|-------------|
| `info.data` | `dict[str, Any]` | All field values (may be incomplete) |
| `info.field_name` | `str` | Current field being validated |
| `info.mode` | `str` | Validation mode ("python" or "json") |

**Important:** `info.data` contains fields in definition order. Fields defined after the current one may not be present yet.

## Model Validators (Cross-Field)

For validation that needs all fields:

```python
from pydantic import model_validator

class GoalRequest(BaseModel):
    start_date: date
    target_date: date
    timeframe: GoalTimeframe

    @model_validator(mode="after")
    def validate_date_alignment(self):
        """Validate dates align with timeframe"""
        if self.target_date <= self.start_date:
            raise ValueError("Target must be after start")

        # Check timeframe alignment
        days = (self.target_date - self.start_date).days
        if self.timeframe == GoalTimeframe.WEEKLY and days > 14:
            raise ValueError("Weekly goals should be < 2 weeks")
        elif self.timeframe == GoalTimeframe.MONTHLY and days > 45:
            raise ValueError("Monthly goals should be < 45 days")

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
    if self.priority == Priority.URGENT and not self.due_date:
        raise ValueError("Urgent tasks require due_date")
    return self
```

## Shared Validators Library

SKUEL's `/core/models/validation_rules.py` provides reusable validator factories.

### Available Validators

#### Date/Time Validators

```python
def validate_future_date(*field_names: str) -> Callable:
    """Validate date/datetime is not in the past"""
    @field_validator(*field_names)
    def _validate(cls, v: date | datetime | None) -> date | datetime | None:
        if v is None:
            return v
        if isinstance(v, datetime):
            if v <= datetime.now():
                raise ValueError("Date/time cannot be in the past")
        elif isinstance(v, date) and v < date.today():
            raise ValueError("Date cannot be in the past")
        return v
    return _validate


def validate_date_not_future(*field_names: str) -> Callable:
    """Validate date is not in the future (for historical dates)"""
    @field_validator(*field_names)
    def _validate(cls, v: date | None) -> date | None:
        if v is not None and v > date.today():
            raise ValueError("Date cannot be in the future")
        return v
    return _validate


def validate_recurrence_end_after_start(
    end_field: str,
    start_field: str
) -> Callable:
    """Validate end date is after start date"""
    @field_validator(end_field)
    def _validate(cls, v: date | None, info: ValidationInfo) -> date | None:
        start = info.data.get(start_field)
        if v and start and v <= start:
            raise ValueError(f"{end_field} must be after {start_field}")
        return v
    return _validate
```

#### String Validators

```python
def validate_required_string(*field_names: str) -> Callable:
    """Validate string is not empty after stripping whitespace"""
    @field_validator(*field_names)
    def _validate(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("Cannot be empty or whitespace only")
        return v.strip()
    return _validate


def validate_slug(*field_names: str) -> Callable:
    """Validate string is URL-safe slug format"""
    @field_validator(*field_names)
    def _validate(cls, v: str) -> str:
        import re
        if not re.match(r"^[a-z0-9]+(?:-[a-z0-9]+)*$", v):
            raise ValueError("Must be lowercase alphanumeric with hyphens")
        return v
    return _validate
```

#### Numeric Validators

```python
def validate_percentage(*field_names: str) -> Callable:
    """Validate value is between 0 and 100"""
    @field_validator(*field_names)
    def _validate(cls, v: float | None) -> float | None:
        if v is not None and not (0 <= v <= 100):
            raise ValueError("Must be between 0 and 100")
        return v
    return _validate


def validate_positive(*field_names: str) -> Callable:
    """Validate number is positive"""
    @field_validator(*field_names)
    def _validate(cls, v: int | float | None) -> int | float | None:
        if v is not None and v <= 0:
            raise ValueError("Must be positive")
        return v
    return _validate


def validate_weights_sum_to_one(weights_field: str) -> Callable:
    """Validate dict values sum to 1.0"""
    @field_validator(weights_field)
    def _validate(cls, v: dict[str, float] | None) -> dict[str, float] | None:
        if v is not None:
            total = sum(v.values())
            if not (0.99 <= total <= 1.01):  # Allow float tolerance
                raise ValueError(f"Weights must sum to 1.0, got {total}")
        return v
    return _validate
```

#### List Validators

```python
def validate_list_max_length(field_name: str, max_length: int) -> Callable:
    """Validate list does not exceed max length"""
    @field_validator(field_name)
    def _validate(cls, v: list | None) -> list | None:
        if v is not None and len(v) > max_length:
            raise ValueError(f"Cannot exceed {max_length} items")
        return v
    return _validate


def validate_unique_list(*field_names: str) -> Callable:
    """Validate list contains no duplicates"""
    @field_validator(*field_names)
    def _validate(cls, v: list | None) -> list | None:
        if v is not None and len(v) != len(set(v)):
            raise ValueError("List contains duplicates")
        return v
    return _validate
```

### Usage Pattern

Apply shared validators as class attributes:

```python
class GoalCreateRequest(BaseModel):
    title: str
    description: str | None = None
    start_date: date | None = None
    target_date: date | None = None
    progress: float | None = None
    weights: dict[str, float] | None = None
    tags: list[str] = Field(default_factory=list)

    # Apply shared validators
    _validate_title = validate_required_string("title")
    _validate_description = validate_required_string("description")
    _validate_dates = validate_future_date("start_date", "target_date")
    _validate_date_order = validate_recurrence_end_after_start("target_date", "start_date")
    _validate_progress = validate_percentage("progress")
    _validate_weights = validate_weights_sum_to_one("weights")
    _validate_tags = validate_unique_list("tags")
```

## Model Validator Factories

For reusable cross-field validation:

```python
def validate_date_after(
    later_field: str,
    earlier_field: str,
    allow_equal: bool = False
) -> Callable:
    """Factory for model validator ensuring date ordering"""
    def validator(self):
        later = getattr(self, later_field)
        earlier = getattr(self, earlier_field)
        if later and earlier:
            if allow_equal:
                if later < earlier:
                    raise ValueError(f"{later_field} must be >= {earlier_field}")
            else:
                if later <= earlier:
                    raise ValueError(f"{later_field} must be > {earlier_field}")
        return self
    return validator


def validate_timeframe_date_alignment() -> Callable:
    """Factory for timeframe/date validation"""
    def validator(self):
        if not hasattr(self, "timeframe") or not hasattr(self, "target_date"):
            return self

        if self.target_date and self.start_date:
            days = (self.target_date - self.start_date).days
            max_days = {
                GoalTimeframe.DAILY: 1,
                GoalTimeframe.WEEKLY: 14,
                GoalTimeframe.MONTHLY: 45,
                GoalTimeframe.QUARTERLY: 120,
                GoalTimeframe.YEARLY: 400,
            }
            limit = max_days.get(self.timeframe)
            if limit and days > limit:
                raise ValueError(f"{self.timeframe} goal exceeds {limit} days")
        return self
    return validator
```

**Usage:**

```python
class GoalCreateRequest(BaseModel):
    start_date: date
    target_date: date
    timeframe: GoalTimeframe

    @model_validator(mode="after")
    def validate_dates(self):
        return validate_date_after("target_date", "start_date")(self)

    @model_validator(mode="after")
    def validate_alignment(self):
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
    print(e.errors())
    # [
    #   {'type': 'string_too_short', 'loc': ('title',), 'msg': 'String should have at least 1 character'},
    #   {'type': 'enum', 'loc': ('priority',), 'msg': "Input should be 'low', 'medium', 'high' or 'urgent'"}
    # ]
```

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
    yesterday = date.today() - timedelta(days=1)

    with pytest.raises(ValidationError) as exc:
        TaskCreateRequest(title="Test", due_date=yesterday)

    errors = exc.value.errors()
    assert "past" in str(errors).lower()


def test_goal_date_ordering():
    """Target date must be after start date"""
    with pytest.raises(ValidationError) as exc:
        GoalCreateRequest(
            title="Test",
            start_date=date(2025, 6, 1),
            target_date=date(2025, 5, 1),  # Before start!
        )

    assert "after" in str(exc.value).lower()
```

## Performance Tips

1. **Use Field() constraints first** - Faster than custom validators
2. **Avoid mode="before"** - Adds overhead, use only when necessary
3. **Reuse shared validators** - Factory functions are cached
4. **Validate early** - Fail fast on invalid input
