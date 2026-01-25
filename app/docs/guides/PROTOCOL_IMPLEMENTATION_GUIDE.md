---
title: Protocol Implementation Guide
created: 2026-01-03
updated: 2026-01-03
status: active
audience: developers
tags: [guide, protocols, implementation]
---

# Protocol Implementation Guide

**Last Updated**: January 3, 2026

## Quick Start

This guide shows you how to implement and use protocols in SKUEL. For architecture overview, see [protocol_architecture.md](../patterns/protocol_architecture.md).

## Core Type-Checking Protocols

SKUEL's type-checking protocols live in `core/protocols.py` and eliminate all `hasattr()` usage.

### Timestamp Protocols

Replace `hasattr(obj, 'created_at')` with type-safe protocol checks:

```python
from typing import Protocol, runtime_checkable, Any

@runtime_checkable
class HasCreatedAt(Protocol):
    """Protocol for objects with created_at timestamp."""
    created_at: Any

@runtime_checkable
class HasUpdatedAt(Protocol):
    """Protocol for objects with updated_at timestamp."""
    updated_at: Any

@runtime_checkable
class HasTimestamps(Protocol):
    """Protocol for objects with both created and updated timestamps."""
    created_at: Any
    updated_at: Any
```

**Usage**:
```python
# ❌ OLD - hasattr (runtime only)
if hasattr(obj, 'created_at'):
    use(obj.created_at)

# ✅ NEW - Protocol (compile-time + runtime)
if isinstance(obj, HasCreatedAt):
    use(obj.created_at)  # MyPy knows this is safe
```

### Conversion Protocols

For objects that can be converted to dictionaries:

```python
@runtime_checkable
class PydanticModel(Protocol):
    """Protocol for Pydantic models with model_dump method."""
    def model_dump(self, **kwargs) -> dict[str, Any]: ...

@runtime_checkable
class HasDict(Protocol):
    """Protocol for objects that can be converted to dict."""
    def dict(self) -> dict[str, Any]: ...

@runtime_checkable
class HasToDict(Protocol):
    """Protocol for objects with to_dict method."""
    def to_dict(self) -> dict[str, Any]: ...

@runtime_checkable
class HasNeo4jProperties(Protocol):
    """Protocol for objects that can convert to Neo4j properties."""
    def to_neo4j_properties(self) -> dict[str, Any]: ...
```

**Usage**:
```python
def serialize(obj: Any) -> dict[str, Any]:
    """Serialize object to dictionary."""
    if isinstance(obj, PydanticModel):
        return obj.model_dump()
    elif isinstance(obj, HasToDict):
        return obj.to_dict()
    elif isinstance(obj, HasDict):
        return obj.dict()
    elif isinstance(obj, HasNeo4jProperties):
        return obj.to_neo4j_properties()
    else:
        return {}
```

### Domain-Specific Attribute Protocols

For domain-specific fields:

```python
@runtime_checkable
class HasMetrics(Protocol):
    """Protocol for objects with metrics field."""
    metrics: Any

@runtime_checkable
class HasMasteryLevel(Protocol):
    """Protocol for metrics objects with mastery_level field."""
    mastery_level: Any

@runtime_checkable
class HasTimeSpentMinutes(Protocol):
    """Protocol for metrics objects with time_spent_minutes field."""
    time_spent_minutes: Any
```

**Usage**:
```python
def get_learning_metrics(obj: Any) -> dict[str, Any]:
    """Extract learning metrics if available."""
    if isinstance(obj, HasMetrics) and isinstance(obj.metrics, HasMasteryLevel):
        return {
            "mastery": obj.metrics.mastery_level,
            "time_spent": obj.metrics.time_spent_minutes if isinstance(obj.metrics, HasTimeSpentMinutes) else 0
        }
    return {}
```

### Event & Priority Protocols

For event-related conversions:

```python
@runtime_checkable
class HasToPriority(Protocol):
    """Protocol for priority objects with to_priority method."""
    def to_priority(self) -> Any: ...

@runtime_checkable
class HasToVisibility(Protocol):
    """Protocol for visibility objects with to_visibility method."""
    def to_visibility(self) -> Any: ...

@runtime_checkable
class HasRecurrenceType(Protocol):
    """Protocol for objects with recurrence_type field."""
    recurrence_type: Any

@runtime_checkable
class HasToRecurrencePattern(Protocol):
    """Protocol for objects with to_recurrence_pattern method."""
    def to_recurrence_pattern(self) -> Any: ...
```

