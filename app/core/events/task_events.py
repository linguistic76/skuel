"""
Task Domain Events
==================

Events published by TasksService for task lifecycle operations.

Event Catalog:
- task.created - Task created
- task.completed - Task marked complete
- task.updated - Task properties changed
- task.deleted - Task deleted
- task.priority_changed - Task priority changed (high-priority event)

Subscribers:
- TaskEventHandlerService (duration calibration, overdue detection, principle alignment)
- UserService (context invalidation)
- GoalAnalyticsService (goal progress tracking)
- AnalyticsEngine (completion patterns)
"""

from dataclasses import dataclass
from typing import ClassVar

from core.events.base import BaseEvent
from core.models.type_hints import UserUID

# ============================================================================
# TASK LIFECYCLE EVENTS
# ============================================================================


@dataclass(frozen=True)
class TaskCreated(BaseEvent):
    """
    Published when a task is created.

    Subscribers:
    - Analytics (track task creation patterns)
    - UserService (invalidate context)
    """

    task_uid: str
    user_uid: UserUID
    title: str
    priority: str
    domain: str | None

    event_type: ClassVar[str] = "task.created"


@dataclass(frozen=True)
class TaskCompleted(BaseEvent):
    """
    Published when a task is marked complete.

    This is a high-volume, high-importance event.
    Triggers context invalidation, analytics, and goal progress updates.

    Subscribers:
    - TaskEventHandlerService (duration calibration, overdue detection, principle alignment)
    - UserService (invalidate user context)
    - GoalAnalyticsService (update goal progress)
    - AnalyticsEngine (track completion patterns)

    **The idempotency contract.** Completing an already-completed task is a
    legal, reachable action (both explicit-complete doors sit behind an
    ownership check with no already-completed guard), and the cascade
    deliberately re-runs on it so it stays a repair path. ``is_repeat`` is the
    single seam that makes the re-run safe:

        Handlers that **recompute** state ignore ``is_repeat`` and do their
        work every time — that is the repair path. Handlers that **count** or
        **append** skip when ``is_repeat`` is true.

    Recompute-shaped subscribers (goal progress, PS engagement auto-complete,
    knowledge generation, context invalidation) therefore read nothing from
    this flag. The counting/appending ones do: duration-calibration EMA and its
    sample counter, the overdue ``PersistedInsight`` append, the
    ``ProductivityAnalytics.tasks_completed`` increment, and the Prometheus
    ``entities_completed{task}`` counter — the last of which cannot be fixed
    any other way, since a monotonic counter has no un-increment.

    The principle-alignment check is **split across both halves** and is the
    reason the contract names appending separately from counting: it recomputes
    the alignment from the graph on every complete, then appends a
    ``PersistedInsight`` only when this is not a repeat.
    """

    task_uid: str
    user_uid: UserUID

    # Optional context for analytics
    completion_time_seconds: int | None = None
    was_overdue: bool = False

    #: True when the task was already COMPLETED before this complete — i.e. the
    #: publisher's write was not a transition into COMPLETED. See the contract
    #: in the class docstring.
    is_repeat: bool = False

    event_type: ClassVar[str] = "task.completed"


@dataclass(frozen=True)
class TaskUpdated(BaseEvent):
    """
    Published when task properties change.

    Subscribers:
    - UserService (invalidate context if significant change)
    - Analytics (track update patterns)
    """

    task_uid: str
    user_uid: UserUID
    updated_fields: list[str]

    # Include old/new values for significant fields
    priority_changed: bool = False
    due_date_changed: bool = False

    event_type: ClassVar[str] = "task.updated"


@dataclass(frozen=True)
class TaskDeleted(BaseEvent):
    """
    Published when a task is deleted.

    Subscribers:
    - UserService (invalidate context)
    - Analytics (track deletion patterns)
    """

    task_uid: str
    user_uid: UserUID

    # Context for why deleted
    reason: str | None = None  # "completed_elsewhere", "no_longer_needed", etc.

    event_type: ClassVar[str] = "task.deleted"


@dataclass(frozen=True)
class TaskPriorityChanged(BaseEvent):
    """
    Published when task priority changes.

    This is a specialized event for high-priority changes that need
    immediate attention from multiple subscribers.

    Subscribers:
    - TaskEventHandlerService (categorization, cascade impact, inflation detection)
    - UserService (invalidate context)
    - NotificationService (notify if priority increased to urgent)
    - Analytics (track priority escalation patterns)
    """

    task_uid: str
    user_uid: UserUID
    old_priority: str
    new_priority: str

    # Was this an escalation to urgent?
    escalated_to_urgent: bool = False

    event_type: ClassVar[str] = "task.priority_changed"


# ============================================================================
# TASK BATCH EVENTS
# ============================================================================


@dataclass(frozen=True)
class TasksBulkCompleted(BaseEvent):
    """
    Published when multiple tasks are completed in a batch operation.

    More efficient than publishing N individual TaskCompleted events.

    Subscribers:
    - TaskEventHandlerService (batch pattern classification)
    - UserService (single context invalidation)
    - GoalAnalyticsService (batch goal progress update)
    """

    task_uids: list[str]
    user_uid: UserUID
    count: int = 0  # Number of tasks completed

    def __post_init__(self) -> None:
        # Set count from task_uids length
        object.__setattr__(self, "count", len(self.task_uids))

    event_type: ClassVar[str] = "tasks.bulk_completed"


# ============================================================================
# USAGE EXAMPLES
# ============================================================================

"""
Publishing Task Events:
=======================

# In TasksService.create()
async def create_task(self, task: Task) -> Result[Task]:
    result = await self.backend.create(task)

    if result.is_ok and self.event_bus:
        event = TaskCreated(
            task_uid=task.uid,
            user_uid=task.user_uid,
            title=task.title,
            priority=task.priority or "medium",
            domain=task.domain.value if task.domain else None,
        )
        await self.event_bus.publish_async(event)
        self.logger.info(f"Published {event.event_type} for {task.uid}")

    return result


# In TasksService.complete()
async def complete_task(self, uid: str) -> Result[Task]:
    start_time = datetime.now()
    result = await self.backend.complete(uid)

    if result.is_ok and self.event_bus:
        task = result.value
        completion_time = (datetime.now() - start_time).total_seconds()

        event = TaskCompleted(
            task_uid=task.uid,
            user_uid=task.user_uid,
            completion_time_seconds=int(completion_time),
            was_overdue=task.due_date and task.due_date < datetime.now()
        )
        await self.event_bus.publish_async(event)

    return result


Subscribing to Task Events:
===========================

# In UserService
async def handle_task_completed(self, event: TaskCompleted) -> None:
    '''Invalidate user context when task completed.'''
    try:
        await self.invalidate_context(event.user_uid)
        self.logger.info(f"Context invalidated for user {event.user_uid}")
    except Exception as e:  # intentional-broad: event handler must not propagate
        self.logger.error(f"Error handling task.completed: {e}")


# In GoalAnalyticsService
async def handle_task_completed(self, event: TaskCompleted) -> None:
    '''Update goal progress when related task completed.'''
    try:
        await self.update_goal_progress_for_task(event.task_uid)
        self.logger.info(f"Goal progress updated for task {event.task_uid}")
    except Exception as e:  # intentional-broad: event handler must not propagate
        self.logger.error(f"Error updating goal progress: {e}")


# In Bootstrap
event_bus.subscribe(TaskCompleted, user_service.handle_task_completed)
event_bus.subscribe(TaskCompleted, goal_analytics.handle_task_completed)
event_bus.subscribe(TaskCreated, analytics_engine.handle_task_created)
"""
