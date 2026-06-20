"""
Principle Event Handler Service
================================

Handles event-driven analysis for principle domain events.

Fire-and-forget handlers that analyze cascade impacts, generate
cross-domain insights, and persist conflict intelligence.

Part of the PrinciplesService decomposition — extracted from
PrinciplesIntelligenceService to separate event handling from
graph analytics.

Responsibilities:
- Analyze cascade impact when principle strength changes
- Generate cross-domain insights from reflection events
- Handle conflict detection and resolution guidance
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from core.events.principle_events import (
    PrincipleConflictRevealed,
    PrincipleReflectionRecorded,
    PrincipleStrengthChanged,
)
from core.models.enums.principle_enums import PrincipleStrength, TriggerType
from core.models.insight.persisted_insight import InsightImpact, InsightType, PersistedInsight
from core.models.principle.principle import Principle
from core.models.type_hints import EntityUID
from core.utils.exception_types import DATA_CONVERSION_EXCEPTIONS, NEO4J_EXCEPTIONS
from core.utils.logging import get_logger

if TYPE_CHECKING:
    from core.ports.domain_protocols import (
        BaseRelationshipOperations,
        PrinciplesOperations,
    )
    from core.services.insight.insight_store import InsightStore

logger = get_logger(__name__)


def _determine_conflict_severity_from_strengths(strength1: str, strength2: str) -> str:
    """Determine conflict severity based on principle strength strings.

    Shared logic used by both event handlers and conflict analysis.

    Args:
        strength1: First principle's strength value
        strength2: Second principle's strength value

    Returns:
        Severity level: "high", "medium", or "low"
    """
    if strength1 == "core" and strength2 == "core":
        return "high"
    elif "core" in (strength1, strength2) or (strength1 == "strong" and strength2 == "strong"):
        return "medium"
    else:
        return "low"


class PrincipleEventHandlerService:
    """Event-driven handlers for principle domain events.

    Fire-and-forget handlers that analyze cascade impacts, generate
    cross-domain insights, and persist conflict intelligence.

    Handles:
    - PrincipleStrengthChanged: Cascade impact analysis on connected goals/habits
    - PrincipleReflectionRecorded: Cross-domain insight generation
    - PrincipleConflictRevealed: Conflict detection, resolution guidance, persistence
    """

    def __init__(
        self,
        backend: PrinciplesOperations,
        relationship_service: BaseRelationshipOperations | None = None,
        insight_store: InsightStore | None = None,
        event_bus: Any = None,
    ) -> None:
        """
        Initialize principle event handler service.

        Args:
            backend: Backend for principle operations
            relationship_service: For querying related entities (goals, habits)
            insight_store: For persisting event-driven insights (optional)
            event_bus: Event bus (accepted for factory uniformity, not used)
        """
        self.backend = backend
        self.relationships = relationship_service
        self.insight_store = insight_store
        self.logger = get_logger("skuel.services.principles.event_handler")

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

            principle: Principle | None = principle_result.value
            if not principle:
                self.logger.warning(
                    f"Principle not found for cascade analysis: {event.principle_uid}"
                )
                return

            # 2. Query connected goals via the principle's GUIDES_GOAL edge.
            # ("get_principle_goals" was a phantom — declared on the protocol but
            # implemented nowhere; the generic reader keyed by config method is the
            # one real path. See PRINCIPLES_CONFIG: GUIDES_GOAL → "guided_goals".)
            goal_uids: list[str] = []
            if self.relationships:
                goal_result = await self.relationships.get_related_uids(
                    "guided_goals", EntityUID(event.principle_uid)
                )
                if goal_result.is_ok:
                    goal_uids = goal_result.value

            # 3. Query connected habits via the principle's INSPIRES_HABIT edge.
            # ("habits" was not a valid PRINCIPLES_CONFIG method key → the reader
            # failed and silently returned none; "inspired_habits" is the key for
            # INSPIRES_HABIT, the principle→habit cascade direction.)
            habit_uids: list[str] = []
            if self.relationships:
                habit_result = await self.relationships.get_related_uids(
                    "inspired_habits", EntityUID(event.principle_uid)
                )
                if habit_result.is_ok:
                    habit_uids = habit_result.value

            # 4. Calculate cascade impact
            total_affected = len(goal_uids) + len(habit_uids)
            strength_change = _categorize_strength_change(event.old_strength, event.new_strength)

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

        except (*NEO4J_EXCEPTIONS, *DATA_CONVERSION_EXCEPTIONS) as e:
            self.logger.error(
                f"Error analyzing principle strength change: {e}",
                extra={"principle_uid": event.principle_uid, "error": str(e)},
            )

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

            principle: Principle | None = principle_result.value
            if not principle:
                self.logger.warning(
                    f"Principle not found for reflection analysis: {event.principle_uid}"
                )
                return

            # 2. Analyze trigger context - cross-domain insight generation
            is_cross_domain = (
                event.trigger_type is not None and event.trigger_type.is_cross_domain()
            )
            trigger_context = _analyze_trigger_context(event.trigger_type, event.trigger_uid)

            # 3. Determine alignment quality category
            alignment_category = _categorize_alignment(event.alignment_level)

            # 4. Calculate reflection quality assessment
            quality_assessment = _assess_reflection_quality(
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

        except (*NEO4J_EXCEPTIONS, *DATA_CONVERSION_EXCEPTIONS) as e:
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

    async def handle_conflict_revealed(self, event: PrincipleConflictRevealed) -> None:
        """
        Handle principle conflict detection and generate resolution guidance.

        Event-driven handler that responds to revealed conflicts between principles.
        Creates/updates CONFLICTS_WITH relationships in the graph and generates
        guidance for resolving the tension.

        The handler:
        1. Gets both principle details
        2. Determines conflict severity from principle strengths
        3. Generates resolution guidance
        4. Logs high-priority conflict insight
        5. Persists conflict insight to InsightStore

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

            principle1: Principle | None = p1_result.value
            principle2: Principle | None = p2_result.value
            if not principle1 or not principle2:
                self.logger.warning(
                    f"One or both principles not found for conflict analysis: "
                    f"{event.principle_uid}, {event.conflicting_principle_uid}"
                )
                return

            # 2. Determine conflict severity based on principle strengths
            p1_strength = "unknown"
            p2_strength = "unknown"
            if isinstance(principle1, Principle) and principle1.strength:
                p1_strength = principle1.strength.value
            if isinstance(principle2, Principle) and principle2.strength:
                p2_strength = principle2.strength.value
            severity = _determine_conflict_severity_from_strengths(p1_strength, p2_strength)

            # 3. Generate resolution guidance
            resolution_guidance = _generate_resolution_guidance(
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

            # 7. Persist conflict insight to InsightStore
            if self.insight_store:
                impact = InsightImpact.CRITICAL if severity == "high" else InsightImpact.HIGH
                insight = PersistedInsight(
                    uid=PersistedInsight.generate_uid(
                        InsightType.PRINCIPLE_CONFLICT, EntityUID(event.principle_uid)
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
                    entity_uid=EntityUID(event.principle_uid),
                    related_entities={"principles": [event.conflicting_principle_uid]},
                    recommended_actions=resolution_guidance,
                    supporting_data={
                        "severity": severity,
                        "conflict_context": event.conflict_context,
                        "reflection_uid": event.reflection_uid,
                        "principle1_strength": p1_strength,
                        "principle2_strength": p2_strength,
                    },
                )
                create_result = await self.insight_store.create_insight(insight)
                if create_result.is_error:
                    self.logger.warning(
                        f"Failed to persist conflict insight: {create_result.error}"
                    )

        except (*NEO4J_EXCEPTIONS, *DATA_CONVERSION_EXCEPTIONS) as e:
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


# ========================================================================
# MODULE-LEVEL HELPERS
# ========================================================================


def _categorize_strength_change(old_strength: str, new_strength: str) -> str:
    """Categorize the type of strength change.

    Args:
        old_strength: Previous strength value
        new_strength: New strength value

    Returns:
        Change type: "elevation", "demotion", or "lateral"
    """
    valid = {s.value for s in PrincipleStrength}
    if old_strength.lower() not in valid or new_strength.lower() not in valid:
        return "lateral"
    old_rank = PrincipleStrength.from_value(old_strength).rank()
    new_rank = PrincipleStrength.from_value(new_strength).rank()
    if new_rank > old_rank:
        return "elevation"
    if new_rank < old_rank:
        return "demotion"
    return "lateral"


def _analyze_trigger_context(
    trigger_type: TriggerType | None, trigger_uid: str | None
) -> dict[str, Any]:
    """Analyze the context of what triggered this reflection."""
    if not trigger_type or not trigger_uid:
        return {"type": TriggerType.MANUAL.value, "description": "Self-initiated reflection"}

    descriptions = {
        TriggerType.GOAL: "Reflection triggered while working on a goal",
        TriggerType.HABIT: "Reflection triggered during habit practice",
        TriggerType.EVENT: "Reflection triggered by a calendar event",
        TriggerType.CHOICE: "Reflection triggered while making a decision",
    }

    return {
        "type": trigger_type.value,
        "trigger_uid": trigger_uid,
        "description": descriptions.get(trigger_type, f"Triggered by {trigger_type.value}"),
        "cross_domain": True,
    }


def _categorize_alignment(alignment_level: str) -> str:
    """Categorize alignment level into broad categories."""
    level_lower = alignment_level.lower()
    if level_lower in ("strongly_aligned", "aligned", "exemplary"):
        return "aligned"
    elif level_lower in ("neutral", "somewhat_aligned", "mixed"):
        return "neutral"
    else:
        return "misaligned"


def _assess_reflection_quality(quality_score: float, evidence: str) -> str:
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


def _generate_resolution_guidance(
    principle1: Principle,
    principle2: Principle,
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
