---
name: python
description: Expert guide to Python development patterns in SKUEL. Use when writing Python code, implementing services, working with type hints, async/await patterns, Result[T] error handling, Pydantic models, frozen dataclasses, protocols, or when the user mentions Python, typing, services, or asks about SKUEL's Python architecture.
allowed-tools: Read, Grep, Glob
---

# Python Development Patterns for SKUEL

## Core Philosophy

> "Type safety as translation - types encode domain language into compiler-verifiable structure"

SKUEL uses modern Python (3.11+) with strict typing, protocol-based architecture, and Result-based error handling. The goal: code that reads like documentation and fails fast when contracts are violated.

## Quick Reference

| Pattern | Location | Purpose |
|---------|----------|---------|
| **Result[T]** | `core/result.py` | Error handling without exceptions |
| **Protocols** | `core/services/protocols/` | Interface contracts |
| **Frozen Dataclasses** | Domain models | Immutable business entities |
| **Pydantic Models** | API boundaries | Validation & serialization |
| **DTOs** | Transfer layer | Mutable data movement |

## Three-Tier Type System

SKUEL separates types by responsibility:

```python
# Tier 1: External (Pydantic) - Validation & serialization
from pydantic import BaseModel

class TaskCreateRequest(BaseModel):
    title: str
    description: str | None = None
    priority: str = "medium"


# Tier 2: Transfer (DTO) - Mutable data movement
from dataclasses import dataclass

@dataclass
class TaskDTO:
    uid: str
    title: str
    description: str | None
    priority: str
    status: str


# Tier 3: Core (Frozen Dataclass) - Immutable business logic
from dataclasses import dataclass, field
from datetime import datetime

@dataclass(frozen=True)
class Task:
    uid: str
    title: str
    priority: Priority
    status: ActivityStatus
    created_at: datetime = field(default_factory=datetime.now)

    def is_overdue(self, now: datetime) -> bool:
        """Business logic in domain model"""
        return self.due_date is not None and self.due_date < now
```

### Key Rules

1. **Pydantic at edges** - HTTP requests/responses
2. **DTOs for transfer** - Between layers
3. **Frozen for business logic** - Domain models are immutable

## Result[T] Error Handling

SKUEL uses `Result[T]` internally, converting to HTTP at boundaries.

### Basic Usage

```python
from core.result import Result

# Success
result = Result.ok(task)

# Failure
result = Result.fail(Errors.not_found("Task", uid))

# Checking results
if result.is_error:
    return result  # Propagate error

task = result.value  # Access success value
```

### Error Factory (Errors)

```python
from core.errors import Errors

# Use factory methods for typed errors
return Errors.not_found("Task", uid)
return Errors.validation("Title is required")
return Errors.database("Connection failed")
return Errors.business("Cannot delete task with dependents")
```

### Service Pattern

```python
from core.result import Result
from core.errors import Errors

class TasksService:
    async def get(self, uid: str) -> Result[Task]:
        entity = await self.backend.get(uid)
        if entity is None:
            return Errors.not_found("Task", uid)
        return Result.ok(entity)

    async def create(self, data: TaskCreateRequest) -> Result[Task]:
        # Validation
        if not data.title:
            return Errors.validation("Title is required")

        # Business logic
        task = await self.backend.create(data.model_dump())
        return Result.ok(task)
```

### Boundary Handler

```python
from core.http import boundary_handler

@rt("/api/tasks/{uid}")
@boundary_handler()  # Converts Result[T] to HTTP responses
async def get_task(request, uid: str):
    return await service.get(uid)  # Returns Result[Task]
```

## Protocol-Based Architecture

Services depend on protocols, not implementations.

### Defining Protocols

```python
from typing import Protocol
from core.result import Result

class TasksOperations(Protocol):
    """Protocol for task operations"""

    async def get(self, uid: str) -> Result[Task | None]: ...
    async def create(self, data: dict) -> Result[Task]: ...
    async def update(self, uid: str, data: dict) -> Result[Task]: ...
    async def delete(self, uid: str) -> Result[bool]: ...
```

### Using Protocols

```python
class TasksService:
    def __init__(self, backend: TasksOperations) -> None:
        self.backend = backend  # Depends on protocol

    async def get(self, uid: str) -> Result[Task]:
        result = await self.backend.get(uid)
        if result.is_error:
            return result
        if result.value is None:
            return Errors.not_found("Task", uid)
        return Result.ok(result.value)
```

### ISP-Compliant Protocols

Use focused sub-protocols when you don't need all operations:

```python
from core.services.protocols import (
    CrudOperations,        # create, get, update, delete, list
    EntitySearchOperations, # search, find_by, count
    RelationshipOperations, # add/delete relationships
)

class ReadOnlyService:
    def __init__(self, backend: CrudOperations[Task]) -> None:
        self.backend = backend  # Only needs CRUD subset
```

## Async/Sync Design

**Rule:** If you need `await` inside the function, make it `async def`. Otherwise use `def`.

