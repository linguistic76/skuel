---
title: Domain Patterns Catalog
updated: 2026-01-29
category: patterns
related_skills:
- python
- pydantic
related_docs:
- /docs/patterns/three_tier_type_system.md
- /docs/decisions/ADR-035-tier-selection-guidelines.md
---

# Domain Patterns Catalog

*Last updated: 2026-01-29*

## Overview

SKUEL uses **two approved patterns** for domain implementation. This catalog documents both patterns with complete examples, data flows, and decision guidance.

**See also**:
- [ADR-035](/docs/decisions/ADR-035-tier-selection-guidelines.md) - Why we have two patterns
- [Three-Tier Type System](/docs/patterns/three_tier_type_system.md) - Tier definitions
- [DATA_FLOW_WALKTHROUGH](/docs/tutorials/DATA_FLOW_WALKTHROUGH.md) - Complete example

---

## Pattern Selection Quick Reference

```
┌─────────────────────────────────────────┐
│ Choosing a Pattern for New Domain       │
└─────────────────────────────────────────┘

Does the domain have 3+ business logic methods?
├─ YES → Pattern A (Three-Tier) ✅
└─ NO  → Continue...
         │
         └─ Is immutability semantically important?
            ├─ YES → Pattern A (Three-Tier) ✅
            └─ NO  → Continue...
                     │
                     └─ Is domain admin-only bookkeeping?
                        ├─ YES → Pattern B (Two-Tier) ✅
                        └─ NO  → Pattern A (default) ✅
```

**Rule of thumb**: Default to Pattern A unless the domain is genuinely simple (pure CRUD, no logic).

---

## Pattern A: Full Three-Tier (Default)

### When to Use

✅ **Use Pattern A when**:
- Domain has business logic methods (is_overdue, calculate_score, etc.)
- Immutability is semantically important
- Used by generic services requiring `DomainModelProtocol`
- Complex state transitions (draft→scheduled→in_progress→completed)
- Computed fields needed (urgency_score, impact_score, progress_percentage)
- User-owned or shared content (not admin-only)

### Architecture

```
┌──────────────────┐
│  User Client     │
└────────┬─────────┘
         │ HTTP POST + JSON
         ▼
┌──────────────────────────────────┐
│ TIER 1: Pydantic Request Model   │
│ - Validates JSON structure       │
│ - Validates types & constraints  │
│ - Returns 422 on failure         │
└────────┬─────────────────────────┘
         │ Validated data
         ▼
┌──────────────────────────────────┐
│ TIER 2: DTO (Mutable)             │
│ - Generate UID                    │
│ - Set timestamps                  │
│ - Service layer operations        │
│ - Database serialization          │
└────────┬─────────────────────────┘
         │ DTO + Relationships
         ▼
┌──────────────────────────────────┐
│ NEO4J DATABASE                    │
│ - Store node properties           │
│ - Create relationship edges       │
└────────┬─────────────────────────┘
         │ Read request
         ▼
┌──────────────────────────────────┐
│ TIER 2: DTO (Reconstituted)      │
│ - from_dict(neo4j_record)         │
│ - Convert strings → enums/dates   │
└────────┬─────────────────────────┘
         │
         ▼
┌──────────────────────────────────┐
│ TIER 3: Domain Model (Frozen)    │
│ - Immutable business entity       │
│ - Business logic methods          │
│ - is_overdue(), urgency_score()   │
└────────┬─────────────────────────┘
         │
         ▼
┌──────────────────────────────────┐
│ TIER 1: Pydantic Response Model  │
│ - Scalar fields from DTO          │
│ - Relationships from graph        │
│ - Computed fields from Domain     │
└────────┬─────────────────────────┘
         │ JSON response
         ▼
┌──────────────────┐
│  User Client     │
└──────────────────┘
```

### File Structure

```
core/models/{domain}/
├── {domain}.py                # Tier 3: Frozen domain model
├── {domain}_dto.py            # Tier 2: Mutable DTO
├── {domain}_request.py        # Tier 1: Pydantic request/response
├── {domain}_converters.py     # Tier transitions
└── {domain}_relationships.py  # Graph-native relationships
```

### Complete Example: Tasks Domain

#### Tier 1: Pydantic Request (External Boundary)

