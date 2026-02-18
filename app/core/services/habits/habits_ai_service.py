"""
Habits AI Service
=================

AI-powered features for Habits domain (requires LLM/Embeddings).

Created: January 2026
Purpose: Separate AI features from graph analytics (ADR-030)

AI services contain features that REQUIRE:
- embeddings_service (semantic search, similarity matching)
- llm_service (AI-generated insights, recommendations, natural language)

AI services are OPTIONAL - the app functions fully without them.
They enhance the user experience but are not required for core functionality.

This service explicitly DOES use:
- embeddings_service (semantic habit similarity)
- llm_service (AI-generated habit formation tips)

The app works WITHOUT this service. It's an enhancement layer.
"""

from typing import TYPE_CHECKING, Any

from core.models.ku.ku_habit import HabitKu
from core.services.base_ai_service import BaseAIService
from core.services.protocols import HabitsOperations
from core.utils.result_simplified import Errors, Result

if TYPE_CHECKING:
    from core.services.llm_service import LLMService
    from core.services.neo4j_genai_embeddings_service import Neo4jGenAIEmbeddingsService


class HabitsAIService(BaseAIService[HabitsOperations, HabitKu]):
    """
    AI-powered features for Habits domain.

    This service is OPTIONAL - the app works without it.
    Provides enhanced features using LLM and embeddings.

    AI features:
    - Semantic habit similarity (find similar habits by meaning)
    - AI-generated streak insights and motivation
    - Habit formation tips based on behavioral science
    - Cue-Routine-Reward optimization
    - Identity-based habit recommendations

    NOTE: These features require LLM/embeddings services.
    If not available, this service won't be instantiated.
    """

    _service_name = "habits.ai"

    def __init__(
        self,
        backend: HabitsOperations,
        llm_service: "LLMService",
        embeddings_service: "Neo4jGenAIEmbeddingsService",
        event_bus: Any | None = None,
    ) -> None:
        """
        Initialize habits AI service.

        Args:
            backend: Habits backend operations (protocol)
            llm_service: LLM service for AI insights (REQUIRED)
            embeddings_service: Embeddings service for semantic search (REQUIRED)
            event_bus: Event bus for publishing events (optional)

        NOTE: Both llm_service and embeddings_service are REQUIRED.
        This service should only be instantiated when AI is available.
        """
        super().__init__(
            backend=backend,
            llm_service=llm_service,
            embeddings_service=embeddings_service,
            event_bus=event_bus,
        )

    # ========================================================================
    # SEMANTIC SIMILARITY
    # ========================================================================

    async def find_similar_habits(
        self, habit_uid: str, limit: int = 5
    ) -> Result[list[tuple[str, float]]]:
        """
        Find semantically similar habits using embeddings.

        Uses embeddings to find habits with similar meaning/context,
        not just keyword matching.

        Args:
            habit_uid: Habit to find similar habits for
            limit: Maximum number of similar habits to return

        Returns:
            Result containing list of (habit_uid, similarity_score) tuples
        """
        habit_result = await self.backend.get(habit_uid)
        if habit_result.is_error:
            return Result.fail(habit_result.expect_error())

        habit = habit_result.value
        if not habit:
            return Result.fail(Errors.not_found(resource="Habit", identifier=habit_uid))

        search_text = f"{habit.title}"
        if habit.description:
            search_text += f" {habit.description}"
        if habit.routine:
            search_text += f" {habit.routine}"

        all_habits_result = await self.backend.find_by(user_uid=habit.user_uid)
        if all_habits_result.is_error:
            return Result.fail(all_habits_result.expect_error())

        all_habits = all_habits_result.value or []
        candidates = [
            (h.uid, f"{h.name} {h.description or ''} {h.routine or ''}")
            for h in all_habits
            if h.uid != habit_uid
        ]

        if not candidates:
            return Result.ok([])

        return await self._semantic_search(search_text, candidates, limit)

    # ========================================================================
    # STREAK INSIGHTS
    # ========================================================================

    async def generate_streak_insight(self, habit_uid: str) -> Result[str]:
        """
        Generate AI-powered insight about a habit streak.

        Uses LLM to provide personalized motivation and streak analysis.

        Args:
            habit_uid: Habit to analyze

        Returns:
            Result containing AI-generated streak insight
        """
        habit_result = await self.backend.get(habit_uid)
        if habit_result.is_error:
            return Result.fail(habit_result.expect_error())

        habit = habit_result.value
        if not habit:
            return Result.fail(Errors.not_found(resource="Habit", identifier=habit_uid))

        streak_status = "building momentum" if habit.current_streak > 0 else "starting fresh"
        if habit.current_streak >= habit.best_streak and habit.best_streak > 0:
            streak_status = "at personal best"

        context = {
            "name": habit.title,
            "current_streak": habit.current_streak,
            "best_streak": habit.best_streak,
            "total_completions": habit.total_completions,
            "success_rate": f"{habit.success_rate * 100:.1f}%",
            "streak_status": streak_status,
            "polarity": habit.polarity.value if habit.polarity else "unknown",
        }

        prompt = """Provide a brief, motivating insight about this habit streak.

Consider:
1. The user's current progress vs their best
2. Specific encouragement based on their streak status
3. A behavioral science tip for maintaining momentum

Keep it under 100 words. Be warm but not over-the-top."""

        return await self._generate_insight(prompt, context=context, max_tokens=200)

    # ========================================================================
    # HABIT FORMATION TIPS
    # ========================================================================

    async def suggest_habit_stack(self, habit_uid: str) -> Result[dict[str, Any]]:
        """
        Suggest habit stacking opportunities based on James Clear's methodology.

        Habit stacking: "After I [CURRENT HABIT], I will [NEW HABIT]."

        Args:
            habit_uid: Habit to find stacking opportunities for

        Returns:
            Result containing habit stacking suggestions
        """
        habit_result = await self.backend.get(habit_uid)
        if habit_result.is_error:
            return Result.fail(habit_result.expect_error())

        habit = habit_result.value
        if not habit:
            return Result.fail(Errors.not_found(resource="Habit", identifier=habit_uid))

        context = {
            "name": habit.title,
            "category": habit.habit_category.value if habit.habit_category else "unknown",
            "preferred_time": habit.preferred_time or "any time",
            "duration_minutes": habit.duration_minutes,
            "cue": habit.cue or "Not specified",
        }

        prompt = """Suggest 3 habit stacking opportunities for this habit.

Use the format: "After I [existing habit], I will [this habit]" or
"After I [this habit], I will [suggested next habit]"

Consider:
1. Time of day compatibility
2. Duration flow (short habits stack well)
3. Category synergies

Format each suggestion as:
BEFORE: [habit that comes before]
AFTER: [habit that comes after]
WHY: [brief explanation]"""

        insight_result = await self._generate_insight(prompt, context=context, max_tokens=350)
        if insight_result.is_error:
            return Result.fail(insight_result.expect_error())

        response = insight_result.value
        stacks = []
        current_stack: dict[str, str] = {}

        for line in response.split("\n"):
            line = line.strip()
            if line.upper().startswith("BEFORE:"):
                if current_stack:
                    stacks.append(current_stack)
                current_stack = {"before": line.split(":", 1)[1].strip()}
            elif line.upper().startswith("AFTER:"):
                if current_stack:
                    current_stack["after"] = line.split(":", 1)[1].strip()
            elif line.upper().startswith("WHY:"):
                if current_stack:
                    current_stack["reason"] = line.split(":", 1)[1].strip()

        if current_stack and "before" in current_stack:
            stacks.append(current_stack)

        return Result.ok(
            {
                "habit_uid": habit_uid,
                "habit_name": habit.title,
                "stacking_suggestions": stacks,
            }
        )

    # ========================================================================
    # CUE-ROUTINE-REWARD OPTIMIZATION
    # ========================================================================

    async def optimize_habit_loop(self, habit_uid: str) -> Result[dict[str, Any]]:
        """
        Suggest improvements to the habit's cue-routine-reward loop.

        Based on Charles Duhigg's "The Power of Habit" habit loop model.

        Args:
            habit_uid: Habit to optimize

        Returns:
            Result containing optimized cue, routine, and reward suggestions
        """
        habit_result = await self.backend.get(habit_uid)
        if habit_result.is_error:
            return Result.fail(habit_result.expect_error())

        habit = habit_result.value
        if not habit:
            return Result.fail(Errors.not_found(resource="Habit", identifier=habit_uid))

        context = {
            "name": habit.title,
            "description": habit.description or "Not specified",
            "current_cue": habit.cue or "Not specified",
            "current_routine": habit.routine or "Not specified",
            "current_reward": habit.reward or "Not specified",
            "polarity": habit.polarity.value if habit.polarity else "unknown",
            "difficulty": habit.habit_difficulty.value if habit.habit_difficulty else "unknown",
        }

        prompt = """Optimize this habit's cue-routine-reward loop.

For each element, provide:
1. An evaluation of the current setup (if specified)
2. A specific, actionable improvement

Format:
CUE_ANALYSIS: [evaluation of current cue]
CUE_SUGGESTION: [specific improved cue]
ROUTINE_ANALYSIS: [evaluation of current routine]
ROUTINE_SUGGESTION: [specific improved routine]
REWARD_ANALYSIS: [evaluation of current reward]
REWARD_SUGGESTION: [specific improved reward]
OVERALL_TIP: [one key insight for this habit]"""

        insight_result = await self._generate_insight(prompt, context=context, max_tokens=450)
        if insight_result.is_error:
            return Result.fail(insight_result.expect_error())

        response = insight_result.value
        optimization: dict[str, Any] = {
            "habit_uid": habit_uid,
            "habit_name": habit.title,
            "current": {
                "cue": habit.cue,
                "routine": habit.routine,
                "reward": habit.reward,
            },
            "analysis": {},
            "suggestions": {},
            "overall_tip": None,
        }

        for line in response.split("\n"):
            line = line.strip()
            if line.upper().startswith("CUE_ANALYSIS:"):
                optimization["analysis"]["cue"] = line.split(":", 1)[1].strip()
            elif line.upper().startswith("CUE_SUGGESTION:"):
                optimization["suggestions"]["cue"] = line.split(":", 1)[1].strip()
            elif line.upper().startswith("ROUTINE_ANALYSIS:"):
                optimization["analysis"]["routine"] = line.split(":", 1)[1].strip()
            elif line.upper().startswith("ROUTINE_SUGGESTION:"):
                optimization["suggestions"]["routine"] = line.split(":", 1)[1].strip()
            elif line.upper().startswith("REWARD_ANALYSIS:"):
                optimization["analysis"]["reward"] = line.split(":", 1)[1].strip()
            elif line.upper().startswith("REWARD_SUGGESTION:"):
                optimization["suggestions"]["reward"] = line.split(":", 1)[1].strip()
            elif line.upper().startswith("OVERALL_TIP:"):
                optimization["overall_tip"] = line.split(":", 1)[1].strip()

        return Result.ok(optimization)

    # ========================================================================
    # IDENTITY-BASED HABITS
    # ========================================================================

    async def suggest_identity_reinforcement(self, habit_uid: str) -> Result[dict[str, Any]]:
        """
        Suggest identity-based framing for a habit (James Clear's Atomic Habits).

        "Every action is a vote for the type of person you wish to become."

        Args:
            habit_uid: Habit to analyze

        Returns:
            Result containing identity statements and reinforcement strategies
        """
        habit_result = await self.backend.get(habit_uid)
        if habit_result.is_error:
            return Result.fail(habit_result.expect_error())

        habit = habit_result.value
        if not habit:
            return Result.fail(Errors.not_found(resource="Habit", identifier=habit_uid))

        context = {
            "name": habit.title,
            "description": habit.description or "Not specified",
            "category": habit.habit_category.value if habit.habit_category else "unknown",
            "current_identity": habit.reinforces_identity or "Not specified",
            "identity_votes": habit.identity_votes_cast,
            "polarity": habit.polarity.value if habit.polarity else "unknown",
        }

        prompt = """Create identity-based framing for this habit.

Provide:
1. An identity statement ("I am a..." or "I am someone who...")
2. Why this identity matters
3. How each completion reinforces this identity
4. A mantra for difficult days

Format:
IDENTITY: [I am a... statement]
WHY_IT_MATTERS: [brief explanation]
VOTE_MEANING: [what each completion represents]
MANTRA: [short motivational phrase]"""

        insight_result = await self._generate_insight(prompt, context=context, max_tokens=300)
        if insight_result.is_error:
            return Result.fail(insight_result.expect_error())

        response = insight_result.value
        identity: dict[str, Any] = {
            "habit_uid": habit_uid,
            "habit_name": habit.title,
            "current_identity": habit.reinforces_identity,
            "identity_votes_cast": habit.identity_votes_cast,
        }

        for line in response.split("\n"):
            line = line.strip()
            if line.upper().startswith("IDENTITY:"):
                identity["suggested_identity"] = line.split(":", 1)[1].strip()
            elif line.upper().startswith("WHY_IT_MATTERS:"):
                identity["why_it_matters"] = line.split(":", 1)[1].strip()
            elif line.upper().startswith("VOTE_MEANING:"):
                identity["vote_meaning"] = line.split(":", 1)[1].strip()
            elif line.upper().startswith("MANTRA:"):
                identity["mantra"] = line.split(":", 1)[1].strip()

        return Result.ok(identity)
