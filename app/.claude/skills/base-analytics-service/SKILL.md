---
name: base-analytics-service
description: Expert guide for creating and modifying domain analytics services using BaseAnalyticsService. Use when adding analytics methods, implementing KnowledgeIntelligenceOperations/DomainIntelligenceOperations/IntelligenceOperations protocols, cross-domain context retrieval (mechanism B / get_with_context), or working with the 9 domain intelligence services.
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
| Tasks | `TasksIntelligenceService` | `_CoreIntelligenceMixin, _AnalyticsMixin, _ProductivityMixin, _DualTrackMixin, BaseAnalyticsService["TasksOperations", Task]` | Knowledge, behavioral, performance, dual-track productivity ADR-030 (shell + 4 mixins) |
| Goals | `GoalsIntelligenceService` | `_CoreIntelligenceMixin, _AnalyticsMixin, _PredictiveMixin, _DualTrackMixin, BaseAnalyticsService[GoalsOperations, Goal]` | Progress forecasting (shell + 4 mixins) |
| Habits | `HabitsIntelligenceService` | `BaseAnalyticsService[HabitsOperations, Habit]` | Streak patterns |
| Events | `EventsIntelligenceService` | `_CoreIntelligenceMixin, _AnalyticsMixin, _BehavioralSignalsMixin, BaseAnalyticsService["EventsOperations", Event]` | Cross-domain impact (shell + 3 mixins) |
| Choices | `ChoicesIntelligenceService` | `BaseAnalyticsService["ChoicesOperations", Choice]` | Decision support |
| Principles | `PrinciplesIntelligenceService` | `BaseAnalyticsService[PrinciplesOperations, Principle]` | Alignment analysis |
| **Curriculum (3)** |
| KU | `KuIntelligenceService` | `_CoreIntelligenceMixin[Ku], BaseAnalyticsService["BackendOperations[Ku]", Ku]` | Knowledge graph analytics + dual-track mastery ADR-030 (`assess_mastery_dual_track`, per-(user, Ku)) |
| PS | `PsIntelligenceService` | `_CoreIntelligenceMixin[PathStep], BaseAnalyticsService["BackendOperations[PathStep]", PathStep]` | Readiness checks |
| LP | `LpIntelligenceService` | `_CoreIntelligenceMixin[LearningPath], BaseAnalyticsService[LpOperations, LearningPath]` | Learning state analysis |

**Key pattern:** The second type parameter is the domain's own model — `Task` for tasks, `Habit` for habits, `Ku` for knowledge units, `PathStep` for path steps, `LearningPath` for learning paths. PS, LP, and KU inherit `_CoreIntelligenceMixin[T]` directly (no per-domain mixin wrapper) and get a typed `get_with_context() -> Result[tuple[T, GraphContext]]` for free.

### Beyond the 9 domains: corpus-level analytics

`BaseAnalyticsService` is not only for per-entity domain services. **`KnowledgeHealthService`**
(`core/services/analytics/knowledge_health_service.py`, ADR-080 Horizon 1) is a *corpus-level*
subclass — same base (no AI, CORE-tier safe), but it reports on the **whole knowledge subgraph**
(Ku / PathStep / LearningPath / Exercise) instead of one entity type, and takes **no `user_uid`**.
It's wired into the `AnalyticsService` facade (not a domain facade) as
`analyze_knowledge_subgraph_health()`, and it takes only a backend — no `graph_intel` /
`relationships` (it needs neither the per-entity context loader nor the relationship service):

```python
class KnowledgeHealthService(BaseAnalyticsService[KnowledgeHealthOperations, Ku]):
    # backend measures raw structural facts; the service derives coverage ratios,
    # a composite GDS-readiness score, and authoring-guidance flags. Sync helpers
    # (_ratio, score composition) are pure-Python computation — analytics aggregate,
    # they don't create.
```

