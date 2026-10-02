# Activity Domain Facade Pattern

> The 6 Activity Domains (Tasks, Goals, Habits, Events, Choices, Principles) share one facade shape: explicit, typed delegation methods over sub-services.

## Facade Structure

```python
class TasksService(
    _OrchestrationMixin,                    # domain-specific facade mixin(s)
    KnowledgeIntelligenceDelegationMixin,   # the 4 shared knowledge methods
    BaseService["TasksOperations", Task, TaskUpdateIntent],
):
    # Class-level annotations (for IDE and MyPy)
    core: TasksCoreService
    search: TasksSearchOperations
    relationships: UnifiedRelationshipService
    intelligence: TasksIntelligenceService
    ai: TasksAIService | None               # None when INTELLIGENCE_TIER=core

    # Explicit delegation methods — one typed method per delegated call
    async def get_task(self, task_uid: str) -> Result[Task]:
        return await self.core.get_task(task_uid)

    async def link_task_to_goal(
        self,
        task_uid: str,
        goal_uid: str,
        contribution_percentage: float = 0.1,
        milestone_uid: str | None = None,
    ) -> Result[bool]:
        # The facade names the explicit registry method_key and what the far end must be;
        # create_relationship validates the key and admits the far end (exists, a Goal, the
        # task owner's own) before it writes.
        return await self.relationships.create_relationship(
            "contributes_to_goal",
            task_uid,
            goal_uid,
            {"contribution_percentage": contribution_percentage, "milestone_uid": milestone_uid},
            far_end=GOAL_FAR_END,
        )
```

## Common Sub-services (All 6 Domains)

