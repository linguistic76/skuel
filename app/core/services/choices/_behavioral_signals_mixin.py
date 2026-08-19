"""
Behavioral Signals Mixin — ChoicesIntelligenceService
======================================================

Dual-track assessment, principle analysis, and ZPD behavioral signals.

Event handlers migrated to ChoiceEventHandlerService (March 2026).

This mixin is the ZPD bridge — it holds the richest behavioral readiness
signals consumed by ZPDService.assess_zone():
- analyze_principle_adherence → principle_adherence_score
- assess_decision_quality_dual_track → decision_consistency_score
- get_zpd_behavioral_signals → cross-domain conflict count

Cross-domain reads (choice→principle joins) are delegated to
CrossDomainQueryService. Score blending and business logic stays here.

See: core/services/zpd/zpd_service.py — ZPDService.assess_zone() consumes
     get_zpd_behavioral_signals() for behavioral_readiness computation.

Part of choices_intelligence_service.py decomposition (March 2026).
"""

from __future__ import annotations

from collections import defaultdict
from typing import TYPE_CHECKING, Any

from core.constants import QueryLimit
from core.models.enums.activity_enums import DecisionQualityLevel
from core.models.shared.dual_track import DualTrackResult
from core.models.type_hints import UserUID
from core.utils.result_simplified import Result

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from core.ports.domain_protocols import ChoicesOperations


