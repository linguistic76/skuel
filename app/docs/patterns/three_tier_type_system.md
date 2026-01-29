---
title: Three-Tier Type System
updated: 2026-01-24
status: current
category: patterns
tags:
- patterns
- system
- three
- tier
- type
- typeddict
- pydantic
- validation
related:
- query_architecture.md
- API_VALIDATION_PATTERNS.md
related_skills:
- pydantic
- python
---

# Three-Tier Type System

*Last updated: 2026-01-24*

## Core Principle

> "Pydantic at the edges, pure Python at the core"

```
External World → [Pydantic] → [DTOs] → [Domain Models] → Core Logic
```

## The Three Tiers

| Tier | Type | Mutability | Purpose |
|------|------|------------|---------|
| **External** | Pydantic Models | N/A | Validation & serialization |
| **Transfer** | DTOs | Mutable | Data movement between layers |
| **Core** | Domain Models | **Frozen** | Immutable business entities |

## Data Flow Overview

**See [DATA_FLOW_WALKTHROUGH.md](/docs/tutorials/DATA_FLOW_WALKTHROUGH.md) for a complete step-by-step example following a Task creation request through all tiers.**

### Create Flow (HTTP → Neo4j)

```
User Client
     │
     │ POST /api/tasks/create + JSON
     ▼
[Tier 1: Pydantic Request]
     │ Validates JSON, returns 422 on failure
     ▼
[Tier 2: DTO]
     │ Generate UID, set timestamps, prepare for persistence
     ▼
[Neo4j]
     │ Store properties + create relationship edges
```

### Read Flow (Neo4j → HTTP)

```
[Neo4j]
     │ Query node properties + relationships
     ▼
[Tier 2: DTO]
     │ Reconstitute from database (strings → enums/dates)
     ▼
[Tier 3: Domain Model]
     │ Apply business logic (is_overdue, urgency_score, etc.)
     ▼
[Tier 1: Pydantic Response]
     │ Combine scalar fields + relationships + computed fields
     ▼
User Client (receives JSON)
```

### When to Use Each Tier

**Always use Tier 1 (Pydantic)**:
- API request validation (prevents 500 errors)
- API response serialization (consistent JSON format)

**Always use Tier 2 (DTO)**:
- Service layer operations (mutable for status updates)
- Database serialization (to_dict / from_dict)

**Tier 3 (Domain) is optional**:
- ✅ Use when: Complex business logic, immutability semantics, protocol-based generics
- ❌ Skip when: Simple bookkeeping (Finance), admin-only CRUD (no complex state)

## Implementation Example

```python
# Tier 1: Pydantic (External)
class TaskCreateRequest(BaseModel):
    title: str
    due_date: Optional[date]

# Tier 2: DTO (Transfer)
@dataclass
class TaskDTO:
    uid: str
    title: str
    due_date: Optional[date]

# Tier 3: Domain Model (Core)
@dataclass(frozen=True)
class TaskPure:
    uid: str
    title: str
    due_date: Optional[date]

    def is_overdue(self) -> bool:
        """Business logic lives here"""
        return self.due_date and self.due_date < date.today()
```

## Tier 1: Pydantic Request Models (External)

**Core Principle:** "Pydantic at the edges - validate all external input at API boundaries"

Pydantic request models are **Tier 1 (External)** types used exclusively for API input validation. They prevent 500 errors from malformed data by validating structure, types, and constraints at the API boundary.

### File Organization

Request models live in domain-specific `*_request.py` files:

```
core/models/{domain}/
├── {domain}_domain.py     # Domain models (Tier 3)
├── {domain}_dto.py        # DTOs (Tier 2)
└── {domain}_request.py    # Pydantic request models (Tier 1)
```

### Example: Context API Request Models

```python
# core/models/context/context_request.py

from typing import Any, Literal
from pydantic import BaseModel, Field

class TaskCompletionRequest(BaseModel):
    """Request model for completing a task with context awareness."""

    context: dict[str, Any] = Field(
        default_factory=dict,
        description="Context data (knowledge_applied, time_invested_minutes)"
    )
    reflection: str = Field(
        default="",
        max_length=2000,
        description="Reflection notes on task completion"
    )

class HabitCompletionRequest(BaseModel):
    """Request model for completing a habit with quality tracking."""

    quality: Literal["poor", "fair", "good", "excellent"] = Field(
        default="good",
        description="Quality rating of the habit completion"
    )
    environmental_factors: dict[str, Any] = Field(
        default_factory=dict,
        description="Environmental context (location, mood, etc.)"
    )
```

