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
| Tasks | `adapters/inbound/tasks_ui.py` | `components/tasks_views.py` | `core/events/task_events.py` |
| Goals | `adapters/inbound/goals_ui.py` | `components/goals_views.py` | `core/events/goal_events.py` |
| Habits | `adapters/inbound/habits_ui.py` | `components/habits_views.py` | `core/events/habit_events.py` |
| Events | `adapters/inbound/events_ui.py` | `components/events_views.py` | `core/events/calendar_event_events.py` |
| Choices | `adapters/inbound/choice_ui.py` | `components/choices_views.py` | `core/events/choice_events.py` |
| Principles | `adapters/inbound/principles_ui.py` | `components/principles_views.py` | `core/events/principle_events.py` |

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
from core.models.shared_enums import Priority, Domain, ActivityStatus

# Results
from core.utils.result_simplified import Result

# Relationship service
from core.services.relationships import UnifiedRelationshipService
```

## Bootstrap Location

All services wired in: `core/utils/services_bootstrap.py`

```python
async def compose_services(neo4j_adapter, event_bus=None) -> Result[Services]:
    # All 6 Activity Domain services created here
    tasks_service = TasksService(tasks_backend, graph_intel, event_bus)
    goals_service = GoalsService(goals_backend, graph_intel, event_bus)
    # ...
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
