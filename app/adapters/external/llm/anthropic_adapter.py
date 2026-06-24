"""
Anthropic Chat Adapter — Thin Wrapper for Messages
===================================================

Implements ``ChatCompletionPort`` over ``anthropic.Anthropic``. Single
responsibility: messages → completion → text. No prompt building, no
business logic.

ARCHITECTURE (W1 / ADR-044):
Keeps the ``anthropic`` SDK out of ``core/``. The API key is read at the
composition root and passed in.

Note: the Anthropic ``system`` prompt is a top-level parameter (not a
message), and ``usage`` is not surfaced here (left ``None``).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from anthropic import AsyncAnthropic
from anthropic.types import TextBlock

from core.ports.llm_protocols import LLMCompletion
from core.utils.exception_types import ANTHROPIC_EXCEPTIONS
from core.utils.logging import get_logger
from core.utils.result_simplified import Errors, Result
from core.utils.retry import async_retry

if TYPE_CHECKING:
    from core.ports.llm_protocols import ChatMessage

logger = get_logger("skuel.adapters.llm.anthropic")

DEFAULT_MODEL = "claude-sonnet-4-6"


class AnthropicChatAdapter:
    """Anthropic chat-completion adapter implementing ``ChatCompletionPort``."""

    def __init__(self, api_key: str, default_model: str = DEFAULT_MODEL) -> None:
        """Initialize with the Anthropic API key.

        Raises:
            ValueError: If ``api_key`` is empty (fail-fast at the wiring layer).
        """
        if not api_key:
            raise ValueError("ANTHROPIC_API_KEY is required to construct AnthropicChatAdapter.")
        self._client = AsyncAnthropic(api_key=api_key)
        self._default_model = default_model
        self.logger = logger

    @async_retry(exceptions=ANTHROPIC_EXCEPTIONS, max_attempts=3, base_delay=1.0)
    async def complete(
        self,
        messages: list[ChatMessage],
        *,
        system_prompt: str | None = None,
        model: str | None = None,
        temperature: float = 0.7,
        max_tokens: int = 500,
    ) -> Result[LLMCompletion]:
        model = model or self._default_model

        try:
            message = await self._client.messages.create(
                model=model,
                max_tokens=max_tokens,
                temperature=temperature,
                system=system_prompt or "",
                messages=[dict(m) for m in messages],
            )
            if not message.content:
                self.logger.error("Anthropic returned empty content list")
                return Result.fail(
                    Errors.integration(
                        service="Anthropic",
                        operation="complete",
                        message="API returned empty content",
                    )
                )
            first_block = message.content[0]
            text = first_block.text if isinstance(first_block, TextBlock) else ""
            return Result.ok(LLMCompletion(text=text, model=model, usage=None))

        except ANTHROPIC_EXCEPTIONS as e:
            self.logger.error(f"Anthropic completion failed: {e}")
            return Result.fail(
                Errors.integration(service="Anthropic", operation="complete", message=str(e))
            )
        except Exception as e:  # safety-net: Anthropic SDK raises varied exception types
            self.logger.error(f"Anthropic completion failed unexpectedly ({type(e).__name__}): {e}")
            return Result.fail(
                Errors.integration(service="Anthropic", operation="complete", message=str(e))
            )


__all__ = ["AnthropicChatAdapter"]
