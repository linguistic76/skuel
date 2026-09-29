# Activity Domains - Implementation Patterns

> Implementation patterns shared across the 6 Activity Domains.

---

## Pattern: Activity Domain Route File

**Problem**: Every Activity Domain needs CRUD, Query, and Intelligence routes registered identically. Writing this manually produces ~80 lines of near-identical boilerplate per domain.

**Solution**: Use `create_activity_domain_route_config` — pre-populates all three factory configs from a single call.

```python
"""
Tasks Routes - Configuration-Driven Registration
==================================================

Factory that wires tasks API and UI routes using DomainRouteConfig.
"""

from typing import TYPE_CHECKING

from adapters.inbound.fasthtml_types import FastHTMLApp, RouteDecorator
from adapters.inbound.route_factories import (
    create_activity_domain_route_config,
    register_domain_routes,
)
from adapters.inbound.tasks_api import create_tasks_api_routes
from adapters.inbound.tasks_ui import create_tasks_ui_routes
from core.models.task.task_request import TaskCreateRequest, TaskUpdateRequest

if TYPE_CHECKING:
    from services_bootstrap import Services


TASKS_CONFIG = create_activity_domain_route_config(
    domain_name="tasks",
    primary_service_attr="tasks",
    api_factory=create_tasks_api_routes,
    ui_factory=create_tasks_ui_routes,
    create_schema=TaskCreateRequest,
    update_schema=TaskUpdateRequest,
    uid_prefix="task",
    request_create_method="create_task",  # required: the request-door create primitive
    supports_goal_filter=True,
    supports_habit_filter=True,
    api_related_services={
        "goals_service": "goals",
        "habits_service": "habits",
    },
    ui_related_services={
        "connection_fetch_backend": "connection_fetch_backend",
        "user_service": "user",
        "goals_service": "goals",
        "habits_service": "habits",
    },
    prometheus_metrics_attr="prometheus_metrics",
)


def create_tasks_routes(app: FastHTMLApp, rt: RouteDecorator, services: Services | None) -> None:
    """Wire tasks API and UI routes using configuration-driven registration."""
    register_domain_routes(app, rt, services, TASKS_CONFIG)


__all__ = ["create_tasks_routes"]
```

**What `create_activity_domain_route_config` registers automatically** (scope `USER_OWNED`):
- `CRUDRouteFactory` — `/api/{domain}/create`, `/get`, `/update`, `/delete`, `/list`
- `CommonQueryRouteFactory` — `/api/{domain}/user`, `/by-status`, plus `/goal` and `/habit` when
  the `supports_*_filter` flags are set
- `IntelligenceRouteFactory` — `/api/{domain}/analytics`, `/context`, `/insights`

**What the domain's `api_factory` (`tasks_api.py`) adds:**
- `create_activity_field_api_routes` — `POST /api/{domain}/{uid}/status` and `/priority` (card swaps)
- `create_activity_hierarchy_api_routes` — children / parent / hierarchy / add-child / remove-child
- `create_activity_link_api_routes` — the cross-domain link POSTs
- Manual domain-specific routes (e.g. `GET /api/tasks/knowledge-priorities`)

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

# 2. Add a typed delegation method to the TasksService facade:
async def create_task_with_context(
    self, task_data: TaskCreateRequest, user_context: UserContext
) -> Result[Task]:
    return await self.scheduling.create_task_with_context(task_data, user_context)

