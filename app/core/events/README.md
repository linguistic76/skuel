# SKUEL Domain Events

**Status:** IN PROGRESS (Migration from direct dependencies to events)
**Complete Guide:** `/home/mike/0bsidian/skuel/docs/guides/EVENT_DRIVEN_MIGRATION_GUIDE.md`

## Quick Reference

### Event Structure

All events follow this pattern:

```python
from dataclasses import dataclass
from datetime import datetime

@dataclass
class TaskCompleted:
    """Published when a task is marked complete."""
    # Core identifiers
    task_uid: str
    user_uid: str

    # Event metadata
    completed_at: datetime

    # Optional context
    completion_time_seconds: int | None = None

    @property
    def event_type(self) -> str:
        return "task.completed"
```

### Publishing Events

**Standard Pattern (100% conformance as of October 2025):**

```python
# 1. Top-level imports
from core.events.task_events import TaskCreated, TaskCompleted, TaskUpdated

# 2. Conditional publishing in service methods
if self.event_bus:
    event = TaskCompleted(
        task_uid=task.uid,
        user_uid=task.user_uid,
        completed_at=datetime.now()
    )
    await self.event_bus.publish_async(event)
    self.logger.debug(f"Published {event.event_type} for {task.uid}")
```

**Rules:**
- ✅ Always use typed event objects (frozen dataclasses)
- ✅ Always check `if self.event_bus:` before publishing
- ✅ Always use `publish_async()` in async services
- ✅ Always log at `debug` level (events are high-volume)
- ✅ Always import events at top of file (not local imports)
- ❌ Never use string-based publishing
- ❌ Never log at `info` level for event publishing

### Subscribing to Events

```python
# In service class
async def handle_task_completed(self, event: TaskCompleted) -> None:
    """Handle task completion event."""
    await self.invalidate_context(event.user_uid)
    self.logger.info(f"Processed {event.event_type} for {event.user_uid}")

# In bootstrap
event_bus.subscribe(TaskCompleted, user_service.handle_task_completed)
```

## Event Catalog

### Tasks Domain

**File:** `task_events.py` (to be created)

| Event | When Published | Subscribers |
|-------|----------------|-------------|
| `task.created` | Task created | Analytics, User Context |
| `task.completed` | Task marked complete | User Context, Goal Analytics |
| `task.updated` | Task properties changed | User Context |
| `task.deleted` | Task deleted | User Context |
| `task.priority_changed` | Priority changed | Analytics |

### Goals Domain

**File:** `goal_events.py` (to be created)

| Event | When Published | Subscribers |
|-------|----------------|-------------|
| `goal.created` | Goal created | Analytics, Recommendations |
| `goal.achieved` | Goal achieved | User Context, Analytics, Celebrations |
| `goal.progress_updated` | Progress changed | Analytics, Dashboard |
| `goal.abandoned` | Goal abandoned | Analytics, Insights |

### Habits Domain

**File:** `habit_events.py` (to be created)

| Event | When Published | Subscribers |
|-------|----------------|-------------|
| `habit.completed` | Habit completion logged | User Context, Streak Tracking |
| `habit.streak_broken` | Streak broken | Notifications, Analytics |
| `habit.created` | Habit created | Analytics |
| `habit.missed` | Habit missed (scheduled but not done) | Reminders, Analytics |

### User Context Domain

**File:** `user_events.py` (to be created)

| Event | When Published | Subscribers |
|-------|----------------|-------------|
| `user.context_invalidated` | Context needs refresh | Askesis, Search, Recommendations |
| `user.preferences_changed` | Preferences updated | Personalization Services |

### Learning Domain

**File:** `learning_events.py` (to be created)

| Event | When Published | Subscribers |
|-------|----------------|-------------|
| `knowledge.mastered` | KU mastered | Learning Path, Analytics |
| `learning_path.started` | Path started | Progress Tracking, Analytics |
| `learning_path.completed` | Path completed | Achievements, Analytics |
| `prerequisites.analyzed` | Prerequisites computed | KU Service, Path Builder |

## Migration Checklist

### For Service Publishers

