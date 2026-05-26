"""
Unit tests for OpenAIChatAdapter (W1 chat-completion boundary).

Covers payload construction (system prompt placement), model override,
LLMCompletion mapping (text + usage), None-content and exception → Result.fail,
and the empty-key fail-fast. The OpenAI SDK call is mocked — no network.
"""

from unittest.mock import AsyncMock, MagicMock

import pytest

from adapters.external.llm import OpenAIChatAdapter


def _adapter() -> OpenAIChatAdapter:
    adapter = OpenAIChatAdapter(api_key="test-key")
    adapter._client = MagicMock()
    return adapter


def _response(content: str | None, usage: dict | None = None):
    resp = MagicMock()
    msg = MagicMock()
    msg.content = content
    choice = MagicMock()
    choice.message = msg
    resp.choices = [choice]
    if usage is None:
        resp.usage = None
    else:
        resp.usage = MagicMock()
        resp.usage.model_dump.return_value = usage
    return resp


def test_fail_fast_without_api_key():
    with pytest.raises(ValueError, match="OPENAI_API_KEY"):
        OpenAIChatAdapter(api_key="")


@pytest.mark.asyncio
async def test_complete_returns_text_and_usage():
    adapter = _adapter()
    adapter._client.chat.completions.create = AsyncMock(
        return_value=_response("the answer", {"prompt_tokens": 3, "completion_tokens": 5})
    )

    result = await adapter.complete([{"role": "user", "content": "hi"}])

    assert result.is_ok
    completion = result.value
    assert completion.text == "the answer"
    assert completion.model == "gpt-4"  # default model
    assert completion.usage == {"prompt_tokens": 3, "completion_tokens": 5}


@pytest.mark.asyncio
async def test_system_prompt_prepended_and_model_override():
    adapter = _adapter()
    adapter._client.chat.completions.create = AsyncMock(return_value=_response("ok"))

    await adapter.complete(
        [{"role": "user", "content": "hi"}],
        system_prompt="You are helpful.",
        model="gpt-4o-mini",
    )

    kwargs = adapter._client.chat.completions.create.call_args.kwargs
    assert kwargs["model"] == "gpt-4o-mini"
    assert kwargs["messages"][0] == {"role": "system", "content": "You are helpful."}
    assert kwargs["messages"][-1] == {"role": "user", "content": "hi"}


@pytest.mark.asyncio
async def test_none_content_is_error():
    adapter = _adapter()
    adapter._client.chat.completions.create = AsyncMock(return_value=_response(None))

    result = await adapter.complete([{"role": "user", "content": "hi"}])

    assert result.is_error


@pytest.mark.asyncio
async def test_exception_mapped_to_integration_error():
    adapter = _adapter()
    adapter._client.chat.completions.create = AsyncMock(side_effect=RuntimeError("boom"))

    result = await adapter.complete([{"role": "user", "content": "hi"}])

    assert result.is_error
    assert "openai" in str(result.expect_error()).lower()
