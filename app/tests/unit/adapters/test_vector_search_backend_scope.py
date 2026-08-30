"""Unit tests for VectorSearchBackend.semantic_search_chunks facet scoping.

PR1 of the Search+Askesis merge: chunk retrieval honors the active facets
(nous/level/...) on the chunk's owning Entity, mirroring `_search_raw_mixin`'s
list-vs-scalar membership so `nous` (an array property) and scalar facets
behave identically across the frontmatter and body-chunk paths.

The vector index ranks by score, not facet, so a scoped query post-filters and
escalates its candidate pool until `limit` in-scope chunks survive. These tests
capture the emitted query/params through a fake executor and assert the
load-bearing scope clauses + escalation — no Neo4j required (in the style of
test_content_adapter_chunk_persistence.py).

Audience (ADR-085, 2026-08-30): EVERY chunk query carries the visibility clause —
a curriculum parent must be published, a user-owned parent must be the viewer's.
There is no unscoped variant any more; the "viewer-less" tests below pin that a
missing viewer yields the curriculum half alone (fail-closed), never everything.
"""

from typing import Any

import pytest

from adapters.persistence.neo4j.vector_search_backend import VectorSearchBackend
from core.models.enums.entity_enums import EntityType
from core.utils.result_simplified import Result

_CURRICULUM_HALF = "NOT parent.entity_type IN $user_owned_types"
_PUBLISHED = "parent.publication_state IS NULL OR parent.publication_state <> $publication_draft"
_OWNED_HALF = "parent.entity_type IN $user_owned_types AND (parent.user_uid = $user_uid)"
_PRIVATE_GATE = "coalesce(parent.private, false) = false"


class _FakeExecutor:
    """Captures (query, params) and returns a fixed count of stub rows.

    ``rows`` controls how many in-scope chunks each call yields — enough to
    satisfy ``limit`` (early exit) or too few (drives the escalation schedule).
    """

    def __init__(self, rows: int = 0) -> None:
        self.rows = rows
        self.queries: list[tuple[str, dict[str, Any]]] = []

    async def execute_query(
        self, query: str, params: dict[str, Any] | None = None
    ) -> Result[list[dict[str, Any]]]:
        self.queries.append((query, dict(params or {})))
        return Result.ok([{"chunk_uid": f"c{i}"} for i in range(self.rows)])


@pytest.mark.asyncio
async def test_viewerless_query_is_curriculum_only_and_published() -> None:
    # No viewer → the curriculum half alone: published Ku/PS bodies, no owner
    # predicate, no $user_uid. This is the shape /search's body-chunk fold
    # emits, and what any caller that forgets the viewer gets (fail-closed).
    executor = _FakeExecutor(rows=5)
    backend = VectorSearchBackend(executor)
    await backend.semantic_search_chunks(query_embedding=[0.1, 0.2], limit=5, threshold=0.6)

    assert len(executor.queries) == 1  # filled on the first tier
    cypher, params = executor.queries[-1]
    assert params["candidate_limit"] == 50  # 5 * 10 — every query is scoped now
    assert _CURRICULUM_HALF in cypher
    assert _PUBLISHED in cypher
    assert params["publication_draft"] == "draft"
    assert "$user_uid" not in cypher
    assert "user_uid" not in params
    assert "pf_" not in cypher
    assert "CASE WHEN parent." not in cypher


@pytest.mark.asyncio
async def test_viewer_scope_adds_the_owned_half() -> None:
    # A viewer widens the audience by exactly their own user-owned parents:
    # the OWNER_ONLY predicate every entity strategy composes, plus the
    # private gate. Curriculum stays in through the published half.
    executor = _FakeExecutor(rows=5)
    backend = VectorSearchBackend(executor)
    await backend.semantic_search_chunks(
        query_embedding=[0.1], limit=5, threshold=0.6, viewer_uid="user_1"
    )

    cypher, params = executor.queries[-1]
    assert params["user_uid"] == "user_1"
    assert _CURRICULUM_HALF in cypher
    assert _OWNED_HALF in cypher
    assert _PRIVATE_GATE in cypher
    assert f"({_CURRICULUM_HALF} AND ({_PUBLISHED})) OR ({_OWNED_HALF}" in cypher
    # Audience is not the vault scope: no OWNS edge, no parent_metadata.
    assert ":OWNS" not in cypher
    assert "parent_metadata" not in cypher


