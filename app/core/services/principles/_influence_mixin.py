"""
Influence Mixin — PrinciplesIntelligenceService
=================================================

How Principles radiate outward — conflict detection, impact metrics,
batch adoption analysis, choice guidance effectiveness.

Part of principles_intelligence_service.py decomposition (April 2026).
See: /docs/architecture/ENTITY_TYPE_ARCHITECTURE.md
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from core.models.type_hints import UserUID
from core.services.intelligence import MetricsCalculator, RecommendationEngine
from core.utils.decorators import requires_graph_intelligence
from core.utils.neo4j_props import coerce_float, coerce_int
from core.utils.result_simplified import Errors, Result

if TYPE_CHECKING:
    from core.models.principle.principle import Principle
    from core.ports.domain_protocols import PrinciplesOperations


class _InfluenceMixin:
    """
    Influence and impact methods for PrinciplesIntelligenceService.

    Declares class-level attributes used by these methods so mypy
    resolves them without runtime cost.
    """

    # Populated by PrinciplesIntelligenceService.__init__
    backend: "PrinciplesOperations"
    relationships: Any
    logger: Any

    # ========================================================================
    # CONFLICT ANALYSIS
    # ========================================================================

    @requires_graph_intelligence("get_principle_conflict_analysis")
    async def get_principle_conflict_analysis(self, user_uid: UserUID) -> Result[dict[str, Any]]:
        """
        Analyze conflicts between user's principles.

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
        from core.models.principle.principle import Principle

        # Get user's principles
        principles_result = await self.backend.find_by(user_uid=user_uid)
        if principles_result.is_error:
            return Result.fail(principles_result)

        principles: list[Principle] = [
            p for p in (principles_result.value or []) if isinstance(p, Principle)
        ]

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
                    message="relationship service (BaseRelationshipOperations) not available",
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
    # CONFLICT HELPERS
    # ========================================================================

    def _determine_conflict_severity(
        self, p1: Principle, p2: Principle
    ) -> tuple[str, int, int, int]:
        """
        Determine conflict severity based on principle strengths.

        Returns (severity, high_count, medium_count, low_count)
        """
        from core.services.principles.principle_event_handler_service import (
            _determine_conflict_severity_from_strengths,
        )

        p1_strength = str(p1.strength.value) if p1.strength else "unknown"
        p2_strength = str(p2.strength.value) if p2.strength else "unknown"
        severity = _determine_conflict_severity_from_strengths(p1_strength, p2_strength)

        if severity == "high":
            return severity, 1, 0, 0
        elif severity == "medium":
            return severity, 0, 1, 0
        else:
            return severity, 0, 0, 1

    def _create_conflict_record(
        self, p1: Principle, p2: Principle, severity: str, overlapping_goals: set
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

    def _calculate_harmony_score(self, principles: list[Principle], conflicts: list[dict]) -> float:
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
    # QUICK IMPACT & BATCH ANALYSIS
    # ========================================================================

    async def get_quick_principle_impact(self, principle_uid: str) -> Result[dict[str, Any]]:
        """
        Get quick principle impact metrics using parallel relationship fetch.

        OPTIMIZATION: Uses fetch() for ~60% faster simple metrics.
        Use for:
        - Dashboard quick views
        - Principle adoption screening
        - Batch principle analysis

        For full context with path metadata, use get_with_context().

        Args:
            principle_uid: Principle UID

        Returns:
            Result containing impact metrics dict
        """
        from core.services.principles.principle_relationships import PrincipleRelationships

        # Use fetch() for fast parallel UID fetching
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

        Args:
            principle_uids: List of principle UIDs

        Returns:
            Result containing mapping of principle_uid -> quick_impact
        """
        import asyncio

        from core.services.principles.principle_relationships import PrincipleRelationships

        # Fetch all relationships in parallel
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

    # =========================================================================
    # PRINCIPLE-CHOICE INTEGRATION (January 2026)
    # =========================================================================

    async def get_choice_guidance_effectiveness(
        self,
        principle_uid: str,
        user_uid: UserUID,
        period_days: int = 90,
    ) -> Result[dict[str, Any]]:
        """
        Analyze how effectively a principle guides user's choices.

        Examines:
        - How many choices the principle has guided
        - The satisfaction scores of those choices
        - The positive outcome rate

        Args:
            principle_uid: Principle identifier
            user_uid: User identifier
            period_days: Analysis period (default 90 days)

        Returns:
            Result containing effectiveness metrics dict
        """
        result = await self.backend.get_choice_influence_stats(principle_uid, user_uid, period_days)

        if result.is_error:
            return Result.fail(result)

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

        record = result.value
        total = coerce_int(record.get("total_choices"))
        avg_sat = coerce_float(record.get("avg_satisfaction"))
        positive = coerce_int(record.get("positive_outcomes"))

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
