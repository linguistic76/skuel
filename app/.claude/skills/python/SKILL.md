---
name: python
description: Expert guide to Python development patterns in SKUEL. Use when writing Python code, implementing services, working with type hints, async/await patterns, Result[T] error handling, Pydantic models, frozen dataclasses, protocols, or when the user mentions Python, typing, services, or asks about SKUEL's Python architecture.
allowed-tools: Read, Grep, Glob
---

# Python Development Patterns for SKUEL

## Core Philosophy

> "Type safety as translation - types encode domain language into compiler-verifiable structure"

SKUEL runs on Python 3.14 (pinned in `.python-version`) with strict typing, protocol-based architecture, and Result-based error handling. The goal: code that reads like documentation and fails fast when contracts are violated.

## Quick Reference

| Pattern | Location | Purpose |
|---------|----------|---------|
| **Result[T]** | `/core/utils/result_simplified.py` | Error handling without exceptions |
| **Protocols** | `core/ports/` | Interface contracts |
| **Frozen Dataclasses** | Domain models | Immutable business entities |
| **Pydantic Models** | API boundaries | Validation & serialization |
| **DTOs** | Transfer layer | Mutable data movement |

## Three-Tier Type System

SKUEL separates types by responsibility:

```python
# Tier 1: External (Pydantic) - validation at the edge
# core/models/task/task_request.py
class TaskCreateRequest(CreateRequestBase):
    title: str = Field(min_length=1, max_length=200)
    description: str | None = Field(default=None)
    due_date: date | None = Field(default=None)
    priority: Priority = Field(default=Priority.MEDIUM)


# Tier 2: Transfer (DTO) - mutable data movement
# core/models/task/task_dto.py
@dataclass
class TaskDTO(UserOwnedDTO):
    due_date: date | None = None


# Tier 3: Core (frozen dataclass) - immutable business logic
# core/models/task/task.py
@dataclass(frozen=True, kw_only=True)
class Task(UserOwnedEntity):
    due_date: date | None = None

    def is_overdue(self) -> bool:
        """Business logic in the domain model. "Today" is today in a zone."""
        if self.is_completed or not self.due_date:
            return False
        return self.due_date < today_in(current_zone())
```

### Key Rules

1. **Pydantic at edges** - HTTP requests; a rejected body is a **400** (`ErrorCategory.VALIDATION`), not 422
2. **DTOs for transfer** - Between layers
3. **Frozen for business logic** - Domain models are immutable
4. **A node map becomes a model through a converter** - `from_neo4j_node` (`adapters/persistence/neo4j/neo4j_mapper.py`) or `DTO.from_dict` / `to_domain_model` (`core/utils/dto_converters.py`), never `Model(**props)`: nodes carry undeclared bookkeeping keys (`embedding_version`, `embedding_text_hash`, …) and a splat raises on the first one

**See:** `/docs/patterns/three_tier_type_system.md`

## Result[T] Error Handling

SKUEL uses `Result[T]` internally, converting to HTTP at boundaries. Full pattern: `@result-pattern`.

### Basic Usage

```python
from core.utils.result_simplified import Errors, Result

# Success
result = Result.ok(task)

# Failure — every Errors factory returns an ErrorContext; Result.fail wraps it
result = Result.fail(Errors.not_found("Task", uid))

# Propagating a failure across type boundaries
if result.is_error:
    return Result.fail(result)

task = result.value  # Access success value
```

### Error Factory (Errors)

```python
Errors.not_found("Task", uid)                             # resource, identifier
Errors.validation("Title is required", field="title")     # message, field
Errors.database("create_task", "Query failed")            # operation, message
Errors.business("no_dependents", "Cannot delete task with dependents")  # rule, message
```

### Service Pattern

```python
async def get(self, uid: str) -> Result[Task]:
    result = await self.backend.get(uid)       # Result[Task | None]
    if result.is_error:
        return Result.fail(result)             # propagate across type boundaries
    if result.value is None:
        return Result.fail(Errors.not_found("Task", uid))
    return Result.ok(result.value)
```

### Boundary Handler