@pytest.mark.asyncio
async def test_user_owned_types_are_read_off_the_entity_type_authority() -> None:
    # The split between the two halves is derived from EntityType.is_user_owned(),
    # never a hand-kept list — so a newly chunked user-owned type is scoped by
    # construction and a curriculum type never needs registering.
    executor = _FakeExecutor(rows=5)
    backend = VectorSearchBackend(executor)
    await backend.semantic_search_chunks(query_embedding=[0.1], limit=5, threshold=0.6)

    _, params = executor.queries[-1]
    expected = sorted(t.value for t in EntityType if t.is_user_owned())
    assert params["user_owned_types"] == expected
    assert EntityType.USER_ENTRY.value in params["user_owned_types"]
    assert EntityType.KU.value not in params["user_owned_types"]
    assert EntityType.PATH_STEP.value not in params["user_owned_types"]


@pytest.mark.asyncio
async def test_visibility_composes_with_facet_and_vault_scopes_in_one_where() -> None:
    # Audience + facet + vault all land in the ONE parent WHERE, ANDed.
    executor = _FakeExecutor(rows=5)
    backend = VectorSearchBackend(executor)
    await backend.semantic_search_chunks(
        query_embedding=[0.1],
        limit=5,
        threshold=0.6,
        parent_filters={"nous": "body"},
        owner_uid="user_1",
        viewer_uid="user_1",
    )

    cypher, params = executor.queries[-1]
    scope_segment = cypher.split("MATCH (chunk)<-[:HAS_CHUNK]-(content:Content)")[-1]
    assert scope_segment.count("WHERE") == 1
    assert _OWNED_HALF in scope_segment
    assert "$owner_uid" in scope_segment
    assert "$pf_nous IN parent.nous" in scope_segment
    assert params["user_uid"] == "user_1"
    assert params["owner_uid"] == "user_1"


@pytest.mark.asyncio
async def test_nous_facet_scopes_parent_with_membership() -> None:
    # Facet well-populated (executor yields >= limit) → early exit on first pass.
    executor = _FakeExecutor(rows=5)
    backend = VectorSearchBackend(executor)
    await backend.semantic_search_chunks(
        query_embedding=[0.1], limit=5, threshold=0.6, parent_filters={"nous": "body"}
    )

    assert len(executor.queries) == 1  # filled on the first candidate tier
    cypher, params = executor.queries[-1]
    assert params["candidate_limit"] == 50  # 5 * 10 (first schedule tier)
    assert params["pf_nous"] == "body"
    # nous is an array property → element membership, same as _search_raw_mixin.
    assert "CASE WHEN parent.nous IS :: LIST<ANY>" in cypher
    assert "$pf_nous IN parent.nous" in cypher


@pytest.mark.asyncio
async def test_underfilled_scope_escalates_candidate_pool() -> None:
    # Narrow facet (executor yields nothing) → widen through the full schedule.
    executor = _FakeExecutor(rows=0)
    backend = VectorSearchBackend(executor)
    await backend.semantic_search_chunks(
        query_embedding=[0.1], limit=5, threshold=0.6, parent_filters={"nous": "obscure"}
    )

    # Schedule (10, 40, 160) x limit 5 -- exhausted because scope never fills.
    candidate_limits = [p["candidate_limit"] for _, p in executor.queries]
    assert candidate_limits == [50, 200, 800]


