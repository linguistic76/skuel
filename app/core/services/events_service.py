"""
Enhanced Events Service - Facade Pattern
==========================================

Events service facade that delegates to specialized sub-services.

Sub-Services:
- EventsCoreService: CRUD operations
- EventsSearchService: Search and discovery (DomainSearchOperations[Event] protocol)
- EventsHabitIntegrationService: Cross-domain habits integration
- EventsLearningService: Learning path integration
- UnifiedRelationshipService (EVENTS_CONFIG): Graph relationships and semantic connections
- EventsIntelligenceService: Pure Cypher analytics
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from core.events import publish_event
from core.events.calendar_event_events import EventAttendeeAdded, EventAttendeeRemoved
from core.models.enums import EntityStatus, RecurrencePattern
from core.models.event.event import Event
from core.models.event.event_dto import EventDTO
from core.ports import get_enum_value
from core.ports.query_types import EventUpdatePayload
from core.services.base_service import BaseService
from core.services.domain_config import create_activity_domain_config

# Import sub-services
from core.services.events import (
    EventsCoreService,
    EventsHabitIntegrationService,
    EventsIntelligenceService,
    EventsLearningService,
    EventsProgressService,
    EventsSchedulingService,
    EventsSearchService,
)
from core.services.events.events_ai_service import EventsAIService
from core.services.infrastructure.graph_intelligence_service import GraphIntelligenceService

# Unified relationship service (replaces EventsRelationshipService)
from core.services.relationships import UnifiedRelationshipService
from core.utils.activity_domain_config import CommonSubServices, create_common_sub_services
from core.utils.logging import get_logger
from core.utils.result_simplified import Errors, Result

if TYPE_CHECKING:
    from datetime import date

    from core.infrastructure.relationships.semantic_relationships import SemanticRelationshipType
    from core.models.event.event_request import (
        AddAttendeeRequest,
        CheckConflictsRequest,
        EventCreateRequest,
        EventStatusUpdateRequest,
        GetRecurringEventsRequest,
        RecurringInstancesRequest,
        RemoveAttendeeRequest,
    )
    from core.ports import BackendOperations
    from core.ports.infrastructure_protocols import EventBusOperations
    from core.ports.search_protocols import EventsSearchOperations
    from core.services.events.events_intelligence_service import EventsIntelligenceService
    from core.services.user import UserContext


class EventsService(BaseService["BackendOperations[Event]", Event]):
    """
    Events service facade with specialized sub-services.

    This facade:
    1. Delegates to 6 specialized sub-services for core operations
    2. Uses explicit delegation methods (~50 methods) for sub-service access
    3. Retains explicit methods for complex cross-service orchestration
    4. Provides clean separation of concerns

    Delegations (explicit methods):
    - Core CRUD: get_event, get_user_events, find_events, count_events
    - Habits: get_events_for_habit, get_habit_reinforcement_events, etc.
    - Learning: get_learning_events, create_study_session, etc.
    - Search: search_events, get_calendar_events, get_event_history, etc.
    - Intelligence: get_event_with_context, analyze_event_performance, etc.

    Explicit Methods (custom logic):
    - Status management: update_event_status, start_event, complete_event, cancel_event
    - Relationships: link_event_to_knowledge, create_semantic_knowledge_relationship
    - Attendees: add_attendee, remove_attendee
    - Recurring: create_recurring_instances
    - Orchestration: create_event_with_context

    Source Tag: "events_service_explicit"
    - Format: "events_service_explicit" for user-created relationships
    - Format: "events_service_inferred" for system-generated relationships

    Confidence Scoring:
    - 0.9+: User explicitly defined relationship
    - 0.7-0.9: Inferred from events metadata
    - 0.5-0.7: Suggested based on patterns
    - <0.5: Low confidence, needs verification

    SKUEL Architecture:
    - Uses CypherGenerator for ALL graph queries
    - Uses explicit delegation methods (February 2026)
    - No APOC calls (Phase 5 eliminated those)
    - Returns Result[T] for error handling
    - Logs operations with structured logging
    """

    # ========================================================================
    # DOMAIN CONFIGURATION (DomainConfig - January 2026)
    # ========================================================================
    # Facade services use same config as core/search sub-services
    _config = create_activity_domain_config(
        dto_class=EventDTO,
        model_class=Event,
        entity_label="Entity",
        domain_name="events",
        date_field="event_date",
        completed_statuses=(EntityStatus.COMPLETED.value,),
    )

    # ========================================================================
    # CLASS-LEVEL TYPE ANNOTATIONS
    # ========================================================================
    core: EventsCoreService
    search: EventsSearchService
    habits: EventsHabitIntegrationService
    learning: EventsLearningService
    progress: EventsProgressService
    scheduling: EventsSchedulingService
    relationships: UnifiedRelationshipService
    intelligence: EventsIntelligenceService

    # ========================================================================
    # DELEGATION METHODS
    # ========================================================================

    # Core CRUD delegations
    async def get_event(self, *args: Any, **kwargs: Any) -> Any:
        return await self.core.get_event(*args, **kwargs)

    async def get_user_events(self, *args: Any, **kwargs: Any) -> Any:
        return await self.core.get_user_events(*args, **kwargs)

    async def find_events(self, *args: Any, **kwargs: Any) -> Any:
        return await self.core.find_events(*args, **kwargs)

    async def count_events(self, *args: Any, **kwargs: Any) -> Any:
        return await self.core.count_events(*args, **kwargs)

    async def update(self, *args: Any, **kwargs: Any) -> Any:
        return await self.core.update(*args, **kwargs)

    async def get_user_items_in_range(
        self,
        user_uid: str,
        start_date: date,
        end_date: date,
        include_completed: bool = False,
    ) -> Any:
        return await self.core.get_user_items_in_range(
            user_uid=user_uid,
            start_date=start_date,
            end_date=end_date,
            include_completed=include_completed,
        )

    # Habit integration delegations
    async def get_events_for_habit(self, *args: Any, **kwargs: Any) -> Any:
        return await self.habits.get_events_for_habit(*args, **kwargs)

    async def get_habit_reinforcement_events(self, *args: Any, **kwargs: Any) -> Any:
        return await self.habits.get_habit_reinforcement_events(*args, **kwargs)

    async def get_at_risk_habit_events(self, *args: Any, **kwargs: Any) -> Any:
        return await self.habits.get_at_risk_habit_events(*args, **kwargs)

    async def complete_event_with_quality(self, *args: Any, **kwargs: Any) -> Any:
        return await self.habits.complete_event_with_quality(*args, **kwargs)

    async def miss_habit_event(self, *args: Any, **kwargs: Any) -> Any:
        return await self.habits.miss_habit_event(*args, **kwargs)

    async def create_recurring_events_for_habit(self, *args: Any, **kwargs: Any) -> Any:
        return await self.habits.create_recurring_events_for_habit(*args, **kwargs)

    async def get_next_habit_events(self, *args: Any, **kwargs: Any) -> Any:
        return await self.habits.get_next_habit_events(*args, **kwargs)

    # Learning integration delegations
    async def get_learning_events(self, *args: Any, **kwargs: Any) -> Any:
        return await self.learning.get_learning_events(*args, **kwargs)

    async def get_events_for_knowledge(self, *args: Any, **kwargs: Any) -> Any:
        return await self.learning.get_events_for_knowledge(*args, **kwargs)

    async def get_events_for_learning_path(self, *args: Any, **kwargs: Any) -> Any:
        return await self.learning.get_events_for_learning_path(*args, **kwargs)

    async def create_study_session(self, *args: Any, **kwargs: Any) -> Any:
        return await self.learning.create_study_session(*args, **kwargs)

    async def suggest_spaced_repetition_events(self, *args: Any, **kwargs: Any) -> Any:
        return await self.learning.suggest_spaced_repetition_events(*args, **kwargs)

    async def create_learning_path_schedule(self, *args: Any, **kwargs: Any) -> Any:
        return await self.learning.create_learning_path_schedule(*args, **kwargs)

    async def get_knowledge_reinforcement_stats(self, *args: Any, **kwargs: Any) -> Any:
        return await self.learning.get_knowledge_reinforcement_stats(*args, **kwargs)

    # Search delegations
    async def search_events(self, *args: Any, **kwargs: Any) -> Any:
        return await self.search.search(*args, **kwargs)

    async def get_calendar_events(self, *args: Any, **kwargs: Any) -> Any:
        return await self.search.get_calendar_events(*args, **kwargs)

    async def get_event_history(self, *args: Any, **kwargs: Any) -> Any:
        return await self.search.get_history(*args, **kwargs)

    async def get_events_due_soon(self, *args: Any, **kwargs: Any) -> Any:
        return await self.search.get_due_soon(*args, **kwargs)

    async def get_overdue_events(self, *args: Any, **kwargs: Any) -> Any:
        return await self.search.get_overdue(*args, **kwargs)

    async def get_events_by_status(self, *args: Any, **kwargs: Any) -> Any:
        return await self.search.get_by_status(*args, **kwargs)

    async def get_events_in_range(self, *args: Any, **kwargs: Any) -> Any:
        return await self.search.get_in_range(*args, **kwargs)

    async def get_prioritized_events(self, *args: Any, **kwargs: Any) -> Any:
        return await self.search.get_prioritized(*args, **kwargs)

    # Relationship delegations
    async def get_event_cross_domain_context(self, *args: Any, **kwargs: Any) -> Any:
        return await self.relationships.get_cross_domain_context(*args, **kwargs)

    async def get_event_with_semantic_context(self, *args: Any, **kwargs: Any) -> Any:
        return await self.relationships.get_with_semantic_context(*args, **kwargs)

    async def analyze_event_impact(self, *args: Any, **kwargs: Any) -> Any:
        return await self.relationships.get_completion_impact(*args, **kwargs)

    # Intelligence delegations
    async def get_event_with_context(self, *args: Any, **kwargs: Any) -> Any:
        return await self.intelligence.get_event_with_context(*args, **kwargs)

    async def analyze_event_performance(self, *args: Any, **kwargs: Any) -> Any:
        return await self.intelligence.analyze_event_performance(*args, **kwargs)

    async def get_event_goal_support(self, *args: Any, **kwargs: Any) -> Any:
        return await self.intelligence.get_event_goal_support(*args, **kwargs)

    async def get_event_knowledge_reinforcement(self, *args: Any, **kwargs: Any) -> Any:
        return await self.intelligence.get_event_knowledge_reinforcement(*args, **kwargs)

    async def analyze_upcoming_events(self, *args: Any, **kwargs: Any) -> Any:
        return await self.intelligence.analyze_upcoming_events(*args, **kwargs)

    # Progress delegations
    async def complete_event_with_cascade(self, *args: Any, **kwargs: Any) -> Any:
        return await self.progress.complete_event_with_cascade(*args, **kwargs)

    async def get_attendance_rate(self, *args: Any, **kwargs: Any) -> Any:
        return await self.progress.get_attendance_rate(*args, **kwargs)

    async def get_quality_trends(self, *args: Any, **kwargs: Any) -> Any:
        return await self.progress.get_quality_trends(*args, **kwargs)

    async def get_goal_contribution_metrics(self, *args: Any, **kwargs: Any) -> Any:
        return await self.progress.get_goal_contribution_metrics(*args, **kwargs)

    async def get_weekly_summary(self, *args: Any, **kwargs: Any) -> Any:
        return await self.progress.get_weekly_summary(*args, **kwargs)

    async def get_habit_event_stats(self, *args: Any, **kwargs: Any) -> Any:
        return await self.progress.get_habit_event_stats(*args, **kwargs)

    # Scheduling delegations
    async def schedule_event_smart(self, *args: Any, **kwargs: Any) -> Any:
        return await self.scheduling.schedule_event_smart(*args, **kwargs)

    async def suggest_time_slots(self, *args: Any, **kwargs: Any) -> Any:
        return await self.scheduling.suggest_time_slots(*args, **kwargs)

    async def find_next_available_slot(self, *args: Any, **kwargs: Any) -> Any:
        return await self.scheduling.find_next_available_slot(*args, **kwargs)

    async def optimize_recurring_schedule(self, *args: Any, **kwargs: Any) -> Any:
        return await self.scheduling.optimize_recurring_schedule(*args, **kwargs)

    async def create_recurring_events(self, *args: Any, **kwargs: Any) -> Any:
        return await self.scheduling.create_recurring_events(*args, **kwargs)

    async def get_busy_times(self, *args: Any, **kwargs: Any) -> Any:
        return await self.scheduling.get_busy_times(*args, **kwargs)

    async def get_calendar_density(self, *args: Any, **kwargs: Any) -> Any:
        return await self.scheduling.get_calendar_density(*args, **kwargs)

    def __init__(
        self,
        backend: BackendOperations[Event],
        graph_intelligence_service: GraphIntelligenceService,
        event_bus: EventBusOperations | None = None,
        ai_service: EventsAIService | None = None,
    ) -> None:
        """
        Initialize enhanced events service with specialized sub-services.

        Args:
            backend: Protocol-based backend for event operations
            graph_intelligence_service: GraphIntelligenceService for pure Cypher analytics (REQUIRED)
            event_bus: Event bus for publishing domain events (optional)

        Note:
            Context invalidation now happens via event-driven architecture.
            Calendar event operations trigger domain events which invalidate context.

        Migration Note (v3.1.0 - December 2025):
            Made graph_intelligence_service REQUIRED - relationship service needs it.
            Fail-fast at construction, not at method call.
        """
        super().__init__(backend, "events")

        self.graph_intel = graph_intelligence_service
        self.event_bus = event_bus
        self.ai: EventsAIService | None = ai_service
        self.logger = get_logger("skuel.services.events")

        # Initialize 4 common sub-services via factory (eliminates ~30 lines of repetitive code)
        common: CommonSubServices[EventsIntelligenceService] = create_common_sub_services(
            domain="events",
            backend=backend,
            graph_intel=graph_intelligence_service,
            event_bus=event_bus,
        )
        self.core = common.core
        self.search: EventsSearchOperations = common.search
        self.relationships: UnifiedRelationshipService = common.relationships
        self.intelligence: EventsIntelligenceService = common.intelligence

        # Domain-specific sub-services (not common to all facades)
        self.habits = EventsHabitIntegrationService(backend=backend, event_bus=event_bus)
        self.learning = EventsLearningService(backend=backend, event_bus=event_bus)
        self.progress = EventsProgressService(backend=backend, event_bus=event_bus)
        self.scheduling = EventsSchedulingService(backend=backend, event_bus=event_bus)

        self.logger.info(
            "EventsService facade initialized with 8 sub-services: "
            "core, search, habits, learning, progress, scheduling, relationships, intelligence"
        )

    # ========================================================================
    # DOMAIN-SPECIFIC CONTRACT
    # ========================================================================

    @property
    def entity_label(self) -> str:
        """Return the graph label for Event entities."""
        return "Entity"

    # Note: Backend access uses inherited BaseService._backend property
    # Custom backend property removed November 2025 - was unnecessary indirection

    # ========================================================================
    # EXPLICIT DELEGATIONS
    # ========================================================================
    # The following methods are auto-generated from _delegations specification:
    # - Core CRUD: get_event, get_user_events, find_events, count_events, get_user_items_in_range
    # - Habits: get_events_for_habit, get_habit_reinforcement_events, get_at_risk_habit_events,
    #           complete_event_with_quality, miss_habit_event, create_recurring_events_for_habit,
    #           get_next_habit_events
    # - Learning: get_learning_events, get_events_for_knowledge, get_events_for_learning_path,
    #             create_study_session, suggest_spaced_repetition_events, create_learning_path_schedule,
    #             get_knowledge_reinforcement_stats
    # - Search: search_events, get_calendar_events, get_event_history, get_events_due_soon,
    #           get_overdue_events, get_events_by_status, get_events_in_range, get_prioritized_events
    # - Relationships: get_event_cross_domain_context, get_event_with_semantic_context, analyze_event_impact
    # - Intelligence: get_event_with_context, analyze_event_performance, get_event_goal_support,
    #                 get_event_knowledge_reinforcement, analyze_upcoming_events
    # ========================================================================

    # ========================================================================
    # GRAPH RELATIONSHIPS - Explicit methods (custom logic)
    # ========================================================================

    async def create_user_event_relationship(
        self, user_uid: str, event_uid: str, participation_type: str = "scheduled"
    ) -> Result[bool]:
        """Create User→Event relationship in graph."""
        properties = (
            {"participation_type": participation_type}
            if participation_type != "scheduled"
            else None
        )
        return await self.relationships.create_user_relationship(user_uid, event_uid, properties)

    async def link_event_to_goal(
        self, event_uid: str, goal_uid: str, contribution_weight: float = 1.0
    ) -> Result[bool]:
        """Link event to goal it supports."""
        return await self.relationships.link_to_goal(
            event_uid, goal_uid, contribution_weight=contribution_weight
        )

    async def link_event_to_habit(self, event_uid: str, habit_uid: str) -> Result[bool]:
        """Link event to habit it reinforces."""
        return await self.relationships.create_relationship("habits", event_uid, habit_uid)

    async def link_event_to_knowledge(
        self, event_uid: str, knowledge_uids: list[str]
    ) -> Result[bool]:
        """Link event to knowledge units it reinforces."""
        result = await self.relationships.create_relationships_batch(
            event_uid, {"knowledge": knowledge_uids}
        )
        # Convert Result[int] (count) to Result[bool] (success)
        if result.is_error:
            return Result.fail(result)
        return Result.ok(result.value > 0)

    async def get_events_supporting_goal(self, goal_uid: str, user_uid: str) -> Result[list[Event]]:
        """Get all events that support a specific goal."""
        # Get event UIDs linked to the goal
        event_uids_result = await self.relationships.get_related_uids("goals", goal_uid)
        if event_uids_result.is_error:
            return Result.fail(event_uids_result)

        event_uids = event_uids_result.value
        if not event_uids:
            return Result.ok([])

        # Fetch events by UIDs using batch get
        events_result = await self.backend.get_many(event_uids)
        if events_result.is_error:
            return Result.fail(events_result.expect_error())

        # Filter to events owned by this user (exclude None from get_many results)
        user_events = [e for e in events_result.value if e is not None and e.user_uid == user_uid]

        return Result.ok(user_events)

    async def create_semantic_knowledge_relationship(
        self,
        event_uid: str,
        knowledge_uid: str,
        semantic_type: SemanticRelationshipType,
        confidence: float = 0.9,
        notes: str | None = None,
    ) -> Result[dict[str, Any]]:
        """Create semantic relationship between event and knowledge."""
        return await self.relationships.create_semantic_relationship(
            event_uid, knowledge_uid, semantic_type, confidence, notes
        )

    async def find_events_reinforcing_knowledge(
        self, knowledge_uid: str, user_uid: str, min_confidence: float = 0.8
    ) -> Result[list[Event]]:
        """Find events that reinforce specific knowledge."""
        return await self.relationships.find_by_semantic_filter(
            target_uid=knowledge_uid, min_confidence=min_confidence, direction="incoming"
        )

    # ========================================================================
    # STATUS MANAGEMENT
    # ========================================================================

    async def update_event_status(self, request: EventStatusUpdateRequest) -> Result[Event]:
        """
        Update an event's status using typed request object.

        Args:
            request: EventStatusUpdateRequest containing:
                - event_uid: UID of the event (added via route)
                - status: New status value
                - notes: Optional status change notes
                - cancellation_reason: Optional cancellation reason

        Returns:
            Result with the updated event

        Note:
            The request object is validated by Pydantic at the API boundary,
            ensuring type safety throughout the call chain.
        """
        # Build update dict from request fields
        updates: dict[str, Any] = {"status": get_enum_value(request.status)}

        # Include optional fields if provided
        # NOTE: Event model doesn't have notes/cancellation_reason fields directly,
        # so we store them in metadata for audit trail
        metadata_updates = {}
        if request.notes:
            metadata_updates["status_change_notes"] = request.notes
        if request.cancellation_reason:
            metadata_updates["cancellation_reason"] = request.cancellation_reason

        if metadata_updates:
            # Get current event to merge metadata
            event_result = await self.core.get(request.event_uid)
            if event_result.is_error:
                return Result.fail(event_result.expect_error())
            if event_result.value is None:
                return Result.fail(Errors.not_found(resource="Event", identifier=request.event_uid))
            current_metadata = event_result.value.metadata or {}
            updates["metadata"] = {**current_metadata, **metadata_updates}

        return await self.core.update(request.event_uid, updates)

    async def start_event(self, event_uid: str) -> Result[Event]:
        """
        Mark an event as started/in progress.

        Args:
            event_uid: UID of the event to start

        Returns:
            Result with the updated event
        """
        updates: EventUpdatePayload = {"status": EntityStatus.ACTIVE.value}
        return await self.core.update(event_uid, updates)

    async def complete_event(self, event_uid: str) -> Result[Event]:
        """
        Mark an event as completed.

        Args:
            event_uid: UID of the event to complete

        Returns:
            Result with the updated event
        """
        updates: EventUpdatePayload = {"status": EntityStatus.COMPLETED.value}
        return await self.core.update(event_uid, updates)

    async def cancel_event(self, event_uid: str, reason: str = "") -> Result[Event]:
        """
        Cancel an event.

        Args:
            event_uid: UID of the event to cancel
            reason: Optional cancellation reason

        Returns:
            Result with the updated event
        """
        updates: EventUpdatePayload = {"status": EntityStatus.CANCELLED.value}
        if reason:
            updates["notes"] = reason
        return await self.core.update(event_uid, updates)

    # ========================================================================
    # SEARCH & DISCOVERY OPERATIONS - Explicit methods (request unwrapping)
    # ========================================================================
    # Note: Most search methods auto-generated via _delegations.
    # Only methods that unwrap typed requests remain explicit.

    async def get_recurring_events(self, request: GetRecurringEventsRequest) -> Result[list[Event]]:
        """
        Get all recurring events for a user using typed request.

        Args:
            request: GetRecurringEventsRequest containing:
                - user_uid: User identifier
                - limit: Maximum results

        Returns:
            Result with list of recurring events
        """
        return await self.search.get_recurring(request.user_uid, request.limit)

    # ========================================================================
    # CONFLICT AND ATTENDEE MANAGEMENT - Delegate to UnifiedRelationshipService
    # ========================================================================

    async def check_conflicts(self, request: CheckConflictsRequest) -> Result[list[str]]:
        """
        Check for scheduling conflicts with other events using typed request.

        Args:
            request: CheckConflictsRequest containing event_uid to check

        Returns:
            Result with list of conflicting event UIDs
        """
        # Get the event to check
        event_result = await self.core.get(request.event_uid)
        if event_result.is_error:
            return Result.fail(event_result.expect_error())

        event = event_result.value
        if not event:
            return Result.fail(Errors.not_found(resource="Event", identifier=request.event_uid))

        if not event.event_date or not event.start_time or not event.end_time:
            # Event has no scheduled time, no conflicts possible
            return Result.ok([])

        # Get all events on the same date for this user
        same_day_result = await self.backend.find_by(
            user_uid=event.user_uid,
            event_date=event.event_date.isoformat(),
        )
        if same_day_result.is_error:
            return Result.fail(same_day_result.expect_error())

        # Find overlapping events using the model's overlaps_with method
        conflicting_uids = [
            other.uid
            for other in (same_day_result.value or [])
            if other.uid != event.uid and event.overlaps_with(other)
        ]

        return Result.ok(conflicting_uids)

    async def get_event_attendees(self, event_uid: str) -> Result[list[str]]:
        """
        Get attendees for an event.

        Args:
            event_uid: UID of the event

        Returns:
            Result with list of attendee UIDs
        """
        # Attendees are stored via User→Event relationships
        # Query incoming HAS_EVENT relationships
        return await self.relationships.get_related_uids("attendees", event_uid)

    async def add_attendee(self, request: AddAttendeeRequest) -> Result[bool]:
        """
        Add an attendee to an event using typed request.

        Args:
            request: AddAttendeeRequest containing:
                - event_uid: UID of the event
                - user_uid: UID of the user to add as attendee
                - role: Attendee role (attendee, organizer, speaker)
                - send_notification: Whether to notify the attendee

        Returns:
            Result with success status
        """
        from datetime import datetime

        properties = {"participation_type": request.role} if request.role != "scheduled" else None
        result = await self.relationships.create_user_relationship(
            user_uid=request.user_uid,
            entity_uid=request.event_uid,
            properties=properties,
        )

        # Publish notification event if requested and relationship creation succeeded
        if request.send_notification and result.is_ok:
            # Get event title for notification
            event_result = await self.core.get(request.event_uid)
            event_title = (
                event_result.value.title if event_result.is_ok and event_result.value else "Event"
            )

            notification_event = EventAttendeeAdded(
                event_uid=request.event_uid,
                event_title=event_title,
                attendee_uid=request.user_uid,
                added_by_uid=request.user_uid,  # Could be enhanced with current_user
                role=request.role,
                occurred_at=datetime.now(),
            )
            await publish_event(self.event_bus, notification_event, self.logger)

        return result

    async def remove_attendee(self, request: RemoveAttendeeRequest) -> Result[bool]:
        """
        Remove an attendee from an event using typed request.

        Args:
            request: RemoveAttendeeRequest containing:
                - event_uid: UID of the event
                - user_uid: UID of the user to remove
                - send_notification: Whether to notify the attendee

        Returns:
            Result with success status
        """
        from datetime import datetime

        # Get event title before removal for notification
        event_title = "Event"
        if request.send_notification:
            event_result = await self.core.get(request.event_uid)
            if event_result.is_ok and event_result.value:
                event_title = event_result.value.title

        result = await self.relationships.delete_user_relationship(
            user_uid=request.user_uid,
            entity_uid=request.event_uid,
        )

        # Publish notification event if requested and removal succeeded
        if request.send_notification and result.is_ok:
            notification_event = EventAttendeeRemoved(
                event_uid=request.event_uid,
                event_title=event_title,
                attendee_uid=request.user_uid,
                removed_by_uid=request.user_uid,  # Could be enhanced with current_user
                occurred_at=datetime.now(),
            )
            await publish_event(self.event_bus, notification_event, self.logger)

        return result

    # ========================================================================
    # RECURRING EVENTS
    # ========================================================================

    async def create_recurring_instances(
        self,
        request: RecurringInstancesRequest,
    ) -> Result[list[Event]]:
        """
        Create instances of a recurring event using typed request.

        Args:
            request: RecurringInstancesRequest containing:
                - event_uid: UID of the recurring event template
                - count: Number of instances to create (1-100)

        Returns:
            Result with list of created event instances
        """
        from datetime import timedelta

        # Get the template event
        event_result = await self.get_event(request.event_uid)
        if event_result.is_error:
            return Result.fail(event_result.expect_error())

        event = event_result.value
        if not event:
            return Result.fail(Errors.not_found(resource="Event", identifier=request.event_uid))

        if not event.recurrence_pattern:
            return Result.fail(
                Errors.validation(
                    message="Event is not recurring",
                    field="recurrence_pattern",
                    value=None,
                )
            )

        # Calculate interval based on recurrence pattern (stored as plain string)
        pattern = event.recurrence_pattern

        interval_days = {
            "daily": 1,
            "weekly": 7,
            "biweekly": 14,
            "monthly": 30,
            "yearly": 365,
        }.get(pattern, 7)

        created_events: list[Event] = []
        base_date = event.event_date

        for i in range(1, request.count + 1):
            new_date = base_date + timedelta(days=interval_days * i)

            # Create new event instance
            dto = EventDTO.create_event(
                user_uid=event.user_uid,
                title=event.title,
                event_date=new_date,
                start_time=event.start_time,
                end_time=event.end_time,
                event_type=event.event_type,
                location=event.location,
                is_online=event.is_online,
                tags=event.tags,
            )
            dto.recurrence_parent_uid = request.event_uid  # Link to template

            create_result = await self.backend.create(dto.to_dict())
            if create_result.is_ok:
                new_event = self._to_domain_model(create_result.value, EventDTO, Event)
                created_events.append(new_event)

        return Result.ok(created_events)

    # ========================================================================
    # ORCHESTRATION METHODS - Remain in Facade
    # ========================================================================

    async def create_event_with_context(
        self, event_data: EventCreateRequest, user_context: UserContext
    ) -> Result[Event]:
        """
        Create an event with full context awareness (orchestration method).

        This method orchestrates multiple checks:
        1. Sets up habit reinforcement relationships
        2. Links to learning paths if applicable
        3. Updates context after creation
        """
        # Create DTO from request
        dto = EventDTO.create_event(
            user_uid=user_context.user_uid,
            title=event_data.title,
            event_date=event_data.event_date,
            start_time=event_data.start_time,
            end_time=event_data.end_time,
            event_type=event_data.event_type,
            location=event_data.location,
            is_online=event_data.is_online,
            tags=event_data.tags,
        )

        # Add learning integration fields
        dto.reinforces_habit_uid = event_data.reinforces_habit_uid
        # PHASE 3B: practices_knowledge_uids is a graph relationship, not a DTO field
        # Services create graph edges after event creation via relationship services
        # NOTE: supports_goal_uid and learning_path_uid use getattr for forward compatibility
        dto.fulfills_goal_uid = getattr(event_data, "supports_goal_uid", None)  # type: ignore[attr-defined]
        dto.learning_path_uid = getattr(event_data, "learning_path_uid", None)  # type: ignore[attr-defined]

        # Set recurrence for habit events
        if dto.reinforces_habit_uid and dto.reinforces_habit_uid in user_context.active_habit_uids:
            # Auto-set recurrence based on habit frequency
            dto.recurrence_pattern = RecurrencePattern.DAILY  # Default

        # Create event in backend
        create_result = await self.backend.create(dto.to_dict())
        if create_result.is_error:
            return Result.fail(create_result)

        event = self._to_domain_model(create_result.value, EventDTO, Event)

        # Publish CalendarEventCreated event (event-driven architecture)
        from datetime import datetime

        from core.events import CalendarEventCreated, publish_event

        event_obj = CalendarEventCreated(
            event_uid=event.uid,
            user_uid=user_context.user_uid,
            title=event.title,
            event_date=event.event_date,
            calendar_event_type=get_enum_value(event.event_type),
            occurred_at=datetime.now(),
        )
        await publish_event(self.event_bus, event_obj, self.logger)

        # Publish KnowledgePracticedInEvent events for substance tracking
        if event_data.practices_knowledge_uids:
            from core.events.ku_events import KnowledgePracticedInEvent

            for knowledge_uid in event_data.practices_knowledge_uids:
                knowledge_event = KnowledgePracticedInEvent(
                    knowledge_uid=knowledge_uid,
                    event_uid=event.uid,
                    user_uid=user_context.user_uid,
                    occurred_at=datetime.now(),
                    event_title=event.title,
                    duration_minutes=event.duration_minutes,
                )
                await publish_event(self.event_bus, knowledge_event, self.logger)

            self.logger.debug(
                f"Published {len(event_data.practices_knowledge_uids)} KnowledgePracticedInEvent events for event {event.uid}"
            )

        # Note: User context invalidation now happens via event-driven architecture
        # CalendarEventCreated event → invalidate_context_on_calendar_event() → user_service.invalidate_context()

        self.logger.info(
            "Created event %s with habit=%s, knowledge=%d",
            event.uid,
            event.reinforces_habit_uid,
            len(event_data.practices_knowledge_uids or []),
        )

        return Result.ok(event)
