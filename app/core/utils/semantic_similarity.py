"""
Semantic Similarity Calculations
=================================

Utilities for calculating semantic similarity between entities
based on their relationships and characteristics.
"""

from core.infrastructure.relationships.semantic_relationships import (
    SemanticRelationship,
    SemanticRelationshipType,
)


class SemanticSimilarity:
    """Calculate semantic similarity between entities."""

    @staticmethod
    def calculate_similarity(
        entity1_relations: list[SemanticRelationship], entity2_relations: list[SemanticRelationship]
    ) -> float:
        """
        Calculate semantic similarity based on relationships.

        Returns a score between 0 and 1.
        """
        if not entity1_relations or not entity2_relations:
            return 0.0

        # Extract relationship fingerprints
        fingerprint1 = SemanticSimilarity._get_fingerprint(entity1_relations)
        fingerprint2 = SemanticSimilarity._get_fingerprint(entity2_relations)

        # Calculate Jaccard similarity
        intersection = fingerprint1.intersection(fingerprint2)
        union = fingerprint1.union(fingerprint2)

        if not union:
            return 0.0

        jaccard = len(intersection) / len(union)

        # Weight by relationship importance
        return SemanticSimilarity._weight_similarity(entity1_relations, entity2_relations, jaccard)

    @staticmethod
    def _get_fingerprint(relations: list[SemanticRelationship]) -> set[str]:
        """Get relationship fingerprint for an entity."""
        fingerprint = set()

        for rel in relations:
            # Include relationship type and target
            fingerprint.add(f"{rel.predicate.value}:{rel.object_uid}")

            # Include inverse if available
            inverse = rel.predicate.get_inverse()
            if inverse:
                fingerprint.add(f"{inverse.value}:{rel.subject_uid}")

        return fingerprint

    @staticmethod
    def _weight_similarity(
        relations1: list[SemanticRelationship],
        relations2: list[SemanticRelationship],
        base_similarity: float,
    ) -> float:
        """Weight similarity by relationship importance."""
        # Find common relationship types
        types1 = {r.predicate for r in relations1}
        types2 = {r.predicate for r in relations2}
        common_types = types1.intersection(types2)

        if not common_types:
            return base_similarity * 0.5  # Penalize no common types

        # Weight by importance of common relationship types
        importance_weights = {
            SemanticRelationshipType.REQUIRES_THEORETICAL_UNDERSTANDING: 2.0,
            SemanticRelationshipType.BUILDS_MENTAL_MODEL: 1.8,
            SemanticRelationshipType.APPLIES_KNOWLEDGE_TO: 1.5,
            SemanticRelationshipType.SHARES_PRINCIPLE_WITH: 1.2,
            SemanticRelationshipType.COMPLEMENTS: 1.0,
        }

        total_weight = 0.0
        for rel_type in common_types:
            weight = importance_weights.get(rel_type, 1.0)
            total_weight += weight

        avg_weight = total_weight / len(common_types) if common_types else 1.0

        # Scale similarity by average weight
        return min(1.0, base_similarity * avg_weight)
