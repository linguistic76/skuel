# Activity Domains - Implementation Patterns

> Implementation patterns shared across the 6 Activity Domains.

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

from typing import Any

from adapters.inbound.fasthtml_types import FastHTMLApp, RouteDecorator
from adapters.inbound.route_factories import (
    create_activity_domain_route_config,
    register_domain_routes,
)
from adapters.inbound.tasks_api import create_tasks_api_routes
from adapters.inbound.tasks_ui import create_tasks_ui_routes
from core.models.task.task_request import TaskCreateRequest, TaskUpdateRequest

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
        "goals_service": "goals",
        "habits_service": "habits",
    },
    prometheus_metrics_attr="prometheus_metrics",
)


def create_tasks_routes(
    app: FastHTMLApp, rt: RouteDecorator, services: Any, _sync_service: Any = None
) -> None:
    """Wire tasks API and UI routes using configuration-driven registration."""
    register_domain_routes(app, rt, services, TASKS_CONFIG)


__all__ = ["create_tasks_routes"]
```

**What `create_activity_domain_route_config` registers automatically:**
- `CRUDRouteFactory` (create, get, list, update, delete)
- `CommonQueryRouteFactory` (filter by status, domain, goal, habit)
- `IntelligenceRouteFactory` (context, recommendations)

**What remains in `api_factory` (`tasks_api.py`):**
- `create_activity_field_api_routes` (inline status/priority card updates)
- `AnalyticsRouteFactory` (custom analytics handlers)
- Manual domain-specific routes

---

## Pattern: Adding a Domain-Specific Sub-service

**Problem**: A new capability (e.g., scheduling logic) doesn't fit the generic factory sub-services.

**Solution**: Add to the service `__init__`, then add delegation method to facade.

```python
# 1. In tasks_service.py __init__:
from core.services.tasks.tasks_scheduling_service import TasksSchedulingService

# Sibling injection: a sub-service that CREATES entities receives the core
# sub-service so its creates run through THE create primitive (events, embedding
# request, guarded link edges) — construct it AFTER self.core. Same shape as
# HabitsPatternService(habits_core=...). Sub-services with no create path take
# only the backend.
self.scheduling = TasksSchedulingService(backend=backend, core=self.core)

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

**Two consumers**: UI routes (per-domain filtered list pages) and intelligence services (`DailyPlanningMixin._generate_domain_health_warnings()` queries all 6 Activity domain stats for aggregate health + cross-domain balance warnings). UserContext is the broad snapshot (MEGA_QUERY); `get_filtered_context()` is the per-domain zoom lens.

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

**Method signatures (Curriculum Domains — 4):**

| Service | Signature |
|---------|-----------|
| `KuService` | `get_filtered_context(user_uid, status_filter="all", sort_by="title")` |
| `PsService` | `get_filtered_context(user_uid, status_filter="all", sort_by="title")` |
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

**`ListContext` TypedDict** (`core/ports/query_types.py`): `entities` (filtered list), `stats` (dict[str, int | float] — guaranteed `total` + `active` keys per `BaseStats` contract), `metadata` (dict[str, Any], optional).

**`BaseStats` contract** (`core/ports/query_types.py`): Every `_compute_*_stats()` function returns at least `total: int` and `active: int`. Domain-specific keys (`overdue`, `streaks`, `pending`, `core`, etc.) are additional. Intelligence consumers can rely on `active` for generic health checks without knowing domain-specific keys.

**Consuming a `ListContext`:** `ctx["entities"]` and `ctx["stats"]` are always present; `metadata` is optional (the TypedDict is `total=False` and `build_filtered_context()` only sets it when a `compute_metadata` callable is passed), so read it as `ctx.get("metadata", {})`. `entities` is typed `list[Any]`, so annotate at the call site to narrow: `tasks: list[Task] = ctx["entities"]`.

**Module-level helpers** (Python-side):
- `compute_{domain}_stats(entities)` — **6 Activity Domain stat functions live in `core/utils/activity_stats.py`** (April 2026 consolidation). Each returns a frozen dataclass (e.g. `TaskStats`, `GoalStats`). Facade-level `_compute_{domain}_stats()` wrappers project these into `dict[str, int | float]` for the `ListContext` contract. Curriculum domains retain stats in their respective facade files.
- `_{DOMAIN}_FILTER_CONFIG: FilterConfig` — **service-layer** declarative filter predicate dict used in `get_filtered_context()` (7 domains; Principles uses multi-dimensional `_apply_principle_filters` instead; KU uses namespace filter; PS/LP have no filtering). Distinct from the **UI-layer** `FILTER_CONFIGS` dict in `ui/activities/filter_bar.py` which drives filter bar rendering.
- `_{DOMAIN}_SORT_CONFIG: SortConfig` — declarative sort key dict (all 11 domains)
- `_apply_{domain}_sort(entities, sort_by)` — thin wrapper calling `apply_entity_sort()` with the domain's `SortConfig`
- `_apply_task_secondary_filters(tasks, project, assignee, due_filter)` — Tasks only
- `_apply_principle_filters(principles, category_filter, strength_filter, status_filter)` — Principles only (multi-dimensional)
- `_compute_task_metadata(all_tasks)` — Tasks: project/assignee lists
- `_compute_principle_metadata(_all)` — Principles: categories from `PrincipleCategory` enum
- `_compute_goal_metadata(_all)` — Goals: categories from `_GOAL_CATEGORIES` constant
- `_compute_habit_metadata(_all)` — Habits: categories from `HabitCategory` enum

