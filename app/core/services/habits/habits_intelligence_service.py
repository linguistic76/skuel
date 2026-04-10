"""
Habits Intelligence Service - Pure Cypher Graph Analytics
==========================================================

Handles pure Cypher graph intelligence queries for habits.

Architecture: Shell delegates to 3 focused mixins in the same directory:
  _core_intelligence_mixin.py  — get_habit_with_context
  _behavioral_signals_mixin.py — analyze_habit_performance,
                                  get_habit_knowledge_reinforcement,
                                  get_habit_goal_support
  _dual_track_mixin.py         — assess_consistency_dual_track,
                                  get_zpd_knowledge_signals
                                  (event handlers migrated to HabitEventHandlerService, March 2026)

See: /docs/architecture/ENTITY_TYPE_ARCHITECTURE.md
"""

from typing import TYPE_CHECKING, Any

from core.constants import ConfidenceLevel
from core.models.enums import Domain
from core.models.habit.habit import Habit
from core.models.habit.habit_dto import HabitDTO
from core.models.type_hints import UserUID
from core.ports.domain_protocols import HabitsOperations
from core.services.base_analytics_service import BaseAnalyticsService
from core.services.habits._behavioral_signals_mixin import _BehavioralSignalsMixin
from core.services.habits._core_intelligence_mixin import _CoreIntelligenceMixin
from core.services.habits._dual_track_mixin import _DualTrackMixin
from core.services.intelligence import GraphContextOrchestrator
from core.utils.result_simplified import Result

if TYPE_CHECKING:
    from core.models.graph_context import GraphContext
    from core.ports.domain_protocols import HabitsRelationshipOperations
    from core.services.cross_domain import CrossDomainQueryService
    from core.services.insight.insight_store import InsightStore


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
        relationship_service: "HabitsRelationshipOperations",
        cross_domain_query: "CrossDomainQueryService",
        graph_intelligence_service=None,
        insight_store: "InsightStore | None" = None,
    ) -> None:
        """
        Initialize habits intelligence service.

        Args:
            backend: Protocol-based backend for habit operations,
            graph_intelligence_service: GraphIntelligenceService for pure Cypher analytics,
            relationship_service: HabitsRelationshipOperations protocol for specialized relationship queries (REQUIRED)
            insight_store: InsightStore for persisting event-driven insights (optional)

        Note:
            Context invalidation now happens via event-driven architecture.
            Habit events trigger user_service.invalidate_context() in bootstrap.
        """
        super().__init__(
            backend=backend,
            graph_intelligence_service=graph_intelligence_service,
            relationship_service=relationship_service,
            insight_store=insight_store,
        )
        self.cross_domain_query = cross_domain_query

        # Initialize GraphContextOrchestrator for generic get_with_context pattern
        if graph_intelligence_service:
            self.orchestrator = GraphContextOrchestrator[Habit, HabitDTO](
                service=self,
                backend_get_method="get_habit",
                dto_class=HabitDTO,
                model_class=Habit,
                domain=Domain.HABITS,
            )

    # ========================================================================
    # DOMAIN-SPECIFIC CONTRACT
    # ========================================================================

    @property
    def entity_label(self) -> str:
        """Return the graph label for Habit entities."""
        return "Habit"

    # ========================================================================
    # INTELLIGENCEOPERATIONS PROTOCOL METHODS (January 2026)
    # These methods implement the IntelligenceOperations protocol for use
    # with IntelligenceRouteFactory.
    # ========================================================================

    async def get_with_context(
        self, uid: str, depth: int = 2
    ) -> "Result[tuple[Habit, GraphContext]]":
        """
        Get habit with full graph context.

        Protocol method: Maps to get_habit_with_context.
        Used by IntelligenceRouteFactory for GET /api/habits/context route.

        Args:
            uid: Habit UID
            depth: Graph traversal depth (default: 2)

        Returns:
            Result containing (Habit, GraphContext) tuple
        """
        return await self.get_habit_with_context(uid, depth)

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
        on_time_rates = [
            getattr(h, "learned_on_time_rate", None)
            for h in habits
            if getattr(h, "learned_on_time_rate", None) is not None
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
