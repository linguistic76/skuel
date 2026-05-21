---
name: base-analytics-service
description: Expert guide for creating and modifying domain analytics services using BaseAnalyticsService. Use when adding analytics methods, implementing KnowledgeIntelligenceOperations/DomainIntelligenceOperations/IntelligenceOperations protocols, using GraphContextLoader, or working with the 9 domain intelligence services.
allowed-tools: Read, Grep, Glob
---

# BaseAnalyticsService: Domain Analytics Pattern

> "Graph analytics without AI dependencies - the app runs at full capacity without LLM"

SKUEL's intelligence layer uses `BaseAnalyticsService[B, T]` as the foundation for all 9 domain intelligence services. This skill covers creating, modifying, and extending analytics services.

## Key Architecture (ADR-030)

SKUEL separates analytics from AI with two base classes:

| Base Class | Purpose | AI Dependencies |
|------------|---------|-----------------|
| **`BaseAnalyticsService`** | Graph analytics, pure Python | **NONE** |
| `BaseAIService` | LLM/embeddings features | Yes (optional) |

**All 9 domain `*_intelligence_service.py` files extend `BaseAnalyticsService`** - they are pure graph analytics with ZERO AI dependencies. The app functions completely without LLM.

## Quick Start

### What is BaseAnalyticsService?

`BaseAnalyticsService[B, T]` is the base class for all 9 domain intelligence services, providing:
- Standardized initialization for common attributes
- Fail-fast validation for required dependencies
- Hierarchical logging with domain names
- Event handler auto-registration
- Template methods for context-based analysis
- Dual-track assessment (user vision vs system measurement)

### The 9 Domain Intelligence Services

Services >~350 lines are decomposed into mixin files in the same package directory (April 2026). See `SERVICE_DECOMPOSITION_RULE.md`.

| Domain | Service | Inherits | Key Focus |
|--------|---------|----------|-----------|
| **Activity (6)** |
| Tasks | `TasksIntelligenceService` | `_CoreIntelligenceMixin, _AnalyticsMixin, _ProductivityMixin, BaseAnalyticsService["TasksOperations", Task]` | Knowledge, behavioral, performance (shell + 3 mixins) |
| Tasks | `TasksProductivityService` | `BaseAnalyticsService["TasksOperations", Task]` | Dual-track productivity (ADR-030) |
| Goals | `GoalsIntelligenceService` | `_CoreIntelligenceMixin, _AnalyticsMixin, _PredictiveMixin, _DualTrackMixin, BaseAnalyticsService[GoalsOperations, Goal]` | Progress forecasting (shell + 4 mixins) |
| Habits | `HabitsIntelligenceService` | `BaseAnalyticsService[HabitsOperations, Habit]` | Streak patterns |
| Events | `EventsIntelligenceService` | `_CoreIntelligenceMixin, _AnalyticsMixin, _BehavioralSignalsMixin, BaseAnalyticsService["EventsOperations", Event]` | Cross-domain impact (shell + 3 mixins) |
| Choices | `ChoicesIntelligenceService` | `BaseAnalyticsService["ChoicesOperations", Choice]` | Decision support |
| Principles | `PrinciplesIntelligenceService` | `BaseAnalyticsService[PrinciplesOperations, Principle]` | Alignment analysis |
| **Curriculum (3)** |
| KU | `KuIntelligenceService` | `_CoreIntelligenceMixin[Ku], BaseAnalyticsService["BackendOperations[Ku]", Ku]` | Knowledge graph analytics |
| PS | `PsIntelligenceService` | `_CoreIntelligenceMixin[PathStep], BaseAnalyticsService["BackendOperations[PathStep]", PathStep]` | Readiness checks |
| LP | `LpIntelligenceService` | `_CoreIntelligenceMixin[LearningPath], BaseAnalyticsService[Any, LearningPath]` | Learning state analysis |

