"""Pin the vector-index label set to its two importers.

Which labels carry a vector index is decided by
:data:`EmbeddingGeometry.INDEX_LABELS`, read by the bootstrap sync
(``services_bootstrap/compose.py``) and by ``scripts/create_vector_indexes.py``.
This module asserts both still read it, and that every member is a real
``NeoLabel``: SKUEL030 cannot see through the schema manager's
``f"{label.lower()}_embedding_idx"`` interpolation, and Neo4j answers an unknown
label with an empty index rather than an error — so a typo yields a silent
zero-row index, which is indistinguishable from a missing one.

The set holds what EXISTS, not a chosen minimum. The label-generic semantic /
learning rung can request a domain outside it and degrades silently; that gap is
tracked in ``docs/roadmap/deferred-work.md`` § Label-Generic Vector Rung Has No
Index for Most Domains, which also records the ruling not to narrow this tuple.

Why one constant instead of two lists: ``docs/roadmap/catalog-copies-in-code.md`` § 6.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from core.constants import EmbeddingGeometry
from core.models.enums.neo_labels import NeoLabel

APP_ROOT = Path(__file__).resolve().parents[2]
COMPOSE = APP_ROOT / "services_bootstrap" / "compose.py"
CREATE_SCRIPT = APP_ROOT / "scripts" / "create_vector_indexes.py"

# The three readers of the derived index name — creation, the sync, and query.
_INDEX_NAME_RE = re.compile(r"\{label\.lower\(\)\}_embedding_idx")


@pytest.mark.parametrize("label", EmbeddingGeometry.INDEX_LABELS)
def test_every_vector_index_label_is_a_real_neo_label(label: str) -> None:
    """An unknown label yields an index over nothing, silently."""
    assert NeoLabel.is_valid(label), (
        f"{label!r} in EmbeddingGeometry.INDEX_LABELS is not a NeoLabel member — "
        "Neo4j would create a vector index that can never match a node."
    )


def test_the_label_set_is_not_empty_and_has_no_duplicates() -> None:
    labels = EmbeddingGeometry.INDEX_LABELS
    assert labels, "no vector-index labels — FULL tier would sync no indexes at all"
    assert len(set(labels)) == len(labels), f"duplicate label: {labels}"


def test_the_base_entity_label_carries_an_index() -> None:
    """``Entity`` is the cross-domain index; without it semantic search is blind.

    Named explicitly because it is the one member whose absence degrades a
    feature silently rather than removing it — ``db.index.vector.queryNodes``
    on a missing index returns nothing, which reads as "no similar entities".
    """
    assert NeoLabel.ENTITY.value in EmbeddingGeometry.INDEX_LABELS


@pytest.mark.parametrize(
    ("path", "what"),
    [(COMPOSE, "the bootstrap vector-index sync"), (CREATE_SCRIPT, "create_vector_indexes.py")],
    ids=["compose", "script"],
)
def test_both_importers_read_the_constant(path: Path, what: str) -> None:
    """Neither side may re-grow its own list."""
    source = path.read_text(encoding="utf-8")
    assert "EmbeddingGeometry.INDEX_LABELS" in source, (
        f"{what} no longer reads EmbeddingGeometry.INDEX_LABELS — if it has its own "
        "label list again, that is the two-lists-two-values state this constant removed."
    )


def test_index_names_are_derived_the_same_way_on_both_sides() -> None:
    """Creation and query must compute the index name identically.

    They do it by the same expression in two files; if either stops, an index is
    created under one name and queried under another, and the failure is an empty
    result set rather than an error.
    """
    schema_manager = (
        APP_ROOT / "adapters" / "persistence" / "neo4j" / "neo4j_schema_manager.py"
    ).read_text(encoding="utf-8")
    vector_search = (APP_ROOT / "core" / "services" / "neo4j_vector_search_service.py").read_text(
        encoding="utf-8"
    )
    assert _INDEX_NAME_RE.search(schema_manager), "the schema manager stopped deriving the name"
    assert _INDEX_NAME_RE.search(vector_search), "vector search stopped deriving the name"
