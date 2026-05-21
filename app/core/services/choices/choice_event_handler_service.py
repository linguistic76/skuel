"""
Choice Event Handler Service
===============================

Handles event-driven reactive logic for choice domain events.

Fire-and-forget handlers that analyze decision quality when outcomes are
recorded and track decision patterns when choices are finalized.

Part of the ChoicesService decomposition — extracted from
_behavioral_signals_mixin.py which retains pure analytics methods
(dual-track assessment, principle adherence, conflict detection,
decision quality prediction, life path contribution, ZPD behavioral signals).

Responsibilities:
- Decision quality tracking when outcomes are recorded
- Decision pattern analysis when choices are made
- Principle alignment cross-domain insights
- Insight persistence for positive/missing alignment patterns
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from core.models.insight.persisted_insight import InsightImpact, InsightType, PersistedInsight
from core.models.type_hints import EntityUID
from core.utils.exception_types import DATA_CONVERSION_EXCEPTIONS, NEO4J_EXCEPTIONS
from core.utils.logging import get_logger

if TYPE_CHECKING:
    from core.events.choice_events import ChoiceMade, ChoiceOutcomeRecorded
    from core.ports.domain_protocols import ChoicesOperations
    from core.ports.infrastructure_protocols import EventBusOperations
    from core.services.insight.insight_store import InsightStore
    from core.services.relationships import UnifiedRelationshipService


# ========================================================================
# MODULE-LEVEL HELPERS
# ========================================================================


def categorize_outcome_quality(quality: float) -> str:
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


def categorize_confidence(confidence: float) -> str:
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


class ChoiceEventHandlerService:
    """Event-driven handlers for choice domain events.

    Fire-and-forget handlers that analyze decision quality and track
    decision patterns for cross-domain intelligence.

    Handles:
    - ChoiceOutcomeRecorded: Outcome quality analysis, principle alignment correlation
    - ChoiceMade: Decision pattern tracking, confidence analysis, insight persistence
    """

    def __init__(
        self,
        backend: ChoicesOperations,
        relationship_service: UnifiedRelationshipService | None = None,
        insight_store: InsightStore | None = None,
        event_bus: EventBusOperations | None = None,
    ) -> None:
        """Initialize choice event handler service.

        Args:
            backend: Backend for choice operations
            relationship_service: For querying principle alignment (optional)
            insight_store: For persisting decision pattern insights (optional)
            event_bus: For publishing follow-up events (optional)
        """
        self.backend = backend
        self.relationships = relationship_service
        self.insight_store = insight_store
        self.event_bus = event_bus
        self.logger = get_logger("skuel.services.choices.event_handler")

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
                    "principles",
                    EntityUID(event.choice_uid),
                )
                if rel_result.is_ok:
                    aligned_principles = rel_result.value

            # 3. Determine outcome quality category
            outcome_quality = event.outcome_quality
            quality_category = categorize_outcome_quality(outcome_quality)

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

        except (*NEO4J_EXCEPTIONS, *DATA_CONVERSION_EXCEPTIONS) as e:
            self.logger.error(
                f"Error analyzing choice outcome: {e}",
                extra={"choice_uid": event.choice_uid, "error": str(e)},
            )

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
                    "principles",
                    EntityUID(event.choice_uid),
                )
                if rel_result.is_ok:
                    aligned_principles = rel_result.value

            # 3. Analyze decision confidence
            confidence = event.confidence
            confidence_category = categorize_confidence(confidence)
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
                            InsightType.DECISION_PATTERN, EntityUID(event.choice_uid)
                        ),
                        user_uid=event.user_uid,
                        insight_type=InsightType.DECISION_PATTERN,
                        domain="choices",
                        title="Strong Principle-Aligned Decision",
                        description=f"You made a high-confidence decision aligned with {len(aligned_principles)} principle(s).",
                        confidence=0.9,
                        impact=InsightImpact.LOW,  # Positive pattern, not urgent
                        entity_uid=EntityUID(event.choice_uid),
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
                            InsightType.PRINCIPLE_ALIGNMENT, EntityUID(event.choice_uid)
                        ),
                        user_uid=event.user_uid,
                        insight_type=InsightType.PRINCIPLE_ALIGNMENT,
                        domain="choices",
                        title="Complex Decision Without Principle Guidance",
                        description=f"This complex decision (complexity: {round(complexity, 1)}) wasn't aligned with any principles.",
                        confidence=0.8,
                        impact=InsightImpact.MEDIUM,
                        entity_uid=EntityUID(event.choice_uid),
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

        except (*NEO4J_EXCEPTIONS, *DATA_CONVERSION_EXCEPTIONS) as e:
            self.logger.error(
                f"Error analyzing choice made: {e}",
                extra={"choice_uid": event.choice_uid, "error": str(e)},
            )
