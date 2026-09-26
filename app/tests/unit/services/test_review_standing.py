"""The derived review standing read (Submit & Share arc R2) — converter and the one-entry service read."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from core.services.report.report_relationship_service import ReportRelationshipService
from core.services.report.review_standing import review_standing_from_row
from core.utils.result_simplified import Errors, Result


def test_converter_reads_the_two_derived_columns_and_defaults_absent_ones() -> None:
    assert review_standing_from_row({"reviewed_by": "llm", "revised_after_feedback": True}) == {
        "reviewed_by": "llm",
        "revised_after_feedback": True,
    }
    assert review_standing_from_row({}) == {"reviewed_by": None, "revised_after_feedback": False}


@pytest.mark.asyncio
async def test_service_returns_the_standing_or_none_for_no_row() -> None:
    backend = MagicMock()
    backend.get_entry_review_standing_raw = AsyncMock(
        return_value=Result.ok([{"reviewed_by": "human", "revised_after_feedback": False}])
    )
    service = ReportRelationshipService(backend=backend)
    result = await service.get_entry_review_standing("ue_1")
    assert result.is_ok
    assert result.value == {"reviewed_by": "human", "revised_after_feedback": False}
    backend.get_entry_review_standing_raw.assert_awaited_once_with("ue_1")

    backend.get_entry_review_standing_raw = AsyncMock(return_value=Result.ok([]))
    missing = await service.get_entry_review_standing("ue_missing")
    assert missing.is_ok and missing.value is None

    backend.get_entry_review_standing_raw = AsyncMock(
        return_value=Result.fail(Errors.database("read", "boom"))
    )
    failed = await service.get_entry_review_standing("ue_1")
    assert failed.is_error
