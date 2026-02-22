"""
Goals Intelligence Service
===========================

Handles pure Cypher graph intelligence queries for goals.

Responsibilities:
- Get goal with graph context (pure Cypher)
- Generate progress dashboard with supporting activities
- Generate completion forecasts with velocity analysis
- Analyze learning requirements with knowledge gaps
- **Predictive Analytics** (merged from GoalAnalyticsService, November 2025)
  - Predict goal success probability
  - Analyze habit impact on goals
  - Run what-if scenario analysis
"""

import math
from dataclasses import dataclass
from datetime import date, timedelta
from operator import attrgetter
from typing import TYPE_CHECKING, Any

from core.models.enums import Domain, KuStatus
from core.models.enums.activity_enums import ProgressLevel
from core.models.graph_context import GraphContext
from core.models.ku.ku_dto import KuDTO
from core.models.ku.ku_goal import GoalKu
from core.models.ku.ku_habit import HabitKu as Habit
from core.models.shared.dual_track import DualTrackResult
from core.services.base_analytics_service import BaseAnalyticsService
from core.services.intelligence import (
    GoalCrossContext,
    GraphContextOrchestrator,
    MetricsCalculator,
    RecommendationEngine,
    calculate_goal_metrics,
    compare_progress_to_expected,
)
from core.ports.domain_protocols import GoalsOperations
from core.utils.decorators import requires_graph_intelligence, with_error_handling
from core.utils.logging import get_logger
from core.utils.result_simplified import Errors, Result

if TYPE_CHECKING:
    from core.ports.domain_protocols import (
        GoalsRelationshipOperations,
        HabitsOperations,
    )

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


