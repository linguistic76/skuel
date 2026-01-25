"""
Habits Intelligence Service
============================

Handles pure Cypher graph intelligence queries for habits.

Responsibilities:
- APOC-powered habit context retrieval
- Performance analysis with knowledge reinforcement
- Knowledge practice tracking
- Goal support analysis
- Cross-domain graph intelligence

Version: 1.0.0
Date: 2025-10-13
"""

from typing import TYPE_CHECKING, Any

from core.events.habit_events import HabitMissed, HabitStreakBroken
from core.models.enums.activity_enums import ConsistencyLevel
from core.models.graph_context import GraphContext
from core.models.habit.habit import Habit
from core.models.habit.habit_dto import HabitDTO
from core.models.relationship_names import RelationshipName
from core.models.shared.dual_track import DualTrackResult
from core.models.shared_enums import Domain
from core.services.base_analytics_service import BaseAnalyticsService
from core.services.intelligence import (
    GraphContextOrchestrator,
    HabitCrossContext,
    MetricsCalculator,
    RecommendationEngine,
    calculate_habit_metrics,
    get_context_service,
)

# NOTE (November 2025): Removed HasConsistencyScore, HasFrequency, HasStreakCount imports
# These protocols were used for defensive isinstance() checks, but the Habit model
# is well-typed - use direct attribute access instead:
#   - habit.calculate_consistency_score() instead of isinstance(habit, HasConsistencyScore)
#   - habit.current_streak instead of isinstance(habit, HasStreakCount)
#   - habit.recurrence_pattern instead of isinstance(habit, HasFrequency)
from core.services.protocols.domain_protocols import HabitsOperations
from core.utils.decorators import requires_graph_intelligence
from core.utils.result_simplified import Errors, Result

if TYPE_CHECKING:
    from core.services.protocols.domain_protocols import HabitsRelationshipOperations


