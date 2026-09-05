---
updated: 2026-09-05
---

# Type Safety Architecture Overview

*Last updated: 2026-03-28 (submission/report protocol enum enforcement, new TypedDicts)*

SKUEL treats type safety as infrastructure — not ceremony. Types are enforced at every
layer, from HTTP boundaries through to database writes. The goal is that a type error from
MyPy or Pyright reveals a real design problem, not an annotation oversight.

---

## The Three Interlocking Systems

```
HTTP Request
    │
    ▼  Pydantic validates (Tier 1 — External)
Request Model (TaskCreateRequest, GoalCreateRequest, ...)
    │
    ▼  Typed transfer between layers (Tier 2 — Transfer)
DTO (TaskDTO, GoalDTO, ...)
    │
    ▼  Frozen domain model at the core (Tier 3 — Core)
Domain Model (Task, Goal, ...)
    │
    ▼  Protocol-typed service calls
Service (TasksOperations, GoalsOperations, ...)
    │
    ▼  Neo4j boundary — Neo4jProperties
Database
```

---

## System 1: Three-Tier Type System

**Principle:** "Pydantic at the edges, pure Python at the core"

| Tier | Type | Key Characteristic |
|------|------|--------------------|
| External (Tier 1) | Pydantic `BaseModel` | Validates user input, rejects bad data at the boundary |
| Transfer (Tier 2) | Mutable DTOs | Move data between layers with explicit field names |
| Core (Tier 3) | Frozen `@dataclass(frozen=True)` | Immutable business entities; can't be accidentally mutated |

**Frozen dataclasses use `__post_init__` for dynamic defaults** (the one known MyPy
limitation in this codebase):
```python
@dataclass(frozen=True)
class Task(UserOwnedEntity):
    created_at: datetime = None  # type: ignore[assignment] — set in __post_init__

    def __post_init__(self) -> None:
        if self.created_at is None:
            object.__setattr__(self, "created_at", datetime.now(UTC))
        super().__post_init__()
```
The `# type: ignore[assignment]` here is the only justified suppression pattern for
frozen dataclass defaults. It's not a design flaw — it's a MyPy limitation with
frozen dataclasses. See `three_tier_type_system.md` for the full rationale.

**See:** `docs/patterns/three_tier_type_system.md` (468 lines, complete reference)

---

## System 2: Protocol-Based Dependency Injection

**Principle:** "Right type at the right boundary — concrete for facades, protocol for thin services"

Facades use concrete types (the facade IS the contract), thin services use ISP protocols:
```python
# Route function — facades use concrete types, thin services use protocols
def create_tasks_api_routes(
    app: FastHTMLApp,
    rt: RouteDecorator,
    tasks_service: TasksService,          # Facade — concrete class IS the contract
    user_service: UserService,            # Facade — concrete class IS the contract
) -> list[Any]: ...
```

**Why this matters:**
- Routes can't accidentally call internal methods not on the protocol
- Services can be swapped for test doubles without changing route code
- MyPy catches mismatches between what routes call and what protocols declare

**Key numbers:**
- 517 `@runtime_checkable` Protocol definitions across 11 files in `core/ports/`
- 100% protocol compliance — all 7 `BaseService` mixins verified by TYPE_CHECKING blocks
- 29 automated compliance tests (run: `uv run pytest tests/unit/test_protocol_mixin_compliance.py`)
- Zero `Any` fields in the `Services` dataclass — all 72 fields typed
- ~170 protocol return types migrated from `Result[Any]` / `Result[dict[str, Any]]` to specific types (March 2026). 0 `Result[Any]` remain in protocols (1 intentional in `base_service_interface.py`). Service-layer `Result[Any]` also narrowed. Route handlers: 0 `Result[Any]` across 27 API files (2 intentional `# boundary:` for FastHTML FT components)
- 159 TypedDicts in `query_types.py` — 21 for inputs (filters, payloads), 138 for outputs (domain stats, system health, teacher review, visualization configs, result shapes, UserContext field types, context intelligence, graph entity, curriculum structure, curriculum backend Cypher returns, PS backend result types, lateral relationship backend returns, life path nested types, review queue results, journal cleanup stats)
- **Search protocol generics** — all 6 extended search protocols (`TasksSearchOperations`, `GoalsSearchOperations`, etc.) parameterized with their domain model type (`Task`, `Goal`, `Event`, `Choice`, `Habit`, `Principle`), not `Entity`. Eliminates `# type: ignore[return-value]` in facade delegation methods

