"""
Unified LLM Caller
====================

Routes LLM calls to OpenAI or Anthropic based on model prefix.

Extracts the model-routing logic that was duplicated in SubmissionReportService
and hardcoded in JournalOutputGenerator into a single reusable service.

Usage:
    caller = UnifiedLLMCaller(openai=openai_service, anthropic=anthropic_service)
    result = await caller.generate("prompt", model="gpt-4o-mini")
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol, runtime_checkable

from core.utils.exception_types import LLM_EXCEPTIONS
from core.utils.logging import get_logger
from core.utils.result_simplified import Errors, Result

if TYPE_CHECKING:
    from core.services.ai_service import AnthropicService, OpenAIService

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

    def get_supported_models(self) -> dict[str, list[str]]:
        """Get supported models by provider."""
        ...

    def is_model_supported(self, model: str) -> bool:
        """Check if a model is supported."""
        ...


class UnifiedLLMCaller:
    """
    Routes LLM calls to OpenAI or Anthropic based on model prefix.

    Replaces duplicated routing logic in SubmissionReportService (lines 136-174)
    and hardcoded OpenAI calls in JournalOutputGenerator.
    """

    def __init__(
        self,
        openai: "OpenAIService | None" = None,
        anthropic: "AnthropicService | None" = None,
    ) -> None:
        if not openai and not anthropic:
            raise ValueError("At least one AI service (OpenAI or Anthropic) must be provided")

        self.openai = openai
        self.anthropic = anthropic
        self.logger = logger

        available = []
        if self.openai:
            available.append("OpenAI")
        if self.anthropic:
            available.append("Anthropic")
        logger.info(f"UnifiedLLMCaller initialized with: {', '.join(available)}")

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

        Args:
            prompt: The prompt text
            model: Model name (prefix determines provider: gpt* → OpenAI, claude* → Anthropic)
            temperature: Sampling temperature (0-1)
            max_tokens: Maximum tokens to generate
            system_prompt: Optional system prompt (OpenAI only)

        Returns:
            Result containing the generated text
        """
        try:
            if model.startswith("gpt"):
                if not self.openai:
                    return Result.fail(
                        Errors.integration(
                            service="OpenAI",
                            operation="generate",
                            message="OpenAI service not configured, but GPT model requested",
                        )
                    )
                return await self.openai.generate_completion(
                    prompt=prompt,
                    max_tokens=max_tokens,
                    temperature=temperature,
                    model=model,
                    system_prompt=system_prompt,
                )

            if model.startswith("claude"):
                if not self.anthropic:
                    return Result.fail(
                        Errors.integration(
                            service="Anthropic",
                            operation="generate",
                            message="Anthropic service not configured, but Claude model requested",
                        )
                    )
                return await self.anthropic.generate_completion(
                    prompt=prompt,
                    max_tokens=max_tokens,
                    temperature=temperature,
                    model=model,
                )

            return Result.fail(
                Errors.validation(
                    f"Unknown model: {model}. Must start with 'gpt' or 'claude'",
                    field="model",
                )
            )

        except LLM_EXCEPTIONS as e:
            self.logger.error(f"LLM error ({model}): {e}")
            return Result.fail(
                Errors.integration(
                    service="LLM",
                    operation="generate",
                    message=f"LLM call failed ({model}): {e!s}",
                )
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