```python
# core/models/task/task_request.py

from datetime import date
from pydantic import Field

from core.models.request_base import CreateRequestBase
from core.models.shared_enums import ActivityStatus, Priority

class TaskCreateRequest(CreateRequestBase):
    """External API request for creating a task."""

    title: str = Field(min_length=1, max_length=200, description="Task title")
    description: str | None = Field(None, description="Detailed description")

    # Scheduling
    due_date: date | None = Field(None, description="Due date")
    scheduled_date: date | None = Field(None, description="Scheduled work date")
    duration_minutes: int = Field(default=30, ge=5, le=480, description="Estimated duration")

    # Priority and status
    priority: Priority = Field(default=Priority.MEDIUM, description="Task priority")
    status: ActivityStatus = Field(default=ActivityStatus.DRAFT, description="Initial status")

    # Organization
    tags: list[str] = Field(default_factory=list, description="Task tags")

    # Learning Integration
    applies_knowledge_uids: list[str] = Field(
        default_factory=list, description="Knowledge being applied"
    )
    prerequisite_knowledge_uids: list[str] = Field(
        default_factory=list, description="Required knowledge"
    )

    # Pydantic validators
    _validate_dates = validate_future_date("due_date", "scheduled_date")
```

**What it does**:
- Validates JSON structure and types
- Ensures `title` is 1-200 chars
- Ensures `duration_minutes` is 5-480
- Ensures `priority` is valid enum value
- Returns 422 with field errors if validation fails

#### Tier 2: DTO (Service Layer - Mutable)

```python
# core/models/task/task_dto.py

from dataclasses import dataclass, field
from datetime import date, datetime

from core.models.shared_enums import ActivityStatus, Priority

@dataclass
class TaskDTO:
    """
    Mutable data transfer object for tasks - PROPERTIES ONLY.

    Graph-native design: Relationship lists stored as Neo4j edges,
    accessed via TaskRelationships.fetch().
    """

    # Identity
    uid: str
    user_uid: str
    title: str
    description: str | None = None

    # Scheduling
    due_date: date | None = None
    scheduled_date: date | None = None
    completion_date: date | None = None

    # Time tracking
    duration_minutes: int = 30
    actual_minutes: int | None = None

    # Status and priority
    status: ActivityStatus = ActivityStatus.DRAFT
    priority: Priority = Priority.MEDIUM

    # Organization
    tags: list[str] = field(default_factory=list)

    # Single UID fields (stored as properties)
    fulfills_goal_uid: str | None = None
    reinforces_habit_uid: str | None = None

    # Metadata
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def create(
        cls,
        user_uid: str,
        title: str,
        priority: Priority = Priority.MEDIUM,
        due_date: date | None = None,
        duration_minutes: int = 30,
        tags: list[str] | None = None,
    ) -> "TaskDTO":
        """Factory method to create new TaskDTO with generated UID."""
        return cls(
            uid=f"task.{uuid.uuid4()}",  # Generate unique ID
            user_uid=user_uid,
            title=title,
            priority=priority,
            due_date=due_date,
            duration_minutes=duration_minutes,
            tags=tags or [],
            status=ActivityStatus.DRAFT,
            created_at=datetime.now(),
            updated_at=datetime.now(),
        )

    def complete(self, actual_minutes: int | None = None) -> None:
        """Mark task as completed (mutation allowed)."""
        self.status = ActivityStatus.COMPLETED
        self.completion_date = date.today()
        if actual_minutes:
            self.actual_minutes = actual_minutes
        self.updated_at = datetime.now()

    def to_dict(self) -> dict:
        """Convert to dictionary for database operations."""
        return {
            "uid": self.uid,
            "user_uid": self.user_uid,
            "title": self.title,
            "description": self.description,
            "due_date": self.due_date.isoformat() if self.due_date else None,
            "priority": self.priority.value,  # Enum → string
            "status": self.status.value,      # Enum → string
            "duration_minutes": self.duration_minutes,
            "tags": self.tags,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            # ... other fields
        }

    @classmethod
    def from_dict(cls, data: dict) -> "TaskDTO":
        """Create DTO from dictionary (Neo4j record)."""
        return cls(
            uid=data["uid"],
            user_uid=data["user_uid"],
            title=data["title"],
            description=data.get("description"),
            due_date=date.fromisoformat(data["due_date"]) if data.get("due_date") else None,
            priority=Priority(data["priority"]),  # String → enum
            status=ActivityStatus(data["status"]),  # String → enum
            duration_minutes=data.get("duration_minutes", 30),
            tags=data.get("tags", []),
            created_at=datetime.fromisoformat(data["created_at"]),
            updated_at=datetime.fromisoformat(data["updated_at"]),
            # ... other fields
        )
```

