"""
Unified LLM Caller
====================

Routes LLM calls to OpenAI or Anthropic based on model prefix.

Extracts the model-routing logic that was duplicated across EntryReportService
and JournalService into a single reusable service.

Usage:
    caller = UnifiedLLMCaller(openai=openai_chat_adapter, anthropic=anthropic_chat_adapter)
    result = await caller.generate("prompt", model="gpt-4o-mini")
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol, runtime_checkable

from core.utils.logging import get_logger
from core.utils.result_simplified import Errors, Result

if TYPE_CHECKING:
    from core.ports.llm_protocols import ChatCompletionPort, ChatMessage, LLMCompletion

logger = get_logger("skuel.services.llm_caller")

# Supported model lists (static knowledge)
SUPPORTED_OPENAI_MODELS = ["gpt-4o", "gpt-4o-mini", "gpt-4-turbo", "gpt-3.5-turbo"]
SUPPORTED_ANTHROPIC_MODELS = [
    "claude-sonnet-4-6",
    "claude-opus-4-6",
    "claude-haiku-4-5-20251001",
    "claude-3-5-sonnet-20241022",
    "claude-3-5-haiku-20241022",
]


@runtime_checkable
class LLMCallerProtocol(Protocol):
    """Protocol for LLM call routing."""

    async def generate(
        self,
        prompt: str,
        model: str = "gpt-4o-mini",
        temperature: float = 0.7,
        max_tokens: int = 4000,
        system_prompt: str | None = None,
    ) -> Result[str]:
        """Generate LLM completion, routing to the appropriate provider."""
        ...

    async def complete(
        self,
        messages: list[ChatMessage],
        *,
        system_prompt: str | None = None,
        model: str = "gpt-4o-mini",
        temperature: float = 0.7,
        max_tokens: int = 4000,
    ) -> Result[LLMCompletion]:
        """Generate a completion for a message history, routing to the appropriate provider."""
        ...

    def get_supported_models(self) -> dict[str, list[str]]:
        """Get supported models by provider."""
        ...

    def is_model_supported(self, model: str) -> bool:
        """Check if a model is supported."""
        ...


class UnifiedLLMCaller:
    """
    Routes LLM calls to OpenAI or Anthropic based on model prefix.

    Routes to OpenAI (gpt* prefix) or Anthropic (claude* prefix). Used by
    EntryReportService and JournalService.
    """

    def __init__(
        self,
        openai: ChatCompletionPort | None = None,
        anthropic: ChatCompletionPort | None = None,
    ) -> None:
        if not openai and not anthropic:
            raise ValueError("At least one chat adapter (OpenAI or Anthropic) must be provided")

        self.openai = openai
        self.anthropic = anthropic
        self.logger = logger

        available = []
        if self.openai:
            available.append("OpenAI")
        if self.anthropic:
            available.append("Anthropic")
        logger.info(f"UnifiedLLMCaller initialized with: {', '.join(available)}")

    def _select_port(self, model: str) -> Result[ChatCompletionPort]:
        """Route a model name to its provider adapter by prefix.

        gpt* → OpenAI, claude* → Anthropic. Fails if the routed provider is not
        wired or the prefix is unrecognized.
        """
        if model.startswith("gpt"):
            if not self.openai:
                return Result.fail(
                    Errors.integration(
                        service="OpenAI",
                        operation="complete",
                        message="OpenAI adapter not configured, but GPT model requested",
                    )
                )
            return Result.ok(self.openai)
        if model.startswith("claude"):
            if not self.anthropic:
                return Result.fail(
                    Errors.integration(
                        service="Anthropic",
                        operation="complete",
                        message="Anthropic adapter not configured, but Claude model requested",
                    )
                )
            return Result.ok(self.anthropic)
        return Result.fail(
            Errors.validation(
                f"Unknown model: {model}. Must start with 'gpt' or 'claude'",
                field="model",
            )
        )

    async def generate(
        self,
        prompt: str,
        model: str = "gpt-4o-mini",
        temperature: float = 0.7,
        max_tokens: int = 4000,
        system_prompt: str | None = None,
    ) -> Result[str]:
        """
        Generate LLM completion, routing to the appropriate provider.

        The thin single-prompt path (Journals / EntryReport). For multi-turn RAG
        that needs a message history, use ``complete``.

        Args:
            prompt: The prompt text
            model: Model name (prefix determines provider: gpt* → OpenAI, claude* → Anthropic)
            temperature: Sampling temperature (0-1)
            max_tokens: Maximum tokens to generate
            system_prompt: Optional system prompt

        Returns:
            Result containing the generated text
        """
        result = await self.complete(
            [{"role": "user", "content": prompt}],
            system_prompt=system_prompt,
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        if result.is_error:
            return Result.fail(result)
        return Result.ok(result.value.text)

    async def complete(
        self,
        messages: list[ChatMessage],
        *,
        system_prompt: str | None = None,
        model: str = "gpt-4o-mini",
        temperature: float = 0.7,
        max_tokens: int = 4000,
    ) -> Result[LLMCompletion]:
        """
        Generate a completion for a message history, routing to the appropriate provider.

        The message/history-aware path (Askesis's multi-turn RAG). Routes by model
        prefix and returns the full ``LLMCompletion`` (mirrors ``ChatCompletionPort``).

        Args:
            messages: Conversation turns, newest last (role ``user``/``assistant``)
            system_prompt: Optional system prompt (each adapter places it where its SDK expects)
            model: Model name (prefix determines provider: gpt* → OpenAI, claude* → Anthropic)
            temperature: Sampling temperature (0-1)
            max_tokens: Maximum tokens to generate

        Returns:
            Result containing the LLMCompletion (text, model, usage)
        """
        port_result = self._select_port(model)
        if port_result.is_error:
            return Result.fail(port_result)
        # The adapter catches SDK exceptions and returns a Result.
        return await port_result.value.complete(
            messages,
            system_prompt=system_prompt,
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
        )

    def get_supported_models(self) -> dict[str, list[str]]:
        """Get supported models by provider."""
        models: dict[str, list[str]] = {}
        if self.openai:
            models["openai"] = list(SUPPORTED_OPENAI_MODELS)
        if self.anthropic:
            models["anthropic"] = list(SUPPORTED_ANTHROPIC_MODELS)
        return models

    def is_model_supported(self, model: str) -> bool:
        """Check if a model is supported by available services."""
        if model.startswith("gpt") and self.openai:
            return True
        return bool(model.startswith("claude") and self.anthropic)


__all__ = ["LLMCallerProtocol", "UnifiedLLMCaller"]
