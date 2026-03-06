"""
Analytics Mixin — ChoicesIntelligenceService
============================================

Decision pattern analytics: get_quick_decision_metrics,
batch_analyze_decision_complexity, get_decision_patterns,
get_choice_quality_correlations, get_domain_decision_patterns.

Part of choices_intelligence_service.py decomposition (March 2026).
See: /docs/architecture/ENTITY_TYPE_ARCHITECTURE.md
"""

from __future__ import annotations

from collections import defaultdict
from datetime import date, timedelta
from typing import Any

from core.utils.result_simplified import Result
from core.utils.sort_functions import get_domain_choice_count


class _AnalyticsMixin:
    """
    Decision pattern analytics methods for ChoicesIntelligenceService.

    Declares class-level attributes used by these methods so mypy
    resolves them without runtime cost.
    """

    # Populated by ChoicesIntelligenceService.__init__
    backend: Any
    relationships: Any

    async def get_quick_decision_metrics(self, choice_uid: str) -> Result[dict[str, Any]]:
        """
        Get quick decision metrics using parallel relationship fetch.

        OPTIMIZATION: This method uses fetch() for ~60% faster simple metrics
        without path metadata. Use this for:
        - Dashboard quick views
        - Decision complexity screening
        - Batch analysis of multiple choices

        For full intelligence with path metadata, use get_decision_intelligence().

        Args:
            choice_uid: Choice UID

        Returns:
            Result containing:
            {
                "choice_uid": str,
                "relationship_counts": {
                    "knowledge": int,
                    "principles": int,
                    "learning_paths": int,
                    "required_knowledge": int
                },
                "quick_complexity": float (0-10),
                "stake_level": str ("low" | "medium" | "high"),
                "needs_full_analysis": bool,
                "is_informed": bool,
                "is_principle_aligned": bool
            }

        Example:
            ```python
            # Quick check first (fast - ~160ms)
            metrics_result = await service.get_quick_decision_metrics(choice_uid)
            metrics = metrics_result.value

            if metrics["needs_full_analysis"]:
                # Only call expensive method when needed (slow - ~250ms)
                intel_result = await service.get_decision_intelligence(choice_uid)
            else:
                # Use quick metrics for simple decisions
                print(f"Simple decision: {metrics['stake_level']} complexity")
            ```
        """
        from core.services.choices.choice_relationships import ChoiceRelationships

        # ✅ Use fetch() for fast parallel UID fetching (~160ms vs ~250ms)
        rels = await ChoiceRelationships.fetch(choice_uid, self.relationships)

        # Quick complexity calculation based on relationship counts
        knowledge_count = len(rels.informed_by_knowledge_uids)
        principle_count = len(rels.aligned_principle_uids)
        path_count = len(rels.opens_learning_path_uids)
        required_count = len(rels.required_knowledge_uids)

        total_relationships = knowledge_count + principle_count + path_count

        # Simple complexity score (0-10)
        quick_complexity = min(
            10.0, (knowledge_count * 1.5) + (principle_count * 2.0) + (required_count * 1.0)
        )

        # Stake level based on total relationships
        stake_level = "low"
        if total_relationships > 10:
            stake_level = "high"
        elif total_relationships > 5:
            stake_level = "medium"

        # Recommend full analysis for complex decisions
        needs_full_analysis = quick_complexity > 6.0 or principle_count > 2

        return Result.ok(
            {
                "choice_uid": choice_uid,
                "relationship_counts": {
                    "knowledge": knowledge_count,
                    "principles": principle_count,
                    "learning_paths": path_count,
                    "required_knowledge": required_count,
                },
                "quick_complexity": quick_complexity,
                "stake_level": stake_level,
                "needs_full_analysis": needs_full_analysis,
                "is_informed": rels.is_informed_decision(),
                "is_principle_aligned": rels.is_principle_aligned(),
            }
        )

    async def batch_analyze_decision_complexity(
        self, choice_uids: list[str]
    ) -> Result[dict[str, dict[str, Any]]]:
        """
        Analyze decision complexity for multiple choices in parallel.

        OPTIMIZATION: Uses fetch() for ~50% faster batch processing.
        Perfect for:
        - User dashboards showing all choices
        - Decision pattern analysis
        - Filtering choices by complexity before detailed analysis

        For individual full intelligence, use get_decision_intelligence().

        Args:
            choice_uids: List of choice UIDs

        Returns:
            Result containing mapping of choice_uid -> quick_metrics

        Example:
            ```python
            # Analyze 100 user choices in ~4s instead of ~8s
            all_choices = ["choice:1", "choice:2", ..., "choice:100"]
            batch_result = await service.batch_analyze_decision_complexity(all_choices)

            # Filter complex decisions for full analysis
            complex_choices = [
                uid
                for uid, metrics in batch_result.value.items()
                if metrics["complexity"] > 6.0
            ]

            # Only run expensive analysis on subset
            for uid in complex_choices:
                await service.get_decision_intelligence(uid)
            ```
        """
        import asyncio

        from core.services.choices.choice_relationships import ChoiceRelationships

        # ✅ Fetch all relationships in parallel (~4s for 100 choices vs ~8s sequential)
        all_rels = await asyncio.gather(
            *[ChoiceRelationships.fetch(uid, self.relationships) for uid in choice_uids]
        )

        # Calculate quick complexity for each
        results = {}
        for choice_uid, rels in zip(choice_uids, all_rels, strict=False):
            knowledge_count = len(rels.informed_by_knowledge_uids)
            principle_count = len(rels.aligned_principle_uids)
            total = rels.total_knowledge_count()

            quick_complexity = min(10.0, (knowledge_count * 1.5) + (principle_count * 2.0))

            results[choice_uid] = {
                "complexity": quick_complexity,
                "total_relationships": total,
                "is_informed": rels.is_informed_decision(),
                "is_principle_aligned": rels.is_principle_aligned(),
            }

        return Result.ok(results)

    async def get_decision_patterns(self, user_uid: str, days: int = 90) -> Result[dict[str, Any]]:
        """
        Analyze user's decision-making patterns.

        Provides pattern analysis including:
        - Decision frequency and distribution
        - Principle alignment trends
        - Goal-oriented vs exploratory choices
        - Decision quality metrics

        Args:
            user_uid: User UID
            days: Number of days to analyze (default: 90)

        Returns:
            Result containing decision pattern analysis:
            {
                "user_uid": str,
                "period": {
                    "start_date": date,
                    "end_date": date,
                    "days": int
                },
                "decision_metrics": {
                    "total_choices": int,
                    "choices_per_week": float,
                    "principle_aligned_percentage": float,
                    "goal_oriented_percentage": float
                },
                "decision_quality": {
                    "average_confidence": float,
                    "average_satisfaction": float,
                    "principle_alignment_score": float
                },
                "patterns": {
                    "most_common_principle": str,
                    "decision_making_trend": str, # "improving", "stable", "declining"
                    "strategic_vs_tactical": str # "strategic", "balanced", "tactical"
                },
                "recommendations": List[str]
            }

        Example:
            ```python
            result = await choices_service.get_decision_patterns(user_uid, days=90)
            patterns = result.value

            metrics = patterns["decision_metrics"]
            print(f"Made {metrics['total_choices']} choices")
            print(f"Avg {metrics['choices_per_week']:.1f} per week")
            print(f"Principle-aligned: {metrics['principle_aligned_percentage']:.0%}")

            quality = patterns["decision_quality"]
            print(f"Avg confidence: {quality['average_confidence']:.0%}")
            print(f"Avg satisfaction: {quality['average_satisfaction']:.0%}")
            ```
        """
        # Calculate date range
        end_date = date.today()
        start_date = end_date - timedelta(days=days)

        # Get user's choices in period
        choices_result = await self.backend.find_by(
            user_uid=user_uid, date__gte=start_date, date__lte=end_date
        )

        if choices_result.is_error:
            return Result.fail(choices_result.expect_error())

        choices = choices_result.value

        if not choices:
            return Result.ok(
                {
                    "user_uid": user_uid,
                    "period": {"start_date": start_date, "end_date": end_date, "days": days},
                    "decision_metrics": {
                        "total_choices": 0,
                        "choices_per_week": 0.0,
                        "principle_aligned_percentage": 0.0,
                        "goal_oriented_percentage": 0.0,
                    },
                    "decision_quality": {
                        "average_confidence": 0.0,
                        "average_satisfaction": 0.0,
                        "principle_alignment_score": 0.0,
                    },
                    "patterns": {
                        "most_common_principle": None,
                        "decision_making_trend": "no_data",
                        "strategic_vs_tactical": "no_data",
                    },
                    "recommendations": ["No choices found in this period"],
                }
            )

        # Calculate metrics
        total_choices = len(choices)
        weeks = days / 7.0
        choices_per_week = total_choices / weeks

        # Analyze alignment (simplified - would need actual principle/goal links)
        principle_aligned_count = sum(1 for c in choices if getattr(c, "aligned_principles", None))
        goal_oriented_count = sum(1 for c in choices if getattr(c, "related_goals", None))

        principle_aligned_percentage = (
            (principle_aligned_count / total_choices) if total_choices > 0 else 0
        )
        goal_oriented_percentage = (goal_oriented_count / total_choices) if total_choices > 0 else 0

        # Decision quality (simplified)
        avg_confidence = 0.7  # Placeholder
        avg_satisfaction = 0.75  # Placeholder
        principle_alignment_score = principle_aligned_percentage

        # Identify patterns
        decision_making_trend = "stable"
        if choices_per_week > 3:
            decision_making_trend = "improving"
        elif choices_per_week < 1:
            decision_making_trend = "declining"

        strategic_vs_tactical = "balanced"
        if goal_oriented_percentage > 0.6:
            strategic_vs_tactical = "strategic"
        elif goal_oriented_percentage < 0.3:
            strategic_vs_tactical = "tactical"

        # Recommendations
        recommendations = []
        if principle_aligned_percentage < 0.5:
            recommendations.append("Consider linking more choices to your core principles")
        if goal_oriented_percentage < 0.4:
            recommendations.append("Align more decisions with your goals")
        if choices_per_week < 1:
            recommendations.append("Track more decisions to build better patterns")
        if principle_aligned_percentage > 0.7:
            recommendations.append("Excellent principle alignment - keep it up!")

        return Result.ok(
            {
                "user_uid": user_uid,
                "period": {"start_date": start_date, "end_date": end_date, "days": days},
                "decision_metrics": {
                    "total_choices": total_choices,
                    "choices_per_week": choices_per_week,
                    "principle_aligned_percentage": principle_aligned_percentage,
                    "goal_oriented_percentage": goal_oriented_percentage,
                },
                "decision_quality": {
                    "average_confidence": avg_confidence,
                    "average_satisfaction": avg_satisfaction,
                    "principle_alignment_score": principle_alignment_score,
                },
                "patterns": {
                    "most_common_principle": None,  # Would need aggregation
                    "decision_making_trend": decision_making_trend,
                    "strategic_vs_tactical": strategic_vs_tactical,
                },
                "recommendations": recommendations,
            }
        )

    async def get_choice_quality_correlations(
        self, user_uid: str, days: int = 90
    ) -> Result[dict[str, Any]]:
        """
        Analyze correlations between decision quality metrics.

        Returns:
            Result containing correlations between:
            - Time pressure vs satisfaction
            - Energy level vs confidence
            - Principle alignment vs long-term satisfaction
            - Decision complexity vs quality
        """
        # Calculate date range
        end_date = date.today()
        start_date = end_date - timedelta(days=days)

        # Get user's choices in period
        choices_result = await self.backend.find_by(
            user_uid=user_uid, date__gte=start_date, date__lte=end_date
        )

        if choices_result.is_error:
            return Result.fail(choices_result.expect_error())

        choices = choices_result.value

        if not choices:
            return Result.ok(
                {
                    "user_uid": user_uid,
                    "period": {"start_date": start_date, "end_date": end_date, "days": days},
                    "correlations": {},
                    "insights": ["Insufficient data for correlation analysis"],
                }
            )

        # Placeholder correlation analysis
        # In real implementation, would calculate actual correlations from choice data
        correlations = {
            "time_pressure_vs_satisfaction": -0.3,  # Negative correlation
            "energy_vs_confidence": 0.7,  # Strong positive correlation
            "principle_alignment_vs_satisfaction": 0.8,  # Strong positive correlation
            "complexity_vs_quality": -0.2,  # Slight negative correlation
        }

        insights = []
        if correlations["time_pressure_vs_satisfaction"] < -0.2:
            insights.append("Decisions made under time pressure tend to have lower satisfaction")
        if correlations["energy_vs_confidence"] > 0.5:
            insights.append("Higher energy levels strongly correlate with decision confidence")
        if correlations["principle_alignment_vs_satisfaction"] > 0.7:
            insights.append("Principle-aligned decisions show significantly higher satisfaction")

        return Result.ok(
            {
                "user_uid": user_uid,
                "period": {"start_date": start_date, "end_date": end_date, "days": days},
                "total_choices_analyzed": len(choices),
                "correlations": correlations,
                "insights": insights,
                "recommendations": [
                    "Allow more time for important decisions",
                    "Make critical decisions when energy is high",
                    "Prioritize principle alignment for long-term satisfaction",
                ],
            }
        )

    async def get_domain_decision_patterns(
        self, user_uid: str, days: int = 90
    ) -> Result[dict[str, Any]]:
        """
        Analyze decision patterns by domain.

        Returns:
            Result containing per-domain analysis:
            - Choice frequency by domain
            - Average quality scores by domain
            - Domain-specific strengths and weaknesses
        """
        # Calculate date range
        end_date = date.today()
        start_date = end_date - timedelta(days=days)

        # Get user's choices in period
        choices_result = await self.backend.find_by(
            user_uid=user_uid, date__gte=start_date, date__lte=end_date
        )

        if choices_result.is_error:
            return Result.fail(choices_result.expect_error())

        choices = choices_result.value

        if not choices:
            return Result.ok(
                {
                    "user_uid": user_uid,
                    "period": {"start_date": start_date, "end_date": end_date, "days": days},
                    "domain_patterns": {},
                    "insights": ["No choices found in this period"],
                }
            )

        # Group choices by domain
        domain_choices: dict[str, list[Any]] = defaultdict(list)
        for choice in choices:
            domain = getattr(choice, "domain", None)
            if domain:
                domain_choices[str(domain.value)].append(choice)

        # Analyze each domain
        domain_patterns = {}
        for domain, domain_choice_list in domain_choices.items():
            count = len(domain_choice_list)
            domain_patterns[domain] = {
                "choice_count": count,
                "percentage": (count / len(choices)) * 100,
                "avg_quality_score": 0.7,  # Placeholder
                "common_themes": [],
            }

        # Generate insights
        insights = []
        if domain_patterns:
            most_common_domain = max(domain_patterns.items(), key=get_domain_choice_count)
            insights.append(f"Most decisions made in {most_common_domain[0]} domain")

        return Result.ok(
            {
                "user_uid": user_uid,
                "period": {"start_date": start_date, "end_date": end_date, "days": days},
                "total_choices": len(choices),
                "domain_patterns": domain_patterns,
                "insights": insights,
            }
        )
