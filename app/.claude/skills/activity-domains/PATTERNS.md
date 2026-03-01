# Activity Domains - Route Registration Pattern

> The standard way to wire a new or updated Activity Domain route file.

---

## Pattern: Activity Domain Route File

**Problem**: Every Activity Domain needs CRUD, Query, and Intelligence routes registered identically. Writing this manually produces ~80 lines of near-identical boilerplate per domain.

**Solution**: Use `create_activity_domain_route_config` — pre-populates all three factory configs from a single call.

```python
"""
Tasks Routes - Config-Driven Registration
==========================================

CRUD, Query, and Intelligence factories declared in config.
Status and Analytics factories (runtime closures) remain in tasks_api.py.
"""

from adapters.inbound.route_factories import (
    create_activity_domain_route_config,
    register_domain_routes,
)
from adapters.inbound.tasks_api import create_tasks_api_routes
from adapters.inbound.tasks_ui import create_tasks_ui_routes
from core.models.entity_requests import EntityUpdateRequest as TaskUpdateRequest
from core.models.task.task_request import TaskCreateRequest

TASKS_CONFIG = create_activity_domain_route_config(
    domain_name="tasks",
    primary_service_attr="tasks",
    api_factory=create_tasks_api_routes,
    ui_factory=create_tasks_ui_routes,
    create_schema=TaskCreateRequest,
    update_schema=TaskUpdateRequest,
    uid_prefix="task",
    supports_goal_filter=True,
    supports_habit_filter=True,
    api_related_services={
        "user_service": "user_service",
        "goals_service": "goals",
        "habits_service": "habits",
    },
    prometheus_metrics_attr="prometheus_metrics",
)


def create_tasks_routes(app, rt, services, _sync_service=None):
    """Wire tasks API and UI routes using configuration-driven registration."""
    return register_domain_routes(app, rt, services, TASKS_CONFIG)


__all__ = ["create_tasks_routes"]
```

**What `create_activity_domain_route_config` registers automatically:**
- `CRUDRouteFactory` (create, get, list, update, delete)
- `CommonQueryRouteFactory` (filter by status, domain, goal, habit)
- `IntelligenceRouteFactory` (context, recommendations)

**What remains in `api_factory` (`tasks_api.py`):**
- `StatusRouteFactory` (runtime closures for complete, archive, etc.)
- `AnalyticsRouteFactory` (custom analytics handlers)
- Manual domain-specific routes

---

## Pattern: Adding a Domain-Specific Sub-service

**Problem**: A new capability (e.g., scheduling logic) doesn't fit the generic factory sub-services.

**Solution**: Add to the service `__init__`, then add delegation method to facade.

```python
# 1. In tasks_service.py __init__:
from core.services.tasks.tasks_scheduling_service import TasksSchedulingService

self.scheduling = TasksSchedulingService(backend=backend)

# 2. Add delegation in TasksService facade:
async def get_scheduling_recommendations(self, *args: Any, **kwargs: Any) -> Any:
    return await self.scheduling.get_recommendations(*args, **kwargs)

# 3. In route:
result = await tasks_service.get_scheduling_recommendations(user_uid)
```

---

**See Also**: [SKILL.md](SKILL.md) for domain overview, [FACADE_PATTERN.md](FACADE_PATTERN.md) for facade architecture
