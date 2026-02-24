---
title: Events Domain
created: 2025-12-04
updated: 2026-01-19
status: current
category: domains
tags: [events, activity-domain, domain]
---

# Events Domain

**Type:** Activity Domain (4 of 6)
**UID Prefix:** `event:`
**Entity Label:** `Event`
**Config:** `EVENTS_CONFIG` (from `core.models.relationship_registry`)

## Purpose

Events represent scheduled calendar items. They connect to knowledge application, goal contribution, and habit practice.

## Key Files

| Component | Location |
|-----------|----------|
| Model | `/core/models/event/event.py` |
| DTO | `/core/models/event/event_dto.py` |
| Request Models | `/core/models/event/event_request.py` |
| Relationships | `/core/models/event/event_relationships.py` |
| Core Service | `/core/services/events/events_core_service.py` |
| Search Service | `/core/services/events/events_search_service.py` |
| Habit Integration | `/core/services/events/events_habit_integration_service.py` |
| Learning Service | `/core/services/events/events_learning_service.py` |
| Progress Service | `/core/services/events/events_progress_service.py` |
| Scheduling Service | `/core/services/events/events_scheduling_service.py` |
| Intelligence Service | `/core/services/events/events_intelligence_service.py` |
| Facade | `/core/services/events_service.py` |
| Config | `EVENTS_CONFIG` in `/core/models/relationship_registry.py` |
| Events | `/core/events/calendar_event_events.py` |
| UI Routes | `/adapters/inbound/events_ui.py` |
| View Components | `/ui/events/views.py` |

## Facade Pattern (January 2026)

EventsService uses `FacadeDelegationMixin` with **signature preservation**:

```python
class EventsService(FacadeDelegationMixin, BaseService[EventsOperations, Event]):
    # Class-level type annotations for signature preservation
    core: EventsCoreService
    search: EventsSearchService
    habits: EventsHabitIntegrationService
    learning: EventsLearningService
    progress: EventsProgressService      # January 2026
    scheduling: EventsSchedulingService  # January 2026
    relationships: UnifiedRelationshipService
    intelligence: EventsIntelligenceService

    _delegations = merge_delegations(
        {"get_event": ("core", "get_event"), ...},
        {"get_user_items_in_range": ("core", "get_user_items_in_range"), ...},
        {"complete_event_with_cascade": ("progress", "complete_event_with_cascade"), ...},
        {"schedule_event_smart": ("scheduling", "schedule_event_smart"), ...},
    )
```

**Signature preservation**: `inspect.signature(EventsService.get_user_items_in_range)` returns the actual parameters (`user_uid`, `start_date`, `end_date`, `include_completed`) rather than generic `(*args, **kwargs)`.

## Model Fields

| Field | Type | Description |
|-------|------|-------------|
| `uid` | `str` | Unique identifier |
| `user_uid` | `str` | Owner user |
| `title` | `str` | Event title |
| `description` | `str?` | Event description |
| `event_date` | `date` | Event date |
| `start_time` | `time?` | Start time |
| `end_time` | `time?` | End time |
| `duration_minutes` | `int` | Duration in minutes |
| `location` | `str?` | Event location |
| `event_type` | `EventType` | Meeting, Practice, Learning, etc. |
| `status` | `KuStatus` | Scheduled, Completed, Cancelled |
| `priority` | `Priority` | Low, Medium, High, Urgent |
| `recurrence_pattern` | `RecurrencePattern?` | Daily, Weekly, etc. |

## Relationships

### Outgoing (Event → Other)

| Key | Relationship | Target | Description |
|-----|--------------|--------|-------------|
| `knowledge` | `APPLIES_KNOWLEDGE` | Ku | Knowledge applied at event |
| `goals` | `CONTRIBUTES_TO_GOAL` | Goal | Goals event contributes to |
| `habits` | `PRACTICED_AT_EVENT` | Habit | Habits practiced at event |
| `celebrated_goals` | `CELEBRATED_BY_EVENT` | Goal | Goals celebrated by event |

### Incoming (Other → Event)

| Key | Relationship | Source | Description |
|-----|--------------|--------|-------------|
| `conflicting_events` | `CONFLICTS_WITH` | Event | Events that conflict |

