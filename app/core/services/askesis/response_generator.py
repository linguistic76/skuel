"""
Response Generator - Action and Response Generation
====================================================

Generates suggested actions and responses based on context and intent.
Extracted from QueryProcessor for single responsibility.

Responsibilities:
- Build LLM-friendly context from UserContext
- Generate suggested actions based on intent and context
- Generate context-aware responses

Architecture:
- Uses UserContext as primary input
- Uses QueryIntent for intent-specific logic
- Returns structured data for API responses

January 2026: Extracted from QueryProcessor as part of Askesis design improvement.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from core.constants import MasteryLevel
from core.models.query import QueryIntent
from core.utils.logging import get_logger

if TYPE_CHECKING:
    from core.services.user import UserContext

logger = get_logger(__name__)


class ResponseGenerator:
    """
    Generate actions and responses based on context and intent.

    This service handles response generation:
    - Build LLM-friendly context from UserContext
    - Generate suggested next actions
    - Generate context-aware responses

    Architecture:
    - Uses UserContext (~240 fields) as input
    - Uses QueryIntent for intent-specific logic
    - Returns structured dicts for API responses
    """

    def __init__(self) -> None:
        """Initialize response generator."""
        logger.info("ResponseGenerator initialized")

    def build_llm_context(self, user_context: UserContext, query: str) -> str:
        """
        Convert UserContext into LLM-friendly natural language.

        Intelligently selects relevant fields based on query keywords,
        building a rich context for the LLM to understand user's current state.

        Args:
            user_context: Complete user context with 240+ fields
            query: User's question (used for intelligent field selection)

        Returns:
            Natural language context string for LLM consumption
        """
        context_parts = []

        # Always include user identity
        context_parts.append(f"User: {user_context.username}")

        query_lower = query.lower()

        # Task context (if query mentions tasks/work)
        if any(word in query_lower for word in ["task", "work", "do", "complete", "todo"]):
            context_parts.append("\n--- Tasks ---")
            context_parts.append(f"Active Tasks: {len(user_context.active_task_uids)}")
            if user_context.overdue_task_uids:
                context_parts.append(f"Overdue: {len(user_context.overdue_task_uids)} tasks")
            if user_context.blocked_task_uids:
                context_parts.append(f"Blocked: {len(user_context.blocked_task_uids)} tasks")
            if user_context.today_task_uids:
                context_parts.append(f"Due Today: {len(user_context.today_task_uids)} tasks")

        # Knowledge context (if query mentions learning/knowledge)
        if any(word in query_lower for word in ["learn", "know", "study", "understand", "master"]):
            context_parts.append("\n--- Knowledge & Learning ---")
            mastery_avg = user_context.mastery_average
            context_parts.append(f"Average Mastery: {mastery_avg:.0%}")
            context_parts.append(
                f"Mastered: {len(user_context.mastered_knowledge_uids)} knowledge units"
            )
            context_parts.append(
                f"In Progress: {len(user_context.in_progress_knowledge_uids)} knowledge units"
            )

            if user_context.current_learning_path_uid:
                context_parts.append(
                    f"Current Learning Path: {user_context.current_learning_path_uid}"
                )

            if user_context.next_recommended_knowledge:
                context_parts.append(
                    f"Ready to Learn: {len(user_context.next_recommended_knowledge)} topics"
                )

        # Goal context (if query mentions goals/progress/achieve)
        if any(word in query_lower for word in ["goal", "achieve", "progress", "target"]):
            context_parts.append("\n--- Goals ---")
            context_parts.append(f"Active Goals: {len(user_context.active_goal_uids)}")
            if user_context.goal_progress:
                avg_progress = sum(user_context.goal_progress.values()) / len(
                    user_context.goal_progress
                )
                context_parts.append(f"Average Progress: {avg_progress:.0%}")

            # Goals nearing deadline
            near_deadline = user_context.get_goals_nearing_deadline(days=30)
            if near_deadline:
                context_parts.append(f"Goals with deadlines in 30 days: {len(near_deadline)}")

        # Habit context (if query mentions habits/routine/streak)
        if any(
            word in query_lower for word in ["habit", "routine", "daily", "streak", "consistency"]
        ):
            context_parts.append("\n--- Habits ---")
            context_parts.append(f"Active Habits: {len(user_context.active_habit_uids)}")
            if user_context.habit_streaks:
                max_streak = max(user_context.habit_streaks.values())
                avg_streak = sum(user_context.habit_streaks.values()) / len(
                    user_context.habit_streaks
                )
                context_parts.append(f"Longest Streak: {max_streak} days")
                context_parts.append(f"Average Streak: {avg_streak:.1f} days")
            if user_context.at_risk_habits:
                context_parts.append(
                    f"At Risk: {len(user_context.at_risk_habits)} habits need attention"
                )

        # Event context (if query mentions events/schedule/calendar)
        if any(word in query_lower for word in ["event", "schedule", "calendar", "meeting"]):
            context_parts.append("\n--- Events ---")
            context_parts.append(f"Upcoming Events: {len(user_context.upcoming_event_uids)}")
            if user_context.today_event_uids:
                context_parts.append(f"Today: {len(user_context.today_event_uids)} events")

        # Always include workload and capacity
        context_parts.append("\n--- Workload & Capacity ---")
        context_parts.append(f"Current Workload: {user_context.current_workload_score:.0%}")
        capacity_available = 100 - (user_context.current_workload_score * 100)
        context_parts.append(f"Capacity Available: {capacity_available:.0f}%")

        # State flags (always relevant)
        if user_context.is_blocked or user_context.is_overwhelmed:
            context_parts.append("\n--- Alerts ---")
            if user_context.is_blocked:
                context_parts.append("Blocked by prerequisites")
            if user_context.is_overwhelmed:
                context_parts.append("Workload overwhelming")

        # Life path alignment (if query mentions life/align/purpose)
        if (
            any(word in query_lower for word in ["life", "align", "purpose", "direction"])
            and user_context.life_path_uid
        ):
            context_parts.append("\n--- Life Path ---")
            context_parts.append(
                f"Life Path Alignment: {user_context.life_path_alignment_score:.0%}"
            )
            aligned = user_context.is_life_aligned(MasteryLevel.DEFAULT)
            context_parts.append(f"Status: {'Aligned' if aligned else 'Needs attention'}")

        # Activity report context (if query mentions feedback/patterns/reflection)
        if (
            any(
                word in query_lower
                for word in [
                    "feedback",
                    "pattern",
                    "review",
                    "reflect",
                    "report",
                    "progress",
                    "trend",
                    "doing",
                    "going",
                    "focus",
                    "week",
                    "lately",
                    "recently",
                ]
            )
            and user_context.latest_activity_report_uid
        ):
            report_age_days: int | None = None
            generated_at = user_context.latest_activity_report_generated_at
            if generated_at is not None:
                now = datetime.now(tz=UTC)
                aware_generated_at = (
                    generated_at.replace(tzinfo=UTC)
                    if generated_at.tzinfo is None
                    else generated_at
                )
                report_age_days = (now - aware_generated_at).days
            age_label = (
                f" (from {report_age_days} days ago — may not reflect current activity)"
                if report_age_days is not None and report_age_days > 30
                else ""
            )
            context_parts.append(f"\n--- Recent Activity Analysis{age_label} ---")
            if user_context.latest_activity_report_period:
                context_parts.append(f"Period: last {user_context.latest_activity_report_period}")
            if user_context.latest_activity_report_content:
                content = user_context.latest_activity_report_content
                _max = 500
                if len(content) <= _max:
                    snippet = content
                else:
                    boundary = max(
                        content.rfind(". ", 0, _max),
                        content.rfind("\n", 0, _max),
                    )
                    snippet = content[: boundary + 1] if boundary != -1 else content[:_max]
                trailing = "..." if len(content) > len(snippet) else ""
                context_parts.append(f"AI synthesis: {snippet}{trailing}")
            if user_context.latest_activity_report_user_annotation:
                context_parts.append(
                    f"Your reflection: {user_context.latest_activity_report_user_annotation}"
                )

        return "\n".join(context_parts)

    def generate_actions(
        self,
        user_context: UserContext,
        intent: QueryIntent,
        relevant_context: dict[str, Any],
    ) -> list[dict[str, Any]]:
        """
        Generate suggested next actions based on context and intent.

        Args:
            user_context: Complete user context
            intent: Query intent
            relevant_context: Retrieved entities

        Returns:
            List of suggested actions with metadata
        """
        actions = []

        # Critical actions first (at-risk habits, overdue tasks)
        if user_context.at_risk_habits:
            actions.append(
                {
                    "priority": "critical",
                    "action": "reinforce_habits",
                    "description": f"Maintain {len(user_context.at_risk_habits)} at-risk habits",
                    "entity_type": "habits",
                    "entity_count": len(user_context.at_risk_habits),
                }
            )

        if user_context.overdue_task_uids:
            actions.append(
                {
                    "priority": "high",
                    "action": "complete_overdue",
                    "description": f"Complete {len(user_context.overdue_task_uids)} overdue tasks",
                    "entity_type": "tasks",
                    "entity_count": len(user_context.overdue_task_uids),
                }
            )

        # Intent-specific actions
        if intent == QueryIntent.PREREQUISITE and relevant_context.get("blocked_knowledge"):
            actions.append(
                {
                    "priority": "medium",
                    "action": "learn_prerequisites",
                    "description": "Focus on prerequisite knowledge to unblock learning",
                    "entity_type": "knowledge",
                    "entity_count": relevant_context["blocked_knowledge"],
                }
            )

        elif intent == QueryIntent.PRACTICE and user_context.active_task_uids:
            actions.append(
                {
                    "priority": "medium",
                    "action": "apply_knowledge",
                    "description": "Complete tasks to apply your knowledge",
                    "entity_type": "tasks",
                    "entity_count": len(user_context.active_task_uids),
                }
            )

        elif intent == QueryIntent.HIERARCHICAL and user_context.current_learning_path_uid:
            actions.append(
                {
                    "priority": "medium",
                    "action": "continue_learning_path",
                    "description": "Continue current learning path",
                    "entity_type": "learning_path",
                    "entity_uid": user_context.current_learning_path_uid,
                }
            )

        # Capacity-based actions
        if user_context.current_workload_score < 0.5:
            actions.append(
                {
                    "priority": "low",
                    "action": "add_challenge",
                    "description": "You have capacity for more challenging work",
                    "capacity_available": f"{(1 - user_context.current_workload_score) * 100:.0f}%",
                }
            )

        return actions[:5]  # Return top 5 actions

    def generate_suggested_actions(
        self, _query_message: str, context_data: dict[str, Any], intent: QueryIntent
    ) -> list[dict[str, Any]]:
        """
        Generate suggested actions based on context and intent.

        Args:
            _query_message: User's query (unused - for future use)
            context_data: Retrieved context
            intent: Query intent

        Returns:
            List of suggested actions
        """
        actions = []

        # Add actions based on intent
        if intent == QueryIntent.HIERARCHICAL:
            learning_paths = context_data.get("learning_paths", [])
            if learning_paths:
                actions.append(
                    {
                        "action": "continue_learning_path",
                        "target": learning_paths[0].uid if learning_paths else None,
                        "description": "Continue your current learning path",
                    }
                )

        elif intent == QueryIntent.PRACTICE:
            tasks = context_data.get("related_tasks", [])
            if tasks:
                actions.append(
                    {
                        "action": "complete_task",
                        "target": tasks[0].uid if tasks else None,
                        "description": "Apply knowledge through practical task",
                    }
                )

        return actions
