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
from core.services.dsl.activity_dsl_parser import parse_activity_line
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
async def test_transform_with_context_grounds_in_separate_nonextractable_slot():
    # Goal grounding must NOT sit inside the extractable journal text, or the
    # LLM can emit activity lines from the user's own goals (phantom entities on
    # the extraction path). It belongs in the {user_context} slot the prompt
    # marks "background only — do not extract" (ADR-069 § Decision 1.1).
    port = _port("")
    bridge = LLMDSLBridgeService(chat_port=port)

    result = await bridge.transform_with_context(
        "Need to email the landlord.",
        user_uid="user_mike",
        active_goals=[{"title": "Run a marathon"}],
    )

    assert result.is_ok
    prompt = port.complete.call_args.args[0][0]["content"]
    # Grounding reached the model, framed as non-extractable USER CONTEXT...
    assert "USER CONTEXT" in prompt
    assert "Run a marathon" in prompt
    assert "do NOT create activities" in prompt
    # ...and the journal text the model is told to extract from sits AFTER the
    # "JOURNAL TEXT TO ANALYZE" marker, with the goal NOT inside that section.
    journal_section = prompt.split("JOURNAL TEXT TO ANALYZE")[1]
    assert "Run a marathon" not in journal_section
    assert "email the landlord" in journal_section


@pytest.mark.asyncio
async def test_transform_with_context_ungrounded_omits_context_section():
    port = _port("")
    bridge = LLMDSLBridgeService(chat_port=port)

    result = await bridge.transform_with_context(
        "Need to email the landlord.", user_uid="user_mike", active_goals=None
    )

    assert result.is_ok
    prompt = port.complete.call_args.args[0][0]["content"]
    # The template instructions always mention a USER CONTEXT section; what must
    # be absent when ungrounded is the injected context BLOCK (its header + data).
    assert "do NOT create activities" not in prompt
    assert "Run a marathon" not in prompt


@pytest.mark.asyncio
async def test_bridge_output_carries_no_link_tag():
    # Links are the user's own: a @link id is a UID the model has no source for
    # (grounding passes titles), so any @link the model emits is dropped before
    # the line reaches the parser — every other tag survives.
    port = _port(
        "- @context(task) Work out @link(goal:goal_health_a1b2) @priority(2)\n"
        "- @context(habit) Meditate @link(goal:x, principle:y) @repeat(daily)"
    )
    bridge = LLMDSLBridgeService(chat_port=port)

    result = await bridge.transform("Work out and meditate.")

    assert result.is_ok
    assert result.value.activity_lines == [
        "- @context(task) Work out @priority(2)",
        "- @context(habit) Meditate @repeat(daily)",
    ]
    for line in result.value.activity_lines:
        parsed = parse_activity_line(line)
        assert parsed.is_ok
        assert parsed.value.links == []


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
