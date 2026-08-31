"""AGGREGATION delivery — the outcome REACHES the learner on every served path.

Tool-selection first slice (docs/roadmap/askesis-tool-selection-queries.md § 6-7,
ruled 2026-08-31). Selection is where the design looks; delivery is where it
silently fails — a count computed in the retriever means nothing if the answer
the learner reads never contains it. These pin, per answer path:

- ``answer_user_question`` (normal chat, guided-eligible AND facet-scoped):
  the outcome's own text IS the answer; generation is short-circuited on every
  outcome, so the model cannot invent a count or answer around a decline; the
  guided pipeline is bypassed — an aggregation result never enters the
  deliberately narrow Socratic prompt (ADR-077 preserved).
- ``process_query_with_context`` (the API surface): ruled NOT to serve the
  tool — it declines deterministically instead of letting ordinary generation
  answer a count question generically.

The executor's own invariants (cross-tenant injection, coverage decline) are
GUARD 3 of tests/unit/test_askesis_intent_filter_activation_guard.py.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

from core.models.query_types import QueryIntent
from core.models.search_request import SearchRequest
from core.services.askesis.query_tools import (
    AggregationAnswered,
    AggregationCount,
    AggregationDeclined,
    AggregationUnavailable,
)
from core.utils.result_simplified import Result
from tests.unit.test_askesis_enrollment_gate import _make_processor, _make_user_context

_ANSWERED = AggregationAnswered(
    payload=AggregationCount(
        subject="goals achieved", total=4, since="2026-04-01", until="2026-06-30"
    )
)


def _aggregation_processor(outcome, scope=None):
    """Processor whose classifier says AGGREGATION and whose retriever produced
    ``outcome`` (None = the branch produced nothing — the mis-wiring floor)."""
    processor, llm_mock = _make_processor(_make_user_context(current_ps_uids={"ps.test.step"}))
    processor.intent_classifier.classify_intent = AsyncMock(
        return_value=Result.ok(QueryIntent.AGGREGATION)
    )
    context = {} if outcome is None else {"aggregation": outcome}
    processor.context_retriever.retrieve_relevant_context = AsyncMock(return_value=context)
    return processor, llm_mock


async def test_covered_count_reaches_the_answer_in_normal_chat() -> None:
    """A guided-eligible user's count question gets the REAL count — the guided
    branch is bypassed, not fed the aggregation (the pedagogical ruling: count
    questions are not Socratic turns; the Socratic prompt is untouched)."""
    processor, llm_mock = _aggregation_processor(_ANSWERED)
    guided = AsyncMock()

    with patch.object(processor, "_run_guided_pipeline", guided):
        result = await processor.answer_user_question("user_test", "how many goals last quarter?")

    assert result.is_ok
    assert result.value["answer"] == _ANSWERED.answer_text()
    assert "4" in result.value["answer"]
    assert result.value["mode"] == "aggregation"
    # deterministic delivery: no generation ran, guided never consulted
    guided.assert_not_awaited()
    llm_mock.generate_context_aware_answer.assert_not_awaited()
    llm_mock.generate.assert_not_called()
    # context_used carries the JSON-safe projection, not the outcome object
    assert result.value["context_used"]["aggregation"] == _ANSWERED.to_context()


async def test_covered_count_reaches_the_answer_on_a_scoped_call() -> None:
    """The nous-scoped (context-aware) path delivers the same deterministic answer."""
    processor, llm_mock = _aggregation_processor(_ANSWERED)

    result = await processor.answer_user_question(
        "user_test", "how many goals last quarter?", scope=SearchRequest(nous="body")
    )

    assert result.is_ok
    assert result.value["answer"] == _ANSWERED.answer_text()
    llm_mock.generate_context_aware_answer.assert_not_awaited()


async def test_decline_reaches_the_learner_and_short_circuits_generation() -> None:
    """OPEN PROBLEM 2, closed by construction: the decline is the answer itself,
    not a hint in prompt context the model can ignore."""
    declined = AggregationDeclined(reason="none of my count tools covers this question.")
    processor, llm_mock = _aggregation_processor(declined)

    result = await processor.answer_user_question("user_test", "what is my streak?")

    assert result.is_ok
    assert result.value["answer"] == declined.answer_text()
    assert "none of my count tools covers this question." in result.value["answer"]
    llm_mock.generate_context_aware_answer.assert_not_awaited()
    llm_mock.generate.assert_not_called()


async def test_failure_is_unavailable_not_generation() -> None:
    """A selection/tool failure must not fall back to baseline generation — that
    path could produce a plausible INVENTED count through the error door."""
    unavailable = AggregationUnavailable(reason="provider outage")
    processor, llm_mock = _aggregation_processor(unavailable)

    result = await processor.answer_user_question("user_test", "how many goals last quarter?")

    assert result.is_ok
    assert result.value["answer"] == unavailable.answer_text()
    llm_mock.generate_context_aware_answer.assert_not_awaited()


async def test_missing_outcome_floors_to_unavailable() -> None:
    """The pipeline holds its own floor: an AGGREGATION verdict with no outcome
    object (a mis-wired retriever) still never reaches generation."""
    processor, llm_mock = _aggregation_processor(outcome=None)

    result = await processor.answer_user_question("user_test", "how many goals last quarter?")

    assert result.is_ok
    assert result.value["answer"] == AggregationUnavailable(reason="").answer_text()
    llm_mock.generate_context_aware_answer.assert_not_awaited()


async def test_process_query_with_context_declines_aggregation() -> None:
    """The API surface is ruled NOT to serve the tool — it declines instead of
    letting ordinary generation answer a count question (the documented
    delivery decision, not an omission)."""
    processor, llm_mock = _make_processor(_make_user_context(current_ps_uids={"ps.test.step"}))
    processor.intent_classifier.classify_intent = AsyncMock(
        return_value=Result.ok(QueryIntent.AGGREGATION)
    )
    guided = AsyncMock()

    with patch.object(processor, "_run_guided_pipeline", guided):
        result = await processor.process_query_with_context("user_test", "how many goals?")

    assert result.is_ok
    assert result.value["response"].startswith("I can't answer that count yet")
    guided.assert_not_awaited()
    llm_mock.generate_context_aware_answer.assert_not_awaited()
    llm_mock.generate.assert_not_called()


async def test_non_aggregation_intents_are_untouched() -> None:
    """Control: every other intent still flows to its existing answer branch."""
    processor, llm_mock = _make_processor(_make_user_context(current_ps_uids={"ps.test.step"}))

    result = await processor.answer_user_question("user_test", "what should I learn?")

    assert result.is_ok
    assert result.value["answer"] == "A real answer."
    llm_mock.generate_context_aware_answer.assert_awaited()
