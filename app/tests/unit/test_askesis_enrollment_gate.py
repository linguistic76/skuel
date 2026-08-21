"""
Tests for the Askesis enrollment gate — PS-first, LP when available.

The gate (systems-review Arc B) passes when the user has an active PathStep
(``current_ps_uids``, from the IN_PROGRESS edge the PS enrollment door writes)
OR an enrolled Learning Path (``enrolled_path_uids``). Only a user with
neither gets the enrollment stub.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock

from core.models.query_types import QueryIntent
from core.services.askesis.query_processor import (
    _ENROLLMENT_GATE_RESPONSE,
    QueryProcessor,
    _passes_enrollment_gate,
)
from core.utils.result_simplified import Errors, Result


def _make_user_context(
    current_ps_uids: set[str] | None = None,
    enrolled_path_uids: list[str] | None = None,
) -> MagicMock:
    ctx = MagicMock()
    ctx.current_ps_uids = current_ps_uids or set()
    ctx.enrolled_path_uids = enrolled_path_uids or []
    ctx.active_path_steps_rich = []
    return ctx


def _make_processor(user_context: MagicMock) -> tuple[QueryProcessor, MagicMock]:
    """Build a QueryProcessor with mocked sub-services; returns (processor, llm mock).

    Pipelines past the gate are stubbed to complete without a real LLM:
    the PS bundle load fails (no guided prompt) so the context-aware path runs.
    """
    intent_classifier = MagicMock()
    intent_classifier.classify_intent = AsyncMock(return_value=Result.ok(QueryIntent.EXPLORATORY))

    response_generator = MagicMock()
    response_generator.build_llm_context = MagicMock(return_value="llm context")
    response_generator.generate_actions = MagicMock(return_value=[])
    response_generator.generate_suggested_actions = MagicMock(return_value=[])

    entity_extractor = MagicMock()
    entity_extractor.extract_entities_from_query = AsyncMock(return_value={})

    context_retriever = MagicMock()
    context_retriever.retrieve_relevant_context = AsyncMock(return_value={})
    context_retriever.load_ps_bundle = AsyncMock(
        return_value=Result.fail(Errors.not_found("path_step", "no_active_ps"))
    )
    context_retriever.get_learning_context = AsyncMock(
        return_value=Result.ok(
            {"knowledge_units": [], "learning_paths": [], "related_tasks": [], "related_goals": []}
        )
    )

    user_service = MagicMock()
    user_service.get_rich_unified_context = AsyncMock(return_value=Result.ok(user_context))
    user_service.add_conversation_message = AsyncMock(return_value=Result.ok(True))

    llm_service = MagicMock()
    llm_service.generate_context_aware_answer = AsyncMock(return_value="A real answer.")

    processor = QueryProcessor(
        intent_classifier=intent_classifier,
        response_generator=response_generator,
        entity_extractor=entity_extractor,
        context_retriever=context_retriever,
        user_service=user_service,
        llm_service=llm_service,
        zpd_service=MagicMock(),
    )
    return processor, llm_service


# ============================================================================
# _passes_enrollment_gate — the gate predicate itself
# ============================================================================


def test_gate_passes_with_ps_only() -> None:
    ctx = _make_user_context(current_ps_uids={"ps.mindfulness.breath-awareness-basics"})
    assert _passes_enrollment_gate(ctx) is True


def test_gate_passes_with_lp_only() -> None:
    ctx = _make_user_context(enrolled_path_uids=["lp.mindfulness-101"])
    assert _passes_enrollment_gate(ctx) is True


def test_gate_passes_with_both() -> None:
    ctx = _make_user_context(current_ps_uids={"ps.test.step"}, enrolled_path_uids=["lp.test-path"])
    assert _passes_enrollment_gate(ctx) is True


def test_gate_blocks_with_neither() -> None:
    assert _passes_enrollment_gate(_make_user_context()) is False


# ============================================================================
# Pipeline short-circuit behavior (answer_user_question)
# ============================================================================


async def test_answer_returns_stub_for_unenrolled_user() -> None:
    """Neither PS nor LP → the enrollment stub, before any LLM call."""
    processor, llm_mock = _make_processor(_make_user_context())

    result = await processor.answer_user_question("user_test", "What should I learn?")

    assert result.is_ok
    assert result.value == _ENROLLMENT_GATE_RESPONSE
    assert result.value["mode"] == "enrollment_gate"
    llm_mock.generate_context_aware_answer.assert_not_awaited()


async def test_answer_proceeds_with_ps_only() -> None:
    """An active PathStep alone (no LP enrollment) unlocks the pipeline."""
    processor, _ = _make_processor(_make_user_context(current_ps_uids={"ps.test.step"}))

    result = await processor.answer_user_question("user_test", "What should I learn?")

    assert result.is_ok
    assert result.value["mode"] != "enrollment_gate"
    assert result.value["answer"] == "A real answer."


async def test_answer_proceeds_with_lp_only() -> None:
    """An enrolled Learning Path alone still unlocks the pipeline."""
    processor, _ = _make_processor(_make_user_context(enrolled_path_uids=["lp.test-path"]))

    result = await processor.answer_user_question("user_test", "What should I learn?")

    assert result.is_ok
    assert result.value["mode"] != "enrollment_gate"


# ============================================================================
# Pipeline short-circuit behavior (process_query_with_context)
# ============================================================================


async def test_process_query_returns_stub_for_unenrolled_user() -> None:
    processor, _ = _make_processor(_make_user_context())

    result = await processor.process_query_with_context("user_test", "What next?")

    assert result.is_ok
    assert result.value == _ENROLLMENT_GATE_RESPONSE


async def test_process_query_proceeds_with_ps_only() -> None:
    processor, _ = _make_processor(_make_user_context(current_ps_uids={"ps.test.step"}))

    result = await processor.process_query_with_context("user_test", "What next?")

    assert result.is_ok
    assert result.value.get("mode") != "enrollment_gate"


# ============================================================================
# Gate response shape
# ============================================================================


def test_gate_response_points_at_path_step_first() -> None:
    """The stub's self-serve door is PathStep enrollment; LP is secondary."""
    assert "Path Step" in _ENROLLMENT_GATE_RESPONSE["answer"]
    actions: list[dict[str, Any]] = _ENROLLMENT_GATE_RESPONSE["suggested_actions"]
    assert actions[0]["action"] == "start_path_step"
    assert any(a["action"] == "enroll_learning_path" for a in actions)
