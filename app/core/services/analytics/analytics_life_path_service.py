"""
Analytics Life Path Service
============================

Life Path alignment tracking and analytics for Layer 3 meta-analysis.

This service provides the CRITICAL missing piece for Analytics to become
true Layer 3: calculating how well user's activities align with their
ultimate life goal (Life Path).

Core Philosophy: "Everything flows toward the life path"

This service answers:
- "Am I living my life path?" → Alignment score (0.0-1.0)
- "What knowledge do I actually use?" → Substance metrics
- "Which activities drive alignment?" → Domain contribution breakdown
- "Where should I focus?" → Gap identification + recommendations

Part of the 4-service Analytics architecture:
- AnalyticsService: Facade orchestrating all analytics
- AnalyticsMetricsService: Domain-specific statistics
- AnalyticsAggregationService: Cross-domain synthesis
- AnalyticsLifePathService: Life Path alignment tracking (this file)

Implementation Date: October 24, 2025
"""

from datetime import datetime
from typing import Any, TypedDict

from core.utils.logging import get_logger
from core.utils.result_simplified import Errors, Result

logger = get_logger(__name__)


class KnowledgeSubstanceInfo(TypedDict):
    """Type definition for knowledge substance analysis data."""

    ku_uid: str  # Knowledge unit UID
    title: str  # Knowledge unit title
    substance: float  # Substance score (0.0-1.0)


