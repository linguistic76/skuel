"""
Tests for Askesis canon grounding (ADR-077 PR-B).

The guided pipeline retrieves PS-scoped canon readings (scope = the bundle's
cited Resources, keyed on the learner's question), the teaching block lands in
the guided system prompt, and canon sources thread to answer_user_question's
response dict — while process_query_with_context gains grounded prompts only
(no canon_sources key). Everything fails soft: no canon service, no cited
Resources, or a retrieval error all degrade to canon-free guidance.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock

from fasthtml.common import to_xml

from core.models.enums import GuidanceMode
from core.models.query_types import QueryIntent
from core.services.askesis.query_processor import QueryProcessor
from core.services.askesis.response_generator import ResponseGenerator
from core.services.canon import CanonContext, CanonPassage, CanonSource
from core.utils.result_simplified import Errors, Result
from ui.askesis.chat import render_assistant_message

# ============================================================================
# Fixtures
# ============================================================================


def _passage() -> CanonPassage:
    return CanonPassage(
        text="Hypermedia is a media type with hypermedia controls.",
        book_title="Hypermedia Systems",
        resource_uid="resource.hypermedia-systems",
        similarity_score=0.91,
        heading="A Brief History of Hypermedia",
        section_path="Hypermedia Concepts > Hypermedia: A Reintroduction",
        sequence=7,
    )


def _canon_context() -> CanonContext:
    return CanonContext(passages=(_passage(),))


def _make_resource(uid: str) -> MagicMock:
    resource = MagicMock()
    resource.uid = uid
    return resource


def _make_bundle(resources: tuple[Any, ...]) -> MagicMock:
    bundle = MagicMock()
    bundle.resources = resources
    bundle.curriculum_context_text = ""
    return bundle


def _make_user_context() -> MagicMock:
    ctx = MagicMock()
    ctx.current_ps_uids = {"ps.web.hypermedia-foundations"}
    ctx.enrolled_path_uids = []
    ctx.active_path_steps_rich = []
    return ctx


def _make_processor(
    *,
    canon_service: MagicMock | None,
    bundle_result: Result[Any],
) -> tuple[QueryProcessor, dict[str, MagicMock]]:
    """QueryProcessor with mocked sub-services and a controllable PS bundle."""
    intent_classifier = MagicMock()
    intent_classifier.classify_intent = AsyncMock(return_value=Result.ok(QueryIntent.EXPLORATORY))
    guidance = MagicMock()
    guidance.mode = GuidanceMode.SOCRATIC
    intent_classifier.determine_guidance_mode = MagicMock(return_value=guidance)

    response_generator = MagicMock()
    response_generator.build_guided_system_prompt = MagicMock(return_value="guided prompt")
    response_generator.build_llm_context = MagicMock(return_value="llm context")
    response_generator.generate_actions = MagicMock(return_value=[])
    response_generator.generate_suggested_actions = MagicMock(return_value=[])

    entity_extractor = MagicMock()
    entity_extractor.extract_entities_from_query = AsyncMock(return_value={})
    entity_extractor.extract_from_bundle = MagicMock(return_value=[])

    context_retriever = MagicMock()
    context_retriever.retrieve_relevant_context = AsyncMock(return_value={})
    context_retriever.load_ps_bundle = AsyncMock(return_value=bundle_result)
    context_retriever.get_learning_context = AsyncMock(
        return_value=Result.ok(
            {"knowledge_units": [], "learning_paths": [], "related_tasks": [], "related_goals": []}
        )
    )

    user_service = MagicMock()
    user_service.get_rich_unified_context = AsyncMock(return_value=Result.ok(_make_user_context()))
    user_service.add_conversation_message = AsyncMock(return_value=Result.ok(True))

    llm_service = MagicMock()
    llm_service.generate = AsyncMock(return_value=MagicMock(content="Guided answer."))
    llm_service.generate_context_aware_answer = AsyncMock(return_value="Context answer.")

    processor = QueryProcessor(
        intent_classifier=intent_classifier,
        response_generator=response_generator,
        entity_extractor=entity_extractor,
        context_retriever=context_retriever,
        user_service=user_service,
        llm_service=llm_service,
        graph_intel=MagicMock(),
        zpd_service=MagicMock(),
        canon_service=canon_service,
    )
    mocks = {
        "response_generator": response_generator,
        "llm_service": llm_service,
    }
    return processor, mocks


# ============================================================================
# _run_guided_pipeline — canon retrieval behavior
# ============================================================================


async def test_pipeline_retrieves_canon_scoped_to_bundle_resources() -> None:
    """Retrieval is keyed on the QUESTION and scoped to the bundle's Resources."""
    canon_service = MagicMock()
    canon_service.retrieve = AsyncMock(return_value=Result.ok(_canon_context()))
    bundle = _make_bundle((_make_resource("resource.hypermedia-systems"),))
    processor, mocks = _make_processor(canon_service=canon_service, bundle_result=Result.ok(bundle))

    prompt, _mode, ps_bundle, canon_context = await processor._run_guided_pipeline(
        "user_test", "What is hypermedia?", _make_user_context()
    )

    canon_service.retrieve.assert_awaited_once_with(
        "What is hypermedia?", resource_uids=["resource.hypermedia-systems"]
    )
    assert canon_context.has_passages
    assert prompt == "guided prompt"
    assert ps_bundle is bundle
    # The teaching block reaches the prompt build (B3 seam)
    _, kwargs = mocks["response_generator"].build_guided_system_prompt.call_args
    assert kwargs["canon_context"] is canon_context