**What it does**:
- Provides mutability for service operations
- Generates UIDs and timestamps
- Serializes to/from Neo4j (to_dict / from_dict)
- No business logic - pure data transfer

#### Tier 3: Domain Model (Business Logic - Frozen)

```python
# core/models/task/task.py

from dataclasses import dataclass
from datetime import date, datetime

from core.models.shared_enums import ActivityStatus, Priority

@dataclass(frozen=True)
class Task:
    """
    Immutable domain model representing a task.

    Contains all business logic and rules for task management.
    """

    # Identity
    uid: str
    user_uid: str
    title: str
    description: str | None = None

    # Scheduling
    due_date: date | None = None
    scheduled_date: date | None = None
    completion_date: date | None = None

    # Status and priority
    status: ActivityStatus = ActivityStatus.DRAFT
    priority: Priority = Priority.MEDIUM

    # Metadata
    created_at: datetime = None  # type: ignore[assignment]
    updated_at: datetime = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        """Set defaults for datetime fields."""
        if self.created_at is None:
            object.__setattr__(self, "created_at", datetime.now())
        if self.updated_at is None:
            object.__setattr__(self, "updated_at", datetime.now())

    # ==========================================================================
    # BUSINESS LOGIC METHODS
    # ==========================================================================

    def is_overdue(self) -> bool:
        """Check if task is overdue."""
        if not self.due_date or self.status in [ActivityStatus.COMPLETED, ActivityStatus.CANCELLED]:
            return False
        return date.today() > self.due_date

    def days_until_due(self) -> int | None:
        """Calculate days until due date."""
        if not self.due_date:
            return None
        delta = self.due_date - date.today()
        return delta.days

    def is_due_soon(self, days: int = 3) -> bool:
        """Check if task is due within specified days."""
        days_left = self.days_until_due()
        if days_left is None:
            return False
        return 0 <= days_left <= days

    def urgency_score(self) -> int:
        """
        Calculate urgency score (0-10).

        Factors:
        - Priority (0-4 points)
        - Days until due (0-3 points)
        - Overdue (3 points)
        """
        score = 0

        # Priority score
        priority_scores = {
            Priority.LOW: 1,
            Priority.MEDIUM: 2,
            Priority.HIGH: 3,
            Priority.CRITICAL: 4,
        }
        score += priority_scores.get(self.priority, 0)

        # Due date score
        if self.is_overdue():
            score += 3
        elif self.is_due_soon(days=3):
            score += 2
        elif self.is_due_soon(days=7):
            score += 1

        return min(score, 10)

    def progress_percentage(self) -> float:
        """
        Calculate progress percentage.

        - Draft: 0%
        - Scheduled: 10%
        - In Progress: 50%
        - Completed: 100%
        """
        progress_map = {
            ActivityStatus.DRAFT: 0.0,
            ActivityStatus.SCHEDULED: 10.0,
            ActivityStatus.IN_PROGRESS: 50.0,
            ActivityStatus.COMPLETED: 100.0,
            ActivityStatus.CANCELLED: 0.0,
        }
        return progress_map.get(self.status, 0.0)

    def impact_score(self) -> float:
        """
        Calculate overall impact of completing this task.

        Combines urgency, learning alignment, and progress contribution.
        """
        urgency = self.urgency_score() / 10.0  # Normalize to 0-1
        # ... more complex calculation
        return urgency * 0.4  # Simplified for example

    # ==========================================================================
    # FACTORY METHODS
    # ==========================================================================

    @classmethod
    def from_dto(cls, dto: TaskDTO) -> "Task":
        """Create immutable Task from mutable DTO."""
        return cls(
            uid=dto.uid,
            user_uid=dto.user_uid,
            title=dto.title,
            description=dto.description,
            due_date=dto.due_date,
            scheduled_date=dto.scheduled_date,
            completion_date=dto.completion_date,
            status=dto.status,
            priority=dto.priority,
            created_at=dto.created_at,
            updated_at=dto.updated_at,
        )

    def to_dto(self) -> TaskDTO:
        """Convert to mutable DTO."""
        return TaskDTO(
            uid=self.uid,
            user_uid=self.user_uid,
            title=self.title,
            description=self.description,
            due_date=self.due_date,
            scheduled_date=self.scheduled_date,
            completion_date=self.completion_date,
            status=self.status,
            priority=self.priority,
            created_at=self.created_at,
            updated_at=self.updated_at,
        )
```

