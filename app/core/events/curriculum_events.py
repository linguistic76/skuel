"""
Curriculum Events (PS)
==============================

Events about a learner's engagement with path steps. A path step is authored in
the content vault (ADR-091); its sync publishes no creation, update or deletion
event.

These events complement learning_events.py which covers KU and LP events.

NOTE: MOC events (moc.created, moc.updated, moc.deleted) removed January 2026.
MOC is now KU-based - use KU events instead.

The classes below are the catalog. For consumers read the wiring modules
(``services_bootstrap/_event_wiring.py``, ``_intelligence_hub.py``).
"""

from dataclasses import dataclass
from typing import ClassVar

from core.events.base import BaseEvent
from core.models.type_hints import UserUID

# ============================================================================
# LEARNING STEP EVENTS
# ============================================================================


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