async def test_pipeline_skips_retrieval_when_no_cited_resources() -> None:
    """A PS citing nothing shelved → no retrieval call, empty canon context."""
    canon_service = MagicMock()
    canon_service.retrieve = AsyncMock()
    processor, _ = _make_processor(
        canon_service=canon_service, bundle_result=Result.ok(_make_bundle(()))
    )

    _, _, _, canon_context = await processor._run_guided_pipeline(
        "user_test", "What is hypermedia?", _make_user_context()
    )

    canon_service.retrieve.assert_not_awaited()
    assert not canon_context.has_passages


async def test_pipeline_without_canon_service_degrades_canon_free() -> None:
    """CORE tier (canon_service=None) → empty context, no crash."""
    bundle = _make_bundle((_make_resource("resource.hypermedia-systems"),))
    processor, _ = _make_processor(canon_service=None, bundle_result=Result.ok(bundle))

    prompt, _, _, canon_context = await processor._run_guided_pipeline(
        "user_test", "What is hypermedia?", _make_user_context()
    )

    assert prompt == "guided prompt"
    assert not canon_context.has_passages


async def test_pipeline_fails_soft_on_retrieval_error() -> None:
    """A canon retrieval error never breaks the session — guidance stays canon-free."""
    canon_service = MagicMock()
    canon_service.retrieve = AsyncMock(
        return_value=Result.fail(Errors.system(message="embedding down", operation="retrieve"))
    )
    bundle = _make_bundle((_make_resource("resource.hypermedia-systems"),))
    processor, _ = _make_processor(canon_service=canon_service, bundle_result=Result.ok(bundle))

    prompt, _, _, canon_context = await processor._run_guided_pipeline(
        "user_test", "What is hypermedia?", _make_user_context()
    )

    assert prompt == "guided prompt"
    assert not canon_context.has_passages


async def test_pipeline_bundle_error_returns_empty_canon_context() -> None:
    """No bundle → the 4-tuple degrades whole: (None, None, None, empty)."""
    canon_service = MagicMock()
    canon_service.retrieve = AsyncMock()
    processor, _ = _make_processor(
        canon_service=canon_service,
        bundle_result=Result.fail(Errors.not_found("path_step", "no_active_ps")),
    )

    prompt, mode, ps_bundle, canon_context = await processor._run_guided_pipeline(
        "user_test", "What is hypermedia?", _make_user_context()
    )

    assert (prompt, mode, ps_bundle) == (None, None, None)
    assert not canon_context.has_passages
    canon_service.retrieve.assert_not_awaited()


# ============================================================================
# build_guided_system_prompt — teaching block append (B3)
# ============================================================================


def _make_response_generator() -> ResponseGenerator:
    generator = ResponseGenerator()
    # Patch the mode builder — the append seam is what's under test, not templates.
    generator._build_socratic_prompt = MagicMock(return_value="BASE PROMPT")  # type: ignore[method-assign]
    return generator


def _guidance() -> MagicMock:
    guidance = MagicMock()
    guidance.mode = GuidanceMode.SOCRATIC
    return guidance


def test_guided_prompt_appends_teaching_block_when_passages_exist() -> None:
    generator = _make_response_generator()

    prompt = generator.build_guided_system_prompt(
        _guidance(), MagicMock(), MagicMock(), canon_context=_canon_context()
    )

    assert prompt.startswith("BASE PROMPT")
    assert "## Readings for This Step" in prompt
    assert "Hypermedia Systems" in prompt


