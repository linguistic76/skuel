---
title: Protocol-Based Architecture
updated: 2026-08-20
category: patterns
related_skills:
- python
related_docs:
- /docs/decisions/ADR-017-relationship-service-unification.md
- /docs/decisions/ADR-023-curriculum-baseservice-migration.md
---

# Protocol-Based Architecture

**Last Updated**: March 27, 2026

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

**Core Achievements:**
- **Two-tier typing strategy** - Facade services use concrete class types in routes; thin/ISP services (Groups, Submissions, Sharing, etc.) use ISP protocol types
- **100% hasattr elimination** - All attribute checks now use Protocol-based type checking
- **Zero port dependencies** - All services use `core/ports/*` exclusively
- **Facade services use concrete types** - Route files import `TasksService` directly; no facade protocols needed
- **19 route-facing ISP protocols** - Services container fields typed
- **Services dataclass: zero `Any` fields** — all ~72 fields fully typed
- **~170 typed return types** — protocol methods return specific models/TypedDicts, not `Result[Any]` (March 2026). 0 `Result[Any]` remain in protocols (1 intentional in `base_service_interface.py`). Service-layer `Result[Any]` also narrowed to concrete types
- **TypedDicts** in `query_types.py` — 159 as of March 2026 (21 input + 138 output); **220 measured 2026-08-20**. The file grows with every new typed port, so measure rather than quote this line.
- **Search protocol generics** — all 6 `DomainSearchOperations` extensions parameterized with domain model types (`Goal`, `Event`, etc.), eliminating `# type: ignore[return-value]` in facade delegation
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
core/ports/
├── __init__.py                        # Consolidated exports
├── askesis_protocols.py               # Askesis cross-cutting intelligence (6 protocols)
├── backend_operations_typing.py       # Typed aliases for backend operations
├── base_protocols.py                  # Backend operations ISP hierarchy (42 protocols)
├── base_service_interface.py          # BaseService mixin protocols
├── content_protocols.py               # Content/media protocols
├── curriculum_protocols.py            # KU, PS, LP, Exercise + backend slices (15 protocols)
├── domain_protocols.py                # Activity domain operations (8 protocols)
├── email_protocols.py                 # Email service protocol
├── form_protocols.py                  # Form backend + route protocols (4 protocols)
├── report_protocols.py                # Report stage (15 protocols)
├── graph_protocols.py                 # Graph entity protocols
├── group_protocols.py                 # Group & teaching (2 protocols)
├── infrastructure_protocols.py        # EventBus, User (3 ISP + 1 composed), Schema, Ingestion, Closeable (11 protocols)
├── intelligence_protocols.py          # Intelligence operations (3 protocols: Knowledge, Domain, Composed)
├── query_types.py                     # 220 TypedDicts for type-safe inputs + outputs
├── search_protocols.py                # Search operations (15 protocols)
├── service_protocols.py               # Route-facing services + 2 auth backend slices (14 protocols)
├── sharing_protocols.py               # Cross-entity sharing (2 protocols)
└── user_entry_protocols.py            # UserEntry stage (9 protocols) — replaced
                                       #   submission_protocols.py (ADR-054)
```

### Protocol Hierarchies

Three key protocol hierarchies organize the contracts at their respective layers. Each is ISP-compliant — consumers depend on the narrowest slice they actually use.

**BackendOperations** (the backend-level contract; `UniversalNeo4jBackend` implements this):
```
BackendOperations[T]  <- THE protocol (UniversalNeo4jBackend implements this)
    ├── CrudOperations[T]
    ├── EntitySearchOperations[T]
    ├── RelationshipCrudOperations
    ├── RelationshipQueryOperations
    ├── GraphTraversalOperations
    └── LowLevelOperations
```

**UserOperations** (decomposed per sub-service; `UserBackend` implements the composed protocol):
```
UserOperations  <- composed protocol (UserBackend implements this)
    ├── UserCrudOperations (6)           <- UserCoreService
    ├── UserLearningStateOperations (8)  <- UserProgressRecorderService
    └── UserActivityOperations (3)       <- UserActivityService
