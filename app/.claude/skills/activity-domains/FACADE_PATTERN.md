# Activity Domain Facade Pattern

> All 6 Activity Domains use identical facade architecture with explicit delegation methods (February 2026).

## Facade Structure

```python
from typing import Any

class TasksService(BaseService[TasksOperations, Task]):
    # Class-level type annotations (for IDE and MyPy)
    core: TasksCoreService
    search: TasksSearchService
    relationships: UnifiedRelationshipService
    intelligence: TasksIntelligenceService

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

| Domain | Extra Sub-services |
|--------|-------------------|
| **Tasks** | `progress`, `scheduling`, `analytics` |
| **Goals** | `analytics` |
| **Habits** | `completion`, `streak` |
| **Events** | `habits` (integration), `learning` |
| **Choices** | `learning`, `analytics` |
| **Principles** | `alignment`, `learning`, `reflection` |

## Explicit Delegation Pattern

Each facade method is a real `async def` that delegates to a sub-service:

```python
# Simple delegation (most methods)
async def get_task(self, *args: Any, **kwargs: Any) -> Any:
    return await self.core.get_task(*args, **kwargs)

# Custom orchestration (when logic spans multiple sub-services)
async def complete_task_with_cascade(self, task_uid: str, ...) -> Result[Task]:
    result = await self.progress.complete_task_with_cascade(task_uid, ...)
    if result.is_ok:
        await self._trigger_knowledge_generation()
    return result
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
from core.utils.activity_domain_config import create_common_sub_services

def __init__(self, backend, graph_intelligence_service, event_bus=None):
    super().__init__(backend, "tasks")

    # Create 4 common sub-services via factory
    common = create_common_sub_services(
        domain="tasks",
        backend=backend,
        graph_intel=graph_intelligence_service,
        event_bus=event_bus,
    )
    self.core = common.core
    self.search = common.search
    self.relationships = common.relationships
    self.intelligence = common.intelligence

    # Domain-specific sub-services (manual creation)
    self.progress = TasksProgressService(backend=backend)
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

## Backend Sharing

All sub-services share ONE domain-specific backend instance (no wrappers). Activity Domains use `domain_backends.py` subclasses, which add domain-specific relationship Cypher on top of `UniversalNeo4jBackend`:

```python
# In services_bootstrap.py
from adapters.persistence.neo4j.domain_backends import TasksBackend

tasks_backend = TasksBackend(
    driver, NeoLabel.TASK, Task,
    base_label=NeoLabel.ENTITY,  # Produces :Entity:Task multi-label nodes
)

# Shared across all sub-services — passed via TasksService.__init__
self.core = TasksCoreService(backend=tasks_backend)
self.search = TasksSearchService(backend=tasks_backend)
```

`base_label=NeoLabel.ENTITY` is required for all Activity Domains — it's what makes Neo4j create `(n:Entity:Task)` multi-label nodes, enabling universal Entity queries to work.
