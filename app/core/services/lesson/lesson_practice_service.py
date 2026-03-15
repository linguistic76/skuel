"""
Knowledge Practice Service
===========================

Handles knowledge practice tracking from event attendance.

Responsibilities:
- Track KU practice via event completion
- Update practice counts and timestamps
- Publish KnowledgePracticed events
"""

from datetime import datetime
from typing import TYPE_CHECKING, Any

from core.events import publish_event
from core.events.calendar_event_events import CalendarEventCompleted
from core.events.lesson_events import KnowledgePracticed
from core.utils.logging import get_logger

if TYPE_CHECKING:
    from core.ports import BackendOperations


class LessonPracticeService:
    """
    Knowledge practice tracking service for event-driven updates.

    Handles automatic KU practice count updates when events are completed,
    eliminating direct dependencies between EventsService and LessonService.

    Event-Driven Architecture:
    - Subscribes to CalendarEventCompleted events
    - Updates KU practice counts (times_practiced_in_events)
    - Updates last_practiced_date timestamps
    - Publishes KnowledgePracticed events
    """

    def __init__(
        self,
        backend: "BackendOperations[Any] | None" = None,
        event_bus=None,
    ) -> None:
        """
        Initialize knowledge practice service.

        Args:
            backend: BackendOperations for Cypher queries
            event_bus: Optional event bus for publishing events
        """
        self.backend = backend
        self.event_bus = event_bus
        self.logger = get_logger("skuel.services.lesson.practice")

    # ========================================================================
    # EVENT HANDLERS
    # ========================================================================

    async def handle_event_completed(self, event: CalendarEventCompleted) -> None:
        """
        Update KU practice counts when an event is completed.

        This handler implements event-driven KU practice tracking,
        eliminating direct dependency between EventsService and LessonService.

        When an event is completed:
        1. Find all KUs that this event practices
        2. For each KU:
           - Increment times_practiced_in_events
           - Update last_practiced_date
           - Update KU in database
           - Publish KnowledgePracticed event

        Args:
            event: CalendarEventCompleted event containing event_uid and user_uid

        Note:
            Errors are logged but not raised - practice updates are best-effort
            to prevent event completion from failing if KU update fails.
        """
        try:
            if not self.backend:
                self.logger.warning("No backend available for Event→KU practice tracking")
                return

            self.logger.debug(
                f"Querying for KUs practiced by event {event.event_uid}, user {event.user_uid}"
            )

            # Query Neo4j to find KUs that this event practices
            # Pattern: (Event)-[:PRACTICES]->(KnowledgeUnit)
            query = """
            MATCH (event:Event {uid: $event_uid})-[:PRACTICES]->(ku:Entity)
            RETURN DISTINCT ku.uid as ku_uid
            """

            result = await self.backend.execute_query(query, {"event_uid": event.event_uid})

            if result.is_error:
                self.logger.error(
                    f"Failed to query KUs for event {event.event_uid}: {result.error}"
                )
                return

            records = result.value or []

            self.logger.debug(f"Found {len(records)} KUs practiced by event: {records}")
            ku_uids = [record["ku_uid"] for record in records]

            if not ku_uids:
                self.logger.debug(f"Event {event.event_uid} practices no KUs")
                return

            # Update each practiced KU
            for ku_uid in ku_uids:
                try:
                    await self._update_ku_practice_count(
                        ku_uid=ku_uid,
                        user_uid=event.user_uid,
                        event_uid=event.event_uid,
                        occurred_at=event.occurred_at,
                    )
                except Exception as e:
                    # Best-effort: Don't let one KU failure block others
                    self.logger.error(f"Failed to update KU {ku_uid} practice count: {e}")

        except Exception as e:
            # Best-effort: Log error but don't raise (prevent event completion failure)
            self.logger.error(f"Error handling event_completed event: {e}")

    async def _update_ku_practice_count(
        self, ku_uid: str, user_uid: str, event_uid: str, occurred_at: datetime
    ) -> None:
        """
        Internal helper to update a single KU's practice count.

        Updates:
        - times_practiced_in_events (increment by 1)
        - last_practiced_date (set to occurred_at)

        Args:
            ku_uid: Knowledge unit to update
            user_uid: User who completed the event
            event_uid: Event that was completed
            occurred_at: When the event was completed
        """
        if not self.backend:
            self.logger.warning("No backend available for KU practice tracking")
            return

        # Update KU practice fields directly in Neo4j
        # This is more efficient than fetching, modifying, and saving back
        query = """
        MATCH (ku:Entity {uid: $ku_uid})
        SET ku.times_practiced_in_events = COALESCE(ku.times_practiced_in_events, 0) + 1,
            ku.last_practiced_date = datetime($occurred_at)
        RETURN ku.times_practiced_in_events as new_count
        """

        result = await self.backend.execute_query(
            query, {"ku_uid": ku_uid, "occurred_at": occurred_at.isoformat()}
        )

        if result.is_error:
            self.logger.warning(f"Failed to update KU {ku_uid} practice count: {result.error}")
            return

        records = result.value or []

        if not records:
            self.logger.warning(f"KU {ku_uid} not found during practice update")
            return

        new_count = records[0].get("new_count", 0)

        self.logger.info(
            f"Updated KU {ku_uid} practice count: now {new_count} practices "
            f"(event {event_uid}, user {user_uid})"
        )

        # Publish KnowledgePracticed event
        practice_event = KnowledgePracticed(
            ku_uid=ku_uid,
            user_uid=user_uid,
            occurred_at=occurred_at,
            practice_context="event_completion",
            event_uid=event_uid,
            times_practiced=new_count,
        )
        await publish_event(self.event_bus, practice_event, self.logger)
