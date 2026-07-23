"""
Unit tests for LLMService delegation to the multi-provider caller (W1).

Verifies: mock path when no caller is wired; LLMCompletion → LLMResponse mapping;
error propagation; context/conversation-history assembly into the caller call;
per-call model override (its prefix selects the provider).
"""

from unittest.mock import AsyncMock, MagicMock

import pytest

from core.ports.llm_protocols import LLMCompletion
from core.services.llm_service import LLMConfig, LLMProvider, LLMResponse, LLMService
from core.utils.result_simplified import Errors, Result


def _caller(completion: LLMCompletion | None = None, error=None):
    caller = MagicMock()
    if error is not None:
        caller.complete = AsyncMock(return_value=Result.fail(error))
    else:
        caller.complete = AsyncMock(return_value=Result.ok(completion))
    return caller


@pytest.mark.asyncio
async def test_no_caller_returns_mock_response():
    service = LLMService()  # default MOCK provider, no caller → mock
    resp = await service.generate("How do I learn Python?")
    assert isinstance(resp, LLMResponse)
    assert resp.provider == LLMProvider.MOCK
    assert resp.content  # non-empty canned response
    assert resp.error is None


@pytest.mark.parametrize("provider", [LLMProvider.OPENAI, LLMProvider.ANTHROPIC])
def test_real_provider_without_caller_fails_fast(provider):
    """A real provider with no caller must raise (no silent mock fallback)."""
    with pytest.raises(ValueError, match="requires a"):
        LLMService(config=LLMConfig(provider=provider))


@pytest.mark.asyncio
async def test_delegates_and_maps_completion():
    caller = _caller(LLMCompletion(text="answer", model="gpt-4o", usage={"total_tokens": 9}))
    service = LLMService(
        config=LLMConfig(provider=LLMProvider.OPENAI, model_name="gpt-4o"), caller=caller
    )

    resp = await service.generate("q")

    assert resp.content == "answer"
    assert resp.provider == LLMProvider.OPENAI
    assert resp.model == "gpt-4o"
    assert resp.usage == {"total_tokens": 9}
    assert resp.error is None


@pytest.mark.asyncio
async def test_error_propagates_to_response():
    caller = _caller(error=Errors.integration(service="OpenAI", message="rate limited"))
    service = LLMService(config=LLMConfig(provider=LLMProvider.OPENAI), caller=caller)

    resp = await service.generate("q")

    assert resp.content == ""
    assert resp.error is not None
    assert "rate limited" in resp.error


@pytest.mark.asyncio
async def test_context_and_history_assembled_for_caller():
    caller = _caller(LLMCompletion(text="ok", model="gpt-4o"))
    service = LLMService(config=LLMConfig(provider=LLMProvider.OPENAI), caller=caller)

    await service.generate(
        "What next?",
        context="user has 3 overdue tasks",
        system_prompt="be helpful",
        conversation_history=[{"role": "user", "content": "earlier"}],
    )

    args, kwargs = caller.complete.call_args
    messages = args[0]
    assert messages[0] == {"role": "user", "content": "earlier"}
    assert messages[-1]["role"] == "user"
    assert "Context: user has 3 overdue tasks" in messages[-1]["content"]
    assert kwargs["system_prompt"] == "be helpful"
    assert kwargs["model"] == "gpt-4o-mini"  # config default


@pytest.mark.asyncio
async def test_per_call_model_override_routes_via_caller():
    """A per-call model overrides config.model_name — the caller routes on its prefix."""
    caller = _caller(LLMCompletion(text="from claude", model="claude-sonnet-4-6"))
    service = LLMService(config=LLMConfig(provider=LLMProvider.OPENAI), caller=caller)

    resp = await service.generate("q", model="claude-sonnet-4-6")

    assert resp.content == "from claude"
    assert resp.model == "claude-sonnet-4-6"
    # The response labels the provider the override routed to, not config's OPENAI default.
    assert resp.provider == LLMProvider.ANTHROPIC
    _, kwargs = caller.complete.call_args
    assert kwargs["model"] == "claude-sonnet-4-6"
