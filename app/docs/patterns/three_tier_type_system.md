---
title: Three-Tier Type System
updated: 2026-02-23
category: patterns
related_skills:
- python
- pydantic
related_docs:
- /docs/patterns/query_architecture.md
- /docs/patterns/API_VALIDATION_PATTERNS.md
---

# Three-Tier Type System

*Last updated: 2026-02-23*

## Quick Start

**Skills:** [@python](../../.claude/skills/python/SKILL.md), [@pydantic](../../.claude/skills/pydantic/SKILL.md)

For hands-on implementation:
1. Invoke `@python` for frozen dataclass patterns (Domain tier)
2. Invoke `@pydantic` for request model validation (External tier)
3. See [DOMAIN_PATTERNS_CATALOG.md](DOMAIN_PATTERNS_CATALOG.md) for complete examples
4. Continue below for architectural context and tier selection guidelines

**Related ADRs:** [ADR-035](../decisions/ADR-035-tier-selection-guidelines.md) - When to use Pattern A vs Pattern B

---

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
     │ (includes infrastructure: embedding, embedding_version, etc.)
     ▼
[Tier 2: DTO]
     │ Reconstitute from database (strings → enums/dates)
     │ ⚠️  Infrastructure fields (embeddings) filtered out
     ▼
[Tier 3: Domain Model]
     │ Apply business logic (is_overdue, urgency_score, etc.)
     ▼
[Tier 1: Pydantic Response]
     │ Combine scalar fields + relationships + computed fields
     ▼
User Client (receives JSON)
```

**Infrastructure Field Filtering (ADR-037):**

Neo4j nodes contain infrastructure fields (`embedding`, `embedding_version`, etc.) that are automatically filtered when converting to DTOs. Embeddings are search infrastructure, not domain data.

**Filtered fields:**
- `embedding` - 1024-dimensional vector for semantic search (provider via `create_embedding_client()` — ADR-068/083)
- `embedding_version` - Embedding model version (e.g., "v3")
- `embedding_model` - Model name
- `embedding_updated_at` - Generation timestamp

**See:** `/docs/decisions/ADR-037-embedding-infrastructure-separation.md`

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

The domain-first architecture (February 2026) uses a class hierarchy for both domain models and DTOs, with each domain extending a shared base.

```python
# Tier 1: Pydantic (External) — domain-specific request models
class TaskCreateRequest(BaseModel):
    title: str
    due_date: Optional[date]

# Tier 2: DTO (Transfer) — per-domain DTO hierarchy
@dataclass
class EntityDTO:
    """~18 common fields (identity, content, status, meta)."""
    uid: str
    title: str
    entity_type: EntityType = field(kw_only=True)  # REQUIRED — no default (see below)
    ...

@dataclass
class UserOwnedDTO(EntityDTO):
    """Adds user_uid, visibility, priority."""
    user_uid: UserUID = ""
    ...

@dataclass
class TaskDTO(UserOwnedDTO):
    """Adds 25 task-specific fields (scheduling, hierarchy, cross-domain links)."""
    due_date: date | None = None
    ...

# Tier 3: Domain Model (Core) — per-domain frozen dataclass hierarchy
@dataclass(frozen=True)
class Entity:
    """~19 common fields. Base for all 25 EntityType domains."""
    uid: str
    title: str
    ...

@dataclass(frozen=True)
class UserOwnedEntity(Entity):
    """Adds user_uid, priority. Base for Activity Domains, Submissions, LifePath."""
    user_uid: UserUID = ""
    ...

@dataclass(frozen=True)
class Task(UserOwnedEntity):
    """25 task-specific fields + business logic methods."""
    due_date: date | None = None
    ...

    def is_overdue(self) -> bool:
        """Business logic lives here"""
        return self.due_date and self.due_date < date.today()