**Shared generics** (`core/utils/list_helpers.py`):
- `apply_entity_sort(entities, sort_by, config, default)` — config-driven sort
- `apply_entity_filter(entities, filter_value, config)` — config-driven filter
- `SortConfig`, `FilterConfig` — type aliases for declarative config dicts

**Route file convention** (all 6 `*_ui.py` files, module-level not inside factory):
- **Filters:** All 6 domains use `ActivityFilters` hierarchy from `form_helpers.py`. Goals, Habits, Events, Choices use base `ActivityFilters` + `parse_activity_filters()`. Tasks use `TaskFilters(ActivityFilters)` + `parse_task_filters()`. Principles use `PrincipleFilters(ActivityFilters)` + `parse_principle_filters()`.
- `parse_{domain}_filters(request) -> TaskFilters | PrincipleFilters | ActivityFilters` — extracts query params with domain-specific defaults
- `parse_{domain}_create_request(form_data) -> {Domain}CreateRequest` — pure form→request parsing (no service calls)
- `parse_{domain}_update_payload(form) -> dict[str, Any]` — pure form→update dict parsing
- Static option lists as module-level constants (e.g., Choices: `CHOICE_TYPES`, `DOMAINS`)
- Categories: Principles, Goals, Habits get categories from `ctx["metadata"]["categories"]` (computed by service from enums); standalone create forms use `_get_{domain}_categories()` helper importing enum directly
- All string extraction uses `safe_form_string()` from `adapters.inbound.form_helpers` (not raw `.get().strip()`)
- All enum parsing uses `parse_enum_safe()` from `form_helpers` — prevents 500s from crafted form values
- Date/time parsing uses `parse_date_safe()`, `parse_time_safe()`, `parse_datetime_safe()` from `form_helpers`

**Route handlers stay thin:** authenticate → parse → call service → handle error → render. All form parsing and enum conversion lives in the pure helpers above, not inline in route handlers.

**Domain-specific analytics** live on the service facade, not in route closures. Example: `PrinciplesService.get_analytics_summary(user_uid)` → `Result[dict]` (total, core_count, adherence, reflections).

**Tests:** `tests/unit/services/activity/test_activity_query_helpers.py` — 49 tests covering remaining Python-side helpers (sort, task secondary filters, principle filters).

---

## Pattern: Enrichment Link Population (DERIVED FROM EDGE fields)

**Problem**: Some scoring fields on frozen domain models aren't persisted — they exist as graph edges. Scorers need the UID in-memory without making N+1 per-entity edge queries.

**Solution**: Module-level enrich helpers batch-look up the edges and return new frozen instances via `dataclasses.replace()`. Called only by the paths that need the derived value; never called on every `get()`/`list()`.

**How it works (all three are identical in shape):**

```python
# core/services/habits/_goal_links.py
async def enrich_habits_with_goal_links(
    backend: HabitsOperations,
    habits: list[Habit],
    active_goal_uids: list[str] | None = None,
) -> list[Habit]:
    """Return habits with derived ``supports_goal_uid`` populated from the
    (Habit)-[:SUPPORTS_GOAL]->(Goal) edge. Graph is the source of truth;
    field is never written back.
    """
    links = await backend.get_goal_links_for_habits([h.uid for h in habits])
    if links.is_error or not links.value:
        return habits  # fail-soft: return unchanged if edge lookup fails or is empty
    link_map = links.value   # dict[habit_uid, goal_uid]
    return [
        replace(habit, supports_goal_uid=link_map[habit.uid]) if habit.uid in link_map else habit
        for habit in habits
    ]
```

**The four enrichment helpers:**