# 3. Callers use the facade:
result = await tasks_service.create_task_with_context(request, user_context)
```

---

## Pattern: Filtered List Queries (`get_filtered_context`)

**Problem**: Intelligence services need a per-domain view (fetch → stats → filter → sort) without knowing each domain's internals.

**Solution**: Nine facades (the 6 Activity facades plus `PsService`, `LpService`, `ExerciseService`) expose `get_filtered_context()` returning `Result[ListContext]`, satisfying the `FilteredContextProvider` protocol. `KuService` has none. A shared skeleton (`build_filtered_context()`) enforces the pattern; domains provide callables for their stats, filters, and sort logic.

**One consumer**: `DailyPlanningMixin._query_domain_stats()` (`core/services/user/intelligence/daily_planning.py`), which calls it with `status_filter="all"` for the 6 Activity domains and feeds `_generate_domain_health_warnings()` (aggregate health + cross-domain balance). It returns `None` on a failed read, which its caller treats as "stats unavailable", not zero. The providers reach it as the `filtered_providers` dict built in `services_bootstrap/_intelligence_hub.py` — ⚠ that dict also registers `"ku"` → the Ku facade, which has no `get_filtered_context`; nothing reads that key today, so never iterate the dict. UserContext is the broad snapshot (the MEGA-QUERY); `get_filtered_context()` is the per-domain zoom lens.

**The Activity list pages do not use it.** `activity_ui_factory.py` fetches with the config's `get_all` (e.g. `goals_service.get_user_goals`) and filters with its `filter_fn` (`core/utils/entity_filters.py`: `filter_tasks` … `filter_principles`) — see [Route file convention](#route-file-convention) below.

```python
from core.ports.filtered_context_protocols import FilteredContextProvider
from core.ports.query_types import ListContext  # TypedDict: entities, stats, metadata?

# Intelligence service (domain-agnostic via the protocol):
provider: FilteredContextProvider = self.filtered_providers["habits"]
result = await provider.get_filtered_context(user_uid=user_uid, status_filter="all")
if result.is_error:
    return Result.fail(result)