**Key pattern:** The second type parameter is the domain's own model — `Task` for tasks, `Habit` for habits, `Ku` for knowledge units, `PathStep` for path steps, `LearningPath` for learning paths. PS, LP, and KU inherit `_CoreIntelligenceMixin[T]` directly (no per-domain mixin wrapper) and get a typed `get_with_context() -> Result[tuple[T, GraphContext]]` for free.

---

## Class Attributes

Every analytics service must define these class attributes:

```python
class TasksIntelligenceService(BaseAnalyticsService["TasksOperations", Task]):
    # REQUIRED: Logger name (hierarchical)
    _service_name: ClassVar[str] = "tasks.analytics"

    # OPTIONAL: Fail if relationships not provided (default: False)
    _require_relationships: ClassVar[bool] = False

    # OPTIONAL: Fail if graph_intel not provided (default: False)
    _require_graph_intel: ClassVar[bool] = False

    # OPTIONAL: Auto-register event handlers
    _event_handlers: ClassVar[dict[type, str]] = {
        TaskCompleted: "handle_task_completed",
        TaskCreated: "handle_task_created",
    }
```

### Attribute Reference

| Attribute | Type | Required | Purpose |
|-----------|------|----------|---------|
| `_service_name` | `str` | Yes | Logger name: `skuel.analytics.{_service_name}` |
| `_require_relationships` | `bool` | No | If True, raise if `relationship_service` is None |
| `_require_graph_intel` | `bool` | No | If True, raise if `graph_intel` is None |
| `_event_handlers` | `dict[type, str]` | No | Auto-subscribe handlers on init |

---

## Initialization Pattern

### Constructor Signature

```python
def __init__(
    self,
    backend: B,                                    # REQUIRED - domain operations
    graph_intel: Any | None = None, # GraphIntelligenceService
    relationship_service: Any | None = None,       # UnifiedRelationshipService
    event_bus: Any | None = None,                  # EventBus
    insight_store: Any | None = None,              # InsightStore
) -> None:
```

**NOTE:** No `embeddings_service` or `llm_service` parameters - this is intentional. Analytics services work without AI. For AI features, see the `base-ai-service` skill.

### Standard Initialization

```python
from core.services.base_analytics_service import BaseAnalyticsService

class HabitsIntelligenceService(BaseAnalyticsService[HabitsOperations, Habit]):
    _service_name = "habits.analytics"

    def __init__(
        self,
        backend: HabitsOperations,
        graph_intel: GraphIntelligenceService | None = None,
        relationship_service: UnifiedRelationshipService | None = None,
        event_bus: EventBus | None = None,
        insight_store: InsightStore | None = None,
    ) -> None:
        # ALWAYS call super().__init__() first
        super().__init__(
            backend=backend,
            graph_intel=graph_intel,
            relationship_service=relationship_service,
            event_bus=event_bus,
            insight_store=insight_store,
        )

        # Domain-specific initialization AFTER super().__init__()
        self._streak_cache: dict[str, int] = {}
```

### Provided Attributes After Init

After `super().__init__()`, these attributes are available:

| Attribute | Type | Purpose |
|-----------|------|---------|
| `self.backend` | `B` | Domain operations protocol (REQUIRED) |
| `self.graph_intel` | `GraphIntelligenceService \| None` | Graph queries |
| `self.relationships` | `UnifiedRelationshipService \| None` | Relationship queries |
| `self.event_bus` | `EventBus \| None` | Event publishing |
| `self.insight_store` | `InsightStore \| None` | Event-driven insight persistence |
| `self.logger` | `Logger` | Hierarchical logger |
| `self.context_loader` | `GraphContextLoader \| None` | Context retrieval (set via `self._init_context_loader(...)`) |

---

## Fail-Fast Guards

Use these guard methods to validate dependencies before operations:

### `_require_graph_intelligence(operation)`

```python
async def get_entity_context(self, uid: str) -> Result[dict]:
    self._require_graph_intelligence("get_entity_context")
    # Safe: graph_intel is guaranteed available
    return await self.graph_intel.get_context(uid)
```

### `_require_relationship_service(operation)`

