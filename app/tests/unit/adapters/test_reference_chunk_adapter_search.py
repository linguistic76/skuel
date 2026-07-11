"""Query-shape tests for ``Neo4jReferenceChunkAdapter.search_reference_chunks``.

The two-branch contract (ADR-077, PS-scoped canon retrieval):

- ``resource_uids=None`` → whole-shelf index search (``db.index.vector.queryNodes``
  against ``referencechunk_embedding_idx`` with the 2x candidate over-fetch).
- ``resource_uids=[…]`` → exact ``vector.similarity.cosine`` scan over only the
  in-scope chunks (no index, no ``candidate_limit``).
- ``resource_uids=[]`` → empty scope: ``[]`` with NO query at all (empty scope
  is distinct from "whole shelf").

DB-free: a fake connection records the Cypher + params each call emits.
"""

from typing import Any

import pytest

from adapters.persistence.neo4j.neo4j_reference_chunk_adapter import (
    Neo4jReferenceChunkAdapter,
)


class FakeConnection:
    """Records execute_query calls and returns canned rows."""

    def __init__(self, rows: list[dict[str, Any]] | None = None) -> None:
        self.rows = rows or []
        self.calls: list[tuple[str, dict[str, Any]]] = []

    async def execute_query(self, query: str, params: dict[str, Any]) -> list[dict[str, Any]]:
        self.calls.append((query, params))
        return self.rows


def _row(chunk_uid: str = "rc_1", resource_uid: str = "resource.hms") -> dict[str, Any]:
    return {
        "chunk_uid": chunk_uid,
        "text": "HTML is a hypermedia.",
        "context_window": None,
        "heading": "A Reintroduction",
        "section_path": "Hypermedia Concepts",
        "sequence": 3,
        "similarity_score": 0.87,
        "resource_uid": resource_uid,
        "book_title": "Hypermedia Systems",
    }


class TestUnscopedBranch:
    @pytest.mark.asyncio
    async def test_none_scope_uses_the_vector_index(self):
        conn = FakeConnection(rows=[_row()])
        adapter = Neo4jReferenceChunkAdapter(conn)

        hits = await adapter.search_reference_chunks([0.1, 0.2], limit=5, threshold=0.5)

        assert len(conn.calls) == 1
        query, params = conn.calls[0]
        assert "db.index.vector.queryNodes" in query
        assert "referencechunk_embedding_idx" in query
        assert "vector.similarity.cosine" not in query
        # The 2x over-fetch survives the threshold cut in the common case.
        assert params["candidate_limit"] == 10
        assert "resource_uids" not in params
        assert len(hits) == 1

    @pytest.mark.asyncio
    async def test_rows_map_to_hits(self):
        conn = FakeConnection(rows=[_row()])
        adapter = Neo4jReferenceChunkAdapter(conn)

        hits = await adapter.search_reference_chunks([0.1], limit=5, threshold=0.5)

        hit = hits[0]
        assert hit["chunk_uid"] == "rc_1"
        assert hit["book_title"] == "Hypermedia Systems"
        assert hit["heading"] == "A Reintroduction"
        assert hit["section_path"] == "Hypermedia Concepts"
        assert hit["sequence"] == 3
        assert hit["similarity_score"] == pytest.approx(0.87)


class TestScopedBranch:
    @pytest.mark.asyncio
    async def test_scoped_uses_exact_cosine_scan_not_the_index(self):
        conn = FakeConnection(rows=[_row()])
        adapter = Neo4jReferenceChunkAdapter(conn)

        hits = await adapter.search_reference_chunks(
            [0.1, 0.2], limit=5, threshold=0.5, resource_uids=["resource.hms"]
        )

        assert len(conn.calls) == 1
        query, params = conn.calls[0]
        assert "vector.similarity.cosine" in query
        assert "r.uid IN $resource_uids" in query
        assert "db.index.vector.queryNodes" not in query
        assert params["resource_uids"] == ["resource.hms"]
        # A full scan of the scoped set needs no over-fetch.
        assert "candidate_limit" not in params
        assert len(hits) == 1

    @pytest.mark.asyncio
    async def test_scoped_maps_rows_identically_to_unscoped(self):
        conn = FakeConnection(rows=[_row()])
        adapter = Neo4jReferenceChunkAdapter(conn)

        unscoped = await adapter.search_reference_chunks([0.1], limit=5, threshold=0.5)
        scoped = await adapter.search_reference_chunks(
            [0.1], limit=5, threshold=0.5, resource_uids=["resource.hms"]
        )

        assert scoped == unscoped

    @pytest.mark.asyncio
    async def test_empty_scope_short_circuits_without_a_query(self):
        conn = FakeConnection(rows=[_row()])
        adapter = Neo4jReferenceChunkAdapter(conn)

        hits = await adapter.search_reference_chunks(
            [0.1], limit=5, threshold=0.5, resource_uids=[]
        )

        assert hits == []
        assert conn.calls == []


class TestFailOpen:
    @pytest.mark.asyncio
    async def test_scoped_read_error_returns_empty(self):
        from neo4j.exceptions import ServiceUnavailable

        class BrokenConnection:
            async def execute_query(self, query: str, params: dict[str, Any]) -> None:
                raise ServiceUnavailable("down")

        adapter = Neo4jReferenceChunkAdapter(BrokenConnection())
        hits = await adapter.search_reference_chunks(
            [0.1], limit=5, threshold=0.5, resource_uids=["resource.hms"]
        )
        assert hits == []
