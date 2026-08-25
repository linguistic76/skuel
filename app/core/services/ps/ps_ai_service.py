"""
PathStep AI Service
===================

AI-powered features for PathStep domain (requires LLM/Embeddings).

Purpose: Separate AI features from graph analytics (ADR-030)

AI services are OPTIONAL - the app functions fully without them.
They enhance the user experience but are not required for core functionality.

NOTE: PS is a Curriculum domain - content is SHARED (no user_uid ownership).
"""

import json
from typing import TYPE_CHECKING, Any

from core.models.enums.entity_enums import EntityType
from core.models.pathways.path_step import PathStep
from core.models.type_hints import EntityUID
from core.ports import PsOperations
from core.ports.query_types import StepApplicationsResult, StepLearningSequenceResult
from core.services.base_ai_service import BaseAIService
from core.utils.result_simplified import Errors, Result

if TYPE_CHECKING:
    from core.services.embeddings_service import EmbeddingsService
    from core.services.llm_service import LLMService


class PsAIService(BaseAIService[PsOperations, PathStep]):
    """
    AI-powered features for PathStep domain.

    This service is OPTIONAL - the app works without it.
    Provides enhanced features using LLM and embeddings.

    AI features:
    - Semantic step similarity
    - Step explanation at different levels
    - Practice activity suggestions
    - Application suggestions across activity domains
    - Learning sequence recommendations
    """

    _service_name = "ps.ai"

    def __init__(
        self,
        backend: PsOperations,
        llm_service: "LLMService",
        embeddings_service: "EmbeddingsService",
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
    ) -> Result[list[tuple[EntityUID, float]]]:
        """Find semantically similar path steps using embeddings."""
        ps_result = await self.backend.get(ps_uid)
        if ps_result.is_error:
            return Result.fail(ps_result)

        ps = ps_result.value
        if not ps:
            return Result.fail(Errors.not_found(resource="PathStep", identifier=ps_uid))

        all_steps_result = await self.backend.list(limit=200)
        if all_steps_result.is_error:
            return Result.fail(all_steps_result)

        all_steps_data, _count = all_steps_result.value
        return await self._rank_similar_entities(
            ps,
            EntityType.PATH_STEP,
            all_steps_data or [],
            exclude_uid=ps_uid,
            limit=limit,
        )

    async def explain_step(self, ps_uid: str, target_level: str = "standard") -> Result[str]:
        """Generate an AI-powered explanation of a path step.

        Args:
            ps_uid: PathStep identifier
            target_level: Explanation depth/audience. Values:
                - "beginner": Simple language, foundational context, no assumed knowledge
                - "standard": Clear explanation with key points (default)
                - "intermediate": Assumes familiarity, focuses on nuance
                - "advanced": In-depth, technical, connects to broader concepts
                - "brief": 2-3 sentence overview
                - "detailed": Comprehensive explanation with examples
        """
        ps_result = await self.backend.get(ps_uid)
        if ps_result.is_error:
            return Result.fail(ps_result)

        ps = ps_result.value
        if not ps:
            return Result.fail(Errors.not_found(resource="PathStep", identifier=ps_uid))

        level_guidance = {
            "beginner": "Use simple language. Assume no prior knowledge. Explain why this matters in everyday terms.",
            "standard": "Provide a clear explanation with key points.",
            "intermediate": "Assume some familiarity with the domain. Focus on nuance and connections.",
            "advanced": "Go in-depth. Connect to broader concepts and practical applications at a high level.",
            "brief": "Provide a 2-3 sentence overview.",
            "detailed": "Provide a comprehensive explanation with examples.",
        }

        context = {
            "title": ps.title,
            "intent": ps.intent or "Not specified",
            "description": ps.description or "No description",
            "estimated_time": f"{ps.estimated_hours or 1.0} hours",
        }

        guidance = level_guidance.get(target_level, level_guidance["standard"])

        prompt = f"""Explain this path step. {guidance}

Focus on:
1. What the learner will understand or be able to do
2. Why this step matters in the learning journey
3. How to approach this step effectively"""

        return await self._generate_insight(prompt, context=context, max_tokens=300)

    async def suggest_practice_activities(
        self, ps_uid: str, num_activities: int = 3
    ) -> Result[list[dict[str, str]]]:
        """Suggest practice activities for a path step.

        Returns a list of activity dicts with keys: name, type, description.
        """
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