class GoalsIntelligenceService(BaseAnalyticsService[GoalsOperations, GoalKu]):
    """
    Graph intelligence service for goals using pure Cypher graph intelligence.

    NOTE: This service extends BaseAnalyticsService (ADR-030) and has NO AI dependencies.
    It uses pure graph queries and Python calculations - no LLM or embeddings.

    Handles:
    - Pure Cypher context retrieval
    - Comprehensive progress dashboards
    - Completion forecasts with velocity metrics
    - Learning requirements analysis
    - Dual-track assessment (user vision vs system measurement)


    Source Tag: "goals_intelligence_service_explicit"
    - Format: "goals_intelligence_service_explicit" for user-created relationships
    - Format: "goals_intelligence_service_inferred" for system-generated relationships

    Confidence Scoring:
    - 0.9+: User explicitly defined relationship
    - 0.7-0.9: Inferred from goals_intelligence metadata
    - 0.5-0.7: Suggested based on patterns
    - <0.5: Low confidence, needs verification

    SKUEL Architecture:
    - Uses CypherGenerator for ALL graph queries
    - No APOC calls (Phase 5 eliminated those)
    - Returns Result[T] for error handling
    - Logs operations with structured logging
    - NO embeddings_service or llm_service (ADR-030)

    """

    # Service name for hierarchical logging
    _service_name = "goals.intelligence"

    # Relationships are REQUIRED for this service
    _require_relationships = True

    def __init__(
        self,
        backend: GoalsOperations,
        graph_intelligence_service=None,
        relationship_service: "GoalsRelationshipOperations | None" = None,
        progress_service=None,
    ) -> None:
        """
        Initialize goals intelligence service.

        Args:
            backend: Protocol-based backend for goal operations,
            graph_intelligence_service: GraphIntelligenceService for Phase 1-4 queries,
            relationship_service: GoalsRelationshipOperations protocol for fetching (REQUIRED) goal relationships
            progress_service: GoalsProgressService for velocity calculations
        """
        super().__init__(
            backend=backend,
            graph_intelligence_service=graph_intelligence_service,
            relationship_service=relationship_service,
        )
        self.progress = progress_service  # Domain-specific: for velocity calculations

        # Initialize GraphContextOrchestrator for get_with_context pattern (Phase 2)
        if graph_intelligence_service:
            self.orchestrator = GraphContextOrchestrator[GoalKu, KuDTO](
                service=self,
                backend_get_method="get_goal",
                dto_class=KuDTO,
                model_class=GoalKu,
                domain=Domain.GOALS,
            )

    # ========================================================================
    # DOMAIN-SPECIFIC CONTRACT
    # ========================================================================

    @property
    def entity_label(self) -> str:
        """Return the graph label for Ku entities."""
        return "Ku"

    # ========================================================================
    # INTELLIGENCEOPERATIONS PROTOCOL METHODS (January 2026)
    # These methods implement the IntelligenceOperations protocol for use
    # with IntelligenceRouteFactory.
    # ========================================================================

    async def get_with_context(
        self, uid: str, depth: int = 2
    ) -> Result[tuple[GoalKu, GraphContext]]:
        """
        Get goal with full graph context.

        Protocol method: Maps to get_goal_with_context.
        Used by IntelligenceRouteFactory for GET /api/goals/context route.

        Args:
            uid: Goal UID
            depth: Graph traversal depth (default: 2)

        Returns:
            Result containing (Goal, GraphContext) tuple
        """
        return await self.get_goal_with_context(uid, depth)

    async def get_performance_analytics(
        self, user_uid: str, _period_days: int = 30
    ) -> Result[dict[str, Any]]:
        """
        Get goal performance analytics for a user.

        Protocol method: Aggregates goal metrics over time period.
        Used by IntelligenceRouteFactory for GET /api/goals/analytics route.

        Args:
            user_uid: User UID
            _period_days: Placeholder - not yet implemented. Will filter by period when added.

        Returns:
            Result containing analytics data dict

        Note: _period_days uses underscore prefix per CLAUDE.md convention to indicate
        "API contract defined, implementation deferred". Currently calculates analytics
        over ALL goals. Future enhancement: filter by created_at/updated_at within period.
        """
        # TODO [FEATURE]: Filter by period_days when time-based filtering is implemented
        goals_result = await self.backend.find_by(user_uid=user_uid)
        if goals_result.is_error:
            return Result.fail(goals_result.expect_error())

        goals = goals_result.value or []

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
                "period_days": _period_days,
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

        Args:
            uid: Goal UID
            min_confidence: Minimum confidence threshold (default: 0.7)

        Returns:
            Result containing insights data dict
        """
        return await self.get_goal_progress_dashboard(uid, min_confidence)

    # ========================================================================
    # PHASE 1-4 GRAPH INTELLIGENCE METHODS
    # ========================================================================

    @requires_graph_intelligence("get_goal_with_context")
    async def get_goal_with_context(
        self, uid: str, depth: int = 2
    ) -> Result[tuple[GoalKu, GraphContext]]:
        """
        Get goal with full graph context using pure Cypher graph intelligence.

        Automatically selects optimal query type based on goal's suggested intent:
        - HIERARCHICAL → Supporting activities and milestones
        - PREREQUISITE → Required knowledge and learning paths
        - AGGREGATION → Progress tracking across all activities
        - Default → Comprehensive goal ecosystem

        Args:
            uid: Goal UID,
            depth: Graph traversal depth (default: 2)

        Returns:
            Result containing (goal, GraphContext) tuple with comprehensive insights
        """
        # Use GraphContextOrchestrator pattern (Phase 2 consolidation)
        # Orchestrator is guaranteed to exist when @requires_graph_intelligence passes
        if not self.orchestrator:
            return Result.fail(
                Errors.system(
                    message="GraphContextOrchestrator not initialized",
                    operation="get_goal_with_context",
                )
            )
        return await self.orchestrator.get_with_context(uid=uid, depth=depth)

    @requires_graph_intelligence("get_goal_progress_dashboard")
    async def get_goal_progress_dashboard(
        self, uid: str, min_confidence: float = 0.7
    ) -> Result[dict[str, Any]]:
        """
        Get comprehensive goal progress dashboard using Phase 1-4.

        Provides complete view including:
        - Current progress and status
        - Supporting tasks with completion status
        - Supporting habits with consistency metrics
        - Learning paths and knowledge requirements
        - Timeline tracking and insights
        - Actionable recommendations

        Args:
            uid: Goal UID

        Returns:
            Result containing comprehensive progress dashboard

        Phase 5 Refactoring (Jan 2026):
        - Uses BaseIntelligenceService._analyze_entity_with_context template
        - Consolidates entity fetch + context + metrics pattern
        """
        # Phase 5: Use base class template for standardized analysis
        analysis_result = await self._analyze_entity_with_context(
            uid=uid,
            context_method="get_goal_cross_domain_context",
            context_type=GoalCrossContext,
            metrics_fn=calculate_goal_metrics,
            recommendations_fn=self._generate_progress_recommendations,
            min_confidence=min_confidence,
        )

        if analysis_result.is_error:
            return analysis_result

        analysis = analysis_result.value
        goal = self._to_domain_model(analysis["entity"], KuDTO, GoalKu)
        context: GoalCrossContext = analysis["context"]
        metrics = analysis["metrics"]

        # GRAPH-NATIVE: Fetch relationships from graph (for additional knowledge requirements)
        from core.services.goals.goal_relationships import GoalRelationships

        rels = await GoalRelationships.fetch(uid, self.relationships)

        # Extract supporting activities from context (for backward compatibility)
        # Note: context stores UIDs, we return them as-is for now
        supporting_tasks = [{"uid": uid} for uid in context.supporting_task_uids]
        supporting_habits = [{"uid": uid} for uid in context.supporting_habit_uids]
        learning_paths = [{"uid": uid} for uid in context.learning_path_uids]

        # Calculate timeline
        days_remaining = None
        if goal.target_date:
            days_remaining = (goal.target_date - date.today()).days

        # Calculate contributions (from metrics)
        total_tasks = metrics["task_support_count"]
        completed_tasks = 0  # Would need task status from actual task entities
        task_contribution = 0.0  # Simplified
        habit_contribution = metrics["support_coverage"] * 100 if metrics["has_habit_system"] else 0
        learning_contribution = (len(learning_paths) * 10.0) if learning_paths else 0

        # Generate insights
        has_knowledge_requirements = rels and rels.required_knowledge_uids
        insights = {
            "needs_more_tasks": metrics["task_support_count"] < 3,
            "needs_habit_support": not metrics["has_habit_system"],
            "has_learning_gaps": not metrics["has_curriculum_alignment"]
            and has_knowledge_requirements,
            "on_track": goal.is_active and goal.progress_percentage >= 10.0,
        }

        return Result.ok(
            {
                "goal": goal,
                "progress": {
                    "percentage": goal.progress_percentage,
                    "status": goal.status,
                    "is_on_track": goal.is_active and goal.progress_percentage >= 10.0,
                    "target_date": goal.target_date,
                    "days_remaining": days_remaining,
                },
                "supporting_activities": {
                    "tasks": supporting_tasks,
                    "habits": supporting_habits,
                    "learning_paths": learning_paths,
                    "total_tasks": total_tasks,
                    "completed_tasks": completed_tasks,
                    "active_habits": metrics["habit_support_count"],
                },
                "contributions": {
                    "task_contribution": task_contribution,
                    "habit_contribution": habit_contribution,
                    "learning_contribution": learning_contribution,
                },
                "insights": insights,
                "recommendations": analysis["recommendations"],
                "metrics": metrics,  # Phase 5: Include standard metrics
            }
        )

    def _generate_progress_recommendations(
        self, entity: Any, context: GoalCrossContext, metrics: dict[str, Any]
    ) -> list[str]:
        """Generate recommendations for goal progress dashboard."""
        # Uses RecommendationEngine from shared intelligence utilities (Phase 5 consolidation)
        return (
            RecommendationEngine()
            .with_metrics(metrics)
            .add_threshold_check(
                "task_support_count",
                3,
                "Consider breaking down this goal into more specific tasks",
            )
            .add_conditional(
                not metrics.get("has_habit_system", False),
                "Create habits to support consistent progress toward this goal",
            )
            .add_conditional(
                not metrics.get("has_curriculum_alignment", False)
                and metrics.get("knowledge_requirement_count", 0) > 0,
                "Develop learning paths for required knowledge areas",
            )
            .add_threshold_check(
                "support_coverage",
                0.5,
                "Focus on completing more supporting tasks to advance progress",
            )
            .build()
        )

    @requires_graph_intelligence("get_goal_completion_forecast")
    async def get_goal_completion_forecast(
        self, uid: str, depth: int = 2, min_confidence: float = 0.7
    ) -> Result[dict[str, Any]]:
        """
        Get goal completion forecast using Phase 1-4.

        Analyzes completion trajectory based on:
        - Current progress rate
        - Task completion velocity
        - Habit consistency trends
        - Historical patterns

        Args:
            uid: Goal UID,
            depth: Graph traversal depth (default: 2)

        Returns:
            Result containing completion forecast with velocity metrics

        Phase 5 Refactoring (Jan 2026):
        - Uses BaseIntelligenceService._analyze_entity_with_context template
        """
        # Phase 5: Use base class template for standardized analysis
        analysis_result = await self._analyze_entity_with_context(
            uid=uid,
            context_method="get_goal_cross_domain_context",
            context_type=GoalCrossContext,
            metrics_fn=calculate_goal_metrics,
            depth=depth,
            min_confidence=min_confidence,
        )

        if analysis_result.is_error:
            return analysis_result

        # Progress service is required for forecast calculations
        if not self.progress:
            return Result.fail(
                Errors.system(
                    message="Progress service required for completion forecast",
                    operation="get_goal_completion_forecast",
                )
            )

        analysis = analysis_result.value
        goal = self._to_domain_model(analysis["entity"], KuDTO, GoalKu)
        context: GoalCrossContext = analysis["context"]
        metrics = analysis["metrics"]

        # Calculate all metrics using progress service helpers
        # Note: Progress service methods need GraphContext - pass None for now
        velocity_metrics = self.progress.calculate_velocity_metrics(None, goal)
        current_progress_rate = velocity_metrics["current_progress_rate"]

        forecast = self.progress.generate_forecast(goal, current_progress_rate)
        days_ahead_or_behind = forecast["days_ahead_or_behind"]

        timeline_analysis = self.progress.calculate_timeline_analysis(
            goal, velocity_metrics, days_ahead_or_behind
        )
        required_velocity = timeline_analysis["required_velocity"]
        confidence_level = timeline_analysis["confidence_level"]

        risk_factors = self.progress.identify_risk_factors(velocity_metrics, None)
        acceleration_opportunities = self.progress.identify_acceleration_opportunities(
            velocity_metrics, None, required_velocity
        )

        return Result.ok(
            {
                "goal": goal,
                "forecast": {
                    "estimated_completion_date": forecast["estimated_completion_date"],
                    "confidence_level": confidence_level,
                    "on_track": goal.is_active and goal.progress_percentage >= 10.0,
                    "days_ahead_or_behind": days_ahead_or_behind,
                    "completion_probability": forecast["completion_probability"],
                },
                "velocity_metrics": {
                    "current_progress_rate": velocity_metrics["current_progress_rate"],
                    "task_completion_velocity": velocity_metrics["task_completion_velocity"],
                    "habit_consistency_score": velocity_metrics["habit_consistency_score"],
                    "learning_progress_rate": 0.5,  # Placeholder
                },
                "timeline_analysis": {
                    "target_date": timeline_analysis["target_date"],
                    "days_remaining": timeline_analysis["days_remaining"],
                    "required_velocity": timeline_analysis["required_velocity"],
                    "current_pace": timeline_analysis["current_pace"],
                },
                "risk_factors": risk_factors,
                "acceleration_opportunities": acceleration_opportunities,
                "metrics": metrics,  # Phase 3: Include standard metrics
                "graph_context": {
                    "task_support_count": len(context.supporting_task_uids),
                    "habit_support_count": len(context.supporting_habit_uids),
                    "support_coverage": metrics["support_coverage"],
                },
            }
        )

    @requires_graph_intelligence("get_goal_learning_requirements")
    async def get_goal_learning_requirements(
        self, uid: str, depth: int = 2, min_confidence: float = 0.7
    ) -> Result[dict[str, Any]]:
        """
        Get goal's learning requirements using Phase 1-4.

        Analyzes learning needs for goal achievement:
        - Required knowledge areas
        - Current mastery status
        - Learning paths available
        - Knowledge gaps to fill

        Args:
            uid: Goal UID,
            depth: Graph traversal depth (default: 2)

        Returns:
            Result containing learning requirements analysis

        Phase 5 Refactoring (Jan 2026):
        - Uses BaseIntelligenceService._analyze_entity_with_context template
        """
        # Phase 5: Use base class template for standardized analysis
        analysis_result = await self._analyze_entity_with_context(
            uid=uid,
            context_method="get_goal_cross_domain_context",
            context_type=GoalCrossContext,
            metrics_fn=calculate_goal_metrics,
            recommendations_fn=self._generate_learning_recommendations,
            depth=depth,
            min_confidence=min_confidence,
        )

        if analysis_result.is_error:
            return analysis_result

        analysis = analysis_result.value
        goal = self._to_domain_model(analysis["entity"], KuDTO, GoalKu)
        context: GoalCrossContext = analysis["context"]
        metrics = analysis["metrics"]

        # Convert UIDs to placeholder dicts for backward compatibility
        required_knowledge = [{"uid": uid} for uid in context.required_knowledge_uids]
        learning_paths = [{"uid": uid} for uid in context.learning_path_uids]

        # Note: Without actual KU data, we can't determine mastery level
        # This would require additional queries to KU service
        mastered_knowledge: list[dict[str, Any]] = []
        knowledge_gaps = required_knowledge  # Assume all are gaps without mastery data

        # Calculate mastery percentage
        total_required = metrics["knowledge_requirement_count"]
        total_mastered = len(mastered_knowledge)
        mastery_percentage = (total_mastered / total_required * 100) if total_required > 0 else 100

        # Estimate learning time
        estimated_learning_time = len(knowledge_gaps) * 2  # 2 hours per knowledge area

        # Find recommended path (first available path, or None)
        recommended_path = learning_paths[0] if learning_paths else None

        # Learning analysis
        learning_analysis = {
            "ready_to_start": len(knowledge_gaps) == 0,
            "has_prerequisites": total_required > 0,
            "learning_in_progress": metrics["has_curriculum_alignment"],
            "knowledge_complete": mastery_percentage >= 100,
        }

        return Result.ok(
            {
                "goal": goal,
                "knowledge_requirements": {
                    "required_knowledge": required_knowledge,
                    "mastered_knowledge": mastered_knowledge,
                    "knowledge_gaps": knowledge_gaps,
                    "total_required": total_required,
                    "total_mastered": total_mastered,
                    "mastery_percentage": mastery_percentage,
                },
                "learning_paths": {
                    "available_paths": learning_paths,
                    "recommended_path": recommended_path,
                    "estimated_learning_time": estimated_learning_time,
                },
                "learning_analysis": learning_analysis,
                "recommendations": analysis["recommendations"],
                "metrics": metrics,  # Phase 5: Include standard metrics
                "graph_context": {
                    "knowledge_requirement_count": total_required,
                    "learning_path_count": metrics["learning_path_count"],
                    "has_curriculum_alignment": metrics["has_curriculum_alignment"],
                },
            }
        )

    def _generate_learning_recommendations(
        self, entity: Any, context: GoalCrossContext, metrics: dict[str, Any]
    ) -> list[str]:
        """Generate recommendations for goal learning requirements."""
        # Uses RecommendationEngine from shared intelligence utilities (Phase 5 consolidation)
        knowledge_gaps_count = metrics.get("knowledge_requirement_count", 0)
        has_learning_paths = metrics.get("has_curriculum_alignment", False)

        return (
            RecommendationEngine()
            .with_metrics(metrics)
            .add_conditional(
                knowledge_gaps_count > 0,
                f"Master {knowledge_gaps_count} knowledge areas before starting this goal",
            )
            .add_conditional(
                not has_learning_paths and knowledge_gaps_count > 0,
                "Create a learning path to systematically acquire required knowledge",
            )
            .add_conditional(
                knowledge_gaps_count == 0,
                "You have sufficient knowledge to begin working on this goal",
            )
            .add_conditional(
                knowledge_gaps_count == 0,
                "Define required knowledge areas for better goal planning",
            )
            .build()
        )

    # ========================================================================
    # PREDICTIVE ANALYTICS (merged from GoalAnalyticsService, November 2025)
    # ========================================================================

    @with_error_handling("predict_goal_success", error_type="system", uid_param="goal_uid")
    async def predict_goal_success(
        self,
        goal_uid: str,
        lookback_days: int = 30,
        habits_service: "HabitsOperations | None" = None,
    ) -> Result[GoalPrediction]:
        """
        Predict probability of successfully achieving a goal.

        Uses multiple factors:
        - Current progress vs expected progress
        - Habit consistency trends
        - Time remaining
        - Historical performance patterns

        Args:
            goal_uid: Goal to analyze
            lookback_days: Days of history to consider
            habits_service: Service for fetching habit data (required for full analysis)

        Returns:
            GoalPrediction with success probability and insights
        """
        # Get goal
        goal_result = await self.backend.get(goal_uid)
        if goal_result.is_error:
            return Result.fail(goal_result.expect_error())
        if not goal_result.value:
            return Result.fail(Errors.not_found(resource="Goal", identifier=goal_uid))
        goal = goal_result.value

        # Get supporting habits (from graph relationships)
        from core.services.goals.goal_relationships import GoalRelationships

        rels = await GoalRelationships.fetch(goal_uid, self.relationships)

        habits: list[Habit] = []
        if habits_service:
            for habit_uid in rels.supporting_habit_uids:
                result = await habits_service.get(habit_uid)
                if result.is_ok and result.value:
                    habits.append(result.value)

        # Calculate various probability factors
        progress_factor = self._calculate_progress_factor(goal)
        consistency_factor = await self._calculate_consistency_factor(habits, lookback_days)
        time_factor = self._calculate_time_factor(goal)
        momentum_factor = await self._calculate_momentum_factor(goal, habits, lookback_days)

        # Combine factors using weighted model
        success_probability = self._combine_probability_factors(
            progress_factor, consistency_factor, time_factor, momentum_factor
        )

        # Predict completion date
        predicted_date = self._predict_completion_date(goal, success_probability, momentum_factor)

        # Determine confidence level
        confidence = self._determine_confidence_level(
            lookback_days, len(habits), goal.get_days_remaining()
        )

        # Identify risk and success factors
        risk_factors = self._identify_risk_factors(
            goal, habits, progress_factor, consistency_factor
        )

        success_factors = self._identify_success_factors(
            goal, habits, progress_factor, consistency_factor
        )

        # Generate recommendations
        recommendations = self._generate_prediction_recommendations(
            goal, habits, success_probability, risk_factors
        )

        # Determine trend
        trend = await self._determine_trend(goal, habits, lookback_days)

        # Create prediction
        prediction = GoalPrediction(
            goal_uid=goal.uid,
            goal_title=goal.title,
            success_probability=success_probability,
            predicted_completion_date=predicted_date,
            confidence_level=confidence,
            risk_factors=risk_factors,
            success_factors=success_factors,
            recommended_actions=recommendations,
            trend=trend,
        )

        logger.info(
            f"Generated prediction for goal {goal_uid}: {success_probability:.0%} success probability"
        )
        return Result.ok(prediction)

    @with_error_handling("analyze_habit_impact", error_type="system", uid_param="goal_uid")
    async def analyze_habit_impact(
        self,
        goal_uid: str,
        habits_service: "HabitsOperations | None" = None,
    ) -> Result[list[HabitImpactAnalysis]]:
        """
        Analyze the impact of each habit on goal success.

        Args:
            goal_uid: Goal to analyze
            habits_service: Service for fetching habit data (required)

        Returns:
            List of habit impact analyses sorted by impact score
        """
        if not habits_service:
            return Result.fail(
                Errors.system(
                    message="Habits service not available", operation="analyze_habit_impact"
                )
            )

        goal_result = await self.backend.get(goal_uid)
        if goal_result.is_error:
            return Result.fail(goal_result.expect_error())
        if not goal_result.value:
            return Result.fail(Errors.not_found(resource="Goal", identifier=goal_uid))

        # GRAPH-NATIVE: Fetch goal relationships from graph
        from core.services.goals.goal_relationships import GoalRelationships

        rels = await GoalRelationships.fetch(goal_uid, self.relationships)

        analyses = []

        for habit_uid in rels.supporting_habit_uids:
            result = await habits_service.get(habit_uid)
            if not result.is_ok:
                continue

            habit = result.value
            if not habit:
                continue

            # Calculate impact score
            # GRAPH-NATIVE: habit_weights removed - using default weight
            weight = 1.0  # Default weight for all habits
            consistency = habit.success_rate  # Already 0.0-1.0, not 0-100
            impact_score = weight * consistency

            # Determine criticality
            if weight >= 1.5:
                criticality = "critical"
            elif weight >= 1.0:
                criticality = "important"
            else:
                criticality = "supportive"

            # Calculate consistency gap
            # GRAPH-NATIVE: required_habit_consistency removed - using default threshold
            required = 0.8  # Default 80% consistency requirement
            gap = required - consistency

            analysis = HabitImpactAnalysis(
                habit_uid=habit_uid,
                habit_title=habit.title,
                impact_score=impact_score,
                criticality=criticality,
                current_consistency=consistency,
                required_consistency=required,
                consistency_gap=max(0, gap),
            )

            analyses.append(analysis)

        # Sort by impact score
        analyses.sort(key=attrgetter("impact_score"), reverse=True)

        return Result.ok(analyses)

    @with_error_handling("run_scenario_analysis", error_type="system", uid_param="goal_uid")
    async def run_scenario_analysis(
        self,
        goal_uid: str,
        consistency_adjustments: dict[str, float],
        habits_service: "HabitsOperations | None" = None,
    ) -> Result[GoalPrediction]:
        """
        Run what-if scenario with adjusted habit consistencies.

        Args:
            goal_uid: Goal to analyze
            consistency_adjustments: Dict of habit_uid -> new_consistency (0-1)
            habits_service: Service for fetching habit data (required)

        Returns:
            Prediction based on scenario
        """
        if not habits_service:
            return Result.fail(
                Errors.system(
                    message="Habits service not available", operation="run_scenario_analysis"
                )
            )

        # Get goal
        goal_result = await self.backend.get(goal_uid)
        if goal_result.is_error:
            return Result.fail(goal_result.expect_error())
        if not goal_result.value:
            return Result.fail(Errors.not_found(resource="Goal", identifier=goal_uid))
        goal = goal_result.value

        # Fetch relationships from graph
        from core.services.goals.goal_relationships import GoalRelationships

        rels = await GoalRelationships.fetch(goal_uid, self.relationships)

        # Apply adjustments to habits (in memory only)
        from dataclasses import replace

        adjusted_habits: list[Habit] = []
        for habit_uid in rels.supporting_habit_uids:
            result = await habits_service.get(habit_uid)
            if result.is_ok:
                habit = result.value
                if not habit:
                    continue
                if habit_uid in consistency_adjustments:
                    # Create adjusted version with new success_rate
                    # Note: success_rate is 0.0-1.0, consistency_adjustments assumed to be 0.0-1.0
                    habit = replace(habit, success_rate=consistency_adjustments[habit_uid])
                adjusted_habits.append(habit)

        # Recalculate with adjusted values
        consistency_factor = await self._calculate_consistency_factor(adjusted_habits, 30)
        progress_factor = self._calculate_progress_factor(goal)
        time_factor = self._calculate_time_factor(goal)
        momentum_factor = 0.5  # Neutral for scenario

        success_probability = self._combine_probability_factors(
            progress_factor, consistency_factor, time_factor, momentum_factor
        )

        prediction = GoalPrediction(
            goal_uid=goal.uid,
            goal_title=f"{goal.title} (Scenario)",
            success_probability=success_probability,
            predicted_completion_date=self._predict_completion_date(
                goal, success_probability, momentum_factor
            ),
            confidence_level="medium",  # Scenarios have medium confidence
            risk_factors=[],
            success_factors=[],
            recommended_actions=["This is a what-if scenario"],
            trend="stable",
        )

        return Result.ok(prediction)

    # ========================================================================
    # PREDICTIVE ANALYTICS HELPER METHODS
    # ========================================================================

    def _calculate_progress_factor(self, goal: GoalKu) -> float:
        """Calculate progress factor based on current vs expected progress.

        Uses MetricsCalculator.sigmoid_scale for smooth scaling.
        Returns value between 0.0 and 1.0.
        """
        if not goal.target_date or not goal.start_date:
            return 0.5  # No deadline or start date, neutral factor

        total_days = (goal.target_date - goal.start_date).days
        elapsed_days = (date.today() - goal.start_date).days

        if total_days <= 0:
            return 0.0

        # Expected progress based on linear progression
        expected_progress = (elapsed_days / total_days) * 100
        actual_progress = goal.calculate_progress()

        # Calculate factor with sigmoid function for smooth scaling
        # diff > 0 means ahead of schedule, diff < 0 means behind
        diff = actual_progress - expected_progress

        return MetricsCalculator.sigmoid_scale(
            value=diff,
            midpoint=0.0,  # When on schedule (diff=0), factor = 0.5
            steepness=0.1,  # Gentle slope for progress differences
            output_range=(0.0, 1.0),
        )

    async def _calculate_consistency_factor(
        self, habits: list[Habit], _lookback_days: int
    ) -> float:
        """Calculate consistency factor based on habit performance.

        Uses MetricsCalculator.weighted_average for consistent calculation.
        Returns value between 0.0 and 1.0.
        """
        if not habits:
            return 0.5  # No habits, neutral factor

        # Priority weight mapping
        priority_weights = {"high": 1.5, "medium": 1.0, "low": 0.5}

        def get_priority_weight(habit: Habit) -> float:
            if habit.priority:
                return priority_weights.get(habit.priority.lower(), 1.0)
            return 1.0

        def get_normalized_success_rate(habit: Any) -> float:
            # Habit.success_rate is already 0.0-1.0 (completions/attempts)
            return habit.success_rate

        result = MetricsCalculator.weighted_average(
            items=habits,
            value_fn=get_normalized_success_rate,
            weight_fn=get_priority_weight,
        )

        return result if result > 0 else 0.5

    def _calculate_time_factor(self, goal: GoalKu) -> float:
        """Calculate time pressure factor.

        Uses logarithmic scale: more time remaining = higher success probability.
        Returns value between 0.1 and 1.0.
        """
        days_remaining = goal.get_days_remaining()
        if days_remaining is None:
            return 0.8  # No deadline, good factor

        if days_remaining <= 0:
            return 0.1  # Past deadline

        # Use logarithmic scale for time factor
        # More days = higher factor, but diminishing returns
        # Normalized to 1 year (365 days)
        factor = math.log(days_remaining + 1) / math.log(365)

        return MetricsCalculator.clamp(factor, min_val=0.1, max_val=1.0)

    async def _calculate_momentum_factor(
        self, goal: GoalKu, habits: list[Habit], _lookback_days: int
    ) -> float:
        """
        Calculate momentum based on recent trends.

        Improving trends = higher factor
        """
        # Calculate recent progress rate (simplified)
        days_elapsed = (date.today() - goal.start_date).days if goal.start_date else 1
        recent_progress_rate = goal.calculate_progress() / max(days_elapsed, 1)

        # Calculate habit streak momentum
        streak_momentum = 0.0
        for habit in habits:
            if habit.current_streak > 7:
                streak_momentum += 0.2
            elif habit.current_streak > 3:
                streak_momentum += 0.1

        return min(1.0, recent_progress_rate / 100 + streak_momentum)

    def _combine_probability_factors(
        self, progress: float, consistency: float, time: float, momentum: float
    ) -> float:
        """Combine all factors into final probability.

        Uses MetricsCalculator.combine_weighted_factors with non-linear scaling.
        Returns value between 0.05 and 0.95.
        """
        factors = {
            "progress": progress,
            "consistency": consistency,
            "time": time,
            "momentum": momentum,
        }
        weights = {"progress": 0.35, "consistency": 0.35, "time": 0.15, "momentum": 0.15}

        # Weighted average using MetricsCalculator
        probability = MetricsCalculator.combine_weighted_factors(
            factors=factors,
            weights=weights,
            normalize=True,
        )

        # Apply non-linear scaling for more realistic probabilities
        # This prevents over-confident predictions
        if probability > 0.8:
            probability = 0.8 + (probability - 0.8) * 0.5
        elif probability < 0.2:
            probability = 0.2 * probability

        return MetricsCalculator.clamp(probability, min_val=0.05, max_val=0.95)

    def _predict_completion_date(
        self, goal: GoalKu, success_probability: float, momentum: float
    ) -> date | None:
        """
        Predict when the goal will be completed.
        """
        if goal.calculate_progress() >= 100:
            return date.today()

        if success_probability < 0.3:
            return None  # Unlikely to complete

        # Calculate daily progress rate
        if not goal.start_date:
            return goal.target_date  # No start date, use target as best guess

        days_elapsed = (date.today() - goal.start_date).days
        if days_elapsed <= 0:
            return goal.target_date

        daily_rate = goal.calculate_progress() / days_elapsed

        # Adjust rate based on momentum
        adjusted_rate = daily_rate * (0.5 + momentum)

        if adjusted_rate <= 0:
            return None

        # Calculate days needed
        remaining_progress = 100 - goal.calculate_progress()
        days_needed = int(remaining_progress / adjusted_rate)

        # Add buffer based on success probability
        buffer = int(days_needed * (1 - success_probability) * 0.5)

        predicted_date = date.today() + timedelta(days=days_needed + buffer)

        # Don't predict beyond target date if high probability
        if goal.target_date and success_probability > 0.7:
            return min(predicted_date, goal.target_date)

        return predicted_date

    def _determine_confidence_level(
        self, data_points: int, habit_count: int, days_remaining: int | None
    ) -> str:
        """
        Determine confidence level in the prediction.
        """
        confidence_score = 0

        # More data = higher confidence
        if data_points >= 30:
            confidence_score += 3
        elif data_points >= 14:
            confidence_score += 2
        else:
            confidence_score += 1

        # More habits = more reliable prediction
        if habit_count >= 3:
            confidence_score += 2
        elif habit_count >= 1:
            confidence_score += 1

        # Reasonable time remaining = higher confidence
        if days_remaining and 30 <= days_remaining <= 180:
            confidence_score += 2
        elif days_remaining and days_remaining > 7:
            confidence_score += 1

        if confidence_score >= 6:
            return "high"
        elif confidence_score >= 3:
            return "medium"
        else:
            return "low"

    def _identify_risk_factors(
        self, goal: GoalKu, habits: list[Habit], progress_factor: float, consistency_factor: float
    ) -> list[str]:
        """Identify factors that might prevent goal achievement."""
        risks = []

        if progress_factor < 0.4:
            risks.append("📉 Behind schedule - need to accelerate progress")

        if consistency_factor < 0.5:
            risks.append("⚠️ Low habit consistency threatening goal achievement")

        days_remaining = goal.get_days_remaining()
        if days_remaining and days_remaining < 30:
            risks.append("⏰ Less than 30 days remaining - time pressure high")

        # Check for broken streaks
        broken_streaks = sum(1 for h in habits if h.current_streak == 0)
        if broken_streaks > len(habits) / 2:
            risks.append("💔 Multiple broken habit streaks")

        # Check for low-performing critical habits (success_rate is 0.0-1.0)
        critical_habits = [h for h in habits if h.success_rate < 0.5]
        if critical_habits:
            risks.append(f"🚨 {len(critical_habits)} critical habits underperforming")

        return risks

    def _identify_success_factors(
        self, goal: GoalKu, habits: list[Habit], progress_factor: float, consistency_factor: float
    ) -> list[str]:
        """Identify factors supporting goal achievement."""
        factors = []

        if progress_factor > 0.7:
            factors.append("✅ Ahead of schedule")

        if consistency_factor > 0.8:
            factors.append("💪 Strong habit consistency")

        # Check for strong streaks
        strong_streaks = sum(1 for h in habits if h.current_streak > 14)
        if strong_streaks > 0:
            factors.append(f"🔥 {strong_streaks} habits with 2+ week streaks")

        if goal.calculate_progress() > 50:
            factors.append("📊 Over halfway to goal")

        days_remaining = goal.get_days_remaining()
        if days_remaining and days_remaining > 90:
            factors.append("📅 Plenty of time remaining")

        return factors

    def _generate_prediction_recommendations(
        self,
        goal: GoalKu,
        habits: list[Habit],
        success_probability: float,
        _risk_factors: list[str],
    ) -> list[str]:
        """Generate actionable recommendations to improve success probability.

        Uses RecommendationEngine for structured threshold-based recommendations.
        """
        # Find weakest habit for targeted recommendations
        weakest_habit = min(habits, key=attrgetter("success_rate")) if habits else None
        # success_rate is 0.0-1.0, so 0.7 = 70% consistency
        inconsistent = [h for h in habits if h.success_rate < 0.7]
        days_remaining = goal.get_days_remaining()
        has_long_habits = any((h.duration_minutes or 0) > 45 for h in habits)

        return (
            RecommendationEngine()
            .with_metrics({"success_probability": success_probability})
            # Goal at risk (< 0.5)
            .add_conditional(
                success_probability < 0.5,
                "🎯 Focus exclusively on this goal for next 2 weeks",
            )
            .add_conditional(
                success_probability < 0.5 and weakest_habit is not None,
                f"🔧 Fix '{weakest_habit.title}' - currently at {weakest_habit.success_rate * 100:.0f}%"
                if weakest_habit
                else "",
            )
            .add_conditional(
                success_probability < 0.5 and days_remaining is not None and days_remaining < 60,
                "📅 Consider extending deadline or reducing scope",
            )
            # Goal needs attention (0.5 - 0.7)
            .add_conditional(
                0.5 <= success_probability < 0.7,
                "⚡ Increase habit frequency for 1-2 weeks",
            )
            .add_conditional(
                0.5 <= success_probability < 0.7 and len(inconsistent) > 0,
                f"📱 Set reminders for {len(inconsistent)} inconsistent habits",
            )
            # Goal on track (>= 0.7)
            .add_conditional(
                success_probability >= 0.7,
                "👍 Maintain current momentum",
            )
            .add_conditional(
                success_probability >= 0.7 and has_long_habits,
                "⏱️ Consider optimizing long habit sessions",
            )
            .build()
        )

    async def _determine_trend(self, goal: GoalKu, habits: list[Habit], _lookback_days: int) -> str:
        """Determine if goal achievement probability is improving, stable, or declining.

        Uses compare_progress_to_expected for standardized trend analysis.
        """
        # Calculate actual vs expected progress
        recent_progress = goal.calculate_progress()
        expected_progress = (
            (date.today() - goal.start_date).days
            / max((goal.target_date - goal.start_date).days, 1)
            * 100
            if goal.target_date and goal.start_date
            else 50
        )

        # Check habit trends
        improving_habits = sum(1 for h in habits if h.current_streak > 7)
        declining_habits = sum(1 for h in habits if h.current_streak == 0)

        return compare_progress_to_expected(
            actual_progress=recent_progress,
            expected_progress=expected_progress,
            improving_items=improving_habits,
            declining_items=declining_habits,
        )

    # ========================================================================
    # DUAL-TRACK ASSESSMENT (ADR-030 - January 2026)
    # ========================================================================

    async def assess_progress_dual_track(
        self,
        goal_uid: str,
        user_uid: str,
        user_progress_level: ProgressLevel,
        user_evidence: str,
        user_reflection: str | None = None,
    ) -> Result[DualTrackResult[ProgressLevel]]:
        """
        Dual-track progress assessment for goals.

        Compares user self-assessment (vision) with system measurement (action)
        to generate perception gap analysis and insights.

        This implements SKUEL's core philosophy:
        "The user's vision is understood via the words they use to communicate,
        the UserContext is determined via user's actions."

        Uses BaseIntelligenceService._dual_track_assessment() template (ADR-030).

        Args:
            goal_uid: Goal UID to assess
            user_uid: User making the assessment
            user_progress_level: User's self-reported progress level
            user_evidence: User's evidence for their assessment
            user_reflection: Optional reflection on their progress

        Returns:
            Result[DualTrackResult[ProgressLevel]] with dual-track analysis

        Example:
            >>> from core.models.enums.activity_enums import ProgressLevel
            >>> result = await service.assess_progress_dual_track(
            ...     goal_uid="goal.learn-python",
            ...     user_uid="user_mike",
            ...     user_progress_level=ProgressLevel.ON_TRACK,
            ...     user_evidence="I've completed most milestones",
            ...     user_reflection="Feeling good about this goal",
            ... )
            >>> if result.is_ok:
            ...     dual_track = result.value
            ...     print(f"Gap: {dual_track.perception_gap:.0%}")
        """
        return await self._dual_track_assessment(
            uid=goal_uid,
            user_uid=user_uid,
            user_level=user_progress_level,
            user_evidence=user_evidence,
            user_reflection=user_reflection,
            system_calculator=self._calculate_system_progress,
            level_scorer=self._progress_level_to_score,
            entity_type="goal",
            insight_generator=self._generate_progress_gap_insights,
            recommendation_generator=self._generate_progress_gap_recommendations,
        )

    async def _calculate_system_progress(
        self, goal: GoalKu, _user_uid: str
    ) -> tuple[ProgressLevel, float, list[str]]:
        """
        Calculate system progress from goal metrics.

        Examines:
        - Current progress percentage
        - Time elapsed vs time remaining
        - Milestone completion
        - Activity support (tasks, habits)

        Args:
            goal: The Goal entity
            _user_uid: User UID (unused in goal-specific calculation)

        Returns:
            Tuple of (ProgressLevel, score, evidence_list)
        """
        evidence: list[str] = []

        # Base progress from goal
        progress_percentage = goal.progress_percentage
        evidence.append(f"Current progress: {progress_percentage:.0f}%")

        # Calculate expected progress based on timeline
        expected_progress = 50.0  # Default if no dates
        if goal.target_date and goal.start_date:
            total_days = (goal.target_date - goal.start_date).days
            elapsed_days = (date.today() - goal.start_date).days
            if total_days > 0:
                expected_progress = (elapsed_days / total_days) * 100
                evidence.append(f"Expected progress: {expected_progress:.0f}%")

        # Calculate progress relative to expectation
        if expected_progress > 0:
            relative_progress = progress_percentage / expected_progress
        else:
            relative_progress = 1.0 if progress_percentage > 0 else 0.5

        # Adjust for goal status
        status_factor = 1.0
        if goal.status == KuStatus.COMPLETED:
            status_factor = 1.0
            evidence.append("Goal achieved!")
        elif goal.status == KuStatus.PAUSED:
            status_factor = 0.7
            evidence.append("Goal is currently paused")
        elif goal.status == KuStatus.CANCELLED:
            status_factor = 0.2
            evidence.append("Goal was cancelled")

        # Final score calculation
        score = min(relative_progress * status_factor, 1.0)

        # Check for overdue
        days_remaining = goal.get_days_remaining()
        if days_remaining is not None and days_remaining < 0:
            evidence.append(f"Overdue by {abs(days_remaining)} days")
            score *= 0.7  # Penalty for being overdue

        # Convert score to level
        system_level = ProgressLevel.from_score(score)

        return system_level, score, evidence

    def _progress_level_to_score(self, level: ProgressLevel) -> float:
        """Convert ProgressLevel to numeric score (0.0-1.0)."""
        return level.to_score()

    def _generate_progress_gap_insights(
        self, direction: str, gap: float, entity_name: str
    ) -> list[str]:
        """Generate progress-specific gap insights."""
        insights: list[str] = []

        if direction == "aligned":
            insights.append(
                f"Your self-perception of progress on '{entity_name}' matches the data. "
                "This indicates accurate self-awareness about your goal advancement."
            )
        elif direction == "user_higher":
            insights.append(
                f"Your self-assessment is more optimistic than the metrics suggest "
                f"(gap: {gap:.0%}). Consider: Are there recent setbacks not reflected in your perception?"
            )
            if gap > 0.3:
                insights.append(
                    "This significant gap may indicate optimism bias. "
                    "Review your milestones to ground your assessment."
                )
        else:  # system_higher
            insights.append(
                f"Your progress metrics show more advancement than you perceive (gap: {gap:.0%}). "
                "You may be undervaluing your achievements."
            )
            if gap > 0.3:
                insights.append(
                    "Consider reviewing your completed milestones - you're making more progress than you realize!"
                )

        return insights

    def _generate_progress_gap_recommendations(
        self, direction: str, _gap: float, entity: Any, evidence: list[str]
    ) -> list[str]:
        """Generate progress-specific gap recommendations."""
        recommendations: list[str] = []
        goal = entity

        if direction == "aligned":
            recommendations.append(
                "Continue your current approach - your progress self-awareness is accurate."
            )
            if goal.progress_percentage < 50:
                recommendations.append(
                    "Consider adding more supporting tasks or habits to accelerate progress."
                )
        elif direction == "user_higher":
            recommendations.append("Review your goal milestones and update progress tracking.")
            recommendations.append("Break down remaining work into smaller, trackable tasks.")
            if any("overdue" in e.lower() for e in evidence):
                recommendations.append(
                    "Address timeline issues to align perceived and actual progress."
                )
        else:  # system_higher
            recommendations.append("Celebrate your progress - you're doing better than you think!")
            if evidence:
                recommendations.append(f"Your metrics show: {evidence[0]}")
            recommendations.append(
                "Consider why you underestimate progress - perfectionism can skew perception."
            )

        return recommendations[:4]