```

### entity_type is required at the base, honest at the leaves (G6)

`EntityDTO.entity_type` has **no default**. It used to default to `EntityType.KU`,
so any service that constructed a DTO without passing it persisted the entity as
`entity_type='ku'` — live Habits/Goals carried the wrong type for months while
the frozen models silently force-corrected on read (systems-review G6, Arc C).
The contract since 2026-07-03:

- **Base + intermediate DTOs** (`EntityDTO`, `UserOwnedDTO`, `CurriculumDTO`)
  require `entity_type` as a keyword argument — MyPy flags any construction
  site that omits it.
- **Leaf DTOs** re-declare an honest default
  (`HabitDTO → EntityType.HABIT`, ...): a leaf default states what the class
  IS; only a base default lies.
- **Tier 3 mirrors this**: every leaf frozen model defaults to its own type and
  `__post_init__` **raises `ValueError` on a mismatch** instead of silently
  correcting it — a wrong persisted type fails loudly at the read boundary.
  (`Entity`/`Curriculum` keep a Ku-flavored default for direct generic
  construction; they are not leaves.)

### Domain Model Hierarchy

```
Entity (~19 fields)
├── UserOwnedEntity(Entity) +2 fields (user_uid, priority)
│   ├── Task, Goal, Habit, Event, Choice, Principle
│   ├── ActivityReport                           (activity feedback — no file fields)
│   ├── UserEntry
│   ├── EntryReport(UserOwnedEntity)
│   └── LifePath
├── Curriculum(Entity) +21 fields → PathStep, LearningPath, Exercise
└── Resource(Entity) +7 fields
```

### DTO Hierarchy (mirrors model hierarchy)

```
EntityDTO (~18 fields)
├── UserOwnedDTO(EntityDTO) +3 fields → TaskDTO, GoalDTO, HabitDTO, EventDTO, ChoiceDTO, PrincipleDTO, LifePathDTO
├── UserOwnedDTO → ActivityReportDTO              (activity feedback — no file fields)
├── UserOwnedDTO -> UserEntryDTO
├── UserOwnedDTO -> EntryReportDTO
├── CurriculumDTO(EntityDTO) → PathStepDTO, LearningPathDTO, ExerciseDTO
└── ResourceDTO(EntityDTO)
```

**KuDTO deleted** (February 2026). All services now use per-domain DTOs exclusively. Cross-domain services (SearchRouter, MEGA-QUERY, analytics) use `ENTITY_TYPE_CLASS_MAP` for generic entity deserialization across all 15 EntityType domains.

## Tier 1: Pydantic Request Models (External)

**Core Principle:** "Pydantic at the edges - validate all external input at API boundaries"

Pydantic request models are **Tier 1 (External)** types used exclusively for API input validation. They prevent 500 errors from malformed data by validating structure, types, and constraints at the API boundary.

### File Organization

Domain models and DTOs live in `core/models/ku/` (the unified model package). Request models live in domain-specific packages:

```
core/models/ku/                    # Domain models (Tier 3) + DTOs (Tier 2)
├── entity.py                      # Entity base (~19 fields)
├── entity_dto.py                  # EntityDTO base (~18 fields)
├── user_owned_entity.py           # UserOwnedEntity (Entity +2 fields)
├── user_owned_dto.py              # UserOwnedDTO (EntityDTO +3 fields)
├── task.py                        # Task(UserOwnedEntity) +25 fields
├── task_dto.py                    # TaskDTO(UserOwnedDTO) +25 fields
├── goal.py / goal_dto.py          # Goal domain
├── habit.py / habit_dto.py        # Habit domain
├── event.py / event_dto.py        # Event domain
├── choice.py / choice_dto.py      # Choice domain
├── principle.py / principle_dto.py # Principle domain
├── life_path.py / life_path_dto.py # LifePath domain
├── user_entry.py / user_entry_dto.py # UserEntry(UserOwnedEntity)
├── activity_report.py / activity_report_dto.py # ActivityReport(UserOwnedEntity) — no file fields
├── entry_report.py / entry_report_dto.py  # EntryReport(UserOwnedEntity)
├── curriculum.py / curriculum_dto.py # Curriculum base
├── path_step.py / path_step_dto.py # PathStep(Curriculum)
├── learning_path.py / learning_path_dto.py # LearningPath(Curriculum)
├── exercise.py / exercise_dto.py  # Exercise(Curriculum)
├── resource.py / resource_dto.py  # Resource(Entity)
└── ku.py                          # Ku union type — retained for cross-domain use