**What it does**:
- Provides immutable business entity (frozen=True)
- Implements business logic methods
- Used by intelligence services for calculations
- Satisfies `DomainModelProtocol` for generic services

#### Converters (Tier Transitions)

```python
# core/models/task/task_converters.py

def task_create_request_to_dto(
    request: TaskCreateRequest,
    user_uid: str,
) -> TaskDTO:
    """Convert Pydantic request → DTO (Tier 1 → Tier 2)."""
    return TaskDTO.create(
        user_uid=user_uid,
        title=request.title,
        description=request.description,
        due_date=request.due_date,
        priority=request.priority,
        duration_minutes=request.duration_minutes,
        tags=request.tags,
    )

def task_dto_to_pure(dto: TaskDTO) -> Task:
    """Convert DTO → Domain (Tier 2 → Tier 3)."""
    return Task.from_dto(dto)

def task_pure_to_dto(task: Task) -> TaskDTO:
    """Convert Domain → DTO (Tier 3 → Tier 2)."""
    return task.to_dto()
```

### Pros & Cons

**Pros**:
- ✅ Clear separation of concerns (validation, transfer, logic)
- ✅ Immutability guarantees prevent accidental mutations
- ✅ Business logic centralized in domain model
- ✅ Type-safe via `DomainModelProtocol`
- ✅ Easy to test (business logic isolated)

**Cons**:
- ⚠️ More boilerplate (3 files per domain + converters)
- ⚠️ Conversion overhead (Pydantic→DTO→Domain→DTO→Pydantic)
- ⚠️ Steeper learning curve for new developers

### Current Implementations

**Pattern A domains (12)**:
1. Tasks ✅
2. Goals ✅
3. Habits ✅
4. Events ✅
5. Choices ✅
6. Principles ✅
7. KU (Knowledge Units) ✅
8. LS (Learning Steps) ✅
9. LP (Learning Paths) ✅
10. Assignments ✅
11. User ✅
12. LifePath ✅

---

## Pattern B: Simplified Two-Tier (Exception)

### When to Use

✅ **Use Pattern B when**:
- Domain is admin-only bookkeeping (Finance)
- Simple content storage (Journals)
- Minimal or no business logic (<3 methods)
- No immutability requirements
- Not used by generic protocol-based services
- Simple state (no complex transitions)

⚠️ **Warning**: Use sparingly. Most domains should use Pattern A.

### Architecture

```
┌──────────────────┐
│  User Client     │
└────────┬─────────┘
         │ HTTP POST + JSON
         ▼
┌──────────────────────────────────┐
│ TIER 1: Pydantic Request Model   │
│ - Validates JSON structure       │
│ - Returns 422 on failure         │
└────────┬─────────────────────────┘
         │ Validated data
         ▼
┌──────────────────────────────────┐
│ TIER 2: DTO (Mutable)             │
│ - Generate UID, set timestamps    │
│ - Service layer operations        │
│ - Database serialization          │
│ - Simple mutations only           │
└────────┬─────────────────────────┘
         │ DTO directly
         ▼
┌──────────────────────────────────┐
│ NEO4J DATABASE                    │
│ - Store node properties           │
└────────┬─────────────────────────┘
         │ Read request
         ▼
┌──────────────────────────────────┐
│ TIER 2: DTO (Reconstituted)      │
│ - from_dict(neo4j_record)         │
└────────┬─────────────────────────┘
         │
         ▼
┌──────────────────────────────────┐
│ TIER 1: Pydantic Response Model  │
│ - Fields from DTO directly        │
│ - No computed fields              │
└────────┬─────────────────────────┘
         │ JSON response
         ▼
┌──────────────────┐
│  User Client     │
└──────────────────┘
```

