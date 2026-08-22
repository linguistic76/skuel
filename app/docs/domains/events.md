---
title: Events Domain
created: 2025-12-04
updated: 2026-06-11
status: current
category: domains
tags: [events, scheduling-domain, integration-domain, domain]
---

# Events Domain

**Type:** Activity Domain (1 of 6)
**UID Prefix:** `event:`
**Entity Label:** `Event`
**Config:** `EVENTS_CONFIG` (from `core.models.relationship_registry`)

## Purpose

Events represents time commitments — things a user attends, participates in, or schedules. It is one of the 6 Activity Domains alongside Tasks, Goals, Habits, Choices, and Principles. Events shares the same infrastructure as all Activity Domains: `create_common_sub_services()` factory, facade pattern, `UserOwnedEntity` base class.

Events additionally has an integration sub-service (`EventsHabitIntegrationService`) that bridges it with Habits, and the `ActivityType` enum (12 types: TASK, HABIT, EVENT, LEARNING, MILESTONE, DEADLINE, etc.) gives Events polymorphic calendar coverage. The **Calendar** cross-cutting system aggregates Events alongside Tasks, Habits, and Goals into a unified timeline — Calendar is the scheduling system, Events are the things being scheduled.

## Key Files

| Component | Location |
|-----------|----------|
| Model | `/core/models/event/event.py` |
| DTO | `/core/models/event/event_dto.py` |
| Request Models | `/core/models/event/event_request.py` |
| Relationships | `UnifiedRelationshipService` with `EVENTS_CONFIG` (typed multi-edge view: `EventCrossContext`) |
| Core Service | `/core/services/events/events_core_service.py` |
| Search Service | `/core/services/events/events_search_service.py` |
| Habit Integration | `/core/services/events/events_habit_integration_service.py` |
| Learning Service | `/core/services/events/events_learning_service.py` |
| Progress Service | `/core/services/events/events_progress_service.py` |
| Scheduling Service | `/core/services/events/events_scheduling_service.py` |
| Event Handler Service | `/core/services/events/event_event_handler_service.py` |
| Intelligence Service | `/core/services/events/events_intelligence_service.py` |
| Facade | `/core/services/events_service.py` |
| Config | `EVENTS_CONFIG` in `/core/models/relationship_registry.py` |
| Events | `/core/events/calendar_event_events.py` |
| UI Routes | `/adapters/inbound/events_ui.py` |
| View Components | `/ui/events/views.py` |

## Domain Enums

| Enum | Import | Values | YAML Field |
|------|--------|--------|------------|
| `RecurrencePattern` | `core.models.enums` | NONE, DAILY, WEEKDAYS, WEEKENDS, WEEKLY, BIWEEKLY, MONTHLY, QUARTERLY, YEARLY, CUSTOM | `recurrence_pattern` |
| `EnergyLevel` | `core.models.enums` | LOW, MEDIUM, HIGH, VARIABLE | — (scheduling) |
| `ActivityType` | `core.models.enums` | TASK, HABIT, EVENT, LEARNING, MILESTONE, DEADLINE, MEETING, PRACTICE, REVIEW, BREAK, BLOCK, PLACEHOLDER | `event_type` |
| `Priority` | `core.models.enums` | LOW, MEDIUM, HIGH, CRITICAL | `priority` |

**See:** [Enum Architecture](/docs/architecture/ENUM_ARCHITECTURE.md)

## Facade Pattern (February 2026)

`EventsService` uses explicit `async def` delegation methods:

```python
class EventsService(BaseService[EventsOperations, Event]):
    core: EventsCoreService
    search: EventsSearchService
    habits: EventsHabitIntegrationService
    learning: EventsLearningService  # study sessions, spaced repetition, LP schedules
    progress: EventsProgressService
    scheduling: EventsSchedulingService
    relationships: UnifiedRelationshipService
    event_handler: EventEventHandlerService
    intelligence: EventsIntelligenceService
    knowledge_intelligence: ActivityKnowledgeIntelligenceService  # shared singleton

    # Explicit delegation — MyPy-native, no mixin needed
    async def get_event(self, *args: Any, **kwargs: Any) -> Any:
        return await self.core.get_event(*args, **kwargs)

    async def optimize_recurring_schedule(self, *args: Any, **kwargs: Any) -> Any:
        return await self.scheduling.optimize_recurring_schedule(*args, **kwargs)

    async def create_recurring_events(self, *args: Any, **kwargs: Any) -> Any:
        return await self.scheduling.create_recurring_events(*args, **kwargs)
```

**Note (April 2026):** Cross-domain read methods (`get_events_for_knowledge`, `get_knowledge_reinforcement_stats`, `get_events_supporting_goal`, `get_event_goal_support`, `get_event_knowledge_reinforcement`) were removed from the facade — these queries now go through `CrossDomainQueryService`. `EventsLearningService` remains for creation-side methods (study sessions, spaced repetition, LP schedules).

## Event Handler — Insight Persistence (March 2026)

`EventEventHandlerService` handles fire-and-forget reactive logic and persists structured insights to `InsightStore`:

| Handler | Trigger | InsightType | Impact |
|---------|---------|------------|--------|
| `handle_event_rescheduled` | Chronic pattern (4+ in 30 days) | `IMBALANCE_DETECTED` | HIGH |
| `handle_event_created` | Overcommitted (13+ events/week) | `IMBALANCE_DETECTED` | HIGH |

Also handles: attendance time-of-day tracking, goal alignment checks, rescheduling pattern classification, scheduling density monitoring.

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
| `event_type` | `EventType` | Lowercase StrEnum (`core/models/enums/event_enums.py`): meeting, workshop, deadline, learning, etc. |
| `status` | `EntityStatus` | Scheduled, Completed, Cancelled |
| `priority` | `Priority` | Low, Medium, High, Urgent |
| `recurrence_pattern` | `RecurrencePattern?` | Daily, Weekly, etc. |