```python
async def get_related_goals(self, uid: str) -> Result[list[str]]:
    self._require_relationship_service("get_related_goals")
    # Safe: relationships is guaranteed available
    return await self.relationships.get_related_uids(uid, RelationshipName.FULFILLS_GOAL)
```

### Guard Behavior

All guards raise `ValueError` if the dependency is unavailable:

```
ValueError: TasksIntelligenceService.get_entity_context() requires graph_intel
```

---

## Helper Methods

### `_to_domain_model(dto_or_dict, dto_class, model_class)`

Convert data to domain model (handles DTO, dict, or already-converted):

```python
async def process_tasks(self, raw_data: list[dict]) -> list[Task]:
    return [
        self._to_domain_model(item, TaskDTO, Task)
        for item in raw_data
    ]
```

### `_publish_event(event)`

Publish events to event bus (safe if bus unavailable):

```python
async def complete_task(self, uid: str) -> Result[Task]:
    result = await self.backend.complete(uid)
    if result.is_ok:
        await self._publish_event(TaskCompleted(task_uid=uid))
    return result
```

### `_analyze_entity_with_context()` (Template Method)

Consolidates the common pattern: fetch entity -> get context -> calculate metrics -> generate recommendations:

```python
async def get_goal_progress_dashboard(self, uid: str) -> Result[dict]:
    return await self._analyze_entity_with_context(
        uid=uid,
        context_method="get_goal_cross_domain_context",
        context_type=GoalCrossContext,
        metrics_fn=self._calculate_goal_metrics,
        recommendations_fn=self._generate_progress_recommendations,
        min_confidence=0.7,
    )

def _calculate_goal_metrics(self, goal: Goal, context: GoalCrossContext) -> dict:
    return {
        "progress_percentage": goal.progress * 100,
        "supporting_habits_count": len(context.supporting_habits),
        "blocking_tasks": len(context.blocking_tasks),
    }

def _generate_progress_recommendations(
    self, goal: Goal, context: GoalCrossContext, metrics: dict
) -> list[str]:
    recommendations = []
    if metrics["supporting_habits_count"] < 2:
        recommendations.append("Add habits to support this goal")
    return recommendations
```

### `_dual_track_assessment()` (Template Method)

Compare user self-assessment (vision) with system measurement (action):

```python
async def assess_alignment_dual_track(
    self, principle_uid: str, user_uid: UserUID, user_level: AlignmentLevel, ...
) -> Result[DualTrackResult[AlignmentLevel]]:
    return await self._dual_track_assessment(
        uid=principle_uid,
        user_uid=user_uid,
        user_level=user_level,
        user_evidence=evidence,
        user_reflection=reflection,
        system_calculator=self._calculate_system_alignment,
        level_scorer=self._alignment_level_to_score,  # delegates to AlignmentLevel.to_score()
        entity_type=EntityType.PRINCIPLE.value,
    )
```

---

## Method Categories

Analytics methods fall into these categories:

### 1. Single-Entity Intelligence

Analyze one entity with its graph context:

```python
async def get_task_context(self, uid: str) -> Result[dict]:
    """Get task with full graph neighborhood."""
    self._require_graph_intelligence("get_task_context")
    return await self.graph_intel.get_with_context(uid, depth=2)
```

### 2. User-Scoped Analytics

Analyze patterns across a user's entities:

```python
async def get_behavioral_insights(
    self, user_uid: UserUID, period_days: int = 90
) -> Result[dict]:
    """Analyze user's task completion patterns."""
    tasks = await self.backend.get_user_tasks(user_uid, period_days)
    if tasks.is_error:
        return tasks

    return Result.ok({
        "completion_rate": self._calc_completion_rate(tasks.value),
        "peak_hours": self._find_peak_hours(tasks.value),
        "recommendations": self._generate_recommendations(tasks.value),
    })
```

### 3. Cross-Domain Intelligence

Connect insights across multiple domains:

```python
async def get_knowledge_application_opportunities(
    self, user_uid: UserUID, ku_uid: str
) -> Result[dict]:
    """Find tasks and habits that could apply this knowledge."""
    self._require_relationship_service("get_knowledge_application_opportunities")

    # Find related entities across domains
    tasks = await self.relationships.get_related_uids(
        ku_uid, RelationshipName.APPLIES_KNOWLEDGE, direction="incoming"
    )
    habits = await self.relationships.get_related_uids(
        ku_uid, RelationshipName.REINFORCES_KNOWLEDGE, direction="incoming"
    )

    return Result.ok({
        "applicable_tasks": tasks.value if tasks.is_ok else [],
        "reinforcing_habits": habits.value if habits.is_ok else [],
    })
```

### 4. Performance Analytics

Compute metrics and trends using pure Python:

```python
async def get_performance_analytics(
    self, user_uid: UserUID, period_days: int = 30
) -> Result[dict]:
    """Calculate performance metrics."""
    tasks = await self.backend.get_completed_tasks(user_uid, period_days)
    if tasks.is_error:
        return tasks

    return Result.ok({
        "total_completed": len(tasks.value),
        "avg_completion_time_hours": self._avg_completion_time(tasks.value),
        "trend": self._calculate_trend(tasks.value),
    })
```

---

## Event Handling

### Declaring Event Handlers

Use the `_event_handlers` class attribute:

```python
from core.events.task_events import TaskCompleted, TaskCreated

class TasksIntelligenceService(BaseAnalyticsService["TasksOperations", Task]):
    _service_name = "tasks.analytics"
    _event_handlers = {
        TaskCompleted: "handle_task_completed",
        TaskCreated: "handle_task_created",
    }

    async def handle_task_completed(self, event: TaskCompleted) -> None:
        """Handle task completion - update knowledge substance."""
        self.logger.info(f"Task completed: {event.task_uid}")
        # Update related knowledge units
        await self._update_knowledge_substance(event.task_uid)

    async def handle_task_created(self, event: TaskCreated) -> None:
        """Handle task creation - analyze knowledge requirements."""
        self.logger.info(f"Task created: {event.task_uid}")
```

### Auto-Registration

When `event_bus` is provided to `__init__()`, handlers are automatically registered:

```python
# In base class __init__():
for event_type, handler_name in self._event_handlers.items():
    handler = getattr(self, handler_name, None)
    if handler:
        self.event_bus.subscribe(event_type, handler)
```

---

## Intelligence Protocols

The intelligence protocol layer has two levels:

### Core Protocols (`core/ports/intelligence_protocols.py`)

Split into focused ISP protocols (March 2026):

| Protocol | Methods | Implementor |
|----------|---------|-------------|
| `KnowledgeIntelligenceOperations` | 4 — `get_knowledge_suggestions`, `generate_knowledge_from_entities`, `get_knowledge_prerequisites`, `get_learning_opportunities` | `ActivityKnowledgeIntelligenceService` (shared singleton) |
| `DomainIntelligenceOperations` | 7 — `find_similar_content`, `search_by_features`, `get_learning_velocity`, `get_behavioral_insights`, `get_performance_analytics`, `get_cross_domain_opportunities`, `get_ai_insights` | Per-domain intelligence services |
| `IntelligenceOperations` | 11 (composed) | Backward-compatible union of both |

### Route Factory Protocol (3 methods for auto route generation)

All 10 domain services satisfy this separate protocol from `intelligence_route_factory.py`. `get_with_context()` is inherited from `_CoreIntelligenceMixin[T]` — never implemented per-service:

```python
# Inherited — do not reimplement:
#   _CoreIntelligenceMixin[T].get_with_context(uid, depth=2)
#     -> Result[tuple[T, GraphContext]]

async def get_performance_analytics(
    self, user_uid: UserUID, period_days: int = 30
) -> Result[dict[str, Any]]:
    """Get user-specific analytics."""
    ...

async def get_domain_insights(
    self, uid: str, min_confidence: float = 0.7
) -> Result[dict[str, Any]]:
    """Get domain-specific intelligence."""
    ...
```

---

## GraphContextLoader