**Key difference**: No Tier 3 (Domain Model). DTO used directly for all operations.

### File Structure

```
core/models/{domain}/
├── {domain}_dto.py         # Tier 2: Mutable DTO (used directly)
└── {domain}_request.py     # Tier 1: Pydantic request/response
```

**Notice**: No `{domain}.py` domain model file.

### Complete Example: Finance Domain

#### Tier 1: Pydantic Request

```python
# core/models/finance/finance_request.py

from datetime import date
from pydantic import Field

from core.models.request_base import CreateRequestBase

class ExpenseCreateRequest(CreateRequestBase):
    """External API request for creating an expense."""

    amount: float = Field(gt=0, description="Expense amount")
    category: str = Field(min_length=1, description="Expense category")
    description: str | None = Field(None, description="Expense description")
    paid_at: date = Field(default_factory=date.today, description="Payment date")
```

**What it does**:
- Validates amount > 0
- Validates category not empty
- Returns 422 on validation failure

#### Tier 2: DTO (Used Directly - No Domain Model)

```python
# core/models/finance/expense_dto.py

from dataclasses import dataclass, field
from datetime import date, datetime

@dataclass
class ExpenseDTO:
    """
    DTO for expenses - used directly (no separate domain model).

    Simple bookkeeping domain with minimal logic.
    """

    # Identity
    uid: str
    user_uid: str

    # Finance data
    amount: float
    category: str
    description: str | None = None
    paid_at: date = field(default_factory=date.today)
    status: str = "unpaid"

    # Metadata
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)

    @classmethod
    def create(
        cls,
        user_uid: str,
        amount: float,
        category: str,
        description: str | None = None,
    ) -> "ExpenseDTO":
        """Factory method to create new ExpenseDTO with generated UID."""
        return cls(
            uid=f"expense.{uuid.uuid4()}",
            user_uid=user_uid,
            amount=amount,
            category=category,
            description=description,
            paid_at=date.today(),
            status="unpaid",
            created_at=datetime.now(),
            updated_at=datetime.now(),
        )

    def mark_paid(self) -> None:
        """Simple mutation - mark expense as paid."""
        self.status = "paid"
        self.updated_at = datetime.now()

    def to_dict(self) -> dict:
        """Convert to dictionary for database operations."""
        return {
            "uid": self.uid,
            "user_uid": self.user_uid,
            "amount": self.amount,
            "category": self.category,
            "description": self.description,
            "paid_at": self.paid_at.isoformat(),
            "status": self.status,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: dict) -> "ExpenseDTO":
        """Create DTO from dictionary (Neo4j record)."""
        return cls(
            uid=data["uid"],
            user_uid=data["user_uid"],
            amount=data["amount"],
            category=data["category"],
            description=data.get("description"),
            paid_at=date.fromisoformat(data["paid_at"]),
            status=data.get("status", "unpaid"),
            created_at=datetime.fromisoformat(data["created_at"]),
            updated_at=datetime.fromisoformat(data["updated_at"]),
        )
```

**What it does**:
- Provides mutability for simple operations
- Generates UIDs and timestamps
- Serializes to/from Neo4j
- Simple mutations (mark_paid) directly on DTO
- **No separate domain model** - DTO is sufficient

#### Service Usage (No Domain Model Needed)

```python
# core/services/finance/finance_service.py

class FinanceService:
    """Finance service uses DTO directly."""

    async def create_expense(
        self,
        request: ExpenseCreateRequest,
        user_uid: str,
    ) -> Result[ExpenseDTO]:
        """Create expense (no domain model conversion)."""

        # Pydantic → DTO (no domain model)
        expense_dto = ExpenseDTO.create(
            user_uid=user_uid,
            amount=request.amount,
            category=request.category,
            description=request.description,
        )

        # Persist DTO directly
        result = await self.backend.create(expense_dto)
        return result

    async def mark_paid(self, uid: str) -> Result[ExpenseDTO]:
        """Mark expense as paid (simple mutation on DTO)."""

        # Get DTO
        result = await self.backend.get_by_uid(uid)
        if result.is_error:
            return result

        expense = result.value

        # Mutate DTO directly (no domain model)
        expense.mark_paid()

        # Persist changes
        update_result = await self.backend.update(uid, expense.to_dict())
        return update_result
```

