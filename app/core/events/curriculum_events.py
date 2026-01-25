"""
Curriculum Domain Events (LS)
==============================

*Last updated: 2026-01-20*

Events published by curriculum services (LsService).

These events complement learning_events.py which covers KU and LP events.

Event Catalog:
- learning_step.created - Learning step created
- learning_step.updated - Learning step updated
- learning_step.deleted - Learning step deleted
- learning_step.completed - User completed a learning step

NOTE: MOC events (moc.created, moc.updated, moc.deleted) removed January 2026.
MOC is now KU-based - use KU events instead.

Subscribers:
- UserService (context invalidation)
- SearchService (index for discovery)
- LpService (update path progress when step completes)
- AnalyticsEngine (curriculum patterns)
"""

from dataclasses import dataclass, field
from datetime import datetime

from core.events.base import BaseEvent

# ============================================================================
# LEARNING STEP EVENTS
# ============================================================================


@dataclass(frozen=True)
class LearningStepCreated(BaseEvent):
    """
    Published when a new learning step is created.

    Subscribers:
    - SearchService (index for discovery)
    - LpService (update path structure if linked to LP)
    """

    ls_uid: str
    title: str
    occurred_at: datetime

    # Step context
    intent: str | None = None
    linked_lp_uid: str | None = None
    linked_ku_uids: tuple[str, ...] = field(default_factory=tuple)
    sequence_order: int | None = None

    @property
    def event_type(self) -> str:
        return "learning_step.created"


@dataclass(frozen=True)
class LearningStepUpdated(BaseEvent):
    """
    Published when a learning step is updated.

    Subscribers:
    - SearchService (update index)
    - LpService (update path if relevant)
    """

    ls_uid: str
    occurred_at: datetime

    # Update context
    updated_fields: tuple[str, ...] = field(default_factory=tuple)
    linked_lp_uid: str | None = None

    @property
    def event_type(self) -> str:
        return "learning_step.updated"


@dataclass(frozen=True)
class LearningStepDeleted(BaseEvent):
    """
    Published when a learning step is deleted.

    Subscribers:
    - SearchService (remove from index)
    - LpService (update path structure)
    """

    ls_uid: str
    occurred_at: datetime

    # Deletion context
    linked_lp_uid: str | None = None
    had_ku_links: bool = False

    @property
    def event_type(self) -> str:
        return "learning_step.deleted"


@dataclass(frozen=True)
class LearningStepCompleted(BaseEvent):
    """
    Published when a user completes a learning step.

    Subscribers:
    - UserService (invalidate context)
    - LpService (update path progress)
    - AchievementService (track milestone)
    """

    ls_uid: str
    user_uid: str
    occurred_at: datetime

    # Completion context
    linked_lp_uid: str | None = None
    sequence_order: int | None = None
    completion_score: float = 1.0  # 0.0 to 1.0

    @property
    def event_type(self) -> str:
        return "learning_step.completed"


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


# ============================================================================
# USAGE EXAMPLES
# ============================================================================

"""
Publishing Curriculum Events:
=============================

# In LsCoreService.create_step()
async def create_step(self, data: LsCreateRequest) -> Result[Ls]:
    '''Create a new learning step.'''

    result = await self.backend.create(data)

    if result.is_ok and self.event_bus:
        step = result.value
        event = LearningStepCreated(
            ls_uid=step.uid,
            title=step.title,
            occurred_at=datetime.now(),
            intent=step.intent,
            linked_lp_uid=step.lp_uid,
            sequence_order=step.sequence_order,
        )
        await self.event_bus.publish_async(event)

    return result


Bootstrap Wiring:
================

# In services_bootstrap.py
def _wire_event_subscribers(event_bus: EventBusOperations, services: Services):
    '''Wire curriculum event subscribers.'''

    # Learning step events → LP progress tracking
    event_bus.subscribe(LearningStepCompleted, services.lp.progress.handle_step_completed)

    logger.info("Curriculum event subscribers wired")

NOTE: MOC event examples removed January 2026 - MOC is now KU-based.
"""