```python
# adapters/inbound/pathways_api.py
from adapters.inbound.boundary import boundary_handler
from adapters.inbound.fasthtml_types import Request

@rt("/api/pathways/steps")
@boundary_handler()  # Converts Result[T] to an HTTP response
async def get_path_steps_route(request: Request, path_uid: str) -> Result[list[PathStep]]:
    """Get all steps for a learning path."""
    return await learning_service.get_path_steps(path_uid)
```

An `ok` becomes a JSON 200 (or the decorator's `success_status`); a failure becomes the
status its `ErrorCategory` maps to (`status_for_error`: VALIDATION 400, NOT_FOUND 404,
BUSINESS 422, …) with internal details stripped.

In a route, `require_found(result, "Task", uid)` (`adapters/inbound/result_helpers.py`) collapses the propagate + `None`→404 + narrowing steps into one call. It is adapters-side only — `core/` cannot import `adapters/` (SKUEL022), so services spell the steps out as above.

## Protocol-Based Architecture

Services depend on protocols, not implementations.

### Defining Protocols

Protocols live in `core/ports/`. A domain backend protocol composes the ISP slices:

```python
# core/ports/domain_protocols.py
class TasksOperations(
    BackendOperations["Task"], GraphRelationshipOperations, HierarchyOperations, Protocol
):
    """Core task management operations."""
```

### Using Protocols

`self.backend` in `core/` must name a `core/ports` protocol — SKUEL023 rejects a concrete adapter class, `Any`, and no annotation. Parameterise the base: a class that inherits `backend` from a bare `BaseService` (or `BaseService[Any, ...]`) is flagged too, and annotating the `__init__` parameter does **not** fix it, because the attribute's type comes from the base.

```python
# core/services/ku/ku_core_service.py
class KuCoreService(BaseService[BackendOperations[Ku], Ku]):
    ...
```

Facades (Tasks, Goals, Habits, Events, Choices, Principles, KU, PS, LP) are concrete to their *callers* — a route takes `TasksService`, not a protocol — but inside them `self.backend` is still a protocol.

### ISP-Compliant Protocols

Depend on the narrowest slice you use:

```python
from core.ports import (
    CrudOperations,              # create, get, get_many, update, delete, list, ...
    EntitySearchOperations,      # find_by, count, text_search_raw, ...
    RelationshipCrudOperations,  # add_relationship, ... (edge CRUD)
)

# core/services/relationship_builder.py — needs only edge CRUD
def relate(backend: RelationshipCrudOperations, source_uid: str) -> _EdgeAwaitingType: ...
```

**See:** `/docs/patterns/protocol_architecture.md`, `/docs/patterns/BACKEND_OPERATIONS_ISP.md`

## Async/Sync Design

**Rule:** If you need `await` inside the function, make it `async def`. Otherwise use `def`.

```python
# GOOD: async for I/O operations
async def get_task(self, uid: str) -> Result[Task]:
    return await self.backend.get(uid)

# GOOD: sync for pure computation
def to_numeric(self) -> int:
    return _PRIORITY_NUMERIC_VALUES[self]

# BAD: async without await (SKUEL029)
async def format_title(title: str) -> str:  # Should be sync!
    return title.strip().title()
```

### Layer Guidelines

| Layer | Async | Sync |
|-------|-------|------|
| Database/Persistence | 100% | 0% |
| Service Layer | ~95% | ~5% |
| Data Conversion | 0% | 100% |
| Domain Models | 0% | 100% |
| Utilities | ~5% | ~95% |

## Dynamic Enum Pattern

Enums contain presentation logic (colors, sort order):

```python
# core/models/enums/activity_enums.py
class Priority(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"

    def to_numeric(self) -> int:
        """LOW=1, MEDIUM=2, HIGH=3."""
        return _PRIORITY_NUMERIC_VALUES[self]

    def get_color(self) -> str:
        """Presentation logic in the enum."""
        colors = {
            Priority.LOW: "#10B981",
            Priority.MEDIUM: "#3B82F6",
            Priority.HIGH: "#F59E0B",
        }
        return colors.get(self, "#6B7280")
```

### Enum Usage

```python
# Compare against members, not strings (SKUEL014)
if task.status == EntityStatus.COMPLETED:  # GOOD
    ...
if task.status == "completed":             # BAD
    ...

# Use .value only at boundaries (serialization)
json_data = {"status": task.status.value}

# Models are frozen — "changing" a field builds a copy
updated = replace(task, status=EntityStatus.ACTIVE)
```

## Frozen Dataclass Patterns

### Basic Pattern

```python
from dataclasses import dataclass, field

# core/models/entity.py
@dataclass(frozen=True, kw_only=True)
class Entity:
    uid: EntityUID
    title: str
    tags: tuple[str, ...] = ()  # immutable default


# core/models/ku/ku.py
@dataclass(frozen=True, kw_only=True)
class Ku(Entity):
    aliases: tuple[str, ...] = field(default_factory=tuple)  # alternative names
```

`kw_only=True` lets a subclass declare required fields after the base's defaulted ones. A
default is shared by every instance, so it must be immutable — a tuple, not a list; a
mutable value (a dict, a list) takes `field(default_factory=...)` so each instance gets its
own.

### Defaults That Depend on Another Field

When a default depends on another field, declare it `None` and fill it in `__post_init__` — `object.__setattr__` is the one way to set a field on a frozen instance during initialization:

```python
# core/models/entity.py
    status: EntityStatus = None  # type: ignore[assignment]  # Set in __post_init__ (depends on entity_type)

    def __post_init__(self) -> None:
        if self.status is None:
            object.__setattr__(self, "status", self.entity_type.default_status())
        # Deep immutability: wrap the mutable dict in a read-only proxy
        if isinstance(self.metadata, dict):
            object.__setattr__(self, "metadata", MappingProxyType(self.metadata))
```

Subclasses call `super().__post_init__()` to chain initialization through the hierarchy.

### Immutable Updates

```python
from dataclasses import replace

# Create modified copy
updated_task = replace(task, status=EntityStatus.COMPLETED)
```

## Common Patterns

### Service Composition

Composition happens once, in `services_bootstrap/` (`compose_services()` in `compose.py`). Backends are built in `_backends.py`, with the domain label plus the universal `:Entity` label:

```python
# services_bootstrap/_backends.py
tasks_backend = TasksBackend(
    driver,
    NeoLabel.TASK,
    Task,
    prometheus_metrics=prometheus_metrics,
    base_label=NeoLabel.ENTITY,
)
```

Facades are then constructed with their backend (typed against its protocol) plus their explicit dependencies — see `services_bootstrap/_activity_services.py`.

### Ownership Verification

```python
# core/services/mixins/crud_operations_mixin.py
async def update_for_user(self, uid: str, updates: U, user_uid: UserUID) -> Result[T]:
    # Verify ownership first — not owned is NotFound, not Forbidden
    ownership_result = await self.verify_ownership(uid, user_uid)
    if ownership_result.is_error:
        return ownership_result

    # Domain-specific validation hook
    validation = self._validate_update(ownership_result.value, updates)
    if validation.is_error:
        return Result.fail(validation)

    # Materialize the typed update value (ADR-066) at the single persistence seam
    return await self.backend.update(uid, updates.to_changes())
```

A write that changes a status goes through `backend.update_with_status_guard` instead (ADR-087).

### Logging

```python
from core.utils.logging import get_logger

logger = get_logger("skuel.services.tasks")

result = await self.backend.create(task)
if result.is_error:
    logger.error("Task creation failed: %s", result.expect_error().message)
```

## Anti-Patterns to Avoid

### 1. Don't Use Exceptions for Control Flow

```python
# BAD
try:
    task = await service.get(uid)
except TaskNotFoundError:
    return None

# GOOD
result = await service.get(uid)
if result.is_error:
    return None
```

### 2. Don't Use hasattr() in Production

```python
# BAD (SKUEL011 violation)
if hasattr(obj, "status"):
    return obj.status

# GOOD
if isinstance(obj, Task):
    return obj.status
```

### 3. Don't Use Lambda

```python
# BAD (SKUEL012 violation)
sorted_tasks = sorted(tasks, key=lambda t: t.due_date)

# GOOD
def get_due_date(task: Task) -> date:
    return task.due_date or date.max

sorted_tasks = sorted(tasks, key=get_due_date)
```

### 4. Don't Use String Relationship Names

```python
# BAD (SKUEL013 violation)
await backend.add_relationship(task_uid, ku_uid, "APPLIES_KNOWLEDGE")

# GOOD — the fluent front door (core/services/relationship_builder.py):
# source and target cannot be swapped, and the edge type is the enum
from core.models.relationship_names import RelationshipName

await (
    relate(self.backend, task.uid)
    .via(RelationshipName.APPLIES_KNOWLEDGE)
    .to(ku.uid)
    .create()
)
```

Cypher lives only in `adapters/persistence/neo4j/` (SKUEL021). There, interpolate the enum and escape the braces:

```python
query = f"""
MATCH (parent:Entity {{uid: $uid}})-[:{RelationshipName.HAS_SUBTASK.value}]->(child)
RETURN child
"""
```

### 5. Don't Check .is_err (Use .is_error)

```python
# BAD (SKUEL003 violation)
if result.is_err:
    return result

# GOOD
if result.is_error:
    return result
```

## Type Hints Best Practices

### Use Modern Syntax

```python
# Built-in generics and | unions
def process(items: list[str]) -> dict[str, int]: ...
def maybe_get(uid: str) -> Task | None: ...

# Avoid older typing module equivalents
from typing import List, Dict, Optional  # Don't use these
```

Never quote an annotation — UP037 is live, and PEP 649 defers evaluation, so `Task | None` works even for a `TYPE_CHECKING`-only name.

### Generic Types

SKUEL's core generics use PEP 695 syntax:

```python
class Result[T]: ...                                          # core/utils/result_simplified.py
class CrudOperations[T: "DomainModelProtocol"](Protocol): ...  # core/ports/base_protocols.py
def require_found[T](result: Result[T | None], resource: str, identifier: str) -> Result[T]: ...
```

Older modules still use `TypeVar` + `Generic[T]`; both forms pass the lint (UP046/UP047 are ignored).

### Callable Types

```python
from collections.abc import Callable, Awaitable

# Sync callback
FilterFunc = Callable[[Task], bool]

# Async callback
AsyncProcessor = Callable[[Task], Awaitable[Result[Task]]]
```

## Testing Patterns

### Testing with Result[T]

```python
from core.utils.result_simplified import ErrorCategory

async def test_get_task_success(tasks_service, sample_task):
    result = await tasks_service.get(sample_task.uid)

    assert not result.is_error
    assert result.value.uid == sample_task.uid

async def test_get_task_not_found(tasks_service):
    result = await tasks_service.get("task_missing")

    assert result.is_error
    assert result.expect_error().category == ErrorCategory.NOT_FOUND
```

`asyncio_mode = "auto"` is set in `pyproject.toml`, so async tests need no `@pytest.mark.asyncio`. Fixtures, mock backends and TestContainers: `@pytest`.

## Additional Resources

- [QUICK_REFERENCE.md](QUICK_REFERENCE.md) - Canonical shapes and pitfalls
- [type-hints-reference.md](type-hints-reference.md) - Complete typing patterns
- [async-patterns.md](async-patterns.md) - Async/await best practices
- [testing-guide.md](testing-guide.md) - Testing patterns

## Related Skills

- **[result-pattern](../result-pattern/SKILL.md)** - Error handling pattern used throughout Python services
- **[pydantic](../pydantic/SKILL.md)** - Validation layer (Tier 1 of three-tier type system)
- **[pytest](../pytest/SKILL.md)** - Testing patterns for Python services

## Foundation

This skill has no prerequisites. It is a foundational pattern.

## See Also

- `/docs/patterns/ERROR_HANDLING.md` - Result[T] pattern details
- `/docs/patterns/protocol_architecture.md` - Protocol-based architecture
- `/docs/patterns/three_tier_type_system.md` - Complete type system documentation
- `/docs/patterns/ASYNC_SYNC_DESIGN_PATTERN.md` - Async/sync patterns
