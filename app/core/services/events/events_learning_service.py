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

from datetime import date, datetime, time, timedelta
from typing import TYPE_CHECKING, Any

from core.events import publish_event
from core.models.enums import Domain, EntityStatus
from core.models.ku.event import Event
from core.models.ku.event_dto import EventDTO
from core.models.ku.ku_request import KuEventCreateRequest
from core.models.ku.lp_position import LpPosition
from core.ports import get_enum_value
from core.services.base_service import BaseService
from core.services.domain_config import create_activity_domain_config
from core.services.infrastructure.learning_alignment_helper import LearningAlignmentHelper
from core.utils.result_simplified import Result

if TYPE_CHECKING:
    from core.ports import BackendOperations
    from core.services.relationships import UnifiedRelationshipService


class EventsLearningService(BaseService["BackendOperations[Event]", Event]):
    """
    Learning integration service for events.

    Handles:
    - Learning path-aligned event scheduling
    - Knowledge unit reinforcement through events
    - Study session tracking
    - Learning progress through event completion


    Source Tag: "events_learning_service_explicit"
    - Format: "events_learning_service_explicit" for user-created relationships
    - Format: "events_learning_service_inferred" for system-generated relationships

    Confidence Scoring:
    - 0.9+: User explicitly defined relationship
    - 0.7-0.9: Inferred from events_learning metadata
    - 0.5-0.7: Suggested based on patterns
    - <0.5: Low confidence, needs verification

    SKUEL Architecture:
    - Uses CypherGenerator for ALL graph queries
    - No APOC calls (Phase 5 eliminated those)
    - Returns Result[T] for error handling
    - Logs operations with structured logging

    """

    # ========================================================================
    # DOMAIN-SPECIFIC CONFIGURATION (DomainConfig - January 2026)
    # ========================================================================

    _config = create_activity_domain_config(
        dto_class=EventDTO,
        model_class=Event,
        entity_label="Ku",
        domain_name="events",
        date_field="event_date",
        completed_statuses=(EntityStatus.COMPLETED.value,),
    )

    def __init__(
        self,
        backend: "BackendOperations[Event]",
        relationships: "UnifiedRelationshipService | None" = None,
        event_bus=None,
    ) -> None:
        """
        Initialize events learning service.

        Args:
            backend: Protocol-based backend for event operations
            relationships: UnifiedRelationshipService for graph queries (optional)
            event_bus: Event bus for publishing domain events (optional)

        Note:
            Context invalidation now happens via event-driven architecture.
            Calendar event operations trigger domain events which invalidate context.
        """
        super().__init__(backend, "events.learning")
        self.relationships = relationships
        self.event_bus = event_bus

        # Initialize LearningAlignmentHelper for Events (Phase 6)
        self.learning_helper = LearningAlignmentHelper[Event, EventDTO, KuEventCreateRequest](
            service=self,
            backend_get_method="get",
            backend_get_user_method="list_user_events",
            backend_create_method="create_event",
            dto_class=EventDTO,
            model_class=Event,
            domain=Domain.LEARNING,  # Events default to learning domain
            entity_name="event",
        )

    # ========================================================================
    # PRIVATE HELPER METHODS
    # ========================================================================

    async def _find_events_for_knowledge(
        self, knowledge_uid: str, user_uid: str
    ) -> Result[list[Event]]:
        """
        Find events that reinforce a knowledge unit for a specific user.

        Uses direct Cypher query (Direct Driver pattern) since this cross-domain
        reverse query doesn't map cleanly to UnifiedRelationshipService's generic API.

        Args:
            knowledge_uid: UID of the knowledge unit
            user_uid: UID of the user

        Returns:
            Result containing list of Events that reinforce the knowledge unit
        """
        from core.utils.neo4j_mapper import from_neo4j_node

        query = """
        MATCH (e:Ku)-[:APPLIES_KNOWLEDGE|REINFORCES_KNOWLEDGE]->(ku:Ku {uid: $knowledge_uid})
        WHERE e.user_uid = $user_uid
        RETURN e
        """
        result = await self.backend.execute_query(
            query, {"knowledge_uid": knowledge_uid, "user_uid": user_uid}
        )
        if result.is_error:
            return Result.fail(result.expect_error())

        events = [from_neo4j_node(record["e"], Event) for record in result.value]
        return Result.ok(events)

    # ========================================================================
    # DOMAIN-SPECIFIC CONTRACT
    # ========================================================================

    @property
    def entity_label(self) -> str:
        """Return the graph label for Ku entities."""
        return "Ku"

    # ========================================================================
    # LEARNING-RELATED EVENT QUERIES
    # ========================================================================

    async def get_learning_events(
        self, user_uid: str, days_ahead: int = 7
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

        filters = {
            "user_uid": user_uid,
            "event_date__gte": date.today(),
            "event_date__lte": end_date,
        }

        result = await self.backend.list(filters=filters)
        if result.is_error:
            return Result.fail(result.expect_error())

        # Unpack tuple: backend.list() returns (events, total_count)
        events, _ = result.value

        # Filter for learning events
        # GRAPH-NATIVE: Use existing event fields instead of removed relationship fields
        # - knowledge_retention_check: Boolean flag for knowledge practice events
        # - source_learning_path_uid: Learning path association
        learning_events = [
            event
            for event in events
            if event.knowledge_retention_check or event.source_learning_path_uid
        ]

        return Result.ok(learning_events)

    async def get_events_for_knowledge(
        self, knowledge_uid: str, user_uid: str, days_ahead: int = 30
    ) -> Result[list[Event]]:
        """
        Get events that reinforce a specific knowledge unit.

        Args:
            knowledge_uid: UID of the knowledge unit,
            user_uid: UID of the user,
            days_ahead: Number of days to look ahead

        Returns:
            Result containing list of events
        """
        end_date = date.today() + timedelta(days=days_ahead)

        filters = {
            "user_uid": user_uid,
            "event_date__gte": date.today(),
            "event_date__lte": end_date,
        }

        # GRAPH-NATIVE: Query events via knowledge relationship
        # Use direct Cypher query to find events that practice this knowledge unit
        events_result = await self._find_events_for_knowledge(knowledge_uid, user_uid)
        if events_result.is_error:
            # Fallback: return all events (caller can filter if needed)
            result = await self.backend.list(filters=filters)
            if result.is_error:
                return Result.fail(result.expect_error())
            events, _ = result.value
            return Result.ok(events)

        # Filter by date range
        knowledge_events = [
            event
            for event in events_result.value
            if event.event_date and date.today() <= event.event_date <= end_date
        ]

        return Result.ok(knowledge_events)

    async def get_events_for_learning_path(
        self, learning_path_uid: str, user_uid: str
    ) -> Result[list[Event]]:
        """
        Get all events associated with a learning path.

        Args:
            learning_path_uid: UID of the learning path,
            user_uid: UID of the user

        Returns:
            Result containing list of events
        """
        filters = {"user_uid": user_uid, "learning_path_uid": learning_path_uid}

        result = await self.backend.list(filters=filters)
        if result.is_error:
            return Result.fail(result.expect_error())

        # Unpack tuple: backend.list() returns (events, total_count)
        events, _ = result.value
        return Result.ok(events)

    # ========================================================================
    # LEARNING-ALIGNED EVENT CREATION
    # ========================================================================

    async def create_study_session(
        self,
        user_uid: str,
        knowledge_uids: list[str],
        event_date: date,
        duration_minutes: int = 60,
        title: str | None = None,
        learning_path_uid: str | None = None,
    ) -> Result[Event]:
        """
        Create a study session event for specific knowledge units.

        Uses LearningAlignmentHelper with custom fields for Events-specific data.

        Args:
            user_uid: UID of the user,
            knowledge_uids: List of knowledge unit UIDs to study,
            event_date: Date of the study session,
            duration_minutes: Duration in minutes,
            title: Optional custom title,
            learning_path_uid: Optional learning path UID

        Returns:
            Result containing created event
        """
        # Calculate start and end times from duration
        default_start = time(9, 0)  # 9:00 AM default
        start_datetime = datetime.combine(event_date, default_start)
        end_datetime = start_datetime + timedelta(minutes=duration_minutes)

        # Build KuEventCreateRequest with required time fields
        request = KuEventCreateRequest(
            title=title or f"Study Session: {len(knowledge_uids)} topics",
            event_date=event_date,
            start_time=default_start,
            end_time=end_datetime.time(),
            event_type="learning",
        )

        # Custom fields for Events domain (user_uid required for ownership)
        custom_fields: dict[str, Any] = {"user_uid": user_uid}
        if learning_path_uid:
            custom_fields["source_learning_path_uid"] = learning_path_uid

        # Create via helper (Phase 6 consolidation)
        result = await self.learning_helper.create_with_learning_alignment(
            request=request,
            learning_position=None,  # Not used for study sessions
            custom_fields=custom_fields or None,
        )

        if result.is_error:
            return result

        event = result.value

        # GRAPH-NATIVE: Create PRACTICES_KNOWLEDGE relationships
        # This pattern is consistent with Goals/Habits - caller handles relationships
        if knowledge_uids and self.relationships:
            from core.models.relationship_names import RelationshipName

            for ku_uid in knowledge_uids:
                await self.backend.add_relationship(
                    event.uid,
                    ku_uid,
                    RelationshipName.PRACTICES_KNOWLEDGE,
                )

        # Publish CalendarEventCreated event (event-driven architecture)
        from core.events import CalendarEventCreated

        event_obj = CalendarEventCreated(
            event_uid=event.uid,
            user_uid=user_uid,
            title=event.title,
            event_date=event.event_date,
            calendar_event_type=get_enum_value(event.event_type),
            occurred_at=datetime.now(),
        )
        await publish_event(self.event_bus, event_obj, self.logger)

        self.logger.info(
            f"Created study session for {len(knowledge_uids)} knowledge units on {event_date}"
        )

        return Result.ok(event)

    async def suggest_spaced_repetition_events(
        self,
        _user_uid: str,
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

    async def create_learning_path_schedule(
        self,
        user_uid: str,
        learning_path_uid: str,
        _learning_position: LpPosition,
        study_hours_per_week: int = 5,
    ) -> Result[list[Event]]:
        """
        Create a study schedule for a learning path.

        Uses LearningAlignmentHelper batch creation with custom fields.

        Args:
            user_uid: UID of the user,
            learning_path_uid: UID of the learning path,
            learning_position: Current position in learning path,
            study_hours_per_week: Target study hours per week

        Returns:
            Result containing list of created events
        """
        # Calculate sessions per week (assuming 1-hour sessions)
        sessions_per_week = study_hours_per_week

        # Build schedule dates and requests
        current_date = date.today()
        event_requests = []
        custom_fields_list = []

        for week in range(4):
            for session in range(sessions_per_week):
                # Space sessions throughout the week
                days_offset = week * 7 + (session * 7 // sessions_per_week)
                event_date_for_session = current_date + timedelta(days=days_offset)

                # Calculate start and end times (1-hour sessions)
                session_start = time(9, 0)  # 9:00 AM default
                start_dt = datetime.combine(event_date_for_session, session_start)
                end_dt = start_dt + timedelta(hours=1)

                # Build request with required time fields
                request = KuEventCreateRequest(
                    title=f"Learning Path Study - Week {week + 1}",
                    event_date=event_date_for_session,
                    start_time=session_start,
                    end_time=end_dt.time(),
                    event_type="learning",
                )

                custom_fields: dict[str, Any] = {
                    "user_uid": user_uid,
                    "source_learning_path_uid": learning_path_uid,
                }

                event_requests.append(request)
                custom_fields_list.append(custom_fields)

        # Create all events in batch via helper (Phase 6 consolidation)
        result = await self.learning_helper.create_batch_with_learning_alignment(
            requests=event_requests,
            custom_fields_per_request=custom_fields_list,
        )

        if result.is_error:
            return result

        events = result.value

        # Publish CalendarEventCreated events for each created event
        from core.events import CalendarEventCreated

        for event in events:
            event_obj = CalendarEventCreated(
                event_uid=event.uid,
                user_uid=user_uid,
                title=event.title,
                event_date=event.event_date,
                calendar_event_type=get_enum_value(event.event_type),
                occurred_at=datetime.now(),
            )
            await publish_event(self.event_bus, event_obj, self.logger)

        self.logger.info(
            f"Created {len(events)} study sessions for learning path {learning_path_uid}"
        )

        return Result.ok(events)

    # ========================================================================
    # LEARNING PROGRESS TRACKING
    # ========================================================================

    async def get_knowledge_reinforcement_stats(
        self, user_uid: str, knowledge_uid: str, days_back: int = 30
    ) -> Result[dict[str, Any]]:
        """
        Get statistics on how a knowledge unit has been reinforced through events.

        Args:
            user_uid: UID of the user,
            knowledge_uid: UID of the knowledge unit,
            days_back: Number of days to look back

        Returns:
            Result containing reinforcement statistics
        """
        start_date = date.today() - timedelta(days=days_back)

        # GRAPH-NATIVE: Query events via knowledge relationship
        # Use direct Cypher query to find events that practice this knowledge unit
        events_result = await self._find_events_for_knowledge(knowledge_uid, user_uid)
        if events_result.is_error:
            # Fallback: return empty stats if query failed
            stats = {
                "knowledge_uid": knowledge_uid,
                "total_events": 0,
                "completed_events": 0,
                "completion_rate": 0.0,
                "total_time_minutes": 0,
                "average_time_per_event": 0.0,
            }
            return Result.ok(stats)

        # Filter by date range
        events = [
            event
            for event in events_result.value
            if event.event_date and start_date <= event.event_date <= date.today()
        ]

        # Analyze reinforcement events
        total_events = len(events)
        completed_events = 0
        total_time_minutes = 0

        for event in events:
            if event.status == "completed":
                completed_events += 1
                total_time_minutes += event.duration_minutes or 0

        stats = {
            "knowledge_uid": knowledge_uid,
            "total_reinforcement_events": total_events,
            "completed_events": completed_events,
            "completion_rate": completed_events / total_events if total_events > 0 else 0.0,
            "total_study_time_minutes": total_time_minutes,
            "average_time_per_session": total_time_minutes / completed_events
            if completed_events > 0
            else 0.0,
            "days_analyzed": days_back,
        }

        return Result.ok(stats)
