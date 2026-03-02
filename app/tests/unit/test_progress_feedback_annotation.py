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

    from core.services.feedback.activity_data_reader import ActivityData, ActivityDataReader
    from core.services.feedback.progress_feedback_generator import ProgressFeedbackGenerator
    from core.utils.result_simplified import Result

    executor = MagicMock()
    ku_backend = MagicMock()
    reader = MagicMock(spec=ActivityDataReader)
    reader.read = AsyncMock(return_value=Result.ok(ActivityData()))
    return ProgressFeedbackGenerator(
        executor=executor, ku_backend=ku_backend, activity_data_reader=reader
    )


# =============================================================================
# TESTS
# =============================================================================


def test_build_llm_prompt_includes_previous_annotation() -> None:
    """Previous annotation is appended to the rendered prompt."""
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
    assert "Please acknowledge" in prompt
    assert "previous activity report" in prompt


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

    assert "previous activity report" not in prompt
    assert "Please acknowledge" not in prompt


@pytest.mark.asyncio
async def test_fetch_previous_annotation_returns_none_on_empty() -> None:
    """Empty result from executor → None (no crash, no KeyError)."""
    from unittest.mock import AsyncMock, MagicMock
    from datetime import datetime

    from core.services.feedback.activity_data_reader import ActivityData, ActivityDataReader
    from core.services.feedback.progress_feedback_generator import ProgressFeedbackGenerator

    executor = MagicMock()
    executor.execute_query = AsyncMock(return_value=Result.ok([]))
    ku_backend = MagicMock()
    reader = MagicMock(spec=ActivityDataReader)
    reader.read = AsyncMock(return_value=Result.ok(ActivityData()))

    generator = ProgressFeedbackGenerator(
        executor=executor, ku_backend=ku_backend, activity_data_reader=reader
    )
    result = await generator._fetch_previous_annotation(  # type: ignore[attr-defined]
        user_uid="user_test",
        current_period_start=datetime(2026, 3, 1),
    )

    assert result is None
