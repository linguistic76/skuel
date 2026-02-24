---
title: Protocol-Based Architecture
updated: 2026-02-15
category: patterns
related_skills:
- python
related_docs:
- /docs/decisions/ADR-017-relationship-service-unification.md
- /docs/decisions/ADR-023-curriculum-baseservice-migration.md
---

# Protocol-Based Architecture

**Last Updated**: February 8, 2026

## Quick Start

**Skills:** [@python](../../.claude/skills/python/SKILL.md)

For hands-on implementation:
1. Invoke `@python` for Protocol patterns and type-safe interfaces
2. See [QUICK_REFERENCE.md](../../.claude/skills/python/QUICK_REFERENCE.md) for Protocol examples
3. Continue below for complete protocol architecture

**Related Documentation:**
- [BACKEND_OPERATIONS_ISP.md](BACKEND_OPERATIONS_ISP.md) - Interface segregation for backends
- [protocol_mixin_alignment.md](/docs/migrations/PROTOCOL_MIXIN_ALIGNMENT_COMPLETE_2026-01-29.md) - Protocol compliance migration

---

## Overview

SKUEL uses Python's Protocol typing (PEP 544) for dependency injection without framework overhead. This provides type safety, testability, and clean architecture while maintaining the "one path forward" philosophy.

**Core Achievements** (January–February 2026):
- **100% protocol compliance** - All services, routes, and containers use protocol types
- **100% hasattr elimination** - All attribute checks now use Protocol-based type checking
- **Zero port dependencies** - All services use `core/ports/*` exclusively
- **Facade services use concrete types** - Route files import `TasksService` directly; no facade protocols needed
- **19 route-facing ISP protocols** - Services container fields typed (February 2026)
- **Services dataclass: zero `Any` fields** — all ~72 fields fully typed (February 2026)
- **75% code reduction** through generic programming patterns
- **27+ services** using protocol interfaces exclusively

## What Are Protocols?

Protocols are Python's way of defining structural subtyping (duck typing with type hints). They define interfaces that classes can satisfy without explicit inheritance.

```python
from typing import Protocol, runtime_checkable

@runtime_checkable
class Flyable(Protocol):
    def fly(self) -> None: ...

# Any class with a fly() method satisfies Flyable
class Bird:
    def fly(self) -> None:
        print("Flying!")

# Bird satisfies Flyable without inheriting from it
def make_it_fly(thing: Flyable) -> None:
    thing.fly()

make_it_fly(Bird())  # Works!
```

## Protocol Architecture in SKUEL

### Directory Structure

```
core/
├── protocols.py                      # Core type-checking protocols
└── services/
    └── protocols/
        ├── __init__.py               # Consolidated exports (~120 symbols)
        ├── askesis_protocols.py       # Askesis cross-cutting intelligence (6 protocols)
        ├── base_protocols.py          # Backend operations ISP hierarchy (7+ protocols)
        ├── base_service_interface.py  # BaseService mixin protocols
        ├── calendar_protocol.py       # CalendarTrackable entity protocol
        ├── context_awareness_protocols.py # UserContext slices (11 protocols)
        ├── curriculum_protocols.py    # KU, LS, LP operations (4 protocols)
        ├── domain_protocols.py        # Activity domain operations (9 protocols)
        ├── graph_protocols.py         # Graph entity protocols
        ├── group_protocols.py         # Group & teaching (2 protocols) [Feb 2026]
        ├── infrastructure_protocols.py # EventBus, User, Ingestion (6 protocols)
        ├── intelligence_protocols.py  # Analytics operations (1 protocol)
        ├── query_types.py             # TypedDicts for queries
        ├── reports_protocols.py       # Reports domain (7 protocols) [Feb 2026]
        ├── search_protocols.py        # Search operations (8 protocols)
        └── service_protocols.py       # Route-facing services (10 protocols) [Feb 2026]
```

### Protocol Categories

| Category | File | Purpose | Count |
|----------|------|---------|-------|
| **Type Checking** | `core/protocols.py` | Attribute checking (replaces hasattr) | 30+ |
| **Domain Operations** | `domain_protocols.py` | Business logic (Tasks, Goals, etc.) | 9 |
| **Curriculum** | `curriculum_protocols.py` | KU, LS, LP operations (unified hierarchy) | 4 |
| **Search** | `search_protocols.py` | Search and query operations | 8 |
| **Infrastructure** | `infrastructure_protocols.py` | EventBus, UserOperations, Ingestion | 6 |
| **Intelligence** | `intelligence_protocols.py` | Analytics and intelligence operations | 1 |
| **Askesis** | `askesis_protocols.py` | Cross-cutting intelligence + CRUD | 6 |
| **Reports** | `reports_protocols.py` | Submission, sharing, processing, feedback | 7 |
| **Groups** | `group_protocols.py` | Group CRUD, teacher review queue | 2 |
| **Services** | `service_protocols.py` | Calendar, Viz, System, LifePath, Auth, Orchestration | 9 |