class AnalyticsLifePathService:
    """
    Life Path alignment tracking and analysis.

    This service calculates how well user's activities (Layer 1) serve
    their ultimate life goal (Life Path from Layer 0).

    Substance tracking measures whether knowledge is LIVED, not just learned.


    Source Tag: "analytics_life_path_explicit"
    - Format: "analytics_life_path_explicit" for user-created relationships
    - Format: "analytics_life_path_inferred" for system-generated relationships

    Confidence Scoring:
    - 0.9+: User explicitly defined relationship
    - 0.7-0.9: Inferred from learning_paths metadata
    - 0.5-0.7: Suggested based on patterns
    - <0.5: Low confidence, needs verification

    SKUEL Architecture:
    - Uses CypherGenerator for ALL graph queries
    - No APOC calls (Phase 5 eliminated those)
    - Returns Result[T] for error handling
    - Logs operations with structured logging

    """

    def __init__(self, user_service=None, ku_service=None, lp_service=None) -> None:
        """
        Initialize Life Path analytics service.

        Args:
            user_service: UserService for getting UserContext
            ku_service: KuService for knowledge substance scores
            lp_service: LpService for Learning Path details
        """
        self.user_service = user_service
        self.ku_service = ku_service
        self.lp_service = lp_service
        self.logger = logger
        logger.info("AnalyticsLifePathService initialized")

    async def calculate_life_path_alignment(self, user_uid: str) -> Result[dict[str, Any]]:
        """
        Calculate user's alignment with their ultimate life goal.

        This is THE most important metric in SKUEL - measures whether
        user is LIVING their life path or just learning about it.

        Args:
            user_uid: User identifier

        Returns:
            Result containing comprehensive alignment analysis:
            {
                "life_path_uid": "lp:mindful-software-engineer",
                "life_path_title": "Become a Mindful Software Engineer",
                "alignment_score": 0.73,  # 0.0-1.0
                "knowledge_count": 15,
                "embodied_knowledge": 8,  # substance >= 0.7
                "theoretical_knowledge": 7,  # substance < 0.5
                "domain_contributions": {
                    "habits": 0.40,  # 40% of alignment from habits
                    "tasks": 0.25,
                    ...
                },
                "gaps": [
                    {"ku_uid": "ku:meditation", "title": "...", "substance": 0.3}
                ],
                "trends": {
                    "7_days_ago": 0.68,
                    "30_days_ago": 0.61,
                    "direction": "improving"
                },
                "recommendations": [...]
            }
        """
        try:
            self.logger.info(f"Calculating Life Path alignment for user {user_uid}")

            # Step 1: Get user's Life Path from UserContext
            if not self.user_service:
                return Result.fail(
                    Errors.system(
                        "UserService not available - cannot get Life Path",
                        operation="calculate_life_path_alignment",
                    )
                )

            context_result = await self.user_service.get_user_context(user_uid)
            if context_result.is_error:
                return Result.fail(context_result)

            context = context_result.value
            life_path_uid = context.life_path_uid

            if not life_path_uid:
                # User hasn't designated a Life Path yet
                return Result.ok(
                    {
                        "life_path_uid": None,
                        "life_path_title": None,
                        "alignment_score": 0.0,
                        "knowledge_count": 0,
                        "embodied_knowledge": 0,
                        "theoretical_knowledge": 0,
                        "domain_contributions": {},
                        "gaps": [],
                        "trends": {},
                        "recommendations": ["Designate a Life Path to track alignment"],
                        "message": "No Life Path designated yet",
                    }
                )

            # Step 2: Get Life Path details
            if not self.lp_service:
                return Result.fail(
                    Errors.system(
                        "LpService not available - cannot get Life Path details",
                        operation="calculate_life_path_alignment",
                    )
                )

            lp_result = await self.lp_service.get(life_path_uid)
            if lp_result.is_error:
                return Result.fail(lp_result)

            if not lp_result.value:
                return Result.fail(Errors.not_found(resource="Life Path", identifier=life_path_uid))

            life_path = lp_result.value
            life_path_title = life_path.title

            # Step 3: Get all Knowledge Units in Life Path
            if not self.ku_service:
                return Result.fail(
                    Errors.system(
                        "KuService not available - cannot get knowledge units",
                        operation="calculate_life_path_alignment",
                    )
                )

            # Get knowledge units for this learning path
            # Note: This assumes LpService can provide knowledge UIDs
            # In practice, may need to query through learning steps
            kus_result = await self._get_life_path_knowledge_units(life_path_uid)
            if kus_result.is_error:
                return Result.fail(kus_result)

            knowledge_units = kus_result.value

            if not knowledge_units:
                return Result.ok(
                    {
                        "life_path_uid": life_path_uid,
                        "life_path_title": life_path_title,
                        "alignment_score": 0.0,
                        "knowledge_count": 0,
                        "embodied_knowledge": 0,
                        "theoretical_knowledge": 0,
                        "domain_contributions": {},
                        "gaps": [],
                        "trends": {},
                        "recommendations": ["Add knowledge units to your Life Path"],
                        "message": "Life Path has no knowledge units yet",
                    }
                )

            # Step 4: Calculate substance scores for each Ku
            knowledge_analysis = await self._analyze_knowledge_substance(knowledge_units, user_uid)

            # Step 5: Calculate overall alignment score (average substance)
            alignment_score = knowledge_analysis["avg_substance"]

            # Step 6: Analyze domain contributions
            domain_contributions = await self._analyze_domain_contributions(
                knowledge_units, user_uid
            )

            # Step 7: Identify gaps (low substance knowledge)
            gaps = knowledge_analysis["gaps"]

            # Step 8: Track trends (would need historical data - placeholder for now)
            trends = await self._calculate_alignment_trends(user_uid, life_path_uid)

            # Step 9: Generate recommendations
            recommendations = self._generate_recommendations(
                knowledge_analysis, domain_contributions, gaps
            )

            return Result.ok(
                {
                    "life_path_uid": life_path_uid,
                    "life_path_title": life_path_title,
                    "alignment_score": round(alignment_score, 2),
                    "knowledge_count": knowledge_analysis["total_count"],
                    "embodied_knowledge": knowledge_analysis["embodied_count"],
                    "theoretical_knowledge": knowledge_analysis["theoretical_count"],
                    "domain_contributions": domain_contributions,
                    "gaps": gaps,
                    "trends": trends,
                    "recommendations": recommendations,
                    "calculated_at": datetime.now().isoformat(),
                }
            )

        except Exception as e:
            return Result.fail(
                Errors.system(
                    f"Failed to calculate Life Path alignment: {e!s}",
                    operation="calculate_life_path_alignment",
                    exception=e,
                )
            )

    async def _get_life_path_knowledge_units(self, life_path_uid: str) -> Result[list[Any]]:
        """
        Get all Knowledge Units in a Life Path.

        This queries through the Learning Path to find all associated Kus.

        Args:
            life_path_uid: Learning Path UID

        Returns:
            Result containing list of KnowledgeUnit objects
        """
        try:
            # Get learning steps for this path
            steps_result = await self.lp_service.get_learning_steps(life_path_uid)
            if steps_result.is_error:
                return Result.fail(steps_result)

            steps = steps_result.value or []

            # Extract knowledge UIDs from steps using domain method
            knowledge_uids = [ku_uid for step in steps for ku_uid in step.get_all_knowledge_uids()]

            if not knowledge_uids:
                return Result.ok([])

            # Get all knowledge units
            knowledge_units = []
            for ku_uid in knowledge_uids:
                ku_result = await self.ku_service.get(ku_uid)
                if ku_result.is_ok and ku_result.value:
                    knowledge_units.append(ku_result.value)

            return Result.ok(knowledge_units)

        except Exception as e:
            return Result.fail(
                Errors.system(
                    f"Failed to get Life Path knowledge units: {e!s}",
                    operation="_get_life_path_knowledge_units",
                    exception=e,
                )
            )

    async def _analyze_knowledge_substance(
        self, knowledge_units: list, user_uid: str
    ) -> dict[str, Any]:
        """
        Analyze substance scores for knowledge units.

        Categorizes knowledge by substance level:
        - Embodied (0.7+): Lifestyle-integrated
        - Practiced (0.5-0.7): Regular use
        - Applied (0.3-0.5): Some practice
        - Theoretical (<0.3): No real-world application

        Args:
            knowledge_units: List of Entity objects
            user_uid: User identifier

        Returns:
            Dict with substance analysis
        """
        total_substance = 0.0
        embodied: list[KnowledgeSubstanceInfo] = []  # >= 0.7
        practiced: list[KnowledgeSubstanceInfo] = []  # 0.5-0.7
        applied: list[KnowledgeSubstanceInfo] = []  # 0.3-0.5
        theoretical: list[KnowledgeSubstanceInfo] = []  # < 0.3

        for ku_dto in knowledge_units:
            # Backend returns Ku instances (entity_class=Ku), not DTOs
            substance = ku_dto.substance_score()

            total_substance += substance

            # Categorize by substance level
            ku_info: KnowledgeSubstanceInfo = {
                "ku_uid": ku_dto.uid,
                "title": ku_dto.title,
                "substance": round(substance, 2),
            }

            if substance >= 0.7:
                embodied.append(ku_info)
            elif substance >= 0.5:
                practiced.append(ku_info)
            elif substance >= 0.3:
                applied.append(ku_info)
            else:
                theoretical.append(ku_info)

        count = len(knowledge_units)
        avg_substance = total_substance / count if count > 0 else 0.0

        # Gaps are theoretical + low applied knowledge
        gaps = theoretical + [ku for ku in applied if ku["substance"] < 0.4]

        return {
            "user_uid": user_uid,  # Include for context and validation
            "total_count": count,
            "avg_substance": avg_substance,
            "embodied_count": len(embodied),
            "practiced_count": len(practiced),
            "applied_count": len(applied),
            "theoretical_count": len(theoretical),
            "embodied": embodied,
            "practiced": practiced,
            "applied": applied,
            "theoretical": theoretical,
            "gaps": gaps,
        }

    async def _analyze_domain_contributions(
        self, knowledge_units: list, user_uid: str
    ) -> dict[str, float]:
        """
        Analyze which Layer 1 domains contribute most to Life Path alignment.

        Calculates the proportion of substance that comes from each domain:
        - Habits (weight 0.10 per instance)
        - Journals (weight 0.07 per instance)
        - Choices (weight 0.07 per instance)
        - Events (weight 0.05 per instance)
        - Tasks (weight 0.05 per instance)

        Args:
            knowledge_units: List of Entity objects
            user_uid: User identifier

        Returns:
            Dict mapping domain name to contribution proportion (0.0-1.0)
        """
        # This is a simplified calculation - in full implementation,
        # would need to query each Ku's substance breakdown by domain

        # For now, return placeholder showing expected structure
        # In real implementation, would sum substance_by_type for each Ku

        domain_totals = {
            "habits": 0.0,
            "journals": 0.0,
            "choices": 0.0,
            "events": 0.0,
            "tasks": 0.0,
        }

        total_substance = 0.0

        for ku_dto in knowledge_units:
            # Backend returns Ku instances (entity_class=Ku), not DTOs
            # Get substance breakdown if available (future feature)
            breakdown = getattr(ku_dto, "substance_by_type", None)
            if breakdown is not None:
                for domain, value in breakdown.items():
                    domain_key = domain.lower()
                    if domain_key in domain_totals:
                        domain_totals[domain_key] += value
                        total_substance += value

        # Calculate proportions
        contributions = {}
        if total_substance > 0:
            for domain, value in domain_totals.items():
                contributions[domain] = round(value / total_substance, 2)
        else:
            # No substance yet - equal placeholder
            contributions = {domain: 0.0 for domain in domain_totals}

        # Include user_uid for context and validation
        contributions["user_uid"] = user_uid
        contributions["total_substance"] = round(total_substance, 2)

        return contributions

    async def _calculate_alignment_trends(
        self, user_uid: str, life_path_uid: str
    ) -> dict[str, Any]:
        """
        Calculate alignment trends over time.

        Shows whether alignment is improving, declining, or stable.

        Args:
            user_uid: User identifier
            life_path_uid: Life Path UID

        Returns:
            Dict with historical alignment scores and trend direction
        """
        # TODO [FEATURE]: Full implementation would:
        # 1. Query historical alignment scores for this user+life_path combination
        # 2. Use user_uid and life_path_uid to filter historical snapshots
        # 3. Calculate 7-day and 30-day rolling averages
        # 4. Determine trend direction (improving/declining/stable)
        #
        # Query would look like:
        # snapshots = await self.backend.find_by(
        #     user_uid=user_uid,
        #     life_path_uid=life_path_uid,
        #     limit=30
        # )

        # For now, return structure showing expected data with context
        return {
            "user_uid": user_uid,  # User context for trend analysis
            "life_path_uid": life_path_uid,  # Life path being tracked
            "7_days_ago": None,
            "30_days_ago": None,
            "direction": "unknown",
            "note": "Historical tracking not yet implemented - parameters reserved for future use",
        }

    def _generate_recommendations(
        self,
        knowledge_analysis: dict[str, Any],
        domain_contributions: dict[str, float],
        gaps: list[dict[str, Any]],
    ) -> list[str]:
        """
        Generate actionable recommendations based on alignment analysis.

        Args:
            knowledge_analysis: Substance analysis from _analyze_knowledge_substance
            domain_contributions: Domain contribution analysis
            gaps: List of knowledge units with low substance

        Returns:
            List of recommendation strings
        """
        recommendations = []

        # Check for gaps
        if gaps:
            top_gaps = gaps[:3]  # Top 3 gaps
            recommendations.extend(
                [
                    f"Increase substance for: {gap['title']} (currently {gap['substance']})"
                    for gap in top_gaps
                ]
            )

        # Check for low domain contributions
        for domain, contribution in domain_contributions.items():
            if contribution < 0.1:  # Less than 10% contribution
                if domain == "habits":
                    recommendations.append(
                        "Build habits around Life Path knowledge to increase alignment"
                    )
                elif domain == "tasks":
                    recommendations.append("Create tasks that apply Life Path knowledge")
                elif domain == "events":
                    recommendations.append("Schedule events to practice Life Path skills")

        # Check overall alignment
        avg_substance = knowledge_analysis["avg_substance"]
        if avg_substance < 0.5:
            recommendations.append(
                "Overall alignment is low - focus on applying Life Path knowledge daily"
            )
        elif avg_substance >= 0.7:
            recommendations.append("Excellent alignment! Life Path knowledge is well-practiced")

        if not recommendations:
            recommendations.append("Alignment looks good - keep up the practice!")

        return recommendations
