"""The enrichment context's active goals carry text, never ``None``.

The backend's row holds what the graph holds: a goal with no description stores
null, and a user with no active goal yields one all-null entry. The context a
prompt is built from names each real goal with strings and drops the empty entry.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from core.models.type_hints import UserUID
from core.services.content_enrichment_service import ContentEnrichmentService
from core.utils.result_simplified import Result


def _service(rows: list[dict[str, object]]) -> ContentEnrichmentService:
    backend = MagicMock()
    backend.get_journal_processing_context = AsyncMock(return_value=Result.ok(rows))
    return ContentEnrichmentService(backend=backend)


@pytest.mark.asyncio
async def test_a_goal_without_a_description_reads_as_empty_text() -> None:
    goals = [
        {"uid": "goal_0000000000000001", "title": "Run 10k", "description": None},
        {"uid": None, "title": None, "description": None},
    ]
    service = _service([{"context": {"active_goals": goals}}])

    result = await service.get_journal_context_for_processing(UserUID("user_0000000000000001"))

    assert result.is_ok
    assert result.value.active_goals == [
        {"uid": "goal_0000000000000001", "title": "Run 10k", "description": ""}
    ]


@pytest.mark.asyncio
async def test_no_row_is_no_goals() -> None:
    result = await _service([]).get_journal_context_for_processing(UserUID("user_0000000000000001"))

    assert result.is_ok
    assert result.value.active_goals == []
