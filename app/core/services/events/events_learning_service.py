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
from core.models.event.event import Event
from core.models.event.event_dto import EventDTO
from core.models.event.event_request import EventCreateRequest, EventType
from core.models.pathways.lp_position import LpPosition
from core.models.type_hints import FilterParams, UserUID
from core.services.base_service import BaseService
from core.services.domain_config import create_activity_domain_config
from core.services.infrastructure.learning_alignment_bridge import LearningAlignmentBridge
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

        # Initialize LearningAlignmentBridge for Events
        self.learning_helper = LearningAlignmentBridge[Event, EventDTO, EventCreateRequest](
            service=self,
            backend_get=self.backend.get,
            backend_get_user=self.backend.get_user_events,
            backend_create=self.backend.create_event,
            domain=Domain.LEARNING,
            entity_name="event",
        )

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

    async def create_study_session(
        self,
        user_uid: UserUID,
        knowledge_uids: list[str],
        event_date: date,
        duration_minutes: int = 60,
        title: str | None = None,
    ) -> Result[Event]:
        """
        Create a study session event for specific knowledge units.

        Uses LearningAlignmentBridge with custom fields for Events-specific data.

        Args:
            user_uid: UID of the user,
            knowledge_uids: List of knowledge unit UIDs to study,
            event_date: Date of the study session,
            duration_minutes: Duration in minutes,
            title: Optional custom title

        Returns:
            Result containing created event
        """
        # Calculate start and end times from duration
        default_start = time(9, 0)  # 9:00 AM default
        start_datetime = datetime.combine(event_date, default_start)
        end_datetime = start_datetime + timedelta(minutes=duration_minutes)

        # Build EventCreateRequest with required time fields
        request = EventCreateRequest(
            title=title or f"Study Session: {len(knowledge_uids)} topics",
            event_date=event_date,
            start_time=default_start,
            end_time=end_datetime.time(),
            # EventType.LEARNING, not "learning": EventAdapter.get_activity_type
            # and get_icon compare against the canonical UPPERCASE members, so a
            # lowercase spelling silently falls through to ActivityType.EVENT.
            event_type=EventType.LEARNING,
        )

        # Custom fields for Events domain (user_uid required for ownership)
        custom_fields: dict[str, Any] = {"user_uid": user_uid}

        # Create via helper (consolidation)
        result = await self.learning_helper.create_with_learning_alignment(
            request=request,
            learning_position=None,  # Not used for study sessions
            custom_fields=custom_fields or None,
        )

        if result.is_error:
            return result

        event = result.value

        # GRAPH-NATIVE: Create APPLIES_KNOWLEDGE relationships — the single
        # event→knowledge edge (matches EVENTS_CONFIG, the MEGA-QUERY, and the
        # link_event_to_knowledge facade). Consistent with Goals/Habits: caller
        # handles relationships.
        if knowledge_uids and self.relationships:
            from core.models.relationship_names import RelationshipName

            for ku_uid in knowledge_uids:
                await self.backend.add_relationship(
                    event.uid,
                    ku_uid,
                    RelationshipName.APPLIES_KNOWLEDGE,
                )

        # Publish CalendarEventCreated event (event-driven architecture)
        from core.events import CalendarEventCreated

        event_obj = CalendarEventCreated(
            event_uid=event.uid,
            user_uid=user_uid,
            title=event.title,
            event_date=event_date,
            # Event.event_type is str | None; the request above sets it
            calendar_event_type=event.event_type or EventType.LEARNING,
        )
        await publish_event(self.event_bus, event_obj, self.logger)

        self.logger.info(
            f"Created study session for {len(knowledge_uids)} knowledge units on {event_date}"
        )

        return Result.ok(event)

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

    async def create_learning_path_schedule(
        self,
        user_uid: UserUID,
        learning_path_uid: str,
        _learning_position: LpPosition,
        study_hours_per_week: int = 5,
    ) -> Result[list[Event]]:
        """
        Create a study schedule for a learning path.

        Uses LearningAlignmentBridge batch creation with custom fields.

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
                request = EventCreateRequest(
                    title=f"Learning Path Study - Week {week + 1}",
                    event_date=event_date_for_session,
                    start_time=session_start,
                    end_time=end_dt.time(),
                    event_type=EventType.LEARNING,  # canonical member — see create_study_session
                )

                custom_fields: dict[str, Any] = {"user_uid": user_uid}

                event_requests.append(request)
                custom_fields_list.append(custom_fields)

        # Create all events in batch via helper (consolidation)
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
            if event.event_date is None:
                self.logger.warning(
                    f"Created study session {event.uid} has no event_date; "
                    "skipping calendar notification"
                )
                continue
            event_obj = CalendarEventCreated(
                event_uid=event.uid,
                user_uid=user_uid,
                title=event.title,
                event_date=event.event_date,
                # Event.event_type is str | None; the requests above set it
                calendar_event_type=event.event_type or EventType.LEARNING,
            )
            await publish_event(self.event_bus, event_obj, self.logger)

        self.logger.info(
            f"Created {len(events)} study sessions for learning path {learning_path_uid}"
        )

        return Result.ok(events)
