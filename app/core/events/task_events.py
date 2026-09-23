"""
Task Domain Events
==================

Events published by TasksService for task lifecycle operations.

The classes below are the catalog. For consumers read the wiring modules
(``services_bootstrap/_event_wiring.py``, ``_intelligence_hub.py``).
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

    **Every publisher is transition-gated.** ``TaskCompleted`` is published exactly
    when a write moved the task INTO completed, never on a re-post: the status
    chokepoint (``TasksCoreService.update_task`` — the one completion door; every
    complete control, Today's included, posts through it), the per-row fan-out from
    ``complete_tasks_bulk`` and the vault door's post-persist announcement
    (``UnifiedIngestionService._apply_status_transitions``, from the prior status the
    bulk upsert returns under the node's write-lock) all derive the verdict from the
    prior the write itself captured (ADR-087); the create door
    (``TasksCoreService._publish_born_completed``, for a task born ``completed`` — a
    DSL ``- [x]`` line or an API create carrying the status) has no prior status at
    all, so its publish is a transition by construction. Re-posting ``completed`` on
    a completed task writes nothing and announces nothing, which is why no subscriber
    carries a repeat gate: counting and appending subscribers (the duration EMA, the
    overdue and alignment insight appends, the Prometheus ``entities_completed{task}``
    counter, the productivity completion moment) count each genuine completion once,
    and recompute-shaped ones (goal progress, PS engagement auto-complete, dependent
    scheduling, knowledge generation, context invalidation) converge on their own.

    A task completed away from the app carries its own ``completion_date`` as
    ``occurred_at`` — the born-completed create door and the vault door both —
    which is why the stamps a subscriber keeps must be order-insensitive: a vault
    sync hands historical completions to the graph in file order, not
    chronological order.
    """

    task_uid: str
    user_uid: UserUID

    # Optional context for analytics
    completion_time_seconds: int | None = None
    was_overdue: bool = False

    event_type: ClassVar[str] = "task.completed"


@dataclass(frozen=True)
class TaskReopened(BaseEvent):
    """
    Published when a task moves back OUT of ``completed``.

    The mirror of :class:`TaskCompleted`, published from both places a task can
    leave ``completed``, each on a genuine transition only — re-posting a
    non-completed status on an already-open task publishes nothing, exactly as the
    completion side is transition-gated:

    - the update chokepoint, ``TasksCoreService.update_task``, from the prior status
      ``update_with_status_guard`` returned (ADR-087);
    - the vault ingest door, ``UnifiedIngestionService._apply_status_transitions``,
      from the prior status its bulk upsert returned — the same door that removes
      the reopened task's ``completion_date``.

    A new door that can move a task out of ``completed`` must publish it too, or its
    reopens are the half every subscriber never hears.

    A reopen is **not** a completion, so a subscriber must not treat it as one:
    it records no completion moment and must leave completion timestamps where
    they are.

    Subscribers:

    - ``UserService`` context invalidation — the vault door publishes no
      ``TaskUpdated``, so this is what refreshes a cached context after an Obsidian
      reopen.
    - ``GoalsProgressService.handle_task_reopened`` — recomputes the goals the task
      fulfills from their linked-task tally, lowering progress and un-achieving a
      goal that falls below 100%. The recompute reads graph state under the goal's
      lock, so the event is only its trigger: a missed or repeated one leaves the
      next recompute of that goal correct.

    Not subscribers (docs/roadmap/done/reopen-vault-surface.md):

    - ``ProductivityAnalytics`` — ``tasks_completed`` is derived at read from the
      tasks currently in ``completed``, so a reopen lowers it with no one listening.
    - The vault write-back (un-checking the Obsidian line and stripping its ``✅``
      date, ADR-070 Resolved Design Question 2, amended). Its trigger is the
      outbound sync pass's STATE predicate — "not completed AND the line is still
      marked done" — because a reopen is only knowable after the graph write has
      committed, and a failed vault write driven by this event would have no retry.
    """

    task_uid: str
    user_uid: UserUID

    event_type: ClassVar[str] = "task.reopened"


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
    - NotificationService (notify on an escalation to HIGH)
    - Analytics (track priority escalation patterns)
    """

    task_uid: str
    user_uid: UserUID
    old_priority: str
    new_priority: str

    event_type: ClassVar[str] = "task.priority_changed"


# ============================================================================
# TASK BATCH EVENTS
# ============================================================================


@dataclass(frozen=True)
class TasksBulkCompleted(BaseEvent):
    """
    Published when multiple tasks are completed in a batch operation.

    Published **alongside** the per-row ``TaskCompleted`` events, not instead of
    them. Every door to COMPLETED cascades (ruled 2026-08-22), so
    ``complete_tasks_bulk`` fans out one ``TaskCompleted`` for each row that
    actually transitioned — the efficiency argument for a batch-only event lost
    to the cascade being the point. What this event still carries is the thing
    per-row events cannot express: the shape of the *batch* (how many tasks, at
    what time of day), which the handler classifies into a completion pattern.

    A consumer that merely counts completions must read the per-row events, not
    this one, or it double-counts a bulk call.

    Subscribers:
    - TaskEventHandlerService (batch pattern classification)
    """

    task_uids: list[str]
    user_uid: UserUID
    count: int = 0  # Number of tasks completed

    def __post_init__(self) -> None:
        # Set count from task_uids length
        object.__setattr__(self, "count", len(self.task_uids))

    event_type: ClassVar[str] = "tasks.bulk_completed"