## Relationships

### Outgoing (Event → Other)

| Key | Relationship | Target | Description |
|-----|--------------|--------|-------------|
| `knowledge` | `APPLIES_KNOWLEDGE` | Ku | Knowledge applied at event |
| `goals` | `CONTRIBUTES_TO_GOAL` | Goal | Goals event contributes to |
| `habits` | `REINFORCES_HABIT` | Habit | Habit this event reinforces |
| `celebrated_goals` | `CELEBRATES_GOAL` | Goal | Goals celebrated by event |

### Incoming (Other → Event)

| Key | Relationship | Source | Description |
|-----|--------------|--------|-------------|
| `conflicting_events` | `CONFLICTS_WITH` | Event | Events that conflict |
| — | `PRACTICED_AT_EVENT` | Habit | Habits recorded as practiced at event |

### Bidirectional

- `CONFLICTS_WITH` - Event scheduling conflicts

### Derived fields (populated at fetch time, never persisted)

Two fields are populated from graph edges at read time rather than stored as Neo4j properties:

| Field | Edge | Populated by |
|-------|------|--------------|
| `reinforces_habit_uid` | `(Event)-[:REINFORCES_HABIT]->(Habit)` | `enrich_events_with_habit_links()` |
| `contributes_to_goal_uid` | `(Event)-[:CONTRIBUTES_TO_GOAL]->(Goal)` | `enrich_events_with_goal_links()` |

Both helpers live in `core/services/events/_habit_links.py` and `_goal_links.py` respectively and are called by `EventsSearchService.get_prioritized()` before scoring so the priority scorer can read them.

On CREATE, `reinforces_habit_uid` is the edge's INPUT: it rides on the `Event`, and the shared create primitive (`EventsCoreService._write_link_edges`) turns it into the `REINFORCES_HABIT` edge for both create doors — the generated CRUD route and `create_event`. The request-only `milestone_celebration_for_goal` becomes `CELEBRATES_GOAL` in the same batch. Every request-supplied UID passes `keep_permitted_link_edges` (exists / owner / kind), and a refused link is logged, never fatal to the event. See `docs/architecture/CROSS_DOMAIN_UID_PATTERNS.md` § edge carrier.

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
- `entities_rich["events"]` - Full event data with graph context

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
| `get_by_status(status, user_uid)` | Filter by EntityStatus |
| `get_by_category(category, user_uid)` | Filter by event_type (category_field) |
| `get_by_relationship(related_uid, rel, dir)` | Graph traversal |
| `graph_aware_faceted_search(request)` | Unified search with graph context |

### Domain-Specific Methods

| Method | Description |
|--------|-------------|
| `get_upcoming(days_ahead=7, user_uid, limit)` | Events in next N days (TimeQueryMixin) |
| `get_in_range(start, end, user_uid)` | Events in date range |
| `get_recurring(user_uid)` | Recurring events only |
| `get_for_goal(goal_uid, user_uid)` | Events supporting a goal |
| `get_for_habit(habit_uid, user_uid)` | Events reinforcing a habit |
| `get_calendar_events(user_uid, start, end)` | Calendar window query |
| `get_conflicting(event_uid)` | Time-overlap conflicts (PLANNED surface) |
| `get_prioritized(user_context, limit=10)` | Smart prioritization |

**Full catalog:** [Search Service Methods Reference](/docs/reference/SEARCH_SERVICE_METHODS.md)

## Intelligence Service

`EventsIntelligenceService` provides event analysis and insights (pure Cypher, no APOC):

| Method | Description |
|--------|-------------|
| `get_with_context(uid)` | Event with full graph neighborhood (shared mechanism B) |
| `analyze_event_performance(uid)` | Performance analysis for one event |
| `analyze_upcoming_events(user_uid, days_ahead)` | Batch analysis of upcoming events |
| `get_performance_analytics(user_uid, period_days)` | Event performance metrics for period |
| `get_domain_insights(uid, min_confidence)` | Domain-specific insights |

**See:** [Intelligence Services Index](/docs/intelligence/INTELLIGENCE_SERVICES_INDEX.md)

## Progress Service (January 2026)

`EventsProgressService` handles progress metrics (event completion itself goes
through `update_event`, which stamps `completed_at` on the transition):

| Method | Description |
|--------|-------------|
| `get_attendance_rate(user_uid, period_days)` | Attendance rate metrics |
| `get_quality_trends(user_uid, period_days)` | Quality score trends |
| `get_goal_contribution_metrics(user_uid)` | Goal contribution analysis |
| `get_weekly_summary(user_uid, weeks_back)` | Weekly breakdown |
| `get_habit_event_stats(user_uid)` | Habit event statistics |

## Scheduling Service

`EventsSchedulingService` handles Events-domain recurring event creation:

| Method | Description |
|--------|-------------|
| `optimize_recurring_schedule(user_uid, pattern)` | Generate optimized recurrence dates (Events-aware) |
| `create_recurring_events(user_uid, title, pattern)` | Create recurring Event nodes |

**Cross-domain scheduling** (busy times, slot suggestions, conflict detection, calendar density)
lives in `CalendarOptimizationOrchestrator`, which aggregates Tasks + Events together.

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

Read-focused UI at `/events` is planned. API routes remain active.

## Code Examples

### Create an Event

```python
from core.models.enums import EventType
from core.models.event.event_request import EventCreateRequest
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
    CheckConflictsRequest(event_uid="event.123")
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