### Protocol Cleanup (January 2026)

Following "One Path Forward", unused and dead protocols have been removed:

**Deleted from `ku_protocols.py`:**
- `LearningOperations` - Dead code (type hint was wrong, never implemented)
- `LearningQueryOperations` - Unused legacy protocol
- `ContentOperations` - Aspirational (never properly implemented)
- `ContentQueryOperations` - Unused legacy protocol

**Deleted from `domain_protocols.py`:**
- `HasModelDump`, `HasDict` (duplicate), `HasValue`, `HasStatus`
- `HasInsights`, `HasTimestamps`, `HasCreatedBy` (7 orphaned protocols)

**Migration Path:**
- Use `LpOperations` from `curriculum_protocols.py` instead of `LearningPathsOperations`
- Use `KuOperations` from `curriculum_protocols.py` instead of `KuOperationsLegacy`
- Use duck typing or `Any` for services without proper protocol alignment

### Facade Services — Explicit Delegation (February 2026)

**Previous approach (deleted):** `FacadeDelegationMixin` generated 30-50+ delegation methods dynamically from a `_delegations` dict. This required `facade_protocols.py` (9 protocol classes) to make the dynamic methods visible to MyPy — a three-way synchronization burden.

**Current approach:** All 9 facade services have explicit `async def` delegation methods. MyPy sees them natively. No parallel protocol file needed.

```python
# Current pattern (February 2026)
class TasksService(BaseService[TasksOperations, Task]):
    core: TasksCoreService
    search: TasksSearchService
    intelligence: TasksIntelligenceService

    # Explicit delegation — MyPy-native
    async def create_task(self, *args: Any, **kwargs: Any) -> Any:
        return await self.core.create_task(*args, **kwargs)

    async def search_tasks(self, *args: Any, **kwargs: Any) -> Any:
        return await self.search.search(*args, **kwargs)
```

**Route files import the concrete service class:**

```python
# Current (February 2026)
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from core.services.tasks_service import TasksService

def create_tasks_api_routes(
    app: Any,
    rt: Any,
    tasks_service: "TasksService",  # Concrete class, not protocol
) -> list[Any]:
    await tasks_service.schedule_task(...)  # ✓ Type-safe (method is explicit)
    await tasks_service.get_ready_to_work_on(...)  # ✓ Type-safe
```

**Affected services:** `TasksService`, `GoalsService`, `HabitsService`, `EventsService`, `ChoicesService`, `PrinciplesService`, `KuService`, `LsService`, `LpService`

**Benefits:**
- **MyPy-native** - No protocol workaround needed
- **2,422 lines removed** - No mixin, no protocol file
- **One file** - Service class is the single source of truth
- **Simpler** - Add a method and it just works

### Architecture Pattern

```
Core Domain (Business Logic)
    ↓ depends on
Protocols (in core/ports/)
    ↑ implemented by
Adapters (in adapters/)
```

**Key Insight**: Protocols ARE your ports - they provide the same contract/interface capability as traditional ports, but with better type checking and less boilerplate.

## Protocol Compliance Improvements (January 2026)

SKUEL achieved **100% protocol compliance** across the entire codebase through systematic improvements:

### Phase 1: Protocol Creation (January 2026 — superseded February 2026)
- ✅ Created 9 facade protocols for all facade services
- ✅ Exported all 9 facade protocols in `__init__.py`
- ✅ Added `UserOperations` to infrastructure protocol exports

> **Note:** The facade protocols created in this phase were superseded in February 2026 by explicit delegation methods. Facade services now use concrete class type hints in routes instead of protocol types. See "Facade Services — Explicit Delegation" section.

### Phase 2: Services Container (12 fields updated)
Updated `Services` dataclass in `services_bootstrap.py`:

```python
@dataclass
class Services:
    # Before: Any types
    journals_core: Any = None
    learning: Any = None
    context_service: Any = None

    # After: Protocol types (January 2026) / concrete types (February 2026 for facades)
    journals_core: JournalsOperations | None = None
    learning: "LpService | None" = None  # February 2026: concrete class (was LpFacadeProtocol)
    learning_steps: LsOperations | None = None
    learning_intelligence: IntelligenceOperations | None = None
    context_service: UserContextOperations | None = None
    askesis: AskesisOperations | None = None
    moc: KuOperations | None = None
    search_router: SearchOperations | None = None
    user_service: UserOperations | None = None
```

