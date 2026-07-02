"""
Tests for the batch embedding script's candidate selection (--stale)
====================================================================

The Cypher predicate is the load-bearing piece: --stale must catch both
staleness signals (content edited after last embed, model-version drift)
and must coerce ``updated_at`` through ``datetime()`` — its storage type is
writer-decided (ISO strings AND native datetimes coexist in the live graph),
and a bare ``<`` across types is null in Cypher (silently skips nodes).
"""

import sys
from pathlib import Path
from typing import Any

import pytest

# scripts/ has no __init__.py — add it to sys.path for import
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "scripts"))

from generate_embeddings_batch import (  # type: ignore[import-not-found]
    build_candidate_query,
    generate_embeddings_batch,
    stamp_entity_hashes,
)

from core.services.embeddings_service import EMBEDDING_VERSION
from core.utils.result_simplified import Errors, Result


class TestBuildCandidateQuery:
    def test_default_selects_missing_embeddings_only(self) -> None:
        query = build_candidate_query("Ku", stale=False)
        assert "n.embedding IS NULL" in query
        assert "$current_version" not in query
        assert "MATCH (n:Ku)" in query

    def test_stale_requires_existing_embedding(self) -> None:
        query = build_candidate_query("Task", stale=True)
        assert "n.embedding IS NOT NULL" in query
        assert "n.embedding IS NULL" not in query

    def test_stale_catches_version_mismatch_and_null_version(self) -> None:
        query = build_candidate_query("Task", stale=True)
        assert "n.embedding_version <> $current_version" in query
        assert "n.embedding_version IS NULL" in query

    def test_stale_coerces_updated_at_through_datetime(self) -> None:
        # Writer-decided storage type: STRING updated_at vs DATETIME
        # embedding_updated_at must not silently compare to null.
        query = build_candidate_query("Task", stale=True)
        assert "n.embedding_updated_at < datetime(n.updated_at)" in query
        assert "n.updated_at IS NOT NULL" in query


class _FakeQueryResult:
    def __init__(self, records: list[dict[str, Any]]) -> None:
        self.records = records


class _FakeDriver:
    """Captures the query/params the script sends; returns canned records."""

    def __init__(self, records: list[dict[str, Any]]) -> None:
        self._records = records
        self.queries: list[tuple[str, dict[str, Any]]] = []

    async def execute_query(self, query: str, params: dict[str, Any] | None = None) -> Any:
        self.queries.append((query, params or {}))
        return _FakeQueryResult(self._records)


class _FakeEmbeddingsService:
    def __init__(self, fresh: set[str] | None = None) -> None:
        self.stored_uids: list[str] = []
        self.stored_texts: dict[str, str] = {}
        self.freshness_candidates: list[dict[str, str]] = []
        self.stamped: dict[str, dict[str, str]] = {}
        self._fresh = fresh if fresh is not None else set()
        self.fresh_result: Result[set[str]] | None = None

    async def create_batch_embeddings(self, texts: list[str]) -> Result[list[list[float]]]:
        return Result.ok([[0.1, 0.2] for _ in texts])

    async def store_embedding_with_metadata(
        self, uid: str, label: str, embedding: list[float], text: str
    ) -> Result[None]:
        self.stored_uids.append(uid)
        self.stored_texts[uid] = text
        return Result.ok(None)

    async def verify_fresh_embeddings(self, candidates: dict[str, str]) -> Result[set[str]]:
        self.freshness_candidates.append(candidates)
        if self.fresh_result is not None:
            return self.fresh_result
        return Result.ok(self._fresh & set(candidates))

    async def stamp_embedding_hashes(self, label: str, texts: dict[str, str]) -> Result[int]:
        self.stamped[label] = texts
        return Result.ok(len(texts))


@pytest.mark.asyncio
async def test_stale_mode_parameterizes_current_version() -> None:
    driver = _FakeDriver(
        records=[{"uid": "task_abc123", "props": {"title": "Stale task", "uid": "task_abc123"}}]
    )
    service = _FakeEmbeddingsService()

    stats = await generate_embeddings_batch(
        driver=driver, embeddings_service=service, label="Task", stale=True
    )

    query, params = driver.queries[0]
    assert params == {"current_version": EMBEDDING_VERSION}
    assert "n.embedding IS NOT NULL" in query
    assert stats["successful"] == 1
    assert service.stored_uids == ["task_abc123"]


