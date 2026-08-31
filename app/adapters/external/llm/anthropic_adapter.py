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

from typing import TYPE_CHECKING, Any

from anthropic import AsyncAnthropic
from anthropic.types import TextBlock, ToolUseBlock

from core.ports.llm_protocols import LLMCompletion, ToolSelection
from core.utils.exception_types import ANTHROPIC_EXCEPTIONS
from core.utils.logging import get_logger
from core.utils.result_simplified import Errors, Result
from core.utils.retry import async_retry

if TYPE_CHECKING:
    from core.ports.llm_protocols import ChatMessage, ToolSpec

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

    # ⚠ No ``temperature``: the anthropic SDK 1.x removed it from
    # ``messages.create()`` (sampling controls left the Messages API), so
    # passing it raises TypeError before any request is made — which silently
    # degraded every claude-routed chat call. The port still accepts a
    # ``temperature`` argument for the OpenAI adapter's sake; this adapter
    # cannot honor it.
    @async_retry(exceptions=ANTHROPIC_EXCEPTIONS, max_attempts=3, base_delay=1.0)
    async def _create(
        self,
        model: str,
        max_tokens: int,
        system: str,
        messages: Any,  # boundary: sdk-MessageParam
    ) -> Any:  # boundary: anthropic-sdk-response
        return await self._client.messages.create(
            model=model,
            max_tokens=max_tokens,
            system=system,
            messages=messages,
        )

    async def complete(
        self,
        messages: list[ChatMessage],
        *,
        system_prompt: str | None = None,
        model: str | None = None,
        temperature: float = 0.7,  # noqa: ARG002 — port contract; the 1.x SDK has no sampling control to honor it with
        max_tokens: int = 500,
    ) -> Result[LLMCompletion]:
        model = model or self._default_model

        try:
            message = await self._create(
                model=model,
                max_tokens=max_tokens,
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

    @async_retry(exceptions=ANTHROPIC_EXCEPTIONS, max_attempts=3, base_delay=1.0)
    async def _create_with_tools(
        self,
        model: str,
        system: str,
        messages: Any,  # boundary: sdk-MessageParam
        tools: Any,  # boundary: sdk-ToolParam
    ) -> Any:  # boundary: anthropic-sdk-response
        return await self._client.messages.create(
            model=model,
            max_tokens=256,
            system=system,
            messages=messages,
            tools=tools,
            tool_choice={"type": "auto"},
        )

    async def select_tool(
        self,
        question: str,
        tools: list[ToolSpec],
        *,
        system_prompt: str | None = None,
        model: str | None = None,
    ) -> Result[ToolSelection]:
        """Native Anthropic tool selection — the model picks a tool + args, never a query.

        ``tool_choice`` stays ``auto`` so "no tool fits" is expressible (the only
        decline the model can make). Returns the FIRST tool_use block's name/input as the normalized
        ``ToolSelection``; no tool_use block means ``tool_name=None``.
        """
        model = model or self._default_model
        try:
            message = await self._create_with_tools(
                model=model,
                system=system_prompt or "",
                messages=[{"role": "user", "content": question}],
                tools=[
                    {
                        "name": tool.name,
                        "description": tool.description,
                        "input_schema": tool.input_schema,
                    }
                    for tool in tools
                ],
            )
            for block in message.content:
                if isinstance(block, ToolUseBlock):
                    raw_input = block.input if isinstance(block.input, dict) else {}
                    return Result.ok(ToolSelection(tool_name=block.name, arguments=raw_input))
            return Result.ok(ToolSelection(tool_name=None, arguments={}))

        except ANTHROPIC_EXCEPTIONS as e:
            self.logger.error(f"Anthropic tool selection failed: {e}")
            return Result.fail(
                Errors.integration(service="Anthropic", operation="select_tool", message=str(e))
            )
        except Exception as e:  # safety-net: Anthropic SDK raises varied exception types
            self.logger.error(
                f"Anthropic tool selection failed unexpectedly ({type(e).__name__}): {e}"
            )
            return Result.fail(
                Errors.integration(service="Anthropic", operation="select_tool", message=str(e))
            )


__all__ = ["AnthropicChatAdapter"]