Every facade carries these seven slots. Most come from `create_common_sub_services()`; see
[Factory Pattern](#factory-pattern) for the ones a facade builds itself.

| Sub-service | Purpose | Key Methods |
|-------------|---------|-------------|
| `core` | CRUD operations | `create_*`, `update_*`, `delete_*`, `get_*` |
| `search` | Text search, filtering | `search()`, `get_by_status()`, `get_by_category()` |
| `relationships` | Cross-domain links | `create_relationship(method_key, ...)`, `delete_relationship()`, `get_related_uids()` |
| `intelligence` | Analysis & insights (no AI) | `get_with_context()`, `get_performance_analytics()`, `get_domain_insights()` |
| `event_handler` | Fire-and-forget reactive handlers | `handle_*` subscribers, `InsightStore` writes |
| `learning` | Curriculum-aware suggestions for the domain | e.g. `suggest_learning_aligned_tasks()`, `get_learning_habits()` |
| `knowledge_intelligence` | Shared `ActivityKnowledgeIntelligenceService` singleton | the 4 methods of `KnowledgeIntelligenceDelegationMixin` |

## Domain-Specific Sub-services

Beyond the seven, plus `ai` (FULL tier) on every facade. Read each facade's `__init__` for the
authoritative list.

| Domain | Extra sub-services | Facade mixins |
|--------|-------------------|---------------|
| **Tasks** | `progress`, `scheduling`, `planning` | `_OrchestrationMixin` |
| **Goals** | `progress`, `scheduling`, `planning` | `_OrchestrationMixin` |
| **Habits** | `completions`, `progress`, `planning`, `scheduling`, `patterns` (+ post-wired `goals_service`) | `_CompletionMixin`, `_EnrichmentMixin`, `_OrchestrationMixin` |
| **Events** | `habits` (`EventsHabitIntegrationService`), `progress`, `scheduling` | `_OrchestrationMixin`, `_SchedulingMixin` |
| **Choices** | — | `_OptionManagementMixin` |
| **Principles** | `alignment`, `planning` | `_EmbodimentMixin`, `_GravityMixin`, `_EnrichmentMixin` |

## Explicit Delegation Pattern

Each facade method is a real, typed `async def` that delegates to a sub-service:

```python
# Simple delegation (most methods)
async def get_task(self, task_uid: str) -> Result[Task]:
    return await self.core.get_task(task_uid)

# Orchestration (when logic spans multiple sub-services)
# Side effects belong in event subscribers, not inline — keep orchestration a pure delegation
async def update_task(self, task_uid: str, intent: TaskUpdateIntent) -> Result[Task]:
    habit_uid, applies_knowledge_uids, prop_intent = self._split_relationship_intent(intent)
    result = await self.core.update_task(task_uid, prop_intent)  # events fire here
    ...  # then sync the habit / knowledge / goal edges
```

**Why explicit methods?**
- MyPy sees every method natively — no parallel protocol file needed
- The facade IS the contract routes type against (see the Protocol-Based Architecture table in CLAUDE.md)

## Route Files Use Concrete Class Types

```python
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from adapters.inbound.fasthtml_types import FastHTMLApp, RouteDecorator
    from core.services.goals_service import GoalsService
    from core.services.tasks_service import TasksService


def create_tasks_api_routes(
    app: FastHTMLApp,
    rt: RouteDecorator,
    tasks_service: TasksService,
    goals_service: GoalsService,
    **_kwargs: Any,  # boundary: route-registry — the config's other related services (habits_service, user_service)
) -> None:
    async def update_status(uid: str, new_status: str) -> Result[Task]:
        return await tasks_service.update_task(uid, TaskUpdateIntent(status=new_status))
    ...
```

## Factory Pattern

`create_common_sub_services()` (`core/services/activity_domain_config.py`) builds the slots from
`ACTIVITY_DOMAIN_CONFIGS[domain]`:

- `core`, `search`, `relationships` — always, unless named in `skip` (the only valid `skip`
  names; anything else raises `ValueError`).
- `intelligence` — only when the domain's `intelligence_class` is set. Today that is Principles
  alone; the other five set it to `None` and their facades build intelligence with a
  domain-specific dependency (Tasks: `event_bus`; Goals: `progress_service`; Habits, Choices,
  Events: `cross_domain_query`).
- `event_handler`, `learning` — always.
- `knowledge_intelligence` — passed through from `activity_knowledge_intelligence`.

```python
def __init__(self, backend, graph_intel, cross_domain_query, event_bus=None,
             insight_store=None, activity_knowledge_intelligence=None, ai_service=None):
    super().__init__(backend, "events")

    common: CommonSubServices[
        EventsCoreService, EventsSearchOperations, EventsIntelligenceService
    ] = create_common_sub_services(
        domain="events",
        backend=backend,
        graph_intel=graph_intel,
        event_bus=event_bus,
        insight_store=insight_store,
        activity_knowledge_intelligence=activity_knowledge_intelligence,
    )
    self.core = common.core
    self.search = common.search
    self.relationships = common.relationships
    # intelligence_class is None for Events — build it with cross_domain_query
    self.intelligence = EventsIntelligenceService(
        backend=backend,
        graph_intel=graph_intel,
        relationship_service=self.relationships,
        cross_domain_query=cross_domain_query,
        insight_store=insight_store,
    )
    self.event_handler = common.event_handler
    self.learning = common.learning
    self.knowledge_intelligence = common.knowledge_intelligence

    # Domain-specific sub-services
    self.habits = EventsHabitIntegrationService(backend=backend, event_bus=event_bus)
    self.progress = EventsProgressService(backend=backend, event_bus=event_bus)
```

`skip` avoids constructing a sub-service the facade builds itself. Tasks is the one caller:

```python
common = create_common_sub_services(
    domain="tasks", backend=backend, graph_intel=graph_intel, event_bus=event_bus,
    insight_store=insight_store, skip={"core"},
    activity_knowledge_intelligence=activity_knowledge_intelligence,
)
self.core = TasksCoreService(
    backend=backend, ku_inference_service=ku_inference_service, event_bus=event_bus
)
# Tasks also builds its own event_handler, to wire ku_generation_service into it
```

## Adding New Facade Methods

Add the method to the sub-service, then one typed delegation method to the facade:

```python
# 1. Add to sub-service
class TasksCoreService(...):
    async def my_new_method(self, arg: str) -> Result[Task]:
        ...

# 2. Add delegation to facade
class TasksService(...):
    async def my_new_method(self, arg: str) -> Result[Task]:
        return await self.core.my_new_method(arg)
```

## Cross-Domain Dependencies

When a facade needs another domain's service (circular at construction time), post-wire it in
`services_bootstrap/compose.py`. Habits is the one case:

```python
# HabitsService.__init__ — declared, not yet wired (import GoalsService under TYPE_CHECKING)
self.goals_service: GoalsService | None = None

# services_bootstrap/compose.py — post-wire after all services exist
activity_services["habits"].goals_service = activity_services["goals"]
```

`HabitsService` declares the slot `Any` today; type a new post-wired slot against the facade,
as above.

Orchestration methods (`create_with_goal_links`, `complete_with_goal_impacts`) use
`self.goals_service` — routes never pass cross-domain services as parameters.

### Cross-Domain Read Queries

Cross-domain *reads* that span 2+ domain labels go through `CrossDomainQueryService`
(`core/services/cross_domain/`), not through domain backends or fan-out loops. All 6 Activity
Domain facades take it as a required constructor argument:

```python
class GoalsService(...):
    def __init__(self, backend, graph_intel, cross_domain_query, ...):
        self.cross_domain_query = cross_domain_query
```

`CrossDomainQueryService` holds a `CrossDomainBackendOperations` backend
(`adapters/persistence/neo4j/cross_domain_backend.py` owns the Cypher), makes one backend call
per method, and returns frozen typed dataclasses from `cross_domain_types.py`.

## Backend Sharing

All sub-services share ONE domain-specific backend instance (no wrappers). Activity Domains use
subclasses from `adapters/persistence/neo4j/backends/activity_backends.py`, which add
domain-specific Cypher on top of `UniversalNeo4jBackend`. **Cypher lives below the boundary in
`adapters/persistence/neo4j/`** — services call `self.backend.method_name()`; SKUEL021 refuses
raw Cypher in `core/`. The MEGA-QUERY is `adapters/persistence/neo4j/user_context_queries.py`.

```python
# In services_bootstrap/_backends.py
from adapters.persistence.neo4j.backends.activity_backends import TasksBackend

tasks_backend = TasksBackend(
    driver,
    NeoLabel.TASK,
    Task,
    prometheus_metrics=prometheus_metrics,
    base_label=NeoLabel.ENTITY,  # Produces :Entity:Task multi-label nodes
)
```

`base_label=NeoLabel.ENTITY` is required for all Activity Domains — it's what makes Neo4j create
`(n:Entity:Task)` multi-label nodes, enabling universal Entity queries to work.

Each Activity Domain backend extends `_HierarchyMixin` for parent-child ops (HAS_SUBTASK,
HAS_SUBGOAL, etc.). Most add domain-specific methods such as `get_stats_for_user()`.
HabitsBackend additionally has badge/achievement methods: per-habit streak badges
(`award_badge`, `check_badge_already_earned`) and cross-habit aggregate badges
(`award_user_badge`, `check_user_badge_earned`, `get_user_badge_stats`), and
`get_habit_window_completions` — each habit's completions in the adherence window, the count
`HabitsService.get_adherence_rates` turns into rates (`core/models/habit/adherence.py`).
