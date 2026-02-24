---
title: Protocol Definition Template
updated: 2026-01-24
status: current
category: reference
tags: [definition, protocol, reference]
related: []
---

# Protocol Definition Template

**Created:** 2025-10-17
**Updated:** 2026-01-24
**Status:** active
**Audience:** developers

## Quick Reference

Template for defining protocol interfaces in SKUEL's Protocol-Based Architecture.

## Template

```python
from typing import Protocol, Optional, List, Any
from core.utils.result import Result

class SomeOperations(Protocol):
    """
    Protocol for [domain] backend operations.

    Protocols define contracts between services and backends.
    Implementations must provide all methods defined here.

    Usage:
        class ConcreteBackend(SomeOperations):
            async def create(self, data: Any) -> Result[Any]:
                # Implementation details
                ...

        service = SomeService(backend=ConcreteBackend())
    """

    async def create(self, data: Any) -> Result[Any]:
        """
        Create an entity.

        Args:
            data: Entity data to create

        Returns:
            Result[Any]: Success with created entity or failure with error
        """
        ...

    async def get(self, uid: str) -> Result[Optional[Any]]:
        """
        Get entity by UID.

        Args:
            uid: Entity unique identifier

        Returns:
            Result[Optional[Any]]: Success with entity (or None if not found)
                                  or failure with error
        """
        ...

    async def list(self, limit: int = 100) -> Result[List[Any]]:
        """
        List entities.

        Args:
            limit: Maximum number of entities to return (default 100)

        Returns:
            Result[List[Any]]: Success with entity list or failure with error
        """
        ...

    async def update(self, uid: str, data: Any) -> Result[Any]:
        """
        Update entity.

        Args:
            uid: Entity unique identifier
            data: Updated entity data

        Returns:
            Result[Any]: Success with updated entity or failure with error
        """
        ...

    async def delete(self, uid: str) -> Result[bool]:
        """
        Delete entity.

        Args:
            uid: Entity unique identifier

        Returns:
            Result[bool]: Success (True) or failure with error
        """
        ...
```

## Facade Service Type Hints (February 2026)

> **Note:** `facade_protocols.py` and `FacadeDelegationMixin` are deleted. Facade services now have explicit `async def` delegation methods. Route files import the concrete service class.

**Pattern:** Import the concrete service class under `TYPE_CHECKING`:

```python
from typing import TYPE_CHECKING, Any
from core.utils.result import Result

if TYPE_CHECKING:
    from core.models.tasks.task import Task
    from core.services.tasks_service import TasksService  # Concrete class

async def analyze_tasks(service: "TasksService") -> dict:
    """
    Route function that uses TasksService.
    MyPy sees all explicit methods on TasksService directly.
    """
    result = await service.get_task(uid)
    if result.is_error:
        return {}
    return {"task": result.value}
```

**Key Differences from Domain Protocols:**

| Aspect | Domain Protocol (TasksOperations) | Facade Service (TasksService) |
|--------|-----------------------------------|-------------------------------|
| **Purpose** | Service implementation contract | Facade aggregating sub-services |
| **Inheritance** | ✅ Implement in backend classes | ✅ Import as `TYPE_CHECKING` hint |
| **Return Types** | `Result[T]` | `Result[T]` (same) |
| **Location** | `/core/ports/domain_protocols.py` | `/core/services/tasks_service.py` |
| **Method visibility** | Defined in Protocol | Explicit `async def` on class |

**Adding delegation methods:**

```python
# In core/services/tasks_service.py — add one line per delegated method
async def some_method(self, *args: Any, **kwargs: Any) -> Any:
    return await self.core.some_method(*args, **kwargs)
```

## Key Patterns

### 1. Protocol Naming Convention
```python
class SomeOperations(Protocol):
    # Suffix with "Operations" for backend protocols
```

**Examples:**
- `KnowledgeOperations` - Knowledge backend operations
- `TaskOperations` - Task backend operations
- `SearchOperations` - Search operations

### 2. Return Result[T]
```python
async def get(self, uid: str) -> Result[Optional[Any]]:
    # ALL protocol methods return Result[T]
```

**Never return bare values:**
```python
# ❌ WRONG
async def get(self, uid: str) -> Optional[Any]:

# ✅ CORRECT
async def get(self, uid: str) -> Result[Optional[Any]]:
```

### 3. Docstrings Required
```python
async def create(self, data: Any) -> Result[Any]:
    """
    Create an entity.

    Args:
        data: Entity data to create

    Returns:
        Result[Any]: Success with created entity or failure with error
    """
    ...
```

**Rationale:** Protocols are contracts - documentation clarifies expectations.

### 4. Use ... for Protocol Bodies
```python
async def create(self, data: Any) -> Result[Any]:
    """Create an entity."""
    ...  # Ellipsis indicates protocol method (not implementation)
```

## Protocol Organization

**Location:** `/core/ports/`

```
core/ports/
├── domain_protocols.py      # Business domain operations
│   ├── TaskOperations
│   ├── EventOperations
│   └── HabitOperations
├── knowledge_protocols.py   # Knowledge management
│   ├── KnowledgeOperations
│   └── LearningPathOperations
├── search_protocols.py      # Search operations
│   └── SearchOperations
└── infrastructure_protocols.py  # System & infrastructure
    ├── EmbeddingsOperations
    └── AnalyticsOperations
```

## Implementation Example

```python
# Protocol definition
class TaskOperations(Protocol):
    async def create(self, task: Task) -> Result[Task]:
        ...

# Concrete implementation
class TaskUniversalBackend(UniversalNeo4jBackend[Task], TaskOperations):
    """
    Implements TaskOperations protocol using UniversalNeo4jBackend.
    """

    async def create(self, task: Task) -> Result[Task]:
        """Create task in Neo4j."""
        # Implementation details using UniversalNeo4jBackend
        return await super().create(task)

# Service dependency injection
class TasksService:
    def __init__(self, backend: TaskOperations):
        """
        Depends on TaskOperations protocol, not concrete backend.
        """
        self.backend = backend
```

## Type Checking

**MyPy validation:**
```python
# MyPy checks that implementation satisfies protocol
class ConcreteBackend(SomeOperations):
    # MyPy error if missing methods or wrong signatures
    async def create(self, data: Any) -> Result[Any]:
        ...
```

## Related Documentation

- [Protocol-Based Architecture](/home/mike/0bsidian/skuel/docs/architecture/protocol_based_architecture.md)
- [ADR-001: Why Protocols?](/home/mike/0bsidian/skuel/docs/archive/decisions/ADR-001_why_protocols.md)
- [Service Creation Template](/home/mike/0bsidian/skuel/docs/reference/templates/service_creation.md)

## Examples

**Real protocol definitions:**
- `/core/ports/domain_protocols.py`
- `/core/ports/knowledge_protocols.py`
- `/core/ports/search_protocols.py`