## Domain Operation Protocols

Domain operation protocols define business logic interfaces. Located in `core/services/protocols/domain_protocols.py`.

### Example: TasksOperations

```python
from typing import Protocol
from core.models import Task, EntityUID
from core.utils.result_simplified import Result

class TasksOperations(Protocol):
    """Protocol for task backend operations."""

    async def create(self, data: Metadata) -> Result[EntityUID]:
        """Create a new task."""
        ...

    async def get(self, uid: str) -> Result[Optional[Task]]:
        """Get task by UID."""
        ...

    async def update(self, uid: str, updates: Metadata) -> Result[Task]:
        """Update task."""
        ...

    async def delete(self, uid: str) -> Result[None]:
        """Delete task."""
        ...

    async def list(
        self,
        limit: int = 100,
        offset: int = 0,
        order_by: str = "created_at",
        order_desc: bool = True,
    ) -> Result[list[Task]]:
        """List tasks with pagination."""
        ...
```

### Using Domain Protocols in Services

```python
from core.services.protocols import TasksOperations

class TasksService:
    """Tasks business logic service."""

    def __init__(self, backend: TasksOperations):
        """Initialize with protocol-based backend."""
        self.backend = backend  # Type: TasksOperations (protocol)

    async def create_task(self, title: str, user_uid: str) -> Result[Task]:
        """Create a new task."""
        data = {"title": title, "user_uid": user_uid}
        uid_result = await self.backend.create(data)

        if uid_result.is_error:
            return Result.fail(uid_result.error)

        task_result = await self.backend.get(uid_result.value)
        return task_result
```

### Backend Implementation (Duck Typing)

```python
from core.models.query import UniversalNeo4jBackend

# ✅ Backend automatically satisfies TasksOperations through duck typing
tasks_backend = UniversalNeo4jBackend[Task](driver, "Task", Task)

# No explicit inheritance needed - backend has matching methods:
# - async def create(self, data: Metadata) -> Result[EntityUID]
# - async def get(self, uid: str) -> Result[Optional[Task]]
# - async def update(self, uid: str, updates: Metadata) -> Result[Task]
# - async def delete(self, uid: str) -> Result[None]
# - async def list(...) -> Result[list[Task]]

# Service initialization
tasks_service = TasksService(backend=tasks_backend)  # Type-safe!
```

## Breaking Circular Dependencies with Protocols

### The Problem

```python
# ❌ CIRCULAR DEPENDENCY
# File: tasks_service.py
from core.services.user_context_service import UserContextService

class TasksService:
    def __init__(self, context: UserContextService):
        self.context = context

# File: user_context_service.py
from core.services.tasks_service import TasksService

class UserContextService:
    def __init__(self, tasks: TasksService):
        self.tasks = tasks

# Result: TasksService → UserContextService → TasksService ❌
```

### The Solution: Protocol Abstraction

**Step 1**: Create minimal protocol interface

```python
# File: core/services/protocols/domain_protocols.py
from typing import Protocol
from core.utils.result_simplified import Result

class UserContextOperations(Protocol):
    """Minimal protocol for user context operations."""

    async def invalidate_context(self, user_uid: str) -> Result[None]:
        """Invalidate user context cache."""
        ...

    async def get_context(self, user_uid: str) -> Result[dict[str, Any]]:
        """Get user context."""
        ...
```

**Step 2**: Service depends on protocol, not concrete implementation

```python
# File: tasks_service.py
from typing import Optional
from core.services.protocols import UserContextOperations

class TasksService:
    def __init__(
        self,
        backend: TasksOperations,
        context_service: Optional[UserContextOperations] = None  # Protocol!
    ):
        self.backend = backend
        self.context_service = context_service

    async def create_task(self, data: dict) -> Result[Task]:
        """Create task and invalidate context if service available."""
        result = await self.backend.create(data)

        if result.is_ok and self.context_service:
            await self.context_service.invalidate_context(data["user_uid"])

        return result
```

**Step 3**: Wire concrete implementation during bootstrap

