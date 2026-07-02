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
)

from core.services.embeddings_service import EMBEDDING_VERSION
from core.utils.result_simplified import Result


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
    def __init__(self) -> None:
        self.stored_uids: list[str] = []

    async def create_batch_embeddings(self, texts: list[str]) -> Result[list[list[float]]]:
        return Result.ok([[0.1, 0.2] for _ in texts])

    async def store_embedding_with_metadata(
        self, uid: str, label: str, embedding: list[float]
    ) -> Result[None]:
        self.stored_uids.append(uid)
        return Result.ok(None)


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
