"""
Habits Intelligence Service - Pure Cypher Graph Analytics
==========================================================

Handles pure Cypher graph intelligence queries for habits.

Architecture: Shell delegates to focused mixins (graph context retrieval —
``get_with_context``, mechanism B — comes from the shared
``core.services.intelligence._core_intelligence_mixin``):
  _behavioral_signals_mixin.py — analyze_habit_performance,
                                  get_habit_knowledge_reinforcement,
                                  get_habit_goal_support
  _dual_track_mixin.py         — assess_consistency_dual_track,
                                  get_zpd_knowledge_signals
                                  (event handlers migrated to HabitEventHandlerService, March 2026)

See: /docs/architecture/ENTITY_TYPE_ARCHITECTURE.md
"""

from datetime import date, timedelta
from typing import TYPE_CHECKING, Any

from core.constants import ConfidenceLevel, QueryLimit
from core.models.enums import RecurrencePattern as HabitFrequency
from core.models.habit.habit import Habit
from core.models.habit.habit_dto import HabitDTO
from core.models.type_hints import UserUID
from core.ports.domain_protocols import HabitsOperations
from core.services.base_analytics_service import BaseAnalyticsService
from core.services.habits._behavioral_signals_mixin import _BehavioralSignalsMixin
from core.services.habits._dual_track_mixin import _DualTrackMixin
from core.services.habits.habit_relationships import HabitRelationships
from core.services.intelligence._core_intelligence_mixin import _CoreIntelligenceMixin
from core.services.knowledge.knowledge_pattern_analyzer import KnowledgePatternAnalyzer
from core.utils.dto_helpers import to_domain_model
from core.utils.result_simplified import Result

if TYPE_CHECKING:
    from core.services.cross_domain import CrossDomainQueryService
    from core.services.insight.insight_store import InsightStore
    from core.services.relationships import UnifiedRelationshipService
    from core.services.user import UserContext


