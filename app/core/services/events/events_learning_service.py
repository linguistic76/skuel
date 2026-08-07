"""
Events Learning Service
=======================

Handles learning and knowledge integration for events.

Responsibilities:
- Get events related to learning paths
- Get events reinforcing specific knowledge units
- Create learning-aligned events
- Track learning progress through events
"""

from datetime import date, timedelta
from typing import TYPE_CHECKING, Any

from core.models.enums import EntityStatus
from core.models.event.event import Event
from core.models.event.event_dto import EventDTO
from core.models.type_hints import FilterParams, UserUID
from core.services.base_service import BaseService
from core.services.domain_config import create_activity_domain_config
from core.utils.result_simplified import Result

if TYPE_CHECKING:
    from core.ports.domain_protocols import EventsOperations
    from core.services.relationships import UnifiedRelationshipService


class EventsLearningService(BaseService["EventsOperations", Event]):
    """
    Learning integration service for events.

    Handles:
    - Learning path-aligned event scheduling
    - Knowledge unit reinforcement through events
    - Study session tracking
    - Learning progress through event completion
    """

    # ========================================================================
    # DOMAIN-SPECIFIC CONFIGURATION (DomainConfig - January 2026)
    # ========================================================================

    _config = create_activity_domain_config(
        dto_class=EventDTO,
        model_class=Event,
        entity_label="Entity",
        domain_name="events",
        date_field="event_date",
        completed_statuses=(EntityStatus.COMPLETED.value,),
    )

    def __init__(
        self,
        backend: "EventsOperations",
        event_bus=None,
        relationship_service: "UnifiedRelationshipService | None" = None,
    ) -> None:
        """
        Initialize events learning service.

        Args:
            backend: Protocol-based backend for event operations
            event_bus: Event bus for publishing domain events (optional)
            relationship_service: UnifiedRelationshipService for graph queries (optional)

        Note:
            Context invalidation now happens via event-driven architecture.
            Calendar event operations trigger domain events which invalidate context.
        """
        super().__init__(backend, "events.learning")
        self.relationships = relationship_service
        self.event_bus = event_bus

    # ========================================================================
    # LEARNING-RELATED EVENT QUERIES
    # ========================================================================

    async def get_learning_events(
        self, user_uid: UserUID, days_ahead: int = 7
    ) -> Result[list[Event]]:
        """
        Get all upcoming learning-related events.

        Args:
            user_uid: UID of the user,
            days_ahead: Number of days to look ahead

        Returns:
            Result containing list of learning events
        """
        end_date = date.today() + timedelta(days=days_ahead)

        filters: FilterParams = {
            "user_uid": user_uid,
            "event_date__gte": date.today().isoformat(),
            "event_date__lte": end_date.isoformat(),
        }

        result = await self.backend.list(filters=filters)
        if result.is_error:
            return Result.fail(result)

        # Unpack tuple: backend.list() returns (events, total_count)
        events, _ = result.value

        # Filter for learning events
        # GRAPH-NATIVE: PS link is the curriculum-origin signal
        # (LP is reachable via (PS)-[:IS_STEP_OF]->(LP) traversal).
        learning_events = [
            event
            for event in events
            if event.knowledge_retention_check or event.source_path_step_uid
        ]

        return Result.ok(learning_events)

    # ========================================================================
    # LEARNING-ALIGNED EVENT CREATION
    # ========================================================================

    async def suggest_spaced_repetition_events(  # skuel-lint: disable=SKUEL029 -- facade-delegated: EventsService awaits this via delegation
        self,
        _user_uid: UserUID,
        knowledge_uid: str,
        mastery_level: float = 0.5,
        days_to_schedule: int = 30,
    ) -> Result[list[dict[str, Any]]]:
        """
        Suggest spaced repetition events for a knowledge unit.

        Uses spaced repetition algorithm based on mastery level:
        - Low mastery (< 0.3): Review every 1-2 days
        - Medium mastery (0.3-0.7): Review every 3-7 days
        - High mastery (> 0.7): Review every 14-30 days

        Args:
            user_uid: UID of the user,
            knowledge_uid: UID of the knowledge unit,
            mastery_level: Current mastery level (0.0-1.0),
            days_to_schedule: Number of days to schedule for

        Returns:
            Result containing list of suggested event templates
        """
        # Calculate review intervals based on mastery
        if mastery_level < 0.3:
            intervals = [1, 2, 3, 5, 7]  # Frequent reviews
        elif mastery_level < 0.7:
            intervals = [3, 7, 14, 21]  # Medium frequency
        else:
            intervals = [14, 30, 60]  # Infrequent reviews

        suggestions = []
        current_date = date.today()

        for interval in intervals:
            review_date = current_date + timedelta(days=interval)
            if (review_date - current_date).days > days_to_schedule:
                break

            suggestions.append(
                {
                    "title": f"Review: {knowledge_uid}",
                    "event_date": review_date,
                    "duration_minutes": 30,
                    "reinforces_knowledge_uids": [knowledge_uid],
                    "suggested_interval_days": interval,
                    "mastery_level": mastery_level,
                }
            )

        self.logger.info(
            f"Suggested {len(suggestions)} spaced repetition events for {knowledge_uid}"
        )

        return Result.ok(suggestions)
