"""
Guard: hierarchy reads name the edges the hierarchy writer actually creates.
===========================================================================

SKUEL030 findings §5/§8 (tranche 4). Three sites read the parent→child
hierarchy, and all three named vocabulary nothing writes:

- ``LateralRelationshipBackend.get_siblings`` filtered on ``['SUBGOAL', 'SUBHABIT', …]`` —
  bare forms that are not ``RelationshipName`` members at all.
- ``build_graph_context_query(HIERARCHICAL)`` and
  ``_INTENT_EDGE_SETS["hierarchical"]`` used ``HAS_CHILD|PARENT_OF|CHILD_OF``.
  ``PARENT_OF``/``CHILD_OF`` are not members either, and ``HAS_CHILD`` — though
  registered, and declared Task→Task in ``TASKS_CONFIG`` — has no writer
  anywhere in the repo.

The single live writer is ``_HierarchyMixin.create_hierarchy_relationship``,
driven by the six ``HierarchyConfig`` declarations on the Activity backends. It
writes ``HAS_SUB*`` forward (parent→child) and ``SUB*_OF`` inverse
(child→parent).

Direction is the trap this guard exists for: the findings doc proposed
repointing ``get_siblings`` onto ``SUBGOAL_OF``/``SUBHABIT_OF``/…, but those
point child→parent, the wrong way for a ``(parent)-[r]->(sibling)`` traversal.
Swapping them in would have replaced one silent zero with another.
"""

from __future__ import annotations

import re

from adapters.persistence.neo4j.backends import activity_backends, collab_backends
from adapters.persistence.neo4j.cross_domain_backend import _INTENT_EDGE_SETS
from adapters.persistence.neo4j.query import graph_traversal
from core.models.relationship_names import RelationshipName

# The forward (parent→child) hierarchy vocabulary a "same parent" read must use.
FORWARD_HIERARCHY = {
    "HAS_SUBTASK",
    "HAS_SUBGOAL",
    "HAS_SUBHABIT",
    "HAS_SUBEVENT",
    "HAS_SUBCHOICE",
    "HAS_SUBPRINCIPLE",
    "HAS_STEP",
    "ORGANIZES",
}

# The names these sites used to carry, none of which any writer creates.
DEAD_HIERARCHY_NAMES = {
    "SUBGOAL",
    "SUBHABIT",
    "SUBEVENT",
    "SUBPRINCIPLE",
    "SUBCHOICE",
    "PARENT_OF",
    "CHILD_OF",
    "HAS_CHILD",
}


def _source(obj: object) -> str:
    import inspect

    return inspect.getsource(obj)  # type: ignore[arg-type]


def test_forward_hierarchy_names_are_registered() -> None:
    """Every name the hierarchy reads use is a RelationshipName member."""
    members = {r.value for r in RelationshipName}
    assert members >= FORWARD_HIERARCHY


def test_forward_hierarchy_covers_every_hierarchy_config() -> None:
    """No Activity domain's forward edge is missing from the read vocabulary.

    A new sub-entity domain that adds a ``HierarchyConfig`` without adding its
    forward edge here would be invisible to every hierarchy read.
    """
    configs = [
        config
        for cls in vars(activity_backends).values()
        if isinstance(cls, type) and (config := getattr(cls, "_hierarchy_config", None)) is not None
    ]
    configured = {config.forward_rel for config in configs}
    assert configured, "no HierarchyConfig found — did the backends move?"
    assert configured <= FORWARD_HIERARCHY


def test_get_siblings_uses_forward_edges_only() -> None:
    """get_siblings filters on the forward edges, never the SUB*_OF inverses."""
    source = _source(collab_backends.LateralRelationshipBackend.get_siblings)
    quoted = set(re.findall(r"'([A-Z_]+)'", source))

    assert quoted == FORWARD_HIERARCHY
    # The inverse legs point child→parent — wrong direction for this traversal.
    assert not any(name.endswith("_OF") for name in quoted)


def test_get_siblings_constrains_the_anchor_edge_too() -> None:
    """The parent anchor is typed, so an unrelated edge can't fake a parent."""
    source = _source(collab_backends.LateralRelationshipBackend.get_siblings)
    assert "type(anchor) IN" in source
    assert "-[]->" not in source


