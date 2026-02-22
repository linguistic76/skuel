"""
Choices AI Service
==================

AI-powered features for Choices domain (requires LLM/Embeddings).

Created: January 2026
Purpose: Separate AI features from graph analytics (ADR-030)

AI services are OPTIONAL - the app functions fully without them.
They enhance the user experience but are not required for core functionality.
"""

from typing import TYPE_CHECKING, Any

from core.models.ku.ku import Ku
from core.models.ku.ku_choice import ChoiceKu
from core.services.base_ai_service import BaseAIService
from core.utils.result_simplified import Errors, Result

if TYPE_CHECKING:
    from core.services.llm_service import LLMService
    from core.services.neo4j_genai_embeddings_service import Neo4jGenAIEmbeddingsService
    from core.services.protocols import BackendOperations


class ChoicesAIService(BaseAIService["BackendOperations[Ku]", Ku]):
    """
    AI-powered features for Choices domain.

    This service is OPTIONAL - the app works without it.
    Provides enhanced features using LLM and embeddings.

    AI features:
    - Semantic choice similarity
    - Decision framework suggestions
    - Alternative generation
    - Outcome prediction insights
    """

    _service_name = "choices.ai"

    def __init__(
        self,
        backend: "BackendOperations[Ku]",
        llm_service: "LLMService",
        embeddings_service: "Neo4jGenAIEmbeddingsService",
        event_bus: Any | None = None,
    ) -> None:
        super().__init__(
            backend=backend,
            llm_service=llm_service,
            embeddings_service=embeddings_service,
            event_bus=event_bus,
        )

    async def find_similar_choices(
        self, choice_uid: str, limit: int = 5
    ) -> Result[list[tuple[str, float]]]:
        """Find semantically similar past choices using embeddings."""
        choice_result = await self.backend.get(choice_uid)
        if choice_result.is_error:
            return Result.fail(choice_result.expect_error())

        choice = choice_result.value
        if not choice:
            return Result.fail(Errors.not_found(resource="Choice", identifier=choice_uid))

        search_text = f"{choice.title}"
        if choice.description:
            search_text += f" {choice.description}"

        all_choices_result = await self.backend.find_by(user_uid=choice.user_uid)
        if all_choices_result.is_error:
            return Result.fail(all_choices_result.expect_error())

        all_choices = all_choices_result.value or []
        candidates = [
            (c.uid, f"{c.title} {c.description or ''}") for c in all_choices if c.uid != choice_uid
        ]

        if not candidates:
            return Result.ok([])

        return await self._semantic_search(search_text, candidates, limit)

    async def suggest_decision_framework(self, choice_uid: str) -> Result[dict[str, Any]]:
        """Suggest a decision-making framework for this choice."""
        choice_result = await self.backend.get(choice_uid)
        if choice_result.is_error:
            return Result.fail(choice_result.expect_error())

        choice = choice_result.value
        if not choice or not isinstance(choice, ChoiceKu):
            return Result.fail(Errors.not_found(resource="Choice", identifier=choice_uid))

        context = {
            "title": choice.title,
            "description": choice.description or "No description",
            "priority": choice.priority if choice.priority else "medium",
            "choice_type": choice.choice_type.value if choice.choice_type else "multiple",
        }

        prompt = """Suggest a decision-making framework for this choice.

Provide:
1. FRAMEWORK: The recommended approach (e.g., "Pros/Cons", "10-10-10", "Reversibility Test")
2. WHY: Why this framework fits this decision
3. QUESTIONS: 3 key questions to ask yourself
4. CONSIDERATIONS: 2-3 factors to weigh

Format:
FRAMEWORK: [name]
WHY: [explanation]
QUESTION: [question 1]
QUESTION: [question 2]
QUESTION: [question 3]
CONSIDERATION: [factor 1]
CONSIDERATION: [factor 2]"""

        insight_result = await self._generate_insight(prompt, context=context, max_tokens=350)
        if insight_result.is_error:
            return Result.fail(insight_result.expect_error())

        response = insight_result.value
        framework: dict[str, Any] = {
            "choice_uid": choice_uid,
            "framework_name": None,
            "rationale": None,
            "questions": [],
            "considerations": [],
        }

        for line in response.split("\n"):
            line = line.strip()
            if line.upper().startswith("FRAMEWORK:"):
                framework["framework_name"] = line.split(":", 1)[1].strip()
            elif line.upper().startswith("WHY:"):
                framework["rationale"] = line.split(":", 1)[1].strip()
            elif line.upper().startswith("QUESTION:"):
                framework["questions"].append(line.split(":", 1)[1].strip())
            elif line.upper().startswith("CONSIDERATION:"):
                framework["considerations"].append(line.split(":", 1)[1].strip())

        return Result.ok(framework)

    async def generate_alternatives(
        self, choice_uid: str, num_alternatives: int = 3
    ) -> Result[list[dict[str, str]]]:
        """Generate alternative options for a choice."""
        choice_result = await self.backend.get(choice_uid)
        if choice_result.is_error:
            return Result.fail(choice_result.expect_error())

        choice = choice_result.value
        if not choice or not isinstance(choice, ChoiceKu):
            return Result.fail(Errors.not_found(resource="Choice", identifier=choice_uid))

        context = {
            "title": choice.title,
            "description": choice.description or "No description",
            "current_options": ", ".join(str(o) for o in choice.options)
            if choice.options
            else "Not specified",
        }

        prompt = f"""Generate {num_alternatives} alternative approaches for this decision.

For each alternative:
1. A clear name/description
2. Key advantage
3. Key tradeoff

Format:
ALTERNATIVE: [name/description]
ADVANTAGE: [key benefit]
TRADEOFF: [key downside or consideration]"""

        insight_result = await self._generate_insight(prompt, context=context, max_tokens=350)
        if insight_result.is_error:
            return Result.fail(insight_result.expect_error())

        response = insight_result.value
        alternatives = []
        current_alt: dict[str, str] = {}

        for line in response.split("\n"):
            line = line.strip()
            if line.upper().startswith("ALTERNATIVE:"):
                if current_alt:
                    alternatives.append(current_alt)
                current_alt = {"description": line.split(":", 1)[1].strip()}
            elif line.upper().startswith("ADVANTAGE:"):
                if current_alt:
                    current_alt["advantage"] = line.split(":", 1)[1].strip()
            elif line.upper().startswith("TRADEOFF:"):
                if current_alt:
                    current_alt["tradeoff"] = line.split(":", 1)[1].strip()

        if current_alt and "description" in current_alt:
            alternatives.append(current_alt)

        return Result.ok(alternatives[:num_alternatives])

    async def generate_choice_insight(self, choice_uid: str) -> Result[str]:
        """Generate AI-written insight about a choice."""
        choice_result = await self.backend.get(choice_uid)
        if choice_result.is_error:
            return Result.fail(choice_result.expect_error())

        choice = choice_result.value
        if not choice:
            return Result.fail(Errors.not_found(resource="Choice", identifier=choice_uid))

        context = {
            "title": choice.title,
            "description": choice.description or "No description",
            "status": choice.status.value if choice.status else "pending",
            "priority": choice.priority if choice.priority else "medium",
        }

        prompt = """Provide a brief insight about this decision.
Focus on:
1. What makes this decision significant
2. One key factor to consider
3. A perspective shift that might help
Keep it under 100 words."""

        return await self._generate_insight(prompt, context=context, max_tokens=200)
