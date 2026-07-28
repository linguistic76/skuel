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
- EventEventHandlerService: Event-driven reactive logic (attendance patterns, rescheduling, density)
- EventsIntelligenceService: Pure Cypher analytics

Facade Mixins (extracted April 2026):
- _OrchestrationMixin: Status management, attendee management, cross-domain linking,
                       context-aware event creation
- _SchedulingMixin: Conflict detection, recurring instance creation
"""

from __future__ import annotations

import dataclasses
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from datetime import date, time

from core.events import publish_event
from core.events.calendar_event_events import CalendarEventUpdated
from core.models.enums import EntityStatus, RecurrencePattern
from core.models.event.event import Event
from core.models.event.event_dto import EventDTO
from core.models.event.event_request import EventCreateRequest
from core.models.event.event_update_intent import EventUpdateIntent
from core.models.sentinels import UNSET, Unset
from core.models.type_hints import EntityUID, UserUID
from core.ports import get_enum_attr_str
from core.services.activity_domain_config import CommonSubServices, create_common_sub_services
from core.services.base_service import BaseService
from core.services.cross_domain.cross_domain_query_service import CrossDomainQueryService
from core.services.domain_config import create_activity_domain_config

# Import sub-services
from core.services.events import (
    EventEventHandlerService,
    EventsCoreService,
    EventsHabitIntegrationService,
    EventsIntelligenceService,
    EventsLearningService,
    EventsProgressService,
    EventsSchedulingService,
    EventsSearchService,
)
from core.services.events._orchestration_mixin import _OrchestrationMixin
from core.services.events._scheduling_mixin import _SchedulingMixin
from core.services.filtered_context import build_filtered_context
from core.services.infrastructure.graph_intelligence_service import GraphIntelligenceService
from core.services.mixins import KnowledgeIntelligenceDelegationMixin

# Unified relationship service
from core.services.relationships import UnifiedRelationshipService
from core.utils.activity_stats import compute_event_stats
from core.utils.list_helpers import (
    FilterConfig,
    SortConfig,
    apply_entity_filter,
    apply_entity_sort,
    get_event_sort_datetime,
)
from core.utils.logging import get_logger
from core.utils.result_simplified import Result
from core.utils.sort_functions import get_created_at_attr, get_title_lower

if TYPE_CHECKING:
    from core.models.pathways.lp_position import LpPosition
    from core.ports.domain_protocols import EventsOperations
    from core.ports.infrastructure_protocols import EventBusOperations
    from core.ports.intelligence_protocols import KnowledgeIntelligenceOperations
    from core.ports.query_types import ListContext
    from core.ports.search_protocols import EventsSearchOperations
    from core.services.events.events_ai_service import EventsAIService
    from core.services.insight.insight_store import InsightStore
    from core.services.user import UserContext


def _get_event_status_value(event: Any) -> str:
    """Get status value (handles both enum and string)."""
    return get_enum_attr_str(event, "status", "scheduled")


def _compute_event_stats(all_events: list[Any]) -> dict[str, int | float]:
    """Dict projection of EventStats for the cross-domain ListContext contract."""
    s = compute_event_stats(all_events)
    return {
        "total": s.total,
        "active": s.active,
        "scheduled": s.scheduled,
        "today": s.today,
    }


def _is_event_scheduled(e: Any) -> bool:
    """Filter predicate: event is scheduled."""
    return _get_event_status_value(e) == "scheduled"


def _is_event_completed(e: Any) -> bool:
    """Filter predicate: event is completed."""
    return _get_event_status_value(e) == EntityStatus.COMPLETED


def _is_event_cancelled(e: Any) -> bool:
    """Filter predicate: event is cancelled."""
    return _get_event_status_value(e) == EntityStatus.CANCELLED


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


class EventsService(
    _OrchestrationMixin,
    _SchedulingMixin,
    KnowledgeIntelligenceDelegationMixin,
    BaseService["EventsOperations", Event, EventUpdateIntent],
):
    """
    Events service facade with specialized sub-services.

    This facade:
    1. Delegates to 10 specialized sub-services for core operations
    2. Uses explicit delegation methods (~50 methods) for sub-service access
    3. Complex domain logic provided by two facade mixins (April 2026)

    Delegations (explicit methods):
    - Core CRUD: get_event, get_user_events, find_events, count_events
    - Habits: get_events_for_habit, get_habit_reinforcement_events, etc.
    - Learning: get_learning_events, create_study_session, create_learning_path_schedule
    - Search: get_calendar_events, get_upcoming, get_overdue, etc.
    - Intelligence: analyze_event_performance, etc.
    - Scheduling: optimize_recurring_schedule, create_recurring_events

    Via _OrchestrationMixin:
    - Attendees: add_attendee, remove_attendee, get_event_attendees
    - Linking: link_event_to_goal, link_event_to_habit, link_event_to_knowledge
    - Creation: create_event_with_context

    Via _SchedulingMixin:
    - check_conflicts, create_recurring_instances, get_recurring_events

    Status transitions go through the one update path — the generic status API
    route calls ``update_event(uid, EventUpdateIntent(status=...))`` (events_api.py).

    Cross-domain scheduling (get_busy_times, get_calendar_density, suggest_time_slots,
    find_next_available_slot, check_conflicts by time slot) lives in
    CalendarOptimizationOrchestrator — it sees Tasks + Events together.
    """

    # ========================================================================
    # DOMAIN CONFIGURATION (DomainConfig - January 2026)
    # ========================================================================
    # Facade services use same config as core/search sub-services
    _config = create_activity_domain_config(
        dto_class=EventDTO,
        model_class=Event,
        domain_name="events",
        date_field="event_date",
        completed_statuses=(EntityStatus.COMPLETED.value,),
    )

    # ========================================================================
    # CLASS-LEVEL TYPE ANNOTATIONS
    # ========================================================================
    core: EventsCoreService
    search: EventsSearchService  # type: ignore[assignment]  # search service implements callable protocol
    habits: EventsHabitIntegrationService
    learning: EventsLearningService
    progress: EventsProgressService
    scheduling: EventsSchedulingService
    relationships: UnifiedRelationshipService
    event_handler: EventEventHandlerService
    intelligence: EventsIntelligenceService

    # ========================================================================
    # DELEGATION METHODS
    # ========================================================================

    # Core CRUD delegations
    async def get_event(self, event_uid: str) -> Result[Event]:
        return await self.core.get_event(event_uid)

    async def get_user_events(self, user_uid: UserUID) -> Result[list[Event]]:
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

    async def create_event(self, request: EventCreateRequest, user_uid: UserUID) -> Result[Event]:
        """Create an event from a validated request."""
        validation = self.core._validate_required_user_uid(user_uid, "event creation")
        if validation.is_error:
            return Result.fail(validation)

        from core.utils.uid_generator import UIDGenerator

        event = Event(
            uid=UIDGenerator.generate_uid("event", request.title),
            user_uid=user_uid,
            title=request.title,
            description=request.description,
            event_date=request.event_date,
            start_time=request.start_time,
            end_time=request.end_time,
            event_type=request.event_type,
            visibility=request.visibility,
            location=request.location,
            is_online=request.is_online,
            meeting_url=request.meeting_url,
            tags=tuple(request.tags),
            priority=request.priority,
            attendee_emails=tuple(request.attendee_emails),
            max_attendees=request.max_attendees,
            recurrence_pattern=request.recurrence_pattern,
            recurrence_end_date=request.recurrence_end_date,
            reminder_minutes=request.reminder_minutes,
            habit_completion_quality=request.habit_completion_quality,
            knowledge_retention_check=request.knowledge_retention_check,
        )
        created = await self.core.create(event)
        if created.is_error:
            return created

        # Cross-domain linkages are graph edges, not properties — write them
        # after node creation: (Event)-[:CELEBRATES_GOAL]->(Goal) and
        # (Event)-[:REINFORCES_HABIT]->(Habit).
        if request.milestone_celebration_for_goal:
            edge = await self.relationships.create_relationship(
                "celebrated_goals", created.value.uid, request.milestone_celebration_for_goal
            )
            if edge.is_error:
                return Result.fail(edge)
        if request.reinforces_habit_uid:
            edge = await self.relationships.create_relationship(
                "habits", created.value.uid, request.reinforces_habit_uid
            )
            if edge.is_error:
                return Result.fail(edge)
        return created

    # ------------------------------------------------------------------------
    # Update path (ADR-066 typed update contract)
    # ------------------------------------------------------------------------
    # Events, like Tasks, carry edge-typed fields on the update path. The backend update
    # does an unfiltered `SET n += $changes`, so an edge field left in the property patch
    # would write a junk denormalized property onto the node AND skip the edge — the very
    # split the ADR-035/ADR-065 graph-native migration removed.
    @staticmethod
    def _split_relationship_intent(
        intent: EventUpdateIntent,
    ) -> tuple[str | None | Unset, str | None | Unset, EventUpdateIntent]:
        """Split the two edge-typed fields off an ``EventUpdateIntent``.

        Returns ``(goal_uid, habit_uid, prop_intent)`` where ``prop_intent`` is the same
        intent with both edge fields reset to ``UNSET`` (so its ``to_changes()`` carries
        only node properties). The edge values pass through with the canonical ADR-066
        contract intact — ``UNSET`` = not in this update (untouched), ``None`` = explicit
        clear, value = set — which ``update_event`` / ``_replace_edge`` consume.
        """
        prop_intent = dataclasses.replace(
            intent, milestone_celebration_for_goal=UNSET, reinforces_habit_uid=UNSET
        )
        return intent.milestone_celebration_for_goal, intent.reinforces_habit_uid, prop_intent

    async def _publish_edge_only_update(
        self, event: Event, goal_uid: str | None | Unset, habit_uid: str | None | Unset
    ) -> None:
        """Publish CalendarEventUpdated after an edge-only update so user-context caches
        invalidate.

        Property updates publish CalendarEventUpdated via EventsCoreService.update_event,
        but the relationship-only path bypasses it (fetch-only) — without this, rich context
        (entities_rich, celebrated-goal / reinforced-habit links) stays stale until the
        cache TTL expires. CalendarEventUpdated is wired to context invalidation in
        _event_wiring.py.
        """
        changed_fields = {
            name: value
            for name, value in (
                ("milestone_celebration_for_goal", goal_uid),
                ("reinforces_habit_uid", habit_uid),
            )
            if value is not UNSET
        }
        event_obj = CalendarEventUpdated(
            event_uid=event.uid, user_uid=event.user_uid, updated_fields=changed_fields
        )
        await publish_event(self.event_bus, event_obj, self.logger)

    async def update_event(self, event_uid: str, intent: EventUpdateIntent) -> Result[Event]:
        """THE Events update path (ADR-066). Splits the two edge-typed fields off the
        intent, writes node properties via core (events fire), and replaces the
        ``CELEBRATES_GOAL`` / ``REINFORCES_HABIT`` edges. See ``_replace_edge``."""
        goal_uid, habit_uid, prop_intent = self._split_relationship_intent(intent)

        # An edge-only update (e.g. only milestone_celebration_for_goal, which
        # EventUpdateRequest permits) leaves no node properties to write. The backend
        # rejects an empty update dict, so fetch the event to confirm it exists and to have
        # an Event to return. A genuinely empty call keeps the validation error.
        wrote_properties = bool(prop_intent.to_changes()) or (
            goal_uid is UNSET and habit_uid is UNSET
        )
        if wrote_properties:
            result = await self.core.update_event(event_uid, prop_intent)
        else:
            result = await self.core.get_event(event_uid)
        if result.is_error:
            return result

        if goal_uid is not UNSET:
            replaced = await self._replace_edge("celebrated_goals", event_uid, goal_uid)
            if replaced.is_error:
                return Result.fail(replaced)
        if habit_uid is not UNSET:
            replaced = await self._replace_edge("habits", event_uid, habit_uid)
            if replaced.is_error:
                return Result.fail(replaced)

        if not wrote_properties:  # edge-only: core.update_event didn't fire CalendarEventUpdated
            await self._publish_edge_only_update(result.value, goal_uid, habit_uid)
        return result

    async def update(self, uid: str, updates: EventUpdateIntent) -> Result[Event]:
        """Override the inherited CRUD update (generated JSON route, no ownership check).

        Routes the typed intent through the one update path (``update_event``), which fires
        events and splits edges — the inherited base ``update`` would write edge fields as
        junk node properties and skip the edge replacement."""
        return await self.update_event(uid, updates)

    async def update_for_user(
        self, uid: str, updates: EventUpdateIntent, user_uid: UserUID
    ) -> Result[Event]:
        """Override the inherited ownership-verified CRUD update (generated JSON route).

        Verifies ownership BEFORE any mutation, then routes through the one update path
        (``update_event``)."""
        ownership = await self.verify_ownership(uid, user_uid)
        if ownership.is_error:
            return ownership
        return await self.update_event(uid, updates)

    async def _replace_edge(
        self, relationship_key: str, event_uid: str, target_uid: str | None
    ) -> Result[bool]:
        """Replace the single outbound edge of ``relationship_key`` with ``target_uid``.

        A falsy ``target_uid`` (``None`` — the explicit-clear signal) clears the edge
        (delete only). Used by update_event to route cross-domain field updates to
        graph-edge mutations.
        """
        existing = await self.relationships.get_related_uids(relationship_key, EntityUID(event_uid))
        if existing.is_ok:
            for old_uid in existing.value or []:
                await self.relationships.delete_relationship(relationship_key, event_uid, old_uid)
        if target_uid:  # non-empty → create the new edge (None = cleared)
            return await self.relationships.create_relationship(
                relationship_key, event_uid, target_uid
            )
        return Result.ok(True)

    async def get_celebrated_goal(self, event_uid: str) -> Result[str | None]:
        """Return the goal uid this event celebrates via (Event)-[:CELEBRATES_GOAL]->(Goal).

        An event celebrates at most one goal milestone, so this returns the first
        linked goal uid or ``None``. Graph-native — the linkage is the edge, not a
        property on the event.
        """
        related = await self.relationships.get_related_uids(
            "celebrated_goals", EntityUID(event_uid)
        )
        if related.is_error:
            return Result.fail(related)
        uids = related.value or []
        return Result.ok(uids[0] if uids else None)

    async def get_reinforced_habit(self, event_uid: str) -> Result[str | None]:
        """Return the habit uid this event reinforces via (Event)-[:REINFORCES_HABIT]->(Habit).

        An event reinforces at most one habit, so this returns the first linked
        habit uid or ``None``. Graph-native — the linkage is the edge, not a property.
        """
        related = await self.relationships.get_related_uids("habits", EntityUID(event_uid))
        if related.is_error:
            return Result.fail(related)
        uids = related.value or []
        return Result.ok(uids[0] if uids else None)

    async def get_user_items_in_range(
        self,
        user_uid: UserUID,
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
    async def get_learning_events(
        self, user_uid: UserUID, days_ahead: int = 7
    ) -> Result[list[Event]]:
        return await self.learning.get_learning_events(user_uid, days_ahead)

    async def create_study_session(
        self,
        user_uid: UserUID,
        knowledge_uids: list[str],
        event_date: date,
        duration_minutes: int = 60,
        title: str | None = None,
    ) -> Result[Event]:
        return await self.learning.create_study_session(
            user_uid, knowledge_uids, event_date, duration_minutes, title
        )

    async def suggest_spaced_repetition_events(
        self,
        _user_uid: UserUID,
        knowledge_uid: str,
        mastery_level: float = 0.5,
        days_to_schedule: int = 30,
    ) -> Result[list[dict[str, Any]]]:
        return await self.learning.suggest_spaced_repetition_events(
            _user_uid, knowledge_uid, mastery_level, days_to_schedule
        )

    async def create_learning_path_schedule(
        self,
        user_uid: UserUID,
        learning_path_uid: str,
        _learning_position: LpPosition,
        study_hours_per_week: int = 5,
    ) -> Result[list[Event]]:
        return await self.learning.create_learning_path_schedule(
            user_uid, learning_path_uid, _learning_position, study_hours_per_week
        )

    # Search delegations
    async def get_calendar_events(
        self,
        user_uid: UserUID,
        start_date: date | None = None,
        end_date: date | None = None,
        limit: int = 100,
    ) -> Result[list[Event]]:
        return await self.search.get_calendar_events(user_uid, start_date, end_date, limit)

    async def get_upcoming(
        self, days_ahead: int = 7, user_uid: UserUID | None = None, limit: int = 100
    ) -> Result[list[Event]]:
        return await self.search.get_upcoming(days_ahead, user_uid, limit)

    async def get_overdue(
        self, user_uid: UserUID | None = None, limit: int = 100
    ) -> Result[list[Event]]:
        return await self.search.get_overdue(user_uid, limit)

    async def get_active(self, user_uid: UserUID, limit: int = 100) -> Result[list[Event]]:
        return await self.search.get_active(user_uid, limit)

    async def get_events_in_range(
        self,
        start_date: date,
        end_date: date,
        user_uid: UserUID | None = None,
        limit: int = 100,
    ) -> Result[list[Event]]:
        return await self.search.get_in_range(start_date, end_date, user_uid, limit)

    async def get_upcoming_events_for_user(
        self,
        context: UserContext,
        limit: int = 5,
    ) -> Result[list[Event]]:
        """Today's events for the daily plan P2 slot."""
        return await self.get_upcoming(days_ahead=1, user_uid=context.user_uid, limit=limit)

    # Intelligence delegations
    async def analyze_event_performance(self, uid: str) -> Result[dict[str, Any]]:
        return await self.intelligence.analyze_event_performance(uid)

    async def analyze_upcoming_events(
        self, user_uid: UserUID, days_ahead: int = 7
    ) -> Result[dict[str, Any]]:
        return await self.intelligence.analyze_upcoming_events(user_uid, days_ahead)

    async def analyze_learning_patterns(
        self, user_uid: UserUID, timeframe_days: int = 30
    ) -> Result[list[Any]]:
        return await self.intelligence.analyze_learning_patterns(user_uid, timeframe_days)

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
        self, user_uid: UserUID, period_days: int = 30
    ) -> Result[dict[str, Any]]:
        return await self.progress.get_attendance_rate(user_uid, period_days)

    async def get_quality_trends(
        self, user_uid: UserUID, period_days: int = 30
    ) -> Result[dict[str, Any]]:
        return await self.progress.get_quality_trends(user_uid, period_days)

    async def get_goal_contribution_metrics(
        self, user_uid: UserUID, period_days: int = 30
    ) -> Result[dict[str, Any]]:
        return await self.progress.get_goal_contribution_metrics(user_uid, period_days)

    async def get_weekly_summary(
        self, user_uid: UserUID, weeks_back: int = 4
    ) -> Result[dict[str, Any]]:
        return await self.progress.get_weekly_summary(user_uid, weeks_back)

    async def get_habit_event_stats(
        self, user_uid: UserUID, period_days: int = 30
    ) -> Result[dict[str, Any]]:
        return await self.progress.get_habit_event_stats(user_uid, period_days)

    # Scheduling delegations
    async def optimize_recurring_schedule(
        self,
        user_uid: UserUID,
        pattern: RecurrencePattern,
        preferred_time: time | None = None,
        days_to_schedule: int = 30,
    ) -> Result[list[date]]:
        return await self.scheduling.optimize_recurring_schedule(
            user_uid, pattern, preferred_time, days_to_schedule
        )

    async def create_recurring_events(
        self,
        user_uid: UserUID,
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

    def __init__(
        self,
        backend: EventsOperations,
        graph_intel: GraphIntelligenceService,
        cross_domain_query: CrossDomainQueryService,
        event_bus: EventBusOperations | None = None,
        insight_store: InsightStore | None = None,
        activity_knowledge_intelligence: KnowledgeIntelligenceOperations | None = None,
        ai_service: EventsAIService | None = None,
    ) -> None:
        """
        Initialize enhanced events service with specialized sub-services.

        Args:
            backend: Protocol-based backend for event operations
            graph_intel: GraphIntelligenceService for pure Cypher analytics (REQUIRED)
            cross_domain_query: CrossDomainQueryService for batch cross-domain reads (REQUIRED)
            event_bus: Event bus for publishing domain events (optional)
        """
        super().__init__(backend, "events")

        self.graph_intel = graph_intel
        self.event_bus = event_bus
        # Optional AI service (ADR-030: AI features are optional)
        self.ai: EventsAIService | None = ai_service
        self.logger = get_logger("skuel.services.events")  # structlog BoundLogger

        # Initialize core, search, relationships, event_handler, learning, and
        # knowledge_intelligence via factory; intelligence is created manually
        # to pass cross_domain_query.
        common: CommonSubServices[
            EventsCoreService, EventsSearchOperations, EventsIntelligenceService
        ] = create_common_sub_services(
            domain="events",
            backend=backend,
            graph_intel=graph_intel,
            event_bus=event_bus,
            insight_store=insight_store,
            activity_knowledge_intelligence=activity_knowledge_intelligence,
        )
        assert common.core is not None  # 'core' not in skip
        assert common.search is not None  # 'search' not in skip
        assert common.relationships is not None  # 'relationships' not in skip
        self.core = common.core
        self.search: EventsSearchOperations = common.search  # type: ignore[assignment]  # class-level attr declared as concrete EventsSearchService, local var matches protocol
        self.relationships: UnifiedRelationshipService = common.relationships
        self.intelligence: EventsIntelligenceService = EventsIntelligenceService(
            backend=backend,
            graph_intel=graph_intel,
            relationship_service=self.relationships,  # UnifiedRelationshipService satisfies protocol
            cross_domain_query=cross_domain_query,
            insight_store=insight_store,
        )

        # Domain-specific sub-services (not common to all facades)
        self.habits = EventsHabitIntegrationService(backend=backend, event_bus=event_bus)
        self.learning: EventsLearningService = common.learning
        self.progress = EventsProgressService(backend=backend, event_bus=event_bus)
        self.scheduling = EventsSchedulingService(backend=backend, event_bus=event_bus)

        # Event-driven handler from factory
        self.event_handler: EventEventHandlerService = common.event_handler

        # Knowledge intelligence (shared singleton — domain-agnostic)
        self.knowledge_intelligence = common.knowledge_intelligence  # always passed by bootstrap

        self.logger.info(
            "EventsService facade initialized with 10 sub-services: "
            "core, search, habits, learning, progress, scheduling, relationships, "
            "event_handler, intelligence, knowledge_intelligence"
        )

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
    # - Learning: get_learning_events, create_study_session,
    # suggest_spaced_repetition_events, create_learning_path_schedule
    # - Search: get_calendar_events, get_upcoming, get_overdue,
    # get_active, get_events_in_range
    # - Intelligence: analyze_event_performance, analyze_upcoming_events
    # ========================================================================

    # ========================================================================
    # HIERARCHY DELEGATIONS
    # ========================================================================

    async def get_subevents(self, parent_uid: str, depth: int = 1) -> Result[list[Event]]:
        return await self.core.get_subentities(parent_uid, depth)

    async def get_parent_event(self, subevent_uid: str) -> Result[Event | None]:
        return await self.core.get_parent_entity(subevent_uid)

    async def get_event_hierarchy(self, event_uid: str) -> Result[dict[str, Any]]:
        return await self.core.get_entity_hierarchy(event_uid)

    async def create_subevent_relationship(self, parent_uid: str, child_uid: str) -> Result[bool]:
        return await self.core.create_subevent_relationship(parent_uid, child_uid)

    async def remove_subevent_relationship(self, parent_uid: str, child_uid: str) -> Result[bool]:
        return await self.core.remove_subevent_relationship(parent_uid, child_uid)

    # ========================================================================
    # QUERY LAYER
    # ========================================================================
    # Graph relationships, attendee management, recurring instances, and
    # context-aware creation are provided by:
    #   _OrchestrationMixin  (attendees, linking, create_event_with_context)
    #   _SchedulingMixin     (check_conflicts, create_recurring_instances, get_recurring_events)

    async def get_filtered_context(
        self,
        user_uid: UserUID,
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
