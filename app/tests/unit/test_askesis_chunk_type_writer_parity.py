"""The Askesis chunk filter must speak the vocabulary the chunk WRITER emits.

Regression guard for a live silent-zero bug (fixed 2026-07-27).
``_INTENT_CHUNK_TYPES`` held hand-written UPPERCASE names (``"DEFINITION"``)
while ``Neo4jContentAdapter`` persists ``chunk.chunk_type = chunk_type.value``
— lowercase ``"definition"``. The retrieval filter is a bare equality-set test
(``AND chunk.chunk_type IN $chunk_types``, vector_search_backend.py:151) and
Neo4j matches ZERO rows on a value no node carries instead of erroring. Five of
eight ``QueryIntent``s therefore retrieved no passages at all, silently; only
SPECIFIC and AGGREGATION — which pass ``None`` (no filter) — worked. This is the
SKUEL030 defect class one layer up: an unknown *name* is a silent zero, not a
crash.

The old test restated the map's uppercase literals against a mock, so it stayed
green the entire time the bug was live. This one restates NEITHER side: it
drives the REAL adapter to learn what ``chunk_type`` strings actually reach
Neo4j, then asserts every value ``_intent_to_chunk_types`` can emit is one of
them. See tests/integration/test_askesis_chunk_type_retrieval.py for the
end-to-end proof that rows come back.
"""

from __future__ import annotations

from typing import Any

import pytest

from adapters.persistence.neo4j.neo4j_content_adapter import Neo4jContentAdapter
from core.models.ps_content.content import CurriculumContent
from core.models.ps_content.content_chunks import ContentChunk, ContentChunkType
from core.models.query_types import QueryIntent
from core.services.askesis.context_retriever import _intent_to_chunk_types

_UID = "ps.test.chunk_type_parity"


class _CapturingConnection:
    """Minimal Neo4jConnection stand-in that records the CREATE chunk rows.

    Canned per-query responses mirror what the adapter needs to reach its
    create step: a truthy Content upsert, an empty embedding carry-over read,
    and a real ``created`` count.

    The ``dict[str, Any]`` rows and params are deliberate, not unexamined: they
    mirror the real ``execute_query`` signature this double substitutes for.
    Cypher parameters and Neo4j rows are genuinely heterogeneous here (str, int,
    None, ``list[float]`` embeddings), the chunk rows the adapter builds have no
    TypedDict anywhere in the tree, and ``Neo4jProperties`` (``dict[str,
    Neo4jValue]``) does not cover the nested row list. Narrowing a double below
    the interface it stands in for would make it a worse double.
    """

    def __init__(self, expected_created: int) -> None:
        self._expected_created = expected_created
        self.created_chunk_rows: list[dict[str, Any]] = []

    async def execute_query(
        self, query: str, params: dict[str, Any] | None = None
    ) -> list[dict[str, Any]]:
        params = params or {}
        if "CREATE (chunk:ContentChunk" in query:
            self.created_chunk_rows = list(params["chunks"])
            return [{"created": self._expected_created}]
        if "chunk.embedding IS NOT NULL" in query:
            return []
        return [{"uid": _UID}]


async def _chunk_type_values_the_adapter_writes() -> set[str]:
    """Persist one chunk per ContentChunkType and return the strings written."""
    chunks = tuple(
        ContentChunk(
            parent_uid=_UID,
            chunk_index=index,
            chunk_type=chunk_type,
            text=f"passage {index}",
            context_before="",
            context_after="",
        )
        for index, chunk_type in enumerate(ContentChunkType)
    )
    connection = _CapturingConnection(expected_created=len(chunks))
    adapter = Neo4jContentAdapter(connection)

    stored = await adapter.store_content_with_chunks(
        _UID,
        CurriculumContent(unit_uid=_UID, body="body text", chunks=chunks),
    )
    assert stored, "adapter probe failed — it measured nothing"

    return {row["chunk_type"] for row in connection.created_chunk_rows}


@pytest.mark.asyncio
async def test_adapter_probe_covers_every_chunk_type() -> None:
    """The probe itself is honest: it observes one written value per enum member.

    Without this, a probe that silently wrote nothing would make the parity
    assertion below vacuously true.
    """
    written = await _chunk_type_values_the_adapter_writes()

    assert written == {chunk_type.value for chunk_type in ContentChunkType}


@pytest.mark.asyncio
async def test_intent_filter_values_are_values_the_adapter_writes() -> None:
    """Every chunk type any intent can request is one Neo4j actually stores.

    FAILS on the pre-fix code: the map emitted ``{"DEFINITION", "EXPLANATION",
    "EXERCISE", "EXAMPLE", "INTRODUCTION", "SUMMARY"}``, disjoint from every
    value the writer emits, so the filter matched nothing.
    """
    written = await _chunk_type_values_the_adapter_writes()
    emitted = {value for intent in QueryIntent for value in (_intent_to_chunk_types(intent) or [])}

    assert emitted, "no intent requested any chunk type — the guard would be vacuous"
    assert emitted <= written, (
        f"intent filter asks for {sorted(emitted - written)}, which the chunk writer "
        f"never emits — Neo4j will match zero rows silently. Written: {sorted(written)}"
    )


def test_unfiltered_intents_still_opt_out() -> None:
    """The 'no filter' contract survives the enum migration.

    SPECIFIC/AGGREGATION/GOAL_ACHIEVEMENT must keep returning None (search all
    chunk types) rather than an empty list, which would filter everything out.
    """
    for intent_name in ("SPECIFIC", "AGGREGATION", "GOAL_ACHIEVEMENT"):
        assert _intent_to_chunk_types(QueryIntent[intent_name]) is None
