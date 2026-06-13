"""
Unit tests for LLMService delegation to the chat port (W1).

Verifies: mock path when no port is wired; LLMCompletion → LLMResponse mapping;
error propagation; context/conversation-history assembly into the port call.
"""

from unittest.mock import AsyncMock, MagicMock

import pytest

from core.ports.llm_protocols import LLMCompletion
from core.services.llm_service import LLMConfig, LLMProvider, LLMResponse, LLMService
from core.utils.result_simplified import Errors, Result


def _port(completion: LLMCompletion | None = None, error=None):
    port = MagicMock()
    if error is not None:
        port.complete = AsyncMock(return_value=Result.fail(error))
    else:
        port.complete = AsyncMock(return_value=Result.ok(completion))
    return port


@pytest.mark.asyncio
async def test_no_port_returns_mock_response():
    service = LLMService()  # default MOCK provider, no chat_port → mock
    resp = await service.generate("How do I learn Python?")
    assert isinstance(resp, LLMResponse)
    assert resp.provider == LLMProvider.MOCK
    assert resp.content  # non-empty canned response
    assert resp.error is None


@pytest.mark.parametrize("provider", [LLMProvider.OPENAI, LLMProvider.ANTHROPIC])
def test_real_provider_without_port_fails_fast(provider):
    """A real provider with no chat_port must raise (no silent mock fallback)."""
    with pytest.raises(ValueError, match="requires a"):
        LLMService(config=LLMConfig(provider=provider))


@pytest.mark.asyncio
async def test_delegates_and_maps_completion():
    port = _port(LLMCompletion(text="answer", model="gpt-4", usage={"total_tokens": 9}))
    service = LLMService(
        config=LLMConfig(provider=LLMProvider.OPENAI, model_name="gpt-4"), chat_port=port
    )

    resp = await service.generate("q")

    assert resp.content == "answer"
    assert resp.provider == LLMProvider.OPENAI
    assert resp.model == "gpt-4"
    assert resp.usage == {"total_tokens": 9}
    assert resp.error is None


@pytest.mark.asyncio
async def test_error_propagates_to_response():
    port = _port(error=Errors.integration(service="OpenAI", message="rate limited"))
    service = LLMService(config=LLMConfig(provider=LLMProvider.OPENAI), chat_port=port)

    resp = await service.generate("q")

    assert resp.content == ""
    assert resp.error is not None
    assert "rate limited" in resp.error


@pytest.mark.asyncio
async def test_context_and_history_assembled_for_port():
    port = _port(LLMCompletion(text="ok", model="gpt-4"))
    service = LLMService(config=LLMConfig(provider=LLMProvider.OPENAI), chat_port=port)

    await service.generate(
        "What next?",
        context="user has 3 overdue tasks",
        system_prompt="be helpful",
        conversation_history=[{"role": "user", "content": "earlier"}],
    )

    args, kwargs = port.complete.call_args
    messages = args[0]
    assert messages[0] == {"role": "user", "content": "earlier"}
    assert messages[-1]["role"] == "user"
    assert "Context: user has 3 overdue tasks" in messages[-1]["content"]
    assert kwargs["system_prompt"] == "be helpful"
    assert kwargs["model"] == "gpt-3.5-turbo"  # config default
