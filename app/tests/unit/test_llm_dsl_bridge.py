"""
Unit tests for LLMDSLBridgeService + the relocated factory (W1 PR4).

The bridge now delegates to a ChatCompletionPort; the factory that builds the
OpenAI chat adapter lives below the boundary in adapters/external/llm/.
"""

from unittest.mock import AsyncMock, MagicMock

import pytest

from adapters.external.llm import create_llm_dsl_bridge
from adapters.external.llm.openai_adapter import OpenAIChatAdapter
from core.ports.llm_protocols import LLMCompletion
from core.services.dsl.llm_dsl_bridge import LLMDSLBridgeService
from core.utils.result_simplified import Result


def _port(text: str):
    port = MagicMock()
    port.complete = AsyncMock(return_value=Result.ok(LLMCompletion(text=text, model="gpt-4o-mini")))
    return port


@pytest.mark.asyncio
async def test_transform_delegates_to_chat_port_and_parses_dsl():
    port = _port("- @context(task) Finish the report @when(Friday)")
    bridge = LLMDSLBridgeService(chat_port=port)

    result = await bridge.transform("I need to finish the report by Friday.")

    assert result.is_ok
    assert result.value.activities_identified == 1
    assert result.value.tasks_identified == 1
    assert "@context(task)" in result.value.transformed_text
    # system prompt + model forwarded to the port
    kwargs = port.complete.call_args.kwargs
    assert kwargs["model"] == "gpt-4o-mini"
    assert "extraction assistant" in kwargs["system_prompt"]


@pytest.mark.asyncio
async def test_transform_without_chat_port_fails():
    bridge = LLMDSLBridgeService(chat_port=None)
    result = await bridge.transform("anything")
    assert result.is_error
    assert "chat adapter" in str(result.expect_error()).lower()


@pytest.mark.asyncio
async def test_transform_empty_text_is_ok_noop():
    bridge = LLMDSLBridgeService(chat_port=_port("ignored"))
    result = await bridge.transform("   ")
    assert result.is_ok
    assert result.value.transformed_text == ""


def test_factory_with_key_builds_openai_adapter():
    bridge = create_llm_dsl_bridge(openai_api_key="test-key")
    assert isinstance(bridge, LLMDSLBridgeService)
    assert isinstance(bridge.chat_port, OpenAIChatAdapter)


def _no_credential(*_args, **_kwargs):
    return None


def test_factory_without_key_yields_no_chat_port(monkeypatch):
    monkeypatch.setattr("core.config.credential_store.get_credential", _no_credential)
    bridge = create_llm_dsl_bridge(openai_api_key=None)
    assert isinstance(bridge, LLMDSLBridgeService)
    assert bridge.chat_port is None