stats = result.value["stats"]
```

**Method signatures (Activity Domains — 6):**

| Service | Signature |
|---------|-----------|
| `HabitsService` | `get_filtered_context(user_uid, status_filter="active", sort_by="streak")` |
| `TasksService` | `get_filtered_context(user_uid, project=None, assignee=None, due_filter=None, status_filter="active", sort_by="due_date")` |
| `GoalsService` | `get_filtered_context(user_uid, status_filter="active", sort_by="target_date")` |
| `EventsService` | `get_filtered_context(user_uid, status_filter="scheduled", sort_by="start_time")` |
| `ChoicesService` | `get_filtered_context(user_uid, status_filter="pending", sort_by="deadline")` |
| `PrinciplesService` | `get_filtered_context(user_uid, category_filter="all", strength_filter="all", sort_by="strength", status_filter="all")` |

⚠ **Choices' filter and stats vocabulary is not Choice's status vocabulary.** `_CHOICE_FILTER_CONFIG` tests `status == "pending" / "decided" / "implemented"` and `compute_choice_stats` counts `pending` / `decided` the same way. A Choice's legal statuses are `draft`, `active`, `completed` and `archived`, so those filters match nothing and those counts read 0. The list page is unaffected: `filter_choices` decides by `decided_at`.

**Method signatures (Curriculum — 3):**

| Service | Signature |
|---------|-----------|
| `PsService` | `get_filtered_context(user_uid, status_filter="all", sort_by="title")` |
| `LpService` | `get_filtered_context(user_uid, status_filter="all", sort_by="title")` |
| `ExerciseService` | `get_filtered_context(user_uid, status_filter="all", sort_by="title")` |

**Shared skeleton** (`core/services/filtered_context.py`):

Each facade calls `build_filtered_context()` with domain-specific callables:
1. `fetch_all` — async callable returning all entities (one query)
2. `compute_stats` — stats from the full set (pre-filter)
3. `apply_filters` — domain-specific status/secondary filters (captures params via closure)
4. `apply_sort` — domain-specific sort, with `sort_by`
5. `compute_metadata` — optional domain-specific extras (Tasks: project/assignee lists)

**`FilteredContextProvider` protocol** (`core/ports/filtered_context_protocols.py`):

Common params: `user_uid`, `status_filter`, `sort_by`. Concrete facades add domain-specific params with defaults, satisfying structural subtyping.

**`ListContext` TypedDict** (`core/ports/query_types.py`): `entities` (filtered list), `stats` (`dict[str, int | float]` — guaranteed `total` + `active` keys per `BaseStats` contract), `metadata` (`dict[str, Any]`, optional).

**`BaseStats` contract** (`core/ports/query_types.py`): Every `_compute_*_stats()` function returns at least `total: int` and `active: int`. Domain-specific keys (`overdue`, `streaks`, `pending`, `core`, etc.) are additional. Intelligence consumers can rely on `active` for generic health checks without knowing domain-specific keys.

**Consuming a `ListContext`:** `ctx["entities"]` and `ctx["stats"]` are always present; `metadata` is optional (the TypedDict is `total=False` and `build_filtered_context()` only sets it when a `compute_metadata` callable is passed), so read it as `ctx.get("metadata", {})`. `entities` is typed `list[Any]`, so annotate at the call site to narrow: `tasks: list[Task] = ctx["entities"]`.

**Module-level helpers** (Python-side):
- `compute_{domain}_stats(entities)` — the 6 Activity Domain stat functions live in `core/utils/activity_stats.py`, each returning a frozen dataclass (e.g. `TaskStats`, `GoalStats`). Facade-level `_compute_{domain}_stats()` wrappers project these into `dict[str, int | float]` for the `ListContext` contract. PS, LP and Exercise keep their stats function in their facade file.
- `_{DOMAIN}_FILTER_CONFIG: FilterConfig` — declarative status-filter predicates used in `get_filtered_context()`: Tasks, Goals, Habits, Events, Choices and PS. Principles uses the multi-dimensional `_apply_principle_filters` instead; LP and Exercise have none. Distinct from the UI-layer `FILTER_CONFIGS` dict in `ui/activities/filter_bar.py`, which drives filter-bar rendering.
- `_{DOMAIN}_SORT_CONFIG: SortConfig` — declarative sort key dict (all 9 providers)
- `_apply_{domain}_sort(entities, sort_by)` — thin wrapper calling `apply_entity_sort()` with the domain's `SortConfig`
- `_apply_task_secondary_filters(tasks, project, assignee, due_filter)` — Tasks only
- `_apply_principle_filters(principles, category_filter, strength_filter, status_filter)` — Principles only
- `_compute_task_metadata(all_tasks)` — Tasks: project/assignee lists
- `_compute_principle_metadata(_all)` — Principles: categories from `PrincipleCategory` enum
- `_compute_goal_metadata(_all)` — Goals: categories from `_GOAL_CATEGORIES` constant
- `_compute_habit_metadata(_all)` — Habits: categories from `HabitCategory` enum

**Shared generics** (`core/utils/list_helpers.py`):
- `apply_entity_sort(entities, sort_by, config, default)` — config-driven sort
- `apply_entity_filter(entities, filter_value, config)` — config-driven filter
- `SortConfig`, `FilterConfig` — type aliases for declarative config dicts

**Tests:** `tests/unit/services/activity/test_activity_query_helpers.py` covers the Python-side helpers (sort, task secondary filters, principle filters).

### Route file convention

The six `adapters/inbound/{domain}_ui.py` files:
- **List + detail:** build an `ActivityUIConfig` and call `create_activity_ui_routes(app, rt, config)`. The factory reads the query string by `filter_params` (ordered `(name, default)` pairs), fetches with `get_all(user_uid)`, filters with `filter_fn(items, *param_values)` from `core/utils/entity_filters.py`, and renders the filter bar from `FILTER_CONFIGS[domain]` (`ui/activities/filter_bar.py`). `list_categories` (Goals, Habits, Principles) merges the user's own categories into the filter bar.
- **Create/edit forms:** `POST /{domain}/create` and `POST /{domain}/edit?uid=` parse with `parse_form_body(request, {Domain}CreateRequest | {Domain}UpdateRequest)` (`adapters/inbound/form_helpers.py`), so Pydantic validates the form. A validation failure re-renders the form with `render_error_banner(err.display_message)`. The edit handler checks ownership with `verify_ownership` first, then writes `parsed.value.to_intent()` through the facade's `update_{domain}`.
- **Forms** live in `ui/activities/{domain}_form.py` (`render_activity_form`).

**Route handlers stay thin:** authenticate → parse (`parse_form_body`) → call service → handle error → render.

**Domain-specific analytics** live on the service facade, not in route closures. Example: `PrinciplesService.get_analytics_summary(user_uid)` → `Result[dict]` (total, core_count, adherence, reflections).

---

## Pattern: Enrichment Link Population (DERIVED FROM EDGE fields)

**Problem**: Some scoring fields on frozen domain models aren't persisted — they exist as graph edges. Scorers need the UID in-memory without making N+1 per-entity edge queries.

**Solution**: Module-level enrich helpers batch-look up the edges and return new frozen instances via `dataclasses.replace()`. Called only by the paths that need the derived value; never called on every `get()`/`list()`.

**How it works (the goal-link helpers pick one goal when an entity supports several):**

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
    if not habits:
        return habits
    links = await backend.get_goal_links_for_habits([h.uid for h in habits])
    if links.is_error or not links.value:
        return habits  # fail-soft: return unchanged if edge lookup fails or is empty
    link_map: dict[str, list[str]] = links.value  # habit_uid -> goal_uids
    return [
        replace(habit, supports_goal_uid=pick_goal(link_map[habit.uid], active_goal_uids))
        if habit.uid in link_map
        else habit
        for habit in habits
    ]
```

