"""
Relationship Models
===================

Models for representing relationships in the knowledge graph.
"""

from .semantic_relationships import (
    RelationshipMetadata,
    SemanticRelationship,
    SemanticRelationshipType,
)

__all__ = [
    "RelationshipMetadata",
    "SemanticRelationship",
    "SemanticRelationshipType",
]