class _BehavioralSignalsMixin:
    """
    Dual-track assessment, principle analysis, and ZPD behavioral signals.

    Event handlers migrated to ChoiceEventHandlerService (March 2026).

    Declares class-level attributes used by these methods so mypy
    resolves them without runtime cost.
    """

    # Populated by ChoicesIntelligenceService.__init__
    backend: "ChoicesOperations"
    relationships: Any
    insight_store: Any
    logger: Any
    cross_domain_query: Any

    # ========================================================================
    # DUAL-TRACK ASSESSMENT (ADR-030)
    # ========================================================================

    async def assess_decision_quality_dual_track(
        self,
        user_uid: UserUID,
        user_decision_quality_level: DecisionQualityLevel,
        user_evidence: str,
        user_reflection: str | None = None,
        period_days: int = 30,
        store_callback: Callable[[str, DualTrackResult[DecisionQualityLevel]], Awaitable[None]]
        | None = None,
    ) -> Result[DualTrackResult[DecisionQualityLevel]]:
        """
        Dual-track decision quality assessment for choices.

        Compares user's self-assessed decision-making quality with system-measured
        metrics (outcome quality, principle alignment, decision speed).

        Args:
            user_uid: User making the assessment
            user_decision_quality_level: User's self-reported decision quality level
            user_evidence: User's evidence for their assessment
            user_reflection: Optional reflection on decision-making
            period_days: Period to analyze (default 30 days)
            store_callback: Optional persistence callback (uid, result) -> None. The
                user-level check-in lives on the :User node, so the caller binds
                ``UserService.append_dual_track_checkin`` with the dimension — the
                Choices intelligence backend can't write the User node itself.

        Returns:
            Result[DualTrackResult[DecisionQualityLevel]] with gap analysis
        """
        return await self._dual_track_assessment(  # type: ignore[attr-defined]
            uid=user_uid,  # Using user_uid as entity for user-level assessment
            user_uid=user_uid,
            user_level=user_decision_quality_level,
            user_evidence=user_evidence,
            user_reflection=user_reflection,
            system_calculator=self._make_system_decision_quality_calculator(period_days),
            level_scorer=self._decision_quality_level_to_score,
            entity_type="user_choices",
            require_entity=False,  # user-level: uid=user_uid, no :Entity row to fetch
            insight_generator=self._generate_choice_gap_insights,
            recommendation_generator=self._generate_choice_gap_recommendations,
            store_callback=store_callback,
        )

    def _make_system_decision_quality_calculator(self, period_days: int) -> Any:
        """Create a system calculator for dual-track decision quality assessment."""

        async def _calculate(
            _entity: Any, u_uid: str
        ) -> tuple[DecisionQualityLevel, float, list[str]]:
            return await self._calculate_system_decision_quality_for_dual_track(
                UserUID(u_uid), period_days
            )

        return _calculate

    async def _calculate_system_decision_quality_for_dual_track(
        self, user_uid: UserUID, period_days: int = 30
    ) -> tuple[DecisionQualityLevel, float, list[str]]:
        """
        Calculate system-measured decision quality from choices data.

        Metrics considered:
        - Outcome quality (for decided choices with outcomes)
        - Principle alignment (decisions aligned with principles)
        - Decision rate (ability to decide vs staying pending)
        - Confidence calibration (high confidence → good outcomes)

        Returns:
            Tuple of (DecisionQualityLevel, score 0.0-1.0, evidence list)
        """
        from datetime import date, timedelta

        from core.models.choice.choice import Choice

        evidence: list[str] = []

        # Get choices for period — fetch the full set (find_by defaults to limit=100,
        # so the in-memory window filter below would otherwise sample an arbitrary page).
        start_date = date.today() - timedelta(days=period_days)
        choices_result = await self.backend.find_by(user_uid=user_uid, limit=QueryLimit.MAXIMUM)

        if choices_result.is_error or not choices_result.value:
            evidence.append("No choices found in analysis period")
            return DecisionQualityLevel.STRUGGLING, 0.0, evidence

        all_items = choices_result.value
        if len(all_items) >= QueryLimit.MAXIMUM:
            self.logger.warning(
                "Decision-quality assessment for %s capped at %d choices — score may be truncated",
                user_uid,
                QueryLimit.MAXIMUM,
            )
        # Filter to Choice instances and period (using created_at)
        period_choices = [
            c
            for c in all_items
            if isinstance(c, Choice) and c.created_at and c.created_at.date() >= start_date
        ]

        if not period_choices:
            evidence.append(f"No choices created in last {period_days} days")
            return DecisionQualityLevel.STRUGGLING, 0.1, evidence

        total_choices = len(period_choices)
        evidence.append(f"{total_choices} choices in period")

        # Calculate decision rate (decided vs pending)
        decided = [c for c in period_choices if c.selected_option_uid is not None]
        decision_rate = len(decided) / total_choices if total_choices > 0 else 0.0
        evidence.append(f"Decision rate: {decision_rate:.0%}")

        # Calculate outcome quality (for choices with recorded satisfaction scores)
        # satisfaction_score is 1-5, normalize to 0-1
        choices_with_satisfaction = [c for c in decided if c.satisfaction_score is not None]
        avg_outcome_quality = 0.0
        if choices_with_satisfaction:
            avg_outcome_quality = sum(
                (c.satisfaction_score or 0) / 5.0 for c in choices_with_satisfaction
            ) / len(choices_with_satisfaction)
            evidence.append(f"Average outcome quality: {avg_outcome_quality:.0%}")

        # Calculate principle alignment via relationships. No None guard: the service
        # declares _require_relationships = True, so it cannot be constructed without one.
        principle_aligned_count = 0
        for choice in decided[:10]:  # Sample first 10 for efficiency
            # Service get_related_uids takes (method_key, uid). "principles" is the
            # Choice→Principle config key (INFORMED_BY_PRINCIPLE); the previous 3-arg
            # backend signature with a raw RelationshipName.value never matched.
            rel_result = await self.relationships.get_related_uids(
                "principles",
                choice.uid,
            )
            if rel_result.is_ok and rel_result.value:
                principle_aligned_count += 1

        principle_rate = principle_aligned_count / min(len(decided), 10) if decided else 0.0
        if principle_aligned_count > 0:
            evidence.append(f"{principle_aligned_count} decisions aligned with principles")

        # Calculate quality calibration (decisions with good outcomes)
        calibration_score = 0.5  # Default neutral
        # Use satisfaction_score >= 4 as "good outcome" (4-5 on 1-5 scale)
        if choices_with_satisfaction:
            good_outcomes = [
                c
                for c in choices_with_satisfaction
                if c.satisfaction_score and c.satisfaction_score >= 4
            ]
            calibration_score = len(good_outcomes) / len(choices_with_satisfaction)
            evidence.append(f"Good outcome rate: {calibration_score:.0%}")

        # Weighted composite score
        # Outcome quality: 35%, Decision rate: 25%, Principle alignment: 25%, Calibration: 15%
        composite_score = (
            avg_outcome_quality * 0.35
            + decision_rate * 0.25
            + principle_rate * 0.25
            + calibration_score * 0.15
        )

        # Map to DecisionQualityLevel
        system_level = DecisionQualityLevel.from_score(composite_score)

        return system_level, composite_score, evidence

    @staticmethod
    def _decision_quality_level_to_score(level: DecisionQualityLevel) -> float:
        """Convert DecisionQualityLevel to numeric score."""
        return level.to_score()

    @staticmethod
    def _generate_choice_gap_insights(direction: str, gap: float, _entity_name: str) -> list[str]:
        """Generate choice-specific insights based on perception gap."""
        insights: list[str] = []

        if direction == "aligned":
            insights.append("Your self-perception of decision quality matches measured outcomes.")
            insights.append(
                "This awareness helps you make appropriate decisions for each situation."
            )
        elif direction == "user_higher":
            insights.append(f"Self-assessment exceeds measured decision quality (gap: {gap:.0%}).")
            insights.append("Consider reviewing past decision outcomes more carefully.")
            if gap > 0.25:
                insights.append(
                    "Overconfidence in decision-making may lead to insufficient analysis."
                )
        else:  # system_higher
            insights.append(f"Your decision quality is better than you perceive (gap: {gap:.0%}).")
            insights.append("You may be too self-critical about your choices.")
            if gap > 0.25:
                insights.append("Your decisions have been leading to good outcomes!")

        return insights

    @staticmethod
    def _generate_choice_gap_recommendations(
        direction: str, _gap: float, _entity: Any, evidence: list[str]
    ) -> list[str]:
        """Generate choice-specific recommendations to close the gap."""
        recommendations: list[str] = []

        if direction == "user_higher":
            recommendations.append("Track decision outcomes more systematically.")
            recommendations.append("Align more decisions with your core principles.")
            recommendations.append("Take more time for complex decisions.")
            if any("outcome" in e.lower() for e in evidence):
                recommendations.append("Review outcomes of past decisions to learn from them.")
        elif direction == "system_higher":
            recommendations.append("Acknowledge your strong decision-making abilities.")
            recommendations.append("Trust your judgment on routine decisions.")
            recommendations.append("Build on this strength by tackling more impactful choices.")
        else:  # aligned
            recommendations.append("Maintain your current decision-making practices.")
            recommendations.append("Continue reviewing outcomes to stay calibrated.")

        return recommendations

    # =========================================================================
    # PRINCIPLE-CHOICE INTEGRATION METHODS (January 2026)
    # =========================================================================

    async def analyze_principle_adherence(
        self,
        user_uid: UserUID,
        period_days: int = 90,
    ) -> Result[dict[str, Any]]:
        """
        Analyze how well user's choices adhere to their principles.

        Cross-domain read delegated to ``CrossDomainQueryService``.
        Score blending and recommendation logic stays here.

        Args:
            user_uid: User identifier
            period_days: Period to analyze (default 90 days)

        Returns:
            Result containing:
            - overall_adherence_score: float (0.0-1.0)
            - principle_breakdown: dict mapping principle_uid to adherence data
            - aligned_choices_count: int
            - unaligned_choices_count: int
            - most_aligned_principle: str | None
            - least_aligned_principle: str | None
            - recommendations: list[str]
        """
        from core.utils.sort_functions import get_aligned_count

        result = await self.cross_domain_query.get_choice_principle_adherence(user_uid, period_days)

        if result.is_error:
            return Result.fail(result)

        adherence = result.value
        total_choices = adherence.total_choices
        aligned_count = adherence.aligned_count

        if total_choices == 0:
            return Result.ok(
                {
                    "overall_adherence_score": 0.0,
                    "principle_breakdown": {},
                    "aligned_choices_count": 0,
                    "unaligned_choices_count": 0,
                    "most_aligned_principle": None,
                    "least_aligned_principle": None,
                    "recommendations": ["No choices found - start tracking decisions"],
                }
            )

        # Calculate overall adherence score
        overall_score = aligned_count / total_choices

        # Build principle breakdown
        def _empty_principle_entry() -> dict[str, Any]:
            return {"aligned_count": 0, "choice_uids": [], "avg_satisfaction": 0.0}

        principle_breakdown: dict[str, dict[str, Any]] = defaultdict(_empty_principle_entry)
        satisfaction_sums: dict[str, float] = defaultdict(float)

        for detail in adherence.choice_details:
            for p_uid in detail.principle_uids:
                if p_uid:
                    principle_breakdown[p_uid]["aligned_count"] += 1
                    principle_breakdown[p_uid]["choice_uids"].append(detail.choice_uid)
                    if detail.satisfaction:
                        satisfaction_sums[p_uid] += detail.satisfaction

        # Calculate average satisfaction per principle
        for p_uid, data in principle_breakdown.items():
            count = data["aligned_count"]
            if count > 0 and satisfaction_sums.get(p_uid):
                data["avg_satisfaction"] = (
                    satisfaction_sums[p_uid] / count / 5.0
                )  # Normalize to 0-1

        # Find most/least aligned principles
        most_aligned = None
        least_aligned = None
        if principle_breakdown:
            sorted_principles = sorted(
                principle_breakdown.items(),
                key=get_aligned_count,
                reverse=True,
            )
            most_aligned = sorted_principles[0][0]
            if len(sorted_principles) > 1:
                least_aligned = sorted_principles[-1][0]

        # Generate recommendations
        recommendations: list[str] = []
        if overall_score < 0.3:
            recommendations.append("Consider linking more choices to your core principles")
        if aligned_count < total_choices - aligned_count:
            recommendations.append("Review unaligned choices - are they serving your values?")
        if most_aligned and principle_breakdown[most_aligned]["aligned_count"] > 5:
            recommendations.append("Strong alignment with principle - continue building on this")
        if overall_score >= 0.7:
            recommendations.append(
                "Excellent principle adherence - your decisions reflect your values"
            )

        return Result.ok(
            {
                "overall_adherence_score": round(overall_score, 3),
                "principle_breakdown": dict(principle_breakdown),
                "aligned_choices_count": aligned_count,
                "unaligned_choices_count": total_choices - aligned_count,
                "most_aligned_principle": most_aligned,
                "least_aligned_principle": least_aligned,
                "recommendations": recommendations,
            }
        )

    # =========================================================================
    # ZPD BRIDGE (March 2026)
    # =========================================================================

    async def get_zpd_behavioral_signals(self, user_uid: UserUID) -> Result[dict[str, Any]]:
        """
        Extract behavioral readiness signals for ZPDService consumption.

        Aggregates choice history into signals that indicate the user's
        readiness to engage with new knowledge. Called by ZPDService.assess_zone()
        to compute behavioral_readiness on ZPDAssessment.

        Returns:
            Result containing:
            - principle_adherence_score: float (0.0-1.0) — values clarity
            - decision_consistency_score: float (0.0-1.0) — decision maturity
            - active_conflict_count: int — unresolved principle tensions
            - high_quality_decision_rate: float — recent decision quality trend

        See: core/services/zpd/zpd_service.py — ZPDService.assess_zone()
             consumes these signals for behavioral_readiness computation.
        """
        # Principle adherence (values clarity signal)
        adherence_result = await self.analyze_principle_adherence(user_uid, period_days=90)
        if adherence_result.is_error:
            principle_adherence_score = 0.0
        else:
            principle_adherence_score = adherence_result.value.get("overall_adherence_score", 0.0)

        # Decision consistency via dual-track system score
        # Use _calculate_system_decision_quality_for_dual_track directly (no user input needed)
        (
            _system_level,
            consistency_score,
            _,
        ) = await self._calculate_system_decision_quality_for_dual_track(user_uid, period_days=30)

        # Active conflicts (principle tensions signal) — cross-domain read
        conflict_result = await self.cross_domain_query.get_choice_conflict_count(user_uid)
        active_conflict_count = 0
        if conflict_result.is_ok:
            active_conflict_count = conflict_result.value.conflict_count

        # High-quality decision rate (recent 30 days)
        # Derived from the composite score — scores above 0.6 = high quality
        high_quality_decision_rate = max(0.0, min(1.0, (consistency_score - 0.3) / 0.7))

        return Result.ok(
            {
                "principle_adherence_score": round(principle_adherence_score, 3),
                "decision_consistency_score": round(consistency_score, 3),
                "active_conflict_count": active_conflict_count,
                "high_quality_decision_rate": round(high_quality_decision_rate, 3),
            }
        )
