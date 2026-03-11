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
from core.models.query_types import QueryIntent
from core.utils.logging import get_logger

if TYPE_CHECKING:
    from core.services.user import UserContext

logger = get_logger(__name__)

# Maps QueryIntent → which context sections to include in the LLM prompt.
# Sections not listed here ("workload", "alerts") are always included.
# "activity_report" uses query-text matching (broad keyword set doesn't map to one intent).
INTENT_CONTEXT_SECTIONS: dict[QueryIntent, frozenset[str]] = {
    QueryIntent.HIERARCHICAL: frozenset({"knowledge", "goals", "life_path"}),
    QueryIntent.PREREQUISITE: frozenset({"knowledge"}),
    QueryIntent.PRACTICE: frozenset({"tasks", "knowledge"}),
    QueryIntent.EXPLORATORY: frozenset(
        {"tasks", "knowledge", "goals", "habits", "events", "life_path"}
    ),
    QueryIntent.RELATIONSHIP: frozenset({"knowledge"}),
    QueryIntent.AGGREGATION: frozenset(
        {"tasks", "knowledge", "goals", "habits", "events", "life_path"}
    ),
    QueryIntent.SPECIFIC: frozenset(
        {"tasks", "knowledge", "goals", "habits", "events", "life_path"}
    ),
}

