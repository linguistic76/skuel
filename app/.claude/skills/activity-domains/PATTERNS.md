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

**Problem**: UI list views need fetch → stats → filter → sort orchestration. The same 4-step pattern was duplicated across all 6 Activity domains and needed to extend to Curriculum domains for intelligence service consumption.

**Solution**: All 11 domain facades (6 Activity + 5 Curriculum) expose `get_filtered_context()` returning `Result[ListContext]`, satisfying the `FilteredContextProvider` protocol. A shared skeleton (`build_filtered_context()`) enforces the pattern; domains provide callables for their stats, filters, and sort logic.

**Two consumers**: UI routes (per-domain filtered list pages) and intelligence services (on-demand domain-specific queries via `FilteredContextProvider` protocol). UserContext is the broad snapshot (MEGA_QUERY); `get_filtered_context()` is the per-domain zoom lens.

```python
from core.ports.query_types import ListContext  # TypedDict: entities, stats, metadata?

# In route handler:
result = await habits_service.get_filtered_context(user_uid, status_filter="active", sort_by="streak")
if result.is_error:
    return render_error_banner("Failed to load habits")
ctx = result.value
habits, stats = ctx["entities"], ctx["stats"]

# In intelligence services (domain-agnostic via protocol):
provider: FilteredContextProvider = self.filtered_providers["habits"]
result = await provider.get_filtered_context(user_uid, status_filter="active")
```

**Method signatures (Activity Domains — 6):**

| Service | Signature |
|---------|-----------|
| `HabitsService` | `get_filtered_context(user_uid, status_filter="active", sort_by="streak")` |
| `TasksService` | `get_filtered_context(user_uid, project=None, assignee=None, due_filter=None, status_filter="active", sort_by="due_date")` |
| `GoalsService` | `get_filtered_context(user_uid, status_filter="active", sort_by="target_date")` |
| `EventsService` | `get_filtered_context(user_uid, status_filter="scheduled", sort_by="start_time")` |
| `ChoicesService` | `get_filtered_context(user_uid, status_filter="pending", sort_by="deadline")` |
| `PrinciplesService` | `get_filtered_context(user_uid, category_filter="all", strength_filter="all", sort_by="strength")` |

**Method signatures (Curriculum Domains — 5):**

| Service | Signature |
|---------|-----------|
| `LessonService` | `get_filtered_context(user_uid, status_filter="all", sort_by="title")` |
| `KuService` | `get_filtered_context(user_uid, status_filter="all", sort_by="title")` |
| `LsService` | `get_filtered_context(user_uid, status_filter="all", sort_by="title")` |
| `LpService` | `get_filtered_context(user_uid, status_filter="all", sort_by="title")` |
| `ExerciseService` | `get_filtered_context(user_uid, status_filter="all", sort_by="title")` |

**Shared skeleton** (`core/services/filtered_context.py`):

Each facade calls `build_filtered_context()` with domain-specific callables:
1. `fetch_all` — async callable returning all entities (one query)
2. `compute_stats` — stats from the full set (pre-filter)
3. `apply_filters` — domain-specific status/secondary filters (captures params via closure)
4. `apply_sort` — domain-specific sort
5. `compute_metadata` — optional domain-specific extras (Tasks: project/assignee lists)

**`FilteredContextProvider` protocol** (`core/ports/filtered_context_protocols.py`):

Common params: `user_uid`, `status_filter`, `sort_by`. Concrete facades add domain-specific params with defaults, satisfying structural subtyping. Intelligence services call via the protocol; UI routes call concrete classes directly.

**`ListContext` TypedDict** (`core/ports/query_types.py`): `entities` (filtered list), `stats` (dict[str, int | float]), `metadata` (dict[str, Any], optional — Tasks uses for project/assignee dropdowns).

**Module-level helpers** (Python-side, in each `*_service.py` facade file):
- `_compute_{domain}_stats(entities)` — stats from full set (all 11 domains)
- `_apply_{domain}_status_filter(entities, status_filter)` — status filter (Activity domains)
- `_apply_{domain}_sort(entities, sort_by)` — pure sort logic (all 11 domains)
- `_apply_task_secondary_filters(tasks, project, assignee, due_filter)` — Tasks only
- `_apply_principle_filters(principles, category_filter, strength_filter, status_filter)` — Principles only
- `_compute_task_metadata(all_tasks)` — Tasks only (project/assignee lists)

**Route file convention** (all 6 `*_ui.py` files, module-level not inside factory):
- **Filters:** All 6 domains use `ActivityFilters` hierarchy from `form_helpers.py`. Goals, Habits, Events, Choices use base `ActivityFilters` + `parse_activity_filters()`. Tasks use `TaskFilters(ActivityFilters)` + `parse_task_filters()`. Principles use `PrincipleFilters(ActivityFilters)` + `parse_principle_filters()`.
- `parse_{domain}_filters(request) -> TaskFilters | PrincipleFilters | ActivityFilters` — extracts query params with domain-specific defaults
- `parse_{domain}_create_request(form_data) -> {Domain}CreateRequest` — pure form→request parsing (no service calls)
- `parse_{domain}_update_payload(form) -> dict[str, Any]` — pure form→update dict parsing
- Static option lists as module-level constants (e.g., Choices: `CHOICE_TYPES`, `DOMAINS`)
- All string extraction uses `safe_form_string()` from `adapters.inbound.form_helpers` (not raw `.get().strip()`)
- All enum parsing uses `parse_enum_safe()` from `form_helpers` — prevents 500s from crafted form values
- Date/time parsing uses `parse_date_safe()`, `parse_time_safe()`, `parse_datetime_safe()` from `form_helpers`

**Route handlers stay thin:** authenticate → parse → call service → handle error → render. All form parsing and enum conversion lives in the pure helpers above, not inline in route handlers.

**Domain-specific analytics** live on the service facade, not in route closures. Examples: `ChoicesService.get_analytics_context(user_uid)` → `Result[ChoicesAnalyticsContext]`, `PrinciplesService.get_analytics_summary(user_uid)` → `Result[dict]` (total, core_count, adherence, reflections).

**Tests:** `tests/unit/services/activity/test_activity_query_helpers.py` — 49 tests covering remaining Python-side helpers (sort, task secondary filters, principle filters).

---

**See Also**: [SKILL.md](SKILL.md) for domain overview, [FACADE_PATTERN.md](FACADE_PATTERN.md) for facade architecture
