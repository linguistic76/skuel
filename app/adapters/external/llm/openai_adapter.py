"""
OpenAI Chat Adapter — Thin Wrapper for Chat Completions
=======================================================

Implements ``ChatCompletionPort`` over ``openai.AsyncOpenAI``. Single
responsibility: messages → chat completion → text. No prompt building, no
RAG, no business logic — that lives in the consuming core services.

ARCHITECTURE (W1 / ADR-044):
Keeps the ``openai`` SDK out of ``core/``. The API key is read at the
composition root and passed in (mirrors DeepgramAdapter).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from openai import AsyncOpenAI

from core.ports.llm_protocols import LLMCompletion
from core.utils.exception_types import OPENAI_EXCEPTIONS
from core.utils.logging import get_logger
from core.utils.result_simplified import Errors, Result

if TYPE_CHECKING:
    from core.ports.llm_protocols import ChatMessage

logger = get_logger("skuel.adapters.llm.openai")

DEFAULT_MODEL = "gpt-4"


class OpenAIChatAdapter:
    """OpenAI chat-completion adapter implementing ``ChatCompletionPort``."""

    def __init__(self, api_key: str, default_model: str = DEFAULT_MODEL) -> None:
        """Initialize with the OpenAI API key.

        Raises:
            ValueError: If ``api_key`` is empty (fail-fast at the wiring layer).
        """
        if not api_key:
            raise ValueError("OPENAI_API_KEY is required to construct OpenAIChatAdapter.")
        self._client = AsyncOpenAI(api_key=api_key)
        self._default_model = default_model
        self.logger = logger

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
        payload: list[dict[str, str]] = []
        if system_prompt:
            payload.append({"role": "system", "content": system_prompt})
        payload.extend({"role": m["role"], "content": m["content"]} for m in messages)

        try:
            response = await self._client.chat.completions.create(
                model=model,
                messages=payload,
                temperature=temperature,
                max_tokens=max_tokens,
            )
            content = response.choices[0].message.content
            if content is None:
                self.logger.error("OpenAI returned None as completion content")
                return Result.fail(
                    Errors.integration(
                        service="OpenAI",
                        operation="complete",
                        message="API returned None as content",
                    )
                )
            usage = response.usage.model_dump() if response.usage else None
            return Result.ok(LLMCompletion(text=content, model=model, usage=usage))

        except OPENAI_EXCEPTIONS as e:
            self.logger.error(f"OpenAI completion failed: {e}")
            return Result.fail(
                Errors.integration(service="OpenAI", operation="complete", message=str(e))
            )
        except Exception as e:  # safety-net: OpenAI SDK raises varied exception types
            self.logger.error(f"OpenAI completion failed unexpectedly ({type(e).__name__}): {e}")
            return Result.fail(
                Errors.integration(service="OpenAI", operation="complete", message=str(e))
            )


__all__ = ["OpenAIChatAdapter"]