Each analytics service uses `GraphContextLoader` (in `core/services/intelligence/graph_context_loader.py`) for unified context retrieval. Services never import it directly — they call the `self._init_context_loader(...)` helper on `BaseAnalyticsService`, which no-ops when `graph_intel` is `None` and constructs the loader otherwise, storing it on `self.context_loader`.

```python
class TasksIntelligenceService(
    _CoreIntelligenceMixin,  # inherits get_with_context() — typed via per-domain wrapper
    BaseAnalyticsService["TasksOperations", Task],
):
    def __init__(self, backend, graph_intel=None, ...):
        super().__init__(backend, graph_intel, ...)

        self._init_context_loader(
            get_entity=self.backend.get_task,
            dto_class=TaskDTO,
            model_class=Task,
            domain=Domain.TASKS,
            model_name="Task",
        )
    # get_with_context() is inherited — no override needed.
```

`_CoreIntelligenceMixin[T]` is generic: PS, LP, and KU inherit it directly
(`_CoreIntelligenceMixin[PathStep]`, `_CoreIntelligenceMixin[LearningPath]`,
`_CoreIntelligenceMixin[Ku]`) and get a typed
`Result[tuple[T, GraphContext]]` return with no per-domain wrapper. Activity
domains use their package's `_CoreIntelligenceMixin` wrapper (which extends
the shared base) because they also expose a domain-named alias
(e.g. `get_goal_with_context`). No service needs to special-case the
`_init_context_loader` call — `BaseAnalyticsService` fail-fasts on a missing
backend, so the loader wiring is unconditional.

---

## Anti-Patterns

### Don't Skip super().__init__()

```python
# WRONG - skips base class initialization
def __init__(self, backend, ...):
    self.backend = backend  # Misses validation, logging, event registration

# CORRECT
def __init__(self, backend, ...):
    super().__init__(backend, ...)  # ALWAYS call first
```

### Don't Access Dependencies Without Guards

```python
# WRONG - crashes if graph_intel is None
async def get_context(self, uid: str):
    return await self.graph_intel.get_context(uid)

# CORRECT - fail-fast with clear error
async def get_context(self, uid: str):
    self._require_graph_intelligence("get_context")
    return await self.graph_intel.get_context(uid)
```

### Don't Create Custom Error Classes

```python
# WRONG - use Errors factory
class IntelligenceError(Exception):
    pass

# CORRECT - use Result[T] pattern
from core.utils.errors_simplified import Errors
return Result.fail(Errors.business(rule="intelligence", message="..."))
```

### Don't Return Raw Exceptions

```python
# WRONG - inconsistent error handling
async def analyze(self, uid: str):
    try:
        ...
    except Exception as e:
        raise IntelligenceError(str(e))

# CORRECT - return Result[T]
async def analyze(self, uid: str) -> Result[dict]:
    try:
        ...
        return Result.ok(data)
    except Exception as e:
        return Result.fail(Errors.system(str(e), exception=e))
```

---

## Creating a New Analytics Service

### Step 1: Define the Service

```python
# core/services/new_domain/new_domain_intelligence_service.py
from core.services.base_analytics_service import BaseAnalyticsService
from core.ports import NewDomainOperations
from core.models.new_domain import NewDomainModel, NewDomainDTO

class NewDomainIntelligenceService(
    _CoreIntelligenceMixin[NewDomainModel],
    BaseAnalyticsService[NewDomainOperations, NewDomainModel],
):
    _service_name = "new_domain.analytics"
    _require_relationships = False  # Set True if needed

    def __init__(
        self,
        backend: NewDomainOperations,
        graph_intel=None,
        relationship_service=None,
        event_bus=None,
        insight_store=None,
    ):
        super().__init__(
            backend=backend,
            graph_intel=graph_intel,
            relationship_service=relationship_service,
            event_bus=event_bus,
            insight_store=insight_store,
        )

        self._init_context_loader(
            get_entity=self.backend.get,
            dto_class=NewDomainDTO,
            model_class=NewDomainModel,
            domain=Domain.NEW_DOMAIN,
            model_name="NewDomainModel",
        )
```