### Usage in Routes

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

    Pydantic validates:
    - JSON structure (dict vs string)
    - Field types (str, int, etc.)
    - Field constraints (max_length, Literal enums)
    - Returns 422 on validation failure
    """
    return await service.complete_task_with_context(
        task_uid=task_uid,
        completion_context=body.context,  # Type-safe access
        reflection_notes=body.reflection,
    )
```

### Benefits

- ✅ **Automatic Validation**: Structure, types, and constraints checked automatically
- ✅ **Type Safety**: MyPy validates field access at dev time
- ✅ **Self-Documenting**: Models show expected structure and constraints
- ✅ **Clear Errors**: 422 responses with field-level details
- ✅ **No Boilerplate**: No manual JSON parsing or validation needed

### Validation Features

**Field Constraints:**
```python
class MyRequest(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    priority: int = Field(ge=1, le=5)  # 1-5 range
    tags: list[str] = Field(max_length=10)  # Max 10 tags
```

**Enum Validation (Literal Types):**
```python
QualityLiteral = Literal["poor", "fair", "good", "excellent"]

class HabitRequest(BaseModel):
    quality: QualityLiteral = Field(default="good")
    # Invalid values → 422: "Input should be 'poor', 'fair', 'good' or 'excellent'"
```

**Optional Fields with Defaults:**
```python
class TaskRequest(BaseModel):
    context: dict[str, Any] = Field(default_factory=dict)  # Empty dict
    reflection: str = Field(default="")  # Empty string
    notes: str | None = Field(default=None)  # Nullable
```

See [API_VALIDATION_PATTERNS.md](API_VALIDATION_PATTERNS.md) for comprehensive validation patterns and examples.

### Existing Request Models

**Finance Domain** (`core/models/finance/finance_request.py`):
- `ExpenseCreateRequest`, `ExpenseUpdateRequest`
- `BudgetCreateRequest`, `BudgetUpdateRequest`
- Literal types for enums (ExpenseStatus, PaymentMethod, etc.)

**Knowledge Domain** (`core/models/ku/ku_request.py`):
- `KuCreateRequest`, `KuUpdateRequest`

**Context Domain** (`core/models/context/context_request.py`):
- `TaskCompletionRequest`
- `GoalTaskGenerationRequest`
- `HabitCompletionRequest`

## Frozen Dataclass Dynamic Defaults

**Core Principle:** "Runtime-correct `__post_init__` pattern requires MyPy suppression"

Frozen dataclasses in SKUEL use `__post_init__` to set dynamic defaults for mutable fields (`datetime`, `list`, `dict`). This pattern is **architecturally correct** and works perfectly at runtime, but causes MyPy type errors due to the `None` default values.

### The Pattern

```python
@dataclass(frozen=True)
class TaskPure:
    uid: str
    title: str

    # Fields with dynamic defaults
    created_at: datetime = None  # type: ignore[assignment]
    updated_at: datetime = None  # type: ignore[assignment]
    tags: list[str] = None  # type: ignore[assignment]
    metadata: dict[str, Any] = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        """Initialize mutable fields with proper defaults."""
        if self.created_at is None:
            object.__setattr__(self, 'created_at', datetime.now())
        if self.updated_at is None:
            object.__setattr__(self, 'updated_at', datetime.now())
        if self.tags is None:
            object.__setattr__(self, 'tags', [])
        if self.metadata is None:
            object.__setattr__(self, 'metadata', {})
```

### Why This Pattern

1. **Frozen Constraint**: Can't use `field(default_factory=datetime.now)` in frozen dataclasses
2. **Dynamic Defaults**: `created_at` must be set to `datetime.now()` at instantiation time (not class definition time)
3. **Immutability Preserved**: `object.__setattr__()` bypasses frozen constraint during initialization only
4. **Runtime Correctness**: Works perfectly - fields are NEVER None at runtime

### Why MyPy Complains

- Type annotation says `datetime` but default is `None` → incompatible types
- MyPy can't see that `__post_init__` guarantees non-None values

### The Solution

Use `# type: ignore[assignment]` to suppress static analysis warnings:

```python
created_at: datetime = None  # type: ignore[assignment]
```

### Automated Fixing

```bash
# Apply type ignore comments to all affected fields
poetry run python scripts/add_frozen_dataclass_type_ignores.py
```

### Statistics

As of October 2025:
- 322 fields across 67 files use this pattern
- All in `core/models/` (frozen domain models and DTOs)
- Covers `datetime`, `date`, `list`, `dict`, `set` fields

### Rationale

This is NOT a design flaw - it's the correct way to handle dynamic defaults in frozen dataclasses. The `# type: ignore` comments acknowledge that MyPy's static analysis can't verify the runtime guarantee provided by `__post_init__`.

## DomainModelProtocol

**Core Principle:** "Protocol-constrained generics enable type-safe backend operations"

SKUEL uses a `DomainModelProtocol` to define the structural contract that all domain models must satisfy, enabling type-safe generic operations in `UniversalNeo4jBackend` and `BaseService`.

### The Problem

```python
# Before: Unconstrained generic
class UniversalNeo4jBackend[T]:
    async def create(self, entity: T) -> Result[T]:
        entity_uid = entity.uid  # ❌ Error: "T" has no attribute "uid"
```

### The Solution

```python
# After: Protocol-constrained generic
class UniversalNeo4jBackend[T: DomainModelProtocol]:
    async def create(self, entity: T) -> Result[T]:
        entity_uid = entity.uid  # ✅ Type-safe!
```

### Protocol Definition

```python
# /core/models/protocols/domain_model_protocol.py
from typing import Protocol, Any
from typing_extensions import Self
from datetime import datetime

class DomainModelProtocol(Protocol):
    """
    Structural protocol for all domain models (Tier 3).

    Required Attributes:
        uid: str - Unique identifier
        created_at: datetime | None - Creation timestamp
        updated_at: datetime | None - Last update timestamp

    Required Methods:
        from_dto: classmethod - Create domain model from DTO
        to_dto: instance method - Convert domain model to DTO
    """

    uid: str
    created_at: datetime | None  # Optional statically, non-None at runtime
    updated_at: datetime | None  # Optional statically, non-None at runtime

    @classmethod
    def from_dto(cls, dto: Any) -> Self:
        ...

    def to_dto(self) -> Any:
        ...
```

### Implementation Pattern

```python
# All domain models automatically satisfy the protocol
@dataclass(frozen=True)
class Task:
    uid: str
    created_at: datetime = None  # type: ignore[assignment]
    updated_at: datetime = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        if self.created_at is None:
            object.__setattr__(self, 'created_at', datetime.now())
        if self.updated_at is None:
            object.__setattr__(self, 'updated_at', datetime.now())

    @classmethod
    def from_dto(cls, dto: TaskDTO) -> Task:
        from core.models.task.task_converters import task_dto_to_pure
        return task_dto_to_pure(dto)

    def to_dto(self) -> TaskDTO:
        from core.models.task.task_converters import task_pure_to_dto
        return task_pure_to_dto(self)
```

### Generic Service Pattern

```python
# Type variables with protocol bounds
B = TypeVar('B', bound=BackendOperations)
T = TypeVar('T', bound=DomainModelProtocol)

class BaseService(ABC, Generic[B, T]):
    """
    Base service with type-safe generic operations.

    Type Parameters:
        B: Backend implementing BackendOperations protocol
        T: Domain model implementing DomainModelProtocol
    """

    def __init__(self, backend: B):
        self.backend = backend

    async def create(self, entity: T) -> Result[T]:
        # Type-safe: MyPy knows entity has uid, created_at, updated_at
        return await self.backend.create(entity)
```

### MyPy Limitation and Workaround

MyPy has a limitation where it cannot verify protocol satisfaction for frozen dataclasses when used as TypeVar bounds in generic classes. The error appears even though the models structurally satisfy the protocol:

```python
class GoalsService(BaseService[GoalsOperations, Goal]):
    # ❌ MyPy error: Type argument "Goal" must be a subtype of "DomainModelProtocol"
    pass
```

However:
```python
g: DomainModelProtocol = Goal(...)  # ✅ This works! Protocol is satisfied
```

**Workaround:**
Suppress `type-var` error code in MyPy config:

```toml
# pyproject.toml
[tool.mypy]
disable_error_code = [
    "type-var",  # MyPy limitation with frozen dataclass + Protocol pattern
]
```

### Benefits

- **Type Safety**: Generic operations are fully type-checked
- **DRY**: No duplicate backend implementations per domain
- **Consistency**: All domain models follow same pattern
- **IntelliSense**: IDE autocomplete works for protocol-constrained generics

### Domain Coverage

As of October 2025:
- ✅ All 7 activity domains (Tasks, Events, Habits, Goals, Choices, Principles, Finance)
- ✅ All 3 curriculum domains (KnowledgeUnit, LearningStep, LearningPath)
- ✅ Journals domain
- ⚠️ **User - Special Case** (see below)
- **Total: ~20 domain models**

## User Entity - Architectural Exception

User is **NOT an activity domain** and does NOT implement DomainModelProtocol. User is the foundation/identity layer that all domains reference.

### Why User is Different

- ❌ No Domain.USER enum value (not in Domain categorization)
- ❌ No DTO conversion lifecycle (from_dto/to_dto)
- ❌ Does NOT use UniversalNeo4jBackend
- ✅ Uses dedicated **UserBackend** for identity operations
- ✅ Created via factory functions (`create_user()`), not DTO conversion
- ✅ Delegates rich state to **UserContext** (mutable, ~240 fields)
- ✅ Similar to Reports (meta-layer, not activity domain)

### Backend Pattern

```python
# Activity Domains - Use UniversalNeo4jBackend (requires DomainModelProtocol)
tasks_backend = UniversalNeo4jBackend[Task](driver, "Task", Task)
goals_backend = UniversalNeo4jBackend[Goal](driver, "Goal", Goal)

# User - Use dedicated UserBackend (identity operations, no DTO lifecycle)
users_backend = UserBackend(driver)
```

### Rationale

User is the identity anchor upon which all activity tracking depends. It has a fundamentally different lifecycle and purpose than activity domains, requiring specialized persistence that focuses on identity management rather than activity CRUD.

## TypedDicts for Service Operations (January 2026)

**Core Principle:** "Type-safe dictionaries replace `dict[str, Any]` at call sites"

SKUEL uses TypedDicts to provide type safety for update payloads and filter specifications passed to service methods. This eliminates typos, provides IDE autocomplete, and catches wrong fields at dev time.

### Location

All TypedDicts are defined in `/core/services/protocols/query_types.py`.

### Update Payload TypedDicts

Domain-specific TypedDicts for update operations:

| TypedDict | Domain | Key Fields |
|-----------|--------|------------|
| `TaskUpdatePayload` | Tasks | `status`, `priority`, `due_date`, `title`, `description` |
| `GoalUpdatePayload` | Goals | `status`, `progress_percentage`, `completion_date`, `milestones` |
| `HabitUpdatePayload` | Habits | `current_streak`, `best_streak`, `last_completed`, `total_completions` |
| `EventUpdatePayload` | Events | `status`, `event_date`, `start_time`, `end_time`, `notes` |
| `ChoiceUpdatePayload` | Choices | `status`, `outcome`, `decision_date`, `confidence` |
| `PrincipleUpdatePayload` | Principles | `status`, `strength`, `is_active` |
| `FinanceUpdatePayload` | Finance | `status`, `amount`, `paid_at`, `receipt_link`, `has_receipt` |
| `AssignmentUpdatePayload` | Assignments | `status`, `processing_started_at`, `processing_completed_at` |
| `KuUpdatePayload` | KU | `status`, `difficulty`, `estimated_hours` |
| `LsUpdatePayload` | LS | `status`, `sequence_number` |
| `LpUpdatePayload` | LP | `progress`, `is_completed` |

### Filter Specification TypedDicts

TypedDicts for query filtering:

| TypedDict | Purpose | Key Fields |
|-----------|---------|------------|
| `BaseFilterSpec` | Common filter fields | `status`, `user_uid`, `sort_by`, `limit`, `offset` |
| `ActivityFilterSpec` | Activity domain filters | Extends `BaseFilterSpec` + `category`, `priority`, `due_date` |
| `CurriculumFilterSpec` | Curriculum domain filters | Extends `BaseFilterSpec` + `domain`, `difficulty` |
| `PrinciplesFilterSpec` | Principles-specific | Extends `BaseFilterSpec` + `strength`, `is_active` |
| `PropertyFilterSpec` | Operator-based filters | `strength__gte`, `confidence__gte`, `score__lte`, etc. |

### Usage Pattern

```python
from core.services.protocols.query_types import (
    GoalUpdatePayload,
    ActivityFilterSpec,
)

# Update operations - IDE autocomplete shows valid fields
async def complete_goal(self, uid: str) -> Result[Goal]:
    updates: GoalUpdatePayload = {
        "status": GoalStatus.ACHIEVED.value,
        "progress_percentage": 100.0,
        "completion_date": date.today(),
    }
    return await self.backend.update(uid, updates)

# Filter operations - type-safe filter construction
def render_list_view(user_uid: str) -> Any:
    filters: ActivityFilterSpec = {"status": "active", "sort_by": "created_at"}
    return ListViewComponent(filters=filters)
```

### Type Flexibility

Update payloads accept both string and native Python types for dates/datetimes:

```python
# Both are valid for GoalUpdatePayload.completion_date
updates: GoalUpdatePayload = {"completion_date": "2026-01-21"}  # str
updates: GoalUpdatePayload = {"completion_date": date.today()}  # date object
```

### Benefits

1. **IDE Autocomplete** - Valid fields shown when typing
2. **Typo Prevention** - Misspelled keys caught by type checker
3. **Documentation** - TypedDict docstrings describe each field
4. **Refactoring Safety** - Field renames caught across codebase

### Inheritance Pattern

All domain-specific payloads inherit from `BaseUpdatePayload`:

```python
class BaseUpdatePayload(TypedDict, total=False):
    """Base fields available on all update payloads."""
    status: str
    title: str
    description: str

class GoalUpdatePayload(BaseUpdatePayload, total=False):
    """Goal-specific fields in addition to base fields."""
    progress_percentage: float
    completion_date: str | date
    milestones: list[Any]
```

The `total=False` makes all fields optional, matching the partial update semantics.

## Key Files

| File | Purpose |
|------|---------|
| `/core/models/protocols/domain_model_protocol.py` | Protocol definition |
| `/adapters/persistence/neo4j/universal_backend.py` | Generic backend |
| `/adapters/persistence/neo4j/user_backend.py` | User backend |
| `/core/services/base_service.py` | Base service |
| `/core/services/protocols/query_types.py` | TypedDict definitions |
| `/scripts/add_frozen_dataclass_type_ignores.py` | Migration script |
| `/core/models/task/task.py` | Example implementation |

## Why Three Tiers? (Design Rationale)

### Tier 1 (Pydantic) - Protection at Boundaries

**Problem solved**: External input can be malformed, causing 500 errors deep in business logic.

**Solution**: Validate at API boundaries BEFORE any service code runs.

**Benefits**:
- Automatic 422 responses with field-level error details
- Self-documenting API contracts
- Type-safe parameter extraction
- No manual JSON parsing

**Example**: Without Pydantic validation, `{"priority": "super-high"}` would cause a crash when converting to Priority enum. With Pydantic, it returns 422 immediately: "Input should be 'low', 'medium', 'high', or 'critical'".

### Tier 2 (DTO) - Flexibility in Services

**Problem solved**: Service operations need to modify data (status updates, computed fields) but domain models should be immutable.

**Solution**: Mutable DTOs allow service-layer modifications without violating immutability principles.

**Benefits**:
- Update fields without creating new instances
- Clean database serialization (to_dict / from_dict)
- Separation from business logic
- Graph-native design (relationships separate from properties)

**Example**: Task completion requires updating 4 fields (status, completion_date, actual_minutes, updated_at). With DTOs, this is simple field assignment. With frozen domain models, you'd need to create a new instance with all fields.

### Tier 3 (Domain) - Business Logic Safety

**Problem solved**: Business logic needs immutability guarantees and semantic correctness.

**Solution**: Frozen dataclasses with business logic methods.

**Benefits**:
- Immutability prevents accidental mutations
- Business logic methods (is_overdue, urgency_score, impact_score)
- Protocol-based type safety (`DomainModelProtocol`)
- Used by intelligence services for calculations

**Example**: `task.urgency_score()` combines priority, due date, and status using domain logic. This logic belongs in the domain model, not spread across services.

### Trade-off: Conversion Boilerplate

**Cost**: Each tier requires converter functions (`request_to_dto`, `dto_to_domain`, `domain_to_dto`).

**Benefit**: Clear separation of concerns - each tier has a single responsibility.

**Mitigation**: Converter functions follow consistent patterns and use shared helpers (`dto_to_dict`, `dto_from_dict`).

## Complete Example: Following a Request

See [DATA_FLOW_WALKTHROUGH.md](/docs/tutorials/DATA_FLOW_WALKTHROUGH.md) for a comprehensive example following a Task creation request through all three tiers, showing:
- Exact code files involved at each stage
- What data looks like at each transformation
- Why each conversion happens
- Where relationships are stored (graph-native design)
- When to skip Tier 3 (Finance/Journals examples)

## See Also

- [DATA_FLOW_WALKTHROUGH.md](/docs/tutorials/DATA_FLOW_WALKTHROUGH.md) - Complete step-by-step example
- [Model Architecture](/docs/architecture/MODEL_ARCHITECTURE.md)
- [Protocol-Based Architecture](#protocol-based-architecture) in CLAUDE.md
- [Unified User Architecture](/docs/architecture/UNIFIED_USER_ARCHITECTURE.md)