Return ONLY valid JSON in this exact shape:
{{
  "activities": [
    {{
      "name": "activity name",
      "type": "hands-on | reflective | applied | creative",
      "description": "what the learner should do"
    }}
  ]
}}

Each activity must be specific, actionable, and varied in type."""

        insight_result = await self._generate_insight(prompt, context=context, max_tokens=400)
        if insight_result.is_error:
            return Result.fail(insight_result)

        try:
            raw = insight_result.value
            # Strip markdown code fences if present
            if "```" in raw:
                raw = raw.split("```")[1]
                raw = raw.removeprefix("json")
            parsed = json.loads(raw.strip())
            activities: list[dict[str, str]] = parsed.get("activities", [])
            return Result.ok(activities[:num_activities])
        except json.JSONDecodeError, KeyError, TypeError:
            return Result.fail(
                Errors.integration(
                    message="LLM returned malformed JSON for practice activities",
                    operation="suggest_practice_activities",
                    service="llm",
                )
            )

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

    async def suggest_step_applications(self, ps_uid: str) -> Result[StepApplicationsResult]:
        """Suggest how to apply this path step across activity domains.

        Returns categorized suggestions:
        - tasks: concrete tasks to create
        - habits: habits to build that reinforce this knowledge
        - goals: goals that this step can help achieve
        - real_world_examples: real-world situations where this applies
        """
        ps_result = await self.backend.get(ps_uid)
        if ps_result.is_error:
            return Result.fail(ps_result)

        ps = ps_result.value
        if not ps:
            return Result.fail(Errors.not_found(resource="PathStep", identifier=ps_uid))

        context = {
            "title": ps.title,
            "intent": ps.intent or "Not specified",
            "description": (ps.description or "")[:1500],
            "domain": ps.domain.value if ps.domain else "General",
        }

        prompt = """Suggest practical applications for this path step across different life domains.

Return ONLY valid JSON in this exact shape:
{
  "tasks": ["specific task 1", "specific task 2", "specific task 3"],
  "habits": ["habit to build 1", "habit to build 2", "habit to build 3"],
  "goals": ["goal this enables 1", "goal this enables 2", "goal this enables 3"],
  "real_world_examples": ["real situation 1", "real situation 2", "real situation 3"]
}

