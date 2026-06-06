"""
Alignment Intelligence Mixin — PrinciplesIntelligenceService
=============================================================

Alignment assessment — single-track, dual-track, adherence trends.

Part of principles_intelligence_service.py decomposition (April 2026).
See: /docs/architecture/ENTITY_TYPE_ARCHITECTURE.md
"""

from __future__ import annotations

from dataclasses import asdict
from datetime import date, timedelta
from typing import TYPE_CHECKING, Any

from core.models.enums.principle_enums import AlignmentLevel
from core.models.graph.path_aware_types import PrincipleCrossContext
from core.models.shared.dual_track import DualTrackResult
from core.models.type_hints import UserUID
from core.services.intelligence import (
    MetricsCalculator,
    PatternAnalyzer,
    RecommendationEngine,
    analyze_activity_trajectory,
    calculate_principle_alignment_metrics,
    determine_trend_from_rate,
    principle_recommendations,
)
from core.utils.decorators import requires_graph_intelligence
from core.utils.result_simplified import Errors, Result

if TYPE_CHECKING:
    from core.models.principle.principle import Principle


class _AlignmentIntelligenceMixin:
    """
    Alignment assessment methods for PrinciplesIntelligenceService.

    Declares class-level attributes used by these methods so mypy
    resolves them without runtime cost.
    """

    # Populated by PrinciplesIntelligenceService.__init__
    backend: Any
    relationships: Any
    logger: Any
    # Provided by BaseAnalyticsService via multiple inheritance on the composed service.
    _analyze_entity_with_typed_context: Any

    @requires_graph_intelligence("assess_principle_alignment")
    async def assess_principle_alignment(
        self, principle_uid: str, min_confidence: float = 0.7
    ) -> Result[dict[str, Any]]:
        """
        Assess how well user is living by a principle

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

        Refactoring:
        - Uses BaseAnalyticsService._analyze_entity_with_typed_context over the CANONICAL
          path-aware reader (get_cross_domain_context_typed).
        """
        # Use base class template over the CANONICAL typed (path-aware) reader.
        analysis_result = await self._analyze_entity_with_typed_context(
            uid=principle_uid,
            metrics_fn=calculate_principle_alignment_metrics,
            recommendations_fn=principle_recommendations,
            min_confidence=min_confidence,
        )

        if analysis_result.is_error:
            return analysis_result

        analysis = analysis_result.value
        principle = analysis["entity"]
        context: PrincipleCrossContext = analysis["context"]
        metrics = analysis["metrics"]

        # Extract activities — read UIDs off the path-aware entities.
        recent_tasks: list[dict[str, Any]] = []  # Principles don't directly relate to tasks
        recent_choices = [{"uid": c.uid} for c in context.choices]
        recent_habits = [{"uid": h.uid} for h in context.habits]
        guided_goals = [{"uid": g.uid} for g in context.goals]

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
                "metrics": metrics,  # Include standard metrics
                "graph_context": {
                    "goal_count": metrics["goal_count"],
                    "habit_count": metrics["habit_count"],
                    "choice_count": metrics["choice_count"],
                    "knowledge_count": metrics["knowledge_count"],
                },
                # Rich path-aware additions (additive — existing keys unchanged).
                "cascade_impact": metrics["cascade_impact"],
                "path_aware_context": metrics["path_aware_context"],
            }
        )

    # ========================================================================
    # DUAL-TRACK ASSESSMENT (ADR-030 - January 2026)
    # ========================================================================

    async def assess_alignment_dual_track(
        self,
        principle_uid: str,
        user_uid: UserUID,
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
        """

        return await self._dual_track_assessment(  # type: ignore[attr-defined]
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
        self, principle: Principle, _user_uid: UserUID
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

        # Check connected goals and habits via relationships.
        # self.relationships is the UnifiedRelationshipService — get_related_uids takes
        # (method_key, entity_uid). The keys below are PRINCIPLES_CONFIG method keys, not
        # raw RelationshipName values + direction (that is the backend signature).
        if self.relationships:
            # Get goals guided by this principle (GUIDES_GOAL)
            goals_result = await self.relationships.get_related_uids("guided_goals", principle.uid)
            if goals_result.is_ok and goals_result.value:
                for goal_uid in goals_result.value:
                    evidence.append(f"Goal '{goal_uid}' embodies this principle")
                    total_score += 0.75  # MOSTLY_ALIGNED score
                    count += 1

            # Get habits inspired by this principle (INSPIRES_HABIT)
            habits_result = await self.relationships.get_related_uids(
                "inspired_habits", principle.uid
            )
            if habits_result.is_ok and habits_result.value:
                for habit_uid in habits_result.value:
                    evidence.append(f"Habit '{habit_uid}' practices this principle")
                    total_score += 0.75  # MOSTLY_ALIGNED score
                    count += 1

        # Calculate average score
        avg_score = total_score / count if count > 0 else 0.25  # Unknown if no connected entities

        # Convert score to alignment level
        system_level = self._score_to_alignment_level(avg_score)

        return system_level, avg_score, evidence

    @staticmethod
    def _alignment_level_to_score(level: AlignmentLevel) -> float:
        """Convert AlignmentLevel to numeric score (0.0-1.0).

        Delegates to AlignmentLevel.to_score() — the single source of truth.
        """
        return level.to_score()

    @staticmethod
    def _score_to_alignment_level(score: float) -> AlignmentLevel:
        """Convert numeric score to AlignmentLevel.

        Delegates to AlignmentLevel.from_score() — the single source of truth.
        """
        return AlignmentLevel.from_score(score)

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
        self, direction: str, _gap: float, entity: Any, evidence: list[str]
    ) -> list[str]:
        """Generate principle-specific gap recommendations."""
        from core.models.principle.principle import Principle

        recommendations: list[str] = []

        if direction == "aligned":
            recommendations.append(
                "Continue your current approach - your self-awareness is accurate."
            )
            # Check if principle has expressions (Principle model has this attribute)
            if isinstance(entity, Principle) and entity.expressions:
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
        from core.models.principle.principle import Principle
        from core.models.principle.principle_dto import PrincipleDTO

        # Get current principle
        principle_result = await self.backend.get(principle_uid)
        if principle_result.is_error:
            self.logger.warning(f"Could not store assessment: {principle_result}")
            return

        principle_data = principle_result.value
        if isinstance(principle_data, dict):
            dto = PrincipleDTO.from_dict(principle_data)
        elif isinstance(principle_data, Principle):
            dto = principle_data.to_dto()
        else:
            self.logger.warning(f"Unknown principle data type: {type(principle_data)}")
            return

        # Create assessment
        raw_level = assessment_data.get("user_level")
        if isinstance(raw_level, AlignmentLevel):
            user_level = raw_level
        elif isinstance(raw_level, str) and raw_level in set(AlignmentLevel):
            user_level = AlignmentLevel(raw_level)
        else:
            user_level = AlignmentLevel.UNKNOWN
        user_evidence = assessment_data.get("user_evidence", "")
        user_reflection = assessment_data.get("user_reflection")

        # Add assessment to history
        from core.models.principle.principle_types import (
            AlignmentAssessment as KuAlignmentAssessment,
        )

        assessment = KuAlignmentAssessment(
            assessed_date=date.today(),
            alignment_level=user_level,
            evidence=user_evidence,
            reflection=user_reflection,
        )
        # DTO stores alignment_history as list[dict] (flattened on to_dict via asdict);
        # convert here so the transfer-tier contract stays honest. See Principle._from_dto.
        dto.alignment_history.append(asdict(assessment))

        # raw-write: full-DTO entity replace after appending to alignment_history (not a
        # partial property patch). ADR-066's PrincipleUpdateIntent models partial column
        # patches, not whole-entity persistence or history mutation — dto.to_dict() is the
        # honest shape here.
        await self.backend.update(principle_uid, dto.to_dict())

    # ========================================================================
    # ADHERENCE TRENDS
    # ========================================================================

    @requires_graph_intelligence("get_principle_adherence_trends")
    async def get_principle_adherence_trends(
        self, principle_uid: str, days: int = 90
    ) -> Result[dict[str, Any]]:
        """
        Analyze principle adherence trends over time.

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
            return Result.fail(principle_result)

        principle = principle_result.value

        # Step 2: Calculate date range
        end_date = date.today()
        start_date = end_date - timedelta(days=days)

        # Step 3: Get adherence statistics from graph
        if self.relationships is None:
            return Result.fail(
                Errors.system(
                    message="PrinciplesRelationshipOperations not available",
                    operation="calculate_adherence",
                )
            )

        context_result = await self.relationships.get_cross_domain_context(principle_uid)
        if context_result.is_error:
            return Result.fail(context_result)

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

    # ========================================================================
    # HELPER METHODS
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

    def _extract_recent_activities_from_dict(self, context_dict: dict[str, Any]) -> int:
        """Extract count of recent activities from cross-domain context dict.

        Uses PatternAnalyzer.extract_dict_field_counts for consistent counting.
        Note: Tasks don't relate directly to principles.
        """
        counts = PatternAnalyzer.extract_dict_field_counts(context_dict, ["choices", "habits"])
        return counts["choices"] + counts["habits"]

    def _calculate_current_state(
        self, _principle: Principle, recent_activities: int
    ) -> dict[str, float]:
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