core/models/{domain}/              # Pydantic request models (Tier 1)
├── {domain}_request.py            # Domain-specific request models
```

### Example: Context-Aware Request Models (Dissolved into Domain Files)

```python
# core/models/task/task_request.py
class ContextualTaskCompletionRequest(BaseModel):
    """Request model for completing a task with context awareness."""
    context: dict[str, Any] = Field(default_factory=dict)
    reflection: str = Field(default="", max_length=2000)

# core/models/habit/habit_request.py
class ContextualHabitCompletionRequest(BaseModel):
    """Request model for completing a habit with quality tracking."""
    quality: Literal["poor", "fair", "good", "excellent"] = Field(default="good")
    environmental_factors: dict[str, Any] = Field(default_factory=dict)

# core/models/goal/goal_request.py
class ContextualGoalTaskGenerationRequest(BaseModel):
    """Request model for generating tasks from a goal with context awareness."""
    context_preferences: dict[str, Any] = Field(default_factory=dict)
    auto_create: bool = Field(default=True)
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

**Curriculum Domain** (`core/models/pathways/pathways_request.py`):
- `PathStepCreateRequest`, `LearningPathCreateRequest` (used by ingestion, not CRUD routes)

**Activity Domain Request Models** (domain-specific packages):
- `TaskCreateRequest`, `TaskUpdateRequest` (`core/models/task/task_request.py`)
- `GoalCreateRequest`, `GoalUpdateRequest` (`core/models/goal/goal_request.py`)
- `HabitCreateRequest`, `HabitUpdateRequest` (`core/models/habit/habit_request.py`)
- Plus context-aware models in the same files (e.g., `ContextualTaskCompletionRequest`)

## Frozen Dataclass Dynamic Defaults

**Core Principle:** "Runtime-correct `__post_init__` pattern requires MyPy suppression"

Frozen dataclasses in SKUEL use `__post_init__` to set dynamic defaults for mutable fields (`datetime`, `list`, `dict`). This pattern is **architecturally correct** and works perfectly at runtime, but causes MyPy type errors due to the `None` default values.

### The Pattern

```python
@dataclass(frozen=True)
class Entity:
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

Subclasses (e.g., `Task(UserOwnedEntity)`) call `super().__post_init__()` to chain initialization through the hierarchy.

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
uv run python scripts/add_frozen_dataclass_type_ignores.py
```

### Statistics

As of February 2026:
- 350+ fields across 70+ files use this pattern
- All in `core/models/` (frozen domain models and DTOs)
- Covers `datetime`, `date`, `list`, `dict`, `set` fields
- Includes the full Entity/UserOwnedEntity/domain model hierarchy

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
# Entity base satisfies the protocol; all subclasses inherit it
@dataclass(frozen=True)
class Entity:
    uid: str
    created_at: datetime = None  # type: ignore[assignment]
    updated_at: datetime = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        if self.created_at is None:
            object.__setattr__(self, 'created_at', datetime.now())
        ...

    @classmethod
    def from_dto(cls, dto: "EntityDTO") -> Self:
        return cls._from_dto(dto)

    def to_dto(self) -> "EntityDTO":
        ...

# Per-domain models override from_dto/to_dto to use domain-specific DTOs
@dataclass(frozen=True)
class Task(UserOwnedEntity):
    due_date: date | None = None
    ...

    @classmethod
    def from_dto(cls, dto: "EntityDTO | TaskDTO") -> "Task":
        return cls._from_dto(dto)

    def to_dto(self) -> "TaskDTO":  # type: ignore[override]
        """Convert Task to domain-specific TaskDTO."""
        from core.models.dto_helpers import domain_to_dto
        from core.models.task.task_dto import TaskDTO
        
        return domain_to_dto(self, TaskDTO)
