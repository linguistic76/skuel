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

Naming: ``{domain}.{action}``
-----------------------------
Lowercase, dot-separated, singular domain, past-tense action —
``task.completed``, not ``TaskCompleted`` / ``task_completed`` / ``task.complete``.
Prefer the specific action (``task.priority_changed``) over ``task.updated``, which
means "several fields moved at once".

The one sanctioned exception to the singular domain is a bulk event, where the plural
IS the meaning: ``tasks.bulk_completed`` and ``habits.bulk_completed`` are the only two.

Defining a new event
--------------------
::

    @dataclass(frozen=True)
    class TaskCompleted(BaseEvent):
        '''Published when a task is marked complete.'''

        event_type: ClassVar[str] = "task.completed"

        task_uid: str
        user_uid: UserUID
        completion_time_seconds: int | None = None

``event_type`` must be a ``ClassVar``, never a ``@property`` — it is a fact about the
class, and that is what lets ``EVENT_REGISTRY`` be derived by comprehension instead of
hand-maintained. ``BaseEvent.__init_subclass__`` rejects a subclass that does not
declare its own.

⚠ A new ``core/events/*_events.py`` module MUST be imported in ``core/events/__init__.py``.
The registry is derived, and a comprehension cannot see what nobody imports;
``tests/unit/test_event_registry_derivation.py`` fails when it is missed.

Publishing and subscribing
--------------------------
::

    # occurred_at defaults to datetime.now() — never pass it except in tests/replay
    await publish_event(
        self.event_bus, TaskCompleted(task_uid=uid, user_uid=user_uid), self.logger
    )

    event_bus.subscribe(TaskCompleted, service.handle_task_completed)

``list_event_types()`` is the live catalog. ``services_bootstrap/_event_wiring.py`` is
the one place subscriptions are wired — no per-domain table is kept here, because a
hand-maintained list of publishers and subscribers drifts silently and nothing greps it.
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
