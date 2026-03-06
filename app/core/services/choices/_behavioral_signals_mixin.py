"""
Behavioral Signals Mixin — ChoicesIntelligenceService
======================================================

Event handlers, dual-track assessment, principle analysis, prediction,
life-path contribution, and ZPD behavioral signals.

This mixin is the ZPD bridge — it holds the richest behavioral readiness
signals consumed by ZPDService.assess_zone():
- analyze_principle_adherence → principle_adherence_score
- detect_principle_choice_conflicts → active_conflict_count
- assess_decision_quality_dual_track → decision_consistency_score

See: core/services/zpd/zpd_service.py — ZPDService.assess_zone() consumes
     get_zpd_behavioral_signals() for behavioral_readiness computation.

Part of choices_intelligence_service.py decomposition (March 2026).
"""

from __future__ import annotations

from collections import defaultdict
from typing import TYPE_CHECKING, Any

from core.models.enums.activity_enums import DecisionQualityLevel
from core.models.insight.persisted_insight import InsightImpact, InsightType, PersistedInsight
from core.models.relationship_names import RelationshipName
from core.models.shared.dual_track import DualTrackResult
from core.utils.result_simplified import Errors, Result

if TYPE_CHECKING:
    from core.events.choice_events import ChoiceMade, ChoiceOutcomeRecorded