```

**IntelligenceOperations** (shared knowledge + per-domain intelligence):
```
IntelligenceOperations  <- composed protocol
    ├── KnowledgeIntelligenceOperations (4)  <- ActivityKnowledgeIntelligenceService (shared across all 6 Activity Domains)
    └── DomainIntelligenceOperations (7)     <- Per-domain intelligence services
```

Note: `*Operations` protocols in `domain_protocols.py` are **backend-level** — they type `self.backend` inside `BaseService[Op, T]`, NOT service-level contracts. Facade services use concrete class types in routes (see "Facade Services — Explicit Delegation" below).

### Protocol Categories

Counts measured by AST (`ast.ClassDef` with a `Protocol` base), 2026-08-20 — every
one of these had drifted, several by 3–5×, and one file listed here no longer existed.
Re-measure rather than increment.

| Category | File | Purpose | Count |
|----------|------|---------|-------|
| **Type Checking** | `core/protocols.py` | Attribute checking (replaces hasattr) | 30+ |
| **Domain Operations** | `domain_protocols.py` | Business logic (Tasks, Goals, etc.) | 8 |
| **Curriculum** | `curriculum_protocols.py` | KU, PS, LP, Exercise + their backend slices | 15 |
| **Search** | `search_protocols.py` | Search and query operations | 15 |
| **Infrastructure** | `infrastructure_protocols.py` | EventBus, User (3 ISP + 1 composed), Ingestion | 11 |
| **Intelligence** | `intelligence_protocols.py` | Knowledge (shared) + Domain (per-service) + Composed | 3 |
| **Askesis** | `askesis_protocols.py` | Cross-cutting intelligence + CRUD | 6 |
| **UserEntry** | `user_entry_protocols.py` | CRUD, lifecycle, assessment, content, organizes (ADR-054 — replaced `submission_protocols.py`) | 9 |
| **Report** | `report_protocols.py` | Human + AI reports, progress reports, scheduling | 15 |
| **Forms** | `form_protocols.py` | Backend ops (2) + route-level ISP (2) | 4 |
| **Groups** | `group_protocols.py` | Group CRUD, teacher review queue | 2 |
| **Services** | `service_protocols.py` | Calendar, Viz, System, LifePath, Auth, Orchestration, Lateral | 14 |

### No "Awareness Slice" Protocols

Services that need a user-state parameter take `UserContext` directly. There is **no parallel layer of ISP slice protocols** (`TaskAwareness`, `KnowledgeAwareness`, etc.) — that pattern was retired (2026-05-11, commit `a82faaba`) because the slices re-declared ~25 fields already owned by `UserContext` and drifted by hand.

If you find yourself reaching for a "narrow this signature so MyPy enforces minimum field access" abstraction, take a primitive parameter instead of inventing a wrapping protocol. The single source of truth is `UserContext`.

**See:** `/docs/architecture/UNIFIED_USER_ARCHITECTURE.md` → "UserContext as Single Source of Truth"

### Protocol Cleanup (February 2026)

Following "One Path Forward", service-level and redundant methods were removed from domain backend protocols in `domain_protocols.py`. The principle: **backend protocols define persistence operations only** — CRUD, queries, and graph relationships. Service-level orchestration (state transitions, event publishing) belongs on facade services.

**Removed from activity domain protocols:**
- `complete_task` from `TasksOperations` — service-level (TasksProgressService, with event publishing)
- `complete_goal` from `GoalsOperations` — service-level (GoalsCoreService, with event publishing)
- `record_completion` from `HabitsOperations` — service-level (HabitsCompletionService, multi-step)
- `analyze_decision_patterns` from `ChoicesOperations` — service-level analytics
- `execute_query` from `ChoicesOperations` — self-annotated architectural issue
- `get_user_principle_portfolio`, `calculate_principle_integrity` from `PrinciplesOperations` — service-level
- Redundant `get`/`create`/`update`/`delete` re-declarations from `ChoicesOperations`, `PrinciplesOperations` (already in `BackendOperations[T]`)
- All `get_*_cross_domain_context` methods — never implemented in any backend

These methods still exist as explicit delegation methods on facade services (`TasksService.complete_task()`, `HabitsService.record_completion()`, etc.) — they were only removed from the backend protocol contract.

**Added: Typed backend subclasses (February 2026)**

`HabitsBackend` and `GoalsBackend` in `adapters/persistence/neo4j/backends/activity_backends.py` are thin subclasses of `UniversalNeo4jBackend[T]` that explicitly implement domain-specific backend methods which don't match the `__getattr__` bridge patterns:

```python
# UniversalNeo4jBackend.__getattr__ patterns:
# create_*    → create()           ✓ works
# get_*_by_uid → get()             ✓ works
# update_*    → update()           ✓ works
# list_*s     → list wrapper       ✓ works (must end in 's')
#
# These do NOT match → AttributeError without typed subclass:
# get_habit(uid)       (not get_habit_by_uid)
# list_by_user(uid)    (not list_by_users)
# get_user_habits(uid) (no matching pattern)
# get_goal(uid)        (not get_goal_by_uid)
# get_user_goals(uid)  (no matching pattern)

