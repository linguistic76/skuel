"""Unit guards for the shared graph-context producer `build_domain_context_with_paths`.

Pure-function (no Neo4j) assertions on the generated Cypher for the contract the
direction-aware-bucketing fold depends on — most importantly that the pre-aggregation
``LIMIT`` is emitted ONLY when a ``limit`` is passed. The backend applies that limit only
on the registry-sourced path (``cross_domain_backend.query_with_intent``); the explicit-
intent / generic paths pass ``limit=None`` and must stay UNBOUNDED, matching the retired
builder (a regression Codex caught on PR #243: an unconditional cap silently dropped nodes
for ``get_completion_impact`` / Tasks dependency traversals on dense graphs).
"""

from __future__ import annotations

from adapters.persistence.neo4j.query import build_domain_context_with_paths
from core.models.enums.neo_labels import NeoLabel


def test_limit_omitted_when_none() -> None:
    """No ``limit`` → no ``LIMIT`` clause and no ``limit`` param (explicit-intent/generic path)."""
    query, params = build_domain_context_with_paths("uid", relationship_types=["DEPENDS_ON"])
    assert "LIMIT" not in query
    assert "limit" not in params


def test_limit_emitted_when_supplied() -> None:
    """A ``limit`` → a real pre-aggregation ``LIMIT $limit`` (registry-sourced path)."""
    query, params = build_domain_context_with_paths(
        "uid", relationship_types=["DEPENDS_ON"], limit=100
    )
    assert "LIMIT $limit" in query
    assert params["limit"] == 100


def test_empty_relationship_types_traverses_all_edges() -> None:
    """Empty/None edge set → untyped variable-length pattern (the generic 'every edge' lens)."""
    query, _ = build_domain_context_with_paths("uid", relationship_types=[], depth=2)
    assert "[r*1..2]" in query
    assert "[r:" not in query  # no type filter


def test_supplied_relationship_types_build_typed_pattern() -> None:
    query, _ = build_domain_context_with_paths(
        "uid", relationship_types=["DEPENDS_ON", "FULFILLS_GOAL"], depth=2
    )
    assert "[r:DEPENDS_ON|FULFILLS_GOAL*1..2]" in query


def test_label_less_match_when_no_label() -> None:
    """``node_label=None`` matches on uid alone — the intent path has only the domain."""
    query, _ = build_domain_context_with_paths("uid", node_label=None)
    assert "MATCH (center {uid: $uid})" in query


def test_label_match_when_label_given() -> None:
    query, _ = build_domain_context_with_paths("uid", node_label=NeoLabel.TASK)
    assert f"MATCH (center:{NeoLabel.TASK}" in query


def test_carries_full_node_properties() -> None:
    """Producer emits the related node's full property map (the get_entity_context contract)."""
    query, _ = build_domain_context_with_paths("uid", relationship_types=["DEPENDS_ON"])
    assert "properties: properties(related)" in query


def test_keeps_center_row_for_edge_less_node() -> None:
    """The null-tolerant predicate keeps the center row so an edge-less node → empty, not 0 rows.

    (0 rows ⟺ absent node → NOT_FOUND; present-but-unconnected must still return a record.)
    """
    query, _ = build_domain_context_with_paths("uid", relationship_types=["DEPENDS_ON"])
    assert "related IS NULL OR" in query
    assert "[x in ctx WHERE x IS NOT NULL]" in query
