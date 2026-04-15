"""Tests for UserEntryProcessingService dispatcher (ADR-054).

The dispatcher routes on `entry.pipeline`. `NONE` and `TEACHER_REVIEW` are
legitimate no-ops (entries are complete or waiting on a teacher queue).
The Deepgram/LLM pipelines return a `not_yet_wired` business error until
the legacy `SubmissionsProcessingService` + `JournalOutputService` are
retired (ADR-054 Step 11+).
"""

from unittest.mock import MagicMock

import pytest

from core.models.enums.pipeline import Pipeline
from core.models.user_entry.user_entry import UserEntry
from core.services.user_entry.user_entry_processing_service import (
    UserEntryProcessingService,
)


def _make_entry(pipeline: Pipeline) -> UserEntry:
    return UserEntry(
        uid=f"ue_{pipeline.value}",
        title=f"Entry {pipeline.value}",
        user_uid="user_1",
        pipeline=pipeline,
    )


def _make_dispatcher() -> UserEntryProcessingService:
    return UserEntryProcessingService(entry_service=MagicMock())


class TestNoOpPipelines:
    """NONE and TEACHER_REVIEW return the entry unchanged."""

    @pytest.mark.asyncio
    async def test_pipeline_none_is_noop(self):
        entry = _make_entry(Pipeline.NONE)
        result = await _make_dispatcher().process(entry)
        assert result.is_ok
        assert result.value is entry

    @pytest.mark.asyncio
    async def test_pipeline_teacher_review_is_noop(self):
        entry = _make_entry(Pipeline.TEACHER_REVIEW)
        result = await _make_dispatcher().process(entry)
        assert result.is_ok
        assert result.value is entry


class TestDeferredPipelines:
    """TRANSCRIBE / TRANSCRIBE_AND_STRUCTURE / LLM_SUMMARY are not yet wired."""

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "pipeline",
        [
            Pipeline.TRANSCRIBE,
            Pipeline.TRANSCRIBE_AND_STRUCTURE,
            Pipeline.LLM_SUMMARY,
        ],
    )
    async def test_deferred_pipeline_returns_not_yet_wired(self, pipeline: Pipeline):
        entry = _make_entry(pipeline)
        result = await _make_dispatcher().process(entry)
        assert result.is_error
        err = result.expect_error()
        assert "not yet" in str(err).lower() or "user_entry_pipeline_not_yet_wired" in str(err)


class TestEveryPipelineValueIsHandled:
    """Regression guard: every Pipeline value has a routing branch."""

    @pytest.mark.asyncio
    @pytest.mark.parametrize("pipeline", list(Pipeline))
    async def test_pipeline_value_does_not_fall_through(self, pipeline: Pipeline):
        entry = _make_entry(pipeline)
        result = await _make_dispatcher().process(entry)
        # Either ok (no-op) or explicit not-yet-wired — never the
        # fall-through "Unknown pipeline" validation error.
        if result.is_error:
            err_str = str(result.expect_error())
            assert "Unknown pipeline" not in err_str