class _BehavioralSignalsMixin:
    """
    Event handlers, dual-track assessment, principle analysis, prediction,
    life-path contribution, and ZPD behavioral signals.

    Declares class-level attributes used by these methods so mypy
    resolves them without runtime cost.
    """

    # Populated by ChoicesIntelligenceService.__init__
    backend: Any
    relationships: Any
    insight_store: Any
    logger: Any

    # ========================================================================
    # EVENT HANDLERS
    # ========================================================================

    async def handle_choice_outcome_recorded(self, event: ChoiceOutcomeRecorded) -> None:
        """Track decision quality when outcome is recorded.

        Event-driven handler that analyzes choice outcomes to learn from
        decisions. Enables cross-domain intelligence by connecting
        outcomes to principle alignment and decision patterns.

        The handler:
        1. Gets choice details (description, domain, selected option)
        2. Checks principle alignment of the choice
        3. Tracks outcome quality vs. alignment correlation
        4. Logs structured insights for pattern analysis

        Args:
            event: ChoiceOutcomeRecorded event with outcome context

        Note:
            This is a fire-and-forget handler - it logs but doesn't
            fail the original operation. Errors are caught and logged.
        """
        try:
            # 1. Get choice details
            choice_result = await self.backend.get(event.choice_uid)
            if choice_result.is_error:
                self.logger.warning(
                    f"Failed to get choice for outcome analysis: {event.choice_uid}"
                )
                return

            choice = choice_result.value
            if not choice:
                self.logger.warning(f"Choice not found for outcome analysis: {event.choice_uid}")
                return

            # 2. Query principle alignment relationships
            aligned_principles: list[str] = []
            if self.relationships:
                rel_result = await self.relationships.get_related_uids(
                    event.choice_uid,
                    RelationshipName.ALIGNED_WITH_PRINCIPLE.value,
                    "outgoing",
                )
                if rel_result.is_ok:
                    aligned_principles = rel_result.value

            # 3. Determine outcome quality category
            outcome_quality = event.outcome_quality
            quality_category = self._categorize_outcome_quality(outcome_quality)

            # 4. Analyze principle alignment correlation
            was_principle_aligned = len(aligned_principles) > 0
            alignment_outcome_match = (was_principle_aligned and outcome_quality >= 0.6) or (
                not was_principle_aligned and outcome_quality < 0.6
            )

            # 5. Log structured insights for decision learning
            self.logger.info(
                f"Choice outcome recorded: {(choice.description or '')[:50]}...",
                extra={
                    "choice_uid": event.choice_uid,
                    "user_uid": event.user_uid,
                    "outcome_quality": round(outcome_quality, 2),
                    "quality_category": quality_category,
                    "principles_aligned": len(aligned_principles),
                    "was_principle_aligned": was_principle_aligned,
                    "alignment_outcome_match": alignment_outcome_match,
                    "lessons_learned": (
                        event.lessons_learned[:100] if event.lessons_learned else None
                    ),
                    "event_type": "choice.outcome.analyzed",
                },
            )

            # Log insight about principle correlation
            if was_principle_aligned:
                if outcome_quality >= 0.7:
                    self.logger.info(
                        f"Principle-aligned choice had positive outcome ({quality_category})",
                        extra={
                            "choice_uid": event.choice_uid,
                            "principle_count": len(aligned_principles),
                            "event_type": "choice.principle_correlation.positive",
                        },
                    )
                elif outcome_quality < 0.4:
                    self.logger.info(
                        "Principle-aligned choice had negative outcome - worth reviewing",
                        extra={
                            "choice_uid": event.choice_uid,
                            "principle_uids": aligned_principles[:3],
                            "event_type": "choice.principle_correlation.review_needed",
                        },
                    )

        except Exception as e:
            self.logger.error(
                f"Error analyzing choice outcome: {e}",
                extra={"choice_uid": event.choice_uid, "error": str(e)},
            )

    def _categorize_outcome_quality(self, quality: float) -> str:
        """Categorize outcome quality score into named buckets.

        Args:
            quality: Outcome quality score (0.0 - 1.0)

        Returns:
            Category name: "excellent", "good", "neutral", "poor", "bad"
        """
        if quality >= 0.8:
            return "excellent"
        elif quality >= 0.6:
            return "good"
        elif quality >= 0.4:
            return "neutral"
        elif quality >= 0.2:
            return "poor"
        else:
            return "bad"

    async def handle_choice_made(self, event: ChoiceMade) -> None:
        """Track decision patterns when a choice is finalized.

        Event-driven handler that analyzes decision-making patterns when
        choices are made. Enables cross-domain intelligence by connecting
        decisions to principle alignment and confidence patterns.

        The handler:
        1. Gets choice details (description, domain, urgency)
        2. Checks principle alignment of the decision
        3. Analyzes confidence level vs. complexity correlation
        4. Logs structured insights for decision pattern analysis

        Args:
            event: ChoiceMade event with decision context

        Note:
            This is a fire-and-forget handler - it logs but doesn't
            fail the original operation. Errors are caught and logged.
        """
        from core.models.choice.choice import Choice

        try:
            # 1. Get choice details
            choice_result = await self.backend.get(event.choice_uid)
            if choice_result.is_error:
                self.logger.warning(
                    f"Failed to get choice for decision analysis: {event.choice_uid}"
                )
                return

            choice = choice_result.value
            if not choice or not isinstance(choice, Choice):
                self.logger.warning(f"Choice not found for decision analysis: {event.choice_uid}")
                return

            # 2. Query principle alignment relationships
            aligned_principles: list[str] = []
            if self.relationships:
                rel_result = await self.relationships.get_related_uids(
                    event.choice_uid,
                    RelationshipName.ALIGNED_WITH_PRINCIPLE.value,
                    "outgoing",
                )
                if rel_result.is_ok:
                    aligned_principles = rel_result.value

            # 3. Analyze decision confidence
            confidence = event.confidence
            confidence_category = self._categorize_confidence(confidence)
            was_principle_aligned = len(aligned_principles) > 0

            # 4. Calculate decision complexity from choice model
            complexity = choice.calculate_decision_complexity()

            # 5. Analyze confidence vs complexity correlation
            # High confidence on complex decisions = experienced decision-maker
            # Low confidence on simple decisions = may need support
            confidence_complexity_ratio = confidence / max(complexity / 10.0, 0.1)

            # 6. Log structured insights
            self.logger.info(
                f"Choice made: {(choice.description or '')[:50]}...",
                extra={
                    "choice_uid": event.choice_uid,
                    "user_uid": event.user_uid,
                    "selected_option": event.selected_option,
                    "confidence": round(confidence, 2),
                    "confidence_category": confidence_category,
                    "complexity": round(complexity, 2),
                    "principles_aligned": len(aligned_principles),
                    "was_principle_aligned": was_principle_aligned,
                    "confidence_complexity_ratio": round(confidence_complexity_ratio, 2),
                    "event_type": "choice.made.analyzed",
                },
            )

            # Log insight about principle-aligned decisions
            if was_principle_aligned and confidence >= 0.7:
                self.logger.info(
                    "High-confidence principle-aligned decision made",
                    extra={
                        "choice_uid": event.choice_uid,
                        "principle_count": len(aligned_principles),
                        "confidence": round(confidence, 2),
                        "event_type": "choice.principle_confidence.high",
                    },
                )

                # Persist insight for positive pattern
                if self.insight_store:
                    insight = PersistedInsight(
                        uid=PersistedInsight.generate_uid(
                            InsightType.DECISION_PATTERN, event.choice_uid
                        ),
                        user_uid=event.user_uid,
                        insight_type=InsightType.DECISION_PATTERN,
                        domain="choices",
                        title="Strong Principle-Aligned Decision",
                        description=f"You made a high-confidence decision aligned with {len(aligned_principles)} principle(s).",
                        confidence=0.9,
                        impact=InsightImpact.LOW,  # Positive pattern, not urgent
                        entity_uid=event.choice_uid,
                        recommended_actions=[],
                        supporting_data={
                            "confidence": round(confidence, 2),
                            "principle_count": len(aligned_principles),
                            "aligned_principles": aligned_principles[:3],
                            "complexity": round(complexity, 2),
                        },
                    )
                    create_result = await self.insight_store.create_insight(insight)
                    if create_result.is_error:
                        self.logger.warning(
                            f"Failed to persist decision pattern insight: {create_result.error}"
                        )

            elif not was_principle_aligned and complexity > 5.0:
                self.logger.info(
                    "Complex decision made without principle alignment",
                    extra={
                        "choice_uid": event.choice_uid,
                        "complexity": round(complexity, 2),
                        "event_type": "choice.principle_alignment.missing",
                    },
                )

                # Persist insight for missing alignment
                if self.insight_store:
                    insight = PersistedInsight(
                        uid=PersistedInsight.generate_uid(
                            InsightType.PRINCIPLE_ALIGNMENT, event.choice_uid
                        ),
                        user_uid=event.user_uid,
                        insight_type=InsightType.PRINCIPLE_ALIGNMENT,
                        domain="choices",
                        title="Complex Decision Without Principle Guidance",
                        description=f"This complex decision (complexity: {round(complexity, 1)}) wasn't aligned with any principles.",
                        confidence=0.8,
                        impact=InsightImpact.MEDIUM,
                        entity_uid=event.choice_uid,
                        recommended_actions=[
                            {
                                "action": "Link principles to guide future decisions",
                                "rationale": "Principles provide clarity for complex choices",
                            }
                        ],
                        supporting_data={
                            "complexity": round(complexity, 2),
                            "confidence": round(confidence, 2),
                        },
                    )
                    create_result = await self.insight_store.create_insight(insight)
                    if create_result.is_error:
                        self.logger.warning(
                            f"Failed to persist alignment insight: {create_result.error}"
                        )

        except Exception as e:
            self.logger.error(
                f"Error analyzing choice made: {e}",
                extra={"choice_uid": event.choice_uid, "error": str(e)},
            )

    def _categorize_confidence(self, confidence: float) -> str:
        """Categorize decision confidence into named buckets.

        Args:
            confidence: Confidence score (0.0 - 1.0)

        Returns:
            Category name: "very_high", "high", "moderate", "low", "very_low"
        """
        if confidence >= 0.9:
            return "very_high"
        elif confidence >= 0.7:
            return "high"
        elif confidence >= 0.5:
            return "moderate"
        elif confidence >= 0.3:
            return "low"
        else:
            return "very_low"

    # ========================================================================
    # DUAL-TRACK ASSESSMENT (ADR-030)
    # ========================================================================

    async def assess_decision_quality_dual_track(
        self,
        user_uid: str,
        user_decision_quality_level: DecisionQualityLevel,
        user_evidence: str,
        user_reflection: str | None = None,
        period_days: int = 30,
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
            insight_generator=self._generate_choice_gap_insights,
            recommendation_generator=self._generate_choice_gap_recommendations,
        )

    def _make_system_decision_quality_calculator(self, period_days: int) -> Any:
        """Create a system calculator for dual-track decision quality assessment."""

        async def _calculate(
            _entity: Any, u_uid: str
        ) -> tuple[DecisionQualityLevel, float, list[str]]:
            return await self._calculate_system_decision_quality_for_dual_track(u_uid, period_days)

        return _calculate

    async def _calculate_system_decision_quality_for_dual_track(
        self, user_uid: str, period_days: int = 30
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

        # Get choices for period
        start_date = date.today() - timedelta(days=period_days)
        choices_result = await self.backend.find_by(user_uid=user_uid)

        if choices_result.is_error or not choices_result.value:
            evidence.append("No choices found in analysis period")
            return DecisionQualityLevel.STRUGGLING, 0.0, evidence

        all_items = choices_result.value
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

        # Calculate principle alignment via relationships
        principle_aligned_count = 0
        if self.relationships:
            for choice in decided[:10]:  # Sample first 10 for efficiency
                rel_result = await self.relationships.get_related_uids(
                    choice.uid,
                    RelationshipName.ALIGNED_WITH_PRINCIPLE.value,
                    "outgoing",
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
        user_uid: str,
        period_days: int = 90,
    ) -> Result[dict[str, Any]]:
        """
        Analyze how well user's choices adhere to their principles.

        This method provides insight into the alignment between a user's
        stated principles and their actual decision-making behavior.

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

        # Query for choices with principle alignment in the period
        query = """
        MATCH (u:User {uid: $user_uid})-[:OWNS]->(c:Entity {entity_type: 'choice'})
        WHERE c.created_at >= datetime() - duration({days: $period_days})

        OPTIONAL MATCH (c)-[:ALIGNED_WITH_PRINCIPLE]->(p:Entity {entity_type: 'principle'})

        WITH c,
             collect(DISTINCT p.uid) AS principle_uids,
             CASE WHEN count(p) > 0 THEN 1 ELSE 0 END AS is_aligned

        RETURN
            count(c) AS total_choices,
            sum(is_aligned) AS aligned_count,
            collect({
                choice_uid: c.uid,
                principles: principle_uids,
                satisfaction: c.satisfaction_score
            }) AS choice_details
        """

        result = await self.backend.execute_query(
            query,
            {"user_uid": user_uid, "period_days": period_days},
        )

        if result.is_error:
            return Result.fail(result.expect_error())

        if not result.value:
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

        record = result.value[0]
        total_choices = record.get("total_choices", 0)
        aligned_count = record.get("aligned_count", 0)
        choice_details = record.get("choice_details", [])

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

        for detail in choice_details:
            for p_uid in detail.get("principles", []):
                if p_uid:
                    principle_breakdown[p_uid]["aligned_count"] += 1
                    principle_breakdown[p_uid]["choice_uids"].append(detail["choice_uid"])
                    if detail.get("satisfaction"):
                        satisfaction_sums[p_uid] += detail["satisfaction"]

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

    async def detect_principle_choice_conflicts(
        self,
        choice_uid: str,
        user_uid: str,
    ) -> Result[dict[str, Any]]:
        """
        Detect conflicts between a choice and user's principles.

        Analyzes:
        1. Direct conflicts - choice explicitly conflicts with a principle
        2. Implicit conflicts - choice options may violate principles
        3. Missing alignment - important decisions without principle guidance

        Args:
            choice_uid: Choice identifier
            user_uid: User identifier

        Returns:
            Result containing:
            - has_conflicts: bool
            - direct_conflicts: list of conflicting principles with severity
            - unaligned_warning: bool (True if important choice lacks principle alignment)
            - mitigation_strategies: list of resolution approaches
        """
        # Query for choice and its principle relationships
        query = """
        MATCH (c:Entity {uid: $choice_uid, entity_type: 'choice'})

        // Get aligned principles
        OPTIONAL MATCH (c)-[:ALIGNED_WITH_PRINCIPLE]->(aligned:Entity {entity_type: 'principle'})

        // Get any conflicting principles
        OPTIONAL MATCH (c)-[:CONFLICTS_WITH_PRINCIPLE]->(conflicting:Entity {entity_type: 'principle'})

        // Get user's core principles for comparison
        OPTIONAL MATCH (u:User {uid: $user_uid})-[:OWNS]->(core:Entity {entity_type: 'principle'})
        WHERE core.strength IN ['CORE', 'STRONG']

        RETURN
            c.uid AS choice_uid,
            c.title AS choice_title,
            c.impact_level AS impact_level,
            collect(DISTINCT aligned.uid) AS aligned_uids,
            collect(DISTINCT {
                uid: conflicting.uid,
                name: conflicting.name
            }) AS conflicts,
            collect(DISTINCT core.uid) AS core_principle_uids
        """

        result = await self.backend.execute_query(
            query,
            {"choice_uid": choice_uid, "user_uid": user_uid},
        )

        if result.is_error:
            return Result.fail(result.expect_error())

        if not result.value:
            return Result.fail(Errors.not_found(resource="Choice", identifier=choice_uid))

        record = result.value[0]
        aligned_uids = [u for u in record.get("aligned_uids", []) if u]
        conflicts = [c for c in record.get("conflicts", []) if c.get("uid")]
        core_principle_uids = [u for u in record.get("core_principle_uids", []) if u]
        impact_level = record.get("impact_level", "low")

        # Determine if unaligned warning applies
        # High-impact choices should be aligned with at least one principle
        unaligned_warning = (
            impact_level in ["high", "critical"]
            and len(aligned_uids) == 0
            and len(core_principle_uids) > 0
        )

        # Build direct conflicts list
        direct_conflicts = [
            {
                "principle_uid": c["uid"],
                "principle_name": c.get("name", "Unknown"),
                "conflict_reason": "Choice explicitly conflicts with stated principle",
                "severity": "high",
            }
            for c in conflicts
        ]

        # Generate mitigation strategies
        mitigation_strategies: list[str] = []
        if direct_conflicts:
            mitigation_strategies.append("Review choice alignment with conflicting principles")
            mitigation_strategies.append(
                "Consider alternative approaches that honor all principles"
            )
            mitigation_strategies.append("Discuss trade-offs with a trusted advisor")
        if unaligned_warning:
            mitigation_strategies.append(
                "Link this high-impact choice to relevant principles for better guidance"
            )
            mitigation_strategies.append(
                "Consider which core principles should inform this decision"
            )

        return Result.ok(
            {
                "has_conflicts": len(direct_conflicts) > 0,
                "direct_conflicts": direct_conflicts,
                "unaligned_warning": unaligned_warning,
                "aligned_principle_count": len(aligned_uids),
                "mitigation_strategies": mitigation_strategies,
            }
        )

    async def predict_decision_quality(
        self,
        choice_uid: str,
        user_uid: str,
    ) -> Result[dict[str, Any]]:
        """
        Predict decision quality based on principle alignment and historical patterns.

        Uses a 4-factor model:
        1. Principle alignment (35%) - Is the choice guided by principles?
        2. Knowledge-informed (25%) - Is the choice informed by knowledge?
        3. Historical correlation (25%) - Past aligned choices vs satisfaction
        4. Complexity-guidance ratio (15%) - Guidance relative to complexity

        Args:
            choice_uid: Choice identifier
            user_uid: User identifier

        Returns:
            Result containing:
            - predicted_quality_score: float (0.0-1.0)
            - confidence: float (0.0-1.0)
            - quality_factors: breakdown by factor
            - historical_correlation: float
            - recommendations: list[str]
        """
        from core.models.choice.choice import Choice
        from core.services.choices.choice_relationships import ChoiceRelationships

        # Get choice
        choice_result = await self.backend.get(choice_uid)
        if choice_result.is_error:
            return Result.fail(choice_result.expect_error())

        choice = choice_result.value
        if not choice or not isinstance(choice, Choice):
            return Result.fail(Errors.not_found(resource="Choice", identifier=choice_uid))

        # Fetch relationships
        rels = await ChoiceRelationships.fetch(choice_uid, self.relationships)

        # Factor 1: Principle alignment (35% weight)
        principle_count = len(rels.aligned_principle_uids)
        if principle_count == 0:
            principle_factor = 0.0
        elif principle_count == 1:
            principle_factor = 0.25
        else:
            principle_factor = min(0.35, principle_count * 0.12)

        # Factor 2: Knowledge-informed (25% weight)
        knowledge_count = len(rels.informed_by_knowledge_uids)
        knowledge_factor = 0.0 if knowledge_count == 0 else min(0.25, knowledge_count * 0.08)

        # Factor 3: Historical correlation (25% weight)
        # Query past decisions with similar patterns
        historical_query = """
        MATCH (u:User {uid: $user_uid})-[:OWNS]->(c:Entity {entity_type: 'choice'})
        WHERE c.satisfaction_score IS NOT NULL
        OPTIONAL MATCH (c)-[:ALIGNED_WITH_PRINCIPLE]->(p:Entity {entity_type: 'principle'})
        WITH c, count(p) AS principle_count
        RETURN
            avg(CASE WHEN principle_count > 0 THEN c.satisfaction_score ELSE null END) AS aligned_avg,
            avg(CASE WHEN principle_count = 0 THEN c.satisfaction_score ELSE null END) AS unaligned_avg,
            count(c) AS total_choices
        """

        hist_result = await self.backend.execute_query(
            historical_query,
            {"user_uid": user_uid},
        )

        historical_factor = 0.125  # Default neutral
        historical_correlation = 0.0
        if hist_result.is_ok and hist_result.value:
            record = hist_result.value[0]
            aligned_avg = record.get("aligned_avg") or 3.0
            unaligned_avg = record.get("unaligned_avg") or 3.0
            total_choices = record.get("total_choices", 0)

            if total_choices >= 5:  # Need enough data
                # Calculate correlation (positive if aligned choices have better satisfaction)
                correlation = (aligned_avg - unaligned_avg) / 5.0
                historical_correlation = correlation

                if rels.is_principle_aligned() and aligned_avg > unaligned_avg:
                    historical_factor = 0.25
                elif not rels.is_principle_aligned() and unaligned_avg > aligned_avg:
                    historical_factor = 0.20
                else:
                    historical_factor = 0.125

        # Factor 4: Complexity-guidance ratio (15% weight)
        # Choice model always has calculate_decision_complexity method
        complexity = choice.calculate_decision_complexity()
        guidance_strength = principle_count * 0.2 + knowledge_count * 0.1
        if complexity > 0:
            complexity_factor = 0.15 * min(1.0, guidance_strength / complexity)
        else:
            complexity_factor = 0.15 * min(1.0, guidance_strength)

        # Calculate predicted score
        predicted_score = (
            principle_factor + knowledge_factor + historical_factor + complexity_factor
        )
        predicted_score = min(1.0, max(0.0, predicted_score))

        # Calculate confidence based on data availability
        confidence = 0.5  # Base confidence
        if (
            hist_result.is_ok
            and hist_result.value
            and hist_result.value[0].get("total_choices", 0) >= 10
        ):
            confidence += 0.2
        if rels.is_principle_aligned():
            confidence += 0.15
        if rels.is_informed_decision():
            confidence += 0.15
        confidence = min(1.0, confidence)

        # Generate recommendations
        recommendations: list[str] = []
        if not rels.is_principle_aligned():
            recommendations.append("Link this choice to relevant principles for better outcomes")
        if not rels.is_informed_decision():
            recommendations.append("Consider researching more before deciding")
        if complexity > 0.7 and principle_count < 2:
            recommendations.append("Complex decision - ensure multiple principles guide you")
        if predicted_score >= 0.7:
            recommendations.append("Good decision foundation - proceed with confidence")

        return Result.ok(
            {
                "predicted_quality_score": round(predicted_score, 3),
                "confidence": round(confidence, 3),
                "quality_factors": {
                    "principle_alignment": round(principle_factor, 3),
                    "knowledge_informed": round(knowledge_factor, 3),
                    "historical_pattern": round(historical_factor, 3),
                    "complexity_guidance": round(complexity_factor, 3),
                },
                "historical_correlation": round(historical_correlation, 3),
                "recommendations": recommendations,
            }
        )

    async def calculate_life_path_contribution_via_principles(
        self,
        choice_uid: str,
        user_uid: str,
    ) -> Result[dict[str, Any]]:
        """
        Calculate how a choice contributes to life path via principle alignment.

        Graph traversal: Choice -> Principle -> LifePath

        This method traces the contribution chain from a specific choice
        through aligned principles to the user's ultimate life path.

        Args:
            choice_uid: Choice identifier
            user_uid: User identifier

        Returns:
            Result containing:
            - total_contribution_score: float (0.0-1.0)
            - direct_contribution: float (if Choice -> LifePath exists)
            - principle_mediated_contribution: float (via Choice -> Principle -> LifePath)
            - contributing_principles: list with individual contributions
            - life_path_uid: str | None
            - life_path_title: str | None
        """
        # Query for life path contribution via principles
        query = """
        MATCH (c:Entity {uid: $choice_uid, entity_type: 'choice'})

        // Get user's life path
        OPTIONAL MATCH (u:User {uid: $user_uid})-[:ULTIMATE_PATH]->(lp:Entity {entity_type: 'learning_path'})

        // Direct contribution (if any)
        OPTIONAL MATCH (c)-[direct:SERVES_LIFE_PATH]->(lp)

        // Principle-mediated contribution
        OPTIONAL MATCH (c)-[:ALIGNED_WITH_PRINCIPLE]->(p:Entity {entity_type: 'principle'})
                       -[pserve:SERVES_LIFE_PATH]->(lp)

        RETURN
            lp.uid AS life_path_uid,
            lp.title AS life_path_title,
            direct.contribution_score AS direct_score,
            collect(DISTINCT {
                uid: p.uid,
                name: p.name,
                contribution: pserve.contribution_score
            }) AS principle_contributions
        """

        result = await self.backend.execute_query(
            query,
            {"choice_uid": choice_uid, "user_uid": user_uid},
        )

        if result.is_error:
            return Result.fail(result.expect_error())

        if not result.value:
            return Result.ok(
                {
                    "total_contribution_score": 0.0,
                    "direct_contribution": 0.0,
                    "principle_mediated_contribution": 0.0,
                    "contributing_principles": [],
                    "life_path_uid": None,
                    "life_path_title": None,
                    "message": "Choice not found or no life path defined",
                }
            )

        record = result.value[0]
        life_path_uid = record.get("life_path_uid")

        if not life_path_uid:
            return Result.ok(
                {
                    "total_contribution_score": 0.0,
                    "direct_contribution": 0.0,
                    "principle_mediated_contribution": 0.0,
                    "contributing_principles": [],
                    "life_path_uid": None,
                    "life_path_title": None,
                    "message": "No life path defined for user",
                }
            )

        direct_score = record.get("direct_score") or 0.0
        principle_contributions = record.get("principle_contributions", [])

        # Filter valid contributions (have both uid and contribution score)
        valid_contributions = [
            {
                "uid": p["uid"],
                "name": p.get("name", "Unknown"),
                "contribution": p["contribution"],
            }
            for p in principle_contributions
            if p.get("uid") and p.get("contribution")
        ]

        # Calculate principle-mediated contribution (average of contributions)
        principle_mediated = 0.0
        if valid_contributions:
            principle_mediated = sum(p["contribution"] for p in valid_contributions) / len(
                valid_contributions
            )

        # Total contribution: weighted combination
        # Direct contribution is weighted more (60%) if it exists
        # Principle-mediated fills in the remaining (40%) or full (100%) if no direct
        if direct_score > 0:
            total_score = (direct_score * 0.6) + (principle_mediated * 0.4)
        else:
            total_score = principle_mediated

        total_score = min(1.0, total_score)

        return Result.ok(
            {
                "total_contribution_score": round(total_score, 3),
                "direct_contribution": round(direct_score, 3),
                "principle_mediated_contribution": round(principle_mediated, 3),
                "contributing_principles": valid_contributions,
                "life_path_uid": life_path_uid,
                "life_path_title": record.get("life_path_title"),
            }
        )

    # =========================================================================
    # ZPD BRIDGE (March 2026)
    # =========================================================================

    async def get_zpd_behavioral_signals(self, user_uid: str) -> Result[dict[str, Any]]:
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
            system_level,
            consistency_score,
            _,
        ) = await self._calculate_system_decision_quality_for_dual_track(user_uid, period_days=30)

        # Active conflicts (principle tensions signal)
        # Count recent choices with unresolved principle conflicts
        conflict_query = """
        MATCH (u:User {uid: $user_uid})-[:OWNS]->(c:Entity {entity_type: 'choice'})
        WHERE c.created_at >= datetime() - duration({days: 30})
        MATCH (c)-[:CONFLICTS_WITH_PRINCIPLE]->(:Entity {entity_type: 'principle'})
        RETURN count(DISTINCT c) AS conflict_count
        """
        conflict_result = await self.backend.execute_query(conflict_query, {"user_uid": user_uid})
        active_conflict_count = 0
        if conflict_result.is_ok and conflict_result.value:
            active_conflict_count = conflict_result.value[0].get("conflict_count", 0)

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
