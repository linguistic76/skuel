"""
Curriculum Events (PS)
==============================

Events published by curriculum services (PsService).

These events complement learning_events.py which covers KU and LP events.

NOTE: MOC events (moc.created, moc.updated, moc.deleted) removed January 2026.
MOC is now KU-based - use KU events instead.

The classes below are the catalog. For consumers read the wiring modules
(``services_bootstrap/_event_wiring.py``, ``_intelligence_hub.py``).
"""

from dataclasses import dataclass, field
from typing import ClassVar

from core.events.base import BaseEvent
from core.models.type_hints import UserUID

# ============================================================================
# LEARNING STEP EVENTS
# ============================================================================


@dataclass(frozen=True)
class PathStepCreated(BaseEvent):
    """
    Published when a new path step is created.

    Subscribers:
    - SearchService (index for discovery)
    - LpService (update path structure if linked to LP)
    """

    ps_uid: str
    title: str

    # Step context
    intent: str | None = None
    linked_lp_uid: str | None = None
    linked_ku_uids: tuple[str, ...] = field(default_factory=tuple)
    sequence_order: int | None = None

    event_type: ClassVar[str] = "path_step.created"


@dataclass(frozen=True)
class PathStepUpdated(BaseEvent):
    """
    Published when a path step is updated.

    Subscribers:
    - SearchService (update index)
    - LpService (update path if relevant)
    """

    ps_uid: str

    # Update context
    updated_fields: tuple[str, ...] = field(default_factory=tuple)
    linked_lp_uid: str | None = None

    event_type: ClassVar[str] = "path_step.updated"


@dataclass(frozen=True)
class PathStepDeleted(BaseEvent):
    """
    Published when a path step is deleted.

    Subscribers:
    - SearchService (remove from index)
    - LpService (update path structure)
    """

    ps_uid: str

    # Deletion context
    linked_lp_uid: str | None = None
    had_ku_links: bool = False

    event_type: ClassVar[str] = "path_step.deleted"


@dataclass(frozen=True)
class PathStepEnrolled(BaseEvent):
    """
    Published when a user marks a path step as IN_PROGRESS (enrols).

    Subscribers:
    - GroupService (auto-enrol student in admin's default group — ADR-040)
    """

    ps_uid: str
    user_uid: UserUID

    event_type: ClassVar[str] = "path_step.enrolled"


@dataclass(frozen=True)
class PathStepCompleted(BaseEvent):
    """
    Published when a user completes a path step.

    Subscribers:
    - UserService (invalidate context)
    - LpService (update path progress)
    - AchievementService (track milestone)
    """

    ps_uid: str
    user_uid: UserUID

    # Completion context
    linked_lp_uid: str | None = None
    sequence_order: int | None = None
    completion_score: float = 1.0  # 0.0 to 1.0

    event_type: ClassVar[str] = "path_step.completed"


# ============================================================================
# MAP OF CONTENT EVENTS - REMOVED JANUARY 2026
# ============================================================================
#
# MOC events (MapOfContentCreated, MapOfContentUpdated, MapOfContentDeleted)
# removed January 2026 - MOC is now KU-based.
#
# A KU "is" a MOC when it has outgoing ORGANIZES relationships to other KUs.
# MOC operations now use KU events (KnowledgeCreated, etc.) instead.
#
# See: /docs/domains/moc.md for full architecture documentation
