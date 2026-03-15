---
title: Event-Driven Architecture
updated: 2026-01-19
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
                completed_at=datetime.now()
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

## Event Naming Convention

**Format:** `{domain}.{action}` (lowercase, dot-separated)

**Examples:**
- `task.created`, `task.completed`, `task.deleted`
- `goal.achieved`, `goal.progress_updated`
- `habit.completed`, `habit.streak_broken`
- `user.context_invalidated`
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
5. ✅ **Curriculum Domain Events** - LS/MOC events wired for context invalidation
6. ✅ **Performance Monitoring** - Handler execution timing and slow handler detection

**Event Registry Groups:**
- `TASK_EVENTS` (5 events): TaskCreated, TaskCompleted, TaskUpdated, TaskDeleted, TaskPriorityChanged
- `GOAL_EVENTS` (4 events): GoalCreated, GoalAchieved, GoalProgressUpdated, GoalAbandoned
- `HABIT_EVENTS` (6 events): HabitCreated, HabitCompleted, HabitCompletionBulk, HabitMissed, HabitStreakBroken, HabitStreakMilestone
- `EVENT_EVENTS` (7 events): CalendarEventCreated, CalendarEventUpdated, CalendarEventCompleted, CalendarEventDeleted, CalendarEventRescheduled, EventAttendeeAdded, EventAttendeeRemoved
- `CHOICE_EVENTS` (4 events): ChoiceCreated, ChoiceUpdated, ChoiceMade, ChoiceOutcomeRecorded
- `PRINCIPLE_EVENTS` (4 events): PrincipleCreated, PrincipleUpdated, PrincipleStrengthChanged, PrincipleAlignmentAssessed
- `LEARNING_EVENTS` (12 events): KnowledgeCreated, KnowledgeMastered, LessonCompleted, KnowledgePracticed, LearningPathStarted, LearningPathCompleted, LearningPathProgressUpdated, LearningStepProgressUpdated, PrerequisitesAnalyzed, LearningRecommendationGenerated, etc.
- `KNOWLEDGE_SUBSTANCE_EVENTS` (8 events): KnowledgeAppliedInTask, KnowledgeBuiltIntoHabit, etc.
- `CURRICULUM_EVENTS` (4 events): LearningStepCreated/Updated/Deleted/Completed
- `JOURNAL_EVENTS` (3 events): JournalCreated, JournalUpdated, JournalDeleted
- `ASSIGNMENT_EVENTS` (5 events): AssignmentSubmitted, AssignmentProcessingStarted/Completed/Failed, AssignmentDeleted
- `TRANSCRIPTION_EVENTS` (3 events): TranscriptionCreated, TranscriptionCompleted, TranscriptionFailed
- `USER_EVENTS` (2 events): UserContextInvalidated, UserPreferencesChanged

### Phase 4 Complete (✅ November 2025)

**5 Integrations Operational:**
1. ✅ **Habit → Achievements** - Badge awarding on streak milestones
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

**Complete documentation:** `/home/mike/0bsidian/skuel/docs/guides/EVENT_DRIVEN_MIGRATION_GUIDE.md`

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
# Bootstrap in services_bootstrap.py
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
    event_bus.subscribe(HabitStreakMilestone, habit_achievement_service.handle_habit_streak_milestone)
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
    occurred_at=datetime.now(),
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
from core.events.utils import publish_event

# In service methods:
await publish_event(self.event_bus, event, self.logger)
```

**Behavior:**
- If event_bus exists: publishes event normally
- If event_bus is None: logs warning and continues (no exception)

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
| Learning | KnowledgeCreated, KnowledgeMastered, LessonCompleted, LearningPathStarted, LearningPathCompleted, LearningPathProgressUpdated, LearningStepProgressUpdated |
| LS | LearningStepCreated, LearningStepUpdated, LearningStepDeleted, LearningStepCompleted |
| Journals | JournalCreated, JournalUpdated, JournalDeleted |

---

## Related Documentation

- [Phase 4 Implementation Complete](/home/mike/0bsidian/skuel/docs/patterns/PHASE_4_EVENT_DRIVEN_ARCHITECTURE_COMPLETE.md) - Full implementation details
- [Event-Driven Migration Guide](/home/mike/0bsidian/skuel/docs/guides/EVENT_DRIVEN_MIGRATION_GUIDE.md)
- [Knowledge Substance Philosophy](/home/mike/0bsidian/skuel/docs/architecture/knowledge_substance_philosophy.md) - Uses event-driven substance tracking
- [Service Creation Template](/home/mike/0bsidian/skuel/docs/reference/templates/service_creation.md)

---

**Last Updated:** January 15, 2026
**Status:** Complete - Phase 5 event bus efficiency improvements deployed