```

**Note:** The `# type: ignore[override]` on `to_dto()` is expected -- child classes return a more specific DTO type (covariant return), which is correct at runtime but requires suppression for MyPy.

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

As of February 2026 (domain-first architecture complete):
- All 6 Activity domains: Task, Goal, Habit, Event, Choice, Principle (extend `UserOwnedEntity`)
- All 3 Curriculum domains: PathStep, LearningPath, Exercise (extend `Curriculum`)
- Resource domain (extends `Entity`)
- Submissions/Journal: UserEntry (extends `UserOwnedEntity`)
- Feedback: ActivityReport (extends `UserOwnedEntity` directly — no file fields)
- LifePath (extends `UserOwnedEntity`)
- Each domain has a corresponding per-domain DTO (e.g., `TaskDTO`, `GoalDTO`)
- Finance: Pattern B (Two-Tier) -- no domain model, DTO only
- **User - Special Case** (see below)
- **Total: 15 domain models + 18 per-domain DTOs**

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
# Domain backends use multi-label CREATE with base_label=NeoLabel.ENTITY
# Creates nodes with dual labels: (n:Entity:Task)
from adapters.persistence.neo4j.neo_label import NeoLabel

tasks_backend = UniversalNeo4jBackend[Task](
    driver, NeoLabel.TASK, Task, base_label=NeoLabel.ENTITY
)
goals_backend = UniversalNeo4jBackend[Goal](
    driver, NeoLabel.GOAL, Goal, base_label=NeoLabel.ENTITY
)

# Non-Ku backends — single label, no base_label
finance_backend = UniversalNeo4jBackend[ExpensePure](
    driver, NeoLabel.EXPENSE, ExpensePure
)

# User - Use dedicated UserBackend (identity operations, no DTO lifecycle)
users_backend = UserBackend(driver)
```

### Rationale

User is the identity anchor upon which all activity tracking depends. It has a fundamentally different lifecycle and purpose than activity domains, requiring specialized persistence that focuses on identity management rather than activity CRUD.

## The typed write boundary — update intents + payloads (ADR-066)

**Core Principle:** "An update carries a type that names exactly what it may change"

A service `update` no longer takes an untyped `dict[str, Any]`. The shared CRUD base
(`CrudOperationsMixin[B, T, U]`) is parameterized over a third type parameter `U` — the
update value — bound by the `SupportsToChanges` protocol (`to_changes() -> dict[str, Any]`)
with a default of `RawChanges`. The base materializes the patch exactly once, at the
`backend.update(uid, updates.to_changes())` seam.

Two flavours of `U` exist, by domain:

### Activity Domains → frozen `*UpdateIntent` dataclasses (ADR-066)

The six Activity Domains (Tasks, Goals, Habits, Events, Choices, Principles) each declare
a frozen `*UpdateIntent` dataclass — **not** a TypedDict. Every updatable column is a field
defaulted to the shared `UNSET` sentinel, so `None` stays a meaningful value (an explicit
clear) and `to_changes()` emits only the fields that were actually set.

| `*UpdateIntent` | Domain | Location |
|-----------------|--------|----------|
| `TaskUpdateIntent` | Tasks | `core/models/task/task_update_intent.py` |
| `GoalUpdateIntent` | Goals | `core/models/goal/goal_update_intent.py` |
| `HabitUpdateIntent` | Habits | `core/models/habit/habit_update_intent.py` |
| `EventUpdateIntent` | Events | `core/models/event/event_update_intent.py` |
| `ChoiceUpdateIntent` | Choices | `core/models/choice/choice_update_intent.py` |
| `PrincipleUpdateIntent` | Principles | `core/models/principle/principle_update_intent.py` |

Each domain's `BaseService` instantiation pins `U` to its intent, e.g.
`BaseService[TasksOperations, Task, TaskUpdateIntent]`. The matching `*UpdateRequest`
(Pydantic edge model) carries a `to_intent()` that builds the intent from
`model_fields_set` — see [ADR-066](../decisions/ADR-066-typed-update-intents.md) and
`docs/roadmap/done/update-intents.md`.

### Non-activity domains → update-payload TypedDicts

Domains with no intent (curriculum, finance, reports) keep TypedDict patches, defined in
`/core/ports/query_types.py`. They flow as `RawChanges` (a `dict` subclass that satisfies
`SupportsToChanges`) through the same base `U`, so no per-domain intent type is required.

| TypedDict | Domain | Key Fields |
|-----------|--------|------------|
| `KuUpdatePayload` | KU (cross-domain) | `complexity`, `domain`, `source_path`, `tags`, `aliases` |
| `PsUpdatePayload` | PS | `order_index`, `estimated_minutes`, `is_optional`, `is_completed` |
| `LpUpdatePayload` | LP | `goal`, `domain`, `estimated_hours`, `progress`, `is_completed` |
| `FinanceUpdatePayload` | Finance | `amount`, `paid_at`, `receipt_link`, `has_receipt`, `category` |
| `ReportUpdatePayload` | Reports | `processing_started_at`, `processing_completed_at`, `file_type` |

All five extend `BaseUpdatePayload` (`title`, `description`, `status`, `updated_at`).

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

**Activity Domain — build the intent, never a dict:**

```python
from core.models.goal import GoalUpdateIntent