### Phase 3: Route Signatures (14 files updated)
All API route functions now use protocol types instead of concrete classes. Note: Activity and Curriculum domain facades were later updated again in Phase 2 of the explicit delegation migration (February 2026) to use concrete service class types.

**Activity Domains (6) — now use concrete service class:**
- `tasks_api.py` → `TasksService`
- `goals_api.py` → `GoalsService`
- `habits_api.py` → `HabitsService`
- `events_api.py` → `EventsService`
- `choices_api.py` → `ChoicesService`
- `principles_api.py` → `PrinciplesService`

**Curriculum Domains (4) — now use concrete service class:**
- `knowledge_api.py` → `KuService`
- `learning_api.py` → `LpService`
- `learning_steps_api.py` → `LsService`
- `moc_api.py` → `KuService` (MOC is KU-based)

**Other Domains (4):**
- `context_aware_api.py` → `UserContextOperations`
- `askesis_api.py` → `AskesisOperations`
- `finance_api.py` → `FinancesOperations`

### Phase 4: Backend Type Hints (6 services updated)
Service classes now use protocol types for backend parameters:

```python
# Before: Concrete backend type
class JournalsCoreService(BaseService[UniversalNeo4jBackend[Report], Report]):
    ...

# After: Protocol type
class JournalsCoreService(BaseService[JournalsOperations, Report]):
    ...
```

**Updated Services:**
- `JournalsCoreService` → `JournalsOperations`
- `ContentEnrichmentService` → `JournalsOperations`
- `KuSearchService` → `KuOperations`
- `ReportsCoreService` → `BackendOperations[Entity]`
- `ReportsSearchService` → `BackendOperations[Entity]`
- `ReportsSubmissionService` → `BackendOperations[Entity]`

### Results
- **Zero concrete type dependencies** in route signatures
- **Full type safety** with MyPy across all services
- **Better IDE support** with complete method autocomplete
- **Easier testing** with protocol-based mocking
- **Cleaner architecture** following dependency inversion principle

### Phase 5: Route-Facing ISP Protocols (February 2026)

Extended protocol coverage from Activity/Curriculum domains to **all route-facing services** in the Services dataclass. This phase introduced a key distinction between two typing strategies:

**Strategy 1: ISP Protocols (route-facing services)**

For services passed as parameters to route factory functions (`create_*_routes()`), we create ISP-compliant protocols that capture *only* the methods routes actually call. This prevents drift between what routes expect and what services provide.

```python
# service_protocols.py — ISP: only methods called from routes
@runtime_checkable
class GroupOperations(Protocol):
    async def create_group(self, teacher_uid: str, name: str, ...) -> Result[Any]: ...
    async def get_group(self, uid: str) -> Result[Any | None]: ...
    # ... only methods routes call, not the full service interface
```

**Strategy 2: Concrete Types via TYPE_CHECKING (internal-only services)**

For services used only for internal wiring (never passed to routes), we use concrete class types under `TYPE_CHECKING`. This gives IDE support and documentation without creating unnecessary protocol abstractions.

```python
if TYPE_CHECKING:
    from core.services.transcription.transcription_service import TranscriptionService

@dataclass
class Services:
    transcription: "TranscriptionService | None" = None  # Internal wiring only
```

**New Protocol Files (3):**

| File | Protocols | Purpose |
|------|-----------|---------|
| `reports_protocols.py` | 9 | ReportsSubmission, ReportsContent, ReportsContentSearch, ReportsSharing, ReportsProcessing, Assignment, ReportsFeedback, ProgressReportGenerator, ReportsSchedule |
| `group_protocols.py` | 2 | GroupOperations (9 methods), TeacherReviewOperations (5 methods) |
| `service_protocols.py` | 9 | CalendarService, Visualization, System, CrossDomainAnalytics, LifePath+Alignment, GraphAuth, GoalTaskGenerator, HabitEventScheduler |

**Added to Existing Files:**
- `askesis_protocols.py` — `AskesisCoreOperations` (5 methods for CRUD operations)

**Services Dataclass Fields — Zero `Any` Remaining:**

