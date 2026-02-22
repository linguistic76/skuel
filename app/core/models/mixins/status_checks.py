"""
Status Checks Mixin
====================

Generic mixin providing common status check methods for Activity domain models.

This mixin consolidates repetitive status check patterns across Task, Goal, Habit,
Event, and Choice models. Each domain configures which status enum values map to
which semantic states (completed, cancelled, active, terminal).

Usage:
    from core.models.mixins import StatusChecksMixin
    from core.models.enums import EntityStatus

    @dataclass(frozen=True)
    class Task(StatusChecksMixin):
        status: EntityStatus = EntityStatus.DRAFT

        # Configure status mappings
        _completed_statuses: ClassVar[tuple[EntityStatus, ...]] = (EntityStatus.COMPLETED,)
        _cancelled_statuses: ClassVar[tuple[EntityStatus, ...]] = (EntityStatus.CANCELLED,)
        _terminal_statuses: ClassVar[tuple[EntityStatus, ...]] = (
            EntityStatus.COMPLETED,
            EntityStatus.CANCELLED,
        )
        _active_statuses: ClassVar[tuple[EntityStatus, ...]] = (
            EntityStatus.ACTIVE,
            EntityStatus.PAUSED,
            EntityStatus.BLOCKED,
            EntityStatus.SCHEDULED,
            EntityStatus.DRAFT,
        )

Note:
    Domain-specific status checks (is_overdue, is_on_track, is_decided) remain
    in their respective domain models because they require domain-specific fields.

See: /docs/patterns/three_tier_type_system.md
"""

from typing import Any, ClassVar


class StatusChecksMixin:
    """
    Mixin providing common status check methods.

    Subclasses must:
    1. Have a `status` attribute
    2. Define class variables for status mappings:
       - _completed_statuses: tuple of enum values representing completion
       - _cancelled_statuses: tuple of enum values representing cancellation
       - _terminal_statuses: tuple of enum values representing terminal states
       - _active_statuses: tuple of enum values representing active (workable) states

    Methods provided:
    - is_completed(): True if status in _completed_statuses
    - is_cancelled(): True if status in _cancelled_statuses
    - is_terminal(): True if status in _terminal_statuses
    - is_active_status(): True if status in _active_statuses
    """

    # Class variables to be overridden by subclasses
    # Using Any to avoid generic complexity - actual types are the domain's status enum
    _completed_statuses: ClassVar[tuple[Any, ...]] = ()
    _cancelled_statuses: ClassVar[tuple[Any, ...]] = ()
    _terminal_statuses: ClassVar[tuple[Any, ...]] = ()
    _active_statuses: ClassVar[tuple[Any, ...]] = ()

    # Attribute that subclasses must have
    status: Any

    def is_completed(self) -> bool:
        """
        Check if entity is in a completed state.

        Returns:
            True if status is in _completed_statuses
        """
        return self.status in self._completed_statuses

    def is_cancelled(self) -> bool:
        """
        Check if entity is in a cancelled state.

        Returns:
            True if status is in _cancelled_statuses
        """
        return self.status in self._cancelled_statuses

    def is_terminal(self) -> bool:
        """
        Check if entity is in a terminal state (cannot transition further).

        Terminal states are typically completed or cancelled.

        Returns:
            True if status is in _terminal_statuses
        """
        return self.status in self._terminal_statuses

    def is_active_status(self) -> bool:
        """
        Check if entity is in an active (workable) state.

        Active states are those where work can progress.
        Note: Named is_active_status() to avoid collision with existing is_active() methods.

        Returns:
            True if status is in _active_statuses
        """
        return self.status in self._active_statuses


__all__ = ["StatusChecksMixin"]
