---
title: Protocol Implementation Guide
created: 2026-01-03
updated: 2026-11-13
status: active
audience: developers
tags: [guide, protocols, implementation]
---

# Protocol Implementation Guide

**Last Updated**: January 3, 2026

## Quick Start

This guide shows you how to implement and use protocols in SKUEL. For architecture overview, see [protocol_architecture.md](../patterns/protocol_architecture.md).

## Core Type-Checking Protocols

SKUEL's type-checking protocols live in `/core/ports/base_protocols.py` (the `Has*` attribute protocols) and `/core/utils/type_converters.py` (the conversion protocols), and eliminate all `hasattr()` usage.

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
    elif isinstance(obj, HasNeo4jProperties):
        return obj.to_neo4j_properties()
    else:
        return {}
```

### Domain-Specific Attribute Protocols

For scalar field protocols, keep them minimal:

```python
@runtime_checkable
class HasScore(Protocol):
    """Protocol for objects with score attribute."""
    score: float

@runtime_checkable
class HasRelevanceScore(Protocol):
    """Protocol for objects with relevance_score attribute."""
    relevance_score: float
```

**Usage**:
```python
def rank_results(results: list[Any]) -> list[Any]:
    """Sort results by score if available."""
    scored = [r for r in results if isinstance(r, HasScore)]
    unscored = [r for r in results if not isinstance(r, HasScore)]
    return sorted(scored, key=lambda r: r.score, reverse=True) + unscored
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

Domain operation protocols define business logic interfaces. Located in `core/ports/domain_protocols.py`.

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
from core.ports import TasksOperations

class TasksService:
    """Tasks business logic service."""

    def __init__(self, backend: TasksOperations):
        """Initialize with protocol-based backend."""
        self.backend = backend  # Type: TasksOperations (protocol)

    async def create_task(self, title: str, user_uid: UserUID) -> Result[Task]:
        """Create a new task."""
        data = {"title": title, "user_uid": user_uid}
        uid_result = await self.backend.create(data)

        if uid_result.is_error:
            return Result.fail(uid_result.error)

        task_result = await self.backend.get(uid_result.value)
        return task_result
```

### Backend Implementation (Structural Typing)

Every backend is built in one place, `create_all_backends`
(`services_bootstrap/_backends.py`). The composition root, every test and every
script take their backend from the typed set it returns (`Backends` — each key
under its concrete class, so a read is checked against the consumer's protocol); nothing else constructs one
(`tests/unit/test_production_backend_census.py` fails a test or script that does).
A script opens its own driver and reads one entry:
`create_all_backends(driver, Neo4jQueryExecutor(driver))["uid_census_backend"]`.

```python
# services_bootstrap/_backends.py — inside create_all_backends
from adapters.persistence.neo4j.backends.activity_backends import TasksBackend

tasks_backend = TasksBackend(
    driver,
    NeoLabel.TASK,
    Task,
    prometheus_metrics=prometheus_metrics,
    base_label=NeoLabel.ENTITY,
)
# TasksBackend never names TasksOperations: it satisfies the protocol
# structurally — UniversalNeo4jBackend[Task] supplies BackendOperations[Task]
# (create(task) -> Result[Task], get(uid) -> Result[Task | None], ...) and its
# mixins the relationship and hierarchy operations.

# services_bootstrap/compose.py — each consumer reads its entry from the set
backends = create_all_backends(driver, query_executor, prometheus_metrics=prometheus_metrics)
tasks_backend = backends["tasks_backend"]  # TasksBackend
activity_services = _create_activity_services(
    tasks_backend=tasks_backend,  # checked against TasksOperations
    ...
)
```

## Breaking Circular Dependencies with Protocols

Two services that each need the other cannot both take the other in `__init__`,
and neither module can import the other's at runtime. SKUEL breaks the cycle in
two moves: the dependent names a type that needs no runtime import of the other
service, and the composition root sets the attribute once both exist.

### A protocol-typed dependency, wired after construction

`FormSubmissionService` checks a submission's audience through the sharing
service, which the composition root builds later. It depends on the
`SharingOperations` protocol (`core/ports/sharing_protocols.py`), never on
`UnifiedSharingService`:

```python
# core/services/forms/form_submission_service.py
from core.ports.sharing_protocols import SharingOperations

class FormSubmissionService(...):
    def __init__(
        self,
        backend: FormSubmissionBackendOperations,
        form_template_service: FormTemplateOperations,
        event_bus: EventBusOperations | None = None,
        sharing_service: SharingOperations | None = None,
    ) -> None:
        ...
        self.sharing_service = sharing_service