@pytest.mark.asyncio
async def test_default_mode_sends_no_version_param() -> None:
    driver = _FakeDriver(records=[])
    service = _FakeEmbeddingsService()

    await generate_embeddings_batch(
        driver=driver, embeddings_service=service, label="Ku", stale=False
    )

    query, params = driver.queries[0]
    assert params == {}
    assert "n.embedding IS NULL" in query


@pytest.mark.asyncio
async def test_stale_mode_hash_fine_filter_skips_fresh_candidates() -> None:
    """The coarse Cypher predicate can't compute the current text hash — the
    Python fine filter drops candidates whose vector already matches, so a
    force campaign that bumped updated_at without changing content re-embeds
    nothing."""
    driver = _FakeDriver(
        records=[
            {"uid": "task_fresh", "props": {"title": "Unchanged", "uid": "task_fresh"}},
            {"uid": "task_stale", "props": {"title": "Edited", "uid": "task_stale"}},
        ]
    )
    service = _FakeEmbeddingsService(fresh={"task_fresh"})

    stats = await generate_embeddings_batch(
        driver=driver, embeddings_service=service, label="Task", stale=True
    )

    # Candidates handed to the one skip decision as uid → current text
    assert service.freshness_candidates == [{"task_fresh": "Unchanged", "task_stale": "Edited"}]
    assert service.stored_uids == ["task_stale"]
    assert stats["successful"] == 1


@pytest.mark.asyncio
async def test_stale_mode_fails_open_on_freshness_error() -> None:
    """A fine-filter failure re-embeds all candidates — correctness over savings."""
    driver = _FakeDriver(
        records=[{"uid": "task_abc", "props": {"title": "Task", "uid": "task_abc"}}]
    )
    service = _FakeEmbeddingsService()
    service.fresh_result = Result.fail(Errors.database(operation="freshness", message="boom"))

    stats = await generate_embeddings_batch(
        driver=driver, embeddings_service=service, label="Task", stale=True
    )

    assert service.stored_uids == ["task_abc"]
    assert stats["successful"] == 1


@pytest.mark.asyncio
async def test_default_mode_skips_fine_filter_but_stores_text() -> None:
    """Coverage backfill (embedding IS NULL) never needs the fine filter, but
    every store carries the text so the hash lands."""
    driver = _FakeDriver(records=[{"uid": "ku_new", "props": {"title": "New Ku", "uid": "ku_new"}}])
    service = _FakeEmbeddingsService()

    await generate_embeddings_batch(
        driver=driver, embeddings_service=service, label="Ku", stale=False
    )

    assert service.freshness_candidates == []
    assert service.stored_texts == {"ku_new": "New Ku"}


class TestStampEntityHashes:
    @pytest.mark.asyncio
    async def test_stamp_selects_only_provably_current_vectors(self) -> None:
        """Candidate query guards: embedded, version-current, unhashed, and no
        timestamp drift (updated_at coerced through datetime() — same
        writer-decided-type trap as the --stale predicate)."""
        driver = _FakeDriver(
            records=[{"uid": "task_a", "props": {"title": "A task", "uid": "task_a"}}]
        )
        service = _FakeEmbeddingsService()

        stats = await stamp_entity_hashes(driver, service, "Task")

        query, params = driver.queries[0]
        assert "n.embedding IS NOT NULL" in query
        assert "n.embedding_version = $current_version" in query
        assert "n.embedding_text_hash IS NULL" in query
        assert "n.embedding_updated_at < datetime(n.updated_at)" in query
        assert params == {"current_version": EMBEDDING_VERSION}
        # Texts built with the one recipe, handed to the service (which hashes)
        assert service.stamped == {"Task": {"task_a": "A task"}}
        assert stats == {"label": "Task", "total": 1, "stamped": 1}

    @pytest.mark.asyncio
    async def test_stamp_skips_textless_nodes(self) -> None:
        driver = _FakeDriver(records=[{"uid": "task_empty", "props": {"uid": "task_empty"}}])
        service = _FakeEmbeddingsService()

        stats = await stamp_entity_hashes(driver, service, "Task")

        assert service.stamped == {"Task": {}}
        assert stats["total"] == 0

    @pytest.mark.asyncio
    async def test_stamp_rejects_unsupported_label(self) -> None:
        driver = _FakeDriver(records=[])
        service = _FakeEmbeddingsService()

        stats = await stamp_entity_hashes(driver, service, "ContentChunk")

        assert stats == {"label": "ContentChunk", "total": 0, "stamped": 0}
        assert driver.queries == []
