"""
Choice Domain Events
====================

Events published when choice/decision-related operations occur.

These events enable:
- User context invalidation when choices change
- Decision pattern tracking
- Cross-domain reactions to decision updates
- Analytics and tracking of decision quality

Version: 1.0.0
Date: 2025-10-16
"""

from dataclasses import dataclass
from typing import Any, ClassVar

from core.events.base import BaseEvent
from core.models.type_hints import UserUID


@dataclass(frozen=True)
class ChoiceCreated(BaseEvent):
    """
    Published when a new choice/decision is created.

    Triggers:
    - User context invalidation (decision history changes)
    - Decision pattern analytics updates
    - Alignment assessment for principles/goals
    """

    choice_uid: str
    user_uid: UserUID
    choice_description: str
    domain: str
    urgency: str
    metadata: dict[str, Any] | None = None

    event_type: ClassVar[str] = "choice.created"


@dataclass(frozen=True)
class ChoiceUpdated(BaseEvent):
    """
    Published when a choice is updated.

    Triggers:
    - User context invalidation (decision details changed)
    - Decision quality recalculation
    - Learning pattern updates
    """

    choice_uid: str
    user_uid: UserUID
    updated_fields: dict[str, Any]
    metadata: dict[str, Any] | None = None

    event_type: ClassVar[str] = "choice.updated"


@dataclass(frozen=True)
class ChoiceDeleted(BaseEvent):
    """
    Published when a choice is deleted.

    Triggers:
    - User context invalidation (decision history changes)
    - Cleanup of choice relationships
    - Pattern recalculation
    """

    choice_uid: str
    user_uid: UserUID
    choice_description: str
    metadata: dict[str, Any] | None = None

    event_type: ClassVar[str] = "choice.deleted"


@dataclass(frozen=True)
class ChoiceMade(BaseEvent):
    """
    Published when a decision is finalized.

    Triggers:
    - User context invalidation (active decisions change)
    - Decision confidence tracking
    - Outcome prediction
    """

    choice_uid: str
    user_uid: UserUID
    selected_option: str
    confidence: float
    metadata: dict[str, Any] | None = None

    event_type: ClassVar[str] = "choice.made"


@dataclass(frozen=True)
class ChoiceOutcomeRecorded(BaseEvent):
    """
    Published when a choice outcome is recorded.

    Triggers:
    - Decision quality analytics
    - Learning from outcomes
    - Pattern improvement
    """

    choice_uid: str
    user_uid: UserUID
    outcome_quality: float
    lessons_learned: str | None
    metadata: dict[str, Any] | None = None

    event_type: ClassVar[str] = "choice.outcome_recorded"