**BackendOperations[T] hierarchy** — the foundational generic protocol:
```python
BackendOperations[T]          # UniversalNeo4jBackend[T] implements this
    ├── CrudOperations[T]
    ├── EntitySearchOperations[T]
    ├── RelationshipCrudOperations
    ├── RelationshipQueryOperations
    ├── GraphTraversalOperations
    └── LowLevelOperations
```
`UniversalNeo4jBackend[Task]`, `UniversalNeo4jBackend[Goal]`, etc. — the same generic
backend serves all entity types, constrained by `DomainModelProtocol`.

**See:** `docs/patterns/protocol_architecture.md`, `docs/patterns/BACKEND_OPERATIONS_ISP.md`

---

## System 3: Any Usage Policy

**Principle:** "Every `Any` is either justified or eliminated"

Every `Any` annotation must belong to one of three categories:

| Category | Status | Action |
|----------|--------|--------|
| **A — Lazy Typing** | Must not exist | Fix immediately (`logger: Any` → `logging.Logger`) |
| **B — Reducible** | Use specific types | `Neo4jProperties`, `FilterParams`, `RelationshipMetadata` |
| **C — Permanent Boundary** | Document with `# boundary:` | Neo4j primitives, FastHTML elements, error metadata |

**Type aliases for common boundaries** (in `core/models/type_hints.py`):
```python
from core.models.type_hints import (
    Neo4jProperties,  # dict[str, str | int | float | bool | list | None | datetime]
    FilterParams,     # dict[str, str | int | float | bool | list | None]
)

# Neo4j node data — use Neo4jProperties, not dict[str, Any]
def from_neo4j_node(data: Neo4jProperties, entity_class: type[T]) -> T: ...

# Search/filter — use FilterParams, not dict[str, Any]
async def find_by_filters(filters: FilterParams) -> list[Entity]: ...
```

**FastHTML boundary** — centralized in `adapters/inbound/fasthtml_types.py`:
```python
from adapters.inbound.fasthtml_types import RouteDecorator, FastHTMLApp, Request
# FastHTML has no type stubs; these Protocols capture what SKUEL actually calls
```

**Protocol layer adoption (March 2026):**

*Phase 3 — Input parameters:* All protocol method signatures now use typed aliases
(`Neo4jProperties`, `FilterParams`, `Metadata`, `RelationshipMetadata`, `GraphContextResult`)
instead of `dict[str, Any]` for parameters.

*Phase 4 — Return types:* ~170 protocol methods migrated from `Result[Any]` / `Result[dict[str, Any]]`
to specific types (0 `Result[Any]` remain in protocols, 1 intentional in `base_service_interface.py`):
- Domain model returns: `Result[UserEntry]`, `Result[Askesis]`, `Result[CalendarData]`, etc.
- Existing TypedDicts: `Result[ContextDashboard]`, `Result[ContextSummary]`
- Existing dataclasses: `Result[LearningVelocityMetrics]`, `Result[SpendingPatternAnalysis]`
- 48 output TypedDicts for structured dict returns: auth results (`SignUpResult`, `SignInResult`),
  teacher review (`ReviewQueueItem`, `TeacherDashboardStats`, `GroupMemberProgress`),
  review queue (`ReviewRequestResult`, `PendingReviewItem`), intelligence results
  (`KnowledgeSuggestionsResult`, `PerformanceAnalyticsResult`, `KnowledgePrerequisitesResult`,
  `CrossDomainOpportunitiesResult`, `AIInsightsResult`), life path (`LifePathStatus`,
  `LifePathAlignmentResult`), lateral relationships (`BlockingChainResult`, `RelationshipGraphData`),
  activity reports (`AnnotationResult`, `PrivacySummary`), UserContext field shapes
  (`RichEntityItem`, `RichKnowledgeUnitItem`, `CrossDomainInsightsData`, etc.)

Only genuine boundary types (Neo4j driver params, FastHTML elements, error metadata) and
backend-level raw Cypher results retain `Any`.