Two durable rules this example illustrates (hard-won on #770): **a corpus/authoring gauge excludes
user-generated data** (learner-state telemetry edges, PERSONAL/ASSIGNED/ASSESSMENT exercises), and
it **matches knowledge nodes by `entity_type`, not domain label** — API create paths persist
`:Entity {entity_type:'path_step'}` without the `:PathStep` label, so label-only queries silently
drop them.

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
async def get_fulfilling_tasks(self, uid: str) -> Result[list[str]]:
    self._require_relationship_service("get_fulfilling_tasks")
    # get_related_uids takes a config METHOD-KEY (str) + uid — direction/rel-type and any
    # edge filter come from the registry spec. NOT (uid, RelationshipName, direction=...).
    return await self.relationships.get_related_uids("fulfilling_tasks", uid)
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

### `_analyze_entity_with_typed_context()` (Template Method)

THE canonical template: fetch entity -> get path-aware typed cross-domain context ->
calculate metrics -> generate recommendations. Sources its context from the single
canonical reader `UnifiedRelationshipService.get_cross_domain_context_typed` (the
factory-built **path-aware** context, `core/models/graph/path_aware_types.py`). There is
no `context_type` param — the typed reader resolves the domain context type via the
per-domain `*CrossContext.from_categorized` factory seam. All 6 activity domains run on it:

```python
async def get_goal_progress_dashboard(self, uid: str) -> Result[dict]:
    return await self._analyze_entity_with_typed_context(
        uid=uid,
        metrics_fn=calculate_goal_progress_metrics,
        recommendations_fn=goal_recommendations,
        min_confidence=0.7,  # forwarded to get_cross_domain_context_typed
    )

# Metrics/recommendations functions live in
# core/services/intelligence/metrics_calculators.py and take the PATH-AWARE context
# (path_aware_types.GoalCrossContext: typed entity lists with distance/strength), e.g.
def calculate_goal_progress_metrics(goal: Any, context: PathAwareGoalCrossContext) -> dict:
    return {
        "task_support_count": len(context.tasks),
        "habit_support_count": len(context.habits),
        # ... cascade_impact / path_aware_context rollups
    }
```

> **Failure policy:** a real context-fetch error PROPAGATES as `Result.fail` rather than
> silently degrading to an empty context (an edge-less entity still yields an `ok` empty
> context, not a failure).
>
> **Context kwargs forward to `get_cross_domain_context_typed`.** Extra kwargs
> (`min_confidence`, `depth`) pass straight through. Since PR #212, `depth` is a real
> transitive knob (default `2`): related entities up to `depth` hops are bucketed by
> the edge **incident to each one**, so the path-aware context (and the metrics built from
> it) count correctly-attributed transitive context, each entry tagged with its `distance`.
> Pass `depth=1` if a dashboard should count **direct** cross-domain relationships only.
> Since PR #216 the categorization also honors a mapping's `filter_property`/`filter_value`
> (matched against each node's incident-edge properties), so edge-property-discriminated
> tiers — e.g. GOALS' `essential`/`critical`/`optional` habits on SUPPORTS_GOAL — land in
> their own buckets instead of all collapsing into the no-filter catch-all.
>
> ⚠️ **Buckets are NOT de-duped by uid.** The producer does `collect(DISTINCT {uid,
> distance, …})` — DISTINCT over the whole path map — so at `depth ≥ 2` a node reachable
> by multiple paths recurs once per path. The path-aware `*CrossContext` family
> (built via `from_categorized`) de-dups by uid keeping the **strongest** path (lowest
> `distance`, then highest `path_strength`) — first-seen is not the closest path (no
> `ORDER BY`), and skipping de-dup inflates counts. See `_union_buckets`/`_path_rank` in
> `choices/_core_intelligence_mixin.py` and the gotcha box in
> `docs/patterns/UNIFIED_RELATIONSHIP_SERVICE.md`.

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
        store_callback=self._store_dual_track_checkin,  # per-entity persistence (ADR-030)
    )
```

**Persistence + the per-entity / user-level split (ADR-030).** A `store_callback(uid, result)`
runs *after* the result is built (so it sees the computed system level/score + gap, not just the
self-rating) and is **safe-by-design** — it logs and returns on any failure so a persistence hiccup
never fails the assessment. Three flavors, by who the assessment is about:

- **Per-entity** (Goals/Habits/Principles, `require_entity=True`): callback is the canonical
  `BaseAnalyticsService._store_dual_track_checkin`, which appends the snapshot to the *entity's*
  `dual_track_checkins` field via `self.backend` (capped at `DualTrackCheckin.HISTORY_LIMIT`).
- **User-level** (Tasks/Events/Choices, `require_entity=False`, `uid == user_uid`): there is no
  `:Entity` row and the intelligence service's `self.backend` is the activity backend, not the User
  node. So the callback is `UserService.append_dual_track_checkin(user_uid, result, *, dimension)`,
  bound via `functools.partial(..., dimension=…)` at the route and passed in as `store_callback`.
  It appends to `User.dual_track_checkins` (a `dict[str, list[dict]]` keyed by `DualTrackDimension`
  value). The three user-level assess methods take an optional `store_callback` param and forward
  it.
- **Knowledge / per-(user, Ku)** (`KuIntelligenceService.assess_mastery_dual_track`,
  `require_entity=True` — a Ku *is* an `:Entity`): the system side wraps `calculate_user_substance`
  (mastery `MasteryLevel` vs substance score), but a Ku is SHARED/public, so the check-in can't live
  on the `:Ku` node — it would collide across users. The callback is
  `UserService.append_knowledge_checkin(ku_uid, result, *, user_uid)` (the template passes `ku_uid`
  as the positional `uid`; the Ku-detail route binds `user_uid` via a small store closure). It
  appends to a **separate** `User.knowledge_checkins` field — `dict[ku_uid, list[dict]]`, kept
  distinct from `dual_track_checkins` so per-Ku keys never collide with the fixed dimensions. The
  assess method takes the **rich** `UserContext` (substance needs the rich-only activity→Ku maps).

The cross-domain aggregator (`UserContextIntelligence.get_cross_domain_perception_analysis`) reads
per-entity logs via `find_by(user_uid=…)`, user-level logs off `context.dual_track_checkins`, and the
per-Ku Knowledge logs off `context.knowledge_checkins` (aggregated into one "Knowledge" bucket).

**Atomic append (all paths).** The append is a read-modify-write of a single JSON-string property,
so it runs **under a Neo4j node write-lock** to keep concurrent same-subject appends from losing a
snapshot. All callbacks route through one shared mechanism —
`adapters/persistence/neo4j/_dual_track_checkin_store.py::atomic_append_checkin` (parameterized with
`property_name` for the Knowledge `knowledge_checkins` log), surfaced as
`UniversalNeo4jBackend.atomic_append_dual_track_checkin` (per-entity, flat list),
`UserBackend.atomic_append_dual_track_checkin` (user-level, dimension-keyed), and
`UserBackend.atomic_append_knowledge_checkin` (Knowledge, `ku_uid`-keyed). Don't reintroduce a
plain `get()`+`update()` read-modify-write for check-ins — it reopens the lost-update race.

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

    # Find related entities across domains. get_related_uids takes a config METHOD-KEY
    # (str) + uid; the rel-type, direction, and any edge filter come from the spec.
    tasks = await self.relationships.get_related_uids("applied_in_tasks", ku_uid)
    habits = await self.relationships.get_related_uids("reinforced_by_habits", ku_uid)

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

## Cross-domain context (mechanism B)

> **Deleted (intent-traversal ↔ registry convergence, #241):** `GraphContextLoader`,
> `self._init_context_loader(...)`, and the `self.context_loader` attribute no longer
> exist. Context retrieval is now **mechanism B** (registry-sourced) — no per-service
> wiring. See `/docs/roadmap/intent-traversal-registry-convergence.md`.

`get_with_context()` is provided by the shared `_CoreIntelligenceMixin[T]`
(`core/services/intelligence/_core_intelligence_mixin.py`), which routes through
`self.relationships.get_with_context` — whose edge vocabulary comes from the domain's
`DomainConfig.cross_domain_relationship_types` (the registry, the single source of
truth). `BaseAnalyticsService.__init__` stores the injected relationship service on
`self.relationships`; there is nothing to wire.

```python
class TasksIntelligenceService(
    _CoreIntelligenceMixin[Task],  # inherits get_with_context() — typed in the domain model
    BaseAnalyticsService["TasksOperations", Task],
):
    def __init__(self, backend, graph_intel=None, ...):
        super().__init__(backend, graph_intel, ...)
    # get_with_context() is inherited — no override, no loader wiring needed.
```

`_CoreIntelligenceMixin[T]` is generic: Tasks, Goals, Habits, PS, LP, and KU
inherit it directly (e.g. `_CoreIntelligenceMixin[PathStep]`) and get a typed
`Result[tuple[T, GraphContext]]` return. Events, Choices, and Principles keep a
per-package `_CoreIntelligenceMixin` wrapper (extending the shared base) only
because they add real domain methods (performance / decision / alignment lenses).
The domain-named aliases (`get_goal_with_context`, etc.) were deleted in the
tasks bloat campaign — generic `get_with_context` is the one path.

For cross-domain **analysis** (metrics + recommendations), use the template method
`BaseAnalyticsService._analyze_entity_with_typed_context(uid, metrics_fn, recommendations_fn)`,
which sources the canonical typed, path-aware context from
`UnifiedRelationshipService.get_cross_domain_context_typed` and is built per-domain via
`{Domain}CrossContext.from_categorized` (`core/models/graph/path_aware_types.py`). All
6 activity domains run on it.

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
        # get_with_context() is inherited from _CoreIntelligenceMixin[NewDomainModel]
        # via mechanism B (self.relationships.get_with_context) — no wiring needed.
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
| `/core/services/intelligence/_core_intelligence_mixin.py` | `_CoreIntelligenceMixin[T]` — shared `get_with_context()` (mechanism B) |
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
- [PROTOCOL_INTEGRATION.md](PROTOCOL_INTEGRATION.md) - IntelligenceOperations + cross-domain context (mechanism B)
