"""
Semantic Relationship Inference
================================

Utilities for inferring implicit semantic relationships and
calculating semantic distances in knowledge graphs.
"""

from typing import ClassVar

from core.infrastructure.relationships.semantic_relationships import (
    RelationshipMetadata,
    SemanticRelationship,
    SemanticRelationshipType,
)


class RelationshipInferencer:
    """Infers implicit semantic relationships."""

    # Inference rules - using actual enum values from semantic_relationships.py
    # Transitive rules: (A rel B) AND (B rel C) => (A rel C)
    TRANSITIVE_RULES: ClassVar[
        dict[tuple[SemanticRelationshipType, SemanticRelationshipType], SemanticRelationshipType]
    ] = {
        (
            SemanticRelationshipType.REQUIRES_THEORETICAL_UNDERSTANDING,
            SemanticRelationshipType.REQUIRES_THEORETICAL_UNDERSTANDING,
        ): SemanticRelationshipType.REQUIRES_THEORETICAL_UNDERSTANDING,
        (
            SemanticRelationshipType.BUILDS_MENTAL_MODEL,
            SemanticRelationshipType.BUILDS_MENTAL_MODEL,
        ): SemanticRelationshipType.BUILDS_MENTAL_MODEL,
        (
            SemanticRelationshipType.EXTENDS_PATTERN,
            SemanticRelationshipType.EXTENDS_PATTERN,
        ): SemanticRelationshipType.EXTENDS_PATTERN,
        (
            SemanticRelationshipType.PROVIDES_FOUNDATION_FOR,
            SemanticRelationshipType.PROVIDES_FOUNDATION_FOR,
        ): SemanticRelationshipType.PROVIDES_FOUNDATION_FOR,
    }

    @classmethod
    def infer_relationships(
        cls, existing: list[SemanticRelationship]
    ) -> list[SemanticRelationship]:
        """Infer new relationships from existing ones."""
        inferred = []
        seen_pairs = set()  # Track what we've already inferred

        # Check all pairs for transitive relationships
        for rel1 in existing:
            for rel2 in existing:
                # Check if rel1's object is rel2's subject (transitivity: A->B, B->C => A->C)
                if rel1.object_uid == rel2.subject_uid:
                    rule_key = (rel1.predicate, rel2.predicate)

                    # Check if this is a valid transitive rule
                    if rule_key in cls.TRANSITIVE_RULES:
                        # Create unique key to avoid duplicates
                        inference_key = (
                            rel1.subject_uid,
                            rel2.object_uid,
                            cls.TRANSITIVE_RULES[rule_key],
                        )

                        if inference_key not in seen_pairs and rel1.subject_uid != rel2.object_uid:
                            seen_pairs.add(inference_key)

                            inferred_rel = SemanticRelationship(
                                subject_uid=rel1.subject_uid,
                                predicate=cls.TRANSITIVE_RULES[rule_key],
                                object_uid=rel2.object_uid,
                                metadata=RelationshipMetadata(
                                    confidence=min(
                                        rel1.metadata.confidence, rel2.metadata.confidence
                                    )
                                    * 0.8,
                                    source="inference",
                                    notes=f"Transitive: {rel1.subject_uid} -> {rel1.object_uid} -> {rel2.object_uid}",
                                ),
                            )
                            inferred.append(inferred_rel)

        return inferred

    @classmethod
    def _apply_inference_rule(
        cls, rel1: SemanticRelationship, rel2: SemanticRelationship
    ) -> SemanticRelationshipType | None:
        """Apply inference rules to two relationships."""
        # Check if the object of rel1 is the subject of rel2 (transitivity)
        if rel1.object_uid == rel2.subject_uid:
            rule_key = (rel1.predicate, rel2.predicate)
            if rule_key in cls.TRANSITIVE_RULES:
                return cls.TRANSITIVE_RULES[rule_key]

        return None

    @classmethod
    def calculate_semantic_distance(cls, rel_path: list[SemanticRelationship]) -> float:
        """Calculate semantic distance along a relationship path."""
        if not rel_path:
            return float("inf")

        # Start with base distance
        distance = 0.0

        for rel in rel_path:
            # Add distance based on relationship type
            rel_weight = cls._get_relationship_weight(rel.predicate)

            # Adjust by confidence
            confidence_factor = 2.0 - rel.metadata.confidence  # Lower confidence = higher distance

            distance += rel_weight * confidence_factor

        return distance

    @classmethod
    def _get_relationship_weight(cls, rel_type: SemanticRelationshipType) -> float:
        """Get weight for a relationship type."""
        # Strong relationships have lower weight (shorter distance)
        weights = {
            SemanticRelationshipType.REQUIRES_THEORETICAL_UNDERSTANDING: 1.0,
            SemanticRelationshipType.BUILDS_MENTAL_MODEL: 1.2,
            SemanticRelationshipType.SHARES_PRINCIPLE_WITH: 2.0,
            SemanticRelationshipType.COMPLEMENTS: 3.0,
            SemanticRelationshipType.CONTRASTS_WITH: 4.0,
        }

        return weights.get(rel_type, 2.5)  # Default weight
