"""
Unit tests for LLMDSLBridgeService + the relocated factory (W1 PR4).

The bridge now delegates to a ChatCompletionPort; the factory that builds the
OpenAI chat adapter lives below the boundary in adapters/external/llm/.
"""

import re
from unittest.mock import AsyncMock, MagicMock

import pytest

from adapters.external.llm import create_llm_dsl_bridge
from adapters.external.llm.openai_adapter import OpenAIChatAdapter
from core.ports.llm_protocols import LLMCompletion
from core.services.dsl.activity_dsl_parser import (
    VAULT_AUTHORED_CONTEXTS,
    parse_activity_line,
    resolve_context_value,
)
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
async def test_bridge_output_carries_no_ku_tag():
    # Knowledge links are the user's own or the grounding service's: a @ku value
    # is a Ku uid the model has no source for, so any @ku it emits is dropped —
    # in any case, as the parser reads tag names — while the line and its other
    # tags survive. A model-written @Link goes the same way.
    port = _port(
        "- @context(task) Study dataframes @ku(ku.tech.pandas) @priority(2)\n"
        "- @context(task) Read the docs @KU(pandas) @when(2026-10-20)\n"
        "- @context(habit) Practise daily @Link(goal:goal_x) @repeat(daily)"
    )
    bridge = LLMDSLBridgeService(chat_port=port)

    result = await bridge.transform("Study pandas and practise daily.")

    assert result.is_ok
    assert result.value.activity_lines == [
        "- @context(task) Study dataframes @priority(2)",
        "- @context(task) Read the docs @when(2026-10-20)",
        "- @context(habit) Practise daily @repeat(daily)",
    ]
    for line in result.value.activity_lines:
        parsed = parse_activity_line(line)
        assert parsed.is_ok
        assert parsed.value.primary_ku is None
        assert parsed.value.links == []
    # Control: the parser reads a @ku on the same line when one is there.
    kept = parse_activity_line("- @context(task) Study dataframes @ku(ku.tech.pandas)")
    assert kept.is_ok
    assert kept.value.primary_ku == "ku.tech.pandas"


@pytest.mark.asyncio
@pytest.mark.parametrize("compact", [False, True])
async def test_bridge_prompt_offers_no_link_tag(compact: bool):
    # Neither prompt teaches the model a tag that names a uid: no @ku, no @link.
    port = _port("")
    bridge = LLMDSLBridgeService(chat_port=port, use_compact_prompt=compact)

    await bridge.transform("I want to learn Python for data science.")

    prompt = port.complete.call_args.args[0][0]["content"]
    assert _uid_tags_offered(prompt) == set()
    # Control: the same reader finds a uid tag when one is offered.
    assert _uid_tags_offered(prompt + "\nATTRS: @priority, @ku\n") == {"ku"}


def _uid_tags_offered(prompt: str) -> set[str]:
    """The uid-naming tags (``@ku``, ``@link``) a prompt mentions, in any case."""
    return {name.lower() for name in re.findall(r"@(ku|link)\b", prompt, flags=re.IGNORECASE)}


def _curriculum_names(prompt: str) -> set[str]:
    """Every context the prompt offers (``@context(x)`` tags and the DOMAINS list) that is curriculum."""
    offered = re.findall(r"@context\((\w+)\)", prompt)
    for domains_line in re.findall(r"^DOMAINS:(.*)$", prompt, flags=re.MULTILINE):
        offered.extend(name.strip() for name in domains_line.split(","))
    return {name for name in offered if resolve_context_value(name) in VAULT_AUTHORED_CONTEXTS}


@pytest.mark.asyncio
@pytest.mark.parametrize("compact", [False, True])
async def test_bridge_prompt_offers_no_curriculum_context(compact: bool):
    # Curriculum is authored in the content vault (ADR-091 S8), so neither prompt
    # offers the model a Ku, PathStep or LearningPath context to emit.
    port = _port("")
    bridge = LLMDSLBridgeService(chat_port=port, use_compact_prompt=compact)

    await bridge.transform("I want to learn Python for data science.")

    prompt = port.complete.call_args.args[0][0]["content"]
    assert _curriculum_names(prompt) == set()
    # Control: the same reader finds a curriculum name when one is offered.
    assert _curriculum_names(prompt + "\nDOMAINS: task, ku\n") == {"ku"}


@pytest.mark.asyncio
async def test_bridge_drops_a_curriculum_line_the_model_emits():
    # A model may still write a curriculum line; the bridge suggests none, in any
    # spelling or alongside another context, and keeps every other line whole.
    port = _port(
        "- @context(ku) Pandas library fundamentals\n"
        "- @context(PS) Dataframes step\n"
        "- @context(task,lp) Python for data science\n"
        "- @context(learningpath) Data path\n"
        "- @context(task) Work through the pandas tutorial @ku(ku.tech.pandas)\n"
        "- @context(goal) Learn Python for data science @priority(2)"
    )
    bridge = LLMDSLBridgeService(chat_port=port)

    result = await bridge.transform("I want to learn Python for data science.")

    assert result.is_ok
    assert result.value.activity_lines == [
        "- @context(task) Work through the pandas tutorial",
        "- @context(goal) Learn Python for data science @priority(2)",
    ]
    assert result.value.activities_identified == 2
    assert "kus" not in result.value.to_dict()["breakdown"]


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