**Key point**: No conversion to domain model. DTO used directly throughout service layer.

### Pros & Cons

**Pros**:
- ✅ Minimal boilerplate (2 files vs 4 files)
- ✅ Faster development for simple domains
- ✅ Less conversion overhead (Pydantic→DTO→Neo4j)
- ✅ Easier to understand (fewer layers)

**Cons**:
- ⚠️ No immutability guarantees
- ⚠️ Business logic lives in DTO (mixing concerns)
- ⚠️ Can't use `DomainModelProtocol` for generics
- ⚠️ Not suitable for complex logic

### Current Implementations

**Pattern B domains (2)**:
1. Finance ✅ (admin-only bookkeeping)
2. Journals ✅ (simple content storage)

---

## Migration Between Patterns

### When to Migrate B → A

**Triggers**:
- Domain gains 3+ business logic methods
- Immutability becomes important
- Need to use generic protocol-based services
- Complex state transitions emerge

**Migration steps**:
1. Create `{domain}.py` with frozen dataclass
2. Move business logic from DTO to domain model
3. Create converter functions (`dto_to_pure`, `pure_to_dto`)
4. Update service to use domain model for logic
5. Keep DTO for persistence only
6. Update tests to test domain model methods

### When to Migrate A → B

**Triggers**:
- Domain business logic removed (< 3 methods remain)
- Immutability no longer needed
- Domain becomes admin-only bookkeeping

**Migration steps**:
1. Move remaining logic from domain model to DTO
2. Delete `{domain}.py` domain model file
3. Delete converter functions
4. Update service to use DTO directly
5. Update tests to test DTO methods

**Warning**: Rare scenario. Most domains gain complexity over time, not lose it.

---

## Comparison Matrix

| Aspect | Pattern A (Three-Tier) | Pattern B (Two-Tier) |
|--------|------------------------|----------------------|
| **Files per domain** | 4-5 (dto, domain, request, converters) | 2 (dto, request) |
| **Business logic location** | Domain model (frozen) | DTO (mutable) |
| **Immutability** | Yes (frozen dataclass) | No (mutable dataclass) |
| **Type safety** | `DomainModelProtocol` | Basic dataclass |
| **Conversion steps** | 5 (Pydantic→DTO→Domain→DTO→Pydantic) | 3 (Pydantic→DTO→Pydantic) |
| **Development speed** | Slower (more boilerplate) | Faster (less code) |
| **Maintenance burden** | Higher (more files) | Lower (fewer files) |
| **Suitable for** | Complex domains | Simple domains |
| **Current usage** | 12 domains | 2 domains |

---

## Best Practices

### General Guidelines

1. **Default to Pattern A** unless domain is genuinely simple
2. **Keep pattern count to 2** (no new patterns without deprecating old)
3. **Document exceptions** - If using Pattern B, explain why in domain README
4. **Monitor complexity** - If Pattern B domain gains logic, migrate to Pattern A
5. **Consistent naming** - All Pattern A domains use same file naming

### Code Organization

**Pattern A domains**:
```
core/models/{domain}/
├── {domain}.py                # Domain model (frozen)
├── {domain}_dto.py            # DTO (mutable)
├── {domain}_request.py        # Pydantic models
├── {domain}_converters.py     # Tier transitions
└── {domain}_relationships.py  # Graph-native (optional)
```

**Pattern B domains**:
```
core/models/{domain}/
├── {domain}_dto.py      # DTO used directly
└── {domain}_request.py  # Pydantic models
```

### Testing Strategy

**Pattern A**:
- Test domain model business logic separately
- Test DTO serialization separately
- Test Pydantic validation separately
- Test conversion round-trips

**Pattern B**:
- Test DTO operations directly
- Test Pydantic validation separately
- No domain model tests (doesn't exist)

---

## Related Documentation

- [ADR-035](/docs/decisions/ADR-035-tier-selection-guidelines.md) - Decision rationale
- [Three-Tier Type System](/docs/patterns/three_tier_type_system.md) - Tier definitions
- [DATA_FLOW_WALKTHROUGH](/docs/tutorials/DATA_FLOW_WALKTHROUGH.md) - Complete example
- [CLAUDE.md](/CLAUDE.md) - Quick reference section
