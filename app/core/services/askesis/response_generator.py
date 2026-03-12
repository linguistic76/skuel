"""
Response Generator - Action, Response, and Guided Prompt Generation
=====================================================================

Generates suggested actions, responses, and guided system prompts based on
context, intent, and pedagogical guidance mode.

Responsibilities:
- Build LLM-friendly context from UserContext
- Generate suggested actions based on intent and context
- Generate context-aware responses
- Build guided system prompts for Socratic tutoring (absorbed from SocraticEngine)

Architecture:
- Uses UserContext as primary input
- Uses QueryIntent for intent-specific logic
- Uses GuidanceDetermination for pedagogical prompt generation
- Returns structured data for API responses

January 2026: Extracted from QueryProcessor as part of Askesis design improvement.
March 2026: Absorbed SocraticEngine prompt builders — single response service.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from core.constants import MasteryLevel
from core.models.askesis.pedagogical_intent import PedagogicalIntent
from core.models.query_types import QueryIntent
from core.utils.logging import get_logger

if TYPE_CHECKING:
    from core.models.askesis.ls_bundle import LSBundle
    from core.services.askesis.intent_classifier import GuidanceDetermination
    from core.services.user import UserContext

logger = get_logger(__name__)

# Maps QueryIntent -> which context sections to include in the LLM prompt.
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
    Generate actions, responses, and guided prompts based on context and intent.

    This service handles response generation:
    - Build LLM-friendly context from UserContext
    - Generate suggested next actions
    - Generate context-aware responses
    - Build guided system prompts for Socratic tutoring

    Architecture:
    - Uses UserContext (~240 fields) as input
    - Uses QueryIntent for intent-specific logic
    - Uses GuidanceDetermination for pedagogical prompt generation
    - Returns structured dicts for API responses
    """

    def __init__(self) -> None:
        """Initialize response generator."""
        logger.info("ResponseGenerator initialized")

    def build_llm_context(
        self,
        user_context: UserContext,
        query: str,
        intent: QueryIntent,
        ls_bundle: LSBundle | None = None,
    ) -> str:
        """
        Convert UserContext into LLM-friendly natural language.

        Uses the classified QueryIntent to select which context sections to include,
        rather than re-detecting intent via keyword heuristics. When an LSBundle is
        available, appends curriculum content for grounded responses.

        Args:
            user_context: Complete user context with 240+ fields
            query: User's question (used only for activity report keyword matching)
            intent: Classified query intent from IntentClassifier
            ls_bundle: Optional LS bundle with curriculum content

        Returns:
            Natural language context string for LLM consumption
        """
        sections = INTENT_CONTEXT_SECTIONS.get(
            intent, INTENT_CONTEXT_SECTIONS[QueryIntent.SPECIFIC]
        )
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

        # --- LS Bundle curriculum content ---
        if ls_bundle and ls_bundle.curriculum_context_text:
            context_parts.append("\n--- Curriculum Context ---")
            context_parts.append(ls_bundle.curriculum_context_text)

        from core.constants import AskesisTokenBudget
        from core.utils.text_truncation import truncate_to_budget

        return truncate_to_budget(
            "\n".join(context_parts), AskesisTokenBudget.MAX_LLM_CONTEXT_CHARS
        )

    # ========================================================================
    # GUIDED SYSTEM PROMPT GENERATION (absorbed from SocraticEngine)
    # ========================================================================

    def build_guided_system_prompt(
        self,
        guidance: GuidanceDetermination,
        ls_bundle: LSBundle,
        user_context: UserContext,
    ) -> str:
        """Build a system prompt based on the guidance determination.

        Dispatches to mode-specific builders that construct system prompts
        tailored to the pedagogical intent. Each mode has fine-grained
        variation based on guidance.pedagogical_detail.

        Args:
            guidance: GuidanceDetermination with mode and pedagogical detail
            ls_bundle: Complete LS bundle (scoped context)
            user_context: User context for personalization

        Returns:
            System prompt string for the LLM call
        """
        from core.models.enums import GuidanceMode

        builders = {
            GuidanceMode.DIRECT: self._build_direct_prompt,
            GuidanceMode.SOCRATIC: self._build_socratic_prompt,
            GuidanceMode.EXPLORATORY: self._build_exploratory_prompt,
            GuidanceMode.ENCOURAGING: self._build_encouraging_prompt,
        }
        builder = builders.get(guidance.mode, self._build_direct_prompt)
        return builder(guidance, ls_bundle)

    def _build_direct_prompt(
        self,
        guidance: GuidanceDetermination,
        ls_bundle: LSBundle,
    ) -> str:
        """DIRECT mode: redirect or out-of-scope responses.

        Covers REDIRECT_TO_CURRICULUM and OUT_OF_SCOPE pedagogical intents.
        """
        if guidance.pedagogical_detail == PedagogicalIntent.REDIRECT_TO_CURRICULUM:
            # Find Articles linked to the target KUs
            article_refs = []
            for ku_uid in guidance.target_ku_uids:
                article = ls_bundle.get_article_for_ku(ku_uid)
                if article:
                    article_refs.append(article.title or "Untitled Article")

            if not article_refs:
                article_refs = [a.title or "Untitled Article" for a in ls_bundle.articles]

            articles_text = ", ".join(dict.fromkeys(article_refs))

            return (
                "You are a Socratic tutor. The learner is asking about "
                "concepts they haven't engaged with yet and there is "
                "curriculum content available for them to study. Gently "
                "redirect them to read the relevant material first. Be "
                "encouraging, not dismissive. Give a brief orientation of "
                "what they'll find in the material.\n\n"
                f"Recommended reading: {articles_text}"
            )

        # OUT_OF_SCOPE
        ls_title = ls_bundle.learning_step.title or "your current step"
        ls_intent = ls_bundle.learning_step.intent or ""

        return (
            "You are a Socratic tutor. The learner asked about something "
            "outside the scope of their current learning step. Acknowledge "
            "their curiosity, but gently redirect them to their current "
            "focus. Be warm, not dismissive.\n\n"
            f"Current learning step: {ls_title}\n"
            f"Step intent: {ls_intent}"
        )

    def _build_socratic_prompt(
        self,
        guidance: GuidanceDetermination,
        ls_bundle: LSBundle,
    ) -> str:
        """SOCRATIC mode: assess understanding or probe deeper.

        Covers ASSESS_UNDERSTANDING and PROBE_DEEPER pedagogical intents.
        """
        ku_names = self._get_ku_names(ls_bundle, guidance.target_ku_uids)

        if guidance.pedagogical_detail == PedagogicalIntent.ASSESS_UNDERSTANDING:
            return (
                "You are a Socratic tutor. The learner has engaged with the "
                "following concepts and you need to assess their understanding. "
                "Do NOT give answers or explain the concepts. Instead, ask the "
                "learner to explain what they know in their own words. Use "
                "open-ended questions like 'Tell me what you understand about...' "
                "or 'How would you explain... to someone new to this?'\n\n"
                f"Concepts to assess: {', '.join(ku_names)}"
            )

        # PROBE_DEEPER
        return (
            "You are a Socratic tutor. The learner has some familiarity "
            "with these concepts but hasn't demonstrated deep understanding. "
            "Ask a follow-up question that tests understanding beyond "
            "surface-level recognition. Probe for application, nuance, or "
            "connections. Do NOT give the answer.\n\n"
            f"Concepts to probe: {', '.join(ku_names)}"
        )

    def _build_exploratory_prompt(
        self,
        guidance: GuidanceDetermination,
        ls_bundle: LSBundle,
    ) -> str:
        """EXPLORATORY mode: scaffold or surface connections.

        Covers SCAFFOLD and SURFACE_CONNECTION pedagogical intents.
        """
        if guidance.pedagogical_detail == PedagogicalIntent.SCAFFOLD:
            ku_names = self._get_ku_names(ls_bundle, guidance.target_ku_uids)
            return (
                "You are a Socratic tutor. The learner is approaching new "
                "concepts they haven't engaged with yet. Guide them toward "
                "understanding through questions, analogies, and step-by-step "
                "reasoning. Do NOT give direct explanations. Ask questions "
                "that lead them to discover the insight themselves.\n\n"
                f"Concepts to scaffold: {', '.join(ku_names)}\n\n"
                "Use the curriculum context below to know what you're "
                "scaffolding toward, but do not simply restate it."
            )

        # SURFACE_CONNECTION
        target_set = set(guidance.target_ku_uids)
        relevant_edges: list[dict] = []
        for edge in ls_bundle.edges:
            if isinstance(edge, dict):
                source = edge.get("source_uid", "")
                target = edge.get("target_uid", "")
                if source in target_set or target in target_set:
                    relevant_edges.append(edge)

        edges_text = ""
        for edge in relevant_edges:
            rel_type = edge.get("relationship_type", "related to")
            evidence = edge.get("evidence", "")
            edges_text += f"- {rel_type}: {evidence}\n"

        return (
            "You are a Socratic tutor. The learner's question touches "
            "concepts that are connected in the curriculum. Surface this "
            "connection and ask the learner to reflect on how the concepts "
            "relate. Use the relationship evidence to guide the question.\n\n"
            f"Relationship evidence:\n{edges_text or 'No specific evidence available.'}"
        )

    def _build_encouraging_prompt(
        self,
        guidance: GuidanceDetermination,
        ls_bundle: LSBundle,
    ) -> str:
        """ENCOURAGING mode: connect understanding to practice.

        Covers ENCOURAGE_PRACTICE pedagogical intent.
        """
        practice_items = []
        for habit in ls_bundle.habits:
            practice_items.append(f"Habit: {habit.title}")
        for task in ls_bundle.tasks:
            practice_items.append(f"Task: {task.title}")
        for event in ls_bundle.events:
            practice_items.append(f"Event: {event.title}")

        practice_text = (
            "\n".join(practice_items)
            if practice_items
            else "No specific practice activities linked."
        )

        return (
            "You are a Socratic tutor. The learner has conceptual "
            "understanding but needs to deepen it through practice. "
            "Acknowledge their understanding, then encourage them to "
            "engage with the practice activities linked to their current "
            "learning step. Explain how practice compounds knowledge.\n\n"
            f"Available practice activities:\n{practice_text}"
        )

    # ========================================================================
    # PRIVATE - GUIDED PROMPT HELPERS
    # ========================================================================

    def _get_ku_names(self, ls_bundle: LSBundle, ku_uids: list[str]) -> list[str]:
        """Get KU titles for the given UIDs from the bundle."""
        names = []
        uid_set = set(ku_uids)
        for ku in ls_bundle.kus:
            if ku.uid in uid_set:
                names.append(ku.title or ku.uid)
        return names or ["(unknown concepts)"]

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