**The four enrichment helpers:**

| Helper | File | Field populated | Edge |
|--------|------|----------------|------|
| `enrich_habits_with_goal_links(backend, habits, active_goal_uids?)` | `habits/_goal_links.py` | `Habit.supports_goal_uid` | `(Habit)-[:SUPPORTS_GOAL]->(Goal)` |
| `enrich_events_with_habit_links(backend, events)` (one habit per event, no pick) | `events/_habit_links.py` | `Event.reinforces_habit_uid` | `(Event)-[:REINFORCES_HABIT]->(Habit)` |
| `enrich_events_with_goal_links(backend, events, active_goal_uids?)` | `events/_goal_links.py` | `Event.contributes_to_goal_uid` | `(Event)-[:CONTRIBUTES_TO_GOAL]->(Goal)` |
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
PsEngagementService.engage_pathstep(student_uid, ps_uid)
    → _SpawnOrchestrator.spawn(student_uid, ps_uid, bundle, engagement_uid, anchor)
    → _build(spec, template, student_uid, ps_uid, anchor, template_to_instance)
        → Activity(
              engagement_state=EngagementState.ENGAGED,
              source_path_step_uid=ps_uid,
              ...all authoring fields from template...
          )
        → backend.create_with_spawned_from(instance, template_uid, engagement_uid)
              # atomic: writes node + (instance)-[:SPAWNED_FROM {engagement_uid}]->(template) edge
```

- `engagement_state = EngagementState.ENGAGED` marks the instance as freshly spawned.
- `source_path_step_uid` = the PathStep UID — persisted property (primary read path).
- `(instance)-[:SPAWNED_FROM {engagement_uid}]->(ActivityTemplate)` edge — graph back-reference to the template, stamped with the uid of the `ENGAGED_WITH` edge that spawned it. Complete and abandon reach an engagement's instances by that stamp, never by template.
- Kept at the completion review → `EngagementState.OWNED`: the instance outlives the engagement, and a later engagement of the same step cannot reach it.

**2. Standalone creation** — `service.create_task(request, user_uid)`:

```python
Activity(
    engagement_state=None,       # None = standalone
    source_path_step_uid=None,   # No PS origin
    ...
)
# No SPAWNED_FROM edge created.
```

The path-step scheduling doors (`TasksService.create_task_from_path_step` → `TasksSchedulingService`, and `HabitsSchedulingService`) set `source_path_step_uid` directly without the spawn layer — no `SPAWNED_FROM` edge exists in those cases, which is why the property, not the 2-hop edge, is the universal check.

**Checking curriculum origin in service code:**

```python
# Check on the frozen model (works for both creation paths)
task.source_path_step_uid       # str | None — the PS uid (all 6 models)
task.is_from_path_step          # bool shorthand — Task, Habit and Event only
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
