"""
Goal Event Handler Service
============================

Handles event-driven reactive logic for goal domain events.

Fire-and-forget handlers that analyze achievement patterns, detect
abandonment trends, and monitor progress velocity.

Part of the GoalsService decomposition — replaces GoalsRecommendationService
by centralizing all domain-specific event handling.

Responsibilities:
- Recommendation generation from goal achievements (migrated from GoalsRecommendationService)
- Duration calibration on goal achievement
- Principle alignment cross-domain insights
- Abandonment pattern classification
- Progress stall detection and milestone proximity alerts
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from core.events import publish_event
from core.events.goal_events import (
    GoalAbandoned,
    GoalAchieved,
    GoalProgressUpdated,
    GoalRecommendationsGenerated,
)
from core.models.insight.persisted_insight import InsightImpact, InsightType, PersistedInsight
from core.models.type_hints import EntityUID, UserUID
from core.services.insight import persist_principle_alignment_insight
from core.utils.exception_types import DATA_CONVERSION_EXCEPTIONS, NEO4J_EXCEPTIONS
from core.utils.logging import get_logger

if TYPE_CHECKING:
    from core.ports.domain_protocols import GoalsOperations
    from core.ports.infrastructure_protocols import EventBusOperations
    from core.services.insight.insight_store import InsightStore
    from core.services.relationships import UnifiedRelationshipService


# ========================================================================
# MODULE-LEVEL HELPERS
# ========================================================================


def _classify_abandonment(progress: float) -> str:
    """Classify abandonment by progress at time of abandonment.

    Args:
        progress: Progress percentage (0.0 to 1.0) at abandonment

    Returns:
        Classification: "early_pivot", "mid_course", or "near_miss"
    """
    if progress < 0.25:
        return "early_pivot"
    elif progress > 0.75:
        return "near_miss"
    else:
        return "mid_course"


def _nearest_milestone(progress: float) -> int | None:
    """Return nearest milestone percentage if within 5%, else None.

    Args:
        progress: Current progress (0.0 to 1.0)

    Returns:
        Milestone percentage (25, 50, 75, 100) or None
    """
    for milestone in (0.25, 0.50, 0.75, 1.00):
        if 0 < (milestone - progress) <= 0.05:
            return int(milestone * 100)
    return None


class GoalEventHandlerService:
    """Event-driven handlers for goal domain events.

    Fire-and-forget handlers that analyze achievement patterns, detect
    abandonment trends, and monitor progress velocity.

    Handles:
    - GoalAchieved: Recommendation generation, duration calibration, principle alignment
    - GoalAbandoned: Abandonment classification, structured logging
    - GoalProgressUpdated: Stall detection, milestone proximity, trigger logging
    """

    def __init__(
        self,
        backend: GoalsOperations,
        relationship_service: UnifiedRelationshipService | None = None,
        event_bus: EventBusOperations | None = None,
        insight_store: InsightStore | None = None,
    ) -> None:
        """Initialize goal event handler service.

        Args:
            backend: Backend for goal operations
            relationship_service: For querying related entities (optional)
            event_bus: For publishing recommendation events (optional)
            insight_store: For persisting event-driven insights (optional)
        """
        self.backend = backend
        self.relationships = relationship_service
        self.event_bus = event_bus
        self.insight_store = insight_store
        self.logger = get_logger("skuel.services.goals.event_handler")

    # ========================================================================
    # EVENT HANDLERS
    # ========================================================================

    async def handle_goal_achieved(self, event: GoalAchieved) -> None:
        """Handle goal achievement with recommendations, duration calibration, and alignment.

        Migrated from GoalsRecommendationService.handle_goal_achieved().

        The handler:
        1. Gets achieved goal context and generates recommendations
        2. Publishes GoalRecommendationsGenerated event
        3. Compares actual vs planned duration for calibration insight
        4. Checks principle alignment for cross-domain insight

        Args:
            event: GoalAchieved event with achievement context

        Note:
            Fire-and-forget — errors are logged, never propagated.
        """
        try:
            # 1. Recommendation generation (migrated from GoalsRecommendationService)
            goal_context = await self._get_goal_context(event.goal_uid, event.user_uid)
            if goal_context:
                recommendations = self._generate_recommendations(goal_context, event.user_uid)

                if recommendations:
                    self.logger.info(
                        f"Generated {len(recommendations)} recommendations for goal {event.goal_uid}"
                    )

                    recommendation_event = GoalRecommendationsGenerated(
                        goal_uid=event.goal_uid,
                        user_uid=event.user_uid,
                        recommendations=recommendations,
                        triggered_by_achievement=True,
                    )
                    await publish_event(self.event_bus, recommendation_event, self.logger)
                else:
                    self.logger.info(f"No recommendations generated for goal {event.goal_uid}")
            else:
                self.logger.warning(f"Goal {event.goal_uid} not found, skipping recommendations")

            # 2. Duration calibration
            if event.actual_duration_days is not None and event.planned_duration_days is not None:
                ratio = event.actual_duration_days / max(event.planned_duration_days, 1)
                accuracy = "ahead" if ratio < 0.9 else "behind" if ratio > 1.1 else "on_track"

                self.logger.info(
                    f"Goal duration calibration: {event.actual_duration_days}d actual "
                    f"vs {event.planned_duration_days}d planned ({accuracy})",
                    extra={
                        "goal_uid": event.goal_uid,
                        "user_uid": event.user_uid,
                        "actual_days": event.actual_duration_days,
                        "planned_days": event.planned_duration_days,
                        "duration_ratio": round(ratio, 2),
                        "accuracy": accuracy,
                        "event_type": "goal.duration.calibrated",
                    },
                )

            # 3. Principle alignment check
            if self.relationships:
                await self._check_principle_alignment(event)

        except (*NEO4J_EXCEPTIONS, *DATA_CONVERSION_EXCEPTIONS) as e:
            self.logger.error(
                f"Error handling goal_achieved event: {e}",
                extra={
                    "goal_uid": event.goal_uid,
                    "user_uid": event.user_uid,
                    "error": str(e),
                },
            )

    async def handle_goal_abandoned(self, event: GoalAbandoned) -> None:
        """Handle goal abandonment with classification and structured logging.

        Classifies abandonment as:
        - "early_pivot" (<25% progress)
        - "mid_course" (25-75% progress)
        - "near_miss" (>75% progress)

        Args:
            event: GoalAbandoned event with abandonment context

        Note:
            Fire-and-forget — errors are logged, never propagated.
        """
        try:
            classification = _classify_abandonment(event.progress_at_abandonment)

            self.logger.info(
                f"Goal abandoned ({classification}): {event.progress_at_abandonment:.0%} progress after {event.days_active}d",
                extra={
                    "goal_uid": event.goal_uid,
                    "user_uid": event.user_uid,
                    "classification": classification,
                    "reason": event.reason,
                    "progress_at_abandonment": event.progress_at_abandonment,
                    "days_active": event.days_active,
                    "event_type": "goal.abandoned.classified",
                },
            )

            # Near-miss deserves special attention
            if classification == "near_miss":
                self.logger.warning(
                    f"Near-miss abandonment: goal was {event.progress_at_abandonment:.0%} complete",
                    extra={
                        "goal_uid": event.goal_uid,
                        "user_uid": event.user_uid,
                        "progress": event.progress_at_abandonment,
                        "reason": event.reason,
                        "event_type": "goal.abandoned.near_miss",
                    },
                )

            # Persist abandonment insight
            if self.insight_store:
                impact = (
                    InsightImpact.HIGH if classification == "near_miss" else InsightImpact.MEDIUM
                )
                insight = PersistedInsight(
                    uid=PersistedInsight.generate_uid(
                        InsightType.COMPLETION_PATTERN, EntityUID(event.goal_uid)
                    ),
                    user_uid=event.user_uid,
                    insight_type=InsightType.COMPLETION_PATTERN,
                    domain="goals",
                    title=f"Goal Abandoned ({classification.replace('_', ' ')})",
                    description=f"Goal abandoned at {event.progress_at_abandonment:.0%} progress after {event.days_active} days.",
                    confidence=0.85,
                    impact=impact,
                    entity_uid=EntityUID(event.goal_uid),
                    recommended_actions=[
                        {
                            "action": "Review goal scope and break into smaller milestones",
                            "rationale": "Near-miss abandonments suggest the goal was achievable with better pacing",
                        }
                    ]
                    if classification == "near_miss"
                    else [],
                    supporting_data={
                        "classification": classification,
                        "progress_at_abandonment": event.progress_at_abandonment,
                        "days_active": event.days_active,
                        "reason": event.reason,
                    },
                )
                create_result = await self.insight_store.create_insight(insight)
                if create_result.is_error:
                    self.logger.warning(
                        f"Failed to persist abandonment insight: {create_result.error}"
                    )

        except (*NEO4J_EXCEPTIONS, *DATA_CONVERSION_EXCEPTIONS) as e:
            self.logger.error(
                f"Error handling goal_abandoned event: {e}",
                extra={
                    "goal_uid": event.goal_uid,
                    "user_uid": event.user_uid,
                    "error": str(e),
                },
            )

    async def handle_goal_progress_updated(self, event: GoalProgressUpdated) -> None:
        """Handle goal progress updates with stall detection and milestone proximity.

        The handler:
        1. Detects near-zero progress changes (stall warning)
        2. Alerts when progress is within 5% of a milestone (25/50/75/100%)
        3. Logs which domain triggered the update

        Args:
            event: GoalProgressUpdated event with progress context

        Note:
            Fire-and-forget — lightweight, no graph queries.
        """
        try:
            # 1. Progress stall detection
            if abs(event.progress_delta) < 0.01 and event.new_progress > 0:
                self.logger.warning(
                    f"Progress stall detected: goal at {event.new_progress:.0%} with negligible change",
                    extra={
                        "goal_uid": event.goal_uid,
                        "user_uid": event.user_uid,
                        "new_progress": event.new_progress,
                        "progress_delta": event.progress_delta,
                        "event_type": "goal.progress.stall",
                    },
                )

                # Persist stall insight
                if self.insight_store:
                    insight = PersistedInsight(
                        uid=PersistedInsight.generate_uid(
                            InsightType.IMBALANCE_DETECTED, EntityUID(event.goal_uid)
                        ),
                        user_uid=event.user_uid,
                        insight_type=InsightType.IMBALANCE_DETECTED,
                        domain="goals",
                        title="Goal Progress Stall",
                        description=f"Goal at {event.new_progress:.0%} with negligible recent progress.",
                        confidence=0.8,
                        impact=InsightImpact.MEDIUM,
                        entity_uid=EntityUID(event.goal_uid),
                        recommended_actions=[
                            {
                                "action": "Break the goal into smaller actionable tasks",
                                "rationale": "Stalled goals often need decomposition to regain momentum",
                            }
                        ],
                        supporting_data={
                            "new_progress": event.new_progress,
                            "progress_delta": event.progress_delta,
                        },
                    )
                    create_result = await self.insight_store.create_insight(insight)
                    if create_result.is_error:
                        self.logger.warning(
                            f"Failed to persist stall insight: {create_result.error}"
                        )

            # 2. Milestone proximity alert
            milestone = _nearest_milestone(event.new_progress)
            if milestone is not None:
                self.logger.info(
                    f"Goal approaching {milestone}% milestone (currently {event.new_progress:.0%})",
                    extra={
                        "goal_uid": event.goal_uid,
                        "user_uid": event.user_uid,
                        "new_progress": event.new_progress,
                        "approaching_milestone": milestone,
                        "event_type": "goal.progress.milestone_proximity",
                    },
                )

                # Persist milestone proximity insight
                if self.insight_store:
                    insight = PersistedInsight(
                        uid=PersistedInsight.generate_uid(
                            InsightType.COMPLETION_PATTERN, EntityUID(event.goal_uid)
                        ),
                        user_uid=event.user_uid,
                        insight_type=InsightType.COMPLETION_PATTERN,
                        domain="goals",
                        title=f"Approaching {milestone}% Milestone",
                        description=f"Goal is within 5% of the {milestone}% milestone — keep pushing!",
                        confidence=0.9,
                        impact=InsightImpact.LOW,
                        entity_uid=EntityUID(event.goal_uid),
                        supporting_data={
                            "new_progress": event.new_progress,
                            "approaching_milestone": milestone,
                        },
                    )
                    create_result = await self.insight_store.create_insight(insight)
                    if create_result.is_error:
                        self.logger.warning(
                            f"Failed to persist milestone insight: {create_result.error}"
                        )

            # 3. Cross-domain trigger logging
            trigger = "manual"
            if event.triggered_by_task_completion:
                trigger = "task_completion"
            elif event.triggered_by_habit_completion:
                trigger = "habit_completion"

            self.logger.info(
                f"Goal progress updated: {event.old_progress:.0%} -> {event.new_progress:.0%} (trigger: {trigger})",
                extra={
                    "goal_uid": event.goal_uid,
                    "user_uid": event.user_uid,
                    "old_progress": event.old_progress,
                    "new_progress": event.new_progress,
                    "progress_delta": event.progress_delta,
                    "trigger": trigger,
                    "event_type": "goal.progress.updated",
                },
            )

        except (*NEO4J_EXCEPTIONS, *DATA_CONVERSION_EXCEPTIONS) as e:
            self.logger.error(
                f"Error handling goal_progress_updated event: {e}",
                extra={
                    "goal_uid": event.goal_uid,
                    "user_uid": event.user_uid,
                    "error": str(e),
                },
            )

    # ========================================================================
    # INTERNAL HELPERS (migrated from GoalsRecommendationService)
    # ========================================================================

    async def _get_goal_context(self, goal_uid: str, user_uid: UserUID) -> dict | None:
        """Get achieved goal context for recommendation generation.

        Retrieves:
        - Goal properties (domain, type, timeframe)
        - Related knowledge units (REQUIRES_KNOWLEDGE)
        - Related habits (SUPPORTS_GOAL)
        - Related principles (GUIDED_BY_PRINCIPLE)

        Args:
            goal_uid: Achieved goal UID
            user_uid: User who achieved the goal

        Returns:
            Goal context dict with properties and relationships, or None if not found
        """
        result = await self.backend.get_achievement_context(goal_uid, user_uid)
        if result.is_error:
            self.logger.error(f"Failed to get goal context for {goal_uid}: {result.error}")
            return None

        if not result.value:
            return None

        return result.value[0]

    def _generate_recommendations(self, goal_context: dict, user_uid: UserUID) -> list[dict]:
        """Generate goal recommendations based on achieved goal context.

        Recommendation strategies:
        1. Domain progression: Similar goals in same domain
        2. Knowledge expansion: Goals requiring related knowledge
        3. Habit reinforcement: Goals supported by established habits
        4. Principle alignment: Goals guided by same principles

        Args:
            goal_context: Context from achieved goal
            user_uid: User receiving recommendations

        Returns:
            List of recommendation dicts (max 5)
        """
        recommendations: list[dict[str, Any]] = []
        domain = goal_context.get("domain", "KNOWLEDGE")
        goal_type = goal_context.get("goal_type", "OUTCOME")
        knowledge_units = goal_context.get("knowledge_units", [])
        habits = goal_context.get("habits", [])
        principles = goal_context.get("principles", [])

        # Strategy 1: Domain progression
        domain_rec = self._recommend_domain_progression(domain, goal_type)
        if domain_rec:
            recommendations.append(domain_rec)

        # Strategy 2: Knowledge expansion
        if knowledge_units:
            knowledge_rec = self._recommend_knowledge_expansion(knowledge_units)
            if knowledge_rec:
                recommendations.append(knowledge_rec)

        # Strategy 3: Habit reinforcement
        if habits:
            habit_rec = self._recommend_habit_reinforcement(habits)
            if habit_rec:
                recommendations.append(habit_rec)

        # Strategy 4: Principle alignment
        if principles:
            principle_rec = self._recommend_principle_alignment(principles)
            if principle_rec:
                recommendations.append(principle_rec)

        return recommendations[:5]

    def _recommend_domain_progression(self, domain: str, goal_type: str) -> dict | None:
        """Recommend a progressive goal in the same domain."""
        # FUTURE-IMPL-001: See docs/reference/PLACEHOLDER_INDEX.md § E2
        domain_progressions = {
            "TECH": {
                "LEARNING": "Apply your knowledge by building a real project",
                "OUTCOME": "Share your expertise by teaching or mentoring others",
                "PROJECT": "Expand the project with advanced features",
            },
            "HEALTH": {
                "OUTCOME": "Set a more challenging fitness milestone",
                "PROCESS": "Establish a sustainable long-term health routine",
                "MILESTONE": "Participate in a competition or group challenge",
            },
            "PERSONAL": {
                "LEARNING": "Apply this learning to improve a life area",
                "OUTCOME": "Set a transformational personal development goal",
                "PROCESS": "Build a daily practice around this skill",
            },
            "BUSINESS": {
                "PROJECT": "Scale this project to reach more people",
                "OUTCOME": "Mentor others in this business area",
                "LEARNING": "Apply this knowledge to start a new venture",
            },
        }

        suggestion = domain_progressions.get(domain, {}).get(
            goal_type, "Set a more ambitious goal in this area"
        )

        return {
            "title": f"Next Level: {domain.title()} Goal",
            "description": suggestion,
            "rationale": f"You've mastered a {domain.lower()} goal - time to level up!",
            "confidence": 0.85,
            "recommendation_type": "domain_progression",
            "suggested_domain": domain,
            "suggested_goal_type": goal_type,
        }

    def _recommend_knowledge_expansion(self, knowledge_units: list[dict]) -> dict | None:
        """Recommend a goal that applies mastered knowledge in a new context."""
        # FUTURE-IMPL-002: See docs/reference/PLACEHOLDER_INDEX.md § E2
        knowledge_units = [ku for ku in knowledge_units if ku.get("uid") is not None]
        if not knowledge_units:
            return None

        ku_titles = ", ".join([ku["title"] for ku in knowledge_units[:3]])

        return {
            "title": "Apply Your Knowledge",
            "description": f"Create a project or goal that applies: {ku_titles}",
            "rationale": "You've learned these concepts - now make something with them!",
            "confidence": 0.80,
            "recommendation_type": "knowledge_expansion",
            "related_knowledge": [ku["uid"] for ku in knowledge_units],
            # FUTURE-IMPL-004: See docs/reference/PLACEHOLDER_INDEX.md § E2
        }

    def _recommend_habit_reinforcement(self, habits: list[dict]) -> dict | None:
        """Recommend a goal that leverages established habits."""
        # FUTURE-IMPL-006: See docs/reference/PLACEHOLDER_INDEX.md § E2
        habits = [h for h in habits if h.get("uid") is not None]
        if not habits:
            return None

        habit_titles = ", ".join([h["title"] for h in habits[:2]])

        return {
            "title": "Leverage Your Habits",
            "description": f"Your established habits ({habit_titles}) can support a bigger goal",
            "rationale": "You've built strong habits - use them to achieve something greater!",
            "confidence": 0.75,
            "recommendation_type": "habit_reinforcement",
            "related_habits": [h["uid"] for h in habits],
        }

    def _recommend_principle_alignment(self, principles: list[dict]) -> dict | None:
        """Recommend a goal aligned with guiding principles."""
        principles = [p for p in principles if p.get("uid") is not None]
        if not principles:
            return None

        principle_titles = ", ".join([p["title"] for p in principles[:2]])

        return {
            "title": "Stay Aligned with Your Principles",
            "description": f"Set a goal that furthers: {principle_titles}",
            "rationale": "Your principles guided this success - let them guide your next goal!",
            "confidence": 0.90,
            "recommendation_type": "principle_alignment",
            "related_principles": [p["uid"] for p in principles],
        }

    async def _check_principle_alignment(self, event: GoalAchieved) -> None:
        """Check if achieved goal is aligned with any principles.

        Generates cross-domain insight when goal achievement contributes
        to principle alignment.
        """
        if not self.relationships:
            return

        # "principles" is the Goal→Principle config key (GUIDED_BY_PRINCIPLE); the service
        # takes a method_key, not a raw RelationshipName.value (never matched → empty).
        aligned_result = await self.relationships.get_related_uids(
            "principles", EntityUID(event.goal_uid)
        )
        if aligned_result.is_ok and aligned_result.value:
            principle_uids = aligned_result.value
            self.logger.info(
                f"Achieved goal aligned with {len(principle_uids)} principle(s)",
                extra={
                    "goal_uid": event.goal_uid,
                    "user_uid": event.user_uid,
                    "principle_uids": principle_uids[:5],
                    "event_type": "goal.achievement.principle_alignment",
                },
            )

            # Persist principle alignment insight (parity with the Task handler)
            await persist_principle_alignment_insight(
                self.insight_store,
                self.logger,
                user_uid=event.user_uid,
                entity_uid=EntityUID(event.goal_uid),
                domain="goals",
                title="Goal Aligned with Principles",
                description=f"Achieved goal contributes to {len(principle_uids)} principle(s).",
                principle_uids=principle_uids,
            )