```python
# File: services_bootstrap.py
async def compose_services(driver) -> Services:
    """Bootstrap all services."""

    # Create backends
    tasks_backend = UniversalNeo4jBackend[Task](driver, "Task", Task)

    # Create services (no context yet - avoids circular dependency)
    tasks_service = TasksService(backend=tasks_backend, context_service=None)

    # Create context service (depends on tasks)
    user_context_service = UserContextService(tasks=tasks_service, ...)

    # Wire context service back to tasks (post-construction)
    tasks_service.context_service = user_context_service

    return Services(tasks=tasks_service, user_context=user_context_service)
```

**Result**: ✅ No circular dependency
- TasksService → `UserContextOperations` (protocol interface)
- UserContextService → TasksService (concrete implementation)
- No import cycle because protocol is just an interface

## Complete Protocol Examples

### Implementing a New Protocol

**Step 1**: Define the protocol

```python
# File: core/services/protocols/domain_protocols.py
from typing import Protocol
from core.utils.result_simplified import Result

class NotificationOperations(Protocol):
    """Protocol for notification operations."""

    async def send_notification(
        self,
        user_uid: str,
        message: str,
        priority: str = "normal"
    ) -> Result[None]:
        """Send notification to user."""
        ...

    async def get_unread_count(self, user_uid: str) -> Result[int]:
        """Get count of unread notifications."""
        ...
```

**Step 2**: Implement the backend (duck typing)

```python
# File: adapters/persistence/notification_backend.py
from core.utils.result_simplified import Result

class NotificationBackend:
    """Notification backend implementation."""

    async def send_notification(
        self,
        user_uid: str,
        message: str,
        priority: str = "normal"
    ) -> Result[None]:
        """Send notification implementation."""
        # Implementation here
        return Result.ok(None)

    async def get_unread_count(self, user_uid: str) -> Result[int]:
        """Get unread count implementation."""
        # Implementation here
        return Result.ok(5)

# Backend automatically satisfies NotificationOperations protocol!
# No explicit inheritance needed.
```

**Step 3**: Use in service

```python
# File: core/services/notification_service.py
from core.services.protocols import NotificationOperations

class NotificationService:
    """Notification business logic service."""

    def __init__(self, backend: NotificationOperations):
        """Initialize with protocol-based backend."""
        self.backend = backend  # Type-safe!

    async def notify_user(self, user_uid: str, message: str) -> Result[None]:
        """Send notification to user."""
        return await self.backend.send_notification(user_uid, message)
```

## Testing with Protocols

Protocols make testing trivial - just create a simple class that matches the protocol:

```python
# Test file: tests/test_notification_service.py
import pytest
from core.services.notification_service import NotificationService
from core.utils.result_simplified import Result

class MockNotificationBackend:
    """Mock implementation for testing."""

    def __init__(self):
        self.sent_notifications = []

    async def send_notification(
        self,
        user_uid: str,
        message: str,
        priority: str = "normal"
    ) -> Result[None]:
        """Mock send - just track calls."""
        self.sent_notifications.append({
            "user_uid": user_uid,
            "message": message,
            "priority": priority
        })
        return Result.ok(None)

    async def get_unread_count(self, user_uid: str) -> Result[int]:
        """Mock unread count."""
        return Result.ok(0)

@pytest.mark.asyncio
async def test_notify_user():
    """Test notification sending."""
    # Create mock backend (automatically satisfies NotificationOperations!)
    mock_backend = MockNotificationBackend()

    # Create service with mock
    service = NotificationService(backend=mock_backend)

    # Call service method
    result = await service.notify_user("user:123", "Hello!")

    # Assert
    assert result.is_ok
    assert len(mock_backend.sent_notifications) == 1
    assert mock_backend.sent_notifications[0]["message"] == "Hello!"
```

## See Also

- [protocol_architecture.md](../patterns/protocol_architecture.md) - Architecture overview and best practices
- [PORTS_TO_PROTOCOLS_MIGRATION.md](../migrations/PORTS_TO_PROTOCOLS_MIGRATION.md) - Migration history and lessons learned
- [BACKEND_OPERATIONS_ISP.md](../patterns/BACKEND_OPERATIONS_ISP.md) - BackendOperations protocol hierarchy
- [PROTOCOL_REFERENCE.md](../reference/PROTOCOL_REFERENCE.md) - Complete protocol catalog
- `core/protocols.py` - All type-checking protocols (source of truth)
- `core/services/protocols/` - All domain operation protocols

---

**Status:** Active - Use this guide for all new protocol implementations
