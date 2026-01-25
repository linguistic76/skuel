# Activity Domain Facade Pattern

> All 6 Activity Domains use identical facade architecture with FacadeDelegationMixin.

## Facade Structure

```python
class TasksService(FacadeDelegationMixin, BaseService[TasksOperations, Task]):
    # Class-level type annotations for signature preservation
    core: TasksCoreService
    search: TasksSearchService
    relationships: UnifiedRelationshipService
    intelligence: TasksIntelligenceService

    _delegations = merge_delegations(
        {"get_task": ("core", "get_task"), ...},
        {"search": ("search", "search"), ...},
        create_relationship_delegations("task"),
        {"get_task_with_context": ("intelligence", ...), ...},
    )
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

## FacadeDelegationMixin

Auto-generates delegation methods from `_delegations` dict:

```python
_delegations = {
    "facade_method_name": ("sub_service_attr", "sub_service_method"),
}
```

**Signature Preservation**: Class-level type annotations enable `inspect.signature()` to return actual parameters instead of `(*args, **kwargs)`.

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
    # Note: TasksAnalyticsService removed January 2026 - KU analytics are now direct
```

## Adding New Facade Methods

**Option 1: Delegation (preferred for simple pass-through)**
```python
_delegations = merge_delegations(
    existing_delegations,
    {"new_method": ("sub_service", "method_name")},
)
```

**Option 2: Explicit method (for custom logic)**
```python
async def complex_operation(self, uid: str, ...) -> Result[Entity]:
    # Custom orchestration across sub-services
    context = await self.intelligence.get_with_context(uid)
    if context.is_error:
        return context
    # ... additional logic
    return await self.core.update(uid, updates)
```

## Relationship Delegations

Factory-generated via `create_relationship_delegations()`:

```python
from core.services.mixins import create_relationship_delegations

_delegations = merge_delegations(
    core_delegations,
    create_relationship_delegations("task"),  # Generates ~8 methods
)
```

Generated methods:
- `get_task_cross_domain_context()`
- `link_to_goal()`, `link_to_principle()`, `link_to_knowledge()`
- `get_related_uids()`, `get_entity_with_context()`

## Backend Sharing

All sub-services share ONE backend instance (no wrappers):

```python
# In services_bootstrap.py
tasks_backend = UniversalNeo4jBackend[Task](driver, NeoLabel.TASK, Task)

# Passed to all sub-services
self.core = TasksCoreService(backend=tasks_backend)
self.search = TasksSearchService(backend=tasks_backend)
```
