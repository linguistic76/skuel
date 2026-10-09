"""
Principles Planning Service - Context-First User Planning
=========================================================

Follows TasksPlanningService pattern (December 2025).

**Purpose:** Context-aware planning methods that leverage UserContext (~240 fields)
to provide personalized, filtered, and ranked principle queries.

**Pattern:** Context-First - "Filter by attention needed, rank by relevance, enrich with insights"

**Methods:**
- get_principles_needing_attention_for_user: Principles that need review/practice
- get_contextual_principles_for_user: Principles relevant to today's activities
- get_principle_practice_opportunities_for_user: Activities that strengthen alignment

**Static Helpers:**
- _alignment_trend: Rise / fall / hold across the last two dated assessments
- _calculate_attention_score: Check reflection frequency and alignment trends
- _identify_attention_reasons: Why principle needs attention
- _suggest_attention_action: Actionable recommendation
"""

from __future__ import annotations

import json
from datetime import date
from typing import TYPE_CHECKING, Any

from core.models.enums.principle_enums import AlignmentLevel, PrincipleStrength
from core.models.principle.principle import Principle
from core.ports.domain_protocols import PrinciplesOperations
from core.services.base_planning_service import BasePlanningService
from core.utils.decorators import with_error_handling
from core.utils.result_simplified import Result
from core.utils.timestamp_helpers import today_in
from core.utils.zone_context import current_zone

if TYPE_CHECKING:
    from core.models.context_types import ContextualPrinciple, PracticeOpportunity
    from core.services.user.unified_user_context import UserContext


