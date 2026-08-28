---
title: Event-Driven Architecture
updated: 2026-03-25
category: patterns
related_skills:
- python
- result-pattern
related_docs: []
---

# Event-Driven Architecture

## Quick Start

**Skills:** [@python](../../.claude/skills/python/SKILL.md), [@result-pattern](../../.claude/skills/result-pattern/SKILL.md)

For hands-on implementation:
1. Invoke `@python` for event handler patterns with `@safe_event_handler`
2. Invoke `@result-pattern` for event error handling
3. See event definitions in `/core/events/{domain}_events.py`
4. Continue below for complete event-driven architecture

**Related Documentation:**
- [/core/events/](/core/events/) - 60+ events across all domains

---

## Quick Reference

SKUEL is migrating to event-driven architecture to eliminate service-to-service dependencies through decoupled domain events.

## Core Principle: "Events over dependencies"

**SKUEL is migrating to event-driven architecture to eliminate service-to-service dependencies.**

---

## Why Events?

### Problems with Direct Dependencies

- Circular dependencies (services need each other)
- Tight coupling (changes ripple across services)
- Hard to test (must mock multiple services)
- Complex bootstrap (specific initialization order required)
- No audit trail (state changes hidden in method calls)

### Benefits of Events

- Zero coupling (services don't know about each other)
- Easy testing (mock event bus only)
- Flexible bootstrap (any initialization order)
- Full audit trail (all state changes published)
- Async processing (events can be batched/delayed)

---

## Event Bus Infrastructure

**Location:** `/adapters/infrastructure/event_bus.py`

### Current Implementation

- `InMemoryEventBus` - Simple pub/sub for single-process use
- Sync and async handler support
- Type-safe event subscriptions
- Error handling and logging

### Usage Example

```python
# Service publishes events
class TasksService:
    def __init__(self, backend, event_bus):
        self.backend = backend
        self.event_bus = event_bus

    async def complete_task(self, uid: str) -> Result[Task]:
        result = await self.backend.complete(uid)

        if result.is_ok and self.event_bus:
            event = TaskCompleted(
                task_uid=uid,
                user_uid=result.value.user_uid,
            )
            await self.event_bus.publish_async(event)

        return result

# Other services subscribe
class UserService:
    async def handle_task_completed(self, event: TaskCompleted):
        await self.invalidate_context(event.user_uid)

# Bootstrap wires them together
event_bus.subscribe(TaskCompleted, user_service.handle_task_completed)
```

---

## Auto-Timestamping

`BaseEvent.occurred_at` uses `field(default_factory=datetime.now, kw_only=True)` — every event is automatically timestamped at construction. Do NOT pass `occurred_at=datetime.now()` manually. Override only in tests or event replay scenarios.

---

## Event Naming Convention

**Format:** `{domain}.{action}` (lowercase, dot-separated)

**Examples:**
- `task.created`, `task.completed`, `task.deleted`
- `goal.achieved`, `goal.progress_updated`
- `habit.completed`, `habit.streak_broken`
- `user.activity_recorded`, `user.deleted`
- `knowledge.mastered`, `learning_path.completed`

---

## Current Migration Status

### Phase 5: Event Bus Efficiency (✅ January 2026)

**Status:** Production Ready (January 15, 2026)

**Improvements:**
1. ✅ **Concurrent Async Handler Execution** - `asyncio.gather()` for parallel handler execution
2. ✅ **Batch Event Publishing** - O(1) vs O(n) for bulk operations
3. ✅ **Complete Event Registry** - All 60+ events registered for serialization/replay
4. ✅ **Expanded Context Invalidation** - 49 events trigger context refresh (up from 31)
5. ✅ **Curriculum Domain Events** - PS/MOC events wired for context invalidation
6. ✅ **Performance Monitoring** - Handler execution timing and slow handler detection

**Event Registry Groups:** *deleted 2026-08-17.* The `*_EVENTS` lists and
`ALL_EVENTS` that this section catalogued were removed along with the hand-written
`EVENT_REGISTRY`: they had zero consumers anywhere in the repo, and four of the
names listed here (`EVENT_EVENTS`, `CURRICULUM_EVENTS`, `SUBMISSION_EVENTS`,
`ASSIGNMENT_EVENTS`) had already stopped existing. `EVENT_REGISTRY` is now derived
by comprehension from the imported event classes — `list_event_types()` is the
live answer, and there is no grouping layer to keep in sync.

### Phase 4 Complete (✅ November 2025)

**5 Integrations Operational:**
1. ✅ **Habit → Achievements** - Badge awarding on streak milestones + aggregate badges (completion, quality, identity) on HabitCompleted
2. ✅ **Goal → Recommendations** - Learning path suggestions on goal achievement
3. ✅ **LP → Recommendations** - Next learning suggestions on path completion
4. ✅ **Multi-Domain Analytics** - Cross-domain event aggregation
5. ✅ **Report Generation** - Milestone reports on achievements

### Target State: Achieved ✅

- ✅ Services depend ONLY on event bus (infrastructure)
- ✅ Zero service-to-service dependencies
- ✅ All state changes published as events
- ✅ Bootstrap wires subscribers (any initialization order works)
- ✅ Best-effort error handling (handlers log but don't raise)
- ✅ Full audit trail capability (event history capture)
- ✅ Batch events for O(1) bulk operations

---

## Migration Guide

### Quick Reference

1. Define domain events in `/core/events/`
2. Add `event_bus` parameter to services
3. Publish events on state changes
4. Create subscriber methods in consuming services
5. Wire subscribers in `compose_services()`
6. Remove direct service dependencies

---

## Bootstrap Pattern (Post-Migration)

**Current Implementation (Phase 4 Complete):**

1. Create event bus (single instance)
2. Create backends (no dependencies)
3. Create all services (pass event_bus only)
4. Wire event subscriptions (after all services exist)

```python
# Bootstrap in services_bootstrap/compose.py
async def compose_services(neo4j_adapter, event_bus=None) -> Result[Services]:
    # 1. Create event bus
    if event_bus is None:
        event_bus = InMemoryEventBus(capture_history=True)

    # 2. Create backends (no dependencies)
    tasks_backend = UniversalNeo4jBackend[Task](driver, "Task", Task)
    habits_backend = UniversalNeo4jBackend[Habit](driver, "Habit", Habit)
    # ... more backends ...

    # 3. Create services (event_bus only)
    tasks_service = TasksService(backend=tasks_backend, event_bus=event_bus)
    habits_service = HabitsService(backend=habits_backend, event_bus=event_bus)
    # ... more services ...

    # 4. Wire event subscriptions
    event_bus.subscribe(HabitStreakMilestone, habits_service.event_handler.handle_habit_streak_milestone)
    event_bus.subscribe(GoalAchieved, lp_intelligence.handle_goal_achieved)
    # ... more subscriptions ...

    return Result.ok(Services(...))
```

**Benefits Achieved:**
- ✅ Services can be created in any order
- ✅ No circular dependency issues
- ✅ Easy to add new subscribers
- ✅ Simple to test (mock event bus only)

---

## Batch Event Pattern (January 2026)

For high-volume operations, use batch events to achieve O(1) event overhead vs O(n):

```python
# ❌ Inefficient - O(n) events
for habit_uid in habit_uids:
    event = HabitCompleted(habit_uid=habit_uid, ...)
    await event_bus.publish_async(event)

# ✅ Efficient - O(1) event
event = HabitCompletionBulk(
    habit_uids=tuple(habit_uids),
    user_uid=user_uid,
)
await event_bus.publish_async(event)
```

**Available Batch Events:**
- `HabitCompletionBulk` - Multiple habit completions
- `KnowledgeBulkAppliedInTask` - Task applies multiple KUs
- `KnowledgeBulkBuiltIntoHabit` - Habit builds on multiple KUs
- `KnowledgeBulkInformedChoice` - Choice informed by multiple KUs

---

## Event Publishing Utility

Use `publish_event()` for consistent warning handling when event bus is unavailable:

```python
from core.events import publish_event

# In service methods:
await publish_event(self.event_bus, event, self.logger)
```

**Behavior:**
- If event_bus exists: publishes event normally
- If event_bus is None: logs warning and continues (no exception)

---

## Event Handler Insight Persistence

Event handlers across all 6 Activity Domains and the Learning Loop persist structured insights to `InsightStore` (Neo4j `Insight` nodes) at key decision points. This makes pattern analysis queryable by users — not just write-only logs.

**Pattern:** Each handler accepts an optional `insight_store: InsightStore | None` parameter. When provided, handlers create `PersistedInsight` nodes via `insight_store.create_insight()`. Failures are logged but never propagate (fire-and-forget contract preserved).

| Domain | Insights Persisted | InsightTypes |
|--------|--------------------|--------------|
| Tasks | Overdue completion, priority inflation, principle alignment | `COMPLETION_PATTERN`, `IMBALANCE_DETECTED`, `PRINCIPLE_ALIGNMENT` |
| Goals | Abandonment classification, progress stall, milestone proximity | `COMPLETION_PATTERN`, `IMBALANCE_DETECTED` |
| Events | Chronic rescheduling, schedule overcommitment | `IMBALANCE_DETECTED` |
| Habits | Difficulty detection, streak milestones | `DIFFICULTY_PATTERN`, `STREAK_PATTERN` |
| Choices | Decision patterns, principle alignment gaps | `DECISION_PATTERN`, `PRINCIPLE_ALIGNMENT` |
| Principles | Principle conflicts | `PRINCIPLE_CONFLICT` |
| Learning Loop | Submission iterations, feedback turnaround anomaly, mastery velocity | `LEARNING_PROGRESS`, `COMPLETION_PATTERN`, `MASTERY_ACHIEVED` |

**Wiring:** `services_bootstrap/_event_wiring.py` passes `insight_store` to all 6 Activity Domain facades (which forward it to their per-domain `*EventHandlerService` and `*IntelligenceService` — `HabitEventHandlerService`, `GoalsIntelligenceService`, and so on — via `BaseAnalyticsService`) and directly to `LearningLoopEventHandlerService`.

**See:** [INSIGHT_ACTION_TRACKING.md](/docs/patterns/INSIGHT_ACTION_TRACKING.md), [SUB_SERVICE_CATALOG.md](/docs/reference/SUB_SERVICE_CATALOG.md)

---

## Context Invalidation Coverage

**52 events** trigger UserContext invalidation across all domains:

| Domain | Events |
|--------|--------|
| Tasks | TaskCreated, TaskCompleted, TaskUpdated, TaskDeleted, TaskPriorityChanged |
| Goals | GoalCreated, GoalAchieved, GoalProgressUpdated, GoalAbandoned |
| Habits | HabitCreated, HabitCompleted, HabitCompletionBulk, HabitMissed, HabitStreakBroken, HabitStreakMilestone |
| Events | CalendarEventCreated, CalendarEventUpdated, CalendarEventCompleted, CalendarEventRescheduled, EventAttendeeAdded, EventAttendeeRemoved |
| Choices | ChoiceCreated, ChoiceUpdated, ChoiceMade, ChoiceOutcomeRecorded |
| Principles | PrincipleCreated, PrincipleUpdated, PrincipleStrengthChanged, PrincipleAlignmentAssessed |
| Finance | ExpenseCreated, ExpenseUpdated, ExpensePaid, ExpenseDeleted |
| Learning | KnowledgeCreated, KnowledgeMastered, LessonCompleted, LearningPathStarted, LearningPathCompleted, LearningPathProgressUpdated, PathStepProgressUpdated |
| PS | PathStepCreated, PathStepUpdated, PathStepDeleted, PathStepCompleted |
| Submissions | SubmissionCreated, ReportSubmitted, SubmissionApproved, SubmissionRevisionRequested |

---

## Related Documentation

- [Knowledge Substance Philosophy](/docs/architecture/knowledge_substance_philosophy.md) - Uses event-driven substance tracking
- [Service Creation Template](/docs/reference/templates/service_creation.md)
- `core/events/base.py` - Defining, publishing and subscribing; `core/events/README.md` - the rules
- `services_bootstrap/_event_wiring.py` - most subscription wiring (not all: components that own their handlers subscribe themselves; `git grep '.subscribe('` finds every site)

---

**Last Updated:** March 20, 2026
**Status:** Complete - Phase 5 event bus efficiency improvements deployed