### Bidirectional

- `CONFLICTS_WITH` - Event scheduling conflicts

## Cross-Domain Mappings

| Field | Target Label | Relationships |
|-------|--------------|---------------|
| `knowledge` | Ku | `APPLIES_KNOWLEDGE` |
| `goals` | Goal | `CONTRIBUTES_TO_GOAL` |
| `habits` | Habit | `PRACTICED_AT_EVENT` |
| `conflicts` | Event | `CONFLICTS_WITH` |

## Query Intent

**Default:** `QueryIntent.PRACTICE`

| Context | Intent |
|---------|--------|
| `context` | `PRACTICE` |
| `impact` | `HIERARCHICAL` |

## MEGA-QUERY Sections

- `upcoming_event_uids` - Upcoming event UIDs
- `today_event_uids` - Events scheduled for today
- `active_events_rich` - Full event data with graph context

## Scoring Weights

| Factor | Weight | Description |
|--------|--------|-------------|
| `timing` | 0.4 | Schedule priority |
| `goals` | 0.3 | Goal contribution |
| `knowledge` | 0.2 | Knowledge application |
| `habits` | 0.1 | Habit practice |
| `tasks` | 0.0 | Not directly related |

## Search Methods

**Service:** `EventsSearchService` (`/core/services/events/events_search_service.py`)

### Inherited from BaseService

| Method | Description |
|--------|-------------|
| `search(query, user_uid)` | Text search across title, description, location |
| `get_by_status(status, user_uid)` | Filter by KuStatus |
| `get_by_domain(domain, user_uid)` | Filter by Domain |
| `get_by_category(category, user_uid)` | Filter by event_type (category_field) |
| `get_by_relationship(related_uid, rel, dir)` | Graph traversal |
| `graph_aware_faceted_search(request)` | Unified search with graph context |

### Domain-Specific Methods

| Method | Description |
|--------|-------------|
| `get_upcoming(user_uid, days=7)` | Events in next N days |
| `get_past(user_uid, days=30)` | Events in past N days |
| `get_by_date_range(start, end, user_uid)` | Events in date range |
| `get_recurring(user_uid)` | Recurring events only |
| `get_by_event_type(event_type, user_uid)` | Filter by type |
| `get_related_to_goal(goal_uid, user_uid)` | Events related to goal |
| `intelligent_search(query, user_uid, context)` | AI-enhanced search |
| `get_events_needing_prep(user_uid, days=3)` | Upcoming events needing preparation |
| `get_calendar_view(user_uid, month, year)` | Calendar-formatted view |
| `get_prioritized(user_uid, limit=10)` | Smart prioritization |

**Full catalog:** [Search Service Methods Reference](/docs/reference/SEARCH_SERVICE_METHODS.md)

## Intelligence Service

`EventsIntelligenceService` provides event analysis and insights (pure Cypher, no APOC):

| Method | Description |
|--------|-------------|
| `get_event_with_context(uid)` | Event with full graph neighborhood |
| `get_performance_analytics(user_uid, period_days)` | Event performance metrics for period |
| `analyze_event_impact(uid)` | Impact analysis on goals/habits |
| `get_domain_insights(uid, min_confidence)` | Domain-specific insights |

**See:** [Intelligence Services Index](/docs/intelligence/INTELLIGENCE_SERVICES_INDEX.md)

## Progress Service (January 2026)

`EventsProgressService` handles progress tracking and completion:

| Method | Description |
|--------|-------------|
| `complete_event_with_cascade(event_uid, user_context)` | Complete with cascade updates |
| `get_attendance_rate(user_uid, period_days)` | Attendance rate metrics |
| `get_quality_trends(user_uid, period_days)` | Quality score trends |
| `get_goal_contribution_metrics(user_uid)` | Goal contribution analysis |
| `get_weekly_summary(user_uid, weeks_back)` | Weekly breakdown |
| `get_habit_event_stats(user_uid)` | Habit event statistics |

## Scheduling Service (January 2026)

`EventsSchedulingService` handles smart scheduling and conflict detection:

| Method | Description |
|--------|-------------|
| `schedule_event_smart(request, user_context)` | Smart event scheduling |
| `check_conflicts(event_uid)` | Detect time conflicts with other events |
| `suggest_time_slots(user_uid, date, duration)` | Suggest available time slots |
| `find_next_available_slot(user_uid, duration)` | Find next free slot |
| `create_recurring_events(request)` | Generate recurring event instances |
| `get_busy_times(user_uid, date)` | Get busy time periods |
| `get_calendar_density(user_uid, date_range)` | Calendar density analysis |

**See:** [Intelligence Services Index](/docs/intelligence/INTELLIGENCE_SERVICES_INDEX.md)

## Events/Publishing

The Events domain publishes domain events for cross-service communication:

| Event | Trigger | Data |
|-------|---------|------|
| `CalendarEventCreated` | Event created | `event_uid`, `user_uid`, `title`, `event_date` |
| `CalendarEventUpdated` | Event modified | `event_uid`, `user_uid`, `changed_fields` |
| `CalendarEventCompleted` | Event marked complete | `event_uid`, `user_uid`, `completion_time` |
| `CalendarEventCancelled` | Event cancelled | `event_uid`, `user_uid`, `reason` |
| `CalendarEventRescheduled` | Event rescheduled | `event_uid`, `user_uid`, `old_date`, `new_date` |
| `EventAttendeeAdded` | Attendee added | `event_uid`, `event_title`, `attendee_uid`, `role` |
| `EventAttendeeRemoved` | Attendee removed | `event_uid`, `event_title`, `attendee_uid` |

**Event handling:** Other services subscribe to these events (e.g., UserContext invalidation, habit practice tracking, attendee notifications).

## UI Routes

### Three-View Dashboard

| Route | Method | Description |
|-------|--------|-------------|
| `/events` | GET | Main dashboard with List/Create/Calendar tabs |
| `/events?view=list` | GET | List view (default) |
| `/events?view=create` | GET | Create event form |
| `/events?view=calendar` | GET | Calendar view |

### HTMX Fragments

| Route | Method | Description |
|-------|--------|-------------|
| `/events/view/list` | GET | List view fragment |
| `/events/view/create` | GET | Create form fragment |
| `/events/view/calendar` | GET | Calendar fragment |
| `/events/list-fragment` | GET | Filtered list for updates |
| `/events/quick-add` | POST | Create event via form |

### Detail Routes

| Route | Method | Description |
|-------|--------|-------------|
| `/events/{uid}` | GET | View event detail |
| `/events/{uid}/edit` | GET/POST | Edit event |
| `/events/{uid}/complete` | POST | Mark event complete |
| `/events/{uid}/reschedule` | POST | Reschedule event |

## Code Examples

### Create an Event

```python
from core.models.event.event_request import EventCreateRequest
from core.models.event.event import EventType
from datetime import date, time

result = await events_service.create_event(
    EventCreateRequest(
        title="Python Study Group",
        description="Weekly Python learning session",
        event_date=date.today() + timedelta(days=3),
        start_time=time(14, 0),
        end_time=time(16, 0),
        event_type=EventType.LEARNING,
        location="Online - Zoom",
    ),
    user_uid=user_uid,
)
event = result.value
```

### Link Event to Habit

```python
result = await events_service.link_event_to_habit(
    event_uid=event.uid,
    habit_uid="habit.weekly-learning",
)
```

### Get Upcoming Events

```python
result = await events_service.search.get_upcoming(
    user_uid=user_uid,
    days=7,
)
upcoming_events = result.value
```

### Check for Conflicts

```python
from core.models.event.event_request import CheckConflictsRequest

result = await events_service.check_conflicts(
    CheckConflictsRequest(event_uid="event:123")
)
conflicting_event_uids = result.value  # List of conflicting event UIDs
```

### Get Attendance Rate

```python
result = await events_service.get_attendance_rate(
    user_uid=user_uid,
    period_days=30,
)
# Returns: {"attendance_rate": 0.85, "completed": 17, "total_scheduled": 20, ...}
```

## See Also

- [Tasks Domain](tasks.md) - Events may execute tasks
- [Goals Domain](goals.md) - Events contribute to goals
- [Habits Domain](habits.md) - Events practice habits