```python
# GOOD: async for I/O operations
async def get_task(self, uid: str) -> Result[Task]:
    return await self.backend.get(uid)

# GOOD: sync for pure computation
def calculate_priority_score(task: Task) -> float:
    return task.urgency * task.importance

# BAD: async without await
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

Enums contain presentation logic (colors, icons):

```python
from enum import Enum

class Priority(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    URGENT = "urgent"

    def get_color(self) -> str:
        """Presentation logic in enum"""
        colors = {
            Priority.LOW: "gray",
            Priority.MEDIUM: "blue",
            Priority.HIGH: "orange",
            Priority.URGENT: "red",
        }
        return colors[self]

    def get_sort_order(self) -> int:
        """Sort weight for ordering"""
        return list(Priority).index(self)
```

### Enum Usage

```python
# Use enum members, not strings
task.priority = Priority.HIGH  # GOOD
task.priority = "high"         # BAD

# Use .value only at boundaries (serialization)
json_data = {"priority": task.priority.value}

# Type-safe comparisons
if task.priority == Priority.URGENT:
    send_notification(task)
```

## Frozen Dataclass Patterns

### Basic Pattern

```python
from dataclasses import dataclass, field
from datetime import datetime

@dataclass(frozen=True)
class Task:
    uid: str
    title: str
    priority: Priority
    status: ActivityStatus = ActivityStatus.PENDING
    created_at: datetime = field(default_factory=datetime.now)
```

### Dynamic Defaults with __post_init__

```python
@dataclass(frozen=True)
class Task:
    uid: str
    title: str
    normalized_title: str = field(init=False)

    def __post_init__(self) -> None:
        # Use object.__setattr__ for frozen dataclass
        object.__setattr__(self, "normalized_title", self.title.lower().strip())
```

### Immutable Updates

```python
from dataclasses import replace

# Create modified copy
updated_task = replace(task, status=ActivityStatus.COMPLETED)
```

## Common Patterns

### Service Composition

```python
# Services bootstrap in compose_services()
async def compose_services(driver: Driver) -> Result[Services]:
    # Create backends
    tasks_backend = UniversalNeo4jBackend[Task](driver, "Task", Task)
    goals_backend = UniversalNeo4jBackend[Goal](driver, "Goal", Goal)

    # Create services with protocol dependencies
    tasks_service = TasksService(tasks_backend)
    goals_service = GoalsService(goals_backend)

    return Result.ok(Services(
        tasks=tasks_service,
        goals=goals_service,
    ))
```

### Ownership Verification

```python
async def update(
    self,
    uid: str,
    data: dict,
    user_uid: str
) -> Result[Task]:
    # Verify ownership first
    ownership = await self.verify_ownership(uid, user_uid)
    if ownership.is_error:
        return ownership  # Returns NotFound, not Forbidden

    return await self.backend.update(uid, data)
```

### Logging

```python
from core.utils.logging import get_logger

logger = get_logger("skuel.services.tasks")

async def create(self, data: dict) -> Result[Task]:
    logger.info("Creating task", title=data.get("title"))

    result = await self.backend.create(data)
    if result.is_error:
        logger.error("Task creation failed", error=str(result.error))

    return result
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
sorted_tasks = sorted(tasks, key=lambda t: t.priority)

# GOOD
def get_priority(task: Task) -> int:
    return task.priority.get_sort_order()

sorted_tasks = sorted(tasks, key=get_priority)
```

### 4. Don't Use String Relationship Names

```python
# BAD (SKUEL013 violation)
await backend.add_relationship(task_uid, "APPLIES_KNOWLEDGE", ku_uid)

# GOOD
from core.models.relationship_names import RelationshipName

await backend.add_relationship(
    task_uid,
    RelationshipName.APPLIES_KNOWLEDGE,
    ku_uid
)
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
# Python 3.10+ syntax (preferred)
def process(items: list[str]) -> dict[str, int]: ...
def maybe_get(uid: str) -> Task | None: ...

# Avoid older typing module equivalents
from typing import List, Dict, Optional  # Don't use these
```

### Generic Type Variables

```python
from typing import TypeVar, Generic

T = TypeVar("T")

class Repository(Generic[T]):
    async def get(self, uid: str) -> Result[T | None]: ...
    async def create(self, data: dict) -> Result[T]: ...
```

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
import pytest
from core.result import Result

async def test_get_task_success(tasks_service, sample_task):
    result = await tasks_service.get(sample_task.uid)

    assert not result.is_error
    assert result.value.uid == sample_task.uid
    assert result.value.title == sample_task.title

async def test_get_task_not_found(tasks_service):
    result = await tasks_service.get("nonexistent")

    assert result.is_error
    assert "not found" in str(result.error).lower()
```

### Protocol Mocking

```python
from unittest.mock import AsyncMock

async def test_service_with_mock_backend():
    # Create mock that satisfies protocol
    mock_backend = AsyncMock()
    mock_backend.get.return_value = Result.ok(sample_task)

    service = TasksService(mock_backend)
    result = await service.get("test-uid")

    assert result.value == sample_task
    mock_backend.get.assert_called_once_with("test-uid")
```

## Additional Resources

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
