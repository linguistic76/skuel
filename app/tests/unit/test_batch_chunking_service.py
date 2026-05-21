"""
Unit tests for BatchChunkingService.

Covers the orchestration logic (filtering, concurrency, error isolation, stats)
using mocked dependencies. Integration with the real Neo4j and chunking
algorithm is exercised separately in tests/integration/.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from core.services.chunks.batch_chunking_service import (
    BatchChunkingService,
    RegenerationStats,
)
from core.utils.result_simplified import Errors, Result


def _make_driver_returning(rows: list[dict[str, Any]]) -> MagicMock:
    """Build a driver whose session().run() yields the given rows."""
    session = MagicMock()
    session.__aenter__ = AsyncMock(return_value=session)
    session.__aexit__ = AsyncMock(return_value=None)

    async def _aiter():
        for row in rows:
            yield row

    result = MagicMock()
    result.__aiter__ = lambda _self: _aiter()
    session.run = AsyncMock(return_value=result)

    driver = MagicMock()
    driver.session = MagicMock(return_value=session)
    return driver


def _make_chunking_service(success: bool = True) -> MagicMock:
    """Mock chunking_service whose process_content_for_ingestion returns ok/fail."""
    svc = MagicMock()
    if success:
        content = MagicMock()
        content.chunks = [
            MagicMock(chunk_id="parent_1:chunk:0", context_window="ctx-a"),
            MagicMock(chunk_id="parent_1:chunk:1", context_window="ctx-b"),
        ]
        svc.process_content_for_ingestion = AsyncMock(
            return_value=Result.ok((content, MagicMock()))
        )
    else:
        svc.process_content_for_ingestion = AsyncMock(
            return_value=Result.fail(Errors.system("boom", operation="test"))
        )
    return svc


def _make_adapter(success: bool = True) -> MagicMock:
    """Mock content_adapter whose store_content_with_chunks returns success bool."""
    adapter = MagicMock()
    adapter.store_content_with_chunks = AsyncMock(return_value=success)
    return adapter


class TestRegenerationStats:
    def test_to_dict_rounds_duration(self) -> None:
        stats = RegenerationStats(processed=3, succeeded=2, failed=1, duration_seconds=1.23456)
        d = stats.to_dict()
        assert d["processed"] == 3
        assert d["succeeded"] == 2
        assert d["failed"] == 1
        assert d["duration_seconds"] == 1.23


class TestRegenerateChunks:
    @pytest.mark.anyio
    async def test_happy_path_all_succeed(self) -> None:
        rows = [
            {"uid": "ps:test:1", "body": "content one", "format": "markdown"},
            {"uid": "ps:test:2", "body": "content two", "format": "markdown"},
        ]
        service = BatchChunkingService(
            driver=_make_driver_returning(rows),
            chunking_service=_make_chunking_service(success=True),
            content_adapter=_make_adapter(success=True),
        )

        result = await service.regenerate_chunks()

        assert result.is_ok
        stats = result.value
        assert stats.total_candidates == 2
        assert stats.processed == 2
        assert stats.succeeded == 2
        assert stats.failed == 0
        assert stats.skipped_no_body == 0
        assert stats.errors == {}

    @pytest.mark.anyio
    async def test_skips_empty_body(self) -> None:
        rows = [
            {"uid": "ps:test:1", "body": "real content", "format": "markdown"},
            {"uid": "ps:test:2", "body": "   ", "format": "markdown"},  # whitespace only
        ]
        service = BatchChunkingService(
            driver=_make_driver_returning(rows),
            chunking_service=_make_chunking_service(success=True),
            content_adapter=_make_adapter(success=True),
        )

        result = await service.regenerate_chunks()

        assert result.is_ok
        stats = result.value
        assert stats.total_candidates == 2
        assert stats.processed == 1  # second one skipped before counting
        assert stats.succeeded == 1
        assert stats.skipped_no_body == 1

    @pytest.mark.anyio
    async def test_chunking_failure_recorded_per_uid_not_raised(self) -> None:
        rows = [{"uid": "ps:test:1", "body": "broken content", "format": "markdown"}]
        service = BatchChunkingService(
            driver=_make_driver_returning(rows),
            chunking_service=_make_chunking_service(success=False),
            content_adapter=_make_adapter(success=True),
        )

        result = await service.regenerate_chunks()

        assert result.is_ok  # batch itself doesn't fail
        stats = result.value
        assert stats.failed == 1
        assert "ps:test:1" in stats.errors
        assert "chunking failed" in stats.errors["ps:test:1"]

    @pytest.mark.anyio
    async def test_store_failure_recorded_per_uid(self) -> None:
        rows = [{"uid": "ps:test:1", "body": "content", "format": "markdown"}]
        service = BatchChunkingService(
            driver=_make_driver_returning(rows),
            chunking_service=_make_chunking_service(success=True),
            content_adapter=_make_adapter(success=False),  # store returns False
        )

        result = await service.regenerate_chunks()

        assert result.is_ok
        stats = result.value
        assert stats.failed == 1
        assert "store_content_with_chunks returned False" in stats.errors["ps:test:1"]

    @pytest.mark.anyio
    async def test_partial_failure_one_succeeds_one_fails(self) -> None:
        rows = [
            {"uid": "ps:test:1", "body": "good content", "format": "markdown"},
            {"uid": "ps:test:2", "body": "bad content", "format": "markdown"},
        ]
        # First call succeeds, second fails
        chunking_service = MagicMock()
        good_content = MagicMock(chunks=[])
        chunking_service.process_content_for_ingestion = AsyncMock(
            side_effect=[
                Result.ok((good_content, MagicMock())),
                Result.fail(Errors.system("nope", operation="test")),
            ]
        )

        service = BatchChunkingService(
            driver=_make_driver_returning(rows),
            chunking_service=chunking_service,
            content_adapter=_make_adapter(success=True),
        )

        result = await service.regenerate_chunks()

        assert result.is_ok
        stats = result.value
        assert stats.processed == 2
        assert stats.succeeded == 1
        assert stats.failed == 1
        assert len(stats.errors) == 1

    @pytest.mark.anyio
    async def test_publishes_embedding_event_when_event_bus_provided(self) -> None:
        rows = [{"uid": "ps:test:1", "body": "content", "format": "markdown"}]
        event_bus = MagicMock()
        event_bus.publish_async = AsyncMock()

        service = BatchChunkingService(
            driver=_make_driver_returning(rows),
            chunking_service=_make_chunking_service(success=True),
            content_adapter=_make_adapter(success=True),
            event_bus=event_bus,
        )

        result = await service.regenerate_chunks()
        assert result.is_ok
        # publish_event delegates to event_bus.publish_async()
        assert event_bus.publish_async.await_count >= 1

    @pytest.mark.anyio
    async def test_no_event_published_when_event_bus_none(self) -> None:
        rows = [{"uid": "ps:test:1", "body": "content", "format": "markdown"}]
        service = BatchChunkingService(
            driver=_make_driver_returning(rows),
            chunking_service=_make_chunking_service(success=True),
            content_adapter=_make_adapter(success=True),
            event_bus=None,
        )

        result = await service.regenerate_chunks()
        assert result.is_ok
        # No assertion on event_bus — it's None, can't be called.