class HabitsBackend(UniversalNeo4jBackend["Habit"]):
    async def get_habit(self, habit_id: str) -> Result[Habit]: ...
    async def list_by_user(self, user_uid: UserUID, limit: int = 100) -> Result[list[Habit]]: ...
    async def get_user_habits(self, user_uid: UserUID) -> Result[list[Habit]]: ...
```

`HabitsBackend` and `GoalsBackend` are drop-in replacements with the same constructor signature — only the instantiation in `services_bootstrap/compose.py` changes.

**See:** `adapters/persistence/neo4j/backends/activity_backends.py`

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

**Affected services:** `TasksService`, `GoalsService`, `HabitsService`, `EventsService`, `ChoicesService`, `PrinciplesService`, `KuService`, `PsService`, `LpService`

**Scope of "concrete class": the route→service boundary only.** These facades are concrete
to their *callers*. Inside them, `self.backend` still types against a `core/ports` protocol
— SKUEL023 enforces that, and a facade is not exempt. `KuService.backend` is `KuOperations`;
`PsOrganizationService.backend` is `PsOrganizesBackendOperations`. Do not read this section
as permission to annotate a facade's backend handle with an adapter class.

Since August 2026 SKUEL023 also rejects the weaker escapes: any `core/` class that
*assigns* `self.backend` must name a real protocol there — `Any` and no-annotation-at-all
both fail, because either one leaves every `self.backend.<method>()` call unchecked just
as completely as a concrete adapter would. Declaration-only `backend: Any` in a mixin —
the shape where the *host* constructs the object — fails the same way and is enforced
too: the 27 such mixins were swept in August 2026 (each retyped against its host's
protocol or, where it never touched `self.backend`, deleted), and the rule was extended
to the declaration form only once they were clean, so it landed with zero suppressions.
Write a new one the same way (see SERVICE_DECOMPOSITION_RULE.md § Mixin Class Template).

The inherited form is enforced too, as of August 2026. A class that neither assigns nor
declares `backend` but *inherits* it from a `Base*[Any, ...]` parameterisation — or from a
bare `Base*`, which means the same — was invisible to both checks above while every
`self.backend.<method>()` in it went unchecked. The five such services in `core/` were
typed first and the third trigger landed after, again with zero suppressions. Note the trap
it exists to catch: annotating the `__init__` parameter does **not** fix this. The
attribute's declared type comes from the base, and an assignment never redeclares it, so
`def __init__(self, backend: SomeOps)` on a bare `BaseService` reads as fixed and checks
nothing — four of the five had exactly that shape. Parameterise the base itself. (A
class-body `backend: SomeOps` in the subclass *does* narrow, and is correctly left alone.)

**One escape stays unenforced — deliberately, with a measurement behind it.** A backend
handle under a *different name* (`ku_backend`, `progress_backend`, `session_backend`) is a
**convention**, not a rule. Scope C (2026-08-20) swept every such handle in `core/` and then
ruled against adding a trigger for them:

- The names have no shared structure. `ku_backend` / `progress_backend` are prefixed,
  `_instance_backends` is plural, `_backend_get` is a prefix on a *Callable*. A `*_backend`
  suffix trigger misses three of those four shapes; "name contains *backend*" is precisely
  the over-general matching that produced four false positives in #1095.
- **Measured on the post-Scope-C tree: 39 attributes in `core/` match "contains backend,
  not named backend". 38 are annotated. The 39th —
  `PsEngagementService._instance_backends` — is assigned straight from a constructor call,
  so mypy infers its type and every call on it is already checked.** An AST-only rule
  cannot see that: distinguishing "unannotated but inferred" from "unannotated and `Any`"
  requires type inference, which SKUEL lint rules deliberately refuse to do. So the trigger
  would fire on fully-checked code, on a blocking gate, with no way to be right.
- What it would catch is already empty: after Scope C the only untyped handles are three
  that were **ruled** to stay (the `find_paths_for_user` /
  `get_user_progress_summary` phantom cluster in `lp_intelligence/`, each carrying its
  reason in a comment). A rule would demand three suppressions and buy nothing.

The standing preference for this arc is fail-OPEN: on a blocking gate a false positive
costs more than a missed spelling. SKUEL023's three triggers stay *structural* — they key
on an attribute literally named `backend` — because that is precise. Type a
differently-named handle against a protocol anyway; the rule not reaching there is not a
licence, it is a judgement that a bad rule is worse than none.

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

SKUEL achieved **full type safety** across the entire codebase through systematic improvements (two-tier strategy: concrete for facades, ISP protocols for thin services):

### Phase 1: Protocol Creation (January 2026 — superseded February 2026)
- ✅ Created 9 facade protocols for all facade services
- ✅ Exported all 9 facade protocols in `__init__.py`
- ✅ Added `UserOperations` to infrastructure protocol exports
- ✅ Narrowed `UserOperations` from `Any` to concrete `User`/`UserContext` types (March 2026)
- ✅ ISP decomposition: `UserOperations` → `UserCrudOperations` + `UserLearningStateOperations` + `UserActivityOperations` (March 2026). Sub-services now depend on the narrowest sub-protocol they need.

> **Note:** The facade protocols created in this phase were superseded in February 2026 by explicit delegation methods. Facade services now use concrete class type hints in routes instead of protocol types. See "Facade Services — Explicit Delegation" section.

### Phase 2: Services Container (12 fields updated)
Updated `Services` dataclass in `services_bootstrap/_container.py`:

```python
@dataclass
class Services:
    # Before: Any types
    journals_core: Any = None
    learning: Any = None
    context_service: Any = None

    # After: Protocol types (January 2026) / concrete types (February 2026 for facades)
    learning: "LpService | None" = None  # February 2026: concrete class (was LpFacadeProtocol)
    path_steps: PsOperations | None = None
    learning_intelligence: IntelligenceOperations | None = None
    context_service: UserContextOperations | None = None
    askesis: AskesisOperations | None = None
    moc: KuOperations | None = None
    search_router: "SearchRouter | None" = None  # July 2026: concrete orchestrator class (SoC arc PR 13; the old SearchOperations protocol matched nothing the router implements and was deleted)
    user_service: "UserService | None" = None  # Facade — concrete type
