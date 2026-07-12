"""Scope override — an explicit facet scope bypasses the guided/ZPD pipeline.

PR2 (Scoped Ask) + Codex #544: when the user picks a NOUS topic, the answer must
come from the SCOPED passages (context-aware path), NOT the current PS bundle
(guided path) — otherwise the topic selection is a silent no-op for the guided
users who have an active Path Step. Reuses the proven pipeline mock harness.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

from core.models.search_request import SearchRequest
from core.services.canon import CanonContext
from tests.unit.test_askesis_enrollment_gate import _make_processor, _make_user_context


async def test_explicit_scope_bypasses_guided_pipeline() -> None:
    # An active Path Step would normally trigger the guided pipeline...
    processor, llm_mock = _make_processor(_make_user_context(current_ps_uids={"ps.test.step"}))
    guided = AsyncMock(
        return_value=("GUIDED PROMPT", "socratic", MagicMock(), CanonContext.empty())
    )
    retrieve = AsyncMock(return_value={})

    with (
        patch.object(processor, "_run_guided_pipeline", guided),
        patch.object(processor.context_retriever, "retrieve_relevant_context", retrieve),
    ):
        result = await processor.answer_user_question(
            "user_test", "Tell me about breathing", scope=SearchRequest(nous="body")
        )

    assert result.is_ok
    # ...but an explicit scope overrides it: the guided pipeline never runs,
    guided.assert_not_awaited()
    # the scope reaches retrieval (4th positional arg),
    assert retrieve.await_args is not None
    passed_scope = retrieve.await_args.args[3]
    assert passed_scope is not None
    assert passed_scope.to_property_filters() == {"nous": "body"}
    # and the context-aware (scoped) path produces the answer.
    llm_mock.generate_context_aware_answer.assert_awaited()
    assert result.value["answer"] == "A real answer."


async def test_no_scope_runs_guided_pipeline() -> None:
    # Negative control: with no scope, the guided pipeline runs as before.
    processor, _ = _make_processor(_make_user_context(current_ps_uids={"ps.test.step"}))
    # no guided prompt → context-aware branch
    guided = AsyncMock(return_value=(None, None, None, CanonContext.empty()))

    with patch.object(processor, "_run_guided_pipeline", guided):
        result = await processor.answer_user_question("user_test", "What should I learn?")

    assert result.is_ok
    guided.assert_awaited()
