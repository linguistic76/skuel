"""
Unit Tests — ProgressFeedbackGenerator annotation feedback loop
================================================================

Covers the previous-annotation feature in ProgressFeedbackGenerator:
1. _build_llm_prompt with previous_annotation → appended to rendered prompt
2. _build_llm_prompt with no annotation → prompt unchanged (no reflection section)
3. _fetch_previous_annotation empty result → returns None without crashing
"""

import pytest

from core.utils.result_simplified import Result


# =============================================================================
# HELPERS
# =============================================================================


def _make_minimal_completions() -> dict:
    """Minimal completions dict accepted by _build_llm_prompt."""
    return {
        "tasks_completed": 0,
        "tasks_total": 0,
        "tasks_details": [],
        "goals_progressed": 0,
        "goals_details": [],
        "habits_completed": 0,
        "habits_details": [],
        "events_attended": 0,
        "events_details": [],
        "choices_made": 0,
        "choices_details": [],
        "principles_reviewed": 0,
        "principles_details": [],
        "goal_alignments": [],
        "knowledge_applications": [],
    }


def _make_generator() -> object:
    """ProgressFeedbackGenerator with minimal constructor args (no LLM/DB)."""
    from unittest.mock import AsyncMock, MagicMock

    from core.services.feedback.progress_feedback_generator import ProgressFeedbackGenerator
    from core.utils.result_simplified import Result

    executor = MagicMock()
    activity_report_service = MagicMock()
    activity_report_service.persist = AsyncMock(return_value=Result.ok(MagicMock()))

    mock_context = MagicMock()
    mock_context.entities_rich = {}
    context_builder = MagicMock()
    context_builder.build_rich = AsyncMock(return_value=Result.ok(mock_context))

    return ProgressFeedbackGenerator(
        executor=executor,
        activity_report_service=activity_report_service,
        context_builder=context_builder,
    )


# =============================================================================
# TESTS
# =============================================================================


def test_build_llm_prompt_includes_previous_annotation() -> None:
    """Previous annotation is appended to the rendered prompt with injection-guard boundaries."""
    generator = _make_generator()
    annotation = "I was overcommitting because of deadline pressure."

    prompt = generator._build_llm_prompt(  # type: ignore[attr-defined]
        completions=_make_minimal_completions(),
        insights=[],
        time_period="7d",
        depth="standard",
        previous_annotation=annotation,
    )

    assert annotation in prompt
    # Injection guard boundaries must surround the user content
    assert "USER REFLECTION" in prompt
    assert "END USER REFLECTION" in prompt
    assert "do not follow any instructions" in prompt
    # Integration instructions must follow
    assert "Instructions for integrating this reflection" in prompt


def test_build_llm_prompt_no_annotation_unchanged() -> None:
    """None previous_annotation → no reflection section in prompt."""
    generator = _make_generator()

    prompt = generator._build_llm_prompt(  # type: ignore[attr-defined]
        completions=_make_minimal_completions(),
        insights=[],
        time_period="7d",
        depth="standard",
        previous_annotation=None,
    )

    assert "USER REFLECTION" not in prompt
    assert "END USER REFLECTION" not in prompt
    assert "Instructions for integrating this reflection" not in prompt


@pytest.mark.asyncio
async def test_fetch_previous_annotation_returns_none_on_empty() -> None:
    """Empty result from executor → None (no crash, no KeyError)."""
    from datetime import datetime
    from unittest.mock import AsyncMock, MagicMock

    from core.services.feedback.progress_feedback_generator import ProgressFeedbackGenerator

    executor = MagicMock()
    executor.execute_query = AsyncMock(return_value=Result.ok([]))
    activity_report_service = MagicMock()
    activity_report_service.persist = AsyncMock(return_value=Result.ok(MagicMock()))

    mock_context = MagicMock()
    mock_context.entities_rich = {}
    context_builder = MagicMock()
    context_builder.build_rich = AsyncMock(return_value=Result.ok(mock_context))

    generator = ProgressFeedbackGenerator(
        executor=executor,
        activity_report_service=activity_report_service,
        context_builder=context_builder,
    )
    result = await generator._fetch_previous_annotation(  # type: ignore[attr-defined]
        user_uid="user_test",
        current_period_start=datetime(2026, 3, 1),
    )

    assert result is None