### Step 2: Implement Protocol Methods

```python
    # get_with_context() inherited from _CoreIntelligenceMixin[NewDomainModel]

    async def get_performance_analytics(
        self, user_uid: UserUID, period_days: int = 30
    ) -> Result[dict[str, Any]]:
        entities = await self.backend.get_user_entities(user_uid, period_days)
        if entities.is_error:
            return entities

        return Result.ok({
            "total": len(entities.value),
            "completion_rate": self._calc_completion_rate(entities.value),
        })

    async def get_domain_insights(
        self, uid: str, min_confidence: float = 0.7
    ) -> Result[dict[str, Any]]:
        self._require_graph_intelligence("get_domain_insights")
        context = await self.graph_intel.get_context(uid)
        return Result.ok({
            "insights": self._analyze_context(context),
            "recommendations": self._generate_recommendations(context),
        })
```

### Step 3: Wire in Facade

```python
# core/services/new_domain/new_domain_service.py
class NewDomainService:
    def __init__(self, backend, graph_intel=None, ...):
        self.core = NewDomainCoreService(backend)
        self.search = NewDomainSearchService(backend)
        self.intelligence = NewDomainIntelligenceService(
            backend=backend,
            graph_intel=graph_intel,
            ...
        )
```

### Step 4: Document

Create `/docs/intelligence/NEW_DOMAIN_INTELLIGENCE.md` following existing format.

---

## Key Source Files

| File | Purpose |
|------|---------|
| `/core/services/base_analytics_service.py` | Base class definition |
| `/core/services/base_ai_service.py` | AI features (separate - see base-ai-service skill) |
| `/core/ports/intelligence_protocols.py` | KnowledgeIntelligenceOperations + DomainIntelligenceOperations + composed IntelligenceOperations |
| `/core/services/intelligence/graph_context_loader.py` | GraphContextLoader |
| `/core/services/{domain}/{domain}_intelligence_service.py` | Domain implementations |
| `/docs/intelligence/INTELLIGENCE_SERVICES_INDEX.md` | Master documentation |

## Related Skills

- **[base-ai-service](../base-ai-service/SKILL.md)** - AI-powered features (LLM, embeddings)
- **[result-pattern](../result-pattern/SKILL.md)** - Result[T] error handling
- **[neo4j-cypher-patterns](../neo4j-cypher-patterns/SKILL.md)** - Graph query patterns
- **[python](../python/SKILL.md)** - Python patterns and protocols

## Deep Dive Resources

**Architecture:**
- [INTELLIGENCE_SERVICES_INDEX.md](/docs/intelligence/INTELLIGENCE_SERVICES_INDEX.md) - Complete intelligence services guide
- [ADR-024](/docs/decisions/ADR-024-base-intelligence-service-migration.md) - Analytics vs AI separation decision
- [ADR-031](/docs/decisions/ADR-031-baseservice-mixin-decomposition.md) - BaseService mixin architecture

**Patterns:**
- [SERVICE_DECOMPOSITION_RULE.md](/docs/patterns/SERVICE_DECOMPOSITION_RULE.md) - When to extract mixins (intelligence >350 lines, facade >700 lines)
- [SERVICE_CONSOLIDATION_PATTERNS.md](/docs/patterns/SERVICE_CONSOLIDATION_PATTERNS.md) - Service patterns and facade delegation
- [protocol_architecture.md](/docs/patterns/protocol_architecture.md) - Protocol-based interfaces

**Guides:**
- [BASESERVICE_QUICK_START.md](/docs/guides/BASESERVICE_QUICK_START.md) - New developer onboarding

---

## See Also

- [QUICK_REFERENCE.md](QUICK_REFERENCE.md) - File locations, imports, signatures
- [PATTERNS.md](PATTERNS.md) - Implementation patterns with code examples
- [PROTOCOL_INTEGRATION.md](PROTOCOL_INTEGRATION.md) - IntelligenceOperations + GraphContextLoader
