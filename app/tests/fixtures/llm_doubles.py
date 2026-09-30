"""Real-shaped LLM and embeddings doubles for the AI-tier unit tests.

``LLMService.generate`` folds a provider failure into a degraded
``LLMResponse`` rather than raising, so a test that replaces the service (or
the helper above it) never sees that path. These doubles sit BELOW the
service: ``LLMService`` runs for real and only the chat-completion port is
scripted, so a test sees exactly what ``_generate_insight`` sees.

An embeddings double is a ``MagicMock`` limited to the real class's public
names — ``spec=EmbeddingsService`` would evaluate the class's annotations,
which name ``TYPE_CHECKING``-only imports.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

from core.ports.llm_protocols import ChatMessage, LLMCompletion
from core.services.embeddings_service import EmbeddingsService
from core.services.llm_service import LLMConfig, LLMProvider, LLMService
from core.utils.result_simplified import Errors, Result

EMBEDDINGS_SERVICE_NAMES = [name for name in dir(EmbeddingsService) if not name.startswith("_")]


class ScriptedChatCaller:
    """A chat-completion port that answers every call with one scripted outcome."""

    def __init__(self, outcome: Result[LLMCompletion]) -> None:
        self.outcome = outcome
        self.calls: list[list[ChatMessage]] = []

    async def complete(
        self,
        messages: list[ChatMessage],
        *,
        system_prompt: str | None = None,
        model: str = "gpt-4o-mini",
        temperature: float = 0.7,
        max_tokens: int = 4000,
    ) -> Result[LLMCompletion]:
        self.calls.append(messages)
        return self.outcome


def scripted_llm(text: str) -> LLMService:
    """A real ``LLMService`` whose provider answers ``text``."""
    return LLMService(
        config=LLMConfig(provider=LLMProvider.OPENAI, model_name="gpt-4o-mini"),
        caller=ScriptedChatCaller(Result.ok(LLMCompletion(text=text, model="gpt-4o-mini"))),
    )


def failing_llm(reason: str = "rate limited") -> LLMService:
    """A real ``LLMService`` whose provider fails every call."""
    return LLMService(
        config=LLMConfig(provider=LLMProvider.OPENAI, model_name="gpt-4o-mini"),
        caller=ScriptedChatCaller(Result.fail(Errors.integration(message=reason, service="llm"))),
    )


def embeddings_double(create_embedding: AsyncMock | None = None) -> MagicMock:
    """An ``EmbeddingsService`` stand-in with only the real class's public names."""
    double = MagicMock(spec=EMBEDDINGS_SERVICE_NAMES)
    double.create_embedding = create_embedding or AsyncMock(
        return_value=Result.fail(Errors.integration(message="not scripted", service="embeddings"))
    )
    return double