# A service-authored transition constructs the intent directly.
async def complete_goal(self, uid: str) -> Result[Goal]:
    intent = GoalUpdateIntent(
        status=EntityStatus.COMPLETED.value,
        completion_date=date.today(),
    )
    return await self.update_goal(uid, intent)  # base materializes intent.to_changes()
```

At the HTTP edge, the `*UpdateRequest` builds the intent via `to_intent()` (only the
fields the client actually sent become non-`UNSET`); the generic `CRUDRouteFactory` does
this for every activity domain (`schema.to_intent()` when the schema is `SupportsToIntent`).

**Non-activity domain — a `RawChanges` patch (or the TypedDict that types it):**

```python
from core.models.update_contracts import RawChanges
from core.ports.query_types import PsUpdatePayload

async def mark_step_complete(self, uid: str) -> Result[PathStep]:
    updates: PsUpdatePayload = {"is_completed": True, "completed_at": "2026-06-05T10:00:00Z"}
    return await self.update(uid, RawChanges(updates))
```

**Filter operations — type-safe filter construction:**

```python
from core.ports.query_types import ActivityFilterSpec

def render_list_view(user_uid: UserUID) -> Any:
    filters: ActivityFilterSpec = {"status": "active", "sort_by": "created_at"}
    return ListViewComponent(filters=filters)
```

### Why intents, not TypedDicts, for activity updates

A TypedDict patch could not distinguish "field omitted" from "field set to `None`", was
structurally just a `dict` (so the type was advisory, never enforced at the seam), and
left the update contract invisible in the method signature. The frozen `*UpdateIntent`
fixes all three: `UNSET` vs `None` is explicit, the dataclass is the contract a reader
sees, and `to_changes()` is the single materialization point. See
[ADR-066](../decisions/ADR-066-typed-update-intents.md).

### Inheritance Pattern (non-activity payloads)

The remaining update-payload TypedDicts inherit from `BaseUpdatePayload`:

```python
class BaseUpdatePayload(TypedDict, total=False):
    """Base fields available on all update payloads."""
    title: str
    description: str
    status: str
    updated_at: str

class LpUpdatePayload(BaseUpdatePayload, total=False):
    """LearningPath-specific fields in addition to base fields."""
    goal: str
    progress: float
    is_completed: bool
