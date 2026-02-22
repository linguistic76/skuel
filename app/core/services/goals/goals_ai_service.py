"""
Goals AI Service
================

AI-powered features for Goals domain (requires LLM/Embeddings).

Created: January 2026
Purpose: Separate AI features from graph analytics (ADR-030)

AI services contain features that REQUIRE:
- embeddings_service (semantic search, similarity matching)
- llm_service (AI-generated insights, recommendations, natural language)

AI services are OPTIONAL - the app functions fully without them.
They enhance the user experience but are not required for core functionality.

This service explicitly DOES use:
- embeddings_service (semantic goal similarity)
- llm_service (AI-generated recommendations)

The app works WITHOUT this service. It's an enhancement layer.
"""

from typing import TYPE_CHECKING, Any

from core.models.ku.goal import Goal
from core.ports import GoalsOperations
from core.services.base_ai_service import BaseAIService
from core.utils.result_simplified import Errors, Result

if TYPE_CHECKING:
    from core.services.llm_service import LLMService
    from core.services.neo4j_genai_embeddings_service import Neo4jGenAIEmbeddingsService


class GoalsAIService(BaseAIService[GoalsOperations, Goal]):
    """
    AI-powered features for Goals domain.

    This service is OPTIONAL - the app works without it.
    Provides enhanced features using LLM and embeddings.

    AI features:
    - Semantic goal similarity (find similar goals by meaning)
    - AI-generated milestone suggestions
    - Natural language goal insights
    - Smart goal refinement (SMART criteria)
    - Achievement strategy recommendations

    NOTE: These features require LLM/embeddings services.
    If not available, this service won't be instantiated.
    """

    _service_name = "goals.ai"

    def __init__(
        self,
        backend: GoalsOperations,
        llm_service: "LLMService",
        embeddings_service: "Neo4jGenAIEmbeddingsService",
        event_bus: Any | None = None,
    ) -> None:
        """
        Initialize goals AI service.

        Args:
            backend: Goals backend operations (protocol)
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

    async def find_similar_goals(
        self, goal_uid: str, limit: int = 5
    ) -> Result[list[tuple[str, float]]]:
        """
        Find semantically similar goals using embeddings.

        Uses embeddings to find goals with similar meaning/context,
        not just keyword matching.

        Args:
            goal_uid: Goal to find similar goals for
            limit: Maximum number of similar goals to return

        Returns:
            Result containing list of (goal_uid, similarity_score) tuples
        """
        goal_result = await self.backend.get(goal_uid)
        if goal_result.is_error:
            return Result.fail(goal_result.expect_error())

        goal = goal_result.value
        if not goal:
            return Result.fail(Errors.not_found(resource="Goal", identifier=goal_uid))

        search_text = f"{goal.title}"
        if goal.description:
            search_text += f" {goal.description}"
        if goal.success_criteria:
            search_text += f" {goal.success_criteria}"

        all_goals_result = await self.backend.find_by(user_uid=goal.user_uid)
        if all_goals_result.is_error:
            return Result.fail(all_goals_result.expect_error())

        all_goals = all_goals_result.value or []
        candidates = [
            (g.uid, f"{g.title} {g.description or ''} {g.success_criteria or ''}")
            for g in all_goals
            if g.uid != goal_uid
        ]

        if not candidates:
            return Result.ok([])

        return await self._semantic_search(search_text, candidates, limit)

    # ========================================================================
    # AI-GENERATED MILESTONES
    # ========================================================================

    async def generate_milestones(
        self, goal_uid: str, max_milestones: int = 5
    ) -> Result[list[dict[str, Any]]]:
        """
        Generate AI-suggested milestones for a goal.

        Uses LLM to analyze the goal and suggest meaningful milestones.

        Args:
            goal_uid: Goal to generate milestones for
            max_milestones: Maximum number of milestones to suggest

        Returns:
            Result containing list of milestone suggestions with title and criteria
        """
        goal_result = await self.backend.get(goal_uid)
        if goal_result.is_error:
            return Result.fail(goal_result.expect_error())

        goal = goal_result.value
        if not goal:
            return Result.fail(Errors.not_found(resource="Goal", identifier=goal_uid))

        prompt = f"""Generate {max_milestones} meaningful milestones for achieving this goal.

Goal: {goal.title}
Description: {goal.description or "No description provided"}
Success Criteria: {goal.success_criteria or "Not specified"}
Timeframe: {goal.timeframe.value if goal.timeframe else "Not specified"}

For each milestone, provide:
1. A clear, measurable title
2. Specific completion criteria

