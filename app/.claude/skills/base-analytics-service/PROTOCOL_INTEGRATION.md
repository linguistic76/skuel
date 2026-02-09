# IntelligenceOperations Protocol & GraphContextOrchestrator

## Overview

All 10 domain intelligence services implement the `IntelligenceOperations` protocol and use `GraphContextOrchestrator` for unified context retrieval. This enables automatic route generation via `IntelligenceRouteFactory`.

---

## IntelligenceOperations Protocol

### Location

```python
from core.services.protocols.intelligence_protocols import IntelligenceOperations
```

### Protocol Definition

```python
@runtime_checkable
class IntelligenceOperations(Protocol):
    """Protocol for intelligence operations across all domains."""

    # Knowledge Intelligence
    async def get_knowledge_suggestions(
        self, user_uid: str, entity_uid: str | None = None
    ) -> Result[dict[str, Any]]: ...

    async def get_knowledge_prerequisites(
        self, entity_uid: str
    ) -> Result[dict[str, Any]]: ...

    async def generate_knowledge_from_entities(
        self, user_uid: str, period_days: int = 30
    ) -> Result[dict[str, Any]]: ...

    async def find_similar_content(
        self, uid: str, limit: int = 5
    ) -> Result[list[str]]: ...

    async def search_by_features(
        self, features: dict[str, Any], limit: int = 25
    ) -> Result[list[str]]: ...

    # Learning Intelligence
    async def get_learning_opportunities(
        self, user_uid: str
    ) -> Result[dict[str, Any]]: ...

    async def get_learning_velocity(
        self, user_uid: str, period_days: int = 90
    ) -> Result[dict[str, Any]]: ...

    # Behavioral Intelligence
    async def get_behavioral_insights(
        self, user_uid: str, period_days: int = 90
    ) -> Result[dict[str, Any]]: ...

    # Performance Intelligence
    async def get_performance_analytics(
        self, user_uid: str, period_days: int = 30
    ) -> Result[dict[str, Any]]: ...

    # Cross-Domain Intelligence
    async def get_cross_domain_opportunities(
        self, user_uid: str, entity_uid: str | None = None
    ) -> Result[dict[str, Any]]: ...

    # AI-Powered Insights
    async def get_ai_insights(
        self, user_uid: str, entity_uid: str | None = None, query: str | None = None
    ) -> Result[dict[str, Any]]: ...
```

---

## Three Standardized Methods

Beyond the full protocol, all 10 services implement these three methods for automatic route generation:

### 1. `get_with_context(uid, depth=2)`

Returns entity with full graph neighborhood.

```python
async def get_with_context(
    self, uid: str, depth: int = 2
) -> Result[tuple[T, GraphContext]]:
    """Get entity with graph neighborhood."""
    return await self.orchestrator.get_with_context(uid=uid, depth=depth)
```

**Returns:**
```python
Result[tuple[Task, GraphContext]]
# Where GraphContext contains:
# - related_goals: list[Goal]
# - related_habits: list[Habit]
# - related_knowledge: list[Ku]
# - relationship_summary: dict
```

### 2. `get_performance_analytics(user_uid, period_days=30)`

Returns user-specific analytics.

```python
async def get_performance_analytics(
    self, user_uid: str, period_days: int = 30
) -> Result[dict[str, Any]]:
    """Get user-specific analytics."""
    entities = await self.backend.get_user_entities(user_uid)
    if entities.is_error:
        return entities

    return Result.ok({
        "total": len(entities.value),
        "completion_rate": self._calc_rate(entities.value),
        "trend": self._calc_trend(entities.value, period_days),
        "recommendations": self._generate_recs(entities.value),
    })
```

### 3. `get_domain_insights(uid, min_confidence=0.7)`

Returns domain-specific intelligence.

```python
async def get_domain_insights(
    self, uid: str, min_confidence: float = 0.7
) -> Result[dict[str, Any]]:
    """Get domain-specific insights."""
    self._require_graph_intelligence("get_domain_insights")

    entity = await self.backend.get(uid)
    if entity.is_error:
        return entity

    context = await self.graph_intel.get_context(uid)

    return Result.ok({
        "entity": entity.value,
        "insights": self._analyze(entity.value, context),
        "confidence": self._calc_confidence(context),
        "recommendations": self._recommendations(entity.value, context),
    })
```

---

## GraphContextOrchestrator

### Purpose

`GraphContextOrchestrator[T, DTO]` provides unified context retrieval for all intelligence services. It handles:

1. Entity fetching from backend
2. DTO ↔ Model conversion
3. Graph context retrieval
4. Relationship summarization

### Location

