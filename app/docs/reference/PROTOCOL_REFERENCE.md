---
title: Protocol Reference Guide
updated: 2026-02-15
status: current
category: reference
tags: [protocol, reference]
related: [ADR-025, ADR-027]
---

# Protocol Reference Guide

**Last Updated:** February 8, 2026
**Purpose:** Complete reference for all Protocol interfaces in SKUEL codebase
**Location:** `/core/ports/` (service protocols) and `/core/models/protocols/` (domain model protocols)

---

## Table of Contents

1. [Core Data Protocols](#core-data-protocols)
2. [Pydantic Integration Protocols](#pydantic-integration-protocols)
3. [Backend Capability Protocols](#backend-capability-protocols)
4. [Domain-Specific Protocols](#domain-specific-protocols)
5. [Facade Protocols (January 2026)](#facade-protocols-january-2026)
6. [Route-Facing Service Protocols (February 2026)](#route-facing-service-protocols-february-2026)
7. [Knowledge Carrier Protocols (ADR-027)](#knowledge-carrier-protocols-adr-027)
8. [Context Awareness Protocols](#context-awareness-protocols)
9. [Usage Examples](#usage-examples)

---

## Protocol File Locations

| Category | Location | Purpose |
|----------|----------|---------|
| **Base Protocols** | `/core/ports/base_protocols.py` | Core types, backend operations |
| **Domain Protocols** | `/core/ports/domain_protocols.py` | Domain service operations |
| **Curriculum Protocols** | `/core/ports/curriculum_protocols.py` | KU, LS, LP, MOC operations |
| **Askesis Protocols** | `/core/ports/askesis_protocols.py` | Cross-cutting intelligence + CRUD |
| **Reports Protocols** | `/core/ports/reports_protocols.py` | Submission, sharing, processing, feedback |
| **Group Protocols** | `/core/ports/group_protocols.py` | Group CRUD, teacher review queue |
| **Service Protocols** | `/core/ports/service_protocols.py` | Calendar, Viz, System, LifePath, Auth, Orchestration |
| **Search Protocols** | `/core/ports/search_protocols.py` | Search operations |
| **Infrastructure Protocols** | `/core/ports/infrastructure_protocols.py` | EventBus, Schema, User, Ingestion |
| **Intelligence Protocols** | `/core/ports/intelligence_protocols.py` | Analytics operations |
| **Facade Protocols** | `/core/ports/facade_protocols.py` | Type hints for delegated methods |
| **Context Awareness** | `/core/ports/context_awareness_protocols.py` | UserContext slices (ISP) |
| **Knowledge Carrier** | `/core/models/protocols/knowledge_carrier_protocol.py` | Knowledge integration |

---

## Core Data Protocols

### EnumLike
**Purpose:** Objects with a `.value` attribute (Enum members)

```python
from core.ports import EnumLike

@runtime_checkable
class EnumLike(Protocol):
    value: Any
```

**Usage:**
```python
from core.models.enums import Priority

if isinstance(priority, EnumLike):
    db_value = priority.value  # "high", "medium", "low"
```

**Helper Function:**
```python
from core.ports import get_enum_value

# Handles both enums and plain values
value = get_enum_value(priority)  # Works for Priority.HIGH or "high"
```

---

### HasUID
**Purpose:** Objects with a unique identifier

```python
@runtime_checkable
class HasUID(Protocol):
    uid: str
```

**Usage:**
```python
if isinstance(obj, HasUID):
    print(f"Entity: {obj.uid}")
```

---

### HasToDict
**Purpose:** Objects that can convert to dictionary

```python
@runtime_checkable
class HasToDict(Protocol):
    def to_dict(self) -> dict[str, Any]: ...
```

**Helper Function:**
```python
from core.ports import to_dict

# Universal conversion - tries model_dump(), dict(), to_dict(), serialize()
data = to_dict(any_object)
```

---

## Pydantic Integration Protocols

### PydanticModel
**Purpose:** Pydantic v2 models with model_dump method

```python
@runtime_checkable
class PydanticModel(Protocol):
    def model_dump(self, **kwargs) -> dict[str, Any]: ...
```

---

### PydanticFieldInfo
**Purpose:** Pydantic v2 FieldInfo with metadata list

```python
@runtime_checkable
class PydanticFieldInfo(Protocol):
    description: str | None
    metadata: list[Any]  # List of constraint objects (annotated_types)
```

**Usage:**
```python
from pydantic import BaseModel

class MyModel(BaseModel):
    name: str = Field(description="User name")

field_info = MyModel.model_fields['name']
if isinstance(field_info, PydanticFieldInfo):
    print(field_info.description)  # "User name"
```

---

### Constraint Protocols (Pydantic v2 / annotated_types)

These protocols represent individual constraint objects from Pydantic's `metadata` list:

#### MinLenConstraint
```python
@runtime_checkable
class MinLenConstraint(Protocol):
    min_length: int
```

#### MaxLenConstraint
```python
@runtime_checkable
class MaxLenConstraint(Protocol):
    max_length: int
```

#### GeConstraint (Greater Than or Equal)
```python
@runtime_checkable
class GeConstraint(Protocol):
    ge: float
```

#### LeConstraint (Less Than or Equal)
```python
@runtime_checkable
class LeConstraint(Protocol):
    le: float
```

#### GtConstraint (Greater Than)
```python
@runtime_checkable
class GtConstraint(Protocol):
    gt: float
```

#### LtConstraint (Less Than)
```python
@runtime_checkable
class LtConstraint(Protocol):
    lt: float
```

**Usage Example:**
```python
from pydantic import BaseModel, Field
from core.ports import PydanticFieldInfo, MinLenConstraint, MaxLenConstraint

class User(BaseModel):
    username: str = Field(min_length=3, max_length=20)

field_info = User.model_fields['username']
if isinstance(field_info, PydanticFieldInfo):
    for constraint in field_info.metadata:
        if isinstance(constraint, MinLenConstraint):
            print(f"Minimum length: {constraint.min_length}")
        if isinstance(constraint, MaxLenConstraint):
            print(f"Maximum length: {constraint.max_length}")
```

---

## Backend Capability Protocols

These protocols define what operations a backend supports. Use `isinstance()` checks instead of `hasattr()`.

### UserContextOperations
**Purpose:** User context cache management for breaking circular dependencies
**Added:** October 14, 2025

```python
class UserContextOperations(Protocol):
    """User context operations for cache invalidation."""
    async def invalidate_context(self, user_uid: str) -> None: ...
```

**Usage:**
```python
from core.ports import UserContextOperations

class TasksService:
    def __init__(
        self,
        backend: TasksOperations,
        context_service: Optional[UserContextOperations] = None
    ):
        self.context_service = context_service

    async def complete_task(self, task_uid: str, user_uid: str):
        # ... task completion logic ...

        # Invalidate cache after state changes
        if self.context_service:
            await self.context_service.invalidate_context(user_uid)
```

**Why This Protocol Exists:**
This protocol breaks circular dependencies between services and UserContextService. Services depend on the protocol interface, not the concrete implementation, eliminating import cycles.

---

### SupportsCount
```python
@runtime_checkable
class SupportsCount(Protocol):
    async def count(self, **filters) -> Any: ...
```

---

### SupportsSearch
```python
@runtime_checkable
class SupportsSearch(Protocol):
    async def search(self, query: str, **filters) -> Any: ...
```

---

### SupportsRelationships
```python
@runtime_checkable
class SupportsRelationships(Protocol):
    async def add_relationship(
        self,
        from_uid: str,
        to_uid: str,
        relationship_type: RelationshipName,
        properties: dict[str, Any] | None = None,
    ) -> Any: ...
    async def get_relationships(self, uid: str, direction: str = "both") -> Any: ...
```

---

### SupportsTraversal
```python
@runtime_checkable
class SupportsTraversal(Protocol):
    async def traverse(self, start_uid: str, rel_pattern: str, max_depth: int = 3) -> Any: ...
```

---

### SupportsPathfinding
```python
@runtime_checkable
class SupportsPathfinding(Protocol):
    async def find_path(self, from_uid: str, to_uid: str, rel_types: list, max_depth: int = 5) -> Any: ...
```

---

### SupportsHealthCheck
```python
@runtime_checkable
class SupportsHealthCheck(Protocol):
    async def health_check(self) -> Any: ...
```

---

## Domain Operations Protocols

**Location:** `/core/ports/domain_protocols.py`
**Purpose:** Service operation interfaces for all 14 domains
**Core Principle:** "Results internally, exceptions at boundaries"

All domain operation protocols use `Result[T]` return types, aligning with SKUEL's error handling pattern. Services implement these protocols and return `Result.ok(value)` or `Result.error(error)`.

### Domain Backend Protocols

| Protocol | Domain | Category |
|----------|--------|----------|
| `TasksOperations` | Tasks | Activity |
| `GoalsOperations` | Goals | Activity |
| `HabitsOperations` | Habits | Activity |
| `EventsOperations` | Events | Activity |
| `ChoicesOperations` | Choices | Activity |
| `PrinciplesOperations` | Principles | Activity |
| `FinanceOperations` | Finance | Finance |
| `KuOperations` | Knowledge Units | Curriculum |
| `LsOperations` | Learning Steps | Curriculum |
| `LpOperations` | Learning Paths | Curriculum |

### Result[T] Return Pattern

```python
# Example: TasksOperations protocol
class TasksOperations(Protocol):
    async def get_task(self, uid: str) -> Result[Task]:
        """Get task by UID - returns Result[Task], not Task directly."""
        ...

    async def create_task(self, task_data: TaskCreateDTO) -> Result[Task]:
        """Create task - returns Result[Task]."""
        ...

    async def update_task(self, uid: str, updates: dict[str, Any]) -> Result[Task]:
        """Update task - returns Result[Task]."""
        ...
```

**Usage:**
```python
from core.ports import TasksOperations

async def process_task(service: TasksOperations, task_uid: str):
    result = await service.get_task(task_uid)

    if result.is_error:
        # Handle error (NotFound, Database, etc.)
        return result.error

    task = result.value
    # Process task...
    return task
```

**See:** `/docs/patterns/ERROR_HANDLING.md` for complete Result[T] pattern documentation.

---

## Domain-Specific Protocols

### HasDomain
```python
@runtime_checkable
class HasDomain(Protocol):
    domain: Any
```

---

### HasPriority
```python
@runtime_checkable
class HasPriority(Protocol):
    def get_priority(self) -> Any: ...
```

---

### HasMetrics
```python
@runtime_checkable
class HasMetrics(Protocol):
    metrics: Any
```

---

### HasStreaks
```python
@runtime_checkable
class HasStreaks(Protocol):
    streaks: Any
```

---

## Facade Protocols (January 2026)

**Location:** `/core/ports/facade_protocols.py`
**Purpose:** Type hints for dynamically delegated facade methods
**See:** ADR-025 (Service Consolidation Patterns)

### Core Principle: "Type hints for delegation, NOT for inheritance"

**CRITICAL:** Facade protocols are for TYPE HINTS only, NEVER use them as base classes.

### Rationale: Why Facade Protocols Exist

Facade services use `FacadeDelegationMixin` to dynamically generate delegation methods at class definition time:

```python
class TasksService(FacadeDelegationMixin):
    _delegate_to = ["core", "search", "intelligence"]

    def __init__(self, core, search, intelligence):
        self.core = core
        self.search = search
        self.intelligence = intelligence

# At class definition, FacadeDelegationMixin creates these methods:
# - self.get_task() -> delegates to self.core.get_task()
# - self.search_tasks() -> delegates to self.search.search_tasks()
# - self.analyze_task() -> delegates to self.intelligence.analyze_task()
```

**The Problem:** MyPy can't see these dynamically-generated methods. Static analysis happens before runtime, so MyPy sees TasksService as having NO methods.

**The Solution:** Facade protocols use structural subtyping (Protocol) to tell MyPy what methods exist at runtime:

```python
@runtime_checkable
class TasksFacadeProtocol(Protocol):
    # Declare ALL delegated methods for MyPy
    async def get_task(self, uid: str) -> Result[Task]: ...
    async def search_tasks(self, query: str) -> Result[list[Task]]: ...
    async def analyze_task(self, uid: str) -> Result[dict]: ...
```

When you use `TasksFacadeProtocol` as a type hint, MyPy enables autocomplete and type checking for all delegated methods.

### Available Facade Protocols (9 Total - January 2026)

**Status:** ✅ **100% Coverage** - All facade services have protocol declarations

| Protocol | Facade Service | Sub-services Covered | Methods |
|----------|----------------|---------------------|---------|
| `TasksFacadeProtocol` | TasksService | core, search, scheduling, planning, intelligence | 45+ |
| `GoalsFacadeProtocol` | GoalsService | core, search, scheduling, intelligence | 40+ |
| `HabitsFacadeProtocol` | HabitsService | core, search, tracking, streaks, intelligence | 38+ |
| `EventsFacadeProtocol` | EventsService | core, search, recurrence, intelligence | 35+ |
| `ChoicesFacadeProtocol` | ChoicesService | core, search, decision analysis, intelligence | 30+ |
| `PrinciplesFacadeProtocol` | PrinciplesService | core, search, alignment, intelligence | 32+ |
| `KuFacadeProtocol` | KuService | core, search, graph, semantic, practice, interaction | 50+ |
| `LpFacadeProtocol` | LpService | core, search, pathfinding, intelligence | 35+ |
| `LsFacadeProtocol` | LsService | core, search, step management | 20+ |

**Note:** MOC uses `KuFacadeProtocol` (MOC is KU-based as of January 2026)

### Usage Pattern: TYPE_CHECKING Guard

**Always use TYPE_CHECKING guard to prevent circular imports:**

```python
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from core.ports.facade_protocols import GoalsFacadeProtocol

async def analyze_goals(goals_service: "GoalsFacadeProtocol") -> dict:
    # MyPy sees the protocol's method declarations
    # IDE provides autocomplete for all delegated methods
    milestones = await goals_service.get_goal_milestones(uid)
    progress = await goals_service.update_goal_progress(uid, 0.5)
    return {"milestones": milestones, "progress": progress}
```

**Why TYPE_CHECKING?**
- The `if TYPE_CHECKING:` block only runs during static analysis (MyPy)
- At runtime, the import is skipped, preventing circular dependency issues
- Use string literal `"GoalsFacadeProtocol"` for the type hint to avoid NameError at runtime

### ⚠️ CRITICAL WARNING: Do NOT Inherit From Facade Protocols

```python
# ❌ WRONG - DO NOT DO THIS
class TasksService(TasksFacadeProtocol, FacadeDelegationMixin):
    # MyPy error: Cannot instantiate abstract class 'TasksService' with abstract methods...
    pass

# ✅ CORRECT - Use as TYPE HINT only
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from core.ports.facade_protocols import TasksFacadeProtocol

def process_tasks(service: "TasksFacadeProtocol"):
    # Type hint for parameter, NOT inheritance
    pass
```

**Why NOT to inherit:**
1. **MyPy expects explicit implementations** - When Protocol is a base class, MyPy expects you to explicitly implement ALL protocol methods
2. **Dynamic methods are invisible to static analysis** - FacadeDelegationMixin creates methods at runtime, but MyPy runs BEFORE runtime
3. **Results in "Cannot instantiate abstract class" errors** - MyPy sees "missing" methods that actually exist at runtime

**Facade protocols are ONLY for parameter type hints, NOT for inheritance.**

---

## Route-Facing Service Protocols (February 2026)

**Purpose:** ISP-compliant protocols for services passed from the `Services` dataclass to route files
**Core Principle:** Each protocol captures ONLY the methods actually called from routes — not the full service API

These protocols replace `Any` types on the `Services` dataclass fields, giving route files type-safe contracts without coupling to concrete implementations.

### Three Protocol Files

| File | Protocols | Route Consumers |
|------|-----------|-----------------|
| `reports_protocols.py` | 9 protocols | `reports_api.py`, `reports_sharing_api.py`, `assignments_api.py`, `reports_progress_api.py`, `reports_assessment_api.py` |
| `group_protocols.py` | 2 protocols | `groups_api.py`, `teaching_api.py` |
| `service_protocols.py` | 10 protocols | `orchestration_routes.py`, `calendar_api.py`, `visualization_api.py`, `system_api.py`, `lifepath_api.py`, `auth_ui.py`, `admin_api.py`, `lateral_routes.py` |

Plus `AskesisCoreOperations` added to existing `askesis_protocols.py`.

### Reports Domain Protocols (9)

| Protocol | Services Field | Methods | Route Consumer |
|----------|---------------|---------|----------------|
| `KuSubmissionOperations` | `reports` | 7 (submit_file, get_ku, list_kus, get_file_content, get_processed_file_content, get_ku_statistics, update_processed_content) | `reports_api.py` |
| `KuContentOperations` | `reports_core` | 17 (get_ku, categorize, tags, publish, archive, draft, bulk ops, create_journal_ku, create_assessment, get_assessments_for_student, get_assessments_by_teacher) | `reports_api.py`, `reports_assessment_api.py` |
| `KuContentSearchOperations` | `reports_query` | 4 (search_kus, get_ku_statistics, get_recent_kus, get_journal_for_ku) | `reports_api.py` |
| `KuSharingOperations` | `reports_sharing` | 6 (share_ku, unshare_ku, get_shared_with_users, get_kus_shared_with_me, set_visibility, check_access) | `reports_api.py` |
| `KuProcessingOperations` | `processing_pipeline` | 2 (process_ku, reprocess_ku) | `reports_api.py` |
| `AssignmentOperations` | `assignments` | 5 (create, get, list, update, delete) | `assignments_api.py` |
| `KuFeedbackOperations` | `report_feedback` | 1 (generate_feedback) | `assignments_api.py` |
| `ProgressKuGeneratorOperations` | `progress_generator` | 1 (generate) | `reports_progress_api.py` |
| `KuScheduleOperations` | `report_schedule` | 4 (create_schedule, get_user_schedule, update_schedule, deactivate_schedule) | `reports_progress_api.py` |

### Group & Teaching Protocols (2)

| Protocol | Services Field | Methods | Route Consumer |
|----------|---------------|---------|----------------|
| `GroupOperations` | `group_service` | 9 (create, get, list_teacher, list_user, update, delete, add/remove member, get_members) | `groups_api.py` |
| `TeacherReviewOperations` | `teacher_review` | 5 (get_review_queue, get_feedback_history, submit_feedback, request_revision, approve_report) | `teaching_api.py` |

### Cross-Cutting Service Protocols (9)

| Protocol | Services Field | Methods | Route Consumer |
|----------|---------------|---------|----------------|
| `CalendarServiceOperations` | `calendar` | 4 async (get_calendar_view, get_item, quick_create, reschedule_item) | `calendar_api.py`, `visualization_api.py` |
| `VisualizationOperations` | `visualization` | 11 (4 async data + 7 sync Chart.js/Vis.js formatters) | `visualization_api.py` |
| `SystemServiceOperations` | `system_service` | 11 (5 async health + 6 sync management) | `system_api.py` |
| `CrossDomainAnalyticsOperations` | `cross_domain_analytics` | 5 async (learning_velocity, spending_patterns, mood, productivity, habit_consistency) | `analytics_api.py` |
| `LifePathOperations` | `lifepath` | 3 async + `.alignment` sub-service | `lifepath_api.py` |
| `GraphAuthOperations` | `graph_auth` | 5 async (sign_up, sign_in, sign_out, reset_password, admin_reset_token) | `auth_ui.py`, `admin_api.py` |
| `GoalTaskGeneratorOperations` | `goal_task_generator` | 1 (generate_tasks_for_goal) | `orchestration_routes.py` |
| `HabitEventSchedulerOperations` | `habit_event_scheduler` | 1 (schedule_events_for_habit) | `orchestration_routes.py` |
| `AskesisCoreOperations` | `askesis_core` | 5 (get_or_create, create, get, update, record_conversation) | `askesis_api.py` |

### Nested Protocol Pattern: LifePathOperations

LifePathService exposes a `.alignment` sub-service. The protocol models this with a nested protocol:

```python
@runtime_checkable
class LifePathAlignmentOperations(Protocol):
    async def calculate_alignment(self, user_uid: str) -> Result[Any]: ...

@runtime_checkable
class LifePathOperations(Protocol):
    alignment: LifePathAlignmentOperations  # Sub-service access

    async def get_full_status(self, user_uid: str) -> Result[dict[str, Any]]: ...
    async def capture_and_recommend(self, user_uid: str, vision_statement: str) -> Result[dict[str, Any]]: ...
    async def designate_and_calculate(self, user_uid: str, life_path_uid: str) -> Result[dict[str, Any]]: ...
```

Routes access it as `lifepath_service.alignment.calculate_alignment(user_uid)`.

### Mixed Async/Sync Pattern: VisualizationOperations

Some services have both async (I/O) and sync (computation) methods called from routes. Both are included in the protocol:

```python
@runtime_checkable
class VisualizationOperations(Protocol):
    # Async — data fetching
    async def get_completion_data(self, user_uid: str, period: str, tasks_service: Any) -> Result[dict]: ...
    async def get_streak_data(self, user_uid: str, habits_service: Any) -> Result[list[dict]]: ...

    # Sync — Chart.js formatting
    def format_completion_chart(self, completed: list[int], total: list[int], labels: list[str], ...) -> Result[dict]: ...
    def format_for_visjs(self, calendar_data: Any, group_by: str = "type") -> Result[dict]: ...
```

### Usage in Route Files

```python
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from core.ports import KuSharingOperations, KuContentOperations

def create_reports_sharing_api_routes(
    _app: Any,
    rt: Any,
    reports_sharing: "KuSharingOperations",
    reports_core: "KuContentOperations",
) -> list[Any]:
    # MyPy verifies .share_ku(), .check_access() etc. exist
    ...
```

### Services Dataclass Wiring

Every field on the `Services` dataclass is typed — zero `Any` fields remain. Two strategies:

```python
# services_bootstrap.py
@dataclass
class Services:
    # Route-facing: ISP protocols (19 fields)
    reports: KuSubmissionOperations | None = None
    calendar: CalendarServiceOperations | None = None
    graph_auth: GraphAuthOperations | None = None

    # Internal: concrete classes via TYPE_CHECKING (~53 fields)
    tasks_intelligence: "TasksIntelligenceService | None" = None
    lateral: "LateralRelationshipOperations | None" = None  # Protocol-typed (Feb 2026)
    neo4j_driver: "AsyncDriver | None" = None
```

---

## Knowledge Carrier Protocols (ADR-027)

**Location:** `/core/models/protocols/knowledge_carrier_protocol.py`
**Purpose:** Unified knowledge integration across all 10 domains
**See:** ADR-027 (Knowledge Carrier Protocol)

### KnowledgeCarrier (Base Protocol)

All 10 SKUEL domains implement this protocol, enabling unified knowledge operations.

```python
@runtime_checkable
class KnowledgeCarrier(Protocol):
    """Base protocol for any entity that carries knowledge context."""

    uid: str

    def knowledge_relevance(self) -> float:
        """How relevant is knowledge to this entity? (0.0-1.0)"""
        ...

    def get_knowledge_uids(self) -> tuple[str, ...]:
        """Get all knowledge UIDs this entity carries or references."""
        ...
```

**Implementing Domains:**

| Domain Type | Domains | knowledge_relevance() |
|-------------|---------|----------------------|
| **Curriculum** | KU, LS, LP, MOC | Always 1.0 (ARE knowledge) |
| **Activity** | Task, Event, Habit, Goal, Choice, Principle | 0.0-1.0 (CARRY knowledge) |

**Usage:**
```python
from core.models.protocols import KnowledgeCarrier

def process_knowledge(entity: KnowledgeCarrier) -> float:
    if entity.knowledge_relevance() > 0.5:
        knowledge_uids = entity.get_knowledge_uids()
        # Process high-relevance knowledge carrier
    return entity.knowledge_relevance()
```

---

### SubstantiatedKnowledge (Extended Protocol)

For entities that track how well knowledge is LIVED, not just learned.

```python
@runtime_checkable
class SubstantiatedKnowledge(KnowledgeCarrier, Protocol):
    """Extended protocol for entities that track knowledge substantiation."""

    def substance_score(self) -> float:
        """Calculate how well knowledge is applied in real life (0.0-1.0)."""
        ...
```

**Substance Scale:**
- 0.0-0.2: Pure theory (read about it)
- 0.3-0.5: Applied knowledge (tried it)
- 0.6-0.7: Well-practiced (regular use)
- 0.8-1.0: Lifestyle-integrated (embodied)

**Implemented by:** KU, LS, LP, MOC (curriculum domains only)

---

### CurriculumCarrier (Curriculum Protocol)

```python
@runtime_checkable
class CurriculumCarrier(KnowledgeCarrier, Protocol):
    """Protocol for curriculum entities (KU, LS, LP, MOC)."""

    domain: Domain  # Subject categorization (TECH, HEALTH, etc.)
```

---

### ActivityCarrier (Activity Protocol)

```python
@runtime_checkable
class ActivityCarrier(KnowledgeCarrier, Protocol):
    """Protocol for activity entities (Task, Event, Habit, Goal, Choice, Principle)."""

    user_uid: str
    source_learning_step_uid: str | None

    def learning_impact_score(self) -> float:
        """Calculate learning impact when this activity completes."""
        ...
```

---

## Context Awareness Protocols

**Location:** `/core/ports/context_awareness_protocols.py`
**Purpose:** ISP-compliant slices of UserContext (~240 fields → focused protocols)
**Status:** Designed and tested, available for service adoption

### Philosophy

UserContext has ~240 fields, but most services only need 5-10. These protocols let services declare explicit dependencies:

```python
# Before: unclear what's actually needed
async def get_ready_to_learn(self, context: UserContext) -> ...:

# After: explicit dependency
async def get_ready_to_learn(self, context: KnowledgeAwareness) -> ...:
```

### Available Protocols

| Protocol | Fields | Use Case |
|----------|--------|----------|
| **CoreIdentity** | user_uid, username | Every service needs this |
| **TaskAwareness** | active/blocked/overdue tasks, priorities | Task tracking services |
| **KnowledgeAwareness** | mastery levels, prerequisites | Learning services |
| **HabitAwareness** | streaks, at-risk habits | Habit tracking services |
| **GoalAwareness** | progress, milestones | Goal services |
| **EventAwareness** | upcoming, scheduled events | Calendar services |
| **PrincipleAwareness** | core principles | Value alignment services |
| **ChoiceAwareness** | pending choices | Decision services |
| **LearningPathAwareness** | enrolled paths, current steps | Curriculum services |
| **CrossDomainAwareness** | Multi-domain subset | Cross-domain analysis |
| **FullAwareness** | All fields | Dashboards, Askesis (use sparingly) |

**Usage:**
```python
from core.ports import TaskAwareness, KnowledgeAwareness

async def analyze_blocked_tasks(ctx: TaskAwareness) -> int:
    return len(ctx.blocked_task_uids)

async def get_average_mastery(ctx: KnowledgeAwareness) -> float:
    if not ctx.knowledge_mastery:
        return 0.0
    return sum(ctx.knowledge_mastery.values()) / len(ctx.knowledge_mastery)
```

UserContext implements ALL these protocols, so you can still pass it anywhere.

---

## Usage Examples

### Example 1: Enum Value Extraction

```python
# WRONG - using hasattr()
from core.models.enums import Priority

task_priority = Priority.HIGH
priority_str = task_priority.value if hasattr(task_priority, 'value') else "medium"

# RIGHT - using get_enum_value()
from core.ports import get_enum_value

priority_str = get_enum_value(task_priority)  # "high"
```

---

### Example 2: Backend Capability Checking

```python
# WRONG - using hasattr()
if hasattr(backend, 'count'):
    total = await backend.count()
else:
    total = 0

# RIGHT - using isinstance() with Protocol
from core.ports import SupportsCount

if isinstance(backend, SupportsCount):
    total = await backend.count()
else:
    raise ValueError("Backend does not support count operations")

# BETTER - fail-fast (per CLAUDE.md)
total = await backend.count()  # Let it raise AttributeError if not supported
```

---

### Example 3: Knowledge Carrier Operations

```python
from core.models.protocols import KnowledgeCarrier, SubstantiatedKnowledge

def process_entity(entity: KnowledgeCarrier) -> dict:
    result = {
        "uid": entity.uid,
        "relevance": entity.knowledge_relevance(),
        "knowledge_uids": entity.get_knowledge_uids(),
    }

    # Check for substance tracking
    if isinstance(entity, SubstantiatedKnowledge):
        result["substance"] = entity.substance_score()

    return result
```

---

### Example 4: Facade Protocol Type Hints

```python
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from core.ports.facade_protocols import TasksFacadeProtocol

async def analyze_task_knowledge(
    tasks_service: TasksFacadeProtocol,
    task_uid: str
) -> dict:
    # MyPy sees these delegated methods
    result = await tasks_service.get_task(task_uid)
    if result.is_error:
        return {}

    impact = await tasks_service.get_task_completion_impact(task_uid)
    return impact.value if impact.is_ok else {}
```

---

## Migration Checklist

When replacing `hasattr()` with Protocols:

- [ ] **Identify the pattern:** Is it enum extraction, backend capability, Pydantic field?
- [ ] **Choose the right Protocol:** See table below
- [ ] **Import the Protocol:** `from core.ports import ProtocolName`
- [ ] **Replace hasattr() with isinstance():** `isinstance(obj, Protocol)`
- [ ] **Consider fail-fast:** Per CLAUDE.md, prefer letting errors surface
- [ ] **Test:** Ensure behavioral equivalence

---

## Protocol Lookup Table

Quick reference for common hasattr() patterns:

| hasattr() Pattern | Replace With | Location |
|------------------|--------------|----------|
| `hasattr(enum, 'value')` | `get_enum_value(enum)` | `core.ports` |
| `hasattr(backend, 'count')` | `isinstance(backend, SupportsCount)` | `core.ports` |
| `hasattr(backend, 'search')` | `isinstance(backend, SupportsSearch)` | `core.ports` |
| `hasattr(field_info, 'metadata')` | `isinstance(field_info, PydanticFieldInfo)` | `core.ports` |
| `hasattr(constraint, 'min_length')` | `isinstance(constraint, MinLenConstraint)` | `core.ports` |
| `hasattr(obj, 'domain')` | `isinstance(obj, HasDomain)` | `core.ports` |
| `hasattr(pydantic_model, 'field')` | Just access `model.field` (always defined) | N/A |
| `hasattr(entity, 'knowledge_relevance')` | `isinstance(entity, KnowledgeCarrier)` | `core.models.protocols` |

---

## Anti-Patterns to Avoid

### Anti-Pattern 1: Checking Static Enums
```python
from core.models.enums import Domain

# WRONG - Domain enum is static, this check is meaningless
knowledge = get_nodes(Domain.KNOWLEDGE) if hasattr(Domain, 'KNOWLEDGE') else []

# RIGHT - Just use it
knowledge = get_nodes(Domain.KNOWLEDGE)
```

### Anti-Pattern 2: Checking Pydantic Model Fields
```python
class Request(BaseModel):
    status: Optional[str] = None

request = Request()

# WRONG - Field is always defined on Pydantic models
if hasattr(request, 'status') and request.status:
    # ...

# RIGHT - Field exists, just check if it's not None
if request.status:
    # ...
```

### Anti-Pattern 3: Defensive Backend Checking
```python
# WRONG - Graceful degradation (violates CLAUDE.md)
if hasattr(backend, 'advanced_search'):
    results = await backend.advanced_search(query)
else:
    results = await backend.basic_search(query)

# RIGHT - Fail fast, fix the backend
results = await backend.advanced_search(query)  # Let it fail if not implemented
```

---

## Protocol Design Guidelines

When creating new Protocols:

1. **Name clearly:** `HasFoo`, `SupportsFoo`, `FooLike`
2. **Use @runtime_checkable:** Enables `isinstance()` checks
3. **Define minimal interface:** Only what's needed for the check
4. **Document purpose:** Explain when/why to use
5. **Add to this reference:** Keep documentation current

---

## Related Documentation

- `/docs/patterns/protocol_architecture.md` - Protocol architecture and best practices (includes Phase 5: Route-Facing ISP Protocols)
- `/docs/patterns/BACKEND_OPERATIONS_ISP.md` - BackendOperations protocol hierarchy
- `/docs/guides/PROTOCOL_IMPLEMENTATION_GUIDE.md` - How to implement protocols
- `/docs/decisions/ADR-025-service-consolidation-patterns.md` - Facade protocols context
- `/docs/decisions/ADR-027-knowledge-carrier-protocol.md` - KnowledgeCarrier context
- `CLAUDE.md` - Architectural principles (Three Typing Strategies for Services dataclass)

---

## Conclusion

Protocols provide type-safe, explicit interfaces that replace hasattr() duck typing. They improve:

- **Type Safety:** MyPy can verify Protocol compliance
- **IDE Support:** Autocomplete works correctly
- **Maintainability:** Clear contracts vs implicit checks
- **Performance:** isinstance() is faster than hasattr()
- **Debugging:** Explicit errors vs silent failures

Always prefer Protocols over hasattr() in new code, and migrate existing code per the migration plan.