```

### Phase 3: Route Signatures (14 files updated)
All API route functions now use protocol types instead of concrete classes. Note: Activity and Curriculum domain facades were later updated again in Phase 2 of the explicit delegation migration (February 2026) to use concrete service class types.

**Activity (6) — now use concrete service class:**
- `tasks_api.py` → `TasksService`
- `goals_api.py` → `GoalsService`
- `habits_api.py` → `HabitsService`
- `events_api.py` → `EventsService`
- `choices_api.py` → `ChoicesService`
- `principles_api.py` → `PrinciplesService`

**Curriculum (4) — now use concrete service class:**
- `knowledge_api.py` → `KuService`
- `pathways_api.py` → `LpService`
- `path_steps_api.py` → `PsService`
- `moc_api.py` → `KuService` (MOC is KU-based)

**Other Domains (4):**
- `context_aware_api.py` → `UserContextOperations`
- `askesis_api.py` → `AskesisOperations`
- `finance_api.py` → `FinancesOperations`

### Phase 4: Backend Type Hints (6 services updated)
Service classes now use protocol types for backend parameters:

```python
# Before: Concrete backend type
class SubmissionsCoreService(BaseService[UniversalNeo4jBackend[Entity], Entity]):
    ...

# After: Protocol type
class SubmissionsCoreService(BaseService[BackendOperations[Entity], Entity]):
    ...
