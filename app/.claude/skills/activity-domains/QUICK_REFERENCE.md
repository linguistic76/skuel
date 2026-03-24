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
| Domain | Routes | Views | Events File |
|--------|--------|-------|-------------|
| Tasks | `adapters/inbound/tasks_ui.py` | `ui/tasks/views.py` | `core/events/task_events.py` |
| Goals | `adapters/inbound/goals_ui.py` | `ui/goals/views.py` | `core/events/goal_events.py` |
| Habits | `adapters/inbound/habits_ui.py` | `ui/habits/views.py` | `core/events/habit_events.py` |
| Events | `adapters/inbound/events_ui.py` | `ui/events/views.py` | `core/events/calendar_event_events.py` |
| Choices | `adapters/inbound/choices_ui.py` | `ui/choices/views.py` | `core/events/choice_events.py` |
| Principles | `adapters/inbound/principles_ui.py` | `ui/principles/views.py` | `core/events/principle_events.py` |

## Domain-Specific Quirks

### Tasks
- Has `parent_uid` for subtasks hierarchy
- `DEPENDS_ON` relationship for task dependencies
- `scheduled_date` vs `due_date` distinction

### Goals
- Has `GoalTimeframe` enum (DAILY → MULTI_YEAR)
- Supports milestones via `HAS_MILESTONE` relationship
- Progress is 0.0-1.0 float

### Habits
- Tracks full habit loop: `cue`, `craving`, `response`, `reward`
- `HabitCompletion` entities for daily tracking
- `current_streak` and `best_streak` fields

### Events
- Event file is `calendar_event_events.py` (not `event_events.py`)
- Has `EventType` enum for categorization
- Supports `CONFLICTS_WITH` relationship

### Choices
- **Requires 2+ options** at creation (Alpine.js validation)
- `options` is `list[ChoiceOptionDTO]` with scores
- Has `make_decision()` method to select option

### Principles
- Has `PrincipleReflection` sub-entity for tracking
- Uses `is_active: bool` instead of `status` enum
- `PrincipleCategory` enum for categorization

## Status Enums

| Domain | Status Enum | Values |
|--------|-------------|--------|
| Tasks | `ActivityStatus` | DRAFT, ACTIVE, PAUSED, COMPLETED, ARCHIVED |
| Goals | `GoalStatus` | NOT_STARTED, IN_PROGRESS, COMPLETED, ABANDONED, ON_HOLD |
| Habits | `is_active: bool` | True/False |
| Events | `ActivityStatus` | SCHEDULED, COMPLETED, CANCELLED |
| Choices | `ChoiceStatus` | PENDING, DECIDED, IMPLEMENTED, EVALUATED |
| Principles | `is_active: bool` | True/False |

## Common Imports

```python
# Models
from core.models.task.task import Task
from core.models.task.task_dto import TaskDTO
from core.models.task.task_request import TaskCreateRequest

# Shared enums
from core.models.enums import Priority, Domain, ActivityStatus

# Results
from core.utils.result_simplified import Result

# Relationship service
from core.services.relationships import UnifiedRelationshipService
```

## Filtered List Query Method

All 11 facades (6 Activity + 5 Curriculum) expose `get_filtered_context()` → `Result[ListContext]`, satisfying the `FilteredContextProvider` protocol. Uses shared `build_filtered_context()` skeleton. Stats always include `total` + `active` (BaseStats contract).

```python
ctx = (await habits_service.get_filtered_context(user_uid)).value
habits, stats = ctx["entities"], ctx["stats"]
# stats["total"], stats["active"] — guaranteed on ALL domains
# Tasks metadata: ctx["metadata"]["projects"], ctx["metadata"]["assignees"]
# Principles/Goals/Habits metadata: ctx["metadata"]["categories"] — from enums
```

| Service | Default sort | Default filter |
|---------|-------------|----------------|
| Habits | `streak` | `active` |
| Tasks | `due_date` | `active` |
| Goals | `target_date` | `active` |
| Events | `start_time` | `scheduled` |
| Choices | `deadline` | `pending` |
| Principles | `strength` | `all` |
| Lesson/Ku/LS/LP/Exercise | `title` | `all` |

Module-level helpers (each facade file): `_compute_{domain}_stats`, `_apply_{domain}_status_filter`, `_apply_{domain}_sort` (all 11), plus `_apply_task_secondary_filters` (Tasks), `_apply_principle_filters` (Principles), `_compute_task_metadata` (Tasks), `_compute_principle_metadata` (Principles), `_compute_goal_metadata` (Goals), `_compute_habit_metadata` (Habits)

**Key files:** `core/services/filtered_context.py` (skeleton), `core/ports/filtered_context_protocols.py` (protocol), `core/ports/query_types.py` (ListContext + BaseStats), `core/utils/list_context_helpers.py` (typed accessors)

**See:** `PATTERNS.md` → "Filtered List Queries" section

---

## Bootstrap Location

All services wired in: `services_bootstrap/`

```python
# compose_services() in services_bootstrap/compose.py calls
# _create_activity_services() in services_bootstrap/_activity_services.py:
activity_services = _create_activity_services(
    tasks_backend=tasks_backend, events_backend=events_backend,
    habits_backend=habits_backend, goals_backend=goals_backend,
    choices_backend=choices_backend, principles_backend=principles_backend,
    # ... shared deps: graph_intelligence, event_bus, insight_store
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