| Tier | Strategy | Fields | Examples |
|------|----------|--------|---------|
| Route-facing protocols | `Protocol \| None` | 19 | `group_service: GroupOperations`, `calendar: CalendarServiceOperations` |
| Internal concrete types | `"ConcreteClass \| None"` | ~39 | `transcription: "TranscriptionService"`, `tasks_intelligence: "TasksIntelligenceService"` |

**Route Files Updated (13):**
All route factory functions updated with `TYPE_CHECKING` imports and protocol-typed parameters:
- `reports_api.py`, `reports_sharing_api.py` — Reports protocols
- `groups_api.py`, `teaching_api.py` — Group protocols
- `visualization_api.py`, `system_api.py`, `calendar_api.py`, `lifepath_api.py` — Service protocols
- `askesis_api.py` — AskesisCoreOperations
- `auth_ui.py`, `admin_api.py` — GraphAuthOperations
- `orchestration_routes.py` — GoalTaskGenerator/HabitEventScheduler protocols

**Dead Code Removed:**
- 3 unused fields deleted from Services: `yaml_loader`, `markdown_parser`, `apoc_adapter`

**Why This Matters:**

Before this phase, a developer looking at `group_service: Any` had no way to know what methods were available without reading the concrete class source. Now:
1. **Route-facing protocols** document exactly what the route layer needs (ISP boundary)
2. **TYPE_CHECKING types** give IDE autocomplete for all internal wiring
3. **Drift prevention** — if a service method signature changes, MyPy catches mismatches at the protocol boundary
4. The Services dataclass itself becomes **documentation** — you can read the type annotations to understand the system topology
5. **Zero `Any` fields** — every field on the Services dataclass has a meaningful type

## Best Practices

### 1. Use @runtime_checkable

```python
@runtime_checkable  # Allows isinstance() checks
class HasMetrics(Protocol):
    metrics: Any
```

### 2. Prefer Specific Protocols Over hasattr

```python
# ✅ Good - Specific protocol
if isinstance(obj, HasCreatedAt):
    use(obj.created_at)

# ❌ Bad - Generic hasattr
if hasattr(obj, 'created_at'):
    use(obj.created_at)
```

### 3. No Lambdas

```python
# ❌ Bad - Lambda function
TaskPure.get_color = lambda self: self.color if isinstance(self, HasColor) else None

# ✅ Good - Named function
def _get_color(self):
    """Get task color if available."""
    if isinstance(self, HasColor):
        return self.color
    return None

TaskPure.get_color = _get_color
```

### 4. Duck Typing for Backends

```python
# ✅ Good - Backend satisfies protocol through methods
class MyBackend:
    async def create_journal(self, journal): ...
    # Automatically satisfies JournalOperations

# ❌ Bad - Explicit inheritance (not needed)
class MyBackend(JournalOperations):
    async def create_journal(self, journal): ...
```

### 5. Use Protocols to Break Circular Dependencies

```python
# ❌ Bad - Circular dependency
from core.services.user_context_service import UserContextService

class TasksService:
    def __init__(self, context_service: UserContextService):
        self.context_service = context_service
        # Now TasksService → UserContextService → TasksService ❌

# ✅ Good - Protocol breaks the cycle
from core.ports import UserContextOperations

class TasksService:
    def __init__(
        self,
        backend: TasksOperations,
        context_service: Optional[UserContextOperations] = None
    ):
        self.context_service = context_service
        # Now TasksService → Protocol (no circular dependency) ✅

# Implementation can be provided later during bootstrap
# No import cycle because protocol is just an interface
```

**Pattern for Breaking Circular Dependencies:**
1. Identify the circular dependency (Service A → Service B → Service A)
2. Create a minimal protocol interface for the needed operations
3. Have Service A depend on the protocol, not the concrete Service B
4. Wire up the concrete implementation during bootstrap
5. Use `Optional[Protocol]` to allow None during initialization

## Benefits Summary

### Type Safety
- **Compile-time checking** with MyPy
- **IDE autocomplete** and refactoring support
- **No runtime AttributeErrors**
- **Clear contracts** between components

### Code Quality
- **100% hasattr elimination** - All checks now type-safe
- **Zero port dependencies** - Clean protocol-based architecture
- **No lambdas** - Proper named methods throughout
- **75% code reduction** through generic patterns

### Testability
- **Mock protocols**, not implementations
- **No database required** for unit tests
- **Fast test execution**
- **Reusable test patterns**

### Maintainability
- **No circular dependencies**
- **Clear separation of concerns**
- **Duck typing** - Implementations satisfy protocols automatically
- **One path forward** - No alternatives, no confusion

## Protocol-Mixin Compliance (January 2026)