```

**Updated Services:**
- `KuSearchService` → `KuOperations`
- `SubmissionsCoreService` → `BackendOperations[Entity]`
- `SubmissionsSearchService` → `BackendOperations[Entity]`
- `SubmissionsService` → `BackendOperations[Entity]`

### Results
- **Two-tier typing in route signatures** - Facade services (9: Tasks, Goals, Habits, Events, Choices, Principles, KU, PS, LP) use concrete class types; thin/ISP services use protocol types
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

**Protocol Files — per-file inventory** (counts AST-measured 2026-08-20):

| File | Protocols | Purpose |
|------|-----------|---------|
| `user_entry_protocols.py` | 9 | UserEntryCrud / Lifecycle / Assessment / ReportQuery / Content / Organizes / Processing + the composed `UserEntryOperations`. **Replaced `submission_protocols.py`, which no longer exists** (ADR-054) |
| `sharing_protocols.py` | 2 | SharingOperations — entity-agnostic SHARES_WITH + SHARED_WITH_GROUP management |
| `report_protocols.py` | 15 | EntryReportOperations (AI report + typed reads), AssessmentOperations (a student's received-assessment read — split from EntryReportOperations in PR #128; HUMAN feedback is written by TeacherReviewOperations), ProgressReportOperations, ProgressScheduleOperations, ActivityReportOperations, ReviewQueueOperations, TeacherReviewOperations |
| `form_protocols.py` | 4 | FormTemplateBackendOperations, FormSubmissionBackendOperations (backend-level, import directly from `form_protocols`); FormTemplateOperations, FormSubmissionOperations (route-level, re-exported from `__init__`) |
| `group_protocols.py` | 2 | GroupBackendOperations (backend-level: CRUD + membership edges, `add_member` carries `joined_at`); GroupOperations (route-level, 9 methods) — same root word, two layers |
| `service_protocols.py` | 14 | CalendarService, Visualization, System, CrossDomainAnalytics, LifePath+Alignment, GraphAuth, GoalTaskGenerator, HabitEventScheduler, OwnershipVerifier, LateralRelationship (route + backend); plus two backend slices of the SAME SessionBackend — SessionInvalidationOperations (revocation, consumed by UserService) and SessionBackendOperations (sign-in/session/token persistence, consumed by GraphAuthService) |

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
class HasScore(Protocol):
    score: float
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
Task.get_color = lambda self: self.color if isinstance(self, HasColor) else None

# ✅ Good - Named function
def _get_color(self):
    """Get task color if available."""
    if isinstance(self, HasColor):
        return self.color
    return None

Task.get_color = _get_color
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

BaseService is composed of 6 mixins, each with a corresponding protocol:
- `ConversionHelpersMixin` → `ConversionOperations`
- `CrudOperationsMixin` → `CrudOperations`
- `SearchOperationsMixin` → `SearchOperations`
- `RelationshipOperationsMixin` → `RelationshipOperations`
- `TimeQueryMixin` → `TimeQueryOperations`
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
uv run pytest tests/unit/test_protocol_mixin_compliance.py -v

# Check specific protocol-mixin pair
uv run pytest tests/unit/test_protocol_mixin_compliance.py -k "Conversion" -v

# Verify with MyPy
uv run mypy core/services/mixins/*.py
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
