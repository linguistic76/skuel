"""
Unit tests for Neo4jContentAdapter chunk persistence (delete-then-create).

A force re-ingest re-chunks every PathStep body, changed or not. Since Arc E
(force-reingest contract) persistence is **delete-then-create**:

- the ENTIRE outgoing chunk set is deleted (no MERGE-kept nodes — stale
  properties from earlier chunker/schema generations must not linger)
- fresh nodes are CREATEd; embedding fields are inherited via carry-over
  when an old chunk's embedding_source_text equals the new context_window
  (ADR-074 §8: unchanged text never re-embeds — idempotency by carry-over,
  not node reuse)
- changed text gets NULL embedding fields (stale vector must not survive)

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
from core.models.ps_content.content_chunks import ContentChunkType


class _FakeConnection:
    """Captures queries/params; returns canned rows.

    ``responses`` maps a query substring → rows for the first matching query;
    unmatched queries get ``default_rows``. Keeps the per-call shape honest:
    the create query must see a real ``created`` count, the carry-over read
    must see embedding rows only when a test stages them.
    """

    def __init__(
        self,
        default_rows: list[dict[str, Any]] | None = None,
        responses: dict[str, list[dict[str, Any]]] | None = None,
    ) -> None:
        self.default_rows = default_rows if default_rows is not None else [{"uid": "x"}]
        self.responses = responses or {}
        self.queries: list[tuple[str, dict[str, Any]]] = []
        self.raise_on_query = False

    async def execute_query(self, query: str, params: dict[str, Any] | None = None) -> Any:
        if self.raise_on_query:
            raise ServiceUnavailable("down")
        self.queries.append((query, params or {}))
        for marker, rows in self.responses.items():
            if marker in query:
                return rows
        return self.default_rows


@dataclass
class _FakeChunk:
    chunk_id: str
    text: str
    context_window: str
    chunk_type: ContentChunkType = ContentChunkType.SECTION
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


def _create_responses(created: int) -> dict[str, list[dict[str, Any]]]:
    """Canned rows: empty carry-over read + a real created count for CREATE."""
    return {
        "WHERE chunk.embedding IS NOT NULL": [],
        "CREATE (chunk:ContentChunk": [{"created": created}],
    }


@pytest.mark.asyncio
async def test_delete_and_create_are_one_atomic_statement():
    """Delete-then-create runs as ONE Cypher statement (single transaction):
    a failed create rolls the delete back, so a partial write can never leave
    the Content node chunkless (Kody #503 critical). The whole old chunk set
    goes (no keep_uids scoping) — stale properties can never survive."""
    conn = _FakeConnection(responses=_create_responses(2))
    adapter = Neo4jContentAdapter(conn)

    assert await adapter.store_content_with_chunks("ps:test:doc", _content(2))

    # [0] Content upsert, [1] carry-over read, [2] combined delete+create
    assert len(conn.queries) == 3
    carry_query, _ = conn.queries[1]
    assert "chunk.embedding IS NOT NULL" in carry_query
    assert "embedding_source_text" in carry_query
    replace_query, _ = conn.queries[2]
    assert "DETACH DELETE" in replace_query
    assert "CREATE (chunk:ContentChunk" in replace_query
    assert "keep_uids" not in replace_query


@pytest.mark.asyncio
async def test_default_store_clears_inline_body():
    """Popped-body domains (Ku/PS): the :Content subtree is THE body source
    of truth, so the upsert removes any legacy inline content property."""
    conn = _FakeConnection(responses=_create_responses(2))
    adapter = Neo4jContentAdapter(conn)

    assert await adapter.store_content_with_chunks("ps:test:doc", _content(2))

    upsert_query, _ = conn.queries[0]
    assert "REMOVE ku.content" in upsert_query


@pytest.mark.asyncio
async def test_clear_inline_body_false_preserves_entity_content():
    """UserEntry (canon P3): Entity.content stays load-bearing for /gradebook
    and the journal digest — the upsert must never strip it (Codex P1 #615)."""
    conn = _FakeConnection(responses=_create_responses(2))
    adapter = Neo4jContentAdapter(conn)

    assert await adapter.store_content_with_chunks(
        "ue_note_abc123", _content(2), clear_inline_body=False
    )

    upsert_query, _ = conn.queries[0]
    assert "REMOVE" not in upsert_query
    assert "ku.content" not in upsert_query


@pytest.mark.asyncio
async def test_zero_chunk_result_still_clears_stale_chunks():
    """An empty chunk list must still run the delete side of the combined
    statement (UNWIND [] yields no create rows; the DETACH DELETE precedes it)."""
    conn = _FakeConnection(responses=_create_responses(0))
    adapter = Neo4jContentAdapter(conn)

    assert await adapter.store_content_with_chunks("ps:test:doc", _content(0))

    replace_query, replace_params = conn.queries[2]
    assert "DETACH DELETE" in replace_query
    assert replace_params["chunks"] == []


@pytest.mark.asyncio
async def test_chunks_created_fresh_with_embedding_carry_over():
    """Fresh CREATE (never MERGE); an old chunk's embedding is inherited when
    its embedding_source_text matches the new context_window (ADR-074 §8 —
    unchanged text never re-embeds), NULL otherwise."""
    conn = _FakeConnection(
        responses={
            "WHERE chunk.embedding IS NOT NULL": [
                {
                    "source_text": "window 0",
                    "embedding": [0.1],
                    "version": "v3",
                    "model": "test-model",
                    "updated_at": "2026-07-01T00:00:00",
                }
            ],
            "CREATE (chunk:ContentChunk": [{"created": 2}],
        }
    )
    adapter = Neo4jContentAdapter(conn)

    assert await adapter.store_content_with_chunks("ps:test:doc", _content(2))

    create_query, create_params = conn.queries[2]
    assert "CREATE (chunk:ContentChunk" in create_query
    assert "MERGE (chunk:ContentChunk" not in create_query
    rows = create_params["chunks"]
    assert rows[0]["chunk_uid"] == "ps:test:doc:chunk:0"
    # window 0 matched the carry-over map → embedding inherited
    assert rows[0]["embedding"] == [0.1]
    assert rows[0]["embedding_source_text"] == "window 0"
    # window 1 had no prior embedding → NULL fields (worker will embed it)
    assert rows[1]["embedding"] is None
    assert rows[1]["embedding_source_text"] is None


@pytest.mark.asyncio
async def test_create_count_mismatch_fails():
    """A short CREATE count means chunks silently missing — hard False."""
    conn = _FakeConnection(
        responses={
            "WHERE chunk.embedding IS NOT NULL": [],
            "CREATE (chunk:ContentChunk": [{"created": 1}],
        }
    )
    adapter = Neo4jContentAdapter(conn)
    assert not await adapter.store_content_with_chunks("ps:test:doc", _content(2))


@pytest.mark.asyncio
async def test_content_upsert_writes_no_metadata_node():
    """The fabricated :ContentMetadata write is gone (L1 ruling 2026-07-02) —
    the upsert touches only :Content and its HAS_CONTENT link."""
    conn = _FakeConnection(responses=_create_responses(1))
    adapter = Neo4jContentAdapter(conn)

    assert await adapter.store_content_with_chunks("ps:test:doc", _content(1))

    upsert_query, upsert_params = conn.queries[0]
    assert "ContentMetadata" not in upsert_query
    assert "HAS_METADATA" not in upsert_query
    assert "complexity_score" not in upsert_params


@pytest.mark.asyncio
async def test_store_chunk_embeddings_stamps_event_text_provenance():
    """embedding_source_text comes from the texts the vectors were generated
    from (per-chunk param), NEVER the node-current context_window — a
    conflicting re-chunk between publish and store must not mislabel the
    vector (L3a ruling 2026-07-02)."""
    conn = _FakeConnection(default_rows=[{"updated_count": 2}])
    adapter = Neo4jContentAdapter(conn)

    assert await adapter.store_chunk_embeddings(
        chunk_uids=["c1", "c2"],
        embeddings=[[0.1], [0.2]],
        version="v3",
        model="test-model",
        texts=["window 1", "window 2"],
    )

    query, params = conn.queries[0]
    assert "c.embedding_source_text = chunk_data.source_text" in query
    assert "c.context_window" not in query
    assert params["chunks"] == [
        {"uid": "c1", "embedding": [0.1], "source_text": "window 1"},
        {"uid": "c2", "embedding": [0.2], "source_text": "window 2"},
    ]


@pytest.mark.asyncio
async def test_freshness_read_returns_rows():
    conn = _FakeConnection(
        default_rows=[
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
