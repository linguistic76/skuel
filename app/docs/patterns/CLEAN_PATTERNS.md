---
title: Clean Patterns Reference
updated: '2026-09-23'
category: patterns
related_skills: []
related_docs: []
---
# Clean Patterns Reference

Established patterns for SKUEL service development, each shown on real code. Every section points at the doc that holds the full treatment.

## Enum Value Extraction

```python
from core.utils.type_converters import EnumLike, get_enum_value

# For any enum value extraction:
value = get_enum_value(some_enum)  # Returns enum.value or object itself

# For type checking:
if isinstance(obj, EnumLike):
    # Object has .value attribute
```

**Rules:**
- Do not use lambda expressions (SKUEL012)

## Composition Root Pattern

`compose_services()` (`services_bootstrap/compose.py`) is the single place service wiring happens — explicit constructor injection, no reflection:

```python
async def compose_services(
    neo4j_adapter: Any,
    event_bus: EventBusOperations | None = None,
    config: Any = None,
    prometheus_metrics: PrometheusMetrics | None = None,
    metrics_cache: Any = None,
) -> Result[Services]:
```

It builds backends, then facades, then orchestrators, and returns them in one `Services` dataclass (`services_bootstrap/_container.py`).

## Protocol-Based Dependency Injection

Services type their backend against a `core/ports` protocol; the adapter is injected at the composition root (SKUEL022/SKUEL023):

```python
# core/services/tasks_service.py
class TasksService(...):
    def __init__(
        self,
        backend: TasksOperations,  # core/ports/domain_protocols.py
        cross_domain_query: CrossDomainQueryService,
        graph_intel: GraphIntelligenceService,
        ...
    ) -> None:
```

**See:** `/docs/patterns/protocol_architecture.md`

## Universal Backend Pattern

One generic backend, `UniversalNeo4jBackend[T]`, serves every entity type; a domain backend subclasses it and adds its domain-specific Cypher:

```python
# adapters/persistence/neo4j/backends/activity_backends.py
class TasksBackend(_HierarchyMixin, UniversalNeo4jBackend[Task]): ...

# services_bootstrap/_backends.py
tasks_backend = TasksBackend(
    driver,
    NeoLabel.TASK,
    Task,
    prometheus_metrics=prometheus_metrics,
    base_label=NeoLabel.ENTITY,  # multi-label CREATE: (n:Entity:Task)
)
```

**See:** `/docs/patterns/MODEL_TO_ADAPTER_DYNAMIC_ARCHITECTURE.md`

## Result[T] Error Handling

Services return `Result[T]`; routes convert to HTTP at the boundary. `require_found` (`adapters/inbound/result_helpers.py`) is the route-side fetch + not-found guard:

```python
# adapters/inbound/admin_api.py
@rt("/api/admin/users/get")
@require_admin(get_user_service)
@boundary_handler()
async def get_user_details(request: Request, uid: str, current_user: Any = None):
    found = require_found(await user_service.get_user(uid), "User", uid)
    if found.is_error:
        return found
    user = found.value
    ...
```

**See:** `/docs/patterns/ERROR_HANDLING.md`

## Three-Tier Type System

External → Transfer → Core, shown on Task:

| Tier | Class | Location |
|------|-------|----------|
| 1. Pydantic (external validation) | `TaskCreateRequest` | `core/models/task/task_request.py` |
| 2. DTO (mutable transfer) | `TaskDTO` (`@dataclass`) | `core/models/task/task_dto.py` |
| 3. Domain model (immutable) | `Task` (`@dataclass(frozen=True, kw_only=True)`) | `core/models/task/task.py` |

**See:** `/docs/patterns/three_tier_type_system.md`

## Fail-Fast Architecture

A required dependency is checked at construction and refused loudly:

```python
# core/services/ku_service.py — KuService.__init__
if not backend:
    raise ValueError(
        "KuService backend is REQUIRED. "
        "SKUEL follows fail-fast architecture — all required dependencies "
        "must be provided at initialization."
    )
```

An *optional* Digital-layer dependency (ADR-043) is the one exception: it is checked at use and reported as `Errors.unavailable`, never silently skipped:

```python
# core/services/base_ai_service.py
if not self.llm:
    return Result.fail(
        Errors.unavailable(
            feature="ai_insights",
            reason="LLM service not configured",
            operation="generate_insight",
        )
    )
```

## Related Documentation

- `/docs/patterns/three_tier_type_system.md` - Full type system documentation
- `/docs/patterns/ERROR_HANDLING.md` - Error handling patterns
- `/docs/patterns/protocol_architecture.md` - Protocol architecture
- `/services_bootstrap/compose.py` - Composition root implementation
