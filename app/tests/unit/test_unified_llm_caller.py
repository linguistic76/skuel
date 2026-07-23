"""
Unit tests for UnifiedLLMCaller (W1 PR3).

The caller routes by model prefix (gpt* → OpenAI, claude* → Anthropic) over
injected ChatCompletionPort adapters and unwraps LLMCompletion.text into the
Result[str] its callers expect.
"""

from unittest.mock import AsyncMock, MagicMock

import pytest

from core.ports.llm_protocols import LLMCompletion
from core.services.llm_caller import UnifiedLLMCaller
from core.utils.result_simplified import Errors, Result


def _port(text: str = "answer", error=None):
    port = MagicMock()
    port.complete = AsyncMock(
        return_value=Result.fail(error)
        if error is not None
        else Result.ok(LLMCompletion(text=text, model="m"))
    )
    return port


def test_requires_at_least_one_adapter():
    with pytest.raises(ValueError, match="At least one chat adapter"):
        UnifiedLLMCaller(openai=None, anthropic=None)


@pytest.mark.asyncio
async def test_routes_gpt_to_openai_and_unwraps_text():
    openai, anthropic = _port("from openai"), _port("from anthropic")
    caller = UnifiedLLMCaller(openai=openai, anthropic=anthropic)

    result = await caller.generate("hi", model="gpt-4o-mini", system_prompt="sys")

    assert result.is_ok
    assert result.value == "from openai"
    openai.complete.assert_awaited_once()
    anthropic.complete.assert_not_awaited()
    # routing args forwarded
    args, kwargs = openai.complete.call_args
    assert args[0] == [{"role": "user", "content": "hi"}]
    assert kwargs["model"] == "gpt-4o-mini"
    assert kwargs["system_prompt"] == "sys"


@pytest.mark.asyncio
async def test_routes_claude_to_anthropic():
    openai, anthropic = _port("from openai"), _port("from anthropic")
    caller = UnifiedLLMCaller(openai=openai, anthropic=anthropic)

    result = await caller.generate("hi", model="claude-sonnet-4-6")

    assert result.is_ok
    assert result.value == "from anthropic"
    anthropic.complete.assert_awaited_once()
    openai.complete.assert_not_awaited()


@pytest.mark.asyncio
async def test_gpt_requested_without_openai_fails():
    caller = UnifiedLLMCaller(openai=None, anthropic=_port())
    result = await caller.generate("hi", model="gpt-4o-mini")
    assert result.is_error
    assert "openai" in str(result.expect_error()).lower()


@pytest.mark.asyncio
async def test_claude_requested_without_anthropic_fails():
    caller = UnifiedLLMCaller(openai=_port(), anthropic=None)
    result = await caller.generate("hi", model="claude-sonnet-4-6")
    assert result.is_error
    assert "anthropic" in str(result.expect_error()).lower()


@pytest.mark.asyncio
async def test_unknown_model_fails():
    caller = UnifiedLLMCaller(openai=_port())
    result = await caller.generate("hi", model="llama-3")
    assert result.is_error
    assert "unknown model" in str(result.expect_error()).lower()


@pytest.mark.asyncio
async def test_port_error_propagates():
    openai = _port(error=Errors.integration(service="OpenAI", message="rate limited"))
    caller = UnifiedLLMCaller(openai=openai)
    result = await caller.generate("hi", model="gpt-4o-mini")
    assert result.is_error
    assert "rate limited" in str(result.expect_error())


def test_supported_models_and_is_supported():
    caller = UnifiedLLMCaller(openai=_port())
    models = caller.get_supported_models()
    assert "openai" in models and "anthropic" not in models
    assert caller.is_model_supported("gpt-4o-mini")
    assert not caller.is_model_supported("claude-sonnet-4-6")


@pytest.mark.asyncio
async def test_complete_routes_by_prefix_and_forwards_history():
    openai, anthropic = _port("from openai"), _port("from anthropic")
    caller = UnifiedLLMCaller(openai=openai, anthropic=anthropic)
    history = [
        {"role": "user", "content": "earlier"},
        {"role": "assistant", "content": "prior"},
        {"role": "user", "content": "now"},
    ]

    result = await caller.complete(history, system_prompt="sys", model="gpt-4o")

    assert result.is_ok
    # complete returns the full LLMCompletion, not just text
    assert result.value.text == "from openai"
    anthropic.complete.assert_not_awaited()
    args, kwargs = openai.complete.call_args
    assert args[0] == history  # full message history forwarded
    assert kwargs["model"] == "gpt-4o"
    assert kwargs["system_prompt"] == "sys"


@pytest.mark.asyncio
async def test_complete_routes_claude_to_anthropic():
    openai, anthropic = _port("from openai"), _port("from anthropic")
    caller = UnifiedLLMCaller(openai=openai, anthropic=anthropic)

    result = await caller.complete([{"role": "user", "content": "hi"}], model="claude-sonnet-4-6")

    assert result.is_ok
    assert result.value.text == "from anthropic"
    anthropic.complete.assert_awaited_once()
    openai.complete.assert_not_awaited()


@pytest.mark.asyncio
async def test_complete_unknown_model_fails():
    caller = UnifiedLLMCaller(openai=_port())
    result = await caller.complete([{"role": "user", "content": "hi"}], model="llama-3")
    assert result.is_error
    assert "unknown model" in str(result.expect_error()).lower()


@pytest.mark.asyncio
async def test_complete_missing_provider_fails():
    caller = UnifiedLLMCaller(openai=_port())
    result = await caller.complete([{"role": "user", "content": "hi"}], model="claude-sonnet-4-6")
    assert result.is_error
    assert "anthropic" in str(result.expect_error()).lower()
