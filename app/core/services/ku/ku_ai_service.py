"""
KU AI Service
=============

AI-powered features for Knowledge Units domain (requires LLM/Embeddings).

Created: January 2026
Purpose: Separate AI features from graph analytics (ADR-030)

AI services contain features that REQUIRE:
- embeddings_service (semantic search, similarity matching)
- llm_service (AI-generated insights, recommendations, natural language)

AI services are OPTIONAL - the app functions fully without them.
They enhance the user experience but are not required for core functionality.

This service explicitly DOES use:
- embeddings_service (semantic knowledge search, concept similarity)
- llm_service (AI-generated summaries, explanations, learning recommendations)

The app works WITHOUT this service. It's an enhancement layer.

NOTE: KU is a Curriculum domain - content is SHARED (no user_uid ownership).
"""

from typing import TYPE_CHECKING, Any

from core.models.ku.ku import Ku
from core.services.base_ai_service import BaseAIService
from core.services.protocols import KuOperations
from core.utils.result_simplified import Errors, Result

if TYPE_CHECKING:
    from core.services.embeddings_service import OpenAIEmbeddingsService
    from core.services.llm_service import LLMService


class KuAIService(BaseAIService[KuOperations, Ku]):
    """
    AI-powered features for Knowledge Units domain.

    This service is OPTIONAL - the app works without it.
    Provides enhanced features using LLM and embeddings.

    AI features:
    - Semantic knowledge search (find related KUs by meaning)
    - AI-generated content summaries
    - Concept explanation at different levels
    - Learning path suggestions
    - Knowledge gap identification

    NOTE: These features require LLM/embeddings services.
    If not available, this service won't be instantiated.
    """

    _service_name = "ku.ai"

    def __init__(
        self,
        backend: KuOperations,
        llm_service: "LLMService",
        embeddings_service: "OpenAIEmbeddingsService",
        event_bus: Any | None = None,
    ) -> None:
        """
        Initialize KU AI service.

        Args:
            backend: KU backend operations (protocol)
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
    # SEMANTIC SEARCH
    # ========================================================================

    async def find_related_knowledge(
        self, ku_uid: str, limit: int = 5
    ) -> Result[list[tuple[str, float]]]:
        """
        Find semantically related knowledge units using embeddings.

        Uses embeddings to find KUs with similar concepts/content,
        beyond just explicit graph relationships.

        Args:
            ku_uid: Knowledge unit to find related content for
            limit: Maximum number of related KUs to return

        Returns:
            Result containing list of (ku_uid, similarity_score) tuples
        """
        ku_result = await self.backend.get(ku_uid)
        if ku_result.is_error:
            return Result.fail(ku_result.expect_error())

        ku = ku_result.value
        if not ku:
            return Result.fail(Errors.not_found(resource="KnowledgeUnit", identifier=ku_uid))

        search_text = f"{ku.title} {ku.summary}"
        if ku.content:
            # Use first 500 chars of content for embedding
            search_text += f" {ku.content[:500]}"

        # Get all KUs in the same domain for comparison
        all_kus_result = await self.backend.find_by(domain=ku.domain)
        if all_kus_result.is_error:
            return Result.fail(all_kus_result.expect_error())

        all_kus = all_kus_result.value or []
        candidates = [
            (k.uid, f"{k.title} {k.summary} {k.content[:300] if k.content else ''}")
            for k in all_kus
            if k.uid != ku_uid
        ]

        if not candidates:
            return Result.ok([])

        return await self._semantic_search(search_text, candidates, limit)

    async def semantic_search(
        self, query: str, domain: str | None = None, limit: int = 10
    ) -> Result[list[tuple[str, float]]]:
        """
        Search knowledge units by semantic meaning.

        Uses embeddings to find KUs that match the query conceptually,
        not just by keyword matching.

        Args:
            query: Natural language search query
            domain: Optional domain filter
            limit: Maximum number of results

        Returns:
            Result containing list of (ku_uid, similarity_score) tuples
        """
        # Get KUs to search
        if domain:
            kus_result = await self.backend.find_by(domain=domain)
        else:
            kus_result = await self.backend.list(limit=500)  # Reasonable limit

        if kus_result.is_error:
            return Result.fail(kus_result.expect_error())

        kus = kus_result.value or []
        if not kus:
            return Result.ok([])

        candidates = [
            (k.uid, f"{k.title} {k.summary} {k.content[:300] if k.content else ''}") for k in kus
        ]

        return await self._semantic_search(query, candidates, limit)

    # ========================================================================
    # AI-GENERATED SUMMARIES
    # ========================================================================

    async def generate_summary(self, ku_uid: str, max_words: int = 100) -> Result[str]:
        """
        Generate an AI-powered summary of a knowledge unit.

        Uses LLM to create a concise, clear summary of the KU content.

        Args:
            ku_uid: Knowledge unit to summarize
            max_words: Maximum words in summary

        Returns:
            Result containing AI-generated summary
        """
        ku_result = await self.backend.get(ku_uid)
        if ku_result.is_error:
            return Result.fail(ku_result.expect_error())

        ku = ku_result.value
        if not ku:
            return Result.fail(Errors.not_found(resource="KnowledgeUnit", identifier=ku_uid))

        context = {
            "title": ku.title,
            "domain": ku.domain.value,
            "learning_level": ku.learning_level.value,
            "content": ku.content[:2000] if ku.content else "No content",
        }

        prompt = f"""Summarize this knowledge unit in {max_words} words or fewer.