def test_guided_prompt_direct_mode_gets_answer_framing_not_socratic() -> None:
    """DIRECT mode promises answers (Codex #613 P2): the readings block grounds
    the answer — it must NOT instruct the model to ask a better question."""
    generator = ResponseGenerator()
    generator._build_direct_prompt = MagicMock(return_value="DIRECT BASE")  # type: ignore[method-assign]
    guidance = MagicMock()
    guidance.mode = GuidanceMode.DIRECT

    prompt = generator.build_guided_system_prompt(
        guidance, MagicMock(), MagicMock(), canon_context=_canon_context()
    )

    assert prompt.startswith("DIRECT BASE")
    assert "## Readings for This Step" in prompt
    assert "Do not surrender the method" not in prompt
    assert "Answer directly" in prompt
    # Faithfulness contract holds in both framings
    assert "never invent a passage, chapter, or section" in prompt


def test_guided_prompt_socratic_mode_keeps_the_method() -> None:
    generator = _make_response_generator()

    prompt = generator.build_guided_system_prompt(
        _guidance(), MagicMock(), MagicMock(), canon_context=_canon_context()
    )

    assert "Do not surrender the method" in prompt


def test_guided_prompt_unchanged_when_canon_context_empty() -> None:
    generator = _make_response_generator()

    prompt = generator.build_guided_system_prompt(
        _guidance(), MagicMock(), MagicMock(), canon_context=CanonContext.empty()
    )

    assert prompt == "BASE PROMPT"


def test_guided_prompt_unchanged_when_canon_context_none() -> None:
    generator = _make_response_generator()

    prompt = generator.build_guided_system_prompt(_guidance(), MagicMock(), MagicMock())

    assert prompt == "BASE PROMPT"


# ============================================================================
# Response threading (B4) — answer_user_question vs process_query_with_context
# ============================================================================


async def test_answer_response_carries_canon_sources() -> None:
    """answer_user_question's response dict carries the CanonSource list."""
    canon_service = MagicMock()
    canon_service.retrieve = AsyncMock(return_value=Result.ok(_canon_context()))
    bundle = _make_bundle((_make_resource("resource.hypermedia-systems"),))
    processor, _ = _make_processor(canon_service=canon_service, bundle_result=Result.ok(bundle))

    result = await processor.answer_user_question("user_test", "What is hypermedia?")

    assert result.is_ok
    sources = result.value["canon_sources"]
    assert len(sources) == 1
    assert sources[0].book_title == "Hypermedia Systems"
    assert sources[0].resource_uid == "resource.hypermedia-systems"


async def test_answer_response_canon_sources_empty_when_no_draw() -> None:
    """No cited Resources → canon_sources is [] (key present, silent degrade)."""
    processor, _ = _make_processor(canon_service=None, bundle_result=Result.ok(_make_bundle(())))

    result = await processor.answer_user_question("user_test", "What is hypermedia?")

    assert result.is_ok
    assert result.value["canon_sources"] == []


async def test_process_query_response_has_no_canon_sources_key() -> None:
    """process_query_with_context gains grounded prompts only — no sources surface (P1)."""
    canon_service = MagicMock()
    canon_service.retrieve = AsyncMock(return_value=Result.ok(_canon_context()))
    bundle = _make_bundle((_make_resource("resource.hypermedia-systems"),))
    processor, _ = _make_processor(canon_service=canon_service, bundle_result=Result.ok(bundle))

    result = await processor.process_query_with_context("user_test", "What is hypermedia?")

    assert result.is_ok
    assert "canon_sources" not in result.value
    # The grounded prompt is deliberate for this path (ruled 2026-07-11):
    # retrieval still ran, scoped to the bundle's Resources.
    canon_service.retrieve.assert_awaited_once()


# ============================================================================
# render_assistant_message — CanonSourcesBlock (B5)
# ============================================================================


def _canon_source() -> CanonSource:
    return CanonSource(
        book_title="Hypermedia Systems",
        resource_uid="resource.hypermedia-systems",
        locators=("Hypermedia Concepts > Hypermedia: A Reintroduction",),
    )


def test_assistant_message_renders_canon_sources_block() -> None:
    html = to_xml(render_assistant_message("An answer.", canon_sources=(_canon_source(),)))

    assert "Hypermedia Systems" in html
    assert "/library/resources/get?uid=resource.hypermedia-systems" in html
    assert "Sources" in html
    # The per-message Alpine accordion state stays intact (a11y)
    assert "sourcesOpen" in html


def test_assistant_message_omits_canon_block_when_absent() -> None:
    html = to_xml(render_assistant_message("An answer."))

    assert "/library/resources/get" not in html
