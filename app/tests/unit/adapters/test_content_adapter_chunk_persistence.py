"""
Unit tests for Neo4jContentAdapter chunk persistence idempotency.

A force re-ingest re-chunks every PathStep body, changed or not. Chunk uids
are deterministic (parent_uid + index), so persistence must:

- delete ONLY chunks absent from the new set (never blanket-delete)
- MERGE surviving uids, preserving embedding fields when the stored
  embedding_source_text still equals the incoming context_window
- wipe embedding fields when the text changed (stale vector must not survive)

Also covers get_chunk_embedding_freshness — the worker's pre-generation
chunk read (fails OPEN by returning [] on a Neo4j error).

The adapter is Cypher-heavy; these tests capture the queries sent through a
fake connection and assert their load-bearing clauses, in the style of
test_generate_embeddings_batch.py's predicate tests.
"""

from dataclasses import dataclass, field
from typing import Any

import pytest
from neo4j.exceptions import ServiceUnavailable

from adapters.persistence.neo4j.neo4j_content_adapter import Neo4jContentAdapter


class _FakeConnection:
    """Captures queries/params; returns canned rows."""

    def __init__(self, rows: list[dict[str, Any]] | None = None) -> None:
        self.rows = rows if rows is not None else [{"uid": "x"}]
        self.queries: list[tuple[str, dict[str, Any]]] = []
        self.raise_on_query = False

    async def execute_query(self, query: str, params: dict[str, Any] | None = None) -> Any:
        if self.raise_on_query:
            raise ServiceUnavailable("down")
        self.queries.append((query, params or {}))
        return self.rows


@dataclass
class _FakeChunk:
    chunk_id: str
    text: str
    context_window: str
    chunk_type: str = "CONTENT"
    chunk_index: int = 0
    word_count: int = 2
    chunking_version: str = "v1"


@dataclass
class _FakeContent:
    body: str = "body"
    format: str = "markdown"
    word_count: int = 10
    chunk_count: int = 2
    chunks: list[_FakeChunk] = field(default_factory=list)


def _content(n: int = 2) -> _FakeContent:
    return _FakeContent(
        chunks=[
            _FakeChunk(
                chunk_id=f"ps:test:doc:chunk:{i}",
                text=f"chunk {i}",
                context_window=f"window {i}",
                chunk_index=i,
            )
            for i in range(n)
        ]
    )


@pytest.mark.asyncio
async def test_delete_is_scoped_to_vanished_chunks():
    """The pre-delete keeps the new chunk set's uids — a re-chunk of identical
    content must not destroy embedded chunk nodes."""
    conn = _FakeConnection()
    adapter = Neo4jContentAdapter(conn)

    assert await adapter.store_content_with_chunks("ps:test:doc", _content(2))

    delete_query, delete_params = conn.queries[1]  # [0] is the Content upsert
    assert "DETACH DELETE" in delete_query
    assert "WHERE NOT chunk.uid IN $keep_uids" in delete_query
    assert delete_params["keep_uids"] == ["ps:test:doc:chunk:0", "ps:test:doc:chunk:1"]


@pytest.mark.asyncio
async def test_chunk_upsert_merges_and_preserves_unchanged_embeddings():
    """MERGE (not CREATE) on the deterministic uid; embedding fields are wiped
    only when embedding_source_text no longer matches the incoming window."""
    conn = _FakeConnection()
    adapter = Neo4jContentAdapter(conn)

    assert await adapter.store_content_with_chunks("ps:test:doc", _content(1))

    chunk_query, chunk_params = conn.queries[2]
    assert "MERGE (chunk:ContentChunk {uid: $chunk_uid})" in chunk_query
    assert "CREATE (chunk:ContentChunk" not in chunk_query
    # Conditional wipe: source-text mismatch (or never embedded) → null out
    assert "chunk.embedding_source_text <> $context_window" in chunk_query
    assert "chunk.embedding_source_text IS NULL" in chunk_query
    assert chunk_params["chunk_uid"] == "ps:test:doc:chunk:0"
    assert chunk_params["context_window"] == "window 0"


@pytest.mark.asyncio
async def test_freshness_read_returns_rows():
    conn = _FakeConnection(
        rows=[
            {
                "uid": "c1",
                "has_embedding": True,
                "version": "v3",
                "source_text": "window",
            }
        ]
    )
    adapter = Neo4jContentAdapter(conn)

    rows = await adapter.get_chunk_embedding_freshness(["c1"])

    assert rows == [{"uid": "c1", "has_embedding": True, "version": "v3", "source_text": "window"}]
    query, params = conn.queries[0]
    assert "c.embedding IS NOT NULL as has_embedding" in query
    assert params == {"uids": ["c1"]}


@pytest.mark.asyncio
async def test_freshness_read_fails_open_on_neo4j_error():
    """A read failure returns [] — the worker then skips nothing."""
    conn = _FakeConnection()
    conn.raise_on_query = True
    adapter = Neo4jContentAdapter(conn)

    assert await adapter.get_chunk_embedding_freshness(["c1"]) == []
