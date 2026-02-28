# Type Safety Architecture Overview

*Last updated: 2026-02-28*

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

**Principle:** "Zero concrete dependencies in route signatures"

All services are injected as protocols, not concrete classes:
```python
# Route function — receives protocol, not concrete class
def create_tasks_api_routes(
    app: FastHTMLApp,
    rt: RouteDecorator,
    tasks_service: TasksOperations,      # Protocol — not TasksService
    user_service: UserOperations,         # Protocol — not UserService
) -> RouteList: ...
```

**Why this matters:**
- Routes can't accidentally call internal methods not on the protocol
- Services can be swapped for test doubles without changing route code
- MyPy catches mismatches between what routes call and what protocols declare

**Key numbers (February 2026):**
- 517 `@runtime_checkable` Protocol definitions across 11 files in `core/ports/`
- 100% protocol compliance — all 7 `BaseService` mixins verified by TYPE_CHECKING blocks
- 29 automated compliance tests (run: `poetry run pytest tests/unit/test_protocol_mixin_compliance.py`)
- Zero `Any` fields in the `Services` dataclass — all 72 fields typed

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
backend serves all 15 entity types, constrained by `DomainModelProtocol`.

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
from adapters.inbound.fasthtml_types import RouteDecorator, FastHTMLApp, Request, RouteList
# FastHTML has no type stubs; these Protocols capture what SKUEL actually calls
```

**See:** `docs/patterns/ANY_USAGE_POLICY.md` (complete policy with quick-reference table)

---

## MyPy Configuration Strategy

**Principle:** "Strict where it matters, gradual everywhere else"

SKUEL does NOT run MyPy in strict mode globally. The reason: ~2,200 latent type errors
exist in the service layer from earlier development. Forcing strict mode would make the
checker output unreadable and stall development.

Instead, per-module strictness overrides in `pyproject.toml`:

| Module Group | Strictness | Why |
|--------------|-----------|-----|
| `core.utils.result`, `core.utils.error_boundary` | Strict | Core error-handling infrastructure |
| `core.models.*`, `core.infrastructure.*` | Medium | Domain models must be well-typed |
| `core.services.*` | Gradual | Largest surface area, ongoing improvement |
| `adapters.*` | Gradual | Framework boundaries; `RouteDecorator` protocol handles FastHTML |
| `tests.*` | Lenient | Mocks and fixtures need flexibility |

**Disabled error codes (global):**
- `type-var` — Frozen dataclass + Protocol constraint MyPy limitation
- `assignment` — Frozen dataclass `__post_init__` pattern (see above)
- `arg-type` — Often false positives in framework code

**Ruff enforces annotation discipline:**
- `TCH` rules: correct `TYPE_CHECKING` block usage
- SKUEL linter rules include `SKUEL003` (`.is_error` not `.is_err`)

**See:** `docs/patterns/mypy_pragmatic_strategy.md` (current strategy),
`docs/patterns/MYPY_TYPE_SAFETY_PATTERNS.md` (common error patterns and fixes)

---

## Generic Types

The generic backbone that makes one backend serve 15 entity types:

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

# UniversalNeo4jBackend[T] — one backend, all 15 entity types
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
    from services_bootstrap import Services          # Concrete for wiring

class MyMixin:
    if TYPE_CHECKING:
        driver: AsyncDriver          # ✅ typed for mypy, zero runtime overhead
        logger: logging.Logger       # ✅ stdlib — no circular import risk
```

The `if TYPE_CHECKING:` block runs ONLY during static analysis, never at runtime.
This is how SKUEL achieves protocol compliance checking in mixins without
paying any runtime cost.

---

## Quick Reference

| Need | Use |
|------|-----|
| Neo4j node property dict | `Neo4jProperties` (from `core.models.type_hints`) |
| Search/filter parameters | `FilterParams` (from `core.models.type_hints`) |
| Relationship edge properties | `RelationshipMetadata` (from `core.ports.base_protocols`) |
| FastHTML `rt` decorator | `RouteDecorator` (from `adapters.inbound.fasthtml_types`) |
| FastHTML `app` object | `FastHTMLApp` (from `adapters.inbound.fasthtml_types`) |
| Request object (lightweight) | `Request` (from `adapters.inbound.fasthtml_types`) |
| Generic callable (typed) | `EntityFilter[T]`, `Validator[T]`, `Scorer[T]` |
| Permanent Any boundary | Add `# boundary: reason` comment |
| Service in route signature | Protocol from `core.ports.*` (never concrete class) |
| Domain model | Frozen `@dataclass(frozen=True)` subclassing `Entity` |
| New entity type | `UniversalNeo4jBackend[YourType]` — no new backend needed |