# Keywords that trigger including the activity report section.
# This set is broad and doesn't map to a single QueryIntent.
_ACTIVITY_REPORT_KEYWORDS: frozenset[str] = frozenset(
    {
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
    }
)


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

    def build_llm_context(
        self, user_context: UserContext, query: str, intent: QueryIntent
    ) -> str:
        """
        Convert UserContext into LLM-friendly natural language.

        Uses the classified QueryIntent to select which context sections to include,
        rather than re-detecting intent via keyword heuristics.

        Args:
            user_context: Complete user context with 240+ fields
            query: User's question (used only for activity report keyword matching)
            intent: Classified query intent from IntentClassifier

        Returns:
            Natural language context string for LLM consumption
        """
        sections = INTENT_CONTEXT_SECTIONS.get(intent, INTENT_CONTEXT_SECTIONS[QueryIntent.SPECIFIC])
        context_parts: list[str] = []

        # Always include user identity
        context_parts.append(f"User: {user_context.username}")

        # --- Domain sections driven by intent ---

        if "tasks" in sections:
            self._append_tasks_section(context_parts, user_context)

        if "knowledge" in sections:
            self._append_knowledge_section(context_parts, user_context)

        if "goals" in sections:
            self._append_goals_section(context_parts, user_context)

        if "habits" in sections:
            self._append_habits_section(context_parts, user_context)

        if "events" in sections:
            self._append_events_section(context_parts, user_context)

        # --- Always-included sections ---

        context_parts.append("\n--- Workload & Capacity ---")
        context_parts.append(f"Current Workload: {user_context.current_workload_score:.0%}")
        capacity_available = 100 - (user_context.current_workload_score * 100)
        context_parts.append(f"Capacity Available: {capacity_available:.0f}%")

        if user_context.is_blocked or user_context.is_overwhelmed:
            context_parts.append("\n--- Alerts ---")
            if user_context.is_blocked:
                context_parts.append("Blocked by prerequisites")
            if user_context.is_overwhelmed:
                context_parts.append("Workload overwhelming")

        # --- Conditionally-included sections ---

        if "life_path" in sections and user_context.life_path_uid:
            self._append_life_path_section(context_parts, user_context)

        # Activity report: uses query-text matching (broad keyword set doesn't map to one intent)
        query_lower = query.lower()
        if (
            any(word in query_lower for word in _ACTIVITY_REPORT_KEYWORDS)
            and user_context.latest_activity_report_uid
        ):
            self._append_activity_report_section(context_parts, user_context)

        return "\n".join(context_parts)

    # ========================================================================
    # PRIVATE - CONTEXT SECTION RENDERERS
    # ========================================================================

    @staticmethod
    def _append_tasks_section(parts: list[str], ctx: UserContext) -> None:
        parts.append("\n--- Tasks ---")
        parts.append(f"Active Tasks: {len(ctx.active_task_uids)}")
        if ctx.overdue_task_uids:
            parts.append(f"Overdue: {len(ctx.overdue_task_uids)} tasks")
        if ctx.blocked_task_uids:
            parts.append(f"Blocked: {len(ctx.blocked_task_uids)} tasks")
        if ctx.today_task_uids:
            parts.append(f"Due Today: {len(ctx.today_task_uids)} tasks")

    @staticmethod
    def _append_knowledge_section(parts: list[str], ctx: UserContext) -> None:
        parts.append("\n--- Knowledge & Learning ---")
        parts.append(f"Average Mastery: {ctx.mastery_average:.0%}")
        parts.append(f"Mastered: {len(ctx.mastered_knowledge_uids)} knowledge units")
        parts.append(f"In Progress: {len(ctx.in_progress_knowledge_uids)} knowledge units")
        if ctx.current_learning_path_uid:
            parts.append(f"Current Learning Path: {ctx.current_learning_path_uid}")
        if ctx.next_recommended_knowledge:
            parts.append(f"Ready to Learn: {len(ctx.next_recommended_knowledge)} topics")

    @staticmethod
    def _append_goals_section(parts: list[str], ctx: UserContext) -> None:
        parts.append("\n--- Goals ---")
        parts.append(f"Active Goals: {len(ctx.active_goal_uids)}")
        if ctx.goal_progress:
            avg_progress = sum(ctx.goal_progress.values()) / len(ctx.goal_progress)
            parts.append(f"Average Progress: {avg_progress:.0%}")
        near_deadline = ctx.get_goals_nearing_deadline(days=30)
        if near_deadline:
            parts.append(f"Goals with deadlines in 30 days: {len(near_deadline)}")

    @staticmethod
    def _append_habits_section(parts: list[str], ctx: UserContext) -> None:
        parts.append("\n--- Habits ---")
        parts.append(f"Active Habits: {len(ctx.active_habit_uids)}")
        if ctx.habit_streaks:
            max_streak = max(ctx.habit_streaks.values())
            avg_streak = sum(ctx.habit_streaks.values()) / len(ctx.habit_streaks)
            parts.append(f"Longest Streak: {max_streak} days")
            parts.append(f"Average Streak: {avg_streak:.1f} days")
        if ctx.at_risk_habits:
            parts.append(f"At Risk: {len(ctx.at_risk_habits)} habits need attention")

    @staticmethod
    def _append_events_section(parts: list[str], ctx: UserContext) -> None:
        parts.append("\n--- Events ---")
        parts.append(f"Upcoming Events: {len(ctx.upcoming_event_uids)}")
        if ctx.today_event_uids:
            parts.append(f"Today: {len(ctx.today_event_uids)} events")

    @staticmethod
    def _append_life_path_section(parts: list[str], ctx: UserContext) -> None:
        parts.append("\n--- Life Path ---")
        parts.append(f"Life Path Alignment: {ctx.life_path_alignment_score:.0%}")
        aligned = ctx.is_life_aligned(MasteryLevel.DEFAULT)
        parts.append(f"Status: {'Aligned' if aligned else 'Needs attention'}")

    @staticmethod
    def _append_activity_report_section(parts: list[str], ctx: UserContext) -> None:
        report_age_days: int | None = None
        generated_at = ctx.latest_activity_report_generated_at
        if generated_at is not None:
            now = datetime.now(tz=UTC)
            aware_generated_at = (
                generated_at.replace(tzinfo=UTC) if generated_at.tzinfo is None else generated_at
            )
            report_age_days = (now - aware_generated_at).days
        age_label = (
            f" (from {report_age_days} days ago — may not reflect current activity)"
            if report_age_days is not None and report_age_days > 30
            else ""
        )
        parts.append(f"\n--- Recent Activity Analysis{age_label} ---")
        if ctx.latest_activity_report_period:
            parts.append(f"Period: last {ctx.latest_activity_report_period}")
        if ctx.latest_activity_report_content:
            content = ctx.latest_activity_report_content
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
            parts.append(f"AI synthesis: {snippet}{trailing}")
        if ctx.latest_activity_report_user_annotation:
            parts.append(f"Your reflection: {ctx.latest_activity_report_user_annotation}")

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