class HabitsIntelligenceService(BaseAnalyticsService[HabitsOperations, Habit]):
    """
    Pure Cypher graph intelligence service for habits.

    NOTE: This service extends BaseAnalyticsService (ADR-030) and has NO AI dependencies.
    It uses pure graph queries and Python calculations - no LLM or embeddings.

    Handles:
    - Context-aware habit retrieval
    - Performance analysis with knowledge and goal tracking
    - Knowledge reinforcement analysis
    - Goal support contribution analysis
    - Dual-track assessment (user vision vs system measurement)


    Source Tag: "habits_intelligence_service_explicit"
    - Format: "habits_intelligence_service_explicit" for user-created relationships
    - Format: "habits_intelligence_service_inferred" for system-generated relationships

    Confidence Scoring:
    - 0.9+: User explicitly defined relationship
    - 0.7-0.9: Inferred from habits_intelligence metadata
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
    _service_name = "habits.intelligence"

    # Relationships are REQUIRED for this service
    _require_relationships = True

    def __init__(
        self,
        backend: HabitsOperations,
        relationship_service: "HabitsRelationshipOperations",
        graph_intelligence_service=None,
    ) -> None:
        """
        Initialize habits intelligence service.

        Args:
            backend: Protocol-based backend for habit operations,
            graph_intelligence_service: GraphIntelligenceService for pure Cypher analytics,
            relationship_service: HabitsRelationshipOperations protocol for specialized relationship queries (REQUIRED)

        Note:
            Context invalidation now happens via event-driven architecture.
            Habit events trigger user_service.invalidate_context() in bootstrap.
        """
        super().__init__(
            backend=backend,
            graph_intelligence_service=graph_intelligence_service,
            relationship_service=relationship_service,
        )
        self.context_service = get_context_service()  # Phase 3: DRY cross-domain context

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
    ) -> Result[tuple[Habit, GraphContext]]:
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
        self, user_uid: str, _period_days: int = 30
    ) -> Result[dict[str, Any]]:
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
            return Result.fail(habits_result.expect_error())

        habits = habits_result.value or []

        # Calculate analytics
        total_habits = len(habits)
        active_habits = [h for h in habits if h.is_active()]

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
            }
        )

    async def get_domain_insights(
        self, uid: str, min_confidence: float = 0.7
    ) -> Result[dict[str, Any]]:
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
    # PHASE 1-4 APOC-OPTIMIZED METHODS
    # ========================================================================

    @requires_graph_intelligence("get_habit_with_context")
    async def get_habit_with_context(
        self, uid: str, depth: int = 2
    ) -> Result[tuple[Habit, GraphContext]]:
        """
        Get habit with full graph context using pure Cypher graph intelligence.

        Automatically selects optimal query type based on habit's suggested intent:
        - PRACTICE → Knowledge reinforcement tracking
        - HIERARCHICAL → Goal support analysis
        - RELATIONSHIP → Habit ecosystem connections
        - Default → Knowledge practice context

        This replaces multiple sequential queries with a single Pure Cypher query,
        achieving 8-10x performance improvement.

        Args:
            uid: Habit UID,
            depth: Graph traversal depth (default: 2)

        Returns:
            Result containing (habit, GraphContext) tuple with:
            - habit: The Habit domain model
            - GraphContext: Rich graph context with cross-domain insights including:
                * Related knowledge units being reinforced
                * Supporting goals
                * Related tasks and events
                * Habit ecosystem connections
                * Performance metrics (query time, node counts)

        Performance:
            - Old approach: ~250ms (3-5 separate queries)
            - New approach: ~30ms (single APOC query)
            - 8-10x faster with single database round trip

        Example:
            ```python
            result = await habits_intel.get_habit_with_context(
                "habit_1", GraphDepth.NEIGHBORHOOD
            )
            habit, context = result.value

            # Extract cross-domain insights
            knowledge = context.get_nodes_by_domain(Domain.KNOWLEDGE)
            goals = context.get_nodes_by_domain(Domain.GOALS)
            tasks = context.get_nodes_by_domain(Domain.TASKS)

            print(f"Habit reinforces {len(knowledge)} knowledge areas")
            print(f"Supports {len(goals)} goals")
            ```
        """
        # Use GraphContextOrchestrator for generic pattern (50 lines → 1 line)
        # Orchestrator is guaranteed to exist when @requires_graph_intelligence passes
        if not self.orchestrator:
            return Result.fail(
                Errors.system(
                    message="GraphContextOrchestrator not initialized",
                    operation="get_habit_with_context",
                )
            )
        return await self.orchestrator.get_with_context(uid=uid, depth=depth)

    @requires_graph_intelligence("analyze_habit_performance")
    async def analyze_habit_performance(
        self, uid: str, min_confidence: float = 0.7
    ) -> Result[dict[str, Any]]:
        """
        Analyze habit with knowledge reinforcement and goal support using Phase 1-4.

        Provides comprehensive performance analysis including:
        - Knowledge areas being reinforced through habit practice
        - Goals supported by this habit
        - Streak score and consistency metrics
        - Reinforcement effectiveness calculation
        - Performance insights and recommendations

        Args:
            uid: Habit UID

        Returns:
            Result containing performance analysis:
            {
                "habit": Habit,
                "performance": {
                    "knowledge_reinforced": List[Ku],
                    "supporting_goals": List[Goal],
                    "streak_score": float,
                    "reinforcement_effectiveness": float,
                    "consistency_score": float,
                    "total_knowledge_areas": int,
                    "total_goals_supported": int
                },
                "insights": {
                    "high_reinforcement": bool,  # effectiveness > 5.0
                    "goal_aligned": bool,        # supports goals
                    "knowledge_builder": bool     # reinforces knowledge
                },
                "recommendations": {
                    "maintain_consistency": bool,
                    "expand_knowledge_links": bool,
                    "align_with_more_goals": bool
                },
                "graph_context": GraphContext,
                "performance_metrics": {
                    "query_time_ms": float,
                    "nodes_returned": int
                }
            }

        Example:
            ```python
            result = await habits_intel.analyze_habit_performance("habit_1")
            analysis = result.value

            perf = analysis["performance"]
            print(f"Streak: {perf['streak_score']}")
            print(f"Reinforces {perf['total_knowledge_areas']} knowledge areas")
            print(f"Supports {perf['total_goals_supported']} goals")

            if analysis["insights"]["high_reinforcement"]:
                print("This is a highly effective learning habit!")
            ```

        Phase 5 Refactoring (Jan 2026):
        - Uses BaseIntelligenceService._analyze_entity_with_context template
        """
        # Phase 5: Use base class template for standardized analysis
        analysis_result = await self._analyze_entity_with_context(
            uid=uid,
            context_method="get_habit_cross_domain_context",
            context_type=HabitCrossContext,
            metrics_fn=calculate_habit_metrics,
            recommendations_fn=self._generate_performance_recommendations,
            min_confidence=min_confidence,
        )

        if analysis_result.is_error:
            return analysis_result

        analysis = analysis_result.value
        habit = self._to_domain_model(analysis["entity"], HabitDTO, Habit)
        context: HabitCrossContext = analysis["context"]
        metrics = analysis["metrics"]

        # Return UIDs directly - no placeholder dicts
        knowledge_reinforcement_uids = context.knowledge_reinforcement_uids
        supporting_goal_uids = context.linked_goal_uids

        # Calculate performance metrics
        streak_score = habit.current_streak / habit.best_streak if habit.best_streak > 0 else 0.0
        consistency_score = habit.calculate_consistency_score()
        reinforcement_effectiveness = len(knowledge_reinforcement_uids) * consistency_score

        # Generate insights from metrics
        insights = {
            "high_reinforcement": reinforcement_effectiveness > 5.0,
            "goal_aligned": metrics["has_goal_connection"],
            "knowledge_builder": metrics["is_knowledge_builder"],
        }

        # Generate recommendations dict (convert list to dict for backward compatibility)
        recommendations = {
            "maintain_consistency": consistency_score < 0.7,
            "expand_knowledge_links": metrics["knowledge_reinforcement_count"] < 3,
            "align_with_more_goals": metrics["goal_support_count"] < 2,
        }

        return Result.ok(
            {
                "habit": habit,
                "performance": {
                    "knowledge_reinforcement_uids": knowledge_reinforcement_uids,
                    "supporting_goal_uids": supporting_goal_uids,
                    "streak_score": streak_score,
                    "reinforcement_effectiveness": reinforcement_effectiveness,
                    "consistency_score": consistency_score,
                    "total_knowledge_areas": metrics["knowledge_reinforcement_count"],
                    "total_goals_supported": metrics["goal_support_count"],
                },
                "insights": insights,
                "recommendations": recommendations,
                "metrics": metrics,  # Phase 3: Include standard metrics
            }
        )

    @requires_graph_intelligence("get_habit_knowledge_reinforcement")
    async def get_habit_knowledge_reinforcement(
        self, uid: str, depth: int = 2, min_confidence: float = 0.7
    ) -> Result[dict[str, Any]]:
        """
        Get habit's knowledge practice tracking using Phase 1-4.

        Analyzes how this habit reinforces knowledge through practice:
        - Knowledge units actively reinforced
        - Practice frequency and effectiveness
        - Knowledge mastery progression
        - Learning opportunities

        Args:
            uid: Habit UID,
            depth: Graph traversal depth (default: 2)

        Returns:
            Result containing knowledge reinforcement analysis:
            {
                "habit": Habit,
                "knowledge_reinforcement": {
                    "reinforced_knowledge": List[Ku],
                    "practice_frequency": str,  # from habit
                    "practice_effectiveness_score": float,
                    "mastery_progression": List[Dict],
                    "knowledge_coverage": float  # 0-1
                },
                "learning_analysis": {
                    "primary_knowledge_areas": List[str],
                    "skill_development_rate": float,
                    "learning_consistency": float
                },
                "graph_context": GraphContext
            }

        Example:
            ```python
            result = await habits_intel.get_habit_knowledge_reinforcement("habit_1")
            analysis = result.value

            kr = analysis["knowledge_reinforcement"]
            print(f"Reinforces {len(kr['reinforced_knowledge'])} areas")
            print(f"Effectiveness: {kr['practice_effectiveness_score']}")
            ```

        Phase 5 Refactoring (Jan 2026):
        - Uses BaseIntelligenceService._analyze_entity_with_context template
        """
        # Phase 5: Use base class template for standardized analysis
        analysis_result = await self._analyze_entity_with_context(
            uid=uid,
            context_method="get_habit_cross_domain_context",
            context_type=HabitCrossContext,
            metrics_fn=calculate_habit_metrics,
            depth=depth,
            min_confidence=min_confidence,
        )

        if analysis_result.is_error:
            return analysis_result

        analysis = analysis_result.value
        habit = self._to_domain_model(analysis["entity"], HabitDTO, Habit)
        context: HabitCrossContext = analysis["context"]
        metrics = analysis["metrics"]

        # Return UIDs directly - no placeholder dicts
        knowledge_reinforcement_uids = context.knowledge_reinforcement_uids

        # Calculate practice effectiveness
        practice_effectiveness = self._calculate_practice_effectiveness(
            habit, len(knowledge_reinforcement_uids)
        )

        # Analyze mastery progression per knowledge UID
        mastery_progression = [
            {
                "knowledge_uid": ku_uid,
                "practice_count": habit.current_streak,
                "estimated_mastery": min(1.0, practice_effectiveness * 0.1),
            }
            for ku_uid in knowledge_reinforcement_uids
        ]

        # Calculate knowledge coverage
        knowledge_coverage = min(1.0, len(knowledge_reinforcement_uids) / 10.0)

        # Learning analysis
        consistency_score = habit.calculate_consistency_score()
        learning_analysis = {
            "primary_knowledge_uids": knowledge_reinforcement_uids[:3],
            "skill_development_rate": practice_effectiveness / 10.0,
            "learning_consistency": consistency_score,
        }

        return Result.ok(
            {
                "habit": habit,
                "knowledge_reinforcement": {
                    "knowledge_reinforcement_uids": knowledge_reinforcement_uids,
                    "practice_frequency": habit.recurrence_pattern.value,
                    "practice_effectiveness_score": practice_effectiveness,
                    "mastery_progression": mastery_progression,
                    "knowledge_coverage": knowledge_coverage,
                },
                "learning_analysis": learning_analysis,
                "metrics": metrics,  # Phase 3: Include standard metrics
            }
        )

    @requires_graph_intelligence("get_habit_goal_support")
    async def get_habit_goal_support(
        self, uid: str, depth: int = 2, min_confidence: float = 0.7
    ) -> Result[dict[str, Any]]:
        """
        Get habit's goal contribution analysis using Phase 1-4.

        Analyzes how this habit supports user's goals:
        - Goals directly supported
        - Contribution strength to each goal
        - Goal alignment score
        - Progress impact on goal completion

        Args:
            uid: Habit UID,
            depth: Graph traversal depth (default: 2)

        Returns:
            Result containing goal support analysis:
            {
                "habit": Habit,
                "goal_support": {
                    "supported_goals": List[Goal],
                    "goal_contributions": List[Dict],  # per-goal contribution
                    "alignment_score": float,  # 0-10
                    "total_goals_supported": int,
                    "primary_goal": Optional[Goal]
                },
                "impact_analysis": {
                    "high_impact": bool,  # alignment > 7.0
                    "goal_aligned": bool,  # supports goals
                    "consistency_matters": bool  # high contribution
                },
                "recommendations": {
                    "increase_frequency": bool,
                    "link_more_goals": bool,
                    "maintain_consistency": bool
                },
                "graph_context": GraphContext
            }

        Example:
            ```python
            result = await habits_intel.get_habit_goal_support("habit_1")
            analysis = result.value

            gs = analysis["goal_support"]
            print(f"Supports {gs['total_goals_supported']} goals")
            print(f"Alignment: {gs['alignment_score']}/10")

            for contrib in gs["goal_contributions"]:
                print(f"  {contrib['goal_title']}: {contrib['contribution_strength']}")
            ```

        Phase 5 Refactoring (Jan 2026):
        - Uses BaseIntelligenceService._analyze_entity_with_context template
        """
        # Phase 5: Use base class template for standardized analysis
        analysis_result = await self._analyze_entity_with_context(
            uid=uid,
            context_method="get_habit_cross_domain_context",
            context_type=HabitCrossContext,
            metrics_fn=calculate_habit_metrics,
            recommendations_fn=self._generate_goal_support_recommendations,
            depth=depth,
            min_confidence=min_confidence,
        )

        if analysis_result.is_error:
            return analysis_result

        analysis = analysis_result.value
        habit = self._to_domain_model(analysis["entity"], HabitDTO, Habit)
        context: HabitCrossContext = analysis["context"]
        metrics = analysis["metrics"]

        # Return UIDs directly - no placeholder dicts
        supporting_goal_uids = context.linked_goal_uids

        # Calculate goal contributions
        consistency_score = habit.calculate_consistency_score()
        goal_contributions = [
            {
                "goal_uid": goal_uid,
                "contribution_strength": consistency_score * 2.0,  # 0-2 scale
                "estimated_impact": "high"
                if consistency_score > 0.7
                else "medium"
                if consistency_score > 0.4
                else "low",
            }
            for goal_uid in supporting_goal_uids
        ]

        # Calculate alignment score
        alignment_score = min(10.0, len(supporting_goal_uids) * 2.0 * consistency_score)

        # Identify primary goal UID (if any)
        primary_goal_uid = supporting_goal_uids[0] if supporting_goal_uids else None

        # Impact analysis from metrics
        impact_analysis = {
            "high_impact": alignment_score > 7.0,
            "goal_aligned": metrics["has_goal_connection"],
            "consistency_matters": consistency_score > 0.7,
        }

        # Recommendations dict
        recommendations = {
            "increase_frequency": consistency_score < 0.5,
            "link_more_goals": metrics["goal_support_count"] < 2,
            "maintain_consistency": consistency_score >= 0.7,
        }

        return Result.ok(
            {
                "habit": habit,
                "goal_support": {
                    "supporting_goal_uids": supporting_goal_uids,
                    "goal_contributions": goal_contributions,
                    "alignment_score": alignment_score,
                    "total_goals_supported": metrics["goal_support_count"],
                    "primary_goal_uid": primary_goal_uid,
                },
                "impact_analysis": impact_analysis,
                "recommendations": recommendations,
                "metrics": metrics,  # Phase 3: Include standard metrics
            }
        )

    # ========================================================================
    # PRIVATE HELPER METHODS
    # ========================================================================

    def _calculate_practice_effectiveness(self, habit: Habit, knowledge_count: int) -> float:
        """Calculate practice effectiveness score for knowledge reinforcement.

        Uses MetricsCalculator for consistent calculations.

        Considers:
        - Habit consistency score
        - Number of knowledge areas covered
        - Streak count (if available)

        Args:
            habit: Habit domain model
            knowledge_count: Number of knowledge areas reinforced

        Returns:
            Effectiveness score (0-10 scale)
        """
        consistency = habit.calculate_consistency_score()
        streak = habit.current_streak if habit.current_streak > 0 else 1

        # Base effectiveness from consistency (0-5 points)
        base_score = consistency * 5.0

        # Bonus for knowledge coverage (0-3 points, capped)
        knowledge_bonus = MetricsCalculator.clamp(knowledge_count * 0.5, max_val=3.0)

        # Bonus for streak (0-2 points, capped)
        streak_bonus = MetricsCalculator.clamp((streak / 30.0) * 2.0, max_val=2.0)

        return base_score + knowledge_bonus + streak_bonus

    def _generate_performance_recommendations(
        self, entity: Any, context: HabitCrossContext, metrics: dict[str, Any]
    ) -> list[str]:
        """Generate recommendations for habit performance analysis.

        Uses RecommendationEngine for structured threshold-based recommendations.
        """
        return (
            RecommendationEngine()
            .with_metrics(metrics)
            .add_threshold_check(
                "integration_score",
                threshold=0.5,
                message="Integrate this habit with more life areas",
                comparison="lt",
            )
            .add_conditional(
                not metrics.get("has_goal_connection", False),
                "Link this habit to supporting goals",
            )
            .add_conditional(
                not metrics.get("is_knowledge_builder", False),
                "Connect this habit to knowledge areas for learning reinforcement",
            )
            .add_threshold_check(
                "goal_support_count",
                threshold=2,
                message="Consider aligning with more goals for greater impact",
                comparison="lt",
            )
            .build()
        )

    def _generate_goal_support_recommendations(
        self, entity: Any, context: HabitCrossContext, metrics: dict[str, Any]
    ) -> list[str]:
        """Generate recommendations for habit goal support analysis.

        Uses RecommendationEngine for structured threshold-based recommendations.
        """
        goal_support_count = metrics.get("goal_support_count", 0)

        return (
            RecommendationEngine()
            .with_metrics(metrics)
            .add_conditional(
                goal_support_count == 0,
                "Link this habit to at least one goal",
            )
            .add_conditional(
                0 < goal_support_count < 2,
                "Consider supporting additional goals with this habit",
            )
            .add_conditional(
                not metrics.get("is_principle_aligned", False),
                "Align this habit with your core principles",
            )
            .add_threshold_check(
                "integration_score",
                threshold=0.67,
                message="This habit is well-integrated - maintain consistency",
                comparison="gte",
            )
            .build()
        )

    # ========================================================================
    # EVENT HANDLERS
    # ========================================================================

    async def handle_habit_streak_broken(self, event: HabitStreakBroken) -> None:
        """Generate recovery insights when a habit streak breaks.

        Event-driven handler that analyzes streak breaks to provide
        contextual recovery suggestions. This enables cross-domain
        intelligence by connecting habit failures to knowledge reinforcement.

        The handler:
        1. Gets habit context (title, frequency, knowledge connections)
        2. Queries knowledge units this habit reinforces
        3. Calculates recovery difficulty based on streak length
        4. Logs structured insights for future surfacing

        Args:
            event: HabitStreakBroken event with streak context

        Raises:
            Exception: Re-raised after logging for fail-fast behavior.
        """
        # 1. Get habit details
        habit_result = await self.backend.get(event.habit_uid)
        if habit_result.is_error:
            self.logger.warning(f"Failed to get habit for streak analysis: {event.habit_uid}")
            return

        habit = habit_result.value
        if not habit:
            self.logger.warning(f"Habit not found for streak analysis: {event.habit_uid}")
            return

        # 2. Query knowledge reinforcement relationships
        knowledge_uids: list[str] = []
        if self.relationships is not None:
            rel_result = await self.relationships.get_related_uids(
                event.habit_uid,
                RelationshipName.REINFORCES_KNOWLEDGE.value,
                "outgoing",
            )
            if rel_result.is_ok:
                knowledge_uids = rel_result.value

        # 3. Calculate recovery metrics
        streak_length = event.streak_length
        days_since = event.days_since_last_completion

        # Recovery difficulty: longer streaks and longer gaps = harder recovery
        recovery_difficulty = self._calculate_recovery_difficulty(
            streak_length=streak_length,
            days_since_completion=days_since,
        )

        # 4. Determine recovery suggestion based on difficulty
        if recovery_difficulty < 0.3:
            suggestion = "Quick restart - your momentum is still fresh"
        elif recovery_difficulty < 0.6:
            suggestion = "Gentle restart - consider a lighter version of this habit"
        else:
            suggestion = "Fresh start - rebuild gradually with small wins"

        # 5. Log structured insights
        self.logger.info(
            f"Habit streak broken: {habit.name}",
            extra={
                "habit_uid": event.habit_uid,
                "user_uid": event.user_uid,
                "streak_length": streak_length,
                "days_since_last": days_since,
                "recovery_difficulty": round(recovery_difficulty, 2),
                "knowledge_areas_affected": len(knowledge_uids),
                "recovery_suggestion": suggestion,
                "event_type": "habit.streak_broken.analyzed",
            },
        )

        # Log knowledge impact if habit reinforced knowledge
        if knowledge_uids:
            self.logger.info(
                f"Knowledge reinforcement interrupted for {len(knowledge_uids)} areas",
                extra={
                    "habit_uid": event.habit_uid,
                    "knowledge_uids": knowledge_uids[:5],  # Log first 5
                    "event_type": "habit.knowledge_impact",
                },
            )

    def _calculate_recovery_difficulty(
        self,
        streak_length: int,
        days_since_completion: int,
    ) -> float:
        """Calculate recovery difficulty score (0.0 - 1.0).

        Factors:
        - Longer streaks are harder to restart (more emotional investment lost)
        - Longer gaps make it harder to resume (habit momentum lost)

        Returns:
            Recovery difficulty from 0.0 (easy) to 1.0 (hard)
        """
        # Streak factor: logarithmic scaling (7-day streak = 0.3, 30-day = 0.5, 100-day = 0.7)
        import math

        streak_factor = min(1.0, math.log10(max(1, streak_length) + 1) / 2.5)

        # Gap factor: linear scaling capped at 14 days
        gap_factor = min(1.0, days_since_completion / 14.0)

        # Weighted combination (streak matters more than gap)
        difficulty = (streak_factor * 0.6) + (gap_factor * 0.4)

        return MetricsCalculator.clamp(difficulty, min_val=0.0, max_val=1.0)

    async def handle_habit_missed(self, event: HabitMissed) -> None:
        """Track habit difficulty patterns when habits are missed.

        Event-driven handler that detects difficulty patterns when habits
        are missed. Unlike streak_broken (fires once), this fires for each
        missed occurrence, enabling pattern detection.

        The handler:
        1. Gets habit details (title, frequency, knowledge connections)
        2. Analyzes consecutive misses to detect difficulty patterns
        3. Calculates days overdue impact
        4. Logs structured insights for difficulty detection

        Args:
            event: HabitMissed event with miss context

        Raises:
            Exception: Re-raised after logging for fail-fast behavior.
        """
        # 1. Get habit details
        habit_result = await self.backend.get(event.habit_uid)
        if habit_result.is_error:
            self.logger.warning(f"Failed to get habit for miss analysis: {event.habit_uid}")
            return

        habit = habit_result.value
        if not habit:
            self.logger.warning(f"Habit not found for miss analysis: {event.habit_uid}")
            return

        # 2. Analyze consecutive misses for difficulty detection
        consecutive_misses = event.consecutive_misses
        days_overdue = event.days_overdue

        # 3. Calculate difficulty indicators
        is_difficult = consecutive_misses >= 3
        is_very_difficult = consecutive_misses >= 5
        severity = self._calculate_miss_severity(consecutive_misses, days_overdue)

        # 4. Generate difficulty assessment
        if is_very_difficult:
            difficulty_assessment = "very_difficult"
            suggestion = "Consider reducing frequency or simplifying this habit"
        elif is_difficult:
            difficulty_assessment = "difficult"
            suggestion = "Try a smaller version of this habit to rebuild momentum"
        elif consecutive_misses >= 2:
            difficulty_assessment = "challenging"
            suggestion = "Set a reminder or link this habit to an existing routine"
        else:
            difficulty_assessment = "normal"
            suggestion = None

        # 5. Log structured insights
        self.logger.info(
            f"Habit missed: {habit.name}",
            extra={
                "habit_uid": event.habit_uid,
                "user_uid": event.user_uid,
                "consecutive_misses": consecutive_misses,
                "days_overdue": days_overdue,
                "severity": severity,
                "difficulty_assessment": difficulty_assessment,
                "frequency": habit.recurrence_pattern.value
                if habit.recurrence_pattern
                else "unknown",
                "event_type": "habit.missed.analyzed",
            },
        )

        # Log difficulty insight for significant patterns
        if is_difficult:
            self.logger.info(
                f"Habit difficulty detected: {consecutive_misses} consecutive misses",
                extra={
                    "habit_uid": event.habit_uid,
                    "user_uid": event.user_uid,
                    "consecutive_misses": consecutive_misses,
                    "difficulty_assessment": difficulty_assessment,
                    "suggestion": suggestion,
                    "event_type": "habit.difficulty.detected",
                },
            )

    def _calculate_miss_severity(
        self,
        consecutive_misses: int,
        days_overdue: int,
    ) -> str:
        """Calculate miss severity based on pattern.

        Args:
            consecutive_misses: Number of consecutive misses
            days_overdue: Days since scheduled completion

        Returns:
            Severity level: "low", "medium", "high", "critical"
        """
        # Score based on consecutive misses (0-6 points)
        miss_score = min(6, consecutive_misses)

        # Score based on days overdue (0-4 points)
        overdue_score = min(4, days_overdue // 2)

        total_score = miss_score + overdue_score

        if total_score >= 8:
            return "critical"
        elif total_score >= 5:
            return "high"
        elif total_score >= 2:
            return "medium"
        else:
            return "low"

    # ========================================================================
    # DUAL-TRACK ASSESSMENT (ADR-030 - January 2026)
    # ========================================================================

    async def assess_consistency_dual_track(
        self,
        habit_uid: str,
        user_uid: str,
        user_consistency_level: ConsistencyLevel,
        user_evidence: str,
        user_reflection: str | None = None,
    ) -> "Result[DualTrackResult[ConsistencyLevel]]":
        """
        Dual-track consistency assessment for habits.

        Compares user self-assessment (vision) with system measurement (action)
        to generate perception gap analysis and insights.

        This implements SKUEL's core philosophy:
        "The user's vision is understood via the words they use to communicate,
        the UserContext is determined via user's actions."

        Uses BaseIntelligenceService._dual_track_assessment() template (ADR-030).

        Args:
            habit_uid: Habit UID to assess
            user_uid: User making the assessment
            user_consistency_level: User's self-reported consistency level
            user_evidence: User's evidence for their assessment
            user_reflection: Optional reflection on their consistency

        Returns:
            Result[DualTrackResult[ConsistencyLevel]] with dual-track analysis

        Example:
            >>> from core.models.enums.activity_enums import ConsistencyLevel
            >>> result = await service.assess_consistency_dual_track(
            ...     habit_uid="habit.morning-meditation",
            ...     user_uid="user.mike",
            ...     user_consistency_level=ConsistencyLevel.CONSISTENT,
            ...     user_evidence="I meditate most mornings",
            ...     user_reflection="Sometimes skip on weekends",
            ... )
            >>> if result.is_ok:
            ...     dual_track = result.value
            ...     print(f"Gap: {dual_track.perception_gap:.0%}")
        """
        return await self._dual_track_assessment(
            uid=habit_uid,
            user_uid=user_uid,
            user_level=user_consistency_level,
            user_evidence=user_evidence,
            user_reflection=user_reflection,
            system_calculator=self._calculate_system_consistency,
            level_scorer=self._consistency_level_to_score,
            entity_type="habit",
            insight_generator=self._generate_consistency_gap_insights,
            recommendation_generator=self._generate_consistency_gap_recommendations,
        )

    async def _calculate_system_consistency(
        self, habit: Habit, _user_uid: str
    ) -> tuple[ConsistencyLevel, float, list[str]]:
        """
        Calculate system consistency from habit metrics.

        Examines:
        - Success rate (completions / attempts)
        - Current streak
        - Best streak
        - Recent completion pattern

        Args:
            habit: The Habit entity
            _user_uid: User UID (unused in habit-specific calculation)

        Returns:
            Tuple of (ConsistencyLevel, score, evidence_list)
        """
        evidence: list[str] = []

        # Primary metric: success rate
        success_rate = habit.success_rate  # 0.0-1.0
        evidence.append(f"Success rate: {success_rate * 100:.0f}%")

        # Streak metrics
        current_streak = habit.current_streak
        best_streak = habit.best_streak

        if current_streak > 0:
            evidence.append(f"Current streak: {current_streak} days")
        if best_streak > 0:
            evidence.append(f"Best streak: {best_streak} days")

        # Calculate streak factor (bonus for active streaks)
        streak_factor = 0.0
        if current_streak >= 21:  # 3 weeks = established habit
            streak_factor = 0.2
            evidence.append("Habit is well-established (21+ day streak)")
        elif current_streak >= 7:  # 1 week = building
            streak_factor = 0.1
            evidence.append("Building momentum (7+ day streak)")
        elif current_streak == 0 and habit.total_completions > 0:
            streak_factor = -0.1
            evidence.append("Streak recently broken")

        # Calculate consistency score from Habit model
        consistency_score = habit.calculate_consistency_score()

        # Final score: weighted combination
        score = min(1.0, (success_rate * 0.6) + (consistency_score * 0.3) + streak_factor + 0.1)

        # Adjust for very new habits (give benefit of doubt)
        if habit.total_completions < 5:
            score = max(score, 0.5)  # At least "building" for new habits
            evidence.append("Early stage habit - limited data")

        # Convert score to level
        system_level = ConsistencyLevel.from_score(score)

        return system_level, score, evidence

    def _consistency_level_to_score(self, level: ConsistencyLevel) -> float:
        """Convert ConsistencyLevel to numeric score (0.0-1.0)."""
        return level.to_score()

    def _generate_consistency_gap_insights(
        self, direction: str, gap: float, entity_name: str
    ) -> list[str]:
        """Generate consistency-specific gap insights."""
        insights: list[str] = []

        if direction == "aligned":
            insights.append(
                f"Your self-perception of consistency with '{entity_name}' matches your tracking data. "
                "This indicates accurate self-awareness about your habit patterns."
            )
        elif direction == "user_higher":
            insights.append(
                f"Your self-assessment is more positive than your habit data suggests "
                f"(gap: {gap:.0%}). Consider: Are you remembering completions that weren't tracked?"
            )
            if gap > 0.3:
                insights.append(
                    "This significant gap may indicate memory bias - we often remember doing things "
                    "more consistently than we actually did. The data helps ground our perception."
                )
        else:  # system_higher
            insights.append(
                f"Your habit data shows stronger consistency than you perceive (gap: {gap:.0%}). "
                "You're doing better than you think!"
            )
            if gap > 0.3:
                insights.append(
                    "Consider why you underestimate your consistency - "
                    "focusing on misses rather than successes can skew perception."
                )

        return insights

    def _generate_consistency_gap_recommendations(
        self, direction: str, _gap: float, entity: Any, evidence: list[str]
    ) -> list[str]:
        """Generate consistency-specific gap recommendations."""
        recommendations: list[str] = []
        habit = entity

        if direction == "aligned":
            recommendations.append(
                "Continue your current approach - your self-awareness is accurate."
            )
            if habit.current_streak > 0:
                recommendations.append(
                    f"Protect your {habit.current_streak}-day streak - momentum matters!"
                )
        elif direction == "user_higher":
            recommendations.append(
                "Trust the data - it provides an objective view of your consistency."
            )
            recommendations.append(
                "Consider setting reminders to help bridge the gap between intention and action."
            )
            if any("streak" in e.lower() and "broken" in e.lower() for e in evidence):
                recommendations.append(
                    "Focus on rebuilding your streak with small, achievable completions."
                )
        else:  # system_higher
            recommendations.append(
                "Celebrate your consistency - you're more disciplined than you realize!"
            )
            if evidence:
                recommendations.append(f"Your data shows: {evidence[0]}")
            recommendations.append(
                "Consider tracking wins more visibly to improve self-perception."
            )

        return recommendations[:4]