**Achievement:** 100% protocol-mixin alignment across all 7 BaseService mixins.

### The Challenge

BaseService is composed of 7 mixins, each with a corresponding protocol:
- `ConversionHelpersMixin` → `ConversionOperations`
- `CrudOperationsMixin` → `CrudOperations`
- `SearchOperationsMixin` → `SearchOperations`
- `RelationshipOperationsMixin` → `RelationshipOperations`
- `TimeQueryMixin` → `TimeQueryOperations`
- `UserProgressMixin` → `UserProgressOperations`
- `ContextOperationsMixin` → `ContextOperations`

**The Problem:** Method signatures must be duplicated in both protocol and mixin, requiring manual synchronization.

### The Solution: Automated Verification

**Accept the duplication** (protocols define interface, mixins define implementation), but **automate the verification**:

#### 1. TYPE_CHECKING Verification Blocks

Each mixin includes a verification block that MyPy checks at compile time:

```python
# core/services/mixins/conversion_helpers_mixin.py

class ConversionHelpersMixin[B, T]:
    def _to_domain_model(self, data: Any, dto_class: type, model_class: type[T]) -> T:
        return _to_domain_model_fn(data, dto_class, model_class)
    # ... other methods

# ============================================================================
# PROTOCOL COMPLIANCE VERIFICATION
# ============================================================================
if TYPE_CHECKING:
    from core.ports.base_service_interface import ConversionOperations

    # MyPy verifies structural compatibility - fails if signatures don't match
    _protocol_check: type[ConversionOperations[Any]] = ConversionHelpersMixin  # type: ignore[type-arg]
```

**How It Works:**
- `TYPE_CHECKING` is only `True` during static analysis (MyPy), never at runtime
- MyPy verifies the mixin structurally satisfies the protocol
- Any signature mismatch causes a **compile-time type error**
- **Zero runtime cost** - code is never executed

#### 2. Automated Test Suite

29 comprehensive tests verify all protocol-mixin pairs:

```bash
# Run all compliance tests
poetry run pytest tests/unit/test_protocol_mixin_compliance.py -v

# Check specific protocol-mixin pair
poetry run pytest tests/unit/test_protocol_mixin_compliance.py -k "Conversion" -v

# Verify with MyPy
poetry run mypy core/services/mixins/*.py
```

**Test Coverage:**
- ✅ 7 tests: All protocol methods exist in mixins
- ✅ 7 tests: All method signatures match exactly
- ✅ 7 tests: TYPE_CHECKING blocks present and correctly formatted
- ✅ 8 tests: Infrastructure and documentation verification

**Result:** 29/29 tests passing (100% compliance)

#### 3. Self-Maintaining System

Once protocols match implementations:
- Tests catch any future drift immediately
- MyPy enforces correctness at compile time
- No manual synchronization needed
- Impossible to miss a mismatch

### Benefits

**Before:**
- ❌ Protocols and mixins out of sync
- ❌ Manual checking required (error-prone)
- ❌ Easy to miss mismatches

**After:**
- ✅ 100% protocol-mixin alignment
- ✅ Automatic verification (29 tests + MyPy)
- ✅ Self-maintaining system
- ✅ Zero manual synchronization needed

### Files

**Tests:** `tests/unit/test_protocol_mixin_compliance.py`
**Documentation:**
- `/docs/investigations/PROTOCOL_MIXIN_ALIGNMENT_SOLUTIONS.md` - Analysis & solutions
- `/docs/migrations/PROTOCOL_MIXIN_ALIGNMENT_COMPLETE_2026-01-29.md` - Implementation report

---

## See Also

- [BACKEND_OPERATIONS_ISP.md](BACKEND_OPERATIONS_ISP.md) - BackendOperations protocol hierarchy (ISP-compliant design)
- [PROTOCOL_REFERENCE.md](../reference/PROTOCOL_REFERENCE.md) - Complete protocol catalog
- [PORTS_TO_PROTOCOLS_MIGRATION.md](../migrations/PORTS_TO_PROTOCOLS_MIGRATION.md) - Migration history and lessons learned
- [PROTOCOL_IMPLEMENTATION_GUIDE.md](../guides/PROTOCOL_IMPLEMENTATION_GUIDE.md) - How to implement and use protocols
- [PROTOCOL_MIXIN_ALIGNMENT_COMPLETE_2026-01-29.md](../migrations/PROTOCOL_MIXIN_ALIGNMENT_COMPLETE_2026-01-29.md) - Protocol-mixin compliance achievement

---

**Status:** Active - Core pattern for all dependency injection in SKUEL
