"""Unit tests for VectorSearchBackend.semantic_search_chunks facet scoping.

PR1 of the Search+Askesis merge: chunk retrieval honors the active facets
(nous/level/...) on the chunk's owning Entity, mirroring `_search_raw_mixin`'s
list-vs-scalar membership so `nous` (an array property) and scalar facets
behave identically across the frontmatter and body-chunk paths.

The backend is Cypher-heavy; these tests capture the emitted query/params
through a fake executor and assert the load-bearing scope clauses — no Neo4j
required (in the style of test_content_adapter_chunk_persistence.py).
"""

from typing import Any

import pytest

from adapters.persistence.neo4j.vector_search_backend import VectorSearchBackend
from core.utils.result_simplified import Result


class _FakeExecutor:
    """Captures (query, params) and returns an empty Result — the backend only
    threads scope into the query, so canned-empty rows are enough."""

    def __init__(self) -> None:
        self.queries: list[tuple[str, dict[str, Any]]] = []

    async def execute_query(
        self, query: str, params: dict[str, Any] | None = None
    ) -> Result[list[dict[str, Any]]]:
        self.queries.append((query, params or {}))
        return Result.ok([])


@pytest.fixture
def executor() -> _FakeExecutor:
    return _FakeExecutor()


@pytest.mark.asyncio
async def test_no_parent_filters_leaves_query_unscoped(executor: _FakeExecutor) -> None:
    # The pre-facet behavior must be preserved byte-for-byte: 2x candidate
    # over-fetch, no parent WHERE, no pf_ params. (Empty facets → this path.)
    backend = VectorSearchBackend(executor)
    await backend.semantic_search_chunks(query_embedding=[0.1, 0.2], limit=5, threshold=0.6)

    cypher, params = executor.queries[-1]
    assert params["candidate_limit"] == 10  # 5 * 2
    assert "pf_" not in cypher
    assert "CASE WHEN parent." not in cypher


@pytest.mark.asyncio
async def test_nous_facet_scopes_parent_with_membership(executor: _FakeExecutor) -> None:
    backend = VectorSearchBackend(executor)
    await backend.semantic_search_chunks(
        query_embedding=[0.1], limit=5, threshold=0.6, parent_filters={"nous": "body"}
    )

    cypher, params = executor.queries[-1]
    # Candidate pool widened when scoping (score-then-filter needs headroom).
    assert params["candidate_limit"] == 50  # 5 * 10
    assert params["pf_nous"] == "body"
    # nous is an array property → element membership, same as _search_raw_mixin.
    assert "CASE WHEN parent.nous IS :: LIST<ANY>" in cypher
    assert "$pf_nous IN parent.nous" in cypher


@pytest.mark.asyncio
async def test_list_valued_filter_uses_whole_value_equality(executor: _FakeExecutor) -> None:
    # A list-valued facet matches whole-value equality (mirrors _search_raw_mixin).
    backend = VectorSearchBackend(executor)
    await backend.semantic_search_chunks(
        query_embedding=[0.1], limit=3, threshold=0.6, parent_filters={"tags": ["a", "b"]}
    )

    cypher, params = executor.queries[-1]
    assert params["pf_tags"] == ["a", "b"]
    assert "parent.tags = $pf_tags" in cypher
    assert "CASE WHEN parent.tags" not in cypher


@pytest.mark.asyncio
async def test_multiple_facets_are_anded(executor: _FakeExecutor) -> None:
    backend = VectorSearchBackend(executor)
    await backend.semantic_search_chunks(
        query_embedding=[0.1],
        limit=5,
        threshold=0.6,
        parent_filters={"nous": "body", "learning_level": "beginner"},
    )

    cypher, params = executor.queries[-1]
    assert params["pf_nous"] == "body"
    assert params["pf_learning_level"] == "beginner"
    # Both facets land in the parent-scope WHERE, joined by AND.
    scope_segment = cypher.split("MATCH (chunk)<-[:HAS_CHUNK]-(content:Content)")[-1]
    assert "$pf_nous IN parent.nous" in scope_segment
    assert "parent.learning_level" in scope_segment
    assert " AND " in scope_segment
