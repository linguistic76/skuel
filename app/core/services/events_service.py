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
- EventsEventHandlerService: Event-driven reactive logic (attendance patterns, rescheduling, density)
- EventsIntelligenceService: Pure Cypher analytics
"""

from __future__ import annotations

from datetime import date, time
from typing import TYPE_CHECKING, Any

from core.events import publish_event
from core.events.calendar_event_events import EventAttendeeAdded, EventAttendeeRemoved
from core.models.enums import EntityStatus, RecurrencePattern
from core.models.event.event import Event
from core.models.event.event_dto import EventDTO
from core.ports import get_enum_attr_str, get_enum_value
from core.ports.query_types import EventUpdatePayload
from core.services.activity_domain_config import CommonSubServices, create_common_sub_services
from core.services.base_service import BaseService
from core.services.domain_config import create_activity_domain_config

# Import sub-services
from core.services.events import (
    EventsCoreService,
    EventsEventHandlerService,
    EventsHabitIntegrationService,
    EventsIntelligenceService,
    EventsLearningService,
    EventsProgressService,
    EventsSchedulingService,
    EventsSearchService,
)
from core.services.events.events_ai_service import EventsAIService
from core.services.filtered_context import build_filtered_context
from core.services.infrastructure.graph_intelligence_service import GraphIntelligenceService

# Unified relationship service
from core.services.relationships import UnifiedRelationshipService
from core.utils.list_helpers import (
    FilterConfig,
    SortConfig,
    apply_entity_filter,
    apply_entity_sort,
    get_event_sort_datetime,
)
from core.utils.logging import get_logger
from core.utils.result_simplified import Errors, Result
from core.utils.sort_functions import get_created_at_attr, get_title_lower

if TYPE_CHECKING:
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
    from core.models.graph_context import GraphContext
    from core.models.pathways.lp_position import LpPosition
    from core.ports.domain_protocols import EventsOperations
    from core.ports.infrastructure_protocols import EventBusOperations
    from core.ports.query_types import ListContext
    from core.ports.search_protocols import EventsSearchOperations
    from core.services.events.events_intelligence_service import EventsIntelligenceService
    from core.services.insight.insight_store import InsightStore
    from core.services.user import UserContext


def _null_callable() -> None:
    """No-op callable: fallback for getattr when attribute is an optional method."""
    return


def _get_event_status_value(event: Any) -> str:
    """Get status value (handles both enum and string)."""
    return get_enum_attr_str(event, "status", "scheduled")


def _compute_event_stats(all_events: list[Any]) -> dict[str, int | float]:
    """Compute pre-filter stats from the full event set."""
    today = date.today()
    terminal = {"completed", "cancelled", "archived"}
    return {
        "total": len(all_events),
        "active": sum(1 for e in all_events if _get_event_status_value(e) not in terminal),
        "scheduled": sum(1 for e in all_events if _get_event_status_value(e) == "scheduled"),
        "today": sum(1 for e in all_events if getattr(e, "event_date", None) == today),
    }


def _is_event_scheduled(e: Any) -> bool:
    """Filter predicate: event is scheduled."""
    return _get_event_status_value(e) == "scheduled"


def _is_event_completed(e: Any) -> bool:
    """Filter predicate: event is completed."""
    return _get_event_status_value(e) == "completed"


def _is_event_cancelled(e: Any) -> bool:
    """Filter predicate: event is cancelled."""
    return _get_event_status_value(e) == "cancelled"


_EVENT_FILTER_CONFIG: FilterConfig = {
    "scheduled": _is_event_scheduled,
    "completed": _is_event_completed,
    "cancelled": _is_event_cancelled,
}

_EVENT_SORT_CONFIG: SortConfig = {
    "start_time": (get_event_sort_datetime, False),
    "title": (get_title_lower, False),
    "created_at": (get_created_at_attr, True),
}


def _apply_event_sort(events: list[Any], sort_by: str = "start_time") -> list[Any]:
    """Sort events using declarative config."""
    return apply_entity_sort(events, sort_by, _EVENT_SORT_CONFIG, "start_time")


class EventsService(BaseService["EventsOperations", Event]):
    """
    Events service facade with specialized sub-services.

    This facade:
    1. Delegates to 7 specialized sub-services for core operations
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
    event_handler: EventsEventHandlerService
    intelligence: EventsIntelligenceService

    # ========================================================================
    # DELEGATION METHODS
    # ========================================================================

    # Core CRUD delegations
    async def get_event(self, event_uid: str) -> Result[Event]:
        return await self.core.get_event(event_uid)

    async def get_user_events(self, user_uid: str) -> Result[list[Event]]:
        return await self.core.get_user_events(user_uid)

    async def find_events(
        self,
        filters: dict[str, Any] | None = None,
        limit: int = 100,
        offset: int = 0,
        order_by: str | None = None,
        order_desc: bool = False,
    ) -> Result[list[Event]]:
        return await self.core.find_events(filters, limit, offset, order_by, order_desc)

    async def count_events(self, filters: dict[str, Any] | None = None) -> Result[int]:
        return await self.core.count_events(filters)

    async def update(self, uid: str, updates: dict[str, Any]) -> Result[Event]:
        return await self.core.update(uid, updates)

    async def get_user_items_in_range(
        self,
        user_uid: str,
        start_date: date,
        end_date: date,
        include_completed: bool = False,
    ) -> Result[list[Event]]:
        return await self.core.get_user_items_in_range(
            user_uid=user_uid,
            start_date=start_date,
            end_date=end_date,
            include_completed=include_completed,
        )

    # Habit integration delegations
    async def get_events_for_habit(
        self, habit_uid: str, user_context: UserContext, days_ahead: int = 7
    ) -> Result[list[Event]]:
        return await self.habits.get_events_for_habit(habit_uid, user_context, days_ahead)

    async def get_habit_reinforcement_events(
        self, user_context: UserContext, days_ahead: int = 7
    ) -> Result[dict[str, list[Event]]]:
        return await self.habits.get_habit_reinforcement_events(user_context, days_ahead)

    async def get_at_risk_habit_events(
        self, user_context: UserContext, risk_threshold_days: int = 3
    ) -> Result[list[Event]]:
        return await self.habits.get_at_risk_habit_events(user_context, risk_threshold_days)

    async def complete_event_with_quality(
        self,
        event_uid: str,
        user_context: UserContext,
        quality_score: int = 4,
        completion_date: date | None = None,
    ) -> Result[Event]:
        return await self.habits.complete_event_with_quality(
            event_uid, user_context, quality_score, completion_date
        )

    async def miss_habit_event(
        self, event_uid: str, user_context: UserContext, reason: str | None = None
    ) -> Result[Event]:
        return await self.habits.miss_habit_event(event_uid, user_context, reason)

    async def create_recurring_events_for_habit(
        self,
        habit_uid: str,
        user_context: UserContext,
        pattern: RecurrencePattern,
        duration_minutes: int = 30,
        days_to_create: int = 30,
        title: str | None = None,
    ) -> Result[list[Event]]:
        return await self.habits.create_recurring_events_for_habit(
            habit_uid, user_context, pattern, duration_minutes, days_to_create, title
        )

    async def get_next_habit_events(
        self, user_context: UserContext
    ) -> Result[dict[str, Event | None]]:
        return await self.habits.get_next_habit_events(user_context)

    # Learning integration delegations
    async def get_learning_events(self, user_uid: str, days_ahead: int = 7) -> Result[list[Event]]:
        return await self.learning.get_learning_events(user_uid, days_ahead)

    async def get_events_for_knowledge(
        self, knowledge_uid: str, user_uid: str, days_ahead: int = 30
    ) -> Result[list[Event]]:
        return await self.learning.get_events_for_knowledge(knowledge_uid, user_uid, days_ahead)

    async def get_events_for_learning_path(
        self, learning_path_uid: str, user_uid: str
    ) -> Result[list[Event]]:
        return await self.learning.get_events_for_learning_path(learning_path_uid, user_uid)

    async def create_study_session(
        self,
        user_uid: str,
        knowledge_uids: list[str],
        event_date: date,
        duration_minutes: int = 60,
        title: str | None = None,
        learning_path_uid: str | None = None,
    ) -> Result[Event]:
        return await self.learning.create_study_session(
            user_uid, knowledge_uids, event_date, duration_minutes, title, learning_path_uid
        )

    async def suggest_spaced_repetition_events(
        self,
        _user_uid: str,
        knowledge_uid: str,
        mastery_level: float = 0.5,
        days_to_schedule: int = 30,
    ) -> Result[list[dict[str, Any]]]:
        return await self.learning.suggest_spaced_repetition_events(
            _user_uid, knowledge_uid, mastery_level, days_to_schedule
        )

    async def create_learning_path_schedule(
        self,
        user_uid: str,
        learning_path_uid: str,
        _learning_position: LpPosition,
        study_hours_per_week: int = 5,
    ) -> Result[list[Event]]:
        return await self.learning.create_learning_path_schedule(
            user_uid, learning_path_uid, _learning_position, study_hours_per_week
        )

    async def get_knowledge_reinforcement_stats(
        self, user_uid: str, knowledge_uid: str, days_back: int = 30
    ) -> Result[dict[str, Any]]:
        return await self.learning.get_knowledge_reinforcement_stats(
            user_uid, knowledge_uid, days_back
        )

    # Search delegations
    async def search_events(
        self, query: str, limit: int = 50, user_uid: str | None = None
    ) -> Result[list[Event]]:
        return await self.search.search(query, limit, user_uid)

    async def get_calendar_events(
        self,
        user_uid: str,
        start_date: date | None = None,
        end_date: date | None = None,
        limit: int = 100,
    ) -> Result[list[Event]]:
        return await self.search.get_calendar_events(user_uid, start_date, end_date, limit)

    async def get_event_history(
        self, user_uid: str, days_back: int = 90, limit: int = 100
    ) -> Result[list[Event]]:
        return await self.search.get_history(user_uid, days_back, limit)

    async def get_events_due_soon(
        self, days_ahead: int = 7, user_uid: str | None = None, limit: int = 100
    ) -> Result[list[Event]]:
        return await self.search.get_due_soon(days_ahead, user_uid, limit)

    async def get_overdue_events(
        self, user_uid: str | None = None, limit: int = 100
    ) -> Result[list[Event]]:
        return await self.search.get_overdue(user_uid, limit)

    async def get_events_by_status(
        self, status: str, limit: int = 100, user_uid: str | None = None
    ) -> Result[list[Event]]:
        return await self.search.get_by_status(status, limit, user_uid)

    async def get_events_in_range(
        self,
        start_date: date,
        end_date: date,
        user_uid: str | None = None,
        limit: int = 100,
    ) -> Result[list[Event]]:
        return await self.search.get_in_range(start_date, end_date, user_uid, limit)

    async def get_prioritized_events(
        self, user_context: UserContext, limit: int = 10
    ) -> Result[list[Event]]:
        return await self.search.get_prioritized(user_context, limit)

    # Relationship delegations
    async def get_event_cross_domain_context(
        self, entity_uid: str, depth: int = 2, min_confidence: float = 0.7
    ) -> Result[dict[str, Any]]:
        return await self.relationships.get_cross_domain_context(entity_uid, depth, min_confidence)

    async def get_event_with_semantic_context(
        self,
        uid: str,
        min_confidence: float = 0.8,
        semantic_types: list[SemanticRelationshipType] | None = None,
    ) -> Result[dict[str, Any]]:
        return await self.relationships.get_with_semantic_context(
            uid, min_confidence, semantic_types
        )

    async def analyze_event_impact(self, uid: str) -> Result[dict[str, Any]]:
        return await self.relationships.get_completion_impact(uid)

    # Intelligence delegations
    async def get_event_with_context(
        self, uid: str, depth: int = 2
    ) -> Result[tuple[Event, GraphContext]]:
        return await self.intelligence.get_event_with_context(uid, depth)

    async def analyze_event_performance(self, uid: str) -> Result[dict[str, Any]]:
        return await self.intelligence.analyze_event_performance(uid)

    async def get_event_goal_support(self, uid: str, depth: int = 2) -> Result[dict[str, Any]]:
        return await self.intelligence.get_event_goal_support(uid, depth)

    async def get_event_knowledge_reinforcement(
        self, uid: str, depth: int = 2
    ) -> Result[dict[str, Any]]:
        return await self.intelligence.get_event_knowledge_reinforcement(uid, depth)

    async def analyze_upcoming_events(
        self, user_uid: str, days_ahead: int = 7
    ) -> Result[dict[str, Any]]:
        return await self.intelligence.analyze_upcoming_events(user_uid, days_ahead)

    # Progress delegations
    async def complete_event_with_cascade(
        self,
        event_uid: str,
        user_context: UserContext,
        quality_score: int | None = None,
        notes: str | None = None,
    ) -> Result[Event]:
        return await self.progress.complete_event_with_cascade(
            event_uid, user_context, quality_score, notes
        )

    async def get_attendance_rate(
        self, user_uid: str, period_days: int = 30
    ) -> Result[dict[str, Any]]:
        return await self.progress.get_attendance_rate(user_uid, period_days)

    async def get_quality_trends(
        self, user_uid: str, period_days: int = 30
    ) -> Result[dict[str, Any]]:
        return await self.progress.get_quality_trends(user_uid, period_days)

    async def get_goal_contribution_metrics(
        self, user_uid: str, period_days: int = 30
    ) -> Result[dict[str, Any]]:
        return await self.progress.get_goal_contribution_metrics(user_uid, period_days)

    async def get_weekly_summary(
        self, user_uid: str, weeks_back: int = 4
    ) -> Result[dict[str, Any]]:
        return await self.progress.get_weekly_summary(user_uid, weeks_back)

    async def get_habit_event_stats(
        self, user_uid: str, period_days: int = 30
    ) -> Result[dict[str, Any]]:
        return await self.progress.get_habit_event_stats(user_uid, period_days)

    # Scheduling delegations
    async def schedule_event_smart(
        self,
        event_data: EventCreateRequest,
        user_context: UserContext,
        avoid_conflicts: bool = True,
    ) -> Result[Event]:
        return await self.scheduling.schedule_event_smart(event_data, user_context, avoid_conflicts)

    async def suggest_time_slots(
        self,
        user_uid: str,
        target_date: date,
        duration_minutes: int = 60,
        preferred_hours: tuple[int, int] = (9, 18),
    ) -> Result[list[dict[str, Any]]]:
        return await self.scheduling.suggest_time_slots(
            user_uid, target_date, duration_minutes, preferred_hours
        )

    async def find_next_available_slot(
        self,
        user_uid: str,
        duration_minutes: int = 60,
        preferred_hours: tuple[int, int] = (9, 18),
        days_to_search: int = 7,
    ) -> Result[dict[str, Any] | None]:
        return await self.scheduling.find_next_available_slot(
            user_uid, duration_minutes, preferred_hours, days_to_search
        )

    async def optimize_recurring_schedule(
        self,
        user_uid: str,
        pattern: RecurrencePattern,
        preferred_time: time | None = None,
        days_to_schedule: int = 30,
    ) -> Result[list[date]]:
        return await self.scheduling.optimize_recurring_schedule(
            user_uid, pattern, preferred_time, days_to_schedule
        )

    async def create_recurring_events(
        self,
        user_uid: str,
        title: str,
        pattern: RecurrencePattern,
        duration_minutes: int = 60,
        preferred_time: time | None = None,
        days_to_create: int = 30,
        reinforces_habit_uid: str | None = None,
    ) -> Result[list[Event]]:
        return await self.scheduling.create_recurring_events(
            user_uid,
            title,
            pattern,
            duration_minutes,
            preferred_time,
            days_to_create,
            reinforces_habit_uid,
        )

    async def get_busy_times(
        self, user_uid: str, start_date: date, end_date: date
    ) -> Result[dict[str, list[dict[str, str]]]]:
        return await self.scheduling.get_busy_times(user_uid, start_date, end_date)

    async def get_calendar_density(
        self, user_uid: str, days_ahead: int = 14
    ) -> Result[dict[str, Any]]:
        return await self.scheduling.get_calendar_density(user_uid, days_ahead)

    def __init__(
        self,
        backend: EventsOperations,
        graph_intelligence_service: GraphIntelligenceService,
        event_bus: EventBusOperations | None = None,
        ai_service: EventsAIService | None = None,
        insight_store: InsightStore | None = None,
        activity_knowledge_intelligence: Any = None,
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
        self.event_handler = EventsEventHandlerService(
            backend=backend,
            relationship_service=self.relationships,
            insight_store=insight_store,
        )

        # Knowledge intelligence (shared singleton — domain-agnostic)
        self.knowledge_intelligence = activity_knowledge_intelligence

        self.logger.info(
            "EventsService facade initialized with 10 sub-services: "
            "core, search, habits, learning, progress, scheduling, relationships, "
            "event_handler, intelligence, knowledge_intelligence"
        )

    # ========================================================================
    # KNOWLEDGE INTELLIGENCE - Delegate to ActivityKnowledgeIntelligenceService
    # ========================================================================

    async def get_knowledge_suggestions(
        self, user_uid: str, entity_uid: str | None = None
    ) -> Result[dict[str, Any]]:
        """Generate knowledge suggestions from entity patterns."""
        return await self.knowledge_intelligence.get_knowledge_suggestions(user_uid, entity_uid)

    async def generate_knowledge_from_entities(
        self, user_uid: str, period_days: int = 30
    ) -> Result[dict[str, Any]]:
        """Generate knowledge units from completed entities."""
        return await self.knowledge_intelligence.generate_knowledge_from_entities(
            user_uid, period_days
        )

    async def get_knowledge_prerequisites(self, entity_uid: str) -> Result[dict[str, Any]]:
        """Analyze knowledge prerequisites for an entity."""
        return await self.knowledge_intelligence.get_knowledge_prerequisites(entity_uid)

    async def get_learning_opportunities(self, user_uid: str) -> Result[dict[str, Any]]:
        """Discover learning opportunities from entity patterns."""
        return await self.knowledge_intelligence.get_learning_opportunities(user_uid)

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
    # complete_event_with_quality, miss_habit_event, create_recurring_events_for_habit,
    # get_next_habit_events
    # - Learning: get_learning_events, get_events_for_knowledge, get_events_for_learning_path,
    # create_study_session, suggest_spaced_repetition_events, create_learning_path_schedule,
    # get_knowledge_reinforcement_stats
    # - Search: search_events, get_calendar_events, get_event_history, get_events_due_soon,
    # get_overdue_events, get_events_by_status, get_events_in_range, get_prioritized_events
    # - Relationships: get_event_cross_domain_context, get_event_with_semantic_context, analyze_event_impact
    # - Intelligence: get_event_with_context, analyze_event_performance, get_event_goal_support,
    # get_event_knowledge_reinforcement, analyze_upcoming_events
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

        from core.events import CalendarEventCreated, publish_event

        event_obj = CalendarEventCreated(
            event_uid=event.uid,
            user_uid=user_context.user_uid,
            title=event.title,
            event_date=event.event_date,
            calendar_event_type=get_enum_value(event.event_type),
        )
        await publish_event(self.event_bus, event_obj, self.logger)

        # Publish KnowledgePracticedInEvent events for substance tracking
        if event_data.practices_knowledge_uids:
            from core.events.lesson_events import KnowledgePracticedInEvent

            for knowledge_uid in event_data.practices_knowledge_uids:
                knowledge_event = KnowledgePracticedInEvent(
                    knowledge_uid=knowledge_uid,
                    event_uid=event.uid,
                    user_uid=user_context.user_uid,
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

    # ========================================================================
    # QUERY LAYER
    # ========================================================================

    async def get_filtered_context(
        self,
        user_uid: str,
        status_filter: str = "scheduled",
        sort_by: str = "start_time",
    ) -> Result[ListContext]:
        """Get filtered and sorted events with pre-filter stats in a single query."""

        async def fetch_all() -> Result[list[Any]]:
            return await self.core.get_for_user_filtered(user_uid, "all")

        def apply_filters(all_events: list[Any]) -> list[Any]:
            return apply_entity_filter(all_events, status_filter, _EVENT_FILTER_CONFIG)

        return await build_filtered_context(
            fetch_all=fetch_all,
            compute_stats=_compute_event_stats,
            apply_filters=apply_filters,
            apply_sort=_apply_event_sort,
            sort_by=sort_by,
        )
