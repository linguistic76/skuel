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
- _calculate_attention_score: Check reflection frequency and alignment trends
- _identify_attention_reasons: Why principle needs attention
- _suggest_attention_action: Actionable recommendation
"""

from __future__ import annotations

from datetime import date
from typing import TYPE_CHECKING, Any

from core.models.principle.principle import Principle
from core.ports.domain_protocols import PrinciplesOperations
from core.services.base_planning_service import BasePlanningService
from core.utils.decorators import with_error_handling
from core.utils.result_simplified import Result

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
    - set_relationship_service() for post-construction wiring
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

        Returns dict of principle_uid -> {name, alignment, last_reflection, etc.}
        """
        data: dict[str, dict[str, Any]] = {}

        for rich_principle in context.entities_rich.get("principles", []):
            principle_dict = rich_principle.get("entity", {})
            graph_ctx = rich_principle.get("graph_context", {})

            uid = principle_dict.get("uid")
            if not uid:
                continue

            data[uid] = {
                "name": principle_dict.get("name", "Unknown"),
                "statement": principle_dict.get("statement", ""),
                "strength": principle_dict.get("strength", "MODERATE"),
                "current_alignment": principle_dict.get("current_alignment", "UNKNOWN"),
                "last_review_date": principle_dict.get("last_review_date"),
                "graph_context": graph_ctx,
            }

        return data

    def _extract_principles_for_activities(
        self, context: UserContext
    ) -> tuple[dict[str, list[str]], dict[str, list[str]], dict[str, list[str]]]:
        """
        Extract principle-activity mappings from rich context.

        Returns:
            (principles_for_task, principles_for_event, principles_for_goal)
        """
        principles_for_task: dict[str, list[str]] = {}
        principles_for_event: dict[str, list[str]] = {}
        principles_for_goal: dict[str, list[str]] = {}

        # Extract from entities_rich["tasks"]
        for task_data in context.entities_rich.get("tasks", []):
            task_dict = task_data.get("entity", {})
            graph_ctx = task_data.get("graph_context", {})
            task_uid = task_dict.get("uid")

            if task_uid:
                guiding_principles = graph_ctx.get("guiding_principles", [])
                principle_uids = [p.get("uid") for p in guiding_principles if p.get("uid")]
                if principle_uids:
                    principles_for_task[task_uid] = principle_uids

        # Extract from entities_rich["events"]
        for event_data in context.entities_rich.get("events", []):
            event_dict = event_data.get("entity", {})
            graph_ctx = event_data.get("graph_context", {})
            event_uid = event_dict.get("uid")

            if event_uid:
                guiding_principles = graph_ctx.get("guiding_principles", [])
                principle_uids = [p.get("uid") for p in guiding_principles if p.get("uid")]
                if principle_uids:
                    principles_for_event[event_uid] = principle_uids

        # Extract from entities_rich["goals"]
        for goal_data in context.entities_rich.get("goals", []):
            goal_dict = goal_data.get("entity", {})
            graph_ctx = goal_data.get("graph_context", {})
            goal_uid = goal_dict.get("uid")

            if goal_uid:
                aligned_principles = graph_ctx.get("aligned_principles", [])
                principle_uids = [p.get("uid") for p in aligned_principles if p.get("uid")]
                if principle_uids:
                    principles_for_goal[goal_uid] = principle_uids

        return principles_for_task, principles_for_event, principles_for_goal

    def _get_activity_titles(self, context: UserContext) -> tuple[dict[str, str], dict[str, str]]:
        """Extract task and event titles from rich context."""
        task_titles: dict[str, str] = {}
        event_titles: dict[str, str] = {}

        for task_data in context.entities_rich.get("tasks", []):
            task_dict = task_data.get("entity", {})
            uid = task_dict.get("uid")
            title = task_dict.get("title", "Unknown Task")
            if uid:
                task_titles[uid] = title

        for event_data in context.entities_rich.get("events", []):
            event_dict = event_data.get("entity", {})
            uid = event_dict.get("uid")
            title = event_dict.get("title", "Unknown Event")
            if uid:
                event_titles[uid] = title

        return task_titles, event_titles

    # ========================================================================
    # CONTEXT-FIRST METHODS
    # ========================================================================

    @with_error_handling("get_principles_needing_attention_for_user", error_type="database")
    async def get_principles_needing_attention_for_user(
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
        today = date.today()
        attention_threshold_days = 14

        # Process each core principle
        for principle_uid in context.core_principle_uids:
            data = principle_data.get(principle_uid, {})
            name = data.get("name", "Unknown")

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

            # Determine trend from priorities (higher priority with low alignment = needs attention)
            priority = context.principle_priorities.get(principle_uid, 0.5)
            alignment_trend = "stable"
            if priority > 0.7 and alignment_score < 0.5:
                alignment_trend = "declining"  # High priority but low alignment
            elif alignment_score > 0.7:
                alignment_trend = "improving"

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
                attention_threshold_days=attention_threshold_days,
            )

            contextual = ContextualPrinciple.from_entity_and_context(
                uid=principle_uid,
                title=name,
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
    async def get_contextual_principles_for_user(
        self,
        context: UserContext,
        limit: int = 3,
    ) -> Result[list[ContextualPrinciple]]:
        """
        Get principles relevant to today's activities.

        **Philosophy:** "Connect daily actions to core values"

        Returns principles that:
        1. Are linked to today's tasks/goals/events
        2. Could guide today's planned activities
        3. Have alignment opportunities in scheduled activities

        **Context Fields Used:**
        - todays_task_uids: Tasks scheduled for today
        - todays_event_uids: Events scheduled for today
        - active_goal_uids: Current active goals
        - Rich context for relationship extraction

        Args:
            context: User's complete context
            limit: Maximum principles to return

        Returns:
            Principles relevant to today, with practice opportunities
        """
        from core.models.context_types import ContextualPrinciple

        # Extract mappings from rich context
        principles_for_task, principles_for_event, principles_for_goal = (
            self._extract_principles_for_activities(context)
        )
        principle_data = self._extract_principle_data_from_rich_context(context)

        relevant_principles: dict[str, float] = {}

        # Get today's UIDs
        todays_task_uids = set(getattr(context, "todays_task_uids", []))
        todays_event_uids = set(getattr(context, "todays_event_uids", []))
        active_goal_uids = set(context.active_goal_uids)

        # Check principles linked to today's tasks
        for task_uid in todays_task_uids:
            for principle_uid in principles_for_task.get(task_uid, []):
                relevance = relevant_principles.get(principle_uid, 0.0)
                relevant_principles[principle_uid] = relevance + 0.3

        # Check principles linked to today's events
        for event_uid in todays_event_uids:
            for principle_uid in principles_for_event.get(event_uid, []):
                relevance = relevant_principles.get(principle_uid, 0.0)
                relevant_principles[principle_uid] = relevance + 0.25

        # Check principles linked to active goals
        for goal_uid in active_goal_uids:
            for principle_uid in principles_for_goal.get(goal_uid, []):
                relevance = relevant_principles.get(principle_uid, 0.0)
                relevant_principles[principle_uid] = relevance + 0.2

        # Boost core principles
        for principle_uid in context.core_principle_uids:
            if principle_uid in relevant_principles:
                relevant_principles[principle_uid] *= 1.5

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
            connected_events = [
                e for e in todays_event_uids if principle_uid in principles_for_event.get(e, [])
            ]
            connected_goals = [
                g for g in active_goal_uids if principle_uid in principles_for_goal.get(g, [])
            ]

            # Build practice opportunity description
            practice_opportunity = self._describe_practice_opportunity(
                connected_tasks, connected_events
            )

            principle_name = data.get("name", "Unknown")
            contextual = ContextualPrinciple.from_entity_and_context(
                uid=principle_uid,
                title=principle_name,
                context=context,
                connected_task_uids=connected_tasks,
                connected_event_uids=connected_events,
                connected_goal_uids=connected_goals,
                practice_opportunity=practice_opportunity,
                relevance_override=min(1.0, relevance),
            )
            result.append(contextual)

        self.logger.info(f"Found {len(result)} contextual principles for today's activities")

        return Result.ok(result)

    @with_error_handling("get_principle_practice_opportunities_for_user", error_type="database")
    async def get_principle_practice_opportunities_for_user(
        self,
        context: UserContext,
        principle_uid: str | None = None,
        limit: int = 5,
    ) -> Result[list[PracticeOpportunity]]:
        """
        Find activities that could strengthen principle alignment.

        **Philosophy:** "Every activity is a chance to live your principles"

        For a specific principle (or all if none specified), finds:
        1. Tasks that could embody this principle
        2. Upcoming events with principle practice potential
        3. Goals that align with principle values

        Args:
            context: User's complete context
            principle_uid: Optional specific principle to find opportunities for
            limit: Maximum opportunities to return

        Returns:
            List of practice opportunities with guidance
        """
        from core.models.context_types import PracticeOpportunity

        # Extract mappings
        principles_for_task, principles_for_event, _ = self._extract_principles_for_activities(
            context
        )
        principle_data = self._extract_principle_data_from_rich_context(context)
        task_titles, event_titles = self._get_activity_titles(context)

        opportunities: list[PracticeOpportunity] = []
        target_principles = [principle_uid] if principle_uid else list(context.core_principle_uids)

        # Get today's UIDs
        todays_task_uids = set(getattr(context, "todays_task_uids", []))
        todays_event_uids = set(getattr(context, "todays_event_uids", []))

        for p_uid in target_principles:
            data = principle_data.get(p_uid, {})
            p_name = data.get("name", "Unknown")

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

            # Find events that align with this principle
            for event_uid in todays_event_uids:
                event_principles = principles_for_event.get(event_uid, [])
                if p_uid in event_principles:
                    opportunity = PracticeOpportunity(
                        principle_uid=p_uid,
                        principle_name=p_name,
                        activity_type="event",
                        activity_uid=event_uid,
                        activity_title=event_titles.get(event_uid, "Unknown Event"),
                        opportunity_type="direct_alignment",
                        guidance="This event offers a chance to practice your principle in action.",
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
        """Convert AlignmentLevel string to numeric score."""
        mapping = {
            "ALIGNED": 1.0,
            "MOSTLY_ALIGNED": 0.75,
            "PARTIAL": 0.5,
            "MISALIGNED": 0.25,
            "UNKNOWN": 0.5,
        }
        return mapping.get(alignment_str.upper(), 0.5)

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
        attention_threshold_days: int = 14,
        max_reasons: int = 3,
    ) -> list[str]:
        """Identify specific reasons why principle needs attention."""
        reasons: list[str] = []

        if days_since_reflection > attention_threshold_days:
            reasons.append(f"No reflection in {days_since_reflection} days")

        if alignment_score < 0.5:
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
    def _describe_practice_opportunity(
        connected_tasks: list[str],
        connected_events: list[str],
    ) -> str:
        """Generate a description of the practice opportunity."""
        parts = []

        if connected_tasks:
            task_count = len(connected_tasks)
            parts.append(f"{task_count} task{'s' if task_count > 1 else ''} today")

        if connected_events:
            event_count = len(connected_events)
            parts.append(f"{event_count} event{'s' if event_count > 1 else ''} today")

        if parts:
            return f"Connected to {' and '.join(parts)}"

        return "No direct connections to today's activities"
