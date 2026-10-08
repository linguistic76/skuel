# Activity Domains Quick Reference

> Fast lookup for file locations and domain-specific details.

## File Locations

### Models
| Domain | Model | DTO | Request |
|--------|-------|-----|---------|
| Tasks | `core/models/task/task.py` | `task_dto.py` | `task_request.py` |
| Goals | `core/models/goal/goal.py` | `goal_dto.py` | `goal_request.py` |
| Habits | `core/models/habit/habit.py` | `habit_dto.py` | `habit_request.py` |
| Events | `core/models/event/event.py` | `event_dto.py` | `event_request.py` |
| Choices | `core/models/choice/choice.py` | `choice_dto.py` | `choice_request.py` |
| Principles | `core/models/principle/principle.py` | `principle_dto.py` | `principle_request.py` |

### Services
| Domain | Facade | Core | Search | Intelligence |
|--------|--------|------|--------|--------------|
| Tasks | `tasks_service.py` | `tasks/tasks_core_service.py` | `tasks_search_service.py` | `tasks_intelligence_service.py` |
| Goals | `goals_service.py` | `goals/goals_core_service.py` | `goals_search_service.py` | `goals_intelligence_service.py` |
| Habits | `habits_service.py` | `habits/habits_core_service.py` | `habits_search_service.py` | `habits_intelligence_service.py` |
| Events | `events_service.py` | `events/events_core_service.py` | `events_search_service.py` | `events_intelligence_service.py` |
| Choices | `choices_service.py` | `choices/choices_core_service.py` | `choices_search_service.py` | `choices_intelligence_service.py` |
| Principles | `principles_service.py` | `principles/principles_core_service.py` | `principles_search_service.py` | `principles_intelligence_service.py` |

### UI

All 6 Activity Domains support authoring through per-domain create/edit forms (`/{domain}/create`,
`/{domain}/edit?uid=...`). All 6 are pages of the Tasks+ section — one sidebar
(`ui/activities/nav.py`: Today, Weekly, Monthly, the six domain rows, Journal, GradeBook) on every
domain page, the calendar month/week views and `/today`, with the Tasks+ door (→ `/today`) lit in the
chrome. There is no hub page; `/today` is the landing.

| Domain | Routes | Form | Views | Events File |
|--------|--------|------|-------|-------------|
| Tasks | `adapters/inbound/tasks_ui.py` | `ui/activities/tasks_form.py` | `ui/activities/tasks_views.py` | `core/events/task_events.py` |
| Goals | `adapters/inbound/goals_ui.py` | `ui/activities/goals_form.py` | `ui/activities/goals_views.py` | `core/events/goal_events.py` |
| Habits | `adapters/inbound/habits_ui.py` | `ui/activities/habits_form.py` | `ui/activities/habits_views.py` | `core/events/habit_events.py` |
| Events | `adapters/inbound/events_ui.py` | `ui/activities/events_form.py` | `ui/activities/events_views.py` | `core/events/calendar_event_events.py` |
| Choices | `adapters/inbound/choices_ui.py` | `ui/activities/choices_form.py` | `ui/activities/choices_views.py` | `core/events/choice_events.py` |
| Principles | `adapters/inbound/principles_ui.py` | `ui/activities/principles_form.py` | `ui/activities/principles_views.py` | `core/events/principle_events.py` |

**Shared UI utilities:** `ui/activities/_shared.py` — `MetadataField()` (label + value pairs for detail grids), `safe_id()`, `CONNECTION_ICONS`, `ConnectionsSection()` (detail page links, one list per heading), `ConnectionRows()` (list card links, one line per heading), `PriorityBadgeDropdown()`, `ActivityList()`. `PRIORITY_ORDER` is in `core/utils/entity_filters.py`.

## Domain-Specific Quirks

### Tasks
- `parent_uid` is an edge carrier, not a node property: create writes `(parent)-[:HAS_SUBTASK]->(task)` from it
- `DEPENDS_ON` relationship for task dependencies
- `scheduled_date` vs `due_date` distinction; a task created with neither is due the day it is created (`Task.with_creation_due_date()`), and an update may not clear the last of the two
- A task contributes to any number of goals through `(Task)-[:CONTRIBUTES_TO_GOAL]->(Goal)` edges (the edge events use too); no node property holds them — create takes `contributes_to_goal_uids`, update replaces the set
- A task's principles are `(Task)-[:ALIGNED_WITH_PRINCIPLE]->(Principle)` edges, never a node property — create takes `aligned_principle_uids`, update replaces the set (`[]` clears it)

### Goals
- Has `GoalTimeframe` enum (DAILY → MULTI_YEAR)
- Milestones stored as embedded `tuple[Milestone, ...]` on the Goal (not graph nodes)
- `progress_percentage` (0-100) is the one stored progress field; `calculate_progress()` returns it as 0.0-1.0
- `GoalAchieved` fires on the transition into completed, decided by the guarded write

### Habits
- Tracks full habit loop: `cue`, `craving`, `response`, `reward`
- `HabitCompletion` entities for daily tracking — user-owned (`user_uid` + `:OWNS`)
- `current_streak` and `best_streak` fields
- Due/overdue come from backwards-looking frequency windows, not a due-date column

### Events
- Event file is `calendar_event_events.py` (not `event_events.py`)
- `event_type: str | None` holds a canonical `EventType` value
- Supports `CONFLICTS_WITH` relationship

### Choices
- `options: tuple[ChoiceOption, ...]` on the model (`list[ChoiceOptionRequest]` on the request, default empty — no minimum count); the create form omits them
- `ChoicesService.make_decision()` (via `_OptionManagementMixin`) records the selected option

