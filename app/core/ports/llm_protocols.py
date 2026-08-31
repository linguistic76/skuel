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


@dataclass(frozen=True)
class ToolSpec:
    """A provider-agnostic tool the LLM may select.

    ``input_schema`` is the pydantic-generated JSON schema of the tool's args
    model (``model_json_schema()``), so the provider tool spec and the
    validation gate can never drift apart. Provider-specific wrapping (OpenAI's
    ``{"type": "function", ...}`` envelope vs Anthropic's flat shape) is the
    adapter's concern.
    """

    name: str
    description: str
    input_schema: dict[str, object]


@dataclass(frozen=True)
class ToolSelection:
    """The normalized outcome of a tool-selection call.

    ``tool_name is None`` means the model selected NO tool — a normal outcome
    (the only decline the model can express), never an error. ``arguments``
    are the raw model-emitted args, not yet validated; the executor's pydantic
    gate (``run_tool``) is the validation boundary.
    """

    tool_name: str | None
    arguments: dict[str, object]


@runtime_checkable
class ToolSelectionPort(Protocol):
    """Provider-native tool selection: the model picks a tool name + typed args.

    The model never sees or emits a query — it fills a schema. Implemented by
    the Anthropic adapter (the provider in use for Askesis tool selection);
    an adapter without this operation simply does not satisfy the protocol and
    the caller reports a typed integration failure.
    """

    async def select_tool(
        self,
        question: str,
        tools: list[ToolSpec],
        *,
        system_prompt: str | None = None,
        model: str | None = None,
    ) -> Result[ToolSelection]:
        """Ask the model to pick one of ``tools`` (or none) for ``question``.

        Returns ``Result.ok(ToolSelection)`` — with ``tool_name=None`` when the
        model declines — or ``Result.fail(integration_error)`` on provider
        failure. ``model=None`` uses the adapter's default model.
        """
        ...
