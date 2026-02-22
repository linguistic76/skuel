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

## Facade Protocol Template

**Location:** `/core/ports/facade_protocols.py`
**Purpose:** Type hints for dynamically delegated facade methods
**Use Case:** Services using `FacadeDelegationMixin` to auto-generate delegation methods

**⚠️ CRITICAL WARNING:** Facade protocols are for TYPE HINTS on dynamically delegated methods, NOT for inheritance.

```python
from typing import Protocol, runtime_checkable, TYPE_CHECKING
from core.utils.result import Result

if TYPE_CHECKING:
    # Import domain model only during type checking to prevent circular imports
    from core.models.tasks.task import Task

@runtime_checkable
class TasksFacadeProtocol(Protocol):
    """
    Type hints for TasksService delegated methods.

    **WARNING:** This protocol is for TYPE HINTS ONLY, NOT for inheritance.

    TasksService uses FacadeDelegationMixin to dynamically generate delegation
    methods at class definition time. MyPy can't see these dynamic methods,
    so this protocol tells MyPy what methods exist at runtime.

    **CORRECT Usage:**
    ```python
    from typing import TYPE_CHECKING

    if TYPE_CHECKING:
        from core.ports.facade_protocols import TasksFacadeProtocol

    async def analyze_tasks(service: "TasksFacadeProtocol"):
        # Type hint enables MyPy autocomplete for delegated methods
        result = await service.get_task(uid)
    ```

    **INCORRECT Usage (DO NOT DO THIS):**
    ```python
    # ❌ WRONG - Do NOT inherit from facade protocols
    class TasksService(TasksFacadeProtocol, FacadeDelegationMixin):
        # MyPy error: Cannot instantiate abstract class...
        pass
    ```

    **Why NOT to inherit:**
    - MyPy expects explicit implementations when Protocol is a base class
    - Dynamic methods from FacadeDelegationMixin aren't visible to static analysis
    - Results in "Cannot instantiate abstract class" errors
    """

    # ========================================================================
    # DELEGATED METHODS (from TasksCoreService)
    # ========================================================================

    async def get_task(self, uid: str) -> "Result[Task]":
        """Get task by UID (delegated to self.core.get_task)."""
        ...

    async def create_task(self, task_data: dict) -> "Result[Task]":
        """Create task (delegated to self.core.create_task)."""
        ...

    async def update_task(self, uid: str, updates: dict) -> "Result[Task]":
        """Update task (delegated to self.core.update_task)."""
        ...

    async def delete_task(self, uid: str) -> "Result[bool]":
        """Delete task (delegated to self.core.delete_task)."""
        ...

    # ========================================================================
    # DELEGATED METHODS (from TasksSearchService)
    # ========================================================================

    async def search_tasks(self, query: str, filters: dict) -> "Result[list[Task]]":
        """Search tasks (delegated to self.search.search_tasks)."""
        ...

    # ========================================================================
    # DELEGATED METHODS (from TasksIntelligenceService)
    # ========================================================================

    async def analyze_task_completion_impact(self, uid: str) -> "Result[dict]":
        """Analyze impact (delegated to self.intelligence.analyze_task_completion_impact)."""
        ...
```

**Key Differences from Domain Protocols:**

| Aspect | Domain Protocol (TasksOperations) | Facade Protocol (TasksFacadeProtocol) |
|--------|-----------------------------------|---------------------------------------|
| **Purpose** | Service implementation contract | Type hints for delegated methods |
| **Inheritance** | ✅ Implement in backend classes | ❌ NEVER inherit - type hints only |
| **Return Types** | `Result[T]` | `Result[T]` (same) |
| **Decorator** | Optional | `@runtime_checkable` required |
| **Usage** | Backend depends on protocol | Use as parameter type hint with TYPE_CHECKING |
| **Location** | `/core/ports/domain_protocols.py` | `/core/ports/facade_protocols.py` |

**Template Usage Pattern:**

```python
# Step 1: Define the facade protocol (one-time setup)
# File: /core/ports/facade_protocols.py

@runtime_checkable
class SomeFacadeProtocol(Protocol):
    """Type hints for SomeService delegated methods."""
    async def some_method(self, arg: str) -> Result[Any]:
        ...

# Step 2: Use as type hint in consuming code
# Example file location: <your_service_file>.py

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from core.ports.facade_protocols import SomeFacadeProtocol

async def process_something(service: "SomeFacadeProtocol"):
    # MyPy sees delegated methods, IDE provides autocomplete
    result = await service.some_method("value")
    return result.value
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