| Helper | File | Field populated | Edge |
|--------|------|----------------|------|
| `enrich_habits_with_goal_links(backend, habits, active_goal_uids?)` | `habits/_goal_links.py` | `Habit.supports_goal_uid` | `(Habit)-[:SUPPORTS_GOAL]->(Goal)` |
| `enrich_events_with_habit_links(backend, events)` | `events/_habit_links.py` | `Event.reinforces_habit_uid` | `(Event)-[:REINFORCES_HABIT]->(Habit)` |
| `enrich_events_with_goal_links(backend, events, ...)` | `events/_goal_links.py` | `Event.contributes_to_goal_uid` | `(Event)-[:CONTRIBUTES_TO_GOAL]->(Goal)` |
| inline in `tasks_search_service.py` | `get_habit_links_for_tasks` | `Task.reinforces_habit_uid` | `(Task)-[:REINFORCES_HABIT]->(Habit)` |

**Rules:**
- Fail-soft by convention — `SKUEL005` suppressed with explanation. A missing edge is common (not all habits support a goal); scoring should degrade gracefully, not error.
- Call before the scoring/prioritization step, not at the top of `get_filtered_context()` or every list fetch.
- Never write the derived field back — it vanishes at the end of the request. The edge IS the persistent state.
- Adding a new enrichment link: add the helper module, call it in the scoring path, mark the field `# DERIVED FROM EDGE` on the model, keep it absent from the DTO.

**See:** `/docs/architecture/CROSS_DOMAIN_UID_PATTERNS.md` — taxonomy of which fields are structural anchors vs enrichment links.

---

## Pattern: Curriculum-Spawned Activity (`engagement_state` + `source_path_step_uid`)

**Problem**: Activities can be created in two fundamentally different contexts: standalone (user creates a task manually) and curriculum-engaged (a student engages a PathStep and the spawn layer creates personalized instances). Both look like the same domain model. The consuming code needs to know which is which.

**The two creation paths:**

**1. PathStep engagement (spawn path)** — `_SpawnOrchestrator` reads the PathStep's `TemplateBundle` and creates one Activity per template:

```
PathStep.engage(student_uid)
    → _SpawnOrchestrator._build(spec, template, student_uid, ps_uid)
        → Activity(
              engagement_state=EngagementState.ENGAGED,
              source_path_step_uid=ps_uid,
              ...all authoring fields from template...
          )
        → backend.create_with_spawned_from(instance, template_uid)
              # atomic: writes node + (instance)-[:SPAWNED_FROM]->(template) edge
```

- `engagement_state = EngagementState.ENGAGED` marks the instance as freshly spawned.
- `source_path_step_uid` = the PathStep UID — persisted property (primary read path).
- `(instance)-[:SPAWNED_FROM]->(ActivityTemplate)` edge — graph back-reference (traverse only when you need the template itself).
- Student can promote to `EngagementState.OWNED` (they've personalised it enough to break the template relationship).

**2. Standalone creation** — `service.create_task(request, user_uid)`:

```python
Activity(
    engagement_state=None,       # None = standalone
    source_path_step_uid=None,   # No PS origin
    ...
)
# No SPAWNED_FROM edge created.
```

Some teacher/admin flows set `source_path_step_uid` directly without going through the spawn layer — no `SPAWNED_FROM` edge exists in those cases, which is why the property, not the 2-hop edge, is the universal check.

**Checking curriculum origin in service code:**

```python
# Check on the frozen model (works for both creation paths)
task.is_from_path_step          # bool — source_path_step_uid is not None
task.source_path_step_uid       # str | None — the PS uid
task.engagement_state           # EngagementState.ENGAGED | EngagementState.OWNED | None

# Check at query time (curriculum-spawned only, excludes direct-set)
# (Task)-[:SPAWNED_FROM]->(TaskTemplate)<-[:HAS_TASK_TEMPLATE]-(PathStep)
# Use this only when you need the template; for existence, use the field.
```

**Spawn layer dependency order** (important when adding a 7th domain):

```
Layer 1: Choice, Habit, Principle   # nothing depends on these within a spawn
Layer 2: Goal                        # may reference Choice (INSPIRED_BY_CHOICE edge)
Layer 3: Event                       # may reference Habit, Goal
Layer 4: Task                        # may reference Goal, Habit, Event
```

`DomainSpawnSpec.layer` in `SPAWN_REGISTRY` drives ordering. A new domain that references layer-N entities must be layer N+1 or higher.

**See:** [TEMPLATES.md](TEMPLATES.md) — template entity structure, TemplateBundle, DomainSpawnSpec registry, and template lifecycle (the template side of this pattern). `ADR-061-spawn-layer-consolidation.md`, `core/services/ps_engagement/_spawn_orchestrator.py`, `/docs/architecture/CROSS_DOMAIN_UID_PATTERNS.md § source_path_step_uid in depth`.

---

**See Also**: [SKILL.md](SKILL.md) for domain overview, [FACADE_PATTERN.md](FACADE_PATTERN.md) for facade architecture
