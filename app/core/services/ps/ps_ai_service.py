"""
LS (Learning Steps) AI Service
==============================

AI-powered features for Learning Steps domain (requires LLM/Embeddings).

Created: January 2026
Purpose: Separate AI features from graph analytics (ADR-030)

AI services are OPTIONAL - the app functions fully without them.
They enhance the user experience but are not required for core functionality.

NOTE: LS is a Curriculum domain - content is SHARED (no user_uid ownership).
"""

from typing import TYPE_CHECKING, Any

from core.models.pathways.path_step import PathStep
from core.ports import PsOperations
from core.services.base_ai_service import BaseAIService
from core.utils.result_simplified import Errors, Result

if TYPE_CHECKING:
    from core.services.embeddings_service import HuggingFaceEmbeddingsService
    from core.services.llm_service import LLMService


class PsAIService(BaseAIService[PsOperations, PathStep]):
    """
    AI-powered features for Learning Steps domain.

    This service is OPTIONAL - the app works without it.
    Provides enhanced features using LLM and embeddings.

    AI features:
    - Semantic step similarity
    - Step explanation at different levels
    - Practice activity suggestions
    - Prerequisite recommendations
    """

    _service_name = "ps.ai"

    def __init__(
        self,
        backend: PsOperations,
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

    async def find_similar_steps(
        self, ps_uid: str, limit: int = 5
    ) -> Result[list[tuple[str, float]]]:
        """Find semantically similar path steps using embeddings."""
        ps_result = await self.backend.get(ps_uid)
        if ps_result.is_error:
            return Result.fail(ps_result)

        ps = ps_result.value
        if not ps:
            return Result.fail(Errors.not_found(resource="PathStep", identifier=ps_uid))

        search_text = f"{ps.title}"
        if ps.intent:
            search_text += f" {ps.intent}"
        if ps.description:
            search_text += f" {ps.description}"

        all_steps_result = await self.backend.list(limit=200)
        if all_steps_result.is_error:
            return Result.fail(all_steps_result)

        all_steps_data, _count = all_steps_result.value
        all_steps: list[PathStep] = all_steps_data or []
        candidates = [
            (s.uid, f"{s.title} {s.intent or ''} {s.description or ''}")
            for s in all_steps
            if s.uid != ps_uid
        ]

        if not candidates:
            return Result.ok([])

        return await self._semantic_search(search_text, candidates, limit)

    async def explain_step(self, ps_uid: str, detail_level: str = "standard") -> Result[str]:
        """Generate an AI-powered explanation of a path step."""
        ps_result = await self.backend.get(ps_uid)
        if ps_result.is_error:
            return Result.fail(ps_result)

        ps = ps_result.value
        if not ps:
            return Result.fail(Errors.not_found(resource="PathStep", identifier=ps_uid))

        level_guidance = {
            "brief": "Provide a 2-3 sentence overview.",
            "standard": "Provide a clear explanation with key points.",
            "detailed": "Provide a comprehensive explanation with examples.",
        }

        context = {
            "title": ps.title,
            "intent": ps.intent or "Not specified",
            "description": ps.description or "No description",
            "estimated_time": f"{ps.estimated_hours or 1.0} hours",
        }

        guidance = level_guidance.get(detail_level, level_guidance["standard"])

        prompt = f"""Explain this path step. {guidance}

Focus on:
1. What the learner will understand or be able to do
2. Why this step matters in the learning journey
3. How to approach this step effectively"""

        return await self._generate_insight(prompt, context=context, max_tokens=300)

    async def suggest_practice_activities(
        self, ps_uid: str, num_activities: int = 3
    ) -> Result[list[dict[str, str]]]:
        """Suggest practice activities for a path step."""
        ps_result = await self.backend.get(ps_uid)
        if ps_result.is_error:
            return Result.fail(ps_result)

        ps = ps_result.value
        if not ps:
            return Result.fail(Errors.not_found(resource="PathStep", identifier=ps_uid))

        context = {
            "title": ps.title,
            "intent": ps.intent or "Not specified",
            "description": ps.description or "No description",
        }

        prompt = f"""Suggest {num_activities} practice activities for this path step.

Each activity should:
- Be specific and actionable
- Help reinforce the learning
- Vary in type (some hands-on, some reflective, some applied)

Format:
ACTIVITY: [name]
TYPE: [hands-on/reflective/applied/creative]
DESCRIPTION: [what to do]"""

        insight_result = await self._generate_insight(prompt, context=context, max_tokens=350)
        if insight_result.is_error:
            return Result.fail(insight_result)

        response = insight_result.value
        activities = []
        current_activity: dict[str, str] = {}

        for line in response.split("\n"):
            line = line.strip()
            if line.upper().startswith("ACTIVITY:"):
                if current_activity:
                    activities.append(current_activity)
                current_activity = {"name": line.split(":", 1)[1].strip()}
            elif line.upper().startswith("TYPE:"):
                if current_activity:
                    current_activity["type"] = line.split(":", 1)[1].strip()
            elif line.upper().startswith("DESCRIPTION:"):
                if current_activity:
                    current_activity["description"] = line.split(":", 1)[1].strip()

        if current_activity and "name" in current_activity:
            activities.append(current_activity)

        return Result.ok(activities[:num_activities])

    async def generate_step_insight(self, ps_uid: str) -> Result[str]:
        """Generate AI-written insight about a path step."""
        ps_result = await self.backend.get(ps_uid)
        if ps_result.is_error:
            return Result.fail(ps_result)

        ps = ps_result.value
        if not ps:
            return Result.fail(Errors.not_found(resource="PathStep", identifier=ps_uid))

        context = {
            "title": ps.title,
            "intent": ps.intent or "Not specified",
            "sequence": ps.sequence if ps.sequence else "Standalone",
        }

        prompt = """Provide a brief, encouraging insight about this path step.
Focus on:
1. The value of mastering this step
2. A tip for staying motivated
Keep it under 100 words."""

        return await self._generate_insight(prompt, context=context, max_tokens=200)