```

The `total=False` makes all fields optional, matching the partial update semantics.

## Key Files

| File | Purpose |
|------|---------|
| `/core/models/ku/entity.py` | Entity base class (~19 fields) |
| `/core/models/ku/user_owned_entity.py` | UserOwnedEntity (+user_uid, priority) |
| `/core/models/ku/entity_dto.py` | EntityDTO base (~18 fields) |
| `/core/models/ku/user_owned_dto.py` | UserOwnedDTO (+user_uid, visibility, priority) |
| `/core/models/ku/task.py` | Task domain model (example per-domain implementation) |
| `/core/models/task/task_dto.py` | TaskDTO (example per-domain DTO) |
| `/core/models/entity_types.py` | Ku union type -- cross-domain entity types |
| `/core/models/protocols/domain_model_protocol.py` | Protocol definition |
| `/core/models/enums/entity_enums.py` | EntityType, EntityStatus enums |
| `/adapters/persistence/neo4j/universal_backend.py` | Generic backend with multi-label support |
| `/core/models/enums/neo_labels.py` | NeoLabel enum (`:Entity` + a label per EntityType + infrastructure node labels) |
| `/adapters/persistence/neo4j/user_backend.py` | User backend |
| `/core/services/base_service.py` | Base service |
| `/core/ports/query_types.py` | TypedDict definitions |
| `/scripts/add_frozen_dataclass_type_ignores.py` | Migration script |

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

> **Exception — Intelligence services do NOT mutate DTOs.** See [Intelligence is the exception](#intelligence-is-the-exception-no-dto-mutation) below. The CRUD/persistence story is mutable-DTO; the intelligence story is functional-return-value.

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

### Intelligence is the Exception (No DTO Mutation)

**Core Principle:** "Intelligence services compute, callers apply."

The mutable-DTO story above describes CRUD/persistence flows. **Intelligence services (knowledge inference, scoring, enrichment) do NOT mutate DTOs.** They return a typed `*InferenceResult` frozen dataclass carrying only the fields they produce; the caller applies the result via `dataclasses.replace()` on the frozen domain model.

This closes the risk ADR-035 flagged when it kept Tier 3 frozen models for complex domains: "Intelligence services would operate on mutable DTOs (risky)". Keeping Tier 3 frozen at the model layer is not enough on its own — the intelligence layer must also stop reaching back to the mutable DTO as a scratch space.

**Pattern:**

```python
# core/models/task/task_inference_result.py
@dataclass(frozen=True)
class TaskInferenceResult:
    """Typed return contract for task inference. Enrichment fields ONLY."""
    knowledge_confidence_scores: dict[str, float] | None = None
    knowledge_inference_metadata: dict[str, Any] | None = None
    learning_opportunities_count: int = 0

    def as_kwargs(self) -> dict[str, Any]:
        return {...}

# Inference signature (no input mutation; pure in-memory inference, so sync)
def enhance_task_dto_with_inference(
    self, task: Task | TaskDTO
) -> Result[TaskInferenceResult]: ...

# Caller pattern (functional application)
inference_result = self.ku_inference_service.enhance_task_dto_with_inference(task_draft)
if inference_result.is_error:
    return Result.fail(inference_result)
enrichment = inference_result.value
if enrichment is not None:
    task_draft = dataclasses.replace(task_draft, **enrichment.as_kwargs())