def test_get_cousins_agrees_with_get_siblings() -> None:
    """The "not a sibling" exclusion is only correct if both agree on parenthood."""
    source = _source(collab_backends.LateralRelationshipBackend.get_cousins)
    assert set(re.findall(r"'([A-Z_]+)'", source)) == FORWARD_HIERARCHY
    assert "-[]->" not in source


def test_hierarchical_intent_edge_set_is_live_vocabulary() -> None:
    """The Python-side intent lens uses the same live forward edges.

    This list is a Python literal, so SKUEL030 cannot see it — it carried no
    baseline pair and drifted unnoticed (findings §13).
    """
    assert set(_INTENT_EDGE_SETS["hierarchical"]) == FORWARD_HIERARCHY


def test_hierarchical_graph_context_query_is_live_vocabulary() -> None:
    """The HIERARCHICAL traversal names only live forward edges."""
    from core.models.query_types import QueryIntent

    query = graph_traversal.build_graph_context_query("uid", QueryIntent.HIERARCHICAL, 3)
    named = set(re.findall(r"[A-Z][A-Z_]{3,}", query))

    assert named >= FORWARD_HIERARCHY
    assert not (named & DEAD_HIERARCHY_NAMES)


def test_no_dead_hierarchy_name_survives_in_any_site() -> None:
    """None of the retired names reappears in the three repointed sites."""
    from core.models.query_types import QueryIntent

    blobs = [
        _source(collab_backends.LateralRelationshipBackend.get_siblings),
        _source(collab_backends.LateralRelationshipBackend.get_cousins),
        graph_traversal.build_graph_context_query("uid", QueryIntent.HIERARCHICAL, 3),
        " ".join(_INTENT_EDGE_SETS["hierarchical"]),
    ]
    for blob in blobs:
        # Word-boundary match so HAS_SUBTASK doesn't trip the "SUBTASK" check.
        found = {n for n in DEAD_HIERARCHY_NAMES if re.search(rf"\b{n}\b", blob)}
        # Explanatory comments may name them in prose; only Cypher/list use counts.
        cypher_only = "\n".join(
            line for line in blob.splitlines() if not line.strip().startswith("#")
        )
        found = {n for n in found if re.search(rf"\b{n}\b", cypher_only)}
        assert not found, f"dead hierarchy vocabulary still live: {found}"


# ============================================================================
# build_hierarchy_query — tranche 5
#
# Found by the new Python-edge-list scanner, which is the point: the default
# was a Python list literal, so no Cypher-reading rule could ever see it.
# ============================================================================


def test_build_hierarchy_query_default_is_live_vocabulary() -> None:
    """The default edge list is the live forward hierarchy, not CONTAINS.

    Was ``["CONTAINS", "AGGREGATES", "HAS_STEP"]``: neither CONTAINS nor
    AGGREGATES is a RelationshipName member or exists in the graph, so this
    read had only ever matched HAS_STEP.
    """
    from adapters.persistence.neo4j.query.cypher.crud_queries import (
        _HIERARCHY_FORWARD_EDGES,
    )

    assert set(_HIERARCHY_FORWARD_EDGES) == FORWARD_HIERARCHY


def test_build_hierarchy_query_default_is_forward_only() -> None:
    """No inverse legs: the query walks both directions explicitly.

    ``build_hierarchy_query`` emits ``(parent)-[:R]->(n)`` AND
    ``(n)-[:R]->(child)``. Adding the ``SUB*_OF`` inverses would make every
    child match as its own parent — the direction trap from findings § 5.
    """
    from adapters.persistence.neo4j.query.cypher.crud_queries import (
        _HIERARCHY_FORWARD_EDGES,
    )

    assert not any(name.endswith("_OF") for name in _HIERARCHY_FORWARD_EDGES)


def test_build_hierarchy_query_emits_no_dead_vocabulary() -> None:
    """The rendered query carries neither retired name."""
    from adapters.persistence.neo4j.query.cypher.crud_queries import build_hierarchy_query
    from core.models.enums.neo_labels import NeoLabel

    query, _ = build_hierarchy_query(label=NeoLabel.TASK, uid="task_x")

    assert "CONTAINS" not in query
    assert "AGGREGATES" not in query
    for name in FORWARD_HIERARCHY:
        assert name in query, f"{name} missing from the hierarchy traversal"