Focus on:
1. The core concept being taught
2. Key takeaways for the learner
3. Why this knowledge matters

Be concise and educational."""

        return await self._generate_insight(prompt, context=context, max_tokens=200)

    # ========================================================================
    # CONCEPT EXPLANATION
    # ========================================================================

    async def explain_at_level(self, ku_uid: str, target_level: str = "beginner") -> Result[str]:
        """
        Explain a knowledge unit at a specified learning level.

        Uses LLM to adapt the explanation complexity.

        Args:
            ku_uid: Knowledge unit to explain
            target_level: Target level (beginner, intermediate, advanced)

        Returns:
            Result containing level-appropriate explanation
        """
        ku_result = await self.backend.get(ku_uid)
        if ku_result.is_error:
            return Result.fail(ku_result.expect_error())

        ku = ku_result.value
        if not ku:
            return Result.fail(Errors.not_found(resource="KnowledgeUnit", identifier=ku_uid))

        level_guidance = {
            "beginner": "Use simple language, analogies, and real-world examples. Avoid jargon.",
            "intermediate": "Include technical terms with brief explanations. Build on foundational concepts.",
            "advanced": "Use precise terminology. Focus on nuances, edge cases, and deeper implications.",
        }

        context = {
            "title": ku.title,
            "domain": ku.domain.value,
            "content": ku.content[:2000] if ku.content else "No content",
            "current_level": ku.learning_level.value,
        }

        guidance = level_guidance.get(target_level.lower(), level_guidance["intermediate"])

        prompt = f"""Explain this concept for a {target_level} learner.

{guidance}

Keep the explanation under 200 words. Make it engaging and memorable."""

        return await self._generate_insight(prompt, context=context, max_tokens=300)

    # ========================================================================
    # LEARNING RECOMMENDATIONS
    # ========================================================================

    async def suggest_learning_sequence(
        self, ku_uid: str, max_suggestions: int = 5
    ) -> Result[dict[str, Any]]:
        """
        Suggest a learning sequence starting from or leading to this KU.

        Uses LLM to recommend prerequisites and next steps.

        Args:
            ku_uid: Knowledge unit as reference point
            max_suggestions: Maximum suggestions per category

        Returns:
            Result containing before/after learning suggestions
        """
        ku_result = await self.backend.get(ku_uid)
        if ku_result.is_error:
            return Result.fail(ku_result.expect_error())

        ku = ku_result.value
        if not ku:
            return Result.fail(Errors.not_found(resource="KnowledgeUnit", identifier=ku_uid))

        context = {
            "title": ku.title,
            "domain": ku.domain.value,
            "learning_level": ku.learning_level.value,
            "summary": ku.summary or "No summary",
            "tags": ", ".join(ku.tags) if ku.tags else "None",
        }

        prompt = f"""Suggest a learning sequence for this knowledge unit.