- [ ] Add `event_bus: EventBusOperations | None = None` parameter
- [ ] Define events in `/core/events/{domain}_events.py`
- [ ] Publish events after successful state changes
- [ ] Log event publication
- [ ] Remove direct service dependencies
- [ ] Update tests to verify event publication

### For Service Subscribers

- [ ] Create `handle_{event_name}()` methods
- [ ] Add event type hints to handler signatures
- [ ] Make handlers idempotent (safe to retry)
- [ ] Log event processing
- [ ] Update tests for event handlers

### For Bootstrap

- [ ] Create `_wire_event_subscribers()` function
- [ ] Subscribe handlers to event types
- [ ] Remove service-to-service dependency injection
- [ ] Simplify initialization order
- [ ] Update integration tests

## Examples

### Example 1: Simple Event Publication

```python
# tasks_service.py
# Top-level imports
from core.events.task_events import TaskCompleted

async def complete_task(self, uid: str) -> Result[Task]:
    result = await self.backend.complete(uid)

    if self.event_bus and result.is_ok:
        event = TaskCompleted(
            task_uid=uid,
            user_uid=result.value.user_uid,
            completed_at=datetime.now()
        )
        await self.event_bus.publish_async(event)
        self.logger.debug(f"Published TaskCompleted event for task {uid}")

    return result
```

### Example 2: Event Handler

```python
# user_service.py
async def handle_task_completed(self, event: TaskCompleted) -> None:
    """Invalidate user context when task completed."""
    try:
        await self.invalidate_context(event.user_uid)
        self.logger.info(f"Context invalidated for user {event.user_uid}")
    except Exception as e:
        self.logger.error(f"Error handling task.completed: {e}")
```

### Example 3: Bootstrap Wiring

```python
# services_bootstrap.py
def _wire_event_subscribers(event_bus: EventBusOperations, services: Services):
    """Wire all event subscribers."""

    # User context invalidation
    event_bus.subscribe(TaskCompleted, services.user_service.handle_task_completed)
    event_bus.subscribe(GoalUpdated, services.user_service.handle_goal_updated)

    # Analytics
    event_bus.subscribe(TaskCompleted, services.analytics.handle_task_completed)
    event_bus.subscribe(GoalAchieved, services.analytics.handle_goal_achieved)

    logger.info("✅ Event subscribers wired")
```

### Example 4: Testing Event Flow

```python
# test_event_flow.py
@pytest.mark.asyncio
async def test_task_completion_flow():
    """Test complete flow: task → event → context invalidation."""
    event_bus = InMemoryEventBus()

    tasks_service = TasksService(backend=mock_backend, event_bus=event_bus)
    user_service = UserService(backend=mock_backend)

    # Wire subscriber
    event_bus.subscribe(TaskCompleted, user_service.handle_task_completed)

    # Spy on user service
    user_service.invalidate_context = AsyncMock()

    # Act
    await tasks_service.complete_task("task-123")
    await asyncio.sleep(0.1)  # Allow async processing

    # Assert
    user_service.invalidate_context.assert_called_once()
```

## Event Naming Rules

1. **Lowercase, dot-separated:** `task.completed` not `TaskCompleted` or `task_completed`
2. **Past tense:** `created`, `completed`, `deleted` (what happened, not what will happen)
3. **Domain prefix:** Always start with domain (`task.`, `goal.`, `user.`)
4. **Specific action:** `task.priority_changed` not `task.updated` when priority is the key change
5. **No verbs in domain:** `task.completed` not `tasks.completed` (domain is singular)

## Benefits Tracking

### Before Event Migration
- ❌ 9 circular dependency workarounds
- ❌ 85 lines of post-construction wiring
- ❌ 6 services with initialization order dependencies
- ❌ No audit trail of state changes

### After Event Migration
- ✅ 0 circular dependencies
- ✅ 0 post-construction wiring
- ✅ Order-independent bootstrap
- ✅ Full audit trail via event logs
- ✅ Easier testing (mock event bus only)
- ✅ Flexible feature toggles (subscribe/unsubscribe)

## Timeline

**Week 1:** Define all domain events
**Week 2:** Convert publishers (Tasks, Goals, Habits)
**Week 3:** Wire subscribers (User, Analytics)
**Week 4:** Remove circular dependencies, cleanup

**Target Completion:** End of January 2025