Each item should be concrete and actionable, not generic."""

        insight_result = await self._generate_insight(prompt, context=context, max_tokens=500)
        if insight_result.is_error:
            return Result.fail(insight_result)

        try:
            raw = insight_result.value
            if "```" in raw:
                raw = raw.split("```")[1]
                raw = raw.removeprefix("json")
            parsed = json.loads(raw.strip())
            result: StepApplicationsResult = {
                "ps_uid": ps_uid,
                "ps_title": ps.title,
                "tasks": parsed.get("tasks", [])[:3],
                "habits": parsed.get("habits", [])[:3],
                "goals": parsed.get("goals", [])[:3],
                "real_world_examples": parsed.get("real_world_examples", [])[:3],
            }
            return Result.ok(result)
        except json.JSONDecodeError, KeyError, TypeError:
            return Result.fail(
                Errors.integration(
                    message="LLM returned malformed JSON for step applications",
                    operation="suggest_step_applications",
                    service="llm",
                )
            )

    async def search_by_semantic_query(
        self, query_text: str, limit: int = 20, min_score: float = 0.5
    ) -> Result[list[PathStep]]:
        """Search path steps by semantic meaning using embeddings.

        FULL tier only — this is the `.ai` sub-service, which is `None` in CORE, so
        no CORE caller reaches here. The keyword fallback below is an
        EMBEDDING-FAILURE fallback within FULL (the similarity call errored), not a
        tier fallback; it is also the one production caller of the backend's
        case-SENSITIVE `_SearchMixin.search`, which is on neither `/search` nor
        `/api/search/unified`.

        Args:
            query_text: Natural language query
            limit: Maximum results
            min_score: Minimum similarity score (0.0-1.0)

        Returns:
            Result with list of PathSteps ranked by semantic relevance
        """
        all_steps_result = await self.backend.list(limit=500)
        if all_steps_result.is_error:
            return Result.fail(all_steps_result)

        all_steps_data, _count = all_steps_result.value
        all_steps: list[PathStep] = all_steps_data or []

        if not all_steps:
            return Result.ok([])

        candidates = [
            (s.uid, f"{s.title} {s.intent or ''} {s.description or ''}") for s in all_steps
        ]

        similarity_result = await self._semantic_search(query_text, candidates, limit * 2)
        if similarity_result.is_error:
            # Embedding-failure fallback (NOT a tier fallback — see the docstring)
            search_result = await self.backend.search(query_text, limit=limit)
            if search_result.is_error:
                return Result.fail(search_result)
            keyword_steps = search_result.value
            return Result.ok(keyword_steps or [])

        uid_score_pairs = similarity_result.value or []
        uid_by_score = {uid: score for uid, score in uid_score_pairs if score >= min_score}

        def get_similarity_score(step: PathStep) -> float:
            return uid_by_score.get(step.uid, 0.0)

        ranked = [s for s in all_steps if s.uid in uid_by_score]
        ranked.sort(key=get_similarity_score, reverse=True)
        return Result.ok(ranked[:limit])

    async def suggest_learning_sequence(
        self, ps_uid: str, max_suggestions: int = 5
    ) -> Result[StepLearningSequenceResult]:
        """Suggest prerequisite and next steps for this path step.

        Returns:
            StepLearningSequenceResult with:
            - prerequisites: steps the learner should complete before this one
            - next_steps: steps to pursue after completing this one
            Each item has a title and a reason why it's recommended.
        """
        ps_result = await self.backend.get(ps_uid)
        if ps_result.is_error:
            return Result.fail(ps_result)

        ps = ps_result.value
        if not ps:
            return Result.fail(Errors.not_found(resource="PathStep", identifier=ps_uid))

        context = {
            "title": ps.title,
            "intent": ps.intent or "Not specified",
            "description": (ps.description or "")[:1500],
            "domain": ps.domain.value if ps.domain else "General",
        }

        prompt = f"""Suggest a learning sequence for this path step (up to {max_suggestions} items each).

Return ONLY valid JSON in this exact shape:
{{
  "prerequisites": [
    {{"title": "prerequisite step title", "reason": "why this should come first"}}
  ],
  "next_steps": [
    {{"title": "next step title", "reason": "why this builds on the current step"}}
  ]
}}

Prerequisites: foundational knowledge needed before this step.
Next steps: natural progressions after mastering this step."""

        insight_result = await self._generate_insight(prompt, context=context, max_tokens=600)
        if insight_result.is_error:
            return Result.fail(insight_result)

        try:
            raw = insight_result.value
            if "```" in raw:
                raw = raw.split("```")[1]
                raw = raw.removeprefix("json")
            parsed = json.loads(raw.strip())
            result: StepLearningSequenceResult = {
                "ps_uid": ps_uid,
                "ps_title": ps.title,
                "prerequisites": parsed.get("prerequisites", [])[:max_suggestions],
                "next_steps": parsed.get("next_steps", [])[:max_suggestions],
            }
            return Result.ok(result)
        except json.JSONDecodeError, KeyError, TypeError:
            return Result.fail(
                Errors.integration(
                    message="LLM returned malformed JSON for learning sequence",
                    operation="suggest_learning_sequence",
                    service="llm",
                )
            )
