# Activity Domain Facade Pattern

> The 6 Activity Domains (Tasks, Goals, Habits, Events, Choices, Principles) use identical facade architecture with explicit delegation methods (February 2026).

## Facade Structure

```python
from typing import Any

class TasksService(KnowledgeIntelligenceDelegationMixin, BaseService[TasksOperations, Task]):
    # Class-level type annotations (for IDE and MyPy)
    core: TasksCoreService
    search: TasksSearchService
    relationships: UnifiedRelationshipService
    intelligence: TasksIntelligenceService
    # KnowledgeIntelligenceDelegationMixin provides 4 knowledge methods
    # AI sub-services (.ai) restored (2026-03-29). Some analytics sub-services
    # removed as the UI shifted to read-focused pattern.

    # Explicit delegation methods — one line per delegated method
    async def get_task(self, *args: Any, **kwargs: Any) -> Any:
        return await self.core.get_task(*args, **kwargs)

    async def search_tasks(self, *args: Any, **kwargs: Any) -> Any:
        return await self.search.search(*args, **kwargs)

    async def link_to_goal(self, *args: Any, **kwargs: Any) -> Any:
        return await self.relationships.link_to_goal(*args, **kwargs)

    async def get_task_with_context(self, *args: Any, **kwargs: Any) -> Any:
        return await self.intelligence.get_task_with_context(*args, **kwargs)
```

## Common Sub-services (All 6 Domains)

Created via `create_common_sub_services()` factory:

| Sub-service | Purpose | Key Methods |
|-------------|---------|-------------|
| `core` | CRUD operations | `create_*`, `update_*`, `delete_*`, `get_*` |
| `search` | Text search, filtering | `search()`, `get_by_status()`, `get_prioritized()` |
| `relationships` | Cross-domain links | `link_to_goal()`, `link_to_principle()`, `get_related_uids()` |
| `intelligence` | Analysis & insights | `get_*_with_context()`, domain-specific analysis |

## Domain-Specific Sub-services

> **Note:** Some domain-specific analytics sub-services (`TasksProductivityService`, `PrinciplesReflectionService`, `HabitsGoalAnalyticsService`) were removed when the UI shifted to a read-focused pattern. AI sub-services (`.ai`) are active. Check each facade's current `__init__` for active sub-services.

| Domain | Extra Sub-services |
|--------|-------------------|
| **Tasks** | `progress`, `scheduling`, `planning`, `event_handler` |
| **Goals** | `progress`, `scheduling`, `learning`, `planning`, `event_handler` |
| **Habits** | `progress`, `completions`, `planning`, `scheduling`, `learning`, `event_integration`, `event_handler`, `patterns` — plus 3 **facade mixins**: `_CompletionMixin`, `_EnrichmentMixin`, `_OrchestrationMixin` (April 2026) |
| **Events** | `habits` (integration), `learning` |
| **Choices** | `learning`, `event_handler` |
| **Principles** | `alignment`, `learning`, `planning`, `event_handler` — plus 3 **facade mixins**: `_EmbodimentMixin`, `_GravityMixin`, `_EnrichmentMixin` (April 2026) |

## Explicit Delegation Pattern

Each facade method is a real `async def` that delegates to a sub-service:

```python
# Simple delegation (most methods)
async def get_task(self, *args: Any, **kwargs: Any) -> Any:
    return await self.core.get_task(*args, **kwargs)

# Custom orchestration (when logic spans multiple sub-services)
# Side effects belong in event subscribers, not inline — keep orchestration a pure delegation
async def complete_task_with_cascade(self, task_uid: str, ...) -> Result[Task]:
    return await self.progress.complete_task_with_cascade(task_uid, ...)
```

**Why explicit methods?**
- MyPy sees all methods natively — no parallel protocol file needed
- `FacadeDelegationMixin` and `facade_protocols.py` are deleted (February 2026)
- 2,422 lines removed across 9 facade services

## Route Files Use Concrete Class Types

```python
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from core.services.tasks_service import TasksService

def create_tasks_api_routes(
    app: Any, rt: Any, tasks_service: "TasksService", ...
) -> list[Any]:
    result = await tasks_service.create_task(body, user_uid)
```

## Factory Pattern

```python
from core.services.activity_domain_config import create_common_sub_services

def __init__(self, backend, graph_intel, cross_domain_query,
             event_bus=None, activity_knowledge_intelligence=None):
    super().__init__(backend, "events")

    # Skip intelligence — created manually to receive cross_domain_query
    common = create_common_sub_services(
        domain="events",
        backend=backend,
        graph_intel=graph_intel,
        event_bus=event_bus,
        skip={"intelligence"},
    )
    self.core = common.core
    self.search = common.search
    self.relationships = common.relationships
    self.intelligence = EventsIntelligenceService(
        backend=backend,
        graph_intel=graph_intel,
        relationship_service=self.relationships,
        cross_domain_query=cross_domain_query,
    )

    # Knowledge intelligence — shared singleton, assigned directly (mixin provides methods)
    self.knowledge_intelligence = activity_knowledge_intelligence

    # Domain-specific sub-services (manual creation)
    self.progress = EventsProgressService(backend=backend, event_bus=event_bus)
```

