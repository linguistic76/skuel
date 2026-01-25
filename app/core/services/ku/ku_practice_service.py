"""
Knowledge Practice Service
===========================

Handles knowledge practice tracking from event attendance.

Responsibilities:
- Track KU practice via event completion
- Update practice counts and timestamps
- Publish KnowledgePracticed events

Version: 1.0.0
Date: 2025-11-05
"""

from datetime import datetime
from typing import TYPE_CHECKING

from core.events import publish_event
from core.events.calendar_event_events import CalendarEventCompleted
from core.events.knowledge_events import KnowledgePracticed
from core.utils.logging import get_logger

if TYPE_CHECKING:
    from neo4j import AsyncDriver


class KuPracticeService:
    """
    Knowledge practice tracking service for event-driven updates.

    Handles automatic KU practice count updates when events are completed,
    eliminating direct dependencies between EventsService and KuService.

    Event-Driven Architecture (Phase 4):
    - Subscribes to CalendarEventCompleted events
    - Updates KU practice counts (times_practiced_in_events)
    - Updates last_practiced_date timestamps
    - Publishes KnowledgePracticed events


    Source Tag: "ku_practice_explicit"
    - Format: "ku_practice_explicit" for user-created relationships
    - Format: "ku_practice_inferred" for system-generated relationships

    Confidence Scoring:
    - 0.9+: User explicitly defined relationship
    - 0.7-0.9: Inferred from metadata
    - 0.5-0.7: Suggested based on patterns
    - <0.5: Low confidence, needs verification

    """

    def __init__(
        self,
        driver: "AsyncDriver | None" = None,
        event_bus=None,
    ) -> None:
        """
        Initialize knowledge practice service.

        Args:
            driver: Neo4j driver for Cypher queries (REQUIRED for Phase 4)
            event_bus: Optional event bus for publishing events
        """
        self.driver = driver
        self.event_bus = event_bus
        self.logger = get_logger("skuel.services.ku.practice")

    # ========================================================================
    # EVENT HANDLERS (Phase 4: Event-Driven Architecture)
    # ========================================================================

    async def handle_event_completed(self, event: CalendarEventCompleted) -> None:
        """
        Update KU practice counts when an event is completed.

        This handler implements event-driven KU practice tracking,
        eliminating direct dependency between EventsService and KuService.

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
            if not self.driver:
                self.logger.warning("No driver available for Event→KU practice tracking")
                return

            self.logger.debug(
                f"Querying for KUs practiced by event {event.event_uid}, user {event.user_uid}"
            )

            # Query Neo4j to find KUs that this event practices
            # Pattern: (Event)-[:PRACTICES]->(KnowledgeUnit)
            query = """
            MATCH (event:Event {uid: $event_uid})-[:PRACTICES]->(ku:Ku)
            RETURN DISTINCT ku.uid as ku_uid
            """

            async with self.driver.session() as session:
                result = await session.run(query, {"event_uid": event.event_uid})
                records = await result.data()

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
        if not self.driver:
            self.logger.warning("No driver available for KU practice tracking")
            return

        # Update KU practice fields directly in Neo4j
        # This is more efficient than fetching, modifying, and saving back
        query = """
        MATCH (ku:Ku {uid: $ku_uid})
        SET ku.times_practiced_in_events = COALESCE(ku.times_practiced_in_events, 0) + 1,
            ku.last_practiced_date = datetime($occurred_at)
        RETURN ku.times_practiced_in_events as new_count
        """

        async with self.driver.session() as session:
            result = await session.run(
                query, {"ku_uid": ku_uid, "occurred_at": occurred_at.isoformat()}
            )
            records = await result.data()

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
