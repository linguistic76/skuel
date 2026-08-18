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
from typing import Any, ClassVar

from core.events.base import BaseEvent
from core.models.enums.principle_enums import TriggerType
from core.models.type_hints import EntityUID, UserUID


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
    user_uid: UserUID
    principle_label: str
    category: str
    strength: str
    metadata: dict[str, Any] | None = None

    event_type: ClassVar[str] = "principle.created"


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
    user_uid: UserUID
    updated_fields: dict[str, Any]
    metadata: dict[str, Any] | None = None

    event_type: ClassVar[str] = "principle.updated"


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
    user_uid: UserUID
    principle_label: str
    metadata: dict[str, Any] | None = None

    event_type: ClassVar[str] = "principle.deleted"


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
    user_uid: UserUID
    old_strength: str
    new_strength: str
    metadata: dict[str, Any] | None = None

    event_type: ClassVar[str] = "principle.strength_changed"


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
    entity_uid: EntityUID
    entity_type: str  # "goal" or "habit"
    user_uid: UserUID
    alignment_score: float
    metadata: dict[str, Any] | None = None

    event_type: ClassVar[str] = "principle.alignment_assessed"


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
    user_uid: UserUID
    alignment_level: str  # AlignmentLevel.value
    evidence: str
    trigger_type: TriggerType | None = None
    trigger_uid: str | None = None
    reflection_quality_score: float = 0.0
    metadata: dict[str, Any] | None = None

    event_type: ClassVar[str] = "principle.reflection_recorded"


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
    user_uid: UserUID
    conflict_context: str | None = None  # Description of the conflict
    metadata: dict[str, Any] | None = None

    event_type: ClassVar[str] = "principle.conflict_revealed"
