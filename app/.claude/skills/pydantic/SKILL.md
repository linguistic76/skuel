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
from pydantic import BaseModel, Field

class TaskCreateRequest(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    priority: Priority = Field(default=Priority.MEDIUM)


# Tier 2: DTO (Transfer) - Mutable data movement
@dataclass
class TaskDTO:
    uid: str
    title: str
    priority: str


# Tier 3: Domain Model (Core) - Immutable business logic
@dataclass(frozen=True)
class Task:
    uid: str
    title: str
    priority: Priority

    def is_overdue(self) -> bool:
        """Business logic lives in domain models"""
        return self.due_date and self.due_date < date.today()
```

## Base Class Hierarchy

SKUEL uses a base class hierarchy to eliminate repeated `model_config` declarations:

```python
# core/models/request_base.py
from pydantic import BaseModel, ConfigDict

class RequestBase(BaseModel):
    """Base for all request models"""
    model_config = ConfigDict()


class CreateRequestBase(RequestBase):
    """Base for POST create requests"""
    pass


class UpdateRequestBase(RequestBase):
    """Base for PATCH update requests - all fields optional"""
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


class TaskResponse(ResponseBase):
    uid: str
    title: str
    is_overdue: bool  # Computed field
```

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
from pydantic import field_validator
from typing import Any

class TaskCreateRequest(BaseModel):
    audio_file_path: str = Field(min_length=1)
    custom_vocabulary: list[str] = Field(default_factory=list)

    @field_validator("audio_file_path")
    @classmethod
    def validate_audio_path(cls, v: str) -> str:
        """Validate file has allowed extension"""
        allowed = {".mp3", ".wav", ".m4a", ".webm", ".ogg", ".flac"}
        if not any(v.lower().endswith(ext) for ext in allowed):
            raise ValueError(f"Audio file must have: {', '.join(allowed)}")
        return v

    @field_validator("custom_vocabulary")
    @classmethod
    def validate_vocabulary(cls, v: list[str]) -> list[str]:
        """Validate and normalize vocabulary list"""
        if len(v) > 100:
            raise ValueError("Custom vocabulary cannot exceed 100 words")
        return [word.strip().lower() for word in v if word.strip()]
```

### Conditional Validation with ValidationInfo

Access other field values during validation:

```python
from pydantic import field_validator, ValidationInfo

class TaskStatusUpdateRequest(BaseModel):
    status: ActivityStatus
    completion_date: date | None = None

    @field_validator("completion_date")
    @classmethod
    def validate_completion_date(cls, v: date | None, info: ValidationInfo) -> date | None:
        """Auto-set completion date when status is COMPLETED"""
        if info.data.get("status") == ActivityStatus.COMPLETED and not v:
            return date.today()
        return v
```

## Model Validation (Cross-Field)

Use `@model_validator(mode="after")` for validation that spans multiple fields:

```python
from pydantic import model_validator

class GoalCreateRequest(BaseModel):
    start_date: date | None = Field(default_factory=date.today)
    target_date: date | None = None
    measurement_type: MeasurementType = Field(MeasurementType.PERCENTAGE)
    target_value: float | None = None

    @model_validator(mode="after")
    def validate_date_ordering(self):
        """Ensure target_date is after start_date"""
        if self.target_date and self.start_date:
            if self.target_date <= self.start_date:
                raise ValueError("Target date must be after start date")
        return self

    @model_validator(mode="after")
    def validate_target_value(self):
        """Validate target_value based on measurement_type"""
        if self.measurement_type == MeasurementType.PERCENTAGE:
            if self.target_value and not (0 <= self.target_value <= 100):
                raise ValueError("Percentage must be 0-100")
        elif self.measurement_type == MeasurementType.NUMERIC:
            if self.target_value is None:
                raise ValueError("Numeric measurement requires target_value")
        return self
```

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
    """Factory: Validate date/datetime is not in the past"""
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


def validate_required_string(*field_names: str) -> Callable:
    """Factory: Validate string is not empty after strip"""
    @field_validator(*field_names)
    def _validate(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("Cannot be empty")
        return v.strip()
    return _validate


def validate_percentage(*field_names: str) -> Callable:
    """Factory: Validate value is 0-100"""
    @field_validator(*field_names)
    def _validate(cls, v: float | None) -> float | None:
        if v is not None and not (0 <= v <= 100):
            raise ValueError("Must be between 0 and 100")
        return v
    return _validate
```

**Usage in request models:**

```python
class GoalCreateRequest(BaseModel):
    title: str
    due_date: date | None = None
    progress: float | None = None

    # Apply shared validators
    _validate_title = validate_required_string("title")
    _validate_dates = validate_future_date("due_date", "target_date")
    _validate_progress = validate_percentage("progress")
```

## Serialization Configuration

### ConfigDict Options

```python
from pydantic import ConfigDict

class TaskCreateRequest(BaseModel):
    priority: Priority = Priority.MEDIUM
    domain: Domain = Domain.KNOWLEDGE

    model_config = ConfigDict(
        # Keep enums as objects (not .value strings)
        use_enum_values=False,

        # JSON schema example for docs
        json_schema_extra={
            "example": {
                "title": "Complete ML Course",
                "priority": "high",
                "domain": "tech",
            }
        }
    )


class TaskResponse(BaseModel):
    uid: str
    title: str
    created_at: datetime

    model_config = ConfigDict(
        # Allow creation from ORM/dataclass objects
        from_attributes=True,

        # Serialize enums to their values
        use_enum_values=True,
    )
```

### When to Use Each Option

| Option | Use Case |
|--------|----------|
| `use_enum_values=False` | Keep type safety in request processing |
| `use_enum_values=True` | JSON serialization in responses |
| `from_attributes=True` | Create from DTO/domain model attributes |
| `json_schema_extra` | OpenAPI/Swagger documentation |

## Literal Types for Strict Validation

Use `Literal` for fixed string values (enum-like without defining an enum):

```python
from typing import Literal

ProcessingStatusLiteral = Literal[
    "pending", "transcribing", "transcribed",
    "analyzing", "completed", "failed"
]
AudioFormatLiteral = Literal["mp3", "wav", "m4a", "webm", "ogg", "flac"]
LanguageCodeLiteral = Literal["en", "es", "fr", "de", "zh", "ja"]

class TranscriptionCreateRequest(BaseModel):
    service: Literal["deepgram", "whisper"] = "deepgram"
    language: LanguageCodeLiteral = "en"
    audio_format: AudioFormatLiteral
```

## Response Models

### The from_dto() Pattern

Response models create themselves from DTOs with computed fields:

```python
class TaskResponse(ResponseBase):
    uid: str
    title: str
    status: ActivityStatus
    priority: Priority
    created_at: datetime

    # Computed fields (from domain model business logic)
    is_overdue: bool
    is_recurring: bool
    impact_score: float

    @classmethod
    def from_dto(
        cls,
        dto: "TaskDTO",
        rels: "TaskRelationships | None" = None
    ) -> "TaskResponse":
        """Create response from DTO with graph relationships"""
        from .task import Task

        # Use domain model for business logic
        task = Task.from_dto(dto)

        return cls(
            uid=dto.uid,
            title=dto.title,
            status=dto.status,
            priority=dto.priority,
            created_at=dto.created_at,
            # Computed from domain model
            is_overdue=task.is_overdue(),
            is_recurring=task.is_recurring(),
            impact_score=task.impact_score(),
            # From graph relationships
            subtask_uids=list(rels.subtask_uids) if rels else [],
        )
```

### Search Response with Helper Methods

```python
class SearchResponse(BaseModel):
    results: list[dict[str, Any]] = Field(default_factory=list)
    total: int = Field(..., ge=0)
    limit: int = Field(..., ge=1)
    offset: int = Field(..., ge=0)
    facet_counts: dict[str, list[FacetCount]] = Field(default_factory=dict)
    search_time_ms: float | None = None

    def has_results(self) -> bool:
        return len(self.results) > 0

    def has_more_pages(self) -> bool:
        return (self.offset + self.limit) < self.total

    def get_page_info(self) -> dict[str, int]:
        current_page = (self.offset // self.limit) + 1
        total_pages = (self.total + self.limit - 1) // self.limit
        return {
            "current_page": current_page,
            "total_pages": total_pages,
            "showing_from": self.offset + 1,
            "showing_to": min(self.offset + self.limit, self.total),
        }
```

## Anti-Patterns

### 1. Don't Validate in Domain Models

```python
# BAD - Validation in domain model
@dataclass(frozen=True)
class Task:
    title: str

    def __post_init__(self):
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
def validate_early(cls, data):
    # data is raw dict, types not yet converted
    ...

# PREFER - mode="after" has typed, validated fields
@model_validator(mode="after")
def validate_complete(self):
    # self has properly typed fields
    ...
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