```

**Why a per-domain `*InferenceResult` (not a fresh full DTO):**

- The contract becomes visible in the type. A reader sees `Result[TaskInferenceResult]` and knows exactly which fields inference is allowed to produce — no need to read the body.
- Callers cannot accidentally pick up unrelated fields the inference layer defaulted (status, priority, etc.) — those are not on the result.
- New domains following the same template (Goals, Habits, Events, Choices, Principles when they grow inference services) get the discipline by construction — each defines its own `{Domain}InferenceResult`.

**Scope:** This applies to intelligence/inference services that *compute enrichment* from input content. CRUD service methods that update domain entities (`task.complete()`, `goal.update_progress()`) still go through the mutable-DTO path — they're translating user-initiated changes to persistence, not computing fresh data.

**See:** [ADR-065](../decisions/ADR-065-functional-inference-contract.md) — full context, alternatives, and the dormant-code cleanup that shipped with it.

### Trade-off: Conversion Boilerplate

**Cost**: Each tier requires converter functions (`request_to_dto`, `dto_to_domain`, `domain_to_dto`).

**Benefit**: Clear separation of concerns - each tier has a single responsibility.

**Mitigation**: The domain-first hierarchy reduces boilerplate:
- `to_dict()` chains via `super()` -- EntityDTO serializes 18 fields, UserOwnedDTO adds 3, TaskDTO adds 25
- `from_dict()` uses `dto_from_dict()` generic helper that filters data to only fields on the dataclass
- `to_dto()` / `from_dto()` methods on domain models utilize the `domain_to_dto()` generic helper. This eliminates repetitive field mapping, automatically handles deep immutability unwrapping (like `MappingProxyType`), and enforces structural integrity.

## Complete Example: Following a Request

See [DATA_FLOW_WALKTHROUGH.md](/docs/tutorials/DATA_FLOW_WALKTHROUGH.md) for a comprehensive example following a Task creation request through all three tiers, showing:
- Exact code files involved at each stage
- What data looks like at each transformation
- Why each conversion happens
- Where relationships are stored (graph-native design)
- When to skip Tier 3 (Finance/Journals examples)

## Pattern Selection (Two Patterns)

SKUEL uses two approved patterns: **Domain-First (Pattern A)** for most domains, **Two-Tier (Pattern B)** for simple bookkeeping.

| Pattern | Files | Tiers | Use For | Domains |
|---------|-------|-------|---------|---------|
| **Domain-First** | Per-domain model + per-domain DTO | Pydantic -> DTO -> Entity hierarchy | All 15 EntityType domains | Tasks, Goals, Habits, Events, Choices, Principles, KU, PS, LP, Reports, LifePath |
| **B: Two-Tier** | 2 | Pydantic -> DTO | Simple CRUD, minimal logic | Finance (1 domain) |

**Decision Matrix:**
```
Does the domain have 3+ business logic methods?
+-- YES -> Pattern A (Domain-First)  [Default]
+-- NO  -> Is domain admin-only bookkeeping?
    +-- YES -> Pattern B (Two-Tier)   [Exception]
    +-- NO  -> Pattern A (Domain-First) [Default]
```

**Key enum renames (February 2026):**
- `KuType` -> `EntityType` (15 values)
- `KuStatus` -> `EntityStatus` (14 values)
- `ku_enums.py` was deleted and split into 8 domain-specific enum files (Feb 2026); EntityType/EntityStatus live in `entity_enums.py`
- `ku_type` field and Neo4j property renamed to `entity_type` (March 2026); `parent_ku_uid` renamed to `parent_entity_uid`

**See:** [ADR-035](../decisions/ADR-035-tier-selection-guidelines.md), [ADR-041](../decisions/ADR-041-unified-ku-model.md)

## See Also

- [DATA_FLOW_WALKTHROUGH.md](/docs/tutorials/DATA_FLOW_WALKTHROUGH.md) - Complete step-by-step example
- [Model Architecture](/docs/architecture/MODEL_ARCHITECTURE.md) - Class hierarchy, directory layout, three-tier flow
- [Enum Architecture](/docs/architecture/ENUM_ARCHITECTURE.md) - Enum landscape and dynamic patterns
- [Protocol-Based Architecture](#protocol-based-architecture) in CLAUDE.md
- [Unified User Architecture](/docs/architecture/UNIFIED_USER_ARCHITECTURE.md)
- [DOMAIN_PATTERNS_CATALOG.md](DOMAIN_PATTERNS_CATALOG.md) - Complete per-domain examples
