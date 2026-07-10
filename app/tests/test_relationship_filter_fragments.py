"""
Tests for build_relationship_filter_fragments - Below-Boundary Cypher Authoring
================================================================================

These fragments were relocated from ``core/models/search_request.py``
(``to_graph_patterns``) to below the hexagonal boundary (ADR-044). The core
model now passes a ``RelationshipFilters`` intent down; the Cypher is authored
here. These tests pin the flag→fragment mapping.

The signatures pin the 2026-07 remapped vocabulary (the original hand-authored
edges — PRACTICES, ADHERES_TO, EMBODIES_KNOWLEDGE, ENABLES_LEARNING,
PURSUING_GOAL — had no write paths; see
tests/unit/adapters/test_relationship_filter_vocabulary.py and
tests/integration/test_smart_filter_fragments.py for the guards).
"""

from dataclasses import fields

import pytest

from adapters.persistence.neo4j.query import build_relationship_filter_fragments
from adapters.persistence.neo4j.query.cypher import (
    build_relationship_filter_fragments as build_via_cypher_pkg,
)
from core.models.relationship_filters import RelationshipFilters

# Maps each flag to a distinctive substring of its expected Cypher fragment.
FLAG_SIGNATURES: dict[str, str] = {
    "ready_to_learn": "MATCH (entity)-[:REQUIRES_KNOWLEDGE]->(prereq:Entity)",
    "builds_on_mastered": "(mastered)-[:ENABLES_KNOWLEDGE|RELATED_TO]-(entity)",
    "in_active_path": "[:USES_KU|TRAINS_KU|CONTAINS_KNOWLEDGE]->(entity)",
    "supports_goals": "[:OWNS]->(goal:Goal)",
    "builds_on_habits": "[:OWNS]->(habit:Habit)",
    # datetime() coercion is load-bearing: updated_at is a DTO-written ISO
    # string on most nodes; without it the comparison is null.
    "applied_in_tasks": "datetime(task.updated_at)",
    "aligned_with_principles": "[:GROUNDED_IN_KNOWLEDGE]->(entity)",
    "next_logical_step": "[:ENABLES_KNOWLEDGE]->(entity)",
    "not_yet_viewed": "[:VIEWED|IN_PROGRESS|MASTERED]->(entity)",
    "viewed_not_mastered": "[:VIEWED|IN_PROGRESS]->(entity)",
    "ready_to_review": "[m:MASTERED]->(entity)",
}


class TestRelationshipFilterFragments:
    """Validate the flag→Cypher-fragment mapping authored below the boundary."""

    def test_no_filters_returns_empty(self) -> None:
        """An empty intent produces no WHERE-clause fragments."""
        assert build_relationship_filter_fragments(RelationshipFilters()) == []
        assert bool(RelationshipFilters()) is False

    def test_signatures_cover_every_flag(self) -> None:
        """Guard against adding a RelationshipFilters flag without a fragment."""
        flag_names = {f.name for f in fields(RelationshipFilters)}
        assert flag_names == set(FLAG_SIGNATURES)

    @pytest.mark.parametrize("flag", list(FLAG_SIGNATURES))
    def test_single_flag_emits_its_fragment(self, flag: str) -> None:
        """Each active flag emits exactly one fragment containing its signature."""
        fragments = build_relationship_filter_fragments(RelationshipFilters(**{flag: True}))
        assert len(fragments) == 1
        assert FLAG_SIGNATURES[flag] in fragments[0]

    @pytest.mark.parametrize("flag", list(FLAG_SIGNATURES))
    def test_user_uid_is_a_query_param_placeholder(self, flag: str) -> None:
        """Fragments reference $user_uid (filled at execution), never a literal user."""
        fragments = build_relationship_filter_fragments(RelationshipFilters(**{flag: True}))
        assert "$user_uid" in fragments[0]

    @pytest.mark.parametrize("flag", list(FLAG_SIGNATURES))
    def test_anchor_is_entity_not_ku(self, flag: str) -> None:
        """Fragments anchor on (entity) — the node faceted_search_raw binds — not (ku)."""
        fragments = build_relationship_filter_fragments(RelationshipFilters(**{flag: True}))
        assert "(ku)" not in fragments[0]

    def test_all_flags_emit_in_field_order(self) -> None:
        """Every flag active → all fragments, ordered to match field declaration order."""
        all_on = RelationshipFilters(**dict.fromkeys(FLAG_SIGNATURES, True))
        fragments = build_relationship_filter_fragments(all_on)
        assert len(fragments) == len(FLAG_SIGNATURES)

        ordered_flags = [f.name for f in fields(RelationshipFilters)]
        for fragment, flag in zip(fragments, ordered_flags, strict=True):
            assert FLAG_SIGNATURES[flag] in fragment

    def test_reexported_from_query_package_and_cypher_package(self) -> None:
        """The builder is importable from both the query and cypher packages."""
        assert build_relationship_filter_fragments is build_via_cypher_pkg
