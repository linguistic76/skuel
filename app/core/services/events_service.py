"""
Enhanced Events Service - Facade Pattern
==========================================

Events service facade that delegates to specialized sub-services.
This service provides a unified interface while maintaining clean separation of concerns.

Version: 7.2.0
- v7.2.0: Typed Request Objects pattern - service methods accept typed request objects (November 29, 2025)
- v7.1.0: Added EventsSearchService for search/discovery (November 28, 2025)
- v7.0.0: Facade pattern implementation with 5 specialized sub-services (October 13, 2025)
- v6.0.0: Phase 1-4 integration with pure Cypher graph intelligence (October 3, 2025)
- v5.0.0: Enhanced with habit reinforcement and UserContext awareness
- v4.0.0: Three-tier architecture implementation

Sub-Services:
- EventsCoreService: CRUD operations
- EventsSearchService: Search and discovery (DomainSearchOperations[Event] protocol)
- EventsHabitIntegrationService: Cross-domain habits integration
- EventsLearningService: Learning path integration
- UnifiedRelationshipService (EVENTS_CONFIG): Graph relationships and semantic connections
- EventsIntelligenceService: pure Cypher analytics

Architecture: Zero breaking changes - all existing code continues to work unchanged.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

from core.events import publish_event
from core.events.calendar_event_events import EventAttendeeAdded, EventAttendeeRemoved
from core.models.enums import KuStatus, RecurrencePattern
from core.models.ku.ku import Ku
from core.models.ku.ku_dto import KuDTO
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
from core.services.mixins import FacadeDelegationMixin, merge_delegations
from core.services.protocols import get_enum_value
from core.services.protocols.query_types import EventUpdatePayload

# Unified relationship service (replaces EventsRelationshipService)
from core.services.relationships import UnifiedRelationshipService
from core.utils.activity_domain_config import CommonSubServices, create_common_sub_services
from core.utils.logging import get_logger
from core.utils.result_simplified import Errors, Result

if TYPE_CHECKING:
    from core.infrastructure.relationships.semantic_relationships import SemanticRelationshipType
    from core.models.event.event_request import (
        AddAttendeeRequest,
        CheckConflictsRequest,
        EventStatusUpdateRequest,
        GetRecurringEventsRequest,
        RecurringInstancesRequest,
        RemoveAttendeeRequest,
    )
    from core.models.ku.ku_request import KuEventCreateRequest
    from core.services.events.events_intelligence_service import EventsIntelligenceService
    from core.services.protocols import BackendOperations
    from core.services.protocols.facade_protocols import EventsFacadeProtocol
    from core.services.protocols.infrastructure_protocols import EventBusOperations
    from core.services.protocols.search_protocols import EventsSearchOperations
    from core.services.user import UserContext


class EventsService(FacadeDelegationMixin, BaseService["BackendOperations[Ku]", Ku]):
    """
    Events service facade with specialized sub-services.

    This facade:
    1. Delegates to 6 specialized sub-services for core operations
    2. Uses FacadeDelegationMixin for ~30 auto-generated delegation methods
    3. Retains explicit methods for complex cross-service orchestration
    4. Provides clean separation of concerns

    Auto-Generated Delegations (via FacadeDelegationMixin):
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
    - Uses FacadeDelegationMixin for delegation (January 2026 Phase 3)
    - No APOC calls (Phase 5 eliminated those)
    - Returns Result[T] for error handling
    - Logs operations with structured logging
    """

    # ========================================================================
    # DOMAIN CONFIGURATION (DomainConfig - January 2026)
    # ========================================================================
    # Facade services use same config as core/search sub-services
    _config = create_activity_domain_config(
        dto_class=KuDTO,
        model_class=Ku,
        domain_name="events",
        date_field="event_date",
        completed_statuses=(KuStatus.COMPLETED.value,),
    )

    # ========================================================================
    # CLASS-LEVEL TYPE ANNOTATIONS (for FacadeDelegationMixin signature preservation)
    # ========================================================================
    # These annotations allow the mixin to resolve method signatures at class definition time.
    core: EventsCoreService
    search: EventsSearchService
    habits: EventsHabitIntegrationService
    learning: EventsLearningService
    progress: EventsProgressService
    scheduling: EventsSchedulingService
    relationships: UnifiedRelationshipService
    intelligence: EventsIntelligenceService

    # ========================================================================
    # DELEGATION SPECIFICATION (FacadeDelegationMixin)
    # ========================================================================
    # Simple delegations are auto-generated. Complex methods remain explicit.
    _delegations = merge_delegations(
        # Core CRUD delegations
        {
            "get_event": ("core", "get_event"),
            "get_user_events": ("core", "get_user_events"),
            "find_events": ("core", "find_events"),
            "count_events": ("core", "count_events"),
            "update": ("core", "update"),
            "get_user_items_in_range": ("core", "get_user_items_in_range"),
        },
        # Habit integration delegations
        {
            "get_events_for_habit": ("habits", "get_events_for_habit"),
            "get_habit_reinforcement_events": ("habits", "get_habit_reinforcement_events"),
            "get_at_risk_habit_events": ("habits", "get_at_risk_habit_events"),
            "complete_event_with_quality": ("habits", "complete_event_with_quality"),
            "miss_habit_event": ("habits", "miss_habit_event"),
            "create_recurring_events_for_habit": ("habits", "create_recurring_events_for_habit"),
            "get_next_habit_events": ("habits", "get_next_habit_events"),
        },
        # Learning integration delegations
        {
            "get_learning_events": ("learning", "get_learning_events"),
            "get_events_for_knowledge": ("learning", "get_events_for_knowledge"),
            "get_events_for_learning_path": ("learning", "get_events_for_learning_path"),
            "create_study_session": ("learning", "create_study_session"),
            "suggest_spaced_repetition_events": ("learning", "suggest_spaced_repetition_events"),
            "create_learning_path_schedule": ("learning", "create_learning_path_schedule"),
            "get_knowledge_reinforcement_stats": ("learning", "get_knowledge_reinforcement_stats"),
        },
        # Search delegations (with method name mapping where needed)
        {
            "search_events": ("search", "search"),
            "get_calendar_events": ("search", "get_calendar_events"),
            "get_event_history": ("search", "get_history"),
            "get_events_due_soon": ("search", "get_due_soon"),
            "get_overdue_events": ("search", "get_overdue"),
            "get_events_by_status": ("search", "get_by_status"),
            "get_events_in_range": ("search", "get_in_range"),
            "get_prioritized_events": ("search", "get_prioritized"),
        },
        # Relationship delegations (simple passthrough only)
        {
            "get_event_cross_domain_context": ("relationships", "get_cross_domain_context"),
            "get_event_with_semantic_context": ("relationships", "get_with_semantic_context"),
            "analyze_event_impact": ("relationships", "get_completion_impact"),
        },
        # Intelligence delegations
        {
            "get_event_with_context": ("intelligence", "get_event_with_context"),
            "analyze_event_performance": ("intelligence", "analyze_event_performance"),
            "get_event_goal_support": ("intelligence", "get_event_goal_support"),
            "get_event_knowledge_reinforcement": (
                "intelligence",
                "get_event_knowledge_reinforcement",
            ),
            "analyze_upcoming_events": ("intelligence", "analyze_upcoming_events"),
        },
        # Progress delegations (January 2026)
        {
            "complete_event_with_cascade": ("progress", "complete_event_with_cascade"),
            "get_attendance_rate": ("progress", "get_attendance_rate"),
            "get_quality_trends": ("progress", "get_quality_trends"),
            "get_goal_contribution_metrics": ("progress", "get_goal_contribution_metrics"),
            "get_weekly_summary": ("progress", "get_weekly_summary"),
            "get_habit_event_stats": ("progress", "get_habit_event_stats"),
        },
        # Scheduling delegations (January 2026)
        {
            "schedule_event_smart": ("scheduling", "schedule_event_smart"),
            "check_conflicts": ("scheduling", "check_conflicts"),
            "suggest_time_slots": ("scheduling", "suggest_time_slots"),
            "find_next_available_slot": ("scheduling", "find_next_available_slot"),
            "optimize_recurring_schedule": ("scheduling", "optimize_recurring_schedule"),
            "create_recurring_events": ("scheduling", "create_recurring_events"),
            "get_busy_times": ("scheduling", "get_busy_times"),
            "get_calendar_density": ("scheduling", "get_calendar_density"),
        },
    )

    def __init__(
        self,
        backend: BackendOperations[Ku],
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
        return "Ku"

    # Note: Backend access uses inherited BaseService._backend property
    # Custom backend property removed November 2025 - was unnecessary indirection

    # ========================================================================
    # AUTO-GENERATED DELEGATIONS (via FacadeDelegationMixin)
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

    async def get_events_supporting_goal(self, goal_uid: str, user_uid: str) -> Result[list[Ku]]:
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
    ) -> Result[list[Ku]]:
        """Find events that reinforce specific knowledge."""
        return await self.relationships.find_by_semantic_filter(
            target_uid=knowledge_uid, min_confidence=min_confidence, direction="incoming"
        )

    # ========================================================================
    # STATUS MANAGEMENT
    # ========================================================================

    async def update_event_status(self, request: EventStatusUpdateRequest) -> Result[Ku]:
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

    async def start_event(self, event_uid: str) -> Result[Ku]:
        """
        Mark an event as started/in progress.

        Args:
            event_uid: UID of the event to start

        Returns:
            Result with the updated event
        """
        updates: EventUpdatePayload = {"status": KuStatus.ACTIVE.value}
        return await self.core.update(event_uid, updates)

    async def complete_event(self, event_uid: str) -> Result[Ku]:
        """
        Mark an event as completed.

        Args:
            event_uid: UID of the event to complete

        Returns:
            Result with the updated event
        """
        updates: EventUpdatePayload = {"status": KuStatus.COMPLETED.value}
        return await self.core.update(event_uid, updates)

    async def cancel_event(self, event_uid: str, reason: str = "") -> Result[Ku]:
        """
        Cancel an event.

        Args:
            event_uid: UID of the event to cancel
            reason: Optional cancellation reason

        Returns:
            Result with the updated event
        """
        updates: EventUpdatePayload = {"status": KuStatus.CANCELLED.value}
        if reason:
            updates["notes"] = reason
        return await self.core.update(event_uid, updates)

    # ========================================================================
    # SEARCH & DISCOVERY OPERATIONS - Explicit methods (request unwrapping)
    # ========================================================================
    # Note: Most search methods auto-generated via _delegations.
    # Only methods that unwrap typed requests remain explicit.

    async def get_recurring_events(self, request: GetRecurringEventsRequest) -> Result[list[Ku]]:
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
    ) -> Result[list[Ku]]:
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
        # Cast to protocol for MyPy (FacadeDelegationMixin creates methods dynamically)
        typed_self = cast("EventsFacadeProtocol", self)
        event_result = await typed_self.get_event(request.event_uid)
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

        created_events: list[Ku] = []
        base_date = event.event_date

        for i in range(1, request.count + 1):
            new_date = base_date + timedelta(days=interval_days * i)

            # Create new event instance
            from core.models.ku.ku_dto import KuDTO

            dto = KuDTO.create_event(
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
                new_event = self._to_domain_model(create_result.value, KuDTO, Ku)
                created_events.append(new_event)

        return Result.ok(created_events)

    # ========================================================================
    # ORCHESTRATION METHODS - Remain in Facade
    # ========================================================================

    async def create_event_with_context(
        self, event_data: KuEventCreateRequest, user_context: UserContext
    ) -> Result[Ku]:
        """
        Create an event with full context awareness (orchestration method).

        This method orchestrates multiple checks:
        1. Sets up habit reinforcement relationships
        2. Links to learning paths if applicable
        3. Updates context after creation
        """
        # Create DTO from request
        from core.models.ku.ku_dto import KuDTO

        dto = KuDTO.create_event(
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
        dto.fulfills_goal_uid = getattr(event_data, "supports_goal_uid", None)
        dto.learning_path_uid = getattr(event_data, "learning_path_uid", None)

        # Set recurrence for habit events
        if dto.reinforces_habit_uid and dto.reinforces_habit_uid in user_context.active_habit_uids:
            # Auto-set recurrence based on habit frequency
            dto.recurrence_pattern = RecurrencePattern.DAILY  # Default

        # Create event in backend
        create_result = await self.backend.create(dto.to_dict())
        if create_result.is_error:
            return Result.fail(create_result)

        event = self._to_domain_model(create_result.value, KuDTO, Ku)

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
