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

from core.models.enums.entity_enums import EntityType
from core.models.event.event import Event
from core.models.type_hints import EntityUID
from core.services.base_ai_service import BaseAIService
from core.services.whole_set_read import find_all_by
from core.utils.result_simplified import Errors, Result

if TYPE_CHECKING:
    from core.ports.domain_protocols import EventsOperations
    from core.services.embeddings_service import EmbeddingsService
    from core.services.llm_service import LLMService


class EventsAIService(BaseAIService["EventsOperations", Event]):
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
        llm_service: LLMService,
        embeddings_service: EmbeddingsService,
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
    ) -> Result[list[tuple[EntityUID, float]]]:
        """Find semantically similar events using embeddings."""
        event_result = await self.backend.get(event_uid)
        if event_result.is_error:
            return Result.fail(event_result)

        event = event_result.value
        if not event:
            return Result.fail(Errors.not_found(resource="Event", identifier=event_uid))

        all_events_result = await find_all_by(
            self.backend, self.logger, "Event similarity pool", user_uid=event.user_uid
        )
        if all_events_result.is_error:
            return Result.fail(all_events_result)

        return await self._rank_similar_entities(
            event,
            EntityType.EVENT,
            all_events_result.value or [],
            exclude_uid=event_uid,
            limit=limit,
        )

    async def generate_preparation_checklist(
        self, event_uid: str, max_items: int = 5
    ) -> Result[list[str]]:
        """Generate AI-suggested preparation checklist for an event."""
        event_result = await self.backend.get(event_uid)
        if event_result.is_error:
            return Result.fail(event_result)

        event = event_result.value
        if not event:
            return Result.fail(Errors.not_found(resource="Event", identifier=event_uid))

        context = {
            "title": event.title,
            "description": event.description or "No description",
            "event_type": event.event_type or "general",
            "event_date": str(event.event_date) if event.event_date else "Not set",
        }

        insight_result = await self._generate_insight(
            "events_ai_preparation",
            fields={"max_items": max_items},
            context=context,
            max_tokens=250,
        )
        if insight_result.is_error:
            return Result.fail(insight_result)

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
            return Result.fail(event_result)

        event = event_result.value
        if not event:
            return Result.fail(Errors.not_found(resource="Event", identifier=event_uid))

        context = {
            "title": event.title,
            "description": event.description or "No description",
            "event_type": event.event_type or "general",
            "status": event.status.value if event.status else "scheduled",
        }

        return await self._generate_insight("events_ai_insight", context=context, max_tokens=200)

    async def suggest_reflection_prompts(
        self, event_uid: str, num_prompts: int = 3
    ) -> Result[list[str]]:
        """Generate reflection prompts for after an event."""
        event_result = await self.backend.get(event_uid)
        if event_result.is_error:
            return Result.fail(event_result)

        event = event_result.value
        if not event:
            return Result.fail(Errors.not_found(resource="Event", identifier=event_uid))

        context = {
            "title": event.title,
            "description": event.description or "No description",
            "event_type": event.event_type or "general",
        }

        insight_result = await self._generate_insight(
            "events_ai_reflection",
            fields={"num_prompts": num_prompts},
            context=context,
            max_tokens=200,
        )
        if insight_result.is_error:
            return Result.fail(insight_result)

        response = insight_result.value
        prompts = [
            line.strip().lstrip("- ").lstrip("•").lstrip("1234567890.").strip()
            for line in response.split("\n")
            if line.strip() and "?" in line
        ]

        return Result.ok(prompts[:num_prompts])