Format each milestone as:
MILESTONE: [title]
CRITERIA: [how to know it's complete]

Order from earliest to latest achievement."""

        insight_result = await self._generate_insight(prompt, max_tokens=500)
        if insight_result.is_error:
            return Result.fail(insight_result.expect_error())

        response = insight_result.value
        milestones = []
        current_milestone: dict[str, str] = {}

        for line in response.split("\n"):
            line = line.strip()
            if line.upper().startswith("MILESTONE:"):
                if current_milestone:
                    milestones.append(current_milestone)
                current_milestone = {"title": line.split(":", 1)[1].strip()}
            elif line.upper().startswith("CRITERIA:"):
                if current_milestone:
                    current_milestone["criteria"] = line.split(":", 1)[1].strip()

        if current_milestone and "title" in current_milestone:
            milestones.append(current_milestone)

        return Result.ok(milestones[:max_milestones])

    # ========================================================================
    # AI INSIGHTS
    # ========================================================================

    async def generate_goal_insight(self, goal_uid: str) -> Result[str]:
        """
        Generate AI-written insight about a goal.

        Uses LLM to provide contextual insight about the goal,
        progress expectations, and achievement strategies.

        Args:
            goal_uid: Goal to analyze

        Returns:
            Result containing AI-generated insight text
        """
        goal_result = await self.backend.get(goal_uid)
        if goal_result.is_error:
            return Result.fail(goal_result.expect_error())

        goal = goal_result.value
        if not goal:
            return Result.fail(Errors.not_found(resource="Goal", identifier=goal_uid))

        context = {
            "title": goal.title,
            "description": goal.description or "No description",
            "status": goal.status.value if goal.status else "Unknown",
            "progress": f"{goal.progress_percentage or 0}%",
            "timeframe": goal.timeframe.value if goal.timeframe else "Not set",
            "target_date": str(goal.target_date) if goal.target_date else "No deadline",
        }

        prompt = """Provide a brief, motivating insight about this goal.
Focus on:
1. Why this goal matters for personal growth
2. One specific strategy for making progress
3. A potential challenge to watch for
Keep it under 150 words."""

        return await self._generate_insight(prompt, context=context, max_tokens=250)

    # ========================================================================
    # SMART GOAL REFINEMENT
    # ========================================================================

    async def suggest_smart_refinement(self, goal_uid: str) -> Result[dict[str, Any]]:
        """
        Analyze a goal against SMART criteria and suggest improvements.

        SMART: Specific, Measurable, Achievable, Relevant, Time-bound

        Args:
            goal_uid: Goal to analyze

        Returns:
            Result containing SMART analysis and suggestions
        """
        goal_result = await self.backend.get(goal_uid)
        if goal_result.is_error:
            return Result.fail(goal_result.expect_error())

        goal = goal_result.value
        if not goal:
            return Result.fail(Errors.not_found(resource="Goal", identifier=goal_uid))

        context = {
            "title": goal.title,
            "description": goal.description or "No description",
            "success_criteria": goal.success_criteria or "Not specified",
            "target_date": str(goal.target_date) if goal.target_date else "Not set",
        }

        prompt = """Analyze this goal against SMART criteria and provide suggestions.

For each criterion, rate it (Strong/Needs Work) and provide a specific improvement if needed.

Respond in this exact format:
SPECIFIC: [Strong/Needs Work] - [suggestion if needed]
MEASURABLE: [Strong/Needs Work] - [suggestion if needed]
ACHIEVABLE: [Strong/Needs Work] - [suggestion if needed]
RELEVANT: [Strong/Needs Work] - [suggestion if needed]
TIME_BOUND: [Strong/Needs Work] - [suggestion if needed]
REFINED_GOAL: [A SMART-improved version of the goal title]"""

        insight_result = await self._generate_insight(prompt, context=context, max_tokens=400)
        if insight_result.is_error:
            return Result.fail(insight_result.expect_error())

        response = insight_result.value
        analysis: dict[str, Any] = {
            "goal_uid": goal_uid,
            "original_title": goal.title,
            "criteria": {},
            "refined_goal": None,
        }

        for line in response.split("\n"):
            line = line.strip()
            for criterion in ["SPECIFIC", "MEASURABLE", "ACHIEVABLE", "RELEVANT", "TIME_BOUND"]:
                if line.upper().startswith(f"{criterion}:"):
                    parts = line.split(":", 1)[1].strip()
                    rating = "Strong" if "Strong" in parts else "Needs Work"
                    suggestion = parts.replace("Strong", "").replace("Needs Work", "").strip(" -")
                    analysis["criteria"][criterion.lower()] = {
                        "rating": rating,
                        "suggestion": suggestion or None,
                    }
            if line.upper().startswith("REFINED_GOAL:"):
                analysis["refined_goal"] = line.split(":", 1)[1].strip()

        return Result.ok(analysis)

    # ========================================================================
    # ACHIEVEMENT STRATEGY
    # ========================================================================

    async def suggest_achievement_strategy(self, goal_uid: str) -> Result[dict[str, Any]]:
        """
        Generate an AI-powered achievement strategy for a goal.

        Provides habits to build, tasks to complete, and knowledge to acquire.

        Args:
            goal_uid: Goal to strategize for

        Returns:
            Result containing strategy with habits, tasks, and knowledge recommendations
        """
        goal_result = await self.backend.get(goal_uid)
        if goal_result.is_error:
            return Result.fail(goal_result.expect_error())

        goal = goal_result.value
        if not goal:
            return Result.fail(Errors.not_found(resource="Goal", identifier=goal_uid))

        context = {
            "title": goal.title,
            "description": goal.description or "No description",
            "timeframe": goal.timeframe.value if goal.timeframe else "Not specified",
            "domain": goal.domain.value if goal.domain else "General",
        }

        prompt = """Create an achievement strategy for this goal.

Suggest 2-3 items for each category:

HABITS: Daily/weekly habits that support this goal
TASKS: Specific one-time tasks to complete
KNOWLEDGE: Skills or knowledge areas to develop

Format:
HABIT: [habit description]
TASK: [task description]
KNOWLEDGE: [knowledge/skill area]"""

        insight_result = await self._generate_insight(prompt, context=context, max_tokens=400)
        if insight_result.is_error:
            return Result.fail(insight_result.expect_error())

        response = insight_result.value
        strategy: dict[str, Any] = {
            "goal_uid": goal_uid,
            "habits": [],
            "tasks": [],
            "knowledge": [],
        }

        for line in response.split("\n"):
            line = line.strip()
            if line.upper().startswith("HABIT:"):
                strategy["habits"].append(line.split(":", 1)[1].strip())
            elif line.upper().startswith("TASK:"):
                strategy["tasks"].append(line.split(":", 1)[1].strip())
            elif line.upper().startswith("KNOWLEDGE:"):
                strategy["knowledge"].append(line.split(":", 1)[1].strip())

        return Result.ok(strategy)
