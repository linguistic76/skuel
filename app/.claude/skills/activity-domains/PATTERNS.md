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

## Pattern: Filtered List Queries (`get_filtered_context`)

**Problem**: UI list views need fetch → stats → filter → sort orchestration. Writing this as closures inside route factories made it untestable and duplicated the same 4-step pattern across all 6 domains.

**Solution**: Each service facade exposes `get_filtered_context()` returning `Result[ListContext]`. Stats are computed over the full list *before* filtering, so they always reflect totals.

```python
from core.ports.query_types import ListContext  # TypedDict: {"entities": list[Any], "stats": dict[str, int]}

# In route handler:
result = await habits_service.get_filtered_context(user_uid, status_filter="active", sort_by="streak")
if result.is_error:
    return render_error_banner("Failed to load habits")
ctx = result.value
habits, stats = ctx["entities"], ctx["stats"]
```

**Method signatures (all 6 domains):**

| Service | Signature |
|---------|-----------|
| `HabitsService` | `get_filtered_context(user_uid, status_filter="active", sort_by="streak")` |
| `TasksService` | `get_filtered_context(user_uid, project=None, assignee=None, due_filter=None, status_filter="active", sort_by="due_date")` |
| `GoalsService` | `get_filtered_context(user_uid, status_filter="active", sort_by="target_date")` |
| `EventsService` | `get_filtered_context(user_uid, status_filter="scheduled", sort_by="start_time")` |
| `ChoicesService` | `get_filtered_context(user_uid, status_filter="pending", sort_by="deadline")` |
| `PrinciplesService` | `get_filtered_context(user_uid, category_filter="all", strength_filter="all", sort_by="strength")` |

**Module-level helpers** (each `*_service.py` facade file, directly importable for unit tests):
- `_compute_{domain}_stats(entities)` — stats BEFORE filtering
- `_apply_{domain}_filters(entities, ...)` — pure filter logic
- `_apply_{domain}_sort(entities, sort_by)` — pure sort logic

**Route file convention** (all 6 `*_ui.py` files, module-level not inside factory):
- `@dataclass class Filters` — typed filter container
- `parse_filters(request) -> Filters` — extracts query params
- `validate_*_form_data(form_data) -> Result[None]` — called by `create_*_from_form`

**Tests:** `tests/unit/services/activity/test_activity_query_helpers.py` — 78 tests covering all helpers.

---

**See Also**: [SKILL.md](SKILL.md) for domain overview, [FACADE_PATTERN.md](FACADE_PATTERN.md) for facade architecture