*Phase 5 — Service-layer narrowing and search protocol generics:* Remaining `Result[Any]` in
service methods narrowed to concrete types (`Result[GraphContext]`, `Result[HabitCompletion]`,
`Result[ValidationResult]`, `Result[DirectoryValidationResult]`, `Result[Habit]`). Search
protocol root cause fixed: 4 extended protocols (`GoalsSearchOperations`, `EventsSearchOperations`,
`ChoicesSearchOperations`, `PrinciplesSearchOperations`) re-parameterized from `Entity` to their
domain model type, eliminating 27 `# type: ignore[return-value]` suppressions in facade delegation
methods. `EntityStatus` enum now enforced in all status comparisons (previously only `UserRole`
and `ExerciseScope`). `Pipeline` and `Visibility` enums enforced in user entry protocol
parameters (previously `Any`). 30 missing return type annotations added to service methods.

*Phase 6 — Route handler returns:* All 27 `*_api.py` route files narrowed from `Result[Any]` to
specific types (267 → 2). Route handlers now declare exact payload types (`Result[Task]`,
`Result[ContextDashboard]`, `Result[list[Goal]]`, etc.). ~20 cross-type error propagation sites
fixed using `Result.fail(result)` instead of bare `return result`. The 2 remaining `Result[Any]`
are intentional `# boundary:` annotations for FastHTML FT components without type stubs.

**See:** `docs/patterns/ANY_USAGE_POLICY.md` (complete policy with quick-reference table)

---

## MyPy Configuration Strategy

**Principle:** "Strict where it matters, gradual everywhere else"

SKUEL achieved **0 MyPy errors** in March 2026 through gradual per-module strictness.
The strategy was never "strict mode everywhere" — it was systematic resolution through
per-module overrides in `pyproject.toml`, climbing from ~2,200 latent errors to zero.

Per-module strictness overrides:

| Module Group | Strictness | Why |
|--------------|-----------|-----|
| `core.utils.result`, `core.utils.error_boundary` | Strict | Core error-handling infrastructure |
| `core.models.*`, `core.infrastructure.*` | Medium | Domain models must be well-typed |
| `core.services.*` | Gradual | 94 untyped defs remain — enable incrementally |
| `core.ports.*` | `disallow_untyped_defs` | All protocol definitions must have type annotations |
| `adapters.*` | Gradual | Framework boundaries; `RouteDecorator` protocol handles FastHTML |
| `adapters.persistence.neo4j.backends.*` | Custom | `misc` suppressed for MRO mixin conflicts (all 9 cluster files) |
| `tests.*` | Lenient | Mocks and fixtures need flexibility |

**Disabled error codes (global):** none. `arg-type` is enforced on all four first-party trees (`core`, `services_bootstrap`, `adapters`, `ui`) as of 2026-05-31 — the global disable was deleted once the sweep reached 0 everywhere.

