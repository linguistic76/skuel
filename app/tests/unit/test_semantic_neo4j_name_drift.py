"""Drift test for the semantic-annotation authority rule (roadmap Phase 1).

`RelationshipName` owns every string that reaches Neo4j. `SemanticRelationshipType`
is a semantic annotation layer over it: each of the 81 members maps to exactly one
`RelationshipName` via `to_neo4j_name()`, and the precise namespaced predicate is
preserved as the `semantic_type` edge property at write time. These tests fail
closed if a future member is added without a mapping (KeyError) or if the mapping
ever emits a raw string that is not registered vocabulary.

See: docs/roadmap/semantic-relationship-layer.md
"""

from __future__ import annotations

from core.config.unified_config import _default_relationship_type_weights
from core.infrastructure.relationships.semantic_relationships import (
    SEMANTIC_TO_RELATIONSHIP_NAME,
    SemanticRelationshipType,
)
from core.models.relationship_names import RelationshipName


class TestSemanticToNeo4jNameDrift:
    def test_every_member_maps_to_a_relationship_name(self) -> None:
        """No SemanticRelationshipType may emit unregistered vocabulary."""
        for member in SemanticRelationshipType:
            emitted = member.to_neo4j_name()
            assert isinstance(emitted, RelationshipName), (
                f"{member.name}.to_neo4j_name() returned {emitted!r} "
                f"({type(emitted).__name__}), not a RelationshipName"
            )

    def test_mapping_covers_exactly_the_enum(self) -> None:
        """Mapping keys are exactly the 81 members — no gaps, no strays."""
        assert set(SEMANTIC_TO_RELATIONSHIP_NAME) == set(SemanticRelationshipType)

    def test_no_member_missing_from_mapping(self) -> None:
        """A member added without a mapping entry raises KeyError, not silent drift."""
        for member in SemanticRelationshipType:
            # Would raise KeyError if unmapped — the guard the whole rule rests on.
            assert member in SEMANTIC_TO_RELATIONSHIP_NAME

    def test_intra_enum_collisions_stay_distinguishable(self) -> None:
        """Members that collapse onto one edge name differ by their namespaced value.

        cross:related_to and moc:related_to both emit RELATED_TO; concept:child_of
        and moc:child_of both emit RELATED_TO. The `semantic_type` property (the
        enum .value) is what keeps them distinct in the graph.
        """
        s = SemanticRelationshipType
        for a, b in [
            (s.RELATED_TO, s.RELATED_MOC),
            (s.CHILD_OF, s.CHILD_MOC_OF),
        ]:
            assert a.to_neo4j_name() == b.to_neo4j_name()
            assert a.value != b.value

    def test_weight_keys_are_valid_semantic_values(self) -> None:
        """The vector-search weight table keys on namespaced predicate values.

        A typo would silently fall through to the 0.5 default, so pin the keys to
        real SemanticRelationshipType values.
        """
        valid = {m.value for m in SemanticRelationshipType}
        for key in _default_relationship_type_weights():
            assert key in valid, f"weight key {key!r} is not a SemanticRelationshipType value"
