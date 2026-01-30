"""
Events AI Service
=================

AI-powered features for Events domain (requires LLM/Embeddings).

Created: January 2026
Purpose: Separate AI features from graph analytics (ADR-030)

AI services are OPTIONAL - the app functions fully without them.
They enhance the user experience but are not required for core functionality.
"""

from typing import TYPE_CHECKING, Any

from core.models.event.event import Event
from core.services.base_ai_service import BaseAIService
from core.services.protocols import EventsOperations
from core.utils.result_simplified import Errors, Result

if TYPE_CHECKING:
    from core.services.llm_service import LLMService
    from core.services.neo4j_genai_embeddings_service import Neo4jGenAIEmbeddingsService


class EventsAIService(BaseAIService[EventsOperations, Event]):
    """
    AI-powered features for Events domain.

    This service is OPTIONAL - the app works without it.
    Provides enhanced features using LLM and embeddings.

    AI features:
    - Semantic event similarity
    - AI-generated event preparation suggestions
    - Learning practice recommendations
    - Event reflection prompts
    """

    _service_name = "events.ai"

    def __init__(
        self,
        backend: EventsOperations,
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

    async def find_similar_events(
        self, event_uid: str, limit: int = 5
    ) -> Result[list[tuple[str, float]]]:
        """Find semantically similar events using embeddings."""
        event_result = await self.backend.get(event_uid)
        if event_result.is_error:
            return Result.fail(event_result.expect_error())

        event = event_result.value
        if not event:
            return Result.fail(Errors.not_found(resource="Event", identifier=event_uid))

        search_text = f"{event.title}"
        if event.description:
            search_text += f" {event.description}"

        all_events_result = await self.backend.find_by(user_uid=event.user_uid)
        if all_events_result.is_error:
            return Result.fail(all_events_result.expect_error())

        all_events = all_events_result.value or []
        candidates = [
            (e.uid, f"{e.title} {e.description or ''}") for e in all_events if e.uid != event_uid
        ]

        if not candidates:
            return Result.ok([])

        return await self._semantic_search(search_text, candidates, limit)

    async def generate_preparation_checklist(
        self, event_uid: str, max_items: int = 5
    ) -> Result[list[str]]:
        """Generate AI-suggested preparation checklist for an event."""
        event_result = await self.backend.get(event_uid)
        if event_result.is_error:
            return Result.fail(event_result.expect_error())

        event = event_result.value
        if not event:
            return Result.fail(Errors.not_found(resource="Event", identifier=event_uid))

        context = {
            "title": event.title,
            "description": event.description or "No description",
            "event_type": event.event_type or "general",
            "event_date": str(event.event_date) if event.event_date else "Not set",
        }

        prompt = f"""Create a preparation checklist for this event with up to {max_items} items.

Focus on actionable items that help the person prepare effectively.
Order from most important to least important.

Return only the checklist items, one per line. Be specific and practical."""

        insight_result = await self._generate_insight(prompt, context=context, max_tokens=250)
        if insight_result.is_error:
            return Result.fail(insight_result.expect_error())

        response = insight_result.value
        items = [
            line.strip().lstrip("- ").lstrip("•").lstrip("1234567890.").strip()
            for line in response.split("\n")
            if line.strip() and not line.strip().startswith("#")
        ]

        return Result.ok(items[:max_items])

    async def generate_event_insight(self, event_uid: str) -> Result[str]:
        """Generate AI-written insight about an event."""
        event_result = await self.backend.get(event_uid)
        if event_result.is_error:
            return Result.fail(event_result.expect_error())

        event = event_result.value
        if not event:
            return Result.fail(Errors.not_found(resource="Event", identifier=event_uid))

        context = {
            "title": event.title,
            "description": event.description or "No description",
            "event_type": event.event_type or "general",
            "status": event.status.value if event.status else "scheduled",
        }

        prompt = """Provide a brief insight about this event.
Focus on:
1. How to make the most of this event
2. One tip for maximizing learning or value
Keep it under 100 words."""

        return await self._generate_insight(prompt, context=context, max_tokens=200)

    async def suggest_reflection_prompts(
        self, event_uid: str, num_prompts: int = 3
    ) -> Result[list[str]]:
        """Generate reflection prompts for after an event."""
        event_result = await self.backend.get(event_uid)
        if event_result.is_error:
            return Result.fail(event_result.expect_error())

        event = event_result.value
        if not event:
            return Result.fail(Errors.not_found(resource="Event", identifier=event_uid))

        context = {
            "title": event.title,
            "description": event.description or "No description",
            "event_type": event.event_type or "general",
        }

        prompt = f"""Generate {num_prompts} reflection prompts for after this event.

Each prompt should help the person:
- Extract key learnings
- Identify actionable next steps
- Connect the experience to their goals

Format: One prompt per line, phrased as a question."""

        insight_result = await self._generate_insight(prompt, context=context, max_tokens=200)
        if insight_result.is_error:
            return Result.fail(insight_result.expect_error())

        response = insight_result.value
        prompts = [
            line.strip().lstrip("- ").lstrip("•").lstrip("1234567890.").strip()
            for line in response.split("\n")
            if line.strip() and "?" in line
        ]

        return Result.ok(prompts[:num_prompts])