**Disabled error codes (`tests`/`examples`/`scripts` only):** `[method-assign, type-var, misc, arg-type]` — framework-mock noise (fixtures monkey-patch methods, parameterize generics with DTOs, and construct wrong-typed objects freely; never in the sweep's scope).

**Disabled error codes (per-module):**
- `misc` on each of the 8 `backends.*` cluster modules — MRO conflicts from multiple mixin inheritance in domain backend classes

**Ruff enforces annotation discipline:**
- `TCH` rules: correct `TYPE_CHECKING` block usage
- SKUEL linter rules include `SKUEL003` (`.is_error` not `.is_err`)

**See:** `docs/patterns/mypy_pragmatic_strategy.md` (current strategy),
`docs/patterns/MYPY_TYPE_SAFETY_PATTERNS.md` (common error patterns and fixes)

---

## Generic Types

The generic backbone that makes one backend serve every entity type:

```python
# DomainModelProtocol — the constraint on T
@runtime_checkable
class DomainModelProtocol(Protocol):
    uid: str
    created_at: datetime
    entity_type: EntityType
    def to_dto(self) -> Any: ...
    @classmethod
    def from_dto(cls, dto: Any) -> "DomainModelProtocol": ...

# UniversalNeo4jBackend[T] — one backend, all entity types
backend = UniversalNeo4jBackend[Task](driver, NeoLabel.TASK, Task, base_label=NeoLabel.ENTITY)

# BaseService[B, T] — all 6 activity domains use this
class GoalsCoreService(BaseService[GoalsOperations, Goal]):
    _config = create_activity_domain_config(...)

# Generic type aliases (from core.models.type_hints)
type Validator[T] = Callable[[T], list[str]]
type EntityFilter[T] = Callable[[T], bool]
type Scorer[T] = Callable[[T], Score]
```

**See:** `adapters/persistence/neo4j/universal_backend.py`, `core/services/base_service.py`

---

## TYPE_CHECKING Pattern

Used throughout the codebase to avoid circular imports while maintaining type safety:

```python
from __future__ import annotations
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from neo4j import AsyncDriver                    # Zero runtime cost
    from core.ports import TasksOperations           # Protocol for IDE
    from services_bootstrap import Services              # Concrete for wiring

class MyMixin:
    if TYPE_CHECKING:
        driver: AsyncDriver          # ✅ typed for mypy, zero runtime overhead
        logger: logging.Logger       # ✅ stdlib — no circular import risk
```

The `if TYPE_CHECKING:` block runs ONLY during static analysis, never at runtime.
This is how SKUEL achieves protocol compliance checking in mixins without
paying any runtime cost.

---

## Identity NewTypes

**Principle:** "A user UID is not an entity UID — the type system enforces this"

`UserUID` and `EntityUID` are `NewType` wrappers over `str` that prevent accidental mixing
of user identifiers with entity identifiers. They are propagated across the entire codebase:

```python
from core.models.type_hints import UserUID, EntityUID

# Protocols, services, backends, routes all use typed UIDs:
async def verify_ownership(self, uid: str, user_uid: UserUID) -> Result[T]: ...
async def get_cross_domain_context(self, entity_uid: EntityUID) -> Result[dict]: ...

# Auth boundary creates UserUID:
user_uid: UserUID = require_authenticated_user(request)  # Returns UserUID

# Dataclass defaults use type: ignore for frozen pattern:
user_uid: UserUID = ""  # type: ignore[assignment]
```

**Coverage:** ~1,930 `UserUID` annotations across 313 files; ~200 `EntityUID` annotations. Variant names (`other_user_uid`, `parent_entity_uid`, `source_entity_uid`) also use the typed versions. All layers enforce `UserUID` — auth boundaries, REST routes, service facades, backends, and ingestion defaults.

**See:** `docs/architecture/TYPE_SAFETY_DESIGN_PHILOSOPHY.md` (why), `docs/patterns/AUTH_PATTERNS.md` (auth boundary)

---

## Enum-YAML Foundation

Enums don't just enforce code boundaries — they define the vocabulary that content authors use in YAML templates. When an author writes `priority: medium` in a YAML file, that value is validated against the `Priority` enum during ingestion. The chain is unbroken: YAML field value → `detector.py` → `preparer.py` → Pydantic validation → enum member → frozen dataclass → Neo4j property.

This means the type safety system extends beyond code into content authoring. A typo in a YAML template produces a Pydantic validation error, not a silent bad value in the database.

**87 enum classes** across 17 files in `core/models/enums/` define SKUEL's complete vocabulary. **See:** [Enum Architecture](../architecture/ENUM_ARCHITECTURE.md) for the full catalog and the enum-YAML field mapping.

---

## Quick Reference

| Need | Use |
|------|-----|
| User identifier | `UserUID` (from `core.models.type_hints`) |
| Entity identifier | `EntityUID` (from `core.models.type_hints`) |
| Neo4j node property dict | `Neo4jProperties` (from `core.models.type_hints`) |
| Search/filter parameters | `FilterParams` (from `core.models.type_hints`) |
| Relationship edge properties | `RelationshipMetadata` (from `core.ports.base_protocols`) |
| FastHTML `rt` decorator | `RouteDecorator` (from `adapters.inbound.fasthtml_types`) |
| FastHTML `app` object | `FastHTMLApp` (from `adapters.inbound.fasthtml_types`) |
| Request object (lightweight) | `Request` (from `adapters.inbound.fasthtml_types`) |
| Generic callable (typed) | `EntityFilter[T]`, `Validator[T]`, `Scorer[T]` |
| Protocol return type | Specific model or TypedDict from `core.ports.query_types` |
| Permanent Any boundary | Add `# boundary: reason` comment |
| Service in route signature | Protocol from `core.ports.*` (never concrete class) |
| Domain model | Frozen `@dataclass(frozen=True)` subclassing `Entity` |
| New entity type | `UniversalNeo4jBackend[YourType]` — no new backend needed |
