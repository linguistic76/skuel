"""
Base Event Classes and Protocols
=================================

Foundation for all domain events in SKUEL.
Provides type-safe event structure and common functionality.

Design Principles:
- Immutable dataclasses (frozen=True)
- Past tense naming (what happened, not what will happen)
- Include all context needed by subscribers
- Timestamp all events for audit trail
"""

from abc import ABC
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, ClassVar, Protocol

# ============================================================================
# BASE EVENT PROTOCOL
# ============================================================================


class DomainEvent(Protocol):
    """
    Protocol for all domain events.

    Events are immutable records of things that happened in the system.
    They enable loose coupling between services via the event bus.
    """

    @property
    def event_type(self) -> str:
        """
        Unique identifier for this event type.

        Format: {domain}.{action} (lowercase, dot-separated)
        Examples: 'task.completed', 'goal.achieved', 'user.context_invalidated'
        """
        ...

    @property
    def occurred_at(self) -> datetime:
        """When this event occurred (for ordering and audit trail)."""
        ...

    def to_dict(self) -> dict[str, Any]:
        """Convert event to dictionary for serialization."""
        ...


# ============================================================================
# BASE EVENT IMPLEMENTATION
# ============================================================================


@dataclass(frozen=True)
class BaseEvent(ABC):
    """
    Abstract base class for all domain events.

    Provides common functionality like serialization and timestamp.
    All concrete events should inherit from this class.
    """

    # Declared, deliberately unassigned: the event type is a fact about the
    # CLASS, not the instance, which is what lets ``core.events`` derive
    # EVENT_REGISTRY by comprehension instead of hand-maintaining it. A bare
    # ClassVar annotation type-checks ``self.event_type`` below without
    # creating the attribute, so ``BaseEvent.event_type`` still raises.
    # ClassVar is excluded from dataclass fields, so frozen-ness, ``fields()``
    # and ``asdict()`` are all unaffected.
    event_type: ClassVar[str]

    occurred_at: datetime = field(default_factory=datetime.now, kw_only=True)

    def __init_subclass__(cls, **kwargs: object) -> None:
        """Enforce what ``@abstractmethod`` used to guarantee.

        Every event class must state its own ``event_type``; inheriting one
        silently would make two classes share a registry key and let the later
        import win. ``cls.__dict__`` (not ``hasattr``) is the check, because
        the point is *own* declaration, not reachability.

        ``kwargs`` is typed ``object``, not ``Any``: these are class-creation
        keywords that this hook only forwards to ``super()`` and never reads,
        so the weakest type that accepts them is the honest one.
        """
        super().__init_subclass__(**kwargs)
        if "event_type" not in cls.__dict__:
            raise TypeError(
                f"{cls.__name__} must declare its own "
                f'event_type: ClassVar[str] = "{{domain}}.{{action}}"'
            )

    def to_dict(self) -> dict[str, Any]:
        """
        Convert event to dictionary for serialization.

        Returns:
            Dictionary with all event fields plus event_type
        """
        from dataclasses import asdict

        data = asdict(self)
        data["event_type"] = self.event_type

        # Convert datetime objects to ISO format strings
        for key, value in data.items():
            if isinstance(value, datetime):
                data[key] = value.isoformat()

        return data

    def __str__(self) -> str:
        """Human-readable event representation."""
        return f"{self.event_type} at {self.occurred_at.isoformat()}"


# ============================================================================
# EVENT METADATA
# ============================================================================


@dataclass(frozen=True)
class EventMetadata:
    """
    Optional metadata for events.

    Useful for tracing, debugging, and analytics.
    """

    # Source of the event
    source: str | None = None  # e.g., "tasks_service", "goal_analytics"

    # Correlation ID for tracing related events
    correlation_id: str | None = None

    # User who triggered the event (if applicable)
    triggered_by: str | None = None

    # Additional context
    context: dict[str, Any] | None = None


# ============================================================================
# EVENT NAMING CONVENTIONS
# ============================================================================

"""
Event Naming Rules:
===================

1. Format: {domain}.{action}
   - domain: singular noun (task, goal, habit, user, learning_path)
   - action: past tense verb (created, completed, updated, deleted, achieved)

2. Lowercase with dot separator
   - ✅ "task.completed"
   - ❌ "TaskCompleted" or "task_completed"

3. Past tense (what happened)
   - ✅ "goal.achieved" (happened)
   - ❌ "goal.achieve" (command)

4. Specific when needed
   - ✅ "task.priority_changed" (specific)
   - ⚠️ "task.updated" (too general, use when multiple fields change)

5. Domain is singular
   - ✅ "task.completed"
   - ❌ "tasks.completed"

Examples:
---------
✅ Good:
  - task.created, task.completed, task.deleted
  - goal.achieved, goal.progress_updated, goal.abandoned
  - habit.completed, habit.streak_broken
  - user.context_invalidated, user.preferences_changed
  - learning_path.started, learning_path.completed

❌ Bad:
  - TaskCreated (class name, not event type string)
  - task_created (underscore instead of dot)
  - task.create (present tense, sounds like command)
  - tasks.completed (plural domain)
"""


# ============================================================================
# EXAMPLE USAGE
# ============================================================================

"""
Creating a New Event Type:
==========================

from dataclasses import dataclass
from datetime import datetime
from typing import ClassVar
from core.events.base import BaseEvent

@dataclass(frozen=True)
class TaskCompleted(BaseEvent):
    '''Published when a task is marked complete.'''

    event_type: ClassVar[str] = "task.completed"

    task_uid: str
    user_uid: UserUID
    completion_time_seconds: int | None = None

# Publishing (occurred_at auto-set to datetime.now()):
event = TaskCompleted(task_uid="task-123", user_uid="user-456")
await event_bus.publish_async(event)

# Or with explicit timestamp:
event = TaskCompleted(task_uid="task-123", user_uid="user-456", occurred_at=specific_time)

# Subscribing:
async def handle_task_completed(event: TaskCompleted) -> None:
    await invalidate_context(event.user_uid)

event_bus.subscribe(TaskCompleted, handle_task_completed)
"""
