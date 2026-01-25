"""
Principles AI Service
=====================

AI-powered features for Principles domain (requires LLM/Embeddings).

Created: January 2026
Purpose: Separate AI features from graph analytics (ADR-030)

AI services are OPTIONAL - the app functions fully without them.
They enhance the user experience but are not required for core functionality.
"""

from typing import TYPE_CHECKING, Any

from core.models.principle.principle import Principle
from core.services.base_ai_service import BaseAIService
from core.services.protocols import PrinciplesOperations
from core.utils.result_simplified import Errors, Result

if TYPE_CHECKING:
    from core.services.embeddings_service import OpenAIEmbeddingsService
    from core.services.llm_service import LLMService


class PrinciplesAIService(BaseAIService[PrinciplesOperations, Principle]):
    """
    AI-powered features for Principles domain.

    This service is OPTIONAL - the app works without it.
    Provides enhanced features using LLM and embeddings.

    AI features:
    - Semantic principle similarity
    - Value clarification support
    - Principle alignment analysis
    - Application suggestions
    """

    _service_name = "principles.ai"
    _require_llm = True
    _require_embeddings = True

    def __init__(
        self,
        backend: PrinciplesOperations,
        llm_service: "LLMService",
        embeddings_service: "OpenAIEmbeddingsService",
        event_bus: Any | None = None,
    ) -> None:
        super().__init__(
            backend=backend,
            llm_service=llm_service,
            embeddings_service=embeddings_service,
            event_bus=event_bus,
        )

    async def find_similar_principles(
        self, principle_uid: str, limit: int = 5
    ) -> Result[list[tuple[str, float]]]:
        """Find semantically similar principles using embeddings."""
        principle_result = await self.backend.get(principle_uid)
        if principle_result.is_error:
            return Result.fail(principle_result.expect_error())

        principle = principle_result.value
        if not principle:
            return Result.fail(Errors.not_found(resource="Principle", identifier=principle_uid))

        search_text = f"{principle.name}"
        if principle.description:
            search_text += f" {principle.description}"

        all_principles_result = await self.backend.find_by(user_uid=principle.user_uid)
        if all_principles_result.is_error:
            return Result.fail(all_principles_result.expect_error())

        all_principles = all_principles_result.value or []
        candidates = [
            (p.uid, f"{p.name} {p.description or ''}")
            for p in all_principles
            if p.uid != principle_uid
        ]

        if not candidates:
            return Result.ok([])

        return await self._semantic_search(search_text, candidates, limit)

    async def deepen_principle(self, principle_uid: str) -> Result[dict[str, Any]]:
        """Generate deeper understanding of a principle."""
        principle_result = await self.backend.get(principle_uid)
        if principle_result.is_error:
            return Result.fail(principle_result.expect_error())

        principle = principle_result.value
        if not principle:
            return Result.fail(Errors.not_found(resource="Principle", identifier=principle_uid))

        context = {
            "name": principle.name,
            "description": principle.description or "No description",
            "category": principle.category.value if principle.category else "personal",
        }

        prompt = """Help deepen understanding of this principle.

Provide:
1. ORIGIN: Where might this principle come from (personal experience, tradition, observation)?
2. WHEN_TESTED: When is this principle most challenged or tested?
3. OPPOSITE: What is the opposite belief, and why might someone hold it?
4. DAILY_APPLICATION: How might this show up in daily decisions?
5. GROWTH_EDGE: How might living this principle more fully lead to growth?

Format each as KEY: [response]"""

        insight_result = await self._generate_insight(prompt, context=context, max_tokens=400)
        if insight_result.is_error:
            return Result.fail(insight_result.expect_error())

        response = insight_result.value
        deepening: dict[str, Any] = {
            "principle_uid": principle_uid,
            "principle_name": principle.name,
        }

        key_mapping = {
            "ORIGIN": "origin",
            "WHEN_TESTED": "when_tested",
            "OPPOSITE": "opposite_view",
            "DAILY_APPLICATION": "daily_application",
            "GROWTH_EDGE": "growth_edge",
        }

        for line in response.split("\n"):
            line = line.strip()
            for key, field in key_mapping.items():
                if line.upper().startswith(f"{key}:"):
                    deepening[field] = line.split(":", 1)[1].strip()

        return Result.ok(deepening)

    async def suggest_practices(
        self, principle_uid: str, num_practices: int = 3
    ) -> Result[list[dict[str, str]]]:
        """Suggest practices to embody a principle more fully."""
        principle_result = await self.backend.get(principle_uid)
        if principle_result.is_error:
            return Result.fail(principle_result.expect_error())

        principle = principle_result.value
        if not principle:
            return Result.fail(Errors.not_found(resource="Principle", identifier=principle_uid))

        context = {
            "name": principle.name,
            "description": principle.description or "No description",
            "category": principle.category.value if principle.category else "personal",
        }

        prompt = f"""Suggest {num_practices} practices to embody this principle more fully.

Each practice should be:
- Specific and actionable
- Something that can be done regularly
- Connected to real-life situations

Format:
PRACTICE: [name]
HOW: [specific instruction]
WHEN: [when/where to apply it]"""

        insight_result = await self._generate_insight(prompt, context=context, max_tokens=350)
        if insight_result.is_error:
            return Result.fail(insight_result.expect_error())

        response = insight_result.value
        practices = []
        current_practice: dict[str, str] = {}

        for line in response.split("\n"):
            line = line.strip()
            if line.upper().startswith("PRACTICE:"):
                if current_practice:
                    practices.append(current_practice)
                current_practice = {"name": line.split(":", 1)[1].strip()}
            elif line.upper().startswith("HOW:"):
                if current_practice:
                    current_practice["how"] = line.split(":", 1)[1].strip()
            elif line.upper().startswith("WHEN:"):
                if current_practice:
                    current_practice["when"] = line.split(":", 1)[1].strip()

        if current_practice and "name" in current_practice:
            practices.append(current_practice)

        return Result.ok(practices[:num_practices])

    async def generate_principle_insight(self, principle_uid: str) -> Result[str]:
        """Generate AI-written insight about a principle."""
        principle_result = await self.backend.get(principle_uid)
        if principle_result.is_error:
            return Result.fail(principle_result.expect_error())

        principle = principle_result.value
        if not principle:
            return Result.fail(Errors.not_found(resource="Principle", identifier=principle_uid))

        context = {
            "name": principle.name,
            "description": principle.description or "No description",
            "strength": f"{(principle.strength or 0.5) * 100:.0f}%",
        }

        prompt = """Provide a brief, meaningful insight about living this principle.
Focus on:
1. What living this principle reveals about character
2. A challenge or paradox within this principle
Keep it reflective and under 100 words."""

        return await self._generate_insight(prompt, context=context, max_tokens=200)
