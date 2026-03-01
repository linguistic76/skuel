"""
Domain Planning Mixin
=====================

Domain-specific UserContext-aware planning methods for each Activity Domain.
Called by DailyPlanningMixin in UserContextIntelligence.

Provides:
    get_at_risk_habits_for_user: Habits with streaks at risk of breaking
    get_upcoming_events_for_user: Events scheduled for today and near future
    get_actionable_tasks_for_user: Tasks user can start immediately
    get_advancing_goals_for_user: Goals ready for progress advancement
    get_pending_decisions_for_user: Choices awaiting resolution
    get_aligned_principles_for_user: Principles aligned with user's active focus

Requires on concrete class:
    config, logger (set by UnifiedRelationshipService.__init__)
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from core.utils.decorators import with_error_handling
from core.utils.result_simplified import Result
from core.utils.sort_functions import (
    get_core_and_alignment,
    get_days_until_and_priority,
    get_overdue_and_priority,
    get_priority_score,
    get_risk_progress_priority,
    get_streak_and_priority,
)

if TYPE_CHECKING:
    from core.models.relationship_registry import DomainRelationshipConfig
    from core.services.user.unified_user_context import UserContext


class DomainPlanningMixin:
    """
    Mixin providing domain-specific UserContext-aware planning methods.

    Each method is tailored to one Activity Domain and returns typed
    Contextual* objects consumed by DailyPlanningMixin in UserContextIntelligence.

    Requires on concrete class:
        config: DomainRelationshipConfig
        logger: Logger instance
    """

    # Provided by UnifiedRelationshipService.__init__ — declared for mypy
    config: DomainRelationshipConfig
    logger: Any

    # =========================================================================
    # DOMAIN-SPECIFIC PLANNING METHODS
    # Called by DailyPlanningMixin in UserContextIntelligence.
    # Each returns domain-specific contextual entities.
    # =========================================================================

    @with_error_handling("get_at_risk_habits_for_user", error_type="database")
    async def get_at_risk_habits_for_user(
        self,
        context: UserContext,
        limit: int = 10,
    ) -> Result[list[Any]]:
        """
        Get habits with streaks at risk of breaking.

        Context Fields Used:
        - at_risk_habits: UIDs of habits at risk
        - active_habits_rich: Rich habit data with context

        Returns:
            Result[list[ContextualHabit]] - habits needing attention
        """
        from core.models.context_types import ContextualHabit

        at_risk_uids = set(getattr(context, "at_risk_habits", []) or [])
        rich_habits = getattr(context, "active_habits_rich", []) or []

        contextual_habits = []
        for habit_data in rich_habits:
            habit_dict = habit_data.get("habit", {})
            uid = habit_dict.get("uid")
            if not uid or uid not in at_risk_uids:
                continue

            contextual = ContextualHabit.from_entity_and_context(
                uid=uid,
                title=habit_dict.get("title", ""),
                context=context,
                current_streak=habit_dict.get("current_streak", 0),
                days_since_last=habit_dict.get("days_since_last", 0),
                readiness_override=1.0,
                relevance_override=0.9,
                priority_override=0.95,
            )
            contextual_habits.append(contextual)

        contextual_habits.sort(key=get_streak_and_priority, reverse=True)

        return Result.ok(contextual_habits[:limit])

    @with_error_handling("get_upcoming_events_for_user", error_type="database")
    async def get_upcoming_events_for_user(
        self,
        context: UserContext,
        limit: int = 10,
    ) -> Result[list[Any]]:
        """
        Get upcoming events for today and near future.

        Context Fields Used:
        - today_event_uids: Events scheduled for today
        - upcoming_event_uids: Events scheduled for near future
        - active_events_rich: Rich event data with context

        Returns:
            Result[list[ContextualEvent]] - upcoming events
        """
        from core.models.context_types import ContextualEvent

        today_uids = set(getattr(context, "today_event_uids", []) or [])
        upcoming_uids = set(getattr(context, "upcoming_event_uids", []) or [])
        all_event_uids = today_uids | upcoming_uids
        rich_events = getattr(context, "active_events_rich", []) or []

        contextual_events = []
        for event_data in rich_events:
            event_dict = event_data.get("event", {})
            uid = event_dict.get("uid")
            if not uid or uid not in all_event_uids:
                continue

            is_today = uid in today_uids
            days_until = 0 if is_today else event_dict.get("days_until", 1)
            contextual = ContextualEvent.from_entity_and_context(
                uid=uid,
                title=event_dict.get("title", ""),
                _context=context,
                days_until=days_until,
                duration_minutes=event_dict.get("duration_minutes", 30),
            )
            contextual_events.append(contextual)

        contextual_events.sort(key=get_days_until_and_priority)

        return Result.ok(contextual_events[:limit])

    @with_error_handling("get_actionable_tasks_for_user", error_type="database")
    async def get_actionable_tasks_for_user(
        self,
        context: UserContext,
        limit: int = 10,
    ) -> Result[list[Any]]:
        """
        Get tasks user can start immediately, ranked by priority.

        Context Fields Used:
        - active_tasks_rich: Rich task data with graph_context
        - overdue_task_uids: Overdue tasks (urgency boost)
        - knowledge_mastery: Knowledge mastery levels

        Returns:
            Result[list[ContextualTask]] - actionable tasks sorted by priority
        """
        from core.models.context_types import ContextualTask

        rich_tasks = getattr(context, "active_tasks_rich", []) or []
        overdue_uids = set(getattr(context, "overdue_task_uids", []) or [])
        mastery = getattr(context, "knowledge_mastery", {}) or {}

        contextual_tasks = []
        for task_data in rich_tasks:
            task_dict = task_data.get("task", {})
            uid = task_dict.get("uid")
            if not uid:
                continue

            graph_ctx = task_data.get("graph_context", {})

            # Check knowledge prerequisites
            knowledge_uids = [
                k.get("uid") for k in graph_ctx.get("applied_knowledge", []) if k.get("uid")
            ]
            prereq_met = (
                all(mastery.get(k, 0) >= 0.7 for k in knowledge_uids) if knowledge_uids else True
            )

            # Check task prerequisites
            prereq_tasks = [t.get("uid") for t in graph_ctx.get("dependencies", []) if t.get("uid")]
            completed_tasks = set(getattr(context, "completed_task_uids", []) or [])
            tasks_met = all(t in completed_tasks for t in prereq_tasks) if prereq_tasks else True

            if not prereq_met or not tasks_met:
                continue  # Not actionable

            is_overdue = uid in overdue_uids
            priority = task_dict.get("priority", "medium")
            priority_scores = {"urgent": 0.3, "high": 0.2, "medium": 0.1, "low": 0.0}
            base_priority = 0.5 + priority_scores.get(str(priority).lower(), 0.1)
            overdue_boost = 0.3 if is_overdue else 0

            contextual = ContextualTask.from_entity_and_context(
                uid=uid,
                title=task_dict.get("title", ""),
                context=context,
                prerequisite_knowledge=knowledge_uids,
                prerequisite_tasks=prereq_tasks,
                readiness_override=1.0,  # Passed all checks above
                relevance_override=0.7,
                priority_override=min(1.0, base_priority + overdue_boost),
            )
            contextual_tasks.append(contextual)

        contextual_tasks.sort(key=get_overdue_and_priority, reverse=True)

        return Result.ok(contextual_tasks[:limit])

    @with_error_handling("get_advancing_goals_for_user", error_type="database")
    async def get_advancing_goals_for_user(
        self,
        context: UserContext,
        limit: int = 10,
    ) -> Result[list[Any]]:
        """
        Get goals ready for progress advancement.

        Context Fields Used:
        - active_goal_uids: User's active goals
        - active_goals_rich: Rich goal data with context
        - at_risk_goals: Goals at risk (deprioritize)

        Returns:
            Result[list[ContextualGoal]] - goals to advance
        """
        from core.models.context_types import ContextualGoal

        active_goal_uids = set(getattr(context, "active_goal_uids", []) or [])
        rich_goals = getattr(context, "active_goals_rich", []) or []
        at_risk_uids = set(getattr(context, "at_risk_goals", []) or [])
        stalled_uids = set(context.get_stalled_goals())

        contextual_goals = []
        for goal_data in rich_goals:
            goal_dict = goal_data.get("goal", {})
            uid = goal_dict.get("uid")
            if not uid or uid not in active_goal_uids:
                continue

            if uid in stalled_uids:
                continue

            is_at_risk = uid in at_risk_uids
            progress = goal_dict.get("progress", 0.0)

            contextual = ContextualGoal.from_entity_and_context(
                uid=uid,
                title=goal_dict.get("title", ""),
                context=context,
                readiness_override=0.9 if not is_at_risk else 0.6,
                relevance_override=0.8,
                priority_override=0.7 + (progress * 0.2),
            )
            contextual_goals.append(contextual)

        contextual_goals.sort(key=get_risk_progress_priority, reverse=True)

        return Result.ok(contextual_goals[:limit])

    @with_error_handling("get_pending_decisions_for_user", error_type="database")
    async def get_pending_decisions_for_user(
        self,
        context: UserContext,
        limit: int = 10,
    ) -> Result[list[Any]]:
        """
        Get choices/decisions awaiting resolution.

        Context Fields Used:
        - pending_choice_uids: Pending choices
        - recent_choices_rich: Rich choice data with context

        Returns:
            Result[list[ContextualChoice]] - pending decisions
        """
        from core.models.context_types import ContextualChoice

        pending_uids = set(getattr(context, "pending_choice_uids", []) or [])
        rich_choices = getattr(context, "recent_choices_rich", []) or []

        contextual_choices = []
        for choice_data in rich_choices:
            choice_dict = choice_data.get("choice", {})
            uid = choice_dict.get("uid")
            if not uid or uid not in pending_uids:
                continue

            priority_level = str(choice_dict.get("priority", "medium")).lower()
            contextual = ContextualChoice.from_entity_and_context(
                uid=uid,
                title=choice_dict.get("title", ""),
                context=context,
                priority_level=priority_level,
            )
            contextual_choices.append(contextual)

        contextual_choices.sort(key=get_priority_score, reverse=True)

        return Result.ok(contextual_choices[:limit])

    @with_error_handling("get_aligned_principles_for_user", error_type="database")
    async def get_aligned_principles_for_user(
        self,
        context: UserContext,
        limit: int = 10,
    ) -> Result[list[Any]]:
        """
        Get principles aligned with user's active focus.

        Context Fields Used:
        - core_principle_uids: Core principles
        - core_principles_rich: Rich principle data with context

        Returns:
            Result[list[ContextualPrinciple]] - aligned principles
        """
        from core.models.context_types import ContextualPrinciple

        rich_principles = getattr(context, "core_principles_rich", []) or []

        contextual_principles = []
        for principle_data in rich_principles:
            principle_dict = principle_data.get("principle", {})
            uid = principle_dict.get("uid")
            if not uid:
                continue

            alignment = principle_dict.get("alignment_score", 0.5)
            contextual = ContextualPrinciple.from_entity_and_context(
                uid=uid,
                title=principle_dict.get("title", ""),
                context=context,
                alignment_score=alignment,
            )
            contextual_principles.append(contextual)

        contextual_principles.sort(key=get_core_and_alignment, reverse=True)

        return Result.ok(contextual_principles[:limit])
