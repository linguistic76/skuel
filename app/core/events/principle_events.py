"""
Principle Domain Events
=======================

Events published when principle-related operations occur.

These events enable:
- User context invalidation when principles change
- Audit trail of principle modifications
- Cross-domain reactions to principle updates
- Analytics and tracking of principle evolution

Version: 1.0.0
Date: 2025-10-16
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from core.events.base import BaseEvent


@dataclass(frozen=True)
class PrincipleCreated(BaseEvent):
    """
    Published when a new principle is created.

    Triggers:
    - User context invalidation (principle portfolio changes)
    - Principle analytics updates
    - Alignment recalculation for goals/habits
    """

    principle_uid: str
    user_uid: str
    principle_label: str
    category: str
    strength: str
    occurred_at: datetime
    metadata: dict[str, Any] | None = None

    @property
    def event_type(self) -> str:
        return "principle.created"


@dataclass(frozen=True)
class PrincipleUpdated(BaseEvent):
    """
    Published when a principle is updated.

    Triggers:
    - User context invalidation (principle details changed)
    - Alignment recalculation (if strength or category changed)
    - Integrity score updates
    """

    principle_uid: str
    user_uid: str
    updated_fields: dict[str, Any]
    occurred_at: datetime
    metadata: dict[str, Any] | None = None

    @property
    def event_type(self) -> str:
        return "principle.updated"


@dataclass(frozen=True)
class PrincipleDeleted(BaseEvent):
    """
    Published when a principle is deleted.

    Triggers:
    - User context invalidation (principle portfolio changes)
    - Cleanup of principle relationships
    - Alignment recalculation for affected entities
    """

    principle_uid: str
    user_uid: str
    principle_label: str
    occurred_at: datetime
    metadata: dict[str, Any] | None = None

    @property
    def event_type(self) -> str:
        return "principle.deleted"


@dataclass(frozen=True)
class PrincipleStrengthChanged(BaseEvent):
    """
    Published when a principle's strength changes.

    Triggers:
    - User context invalidation (core vs. aspirational change)
    - Motivational profile recalculation
    - Priority adjustments for aligned goals/habits
    """

    principle_uid: str
    user_uid: str
    old_strength: str
    new_strength: str
    occurred_at: datetime
    metadata: dict[str, Any] | None = None

    @property
    def event_type(self) -> str:
        return "principle.strength_changed"


@dataclass(frozen=True)
class PrincipleAlignmentAssessed(BaseEvent):
    """
    Published when principle alignment is assessed for an entity.

    Triggers:
    - Alignment score caching
    - Analytics tracking
    - Integrity score updates
    """

    principle_uid: str
    entity_uid: str
    entity_type: str  # "goal" or "habit"
    user_uid: str
    alignment_score: float
    occurred_at: datetime
    metadata: dict[str, Any] | None = None

    @property
    def event_type(self) -> str:
        return "principle.alignment_assessed"


@dataclass(frozen=True)
class PrincipleReflectionRecorded(BaseEvent):
    """
    Published when a user records a reflection on a principle.

    Triggers:
    - User context invalidation (principle alignment history changes)
    - Alignment trend recalculation
    - Integrity score updates
    - Cross-domain insight generation (if triggered by goal/habit/event/choice)
    """

    reflection_uid: str
    principle_uid: str
    user_uid: str
    alignment_level: str  # AlignmentLevel.value
    evidence: str
    occurred_at: datetime
    trigger_type: str | None = None  # "goal", "habit", "event", "choice", "manual"
    trigger_uid: str | None = None
    reflection_quality_score: float = 0.0
    metadata: dict[str, Any] | None = None

    @property
    def event_type(self) -> str:
        return "principle.reflection_recorded"


@dataclass(frozen=True)
class PrincipleConflictRevealed(BaseEvent):
    """
    Published when a reflection reveals a conflict between principles.

    This occurs when reflecting on one principle highlights tension with another.
    For example, reflecting on "Family First" during a work deadline might reveal
    conflict with "Excellence at Work".

    Triggers:
    - Conflict relationship creation in graph
    - User notification of principle tension
    - Integrity analysis updates
    - Guidance generation for resolution
    """

    reflection_uid: str
    principle_uid: str
    conflicting_principle_uid: str
    user_uid: str
    occurred_at: datetime
    conflict_context: str | None = None  # Description of the conflict
    metadata: dict[str, Any] | None = None

    @property
    def event_type(self) -> str:
        return "principle.conflict_revealed"
