"""
LP (Learning Paths) AI Service
==============================

AI-powered features for Learning Paths domain (requires LLM/Embeddings).

Created: January 2026
Purpose: Separate AI features from graph analytics (ADR-030)

AI services are OPTIONAL - the app functions fully without them.
They enhance the user experience but are not required for core functionality.

NOTE: LP is a Curriculum domain - content is SHARED (no user_uid ownership).
"""

from typing import TYPE_CHECKING, Any

from core.models.pathways.learning_path import LearningPath
from core.ports import LpOperations
from core.services.base_ai_service import BaseAIService
from core.utils.result_simplified import Errors, Result

if TYPE_CHECKING:
    from core.services.embeddings_service import HuggingFaceEmbeddingsService
    from core.services.llm_service import LLMService


class LpAIService(BaseAIService[LpOperations, LearningPath]):
    """
    AI-powered features for Learning Paths domain.

    This service is OPTIONAL - the app works without it.
    Provides enhanced features using LLM and embeddings.

    AI features:
    - Semantic path similarity
    - Path overview generation
    - Completion strategy suggestions
    - Adaptive pacing recommendations
    """

    _service_name = "lp.ai"

    def __init__(
        self,
        backend: LpOperations,
        llm_service: "LLMService",
        embeddings_service: "HuggingFaceEmbeddingsService",
        event_bus: Any | None = None,
    ) -> None:
        super().__init__(
            backend=backend,
            llm_service=llm_service,
            embeddings_service=embeddings_service,
            event_bus=event_bus,
        )

    async def find_similar_paths(
        self, lp_uid: str, limit: int = 5
    ) -> Result[list[tuple[str, float]]]:
        """Find semantically similar learning paths using embeddings."""
        lp_result = await self.backend.get(lp_uid)
        if lp_result.is_error:
            return Result.fail(lp_result.expect_error())

        lp = lp_result.value
        if not lp:
            return Result.fail(Errors.not_found(resource="LearningPath", identifier=lp_uid))

        search_text = f"{lp.title}"
        if lp.description:
            search_text += f" {lp.description}"
        if lp.outcomes:
            search_text += f" {' '.join(lp.outcomes[:3])}"

        all_paths_result = await self.backend.list(limit=100)
        if all_paths_result.is_error:
            return Result.fail(all_paths_result.expect_error())

        all_paths: list[LearningPath] = all_paths_result.value or []
        candidates = [
            (p.uid, f"{p.title} {p.description or ''}") for p in all_paths if p.uid != lp_uid
        ]

        if not candidates:
            return Result.ok([])

        return await self._semantic_search(search_text, candidates, limit)

    async def generate_path_overview(self, lp_uid: str) -> Result[dict[str, Any]]:
        """Generate an AI-powered overview of a learning path."""
        lp_result = await self.backend.get(lp_uid)
        if lp_result.is_error:
            return Result.fail(lp_result.expect_error())

        lp = lp_result.value
        if not lp:
            return Result.fail(Errors.not_found(resource="LearningPath", identifier=lp_uid))

        outcomes = ", ".join(lp.outcomes) if lp.outcomes else "Not specified"

        context = {
            "name": lp.title,
            "goal": lp.description or "No goal specified",
            "domain": lp.domain.value if lp.domain else "General",
            "estimated_hours": lp.estimated_hours or "Not specified",
            "outcomes": outcomes,
        }

        prompt = """Create an engaging overview of this learning path.

Provide:
1. HOOK: A compelling 1-sentence hook about why this path matters
2. WHO_ITS_FOR: Who would benefit most from this path
3. WHAT_YOULL_LEARN: Key skills/knowledge (3-4 bullet points)
4. COMMITMENT: Realistic time/effort expectation
5. OUTCOME: What success looks like after completion

Format each section with its label."""

        insight_result = await self._generate_insight(prompt, context=context, max_tokens=400)
        if insight_result.is_error:
            return Result.fail(insight_result.expect_error())

        response = insight_result.value
        overview: dict[str, Any] = {
            "lp_uid": lp_uid,
            "lp_name": lp.title,
        }

        key_mapping = {
            "HOOK": "hook",
            "WHO_ITS_FOR": "target_audience",
            "WHAT_YOULL_LEARN": "key_learnings",
            "COMMITMENT": "commitment",
            "OUTCOME": "success_outcome",
        }

        for line in response.split("\n"):
            line = line.strip()
            for key, field in key_mapping.items():
                if line.upper().startswith(f"{key}:"):
                    overview[field] = line.split(":", 1)[1].strip()

        return Result.ok(overview)

    async def suggest_completion_strategy(self, lp_uid: str) -> Result[dict[str, Any]]:
        """Suggest a strategy for completing a learning path."""
        lp_result = await self.backend.get(lp_uid)
        if lp_result.is_error:
            return Result.fail(lp_result.expect_error())

        lp = lp_result.value
        if not lp:
            return Result.fail(Errors.not_found(resource="LearningPath", identifier=lp_uid))

        context = {
            "name": lp.title,
            "estimated_hours": lp.estimated_hours or "Unknown",
            "difficulty": getattr(lp, "step_difficulty", None) or "intermediate",
        }

        prompt = """Create a completion strategy for this learning path.

Provide:
1. PACE: Recommended pace (hours per day/week)
2. SCHEDULE: Suggested schedule pattern (e.g., "30 min daily" or "2 hours on weekends")
3. FOCUS_TIP: One key tip for staying focused
4. CHALLENGE: The most likely challenge and how to overcome it
5. MILESTONE: A meaningful mid-point milestone to celebrate

Format each as KEY: [response]"""

        insight_result = await self._generate_insight(prompt, context=context, max_tokens=350)
        if insight_result.is_error:
            return Result.fail(insight_result.expect_error())

        response = insight_result.value
        strategy: dict[str, Any] = {
            "lp_uid": lp_uid,
            "lp_name": lp.title,
        }

        key_mapping = {
            "PACE": "recommended_pace",
            "SCHEDULE": "schedule_pattern",
            "FOCUS_TIP": "focus_tip",
            "CHALLENGE": "likely_challenge",
            "MILESTONE": "mid_point_milestone",
        }

        for line in response.split("\n"):
            line = line.strip()
            for key, field in key_mapping.items():
                if line.upper().startswith(f"{key}:"):
                    strategy[field] = line.split(":", 1)[1].strip()

        return Result.ok(strategy)

    async def generate_path_insight(self, lp_uid: str) -> Result[str]:
        """Generate AI-written insight about a learning path."""
        lp_result = await self.backend.get(lp_uid)
        if lp_result.is_error:
            return Result.fail(lp_result.expect_error())

        lp = lp_result.value
        if not lp:
            return Result.fail(Errors.not_found(resource="LearningPath", identifier=lp_uid))

        context = {
            "name": lp.title,
            "domain": lp.domain.value if lp.domain else "General",
            "estimated_hours": lp.estimated_hours or "Unknown",
        }

        prompt = """Provide a brief, motivating insight about this learning path.
Focus on:
1. The transformation this path enables
2. One encouraging thought for someone starting
Keep it under 100 words."""

        return await self._generate_insight(prompt, context=context, max_tokens=200)