```

```python
# services_bootstrap/compose.py — inside compose_services
unified_sharing_service = UnifiedSharingService(backend=backends["sharing_backend"])

# Wire sharing into FormSubmissionService, created earlier without it.
form_submission_service.sharing_service = unified_sharing_service
```

mypy checks the assignment: `UnifiedSharingService` must satisfy
`SharingOperations`. A method that needs the dependency refuses while it is
`None` — `FormSubmissionService` answers a forbidden `Result` when it cannot
verify an audience — it never skips the check.

### A facade-typed dependency, wired after construction

Between two facades the type is the concrete class (the facade is the contract —
see `/docs/patterns/protocol_architecture.md`), imported under `TYPE_CHECKING` so
no import cycle forms:

```python
# core/services/habits_service.py
if TYPE_CHECKING:
    from core.services.goals_service import GoalsService

class HabitsService(...):
    def __init__(self, ...) -> None:
        ...
        self.goals_service: GoalsService | None = None
```

```python
# services_bootstrap/compose.py — inside compose_services
activity_services["habits"].goals_service = activity_services["goals"]
```

`activity_services` is a typed set (`ActivityServices`,
`core/services/activity_services.py`), so this assignment is checked too.

### What the two share

- The attribute is declared `X | None` in `__init__` and set at the composition
  root, after both services exist.
- No service imports the other's module at runtime.
- Fail-fast still holds: a `None` here is the "true circular dependency" case, not
  an optional feature.

## Complete Protocol Examples

### Implementing a New Protocol

> The `Alert*` names below are illustrative — no such service exists. For a real,
> minimal port pair, read `core/ports/notification_protocols.py`
> (`NotificationBackendOperations` + `NotificationOperations`).

**Step 1**: Define the protocol

```python
# File: core/ports/domain_protocols.py
from typing import Protocol
from core.utils.result_simplified import Result

class AlertOperations(Protocol):
    """Protocol for alert operations."""

    async def send_notification(
        self,
        user_uid: UserUID,
        message: str,
        priority: str = "normal"
    ) -> Result[None]:
        """Send notification to user."""
        ...

    async def get_unread_count(self, user_uid: UserUID) -> Result[int]:
        """Get count of unread notifications."""
        ...
```

**Step 2**: Implement the backend (duck typing)

```python
# Illustrative backend adapter (would live with the persistence adapters)
from core.utils.result_simplified import Result

class AlertBackend:
    """Alert backend implementation."""

    async def send_notification(
        self,
        user_uid: UserUID,
        message: str,
        priority: str = "normal"
    ) -> Result[None]:
        """Send notification implementation."""
        # Implementation here
        return Result.ok(None)

    async def get_unread_count(self, user_uid: UserUID) -> Result[int]:
        """Get unread count implementation."""
        # Implementation here
        return Result.ok(5)

# Backend automatically satisfies AlertOperations protocol!
# No explicit inheritance needed.
```

**Step 3**: Use in service

```python
# Illustrative service (would live with the core services)
from core.ports.alert_protocols import AlertOperations

class AlertService:
    """Alert business logic service."""

    def __init__(self, backend: AlertOperations):
        """Initialize with protocol-based backend."""
        self.backend = backend  # Type-safe!

    async def notify_user(self, user_uid: UserUID, message: str) -> Result[None]:
        """Send an alert to a user."""
        return await self.backend.send_notification(user_uid, message)
```

## Testing with Protocols

Protocols make testing trivial - just create a simple class that matches the protocol:

```python
# Illustrative unit test
import pytest
from core.services.alerts.alert_service import AlertService
from core.utils.result_simplified import Result

class MockAlertBackend:
    """Mock implementation for testing."""

    def __init__(self):
        self.sent_notifications = []

    async def send_notification(
        self,
        user_uid: UserUID,
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

    async def get_unread_count(self, user_uid: UserUID) -> Result[int]:
        """Mock unread count."""
        return Result.ok(0)

@pytest.mark.asyncio
async def test_notify_user():
    """Test notification sending."""
    # Create mock backend (automatically satisfies AlertOperations!)
    mock_backend = MockAlertBackend()

    # Create service with mock
    service = AlertService(backend=mock_backend)

    # Call service method
    result = await service.notify_user("user_2b8e4d0a6c1f9573", "Hello!")

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
- `/core/ports/base_protocols.py` - the `Has*` attribute protocols (`HasCreatedAt`, `HasUpdatedAt`, `HasScore`, `HasRelevanceScore`, …); `/core/utils/type_converters.py` - the conversion protocols (`PydanticModel`, `HasToDict`)
- `core/ports/` - All domain operation protocols

---

**Status:** Active - Use this guide for all new protocol implementations