### Principles
- Reflection is event-driven: `POST /api/principles/reflection` → `record_principle_reflection()` publishes `PrincipleReflectionRecorded` (no graph node)
- Has an `is_active: bool` field alongside its `status`
- `PrincipleCategory` enum for categorization

## Status Enums

All six domains use `EntityStatus` (`core/models/enums/entity_enums.py`). The legal set is
`EntityType.<T>.valid_statuses()` and a new entity's status is `EntityType.<T>.default_status()` —
the enum is the authority; this table is a snapshot of it.

| Domain | Default | Legal `EntityStatus` values |
|--------|---------|-----------------------------|
| Tasks | DRAFT | DRAFT, SCHEDULED, ACTIVE, PAUSED, BLOCKED, COMPLETED, FAILED, CANCELLED, POSTPONED |
| Goals | DRAFT | DRAFT, ACTIVE, PAUSED, COMPLETED, FAILED, CANCELLED, ARCHIVED |
| Habits | ACTIVE | ACTIVE, PAUSED, COMPLETED, CANCELLED, ARCHIVED (`is_active` is the property `status == ACTIVE`) |
| Events | SCHEDULED | SCHEDULED, ACTIVE, COMPLETED, CANCELLED |
| Choices | DRAFT | DRAFT, ACTIVE, COMPLETED, ARCHIVED |
| Principles | ACTIVE | ACTIVE, PAUSED, ARCHIVED (plus a separate `is_active: bool` field) |

## Common Imports

```python
# Models
from core.models.task.task import Task
from core.models.task.task_dto import TaskDTO
from core.models.task.task_request import TaskCreateRequest

# Shared enums
from core.models.enums import Priority, Domain, EntityStatus

# Results
from core.utils.result_simplified import Result

# Relationship service
from core.services.relationships import UnifiedRelationshipService
```

## Filtered List Query Method

Nine facades (the 6 Activity facades + PS, LP, Exercise; not Ku) expose `get_filtered_context()` → `Result[ListContext]`, satisfying the `FilteredContextProvider` protocol. Uses shared `build_filtered_context()` skeleton. Stats always include `total` + `active` (BaseStats contract). Its one caller is daily planning's domain-health warnings; the Activity list pages use the UI factory's `get_all` + `filter_fn` instead.

```python
result = await habits_service.get_filtered_context(user_uid)
if result.is_error:
    return Result.fail(result)
habits, stats = result.value["entities"], result.value["stats"]
# stats["total"], stats["active"] — guaranteed on ALL domains
# Tasks metadata: ["metadata"]["projects"], ["metadata"]["assignees"]
# Principles/Goals/Habits metadata: ["metadata"]["categories"]
```

| Service | Default sort | Default filter |
|---------|-------------|----------------|
| Habits | `streak` | `active` |
| Tasks | `due_date` | `active` |
| Goals | `target_date` | `active` |
| Events | `start_time` | `scheduled` |
| Choices | `deadline` | `pending` (matches no Choice status — see PATTERNS.md) |
| Principles | `strength` | `all` |
| PS/LP/Exercise | `title` | `all` |

Module-level helpers: **Activity domain stats** (`compute_{domain}_stats` for 6 Activity Domains) live in `core/utils/activity_stats.py`, returning frozen dataclasses; facade wrappers project to dicts. Sort/filter configs stay in facade files: `_{DOMAIN}_SORT_CONFIG` + `_apply_{domain}_sort` (all 9, config-driven via `apply_entity_sort`), `_{DOMAIN}_FILTER_CONFIG` (Tasks, Goals, Habits, Events, Choices, PS; config-driven via `apply_entity_filter`), plus `_apply_task_secondary_filters` (Tasks), `_apply_principle_filters` (Principles multi-dimensional), `_compute_*_metadata` (Tasks/Principles/Goals/Habits). Generics in `core/utils/list_helpers.py`. **Cross-domain reads** go through `CrossDomainQueryService` (`core/services/cross_domain/`) — 9 methods, one backend query per call, returns frozen typed dataclasses. **UI-layer:** `ActivityList(items, domain, card_fn, connections_map)` in `ui/activities/_shared.py` — generic list renderer used by all 6 `{Domain}List` functions. `FILTER_CONFIGS: dict[str, FilterBarConfig]` in `ui/activities/filter_bar.py` — centralised filter bar configs for all 6 Activity Domains.

**Key files:** `core/services/filtered_context.py` (skeleton), `core/ports/filtered_context_protocols.py` (protocol), `core/ports/query_types.py` (ListContext + BaseStats)

**See:** `PATTERNS.md` → "Filtered List Queries" section

---

## Bootstrap Location

All services wired in: `services_bootstrap/`

```python
# compose_services() in services_bootstrap/compose.py calls
# _create_activity_services() in services_bootstrap/_activity_services.py:
activity_services = _create_activity_services(
    tasks_backend=tasks_backend, events_backend=events_backend,
    habits_backend=habits_backend, habit_completions_backend=habit_completions_backend,
    goals_backend=goals_backend, choices_backend=choices_backend,
    principles_backend=principles_backend,
    # ... shared deps: graph_intelligence, cross_domain_query, event_bus, ...
)
# AI wired separately by _wire_ai_services() in services_bootstrap/_ai_wiring.py
# Event subscriptions wired by _wire_event_subscribers() in services_bootstrap/_event_wiring.py
```

## Documentation

| Domain | Doc File |
|--------|----------|
| Tasks | `/docs/domains/tasks.md` |
| Goals | `/docs/domains/goals.md` |
| Habits | `/docs/domains/habits.md` |
| Events | `/docs/domains/events.md` |
| Choices | `/docs/domains/choices.md` |
| Principles | `/docs/domains/principles.md` |
