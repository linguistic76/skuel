"""
Goals Intelligence Service
===========================

Handles pure Cypher graph intelligence queries for goals.

Architecture: Shell delegates to focused mixins (graph context retrieval —
``get_with_context``, mechanism B — comes from the shared
``core.services.intelligence._core_intelligence_mixin``):
  _analytics_mixin.py               — get_goal_progress_dashboard, get_goal_completion_forecast,
                                       get_goal_learning_requirements
  _predictive_mixin.py              — predict_goal_success, analyze_habit_impact,
                                       assess_goal_risk, run_scenario_analysis
  _dual_track_mixin.py              — assess_progress_dual_track

See: /docs/architecture/ENTITY_TYPE_ARCHITECTURE.md
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from typing import TYPE_CHECKING, Any

from core.constants import QueryLimit
from core.models.goal.goal import Goal
from core.models.type_hints import UserUID
from core.ports.domain_protocols import GoalsOperations
from core.services.base_analytics_service import BaseAnalyticsService
from core.services.goals._analytics_mixin import _AnalyticsMixin
from core.services.goals._dual_track_mixin import _DualTrackMixin
from core.services.goals._predictive_mixin import _PredictiveMixin
from core.services.goals.goal_relationships import GoalRelationships
from core.services.intelligence._core_intelligence_mixin import _CoreIntelligenceMixin
from core.services.knowledge.knowledge_pattern_analyzer import KnowledgePatternAnalyzer
from core.utils.logging import get_logger
from core.utils.result_simplified import Result

if TYPE_CHECKING:
    from core.ports.domain_protocols import HabitsOperations
    from core.services.insight.insight_store import InsightStore
    from core.services.relationships import UnifiedRelationshipService

logger = get_logger(__name__)


# ============================================================================
# PREDICTIVE ANALYTICS DATA CLASSES (merged from GoalAnalyticsService)
# ============================================================================


@dataclass
class GoalPrediction:
    """Prediction for a goal's success."""

    goal_uid: str
    goal_title: str
    success_probability: float  # 0.0 to 1.0
    predicted_completion_date: date | None
    confidence_level: str  # "high", "medium", "low"
    risk_factors: list[str]
    success_factors: list[str]
    recommended_actions: list[str]
    trend: str  # "improving", "stable", "declining"

    @property
    def risk_level(self) -> str:
        """Classify risk based on success probability."""
        if self.success_probability < 0.5:
            return "high"
        if self.success_probability < 0.75:
            return "medium"
        return "low"


@dataclass
class HabitImpactAnalysis:
    """Analysis of a habit's impact on goal success."""

    habit_uid: str
    habit_title: str
    impact_score: float  # 0.0 to 1.0
    criticality: str  # "critical", "important", "supportive"
    current_consistency: float
    required_consistency: float
    consistency_gap: float


