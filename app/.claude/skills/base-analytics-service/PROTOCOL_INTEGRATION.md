# Intelligence Protocols & Cross-Domain Context (Mechanism B)

## Overview

All 9 domain intelligence services retrieve unified context via **mechanism B** — the inherited `get_with_context()` on `_CoreIntelligenceMixin[T]`, which routes through `self.relationships.get_with_context` (registry-sourced edges) — and implement protocols enabling automatic route generation via `IntelligenceRouteFactory`. There is nothing to wire: `BaseAnalyticsService.__init__` stores the injected relationship service on `self.relationships`. (The former `GraphContextLoader` + `self._init_context_loader(...)` were deleted in the intent-traversal ↔ registry convergence, #241.)

---

## Intelligence Protocols (ISP Split — March 2026)

### Location

```python
from core.ports.intelligence_protocols import (
    KnowledgeIntelligenceOperations,   # 4 methods — shared across all activity domains
    DomainIntelligenceOperations,      # 7 methods — per-domain services
    IntelligenceOperations,            # Composed (both combined)
)
```

### KnowledgeIntelligenceOperations (shared)

Implemented by `ActivityKnowledgeIntelligenceService` — a single instance wired into all 6 activity domain facades via `self.knowledge_intelligence`. The 4 delegation methods are provided by `KnowledgeIntelligenceDelegationMixin` (`core/services/mixins/`).

```python
@runtime_checkable
class KnowledgeIntelligenceOperations(Protocol):
    async def get_knowledge_suggestions(
        self, user_uid: UserUID, entity_uid: EntityUID | None = None
    ) -> Result[KnowledgeSuggestionsResult]: ...

    async def get_knowledge_prerequisites(
        self, entity_uid: EntityUID
    ) -> Result[KnowledgePrerequisitesResult]: ...

    async def generate_knowledge_from_entities(
        self, user_uid: UserUID, period_days: int = 30
    ) -> Result[KnowledgeGenerationResult]: ...

    async def get_learning_opportunities(
        self, user_uid: UserUID
    ) -> Result[LearningOpportunitiesResult]: ...
```

### DomainIntelligenceOperations (per-domain)

Implemented by per-domain intelligence services (TasksIntelligenceService, GoalsIntelligenceService, etc.).

```python
@runtime_checkable
class DomainIntelligenceOperations(Protocol):
    async def find_similar_content(
        self, uid: str, limit: int = 5
    ) -> Result[list[str]]: ...

    async def search_by_features(
        self, features: dict[str, Any], limit: int = 25
    ) -> Result[list[str]]: ...

    async def get_learning_velocity(
        self, user_uid: UserUID, period_days: int = 90
    ) -> Result[LearningVelocityMetrics]: ...

    async def get_behavioral_insights(
        self, user_uid: UserUID, period_days: int = 90
    ) -> Result[BehavioralInsightsResult]: ...

    async def get_performance_analytics(
        self, user_uid: UserUID, period_days: int = 30
    ) -> Result[PerformanceAnalyticsResult]: ...

    async def get_cross_domain_opportunities(
        self, user_uid: UserUID, entity_uid: EntityUID | None = None
    ) -> Result[CrossDomainOpportunitiesResult]: ...

    async def get_ai_insights(
        self, user_uid: UserUID, entity_uid: EntityUID | None = None, query: str | None = None
    ) -> Result[AIInsightsResult]: ...
```

### IntelligenceOperations (composed)

```python
class IntelligenceOperations(KnowledgeIntelligenceOperations, DomainIntelligenceOperations, Protocol):
    """Full intelligence operations — backward-compatible union of both."""
    ...
```

---

## Route Factory Protocol (3 Standardized Methods)

Separate from the core protocols, all 10 services implement this local protocol from `intelligence_route_factory.py` for automatic route generation:

### 1. `get_with_context(uid, depth=2)`

Returns entity with full graph neighborhood. **Inherited, not implemented per-service.** Services inherit `_CoreIntelligenceMixin[T]` (generic in the domain model) which owns the delegation:

```python
# core/services/intelligence/_core_intelligence_mixin.py
class _CoreIntelligenceMixin[T]:
    @requires_graph_intelligence("get_with_context")
    async def get_with_context(
        self, uid: str, depth: int = 2
    ) -> Result[tuple[T, GraphContext]]:
        # Mechanism B: route through the relationship service, whose edge
        # vocabulary comes from DomainConfig.cross_domain_relationship_types.
        if self.relationships is None:
            return Result.fail(Errors.system(
                message="relationship_service required for get_with_context",
                operation="get_with_context",
            ))
        return await self.relationships.get_with_context(uid, depth)
```

Subclasses parameterize with their model (`_CoreIntelligenceMixin[PathStep]`, `_CoreIntelligenceMixin[Goal]`, etc.) to get a typed return. Activity domains wrap this in a per-package `_CoreIntelligenceMixin` that also adds domain-named aliases (`get_task_with_context`, etc.). PS/LP/KU inherit directly (Events is an activity domain and inherits via its package wrapper).

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
    self, user_uid: UserUID, period_days: int = 30
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

## Cross-domain context (mechanism B)

> **Deleted (#241):** `GraphContextLoader`, `_init_context_loader`, and `self.context_loader`
> no longer exist. The model-suggested "mechanism A" loader was removed in the
> intent-traversal ↔ registry convergence. See
> `/docs/roadmap/intent-traversal-registry-convergence.md`.

### How it works now

Unified context retrieval is **mechanism B** (registry-sourced):

1. `BaseAnalyticsService.__init__` stores the injected relationship service on
   `self.relationships` — nothing to wire per service.
2. `get_with_context()` is inherited from `_CoreIntelligenceMixin[T]` and routes
   through `self.relationships.get_with_context`.
3. The edge vocabulary it traverses comes from the domain's
   `DomainConfig.cross_domain_relationship_types` — the registry, the single source
   of truth (not a model-suggested query intent).

```python
class TasksIntelligenceService(
    _CoreIntelligenceMixin[Task],  # inherits get_with_context() — typed in the model
    BaseAnalyticsService[TasksOperations, Task],
):
    def __init__(self, backend, graph_intel=None, relationship_service=None, ...):
        super().__init__(backend, graph_intel, relationship_service=relationship_service, ...)
    # get_with_context() inherited — no override, no loader wiring.
```

For cross-domain **analysis** (metrics + recommendations), call the template
`BaseAnalyticsService._analyze_entity_with_typed_context(uid, metrics_fn, recommendations_fn)`,
which sources the canonical typed, path-aware context from
`UnifiedRelationshipService.get_cross_domain_context_typed` (built per-domain via
`{Domain}CrossContext.from_categorized`).

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
        async def get_analytics(request, user_uid: UserUID, period_days: int = 30):
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
from core.ports import TasksOperations, IntelligenceOperations
from core.models.task import Task, TaskDTO
from core.models.enums import Domain


class TasksIntelligenceService(
    _CoreIntelligenceMixin[Task],  # inherits typed get_with_context()
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
        insight_store=None,
    ):
        super().__init__(
            backend=backend,
            graph_intel=graph_intel,
            relationships=relationships,
            event_bus=event_bus,
            insight_store=insight_store,
        )
        # get_with_context() is inherited from _CoreIntelligenceMixin[Task] (mechanism B);
        # the relationship service is stored on self.relationships — no loader to wire.

    # =========================================================================
    # THREE STANDARDIZED METHODS
    # get_with_context() is inherited from _CoreIntelligenceMixin[Task].
    # =========================================================================

    async def get_performance_analytics(
        self, user_uid: UserUID, period_days: int = 30
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
    # TASK-SPECIFIC PROTOCOL METHODS
    # =========================================================================
    # NOTE: Knowledge methods (get_knowledge_suggestions, generate_knowledge_from_entities,
    # get_knowledge_prerequisites, get_learning_opportunities) extracted to
    # ActivityKnowledgeIntelligenceService (core/services/knowledge/) — March 2026

    async def get_behavioral_insights(
        self, user_uid: UserUID, period_days: int = 90
    ) -> Result[dict[str, Any]]:
        """Analyze task completion behavior."""
        # Implementation
        ...

    async def get_performance_analytics(
        self, user_uid: UserUID, period_days: int = 30
    ) -> Result[dict[str, Any]]:
        """Completion rates, trends, duration calibration."""
        # Implementation
        ...

    # ... other task-specific methods
```

---

## Rollout Status

All 9 domain intelligence services implement the protocol and inherit
`get_with_context()` from `_CoreIntelligenceMixin[T]` (mechanism B):

| Service | Protocol | get_with_context (inherited) | Routes |
|---------|----------|------------------------------|--------|
| TasksIntelligenceService | ✅ | ✅ | ✅ |
| GoalsIntelligenceService | ✅ | ✅ | ✅ |
| HabitsIntelligenceService | ✅ | ✅ | ✅ |
| EventsIntelligenceService | ✅ | ✅ | ✅ |
| ChoicesIntelligenceService | ✅ | ✅ | ✅ |
| PrinciplesIntelligenceService | ✅ | ✅ | ✅ |
| KuIntelligenceService | ✅ | ✅ | ✅ |
| PsIntelligenceService | ✅ | ✅ | ✅ |
| LpIntelligenceService | ✅ | ✅ | ✅ |

---

## Testing Protocol Implementation

```python
import pytest
from core.ports import IntelligenceOperations


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