@pytest.mark.asyncio
async def test_list_valued_filter_uses_whole_value_equality() -> None:
    executor = _FakeExecutor(rows=5)
    backend = VectorSearchBackend(executor)
    await backend.semantic_search_chunks(
        query_embedding=[0.1], limit=3, threshold=0.6, parent_filters={"tags": ["a", "b"]}
    )

    cypher, params = executor.queries[-1]
    assert params["pf_tags"] == ["a", "b"]
    assert "parent.tags = $pf_tags" in cypher
    assert "CASE WHEN parent.tags" not in cypher


@pytest.mark.asyncio
async def test_viewerless_query_never_names_owner_or_vault_scope() -> None:
    # Without a viewer neither the owned half nor the canon-P3 vault branch
    # may appear: no OWNS clause, no private gate, no parent_metadata.
    executor = _FakeExecutor(rows=0)
    backend = VectorSearchBackend(executor)
    await backend.semantic_search_chunks(query_embedding=[0.1, 0.2], limit=5, threshold=0.6)

    cypher, params = executor.queries[-1]
    assert ":OWNS" not in cypher
    assert "private" not in cypher
    assert "parent_metadata" not in cypher
    assert "owner_uid" not in params


@pytest.mark.asyncio
async def test_owner_scope_adds_owns_and_private_clauses() -> None:
    # Canon P3 vault branch: OWNS edge on the parent + hard private exclusion,
    # scoped candidate schedule, parent_metadata in the RETURN.
    executor = _FakeExecutor(rows=5)
    backend = VectorSearchBackend(executor)
    await backend.semantic_search_chunks(
        query_embedding=[0.1], limit=5, threshold=0.6, owner_uid="user_1", viewer_uid="user_1"
    )

    assert len(executor.queries) == 1  # filled on the first scoped tier
    cypher, params = executor.queries[-1]
    assert params["owner_uid"] == "user_1"
    assert params["candidate_limit"] == 50  # 5 * 10 — the scoped schedule
    assert "EXISTS { MATCH (parent)<-[:OWNS]-(:User {uid: $owner_uid}) }" in cypher
    assert "coalesce(parent.private, false) = false" in cypher
    assert "parent.metadata as parent_metadata" in cypher


@pytest.mark.asyncio
async def test_owner_scope_composes_with_pipeline_filter() -> None:
    # retrieve_vault's exact call shape: owner + {"pipeline": "knowledge"} —
    # both clauses land in the ONE parent WHERE, joined by AND.
    executor = _FakeExecutor(rows=5)
    backend = VectorSearchBackend(executor)
    await backend.semantic_search_chunks(
        query_embedding=[0.1],
        limit=4,
        threshold=0.3,
        parent_filters={"pipeline": "knowledge"},
        owner_uid="user_1",
        viewer_uid="user_1",
    )

    cypher, params = executor.queries[-1]
    assert params["owner_uid"] == "user_1"
    assert params["pf_pipeline"] == "knowledge"
    scope_segment = cypher.split("MATCH (chunk)<-[:HAS_CHUNK]-(content:Content)")[-1]
    assert scope_segment.count("WHERE") == 1
    assert "$owner_uid" in scope_segment
    assert "coalesce(parent.private, false) = false" in scope_segment
    assert "parent.pipeline" in scope_segment


@pytest.mark.asyncio
async def test_underfilled_owner_scope_escalates_candidate_pool() -> None:
    # A sparse vault behaves like a narrow facet: widen through the schedule.
    executor = _FakeExecutor(rows=0)
    backend = VectorSearchBackend(executor)
    await backend.semantic_search_chunks(
        query_embedding=[0.1], limit=4, threshold=0.3, owner_uid="user_1"
    )

    candidate_limits = [p["candidate_limit"] for _, p in executor.queries]
    assert candidate_limits == [40, 160, 640]


@pytest.mark.asyncio
async def test_multiple_facets_are_anded() -> None:
    executor = _FakeExecutor(rows=5)
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