class HabitsIntelligenceService(
    _CoreIntelligenceMixin,
    _BehavioralSignalsMixin,
    _DualTrackMixin,
    BaseAnalyticsService[HabitsOperations, Habit],
):
    """
    Pure Cypher graph intelligence service for habits.

    NOTE: This service extends BaseAnalyticsService (ADR-030) and has NO AI dependencies.
    It uses pure graph queries and Python calculations - no LLM or embeddings.

    Responsibilities:
    - Get habit with graph context
    - Analyze habit performance with knowledge reinforcement and goal support
    - Track knowledge practice and reinforcement
    - Dual-track consistency assessment (user vision vs system measurement)
    - ZPD knowledge signals for ZPDService
    """

    # Service name for hierarchical logging
    _service_name = "habits.intelligence"

    # Relationships are REQUIRED for this service
    _require_relationships = True

    def __init__(
        self,
        backend: HabitsOperations,
        relationship_service: "UnifiedRelationshipService[Any, Any, Any]",
        cross_domain_query: "CrossDomainQueryService",
        graph_intel=None,
        insight_store: "InsightStore | None" = None,
    ) -> None:
        """
        Initialize habits intelligence service.

        Args:
            backend: Protocol-based backend for habit operations,
            graph_intel: GraphIntelligenceService for pure Cypher analytics,
            relationship_service: UnifiedRelationshipService for specialized relationship queries (REQUIRED)
            insight_store: InsightStore for persisting event-driven insights (optional)

        Note:
            Context invalidation now happens via event-driven architecture.
            Habit events trigger user_service.invalidate_context() in bootstrap.
        """
        super().__init__(
            backend=backend,
            graph_intel=graph_intel,
            relationship_service=relationship_service,
            insight_store=insight_store,
        )
        self.cross_domain_query = cross_domain_query
        self._knowledge_analyzer = KnowledgePatternAnalyzer()

    # ========================================================================
    # INTELLIGENCEOPERATIONS PROTOCOL METHODS (January 2026)
    # These methods implement the IntelligenceOperations protocol for use
    # with IntelligenceRouteFactory.
    #
    # get_with_context is provided by the shared _CoreIntelligenceMixin
    # (mechanism B, registry-sourced via self.relationships) — NOT redefined
    # here. (Convergence Phase 1, 2B.)
    # ========================================================================

    async def get_performance_analytics(
        self, user_uid: UserUID, _period_days: int = 30
    ) -> "Result[dict[str, Any]]":
        """
        Get habit performance analytics for a user.

        Protocol method: Aggregates habit metrics over time period.
        Used by IntelligenceRouteFactory for GET /api/habits/analytics route.

        Args:
            user_uid: User UID
            _period_days: Placeholder - not yet implemented. Will filter by period when added.

        Returns:
            Result containing analytics data dict

        Note: _period_days uses underscore prefix per CLAUDE.md convention to indicate
        "API contract defined, implementation deferred". Currently calculates analytics
        over ALL habits. Future enhancement: filter by created_at within period.
        """
        # Get all habits for user
        habits_result = await self.backend.find_by(user_uid=user_uid)
        if habits_result.is_error:
            return Result.fail(habits_result)

        habits = habits_result.value or []

        # Calculate analytics
        total_habits = len(habits)
        active_habits = [h for h in habits if h.is_active]

        # Calculate average consistency (success_rate is 0.0-1.0)
        if total_habits > 0:
            avg_consistency = sum(h.success_rate for h in habits) / total_habits
        else:
            avg_consistency = 0.0

        # Calculate streak stats
        total_current_streak = sum(h.current_streak for h in habits)
        habits_with_streak = [h for h in habits if h.current_streak > 0]
        avg_streak = total_current_streak / len(habits_with_streak) if habits_with_streak else 0.0

        # Calculate at-risk habits (success_rate < 0.5)
        at_risk_habits = [h for h in active_habits if h.success_rate < 0.5]

        # Learned insights (ADR-048)
        habits_with_difficulty = [
            h for h in habits if getattr(h, "learned_difficulty_level", None) is not None
        ]
        habits_with_timing = [
            h for h in habits if getattr(h, "learned_preferred_hour", None) is not None
        ]
        on_time_rates: list[float] = [
            float(rate)
            for h in habits
            if (rate := getattr(h, "learned_on_time_rate", None)) is not None
        ]
        avg_on_time = sum(on_time_rates) / len(on_time_rates) if on_time_rates else None

        return Result.ok(
            {
                "user_uid": user_uid,
                "period_days": _period_days,
                "total_habits": total_habits,
                "active_habits": len(active_habits),
                "habits_with_streak": len(habits_with_streak),
                "at_risk_habits": len(at_risk_habits),
                "avg_consistency": round(avg_consistency, 2),
                "avg_streak": round(avg_streak, 1),
                "analytics": {
                    "total": total_habits,
                    "active": len(active_habits),
                    "with_streak": len(habits_with_streak),
                    "at_risk": len(at_risk_habits),
                    "avg_consistency_percentage": round(avg_consistency * 100, 1),
                    "total_current_streak_days": total_current_streak,
                },
                "learned_insights": {
                    "habits_with_difficulty": len(habits_with_difficulty),
                    "habits_with_timing_data": len(habits_with_timing),
                    "avg_on_time_rate": round(avg_on_time, 4) if avg_on_time is not None else None,
                },
            }
        )

    async def get_domain_insights(
        self, uid: str, min_confidence: float = ConfidenceLevel.MEDIUM
    ) -> "Result[dict[str, Any]]":
        """
        Get domain-specific insights for a habit.

        Protocol method: Maps to analyze_habit_performance.
        Used by IntelligenceRouteFactory for GET /api/habits/insights route.

        Args:
            uid: Habit UID
            min_confidence: Minimum confidence threshold (default: 0.7)

        Returns:
            Result containing insights data dict
        """
        return await self.analyze_habit_performance(uid, min_confidence)

    # ========================================================================
    # EVENT SCHEDULING INTELLIGENCE
    # Migrated from HabitsEventIntegrationService (April 2026).
    # Read-only UserContext intelligence and recurrence logic belong here,
    # not in a standalone integration service.
    # ========================================================================

    async def get_event_uids_for_habit(  # skuel-lint: disable=SKUEL029 -- facade-delegated: habits_service awaits this via delegation (facade uniformity)
        self, habit_uid: str, user_context: "UserContext", _days_ahead: int = 7
    ) -> "Result[list[str]]":
        """
        Get upcoming event UIDs that reinforce a specific habit.

        Reads from UserContext.events_by_habit — no Neo4j query.

        Args:
            habit_uid: UID of the habit
            user_context: User context with event mappings
            _days_ahead: Placeholder — filtering is done via upcoming_event_uids

        Returns:
            Result containing list of event UIDs
        """
        if habit_uid not in user_context.events_by_habit:
            return Result.ok([])

        event_uids = user_context.events_by_habit[habit_uid]
        upcoming = [uid for uid in event_uids if uid in user_context.upcoming_event_uids]
        return Result.ok(upcoming)

    async def schedule_events_for_habit(
        self, habit_uid: str, _user_context: "UserContext", days_to_schedule: int = 7
    ) -> "Result[list[dict[str, Any]]]":
        """
        Generate event suggestion templates for maintaining a habit.

        Returns dicts that EventsService can use to create actual Event entities.
        Does NOT create events — that is EventsService's responsibility.

        DESIGN DECISION — Knowledge UIDs Intentionally Omitted (Graph-Native):
        Event suggestions do NOT include `practices_knowledge_uids` even though
        habits may have knowledge reinforcement relationships in the graph.
        EventsService handles relationship wiring when converting suggestion → Event.

        Args:
            habit_uid: UID of the habit
            _user_context: User context (reserved for future filtering)
            days_to_schedule: Number of days to generate suggestions for

        Returns:
            Result containing list of event suggestion dicts
        """
        habit_result = await self.backend.get_habit(habit_uid)
        if habit_result.is_error:
            return Result.fail(habit_result)

        habit = to_domain_model(habit_result.value, HabitDTO, Habit)

        event_suggestions = []
        start_date = date.today()

        for day_offset in range(days_to_schedule):
            event_date = start_date + timedelta(days=day_offset)
            if self._should_occur_on_date(habit, event_date):
                event_suggestions.append(
                    {
                        "title": habit.title,
                        "description": f"Maintain {habit.title} habit",
                        "reinforces_habit_uid": habit_uid,
                        "event_date": event_date.isoformat(),
                        "duration_minutes": habit.duration_minutes,
                        "recurrence_maintains_habit": True,
                        "skip_breaks_habit_streak": True,
                        "habit_completion_quality": None,
                        "tags": ["habit", *list(habit.tags if habit.tags else [])],
                    }
                )

        return Result.ok(event_suggestions)

    def _should_occur_on_date(self, habit: Habit, check_date: date) -> bool:
        """
        Check if a habit should occur on a specific date based on its recurrence pattern.

        Args:
            habit: Habit domain model
            check_date: Date to check

        Returns:
            True if the habit should occur on this date
        """
        if habit.recurrence_pattern == HabitFrequency.DAILY:
            return True
        elif habit.recurrence_pattern == HabitFrequency.WEEKDAYS:
            return check_date.weekday() < 5
        elif habit.recurrence_pattern == HabitFrequency.WEEKENDS:
            return check_date.weekday() >= 5
        elif habit.recurrence_pattern == HabitFrequency.WEEKLY:
            # GRAPH-NATIVE: Simplified — occurs once per week
            if habit.started_at:
                days_since_start = (check_date - habit.started_at.date()).days
                return days_since_start % 7 == 0
            return check_date.weekday() == 0  # Default to Monday
        elif habit.recurrence_pattern == HabitFrequency.CUSTOM:
            # GRAPH-NATIVE: Custom patterns not supported in simplified check
            return False
        return False

    async def analyze_learning_patterns(
        self, user_uid: UserUID, timeframe_days: int = 30
    ) -> "Result[list[Any]]":
        """Detect knowledge-learning patterns across the user's habit activities."""
        entities_result = await self.backend.find_by(user_uid=user_uid, limit=QueryLimit.MAXIMUM)
        if entities_result.is_error:
            return Result.fail(entities_result)

        service = self.relationships

        async def _fetch_habit_rels(uid: str) -> HabitRelationships:
            if service:
                return await HabitRelationships.fetch(uid, service)
            return HabitRelationships.empty()

        return await self._knowledge_analyzer.analyze_learning_patterns(
            entities_result.value, _fetch_habit_rels, timeframe_days
        )