class PrinciplesPlanningService(BasePlanningService[PrinciplesOperations, Principle]):
    """
    Context-aware principle planning service.

    Provides personalized principle recommendations based on user context.
    All methods use UserContext (~240 fields) for filtering and ranking.

    **Naming Convention:** *_for_user() suffix indicates context-awareness

    Inherits from BasePlanningService:
    - Constructor with backend + relationship_service
    - _get_entities_by_uids() for batch entity fetching
    - _get_related_uids() for relationship queries
    """

    _domain_name = "Principles"

    # ========================================================================
    # PRIVATE HELPER METHODS
    # ========================================================================

    def _extract_principle_data_from_rich_context(
        self, context: UserContext
    ) -> dict[str, dict[str, Any]]:
        """
        Extract principle data from entities_rich["principles"].

        Returns dict of principle_uid -> {title, alignment, last_reflection, etc.}
        """
        data: dict[str, dict[str, Any]] = {}

        for rich_principle in context.entities_rich.get("principles", []):
            principle_dict = rich_principle.get("entity", {})
            graph_ctx = rich_principle.get("graph_context", {})

            uid = principle_dict.get("uid")
            if not uid:
                continue

            data[uid] = {
                "title": principle_dict.get("title", "Unknown"),
                "statement": principle_dict.get("statement", ""),
                "strength": principle_dict.get("strength", "MODERATE"),
                "current_alignment": principle_dict.get("current_alignment", "UNKNOWN"),
                "last_review_date": principle_dict.get("last_review_date"),
                "alignment_history": principle_dict.get("alignment_history"),
                "graph_context": graph_ctx,
            }

        return data

    def _get_task_titles(self, context: UserContext) -> dict[str, str]:
        """Extract task titles from rich context."""
        task_titles: dict[str, str] = {}
        for task_data in context.entities_rich.get("tasks", []):
            task_dict = task_data.get("entity", {})
            uid = task_dict.get("uid")
            if uid:
                task_titles[uid] = task_dict.get("title", "Unknown Task")
        return task_titles

    # ========================================================================
    # CONTEXT-FIRST METHODS
    # ========================================================================

    @with_error_handling("get_principles_needing_attention_for_user", error_type="database")
    async def get_principles_needing_attention_for_user(  # skuel-lint: disable=SKUEL029 -- facade-delegated: service facade awaits this via delegation (facade uniformity)
        self,
        context: UserContext,
        limit: int = 5,
    ) -> Result[list[ContextualPrinciple]]:
        """
        Get principles that need attention, ranked by urgency.

        **Philosophy:** "Principles need regular reflection to stay alive"

        Returns principles that:
        1. Haven't been reflected on recently (> 14 days)
        2. Show low alignment scores
        3. Are CORE/STRONG but underengaged

        **Context Fields Used:**
        - core_principle_uids: User's stated core principles
        - entities_rich["principles"]: Rich principle data with graph context

        Args:
            context: User's complete context (~240 fields)
            limit: Maximum principles to return

        Returns:
            Result[list[ContextualPrinciple]] - sorted by attention urgency
        """
        from core.models.context_types import ContextualPrinciple

        # Extract principle data from rich context
        principle_data = self._extract_principle_data_from_rich_context(context)

        if not principle_data and not context.core_principle_uids:
            return Result.ok([])

        needing_attention: list[ContextualPrinciple] = []
        today = today_in(current_zone())
        attention_threshold_days = 14

        # Process each core principle
        for principle_uid in context.core_principle_uids:
            data = principle_data.get(principle_uid, {})
            title = data.get("title", "Unknown")

            # Calculate days since last review
            last_review = data.get("last_review_date")
            if isinstance(last_review, str):
                try:
                    last_review = date.fromisoformat(last_review)
                except ValueError:
                    last_review = None

            days_since_reflection = (today - last_review).days if last_review else 999

            # Get alignment info
            alignment_str = data.get("current_alignment", "UNKNOWN")
            alignment_score = self._alignment_level_to_score(alignment_str)

            # The trend is read off the user's own dated assessments; how deeply the
            # principle is held is its own reason, never a trend.
            alignment_trend = self._alignment_trend(data.get("alignment_history"))
            deeply_held = (
                context.principle_priorities.get(
                    principle_uid, PrincipleStrength.MODERATE.importance()
                )
                > 0.7
            )

            # Calculate attention score
            attention_score = self._calculate_attention_score(
                days_since_reflection=days_since_reflection,
                alignment_score=alignment_score,
                alignment_trend=alignment_trend,
                attention_threshold_days=attention_threshold_days,
            )

            # Skip if attention score below threshold
            if attention_score < 0.3:
                continue

            # Identify reasons
            reasons = self._identify_attention_reasons(
                days_since_reflection=days_since_reflection,
                alignment_score=alignment_score,
                alignment_trend=alignment_trend,
                deeply_held=deeply_held,
                attention_threshold_days=attention_threshold_days,
            )

            contextual = ContextualPrinciple.from_entity_and_context(
                uid=principle_uid,
                title=title,
                context=context,
                alignment_score=alignment_score,
                days_since_reflection=days_since_reflection,
                alignment_trend=alignment_trend,
                attention_reasons=reasons,
                suggested_action=self._suggest_attention_action(reasons),
                priority_override=attention_score,
            )
            needing_attention.append(contextual)

        # Sort by attention score (highest = most urgent)
        def get_attention_score(p: ContextualPrinciple) -> float:
            """Get attention score for sorting."""
            return p.attention_score

        needing_attention.sort(key=get_attention_score, reverse=True)

        self.logger.info(
            f"Found {len(needing_attention)} principles needing attention "
            f"(from {len(context.core_principle_uids)} core principles)"
        )

        return Result.ok(needing_attention[:limit])

    @with_error_handling("get_contextual_principles_for_user", error_type="database")
    async def get_contextual_principles_for_user(  # skuel-lint: disable=SKUEL029 -- facade-delegated: service facade awaits this via delegation (facade uniformity)
        self,
        context: UserContext,
        limit: int = 3,
    ) -> Result[list[ContextualPrinciple]]:
        """
        Get principles relevant to today's activities.

        **Philosophy:** "Connect daily actions to core values"

        Returns the user's active principles linked to today's tasks or to an
        active goal, weighted by how deeply the user holds each one.

        **Context Fields Used (rich build):**
        - principles_by_task / principles_by_goal: each task / goal -> its active
          principles (``ALIGNED_WITH_PRINCIPLE`` / ``SUPPORTS_GOAL``)
        - today_task_uids: Tasks due today
        - active_goal_uids: Current active goals
        - principle_priorities: How deeply each principle is held

        Args:
            context: User's complete context
            limit: Maximum principles to return

        Returns:
            Principles relevant to today, with practice opportunities
        """
        from core.models.context_types import ContextualPrinciple

        principles_for_task = context.principles_by_task
        principles_for_goal = context.principles_by_goal
        principle_data = self._extract_principle_data_from_rich_context(context)

        relevant_principles: dict[str, float] = {}

        todays_task_uids = set(context.today_task_uids)
        active_goal_uids = set(context.active_goal_uids)

        # Check principles linked to today's tasks
        for task_uid in todays_task_uids:
            for principle_uid in principles_for_task.get(task_uid, []):
                relevance = relevant_principles.get(principle_uid, 0.0)
                relevant_principles[principle_uid] = relevance + 0.3

        # Check principles linked to active goals
        for goal_uid in active_goal_uids:
            for principle_uid in principles_for_goal.get(goal_uid, []):
                relevance = relevant_principles.get(principle_uid, 0.0)
                relevant_principles[principle_uid] = relevance + 0.2

        # Weigh each by how deeply it is held (CORE x1.5 ... EXPLORING x0.7)
        unset = PrincipleStrength.MODERATE.importance()
        for principle_uid in relevant_principles:
            relevant_principles[principle_uid] *= 0.5 + context.principle_priorities.get(
                principle_uid, unset
            )

        # Build result list
        result: list[ContextualPrinciple] = []

        def get_relevance_value(item: tuple[str, float]) -> float:
            """Get relevance value for sorting principle items."""
            return item[1]

        sorted_principles = sorted(
            relevant_principles.items(), key=get_relevance_value, reverse=True
        )

        for principle_uid, relevance in sorted_principles[:limit]:
            data = principle_data.get(principle_uid, {})

            # Get connected activities
            connected_tasks = [
                t for t in todays_task_uids if principle_uid in principles_for_task.get(t, [])
            ]
            connected_goals = [
                g for g in active_goal_uids if principle_uid in principles_for_goal.get(g, [])
            ]

            contextual = ContextualPrinciple.from_entity_and_context(
                uid=principle_uid,
                title=data.get("title", "Unknown"),
                context=context,
                connected_task_uids=connected_tasks,
                connected_goal_uids=connected_goals,
                practice_opportunity=self._describe_practice_opportunity(connected_tasks),
                relevance_override=min(1.0, relevance),
            )
            result.append(contextual)

        self.logger.info(f"Found {len(result)} contextual principles for today's activities")

        return Result.ok(result)

    @with_error_handling("get_principle_practice_opportunities_for_user", error_type="database")
    async def get_principle_practice_opportunities_for_user(  # skuel-lint: disable=SKUEL029 -- facade-delegated: service facade awaits this via delegation (facade uniformity)
        self,
        context: UserContext,
        principle_uid: str | None = None,
        limit: int = 5,
    ) -> Result[list[PracticeOpportunity]]:
        """
        Find activities that could strengthen principle alignment.

        **Philosophy:** "Every activity is a chance to live your principles"

        For a specific principle (or every active principle if none specified),
        finds today's tasks aligned with it (``principles_by_task``).

        Args:
            context: User's complete context
            principle_uid: Optional specific principle to find opportunities for
            limit: Maximum opportunities to return

        Returns:
            List of practice opportunities with guidance
        """
        from core.models.context_types import PracticeOpportunity

        principles_for_task = context.principles_by_task
        principle_data = self._extract_principle_data_from_rich_context(context)
        task_titles = self._get_task_titles(context)

        opportunities: list[PracticeOpportunity] = []
        target_principles = [principle_uid] if principle_uid else list(context.core_principle_uids)

        todays_task_uids = set(context.today_task_uids)

        for p_uid in target_principles:
            data = principle_data.get(p_uid, {})
            p_name = data.get("title", "Unknown")

            # Find tasks that align with this principle
            for task_uid in todays_task_uids:
                task_principles = principles_for_task.get(task_uid, [])
                if p_uid in task_principles:
                    opportunity = PracticeOpportunity(
                        principle_uid=p_uid,
                        principle_name=p_name,
                        activity_type="task",
                        activity_uid=task_uid,
                        activity_title=task_titles.get(task_uid, "Unknown Task"),
                        opportunity_type="direct_alignment",
                        guidance="This task directly embodies your principle. Focus on the 'why' as you work.",
                    )
                    opportunities.append(opportunity)

        # Sort by alignment weakness (lower alignment = higher priority for practice)
        def get_alignment_priority(opp: PracticeOpportunity) -> float:
            """Lower alignment = higher priority for practice."""
            data = principle_data.get(opp.principle_uid, {})
            alignment_str = data.get("current_alignment", "UNKNOWN")
            alignment_score = self._alignment_level_to_score(alignment_str)
            return 1.0 - alignment_score

        opportunities.sort(key=get_alignment_priority, reverse=True)

        self.logger.info(f"Found {len(opportunities)} practice opportunities")

        return Result.ok(opportunities[:limit])

    # ========================================================================
    # STATIC HELPER METHODS
    # ========================================================================

    @staticmethod
    def _alignment_level_to_score(alignment_str: str) -> float:
        """Convert AlignmentLevel string to numeric score.

        Delegates to AlignmentLevel.to_score() — the single source of truth.
        """
        try:
            level = AlignmentLevel(alignment_str.lower())
        except ValueError:
            return 0.5
        return level.to_score()

    @staticmethod
    def _alignment_trend(raw_history: object) -> str:
        """Whether the user's last two dated assessments rose, fell or held.

        ``alignment_history`` is one JSON string on the node (``properties(n)``);
        an unreadable value, fewer than two assessed levels, or an equal pair is
        "stable".
        """
        if isinstance(raw_history, str):
            try:
                raw_history = json.loads(raw_history)
            except json.JSONDecodeError:
                return "stable"
        if not isinstance(raw_history, list):
            return "stable"
        scored: list[tuple[str, float]] = []
        for entry in raw_history:
            if not isinstance(entry, dict):
                continue
            try:
                level = AlignmentLevel(str(entry.get("alignment_level", "")).lower())
            except ValueError:
                continue
            if level is AlignmentLevel.UNKNOWN:
                continue
            scored.append((str(entry.get("assessed_date", "")), level.to_score()))
        if len(scored) < 2:
            return "stable"
        scored.sort()
        earlier, latest = scored[-2][1], scored[-1][1]
        if latest > earlier:
            return "improving"
        if latest < earlier:
            return "declining"
        return "stable"

    @staticmethod
    def _calculate_attention_score(
        days_since_reflection: int,
        alignment_score: float,
        alignment_trend: str,
        attention_threshold_days: int = 14,
    ) -> float:
        """
        Calculate how urgently a principle needs attention.

        Components:
        - Reflection gap (40%): Days since last reflection
        - Alignment weakness (35%): Low alignment score
        - Trend decline (25%): Declining alignment trend
        """
        # Reflection gap component (0-1)
        reflection_urgency = min(1.0, days_since_reflection / (attention_threshold_days * 2))

        # Alignment weakness component (0-1, inverted)
        alignment_weakness = 1.0 - alignment_score

        # Trend component
        trend_score = 0.0
        if alignment_trend == "declining":
            trend_score = 1.0
        elif alignment_trend == "stable":
            trend_score = 0.3
        # improving = 0.0

        return (reflection_urgency * 0.4) + (alignment_weakness * 0.35) + (trend_score * 0.25)

    @staticmethod
    def _identify_attention_reasons(
        days_since_reflection: int,
        alignment_score: float,
        alignment_trend: str,
        deeply_held: bool = False,
        attention_threshold_days: int = 14,
        max_reasons: int = 3,
    ) -> list[str]:
        """Identify specific reasons why principle needs attention."""
        reasons: list[str] = []

        if days_since_reflection > attention_threshold_days:
            reasons.append(f"No reflection in {days_since_reflection} days")

        if alignment_score < 0.5:
            if deeply_held:
                reasons.append(f"Deeply held, but low alignment ({alignment_score:.0%})")
            else:
                reasons.append(f"Low alignment score ({alignment_score:.0%})")

        if alignment_trend == "declining":
            reasons.append("Alignment trend is declining")

        return reasons[:max_reasons]

    @staticmethod
    def _suggest_attention_action(reasons: list[str]) -> str:
        """Suggest action based on attention reasons."""
        if not reasons:
            return "Principle is healthy - consider deepening practice"

        if any("No reflection" in r for r in reasons):
            return "Schedule time to reflect on this principle today"

        if any("Low alignment" in r for r in reasons):
            return "Identify one activity today that embodies this principle"

        if any("declining" in r for r in reasons):
            return "Review recent choices - what's pulling you away from this principle?"

        return "Consider how this principle applies to today's activities"

    @staticmethod
    def _describe_practice_opportunity(connected_tasks: list[str]) -> str:
        """Generate a description of the practice opportunity."""
        if connected_tasks:
            task_count = len(connected_tasks)
            return f"Connected to {task_count} task{'s' if task_count > 1 else ''} today"
        return "No direct connections to today's tasks"
