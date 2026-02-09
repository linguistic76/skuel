"""
Lateral Relationships - Core Graph Modeling
============================================

Fundamental graph modeling for explicit lateral relationships between entities.

This module provides the core infrastructure for managing relationships between
entities at the same or related hierarchical levels (siblings, cousins, dependencies,
semantic connections, etc.).

Philosophy:
    "Lateral relationships are as fundamental as hierarchical ones. They capture
    the rich semantics of how entities relate beyond parent-child structure."

Components:
    - LateralRelationshipService: Core domain-agnostic service (with ownership verification)
    - LateralRelationshipSpec: Metadata registry (in relationship_registry.py)

See: /docs/architecture/LATERAL_RELATIONSHIPS_CORE.md
"""

from core.services.lateral_relationships.lateral_relationship_service import (
    LateralRelationshipService,
)

__all__ = ["LateralRelationshipService"]