```python
from core.services.intelligence.orchestrator import GraphContextOrchestrator
```

### Initialization Pattern

```python
class TasksIntelligenceService(BaseIntelligenceService[TasksOperations, Task]):
    def __init__(self, backend, graph_intelligence_service=None, ...):
        super().__init__(backend, graph_intelligence_service, ...)

        # Initialize orchestrator only if graph intelligence available
        if graph_intelligence_service:
            self.orchestrator = GraphContextOrchestrator[Task, TaskDTO](
                service=self,                    # The intelligence service
                backend_get_method="get",        # Method name on backend
                dto_class=TaskDTO,               # DTO class for conversion
                model_class=Task,                # Domain model class
                domain=Domain.TASKS,             # Domain enum value
            )
```

### Constructor Parameters

| Parameter | Type | Purpose |
|-----------|------|---------|
| `service` | `BaseIntelligenceService` | The intelligence service instance |
| `backend_get_method` | `str` | Name of method to fetch entity |
| `dto_class` | `type[DTO]` | DTO class for serialization |
| `model_class` | `type[T]` | Domain model class |
| `domain` | `Domain` | Domain enum for relationship config |

### Usage

```python
# In intelligence service
async def get_with_context(
    self, uid: str, depth: int = 2
) -> Result[tuple[Task, GraphContext]]:
    # Orchestrator handles:
    # 1. Fetch entity via backend.get(uid)
    # 2. Convert DTO to model if needed
    # 3. Get graph context with relationships
    # 4. Return (model, context) tuple
    return await self.orchestrator.get_with_context(uid=uid, depth=depth)
```

### GraphContext Structure

```python
@dataclass
class GraphContext:
    """Graph neighborhood context for an entity."""

    # Related entities by type
    goals: list[Goal] = field(default_factory=list)
    habits: list[Habit] = field(default_factory=list)
    tasks: list[Task] = field(default_factory=list)
    events: list[Event] = field(default_factory=list)
    knowledge: list[Ku] = field(default_factory=list)
    principles: list[Principle] = field(default_factory=list)

    # Relationship summary
    relationships: dict[str, list[str]] = field(default_factory=dict)
    relationship_counts: dict[str, int] = field(default_factory=dict)

    # Traversal metadata
    depth: int = 2
    total_nodes: int = 0
```

---

## IntelligenceRouteFactory

### Purpose

Automatically generates HTTP routes for intelligence services implementing the protocol.

### Location

```python
from core.adapters.inbound.factories import IntelligenceRouteFactory
```

### Generated Routes

| Method | Route | Parameters |
|--------|-------|------------|
| `get_with_context` | `GET /api/{domain}/context` | `?uid=...&depth=2` |
| `get_performance_analytics` | `GET /api/{domain}/analytics` | `?user_uid=...&period_days=30` |
| `get_domain_insights` | `GET /api/{domain}/insights` | `?uid=...&min_confidence=0.7` |

### Usage

```python
# In routes module
from core.adapters.inbound.factories import IntelligenceRouteFactory

def create_tasks_intelligence_routes(app, rt, tasks_service):
    """Create intelligence routes for tasks."""
    IntelligenceRouteFactory.create_routes(
        app=app,
        rt=rt,
        service=tasks_service.intelligence,
        domain="tasks",
    )
```

### Implementation Example

```python
class IntelligenceRouteFactory:
    @staticmethod
    def create_routes(app, rt, service, domain: str):
        """Generate intelligence routes for a domain."""

        @rt(f"/api/{domain}/context")
        @boundary_handler()
        async def get_context(request, uid: str, depth: int = 2):
            return await service.get_with_context(uid, depth)

        @rt(f"/api/{domain}/analytics")
        @boundary_handler()
        async def get_analytics(request, user_uid: str, period_days: int = 30):
            return await service.get_performance_analytics(user_uid, period_days)

        @rt(f"/api/{domain}/insights")
        @boundary_handler()
        async def get_insights(request, uid: str, min_confidence: float = 0.7):
            return await service.get_domain_insights(uid, min_confidence)
```

---

## Complete Integration Example

Full example showing protocol, orchestrator, and routes:

```python
# core/services/tasks/tasks_intelligence_service.py
from core.services.base_analytics_service import BaseAnalyticsService
from core.services.intelligence.orchestrator import GraphContextOrchestrator
from core.services.protocols import TasksOperations, IntelligenceOperations
from core.models.task import Task, TaskDTO
from core.models.enums import Domain


class TasksIntelligenceService(
    BaseAnalyticsService[TasksOperations, Task],
    IntelligenceOperations  # Implements protocol
):
    _service_name = "tasks.analytics"

    def __init__(
        self,
        backend: TasksOperations,
        graph_intel=None,
        relationships=None,
        event_bus=None,
    ):
        super().__init__(
            backend=backend,
            graph_intel=graph_intel,
            relationships=relationships,
            event_bus=event_bus,
        )

        # Initialize orchestrator
        if graph_intelligence_service:
            self.orchestrator = GraphContextOrchestrator[Task, TaskDTO](
                service=self,
                backend_get_method="get",
                dto_class=TaskDTO,
                model_class=Task,
                domain=Domain.TASKS,
            )

    # =========================================================================
    # THREE STANDARDIZED METHODS
    # =========================================================================

    async def get_with_context(
        self, uid: str, depth: int = 2
    ) -> Result[tuple[Task, GraphContext]]:
        """Get task with graph neighborhood."""
        if not self.orchestrator:
            return Result.fail(Errors.system("Orchestrator unavailable"))
        return await self.orchestrator.get_with_context(uid=uid, depth=depth)

    async def get_performance_analytics(
        self, user_uid: str, period_days: int = 30
    ) -> Result[dict[str, Any]]:
        """Get task performance analytics."""
        tasks = await self.backend.get_user_tasks(user_uid)
        if tasks.is_error:
            return tasks

        completed = [t for t in tasks.value if t.status == "completed"]
        completion_rate = len(completed) / len(tasks.value) if tasks.value else 0.0

        return Result.ok({
            "total_tasks": len(tasks.value),
            "completed": len(completed),
            "completion_rate": completion_rate,
            "avg_completion_days": self._avg_completion_time(completed),
            "by_priority": self._group_by_priority(tasks.value),
        })

    async def get_domain_insights(
        self, uid: str, min_confidence: float = 0.7
    ) -> Result[dict[str, Any]]:
        """Get task-specific insights."""
        self._require_graph_intelligence("get_domain_insights")

        task_result = await self.backend.get(uid)
        if task_result.is_error:
            return task_result

        task = task_result.value
        context = await self.graph_intel.get_context(uid)

        return Result.ok({
            "task": task,
            "blocking_count": len(context.relationships.get("BLOCKED_BY", [])),
            "knowledge_required": len(context.knowledge),
            "recommendations": self._task_recommendations(task, context),
        })

    # =========================================================================
    # PROTOCOL METHODS (full IntelligenceOperations)
    # =========================================================================

    async def get_knowledge_suggestions(
        self, user_uid: str, entity_uid: str | None = None
    ) -> Result[dict[str, Any]]:
        """Generate knowledge suggestions from task patterns."""
        # Implementation
        ...

    async def get_behavioral_insights(
        self, user_uid: str, period_days: int = 90
    ) -> Result[dict[str, Any]]:
        """Analyze task completion behavior."""
        # Implementation
        ...

    # ... other protocol methods
```

---

## Rollout Status (January 2026)

All 10 domain intelligence services implement the protocol:

| Service | Protocol | Orchestrator | Routes |
|---------|----------|--------------|--------|
| TasksIntelligenceService | ✅ | ✅ | ✅ |
| GoalsIntelligenceService | ✅ | ✅ | ✅ |
| HabitsIntelligenceService | ✅ | ✅ | ✅ |
| EventsIntelligenceService | ✅ | ✅ | ✅ |
| ChoicesIntelligenceService | ✅ | ✅ | ✅ |
| PrinciplesIntelligenceService | ✅ | ✅ | ✅ |
| KuIntelligenceService | ✅ | ✅ | ✅ |
| LsIntelligenceService | ✅ | ✅ | ✅ |
| LpIntelligenceService | ✅ | ✅ | ✅ |
| MocIntelligenceService | ✅ | ✅ | ✅ |

---

## Testing Protocol Implementation

```python
import pytest
from core.services.protocols import IntelligenceOperations


def test_service_implements_protocol():
    """Verify service implements IntelligenceOperations."""
    service = TasksIntelligenceService(backend=mock_backend)

    # Protocol is runtime checkable
    assert isinstance(service, IntelligenceOperations)


async def test_get_with_context():
    """Test standardized context method."""
    service = create_test_service()

    result = await service.get_with_context("task-123", depth=2)

    assert result.is_ok
    task, context = result.value
    assert isinstance(task, Task)
    assert hasattr(context, "relationships")


async def test_route_integration():
    """Test generated routes work correctly."""
    app = create_test_app()

    response = await app.get("/api/tasks/context?uid=task-123&depth=2")

    assert response.status_code == 200
    data = response.json()
    assert "entity" in data
    assert "context" in data
```
