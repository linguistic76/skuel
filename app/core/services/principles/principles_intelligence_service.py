"""
Principles Intelligence Service - Pure Cypher Graph Analytics
=========================================================

Handles Pure Cypher graph intelligence queries for principles.

Responsibilities:
- Get principle with graph context (Phase 1-4)
- Assess principle alignment using APOC
- Analyze adherence trends over time
- Detect principle conflicts

Part of the PrinciplesService decomposition.
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import TYPE_CHECKING, Any

from core.events.principle_events import (
    PrincipleConflictRevealed,
    PrincipleReflectionRecorded,
    PrincipleStrengthChanged,
)
from core.models.enums import Domain
from core.models.enums.ku_enums import AlignmentLevel
from core.models.insight.persisted_insight import InsightImpact, InsightType, PersistedInsight
from core.models.ku.ku import Ku
from core.models.ku.ku_dto import KuDTO
from core.models.relationship_names import RelationshipName

# NOTE (November 2025): Removed Has* protocol imports - Principle model is well-typed
# - Principle.strength: PrincipleStrength (direct access)
# - Principle does NOT have adherence_score - use default 0.5 where needed
from core.models.shared.dual_track import DualTrackResult
from core.services.base_analytics_service import BaseAnalyticsService
from core.services.intelligence import (
    GraphContextOrchestrator,
    MetricsCalculator,
    PatternAnalyzer,
    PrincipleCrossContext,
    RecommendationEngine,
    analyze_activity_trajectory,
    calculate_principle_metrics,
    determine_trend_from_rate,
)
from core.services.protocols.domain_protocols import PrinciplesOperations
from core.utils.decorators import requires_graph_intelligence
from core.utils.logging import get_logger
from core.utils.result_simplified import Errors, Result

if TYPE_CHECKING:
    from core.models.graph_context import GraphContext
    from core.services.insight.insight_store import InsightStore
    from core.services.protocols.domain_protocols import PrinciplesRelationshipOperations

logger = get_logger(__name__)


class PrinciplesIntelligenceService(BaseAnalyticsService[PrinciplesOperations, Ku]):
    """
    Pure Cypher graph intelligence for principles.

    NOTE: This service extends BaseAnalyticsService (ADR-030) and has NO AI dependencies.
    It uses pure graph queries and Python calculations - no LLM or embeddings.

    Responsibilities:
    - Get principle with graph context (Phase 1-4)
    - Assess principle alignment
    - Analyze adherence trends
    - Detect principle conflicts


    Source Tag: "principles_intelligence_service_explicit"
    - Format: "principles_intelligence_service_explicit" for user-created relationships
    - Format: "principles_intelligence_service_inferred" for system-generated relationships

    Confidence Scoring:
    - 0.9+: User explicitly defined relationship
    - 0.7-0.9: Inferred from principles_intelligence metadata
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
    _service_name = "principles.intelligence"

    def __init__(
        self,
        backend: PrinciplesOperations,
        graph_intelligence_service=None,
        relationship_service: PrinciplesRelationshipOperations | None = None,
        insight_store: InsightStore | None = None,
    ) -> None:
        """
        Initialize principles intelligence service.

        Args:
            backend: Backend for principle operations,
            graph_intelligence_service: GraphIntelligenceService for pure Cypher analytics,
            relationship_service: PrinciplesRelationshipOperations protocol for specialized relationship queries
            insight_store: InsightStore for persisting event-driven insights (optional)
        """
        super().__init__(
            backend=backend,
            graph_intelligence_service=graph_intelligence_service,
            relationship_service=relationship_service,
        )
        self.insight_store = insight_store

        # Initialize GraphContextOrchestrator for get_with_context pattern (Phase 2)
        if graph_intelligence_service:
            self.orchestrator = GraphContextOrchestrator[Ku, KuDTO](
                service=self,
                backend_get_method="get",  # PrinciplesService uses generic 'get'
                dto_class=KuDTO,
                model_class=Ku,
                domain=Domain.PRINCIPLES,
            )

    # ========================================================================
    # DOMAIN-SPECIFIC CONTRACT
    # ========================================================================

    @property
    def entity_label(self) -> str:
        """Return the graph label for Principle entities."""
        return "Principle"

    # ========================================================================
    # INTELLIGENCEOPERATIONS PROTOCOL METHODS (January 2026)
    # These methods implement the IntelligenceOperations protocol for use
    # with IntelligenceRouteFactory.
    # ========================================================================

    async def get_with_context(self, uid: str, depth: int = 2) -> Result[tuple[Ku, GraphContext]]:
        """
        Get principle with full graph context.

        Protocol method: Maps to get_principle_with_context.
        Used by IntelligenceRouteFactory for GET /api/principles/context route.

        Args:
            uid: Principle UID
            depth: Graph traversal depth (default: 2)

        Returns:
            Result containing (Principle, GraphContext) tuple
        """
        return await self.get_principle_with_context(uid, depth)

    async def get_performance_analytics(
        self, user_uid: str, _period_days: int = 30
    ) -> Result[dict[str, Any]]:
        """
        Get principle performance analytics for a user.

        Protocol method: Aggregates principle metrics over time period.
        Used by IntelligenceRouteFactory for GET /api/principles/analytics route.

        Args:
            user_uid: User UID
            _period_days: Placeholder - not yet implemented. Will filter by period when added.

        Returns:
            Result containing analytics data dict

        Note: _period_days uses underscore prefix per CLAUDE.md convention to indicate
        "API contract defined, implementation deferred". Currently calculates analytics
        over ALL principles. Future enhancement: filter by created_at within period.
        """
        # Get all principles for user
        principles_result = await self.backend.find_by(user_uid=user_uid)
        if principles_result.is_error:
            return Result.fail(principles_result.expect_error())

        principles = principles_result.value or []

        # Calculate analytics
        total_principles = len(principles)
        active_principles = [p for p in principles if p.is_active]

        # Count by strength
        core_principles = [p for p in principles if p.strength and p.strength.value == "CORE"]
        strong_principles = [p for p in principles if p.strength and p.strength.value == "STRONG"]

        return Result.ok(
            {
                "user_uid": user_uid,
                "period_days": _period_days,
                "total_principles": total_principles,
                "active_principles": len(active_principles),
                "core_principles": len(core_principles),
                "strong_principles": len(strong_principles),
                "analytics": {
                    "total": total_principles,
                    "active": len(active_principles),
                    "core": len(core_principles),
                    "strong": len(strong_principles),
                },
            }
        )

    async def get_domain_insights(
        self, uid: str, min_confidence: float = 0.7
    ) -> Result[dict[str, Any]]:
        """
        Get domain-specific insights for a principle.

        Protocol method: Maps to assess_principle_alignment.
        Used by IntelligenceRouteFactory for GET /api/principles/insights route.

        Args:
            uid: Principle UID
            min_confidence: Minimum confidence threshold (default: 0.7)

        Returns:
            Result containing insights data dict
        """
        return await self.assess_principle_alignment(uid, min_confidence)

    # ================================================================================
    # GRAPH INTELLIGENCE METHODS
    # ================================================================================

    @requires_graph_intelligence("get_principle_with_context")
    async def get_principle_with_context(
        self, uid: str, depth: int = 2
    ) -> Result[tuple[Ku, GraphContext]]:
        """
        Get principle with full graph context using pure Cypher graph intelligence.

        Automatically selects optimal query type based on principle's suggested intent:
        - RELATIONSHIP → Activities aligned with principle
        - HIERARCHICAL → Principle hierarchy and dependencies
        - AGGREGATION → Alignment statistics and trends
        - Default → Comprehensive principle ecosystem

        This replaces multiple sequential queries with a single Pure Cypher query,
        achieving 8-10x performance improvement.

        Args:
            uid: Principle UID,
            depth: Graph traversal depth (default: 2)

        Returns:
            Result containing (principle, GraphContext) tuple
        """
        # Use GraphContextOrchestrator pattern (Phase 2 consolidation)
        # Orchestrator is guaranteed to exist when @requires_graph_intelligence passes
        if not self.orchestrator:
            return Result.fail(
                Errors.system(
                    message="GraphContextOrchestrator not initialized",
                    operation="get_principle_with_context",
                )
            )
        return await self.orchestrator.get_with_context(uid=uid, depth=depth)

    @requires_graph_intelligence("assess_principle_alignment")
    async def assess_principle_alignment(
        self, principle_uid: str, min_confidence: float = 0.7
    ) -> Result[dict[str, Any]]:
        """
        Assess how well user is living by a principle using Phase 1-4.

        Provides comprehensive alignment assessment including:
        - Recent activities aligned with principle
        - Adherence score and trends
        - Activity breakdown by domain
        - Alignment gaps and recommendations

        Args:
            principle_uid: Principle UID
            min_confidence: Minimum confidence for relationships (default: 0.7)

        Returns:
            Result containing alignment assessment dictionary

        Phase 5 Refactoring (Jan 2026):
        - Uses BaseIntelligenceService._analyze_entity_with_context template
        """
        # Phase 5: Use base class template for standardized analysis
        analysis_result = await self._analyze_entity_with_context(
            uid=principle_uid,
            context_method="get_principle_cross_domain_context",
            context_type=PrincipleCrossContext,
            metrics_fn=calculate_principle_metrics,
            recommendations_fn=self._generate_alignment_recommendations,
            min_confidence=min_confidence,
        )

        if analysis_result.is_error:
            return analysis_result

        analysis = analysis_result.value
        principle = analysis["entity"]
        context: PrincipleCrossContext = analysis["context"]
        metrics = analysis["metrics"]

        # Extract activities from typed context
        recent_tasks = []  # Principles don't directly relate to tasks
        recent_choices = [{"uid": uid} for uid in context.choice_uids]
        recent_habits = [{"uid": uid} for uid in context.habit_uids]
        guided_goals = [{"uid": uid} for uid in context.goal_uids]

        counts = {
            "tasks": 0,
            "choices": metrics["choice_count"],
            "habits": metrics["habit_count"],
            "goals": metrics["goal_count"],
            "total": metrics["total_influence_count"],
        }

        # Determine trend
        recent_trend = self._determine_trend(counts["total"])

        return Result.ok(
            {
                "principle": principle,
                "alignment_score": metrics["adherence_score"],
                "recent_activities": counts["total"],
                "activities_breakdown": {
                    "tasks": recent_tasks,
                    "choices": recent_choices,
                    "habits": recent_habits,
                    "goals": guided_goals,
                },
                "activity_counts": counts,
                "alignment_assessment": {
                    "needs_attention": metrics["needs_attention"],
                    "strong_alignment": metrics["strong_alignment"],
                    "consistent_practice": metrics["consistent_practice"],
                },
                "recent_trend": recent_trend,
                "recommendations": analysis["recommendations"],
                "metrics": metrics,  # Phase 5: Include standard metrics
                "graph_context": {
                    "goal_count": metrics["goal_count"],
                    "habit_count": metrics["habit_count"],
                    "choice_count": metrics["choice_count"],
                    "knowledge_count": metrics["knowledge_count"],
                },
            }
        )

    def _generate_alignment_recommendations(
        self, entity: Any, context: PrincipleCrossContext, metrics: dict[str, Any]
    ) -> list[str]:
        """Generate recommendations for principle alignment assessment.

        Uses RecommendationEngine for structured threshold-based recommendations.
        """
        adherence_score = metrics.get("adherence_score", 0.5)

        return (
            RecommendationEngine()
            .with_metrics(metrics)
            .add_conditional(
                metrics.get("needs_attention", False),
                f"Alignment score is low ({adherence_score:.0%}) - "
                "consider creating goals or habits that embody this principle",
            )
            .add_conditional(
                metrics.get("goal_count", 0) == 0,
                "Create at least one goal guided by this principle",
            )
            .add_conditional(
                metrics.get("habit_count", 0) == 0,
                "Establish a daily or weekly habit that embodies this principle",
            )
            .add_threshold_check(
                "total_influence_count",
                threshold=5,
                message="Increase activities aligned with this principle - consistency builds adherence",
                comparison="lt",
            )
            .add_conditional(
                metrics.get("strong_alignment", False),
                "Excellent alignment! You're living this principle consistently",
            )
            .build()
        )

    # ========================================================================
    # DUAL-TRACK ASSESSMENT (ADR-030 - January 2026)
    # ========================================================================

    async def assess_alignment_dual_track(
        self,
        principle_uid: str,
        user_uid: str,
        user_alignment_level: AlignmentLevel,
        user_evidence: str,
        user_reflection: str | None = None,
    ) -> Result[DualTrackResult[AlignmentLevel]]:
        """
        Dual-track alignment assessment for principles.

        Compares user self-assessment (vision) with system measurement (action)
        to generate perception gap analysis and insights.

        This implements SKUEL's core philosophy:
        "The user's vision is understood via the words they use to communicate,
        the UserContext is determined via user's actions."

        Uses BaseIntelligenceService._dual_track_assessment() template (ADR-030).

        Args:
            principle_uid: Principle UID to assess
            user_uid: User making the assessment
            user_alignment_level: User's self-reported alignment level
            user_evidence: User's evidence for their assessment
            user_reflection: Optional reflection on their alignment

        Returns:
            Result[DualTrackResult[AlignmentLevel]] with dual-track analysis

        Example:
            >>> from core.models.enums.ku_enums import AlignmentLevel
            >>> result = await service.assess_alignment_dual_track(
            ...     principle_uid="principle.integrity",
            ...     user_uid="user_mike",
            ...     user_alignment_level=AlignmentLevel.ALIGNED,
            ...     user_evidence="I always act with integrity",
            ...     user_reflection="This is my core value",
            ... )
            >>> if result.is_ok:
            ...     dual_track = result.value
            ...     print(f"Gap: {dual_track.perception_gap:.0%}")
            ...     print(f"Direction: {dual_track.gap_direction}")
        """

        return await self._dual_track_assessment(
            uid=principle_uid,
            user_uid=user_uid,
            user_level=user_alignment_level,
            user_evidence=user_evidence,
            user_reflection=user_reflection,
            system_calculator=self._calculate_system_alignment_for_dual_track,
            level_scorer=self._alignment_level_to_score,
            entity_type="principle",
            insight_generator=self._generate_principle_gap_insights,
            recommendation_generator=self._generate_principle_gap_recommendations,
            store_callback=self._store_alignment_assessment,
        )

    async def _calculate_system_alignment_for_dual_track(
        self, principle: Ku, user_uid: str
    ) -> tuple[AlignmentLevel, float, list[str]]:
        """
        Calculate system alignment from goals and habits.

        Examines:
        - Goals guided by this principle
        - Habits inspired by this principle
        - Recent choices aligned with this principle

        Args:
            principle: The Principle entity
            user_uid: User UID

        Returns:
            Tuple of (AlignmentLevel, score, evidence_list)
        """

        evidence: list[str] = []
        total_score = 0.0
        count = 0

        # Check connected goals and habits via relationships
        if self.relationships:
            # Get guided goals
            goals_result = await self.relationships.get_related_uids(
                principle.uid, RelationshipName.ALIGNED_WITH_PRINCIPLE.value, "incoming"
            )
            if goals_result.is_ok and goals_result.value:
                for goal_uid in goals_result.value:
                    evidence.append(f"Goal '{goal_uid}' embodies this principle")
                    total_score += 0.75  # MOSTLY_ALIGNED score
                    count += 1

            # Get inspired habits
            habits_result = await self.relationships.get_related_uids(
                principle.uid, "GUIDED_BY_PRINCIPLE", "incoming"
            )
            if habits_result.is_ok and habits_result.value:
                for habit_uid in habits_result.value:
                    evidence.append(f"Habit '{habit_uid}' practices this principle")
                    total_score += 0.75  # MOSTLY_ALIGNED score
                    count += 1

        # Calculate average score
        if count > 0:
            avg_score = total_score / count
        else:
            avg_score = 0.25  # Unknown if no connected entities

        # Convert score to alignment level
        system_level = self._score_to_alignment_level(avg_score)

        return system_level, avg_score, evidence

    def _alignment_level_to_score(self, level: AlignmentLevel) -> float:
        """Convert AlignmentLevel to numeric score (0.0-1.0)."""
        return {
            AlignmentLevel.ALIGNED: 1.0,
            AlignmentLevel.MOSTLY_ALIGNED: 0.75,
            AlignmentLevel.PARTIAL: 0.5,
            AlignmentLevel.MISALIGNED: 0.25,
            AlignmentLevel.UNKNOWN: 0.0,
        }.get(level, 0.5)

    def _score_to_alignment_level(self, score: float) -> AlignmentLevel:
        """Convert numeric score to AlignmentLevel."""
        if score >= 0.85:
            return AlignmentLevel.ALIGNED
        elif score >= 0.6:
            return AlignmentLevel.MOSTLY_ALIGNED
        elif score >= 0.4:
            return AlignmentLevel.PARTIAL
        elif score >= 0.15:
            return AlignmentLevel.MISALIGNED
        else:
            return AlignmentLevel.UNKNOWN

    def _generate_principle_gap_insights(
        self, direction: str, gap: float, entity_name: str
    ) -> list[str]:
        """Generate principle-specific gap insights."""
        insights: list[str] = []

        if direction == "aligned":
            insights.append(
                f"Your self-perception of alignment with '{entity_name}' "
                "matches your recorded actions. This indicates healthy self-reflection."
            )
        elif direction == "user_higher":
            insights.append(
                f"Your self-assessment is more positive than your recorded actions suggest "
                f"(gap: {gap:.0%}). Consider: Are there activities expressing this principle "
                "that aren't tracked in SKUEL?"
            )
            if gap > 0.3:
                insights.append(
                    "This significant gap may indicate a blind spot in self-perception, "
                    "or opportunities to better live out this principle."
                )
        else:  # system_higher
            insights.append(
                f"Your actions show stronger alignment than you perceive (gap: {gap:.0%}). "
                "You may be undervaluing your consistency with this principle."
            )
            if gap > 0.3:
                insights.append(
                    "Consider acknowledging your progress - self-recognition strengthens motivation."
                )

        return insights

    def _generate_principle_gap_recommendations(
        self, direction: str, gap: float, entity: Any, evidence: list[str]
    ) -> list[str]:
        """Generate principle-specific gap recommendations."""
        recommendations: list[str] = []

        if direction == "aligned":
            recommendations.append(
                "Continue your current approach - your self-awareness is accurate."
            )
            # Check if principle has expressions (Principle model has this attribute)
            if isinstance(entity, Ku) and entity.expressions:
                recommendations.append(
                    "Consider documenting new expressions of this principle as they arise."
                )
        elif direction == "user_higher":
            recommendations.append(
                "Review your goals and habits to ensure they explicitly connect to this principle."
            )
            if not evidence:
                recommendations.append(
                    "Create at least one goal or habit that directly expresses this principle."
                )
            recommendations.append(
                "Track specific instances where you practice this principle over the next week."
            )
        else:  # system_higher
            recommendations.append(
                "Acknowledge the alignment you've already achieved through your actions."
            )
            if evidence:
                recommendations.append(
                    f"Celebrate your progress: {len(evidence)} activities already express this principle."
                )
            recommendations.append(
                "Consider reflecting on why your self-perception doesn't match your positive actions."
            )

        return recommendations[:4]

    async def _store_alignment_assessment(
        self, principle_uid: str, assessment_data: dict[str, Any]
    ) -> None:
        """Store user's self-assessment in principle's alignment_history."""

        from core.models.ku.ku_dto import KuDTO

        # Get current principle
        principle_result = await self.backend.get(principle_uid)
        if principle_result.is_error:
            self.logger.warning(f"Could not store assessment: {principle_result}")
            return

        principle_data = principle_result.value
        if isinstance(principle_data, dict):
            dto = KuDTO.from_dict(principle_data)
        elif isinstance(principle_data, Ku):
            dto = principle_data.to_dto()
        else:
            self.logger.warning(f"Unknown principle data type: {type(principle_data)}")
            return

        # Create assessment
        user_level = assessment_data.get("user_level")
        user_evidence = assessment_data.get("user_evidence", "")
        user_reflection = assessment_data.get("user_reflection")

        # Add assessment to history
        from core.models.ku.ku_nested_types import AlignmentAssessment as KuAlignmentAssessment

        assessment = KuAlignmentAssessment(
            assessed_date=date.today(),
            alignment_level=user_level,
            evidence=user_evidence,
            reflection=user_reflection,
        )
        dto.alignment_history.append(assessment)

        # Update in backend
        await self.backend.update(principle_uid, dto.to_dict())

    @requires_graph_intelligence("get_principle_adherence_trends")
    async def get_principle_adherence_trends(
        self, principle_uid: str, days: int = 90
    ) -> Result[dict[str, Any]]:
        """
        Analyze principle adherence trends over time using Phase 1-4.

        Provides trend analysis including:
        - Adherence score trajectory
        - Activity frequency over time
        - Consistency metrics
        - Pattern identification

        Args:
            principle_uid: Principle UID,
            days: Number of days to analyze (default: 90)

        Returns:
            Result containing trend analysis dictionary
        """
        # Step 1: Get principle
        principle_result = await self.backend.get(principle_uid)
        if principle_result.is_error:
            return Result.fail(principle_result.expect_error())  # P3: Type-safe error propagation

        principle = principle_result.value

        # Step 2: Calculate date range
        end_date = date.today()
        start_date = end_date - timedelta(days=days)

        # Step 3: Get adherence statistics from graph
        # Get cross-domain context using relationship helper (Priority 2 refactoring)
        if self.relationships is None:
            return Result.fail(
                Errors.system(
                    message="PrinciplesRelationshipOperations not available",
                    operation="calculate_adherence",
                )
            )

        context_result = await self.relationships.get_cross_domain_context(principle_uid)
        if context_result.is_error:
            return Result.fail(context_result.expect_error())

        context_dict = context_result.value

        # Step 4: Extract and analyze metrics
        recent_activities = self._extract_recent_activities_from_dict(context_dict)
        current_state = self._calculate_current_state(principle, recent_activities)

        weeks = days // 7
        trajectory, avg_weekly_activities, most_active, least_active = self._analyze_trajectory(
            recent_activities, weeks
        )

        consistency_analysis = self._analyze_consistency(weeks, current_state["consistency_score"])

        # Step 5: Generate recommendations
        recommendations = self._generate_adherence_recommendations(
            trajectory,
            consistency_analysis["consistency_percentage"],
            consistency_analysis["current_streak"],
            avg_weekly_activities,
            consistency_analysis["weeks_with_activity"],
            weeks,
        )

        return Result.ok(
            {
                "principle": principle,
                "period": {"start_date": start_date, "end_date": end_date, "days": days},
                "current_state": current_state,
                "trends": {
                    "trajectory": trajectory,
                    "average_weekly_activities": avg_weekly_activities,
                    "most_active_week": most_active,
                    "least_active_week": least_active,
                },
                "consistency_analysis": consistency_analysis,
                "recommendations": recommendations,
            }
        )

    @requires_graph_intelligence("get_principle_conflict_analysis")
    async def get_principle_conflict_analysis(self, user_uid: str) -> Result[dict[str, Any]]:
        """
        Analyze conflicts between user's principles using Phase 1-4.

        Identifies situations where principles may be in tension:
        - Competing principles for same activity
        - Resource allocation conflicts
        - Priority conflicts
        - Value tensions

        Args:
            user_uid: User UID

        Returns:
            Result containing conflict analysis dictionary
        """
        # Get user's principles
        principles_result = await self.backend.find_by(user_uid=user_uid)
        if principles_result.is_error:
            return Result.fail(principles_result.expect_error())  # P3: Type-safe error propagation

        principles = principles_result.value

        if len(principles) < 2:
            return Result.ok(
                {
                    "user_uid": user_uid,
                    "total_principles": len(principles),
                    "conflicts_detected": 0,
                    "conflicts": [],
                    "conflict_severity": {"high": 0, "medium": 0, "low": 0},
                    "resolution_recommendations": [
                        "Define at least 2 principles to analyze conflicts"
                    ],
                    "harmony_score": 1.0,
                }
            )

        # Analyze each principle pair for conflicts
        conflicts = []
        high_severity = 0
        medium_severity = 0
        low_severity = 0

        if self.relationships is None:
            return Result.fail(
                Errors.system(
                    message="PrinciplesRelationshipOperations not available",
                    operation="detect_conflicts",
                )
            )

        for i, p1 in enumerate(principles):
            for p2 in principles[i + 1 :]:
                # Get cross-domain contexts using relationship helper (Priority 2 refactoring)
                context1_result = await self.relationships.get_cross_domain_context(p1.uid)
                context2_result = await self.relationships.get_cross_domain_context(p2.uid)

                if context1_result.is_ok and context2_result.is_ok:
                    # Check for overlapping activities (potential conflict)
                    c1_goals = set(g.get("uid") for g in context1_result.value.get("goals", []))
                    c2_goals = set(g.get("uid") for g in context2_result.value.get("goals", []))

                    overlapping_goals = c1_goals & c2_goals

                    if overlapping_goals:
                        # Determine severity and update counters
                        severity, h, m, low = self._determine_conflict_severity(p1, p2)
                        high_severity += h
                        medium_severity += m
                        low_severity += low

                        # Create conflict record
                        conflict = self._create_conflict_record(p1, p2, severity, overlapping_goals)
                        conflicts.append(conflict)

        # Calculate harmony score
        harmony_score = self._calculate_harmony_score(principles, conflicts)

        # Resolution recommendations
        recommendations = self._generate_conflict_recommendations(
            high_severity, medium_severity, harmony_score, conflicts
        )

        return Result.ok(
            {
                "user_uid": user_uid,
                "total_principles": len(principles),
                "conflicts_detected": len(conflicts),
                "conflicts": conflicts,
                "conflict_severity": {
                    "high": high_severity,
                    "medium": medium_severity,
                    "low": low_severity,
                },
                "resolution_recommendations": recommendations,
                "harmony_score": harmony_score,
            }
        )

    # ========================================================================
    # HELPER METHODS - ALIGNMENT ASSESSMENT
    # ========================================================================

    def _extract_activities_from_dict(
        self, context_dict: dict[str, Any]
    ) -> tuple[list, list, list, list, dict[str, int]]:
        """Extract and count activities by domain from cross-domain context dict.

        Uses PatternAnalyzer.extract_dict_field_counts for consistent counting.
        Returns (tasks, choices, habits, goals, counts_dict)
        """
        # Note: Tasks don't exist in principle cross-domain context (principles → goals/choices/habits)
        recent_tasks: list[Any] = []  # Principles don't directly relate to tasks
        recent_choices = context_dict.get("choices", [])
        recent_habits = context_dict.get("habits", [])
        guided_goals = context_dict.get("goals", [])

        # Use PatternAnalyzer for consistent field counting
        counts = PatternAnalyzer.extract_dict_field_counts(
            context_dict, ["choices", "habits", "goals"]
        )
        counts["tasks"] = 0  # Principles don't relate to tasks
        counts["total"] = counts["choices"] + counts["habits"]

        return recent_tasks, recent_choices, recent_habits, guided_goals, counts

    def _determine_trend(self, total_activities: int) -> str:
        """Determine trend based on total activities.

        Uses determine_trend_from_rate for standardized trend classification.
        """
        return determine_trend_from_rate(
            rate=float(total_activities),
            thresholds=[(15.0, "improving"), (5.0, "stable")],
            default="declining",
        )

    def _generate_principle_alignment_recommendations(
        self,
        alignment_score: float,
        goal_count: int,
        habit_count: int,
        total_activities: int,
        needs_attention: bool,
        strong_alignment: bool,
    ) -> list[str]:
        """Generate recommendations for principle alignment.

        Uses RecommendationEngine for structured threshold-based recommendations.
        """
        return (
            RecommendationEngine()
            .with_metrics({"total_activities": total_activities})
            .add_conditional(
                needs_attention,
                f"Alignment score is low ({alignment_score:.0%}) - "
                "consider creating goals or habits that embody this principle",
            )
            .add_conditional(
                goal_count == 0,
                "Create at least one goal guided by this principle",
            )
            .add_conditional(
                habit_count == 0,
                "Establish a daily or weekly habit that embodies this principle",
            )
            .add_threshold_check(
                "total_activities",
                threshold=5,
                message="Increase activities aligned with this principle - consistency builds adherence",
                comparison="lt",
            )
            .add_conditional(
                strong_alignment,
                "Excellent alignment! You're living this principle consistently",
            )
            .build()
        )

    # ========================================================================
    # HELPER METHODS - ADHERENCE TRENDS
    # ========================================================================

    def _extract_recent_activities_from_dict(self, context_dict: dict[str, Any]) -> int:
        """Extract count of recent activities from cross-domain context dict.

        Uses PatternAnalyzer.extract_dict_field_counts for consistent counting.
        Note: Tasks don't relate directly to principles.
        """
        counts = PatternAnalyzer.extract_dict_field_counts(context_dict, ["choices", "habits"])
        return counts["choices"] + counts["habits"]

    def _calculate_current_state(self, principle: Ku, recent_activities: int) -> dict[str, float]:
        """Calculate current state metrics."""
        # NOTE: Principle model does not have adherence_score field
        # Using default 0.5 - consider adding adherence tracking in future
        adherence_score = 0.5
        consistency_score = min(1.0, recent_activities / 30.0)  # 30 activities = full consistency

        return {
            "adherence_score": adherence_score,
            "recent_activity_count": recent_activities,
            "consistency_score": consistency_score,
        }

    def _analyze_trajectory(
        self, recent_activities: int, weeks: int
    ) -> tuple[str, float, dict[str, Any], dict[str, Any]]:
        """Analyze trend trajectory and weekly statistics.

        Uses analyze_activity_trajectory for standardized trend classification.
        """
        # Use shared trend analyzer for consistent classification
        trajectory, avg_weekly_activities = analyze_activity_trajectory(
            activity_count=recent_activities,
            period_count=weeks,
            improving_threshold=3.0,
            declining_threshold=1.0,
        )

        # Estimate most/least active periods (simplified)
        most_active = {"week": 1, "activities": int(avg_weekly_activities * 1.5)}
        least_active = {"week": weeks, "activities": max(0, int(avg_weekly_activities * 0.5))}

        return trajectory, avg_weekly_activities, most_active, least_active

    def _analyze_consistency(self, weeks: int, consistency_score: float) -> dict[str, Any]:
        """Analyze consistency metrics.

        Uses MetricsCalculator for consistent calculations.
        """
        weeks_with_activity = int(weeks * consistency_score)
        consistency_percentage = (
            MetricsCalculator.calculate_ratio(weeks_with_activity, weeks, default=0.0) * 100
        )
        longest_streak = min(weeks_with_activity, weeks // 2)  # Simplified estimate
        current_streak = min(4, weeks_with_activity) if consistency_score > 0.5 else 0

        return {
            "weeks_with_activity": weeks_with_activity,
            "consistency_percentage": consistency_percentage,
            "longest_streak": longest_streak,
            "current_streak": current_streak,
        }

    def _generate_adherence_recommendations(
        self,
        trajectory: str,
        consistency_percentage: float,
        current_streak: int,
        avg_weekly_activities: float,
        weeks_with_activity: int,
        weeks: int,
    ) -> list[str]:
        """Generate recommendations based on adherence metrics.

        Uses RecommendationEngine for structured threshold-based recommendations.
        """
        return (
            RecommendationEngine()
            .with_metrics(
                {
                    "consistency_percentage": consistency_percentage,
                    "avg_weekly_activities": avg_weekly_activities,
                }
            )
            .add_conditional(
                trajectory == "declining",
                "Adherence is declining - recommit to activities aligned with this principle",
            )
            .add_threshold_check(
                "consistency_percentage",
                threshold=50,
                message=f"Only {weeks_with_activity} active weeks out of {weeks} - build more consistent habits",
                comparison="lt",
            )
            .add_conditional(
                current_streak == 0,
                "No recent activity streak - start fresh today!",
            )
            .add_conditional(
                current_streak >= 4,
                f"Great {current_streak}-week streak! Keep it going",
            )
            .add_threshold_check(
                "avg_weekly_activities",
                threshold=2,
                message="Aim for at least 2-3 activities per week aligned with this principle",
                comparison="lt",
            )
            .build()
        )

    # ========================================================================
    # HELPER METHODS - CONFLICT ANALYSIS
    # ========================================================================

    def _determine_conflict_severity(self, p1: Ku, p2: Ku) -> tuple[str, int, int, int]:
        """
        Determine conflict severity based on principle strengths.

        Returns (severity, high_count, medium_count, low_count)
        """
        p1_strength = str(p1.strength.value) if p1.strength else "unknown"
        p2_strength = str(p2.strength.value) if p2.strength else "unknown"

        if p1_strength == "core" and p2_strength == "core":
            return "high", 1, 0, 0
        elif "core" in [p1_strength, p2_strength]:
            return "medium", 0, 1, 0
        else:
            return "low", 0, 0, 1

    def _create_conflict_record(
        self, p1: Ku, p2: Ku, severity: str, overlapping_goals: set
    ) -> dict[str, Any]:
        """Create a conflict record dict."""
        return {
            "principle1": {"uid": p1.uid, "label": p1.title},
            "principle2": {"uid": p2.uid, "label": p2.title},
            "severity": severity,
            "conflict_area": "goal_alignment",
            "overlapping_goals_count": len(overlapping_goals),
            "description": f"{p1.title} and {p2.title} both guide the same goals",
        }

    def _calculate_harmony_score(self, principles: list[Ku], conflicts: list[dict]) -> float:
        """Calculate overall principle harmony score.

        Uses MetricsCalculator.calculate_harmony_score for consistent calculation.
        """
        return MetricsCalculator.calculate_harmony_score(
            total_items=len(principles),
            conflict_count=len(conflicts),
        )

    def _generate_conflict_recommendations(
        self, high_severity: int, medium_severity: int, harmony_score: float, conflicts: list[dict]
    ) -> list[str]:
        """Generate resolution recommendations based on conflicts.

        Uses RecommendationEngine for structured threshold-based recommendations.
        """
        return (
            RecommendationEngine()
            .with_metrics({"harmony_score": harmony_score})
            .add_conditional(
                high_severity > 0,
                f"Resolve {high_severity} high-severity conflicts involving core principles",
            )
            .add_conditional(
                medium_severity > 0,
                f"Review {medium_severity} medium-severity conflicts for priority clarification",
            )
            .add_threshold_check(
                "harmony_score",
                threshold=0.7,
                message="Low harmony score - clarify principle priorities and values",
                comparison="lt",
            )
            .add_conditional(
                len(conflicts) == 0,
                "No conflicts detected - your principles are well-aligned!",
            )
            .build()
        )

    # ========================================================================
    # RELATIONSHIP HELPER INTEGRATION (November 2025)
    # ========================================================================
    # Two-phase optimization methods using fetch() for quick metrics

    async def get_quick_principle_impact(self, principle_uid: str) -> Result[dict[str, Any]]:
        """
        Get quick principle impact metrics using parallel relationship fetch.

        OPTIMIZATION: Uses fetch() for ~60% faster simple metrics.
        Use for:
        - Dashboard quick views
        - Principle adoption screening
        - Batch principle analysis

        For full context with path metadata, use get_principle_with_context().

        Args:
            principle_uid: Principle UID

        Returns:
            Result containing:
            {
                "principle_uid": str,
                "relationship_counts": {
                    "grounded_knowledge": int,
                    "guided_goals": int,
                    "inspired_habits": int,
                    "related_principles": int
                },
                "impact_score": float (0-10),
                "adoption_level": str ("exploring" | "developing" | "embodied"),
                "has_foundation": bool,
                "guides_actions": bool,
                "total_action_count": int
            }

        Example:
            ```python
            # Quick check first (fast - ~160ms)
            impact_result = await service.get_quick_principle_impact(principle_uid)
            impact = impact_result.value

            if impact["impact_score"] > 5.0:
                # Only call expensive method for high-impact principles
                full_result = await service.get_principle_with_context(principle_uid)
            else:
                # Use quick metrics for low-impact principles
                print(f"Low-impact principle: {impact['adoption_level']}")
            ```
        """
        from core.models.principle.principle_relationships import PrincipleRelationships

        # ✅ Use fetch() for fast parallel UID fetching
        rels = await PrincipleRelationships.fetch(principle_uid, self.relationships)

        # Quick impact calculation based on relationship counts
        knowledge_count = len(rels.grounded_knowledge_uids)
        goal_count = len(rels.guided_goal_uids)
        habit_count = len(rels.inspired_habit_uids)
        principle_count = len(rels.related_principle_uids)

        # Simple impact score (0-10)
        impact_score = min(10.0, (goal_count * 2.5) + (habit_count * 2.0) + (knowledge_count * 1.0))

        # Adoption level based on action guidance
        total_actions = goal_count + habit_count
        adoption_level = "exploring"
        if total_actions > 5:
            adoption_level = "embodied"
        elif total_actions > 2:
            adoption_level = "developing"

        return Result.ok(
            {
                "principle_uid": principle_uid,
                "relationship_counts": {
                    "grounded_knowledge": knowledge_count,
                    "guided_goals": goal_count,
                    "inspired_habits": habit_count,
                    "related_principles": principle_count,
                },
                "impact_score": impact_score,
                "adoption_level": adoption_level,
                "has_foundation": rels.has_any_knowledge(),
                "guides_actions": rels.is_integrated(),
                "total_action_count": rels.total_influence_count(),
            }
        )

    async def batch_analyze_principle_adoption(
        self, principle_uids: list[str]
    ) -> Result[dict[str, dict[str, Any]]]:
        """
        Analyze principle adoption for multiple principles in parallel.

        OPTIMIZATION: Uses fetch() for ~50% faster batch processing.
        Perfect for:
        - User principle dashboard
        - Principle adherence trends
        - Filtering principles by adoption before detailed analysis

        Args:
            principle_uids: List of principle UIDs

        Returns:
            Result containing mapping of principle_uid -> quick_impact

        Example:
            ```python
            # Analyze all user principles in ~2s instead of ~4s
            all_principles = ["principle:1", "principle:2", ..., "principle:50"]
            batch_result = await service.batch_analyze_principle_adoption(all_principles)

            # Filter embodied principles for deeper analysis
            embodied = [
                uid
                for uid, metrics in batch_result.value.items()
                if metrics["adoption_level"] == "embodied"
            ]

            # Only run expensive analysis on embodied principles
            for uid in embodied:
                await service.get_principle_with_context(uid)
            ```
        """
        import asyncio

        from core.models.principle.principle_relationships import PrincipleRelationships

        # ✅ Fetch all relationships in parallel
        all_rels = await asyncio.gather(
            *[PrincipleRelationships.fetch(uid, self.relationships) for uid in principle_uids]
        )

        # Calculate quick impact for each
        results = {}
        for principle_uid, rels in zip(principle_uids, all_rels, strict=False):
            goal_count = len(rels.guided_goal_uids)
            habit_count = len(rels.inspired_habit_uids)
            total_actions = goal_count + habit_count

            impact_score = min(10.0, (goal_count * 2.5) + (habit_count * 2.0))

            adoption_level = "exploring"
            if total_actions > 5:
                adoption_level = "embodied"
            elif total_actions > 2:
                adoption_level = "developing"

            results[principle_uid] = {
                "impact_score": impact_score,
                "adoption_level": adoption_level,
                "total_actions": total_actions,
                "has_foundation": rels.has_any_knowledge(),
                "guides_actions": rels.is_integrated(),
            }

        return Result.ok(results)

    # ========================================================================
    # EVENT HANDLERS
    # ========================================================================

    async def handle_principle_strength_changed(self, event: PrincipleStrengthChanged) -> None:
        """Analyze cascade impact when principle strength changes.

        Event-driven handler that evaluates how a principle strength change
        affects connected goals and habits. Enables cross-domain intelligence
        by analyzing alignment cascade effects.

        The handler:
        1. Gets principle details and connected entities
        2. Queries connected goals (via ALIGNED_WITH_PRINCIPLE)
        3. Queries connected habits (via GUIDED_BY_PRINCIPLE)
        4. Calculates cascade impact based on new strength
        5. Logs structured insights for alignment tracking

        Args:
            event: PrincipleStrengthChanged event with strength context

        Note:
            This is a fire-and-forget handler - it logs but doesn't
            fail the original operation. Errors are caught and logged.
        """
        try:
            # 1. Get principle details
            principle_result = await self.backend.get(event.principle_uid)
            if principle_result.is_error:
                self.logger.warning(
                    f"Failed to get principle for cascade analysis: {event.principle_uid}"
                )
                return

            principle = principle_result.value
            if not principle:
                self.logger.warning(
                    f"Principle not found for cascade analysis: {event.principle_uid}"
                )
                return

            # 2. Query connected goals
            goal_uids: list[str] = []
            if self.relationships:
                goal_result = await self.relationships.get_related_uids(
                    event.principle_uid,
                    RelationshipName.ALIGNED_WITH_PRINCIPLE.value,
                    "incoming",
                )
                if goal_result.is_ok:
                    goal_uids = goal_result.value

            # 3. Query connected habits
            habit_uids: list[str] = []
            if self.relationships:
                habit_result = await self.relationships.get_related_uids(
                    event.principle_uid, "GUIDED_BY_PRINCIPLE", "incoming"
                )
                if habit_result.is_ok:
                    habit_uids = habit_result.value

            # 4. Calculate cascade impact
            total_affected = len(goal_uids) + len(habit_uids)
            strength_change = self._categorize_strength_change(
                event.old_strength, event.new_strength
            )

            # 5. Log structured insights
            self.logger.info(
                f"Principle strength changed: {principle.title} ({event.old_strength} -> {event.new_strength})",
                extra={
                    "principle_uid": event.principle_uid,
                    "user_uid": event.user_uid,
                    "old_strength": event.old_strength,
                    "new_strength": event.new_strength,
                    "strength_change_type": strength_change,
                    "goals_affected": len(goal_uids),
                    "habits_affected": len(habit_uids),
                    "total_affected": total_affected,
                    "event_type": "principle.strength.cascade_analyzed",
                },
            )

            # Log cascade impact for significant changes
            if total_affected > 0 and strength_change in ("elevation", "demotion"):
                impact_severity = (
                    "high" if total_affected > 5 else "medium" if total_affected > 2 else "low"
                )

                self.logger.info(
                    f"Cascade impact: {total_affected} entities affected by {strength_change}",
                    extra={
                        "principle_uid": event.principle_uid,
                        "strength_change_type": strength_change,
                        "impact_severity": impact_severity,
                        "goal_uids": goal_uids[:5],  # Log first 5
                        "habit_uids": habit_uids[:5],
                        "event_type": "principle.cascade_impact",
                    },
                )

                # Log specific insight for core principle changes
                if event.new_strength == "core":
                    self.logger.info(
                        f"Principle elevated to CORE - {total_affected} entities now aligned with core value",
                        extra={
                            "principle_uid": event.principle_uid,
                            "total_affected": total_affected,
                            "event_type": "principle.core_elevation",
                        },
                    )

        except Exception as e:
            self.logger.error(
                f"Error analyzing principle strength change: {e}",
                extra={"principle_uid": event.principle_uid, "error": str(e)},
            )

    def _categorize_strength_change(self, old_strength: str, new_strength: str) -> str:
        """Categorize the type of strength change.

        Args:
            old_strength: Previous strength value
            new_strength: New strength value

        Returns:
            Change type: "elevation", "demotion", or "lateral"
        """
        strength_order = ["aspirational", "developing", "strong", "core"]

        try:
            old_idx = strength_order.index(old_strength.lower())
            new_idx = strength_order.index(new_strength.lower())

            if new_idx > old_idx:
                return "elevation"
            elif new_idx < old_idx:
                return "demotion"
            else:
                return "lateral"
        except ValueError:
            # Unknown strength values - treat as lateral
            return "lateral"

    async def handle_reflection_recorded(self, event: PrincipleReflectionRecorded) -> None:
        """
        Generate cross-domain insights when a principle reflection is recorded.

        Event-driven handler that analyzes reflection patterns and generates
        insights about principle alignment trends. Special attention is paid
        to reflections triggered by other domains (goals, habits, events, choices).

        The handler:
        1. Gets principle details
        2. Analyzes trigger context (cross-domain if triggered by goal/habit/etc.)
        3. Tracks alignment trends (improving/declining)
        4. Logs structured reflection impact insights

        Args:
            event: PrincipleReflectionRecorded event with reflection context

        Note:
            Fire-and-forget handler - logs errors but doesn't fail the operation.
        """
        try:
            # 1. Get principle details
            principle_result = await self.backend.get(event.principle_uid)
            if principle_result.is_error:
                self.logger.warning(
                    f"Failed to get principle for reflection analysis: {event.principle_uid}"
                )
                return

            principle = principle_result.value
            if not principle:
                self.logger.warning(
                    f"Principle not found for reflection analysis: {event.principle_uid}"
                )
                return

            # 2. Analyze trigger context - cross-domain insight generation
            is_cross_domain = event.trigger_type in ("goal", "habit", "event", "choice")
            trigger_context = self._analyze_trigger_context(event.trigger_type, event.trigger_uid)

            # 3. Determine alignment quality category
            alignment_category = self._categorize_alignment(event.alignment_level)

            # 4. Calculate reflection quality assessment
            quality_assessment = self._assess_reflection_quality(
                event.reflection_quality_score, event.evidence
            )

            # 5. Log base reflection insight
            self.logger.info(
                f"Principle reflection recorded: {principle.title} ({event.alignment_level})",
                extra={
                    "event_type": "principle.reflection.analyzed",
                    "principle_uid": event.principle_uid,
                    "user_uid": event.user_uid,
                    "reflection_uid": event.reflection_uid,
                    "alignment_level": event.alignment_level,
                    "alignment_category": alignment_category,
                    "reflection_quality_score": event.reflection_quality_score,
                    "quality_assessment": quality_assessment,
                    "is_cross_domain": is_cross_domain,
                    "trigger_type": event.trigger_type,
                    "trigger_uid": event.trigger_uid,
                    "insight": {
                        "type": "principle_reflection",
                        "title": f"Reflection on {principle.title}: {alignment_category}",
                        "description": (
                            f"Recorded reflection with {quality_assessment} quality. "
                            f"Alignment level: {event.alignment_level}."
                        ),
                        "confidence": event.reflection_quality_score,
                        "impact": "medium" if alignment_category == "aligned" else "low",
                    },
                },
            )

            # 6. Generate cross-domain insight if triggered by another domain
            if is_cross_domain:
                self.logger.info(
                    f"Cross-domain principle activation: {event.trigger_type} -> {principle.title}",
                    extra={
                        "event_type": "principle.cross_domain.insight",
                        "principle_uid": event.principle_uid,
                        "user_uid": event.user_uid,
                        "trigger_type": event.trigger_type,
                        "trigger_uid": event.trigger_uid,
                        "trigger_context": trigger_context,
                        "alignment_level": event.alignment_level,
                        "insight": {
                            "type": "cross_domain_activation",
                            "title": f"Principle activated by {event.trigger_type}",
                            "description": (
                                f"Working on a {event.trigger_type} triggered reflection "
                                f"on '{principle.title}'. This shows integrated living."
                            ),
                            "confidence": 0.8,
                            "impact": "medium",
                            "recommended_actions": [
                                {
                                    "action": f"Continue linking {event.trigger_type}s to principles",
                                    "rationale": "Cross-domain connections strengthen alignment",
                                }
                            ],
                        },
                    },
                )

            # 7. Check for misalignment that needs attention
            if alignment_category == "misaligned":
                self.logger.warning(
                    f"Principle misalignment detected: {principle.title}",
                    extra={
                        "event_type": "principle.misalignment.detected",
                        "principle_uid": event.principle_uid,
                        "user_uid": event.user_uid,
                        "alignment_level": event.alignment_level,
                        "insight": {
                            "type": "misalignment_warning",
                            "title": f"Misalignment with {principle.title}",
                            "description": (
                                f"Your reflection indicates misalignment with '{principle.title}'. "
                                "Consider what changes could improve alignment."
                            ),
                            "confidence": 0.85,
                            "impact": "high",
                            "recommended_actions": [
                                {
                                    "action": "Review recent choices and goals",
                                    "rationale": "Identify where alignment broke down",
                                },
                                {
                                    "action": "Create a habit that embodies this principle",
                                    "rationale": "Regular practice rebuilds alignment",
                                },
                            ],
                        },
                    },
                )

        except Exception as e:
            self.logger.error(
                f"Error analyzing principle reflection: {e}",
                extra={
                    "event_type": "principle.reflection.error",
                    "principle_uid": event.principle_uid,
                    "user_uid": event.user_uid,
                    "error": str(e),
                },
                exc_info=True,
            )

    def _analyze_trigger_context(
        self, trigger_type: str | None, trigger_uid: str | None
    ) -> dict[str, Any]:
        """Analyze the context of what triggered this reflection."""
        if not trigger_type or not trigger_uid:
            return {"type": "manual", "description": "Self-initiated reflection"}

        descriptions = {
            "goal": "Reflection triggered while working on a goal",
            "habit": "Reflection triggered during habit practice",
            "event": "Reflection triggered by a calendar event",
            "choice": "Reflection triggered while making a decision",
        }

        return {
            "type": trigger_type,
            "trigger_uid": trigger_uid,
            "description": descriptions.get(trigger_type, f"Triggered by {trigger_type}"),
            "cross_domain": True,
        }

    def _categorize_alignment(self, alignment_level: str) -> str:
        """Categorize alignment level into broad categories."""
        level_lower = alignment_level.lower()
        if level_lower in ("strongly_aligned", "aligned", "exemplary"):
            return "aligned"
        elif level_lower in ("neutral", "somewhat_aligned", "mixed"):
            return "neutral"
        else:
            return "misaligned"

    def _assess_reflection_quality(self, quality_score: float, evidence: str) -> str:
        """Assess overall reflection quality."""
        evidence_length = len(evidence) if evidence else 0

        if quality_score >= 0.8 and evidence_length > 100:
            return "excellent"
        elif quality_score >= 0.6 or evidence_length > 50:
            return "good"
        elif quality_score >= 0.4 or evidence_length > 20:
            return "adequate"
        else:
            return "brief"

    async def handle_conflict_revealed(self, event: PrincipleConflictRevealed) -> None:
        """
        Handle principle conflict detection and generate resolution guidance.

        Event-driven handler that responds to revealed conflicts between principles.
        Creates/updates CONFLICTS_WITH relationships in the graph and generates
        guidance for resolving the tension.

        The handler:
        1. Gets both principle details
        2. Creates/updates CONFLICTS_WITH relationship in graph
        3. Queries historical conflicts between these principles
        4. Generates resolution guidance
        5. Logs high-priority conflict insight

        Args:
            event: PrincipleConflictRevealed event with conflict context

        Note:
            Fire-and-forget handler - logs errors but doesn't fail the operation.
        """
        try:
            # 1. Get both principle details
            p1_result = await self.backend.get(event.principle_uid)
            p2_result = await self.backend.get(event.conflicting_principle_uid)

            if p1_result.is_error:
                self.logger.warning(
                    f"Failed to get principle for conflict analysis: {event.principle_uid}"
                )
                return
            if p2_result.is_error:
                self.logger.warning(
                    f"Failed to get conflicting principle: {event.conflicting_principle_uid}"
                )
                return

            principle1 = p1_result.value
            principle2 = p2_result.value
            if not principle1 or not principle2:
                self.logger.warning(
                    f"One or both principles not found for conflict analysis: "
                    f"{event.principle_uid}, {event.conflicting_principle_uid}"
                )
                return

            # 2. Determine conflict severity based on principle strengths
            severity = self._determine_conflict_severity_for_event(
                principle1.strength.value if principle1.strength else "unknown",
                principle2.strength.value if principle2.strength else "unknown",
            )

            # 3. Generate resolution guidance
            resolution_guidance = self._generate_resolution_guidance(
                principle1, principle2, severity, event.conflict_context
            )

            # 4. Log high-priority conflict insight
            self.logger.warning(
                f"Principle conflict revealed: {principle1.title} vs {principle2.title}",
                extra={
                    "event_type": "principle.conflict.revealed",
                    "principle_uid": event.principle_uid,
                    "conflicting_principle_uid": event.conflicting_principle_uid,
                    "user_uid": event.user_uid,
                    "reflection_uid": event.reflection_uid,
                    "severity": severity,
                    "conflict_context": event.conflict_context,
                    "insight": {
                        "type": "principle_conflict",
                        "title": f"Conflict: {principle1.title} vs {principle2.title}",
                        "description": (
                            f"A conflict has been revealed between '{principle1.title}' and "
                            f"'{principle2.title}'. {event.conflict_context or 'Consider how to resolve this tension.'}"
                        ),
                        "confidence": 0.9,
                        "impact": "critical" if severity == "high" else "high",
                        "recommended_actions": resolution_guidance,
                    },
                },
            )

            # 5. If both are core principles, this is critical
            if severity == "high":
                self.logger.error(
                    "Critical: Core principle conflict detected",
                    extra={
                        "event_type": "principle.conflict.critical",
                        "principle1_uid": event.principle_uid,
                        "principle2_uid": event.conflicting_principle_uid,
                        "user_uid": event.user_uid,
                        "recommendation": (
                            "Core principles in conflict require immediate attention. "
                            "Consider re-evaluating which principle takes priority in this context."
                        ),
                    },
                )

            # 6. Log specific guidance
            self.logger.info(
                f"Resolution guidance generated for {principle1.title} vs {principle2.title}",
                extra={
                    "event_type": "principle.conflict.guidance",
                    "principle_uid": event.principle_uid,
                    "conflicting_principle_uid": event.conflicting_principle_uid,
                    "user_uid": event.user_uid,
                    "guidance_count": len(resolution_guidance),
                    "guidance": resolution_guidance,
                },
            )

            # 7. Persist conflict insight to InsightStore (Phase 1: Quick Wins)
            if self.insight_store:
                impact = InsightImpact.CRITICAL if severity == "high" else InsightImpact.HIGH
                insight = PersistedInsight(
                    uid=PersistedInsight.generate_uid(
                        InsightType.PRINCIPLE_CONFLICT, event.principle_uid
                    ),
                    user_uid=event.user_uid,
                    insight_type=InsightType.PRINCIPLE_CONFLICT,
                    domain="principles",
                    title=f"Conflict: {principle1.title} vs {principle2.title}",
                    description=(
                        f"A conflict has been revealed between '{principle1.title}' and "
                        f"'{principle2.title}'. {event.conflict_context or 'Consider how to resolve this tension.'}"
                    ),
                    confidence=0.9,
                    impact=impact,
                    entity_uid=event.principle_uid,
                    related_entities={"principles": [event.conflicting_principle_uid]},
                    recommended_actions=resolution_guidance,
                    supporting_data={
                        "severity": severity,
                        "conflict_context": event.conflict_context,
                        "reflection_uid": event.reflection_uid,
                        "principle1_strength": principle1.strength.value
                        if principle1.strength
                        else "unknown",
                        "principle2_strength": principle2.strength.value
                        if principle2.strength
                        else "unknown",
                    },
                )
                create_result = await self.insight_store.create_insight(insight)
                if create_result.is_error:
                    self.logger.warning(
                        f"Failed to persist conflict insight: {create_result.error}"
                    )

        except Exception as e:
            self.logger.error(
                f"Error handling principle conflict: {e}",
                extra={
                    "event_type": "principle.conflict.error",
                    "principle_uid": event.principle_uid,
                    "conflicting_principle_uid": event.conflicting_principle_uid,
                    "user_uid": event.user_uid,
                    "error": str(e),
                },
                exc_info=True,
            )

    def _determine_conflict_severity_for_event(self, strength1: str, strength2: str) -> str:
        """Determine conflict severity based on principle strengths."""
        if strength1 == "core" and strength2 == "core":
            return "high"
        elif "core" in (strength1, strength2) or (strength1 == "strong" and strength2 == "strong"):
            return "medium"
        else:
            return "low"

    def _generate_resolution_guidance(
        self,
        principle1: Ku,
        principle2: Ku,
        severity: str,
        conflict_context: str | None,
    ) -> list[dict[str, str]]:
        """Generate specific resolution guidance for the conflict."""
        guidance: list[dict[str, str]] = []

        # Context-specific guidance
        if conflict_context:
            guidance.append(
                {
                    "action": "Reflect on the specific situation",
                    "rationale": f"Context: {conflict_context[:100]}...",
                }
            )

        # Severity-based guidance
        if severity == "high":
            guidance.append(
                {
                    "action": "Prioritize between core values",
                    "rationale": (
                        "Both principles are core values. Decide which takes "
                        "precedence in this specific context."
                    ),
                }
            )
            guidance.append(
                {
                    "action": "Consider if reframing eliminates the conflict",
                    "rationale": "Sometimes perceived conflicts dissolve with new perspective.",
                }
            )
        elif severity == "medium":
            guidance.append(
                {
                    "action": "Look for a compromise position",
                    "rationale": "Medium-severity conflicts often have middle-ground solutions.",
                }
            )
        else:
            guidance.append(
                {
                    "action": "Accept the tension as growth opportunity",
                    "rationale": "Low-severity conflicts can coexist and promote balanced thinking.",
                }
            )

        # General guidance
        guidance.append(
            {
                "action": "Journal about this conflict",
                "rationale": "Writing clarifies thinking and may reveal resolution paths.",
            }
        )
        guidance.append(
            {
                "action": f"Review how '{principle1.title}' and '{principle2.title}' have guided you before",
                "rationale": "Past experience may offer resolution patterns.",
            }
        )

        return guidance

    # =========================================================================
    # PRINCIPLE-CHOICE INTEGRATION (January 2026)
    # =========================================================================

    async def get_choice_guidance_effectiveness(
        self,
        principle_uid: str,
        user_uid: str,
        period_days: int = 90,
    ) -> Result[dict[str, Any]]:
        """
        Analyze how effectively a principle guides user's choices.

        This method evaluates the effectiveness of a specific principle
        in guiding the user's decision-making by examining:
        - How many choices the principle has guided
        - The satisfaction scores of those choices
        - The positive outcome rate

        Args:
            principle_uid: Principle identifier
            user_uid: User identifier
            period_days: Analysis period (default 90 days)

        Returns:
            Result containing:
            - total_choices_guided: int
            - avg_satisfaction_score: float (normalized 0.0-1.0)
            - positive_outcome_rate: float (0.0-1.0)
            - alignment_strength: float (0.0-1.0)
            - recommendation: str
        """
        query = """
        MATCH (p:Principle {uid: $principle_uid})-[:GUIDES_CHOICE]->(c:Choice)
        WHERE c.user_uid = $user_uid
          AND c.created_at >= datetime() - duration({days: $period_days})

        RETURN
            count(c) AS total_choices,
            avg(c.satisfaction_score) AS avg_satisfaction,
            sum(CASE WHEN c.satisfaction_score >= 4 THEN 1 ELSE 0 END) AS positive_outcomes
        """

        result = await self.backend.execute_query(
            query,
            {
                "principle_uid": principle_uid,
                "user_uid": user_uid,
                "period_days": period_days,
            },
        )

        if result.is_error:
            return Result.fail(result.expect_error())

        if not result.value:
            return Result.ok(
                {
                    "total_choices_guided": 0,
                    "avg_satisfaction_score": 0.0,
                    "positive_outcome_rate": 0.0,
                    "alignment_strength": 0.0,
                    "recommendation": "Start linking choices to this principle",
                }
            )

        record = result.value[0]
        total = record.get("total_choices", 0)
        avg_sat = record.get("avg_satisfaction") or 0.0
        positive = record.get("positive_outcomes", 0)

        if total == 0:
            return Result.ok(
                {
                    "total_choices_guided": 0,
                    "avg_satisfaction_score": 0.0,
                    "positive_outcome_rate": 0.0,
                    "alignment_strength": 0.0,
                    "recommendation": "Start linking choices to this principle",
                }
            )

        # Normalize satisfaction to 0-1 (assuming 1-5 scale)
        normalized_satisfaction = avg_sat / 5.0
        positive_rate = positive / total

        # Calculate alignment strength: combined metric
        alignment_strength = normalized_satisfaction * positive_rate

        # Generate recommendation based on effectiveness
        if total == 0:
            recommendation = "Start linking choices to this principle"
        elif positive_rate < 0.5:
            recommendation = "Review how this principle is being applied to choices"
        elif normalized_satisfaction < 0.6:
            recommendation = "Consider if principle interpretation needs refinement"
        elif positive_rate >= 0.7 and normalized_satisfaction >= 0.7:
            recommendation = "Excellent guidance - continue using this principle for decisions"
        else:
            recommendation = "Continue using this principle for decision guidance"

        return Result.ok(
            {
                "total_choices_guided": total,
                "avg_satisfaction_score": round(normalized_satisfaction, 3),
                "positive_outcome_rate": round(positive_rate, 3),
                "alignment_strength": round(alignment_strength, 3),
                "recommendation": recommendation,
            }
        )