The `skip` parameter avoids constructing sub-services the facade replaces manually:

```python
# Tasks skips core + intelligence (needs domain-specific parameters)
common = create_common_sub_services(
    domain="tasks", backend=backend, graph_intel=graph_intel,
    event_bus=event_bus, skip={"core", "intelligence"},
)
self.search = common.search
self.relationships = common.relationships
# Then create core/intelligence manually with extra params
self.core = TasksCoreService(backend=backend, ku_inference_service=ku_inference_service, ...)

# Events skips intelligence only (core/search/relationships are standard)
common = create_common_sub_services(
    domain="events", backend=backend, graph_intel=graph_intel,
    event_bus=event_bus, skip={"intelligence"},
)
self.intelligence = EventsIntelligenceService(
    backend=backend,
    graph_intel=graph_intel,
    relationship_service=common.relationships,
    cross_domain_query=cross_domain_query,
)
```

## Adding New Facade Methods

Add the method to the sub-service, then add one delegation line to the facade:

```python
# 1. Add to sub-service
class TasksCoreService(BaseService[...]):
    async def my_new_method(self, arg: str) -> Result[Task]:
        ...

# 2. Add delegation to facade
class TasksService(BaseService[...]):
    async def my_new_method(self, *args: Any, **kwargs: Any) -> Any:
        return await self.core.my_new_method(*args, **kwargs)
```

## Cross-Domain Dependencies

When a facade needs another domain's service (circular at construction time), use post-wiring in `services_bootstrap/compose.py`:

```python
# In __init__ — declare as None
self.goals_service: Any = None

# In services_bootstrap/compose.py — post-wire after all services exist
activity_services["habits"].goals_service = activity_services["goals"]
```

Orchestration methods use `self.goals_service` — routes never pass cross-domain services as parameters.

### Cross-Domain Read Queries (April 2026)

Cross-domain *reads* that span 2+ domain labels go through `CrossDomainQueryService` (`core/services/cross_domain/`), not through domain backends or fan-out loops. All 6 Activity Domain facades receive it as a required constructor dependency:

```python
class GoalsService(...):
    def __init__(self, backend, graph_intel, cross_domain_query, ...):
        self.cross_domain_query = cross_domain_query
```

This replaces the old pattern of domain services calling `self.backend.find_by()` across multiple types and joining in Python. `CrossDomainQueryService` takes only a `QueryExecutor`, runs one Cypher per call, and returns frozen typed dataclasses from `cross_domain_types.py`. When a facade's intelligence sub-service needs `cross_domain_query`, skip `intelligence` in the factory and create it manually (see Events example above).

## Backend Sharing

All sub-services share ONE domain-specific backend instance (no wrappers). Activity Domains use subclasses from `backends/activity_backends.py`, which add domain-specific relationship Cypher on top of `UniversalNeo4jBackend`. **Single-domain Cypher lives in backends — services delegate, never execute inline Cypher.** The two service-layer exceptions are `user_context_queries.py` (MEGA-QUERY) and `CrossDomainQueryService` (targeted cross-domain reads), both of which use `QueryExecutor` directly for explicitly cross-domain Cypher.

```python
# In services_bootstrap/_backends.py
from adapters.persistence.neo4j.backends.activity_backends import TasksBackend

tasks_backend = TasksBackend(
    driver, NeoLabel.TASK, Task,
    base_label=NeoLabel.ENTITY,  # Produces :Entity:Task multi-label nodes
)

# Shared across all sub-services — passed via TasksService.__init__
self.core = TasksCoreService(backend=tasks_backend)
self.search = TasksSearchService(backend=tasks_backend)
```

`base_label=NeoLabel.ENTITY` is required for all Activity Domains — it's what makes Neo4j create `(n:Entity:Task)` multi-label nodes, enabling universal Entity queries to work.

Each Activity Domain backend extends `_HierarchyMixin` for parent-child ops (HAS_SUBTASK, HAS_SUBGOAL, etc.) plus domain-specific methods like `get_stats_for_user()`. HabitsBackend additionally has badge/achievement methods: per-habit streak badges (`award_badge`, `check_badge_already_earned`) and cross-habit aggregate badges (`award_user_badge`, `check_user_badge_earned`, `get_user_badge_stats`).
