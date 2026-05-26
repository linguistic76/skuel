"""
LLM Protocols
=============

The chat-completion boundary (W1 / ADR-044). Keeps the vendor SDKs
(``openai``, ``anthropic``) out of ``core/`` — core depends only on
``ChatCompletionPort``; provider-specific message formatting (OpenAI's
system-as-message vs Anthropic's separate ``system=`` parameter) and error
mapping are the adapter's concern.

Implementations: adapters/external/llm/{openai_adapter,anthropic_adapter}.py
Consumers: LLMService (RAG / Askesis), and — after W1 PR3 — the former
ai_service.py callers (content enrichment, report generation).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, TypedDict, runtime_checkable

from core.utils.result_simplified import Result


class ChatMessage(TypedDict):
    """A single conversation turn. ``role`` is ``"user"`` or ``"assistant"``.

    The system prompt is passed separately to ``ChatCompletionPort.complete``
    (not as a message) so each adapter can place it where its SDK expects.
    """

    role: str
    content: str


@dataclass(frozen=True)
class LLMCompletion:
    """A chat completion returned by an LLM provider.

    ``usage`` carries token counts when the provider reports them (OpenAI does;
    the Anthropic path currently leaves it ``None``).
    """

    text: str
    model: str
    usage: dict[str, int] | None = None


@runtime_checkable
class ChatCompletionPort(Protocol):
    """Provider-agnostic chat-completion boundary.

    The vendor SDK lives in the adapter; the model is selected per call so a
    single adapter instance serves callers that use different models.
    """

    async def complete(
        self,
        messages: list[ChatMessage],
        *,
        system_prompt: str | None = None,
        model: str | None = None,
        temperature: float = 0.7,
        max_tokens: int = 500,
    ) -> Result[LLMCompletion]:
        """Generate a completion for ``messages`` (newest turn last).

        Returns ``Result.ok(LLMCompletion)`` or
        ``Result.fail(integration_error)``. ``model=None`` uses the adapter's
        default model.
        """
        ...