Provide up to {max_suggestions} suggestions for each category:

PREREQUISITES: What should a learner know BEFORE this topic?
NEXT_STEPS: What should they learn AFTER mastering this?

Format each suggestion as:
PREREQ: [topic name] - [why it's needed]
NEXT: [topic name] - [why it follows naturally]"""

        insight_result = await self._generate_insight(prompt, context=context, max_tokens=400)
        if insight_result.is_error:
            return Result.fail(insight_result.expect_error())

        response = insight_result.value
        sequence: dict[str, Any] = {
            "ku_uid": ku_uid,
            "ku_title": ku.title,
            "prerequisites": [],
            "next_steps": [],
        }

        for line in response.split("\n"):
            line = line.strip()
            if line.upper().startswith("PREREQ:"):
                parts = line.split(":", 1)[1].strip()
                if " - " in parts:
                    topic, reason = parts.split(" - ", 1)
                    sequence["prerequisites"].append(
                        {"topic": topic.strip(), "reason": reason.strip()}
                    )
                else:
                    sequence["prerequisites"].append({"topic": parts, "reason": None})
            elif line.upper().startswith("NEXT:"):
                parts = line.split(":", 1)[1].strip()
                if " - " in parts:
                    topic, reason = parts.split(" - ", 1)
                    sequence["next_steps"].append(
                        {"topic": topic.strip(), "reason": reason.strip()}
                    )
                else:
                    sequence["next_steps"].append({"topic": parts, "reason": None})

        return Result.ok(sequence)

    # ========================================================================
    # KNOWLEDGE APPLICATION
    # ========================================================================

    async def suggest_applications(self, ku_uid: str) -> Result[dict[str, Any]]:
        """
        Suggest practical applications for this knowledge.

        Uses LLM to identify how this knowledge can be applied in tasks,
        habits, goals, and real-world scenarios.

        Args:
            ku_uid: Knowledge unit to find applications for

        Returns:
            Result containing application suggestions
        """
        ku_result = await self.backend.get(ku_uid)
        if ku_result.is_error:
            return Result.fail(ku_result.expect_error())

        ku = ku_result.value
        if not ku:
            return Result.fail(Errors.not_found(resource="KnowledgeUnit", identifier=ku_uid))

        context = {
            "title": ku.title,
            "domain": ku.domain.value,
            "content": ku.content[:1500] if ku.content else "No content",
        }

        prompt = """Suggest practical applications for this knowledge.

For each category, provide 2-3 specific suggestions:

TASKS: Specific one-time projects or tasks
HABITS: Daily/weekly practices to reinforce this knowledge
GOALS: Larger objectives this knowledge supports
REAL_WORLD: Real-world scenarios where this applies

Format:
TASK: [specific task]
HABIT: [specific habit]
GOAL: [specific goal]
REAL_WORLD: [scenario description]"""

        insight_result = await self._generate_insight(prompt, context=context, max_tokens=450)
        if insight_result.is_error:
            return Result.fail(insight_result.expect_error())

        response = insight_result.value
        applications: dict[str, Any] = {
            "ku_uid": ku_uid,
            "ku_title": ku.title,
            "tasks": [],
            "habits": [],
            "goals": [],
            "real_world": [],
        }

        for line in response.split("\n"):
            line = line.strip()
            if line.upper().startswith("TASK:"):
                applications["tasks"].append(line.split(":", 1)[1].strip())
            elif line.upper().startswith("HABIT:"):
                applications["habits"].append(line.split(":", 1)[1].strip())
            elif line.upper().startswith("GOAL:"):
                applications["goals"].append(line.split(":", 1)[1].strip())
            elif line.upper().startswith("REAL_WORLD:"):
                applications["real_world"].append(line.split(":", 1)[1].strip())

        return Result.ok(applications)