class GoalsIntelligenceService(
    _CoreIntelligenceMixin,
    _AnalyticsMixin,
    _PredictiveMixin,
    _DualTrackMixin,
    BaseAnalyticsService[GoalsOperations, Goal],
):
    """
    Graph intelligence service for goals using pure Cypher graph intelligence.

    NOTE: This service extends BaseAnalyticsService (ADR-030) and has NO AI dependencies.
    It uses pure graph queries and Python calculations - no LLM or embeddings.

    Handles:
    - Pure Cypher context retrieval (_CoreIntelligenceMixin)
    - Comprehensive progress dashboards, forecasts, learning requirements (_AnalyticsMixin)
    - Predictive analytics: success probability, habit impact, scenarios (_PredictiveMixin)
    - Dual-track assessment: user vision vs system measurement (_DualTrackMixin)
    """

    # Service name for hierarchical logging
    _service_name = "goals.intelligence"

    # Relationships are REQUIRED for this service
    _require_relationships = True

    def __init__(
        self,
        backend: GoalsOperations,
        graph_intel=None,
        relationship_service: UnifiedRelationshipService[Any, Any, Any] | None = None,
        progress_service=None,
        insight_store: InsightStore | None = None,
    ) -> None:
        """
        Initialize goals intelligence service.

        Args:
            backend: Protocol-based backend for goal operations,
            graph_intel: GraphIntelligenceService for graph intelligence queries,
            relationship_service: UnifiedRelationshipService for fetching (REQUIRED) goal relationships
            progress_service: GoalsProgressService for velocity calculations
            insight_store: For persisting event-driven insights (optional)
        """
        super().__init__(
            backend=backend,
            graph_intel=graph_intel,
            relationship_service=relationship_service,
            insight_store=insight_store,
        )
        self.progress = progress_service  # Domain-specific: for velocity calculations
        self.habits_service: HabitsOperations | None = None  # Post-wired cross-domain dep
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
        self, user_uid: UserUID, period_days: int = 30
    ) -> Result[dict[str, Any]]:
        """
        Get goal performance analytics for a user.

        Protocol method: Aggregates goal metrics over time period.
        Used by IntelligenceRouteFactory for GET /api/goals/analytics route.

        The window keys off ``updated_at`` — recent *activity* on a goal, which is what a
        rolling performance report means — and is fetched with ``find_by_date_range``
        rather than ``find_by(updated_at__gte=...)``. ``updated_at`` is stored in two
        shapes: an ISO string on the CRUD write path (``_crud_mixin.py``) and a native
        temporal on the vault re-ingest path (``bulk_upsert_backend.py``, ``ON MATCH``).
        ``Goal`` carries an ``EntityIngestionConfig``, so any goal whose last write came
        from a vault sync holds the temporal shape. Only ``find_by_date_range`` coerces
        both before comparing; a bare ``>=`` against a string bound evaluates to null on
        the temporally-stored rows and drops them, under-reporting every metric below
        without raising. The coercion is day-granular, which is what reconciles this
        ``date`` bound with the ``datetime`` the field holds.

        Backend: UniversalNeo4jBackend.find_by_date_range
        """
        cutoff = date.today() - timedelta(days=period_days)
        goals_result = await self.backend.find_by_date_range(
            start_date=cutoff,
            end_date=None,
            date_field="updated_at",
            additional_filters={"user_uid": user_uid},
            limit=QueryLimit.MAXIMUM,
        )
        if goals_result.is_error:
            return Result.fail(goals_result)

        goals = goals_result.value or []
        # find_by_date_range defaults to limit=100; every metric below is a count or a
        # mean over this set, so a truncated page would understate all of them silently.
        if len(goals) >= QueryLimit.MAXIMUM:
            self.logger.warning(
                "Goal performance analytics for %s capped at %d goals — metrics may be truncated",
                user_uid,
                QueryLimit.MAXIMUM,
            )

        # Calculate analytics
        total_goals = len(goals)
        active_goals = [g for g in goals if g.is_active]
        completed_goals = [g for g in goals if g.is_achieved()]
        on_track_goals = [g for g in goals if g.is_on_track()]

        # Calculate average progress
        if total_goals > 0:
            avg_progress = sum(g.progress_percentage for g in goals) / total_goals
        else:
            avg_progress = 0.0

        # Calculate success rate
        goals_with_deadline = [g for g in goals if g.target_date]
        past_deadline_goals = [
            g for g in goals_with_deadline if g.target_date and g.target_date < date.today()
        ]
        if past_deadline_goals:
            completed_on_time = [g for g in past_deadline_goals if g.is_achieved()]
            success_rate = len(completed_on_time) / len(past_deadline_goals)
        else:
            success_rate = 0.0

        return Result.ok(
            {
                "user_uid": user_uid,
                "period_days": period_days,
                "total_goals": total_goals,
                "active_goals": len(active_goals),
                "completed_goals": len(completed_goals),
                "on_track_goals": len(on_track_goals),
                "avg_progress": round(avg_progress, 2),
                "success_rate": round(success_rate, 2),
                "analytics": {
                    "total": total_goals,
                    "active": len(active_goals),
                    "completed": len(completed_goals),
                    "on_track": len(on_track_goals),
                    "avg_progress_percentage": round(avg_progress, 2),
                    "completion_rate": round(success_rate, 2),
                },
            }
        )

    async def get_domain_insights(
        self, uid: str, min_confidence: float = 0.7
    ) -> Result[dict[str, Any]]:
        """
        Get domain-specific insights for a goal.

        Protocol method: Maps to get_goal_progress_dashboard.
        Used by IntelligenceRouteFactory for GET /api/goals/insights route.
        """
        return await self.get_goal_progress_dashboard(uid, min_confidence)

    async def analyze_learning_patterns(
        self, user_uid: UserUID, timeframe_days: int = 30
    ) -> Result[list[Any]]:
        """Detect knowledge-learning patterns across the user's goal activities."""
        entities_result = await self.backend.find_by(user_uid=user_uid, limit=QueryLimit.MAXIMUM)
        if entities_result.is_error:
            return Result.fail(entities_result)

        service = self.relationships

        async def _fetch_goal_rels(uid: str) -> GoalRelationships:
            if service:
                return await GoalRelationships.fetch(uid, service)
            return GoalRelationships.empty()

        return await self._knowledge_analyzer.analyze_learning_patterns(
            entities_result.value, _fetch_goal_rels, timeframe_days
        )
