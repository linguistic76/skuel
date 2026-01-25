"""
Semantic Models
===============

Models for semantic relationships and edge metadata (Phase 4).
"""

from .edge_metadata import (
    EdgeMetadata,
    create_ai_inferred_metadata,
    create_enables_metadata,
    create_prerequisite_metadata,
    create_related_metadata,
)

__all__ = [
    "EdgeMetadata",
    "create_ai_inferred_metadata",
    "create_enables_metadata",
    "create_prerequisite_metadata",
    "create_related_metadata",
]
