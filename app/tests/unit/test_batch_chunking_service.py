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

from adapters.persistence.neo4j.batch_chunking_backend import BatchChunkingBackend
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
            backend=BatchChunkingBackend(_make_driver_returning(rows)),
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
            backend=BatchChunkingBackend(_make_driver_returning(rows)),
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
            backend=BatchChunkingBackend(_make_driver_returning(rows)),
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
            backend=BatchChunkingBackend(_make_driver_returning(rows)),
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
            backend=BatchChunkingBackend(_make_driver_returning(rows)),
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
            backend=BatchChunkingBackend(_make_driver_returning(rows)),
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
            backend=BatchChunkingBackend(_make_driver_returning(rows)),
            chunking_service=_make_chunking_service(success=True),
            content_adapter=_make_adapter(success=True),
            event_bus=None,
        )

        result = await service.regenerate_chunks()
        assert result.is_ok
        # No assertion on event_bus — it's None, can't be called.


class TestBatchDoorHonorsPerDomainParams:
    """The batch door must resolve per-domain chunking params from the parent
    label the candidate Cypher now returns — the same params the ingest door uses.
    """

    @pytest.mark.anyio
    async def test_absent_label_falls_back_to_default_params(self) -> None:
        # Legacy candidate with no entity_label (parentless :Content) → defaults.
        from core.models.ps_content.content_chunks import DEFAULT_CHUNKING_PARAMS

        rows = [{"uid": "ps:test:1", "body": "content", "format": "markdown"}]
        chunking_service = _make_chunking_service(success=True)
        service = BatchChunkingService(
            backend=BatchChunkingBackend(_make_driver_returning(rows)),
            chunking_service=chunking_service,
            content_adapter=_make_adapter(success=True),
        )

        result = await service.regenerate_chunks()
        assert result.is_ok
        _, kwargs = chunking_service.process_content_for_ingestion.call_args
        assert kwargs["params"] == DEFAULT_CHUNKING_PARAMS

    @pytest.mark.anyio
    async def test_labelled_candidate_resolves_that_domains_params(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Temporarily diverge Ku's config (NOT shipped) and assert the batch door
        # threads those params through to the chunker for a Ku-labelled candidate.
        from core.models.enums.entity_enums import EntityType
        from core.models.ps_content.content_chunks import ChunkingParams
        from core.services.ingestion import config as ingestion_config

        ku_params = ChunkingParams(max_chunk_size=250, context_size=40)
        monkeypatch.setattr(
            ingestion_config.ENTITY_CONFIGS[EntityType.KU],
            "chunking_params",
            ku_params,
        )

        rows = [
            {
                "uid": "ku:test:1",
                "body": "content",
                "format": "markdown",
                "entity_label": "Ku",
            }
        ]
        chunking_service = _make_chunking_service(success=True)
        service = BatchChunkingService(
            backend=BatchChunkingBackend(_make_driver_returning(rows)),
            chunking_service=chunking_service,
            content_adapter=_make_adapter(success=True),
        )

        result = await service.regenerate_chunks()
        assert result.is_ok
        _, kwargs = chunking_service.process_content_for_ingestion.call_args
        assert kwargs["params"] == ku_params


class TestBatchDoorInlineBodyOwnership:
    """The batch door must tell the adapter who owns the parent's inline body:
    popped-body domains (Ku/PS) may clear a legacy inline ``content`` property;
    everything else (UserEntry — canon P3 additive substrate) keeps it
    load-bearing, so a version-bump re-chunk sweep must never strip it
    (Codex P1 #615)."""

    @pytest.mark.anyio
    async def test_popped_body_label_clears_inline_body(self) -> None:
        rows = [{"uid": "ku:test:1", "body": "content", "format": "markdown", "entity_label": "Ku"}]
        adapter = _make_adapter(success=True)
        service = BatchChunkingService(
            backend=BatchChunkingBackend(_make_driver_returning(rows)),
            chunking_service=_make_chunking_service(success=True),
            content_adapter=adapter,
        )

        assert (await service.regenerate_chunks()).is_ok
        _, kwargs = adapter.store_content_with_chunks.call_args
        assert kwargs["clear_inline_body"] is True

    @pytest.mark.anyio
    async def test_user_entry_label_preserves_inline_body(self) -> None:
        rows = [
            {
                "uid": "ue_note_1",
                "body": "content",
                "format": "markdown",
                "entity_label": "UserEntry",
            }
        ]
        adapter = _make_adapter(success=True)
        service = BatchChunkingService(
            backend=BatchChunkingBackend(_make_driver_returning(rows)),
            chunking_service=_make_chunking_service(success=True),
            content_adapter=adapter,
        )

        assert (await service.regenerate_chunks()).is_ok
        _, kwargs = adapter.store_content_with_chunks.call_args
        assert kwargs["clear_inline_body"] is False

    @pytest.mark.anyio
    async def test_unknown_label_preserves_inline_body(self) -> None:
        # Parentless/legacy candidate — never destroy data we can't classify.
        rows = [{"uid": "x:1", "body": "content", "format": "markdown"}]
        adapter = _make_adapter(success=True)
        service = BatchChunkingService(
            backend=BatchChunkingBackend(_make_driver_returning(rows)),
            chunking_service=_make_chunking_service(success=True),
            content_adapter=adapter,
        )

        assert (await service.regenerate_chunks()).is_ok
        _, kwargs = adapter.store_content_with_chunks.call_args
        assert kwargs["clear_inline_body"] is False


class TestBatchDoorStalenessIsPerDomain:
    """Candidate *selection* (not just re-chunking) must compare each unit against
    its own domain's expected tag. Otherwise a diverged domain's default-tagged
    chunks never re-chunk, and its own-tagged chunks re-chunk on every run.
    """

    def test_diverged_map_empty_when_all_domains_default(self) -> None:
        # Shipped state: nothing diverges → empty map → backend falls back to the
        # bare version for every unit → zero churn.
        from core.services.ingestion.config import diverged_chunk_version_by_label

        assert diverged_chunk_version_by_label() == {}

    def test_diverged_map_uses_the_same_tag_the_ingest_door_stamps(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from core.models.enums.entity_enums import EntityType
        from core.models.ps_content.content_chunks import ChunkingParams, chunk_version_tag
        from core.services.ingestion import config as ingestion_config
        from core.services.ingestion.config import diverged_chunk_version_by_label

        ku_params = ChunkingParams(max_chunk_size=250, context_size=40)
        monkeypatch.setattr(
            ingestion_config.ENTITY_CONFIGS[EntityType.KU], "chunking_params", ku_params
        )

        mapping = diverged_chunk_version_by_label()
        assert mapping == {"Ku": chunk_version_tag(ku_params)}
        assert mapping["Ku"] == "v1:250-40"  # suffixed, not the bare "v1"

    @pytest.mark.anyio
    async def test_service_threads_expected_map_into_candidate_query(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from core.models.enums.entity_enums import EntityType
        from core.models.ps_content.content_chunks import ChunkingParams, chunk_version_tag
        from core.services.ingestion import config as ingestion_config

        ku_params = ChunkingParams(max_chunk_size=250, context_size=40)
        monkeypatch.setattr(
            ingestion_config.ENTITY_CONFIGS[EntityType.KU], "chunking_params", ku_params
        )

        backend = MagicMock()
        backend.fetch_regeneration_candidates = AsyncMock(return_value=[])
        service = BatchChunkingService(
            backend=backend,
            chunking_service=_make_chunking_service(success=True),
            content_adapter=_make_adapter(success=True),
        )

        await service.regenerate_chunks()

        args, _ = backend.fetch_regeneration_candidates.call_args
        # (parent_uids, force, current_version, expected_by_label)
        assert args[3] == {"Ku": chunk_version_tag(ku_params)}
